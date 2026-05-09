import os
import random
import time
import importlib
import zipfile
import re
from io import BytesIO
import telebot
from telebot.types import InputMediaDocument
from datetime import datetime, timezone, timedelta

BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"
ADMIN_ID = 6042965834

PRICE_SPLIT = 0.0004
PRICE_INSERT = 0.0001
PRICE_MERGE = 0.0002
PRICE_DEDUP = 0.0002
BATCH_SIZE = 10

# 广播全局缓存
broad_img = None
broad_text = ""

# 随机三字中文名
XING = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛"
MING1 = "伟俊佳浩宇泽晨欣雨轩博文铭凯艺霖梓睿一诺嘉航沐辰"
MING2 = "杰豪琳雪婷芳莹瑞阳鑫鹏佳怡涵悦彤诗雅泽安诺"

def get_rand_3_name():
    return random.choice(XING) + random.choice(MING1) + random.choice(MING2)

user_file = {}
users = {}
# 卡密格式：{卡密:{"money":金额,"expire_time":过期时间戳}}
cards = {}
user_merge = {}
user_state = {}
user_insert = {}
log_user = {}
log_recharge = {}

def get_user(uid):
    if uid not in users:
        users[uid] = {"balance": 0.0, "mode":"TXT", "line":100}
    return users[uid]

def is_admin(uid):
    return uid == ADMIN_ID

def add_log(uid, txt, num, cost):
    t = get_beijing_time_str()
    log_user[uid] = log_user.get(uid,[]) + [f"[{t}]用户{uid}｜{txt}｜{num}行｜扣费{cost:.4f}｜剩余余额{get_user(uid)['balance']:.4f}"]

def add_rc(uid,money):
    t = get_beijing_time_str()
    log_recharge[uid] = log_recharge.get(uid,[]) + [f"[{t}]用户{uid}｜后台批量充值+{money:.4f}｜剩余余额{get_user(uid)['balance']:.4f}"]

# 精准北京时间
def get_beijing_time_str():
    beijing_tz = timezone(timedelta(hours=8))
    beijing_now = datetime.now(beijing_tz)
    return beijing_now.strftime("%Y-%m-%d %H:%M:%S")

# 获取当前时间戳
def get_now_timestamp():
    return int(time.time())

# 清洗空白行
def clean_empty_line(text):
    lines = text.splitlines()
    new_lines = []
    for line in lines:
        strip_line = line.strip()
        if strip_line:
            new_lines.append(strip_line)
    return "\n".join(new_lines)

# 解压ZIP提取TXT
def extract_txt_from_zip(zip_bytes):
    all_text = ""
    try:
        zip_file = zipfile.ZipFile(BytesIO(zip_bytes))
        for file_name in zip_file.namelist():
            if file_name.lower().endswith(".txt") and not file_name.endswith("/"):
                data = zip_file.read(file_name)
                txt = data.decode("utf-8", "ignore")
                all_text += txt + "\n"
        zip_file.close()
        return clean_empty_line(all_text)
    except Exception as e:
        return ""

bot = telebot.TeleBot(BOT_TOKEN, skip_pending=True)

# 主菜单
def menu(uid):
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        telebot.types.InlineKeyboardButton(f"📄格式：{get_user(uid)['mode']}",callback_data="mode"),
        telebot.types.InlineKeyboardButton(f"💰分割每份{get_user(uid)['line']}",callback_data="line")
    )
    kb.add(
        telebot.types.InlineKeyboardButton("👤个人中心",callback_data="user"),
        telebot.types.InlineKeyboardButton("💳卡密充值",callback_data="user_cdk")
    )
    kb.add(
        telebot.types.InlineKeyboardButton("📎文件合并",callback_data="hebing"),
        telebot.types.InlineKeyboardButton("🧹号码去重",callback_data="quchong")
    )
    if is_admin(uid):
        kb.add(
            telebot.types.InlineKeyboardButton("🔧管理后台",callback_data="admin")
        )
    return kb

# 个人中心菜单
def user_menu(uid):
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        telebot.types.InlineKeyboardButton("💰我的余额",callback_data="bal"),
        telebot.types.InlineKeyboardButton("💳充值记录",callback_data="rclog")
    )
    kb.add(
        telebot.types.InlineKeyboardButton("📜消费明细",callback_data="uselog"),
        telebot.types.InlineKeyboardButton("🔙返回主页",callback_data="back")
    )
    return kb

# 管理员后台
def admin_kb():
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(telebot.types.InlineKeyboardButton("➕单人手动加余额",callback_data="addbal"),telebot.types.InlineKeyboardButton("➖单人扣余额",callback_data="subbal"))
    kb.add(telebot.types.InlineKeyboardButton("🎟️批量生成卡密",callback_data="card"),telebot.types.InlineKeyboardButton("📊全部用户余额总表",callback_data="ulist"))
    kb.add(telebot.types.InlineKeyboardButton("📋全体用户充值总记录",callback_data="all_rc_log"),telebot.types.InlineKeyboardButton("📋全体用户消费记录",callback_data="all_use_log"))
    kb.add(telebot.types.InlineKeyboardButton("📢全站广播",callback_data="broad"),telebot.types.InlineKeyboardButton("🔥批量加用户余额",callback_data="batch_addbal"))
    kb.add(telebot.types.InlineKeyboardButton("🎫查看所有有效卡密",callback_data="check_all_cdk"))
    kb.add(telebot.types.InlineKeyboardButton("🗑️作废指定卡密",callback_data="del_cdk"),telebot.types.InlineKeyboardButton("📤导出全部有效卡密",callback_data="export_cdk"))
    kb.add(telebot.types.InlineKeyboardButton("🔙返回",callback_data="back"))
    return kb

def select_menu():
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        telebot.types.InlineKeyboardButton("⚡插入雷号分割",callback_data="ins"),
        telebot.types.InlineKeyboardButton("📄纯净直接分割",callback_data="noins")
    )
    return kb

@bot.message_handler(commands=['start'])
def s(m):
    uid = m.from_user.id
    get_user(uid)
    user_state[uid]="idle"
    now_time = get_beijing_time_str()
    bot.send_message(m.chat.id,f"🤖工具机器人运行正常✅\n当前北京时间：{now_time}\n支持TXT / VCF互转｜TXT/ZIP自动解析",reply_markup=menu(uid))

@bot.message_handler(func=lambda msg: msg.text.strip() == "取消")
def cancel_all(msg):
    uid = msg.from_user.id
    user_state[uid] = "idle"
    user_merge[uid] = ""
    if uid in user_insert:
        del user_insert[uid]
    if uid in user_file:
        del user_file[uid]
    bot.send_message(msg.chat.id,"✅已清空所有操作缓存，请重新上传文件")

# 文件合并
@bot.message_handler(func=lambda m:user_state.get(m.from_user.id)=="hebing" and m.text=="完成")
def heb(m):
    uid=m.from_user.id
    if len(user_merge[uid])==0:
        bot.send_message(m.chat.id,"❌你还没有上传任何文件")
        return
    txt="\n".join(user_merge[uid])
    ls=len(txt.splitlines())
    fee=ls*PRICE_MERGE
    u=get_user(uid)
    if u['balance']<fee:
        bot.send_message(m.chat.id,"❌余额不足")
        return
    
    u['balance']-=fee
    add_log(uid,"文件合并",ls,fee)
    
    if u['mode']=="VCF":
        vcf_all = ""
        for phone in txt.splitlines():
            name = get_rand_3_name()
            vcf_all += f"""BEGIN:VCARD
VERSION:3.0
N:{name};;;
FN:{name}
TEL;TYPE=CELL:{phone}
END:VCARD
"""
        bio=BytesIO(vcf_all.encode())
        bio.name="合并通讯录.vcf"
    else:
        bio=BytesIO(txt.encode())
        bio.name="合并成品.txt"
    bot.send_document(m.chat.id,bio)
    user_state[uid]="idle"
    bot.send_message(m.chat.id,f"✅合并完成｜共{ls}行｜扣费{fee:.4f}元")

# 管理员指令
@bot.message_handler(func=lambda msg: is_admin(msg.from_user.id))
def admin_cmd(msg):
    txt = msg.text.strip()
    if txt.startswith("查询用户充值记录"):
        try:
            uid = int(txt.replace("查询用户充值记录","").strip())
            log = log_recharge.get(uid,["该用户暂无任何充值记录"])
            bot.send_message(msg.chat.id,f"📋 用户{uid} 充值明细\n"+"\n".join(log)[:4000])
        except:
            bot.send_message(msg.chat.id,"❌格式：查询用户充值记录 用户ID")
    elif txt.startswith("查询用户消费记录"):
        try:
            uid = int(txt.replace("查询用户消费记录","").strip())
            log = log_user.get(uid,["该用户暂无消费记录"])
            bot.send_message(msg.chat.id,f"📋 用户{uid} 消费明细\n"+"\n".join(log)[:4000])
        except:
            bot.send_message(msg.chat.id,"❌格式：查询用户消费记录 用户ID")

# 接收广播图片
@bot.message_handler(content_types=['photo'])
def broadcast_photo(msg):
    if not is_admin(msg.from_user.id):return
    global broad_img
    broad_img = msg.photo[-1].file_id
    bot.send_message(msg.chat.id,"✅图片已保存，请发送广播文字内容")

# 图文全站广播
def admin_broadcast(msg):
    global broad_img, broad_text
    broad_text = msg.text
    user_list = list(users.keys())
    total_user = len(user_list)
    send_count = 0
    bot.send_message(msg.chat.id,f"📢开始全站广播，总用户：{total_user}位")
    for uid in user_list:
        try:
            if broad_img:
                bot.send_photo(uid, broad_img, caption=broad_text)
            else:
                bot.send_message(chat_id=uid, text=broad_text)
            send_count += 1
        except:
            continue
    bot.send_message(msg.chat.id,f"🎉全站广播全部结束\n成功送达总数：{send_count} 位用户")
    
    broad_img = None
    broad_text = ""

temp_split_data = {}

@bot.callback_query_handler(func=lambda c:True)
def cb(c):
    bot.answer_callback_query(c.id)
    uid = c.from_user.id
    cid = c.message.chat.id
    d = c.data

    if d=="mode":
        u=get_user(uid)
        u['mode']="VCF" if u['mode']=="TXT" else "TXT"
        bot.edit_message_text("✅格式已切换",cid,c.message.message_id,reply_markup=menu(uid))
    elif d=="line":
        bot.send_message(cid,"📏请输入每份分割行数")
        bot.register_next_step_handler(c.message,set_line)
    elif d=="user_cdk":
        bot.send_message(cid,"💳请粘贴你的卡密兑换")
        bot.register_next_step_handler(c.message,use_cdk)
    elif d=="user":
        bot.edit_message_text("👤个人中心",cid,c.message.message_id,reply_markup=user_menu(uid))
    elif d=="bal":
        bot.send_message(cid,f"💰您当前余额：{get_user(uid)['balance']:.4f}元")
    bot.answer_callback_query(c.id)
    elif d=="rclog"):
        txt="\n".join(log_recharge.get(uid,["暂无充值记录"]))
        bot.send_message(cid,txt[:4000])
    elif d=="uselog":
        txt="\n".join(log_user.get(uid,["暂无消费记录"]))
        bot.send_message(cid,txt[:4000])
    elif d=="back":
        bot.edit_message_text("🏠机器人主菜单",cid,c.message.message_id,reply_markup=menu(uid))
    elif d=="hebing":
        user_merge[uid]=[]
        user_state[uid]="hebing"
        bot.send_message(cid,"📎请依次发送文件，全部发完回复：完成")
    elif d=="quchong":
        user_state[uid]="quchong"
        bot.send_message(cid,"🧹请发送需要去重的号码文件")
    elif d=="admin" and is_admin(uid):
        bot.edit_message_text("🔧管理员后台控制面板",cid,c.message.message_id,reply_markup=admin_kb())

    # 修复卡密生成按钮
    elif d=="card" and is_admin(uid):
        bot.send_message(cid,"🎟️请输入卡密有效期【天数】")
        bot.register_next_step_handler(c.message, input_card_day)

    elif d=="del_cdk" and is_admin(uid):
        bot.send_message(cid,"🗑️请发送要作废删除的完整卡密")
        bot.register_next_step_handler(c.message, del_single_cdk)

    elif d=="export_cdk" and is_admin(uid):
        now = get_now_timestamp()
        export_text = "卡密,面值(元),过期时间\n"
        for cdk,info in cards.items():
            if info['expire_time'] > now:
                time_str = datetime.fromtimestamp(info['expire_time']).strftime("%Y-%m-%d %H:%M:%S")
                export_text += f"{cdk},{info['money']},{time_str}\n"
        if export_text == "卡密,面值(元),过期时间\n":
            bot.send_message(cid,"❌暂无未过期有效卡密可导出")
        else:
            bio = BytesIO(export_text.encode("utf-8-sig"))
            bio.name = "全部有效卡密清单.txt"
            bot.send_document(cid,bio)

    elif d=="check_all_cdk" and is_admin(uid):
        now = get_now_timestamp()
        msg = "🎫所有未使用·未过期有效卡密\n"
        has = False
        for cdk,info in cards.items():
            if info['expire_time'] > now:
                has=True
                expire_str = datetime.fromtimestamp(info['expire_time']).strftime("%Y-%m-%d %H:%M:%S")
                msg+=f"卡密：{cdk}\n面值：{info['money']:.4f}元\n过期时间：{expire_str}\n————————\n"
        if not has:
            bot.send_message(cid,"暂无任何有效未使用卡密")
        else:
            bot.send_message(cid,msg[:4000])

    elif d=="ulist" and is_admin(uid):
        msg = "📊全站所有用户余额清单\n"
        for u_id,info in users.items():
            msg+=f"用户ID:{u_id} | 余额:{info['balance']:.4f}\n"
        bot.send_message(cid,msg[:4000])
    elif d=="all_rc_log" and is_admin(uid):
        all_log = []
        for u_id,logs in log_recharge.items():
            all_log.extend([f"【用户{u_id}】"+x for x in logs])
        if not all_log:all_log=["暂无充值记录"]
        bot.send_message(cid,"📋全体用户充值总记录\n"+"\n".join(all_log[:4000]))
    elif d=="all_use_log" and is_admin(uid):
        all_log = []
        for u_id,logs in log_user.items():
            all_log.extend([f"【用户{u_id}】"+x for x in logs])
        if not all_log:all_log=["暂无消费记录"]
        bot.send_message(cid,"📋全体用户消费总记录\n"+"\n".join(all_log[:4000]))
    elif d=="broad" and is_admin(uid):
        bot.send_message(cid,"📢请先发送广播图片，再发送文字内容")
        bot.register_next_step_handler(c.message, admin_broadcast)
    elif d=="batch_addbal" and is_admin(uid):
        bot.send_message(cid,"🔥请批量粘贴用户数据\n格式：\n用户ID1 金额\n用户ID2 金额\n一行一个")
        bot.register_next_step_handler(c.message, batch_add_user_balance)
    elif d=="ins":
        if uid not in user_file:
            return bot.send_message(cid,"📭文件已过期，请重新上传")
        bot.send_message(cid,"⚡每份插入几条雷号？")
        bot.register_next_step_handler(c.message,ins_num)
    elif d=="noins":
        if uid not in user_file:
            return bot.send_message(cid,"📭文件已过期，请重新上传")
        temp_split_data[uid] = user_file[uid]['txt']
        bot.send_message(cid,"📄请输入自定义文件名")
        bot.register_next_step_handler(c.message,lambda m:split_send_clean(cid,uid,temp_split_data[uid],m.text))

# 作废单张卡密
def del_single_cdk(msg):
    cdk = msg.text.strip()
    if cdk in cards:
        del cards[cdk]
        bot.send_message(msg.chat.id,f"✅卡密 {cdk} 已成功作废删除")
    else:
        bot.send_message(msg.chat.id,"❌未找到该卡密，可能已被使用/过期")

# 输入有效期天数
def input_card_day(msg):
    try:
        day = int(msg.text.strip())
        bot.send_message(msg.chat.id,f"✅有效期{day}天，请输入卡密面值金额")
        bot.register_next_step_handler(msg, lambda m:make_card(m,day))
    except:
        bot.send_message(msg.chat.id,"❌请输入纯数字天数")

# 生成卡密
def make_card(msg,day):
    try:
        money = float(msg.text)
        import string
        expire = get_now_timestamp() + day * 86400
        cdk = "TK"+''.join(random.choices(string.ascii_uppercase+string.digits,k=12))
        cards[cdk] = {"money":money,"expire_time":expire}
        expire_str = datetime.fromtimestamp(expire).strftime("%Y-%m-%d %H:%M:%S")
        bot.send_message(msg.chat.id,f"✅卡密生成成功\n{cdk}\n面值：{money:.4f}元\n过期时间：{expire_str}")
    except:
        bot.send_message(msg.chat.id,"请输入正确金额")

# 卡密兑换
def use_cdk(m):
    cdk=m.text.strip()
    now = get_now_timestamp()
    if cdk not in cards:
        bot.send_message(m.chat.id,"❌卡密无效、已使用、已作废或已过期")
        return
    info = cards[cdk]
    if info['expire_time'] < now:
        del cards[cdk]
        bot.send_message(m.chat.id,"❌该卡密已过期，无法充值")
        return
    money = info['money']
    cards.pop(cdk)
    get_user(m.from_user.id)['balance']+=money
    add_rc(m.from_user.id,money)
    bot.send_message(m.chat.id,f"✅充值到账{money:.4f}元\n余额：{get_user(m.from_user.id)['balance']:.4f}")

def batch_add_user_balance(msg):
    if not is_admin(msg.from_user.id):return
    lines = msg.text.strip().splitlines()
    success = 0
    fail = []
    for line in lines:
        line = line.strip()
        if not line:continue
        try:
            uid, money = line.split()
            uid = int(uid)
            money = float(money)
            get_user(uid)['balance']+=money
            add_rc(uid, money)
            success +=1
        except:
            fail.append(line)
    reply = f"✅批量充值完成\n成功：{success} 个用户"
    if fail:
        reply += f"\n❌格式错误跳过：{len(fail)} 条"
    bot.send_message(msg.chat.id, reply)

def admin_add_balance(msg):
    try:
        u_id,money = msg.text.split()
        uid=int(u_id)
        money=float(money)
        get_user(uid)['balance']+=money
        add_rc(uid,money)
        bot.send_message(msg.chat.id,f"✅成功充值用户{u_id}：{money:.4f}元")
    except:
        bot.send_message(msg.chat.id,"格式错误：用户ID 金额")

def admin_sub_balance(msg):
    try:
        u_id,money = msg.text.split()
        u_id=int(u_id)
        money=float(money)
        get_user(u_id)['balance']-=money
        bot.send_message(msg.chat.id,f"✅成功扣除用户{u_id}：{money:.4f}元")
    except:
        bot.send_message(msg.chat.id,"格式错误：用户ID 金额")

def set_line(m):
    try:
        get_user(m.from_user.id)['line']=int(m.text)
        bot.send_message(m.chat.id,"✅分割行数设置成功")
    except:
        bot.send_message(m.chat.id,"❌请输入纯数字")

def ins_num(m):
    uid=m.from_user.id
    try:
        num=int(m.text)
        user_insert[uid]={"num":num,"txt":user_file[uid]['txt']}
        bot.send_message(m.chat.id,"⚡请发送雷号，一行一个")
        bot.register_next_step_handler(m, ins_phone)
    except:
        bot.send_message(m.chat.id,"❌请输入纯数字，发取消重置")

def ins_phone(m):
    uid=m.from_user.id
    if uid not in user_insert:
        return bot.send_message(m.chat.id,"❌流程失效，请重新上传")
    phones=re.findall(r"\d+",m.text)
    if len(phones)==0:
        bot.send_message(m.chat.id,"❌未识别号码，请重发")
        bot.register_next_step_handler(m, ins_phone)
        return
    user_insert[uid]['phone']=phones
    bot.send_message(m.chat.id,"📄请输入文件前缀名")
    bot.register_next_step_handler(m, ins_done)

# 插雷分包
def ins_done(m):
    uid=m.from_user.id
    info=user_insert[uid]
    lines=[x for x in info['txt'].splitlines() if x]
    total=len(lines)
    fee_split = total * PRICE_SPLIT
    fee_insert = total * PRICE_INSERT
    total_fee = fee_split + fee_insert
    u=get_user(uid)

    if u['balance'] < total_fee:
        return bot.send_message(m.chat.id,"❌余额不足")
    
    u['balance'] -= total_fee
    add_log(uid,"分包+插入雷号",total,total_fee)
    bot.send_message(m.chat.id,f"💸分包{fee_split:.4f}+插雷{fee_insert:.4f}\n合计：{total_fee:.4f}｜剩余：{u['balance']:.4f}")

    chunk = [lines[i:i+u['line']] for i in range(0,total,u['line'])]
    media=[]
    idx=1
    ph_idx=0
    phones = info['phone']
    csv_rows = "分包序号,本行位置,原始号码,插入雷号\n"
    send_total = len(chunk)
    bot.send_message(m.chat.id,f"📦开始发送分包文件，共{send_total}个\n每发送10个暂停3秒")

    for c in chunk:
        chunk_len = len(c)
        insert_count = info['num']
        insert_pos_list = random.sample(range(1, chunk_len+1), insert_count)
        insert_pos_list.sort()
        temp_list = c.copy()
        for pos in insert_pos_list:
            lei = phones[ph_idx % len(phones)]
            temp_list.insert(pos-1, lei)
            csv_rows += f"{idx},{pos},{c[pos-1]},{lei}\n"
            ph_idx += 1

        if u['mode']=="VCF":
            vcf_content = ""
            for phone in temp_list:
                name = get_rand_3_name()
                vcf_content += f"""BEGIN:VCARD
VERSION:3.0
N:{name};;;
FN:{name}
TEL;TYPE=CELL:{phone}
END:VCARD
"""
            filename = f"{m.text}_{idx}.vcf"
            bio=BytesIO(vcf_content.encode())
        else:
            bio=BytesIO("\n".join(temp_list).encode())
            filename = f"{m.text}_{idx}.txt"
        bio.name=filename
        media=media+[InputMediaDocument(bio)]

        if len(media)>=BATCH_SIZE:
            bot.send_media_group(m.chat.id,media)
            bot.send_message(m.chat.id,f"✅已发送分包：{idx-9} ~ {idx}")
            time.sleep(3)
            media=[]
        idx+=1

    if media:
        bot.send_media_group(m.chat.id,media)
    csv_bio = BytesIO(csv_rows.encode("utf-8-sig"))
    csv_bio.name = "雷号插入位置明细.csv"
    bot.send_document(m.chat.id, csv_bio)
    bot.send_message(m.chat.id,f"🎉全部分包文件发送完成\n北京时间：{get_beijing_time_str()}")
    
    del user_file[uid]
    del user_insert[uid]

# 纯净分包
def split_send_clean(cid,uid,txt,name):
    lines=[x for x in txt.splitlines() if x]
    total=len(lines)
    fee=total*PRICE_SPLIT
    u=get_user(uid)
    if u['balance']<fee:return bot.send_message(cid,"❌余额不足")

    u['balance']-=fee
    add_log(uid,f"{u['mode']}纯净分包",total,fee)
    bot.send_message(cid,f"💸扣费：{fee:.4f}元｜剩余：{u['balance']:.4f}")

    chunk = [lines[i:i+u['line']] for i in range(0,total,u['line'])]
    media=[]
    idx=1
    send_total = len(chunk)
    bot.send_message(cid,f"📦开始发送纯净分包，共{send_total}个\n每发送10个暂停3秒")

    for c in chunk:
        if u['mode']=="VCF":
            vcf_txt = ""
            for phone in c:
                name3 = get_rand_3_name()
                vcf_txt += f"BEGIN:VCARD\nVERSION:3.0\nN:{name3};;;\nFN:{name3}\nTEL;TYPE=CELL:{phone}\nEND:VCARD\n\n"
            bio=BytesIO(vcf_txt.encode())
            bio.name=f"{name}_{idx}.vcf"
        else:
            bio=BytesIO("\n".join(c).encode())
            bio.name=f"{name}_{idx}.txt"
        media.append(InputMediaDocument(bio))

        if len(media)>=BATCH_SIZE:
            bot.send_media_group(cid,media)
            bot.send_message(cid,f"✅已发送分包：{idx-9} ~ {idx}")
            time.sleep(3)
            media=[]
        idx+=1

    if media:bot.send_media_group(cid,media)
    bot.send_message(cid,f"🎉纯净分包全部发送完毕\n北京时间：{get_beijing_time_str()}")
    
    if uid in temp_split_data:del temp_split_data[uid]
    if uid in user_file:del user_file[uid]

# 文件上传接收
@bot.message_handler(content_types=['document'])
def doc(m):
    uid=m.from_user.id
    current_state = user_state.get(uid, "idle")
    try:
        file = bot.get_file(m.document.file_id)
        file_bytes = bot.download_file(file.file_path)
        file_name = m.document.file_name.lower()

        if current_state == "hebing":
            if file_name.endswith(".zip"):
                total_txt = extract_txt_from_zip(file_bytes)
                if not total_txt:
                    return bot.send_message(m.chat.id,"❌压缩包里未找到任何TXT文本")
                user_merge[uid].append(total_txt)
            else:
                txt = file_bytes.decode("utf-8","ignore")
                clean_txt = clean_empty_line(txt)
                user_merge[uid].append(clean_txt)
            
            num = len(user_merge[uid])
            bot.send_message(m.chat.id,f"✅已收录第{num}个文件，发完回复：完成")
            return
        
        elif current_state == "quchong":
            if file_name.endswith(".zip"):
                total_txt = extract_txt_from_zip(file_bytes)
                if not total_txt:
                    return bot.send_message(m.chat.id,"❌压缩包里未找到任何TXT文本")
                clean_txt = total_txt
            else:
                txt = file_bytes.decode("utf-8","ignore")
                clean_txt = clean_empty_line(txt)
            
            old_lines = clean_txt.splitlines()
            old_count = len(old_lines)
            new_lines = list(set(old_lines))
            new_count = len(new_lines)
            fee = new_count * PRICE_DEDUP
            
            u = get_user(uid)
            if u['balance'] < fee:
                return bot.send_message(m.chat.id,"❌余额不足")
            
            u['balance'] -= fee
            add_log(uid,f"号码去重",old_count,fee)

            if u['mode']=="VCF":
                out_vcf = ""
                for p in new_lines:
                    n = get_rand_3_name()
                    out_vcf += f"BEGIN:VCARD\nVERSION:3.0\nN:{n};;;\nFN:{n}\nTEL;TYPE=CELL:{p}\nEND:VCARD\n\n"
                bio = BytesIO(out_vcf.encode())
                bio.name = "去重通讯录.vcf"
            else:
                bio = BytesIO("\n".join(new_lines).encode())
                bio.name = "去重成品.txt"
            bot.send_document(m.chat.id, bio)
            bot.send_message(m.chat.id,f"✅去重完成｜原{old_count}｜新{new_count}｜扣费{fee:.4f}元")
            user_state[uid] = "idle"
            return
        
        else:
            if file_name.endswith(".zip"):
                total_txt = extract_txt_from_zip(file_bytes)
                if not total_txt:
                    return bot.send_message(m.chat.id,"❌压缩包里未找到任何TXT文本")
                user_file[uid] = {"txt": total_txt}
                bot.send_message(m.chat.id,"✅ZIP解压完成！\n当前格式："+get_user(uid)['mode'],reply_markup=select_menu())
            else:
                txt = file_bytes.decode("utf-8","ignore")
                clean_txt = clean_empty_line(txt)
                user_file[uid]={"txt":clean_txt}
                bot.send_message(m.chat.id,"📄文件已保存，已清空白行\n当前格式："+get_user(uid)['mode'],reply_markup=select_menu())
    except Exception as e:
        bot.send_message(m.chat.id,f"❌文件读取失败：{str(e)}")

# 防掉线循环
while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"掉线重连: {e}")
        time.sleep(5)
