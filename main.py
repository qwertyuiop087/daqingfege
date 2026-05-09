import os
import re
import random
import time
import threading
from io import BytesIO
from flask import Flask
from telebot import TeleBot, types

# ====================== 配置 ======================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"   # <-- 填你的Bot Token
ADMIN_ID = 6042965834         # <-- 填你的 Telegram ID
os.environ['FLASK_ENV'] = 'production'

# ====================== 全局变量 ======================
user_file = {}      # 保存用户上传文件内容
user_state = {}     # 保存用户当前状态
users = {}          # 用户信息（余额、模式、分包行数）
merge_temp = {}     # 合并TXT缓存
cards = {}          # 卡密
phone_temp = {}     # 临时保存插入手机号信息

# ====================== 工具函数 ===================
def get_user(uid):
    if uid not in users:
        users[uid] = {"balance": 0, "mode": "TXT", "split_lines": 100}
    return users[uid]

def is_admin(uid):
    return uid == ADMIN_ID

def random_name():
    first = ["李", "王", "张", "刘", "陈"]
    last = ["伟", "芳", "强", "磊", "军"]
    return random.choice(first) + random.choice(last)

def main_menu(uid):
    user = get_user(uid)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"📂 模式：{user['mode']}", callback_data="switch_mode"),
        types.InlineKeyboardButton(f"📏 行数：{user['split_lines']}", callback_data="set_lines")
    )
    kb.add(
        types.InlineKeyboardButton("💰 余额", callback_data="balance"),
        types.InlineKeyboardButton("💳 充值", callback_data="redeem")
    )
    kb.add(
        types.InlineKeyboardButton("📎 合并Txt", callback_data="merge_txt"),
        types.InlineKeyboardButton("🧹 号码去重", callback_data="deduplicate")
    )
    if is_admin(uid):
        kb.add(types.InlineKeyboardButton("🔧 管理", callback_data="admin"))
    return kb

# ====================== 机器人初始化 ===================
bot = TeleBot(BOT_TOKEN, skip_pending=True)

# ====================== 启动命令 ===================
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.from_user.id
    get_user(uid)
    user_state[uid] = "idle"
    bot.send_message(msg.chat.id, "✅ 机器人已启动", reply_markup=main_menu(uid))

# ====================== 回调按钮 ===================
@bot.callback_query_handler(func=lambda call: True)
def handle_all(call):
    try:
        uid = call.from_user.id
        cid = call.message.chat.id
        mid = call.message.id
        act = call.data
        bot.answer_callback_query(call.id)

        if act == "switch_mode":
            u = get_user(uid)
            u['mode'] = "VCF" if u['mode']=="TXT" else "TXT"
            bot.edit_message_text("✅ 模式已切换",cid,mid,reply_markup=main_menu(uid))
        elif act == "set_lines":
            bot.send_message(cid,"✏️ 输入分包行数：")
            bot.register_next_step_handler(call.message, lambda m: set_lines(m, uid))
        elif act == "balance":
            bot.edit_message_text(f"💰 余额：{get_user(uid)['balance']}",cid,mid,reply_markup=main_menu(uid))
        elif act == "redeem":
            bot.send_message(cid,"💳 输入卡密：")
            bot.register_next_step_handler(call.message, lambda m: redeem(m, uid))
        # 插入手机号选择
        elif act == "insert_phone_yes":
            bot.send_message(cid, "📄 每个分包插入多少个手机号？")
            user_state[uid] = "insert_count"
        elif act == "insert_phone_no":
            user_state[uid] = "split_only"
            go(cid, uid, user_file[uid], user_file[uid]['n'])
        # 自定义分包名称
        elif act == "custom":
            data = user_file[uid]
            del user_file[uid]
            bot.send_message(cid,"✏️ 输入前缀：")
            bot.register_next_step_handler(call.message, lambda m: go(cid, uid, data, m.text.strip()))
        elif act == "original":
            data = user_file[uid]
            del user_file[uid]
            go(cid, uid, data, data['n'])
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ 操作失败：{str(e)}")

# ====================== 功能函数 ===================
def set_lines(m,uid):
    try:
        get_user(uid)['split_lines'] = int(m.text)
        bot.send_message(m.chat.id,"✅ 已设置")
    except:
        bot.send_message(m.chat.id,"❌ 请输入数字")

def redeem(m,uid):
    c=m.text.strip()
    if c in cards and not cards[c]['used']:
        get_user(uid)['balance']+=cards[c]['amount']
        cards[c]['used']=True
        bot.send_message(m.chat.id,"✅ 充值成功")
    else:
        bot.send_message(m.chat.id,"❌ 卡密无效")

# ====================== 文件上传处理 ===================
@bot.message_handler(content_types=['document'])
def handle_all_files(msg):
    uid = msg.from_user.id
    cid = msg.chat.id
    try:
        file_info = bot.get_file(msg.document.file_id)
        data = bot.download_file(file_info.file_path)
        name = msg.document.file_name.lower()
        if not name.endswith(".txt"):
            bot.send_message(cid, "❌ 仅支持 TXT 文件")
            return
        text = data.decode('utf-8', 'ignore')
        user_file[uid] = {'c': text, 'n': msg.document.file_name, 'fee': 1}  # 简化计费
        # 上传完成后，询问是否插入手机号
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ 插入手机号", callback_data="insert_phone_yes"),
            types.InlineKeyboardButton("❌ 不插入", callback_data="insert_phone_no")
        )
        bot.send_message(cid,"是否在分包时插入手机号？", reply_markup=kb)
    except Exception as e:
        bot.send_message(cid,f"❌ 处理失败：{str(e)}")

# ====================== 插入手机号设置 ===================
@bot.message_handler(func=lambda msg: user_state.get(msg.from_user.id) in ["insert_count","insert_file"])
def handle_phone_setting(msg):
    uid = msg.from_user.id
    cid = msg.chat.id
    state = user_state.get(uid)
    if state == "insert_count":
        try:
            count = int(msg.text)
            phone_temp[uid] = {'count': count}
            bot.send_message(cid,"📄 请上传手机号 TXT，每行一个手机号")
            user_state[uid] = "insert_file"
        except:
            bot.send_message(cid,"❌ 请输入数字")
    elif state == "insert_file":
        try:
            file_info = bot.get_file(msg.document.file_id)
            data = bot.download_file(file_info.file_path)
            text = data.decode('utf-8', 'ignore')
            phones = [x.strip() for x in text.splitlines() if x.strip()]
            phone_temp[uid]['phones'] = phones
            user_state[uid] = "split_only"
            go(cid, uid, user_file[uid], user_file[uid]['n'], insert_info=phone_temp[uid])
            del phone_temp[uid]
        except:
            bot.send_message(cid,"❌ 处理失败，请重新上传手机号 TXT")

# ====================== 分包发送函数 ===================
def go(cid, uid, s, p, insert_info=None):
    try:
        u = get_user(uid)
        u['balance'] -= s['fee']
        con = s['c']
        step = u['split_lines']
        ls = con.splitlines()
        files = []
        insert_log = []
        phone_index = 0
        phone_list = insert_info['phones'] if insert_info else []
        insert_per_file = insert_info['count'] if insert_info else 0

        # 分包并插入手机号
        for i in range(0, len(ls), step):
            part = ls[i:i+step]
            new_part = []
            for idx, line in enumerate(part):
                new_part.append(line)
                if insert_info and (idx+1) % insert_per_file == 0:
                    phone = phone_list[phone_index]
                    phone_index = (phone_index + 1) % len(phone_list)
                    new_part.append(phone)
                    insert_log.append({"file": f"{p}_{i//step+1}.txt", "line": idx+1, "phone": phone})
            b = BytesIO("\n".join(new_part).encode("utf-8"))
            b.name = f"{p}_{i//step+1}.txt"
            files.append(b)

        # 每10个一批发送
        total = len(files)
        batch_size = 10
        bot.send_message(cid, f"✅ 共 {total} 个分包，每10个一批发送")
        for i in range(0, total, batch_size):
            batch = files[i:i+batch_size]
            media_group = [types.InputMediaDocument(f) for f in batch]
            bot.send_media_group(cid, media=media_group)
            sent_num = min(i+batch_size, total)
            bot.send_message(cid, f"✅ 已发送 {sent_num}/{total}")
            if i+batch_size < total:
                time.sleep(3)

        # 手机号插入明细
        if insert_info:
            log_bio = BytesIO("\n".join([f'{x["file"]} 行{x["line"]}: {x["phone"]}' for x in insert_log]).encode("utf-8"))
            log_bio.name = "手机号插入明细.txt"
            bot.send_document(cid, log_bio, caption="📄 手机号插入明细")

        bot.send_message(cid, f"✅ 发送完成！余额：{u['balance']}")
    except Exception as e:
        bot.send_message(cid, f"❌ 发送失败：{str(e)}")

# ====================== Flask Web ===================
app = Flask(__name__)
@app.route("/")
def home():
    return "Bot Running"

def run_bot():
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except:
            time.sleep(10)

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    run_web()
