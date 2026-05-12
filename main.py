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

# --- 时间工具 ---
def get_beijing_time():
    # 获取当前北京时间
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

# --- 识别与提取逻辑 ---
def extract_link_smartly(text):
    if not text: return None
    full_link = re.search(r"([a-zA-Z0-9-]+\.vip)", text)
    if full_link: return full_link.group(1)
    all_numbers = re.findall(r"\d{4,8}", text)
    if all_numbers: return f"{all_numbers[-1]}.vip"
    return None

def auto_extract_filenames(text):
    start_match = re.search(r"(包号|编号|单反)[：:](.*?)(?=手机|尾号|数量|话术|送达|用浏览器|$)", text, re.DOTALL)
    if not start_match: 
        return None if len(text.strip()) < 10 else text.split('\n')[0][:50].strip()
    raw_content = start_match.group(2).strip()
    found_items = []
    for line in raw_content.split('\n'):
        line = line.strip()
        if re.search(r"\d", line) and (("-" in line) or ("." in line) or ("A" in line.upper())):
            clean_line = re.sub(r"^[^\da-zA-Z\u4e00-\u9fa5]*?[\u4e00-\u9fa5]{2,3}\s+", "", line)
            found_items.append(clean_line.strip())
    return ", ".join(found_items) if found_items else None

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

# --- 核心录入逻辑 ---
async def handle_direct_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    if not is_chat_authorized(chat_id) or not is_admin(admin_user.id, chat_id): return
    
    msg_text = update.message.text.strip()
    val_match = re.search(r"^([+-])(\d+)", msg_text)
    if not val_match: return
    
    change_val = int(val_match.group(2)) if val_match.group(1) == '+' else -int(val_match.group(2))
    reply_msg = update.message.reply_to_message

    # 判定误触：无回复且无网址内容则无视
    link_in_msg = extract_link_smartly(msg_text)
    file_in_msg = auto_extract_filenames(msg_text)
    if not reply_msg and not link_in_msg and not file_in_msg: return 

    if reply_msg:
        target_worker = reply_msg.from_user
        source_text = reply_msg.text or reply_msg.caption or msg_text
    else:
        target_worker = admin_user
        source_text = msg_text

    final_link = extract_link_smartly(source_text) or "手动录入"
    final_f_name = auto_extract_filenames(source_text) or "手动录入"
    now = get_beijing_time()

    conn = sqlite3.connect('stats.db')
    conn.execute('''INSERT INTO admin_confirmed (link, file_name, final_val, admin_name, bj_time, chat_id, worker_id, worker_name) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (final_link, final_f_name, change_val, admin_user.full_name, now, chat_id, target_worker.id, target_worker.full_name))
    res = conn.execute('SELECT SUM(final_val) FROM admin_confirmed WHERE chat_id = ? AND worker_id = ?', (chat_id, target_worker.id)).fetchone()
    conn.commit()
    conn.close()
    
    bal = res[0] if res[0] else 0

    # 独立发信回执
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🎯 **操作成功**\n━━━━━━━━━━━━━━\n"
             f"👤 **对象:** [{target_worker.full_name}](tg://user?id={target_worker.id})\n"
             f"🌐 **网址:** `{final_link}`\n"
             f"📦 **包号:** `{final_f_name}`\n"
             f"🔢 **变动:** `{val_match.group(0)}`\n"
             f"💰 **余额:** `{bal}`\n"
             f"━━━━━━━━━━━━━━\n⏰ {now}",
        parse_mode='Markdown'
    )

# --- 报表与明细统计 ---
async def query_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    conn = sqlite3.connect('stats.db')
    links = conn.execute('SELECT link, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY link', (chat_id,)).fetchall()
    workers = conn.execute('SELECT worker_name, worker_id, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY worker_id ORDER BY SUM(final_val) DESC', (chat_id,)).fetchall()
    conn.close()
    
    total_sum = sum(r[1] for r in links)
    report = f"📋 **本群总报表**\n\n🌐 **链接统计：**\n"
    for r in links: report += f"• `{r[0]}`: **{r[1]}**\n"
    report += f"━━━━━━━━━━━━━━\n🌟 **全部总计：{total_sum}**\n━━━━━━━━━━━━━━\n\n🏆 **排名汇总：**\n"
    for w in workers: report += f"• [{w[0]}](tg://user?id={w[1]}): **{w[2]}**\n"
    
    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

async def query_link_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    parts = update.message.text.split()
    if len(parts) < 2: return
    target = parts[1]
    
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT file_name, final_val, worker_name, worker_id, bj_time FROM admin_confirmed WHERE chat_id = ? AND link LIKE ? ORDER BY id DESC', (chat_id, f"%{target}%")).fetchall()
    conn.close()
    
    if not rows:
        return await context.bot.send_message(chat_id=chat_id, text=f"📭 链接 `{target}` 暂无明细记录")

    report = f"📊 **明细记录: {target}**\n━━━━━━━━━━━━━━\n"
    for r in rows:
        mark = "➕" if r[1] > 0 else "➖"
        report += f"{mark} `{r[0]}` | **{r[1]}**\n👤 [{r[2]}](tg://user?id={r[3]}) | ⏰ {r[4].split()[1]}\n\n"
    
    await context.bot.send_message(chat_id=chat_id, text=report[:4000], parse_mode='Markdown')

# --- 资金查询与管理 ---
async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_chat_authorized(update.effective_chat.id): return
    conn = sqlite3.connect('stats.db')
    res = conn.execute('SELECT SUM(final_val) FROM admin_confirmed WHERE chat_id = ? AND worker_id = ?', (update.effective_chat.id, update.effective_user.id)).fetchone()
    conn.close()
    bal = res[0] if res[0] else 0
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"💰 [{update.effective_user.full_name}](tg://user?id={update.effective_user.id})\n实时余额: `{bal}`\n⏰ {get_beijing_time()}", parse_mode='Markdown')

async def admin_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID or not update.message.reply_to_message: return
    target = update.message.reply_to_message.from_user
    cmd = update.message.text
    conn = sqlite3.connect('stats.db')
    if "授权管理员" in cmd:
        conn.execute('INSERT OR REPLACE INTO admins (user_id, chat_id, name) VALUES (?, ?, ?)', (target.id, update.effective_chat.id, target.full_name))
        text = f"👑 **已成功授权管理员:** {target.full_name}"
    else:
        conn.execute('DELETE FROM admins WHERE user_id = ? AND chat_id = ?', (target.id, update.effective_chat.id))
        text = f"❌ **已撤销管理员权限:** {target.full_name}"
    conn.commit()
    conn.close()
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

async def service_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    cmd = update.message.text
    conn = sqlite3.connect('stats.db')
    if "授权群聊" in cmd:
        conn.execute('INSERT OR IGNORE INTO authorized_chats (chat_id) VALUES (?)', (update.effective_chat.id,))
        text = "✅ **本群服务已启动 (独立消息模式)**"
    else:
        conn.execute('DELETE FROM authorized_chats WHERE chat_id = ?', (update.effective_chat.id,))
        text = "🚫 **本群服务已停止**"
    conn.commit()
    conn.close()
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

async def clear_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_chat.id): return
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admin_confirmed WHERE chat_id = ?', (update.effective_chat.id,))
    conn.commit()
    conn.close()
    await context.bot.send_message(chat_id=update.effective_chat.id, text="🗑 **本群数据已清空归零**")

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    
    # 授权与停止服务
    app.add_handler(MessageHandler(filters.Regex(r"^(授权群聊|停止本群服务)$"), service_management))
    # 授权与取消管理员
    app.add_handler(MessageHandler(filters.Regex(r"^(授权管理员|取消管理员)$"), admin_management))
    # 数据统计
    app.add_handler(MessageHandler(filters.Regex(r"^统计全部$"), query_all))
    app.add_handler(MessageHandler(filters.Regex(r"^统计\s+"), query_link_detail))
    app.add_handler(MessageHandler(filters.Regex(r"^清空全部$"), clear_all))
    # 余额查询
    app.add_handler(MessageHandler(filters.Regex(r"^资金$"), check_balance))
    # 核心录入
    app.add_handler(MessageHandler(filters.Regex(r"^[+-]\d+"), handle_direct_entry))
    
    print("🚀 机器人已启动 (满血独立发信模式)...")
    app.run_polling()

if __name__ == '__main__': main()
