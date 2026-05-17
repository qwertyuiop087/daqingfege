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
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

# --- 【彻底修复 Bug】识别与提取逻辑 ---
def extract_link_smartly(text):
    if not text: return None
    
    # 动态匹配任意合法的网址后缀（如 .com, .vip, .top, .net, .org 等）
    url_match = re.search(r"([a-zA-Z0-9-]+\.[a-zA-Z]{2,4})", text)
    if url_match: 
        return url_match.group(1).lower()
        
    # 【严重Bug修复】彻底砍掉之前的数字补全和盲猜逻辑！
    # 如果消息里没有带合法后缀的网址，这里直接返回 None，后面会统一归类到 "手动录入"
    return None

def auto_extract_filenames(text):
    start_match = re.search(r"(包号|编号|单反)[：:](.*?)(?=手机|尾号|数量|话术|送达|用浏览器|$)", text, re.DOTALL)
    if not start_match: 
        # 如果没有“包号：”关键字，但消息很长（比如转发的完整单子），截取第一行
        # 如果是直接发的指令如 "+100 大晴_20"，msg_text 去了前面的 +100，剩下的就是包号
        clean_text = re.sub(r"^[+-]\d+\s*", "", text).strip()
        return clean_text[:50] if clean_text else "未指定包号"
        
    raw_content = start_match.group(2).strip()
    found_items = []
    for line in raw_content.split('\n'):
        line = line.strip()
        if re.search(r"\d", line) and (("-" in line) or ("." in line) or ("A" in line.upper())):
            clean_line = re.sub(r"^[^\da-zA-Z\u4e00-\u9fa5]*?[\u4e00-\u9fa5]{2,3}\s+", "", line)
            found_items.append(clean_line.strip())
    return ", ".join(found_items) if found_items else None

# --- 排序辅助函数 ---
def sort_by_package_number(row):
    file_name = row[0]
    if not file_name: return (1, "")
    num_match = re.search(r"(\d+)\s*$", file_name)
    if num_match: return (0, int(num_match.group(1)))
    return (1, file_name)

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

    # 判定误触：如果没有回复任何人，且当前消息里除了数字指令啥都没写，就无视
    link_in_msg = extract_link_smartly(msg_text)
    clean_cmd_check = re.sub(r"^[^\s]*", "", msg_text).strip() # 看看除指令外有没有跟文本
    if not reply_msg and not link_in_msg and not clean_cmd_check: return 

    if reply_msg:
        target_worker = reply_msg.from_user
        source_text = reply_msg.text or reply_msg.caption or msg_text
    else:
        target_worker = admin_user
        source_text = msg_text

    # 提取：没有网址就严格打入"手动录入"，绝对不能污染 link 字段
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

# --- 报表与统计 ---
async def query_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id) or not is_admin(update.effective_user.id, chat_id): return
    conn = sqlite3.connect('stats.db')
    links = conn.execute('SELECT link, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY link', (chat_id,)).fetchall()
    workers = conn.execute('SELECT worker_name, worker_id, SUM(final_val) FROM admin_confirmed WHERE chat_id = ? GROUP BY worker_id ORDER BY SUM(final_val) DESC', (chat_id,)).fetchall()
    conn.close()
    
    if not links:
        return await context.bot.send_message(chat_id=chat_id, text="📭 暂无统计数据")
        
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
    target = parts[1].strip().lower()
    
    conn = sqlite3.connect('stats.db')
    rows = conn.execute('SELECT file_name, final_val, worker_name, worker_id, bj_time FROM admin_confirmed WHERE chat_id = ? AND link LIKE ?', (chat_id, f"%{target}%")).fetchall()
    conn.close()
    
    if not rows:
        return await context.bot.send_message(chat_id=chat_id, text=f"📭 链接 `{target}` 暂无明细记录")

    sorted_rows = sorted(rows, key=sort_by_package_number)

    report = f"📊 **明细记录: {target}**\n━━━━━━━━━━━━━━\n"
    for r in sorted_rows:
        mark = "➕" if r[1] > 0 else "➖"
        report += f"{mark} `{r[0]}` | **{r[1]}**\n👤 [{r[2]}](tg://user?id={r[3]}) | ⏰ {r[4].split()[1]}\n\n"
    
    await context.bot.send_message(chat_id=chat_id, text=report[:4000], parse_mode='Markdown')

# --- 资金查询与管理 ---
async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_chat_authorized(chat_id): return
    conn = sqlite3.connect('stats.db')
    res = conn.execute('SELECT SUM(final_val) FROM admin_confirmed WHERE chat_id = ? AND worker_id = ?', (chat_id, update.effective_user.id)).fetchone()
    conn.close()
    bal = res[0] if res[0] else 0
    await context.bot.send_message(
        chat_id=chat_id, 
        text=f"💰 [{update.effective_user.full_name}](tg://user?id={update.effective_user.id})\n实时余额: `{bal}`\n⏰ {get_beijing_time()}", 
        parse_mode='Markdown'
    )

async def admin_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_user.id != MY_ID or not update.message.reply_to_message: return
    target = update.message.reply_to_message.from_user
    cmd = update.message.text.strip()
    
    conn = sqlite3.connect('stats.db')
    if "授权管理员" in cmd:
        conn.execute('INSERT OR REPLACE INTO admins (user_id, chat_id, name) VALUES (?, ?, ?)', (target.id, chat_id, target.full_name))
        text = f"👑 **已成功授权管理员:** [{target.full_name}](tg://user?id={target.id})"
    else:
        conn.execute('DELETE FROM admins WHERE user_id = ? AND chat_id = ?', (target.id, chat_id))
        text = f"❌ **已撤销管理员权限:** {target.full_name}"
    conn.commit()
    conn.close()
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')

async def service_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_user.id != MY_ID: return
    cmd = update.message.text.strip()
    
    conn = sqlite3.connect('stats.db')
    if "授权群聊" in cmd:
        conn.execute('INSERT OR IGNORE INTO authorized_chats (chat_id) VALUES (?)', (chat_id,))
        text = "✅ **本群服务已启动 (独立消息模式)**"
    else:
        conn.execute('DELETE FROM authorized_chats WHERE chat_id = ?', (chat_id,))
        text = "🚫 **本群服务已停止**"
    conn.commit()
    conn.close()
    await context.bot.send_message(chat_id=chat_id, text=text)

async def clear_all(update: Update, context: ContextTypes.DEFAULT_TYPE
