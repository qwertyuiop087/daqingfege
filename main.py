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

# --- 数据库初始化 ---
def init_db():
    conn = sqlite3.connect('stats.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_confirmed (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link TEXT, file_name TEXT, final_val INTEGER,
        admin_name TEXT, bj_time TEXT, chat_id INTEGER,
        worker_id INTEGER, worker_name TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER, chat_id INTEGER, name TEXT, PRIMARY KEY (user_id, chat_id))''')
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

# --- 权限管理指令 ---
async def auth_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR IGNORE INTO authorized_chats (chat_id) VALUES (?)', (update.effective_chat.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ **本群服务已开启**")

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    chat_id = update.effective_chat.id
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM authorized_chats WHERE chat_id = ?', (chat_id,))
    conn.execute('DELETE FROM admin_confirmed WHERE chat_id = ?', (chat_id,))
    conn.execute('DELETE FROM admins WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🚫 **本群服务已停止并清空所有权限/数据**")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID or not update.message.reply_to_message: return
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR REPLACE INTO admins (user_id, chat_id, name) VALUES (?, ?, ?)', (target.id, update.effective_chat.id, target.full_name))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 已授权 **{target.full_name}** 为本群管理员")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID or not update.message.reply_to_message: return
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admins WHERE user_id = ? AND chat_id = ?', (target.id, update.effective_chat.id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"❌ 已撤销 **{target.full_name}** 的本群管理员权限")

# --- 核心：加减单逻辑 ---
async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    reply_msg = update.message.reply_to_message
    if not reply_msg or not reply_msg.text: return

    link, is_auto = extract_link_smartly(reply_msg.text)
    if not link: return

    file_block_match = re.search(r"包号[：:](.*?)(?=手机号|成功|数量|失败|$)", reply_msg.text, re.DOTALL)
    f_name = " ".join(file_block_match.group(1).strip().split()) if file_block_match else reply_msg.text.split('\n')[0][:30].strip()

    worker = reply_msg.from_user
    val_match = re.search(r"^([+-])(\d+)$", update.message.text.strip())
    if not val_match: return
    final_val = int(val_match.group(2)) if val_match.group(1) == '+' else -int(val_match.group(2))
    
    now_time = get_beijing_time()
    conn = sqlite3.connect('stats.db')
    conn.execute('''INSERT INTO admin_confirmed (link, file_name, final_val, admin_name, bj_time, chat_id, worker_id, worker_name) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (link, f_name, final_val, update.effective_user.full_name, now_time, chat_id, worker.id, worker.full_name))
    conn.commit()
    conn.close()

    status = "加单" if final_val > 0 else "减单"
    await update.message.reply_text(
        f"🎯 **{status}成功**\n━━━━━━━━━━━━━━\n"
        f"👤 **做单人:** [{worker.full_name}](tg://user?id={worker.id})\n"
        f"🌐 **链接:** `{link}`\n"
        f"📦 **包号:** `{f_name}`\n"
        f"🔢 **变动:** `{update.message.text}`\n"
        f"⏰ **时间:** `{now_time}`", parse_mode='Markdown'
    )

# --- 查询指令 (无限制版本) ---
async def query_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    conn = sqlite3.connect('stats.db')
    links = conn.execute('SELECT link, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY link', (chat_id,)).fetchall()
    workers = conn.execute('SELECT worker_name, worker_id, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY worker_id ORDER BY SUM(final_val) DESC', (chat_id,)).fetchall()
    conn.close()

    if not links: return await update.message.reply_text("📭 本群暂无统计")
    report = f"📋 **本群总报表**\n🕒 `{get_beijing_time()}`\n\n🌐 **链接汇总：**\n"
    total = 0
    for r in links:
        report += f"• `{r[0]}`: **{r[1]}**\n"
        total += r[1]
    report += f"\n🏆 **员工战绩(人均)：**\n"
    for w in workers: report += f"• [{w[0]}](tg://user?id={w[1]}): **{w[2]}**\n"
    report += f"━━━━━━━━━━━━━━\n🌟 **总计总额：{total}**"
    await update.message.reply_text(report, parse_mode='Markdown')

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """【更新】全量查询明细，不设 15 条限制"""
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    parts = update.message.text.split()
    if len(parts) < 2: return
    link_to_query = parts[1]
    
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT file_name, final_val, worker_name, bj_time, worker_id FROM admin_confirmed WHERE chat_id = ? AND link = ? ORDER BY id ASC', (chat_id, link_to_query)).fetchall()
    conn.close()
    
    if not rows: return await update.message.reply_text(f"📭 `{link_to_query}` 无明细记录")
    
    report = f"📊 **全量明细：{link_to_query}**\n总额：**{sum(r[1] for r in rows)}**\n━━━━━━━━━━━━━━\n"
    # 如果记录非常多，Telegram 消息有长度限制(4096字符)，所以这里做个安全切片，或者分段发。
    # 这里依然显示所有，如果超出长度，建议使用清空全部开始新账期。
    for r in rows:
        mark = "➕" if r[1] > 0 else "➖"
        report += f"{mark} `{r[0][:10]}` | **{r[1]}** | [{r[2]}](tg://user?id={r[4]})\n"
    
    if len(report) > 4000:
        report = report[:3900] + "\n...(由于记录过多，仅显示部分，建议清空后再对账)"
        
    await update.message.reply_text(report, parse_mode='Markdown')

async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admin_confirmed WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🗑 **已彻底清空本群所有账单及员工业绩。**")

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.Regex(r"^授权群聊$"), auth_chat))
    app.add_handler(MessageHandler(filters.Regex(r"^停止本群服务$"), stop_chat))
    app.add_handler(MessageHandler(filters.Regex(r"^(授权|/auth)$"), add_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^取消管理员$"), remove_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^统计全部$"), query_all))
    app.add_handler(MessageHandler(filters.Regex(r"^统计\s+"), handle_query))
    app.add_handler(MessageHandler(filters.Regex(r"^清空全部$"), clear_data))
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"^[+-]\d+$"), handle_admin_action))
    app.run_polling()

if __name__ == '__main__': main()
