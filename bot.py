import telebot
import re
from datetime import datetime
import time

TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"
bot = telebot.TeleBot(TOKEN)
data = []

@bot.message_handler(func=lambda msg: True)
def main(msg):
    txt = msg.caption if msg.photo else msg.text
    if not txt:return

    # 提取完整包名
    pack = re.search(r'包号[:：]\s*(.+)',txt)
    pack_name = pack.group(1) if pack else "未知包"

    # 只统计成功
    suc = re.findall(r'成功[:：]\s*(\d+)',txt)
    num = int(suc[0]) if suc else 0

    # 提取链接
    link = re.search(r'([a-zA-Z0-9]+\.vip)',txt)
    link_name = link.group(1) if link else "未知链接"

    data.append({"link":link_name,"pack":pack_name,"num":num,"time":datetime.now()})

    # 统计指令
    if txt.startswith("统计"):
        l = re.search(r'([a-zA-Z0-9]+\.vip)',txt)
        t = re.search(r'北京时间\s*(\d+:\d+)-(\d+:\d+)',txt)
        if not l or not t:
            bot.reply_to(msg,"格式：统计 95506.vip 北京时间 00:00-23:59")
            return
        
        lt,ts,te = l.group(1),t.groups()
        res,total = {},0
        for d in data:
            if d["link"]!=l.group(1):continue
            res[d["pack"]] = res.get(d["pack"],0)+d["num"]
            total+=d["num"]
        
        out=f"📊链接统计\n链接：{lt}\n时段：北京时间{ts}-{te}\n\n"
        for k,v in res.items():out+=f"{k}：{v}\n"
        out+=f"\n✅总成功：{total}"
        bot.reply_to(msg,out)

# Railway永不掉线
while True:
    try:
        bot.infinity_polling()
    except Exception as e:
        time.sleep(3)
