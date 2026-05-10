import re
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= 配置区 =================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"  # 填入 Token
MY_ID = 6042965834             # 填入你的数字 ID
# ==========================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def get_beijing_time():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

def init_db():
    conn = sqlite3.connect('stats.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_confirmed (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link TEXT, file_name TEXT, final_val INTEGER,
        admin_name TEXT, bj_time TEXT)''')
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
    """授权逻辑：现在支持回复对方并发送 '授权' 或 '/auth'"""
    if update.effective_user.id != MY_ID: return
    if not update.message.reply_to_message:
        return await update.message.reply_text("💡 请通过“回复”对方的消息来发送 授权")
    
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR REPLACE INTO admins (user_id, name) VALUES (?, ?)', (target.id, target.full_name))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 已成功授权管理员：{target.full_name}")

async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id) or not update.message.reply_to_message:
        return

    action_text = update.message.text.strip()
    source_text = update.message.reply_to_message.text
    if not source_text: return

    link_match = re.search(r"([a-zA-Z0-9-]+\.vip)", source_text)
    if not link_match: return
    link = link_match.group(1)

    file_block_match = re.search(r"包号[：:](.*?)(?=手机号|成功|数量|失败|$)", source_text, re.DOTALL)
    f_name = " ".join(file_block_match.group(1).strip().split()) if file_block_match else source_text.split('\n')[0][:30].strip()

    val_match = re.search(r"^([+-])(\d+)$", action_text)
    if not val_match: return

    sign, num = val_match.group(1), int(val_match.group(2))
    final_val = num if sign == '+' else -num
    now_time = get_beijing_time()

    conn = sqlite3.connect('stats.db')
    conn.execute('''INSERT INTO admin_confirmed (link, file_name, final_val, admin_name, bj_time) 
                    VALUES (?, ?, ?, ?, ?)''', (link, f_name, final_val, update.effective_user.full_name, now_time))
    conn.commit()
    conn.close()

    status_text = "加单成功" if sign == '+' else "减单成功"
    response = (
        f"🎯 **管理员{status_text}**\n"
        f"━━━━━━━━━━━━━━\n"
        f"🌐 **链接：** `{link}`\n"
        f"📦 **包号：** `{f_name}`\n"
        f"🔢 **变动：** `{action_text}`\n"
        f"👤 **操作：** {update.effective_user.first_name}\n"
        f"⏰ **北京时间：** `{now_time}`"
    )
    await update.message.reply_text(response, parse_mode='Markdown')

async def query_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT link, SUM(final_val), COUNT(id) FROM admin_confirmed GROUP BY link').fetchall()
    conn.close()

    if not rows: return await update.message.reply_text("📭 暂无统计数据")

    total_all = 0
    report = f"📋 **全部链接汇总报表**\n🕒 统计时间：`{get_beijing_time()}`\n━━━━━━━━━━━━━━\n"
    for row in rows:
        report += f"🌐 `{row[0]}`\n累计数量：**{row[1]}** ({row[2]}笔)\n\n"
        total_all += row[1]
    report += f"━━━━━━━━━━━━━━\n🌟 **总计总数量：{total_all}**"
    await update.message.reply_text(report, parse_mode='Markdown')

async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admin_confirmed')
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑 **所有统计记录已清空！**\n北京时间：`{get_beijing_time()}`")

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    parts = update.message.text.split()
    if len(parts) < 2: return
    link = parts[1]
    
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT file_name, final_val, bj_time FROM admin_confirmed WHERE link = ?', (link,)).fetchall()
    conn.close()

    if not rows: return await update.message.reply_text(f"📭 `{link}` 暂无明细记录")

    total_sum = sum(r[1] for r in rows)
    report = f"📊 **单链报表：{link}**\n实时总额：**{total_sum}**\n━━━━━━━━━━━━━━\n"
    for r in rows[-10:]:
        mark = "➕" if r[1] > 0 else "➖"
        display_name = (r[0][:15] + "..") if len(r[0]) > 15 else r[0]
        report += f"{mark} `{display_name}` | **{r[1]}** | `{r[2][11:16]}`\n"
    await update.message.reply_text(report, parse_mode='Markdown')

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    
    # --- 指令处理逻辑 ---
    # 1. 授权：支持回复对方并发送 "/auth" 或 直接发送中文 "授权"
    app.add_handler(CommandHandler("auth", add_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^(授权|/授权)$"), add_admin))
    
    # 2. 清空：支持 "清空全部"
    app.add_handler(MessageHandler(filters.Regex(r"^清空全部$"), clear_data))
    
    # 3. 加减单：回复 +100 或 -100
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"^[+-]\d+$"), handle_admin_action))
    
    # 4. 统计查询
    app.add_handler(MessageHandler(filters.Regex(r"^统计全部$"), query_all))
    app.add_handler(MessageHandler(filters.Regex(r"^统计\s+"), handle_query))
    
    print("机器人启动中...")
    app.run_polling()

if __name__ == '__main__':
    main()
