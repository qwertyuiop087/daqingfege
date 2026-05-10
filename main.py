import re
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= 配置区 =================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"  # 在这里填入 @BotFather 给你的 Token
MY_ID = 6042965834            # 在这里填入你的数字 ID (超级管理员)
# ==========================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def init_db():
    conn = sqlite3.connect('stats.db')
    cursor = conn.cursor()
    # 记录表
    cursor.execute('''CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER, link TEXT, file_name TEXT, success_val INTEGER,
        is_confirmed INTEGER DEFAULT 0, admin_name TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    # 管理员表
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, name TEXT)''')
    conn.commit()
    conn.close()

def is_admin(user_id):
    if user_id == MY_ID: return True
    conn = sqlite3.connect('stats.db')
    res = conn.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return True if res else False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    keyboard = [[InlineKeyboardButton("📊 查看汇总报告", callback_data='none')]]
    await update.message.reply_text(
        "🛠 **统计机器人已就绪**\n\n"
        "✅ **基础操作：**\n"
        "1. 回复交单消息输入 + 或 加单 确认\n"
        "2. 输入 统计 链接 查询明细\n"
        "3. 回复某人输入 /add 设为管理员",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    if not update.message.reply_to_message:
        return await update.message.reply_text("💡 请回复目标用户的消息使用 /add")
    
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR REPLACE INTO admins (user_id, name) VALUES (?, ?)', (target.id, target.full_name))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 已授权管理员：{target.full_name}")

async def monitor_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return
    
    # 匹配“成功”和“.vip”
    success_match = re.search(r"成功[：:]\s*(\d+)", text)
    link_match = re.search(r"([a-zA-Z0-9-]+\.vip)", text)
    file_match = re.search(r"([^\s]+\.txt)", text)

    if success_match and link_match:
        link, val = link_match.group(1), int(success_match.group(1))
        f_name = file_match.group(1) if file_match else "无包号"
        
        conn = sqlite3.connect('stats.db')
        conn.execute('INSERT INTO records (message_id, link, file_name, success_val) VALUES (?, ?, ?, ?)', 
                     (update.message.message_id, link, f_name, val))
        conn.commit()
        conn.close()

async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id) or not update.message.reply_to_message: return
    
    msg_id = update.message.reply_to_message.message_id
    conn = sqlite3.connect('stats.db')
    cur = conn.cursor()
    cur.execute('UPDATE records SET is_confirmed = 1, admin_name = ? WHERE message_id = ?', 
                (update.effective_user.full_name, msg_id))
    if cur.rowcount > 0:
        await update.message.reply_text(f"🆗 已加单 (确认人: {update.effective_user.first_name})")
    conn.commit()
    conn.close()

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    parts = update.message.text.split()
    if len(parts) < 2: return
    link = parts[1]
    
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT file_name, success_val, is_confirmed FROM records WHERE link = ?', (link,)).fetchall()
    conn.close()

    if not rows: return await update.message.reply_text(f"📭 链接 {link} 暂无数据")

    total_s = sum(r[1] for r in rows)
    conf_s = sum(r[1] for r in rows if r[2] == 1)
    
    report = f"📊 **{link} 精确报表**\n━━━━━━━━━━━━━━\n"
    report += f"📈 总提交成功: {total_s}\n"
    report += f"💰 管理员已加: {conf_s}\n"
    report += f"📦 总计组数: {len(rows)}\n\n"
    report += "**最近明细：**\n"
    for r in rows[-10:]: # 显示最近10条
        tag = "✅" if r[2] == 1 else "⏳"
        report += f"{tag} {r[0]} | {r[1]}\n"
    
    await update.message.reply_text(report, parse_mode='Markdown')

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^(\+|加单)$") & filters.REPLY, handle_confirm))
    app.add_handler(MessageHandler(filters.Regex(r"^统计\s+"), handle_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, monitor_messages))
    print("机器人已启动...")
    app.run_polling()

if name == '__main__':
    main()
