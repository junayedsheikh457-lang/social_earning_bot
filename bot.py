import os
import asyncio
from flask import Flask, send_from_directory
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Flask App (Frontend সার্ভ করার জন্য)
app = Flask(__name__, static_folder='.')

# Render থেকে PORT এবং Environment থেকে TOKEN নিন
PORT = int(os.environ.get('PORT', 8000))
TOKEN = os.environ.get('BOT_TOKEN') 

# Mini App এর URL (আপনার Render URL)
APP_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://your-app.onrender.com')

# -------- ওয়েব পেজ লোড করার অংশ --------
@app.route('/')
def home():
    # index.html ফাইলটি রুট URL-এ দেখাবে
    return send_from_directory('.', 'index.html')

# -------- Telegram Bot এর অংশ --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # বটের জন্য একটি ওয়েব অ্যাপ বাটন তৈরি করুন
    keyboard = [[InlineKeyboardButton("🚀 Open Mini App", web_app={"url": APP_URL})]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "আমার Mini App এ স্বাগতম! নিচের বাটনে ক্লিক করুন:",
        reply_markup=reply_markup
    )

if __name__ == '__main__':
    if not TOKEN:
        print("ERROR: BOT_TOKEN is not set in Environment Variables.")
        exit(1)
        
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    # Flask অ্যাপটি ব্যাকগ্রাউন্ডে চালু করুন (HTML ফাইল সার্ভ করার জন্য)
    # নোট: এটি একটি সিমপ্লিফাইড পদ্ধতি, প্রোডাকশনে গুনিকর্ন ব্যবহার করা উচিত
    import threading
    def run_flask():
        app.run(host="0.0.0.0", port=PORT)

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # ***** সবচেয়ে গুরুত্বপূর্ণ অংশ *****
    # run_polling() বাদ দিয়ে run_webhook ব্যবহার করুন
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{APP_URL}/{TOKEN}"
    )
