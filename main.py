import telebot
import re
from datetime import datetime

# ========== 在这里直接粘贴你的TG机器人Token ==========
BOT_TOKEN = "8740680706:AAE-lmCkHNebFidQO0fvKIsxtJ2vSiJc9M0"
# =====================================================

bot = telebot.TeleBot(BOT_TOKEN)
order_list = []

# 识别图片文案 + 普通文字交单
@bot.message_handler(content_types=['photo', 'text'])
def handle_order(msg):
    content = msg.caption if msg.photo else msg.text
    if not content:
        return

    # 提取完整包号全名，不简写、不改成第几组
    pack_match = re.search(r'包号[:：]\s*([^\n]+)', content)
    pack_name = pack_match.group(1).strip() if pack_match else "未知包号"

    # 智能提取成功数量，完全无视失败数据
    suc = re.findall(r'成功[:：]\s*(\d+)|过\s*(\d+)|出单\s*(\d+)', content)
    all_num = re.findall(r'\d+', content)

    success = 0
    if suc:
        success = int(next(x for x in suc[0] if x))
    elif len(all_num) >= 1:
        success = int(all_num[-1])

    # 提取vip站点链接
    link_match = re.search(r'([a-zA-Z0-9]+\.vip)', content)
    link = link_match.group(1) if link_match else "未知链接"

    # 记录北京时间
    now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    order_list.append({
        "link": link,
        "pack": pack_name,
        "num": success,
        "time": now_time
    })

# 统计指令：统计 95506.vip 北京时间 08:00-23:00
@bot.message_handler(func=lambda m: m.text.startswith("统计"))
def stat_report(msg):
    text = msg.text

    link_res = re.search(r'([a-zA-Z0-9]+\.vip)', text)
    if not link_res:
        bot.reply_to(msg, "请带上要统计的VIP链接")
        return
    target_link = link_res.group(1)

    time_res = re.search(r'北京时间\s*(\d+:\d+)-(\d+:\d+)', text)
    if not time_res:
        bot.reply_to(msg, "格式：统计 95506.vip 北京时间 00:00-24:直接复制整段")
        return
    start, end = time_res.groups()

    pack_total = {}
    sum_all = 0

    for item in order_list:
        if item["link"] != target_link:
            continue
        pack = item["pack"]
        pack_total[pack] = pack_total.get(pack, 0) + item["num"]
        sum_all += item["num"]

    out = f"""📊 链接交单统计报表
链接：{target_link}
统计时段：北京时间 {start} - {end}

"""
    for pk, cnt in pack_total.items():
        out += f"{pk} ：{cnt}\n"

    out += f"\n📈 本时段累计成功总数：{sum_all}"
    bot.reply_to(msg, out)

bot.polling(none_stop=True)
