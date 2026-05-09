import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
import os

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SEND_DELAY = 3.0
user_line_setting = {}
DEFAULT_LINE = 80

async def set_line(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        num = int(context.args[0])
        if 1 <= num <= 500:
            user_line_setting[user_id] = num
            await update.message.reply_text(f"✅ 已设置：每包 {num} 行")
        else:
            await update.message.reply_text("请输入1~500之间的数字")
    except:
        await update.message.reply_text("格式错误！用法：/set 50")

async def get_line(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = user_line_setting.get(user_id, DEFAULT_LINE)
    await update.message.reply_text(f"📌 当前每包行数：{now}")

async def txt_split_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    doc = msg.document
    user_id = update.effective_user.id
    line_per = user_line_setting.get(user_id, DEFAULT_LINE)

    if not doc.file_name.lower().endswith(".txt"):
        await msg.reply_text("请发送TXT文本文件")
        return

    file = await doc.get_file()
    content = await file.download_as_string()
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    if not lines:
        await msg.reply_text("文件为空或无有效内容")
        return

    total = len(lines)
    await msg.reply_text(f"📄 解析完成\n总行数：{total}\n每包：{line_per}行\n开始分包")

    packs = []
    for i in range(0, total, line_per):
        packs.append(lines[i:i+line_per])

    for idx, pack in enumerate(packs, 1):
        text = f"【分包 {idx}/{len(packs)}】\n" + "\n".join(pack)
        await msg.reply_text(text)
        await asyncio.sleep(SEND_DELAY)

    await msg.reply_text(f"✅ 分包全部完成！共 {len(packs)} 包")

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("set", set_line))
    app.add_handler(CommandHandler("now", get_line))
    app.add_handler(MessageHandler(filters.Document.ALL, txt_split_handler))
    
    # 新版正确写法 run_polling
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
