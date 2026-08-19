import os
import time
import zipfile
import threading
import shutil
import secrets
import uuid
from io import BytesIO
from flask import Flask, request, render_template, send_file, abort
from PIL import Image
import telebot
from telebot.types import InputMediaDocument
from datetime import datetime, timezone, timedelta
from telebot.apihelper import ApiException

# ===================== 读取环境变量 =====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PORT = int(os.getenv("PORT", "8080"))

# ===================== 业务配置 =====================
PRICE_SPLIT = 0.0005          # 每张图片分包费用
PRICE_COMPRESS = 0.0003       # 每张图片压缩费用（可选）
TG_API_DELAY = 1.2
MAX_IMAGE_SIZE = 10 * 1024 * 1024   # 单张图片最大10MB
MAX_ZIP_SIZE = 500 * 1024 * 1024    # 网页上传最大500MB
MAX_IMAGES_IN_ZIP = 1000            # ZIP内图片数量上限
COMPRESS_QUALITY = 85
UPLOAD_FOLDER = "/tmp/uploads"
OUTPUT_FOLDER = "/tmp/outputs"
WEB_TOKEN_EXPIRE = 1800             # 上传链接有效期（秒），30分钟

# 确保目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ===================== 全局数据 =====================
users = {}               # 用户数据
cards = {}               # 余额卡密
time_cards = {}          # 时长卡密
user_state = {}          # 用户操作状态
log_user = {}            # 消费日志
log_recharge = {}        # 充值日志
user_web_tokens = {}     # token -> {"uid": uid, "expire": timestamp}

# ===================== 工具函数 =====================
def get_user(uid):
    if uid not in users:
        users[uid] = {
            "balance": 0.0,
            "mode": "original",
            "images_per_group": 10,
            "vip_expire": 0
        }
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

def safe_send_document(chat_id, file_path, retry=3):
    """从磁盘路径发送文档，带重试"""
    for i in range(retry):
        try:
            time.sleep(TG_API_DELAY)
            with open(file_path, 'rb') as f:
                bot.send_document(chat_id, f)
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
    """压缩图片，返回字节"""
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

# ===================== 机器人初始化 =====================
if not BOT_TOKEN or ADMIN_ID == 0:
    print("错误：请在环境变量配置 BOT_TOKEN 和 ADMIN_ID")
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

# ===================== 核心处理函数（从文件路径读取）=====================
def process_zip_file(zip_path, mode='original', group_size=10):
    """
    处理ZIP文件，按组打包成新的ZIP，返回输出ZIP文件路径列表。
    mode: 'original' 或 'compressed'
    group_size: 每组图片数量
    """
    # 解压ZIP到临时目录
    extract_dir = os.path.join(UPLOAD_FOLDER, f"extract_{int(time.time())}_{uuid.uuid4().hex[:6]}")
    os.makedirs(extract_dir, exist_ok=True)
    image_files = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for file_name in zf.namelist():
                if file_name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')):
                    # 解压单个文件
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
        print(f"解压ZIP失败: {e}")
        return []

    if not image_files:
        return []

    # 按组分组
    groups = [image_files[i:i+group_size] for i in range(0, len(image_files), group_size)]
    output_zips = []
    for idx, group in enumerate(groups, 1):
        out_zip_name = f"分包_{idx}_{uuid.uuid4().hex[:8]}.zip"
        out_zip_path = os.path.join(OUTPUT_FOLDER, out_zip_name)
        with zipfile.ZipFile(out_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf_out:
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
        output_zips.append(out_zip_path)

    # 清理解压目录
    shutil.rmtree(extract_dir, ignore_errors=True)
    return output_zips

# ===================== Flask Web应用 =====================
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_ZIP_SIZE

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    token = request.args.get('token', '')
    # 验证token
    token_info = user_web_tokens.get(token)
    if not token_info:
        abort(401, "无效的上传链接")
    if token_info['expire'] < time.time():
        del user_web_tokens[token]
        abort(401, "链接已过期，请重新获取")

    uid = token_info['uid']
    u = get_user(uid)

    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('upload.html', error='没有选择文件', token=token)
        file = request.files['file']
        if file.filename == '':
            return render_template('upload.html', error='文件名为空', token=token)

        # 检查用户余额（非VIP）
        if not is_vip_valid(uid):
            # 先粗略检查：文件大小无法确定图片数量，只能等处理后再扣费
            # 但我们可以先检查余额是否至少大于一个很小的值，防止空文件
            if u['balance'] <= 0:
                return render_template('upload.html', error='余额不足，请先充值', token=token)

        # 保存上传的文件
        upload_path = os.path.join(UPLOAD_FOLDER, f"upload_{uid}_{int(time.time())}_{uuid.uuid4().hex[:6]}.zip")
        file.save(upload_path)

        # 获取处理参数
        mode = request.form.get('mode', 'original')
        group_size = int(request.form.get('group_size', 10))
        if group_size < 1 or group_size > 100:
            group_size = 10

        # 处理文件
        output_zips = process_zip_file(upload_path, mode, group_size)
        os.remove(upload_path)

        if not output_zips:
            return render_template('upload.html', error='处理失败，请检查文件格式或内容', token=token)

        # 统计图片总数（从输出ZIP中获取，或者重新计算）
        # 更准确：从 process_zip_file 返回的图片数量，但我们现在简化：每个ZIP里的图片数量乘以ZIP数量
        # 这里我们直接传入 group_size 和 len(output_zips) 来估算总图片数
        total_images = 0
        for zpath in output_zips:
            with zipfile.ZipFile(zpath, 'r') as zf:
                total_images += len([name for name in zf.namelist() if name.lower().endswith(('.jpg','.jpeg','.png','.bmp','.gif','.webp'))])

        # 计算费用
        fee = total_images * PRICE_SPLIT

        # 检查余额并扣费
        if not is_vip_valid(uid):
            if u['balance'] < fee:
                # 余额不足，删除已生成的ZIP，返回错误
                for zpath in output_zips:
                    os.remove(zpath)
                return render_template('upload.html', error=f'余额不足，需要 {fee:.4f} 元，当前余额 {u["balance"]:.4f} 元，请先充值', token=token)
            u['balance'] -= fee
            add_log(uid, f"网页图片分包ZIP｜每组{group_size}张", total_images, fee)
        else:
            # VIP 免费
            fee = 0.0

        # 生成下载链接
        links = []
        for zpath in output_zips:
            filename = os.path.basename(zpath)
            links.append(f'<a href="/download/{filename}">{filename}</a>')

        result_html = '<br>'.join(links)

        # 通过 Telegram 通知用户
        bot_msg = f"✅ 网页上传处理完成\n图片总数：{total_images}张\n分组：{len(output_zips)}个ZIP文件\n"
        if fee > 0:
            bot_msg += f"扣费：{fee:.4f}元\n剩余余额：{u['balance']:.4f}元\n"
        else:
            bot_msg += "VIP免费处理\n"
        bot_msg += "下载链接：\n" + "\n".join([f"https://{request.host}/download/{os.path.basename(p)}" for p in output_zips])
        safe_send_msg(uid, bot_msg)

        return render_template('upload.html', message=f'处理成功，共 {len(output_zips)} 个ZIP文件，下载链接已发送到您的 Telegram，也可以点击下载：<br>{result_html}', token=token)

    return render_template('upload.html', token=token)

@app.route('/download/<filename>')
def download(filename):
    # 防止路径遍历
    if '..' in filename or filename.startswith('/'):
        abort(404)
    file_path = os.path.join(OUTPUT_FOLDER, filename)
    if not os.path.exists(file_path):
        abort(404)
    return send_file(file_path, as_attachment=True)

# ===================== 机器人回调事件 =====================
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
            if m.text.isdigit() and 1 <= int(m.text) <= 100:
                get_user(uid)["images_per_group"] = int(m.text)
                bot.send_message(cid, "✅每组图片数设置完成", reply_markup=menu(uid))
            else:
                safe_send_msg(cid, "❌请输入1-100之间的数字")
        bot.register_next_step_handler(call.message, set_group_size)

    elif data == "start_split":
        user_state[uid] = "awaiting_images"
        safe_send_msg(cid, "🖼️请发送图片或图片ZIP压缩包\n支持格式：JPG、PNG、BMP、GIF、WEBP\n单张图片不超过10MB，ZIP不超过18MB\n\n💡 大文件请点击菜单中的“🌐大文件上传”获取网页链接")

    elif data == "web_upload":
        # 生成专属 token
        token = secrets.token_urlsafe(16)
        user_web_tokens[token] = {
            "uid": uid,
            "expire": time.time() + WEB_TOKEN_EXPIRE
        }
        # 清理过期 token
        for t, info in list(user_web_tokens.items()):
            if info['expire'] < time.time():
                del user_web_tokens[t]
        # 获取域名（从环境变量或请求中，这里用 Railway 自动分配的域名）
        # 注意：需要在环境变量中设置 PUBLIC_URL，或者从 request.host 获取（但机器人无法直接获取）
        # 简单方式：让用户自己拼接，或我们在环境变量中配置
        public_url = os.getenv("PUBLIC_URL", "https://your-app.up.railway.app")
        url = f"{public_url}/upload?token={token}"
        safe_send_msg(cid, f"🌐 您的专属网页上传链接（{WEB_TOKEN_EXPIRE//60}分钟内有效）：\n{url}\n\n上传完成后结果会自动发送给您")

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

# ===================== 机器人文件接收（Telegram小文件处理）=====================
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
            file_info = bot.get_file(msg.photo[-1].file_id)
            img_data = bot.download_file(file_info.file_path)
            if len(img_data) <= MAX_IMAGE_SIZE:
                images_data.append(img_data)
                images_names.append(f"image_1.jpg")
        elif msg.content_type == 'document':
            file_name = msg.document.file_name.lower()
            file_info = bot.get_file(msg.document.file_id)
            if file_info.file_size and file_info.file_size > 18 * 1024 * 1024:
                safe_send_msg(cid, "❌文件超过18MB，请使用网页上传（点击菜单“🌐大文件上传”）")
                return
            data = bot.download_file(file_info.file_path)
            if file_name.endswith('.zip'):
                # 临时保存ZIP然后调用处理
                tmp_zip = os.path.join(UPLOAD_FOLDER, f"tg_{uid}_{int(time.time())}.zip")
                with open(tmp_zip, 'wb') as f:
                    f.write(data)
                # 处理并发送
                output_zips = process_zip_file(tmp_zip, get_user(uid)['mode'], get_user(uid)['images_per_group'])
                os.remove(tmp_zip)
                if output_zips:
                    # 扣费逻辑
                    total_images = 0
                    for zpath in output_zips:
                        with zipfile.ZipFile(zpath, 'r') as zf:
                            total_images += len([name for name in zf.namelist() if name.lower().endswith(('.jpg','.jpeg','.png','.bmp','.gif','.webp'))])
                    fee = total_images * PRICE_SPLIT
                    u = get_user(uid)
                    if not is_vip_valid(uid):
                        if u['balance'] < fee:
                            for p in output_zips:
                                os.remove(p)
                            safe_send_msg(cid, f"❌余额不足，需要 {fee:.4f} 元")
                            return
                        u['balance'] -= fee
                        add_log(uid, f"Telegram图片分包ZIP", total_images, fee)
                    for p in output_zips:
                        safe_send_document(cid, p)
                        os.remove(p)
                    safe_send_msg(cid, f"✅分包完成，共 {len(output_zips)} 个ZIP文件")
                else:
                    safe_send_msg(cid, "❌ZIP内未找到有效图片")
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
        if total > 100:
            safe_send_msg(cid, "❌图片过多，建议打包ZIP上传或使用网页上传")
            return

        # 单张图片或少量图片：直接打包成ZIP发送
        groups = [images_data[i:i+get_user(uid)['images_per_group']] for i in range(0, total, get_user(uid)['images_per_group'])]
        u = get_user(uid)
        fee = total * PRICE_SPLIT
        if not is_vip_valid(uid) and u['balance'] < fee:
            safe_send_msg(cid, f"❌余额不足，需要 {fee:.4f} 元")
            return
        for idx, group in enumerate(groups, 1):
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for j, img in enumerate(group):
                    zf.writestr(f"image_{j+1}.jpg", img)
            safe_send_document(cid, zip_buffer.getvalue(), f"分包_{idx}.zip")
        if not is_vip_valid(uid):
            u['balance'] -= fee
            add_log(uid, "Telegram单图分包", total, fee)
        safe_send_msg(cid, f"✅分包完成，共 {len(groups)} 个ZIP文件")
        user_state[uid] = "idle"

    except Exception as e:
        print(f"Telegram文件处理异常: {e}")
        safe_send_msg(cid, "❌处理失败，请重试")
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
            "📌 小文件：直接发送图片或ZIP（不超过18MB）\n"
            "📌 大文件：点击菜单中的“🌐大文件上传”获取专属网页链接\n"
            "✅ 支持多用户，每人均有独立链接和扣费"
        )
        bot.send_message(cid, welcome, reply_markup=menu(uid))

# ===================== 启动两个线程 =====================
def run_flask():
    app.run(host="0.0.0.0", port=PORT, debug=False)

def run_telegram():
    print("🤖 机器人启动成功")
    bot.infinity_polling()

if __name__ == "__main__":
    # 启动Flask线程
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # 启动Telegram轮询（主线程）
    run_telegram()
