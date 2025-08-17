import sqlite3
import json
import base64
import time
import subprocess
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import TelegramError, TimedOut
import logging
import asyncio
from flask import Flask, request, jsonify, send_file
import os

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN", "")
STORAGE_CHAT_IDS = [os.getenv("STORAGE_CHAT_ID", "")]
OWNER_ID = os.getenv("OWNER_ID", "")
WEB_APP_URL = os.getenv("WEB_APP_URL", "http://localhost:5000")
UPDATE_INTERVAL = 11 * 24 * 60 * 60
LAST_UPDATE_CHECK = time.time()

app_flask = Flask(__name__)

@app_flask.route('/')
def serve_terminal():
    return send_file('terminal.html')

@app_flask.route('/run_command', methods=['POST'])
def run_command_api():
    data = request.get_json()
    command = data.get('command')
    if not command:
        return jsonify({"error": "دستور خالی است!"})
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
        return jsonify({"output": result.stdout})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": e.stderr})

def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY, link TEXT, type TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS wallets (id INTEGER PRIMARY KEY, wallet TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ads (id INTEGER PRIMARY KEY, ad_text TEXT)''')
    conn.commit()
    conn.close()

async def store_in_channel(context: ContextTypes.DEFAULT_TYPE, data: dict, chat_id: str):
    for attempt in range(5):
        try:
            message = await context.bot.send_message(
                chat_id=chat_id,
                text=json.dumps(data, ensure_ascii=False),
                disable_notification=True
            )
            return message.message_id
        except TimedOut:
            logger.warning(f"تلاش {attempt + 1} برای ذخیره داده در {chat_id} ناموفق بود...")
            await asyncio.sleep(2)
        except TelegramError as error:
            logger.error(f"خطا در ذخیره داده در {chat_id}: {error}")
            return None
    return None

async def store_in_all_channels(context: ContextTypes.DEFAULT_TYPE, data: dict):
    message_ids = []
    for chat_id in STORAGE_CHAT_IDS:
        msg_id = await store_in_channel(context, data, chat_id)
        if msg_id:
            message_ids.append((chat_id, msg_id))
    return message_ids

async def store_source_code(context: ContextTypes.DEFAULT_TYPE, source_chunks: list, file_name: str):
    message_ids = []
    unique_id = str(time.time())
    for i, chunk in enumerate(source_chunks):
        data = {"action": f"store_file_{file_name}", "chunk_id": f"{unique_id}_{i}", "chunk": chunk}
        chunk_message_ids = await store_in_all_channels(context, data)
        message_ids.extend(chunk_message_ids)
    return message_ids

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id == OWNER_ID:
        await update.message.reply_text(
            "به ربات ترمینال لینوکسی خوش آمدید! دستورات مدیریت:\n"
            "/addlink <لینک> <نوع> - افزودن لینک رفرال\n"
            "/addwallet <آدرس_ولت> - افزودن ولت\n"
            "/addad <متن_تبلیغ> - افزودن تبلیغ\n"
            "/addchannel <آیدی_کانال> - افزودن کانال ذخیره‌سازی\n"
            "/removechannel <آیدی_کانال> - حذف کانال ذخیره‌سازی\n"
            "/listitems - نمایش لینک‌ها، ولت‌ها و تبلیغات\n"
            "/terminal - دسترسی به ترمینال لینوکسی"
        )
    else:
        await update.message.reply_text(
            "به ربات ترمینال لینوکسی خوش آمدید! از /terminal برای ترمینال استفاده کنید."
        )

async def add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != OWNER_ID:
        await update.message.reply_text("فقط مالک ربات می‌تواند لینک اضافه کند!")
        return
    if not context.args:
        await update.message.reply_text("لطفاً لینک و نوع آن را وارد کنید، مثلاً: /addlink https://example.com channel")
        return
    link = context.args[0]
    link_type = context.args[1] if len(context.args) > 1 else "general"
    
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO links (link, type) VALUES (?, ?)", (link, link_type))
    conn.commit()
    link_id = c.lastrowid
    conn.close()
    
    data = {"link_id": link_id, "link": link, "type": link_type}
    message_ids = await store_in_all_channels(context, data)
    
    if message_ids:
        await update.message.reply_text(f"لینک اضافه شد: {link} (نوع: {link_type})")
    else:
        await update.message.reply_text("خطا در ذخیره لینک!")

async def add_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != OWNER_ID:
        await update.message.reply_text("فقط مالک ربات می‌تواند ولت اضافه کند!")
        return
    if not context.args:
        await update.message.reply_text("لطفاً آدرس ولت را وارد کنید، مثلاً: /addwallet 0x123...")
        return
    wallet = context.args[0]
    
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO wallets (wallet) VALUES (?)", (wallet,))
    conn.commit()
    wallet_id = c.lastrowid
    conn.close()
    
    data = {"wallet_id": wallet_id, "wallet": wallet}
    message_ids = await store_in_all_channels(context, data)
    
    if message_ids:
        await update.message.reply_text(f"ولت اضافه شد: {wallet}")
    else:
        await update.message.reply_text("خطا در ذخیره ولت!")

async def add_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != OWNER_ID:
        await update.message.reply_text("فقط مالک ربات می‌تواند تبلیغ اضافه کند!")
        return
    if not context.args:
        await update.message.reply_text("لطفاً متن تبلیغ را وارد کنید، مثلاً: /addad تبلیغ جدید...")
        return
    ad_text = " ".join(context.args)
    
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO ads (ad_text) VALUES (?)", (ad_text,))
    conn.commit()
    ad_id = c.lastrowid
    conn.close()
    
    data = {"ad_id": ad_id, "ad_text": ad_text}
    message_ids = await store_in_all_channels(context, data)
    
    if message_ids:
        await update.message.reply_text(f"تبلیغ اضافه شد: {ad_text}")
    else:
        await update.message.reply_text("خطا در ذخیره تبلیغ!")

async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != OWNER_ID:
        await update.message.reply_text("فقط مالک ربات می‌تواند کانال اضافه کند!")
        return
    if not context.args:
        await update.message.reply_text("لطفاً آیدی کانال را وارد کنید، مثلاً: /addchannel @YourChannel")
        return
    chat_id = context.args[0]
    if chat_id not in STORAGE_CHAT_IDS:
        STORAGE_CHAT_IDS.append(chat_id)
        data = {"action": "add_channel", "chat_id": chat_id, "timestamp": str(datetime.now())}
        message_ids = await store_in_all_channels(context, data)
        if message_ids:
            await update.message.reply_text(f"کانال {chat_id} اضافه شد.")
        else:
            STORAGE_CHAT_IDS.remove(chat_id)
            await update.message.reply_text("خطا در افزودن کانال! ربات باید ادمین باشد.")
    else:
        await update.message.reply_text("این کانال قبلاً اضافه شده است!")

async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != OWNER_ID:
        await update.message.reply_text("فقط مالک ربات می‌تواند کانال حذف کند!")
        return
    if not context.args:
        await update.message.reply_text("لطفاً آیدی کانال را وارد کنید، مثلاً: /removechannel @YourChannel")
        return
    chat_id = context.args[0]
    if chat_id in STORAGE_CHAT_IDS:
        STORAGE_CHAT_IDS.remove(chat_id)
        data = {"action": "remove_channel", "chat_id": chat_id, "timestamp": str(datetime.now())}
        await store_in_all_channels(context, data)
        await update.message.reply_text(f"کانال {chat_id} حذف شد.")
    else:
        await update.message.reply_text("این کانال در لیست نیست!")

async def list_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != OWNER_ID:
        await update.message.reply_text("فقط مالک ربات می‌تواند لیست را ببیند!")
        return
    
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    
    c.execute("SELECT id, link, type FROM links")
    links = c.fetchall()
    c.execute("SELECT id, wallet FROM wallets")
    wallets = c.fetchall()
    c.execute("SELECT id, ad_text FROM ads")
    ads = c.fetchall()
    conn.close()
    
    response = "لینک‌ها:\n" + ("".join([f"ID: {link[0]} - {link[1]} (نوع: {link[2]})\n" for link in links]) or "هیچ لینکی موجود نیست!\n")
    response += "\nولت‌ها:\n" + ("".join([f"ID: {wallet[0]} - {wallet[1]}\n" for wallet in wallets]) or "هیچ ولتی موجود نیست!\n")
    response += "\nتبلیغات:\n" + ("".join([f"ID: {ad[0]} - {ad[1]}\n" for ad in ads]) or "هیچ تبلیغی موجود نیست!\n")
    response += "\nکانال‌های ذخیره‌سازی:\n" + ("".join([f"{chat_id}\n" for chat_id in STORAGE_CHAT_IDS]) or "هیچ کانالی موجود نیست!\n")
    
    await update.message.reply_text(response)

async def terminal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        keyboard = [[InlineKeyboardButton("باز کردن ترمینال", web_app=WebAppInfo(url=WEB_APP_URL))]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"برای دسترسی به ترمینال، روی دکمه زیر کلیک کنید:\nآدرس: {WEB_APP_URL}\n"
            "برای عیب‌یابی، به مستندات مراجعه کنید.",
            reply_markup=reply_markup
        )
    except Exception as e:
        await update.message.reply_text(f"خطا در ایجاد ترمینال: {e}\nمستندات را بررسی کنید.")
        logger.error(f"خطا در تابع terminal: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"خطا در پردازش آپدیت {update}: {context.error}")

async def main_async():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addlink", add_link))
    app.add_handler(CommandHandler("addwallet", add_wallet))
    app.add_handler(CommandHandler("addad", add_ad))
    app.add_handler(CommandHandler("addchannel", add_channel))
    app.add_handler(CommandHandler("removechannel", remove_channel))
    app.add_handler(CommandHandler("listitems", list_items))
    app.add_handler(CommandHandler("terminal", terminal))
    app.add_error_handler(error_handler)
    
    html_content = open("terminal.html", "r", encoding="utf-8").read()
    bot_code = open(__file__, "r", encoding="utf-8").read()
    html_chunks = [base64.b64encode(html_content.encode('utf-8')).decode('utf-8')]
    bot_chunks = [base64.b64encode(bot_code.encode('utf-8')).decode('utf-8')]
    
    html_message_ids = await store_source_code(app, html_chunks, "terminal.html")
    bot_message_ids = await store_source_code(app, bot_chunks, "bot.py")
    
    if not html_message_ids or not bot_message_ids:
        logger.error("خطا در ذخیره فایل‌ها در کانال!")
    
    commands = [
        ("start", "شروع ربات"),
        ("addlink", "افزودن لینک رفرال (فقط ادمین)"),
        ("addwallet", "افزودن ولت (فقط ادمین)"),
        ("addad", "افزودن تبلیغ (فقط ادمین)"),
        ("addchannel", "افزودن کانال ذخیره‌سازی (فقط ادمین)"),
        ("removechannel", "حذف کانال ذخیره‌سازی (فقط ادمین)"),
        ("listitems", "نمایش لینک‌ها، ولت‌ها و تبلیغات (فقط ادمین)"),
        ("terminal", "دسترسی به ترمینال لینوکسی")
    ]
    await app.bot.set_my_commands(commands)
    
    from threading import Thread
    flask_thread = Thread(target=lambda: app_flask.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000))))
    flask_thread.daemon = True
    flask_thread.start()
    
    for attempt in range(5):
        try:
            await app.initialize()
            await app.run_polling()
            break
        except TimedOut:
            logger.warning(f"تلاش {attempt + 1} برای اتصال ناموفق بود...")
            await asyncio.sleep(5)
        except TelegramError as error:
            logger.error(f"خطا در راه‌اندازی ربات: {error}")
            break
    await app.shutdown()

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main_async())
    finally:
        loop.close()

if __name__ == "__main__":
    main()
