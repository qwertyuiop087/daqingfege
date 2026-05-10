import re
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= 配置区 =================
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"  # 填入你的 Token
MY_ID = 6042965834             # 填入你的数字 ID (主管理员)
# ==========================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 1. 工具函数 ---
def get_beijing_time():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

def extract_link_smartly(text):
    full_link = re.search(r"([a-zA-Z0-9-]+\.vip)", text)
    if full_link: return full_link.group(1), False
    all_numbers = re.findall(r"\d{4,8}", text)
    if all_numbers: return f"{all_numbers[-1]}.vip", True
    return None, False

# --- 2. 数据库逻辑 (新增群授权表和群ID字段) ---
def init_db():
    conn = sqlite3.connect('stats.db')
    cursor = conn.cursor()
    # 增加 chat_id 字段用于数据隔离
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_confirmed (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link TEXT, file_name TEXT, final_val INTEGER,
        admin_name TEXT, bj_time TEXT, chat_id INTEGER)''')
    # 管理员权限表
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, name TEXT)''')
    # 新增：已授权的群聊表
    cursor.execute('''CREATE TABLE IF NOT EXISTS authorized_chats (chat_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

def is_admin(user_id):
    if user_id == MY_ID: return True
    conn = sqlite3.connect('stats.db')
    res = conn.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return True if res else False

def is_chat_authorized(chat_id):
    conn = sqlite3.connect('stats.db')
    res = conn.execute('SELECT 1 FROM authorized_chats WHERE chat_id = ?', (chat_id,)).fetchone()
    conn.close()
    return True if res else False

# --- 3. 权限指令 ---
async def auth_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """主管理员授权当前群聊使用机器人"""
    if update.effective_user.id != MY_ID: return
    chat_id = update.effective_chat.id
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR IGNORE INTO authorized_chats (chat_id) VALUES (?)', (chat_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ **群聊授权成功！**\n本群数据已独立，现在可以开始统计了。\n群ID: `{chat_id}`")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """授权管理员 (主管理员可用)"""
    if update.effective_user.id != MY_ID: return
    if not update.message.reply_to_message:
        return await update.message.reply_text("💡 请回复对方的消息并发送 授权")
    target = update.message.reply_to_message.from_user
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR REPLACE INTO admins (user_id, name) VALUES (?, ?)', (target.id, target.full_name))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 已成功授权管理员：{target.full_name}")

# --- 4. 核心逻辑：加减单 (带群隔离) ---
async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    # 检查群是否授权
    if not is_chat_authorized(chat_id): return
    # 检查是否是管理员
    if not is_admin(update.effective_user.id) or not update.message.reply_to_message: return

    action_text = update.message.text.strip()
    source_text = update.message.reply_to_message.text
    if not source_text: return

    link, is_auto = extract_link_smartly(source_text)
    if not link: return await update.message.reply_text("⚠️ 未识别到网址或编号。")

    file_block_match = re.search(r"包号[：:](.*?)(?=手机号|成功|数量|失败|$)", source_text, re.DOTALL)
    f_name = " ".join(file_block_match.group(1).strip().split()) if file_block_match else source_text.split('\n')[0][:30].strip()

    val_match = re.search(r"^([+-])(\d+)$", action_text)
    if not val_match: return
    sign, num = val_match.group(1), int(val_match.group(2))
    final_val = num if sign == '+' else -num
    
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT INTO admin_confirmed (link, file_name, final_val, admin_name, bj_time, chat_id) VALUES (?, ?, ?, ?, ?, ?)', 
                 (link, f_name, final_val, update.effective_user.full_name, get_beijing_time(), chat_id))
    conn.commit()
    conn.close()

    status = "加单成功" if sign == '+' else "减单成功"
    link_info = f"`{link}` (补全)" if is_auto else f"`{link}`"
    await update.message.reply_text(f"🎯 **管理员{status}**\n━━━━━━━━━━━━━━\n🌐 链接: {link_info}\n📦 包号: `{f_name}`\n🔢 变动: `{action_text}`\n⏰ 时间: `{get_beijing_time()}`")

# --- 5. 查询逻辑 (仅显示本群数据) ---
async def query_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id): return

    conn = sqlite3.connect('stats.db')
    # 只查询当前群 chat_id 的数据
    rows = conn.execute('SELECT link, SUM(final_val), COUNT(id) FROM admin_confirmed WHERE chat_id = ? GROUP BY link', (chat_id,)).fetchall()
    conn.close()

    if not rows: return await update.message.reply_text("📭 本群暂无统计数据")
    
    total_all = 0
    report = f"📋 **本群独立汇总报表**\n🕒 时间：`{get_beijing_time()}`\n━━━━━━━━━━━━━━\n"
    for row in rows:
        report += f"🌐 `{row[0]}`\n累计数量：**{row[1]}** ({row[2]}笔)\n\n"
        total_all += row[1]
    report += f"━━━━━━━━━━━━━━\n🌟 **总计总数量：{total_all}**"
    await update.message.reply_text(report, parse_mode='Markdown')

async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """仅清空本群数据"""
    if update.effective_user.id != MY_ID: return
    chat_id = update.effective_chat.id
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admin_confirmed WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑 **本群统计记录已清空！**")

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    
    # 指令注册
    app.add_handler(MessageHandler(filters.Regex(r"^授权群聊$"), auth_chat)) # 新增
    app.add_handler(MessageHandler(filters.Regex(r"^(授权|/auth)$"), add_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^清空全部$"), clear_data))
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"^[+-]\d+$"), handle_admin_action))
    app.add_handler(MessageHandler(filters.Regex(r"^统计全部$"), query_all))
    
    print("机器人已启动 (隔离授权版)...")
    app.run_polling()

if __name__ == '__main__':
    main()
