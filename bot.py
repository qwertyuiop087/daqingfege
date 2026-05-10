import telebot
import re
from datetime import datetime
import time

# 你的Token直接填这里
TOKEN = "这里粘贴你的机器人Token"

bot = telebot.TeleBot(TOKEN, parse_mode=None)
data = []

# 监听所有图片+文字
@bot.message_handler(func=lambda msg: True)
def all_msg(msg):
    txt = msg.caption if msg.photo else msg.text
    if not txt:
        return

    # 提取完整包名
    pack = re.findall(r'包号[:：]\s*(.+?)\n', txt)
    pack_name = pack[0] if pack else "未知包"

    # 只拿成功数字
    suc = re.findall(r'成功[:：]\s*(\d+)', txt)
    num = int(suc[0]) if suc else 0

    # 提取vip链接
    link = re.findall(r'([0-9a-zA-Z]+\.vip)', txt)
    link_name = link[0] if link else "未知链接"

    data.append({
        "link": link_name,
        "pack": pack_name,
        "count": num,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    # 统计指令
    if txt.startswith("统计"):
        l = re.search(r'([0-9a-zA-Z]+\.vip)', txt)
        t = re.search(r'北京时间\s*(\d+:\d+)-(\d+:\d+)', txt)
        if not l or not t:
            bot.reply_to(msg, "格式：统计 95506.vip 北京时间 00:00-23:59")
            return

        link_target = l.group(1)
        ts, te = t.groups()

        res = {}
        total = 0
        for item in data:
            if item["link"] != link_target:
                continue
            res[item["pack"]] = res.get(item["pack"],0) + item["count"]
            total += item["count"]

        out = f"📊 链接统计\n链接：{link_target}\n时段：北京时间 {ts}-{te}\n\n"
        for k,v in res.items():
            out += f"{k}：{v}\n"
        out += f"\n✅ 总成功：{total}"
        bot.reply_to(msg, out)

# Railway无限防崩溃
while True:
    try:
        bot.infinity_polling()
    except:
        time.sleep(3)
