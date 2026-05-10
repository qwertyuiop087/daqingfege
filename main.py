import re
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= 配置区 =================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"  # 填入你的 Token
MY_ID = 6042965834            # 填入你的数字 ID (超级管理员)
# ==========================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 1. 工具函数：北京时间 ---
def get_beijing_time():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

# --- 2. 工具函数：智能链接提取 (含自动补全) ---
def extract_link_smartly(text):
    # 优先匹配完整的 .vip
    full_link = re.search(r"([a-zA-Z0-9-]+\.vip)", text)
    if full_link:
        return full_link.group(1), False
    # 没找到则匹配文本中最后出现的 4-8 位连续数字
    all_numbers = re.findall(r"\d{4,8}", text)
    if all_numbers:
        smart_link = f"{all_numbers[-1]}.vip"
        return smart_link, True
    return None, False

# --- 3. 数据库初始化 ---
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

# --- 4. 权限校验 ---
def is_admin(user_id):
    if user_id == MY_ID: return True
    conn = sqlite3.connect('stats.db')
    res = conn.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return True if res else False

# --- 5. 指令处理：授权 ---
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    if not update.message.reply_to_message:
        return await update.message.reply_text("💡 请回复对方的消息并发送 授权")
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR REPLACE INTO admins (user_id, name) VALUES (?, ?)', (target.id, target.full_name))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 已成功授权管理员：{target.full_name}")

# --- 6. 指令处理：清空 ---
async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admin_confirmed')
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑 **所有统计记录已成功清空！**\n北京时间：`{get_beijing_time()}`")

# --- 7. 核心逻辑：加减单处理 ---
async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id) or not update.message.reply_to_message:
        return
    action_text = update.message.text.strip()
    source_text = update.message.reply_to_message.text
    if not source_text: return

    # 智能识别链接
    link, is_auto = extract_link_smartly(source_text)
    if not link:
        return await update.message.reply_text("⚠️ 识别失败：未发现网址或连续数字编号。")

    # 提取多行包号
    file_block_match = re.search(r"包号[：:](.*?)(?=手机号|成功|数量|失败|$)", source_text, re.DOTALL)
    f_name = " ".join(file_block_match.group(1).strip().split()) if file_block_match else source_text.split('\n')[0][:30].strip()

    # 提取数值
    val_match = re.search(r"^([+-])(\d+)$", action_text)
    if not val_match: return
    sign, num = val_match.group(1), int(val_match.group(2))
    final_val = num if sign == '+' else -num
    now_time = get_beijing_time()

    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT INTO admin_confirmed (link, file_name, final_val, admin_name, bj_time) VALUES (?, ?, ?, ?, ?)', 
                 (link, f_name, final_val, update.effective_user.full_name, now_time))
    conn.commit()
    conn.close()

    status = "加单成功" if sign == '+' else "减单成功"
    link_info = f"`{link}` (补全)" if is_auto else f"`{link}`"
    response = (
        f"🎯 **管理员{status}**\n━━━━━━━━━━━━━━\n"
        f"🌐 **链接：** {link_info}\n📦 **包号：** `{f_name}`\n"
        f"🔢 **变动：** `{action_text}`\n👤 **操作：** {update.effective_user.first_name}\n"
        f"⏰ **时间：** `{now_time}`"
    )
    await update.message.reply_text(response, parse_mode='Markdown')

# --- 8. 查询逻辑：统计全部 ---
async def query_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT link, SUM(final_val), COUNT(id) FROM admin_confirmed GROUP BY link').fetchall()
    conn.close()
    if not rows: return await update.message.reply_text("📭 暂无统计数据")
    total_all = 0
    report = f"📋 **全部链接汇总报表**\n🕒 时间：`{get_beijing_time()}`\n━━━━━━━━━━━━━━\n"
    for row in rows:
        report += f"🌐 `{row[0]}`\n累计数量：**{row[1]}** ({row[2]}笔)\n\n"
        total_all += row[1]
    report += f"━━━━━━━━━━━━━━\n🌟 **总计总数量：{total_all}**"
    await update.message.reply_text(report, parse_mode='Markdown')

# --- 9. 查询逻辑：单链统计 ---
async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    parts = update.message.text.split()
    if len(parts) < 2: return
    link = parts[1]
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT file_name, final_val, bj_time FROM admin_confirmed WHERE link = ?', (link,)).fetchall()
    conn.close()
    if not rows: return await update.message.reply_text(f"📭 `{link}` 暂无记录")
    total_sum = sum(r[1] for r in rows)
    report = f"📊 **单链报表：{link}**\n实时总额：**{total_sum}**\n━━━━━━━━━━━━━━\n"
    for r in rows[-10:]:
        mark = "➕" if r[1] > 0 else "➖"
        report += f"{mark} `{r[0][:15]}` | **{r[1]}** | `{r[2][11:16]}`\n"
    await update.message.reply_text(report, parse_mode='Markdown')

# --- 10. 主函数 ---
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    
    # 权限与维护
    app.add_handler(MessageHandler(filters.Regex(r"^(授权|/auth)$"), add_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^清空全部$"), clear_data))
    
    # 统计核心
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"^[+-]\d+$"), handle_admin_action))
    
    # 查询指令
    app.add_handler(MessageHandler(filters.Regex(r"^统计全部$"), query_all))
    app.add_handler(MessageHandler(filters.Regex(r"^统计\s+"), handle_query))
    
    print("机器人已启动...")
    app.run_polling()

if __name__ == '__main__':
    main()
