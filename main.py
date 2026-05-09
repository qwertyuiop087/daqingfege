import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"

# 临时存储用户设置（内存）
user_settings = {}

# /start 命令
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "你好，我是分包机器人！\n"
        "使用步骤：\n"
        "1️⃣ /setlines <行数> 设置分包行数\n"
        "2️⃣ 发送 TXT 文件，我会按行数分割并发送\n"
        "注意：每 10 个文件一批，每个文件间隔 3 秒"
    )

# /setlines 命令
async def set_lines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("用法：/setlines <行数>，例如 /setlines 50")
        return
    user_id = update.effective_user.id
    lines = int(context.args[0])
    user_settings[user_id] = lines
    await update.message.reply_text(f"已设置分包行数为 {lines} 行")

# 尝试多种编码读取 TXT 文件
def read_txt_file(filepath):
    encodings = ["utf-8", "gbk", "ansi", "utf-16"]
    for enc in encodings:
        try:
            with open(filepath, "r", encoding=enc, errors="ignore") as f:
                return f.readlines()
        except Exception:
            continue
    return None

# 文件处理函数
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lines_per_file = user_settings.get(user_id, 50)  # 默认 50 行

    doc = update.message.document

    # 只处理 TXT 文件
    if not doc.file_name.lower().endswith(".txt"):
        await update.message.reply_text("只支持 TXT 文件哦")
        return

    file_path = f"temp_{user_id}_{doc.file_name}"
    await doc.get_file().download_to_drive(file_path)
    await update.message.reply_text(f"文件 {doc.file_name} 已收到，开始拆分...")

    # 读取文件内容
    lines = read_txt_file(file_path)
    if lines is None:
        await update.message.reply_text("读取文件失败，可能编码不支持")
        os.remove(file_path)
        return

    # 按行拆分文件
    chunks = [lines[i:i+lines_per_file] for i in range(0, len(lines), lines_per_file)]
    chunk_files = []
    for idx, chunk in enumerate(chunks, 1):
        chunk_filename = f"chunk_{user_id}_{idx}.txt"
        with open(chunk_filename, "w", encoding="utf-8") as cf:
            cf.writelines(chunk)
        chunk_files.append(chunk_filename)

    await update.message.reply_text(f"文件已拆分成 {len(chunk_files)} 个分包，每 10 个文件发送一次")

    # 分批发送，每批 10 个文件，间隔 3 秒
    batch_size = 10
    for i in range(0, len(chunk_files), batch_size):
        batch = chunk_files[i:i+batch_size]
        for f in batch:
            with open(f, "rb") as file_to_send:
                await update.message.reply_document(file_to_send)
            await asyncio.sleep(3)  # 每个文件间隔 3 秒
        await asyncio.sleep(1)  # 批间间隔 1 秒

    # 删除临时文件
    os.remove(file_path)
    for f in chunk_files:
        os.remove(f)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setlines", set_lines))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))

    print("分包机器人已启动...")
    app.run_polling()
