from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# 直接把你的 Bot Token 写在这里
TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("你好，我是你的机器人！")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await update.message.reply_text(f"你说的是：{text}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    # /start 命令
    app.add_handler(CommandHandler("start", start))

    # 文本消息自动回复
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    print("Bot 已启动...")
    app.run_polling()
