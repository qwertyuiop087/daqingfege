import re
import sqlite3
import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= 配置区 =================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"  # 填入 Token
MY_ID = 6042965834            # 填入你的数字 ID
# ==========================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def init_db():
    conn = sqlite3.connect('stats.db')
    cursor = conn.cursor()
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
        return await update.message.reply_text("💡 请回复对方的消息发送 /add")
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR REPLACE INTO admins (user_id, name) VALUES (?, ?)', (target.id, target.full_name))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 已授权新管理员：{target.full_name}")

async def handle_admin_plus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id) or not update.message.reply_to_message:
        return

    admin_text = update.message.text.strip()
    source_text = update.message.reply_to_message.text
    if not source_text: return

    # --- 改进的解析逻辑 ---
    
    # 1. 提取链接 (依然认 .vip)
    link_match = re.search(r"([a-zA-Z0-9-]+\.vip)", source_text)
    if not link_match:
        return await update.message.reply_text("❌ 无法识别 .vip 链接。")
    link = link_match.group(1)

    # 2. 提取包号 (新逻辑)
    # 优先找“包号：xxxx”或者“包号: xxxx”
    file_match = re.search(r"包号[：:]\s*([^\n]+)", source_text)
    if file_match:
        f_name = file_match.group(1).strip()
    else:
        # 如果没写“包号”两个字，就看有没有包含 .txt 的字眼
        txt_match = re.search(r"([^\s]+\.txt)", source_text)
        if txt_match:
            f_name = txt_match.group(1)
        else:
            # 如果还是没有，就取第一行前20个字作为代称
            f_name = source_text.split('\n')[0][:20].strip()

    # 3. 提取管理员输入的数字
    val_match = re.search(r"^\+(\d+)$", admin_text)
    if not val_match: return
    final_val = int(val_match.group(1))

    # --- 存储 ---
    conn = sqlite3.connect('stats.db')
    conn.execute('''INSERT INTO admin_confirmed (link, file_name, final_val, admin_name) 
                    VALUES (?, ?, ?, ?)''', (link, f_name, final_val, update.effective_user.full_name))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ **管理员加单成功**\n"
        f"🔗 链接: `{link}`\n"
        f"📄 包号: `{f_name}`\n"
        f"💰 加单数: `{final_val}`"
    )

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
    report = f"📊 **{link} 统计结果**\n━━━━━━━━━━━━━━\n"
    report += f"💰 加单总额: **{total_sum}**\n"
    report += f"📦 总组数: {len(rows)}\n\n**最近明细：**\n"
    for r in rows[-10:]:
        report += f"✅ `{r[0]}` | +{r[1]} | {r[2][5:16]}\n"
    await update.message.reply_text(report, parse_mode='Markdown')

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", add_admin))
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"^\+\d+$"), handle_admin_plus))
    app.add_handler(MessageHandler(filters.Regex(r"^统计\s+"), handle_query))
    app.run_polling()

if __name__ == '__main__':
    main()
