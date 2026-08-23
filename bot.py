import os
import sqlite3
import asyncio
import base64
from datetime import datetime
from flask import Flask, request, send_from_directory, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8000))
APP_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

DEFAULT_ADMIN = 5851334722
env_admins = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
ADMIN_IDS = list(set([DEFAULT_ADMIN] + env_admins))

BKASH_NUMBER = "01600170756"
NAGAD_NUMBER = "01727332914"
DB_NAME = "social_earn.db"

if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set!")

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
        require_screenshot INTEGER DEFAULT 1,
        example_text TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        FOREIGN KEY (creator_id) REFERENCES users(telegram_id)
    )''')

    # Add columns if missing (for existing DB)
    try:
        c.execute("ALTER TABLE tasks ADD COLUMN require_screenshot INTEGER DEFAULT 1")
    except: pass
    try:
        c.execute("ALTER TABLE tasks ADD COLUMN example_text TEXT")
    except: pass

    c.execute('''CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        worker_id INTEGER,
        proof_text TEXT,
        proof_image TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        FOREIGN KEY (task_id) REFERENCES tasks(id),
        FOREIGN KEY (worker_id) REFERENCES users(telegram_id)
    )''')

    try:
        c.execute("ALTER TABLE submissions ADD COLUMN proof_text TEXT")
    except: pass
    try:
        c.execute("ALTER TABLE submissions ADD COLUMN proof_image TEXT")
    except: pass

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

app = Flask(__name__)

application = (
    Application.builder()
    .token(TOKEN)
    .updater(None)
    .build()
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id, user.username, user.full_name)
    if not APP_URL:
        await update.message.reply_text("Mini App URL সেট করা নেই।")
        return
    keyboard = [[InlineKeyboardButton("🚀 Open Mini App", web_app=WebAppInfo(url=APP_URL))]]
    await update.message.reply_text(
        f"স্বাগতম {user.first_name}! 👋\n\nএটি Social Earn Bot।\nনিচের বাটনে ক্লিক করে Mini App খুলুন।",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

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
        f"/pending_tasks\n/pending_deposits\n/pending_withdraws"
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
        text = f"📋 Task #{t['id']}\nTitle: {t['title']}\nDesc: {t['description']}\nPrice: ৳{t['price']}\nSlots: {t['total_slots']}\nCreator: {t['full_name']}"
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
        text = f"💳 Deposit #{d['id']}\nUser: {d['full_name']}\nAmount: ৳{d['amount']}\nMethod: {d['method']}\nTrxID: {d['trx_id']}"
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
        text = f"💸 Withdraw #{w['id']}\nUser: {w['full_name']}\nAmount: ৳{w['amount']}\nMethod: {w['method']}\nNumber: {w['number']}"
        keyboard = [[
            InlineKeyboardButton("✅ Paid", callback_data=f"approve_wd_{w['id']}"),
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
        c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        t = c.fetchone()
        if t and t["status"] == "pending":
            refund = t["price"] * t["total_slots"]
            c.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (refund, t["creator_id"]))
            c.execute("UPDATE tasks SET status = 'rejected' WHERE id = ?", (task_id,))
            conn.commit()
            await query.edit_message_text(f"❌ Task #{task_id} Rejected. ৳{refund} ফেরত দেওয়া হয়েছে।")
        else:
            await query.edit_message_text("ইতিমধ্যে প্রসেস হয়েছে।")
    elif data.startswith("approve_dep_"):
        dep_id = int(data.split("_")[2])
        c.execute("SELECT * FROM deposits WHERE id = ?", (dep_id,))
        dep = c.fetchone()
        if dep and dep["status"] == "pending":
            c.execute("UPDATE deposits SET status = 'approved' WHERE id = ?", (dep_id,))
            c.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (dep["amount"], dep["user_id"]))
            conn.commit()
            await query.edit_message_text(f"✅ Deposit #{dep_id} Approved! ৳{dep['amount']} যোগ হয়েছে।")
        else:
            await query.edit_message_text("ইতিমধ্যে প্রসেস হয়েছে।")
    elif data.startswith("reject_dep_"):
        dep_id = int(data.split("_")[2])
        c.execute("UPDATE deposits SET status = 'rejected' WHERE id = ?", (dep_id,))
        conn.commit()
        await query.edit_message_text(f"❌ Deposit #{dep_id} Rejected.")
    elif data.startswith("approve_wd_"):
        wd_id = int(data.split("_")[2])
        c.execute("UPDATE withdraws SET status = 'approved' WHERE id = ?", (wd_id,))
        conn.commit()
        await query.edit_message_text(f"✅ Withdraw #{wd_id} Approved.")
    elif data.startswith("reject_wd_"):
        wd_id = int(data.split("_")[2])
        c.execute("SELECT * FROM withdraws WHERE id = ?", (wd_id,))
        wd = c.fetchone()
        if wd and wd["status"] == "pending":
            c.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (wd["amount"], wd["user_id"]))
            c.execute("UPDATE withdraws SET status = 'rejected' WHERE id = ?", (wd_id,))
            conn.commit()
            await query.edit_message_text(f"❌ Withdraw #{wd_id} Rejected. টাকা ফেরত।")
        else:
            await query.edit_message_text("ইতিমধ্যে প্রসেস হয়েছে।")
    conn.close()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("admin", admin_panel))
application.add_handler(CommandHandler("pending_tasks", pending_tasks))
application.add_handler(CommandHandler("pending_deposits", pending_deposits))
application.add_handler(CommandHandler("pending_withdraws", pending_withdraws))
application.add_handler(CallbackQueryHandler(button_handler))

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
    c.execute("""SELECT t.id, t.title, t.description, t.price, t.total_slots, t.remaining_slots,
               t.require_screenshot, t.example_text, u.full_name as creator_name
               FROM tasks t JOIN users u ON t.creator_id = u.telegram_id
               WHERE t.status = 'approved' AND t.remaining_slots > 0 ORDER BY t.id DESC""")
    tasks = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(tasks)

@app.route("/api/task/<int:task_id>")
def api_task_detail(task_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT t.*, u.full_name as creator_name
               FROM tasks t JOIN users u ON t.creator_id = u.telegram_id
               WHERE t.id = ? AND t.status = 'approved'""", (task_id,))
    task = c.fetchone()
    conn.close()
    if not task:
        return jsonify({"error": "Task পাওয়া যায়নি"}), 404
    return jsonify(dict(task))

@app.route("/api/create_task", methods=["POST"])
def api_create_task():
    data = request.json
    user_id = data.get("user_id")
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    price = float(data.get("price", 0))
    slots = int(data.get("slots", 1))
    require_screenshot = 1 if data.get("require_screenshot", True) else 0
    example_text = data.get("example_text", "").strip()

    if not title or not description or price <= 0 or slots <= 0:
        return jsonify({"error": "সব ঘর সঠিকভাবে পূরণ করুন"}), 400

    user = get_user(user_id)
    if not user:
        get_or_create_user(user_id)
        user = get_user(user_id)

    required = price * slots
    if user["balance"] < required:
        return jsonify({
            "error": f"অপর্যাপ্ত ব্যালেন্স! ৳{required:.0f} লাগবে। আপনার ব্যালেন্স: ৳{user['balance']:.0f}"
        }), 400

    update_balance(user_id, -required)

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO tasks (creator_id, title, description, price, total_slots, remaining_slots, require_screenshot, example_text, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
        (user_id, title, description, price, slots, slots, require_screenshot, example_text, datetime.now().isoformat())
    )
    conn.commit()
    task_id = c.lastrowid
    conn.close()

    return jsonify({
        "success": True,
        "task_id": task_id,
        "message": f"Task সাবমিট হয়েছে। ৳{required:.0f} কেটে রাখা হয়েছে। Admin approve এর অপেক্ষায়।"
    })

@app.route("/api/submit_proof", methods=["POST"])
def api_submit_proof():
    data = request.json
    user_id = data.get("user_id")
    task_id = data.get("task_id")
    proof_text = data.get("proof_text", "").strip()
    proof_image = data.get("proof_image", "")  # base64 string (optional)

    if not user_id or not task_id:
        return jsonify({"error": "Invalid data"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE id = ? AND status = 'approved' AND remaining_slots > 0", (task_id,))
    task = c.fetchone()
    if not task:
        conn.close()
        return jsonify({"error": "Task পাওয়া যায়নি বা আর স্লট নেই"}), 400

    if task["require_screenshot"] and not proof_image and not proof_text:
        conn.close()
        return jsonify({"error": "এই Task-এ Screenshot বা প্রুফ দিতে হবে"}), 400

    # Already submitted?
    c.execute("SELECT id FROM submissions WHERE task_id = ? AND worker_id = ? AND status != 'rejected'", (task_id, user_id))
    if c.fetchone():
        conn.close()
        return jsonify({"error": "আপনি ইতিমধ্যে এই Task-এ সাবমিট করেছেন"}), 400

    # Limit image size roughly
    if proof_image and len(proof_image) > 400000:
        conn.close()
        return jsonify({"error": "ছবি অনেক বড়। ছোট Screenshot দিন।"}), 400

    c.execute(
        "INSERT INTO submissions (task_id, worker_id, proof_text, proof_image, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
        (task_id, user_id, proof_text, proof_image, datetime.now().isoformat())
    )
    # Reduce slot
    c.execute("UPDATE tasks SET remaining_slots = remaining_slots - 1 WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "প্রুফ সাবমিট হয়েছে। Task Creator রিভিউ করবে।"})

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
    c.execute("INSERT INTO deposits (user_id, amount, method, trx_id, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
              (user_id, amount, method, trx_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Deposit রিকোয়েস্ট সাবমিট হয়েছে।"})

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
        return jsonify({"error": "অপর্যাপ্ত ব্যালেন্স"}), 400
    if method not in ["bkash", "nagad"] or not number:
        return jsonify({"error": "Invalid data"}), 400
    update_balance(user_id, -amount)
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO withdraws (user_id, amount, method, number, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
              (user_id, amount, method, number, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Withdraw রিকোয়েস্ট সাবমিট হয়েছে।"})

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

async def setup_webhook():
    if APP_URL:
        await application.bot.set_webhook(url=f"{APP_URL}/webhook")
        print(f"Webhook set to: {APP_URL}/webhook")

def main():
    init_db()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(setup_webhook())
    print(f"Starting on port {PORT} | Admins: {ADMIN_IDS}")
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
