import os
import time
import zipfile
import threading
import shutil
import secrets
from io import BytesIO
from PIL import Image
import telebot
import requests
from datetime import datetime, timezone, timedelta
from telebot.apihelper import ApiException

# ===================== 环境变量 =====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ===================== 业务配置 =====================
PRICE_SPLIT = 0.0005
PRICE_COMPRESS = 0.0003
TG_API_DELAY = 1.2
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_ZIP_SIZE = 18 * 1024 * 1024
MAX_IMAGES_IN_ZIP = 500
COMPRESS_QUALITY = 85
UPLOAD_FOLDER = "/tmp/uploads"
OUTPUT_FOLDER = "/tmp/outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

users = {}
cards = {}
time_cards = {}
user_state = {}
log_user = {}
log_recharge = {}

def get_user(uid):
    if uid not in users:
        users[uid] = {"balance": 0.0, "mode": "original", "images_per_group": 10, "vip_expire": 0}
    return users[uid]

def is_admin(uid):
    return uid == ADMIN_ID

def is_vip_valid(uid):
    u = get_user(uid)
    return u["vip_expire"] > int(time.time())

def get_beijing_time_str():
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

def get_now_timestamp():
    return int(time.time())

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

def safe_send_document(chat_id, file_bytes, filename, retry=3):
    for i in range(retry):
        try:
            time.sleep(TG_API_DELAY)
            bio = BytesIO(file_bytes)
            bio.name = filename
            bot.send_document(chat_id, bio)
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
    try:
        img = Image.open(BytesIO(image_bytes))
        if img.mode in ('RGBA', 'LA', 'P'):
            rgba = img.convert('RGBA')
            background = Image.new('RGB', rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[3])
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        output = BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        current_quality = quality
        while output.tell() > max_size and current_quality > 30:
            current_quality -= 10
            output = BytesIO()
            img.save(output, format='JPEG', quality=current_quality, optimize=True)
        return output.getvalue()
    except:
        return None

def download_file_from_url(url, save_path, max_size=1.5*1024*1024*1024):
    try:
        r = requests.get(url, stream=True, timeout=120)
        if r.status_code != 200:
            return False
        total = 0
        with open(save_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
                    if total > max_size:
                        f.close()
                        os.remove(save_path)
                        return False
        return True
    except Exception as e:
        print(f"下载失败: {e}")
        return False

if not BOT_TOKEN or ADMIN_ID == 0:
    print("错误：请在环境变量配置 BOT_TOKEN 和 ADMIN_ID")
    exit()

bot = telebot.TeleBot(BOT_TOKEN, skip_pending=True)

def menu(uid):
    u = get_user(uid)
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(telebot.types.InlineKeyboardButton(f"🖼️模式：{'压缩' if u['mode'] == 'compressed' else '原图'}", callback_data="mode"),
           telebot.types.InlineKeyboardButton(f"📦每组{u['images_per_group']}张", callback_data="group_size"))
    kb.add(telebot.types.InlineKeyboardButton("👤个人中心", callback_data="user"))
    kb.add(telebot.types.InlineKeyboardButton("💳卡密充值", callback_data="cdk_use"))
    kb.add(telebot.types.InlineKeyboardButton("🖼️开始分包", callback_data="start_split"))
    kb.add(telebot.types.InlineKeyboardButton("🌐大文件上传", callback_data="web_upload"))
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

def process_zip_from_bytes(zip_bytes, mode='original', group_size=10):
    extract_dir = os.path.join(UPLOAD_FOLDER, f"extract_{int(time.time())}_{secrets.token_hex(4)}")
    os.makedirs(extract_dir, exist_ok=True)
    image_files = []
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            for file_name in zf.namelist():
                if file_name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')):
                    target_path = os.path.join(extract_dir, os.path.basename(file_name))
                    with zf.open(file_name) as source, open(target_path, 'wb') as target:
                        shutil.copyfileobj(source, target)
                    if os.path.getsize(target_path) <= MAX_IMAGE_SIZE:
                        image_files.append(target_path)
                    else:
                        os.remove(target_path)
                    if len(image_files) >= MAX_IMAGES_IN_ZIP:
                        break
    except Exception as e:
        print(f"ZIP解压失败: {e}")
        return []
    if not image_files:
        shutil.rmtree(extract_dir, ignore_errors=True)
        return []
    groups = [image_files[i:i+group_size] for i in range(0, len(image_files), group_size)]
    output_zips = []
    for idx, group in enumerate(groups, 1):
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf_out:
            for img_path in group:
                if mode == 'compressed':
                    with open(img_path, 'rb') as f:
                        img_bytes = f.read()
                    compressed = compress_image(img_bytes)
                    if compressed:
                        base = os.path.splitext(os.path.basename(img_path))[0]
                        zf_out.writestr(f"{base}.jpg", compressed)
                    else:
                        zf_out.write(img_path, os.path.basename(img_path))
                else:
                    zf_out.write(img_path, os.path.basename(img_path))
        output_zips.append(zip_buffer.getvalue())
    shutil.rmtree(extract_dir, ignore_errors=True)
    return output_zips

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
        bot.send_message(cid, "📦请输入每组图片数量（纯数字，建议5-50张）")
        def set_group_size(m):
            if m.text.isdigit() and 1 <= int(m.text) <= 50:
                get_user(uid)["images_per_group"] = int(m.text)
                bot.send_message(cid, "✅每组图片数设置完成", reply_markup=menu(uid))
            else:
                safe_send_msg(cid, "❌请输入1-50之间的数字")
        bot.register_next_step_handler(call.message, set_group_size)
    elif data == "start_split":
        user_state[uid] = "awaiting_images"
        safe_send_msg(cid, "🖼️请发送图片或图片ZIP压缩包（≤18MB）\n支持格式：JPG、PNG、BMP、GIF、WEBP")
    elif data == "web_upload":
        safe_send_msg(cid, 
            "🌐 大文件上传方法：\n\n"
            "1️⃣ 将 ZIP 文件上传到以下任意网站（推荐 catbox.moe）\n"
            "   - https://catbox.moe （最大200MB，免费）\n"
            "   - https://tmpfiles.org （最大100MB）\n"
            "   - https://file.io （最大2GB，文件下载一次后自动删除）\n\n"
            "2️⃣ 上传完成后，复制文件的直链（例如 https://files.catbox.moe/xxxx.zip）\n\n"
            "3️⃣ 将直链直接发送给机器人\n\n"
            "机器人会自动下载、分包，并将结果发回给您。"
        )
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
        for uid_key, info in all_user_list[:50]:
            text += f"{uid_key} | {info['balance']:.4f}\n"
        safe_send_msg(cid, text[:4000])

@bot.message_handler(content_types=['document', 'photo'])
def handle_images(msg):
    uid = msg.from_user.id
    cid = msg.chat.id
    if user_state.get(uid) != "awaiting_images":
        return
    try:
        safe_send_msg(cid, "📥正在解析，请稍候...")
        images_data = []
        images_names = []
        if msg.content_type == 'photo':
            file_info = bot.get_file(msg.photo[-1].file_id)
            img_data = bot.download_file(file_info.file_path)
            if len(img_data) <= MAX_IMAGE_SIZE:
                images_data.append(img_data)
                images_names.append("image_1.jpg")
        elif msg.content_type == 'document':
            file_name = msg.document.file_name.lower()
            file_info = bot.get_file(msg.document.file_id)
            if file_info.file_size and file_info.file_size > MAX_ZIP_SIZE:
                safe_send_msg(cid, "❌文件超过18MB，请使用大文件上传（点击菜单“🌐大文件上传”）")
                return
            data = bot.download_file(file_info.file_path)
            if file_name.endswith('.zip'):
                output_zips = process_zip_from_bytes(data, get_user(uid)['mode'], get_user(uid)['images_per_group'])
                if not output_zips:
                    safe_send_msg(cid, "❌ZIP内未找到有效图片")
                    return
                total_images = 0
                for zbytes in output_zips:
                    with zipfile.ZipFile(BytesIO(zbytes)) as zf:
                        total_images += len([n for n in zf.namelist() if n.lower().endswith(('.jpg','.jpeg','.png','.bmp','.gif','.webp'))])
                fee = total_images * PRICE_SPLIT
                u = get_user(uid)
                if not is_vip_valid(uid):
                    if u['balance'] < fee:
                        safe_send_msg(cid, f"❌余额不足，需要 {fee:.4f} 元")
                        return
                    u['balance'] -= fee
                    add_log(uid, "Telegram图片分包ZIP", total_images, fee)
                for idx, zbytes in enumerate(output_zips, 1):
                    safe_send_document(cid, zbytes, f"分包_{idx}.zip")
                safe_send_msg(cid, f"✅分包完成，共 {len(output_zips)} 个ZIP文件")
                user_state[uid] = "idle"
                return
            elif file_name.endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')):
                if len(data) <= MAX_IMAGE_SIZE:
                    images_data.append(data)
                    images_names.append(msg.document.file_name)
            else:
                safe_send_msg(cid, "❌不支持的文件格式")
                return
        if not images_data:
            safe_send_msg(cid, "❌未找到有效图片")
            return
        total = len(images_data)
        if total > 50:
            safe_send_msg(cid, "❌图片太多，建议打包ZIP上传")
            return
        output_zips = []
        groups = [images_data[i:i+get_user(uid)['images_per_group']] for i in range(0, total, get_user(uid)['images_per_group'])]
        for idx, group in enumerate(groups, 1):
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for j, img in enumerate(group):
                    zf.writestr(f"image_{j+1}.jpg", img)
            output_zips.append(zip_buffer.getvalue())
        fee = total * PRICE_SPLIT
        u = get_user(uid)
        if not is_vip_valid(uid):
            if u['balance'] < fee:
                safe_send_msg(cid, f"❌余额不足，需要 {fee:.4f} 元")
                return
            u['balance'] -= fee
            add_log(uid, "Telegram单图分包", total, fee)
        for idx, zbytes in enumerate(output_zips, 1):
            safe_send_document(cid, zbytes, f"分包_{idx}.zip")
        safe_send_msg(cid, f"✅分包完成，共 {len(output_zips)} 个ZIP文件")
        user_state[uid] = "idle"
    except Exception as e:
        print(f"文件处理异常: {e}")
        safe_send_msg(cid, "❌处理失败，请重试")
        user_state[uid] = "idle"

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

@bot.message_handler(func=lambda m: True)
def text_msg(msg):
    uid = msg.from_user.id
    cid = msg.chat.id
    txt = msg.text.strip()

    if txt.startswith("http://") or txt.startswith("https://"):
        safe_send_msg(cid, "🔽 开始下载文件，请稍候...")
        def process_url():
            save_path = os.path.join(UPLOAD_FOLDER, f"download_{uid}_{int(time.time())}.zip")
            if not download_file_from_url(txt, save_path):
                safe_send_msg(cid, "❌ 下载失败，请检查链接是否有效")
                return
            with open(save_path, 'rb') as f:
                zip_bytes = f.read()
            os.remove(save_path)
            output_zips = process_zip_from_bytes(zip_bytes, get_user(uid)['mode'], get_user(uid)['images_per_group'])
            if not output_zips:
                safe_send_msg(cid, "❌ 处理失败，请确认是图片ZIP")
                return
            total_images = 0
            for zb in output_zips:
                with zipfile.ZipFile(BytesIO(zb)) as zf:
                    total_images += len([n for n in zf.namelist() if n.lower().endswith(('.jpg','.jpeg','.png','.bmp','.gif','.webp'))])
            fee = total_images * PRICE_SPLIT
            u = get_user(uid)
            if not is_vip_valid(uid):
                if u['balance'] < fee:
                    safe_send_msg(cid, f"❌余额不足，需要 {fee:.4f} 元")
                    return
                u['balance'] -= fee
                add_log(uid, "URL图片分包", total_images, fee)
            for idx, zb in enumerate(output_zips, 1):
                safe_send_document(cid, zb, f"分包_{idx}.zip")
            safe_send_msg(cid, f"✅处理完成，共 {len(output_zips)} 个ZIP文件")
        threading.Thread(target=process_url, daemon=True).start()
        return

    if txt == "取消":
        if uid in user_state:
            user_state[uid] = "idle"
        safe_send_msg(cid, "✅已取消当前操作")
    elif txt == "/start":
        get_user(uid)
        user_state[uid] = "idle"
        now = get_beijing_time_str()
        welcome = (
            "🤖 图片分包机器人\n"
            f"⏰ {now}\n\n"
            "📌 小文件：直接发送图片或ZIP（≤18MB）\n"
            "📌 大文件：点击菜单“🌐大文件上传”获取上传指引\n"
            "✅ 支持多用户，自动扣费"
        )
        bot.send_message(cid, welcome, reply_markup=menu(uid))

if __name__ == "__main__":
    print("🤖 机器人启动成功")
    bot.remove_webhook()
    bot.infinity_polling()
