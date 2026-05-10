import re
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ================= 配置区 =================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"
MY_ID = 6042965834
# ==========================================

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

def get_beijing_time():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

def extract_link_smartly(text):
    if not text: return None
    # 修正逻辑：更强力的正则，无视前后字符，精准抓取 .vip 链接
    full_link = re.search(r"([a-zA-Z0-9-]+\.vip)", text)
    if full_link: return full_link.group(1)
    
    # 兜底识别：找 4-8 位数字补全
    all_numbers = re.findall(r"\d{4,8}", text)
    if all_numbers: return f"{all_numbers[-1]}.vip"
    return None

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

# --- 权限检查工具 ---
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

# --- 管理指令 (仅限 MY_ID) ---
async def auth_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR IGNORE INTO authorized_chats (chat_id) VALUES (?)', (update.effective_chat.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ **本群服务已开启**\n已支持图片账单识别及员工业绩统计。")

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    chat_id = update.effective_chat.id
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM authorized_chats WHERE chat_id = ?', (chat_id,))
    conn.execute('DELETE FROM admin_confirmed WHERE chat_id = ?', (chat_id,))
    conn.execute('DELETE FROM admins WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🚫 **本群服务已停止**\n所有权限及数据已物理粉碎。")

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
    await update.message.reply_text(f"❌ 已撤销 **{target.full_name}** 的管理员权限")

# --- 核心操作：加减单 (强化识别) ---
async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    
    reply_msg = update.message.reply_to_message
    if not reply_msg: return

    # 【深度修复】核心：同时检索文本(text)和图片说明(caption)
    source_text = reply_msg.text if reply_msg.text else reply_msg.caption
    if not source_text: return

    # 抓取链接
    link = extract_link_smartly(source_text)
    if not link: return

    # 抓取包号
    file_block_match = re.search(r"包号[：:](.*?)(?=手机号|成功|数量|失败|$)", source_text, re.DOTALL)
    f_name = " ".join(file_block_match.group(1).strip().split()) if file_block_match else "未识别包号"

    # 抓取加减数值
    val_match = re.search(r"^([+-])(\d+)$", update.message.text.strip())
    if not val_match: return
    final_val = int(val_match.group(2)) if val_match.group(1) == '+' else -int(val_match.group(2))
    
    now_time = get_beijing_time()
    conn = sqlite3.connect('stats.db')
    conn.execute('''INSERT INTO admin_confirmed (link, file_name, final_val, admin_name, bj_time, chat_id, worker_id, worker_name) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (link, f_name, final_val, update.effective_user.full_name, now_time, chat_id, reply_msg.from_user.id, reply_msg.from_user.full_name))
    conn.commit()
    conn.close()

    status = "加单" if final_val > 0 else "减单"
    await update.message.reply_text(
        f"🎯 **{status}成功**\n━━━━━━━━━━━━━━\n"
        f"👤 **做单人:** [{reply_msg.from_user.full_name}](tg://user?id={reply_msg.from_user.id})\n"
        f"🌐 **链接:** `{link}`\n"
        f"📦 **包号:** `{f_name}`\n"
        f"🔢 **变动:** `{update.message.text}`\n"
        f"⏰ **时间:** `{now_time}`", parse_mode='Markdown'
    )

# --- 查询与统计 ---
async def query_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    conn = sqlite3.connect('stats.db')
    links = conn.execute('SELECT link, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY link', (chat_id,)).fetchall()
    workers = conn.execute('SELECT worker_name, worker_id, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY worker_id ORDER BY SUM(final_val) DESC', (chat_id,)).fetchall()
    conn.close()

    if not links: return await update.message.reply_text("📭 本群暂无统计。")
    report = f"📋 **本群总报表**\n🕒 `{get_beijing_time()}`\n\n🌐 **链接汇总：**\n"
    total_all = 0
    for r in links:
        report += f"• `{r[0]}`: **{r[1]}**\n"
        total_all += r[1]
    report += f"\n🏆 **员工业绩：**\n"
    for w in workers:
        report += f"• [{w[0]}](tg://user?id={w[1]}): **{w[2]}**\n"
    report += f"━━━━━━━━━━━━━━\n🌟 **总计：{total_all}**"
    await update.message.reply_text(report, parse_mode='Markdown')

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    parts = update.message.text.split()
    if len(parts) < 2: return
    link_to_query = parts[1]
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT file_name, final_val, worker_name, worker_id FROM admin_confirmed WHERE chat_id = ? AND link = ? ORDER BY id ASC', (chat_id, link_to_query)).fetchall()
    conn.close()
    if not rows: return await update.message.reply_text(f"📭 `{link_to_query}` 无记录")
    report = f"📊 **明细记录：{link_to_query}**\n总额：**{sum(r[1] for r in rows)}**\n━━━━━━━━━━━━━━\n"
    for r in rows:
        mark = "➕" if r[1] > 0 else "➖"
        report += f"{mark} `{r[0][:10]}` | **{r[1]}** | [{r[2]}](tg://user?id={r[3]})\n"
    await update.message.reply_text(report[:4000], parse_mode='Markdown')

async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admin_confirmed WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🗑 **已彻底清空本群所有统计数据。**")

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
