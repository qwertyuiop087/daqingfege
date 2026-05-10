import re
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ================= 配置区 =================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"
MY_ID = 6042965834  # 你的Telegram ID
# ==========================================

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

def get_beijing_time():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

def extract_link_smartly(text):
    if not text: return None
    # 强力提取 .vip 链接，无视前后干扰
    full_link = re.search(r"([a-zA-Z0-9-]+\.vip)", text)
    if full_link: return full_link.group(1)
    # 兜底识别 4-8 位数字
    all_numbers = re.findall(r"\d{4,8}", text)
    if all_numbers: return f"{all_numbers[-1]}.vip"
    return None

# --- 数据库操作 ---
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

# --- 权限管理 ---
async def auth_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR IGNORE INTO authorized_chats (chat_id) VALUES (?)', (update.effective_chat.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ **服务开启** | 已支持图片识别与资金钱包系统")

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    chat_id = update.effective_chat.id
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM authorized_chats WHERE chat_id = ?', (chat_id,))
    conn.execute('DELETE FROM admin_confirmed WHERE chat_id = ?', (chat_id,))
    conn.execute('DELETE FROM admins WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🚫 **服务停止** | 本群所有权限与统计数据已清空")

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
    await update.message.reply_text(f"❌ 已撤销 {target.full_name} 的管理员权限")

# --- 钱包查询 ---
async def check_my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id): return
    balance = get_worker_balance(chat_id, update.effective_user.id)
    await update.message.reply_text(
        f"💰 **资金详情**\n━━━━━━━━━━━━━━\n"
        f"👤 **用户:** [{update.effective_user.full_name}](tg://user?id={update.effective_user.id})\n"
        f"💵 **当前总余额:** `{balance}`\n"
        f"⏰ **时间:** `{get_beijing_time()}`", parse_mode='Markdown'
    )

# --- 核心：加减单逻辑 ---
async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    
    reply_msg = update.message.reply_to_message
    if not reply_msg: return

    # 兼容读取纯文字和图片说明文字
    source_text = reply_msg.text if reply_msg.text else reply_msg.caption
    if not source_text: return

    link = extract_link_smartly(source_text)
    if not link: return

    file_block_match = re.search(r"包号[：:](.*?)(?=手机号|成功|数量|失败|$)", source_text, re.DOTALL)
    f_name = " ".join(file_block_match.group(1).strip().split()) if file_block_match else "未识别包号"

    val_match = re.search(r"^([+-])(\d+)$", update.message.text.strip())
    if not val_match: return
    change_val = int(val_match.group(2)) if val_match.group(1) == '+' else -int(val_match.group(2))
    
    worker = reply_msg.from_user
    now = get_beijing_time()
    conn = sqlite3.connect('stats.db')
    conn.execute('''INSERT INTO admin_confirmed (link, file_name, final_val, admin_name, bj_time, chat_id, worker_id, worker_name) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (link, f_name, change_val, update.effective_user.full_name, now, chat_id, worker.id, worker.full_name))
    conn.commit()
    conn.close()

    new_balance = get_worker_balance(chat_id, worker.id)
    status = "加单" if change_val > 0 else "减单"
    await update.message.reply_text(
        f"🎯 **{status}成功**\n━━━━━━━━━━━━━━\n"
        f"👤 **做单人:** [{worker.full_name}](tg://user?id={worker.id})\n"
        f"🌐 **链接:** `{link}`\n"
        f"🔢 **变动:** `{update.message.text}`\n"
        f"💰 **当前总余额:** `{new_balance}`\n"
        f"⏰ **时间:** `{now}`", parse_mode='Markdown'
    )

# --- 统计汇总 ---
async def query_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    conn = sqlite3.connect('stats.db')
    links = conn.execute('SELECT link, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY link', (chat_id,)).fetchall()
    workers = conn.execute('SELECT worker_name, worker_id, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY worker_id ORDER BY SUM(final_val) DESC', (chat_id,)).fetchall()
    conn.close()
    if not links: return await update.message.reply_text("📭 本群暂无统计记录")
    
    report = f"📋 **本群总报表**\n🕒 `{get_beijing_time()}`\n\n🌐 **链接汇总：**\n"
    total = sum(r[1] for r in links)
    for r in links: report += f"• `{r[0]}`: **{r[1]}**\n"
    report += f"\n🏆 **资金排名：**\n"
    for w in workers: report += f"• [{w[0]}](tg://user?id={w[1]}): **{w[2]}**\n"
    report += f"━━━━━━━━━━━━━━\n🌟 **累计总计：{total}**"
    await update.message.reply_text(report, parse_mode='Markdown')

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    parts = update.message.text.split()
    if len(parts) < 2: return
    link_query = parts[1]
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT file_name, final_val, worker_name, worker_id FROM admin_confirmed WHERE chat_id = ? AND link = ? ORDER BY id ASC', (chat_id, link_query)).fetchall()
    conn.close()
    if not rows: return await update.message.reply_text(f"📭 `{link_query}` 无记录")
    
    report = f"📊 **明细表：{link_query}**\n总计：**{sum(r[1] for r in rows)}**\n━━━━━━━━━━━━━━\n"
    for r in rows:
        mark = "➕" if r[1] > 0 else "➖"
        report += f"{mark} `{r[0][:10]}` | **{r[1]}** | [{r[2]}](tg://user?id={r[3]})\n"
    await update.message.reply_text(report[:4000], parse_mode='Markdown')

async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_chat.id): return
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admin_confirmed WHERE chat_id = ?', (update.effective_chat.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🗑 **本群账目已清空，资金归零。**")

def main():
    init_db()
    # 增强版配置：增加超时时间防止网络波动导致报错
    app = Application.builder() \
        .token(BOT_TOKEN) \
        .connect_timeout(30) \
        .read_timeout(30) \
        .build()
    
    app.add_handler(MessageHandler(filters.Regex(r"^授权群聊$"), auth_chat))
    app.add_handler(MessageHandler(filters.Regex(r"^停止本群服务$"), stop_chat))
    app.add_handler(MessageHandler(filters.Regex(r"^(授权|/auth)$"), add_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^取消管理员$"), remove_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^资金$"), check_my_balance))
    app.add_handler(MessageHandler(filters.Regex(r"^统计全部$"), query_all))
    app.add_handler(MessageHandler(filters.Regex(r"^统计\s+"), handle_query))
    app.add_handler(MessageHandler(filters.Regex(r"^清空全部$"), clear_data))
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"^[+-]\d+$"), handle_admin_action))
    
    print("🚀 机器人正在运行中...")
    app.run_polling()

if __name__ == '__main__': main()
