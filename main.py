import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"  # 直接写Token

# 临时存储用户设置（内存，不保存）
user_settings = {}

# /start 命令
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "你好，我是分包机器人！\n"
        "使用步骤：\n"
        "1️⃣ /setlines <行数> 设置分包行数\n"
        "2️⃣ 发送文件，我会按行数分割并发送"
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

# 文件处理函数
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lines_per_file = user_settings.get(user_id, 50)  # 默认 50 行

    doc = update.message.document
    file_path = f"temp_{user_id}_{doc.file_name}"
    await doc.get_file().download_to_drive(file_path)

    # 按行拆分文件
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    # 生成小文件
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
        await asyncio.sleep(1)  # 批间间隔 1 秒，安全点

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
