import os
import random
import time
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

broad_img = None
broad_text = ""

XING = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛"
MING1 = "伟俊佳浩宇泽晨欣雨轩博文铭凯艺霖梓睿一诺嘉航沐辰"
MING2 = "杰豪琳雪婷芳莹瑞阳鑫鹏佳怡涵悦彤诗雅泽安诺"

def get_rand_3_name():
    return random.choice(XING) + random.choice(MING1) + random.choice(MING2)

user_file = {}
users = {}
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

def get_beijing_time_str():
    beijing_tz = timezone(timedelta(hours=8))
    beijing_now = datetime.now(beijing_tz)
    return beijing_now.strftime("%Y-%m-%d %H:%M:%S")

def get_now_timestamp():
    return int(time.time())

def clean_empty_line(text):
    lines = text.splitlines()
    new_lines = []
    for line in lines:
        strip_line = line.strip()
        if strip_line:
            new_lines.append(strip_line)
    return "\n".join(new_lines)

def extract_txt_from_zip(zip_bytes):
    all_text = ""
    try:
        zip_file = zipfile.ZipFile(BytesIO(zip_bytes))
        for file_name in zip_file.namelist():
            if file_name.lower().endswith(".txt") and not file_name.endswith("/"):
                data = zip_file.read(file_name)
                txt = data.decode("utf-8","ignore")
                all_text += txt + "\n"
        zip_file.close()
        return clean_empty_line(all_text)
    except Exception as e:
        return ""

bot = telebot.TeleBot(BOT_TOKEN, skip_pending=True)

def menu(uid):
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(telebot.types.InlineKeyboardButton(f"📄格式：{get_user(uid)['mode']}",callback_data="mode"),telebot.types.InlineKeyboardButton(f"💰分割每份{get_user(uid)['line']}",callback_data="line"))
    kb.add(telebot.types.InlineKeyboardButton("👤个人中心",callback_data="user"),telebot.types.InlineKeyboardButton("💳卡密充值",callback_data="user_cdk"))
    kb.add(telebot.types.InlineKeyboardButton("📎文件合并",callback_data="hebing"),telebot.types.InlineKeyboardButton("🧹号码去重",callback_data="quchong"))
    if is_admin(uid):
        kb.add(telebot.types.InlineKeyboardButton("🔧管理后台",callback_data="admin"))
    return kb

def user_menu(uid):
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(telebot.types.InlineKeyboardButton("💰我的余额",callback_data="bal"),telebot.types.InlineKeyboardButton("💳充值记录",callback_data="rclog"))
    kb.add(telebot.types.InlineKeyboardButton("📜消费明细",callback_data="uselog"),telebot.types.InlineKeyboardButton("🔙返回主页",callback_data="back"))
    return kb

def admin_kb():
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(telebot.types.InlineKeyboardButton("➕单人手动加余额",callback_data="addbal"),telebot.types.InlineKeyboardButton("➖单人扣余额",callback_data="subbal"))
    kb.add(telebot.types.InlineKeyboardButton("🎟️批量生成卡密",callback_data="card"),telebot.types.InlineKeyboardButton("📊全部用户余额总表",callback_data="ulist"))
    kb.add(telebot.types.InlineKeyboardButton("📋全体用户充值总记录",callback_data="all_rc_log"),telebot.types.InlineKeyboardButton("📋全体用户消费总记录",callback_data="all_use_log"))
    kb.add(telebot.types.InlineKeyboardButton("📢全站广播",callback_data="broad"),telebot.types.InlineKeyboardButton("🔥批量加用户余额",callback_data="batch_addbal"))
    kb.add(telebot.types.InlineKeyboardButton("🎫查看所有有效卡密",callback_data="check_all_cdk"))
    kb.add(telebot.types.InlineKeyboardButton("🗑️作废指定卡密",callback_data="del_cdk"),telebot.types.InlineKeyboardButton("📤导出全部有效卡密",callback_data="export_cdk"))
    kb.add(telebot.types.InlineKeyboardButton("🔙返回",callback_data="back"))
    return kb

def select_menu():
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(telebot.types.InlineKeyboardButton("⚡插入雷号分割",callback_data="ins"),telebot.types.InlineKeyboardButton("📄纯净直接分割",callback_data="noins"))
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
    user_merge[uid] = []
    if uid in user_insert:
        del user_insert[uid]
    if uid in user_file:
        del user_file[uid]
    bot.send_message(msg.chat.id,"✅已清空所有操作缓存，请重新上传文件")

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
            vcf_all += f"BEGIN:VCARD\nVERSION:3.0\nN:{name};;;\nFN:{name}\nTEL;TYPE=CELL:{phone}\nEND:VCARD\n"
        bio=BytesIO(vcf_all.encode())
        bio.name="合并通讯录.vcf"
    else:
        bio=BytesIO(txt.encode())
        bio.name="合并成品.txt"
    bot.send_document(m.chat.id,bio)
    user_state[uid]="idle"
    bot.send_message(m.chat.id,f"✅合并完成｜共{ls}行｜扣费{fee:.4f}元")

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

@bot.message_handler(content_types=['photo'])
def broadcast_photo(msg):
    if not is_admin(msg.from_user.id):
        return
    global broad_img
    broad_img = msg.photo[-1].file_id
    bot.send_message(msg.chat.id,"✅图片已保存，请发送广播文字内容")

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
                bot.send_message(uid, broad_text)
            send_count += 1
        except:
            continue
    bot.send_message(msg.chat.id,f"🎉全站广播全部结束\n成功送达总数：{send_count} 位\n当前时间：{get_beijing_time_str()}")
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
    elif d=="rclog":
        txt="\n".join(log_recharge.get(uid,["暂无充值记录"]))
        bot.send_message(cid,txt[:4000])
    elif d=="uselog":
        txt="\n".join(log_user.get(uid,["暂无消费记录"]))
        bot.send_message(cid,txt[:4000])
    elif d=="back":
        bot.edit_message_text("🏠主菜单",cid,c.message.message_id,reply_markup=menu(uid))
    elif d=="hebing":
        user_merge[uid]=[]
        user_state[uid]="hebing"
        bot.send_message(cid,"📎依次发文件，完了回复：完成")
    elif d=="quchong":
        user_state[uid]="quchong"
        bot.send_message(cid,"🧹请发送去重号码文件")
    elif d=="admin" and is_admin(uid):
        bot.edit_message_text("🔧管理后台",cid,c.message.message_id,reply_markup=admin_kb())
    elif d=="card" and is_admin(uid):
        bot.send_message(cid,"🎟️请输入卡密有效期天数")
        bot.register_next_step_handler(c.message, input_card_day)
    elif d=="del_cdk" and is_admin(uid):
        bot.send_message(cid,"🗑️请发送要作废的卡密")
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
        msg = ""
        for cdk,info in cards.items():
            if info['expire_time'] > now:
                t=datetime.fromtimestamp(info['expire_time']).strftime("%Y-%m-%d %H:%M:%S")
                msg+=f"卡密\n{cdk}\n面值:{info['money']}\n过期:{t}\n----\n"
        bot.send_message(cid,msg[:4000] if msg else "暂无有效卡密")
    elif d=="ulist" and is_admin(uid):
        msg="📊用户余额\n"
        for i,j in users.items():
            msg+=f"{i}→{j['balance']}\n"
        bot.send_message(cid,msg[:4000])
    elif d=="all_rc_log" and is_admin(uid):
        all=[]
        for i,j in log_recharge.items():
            all.extend([f"用户{i}:"+x for x in j])
        bot.send_message(cid,"📋充值记录\n"+"\n".join(all[:4000]))
    elif d=="all_use_log" and is_admin(uid):
        all=[]
        for i,j in log_user.items():
            all.extend([f"用户{i}:"+x for x in j])
        bot.send_message(cid,"📋消费记录\n"+"\n".join(all[:4000]))
    elif d=="broad" and is_admin(uid):
        bot.send_message(cid,"📢先发图再发文字")
        bot.register_next_step_handler(c.message, admin_broadcast)
    elif d=="batch_addbal" and is_admin(uid):
        bot.send_message(cid,"一行一个：ID 金额")
        bot.register_next_step_handler(c.message, batch_add_user_balance)
    elif d=="ins":
        if uid not in user_file:
            return bot.send_message(cid,"请先上传文件")
        bot.send_message(cid,"每份插几条雷号？")
        bot.register_next_step_handler(c.message,ins_num)
    elif d=="noins":
        if uid not in user_file:
            return bot.send_message(cid,"请先上传文件")
        temp_split_data[uid]=user_file[uid]['txt']
        bot.send_message(cid,"请输入文件名前缀")
        bot.register_next_step_handler(c.message,lambda m:split_send_clean(cid,uid,temp_split_data[uid],m.text))

def del_single_cdk(msg):
    cdk=msg.text.strip()
    if cdk in cards:
        del cards[cdk]
        bot.send_message(msg.chat.id,f"✅卡密 {cdk} 已作废")
    else:
        bot.send_message(msg.chat.id,"❌卡密不存在")

def input_card_day(msg):
    try:
        day=int(msg.text)
        bot.send_message(msg.chat.id,f"✅有效期{day}天，请输入卡密面值")
        bot.register_next_step_handler(msg, lambda m:make_card(m,day))
    except:
        bot.send_message(msg.chat.id,"❌请输入纯数字天数")

def make_card(msg,day):
    try:
        money = float(msg.text)
        import string
        expire = get_now_timestamp() + day * 86400
        cdk = "TK"+''.join(random.choices(string.ascii_uppercase+string.digits,k=12))
        cards[cdk] = {"money":money,"expire_time":expire}
        expire_str = datetime.fromtimestamp(expire).strftime("%Y-%m-%d %H:%M:%S")
        bot.send_message(msg.chat.id,f"✅卡密生成成功\n{cdk}\n面值：{money}\n过期时间：{expire_str}")
    except:
        bot.send_message(msg.chat.id,"请输入正确金额")

def use_cdk(m):
    cdk=m.text.strip()
    now=get_now_timestamp()
    if cdk not in cards:
        bot.send_message(m.chat.id,"❌无效/已用/过期")
        return
    info=cards[cdk]
    if info['expire_time']<now:
        del cards[cdk]
        bot.send_message(m.chat.id,"❌该卡密已过期")
        return
    money = info['money']
    cards.pop(cdk)
    get_user(m.from_user.id)['balance']+=money
    add_rc(m.from_user.id,money)
    bot.send_message(m.chat.id,f"✅充值到账{money:.4f}元\n余额：{get_user(m.from_user.id)['balance']:.4f}")

def batch_add_user_balance(msg):
    if not is_admin(msg.from_user.id):
        return
    lines = msg.text.strip().splitlines()
    success = 0
    fail = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
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
        bot.send_message(m.chat.id,"❌请输入纯数字")

def ins_phone(m):
    uid=m.from_user.id
    if uid not in user_insert:
        return bot.send_message(m.chat.id,"❌流程失效")
    phones=re.findall(r"\d+",m.text)
    if len(phones)==0:
        bot.send_message(m.chat.id,"❌未识别号码，请重发")
        bot.register_next_step_handler(m, ins_phone)
        return
    user_insert[uid]['phone']=phones
    bot.send_message(m.chat.id,"📄请输入文件前缀名")
    bot.register_next_step_handler(m, ins_done)

def ins_done(m):
    uid = m.from_user.id
    cid = m.chat.id
    info = user_insert[uid]
    lines = [x for x in info['txt'].splitlines() if x]
    total = len(lines)
    fee_split = total * PRICE_SPLIT
    fee_insert = total * PRICE_INSERT
    total_fee = fee_split + fee_insert
    u = get_user(uid)

    if u['balance'] < total_fee:
        bot.send_message(cid,"❌余额不足")
        return

    u['balance'] -= total_fee
    add_log(uid,"分包+插雷",total,total_fee)
    bot.send_message(cid,f"扣费：{total_fee:.4f}｜剩余：{u['balance']:.4f}")

    chunk = [lines[i:i+u['line']] for i in range(0,total,u['line'])]
    media = []
    file_idx = 1
    batch_num = 1
    ph_idx = 0
    phones = info['phone']
    csv_rows = "分包,位置,原号,雷号\n"

    for c in chunk:
        chunk_len = len(c)
        insert_pos_list = random.sample(range(1, chunk_len+1), info['num'])
        insert_pos_list.sort()
        temp_list = c.copy()

        for pos in insert_pos_list:
            lei = phones[ph_idx % len(phones)]
            temp_list.insert(pos-1, lei)
            csv_rows += f"{file_idx},{pos},{c[pos-1]},{lei}\n"
            ph_idx += 1

        if u['mode']=="VCF":
            vcf = ""
            for p in temp_list:
                n=get_rand_3_name()
                vcf+=f"BEGIN:VCARD\nVERSION:3.0\nN:{n};;;\nFN:{n}\nTEL:{p}\nEND:VCARD\n"
            bio=BytesIO(vcf.encode())
            bio.name=f"{m.text}_{file_idx}.vcf"
        else:
            bio=BytesIO("\n".join(temp_list).encode())
            bio.name=f"{m.text}_{file_idx}.txt"

        media.append(InputMediaDocument(bio))

        if len(media) >= 10:
            bot.send_message(cid,f"📤正在发送第{batch_num}批｜文件 {file_idx-9}～{file_idx}")
            bot.send_media_group(cid, media)
            time.sleep(3)
            media = []
            batch_num += 1

        file_idx += 1

    if media:
        last_start = file_idx - len(media)
        bot.send_message(cid,f"📤正在发送第{batch_num}批｜文件 {last_start}～{file_idx-1}")
        bot.send_media_group(cid, media)

    csv_bio = BytesIO(csv_rows.encode("utf-8-sig"))
    csv_bio.name = "插雷明细.csv"
    bot.send_document(cid, csv_bio)
    bot.send_message(cid,f"✅插雷分包全部完成\n当前北京时间：{get_beijing_time_str()}")

    if uid in user_file:
        del user_file[uid]
    if uid in user_insert:
        del user_insert[uid]

def split_send_clean(cid,uid,txt,name):
    lines=[x for x in txt.splitlines() if x]
    total=len(lines)
    fee=total*PRICE_SPLIT
    u=get_user(uid)
    if u['balance']<fee:
        bot.send_message(cid,"❌余额不足")
        return
    u['balance']-=fee
    add_log(uid,"纯净分包",total,fee)
    bot.send_message(cid,f"扣费：{fee:.4f}｜剩余：{u['balance']:.4f}")

    chunk = [lines[i:i+u['line']] for i in range(0,total,u['line'])]
    media=[]
    file_idx=1
    batch_num=1

    for c in chunk:
        if u['mode']=="VCF":
            vcf=""
            for p in c:
                n=get_rand_3_name()
                vcf+=f"BEGIN:VCARD\nVERSION:3.0\nN:{n};;;\nFN:{n}\nTEL:{p}\nEND:VCARD\n"
            bio=BytesIO(vcf.encode())
            bio.name=f"{name}_{file_idx}.vcf"
        else:
            bio=BytesIO("\n".join(c).encode())
            bio.name=f"{name}_{file_idx}.txt"

        media.append(InputMediaDocument(bio))

        if len(media)>=10:
            bot.send_message(cid,f"📤正在发送第{batch_num}批｜文件 {file_idx-9}～{file_idx}")
            bot.send_media_group(cid,media)
            time.sleep(3)
            media=[]
            batch_num+=1

        file_idx+=1

    if media:
        last_start = file_idx - len(media)
        bot.send_message(cid,f"📤正在发送第{batch_num}批｜文件 {last_start}～{file_idx-1}")
        bot.send_media_group(cid,media)

    bot.send_message(cid,f"✅纯净分包全部完成\n当前北京时间：{get_beijing_time_str()}")

    if uid in temp_split_data:
        del temp_split_data[uid]
    if uid in user_file:
        del user_file[uid]

@bot.message_handler(content_types=['document'])
def doc(m):
    uid=m.from_user.id
    state = user_state.get(uid,"idle")
    try:
        file = bot.get_file(m.document.file_id)
        data = bot.download_file(file.file_path)
        name = m.document.file_name.lower()

        if state=="hebing":
            if name.endswith(".zip"):
                txt=extract_txt_from_zip(data)
            else:
                txt=data.decode("utf-8","ignore")
            txt=clean_empty_line(txt)
            user_merge[uid].append(txt)
            bot.send_message(m.chat.id,f"已收录第{len(user_merge[uid])}个文件")
            return
        if state=="quchong":
            if name.endswith(".zip"):
                txt=extract_txt_from_zip(data)
            else:
                txt=data.decode("utf-8","ignore")
            txt=clean_empty_line(txt)
            old=len(txt.splitlines())
            new=len(list(set(txt.splitlines())))
            fee=new*PRICE_DEDUP
            u=get_user(uid)
            if u['balance']<fee:
                bot.send_message(m.chat.id,"❌余额不足")
                return
            u['balance']-=fee
            add_log(uid,"号码去重",old,fee)
            bot.send_message(m.chat.id,f"去重完成：旧{old}行→新{new}行\n扣费{fee:.4f}")
            user_state[uid]="idle"
            return
        
        if name.endswith(".zip"):
            txt=extract_txt_from_zip(data)
        else:
            txt=data.decode("utf-8","ignore")
        txt=clean_empty_line(txt)
        user_file[uid]={"txt":txt}
        bot.send_message(m.chat.id,"✅文件已保存，请选择分包模式",reply_markup=select_menu())
    except Exception as e:
        bot.send_message(m.chat.id,f"处理异常：{str(e)}")

while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(e)
        time.sleep(5)
