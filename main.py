import telebot
import re
from datetime import datetime
import time

# 你的机器人Token直接写这里
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"

bot = telebot.TeleBot(BOT_TOKEN)
order_list = []

# 兼容图片+文字所有交单
@bot.message_handler(content_types=['photo', 'text'])
def auto_save(message):
    text = message.caption if message.photo else message.text
    if not text:
        return

    # 完整包号原名
    pack = re.search(r'包号[:：]\s*([^\n]+)', text)
    pack_name = pack.group(1).strip() if pack else "未知包"

    # 只提取成功，无视失败
    suc_num = re.findall(r'成功[:：]\s*(\d+)', text)
    nums = re.findall(r'\d+', text)

    success = 0
    if suc_num:
        success = int(suc_num[0])
    elif nums:
        success = int(nums[0])

    # 提取vip链接
    link = re.search(r'([a-zA-Z0-9]+\.vip)', text)
    link_name = link.group(1) if link else "无链接"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    order_list.append({"link":link_name,"pack":pack_name,"num":success,"time":now})

# 统计指令
@bot.message_handler(func=lambda msg: True)
def stat(msg):
    if not msg.text.startswith("统计"):
        return

    text = msg.text
    link_res = re.search(r'([a-zA-Z0-9]+\.vip)', text)
    if not link_res:
        bot.reply_to(msg,"请格式：统计 95506.vip 北京时间 00:00-23:59")
        return

    time_res = re.search(r'北京时间\s*(\d+:\d+)-(\d+:\d+)', text)
    if not time_res:
        bot.reply_to(msg,"请带上时间段：北京时间 xx:xx-xx:xx")
        return

    l = link_res.group(1)
    s,e = time_res.groups()

    pack_sum = {}
    total = 0
    for d in order_list:
        if d["link"] != l:
            continue
        pack_sum[d["pack"]] = pack_sum.get(d["pack"],0) + d["num"]
        total += d["num"]

    reply = f"""📊 交单统计
链接：{l}
时段：北京时间 {s} - {e}

"""
    for pk, cnt in pack_sum.items():
        reply += f"{pk}：{cnt}\n"
    reply += f"\n总计成功：{total}"
    bot.reply_to(msg, reply)

# Railway防掉线永久循环
while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(e)
        time.sleep(5)
