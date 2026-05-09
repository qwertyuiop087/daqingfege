from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# 直接写 Token
TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"

# 文字分包函数
def split_text(text, chunk_size=2000):
    """把文字按 chunk_size 分包"""
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("你好，我是你的分包机器人！发送文字或文件，我会帮你分包。")

# 文字消息处理
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chunks = split_text(text, 2000)
    for i, chunk in enumerate(chunks, 1):
        await update.message.reply_text(f"[分包 {i}/{len(chunks)}]\n{chunk}")

# 文件消息处理（仅示例处理为文件分割通知，不做真实拆分）
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    await update.message.reply_text(f"收到文件：{update.message.document.file_name}\n大小：{update.message.document.file_size} bytes\n临时分包模拟：分成若干部分发送（实际文件未拆分）")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))

    print("分包机器人已启动...")
    app.run_polling()
