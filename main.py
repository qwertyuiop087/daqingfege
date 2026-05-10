import re
import sqlite3
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= 配置区 =================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"  # 填入 @BotFather 给你的 Token
MY_ID = 6042965834             # 填入你的数字 ID (超级管理员)
# ==========================================

# 启用日志
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
    await update.message.reply_text(
        "🛠 **统计机器人已就绪**\n\n"
        "✅ **操作指南：**\n"
        "1. **确认加单**：回复交单消息发送 `+` 或 `加单` \n"
        "2. **统计查询**：发送 `统计 链接` (如: `统计 95506.vip`)\n"
        "3. **添加管理**：回复某人消息发送 `/add` \n"
        "4. **查看面板**：发送 `/start` 查看此帮助",
        parse_mode='Markdown')

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """超级管理员通过回复某人添加为管理员"""
    if update.effective_user.id != MY_ID: return
    if not update.message.reply_to_message:
        return await update.message.reply_text("💡 请通过“回复”对方的消息来使用 /add")
    
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR REPLACE INTO admins (user_id, name) VALUES (?, ?)', (target.id, target.full_name))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 已授权新管理员：{target.full_name}")

async def monitor_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """自动抓取群里的交单数据"""
    text = update.message.text
    if not text: return
    
    # 识别：成功数字、.vip链接、.txt文件名
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
    """回复 + 号确认加单"""
    if not is_admin(update.effective_user.id) or not update.message.reply_to_message: return
    
    msg_id = update.message.reply_to_message.message_id
    conn = sqlite3.connect('stats.db')
    cur = conn.cursor()
    cur.execute('UPDATE records SET is_confirmed = 1, admin_name = ? WHERE message_id = ?', 
                (update.effective_user.full_name, msg_id))
    if cur.rowcount > 0:
        await update.message.reply_text(f"🆗 加单已确认 (管理员: {update.effective_user.first_name})")
    conn.commit()
    conn.close()

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """输入 '统计 链接' 查询结果"""
    if not is_admin(update.effective_user.id): return
    parts = update.message.text.split()
    if len(parts) < 2: return
    link = parts[1]
    
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT file_name, success_val, is_confirmed FROM records WHERE link = ?', (link,)).fetchall()
    conn.close()

    if not rows: return await update.message.reply_text(f"📭 链接 `{link}` 暂无交单记录")

    total_s = sum(r[1] for r in rows)
    conf_s = sum(r[1] for r in rows if r[2] == 1)
    
    report = f"📊 **{link} 统计报表**\n━━━━━━━━━━━━━━\n"
    report += f"📈 总提交条数: {total_s}\n"
    report += f"💰 已加单总数: {conf_s}\n"
    report += f"📦 提交总组数: {len(rows)}\n\n"
    report += "**最近明细：**\n"
    for r in rows[-10:]: # 显示最近10条明细
        tag = "✅" if r[2] == 1 else "⏳"
        report += f"{tag} `{r[0]}` | {r[1]}\n"
    
    await update.message.reply_text(report, parse_mode='Markdown')

def main():
    init_db()
    # 启动机器人
    application = Application.builder().token(BOT_TOKEN).build()
    
    # 注册处理器
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_admin))
    application.add_handler(MessageHandler(filters.Regex(r"^(\+|加单)$") & filters.REPLY, handle_confirm))
    application.add_handler(MessageHandler(filters.Regex(r"^统计\s+"), handle_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, monitor_messages))
    
    print("机器人已启动...")
    application.run_polling()

# 重点修复：这里必须是 __name__ 和 '__main__'
if __name__ == '__main__':
    main()
