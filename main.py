import os
import random
import time
import zipfile
import re
import threading
from io import BytesIO
from PIL import Image
import telebot
from telebot.types import InputMediaDocument, InputMediaPhoto
from datetime import datetime, timezone, timedelta
from telebot.apihelper import ApiException

# ===================== 读取 Railway 环境变量 =====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# 业务价格配置
PRICE_SPLIT = 0.0005      # 图片分包单价（每张）
PRICE_COMPRESS = 0.0003   # 图片压缩单价（每张）— 可自行调整
BATCH_SIZE = 10           # 每批发送图片数
PAGE_NUM = 20
TG_API_DELAY = 1.2
TG_GROUP_DELAY = 2.5
OP_TIMEOUT = 180          # 操作超时3分钟
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 单张图片最大10MB
COMPRESS_QUALITY = 85     # 压缩质量

# 全局数据
users = {}
cards = {}
time_cards = {}
user_state = {}
user_images = {}          # 存储用户上传的图片数据
user_image_groups = {}    # 存储图片分组
log_user = {}
log_recharge = {}

# ===================== 工具函数 =====================
def get_user(uid):
    if uid not in users:
        users[uid] = {
            "balance": 0.0,
            "mode": "original",  # original=原图, compressed=压缩
            "images_per_group": 10,  # 每组图片数
            "vip_expire": 0
        }
    return users[uid]

def is_admin(uid):
    return uid == ADMIN_ID

def is_vip_valid(uid):
    u = get_user(uid)
    now = int(time.time())
    return u["vip_expire"] > now

def get_vip_expire_time_str(uid):
    u = get_user(uid)
    now = int(time.time())
    if u["vip_expire"] <= now:
        return "已过期/未开通"
    return datetime.fromtimestamp(u["vip_expire"], tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

def get_vip_days_remaining(uid):
    u = get_user(uid)
    now = int(time.time())
    if u["vip_expire"] <= now:
        return 0
    return (u["vip_expire"] - now) // 86400

def add_log(uid, txt, num, cost):
    t = get_beijing_time_str()
    if uid not in log_user:
        log_user[uid] = []
    log_user[uid].insert(0, f"[{t}]｜{txt}｜{num}张｜扣费{cost:.4f}｜剩余{get_user(uid)['balance']:.4f}")

def add_rc(uid, money):
    t = get_beijing_time_str()
    if uid not in log_recharge:
        log_recharge[uid] = []
    log_recharge[uid].insert(0, f"[{t}]｜充值+{money:.4f}｜剩余{get_user(uid)['balance']:.4f}")

def get_beijing_time_str():
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

def get_now_timestamp():
    return int(time.time())

def safe_send_msg(chat_id, text, retry=3):
    for i in range(retry):
        try:
            time.sleep(TG_API_DELAY)
            bot.send_message(chat_id, text)
            return True
        except ApiException as e:
            if "429" in str(e):
                time.sleep(3)
                continue
            return False
        except Exception:
            continue
    return False

def safe_send_media_group(chat_id, media_list, retry=3):
    for i in range(retry):
        try:
            time.sleep(TG_GROUP_DELAY)
            bot.send_media_group(chat_id, media_list)
            return True
        except ApiException as e:
            if "429" in str(e):
                time.sleep(4)
                continue
            return False
        except Exception:
            continue
    return False

def compress_image(image_bytes, quality=COMPRESS_QUALITY, max_size=MAX_IMAGE_SIZE):
    """压缩图片"""
    try:
        img = Image.open(BytesIO(image_bytes))
        # 转换为RGB（处理PNG透明背景）
        if img.mode in ('RGBA', 'LA', 'P'):
            rgba = img.convert('RGBA')
            background = Image.new('RGB', rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[3])
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        output = BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)

        # 如果还是太大，继续降低质量
        current_quality = quality
        while output.tell() > max_size and current_quality > 30:
            current_quality -= 10
            output = BytesIO()
            img.save(output, format='JPEG', quality=current_quality, optimize=True)

        return output.getvalue()
    except Exception as e:
        return None

def process_image_batch(image_data_list, mode='original'):
    """处理一批图片"""
    processed = []
    for img_data in image_data_list:
        if mode == 'compressed':
            compressed = compress_image(img_data)
            if compressed:
                processed.append(compressed)
            else:
                processed.append(img_data)  # 压缩失败用原图
        else:
            processed.append(img_data)
    return processed

# ===================== 机器人初始化 =====================
if not BOT_TOKEN or ADMIN_ID == 0:
    print("错误：请在 Railway 环境变量配置 BOT_TOKEN 和 ADMIN_ID")
    exit()

bot = telebot.TeleBot(BOT_TOKEN, skip_pending=True)

# ===================== 菜单UI =====================
def menu(uid):
    u = get_user(uid)
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(telebot.types.InlineKeyboardButton(f"🖼️模式：{'压缩' if u['mode'] == 'compressed' else '原图'}", callback_data="mode"),
           telebot.types.InlineKeyboardButton(f"📦每组{u['images_per_group']}张", callback_data="group_size"))
    kb.add(telebot.types.InlineKeyboardButton("👤个人中心", callback_data="user"))
    kb.add(telebot.types.InlineKeyboardButton("💳卡密充值", callback_data="cdk_use"))
    kb.add(telebot.types.InlineKeyboardButton("🖼️开始分包", callback_data="start_split"))
    if is_admin(uid):
        kb.add(telebot.types.InlineKeyboardButton("🔧管理后台", callback_data="admin"))
    return kb

def user_menu(uid):
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(telebot.types.InlineKeyboardButton("💰我的余额", callback_data="bal"))
    kb.add(telebot.types.InlineKeyboardButton("💳充值记录", callback_data="my_rc_1"))
    kb.add(telebot.types.InlineKeyboardButton("📜消费明细", callback_data="my_use_1"))
    kb.add(telebot.types.InlineKeyboardButton("🔙返回主页", callback_data="back"))
    return kb

def admin_kb():
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(telebot.types.InlineKeyboardButton("➕单人加余额", callback_data="addbal"),
           telebot.types.InlineKeyboardButton("➖单人扣余额", callback_data="subbal"))
    kb.add(telebot.types.InlineKeyboardButton("🎟️余额卡密", callback_data="card"),
           telebot.types.InlineKeyboardButton("⏰时间卡密", callback_data="time_card"))
    kb.add(telebot.types.InlineKeyboardButton("📊用户余额总表", callback_data="ulist"))
    kb.add(telebot.types.InlineKeyboardButton("📢全站广播", callback_data="broad"))
    kb.add(telebot.types.InlineKeyboardButton("🔙返回", callback_data="back"))
    return kb

# ===================== 图片分包核心逻辑 =====================
def split_images(uid, cid, images_data, images_names):
    """图片分包主逻辑"""
    u = get_user(uid)
    total_images = len(images_data)
    fee = total_images * PRICE_SPLIT

    # 检查余额
    if not is_vip_valid(uid):
        if u['balance'] < fee:
            safe_send_msg(cid, f"❌余额不足｜需要{fee:.4f}元｜当前{u['balance']:.4f}元")
            return
        safe_send_msg(cid, f"✅余额校验通过，图片总数：{total_images}张，开始分包...")
    else:
        safe_send_msg(cid, f"✅VIP用户免余额校验，图片总数：{total_images}张，开始分包...")

    # 处理图片（压缩或原图）
    processed_images = process_image_batch(images_data, u['mode'])

    # 分组
    groups = [processed_images[i:i+u['images_per_group']] for i in range(0, len(processed_images), u['images_per_group'])]
    name_groups = [images_names[i:i+u['images_per_group']] for i in range(0, len(images_names), u['images_per_group'])]

    # 发送图片组
    send_success = True
    for idx, (img_group, name_group) in enumerate(zip(groups, name_groups), 1):
        media = []
        for img_data, img_name in zip(img_group, name_group):
            bio = BytesIO(img_data)
            bio.name = img_name if img_name else f"image_{idx}.jpg"
            media.append(InputMediaDocument(bio))

        safe_send_msg(cid, f"📤正在发送第{idx}组｜图片 {len(img_group)}张")
        if not safe_send_media_group(cid, media):
            send_success = False
            break

    # 扣费
    if send_success:
        if not is_vip_valid(uid):
            u['balance'] -= fee
            add_log(uid, f"图片分包｜每组{u['images_per_group']}张", total_images, fee)

        if is_vip_valid(uid):
            safe_send_msg(cid, f"✅图片分包完成（VIP免费）｜共{len(groups)}组")
        else:
            safe_send_msg(cid, f"✅图片分包完成｜扣费{fee:.4f}元｜剩余{u['balance']:.4f}元｜共{len(groups)}组")
    else:
        safe_send_msg(cid, "❌发送失败，本次不扣费，请重试！")

    # 清理
    if uid in user_images:
        del user_images[uid]
    if uid in user_image_groups:
        del user_image_groups[uid]

def process_zip_images(zip_bytes):
    """从ZIP中提取图片"""
    images = []
    names = []
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            for file_name in zf.namelist():
                if file_name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')):
                    with zf.open(file_name) as f:
                        img_data = f.read()
                        if len(img_data) <= MAX_IMAGE_SIZE:
                            images.append(img_data)
                            names.append(os.path.basename(file_name))
    except Exception:
        pass
    return images, names

# ===================== 回调事件 =====================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    uid = call.from_user.id
    cid = call.message.chat.id
    data = call.data
    bot.answer_callback_query(call.id)

    if data == "mode":
        u = get_user(uid)
        u["mode"] = "compressed" if u["mode"] == "original" else "original"
        bot.edit_message_text("✅图片模式已切换", cid, call.message.message_id, reply_markup=menu(uid))

    elif data == "group_size":
        bot.send_message(cid, "📦请输入每组图片数量（纯数字，建议5-20张）")
        def set_group_size(m):
            if m.text.isdigit() and 1 <= int(m.text) <= 50:
                get_user(uid)["images_per_group"] = int(m.text)
                bot.send_message(cid, "✅每组图片数设置完成", reply_markup=menu(uid))
            else:
                safe_send_msg(cid, "❌请输入1-50之间的数字")
        bot.register_next_step_handler(call.message, set_group_size)

    elif data == "start_split":
        user_state[uid] = "awaiting_images"
        safe_send_msg(cid, "🖼️请发送图片或图片ZIP压缩包\n支持格式：JPG、PNG、BMP、GIF、WEBP\n单张图片不超过10MB")

    elif data == "user":
        bot.edit_message_text("👤个人中心", cid, call.message.message_id, reply_markup=user_menu(uid))

    elif data == "bal":
        u = get_user(uid)
        vip_status = "✅生效中" if is_vip_valid(uid) else "❌已过期/未开通"
        expire_time = get_vip_expire_time_str(uid)
        remain_days = get_vip_days_remaining(uid)
        safe_send_msg(cid, f"💰当前余额：{u['balance']:.4f}\n⏰VIP状态：{vip_status}\n📅到期时间：{expire_time}\n剩余时长：{remain_days}天")

    elif data == "back":
        bot.edit_message_text("🏠返回主页", cid, call.message.message_id, reply_markup=menu(uid))

    elif data == "cdk_use":
        safe_send_msg(cid, "💳请发送卡密进行兑换")
        bot.register_next_step_handler(call.message, use_cdk)

    elif data == "admin":
        if not is_admin(uid):
            safe_send_msg(cid, "❌无管理员权限")
            return
        bot.edit_message_text("🔧管理后台", cid, call.message.message_id, reply_markup=admin_kb())

    elif data == "addbal":
        safe_send_msg(cid, "➕格式：用户ID 金额")
        bot.register_next_step_handler(call.message, add_single_balance)

    elif data == "subbal":
        safe_send_msg(cid, "➖格式：用户ID 金额")
        bot.register_next_step_handler(call.message, sub_single_balance)

    elif data == "card":
        safe_send_msg(cid, "🎟️格式：卡密 面额（例：ABC123 10）")
        bot.register_next_step_handler(call.message, create_balance_card)

    elif data == "time_card":
        safe_send_msg(cid, "⏰格式：卡密 天数（例：XYZ789 7）")
        bot.register_next_step_handler(call.message, create_time_card)

    elif data == "broad":
        if not is_admin(uid):
            return
        safe_send_msg(cid, "📢请输入要全站广播的内容：")
        bot.register_next_step_handler(call.message, do_broadcast)

    elif data == "ulist":
        all_user_list = list(users.items())
        if not all_user_list:
            safe_send_msg(cid, "📊暂无用户数据")
            return
        text = "📊用户余额总表\n用户ID | 余额\n"
        for uid_key, info in all_user_list[:50]:  # 限制显示前50个
            text += f"{uid_key} | {info['balance']:.4f}\n"
        safe_send_msg(cid, text[:4000])

# ===================== 文件接收处理 =====================
@bot.message_handler(content_types=['document', 'photo'])
def handle_images(msg):
    uid = msg.from_user.id
    cid = msg.chat.id

    if user_state.get(uid) != "awaiting_images":
        return

    try:
        safe_send_msg(cid, "📥正在解析图片，请稍候...")
        images_data = []
        images_names = []

        if msg.content_type == 'photo':
            # 单张图片
            file_info = bot.get_file(msg.photo[-1].file_id)
            img_data = bot.download_file(file_info.file_path)
            if len(img_data) <= MAX_IMAGE_SIZE:
                images_data.append(img_data)
                images_names.append(f"image_1.jpg")
        elif msg.content_type == 'document':
            file_name = msg.document.file_name.lower()
            file_info = bot.get_file(msg.document.file_id)
            data = bot.download_file(file_info.file_path)

            if file_name.endswith('.zip'):
                # ZIP压缩包
                images_data, images_names = process_zip_images(data)
            elif file_name.endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')):
                # 单张图片
                if len(data) <= MAX_IMAGE_SIZE:
                    images_data.append(data)
                    images_names.append(msg.document.file_name)
            else:
                safe_send_msg(cid, "❌不支持的文件格式，请发送图片或图片ZIP")
                return

        if not images_data:
            safe_send_msg(cid, "❌未找到有效图片")
            return

        total_images = len(images_data)
        if total_images > 500:
            safe_send_msg(cid, "❌图片数量过多（最多500张），请分批处理")
            return

        safe_send_msg(cid, f"✅已接收{total_images}张图片，开始处理...")
        # 直接开始分包
        split_images(uid, cid, images_data, images_names)
        user_state[uid] = "idle"

    except Exception as e:
        safe_send_msg(cid, "❌图片解析失败，请重试")
        user_state[uid] = "idle"

# ===================== 卡密和管理员功能 =====================
def use_cdk(m):
    uid = m.from_user.id
    cdk = m.text.strip()
    cid = m.chat.id
    if cdk in cards:
        val = cards.pop(cdk)
        get_user(uid)["balance"] += val
        add_rc(uid, val)
        safe_send_msg(cid, f"✅余额卡密兑换成功\n到账金额：{val}")
    elif cdk in time_cards:
        days = time_cards.pop(cdk)
        now = get_now_timestamp()
        expire = now + days * 86400
        get_user(uid)["vip_expire"] = expire
        safe_send_msg(cid, f"✅时长VIP兑换成功\n有效时长：{days}天\n到期时间：{get_vip_expire_time_str(uid)}")
    else:
        safe_send_msg(cid, "❌卡密无效或已使用")

def create_balance_card(m):
    try:
        parts = m.text.strip().split()
        cdk = parts[0]
        val = float(parts[1])
        cards[cdk] = val
        safe_send_msg(m.chat.id, f"✅余额卡密创建成功\n卡密：{cdk}\n面额：{val}")
    except:
        safe_send_msg(m.chat.id, "❌格式错误！示例：ABC123 10")

def create_time_card(m):
    try:
        parts = m.text.strip().split()
        cdk = parts[0]
        days = int(parts[1])
        time_cards[cdk] = days
        safe_send_msg(m.chat.id, f"✅时长卡密创建成功\n卡密：{cdk}\n有效天数：{days}天")
    except:
        safe_send_msg(m.chat.id, "❌格式错误！示例：XYZ789 7")

def add_single_balance(m):
    try:
        uid, money = m.text.strip().split()
        uid = int(uid)
        money = float(money)
        get_user(uid)["balance"] += money
        add_rc(uid, money)
        safe_send_msg(m.chat.id, f"✅成功给用户{uid}充值 {money}")
    except:
        safe_send_msg(m.chat.id, "❌格式错误，请按：用户ID 金额 发送")

def sub_single_balance(m):
    try:
        uid, money = m.text.strip().split()
        uid = int(uid)
        money = float(money)
        u = get_user(uid)
        if u["balance"] >= money:
            u["balance"] -= money
            safe_send_msg(m.chat.id, f"✅成功扣除用户{uid}余额 {money}")
        else:
            safe_send_msg(m.chat.id, "❌用户余额不足")
    except:
        safe_send_msg(m.chat.id, "❌格式错误，请按：用户ID 金额 发送")

def do_broadcast(m):
    uid = m.from_user.id
    cid = m.chat.id
    if not is_admin(uid):
        return
    content = m.text.strip()
    if not content:
        safe_send_msg(cid, "❌广播内容不能为空")
        return
    threading.Thread(target=broadcast_task, args=(cid, content), daemon=True).start()

def broadcast_task(admin_cid, content):
    user_list = list(users.keys())
    total = len(user_list)
    success = 0
    fail = 0
    try:
        progress_msg = bot.send_message(admin_cid, f"📢 开始全站广播\n总用户数：{total}")
    except:
        return
    for idx, user_id in enumerate(user_list, 1):
        try:
            time.sleep(0.15)
            bot.send_message(user_id, f"📢【全站公告】\n{content}")
            success += 1
        except:
            fail += 1
    try:
        bot.edit_message_text(f"✅ 广播完成\n成功：{success} | 失败：{fail}", admin_cid, progress_msg.message_id)
    except:
        pass

# ===================== 文本消息处理 =====================
@bot.message_handler(func=lambda m: True)
def text_msg(msg):
    uid = msg.from_user.id
    cid = msg.chat.id
    txt = msg.text.strip()

    if txt == "取消":
        if uid in user_images:
            del user_images[uid]
        if uid in user_state:
            user_state[uid] = "idle"
        safe_send_msg(cid, "✅已取消当前操作")

    elif txt == "/start":
        get_user(uid)
        user_state[uid] = "idle"
        now = get_beijing_time_str()
        welcome_text = (
            "🤖 图片分包机器人 | 正常运行中✅\n"
            f"⏰ 北京时间：{now}\n\n"
            "功能说明：\n"
            "🖼️ 图片分包：将多张图片按组发送\n"
            "🗜️ 图片压缩：自动压缩大图片\n"
            "📦 ZIP支持：可直接上传图片ZIP包"
        )
        bot.send_message(cid, welcome_text, reply_markup=menu(uid))

if __name__ == "__main__":
    print("🤖 图片分包机器人启动成功")
    bot.infinity_polling()
