import re
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ================= 配置区 =================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"
MY_ID = 6042965834  # 换成你的Telegram数字ID
# ==========================================

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

def get_beijing_time():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

def extract_link_smartly(text):
    if not text: return None
    full_link = re.search(r"([a-zA-Z0-9-]+\.vip)", text)
    if full_link: return full_link.group(1)
    all_numbers = re.findall(r"\d{4,8}", text)
    if all_numbers: return f"{all_numbers[-1]}.vip"
    return None

# --- 全自动包号特征识别 ---
def auto_extract_filenames(text):
    start_match = re.search(r"(包号|编号|单反)[：:](.*?)(?=手机|尾号|数量|话术|送达|用浏览器|$)", text, re.DOTALL)
    if not start_match:
        return text.split('\n')[0][:30].strip()
    
    raw_content = start_match.group(2).strip()
    found_items = []
    for line in raw_content.split('\n'):
        line = line.strip()
        if not line: continue
        # 识别带字母、数字或横线的特征，自动切掉行首名字
        if re.search(r"\d", line) and (("-" in line) or ("." in line) or ("A" in line.upper())):
            clean_line = re.sub(r"^[^\da-zA-Z\u4e00-\u9fa5]*?[\u4e00-\u9fa5]{2,3}\s+", "", line)
            found_items.append(clean_line.strip())
    
    if found_items: return " | ".join(found_items)
    fallback = re.sub(r"(啊起|单反|编号|包号|小弟|转|：|:)", "", raw_content).strip()
    return " ".join(fallback.split())[:50]

# --- 数据库操作 ---
def init_db():
    conn = sqlite3.connect('stats.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_confirmed (
        id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT, file_name TEXT, final_val INTEGER,
        admin_name TEXT, bj_time TEXT, chat_id INTEGER, worker_id INTEGER, worker_name TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER, chat_id INTEGER, name TEXT, PRIMARY KEY (user_id, chat_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS authorized_chats (chat_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

def get_worker_balance(chat_id, worker_id):
    conn = sqlite3.connect('stats.db')
    res = conn.execute('SELECT SUM(final_val) FROM admin_confirmed WHERE chat_id = ? AND worker_id = ?', (chat_id, worker_id)).fetchone()
    conn.close()
    return res[0] if res[0] else 0

def is_admin(user_id, chat_id):
    if user_id == MY_ID: return True
    conn = sqlite3.connect('stats.db')
    res = conn.execute('SELECT 1 FROM admins WHERE user_id = ? AND chat_id = ?', (user_id, chat_id)).fetchone()
    conn.close()
    return True if res else False

def is_chat_authorized(chat_id):
    conn = sqlite3.connect('stats.db')
    res = conn.execute('SELECT 1 FROM authorized_chats WHERE chat_id = ?', (chat_id,)).fetchone()
    conn.close()
    return True if res else False

# --- 指令功能 ---
async def auth_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR IGNORE INTO authorized_chats (chat_id) VALUES (?)', (update.effective_chat.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ **服务已授权**")

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM authorized_chats WHERE chat_id = ?', (update.effective_chat.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🚫 **服务已停止并清权**")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID or not update.message.reply_to_message: return
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR REPLACE INTO admins (user_id, chat_id, name) VALUES (?, ?, ?)', (target.id, update.effective_chat.id, target.full_name))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 已授权管理员: {target.full_name}")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID or not update.message.reply_to_message: return
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admins WHERE user_id = ? AND chat_id = ?', (target.id, update.effective_chat.id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"❌ 已取消管理员: {target.full_name}")

async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_chat_authorized(update.effective_chat.id): return
    bal = get_worker_balance(update.effective_chat.id, update.effective_user.id)
    await update.message.reply_text(f"💰 您的当前余额为: `{bal}`", parse_mode='Markdown')

async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    reply_msg = update.message.reply_to_message
    if not reply_msg: return
    source_text = reply_msg.text if reply_msg.text else reply_msg.caption
    if not source_text: return
    link = extract_link_smartly(source_text)
    if not link: return
    f_name = auto_extract_filenames(source_text)
    val_match = re.search(r"^([+-])(\d+)$", update.message.text.strip())
    if not val_match: return
    change_val = int(val_match.group(2)) if val_match.group(1) == '+' else -int(val_match.group(2))
    worker = reply_msg.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('''INSERT INTO admin_confirmed (link, file_name, final_val, admin_name, bj_time, chat_id, worker_id, worker_name) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (link, f_name, change_val, update.effective_user.full_name, get_beijing_time(), chat_id, worker.id, worker.full_name))
    conn.commit()
    conn.close()
    bal = get_worker_balance(chat_id, worker.id)
    await update.message.reply_text(f"🎯 录入成功\n📦 包号: `{f_name}`\n💰 余额: `{bal}`", parse_mode='Markdown')

async def query_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_chat.id): return
    conn = sqlite3.connect('stats.db')
    links = conn.execute('SELECT link, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY link', (update.effective_chat.id,)).fetchall()
    conn.close()
    report = "📋 本群报表:\n" + "\n".join([f"• `{r[0]}`: {r[1]}" for r in links])
    await update.message.reply_text(report, parse_mode='Markdown')

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).connect_timeout(30).read_timeout(30).build()
    
    # 重新补全的所有 Handler
    app.add_handler(MessageHandler(filters.Regex(r"^授权群聊$"), auth_chat))
    app.add_handler(MessageHandler(filters.Regex(r"^停止本群服务$"), stop_chat))
    app.add_handler(MessageHandler(filters.Regex(r"^(授权|/auth)$"), add_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^取消管理员$"), remove_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^资金$"), check_balance))
    app.add_handler(MessageHandler(filters.Regex(r"^统计全部$"), query_all))
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"^[+-]\d+$"), handle_admin_action))
    
    app.run_polling()

if __name__ == '__main__': main()
