import os
import random
import time
import zipfile
from io import BytesIO
import telebot
import flask
from telebot.types import InputMediaDocument
from datetime import datetime, timezone, timedelta

# ===================== 配置 =====================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"
ADMIN_ID = 6042965834

PRICE_SPLIT = 0.0004
PRICE_INSERT = 0.0001
PRICE_MERGE = 0.0002
PRICE_DEDUP = 0.0002
BATCH_SIZE = 10

WEBHOOK_LISTEN = "0.0.0.0"
WEBHOOK_PORT = int(os.getenv("PORT", 8080))

# 广播全局缓存
broad_img = None
broad_text = ""

# 随机中文名
XING = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛"
MING1 = "伟俊佳浩宇泽晨欣雨轩博文铭凯艺霖梓睿一诺嘉航沐辰"
MING2 = "杰豪琳雪婷芳莹瑞阳鑫鹏佳怡涵悦彤诗雅泽安诺"

def get_rand_3_name():
    return random.choice(XING) + random.choice(MING1) + random.choice(MING2)

# 全局用户数据
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

# 日志
def add_log(uid, txt, num, cost):
    t = get_beijing_time_str()
    log_user[uid] = log_user.get(uid,[]) + [f"[{t}]用户{uid}｜{txt}｜{num}行｜扣费{cost:.4f}｜剩余余额{get_user(uid)['balance']:.4f}"]

def add_rc(uid,money):
    t = get_beijing_time_str()
    log_recharge[uid] = log_recharge.get(uid,[]) + [f"[{t}]用户{uid}｜后台批量充值+{money:.4f}｜剩余余额{get_user(uid)['balance']:.4f}"]

# 北京时间
def get_beijing_time_str():
    utc_now = datetime.now(timezone.utc)
    beijing_tz = timezone(timedelta(hours=8))
    beijing_now = utc_now.astimezone(beijing_tz)
    return beijing_now.strftime("%Y-%m-%d %H:%M:%S")

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
        clean_empty_line(all_text)
        return all_text
    except Exception as e:
        return ""

# ===================== Bot 初始化 =====================
bot = telebot.TeleBot(BOT_TOKEN, skip_pending=True)

# ===================== 菜单 =====================
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
        kb.add(telebot.types.InlineKeyboardButton("🔧管理后台",callback_data="admin"))
    return kb

def user_menu(uid):
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        telebot.types.InlineKeyboardButton("💰个人余额",callback_data="bal"),
        telebot.types.InlineKeyboardButton("💳充值记录",callback_data="rclog")
    )
    kb.add(
        telebot.types.InlineKeyboardButton("📜消费记录",callback_data="uselog"),
        telebot.types.InlineKeyboardButton("🔙返回主页",callback_data="back")
    )
    return kb

def admin_kb():
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        telebot.types.InlineKeyboardButton("➕单人加余额",callback_data="addbal"),
        telebot.types.InlineKeyboardButton("➖单人扣余额",callback_data="subbal")
    )
    kb.add(
        telebot.types.InlineKeyboardButton("🎟️批量生成卡密",callback_data="card"),
        telebot.types.InlineKeyboardButton("📊用户余额总表",callback_data="ulist")
    )
    kb.add(
        telebot.types.InlineKeyboardButton("📋充值总记录",callback_data="all_rc_log"),
        telebot.types.InlineKeyboardButton("📋消费总记录",callback_data="all_use_log")
    )
    kb.add(
        telebot.types.InlineKeyboardButton("📢全站广播",callback_data="broad"),
        telebot.types.InlineKeyboardButton("🔥批量加余额",callback_data="batch_addbal")
    )
    kb.add(telebot.types.InlineKeyboardButton("🔙返回",callback_data="back"))
    return kb

def select_menu():
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        telebot.types.InlineKeyboardButton("⚡插入雷号分割",callback_data="ins"),
        telebot.types.InlineKeyboardButton("📄纯净直接分割",callback_data="noins")
    )
    return kb

# ===================== 基础命令 =====================
@bot.message_handler(commands=['start'])
def start_cmd(m):
    uid = m.from_user.id
    get_user(uid)
    user_state[uid] = "idle"
    now_time = get_beijing_time_str()
    bot.send_message(m.chat.id,
        f"🤖工具机器人运行正常✅\n当前北京时间：{now_time}\n支持TXT/VCF互转｜TXT/ZIP自动解析",
        reply_markup=menu(uid)
    )

@bot.message_handler(func=lambda msg: msg.text.strip() == "取消")
def cancel_all(msg):
    uid = msg.from_user.id
    user_state[uid] = "idle"
    user_merge[uid] = []
    user_insert.pop(uid, None)
    user_file.pop(uid, None)
    bot.send_message(msg.chat.id, "✅已清空所有操作缓存，请重新上传文件")

# ===================== 文件合并 =====================
@bot.message_handler(func=lambda m: user_state.get(m.from_user.id) == "hebing" and m.text == "完成")
def merge_done(m):
    uid = m.from_user.id
    if not user_merge.get(uid, []):
        bot.send_message(m.chat.id, "❌你还没有上传任何文件")
        return

    txt = "\n".join(user_merge[uid])
    lines = len(txt.split())
    fee = PRICE_MERGE
    u = get_user(uid)

    if u['balance'] < fee:
        bot.send_message(m.chat.id, "❌余额不足")
        return

    u['balance'] -= fee
    add_log(uid, "文件合并", lines, fee)
    if u['mode'] == "VCF":
        vcf_all = ""
        for phone in txt.splitlines():
            name = get_rand_3_name()
            vcf_all += f"BEGIN:VCARD\nVERSION:3.0\nN:{name};;;\nFN:{name}\nTEL;TYPE=CELL:{phone}\nEND:VCARD\n"
        bio = BytesIO(vcf_all.encode())
        bio.name = "合并通讯录.vcf"
    else:
        bio = BytesIO(txt.encode())
        bio.name = "合并成品.txt"

    bot.send_document(m.chat.id, bio)
    user_state[uid] = "idle"
    bot.send_message(m.chat.id, f"✅合并完成｜共{lines}行｜扣费{fee:.4f}元")

# ===================== 管理员命令 =====================
@bot.message_handler(func=lambda msg: is_admin(msg.from_user.id))
def admin_commands(msg):
    txt = msg.text.strip()
    if txt.startswith("查询用户充值记录"):
        try:
            uid = int(txt.replace("查询用户充值记录", "").strip())
            log = log_recharge.get(uid, ["该用户暂无充值记录"])
            bot.send_message(msg.chat.id, f"📋用户{uid}充值明细\n" + "\n".join(log)[:4000])
        except:
            bot.send_message(msg.chat.id, "❌格式：查询用户充值记录 用户ID")

    elif txt.startswith("查询用户消费记录"):
        try:
            uid = int(txt.replace("查询用户消费记录", "").strip())
            log = log_user.get(uid, ["该用户暂无消费记录"])
            bot.send_message(msg.chat.id, f"📋用户{uid}消费明细\n" + "\n".join(log)[:4000])
        except:
            bot.send_message(msg.chat.id, "❌格式：查询用户消费记录 用户ID")

# ===================== 广播 =====================
@bot.message_handler(content_types=['photo'])
def receive_broad_image(msg):
    if not is_admin(msg.from_user.id):
        return
    global broad_img
    broad_img = msg.photo[-1].file_id
    bot.send_message(msg.chat.id, "✅图片已保存，请直接发送广播文字内容")

def do_broadcast(msg):
    global broad_img, broad_text
    broad_text = msg.text.strip()

    if not broad_text and not broad_img:
        bot.send_message(msg.chat.id, "❌内容不能为空")
        broad_img = None
        broad_text = ""
        return
    user_list = list(users.keys())
    total = len(user_list)
    success = 0
    bot.send_message(msg.chat.id, f"📢开始全站广播，总用户：{total} 位")
    for uid in user_list:
        try:
            if broad_img:
                bot.send_photo(uid, broad_img, caption=broad_text)
            else:
                bot.send_message(uid, broad_text)
            success += 1
            time.sleep(0.1)
        except Exception:
            continue
    bot.send_message(msg.chat.id, f"🎉广播完成\n成功送达：{success}/{total} 位用户")
    broad_img = None
    broad_text = ""

# ===================== 按钮回调 =====================
@bot.callback_query_handler(func=lambda c: True)
def callback(c):
    try:
        bot.answer_callback_query(c.id)
        uid = c.from_user.id
        cid = c.message.chat.id
        d = c.data
        u = get_user(uid)

        if d == "mode":
            u['mode'] = "VCF" if u['mode'] == "TXT" else "TXT"
            bot.edit_message_text("✅格式已切换", cid, c.message.id, reply_markup=menu(uid))

        elif d == "line":
            bot.send_message(cid, "📏请输入每份分割行数")
            bot.register_next_step_handler(c.message, set_split_line)

        elif d == "user_cdk":
            bot.send_message(cid, "💳请粘贴你的卡密兑换")
            bot.register_next_step_handler(c.message, use_card)

        elif d == "user":
            bot.edit_message_text("👤个人中心", cid, c.message.id, reply_markup=user_menu(uid))

        elif d == "bal":
            bot.send_message(cid, f"💰当前余额：{u['balance']:.4f} 元")

        elif d == "rclog":
            log = log_recharge.get(uid, ["暂无充值记录"])
            bot.send_message(cid, "\n".join(log)[:4000])

        elif d == "uselog":
            log = log_user.get(uid, ["暂无消费记录"])
            bot.send_message(cid, "\n".join(log)[:4000])

        elif d == "back":
            bot.edit_message_text("🏠主菜单", cid, c.message.id, reply_markup=menu(uid))

        elif d == "hebing":
            user_merge[uid] = []
            user_state[uid] = "hebing"
            bot.send_message(cid, "📎依次发送文件，发完回复：完成")

        elif d == "quchong":
            user_state[uid] = "quchong"
            bot.send_message(cid, "🧹请发送需要去重的号码文件")

        elif d == "admin" and is_admin(uid):
            bot.edit_message_text("🔧管理员后台", cid, c.message.id, reply_markup=admin_kb())

        elif d == "addbal" and is_admin(uid):
            bot.send_message(cid, "➕格式：用户ID 金额")
            bot.register_next_step_handler(c.message, admin_add_balance)

        elif d == "subbal" and is_admin(uid):
            bot.send_message(cid, "➖格式：用户ID 金额")
            bot.register_next_step_handler(c.message, admin_sub_balance)

        elif d == "card" and is_admin(uid):
            bot.send_message(cid, "🎟️输入卡密面值")
            bot.register_next_step_handler(c.message, create_card)

        elif d == "ulist" and is_admin(uid):
            res = "📊全站用户余额\n"
            for uid_, info in users.items():
                res += f"ID:{uid_} | {info['balance']:.4f}\n"
            bot.send_message(cid, res[:4000])

        elif d == "all_rc_log" and is_admin(uid):
            all_log = []
            for logs in log_recharge.values():
                all_log += logs
            txt = "\n".join(all_log) if all_log else "暂无记录"
            bot.send_message(cid, "📋全站充值记录\n" + txt[:4000])

        elif d == "all_use_log" and is_admin(uid):
            all_log = []
            for logs in log_user.values():
                all_log += logs
            txt = "\n".join(all_log) if all_log else "暂无记录"
            bot.send_message(cid, "📋全站消费记录\n" + txt[:4000])

        elif d == "broad" and is_admin(uid):
            bot.send_message(cid, "📢先发送图片，再发送文字内容")
            bot.register_next_step_handler(c.message, do_broadcast)

        elif d == "batch_addbal" and is_admin(uid):
            bot.send_message(cid, "🔥格式：\n用户ID 金额\n一行一个")
            bot.register_next_step_handler(c.message, batch_add_balance)

        elif d == "ins":
            if uid not in user_file:
                bot.send_message(cid, "📭请先上传文件")
                return
            bot.send_message(cid, "⚡每份插入几条雷号？")
            bot.register_next_step_handler(c.message, set_insert_num)

        elif d == "noins":
            if uid not in user_file:
                bot.send_message(cid, "📭请先上传文件")
                return
            bot.send_message(cid, "📄输入文件名前缀")
            bot.register_next_step_handler(c.message, lambda m: clean_split(cid, uid, user_file[uid]['txt'], m.text.strip()))
    except Exception:
        pass

def set_split_line(m):
    try:
        get_user(m.from_user.id)['line'] = int(m.text)
        bot.send_message(m.chat.id, "✅分割行数已设置")
    except:
        bot.send_message(m.chat.id, "❌请输入数字")

def use_card(m):
    cdk = m.text.strip()
    if cdk not in cards:
        bot.send_message(m.chat.id, "❌卡密无效或已使用")
        return
    money = cards.pop(cdk)
    u = get_user(m.from_user.id)
    u['balance'] += money
    add_rc(m.from_user.id, money)
    bot.send_message(m.chat.id, f"✅充值成功：+{money:.4f}\n余额：{u['balance']:.4f}")

def set_insert_num(m):
    uid = m.from_user.id
    try:
        num = int(m.text)
        user_insert[uid] = {"num": num, "txt": user_file[uid]['txt']}
        bot.send_message(m.chat.id, "⚡发送雷号列表，一行一个")
        bot.register_next_step_handler(m, receive_lei_phones)
    except:
        bot.send_message(m.chat.id, "❌请输入数字")

def receive_lei_phones(m):
    uid = m.from_user.id
    if uid not in user_insert:
        bot.send_message(m.chat.id, "❌流程已过期")
        return
    import re
    phones = re.findall(r'\d+', m.text)
    if not phones:
        bot.send_message(m.chat.id, "❌未识别到号码，请重发")
        bot.register_next_step_handler(m, receive_lei_phones)
        return
    user_insert[uid]['phone'] = phones
    bot.send_message(m.chat.id, "📄输入文件名前缀")
    bot.register_next_step_handler(m, insert_split)

def insert_split(m):
    uid = m.from_user.id
    info = user_insert[uid]
    lines = [x for x in info['txt'].splitlines() if x]
    total = len(lines)
    u = get_user(uid)
    fee_split = total * PRICE_SPLIT
    fee_insert = total * PRICE_INSERT
    total_fee = fee_split + fee_insert

    if u['balance'] < total_fee:
        bot.send_message(m.chat.id, "❌余额不足")
        return

    u['balance'] -= total_fee
    add_log(uid, "插雷+分割", total, total_fee)
    chunks = [lines[i:i+u['line']] for i in range(0, total, u['line'])]
    media = []
    idx = 1
    ph_idx = 0
    csv = "分包,位置,原号码,雷号\n"
    bot.send_message(m.chat.id, f"📦共{len(chunks)}个文件，开始发送...")
    for chunk in chunks:
        cl = len(chunk)
        insert_cnt = info['num']
        if insert_cnt > cl: insert_cnt = cl
        positions = random.sample(range(1, cl+1), insert_cnt)
        positions.sort()
        temp = chunk.copy()
        for pos in positions:
            lei = info['phone'][ph_idx % len(info['phone'])]
            temp.insert(pos-1, lei)
            csv += f"{idx},{pos},{chunk[pos-1]},{lei}\n"
            ph_idx += 1

        if u['mode'] == "VCF":
            vcf = ""
            for p in temp:
                name = get_rand_3_name()
                vcf += f"BEGIN:VCARD\nVERSION:3.0\nN:{name};;;\nFN:{name}\nTEL;TYPE=CELL:{p}\nEND:VCARD\n"
            bio = BytesIO(vcf.encode())
            bio.name = f"{m.text}_{idx}.vcf"
        else:
            bio = BytesIO("\n".join(temp).encode())
            bio.name = f"{m.text}_{idx}.txt"

        media.append(InputMediaDocument(bio))
        if len(media) >= BATCH_SIZE:
            bot.send_media_group(m.chat.id, media)
            bot.send_message(m.chat.id, f"✅已发送 {idx-9} ~ {idx}")
            time.sleep(3)
            media = []
        idx += 1

media and bot.send_media_group(m.chat.id, media)
csv_bio = BytesIO(csv.encode("utf-8-sig"))
log_user
bot.send_document(m.chat.id, csv_bio)
bot.send_message(m.chat.id, "🎉全部完成")
user_file.pop(uid, None)
user_insert.pop(uid, None)

def clean_split(cid, uid, txt, name):
    lines = [x for x in txt.splitlines() if x]
    total = len(lines)
    u = get_user(uid)
    fee = total * PRICE_SPLIT

    if u['balance'] < fee:
        bot.send_message(cid, "❌余额不足")
        return

    u['balance'] -= fee
    add_log(uid, "纯净分割", total, fee)
    chunks = [lines[i:i+u['line']] for i in range(0, total, u['line'])]
    media = []
    idx = 1
    bot.send_message(cid, f"📦共{len(chunks)}个文件")
    for c in chunks:
        if u['mode'] == "VCF":
            vcf = ""
            for p in c:
                n = get_rand_3_name()
                vcf += f"BEGIN:VCARD\nVERSION:3.0\nN:{n};;;\nFN:{n}\nTEL;TYPE=CELL:{p}\nEND:VCARD\n"
            bio = BytesIO(vcf.encode())
            bio.name = f"{name}_{idx}.vcf"
        else:
            bio = BytesIO("\n".join(c).encode())
            bio.name = f"{name}_{idx}.txt"

        media.append(InputMediaDocument(bio))
        if len(media) >= BATCH_SIZE:
            bot.send_media_group(cid, media)
            bot.send_message(cid, f"✅已发送 {idx-9} ~ {idx}")
            time.sleep(3)
            media = []
        idx += 1

media and bot.send_media_group(cid, media)
bot.send_message(cid, "🎉纯净分割完成")
user_file.pop(uid, None)

@bot.message_handler(content_types=['document'])
def handle_file(m):
    try:
        uid = m.from_user.id
        state = user_state.get(uid, "idle")
        file = bot.get_file(m.document.file_id)
        data = bot.download_file(file.file_path)
        name = m.document.file_name.lower()

        if state == "hebing":
            txt = extract_txt_from_zip(data) if name.endswith(".zip") else data.decode("utf-8","ignore")
            txt = clean_empty_line(txt)
            txt and user_merge[uid].append(txt) and bot.send_message(m.chat.id, f"✅已收录第{len(user_merge[uid])}个文件")
            return

        if state == "quchong":
            txt = extract_txt_from_zip(data) if name.endswith(".zip") else data.decode("utf-8","ignore")
            txt = clean_empty_line(txt)
            old = len(txt.splitlines())
            new_lines = list(set(txt.splitlines()))
            new = len(new_lines)
            fee = new * PRICE_DEDUP
            u = get_user(uid)
            if u['balance'] < fee:return bot.send_message(m.chat.id,"❌余额不足")
            u['balance'] -= fee
            add_log(uid, "去重", old, fee)

            bio = BytesIO(("\n".join(new_lines)).encode())
            bio.name = "去重.txt"
            bot.send_document(m.chat.id, bio)
            bot.send_message(m.chat.id, f"✅去重完成｜原{old} → 新{new}｜扣费{fee:.4f}")
            user_state[uid] = "idle"
            return

        txt = extract_txt_from_zip(data) if name.endswith(".zip") else data.decode("utf-8","ignore")
        txt = clean_empty_line(txt)
        if not txt:return bot.send_message(m.chat.id,"❌文件为空")
        user_file[uid] = {"txt": txt}
        bot.send_message(m.chat.id,f"✅文件已接收\n当前格式：{get_user(uid)['mode']}",reply_markup=select_menu())
    except Exception as e:
        bot.send_message(m.chat.id, f"❌错误：{str(e)}")

def admin_add_balance(m):
    try:
        uid, money = m.text.split()
        uid = int(uid)
        money = float(money)
        get_user(uid)['balance'] += money
        add_rc(uid, money)
        bot.send_message(m.chat.id, f"✅成功给 {uid} 充值 {money:.4f}")
    except:
        bot.send_message(m.chat.id, "❌格式：用户ID 金额")

def admin_sub_balance(m):
    try:
        uid, money = m.text.split()
        uid = int(uid)
        money = float(money)
        get_user(uid)['balance'] -= money
        bot.send_message(m.chat.id, f"✅成功扣除 {uid} {money:.4f}")
    except:
        bot.send_message(m.chat.id, "❌格式：用户ID 金额")

def create_card(m):
    try:
        money = float(m.text)
        import string
        cdk = "TK"+''.join(random.choices(string.ascii_uppercase+string.digits,k=10))
        cards[cdk]=money
        bot.send_message(m.chat.id,f"✅卡密：\n{cdk}\n面值：{money:.4f}")
    except:
        bot.send_message(m.chat.id,"❌请输入正确金额")

def batch_add_balance(m):
    lines = m.text.strip().splitlines()
    ok=0
    for line in lines:
        try:
            uid,mon=line.split()
            uid=int(uid)
            mon=float(mon)
            get_user(uid)['balance']+=mon
            add_rc(uid,mon)
            ok+=1
        except:continue
    bot.send_message(m.chat.id,f"✅批量完成：{ok} 个用户")

# ===================== 付费Railway自动Webhook =====================
app = flask.Flask(__name__)
DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN")
WEBHOOK_URL = f"https://{DOMAIN}/bot{BOT_TOKEN}"

@app.route("/bot"+BOT_TOKEN, methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(flask.request.stream.read())])
    return "OK",200

if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(2)
    bot.set_webhook(WEBHOOK_URL)
    print("Webhook绑定成功")
app.run(host="0.0.0.0", port=WEBHOOK_PORT)
