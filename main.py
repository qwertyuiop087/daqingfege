import re
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= 配置区 =================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"  # 填入 Token
MY_ID = 6042965834             # 填入你的数字 ID (超级管理员)
# ==========================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 获取北京时间
def get_beijing_time():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

def init_db():
    conn = sqlite3.connect('stats.db')
    cursor = conn.cursor()
    # 存储最终确认的加减单数据
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_confirmed (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link TEXT, file_name TEXT, final_val INTEGER,
        admin_name TEXT, bj_time TEXT)''')
    # 管理员权限表
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
    """授权新管理员：回复对方消息发送 /授权"""
    if update.effective_user.id != MY_ID: return
    if not update.message.reply_to_message:
        return await update.message.reply_text("💡 请通过“回复”对方的消息来使用 /授权")
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR REPLACE INTO admins (user_id, name) VALUES (?, ?)', (target.id, target.full_name))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 已成功授权管理员权限给：{target.full_name}")

async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """核心：管理员回复 +数字 或 -数字"""
    if not is_admin(update.effective_user.id) or not update.message.reply_to_message:
        return

    action_text = update.message.text.strip()
    source_text = update.message.reply_to_message.text
    if not source_text: return

    # 1. 提取链接
    link_match = re.search(r"([a-zA-Z0-9-]+\.vip)", source_text)
    if not link_match: return
    link = link_match.group(1)

    # 2. 提取多行包号 (抓取“包号”到下一个关键词之间的内容)
    file_block_match = re.search(r"包号[：:](.*?)(?=手机号|成功|数量|失败|$)", source_text, re.DOTALL)
    if file_block_match:
        f_name = " ".join(file_block_match.group(1).strip().split())
    else:
        f_name = source_text.split('\n')[0][:30].strip()

    # 3. 提取操作数值
    val_match = re.search(r"^([+-])(\d+)$", action_text)
    if not val_match: return

    sign, num = val_match.group(1), int(val_match.group(2))
    final_val = num if sign == '+' else -num
    now_time = get_beijing_time()

    # 4. 存入数据库
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
    """汇总报表：发送 统计全部"""
    if not is_admin(update.effective_user.id): return
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT link, SUM(final_val), COUNT(id) FROM admin_confirmed GROUP BY link').fetchall()
    conn.close()

    if not rows: return await update.message.reply_text("📭 暂无任何统计数据")

    total_all = 0
    report = f"📋 **全部链接汇总报表**\n"
    report += f"🕒 统计时间：`{get_beijing_time()}`\n"
    report += "━━━━━━━━━━━━━━\n"
    for row in rows:
        report += f"🌐 `{row[0]}`\n累计数量：**{row[1]}** ({row[2]}笔)\n\n"
        total_all += row[1]
    report += f"━━━━━━━━━━━━━━\n🌟 **总计总数量：{total_all}**"
    await update.message.reply_text(report, parse_mode='Markdown')

async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """清空数据：发送 清空全部"""
    if update.effective_user.id != MY_ID: return
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admin_confirmed')
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑 **所有统计记录已成功清空！**\n北京时间：`{get_beijing_time()}`")

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """明细查询：统计 链接"""
    if not is_admin(update.effective_user.id): return
    parts = update.message.text.split()
    if len(parts) < 2: return
    link = parts[1]
    
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT file_name, final_val, bj_time FROM admin_confirmed WHERE link = ?', (link,)).fetchall()
    conn.close()

    if not rows: return await update.message.reply_text(f"📭 链接 `{link}` 暂无明细记录")

    total_sum = sum(r[1] for r in rows)
    report = f"📊 **单链详细报表：{link}**\n"
    report += f"💰 当前实时总额：**{total_sum}**\n"
    report += "━━━━━━━━━━━━━━\n"
    for r in rows[-10:]:
        mark = "➕" if r[1] > 0 else "➖"
        display_name = (r[0][:15] + "..") if len(r[0]) > 15 else r[0]
        report += f"{mark} `{display_name}` | **{r[1]}** | `{r[2][11:16]}`\n"
    
    report += "\n*(仅显示最近10条明细)*"
    await update.message.reply_text(report, parse_mode='Markdown')

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    
    # 指令汉化
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("机器人已就绪。回复消息发送 +数字/-数字 统计。")))
    app.add_handler(CommandHandler("授权", add_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^清空全部$"), clear_data))
    
    # 逻辑汉化
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"^[+-]\d+$"), handle_admin_action))
    app.add_handler(MessageHandler(filters.Regex(r"^统计全部$"), query_all))
    app.add_handler(MessageHandler(filters.Regex(r"^统计\s+"), handle_query))
    
    app.run_polling()

if __name__ == '__main__':
    main()
