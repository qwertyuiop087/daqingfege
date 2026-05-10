import telebot
import re
import time

TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"
bot = telebot.TeleBot(TOKEN)
data = []

@bot.message_handler(func=lambda msg: True)
def handle(msg):
    txt = msg.caption or msg.text
    if not txt:return

    pack = re.search(r'包号[:：]\s*(.+)', txt)
    pack_name = pack.group(1) if pack else "未知包"

    suc = re.findall(r'成功[:：]\s*(\d+)', txt)
    num = int(suc[0]) if suc else 0

    link = re.search(r'(\w+\.vip)', txt)
    link_name = link.group(1) if link else "未知链接"

    data.append({"link":link_name,"pack":pack_name,"num":num})

    if txt.startswith("统计"):
        l = re.search(r'(\w+\.vip)', txt)
        t = re.search(r'北京时间\s*(\d+:\d+)-(\d+:\d+)', txt)
        if not l or not t:
            bot.reply_to(msg,"格式：统计 95506.vip 北京时间 00:00-23:59")
            return
        lt,ts,te = l.group(1),t.groups()
        res,total = {},0
        for i in data:
            if i["link"]!=lt:continue
            res[i["pack"]] = res.get(i["pack"],0)+i["num"]
            total+=i["num"]
        out=f"📊链接交单统计\n链接：{lt}\n时段：北京时间{ts}-{te}\n\n"
        for k,v in res.items():out+=f"{k}：{v}\n"
        out+=f"\n✅本时段总成功：{total}"
        bot.reply_to(msg,out)

while True:
    try:
        bot.infinity_polling()
    except:
        time.sleep(1)
