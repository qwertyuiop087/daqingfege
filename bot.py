import telebot
import re
from datetime import datetime

# 你的Token直接填这里
TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"
bot = telebot.TeleBot(TOKEN)
order_list = []

# 监听所有消息+图片配文
@bot.message_handler(content_types=['text', 'photo'])
def save_data(message):
    text = message.caption if message.photo else message.text
    if not text:
        return

    # 完整包号原名
    pack = re.search(r'包号[:：]\s*(.+?)\n', text)
    pack_name = pack.group(1).strip() if pack else "未知包号"

    # 只提取成功数量
    success = 0
    res = re.search(r'成功[:：]\s*(\d+)', text)
    if res:
        success = int(res.group(1))

    # 提取vip链接
    link = re.search(r'([a-zA-Z0-9]+\.vip)', text)
    link_name = link.group(1) if link else "未知链接"

    order_list.append({
        "link": link_name,
        "pack": pack_name,
        "num": success,
        "time": datetime.now()
    })

# 统计指令
@bot.message_handler(regexp="^统计")
def count_order(message):
    txt = message.text

    link = re.search(r'([a-zA-Z0-9]+\.vip)', txt)
    time_range = re.search(r'北京时间\s*(\d+:\d+)-(\d+:\d+)', txt)

    if not link or not time_range:
        bot.reply_to(message, "格式：统计 95506.vip 北京时间 00:00-23:59")
        return

    target_link = link.group(1)
    t_start, t_end = time_range.groups()

    pack_total = {}
    total = 0
    for item in order_list:
        if item["link"] != target_link:
            continue
        pack_total[item["pack"]] = pack_total.get(item["pack"], 0) + item["num"]
        total += item["num"]

    reply = f"""📊 链接交单统计
链接：{target_link}
统计时段：北京时间 {t_start} - {t_end}

"""
    for pk, cnt in pack_total.items():
        reply += f"{pk}：{cnt}\n"
    reply += f"\n✅ 本时段总成功：{total}"
    bot.reply_to(message, reply)

# Railway标准启动，不用while死循环！！！
bot.polling(none_stop=True, interval=0)
