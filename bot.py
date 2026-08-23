import os
import sqlite3
import asyncio
from datetime import datetime
from flask import Flask, request, send_from_directory, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# ================== CONFIG ==================
TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8000))
APP_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

# Admin ID
DEFAULT_ADMIN = 5851334722
env_admins = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
ADMIN_IDS = list(set([DEFAULT_ADMIN] + env_admins))

BKASH_NUMBER = "01600170756"
NAGAD_NUMBER = "01727332914"

DB_NAME = "social_earn.db"

if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set!")

# ================== DATABASE ==================
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        balance REAL DEFAULT 0,
        is_admin INTEGER DEFAULT 0,
        created_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creator_id INTEGER,
        title TEXT,
        description TEXT,
        price REAL,
        total_slots INTEGER,
        remaining_slots INTEGER,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        FOREIGN KEY (creator_id) REFERENCES users(telegram_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        worker_id INTEGER,
        proof TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        FOREIGN KEY (task_id) REFERENCES tasks(id),
        FOREIGN KEY (worker_id) REFERENCES users(telegram_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        method TEXT,
        trx_id TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(telegram_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS withdraws (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        method TEXT,
        number TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(telegram_id)
    )''')

    conn.commit()
    conn.close()
    print("Database initialized.")

def get_or_create_user(telegram_id, username=None, full_name=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = c.fetchone()
    if not user:
        is_admin = 1 if telegram_id in ADMIN_IDS else 0
        c.execute(
            "INSERT INTO users (telegram_id, username, full_name, balance, is_admin, created_at) VALUES (?, ?, ?, 0, ?, ?)",
            (telegram_id, username, full_name, is_admin, datetime.now().isoformat())
        )
        conn.commit()
        c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = c.fetchone()
    else:
        if telegram_id in ADMIN_IDS and user["is_admin"] == 0:
            c.execute("UPDATE users SET is_admin = 1 WHERE telegram_id = ?", (telegram_id,))
            conn.commit()
    conn.close()
    return dict(user) if user else None

def get_user(telegram_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = c.fetchone()
    conn.close()
    return dict(user) if user else None

def update_balance(telegram_id, amount):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amount, telegram_id))
    conn.commit()
    conn.close()

# ================== FLASK ==================
app = Flask(__name__)

# ================== TELEGRAM APPLICATION ==================
application = (
    Application.builder()
    .token(TOKEN)
    .updater(None)
    .build()
)

# ================== BOT HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id, user.username, user.full_name)

    if not APP_URL:
        await update.message.reply_text("Mini App URL সেট করা নেই।")
        return

    keyboard = [[InlineKeyboardButton("🚀 Open Mini App", web_app=WebAppInfo(url=APP_URL))]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        f"স্বাগতম {user.first_name}! 👋\n\n"
        f"এটি Social Earn Bot।\n"
        f"নিচের বাটনে ক্লিক করে Mini App খুলুন।"
    )
    await update.message.reply_text(text, reply_markup=reply_markup)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("আপনি Admin নন।")
        return

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status = 'pending'")
    pending_tasks = c.fetchone()["cnt"]

    c.execute("SELECT COUNT(*) as cnt FROM deposits WHERE status = 'pending'")
    pending_deposits = c.fetchone()["cnt"]

    c.execute("SELECT COUNT(*) as cnt FROM withdraws WHERE status = 'pending'")
    pending_withdraws = c.fetchone()["cnt"]

    conn.close()

    text = (
        f"🔐 Admin Panel\n\n"
        f"Pending Tasks: {pending_tasks}\n"
        f"Pending Deposits: {pending_deposits}\n"
        f"Pending Withdraws: {pending_withdraws}\n\n"
        f"কমান্ডসমূহ:\n"
        f"/pending_tasks - Task Approve করুন\n"
        f"/pending_deposits - Deposit Approve করুন\n"
        f"/pending_withdraws - Withdraw Approve করুন"
    )
    await update.message.reply_text(text)

async def pending_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("আপনি Admin নন।")
        return

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT t.*, u.full_name FROM tasks t JOIN users u ON t.creator_id = u.telegram_id WHERE t.status = 'pending' ORDER BY t.id ASC LIMIT 10")
    tasks = c.fetchall()
    conn.close()

    if not tasks:
        await update.message.reply_text("কোনো Pending Task নেই।")
        return

    for t in tasks:
        text = (
            f"📋 Task #{t['id']}\n"
            f"Title: {t['title']}\n"
            f"Desc: {t['description']}\n"
            f"Price: ৳{t['price']}\n"
            f"Slots: {t['total_slots']}\n"
            f"Creator: {t['full_name']} ({t['creator_id']})\n"
        )
        keyboard = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_task_{t['id']}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_task_{t['id']}")
        ]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def pending_deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("আপনি Admin নন।")
        return

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT d.*, u.full_name FROM deposits d JOIN users u ON d.user_id = u.telegram_id WHERE d.status = 'pending' ORDER BY d.id ASC LIMIT 10")
    deposits = c.fetchall()
    conn.close()

    if not deposits:
        await update.message.reply_text("কোনো Pending Deposit নেই।")
        return

    for d in deposits:
        text = (
            f"💳 Deposit #{d['id']}\n"
            f"User: {d['full_name']} ({d['user_id']})\n"
            f"Amount: ৳{d['amount']}\n"
            f"Method: {d['method']}\n"
            f"TrxID: {d['trx_id']}\n"
        )
        keyboard = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_dep_{d['id']}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_dep_{d['id']}")
        ]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def pending_withdraws(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("আপনি Admin নন।")
        return

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT w.*, u.full_name FROM withdraws w JOIN users u ON w.user_id = u.telegram_id WHERE w.status = 'pending' ORDER BY w.id ASC LIMIT 10")
    withdraws = c.fetchall()
    conn.close()

    if not withdraws:
        await update.message.reply_text("কোনো Pending Withdraw নেই।")
        return

    for w in withdraws:
        text = (
            f"💸 Withdraw #{w['id']}\n"
            f"User: {w['full_name']} ({w['user_id']})\n"
            f"Amount: ৳{w['amount']}\n"
            f"Method: {w['method']}\n"
            f"Number: {w['number']}\n"
        )
        keyboard = [[
            InlineKeyboardButton("✅ Paid & Approve", callback_data=f"approve_wd_{w['id']}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_wd_{w['id']}")
        ]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if user_id not in ADMIN_IDS:
        await query.edit_message_text("আপনি Admin নন।")
        return

    conn = get_db()
    c = conn.cursor()

    if data.startswith("approve_task_"):
        task_id = int(data.split("_")[2])
        c.execute("UPDATE tasks SET status = 'approved' WHERE id = ?", (task_id,))
        conn.commit()
        await query.edit_message_text(f"✅ Task #{task_id} Approved!")

    elif data.startswith("reject_task_"):
        task_id = int(data.split("_")[2])
        c.execute("UPDATE tasks SET status = 'rejected' WHERE id = ?", (task_id,))
        conn.commit()
        await query.edit_message_text(f"❌ Task #{task_id} Rejected.")

    elif data.startswith("approve_dep_"):
        dep_id = int(data.split("_")[2])
        c.execute("SELECT * FROM deposits WHERE id = ?", (dep_id,))
        dep = c.fetchone()
        if dep and dep["status"] == "pending":
            c.execute("UPDATE deposits SET status = 'approved' WHERE id = ?", (dep_id,))
            c.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (dep["amount"], dep["user_id"]))
            conn.commit()
            await query.edit_message_text(f"✅ Deposit #{dep_id} Approved! ৳{dep['amount']} যোগ করা হয়েছে।")
        else:
            await query.edit_message_text("ইতিমধ্যে প্রসেস করা হয়েছে।")

    elif data.startswith("reject_dep_"):
        dep_id = int(data.split("_")[2])
        c.execute("UPDATE deposits SET status = 'rejected' WHERE id = ?", (dep_id,))
        conn.commit()
        await query.edit_message_text(f"❌ Deposit #{dep_id} Rejected.")

    elif data.startswith("approve_wd_"):
        wd_id = int(data.split("_")[2])
        c.execute("UPDATE withdraws SET status = 'approved' WHERE id = ?", (wd_id,))
        conn.commit()
        await query.edit_message_text(f"✅ Withdraw #{wd_id} Approved (Paid).")

    elif data.startswith("reject_wd_"):
        wd_id = int(data.split("_")[2])
        c.execute("SELECT * FROM withdraws WHERE id = ?", (wd_id,))
        wd = c.fetchone()
        if wd and wd["status"] == "pending":
            c.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (wd["amount"], wd["user_id"]))
            c.execute("UPDATE withdraws SET status = 'rejected' WHERE id = ?", (wd_id,))
            conn.commit()
            await query.edit_message_text(f"❌ Withdraw #{wd_id} Rejected. টাকা ফেরত দেওয়া হয়েছে।")
        else:
            await query.edit_message_text("ইতিমধ্যে প্রসেস করা হয়েছে।")

    conn.close()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("admin", admin_panel))
application.add_handler(CommandHandler("pending_tasks", pending_tasks))
application.add_handler(CommandHandler("pending_deposits", pending_deposits))
application.add_handler(CommandHandler("pending_withdraws", pending_withdraws))
application.add_handler(CallbackQueryHandler(button_handler))

# ================== API ROUTES ==================
@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/api/user/<int:user_id>")
def api_user(user_id):
    user = get_user(user_id)
    if not user:
        get_or_create_user(user_id)
        user = get_user(user_id)
    return jsonify({
        "telegram_id": user["telegram_id"],
        "full_name": user["full_name"],
        "balance": user["balance"],
        "is_admin": bool(user["is_admin"])
    })

@app.route("/api/tasks")
def api_tasks():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT t.*, u.full_name as creator_name FROM tasks t JOIN users u ON t.creator_id = u.telegram_id WHERE t.status = 'approved' AND t.remaining_slots > 0 ORDER BY t.id DESC")
    tasks = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(tasks)

@app.route("/api/create_task", methods=["POST"])
def api_create_task():
    data = request.json
    user_id = data.get("user_id")
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    price = float(data.get("price", 0))
    slots = int(data.get("slots", 1))

    if not title or not description or price <= 0 or slots <= 0:
        return jsonify({"error": "সব ঘর সঠিকভাবে পূরণ করুন"}), 400

    user = get_user(user_id)
    if not user:
        get_or_create_user(user_id)
        user = get_user(user_id)

    # Task তৈরি করতে price * slots পরিমাণ টাকা লাগবে
    required = price * slots
    if user["balance"] < required:
        return jsonify({
            "error": f"অপর্যাপ্ত ব্যালেন্স! Task তৈরি করতে ৳{required:.0f} লাগবে। আপনার ব্যালেন্স: ৳{user['balance']:.0f}"
        }), 400

    # টাকা কেটে রাখি (hold)
    update_balance(user_id, -required)

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO tasks (creator_id, title, description, price, total_slots, remaining_slots, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
        (user_id, title, description, price, slots, slots, datetime.now().isoformat())
    )
    conn.commit()
    task_id = c.lastrowid
    conn.close()

    return jsonify({
        "success": True,
        "task_id": task_id,
        "message": f"Task সাবমিট হয়েছে। ৳{required:.0f} কেটে রাখা হয়েছে। Admin approve এর অপেক্ষায়।"
    })

@app.route("/api/deposit", methods=["POST"])
def api_deposit():
    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("amount", 0))
    method = data.get("method", "")
    trx_id = data.get("trx_id", "").strip()

    if amount <= 0 or not trx_id or method not in ["bkash", "nagad"]:
        return jsonify({"error": "Invalid data"}), 400

    get_or_create_user(user_id)

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO deposits (user_id, amount, method, trx_id, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
        (user_id, amount, method, trx_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Deposit রিকোয়েস্ট সাবমিট হয়েছে। Admin approve এর অপেক্ষায়।"})

@app.route("/api/withdraw", methods=["POST"])
def api_withdraw():
    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("amount", 0))
    method = data.get("method", "")
    number = data.get("number", "").strip()

    user = get_user(user_id)
    if not user:
        get_or_create_user(user_id)
        user = get_user(user_id)

    if amount <= 0 or amount > user["balance"]:
        return jsonify({"error": "অপর্যাপ্ত ব্যালেন্স বা ভুল এমাউন্ট"}), 400

    if method not in ["bkash", "nagad"] or not number:
        return jsonify({"error": "Invalid data"}), 400

    update_balance(user_id, -amount)

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO withdraws (user_id, amount, method, number, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
        (user_id, amount, method, number, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Withdraw রিকোয়েস্ট সাবমিট হয়েছে।"})

@app.route("/api/payment_info")
def api_payment_info():
    return jsonify({
        "bkash": BKASH_NUMBER,
        "nagad": NAGAD_NUMBER
    })

# ================== WEBHOOK ==================
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.process_update(update))
        loop.close()
        return "ok", 200
    except Exception as e:
        print(f"Webhook Error: {e}")
        return "error", 500

# ================== STARTUP ==================
async def setup_webhook():
    if APP_URL:
        webhook_url = f"{APP_URL}/webhook"
        await application.bot.set_webhook(url=webhook_url)
        print(f"Webhook set to: {webhook_url}")
    else:
        print("WARNING: RENDER_EXTERNAL_URL not found.")

def main():
    init_db()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(setup_webhook())

    print(f"Starting server on port {PORT}...")
    print(f"Admin IDs: {ADMIN_IDS}")
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
