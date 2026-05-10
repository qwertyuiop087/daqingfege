import re
import sqlite3
import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= 配置区 =================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"  # 填入 Token
MY_ID = 6042965834             # 填入你的数字 ID
# ==========================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def init_db():
    conn = sqlite3.connect('stats.db')
    cursor = conn.cursor()
    # 存储最终确认的加减单数据
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_confirmed (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link TEXT, file_name TEXT, final_val INTEGER,
        admin_name TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, name TEXT)''')
    conn.commit()
    conn.close()

def is_admin(user_id):
    if user_id == MY_ID: return True
    conn = sqlite3.connect('stats.db')
    res = conn.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return True if res else False

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    if not update.message.reply_to_message:
        return await update.message.reply_text("💡 请回复对方消息发送 /add")
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR REPLACE INTO admins (user_id, name) VALUES (?, ?)', (target.id, target.full_name))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 已授权新管理员：{target.full_name}")

async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理管理员回复 +数字 或 -数字"""
    if not is_admin(update.effective_user.id) or not update.message.reply_to_message:
        return

    action_text = update.message.text.strip()
    source_text = update.message.reply_to_message.text
    if not source_text: return

    # 1. 提取链接
    link_match = re.search(r"([a-zA-Z0-9-]+\.vip)", source_text)
    if not link_match: return
    link = link_match.group(1)

    # 2. 提取多行包号 (优化后的抓取逻辑)
    file_block_match = re.search(r"包号[：:](.*?)(?=手机号|成功|数量|失败|$)", source_text, re.DOTALL)
    if file_block_match:
        f_name = " ".join(file_block_match.group(1).strip().split())
    else:
        f_name = source_text.split('\n')[0][:30].strip()

    # 3. 提取数字（支持 + 和 -）
    val_match = re.search(r"^([+-])(\d+)$", action_text)
    if not val_match: return

    sign, num = val_match.group(1), int(val_match.group(2))
    final_val = num if sign == '+' else -num

    conn = sqlite3.connect('stats.db')
    conn.execute('''INSERT INTO admin_confirmed (link, file_name, final_val, admin_name) 
                    VALUES (?, ?, ?, ?)''', (link, f_name, final_val, update.effective_user.full_name))
    conn.commit()
    conn.close()

    status = "加单" if sign == '+' else "减单"
    await update.message.reply_text(f"✅ **{status}成功**\n🔗 `{link}`\n📄 `{f_name[:20]}`\n🔢 数值: `{final_val}`")

async def query_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT link, SUM(final_val), COUNT(id) FROM admin_confirmed GROUP BY link').fetchall()
    conn.close()

    if not rows: return await update.message.reply_text("📭 暂无统计数据")

    total_all = 0
    report = "📋 **所有链接汇总**\n━━━━━━━━━━━━━━\n"
    for row in rows:
        report += f"🌐 `{row[0]}`: **{row[1]}**\n"
        total_all += row[1]
    report += f"━━━━━━━━━━━━━━\n总计总数量：**{total_all}**"
    await update.message.reply_text(report, parse_mode='Markdown')

async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admin_confirmed')
    conn.commit()
    conn.close()
    await update.message.reply_text("🗑 **所有数据已清空！**")

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    parts = update.message.text.split()
    if len(parts) < 2: return
    link = parts[1]
    
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT file_name, final_val, timestamp FROM admin_confirmed WHERE link = ?', (link,)).fetchall()
    conn.close()

    if not rows: return await update.message.reply_text(f"📭 `{link}` 暂无记录")

    total_sum = sum(r[1] for r in rows)
    report = f"📊 **明细: {link}**\n当前总额: **{total_sum}**\n\n"
    for r in rows[-8:]:
        mark = "✅" if r[1] > 0 else "❌"
        report += f"{mark} `{r[0][:15]}` | {r[1]}\n"
    await update.message.reply_text(report, parse_mode='Markdown')

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", add_admin))
    app.add_handler(CommandHandler("clear_all", clear_data))
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"^[+-]\d+$"), handle_admin_action))
    app.add_handler(MessageHandler(filters.Regex(r"^统计全部$"), query_all))
    app.add_handler(MessageHandler(filters.Regex(r"^统计\s+"), handle_query))
    print("机器人已启动...")
    app.run_polling()

# 这里是修复后的关键点！前后都是两个下划线
if __name__ == '__main__':
    main()
