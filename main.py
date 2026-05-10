import re
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= 配置区 =================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"
MY_ID = 6042965834
# ==========================================

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

def get_beijing_time():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

def extract_link_smartly(text):
    full_link = re.search(r"([a-zA-Z0-9-]+\.vip)", text)
    if full_link: return full_link.group(1), False
    all_numbers = re.findall(r"\d{4,8}", text)
    if all_numbers: return f"{all_numbers[-1]}.vip", True
    return None, False

# --- 数据库初始化 (新增做单人字段) ---
def init_db():
    conn = sqlite3.connect('stats.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_confirmed (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link TEXT, file_name TEXT, final_val INTEGER,
        admin_name TEXT, bj_time TEXT, chat_id INTEGER,
        worker_id INTEGER, worker_name TEXT)''') # 新增：做单人ID和名字
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER, chat_id INTEGER, name TEXT, PRIMARY KEY (user_id, chat_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS authorized_chats (chat_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

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

# --- 权限指令 ---
async def auth_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR IGNORE INTO authorized_chats (chat_id) VALUES (?)', (update.effective_chat.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ 本群服务已开启（含员工统计功能）")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID or not update.message.reply_to_message: return
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR REPLACE INTO admins (user_id, chat_id, name) VALUES (?, ?, ?)', (target.id, update.effective_chat.id, target.full_name))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 已授权 {target.full_name} 为本群管理员")

# --- 核心：加减单逻辑 ---
async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    
    reply_msg = update.message.reply_to_message
    if not reply_msg or not reply_msg.text: return

    # 识别链接
    link, is_auto = extract_link_smartly(reply_msg.text)
    if not link: return

    # 获取做单人信息 (被回复的人)
    worker = reply_msg.from_user
    worker_id = worker.id
    worker_name = worker.full_name

    # 提取数值
    val_match = re.search(r"^([+-])(\d+)$", update.message.text.strip())
    if not val_match: return
    final_val = int(val_match.group(2)) if val_match.group(1) == '+' else -int(val_match.group(2))
    
    now_time = get_beijing_time()
    conn = sqlite3.connect('stats.db')
    conn.execute('''INSERT INTO admin_confirmed 
                 (link, file_name, final_val, admin_name, bj_time, chat_id, worker_id, worker_name) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                 (link, "自动识别", final_val, update.effective_user.full_name, now_time, chat_id, worker_id, worker_name))
    conn.commit()
    conn.close()

    status = "加单" if final_val > 0 else "减单"
    await update.message.reply_text(
        f"🎯 **{status}成功**\n━━━━━━━━━━━━━━\n"
        f"👤 **做单人:** [{worker_name}](tg://user?id={worker_id})\n"
        f"🌐 **链接:** `{link}`\n"
        f"🔢 **变动:** `{update.message.text}`\n"
        f"⏰ **时间:** `{now_time}`", parse_mode='Markdown'
    )

# --- 查询：统计全部 (按链接和按人) ---
async def query_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    
    conn = sqlite3.connect('stats.db')
    # 1. 链接汇总
    link_rows = conn.execute('SELECT link, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY link', (chat_id,)).fetchall()
    # 2. 员工汇总 (按数值降序)
    worker_rows = conn.execute('SELECT worker_name, worker_id, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY worker_id ORDER BY SUM(final_val) DESC', (chat_id,)).fetchall()
    conn.close()

    if not link_rows: return await update.message.reply_text("📭 本群暂无统计。")

    report = f"📋 **本群实时报表**\n🕒 `{get_beijing_time()}`\n\n"
    report += "🌐 **链接汇总：**\n"
    total_all = 0
    for r in link_rows:
        report += f"• `{r[0]}`: **{r[1]}**\n"
        total_all += r[1]
    
    report += f"\n🏆 **员工战绩：**\n"
    for w in worker_rows:
        # 名字变为可点击的链接
        report += f"• [{w[0]}](tg://user?id={w[1]}): **{w[2]}**\n"
    
    report += f"━━━━━━━━━━━━━━\n🌟 **总计总额：{total_all}**"
    await update.message.reply_text(report, parse_mode='Markdown')

async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admin_confirmed WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🗑 **已清空本群所有数据（包括链接和员工统计）**")

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.Regex(r"^授权群聊$"), auth_chat))
    app.add_handler(MessageHandler(filters.Regex(r"^(授权|/auth)$"), add_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^统计全部$"), query_all))
    app.add_handler(MessageHandler(filters.Regex(r"^清空全部$"), clear_data))
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"^[+-]\d+$"), handle_admin_action))
    app.run_polling()

if __name__ == '__main__': main()
