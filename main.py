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

# --- 2. 数据库初始化 ---
def init_db():
    conn = sqlite3.connect('stats.db')
    cursor = conn.cursor()
    # 统计数据表
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_confirmed (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link TEXT, file_name TEXT, final_val INTEGER,
        admin_name TEXT, bj_time TEXT, chat_id INTEGER)''')
    # 【更新】管理员表：增加 chat_id 实现权限隔离
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER, chat_id INTEGER, name TEXT, PRIMARY KEY (user_id, chat_id))''')
    # 群授权表
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

# --- 3. 权限指令 (仅主管理员可用) ---
async def auth_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    chat_id = update.effective_chat.id
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR IGNORE INTO authorized_chats (chat_id) VALUES (?)', (chat_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ **本群服务已开启**\n权限与数据均已实现本群隔离。")

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """停止本群服务并清空数据"""
    if update.effective_user.id != MY_ID: return
    chat_id = update.effective_chat.id
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM authorized_chats WHERE chat_id = ?', (chat_id,))
    conn.execute('DELETE FROM admin_confirmed WHERE chat_id = ?', (chat_id,))
    conn.execute('DELETE FROM admins WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🚫 **本群服务已停止**\n所有权限及统计数据已清空。")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    if not update.message.reply_to_message:
        return await update.message.reply_text("💡 请回复对方的消息发送 授权")
    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT OR REPLACE INTO admins (user_id, chat_id, name) VALUES (?, ?, ?)', (target.id, chat_id, target.full_name))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 已授权 **{target.full_name}** 为本群管理员。")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消管理员权限"""
    if update.effective_user.id != MY_ID: return
    if not update.message.reply_to_message:
        return await update.message.reply_text("💡 请回复对方的消息发送 取消管理员")
    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admins WHERE user_id = ? AND chat_id = ?', (target.id, chat_id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"❌ 已撤销 **{target.full_name}** 的本群管理员权限。")

# --- 4. 统计逻辑 ---
async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not is_chat_authorized(chat_id) or not is_admin(user_id, chat_id): return
    if not update.message.reply_to_message: return

    action_text = update.message.text.strip()
    source_text = update.message.reply_to_message.text
    link, is_auto = extract_link_smartly(source_text)
    if not link: return

    file_block_match = re.search(r"包号[：:](.*?)(?=手机号|成功|数量|失败|$)", source_text, re.DOTALL)
    f_name = " ".join(file_block_match.group(1).strip().split()) if file_block_match else "未识别包号"

    val_match = re.search(r"^([+-])(\d+)$", action_text)
    if not val_match: return
    sign, num = val_match.group(1), int(val_match.group(2))
    final_val = num if sign == '+' else -num
    now_time = get_beijing_time()
    
    conn = sqlite3.connect('stats.db')
    conn.execute('INSERT INTO admin_confirmed (link, file_name, final_val, admin_name, bj_time, chat_id) VALUES (?, ?, ?, ?, ?, ?)', 
                 (link, f_name, final_val, update.effective_user.full_name, now_time, chat_id))
    conn.commit()
    conn.close()

    status = "加单成功" if sign == '+' else "减单成功"
    await update.message.reply_text(
        f"🎯 **管理员{status}**\n━━━━━━━━━━━━━━\n"
        f"🌐 **链接:** `{link}`\n📦 **包号:** `{f_name}`\n"
        f"🔢 **变动:** `{action_text}`\n⏰ **时间:** `{now_time}`\n"
        f"👤 **操作:** {update.effective_user.first_name}", parse_mode='Markdown'
    )

async def query_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT link, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY link', (chat_id,)).fetchall()
    conn.close()
    if not rows: return await update.message.reply_text("📭 本群暂无统计。")
    report = f"📋 **本群汇总报表**\n🕒 `{get_beijing_time()}`\n━━━━━━━━━━━━━━\n"
    total = 0
    for row in rows:
        report += f"🌐 `{row[0]}`: **{row[1]}**\n"
        total += row[1]
    report += f"━━━━━━━━━━━━━━\n🌟 **总计：{total}**"
    await update.message.reply_text(report, parse_mode='Markdown')

async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    conn = sqlite3.connect('stats.db')
    conn.execute('DELETE FROM admin_confirmed WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑 **本群数据已清空。**")

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.Regex(r"^授权群聊$"), auth_chat))
    app.add_handler(MessageHandler(filters.Regex(r"^停止本群服务$"), stop_chat))
    app.add_handler(MessageHandler(filters.Regex(r"^(授权|/auth)$"), add_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^取消管理员$"), remove_admin))
    app.add_handler(MessageHandler(filters.Regex(r"^清空全部$"), clear_data))
    app.add_handler(MessageHandler(filters.Regex(r"^统计全部$"), query_all))
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"^[+-]\d+$"), handle_admin_action))
    app.run_polling()

if __name__ == '__main__': main()
