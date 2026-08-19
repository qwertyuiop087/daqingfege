import os
import time
import zipfile
from io import BytesIO
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaDocument
from telebot.apihelper import ApiException
from flask import Flask, request

# ================= Railway环境变量 =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# 业务配置
PER_BATCH_IMG = 20        # 默认每个zip包图片张数
TG_API_DELAY = 1.2
TG_GROUP_DELAY = 2.5
IMG_SUFFIX = {".jpg", ".jpeg", ".png", ".webp"}

# 全局状态（和txt机器人结构对齐）
user_state = dict()       # 用户状态 idle / img_split
user_config = dict()      # {uid:{"per_batch":20}}

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# ================= 工具函数 =================
def get_user_cfg(uid):
    if uid not in user_config:
        user_config[uid] = {"per_batch": PER_BATCH_IMG}
    return user_config[uid]

def is_admin(uid):
    return uid == ADMIN_ID

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

def main_menu(uid):
    kb = InlineKeyboardMarkup(row_width=2)
    cfg = get_user_cfg(uid)
    kb.add(InlineKeyboardButton(f"🖼每包图片：{cfg['per_batch']}张", callback_data="set_batch"))
    kb.add(InlineKeyboardButton("ℹ帮助", callback_data="help"))
    if is_admin(uid):
        kb.add(InlineKeyboardButton("🔧管理员", callback_data="admin_panel"))
    return kb

def extract_images_from_zip_bytes(zip_bytes):
    """内存解压zip，提取全部图片二进制+文件名，不落地磁盘"""
    img_items = []
    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
        for fname in zf.namelist():
            if fname.endswith("/"):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext in IMG_SUFFIX:
                raw_data = zf.read(fname)
                img_items.append((os.path.basename(fname), raw_data))
    return img_items

def build_zip_in_memory(image_list, per_batch):
    """
    image_list: [(filename, bytes),...]
    per_batch:每包多少张图片
    return list[BytesIO] 每个元素是一个zip内存对象
    """
    output_zips = []
    total = len(image_list)
    for start in range(0, total, per_batch):
        slice_imgs = image_list[start: start + per_batch]
        mem_zip = BytesIO()
        with zipfile.ZipFile(mem_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in slice_imgs:
                zf.writestr(name, data)
        mem_zip.seek(0)
        output_zips.append(mem_zip)
    return output_zips

# ================= Webhook入口（Railway必须） =================
@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "ok"

@app.route("/")
def index():
    return "✅图片分包Bot运行｜Webhook模式"

def set_webhook():
    import requests
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    hook_url = f"https://{domain}/webhook/{BOT_TOKEN}"
    bot.remove_webhook()
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={hook_url}&drop_pending_updates=true")

# ================= 回调按钮 =================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    uid = call.from_user.id
    cid = call.message.chat.id
    data = call.data
    bot.answer_callback_query(call.id)

    if data == "set_batch":
        bot.send_message(cid, "📏请输入每个分包zip存放多少张图片（纯数字）：")
        def input_batch(m):
            if m.text.isdigit():
                num = int(m.text)
                if 1 <= num <= 200:
                    get_user_cfg(uid)["per_batch"] = num
                    safe_send_msg(cid, f"✅已设置每包 {num} 张图片", reply_markup=main_menu(uid))
                else:
                    safe_send_msg(cid, "❌范围1‑200", reply_markup=main_menu(uid))
            else:
                safe_send_msg(cid, "❌请输入纯数字", reply_markup=main_menu(uid))
        bot.register_next_step_handler(call.message, input_batch)

    elif data == "help":
        text = """🖼图片分包机器人使用说明
1.上传一个zip压缩包，包内放jpg/png/webp图片
2.机器人自动提取全部图片
3.按设定张数打包成多个batch_1.zip、batch_2.zip返回
⚠限制
• bot下载文件最大20MB
• 输出单个zip不能超过50MB(TG限制)
• 只支持zip，不支持rar/7z
发送 /start 返回主页"""
        safe_send_msg(cid, text)

    elif data == "admin_panel":
        if not is_admin(uid):
            safe_send_msg(cid, "❌管理员权限不足")

# ================= 接收上传的zip文档 =================
@bot.message_handler(content_types=["document"])
def handle_document(msg):
    uid = msg.from_user.id
    cid = msg.chat.id
    doc = msg.document
    fname = doc.file_name.lower()
    if not fname.endswith(".zip"):
        safe_send_msg(cid, "❗请上传 .zip 压缩包，内部存放图片")
        return

    safe_send_msg(cid, "📥正在下载并解析压缩包，请稍候…")
    try:
        file_info = bot.get_file(doc.file_id)
        zip_binary = bot.download_file(file_info.file_path)
    except Exception:
        safe_send_msg(cid, "❌下载失败，文件可能超过20MB限制")
        return

    img_list = extract_images_from_zip_bytes(zip_binary)
    if len(img_list) == 0:
        safe_send_msg(cid, "❌zip压缩包没有识别到jpg/png/webp图片")
        return

    cfg = get_user_cfg(uid)
    per = cfg["per_batch"]
    safe_send_msg(cid, f"✅识别图片总数：{len(img_list)}张｜每包{per}张，正在生成分包…")

    zip_mem_list = build_zip_in_memory(img_list, per)
    media_group = []
    batch_index = 1
    send_all_ok = True

    for idx, memzip in enumerate(zip_mem_list, 1):
        memzip.name = f"batch_{idx}.zip"
        media_group.append(InputMediaDocument(memzip))
        if len(media_group) >=10:
            safe_send_msg(cid, f"📤发送分包，第{batch_index}批")
            ok = safe_send_media_group(cid, media_group)
            if not ok:
                send_all_ok = False
                break
            media_group.clear()
            batch_index += 1
    if send_all_ok and len(media_group)>0:
        safe_send_msg(cid, f"📤发送分包，第{batch_index}批")
        safe_send_media_group(cid, media_group)

    if send_all_ok:
        safe_send_msg(cid, f"🎉全部完成！共生成 {len(zip_mem_list)} 个分包zip。")
    else:
        safe_send_msg(cid, "❌部分文件发送失败，请调小每包图片数量重试。")

# ================= 文本指令 /start、取消 =================
@bot.message_handler(func=lambda m: True)
def text_handler(msg):
    uid = msg.from_user.id
    cid = msg.chat.id
    text = msg.text.strip()

    if text == "/start":
        user_state[uid] = "idle"
        welcome = "🤖图片分包机器人✅\n上传包含图片的zip压缩包即可开始处理"
        bot.send_message(cid, welcome, reply_markup=main_menu(uid))
    elif text == "取消":
        user_state[uid] = "idle"
        safe_send_msg(cid, "✅操作已取消")

if __name__ == "__main__":
    if not BOT_TOKEN or ADMIN_ID ==0:
        print("⚠️请配置环境变量 BOT_TOKEN、ADMIN_ID")
    else:
        set_webhook()
        print("🤖图片分包Bot已启动 Webhook模式(Railway)")
