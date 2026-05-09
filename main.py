from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"

async def test_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("收到消息！")
    if update.message.document:
        print("文件名:", update.message.document.file_name)
        await update.message.reply_text(f"收到文件: {update.message.document.file_name}")
    else:
        await update.message.reply_text("这不是文件")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, test_file))
    print("机器人已启动...")
    app.run_polling()
