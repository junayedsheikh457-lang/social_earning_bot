import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Render থেকে PORT এবং Environment থেকে TOKEN নিন
PORT = int(os.environ.get('PORT', 8000))
TOKEN = os.environ.get('BOT_TOKEN') 

# Mini App এর URL (আপনার Render URL)
APP_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://your-app.onrender.com')

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
    
    # ***** সবচেয়ে গুরুত্বপূর্ণ অংশ *****
    # run_polling() বাদ দিয়ে run_webhook ব্যবহার করুন
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{APP_URL}/{TOKEN}"
    )
