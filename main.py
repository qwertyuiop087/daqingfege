import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"

# 存储用户的分包行数设置（内存）
user_settings = {}

# /start 命令
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "你好，我是分包机器人！\n"
        "步骤：\n"
        "1️⃣ /setlines <行数> 设置每个分包行数\n"
        "2️⃣ 发送 TXT 文件，我会按行拆分并发送\n"
        "每 10 个文件一批，每个文件间隔 3 秒"
    )

# /setlines 命令
async def set_lines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("用法：/setlines <行数>，例如 /setlines 50")
        return
    user_settings[update.effective_user.id] = int(context.args[0])
    await update.message.reply_text(f"已设置分包行数为 {context.args[0]} 行")

# 尝试多种编码读取 TXT 文件
def read_txt_file(filepath):
    for enc in ["utf-8", "gbk", "ansi", "utf-16"]:
        try:
            with open(filepath, "r", encoding=enc, errors="ignore") as f:
                lines = f.readlines()
            if lines:
                return lines
        except Exception:
            continue
    return None

# 分批发送文件，每 10 个文件一批
async def send_chunks(update: Update, chunk_files):
    batch_size = 10
    total_files = len(chunk_files)
    sent_files = 0

    for i in range(0, total_files, batch_size):
        batch = chunk_files[i:i+batch_size]
        # 发送这一批的所有文件
        for f in batch:
            with open(f, "rb") as file_to_send:
                await update.message.reply_document(file_to_send)
            sent_files += 1
            await asyncio.sleep(3)  # 每个文件间隔 3 秒
        # 批发送完成后发送进度提示
        await update.message.reply_text(f"已发送 {sent_files}/{total_files} 个分包")
        await asyncio.sleep(1)  # 批间隔 1 秒

# 文件处理
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lines_per_file = user_settings.get(user_id, 50)  # 默认 50 行

    doc = update.message.document
    if not doc.file_name.lower().endswith(".txt"):
        await update.message.reply_text("只支持 TXT 文件")
        return

    temp_path = f"temp_{user_id}_{doc.file_name}"
    try:
        file_obj = await doc.get_file()
        await file_obj.download_to_drive(temp_path)
    except Exception as e:
        await update.message.reply_text(f"文件下载失败: {e}")
        return

    await update.message.reply_text(f"文件 {doc.file_name} 已下载，开始拆分...")

    lines = read_txt_file(temp_path)
    if not lines:
        await update.message.reply_text("读取文件失败，可能编码不支持")
        os.remove(temp_path)
        return

    # 拆分文件
    chunk_files = []
    for idx, i in enumerate(range(0, len(lines), lines_per_file), 1):
        chunk_filename = f"chunk_{user_id}_{idx}.txt"
        with open(chunk_filename, "w", encoding="utf-8") as cf:
            cf.writelines(lines[i:i+lines_per_file])
        chunk_files.append(chunk_filename)

    await update.message.reply_text(f"文件拆分完成，共 {len(chunk_files)} 个分包，开始发送...")

    # 分批发送
    await send_chunks(update, chunk_files)

    # 删除临时文件
    os.remove(temp_path)
    for f in chunk_files:
        os.remove(f)

    await update.message.reply_text("所有文件已发送完毕 ✅")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setlines", set_lines))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    print("分包机器人已启动...")
    app.run_polling()
