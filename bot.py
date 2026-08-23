import os
import asyncio
from flask import Flask, request, send_from_directory
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# ================== Environment Variables ==================
TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8000))
# Render automatically provides this, or you can set it manually
APP_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set!")

# ================== Flask App ==================
app = Flask(__name__)

# ================== Telegram Application ==================
# updater=None because we will process updates ourselves via Flask
application = (
    Application.builder()
    .token(TOKEN)
    .updater(None)
    .build()
)

# ================== Bot Handlers ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not APP_URL:
        await update.message.reply_text("Mini App URL সেট করা নেই। RENDER_EXTERNAL_URL চেক করুন।")
        return

    keyboard = [[InlineKeyboardButton("🚀 Open Mini App", web_app={"url": APP_URL})]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "আমার Mini App এ স্বাগতম! 👇\nনিচের বাটনে ক্লিক করুন:",
        reply_markup=reply_markup
    )

application.add_handler(CommandHandler("start", start))

# ================== Flask Routes ==================
@app.route("/")
def home():
    """Mini App (index.html) সার্ভ করে"""
    return send_from_directory(".", "index.html")


@app.route("/webhook", methods=["POST"])
def webhook():
    """Telegram থেকে আপডেট রিসিভ করে প্রসেস করে"""
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)

        # Async function কে Flask এর ভিতরে চালানোর জন্য
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.process_update(update))
        loop.close()

        return "ok", 200
    except Exception as e:
        print(f"Webhook Error: {e}")
        return "error", 500


# ================== Startup ==================
async def setup_webhook():
    """Webhook সেট করে দেয়"""
    if APP_URL:
        webhook_url = f"{APP_URL}/webhook"
        await application.bot.set_webhook(url=webhook_url)
        print(f"Webhook set to: {webhook_url}")
    else:
        print("WARNING: RENDER_EXTERNAL_URL not found. Webhook not set.")


def main():
    # Application initialize করি
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(setup_webhook())

    # Flask চালু করি
    print(f"Starting server on port {PORT}...")
    app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
