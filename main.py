import re
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ================= 配置区 =================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"
MY_ID = 6042965834  # 你的数字ID
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

def auto_extract_filenames(text):
    start_match = re.search(r"(包号|编号|单反)[：:](.*?)(?=手机|尾号|数量|话术|送达|用浏览器|$)", text, re.DOTALL)
    if not start_match: return text.split('\n')[0][:50].strip()
    raw_content = start_match.group(2).strip()
    found_items = []
    for line in raw_content.split('\n'):
        line = line.strip()
        if re.search(r"\d", line) and (("-" in line) or ("." in line) or ("A" in line.upper())):
            clean_line = re.sub(r"^[^\da-zA-Z\u4e00-\u9fa5]*?[\u4e00-\u9fa5]{2,3}\s+", "", line)
            found_items.append(clean_line.strip())
    return ", ".join(found_items) if found_items else "余额调整/手工"

# --- 数据库操作 ---
def init_db():
    conn = sqlite3.connect('stats.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_confirmed (
        id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT, file_name TEXT, final_val INTEGER,
        admin_name TEXT, bj_time TEXT, chat_id INTEGER, worker_id INTEGER, worker_name TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER, chat_id INTEGER, name TEXT, PRIMARY KEY (user_id, chat_id))''')
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

# --- 权限管理指令 ---
async def auth_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR IGNORE INTO authorized_chats (chat_id) VALUES (?)', (update.effective_chat.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ **本群服务已授权**")

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM authorized_chats WHERE chat_id = ?', (update.effective_chat.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🚫 **本群服务已停止**")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID or not update.message.reply_to_message: return
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR REPLACE INTO admins (user_id, chat_id, name) VALUES (?, ?, ?)', (target.id, update.effective_chat.id, target.full_name))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 **已设为管理员:** [{target.full_name}](tg://user?id={target.id})", parse_mode='Markdown')

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID or not update.message.reply_to_message: return
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admins WHERE user_id = ? AND chat_id = ?', (target.id, update.effective_chat.id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"❌ **已取消管理员权限:** {target.full_name}")

async def clear_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_chat.id): return
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admin_confirmed WHERE chat_id = ?', (update.effective_chat.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🗑 **所有数据已清空归零**")

# --- 核心录入与回扣回溯 ---
async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id): return
    reply_msg = update.message.reply_to_message
    if not reply_msg: return

    source_text = reply_msg.text if reply_msg.text else reply_msg.caption
    link = extract_link_smartly(source_text)
    f_name = auto_extract_filenames(source_text)
    
    val_match = re.search(r"^([+-])(\d+)$", update.message.text.strip())
    if not val_match: return
    change_val = int(val_match.group(2)) if val_match.group(1) == '+' else -int(val_match.group(2))
    
    worker = reply_msg.from_user
    now = get_beijing_time()
    if not link: link = "余额调账"

    conn = sqlite3.connect('stats.db')
    conn.execute('''INSERT INTO admin_confirmed (link, file_name, final_val, admin_name, bj_time, chat_id, worker_id, worker_name) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (link, f_name, change_val, update.effective_user.full_name, now, chat_id, worker.id, worker.full_name))
    
    # 回溯做单记录
    history = conn.execute('SELECT DISTINCT link FROM admin_confirmed WHERE chat_id = ? AND worker_id = ? AND final_val > 0', (chat_id, worker.id)).fetchall()
    conn.commit()
    conn.close()
    
    bal = get_worker_balance(chat_id, worker.id)
    links_str = "\n".join([f"• `{h[0]}`" for h in history]) if history else "暂无历史"

    await update.message.reply_text(
        f"🎯 **录入成功** ({'加单' if change_val > 0 else '扣单'})\n━━━━━━━━━━━━━━\n"
        f"👤 **员工:** [{worker.full_name}](tg://user?id={worker.id})\n"
        f"🌐 **网址:** `{link}`\n"
        f"📦 **包号:** `{f_name}`\n"
        f"🔢 **变动:** `{update.message.text}`\n"
        f"💰 **实时余额:** `{bal}`\n\n"
        f"🔍 **该员历史记录：**\n{links_str}\n"
        f"━━━━━━━━━━━━━━\n⏰ {now}", parse_mode='Markdown'
    )

# --- 统计报表 (包含单链接统计) ---
async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bal = get_worker_balance(update.effective_chat.id, update.effective_user.id)
    await update.message.reply_text(f"💰 [{update.effective_user.full_name}](tg://user?id={update.effective_user.id}) 余额: `{bal}`", parse_mode='Markdown')

async def query_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_chat.id): return
    conn = sqlite3.connect('stats.db')
    links = conn.execute('SELECT link, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY link', (update.effective_chat.id,)).fetchall()
    workers = conn.execute('SELECT worker_name, worker_id, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY worker_id ORDER BY SUM(final_val) DESC', (update.effective_chat.id,)).fetchall()
    conn.close()
    
    report = f"📋 **总报表**\n\n🌐 **链接汇总：**\n"
    for r in links: report += f"• `{r[0]}`: **{r[1]}**\n"
    report += f"\n🏆 **排名汇总 (点击跳转)：**\n"
    for w in workers: report += f"• [{w[0]}](tg://user?id={w[1]}): **{w[2]}**\n"
    await update.message.reply_text(report, parse_mode='Markdown')

async def query_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """这里是您要的单链接明细功能"""
    parts = update.message.text.split()
    if len(parts) < 2: return
    target = parts[1]
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT file_name, final_val, worker_name, worker_id, bj_time FROM admin_confirmed WHERE chat_id = ? AND link LIKE ?', (update.effective_chat.id, f"%{target}%")).fetchall()
    conn.close()
    if not rows: return await update.message.reply_text(f"📭 链接 `{target}` 暂无明细")
    
    report = f"📊 **明细: {target}**\n━━━━━━━━━━━━━━\n"
    for r in rows:
        mark = "➕" if r[1] > 0 else "➖"
        report += f"{mark} `{r[0]}` | **{r[1]}**\n👤 [{r[2]}](tg://user?id={r[3]}) | ⏰ {r[4].split()[1]}\n\n"
    await update.message.reply_text(report[:4000], parse_mode='Markdown')

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).connect_timeout(30).read_timeout(30).build()
    
    app.add_handler(MessageHandler(filters.Regex(r"^授权群聊$"), auth_chat))
    app.add_handler(MessageHandler(filters.Regex(r"^停止本群服务$"), stop_chat))
    app.add_handler(MessageHandler(filters.Regex(r"^授权管理员$"), add_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^取消管理员$"), remove_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^清空全部$"), clear_all))
    app.add_handler(MessageHandler(filters.Regex(r"^资金$"), check_balance))
    app.add_handler(MessageHandler(filters.Regex(r"^统计全部$"), query_all))
    app.add_handler(MessageHandler(filters.Regex(r"^统计\s+"), query_link)) # 单链接统计
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"^[+-]\d+$"), handle_admin_action))
    
    app.run_polling()

if __name__ == '__main__': main()
