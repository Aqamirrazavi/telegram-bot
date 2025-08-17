import os
import subprocess
import sys
import time
import base64
import json
import asyncio
from telegram import Bot
from telegram.error import TelegramError, TimedOut

def run_command(command, check=True):
    try:
        result = subprocess.run(command, shell=True, check=check, text=True, capture_output=True)
        print(result.stdout)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        print(f"خطا در اجرای دستور '{command}': {e.stderr}")
        return False, e.stderr

async def store_file_in_channel(bot, chat_id, file_content, file_name):
    encoded = base64.b64encode(file_content.encode('utf-8')).decode('utf-8')
    chunk_size = 4000
    chunks = [encoded[i:i+chunk_size] for i in range(0, len(encoded), chunk_size)]
    message_ids = []
    unique_id = str(time.time())
    
    for i, chunk in enumerate(chunks):
        data = {"action": f"store_file_{file_name}", "chunk_id": f"{unique_id}_{i}", "chunk": chunk}
        for attempt in range(5):
            try:
                message = await bot.send_message(
                    chat_id=chat_id,
                    text=json.dumps(data, ensure_ascii=False),
                    disable_notification=True
                )
                message_ids.append((chat_id, message.message_id))
                break
            except TimedOut:
                print(f"تلاش {attempt + 1} برای ذخیره در {chat_id} ناموفق بود...")
                await asyncio.sleep(2)
            except TelegramError as error:
                print(f"خطا در ذخیره در {chat_id}: {error}")
                return None
    return message_ids

async def main():
    print("=== شروع راه‌اندازی ربات ===")
    
    # مرحله 1: بررسی اینترنت
    print("مرحله 1: بررسی اتصال اینترنت...")
    success, _ = run_command("ping -c 4 google.com", check=False)
    if not success:
        print("خطا: اتصال اینترنت برقرار نیست!")
        sys.exit(1)
    
    # مرحله 2: آماده‌سازی پوشه
    print("مرحله 2: آماده‌سازی پوشه...")
    run_command("mkdir -p ~/telegram_bot")
    os.chdir(os.path.expanduser("~/telegram_bot"))
    
    # مرحله 3: نصب پیش‌نیازها
    print("مرحله 3: نصب پیش‌نیازها...")
    if not run_command("pkg update && pkg install python termux-tools net-tools git -y")[0]:
        print("خطا: نصب پیش‌نیازها ناموفق بود!")
        sys.exit(1)
    packages = ["python-telegram-bot[job-queue]==20.7", "requests", "flask", "pyngrok"]
    for pkg in packages:
        if not run_command(f"pip install {pkg}")[0]:
            print(f"خطا: نصب {pkg} ناموفق بود!")
            sys.exit(1)
    
    # مرحله 4: ذخیره فایل‌ها در کانال
    print("مرحله 4: ذخیره فایل‌ها در کانال...")
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    bot_code = open("bot.py", "r", encoding="utf-8").read()
    html_content = open("terminal.html", "r", encoding="utf-8").read()
    
    bot_message_ids = await store_file_in_channel(bot, os.getenv("STORAGE_CHAT_ID"), bot_code, "bot.py")
    html_message_ids = await store_file_in_channel(bot, os.getenv("STORAGE_CHAT_ID"), html_content, "terminal.html")
    
    if not bot_message_ids or not html_message_ids:
        print("خطا: ذخیره فایل‌ها در کانال ناموفق بود! ربات باید ادمین کانال باشد.")
        sys.exit(1)
    
    # مرحله 5: راهنمای استقرار روی Render
    print("=== مرحله 5: آماده‌سازی برای Render ===")
    print("1. به https://dashboard.render.com بروید و وارد شوید.")
    print("2. روی New > Web Service کلیک کنید.")
    print("3. مخزن GitHub 'telegram-bot' را انتخاب کنید.")
    print("4. تنظیمات:")
    print("   - Environment: Python")
    print("   - Build Command: pip install -r requirements.txt")
    print("   - Start Command: python bot.py")
    print("   - Environment Variables:")
    print(f"     BOT_TOKEN: {os.getenv('BOT_TOKEN')}")
    print(f"     STORAGE_CHAT_ID: {os.getenv('STORAGE_CHAT_ID')}")
    print(f"     OWNER_ID: {os.getenv('OWNER_ID')}")
    print("     WEB_APP_URL: https://<your-app-name>.onrender.com (پس از ایجاد سرویس)")
    print("5. سرویس را ایجاد کنید و URL را در BotFather با /setmenubutton تنظیم کنید.")
    print("6. دستورات BotFather:")
    print("   /setcommands")
    print("   start - شروع ربات")
    print("   addlink - افزودن لینک رفرال (فقط ادمین)")
    print("   addwallet - افزودن ولت (فقط ادمین)")
    print("   addad - افزودن تبلیغ (فقط ادمین)")
    print("   addchannel - افزودن کانال ذخیره‌سازی (فقط ادمین)")
    print("   removechannel - حذف کانال ذخیره‌سازی (فقط ادمین)")
    print("   listitems - نمایش لینک‌ها، ولت‌ها و تبلیغات (فقط ادمین)")
    print("   terminal - دسترسی به ترمینال لینوکسی")
    print("   /setmenubutton (URL سرویس Render)")
    print("7. برای تست، /terminal را در ربات اجرا کنید.")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
