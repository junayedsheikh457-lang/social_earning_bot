import os
import io
import base64
import sqlite3
import asyncio
from datetime import datetime
from flask import Flask, request, send_from_directory, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8000))
APP_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

DEFAULT_ADMIN = 5851334722
env_admins = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
ADMIN_IDS = list(set([DEFAULT_ADMIN] + env_admins))

BKASH_NUMBER = "01600170756"
NAGAD_NUMBER = "01727332914"
MAX_MEDIA = 900000

# ---- Persistent DB path (Render Disk mount at /var/data recommended) ----
def _resolve_db_path():
    # 1) explicit full path
    if os.environ.get("DB_PATH"):
        path = os.environ["DB_PATH"]
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path
    # 2) DB_DIR env (e.g. /var/data from Render Disk)
    db_dir = os.environ.get("DB_DIR", "/var/data")
    try:
        os.makedirs(db_dir, exist_ok=True)
        test = os.path.join(db_dir, ".write_test")
        with open(test, "w") as f:
            f.write("ok")
        os.remove(test)
        return os.path.join(db_dir, "social_earn.db")
    except Exception:
        pass
    # 3) local ./data fallback (ephemeral on free Render — will wipe on redeploy)
    local = os.path.join(os.getcwd(), "data")
    os.makedirs(local, exist_ok=True)
    print("WARNING: Using local data/ — set Render Disk at /var/data or DB_DIR to keep data after restart")
    return os.path.join(local, "social_earn.db")

DB_NAME = _resolve_db_path()
print(f"Database file: {DB_NAME}")

if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set!")

def normalize_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url

def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
        balance REAL DEFAULT 0, is_admin INTEGER DEFAULT 0, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, creator_id INTEGER, title TEXT, description TEXT,
        price REAL, total_slots INTEGER, remaining_slots INTEGER,
        require_screenshot INTEGER DEFAULT 1, example_text TEXT,
        task_link TEXT, example_image TEXT,
        status TEXT DEFAULT 'pending', created_at TEXT)''')
    for col, typ in [
        ("require_screenshot", "INTEGER DEFAULT 1"),
        ("example_text", "TEXT"),
        ("task_link", "TEXT"),
        ("example_image", "TEXT"),
    ]:
        try: c.execute(f"ALTER TABLE tasks ADD COLUMN {col} {typ}")
        except: pass
    c.execute('''CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, worker_id INTEGER,
        proof_text TEXT, proof_image TEXT, status TEXT DEFAULT 'pending', created_at TEXT)''')
    try: c.execute("ALTER TABLE submissions ADD COLUMN proof_text TEXT")
    except: pass
    try: c.execute("ALTER TABLE submissions ADD COLUMN proof_image TEXT")
    except: pass
    c.execute('''CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, method TEXT,
        trx_id TEXT, status TEXT DEFAULT 'pending', created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdraws (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, method TEXT,
        number TEXT, status TEXT DEFAULT 'pending', created_at TEXT)''')
    conn.commit()
    conn.close()

def get_or_create_user(telegram_id, username=None, full_name=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = c.fetchone()
    if not user:
        is_admin = 1 if telegram_id in ADMIN_IDS else 0
        c.execute("INSERT INTO users (telegram_id, username, full_name, balance, is_admin, created_at) VALUES (?,?,?,0,?,?)",
                  (telegram_id, username, full_name, is_admin, datetime.now().isoformat()))
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

def get_pending_earn(user_id):
    conn = get_db(); c = conn.cursor()
    c.execute("""SELECT COALESCE(SUM(t.price),0) as total FROM submissions s
               JOIN tasks t ON s.task_id=t.id
               WHERE s.worker_id=? AND s.status='pending'""", (user_id,))
    total = c.fetchone()["total"] or 0
    conn.close()
    return float(total)

def decode_data_url(data_url):
    if not data_url or not isinstance(data_url, str):
        return None, None
    if not data_url.startswith("data:"):
        return None, None
    try:
        header, b64 = data_url.split(",", 1)
        raw = base64.b64decode(b64)
        if "video" in header:
            return raw, "video"
        return raw, "photo"
    except Exception:
        return None, None

async def send_proof_to_creator(creator_id, worker_name, title, price, proof_text, proof_image, sub_id):
    caption = f"📩 New Proof\n\nTask: {title}\nWorker: {worker_name}\nReward: ৳{price}\n"
    if proof_text:
        caption += f"\nNote: {proof_text[:200]}"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"c_approve_{sub_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"c_reject_{sub_id}")
    ]])
    raw, kind = decode_data_url(proof_image)
    try:
        if raw and kind == "photo":
            await application.bot.send_photo(
                chat_id=creator_id,
                photo=InputFile(io.BytesIO(raw), filename="proof.jpg"),
                caption=caption[:1024],
                reply_markup=kb
            )
        elif raw and kind == "video":
            await application.bot.send_video(
                chat_id=creator_id,
                video=InputFile(io.BytesIO(raw), filename="proof.mp4"),
                caption=caption[:1024],
                reply_markup=kb
            )
        else:
            await application.bot.send_message(
                chat_id=creator_id,
                text=caption + ("\n\n(No media attached)" if not proof_image else "\n\n(Media in Mini App Reviews)"),
                reply_markup=kb
            )
    except Exception as e:
        print("send_proof_to_creator error:", e)

def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

app = Flask(__name__)
application = Application.builder().token(TOKEN).updater(None).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id, user.username, user.full_name)
    if not APP_URL:
        await update.message.reply_text("Mini App URL সেট করা নেই।")
        return
    keyboard = [[InlineKeyboardButton("Open Mini App", web_app=WebAppInfo(url=APP_URL))]]
    await update.message.reply_text(
        f"স্বাগতম {user.first_name}!\n\nMini App খুলুন।\n\nPC তে: Telegram Desktop latest version ব্যবহার করুন।",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("আপনি Admin নন।"); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status='pending'"); pt = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM deposits WHERE status='pending'"); pd = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM withdraws WHERE status='pending'"); pw = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM users"); uc = c.fetchone()["cnt"]
    conn.close()
    await update.message.reply_text(
        f"Admin\nUsers: {uc}\nPending Tasks: {pt}\nDeposits: {pd}\nWithdraws: {pw}\nDB: {DB_NAME}\n\n/pending_tasks\n/pending_deposits\n/pending_withdraws"
    )

async def pending_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("Admin নন।"); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT t.*, u.full_name FROM tasks t JOIN users u ON t.creator_id=u.telegram_id WHERE t.status='pending' ORDER BY t.id LIMIT 10")
    tasks = c.fetchall(); conn.close()
    if not tasks: await update.message.reply_text("কোনো Pending Task নেই।"); return
    for t in tasks:
        text = f"Task #{t['id']}\n{t['title']}\n৳{t['price']} x {t['total_slots']}\nCreator: {t['full_name']}"
        if t["task_link"]: text += f"\nLink: {t['task_link']}"
        kb = [[InlineKeyboardButton("Approve", callback_data=f"approve_task_{t['id']}"), InlineKeyboardButton("Reject", callback_data=f"reject_task_{t['id']}")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def pending_deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("Admin নন।"); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT d.*, u.full_name FROM deposits d JOIN users u ON d.user_id=u.telegram_id WHERE d.status='pending' ORDER BY d.id LIMIT 10")
    rows = c.fetchall(); conn.close()
    if not rows: await update.message.reply_text("কোনো Pending Deposit নেই।"); return
    for d in rows:
        text = f"#{d['id']} {d['full_name']}\n৳{d['amount']} {d['method']}\n{d['trx_id']}"
        kb = [[InlineKeyboardButton("Approve", callback_data=f"approve_dep_{d['id']}"), InlineKeyboardButton("Reject", callback_data=f"reject_dep_{d['id']}")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def pending_withdraws(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("Admin নন।"); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT w.*, u.full_name FROM withdraws w JOIN users u ON w.user_id=u.telegram_id WHERE w.status='pending' ORDER BY w.id LIMIT 10")
    rows = c.fetchall(); conn.close()
    if not rows: await update.message.reply_text("কোনো Pending Withdraw নেই।"); return
    for w in rows:
        text = f"#{w['id']} {w['full_name']}\n৳{w['amount']} {w['method']} {w['number']}"
        kb = [[InlineKeyboardButton("Paid", callback_data=f"approve_wd_{w['id']}"), InlineKeyboardButton("Reject", callback_data=f"reject_wd_{w['id']}")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

def do_review_submission(sub_id, action, actor_id):
    conn = get_db(); c = conn.cursor()
    c.execute("""SELECT s.*, t.creator_id, t.price, t.id as task_id
               FROM submissions s JOIN tasks t ON s.task_id=t.id WHERE s.id=?""", (sub_id,))
    sub = c.fetchone()
    if not sub:
        conn.close(); return False, "Submission পাওয়া যায়নি"
    if sub["creator_id"] != actor_id and actor_id not in ADMIN_IDS:
        conn.close(); return False, "এই Task আপনার না"
    if sub["status"] != "pending":
        conn.close(); return False, "ইতিমধ্যে রিভিউ হয়েছে"
    if action == "approve":
        c.execute("UPDATE submissions SET status='approved' WHERE id=?", (sub_id,))
        c.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (sub["price"], sub["worker_id"]))
        conn.commit(); conn.close()
        return True, f"Approve। Worker পেয়েছে ৳{sub['price']}"
    else:
        c.execute("UPDATE submissions SET status='rejected' WHERE id=?", (sub_id,))
        c.execute("UPDATE tasks SET remaining_slots = remaining_slots + 1 WHERE id=?", (sub["task_id"],))
        conn.commit(); conn.close()
        return True, "Reject। Slot ফেরত।"

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data.startswith("c_approve_") or data.startswith("c_reject_"):
        parts = data.split("_")
        action = "approve" if parts[1] == "approve" else "reject"
        sub_id = int(parts[2])
        ok, msg = do_review_submission(sub_id, action, uid)
        try:
            if query.message.caption:
                await query.edit_message_caption(caption=(query.message.caption or "") + f"\n\n→ {msg}", reply_markup=None)
            else:
                await query.edit_message_text((query.message.text or "") + f"\n\n→ {msg}", reply_markup=None)
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
        return

    if uid not in ADMIN_IDS:
        await query.edit_message_text("Admin নন।"); return
    conn = get_db(); c = conn.cursor()
    if data.startswith("approve_task_"):
        tid = int(data.split("_")[2])
        c.execute("UPDATE tasks SET status='approved' WHERE id=?", (tid,)); conn.commit()
        await query.edit_message_text(f"Task #{tid} Approved")
    elif data.startswith("reject_task_"):
        tid = int(data.split("_")[2])
        c.execute("SELECT * FROM tasks WHERE id=?", (tid,)); t = c.fetchone()
        if t and t["status"]=="pending":
            refund = t["price"] * t["total_slots"]
            c.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?", (refund, t["creator_id"]))
            c.execute("UPDATE tasks SET status='rejected' WHERE id=?", (tid,)); conn.commit()
            await query.edit_message_text(f"Rejected. ৳{refund} ফেরত")
        else: await query.edit_message_text("Already processed")
    elif data.startswith("approve_dep_"):
        did = int(data.split("_")[2])
        c.execute("SELECT * FROM deposits WHERE id=?", (did,)); d = c.fetchone()
        if d and d["status"]=="pending":
            c.execute("UPDATE deposits SET status='approved' WHERE id=?", (did,))
            c.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?", (d["amount"], d["user_id"])); conn.commit()
            await query.edit_message_text(f"Deposit Approved ৳{d['amount']}")
        else: await query.edit_message_text("Already processed")
    elif data.startswith("reject_dep_"):
        did = int(data.split("_")[2])
        c.execute("UPDATE deposits SET status='rejected' WHERE id=?", (did,)); conn.commit()
        await query.edit_message_text("Deposit Rejected")
    elif data.startswith("approve_wd_"):
        wid = int(data.split("_")[2])
        c.execute("UPDATE withdraws SET status='approved' WHERE id=?", (wid,)); conn.commit()
        await query.edit_message_text("Withdraw Approved")
    elif data.startswith("reject_wd_"):
        wid = int(data.split("_")[2])
        c.execute("SELECT * FROM withdraws WHERE id=?", (wid,)); w = c.fetchone()
        if w and w["status"]=="pending":
            c.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?", (w["amount"], w["user_id"]))
            c.execute("UPDATE withdraws SET status='rejected' WHERE id=?", (wid,)); conn.commit()
            await query.edit_message_text("Withdraw Rejected, টাকা ফেরত")
        else: await query.edit_message_text("Already processed")
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
        get_or_create_user(user_id); user = get_user(user_id)
    pending = get_pending_earn(user_id)
    return jsonify({
        "telegram_id": user["telegram_id"],
        "full_name": user["full_name"],
        "balance": user["balance"],
        "pending_balance": pending,
        "is_admin": bool(user["is_admin"])
    })

@app.route("/api/my_work/<int:user_id>")
def api_my_work(user_id):
    conn = get_db(); c = conn.cursor()
    c.execute("""SELECT s.id as sub_id, s.status, s.proof_text, s.created_at,
               t.title, t.price
               FROM submissions s JOIN tasks t ON s.task_id=t.id
               WHERE s.worker_id=?
               ORDER BY s.id DESC LIMIT 50""", (user_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route("/api/history/<int:user_id>")
def api_history(user_id):
    conn = get_db(); c = conn.cursor()
    items = []
    c.execute("SELECT id, amount, method, trx_id, status, created_at FROM deposits WHERE user_id=? ORDER BY id DESC LIMIT 30", (user_id,))
    for r in c.fetchall():
        items.append({"type": "deposit", "amount": r["amount"], "detail": f"{r['method']} {r['trx_id']}", "status": r["status"], "created_at": r["created_at"]})
    c.execute("SELECT id, amount, method, number, status, created_at FROM withdraws WHERE user_id=? ORDER BY id DESC LIMIT 30", (user_id,))
    for r in c.fetchall():
        items.append({"type": "withdraw", "amount": r["amount"], "detail": f"{r['method']} {r['number']}", "status": r["status"], "created_at": r["created_at"]})
    c.execute("""SELECT s.status, s.created_at, t.title, t.price
               FROM submissions s JOIN tasks t ON s.task_id=t.id
               WHERE s.worker_id=? ORDER BY s.id DESC LIMIT 30""", (user_id,))
    for r in c.fetchall():
        items.append({"type": "task", "amount": r["price"], "detail": r["title"], "status": r["status"], "created_at": r["created_at"]})
    conn.close()
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return jsonify(items[:50])

@app.route("/api/tasks")
def api_tasks():
    conn = get_db(); c = conn.cursor()
    c.execute("""SELECT t.id, t.title, t.description, t.price, t.total_slots, t.remaining_slots,
               t.require_screenshot, t.example_text, t.task_link, t.creator_id, u.full_name as creator_name
               FROM tasks t JOIN users u ON t.creator_id=u.telegram_id
               WHERE t.status='approved' AND t.remaining_slots>0 ORDER BY t.id DESC""")
    tasks = [dict(r) for r in c.fetchall()]; conn.close()
    return jsonify(tasks)

@app.route("/api/task/<int:task_id>")
def api_task_detail(task_id):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT t.*, u.full_name as creator_name FROM tasks t JOIN users u ON t.creator_id=u.telegram_id WHERE t.id=? AND t.status='approved'", (task_id,))
    task = c.fetchone(); conn.close()
    if not task: return jsonify({"error": "Task পাওয়া যায়নি"}), 404
    d = dict(task)
    if d.get("task_link"):
        d["task_link"] = normalize_url(d["task_link"])
    return jsonify(d)

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
    task_link = normalize_url(data.get("task_link", ""))
    example_image = data.get("example_image", "")
    if not title or not description or price <= 0 or slots <= 0:
        return jsonify({"error": "সব ঘর পূরণ করুন"}), 400
    if example_image and len(example_image) > MAX_MEDIA:
        return jsonify({"error": "Example ছবি অনেক বড় — ছোট করুন"}), 400
    user = get_user(user_id) or get_or_create_user(user_id)
    user = get_user(user_id)
    required = price * slots
    if user["balance"] < required:
        return jsonify({"error": f"অপর্যাপ্ত ব্যালেন্স! ৳{required:.0f} লাগবে"}), 400
    update_balance(user_id, -required)
    conn = get_db(); c = conn.cursor()
    c.execute("""INSERT INTO tasks
        (creator_id,title,description,price,total_slots,remaining_slots,require_screenshot,example_text,task_link,example_image,status,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,'pending',?)""",
        (user_id, title, description, price, slots, slots, require_screenshot, example_text, task_link, example_image, datetime.now().isoformat()))
    conn.commit(); tid = c.lastrowid; conn.close()
    return jsonify({"success": True, "task_id": tid, "message": f"Task সাবমিট। ৳{required:.0f} কেটে রাখা হয়েছে।"})

@app.route("/api/submit_proof", methods=["POST"])
def api_submit_proof():
    data = request.json
    user_id = data.get("user_id")
    task_id = data.get("task_id")
    proof_text = data.get("proof_text", "").strip()
    proof_image = data.get("proof_image", "")
    if not user_id or not task_id:
        return jsonify({"error": "Invalid"}), 400
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE id=? AND status='approved' AND remaining_slots>0", (task_id,))
    task = c.fetchone()
    if not task:
        conn.close(); return jsonify({"error": "Task নেই বা স্লট শেষ"}), 400
    if task["creator_id"] == user_id:
        conn.close(); return jsonify({"error": "নিজের Task নিজে Complete করতে পারবেন না"}), 400
    if task["require_screenshot"] and not proof_image:
        conn.close(); return jsonify({"error": "Screenshot/Video দিতে হবে"}), 400
    if not proof_text and not proof_image:
        conn.close(); return jsonify({"error": "প্রুফ দিন"}), 400
    c.execute("SELECT id FROM submissions WHERE task_id=? AND worker_id=? AND status!='rejected'", (task_id, user_id))
    if c.fetchone():
        conn.close(); return jsonify({"error": "ইতিমধ্যে সাবমিট করেছেন"}), 400
    if proof_image and len(proof_image) > MAX_MEDIA:
        conn.close(); return jsonify({"error": "ফাইল অনেক বড় — ছোট SS/ভিডিও দিন"}), 400
    c.execute("INSERT INTO submissions (task_id,worker_id,proof_text,proof_image,status,created_at) VALUES (?,?,?,?,'pending',?)",
              (task_id, user_id, proof_text, proof_image, datetime.now().isoformat()))
    c.execute("UPDATE tasks SET remaining_slots=remaining_slots-1 WHERE id=?", (task_id,))
    sub_id = c.lastrowid
    conn.commit()
    worker = get_user(user_id)
    worker_name = (worker.get("full_name") if worker else None) or str(user_id)
    creator_id = task["creator_id"]
    title = task["title"]
    price = task["price"]
    conn.close()
    try:
        run_async(send_proof_to_creator(creator_id, worker_name, title, price, proof_text, proof_image, sub_id))
    except Exception as e:
        print("notify creator failed:", e)
    return jsonify({"success": True, "message": "প্রুফ সাবমিট। Creator Telegram-এ দেখতে পাবে।"})

@app.route("/api/my_reviews/<int:user_id>")
def api_my_reviews(user_id):
    conn = get_db(); c = conn.cursor()
    c.execute("""SELECT s.id as sub_id, s.proof_text, s.proof_image, s.status, s.created_at,
               t.id as task_id, t.title, t.price, u.full_name as worker_name, u.telegram_id as worker_id
               FROM submissions s
               JOIN tasks t ON s.task_id = t.id
               JOIN users u ON s.worker_id = u.telegram_id
               WHERE t.creator_id = ? AND s.status = 'pending'
               ORDER BY s.id DESC""", (user_id,))
    rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        r["has_image"] = bool(r.get("proof_image"))
        media = r.get("proof_image") or ""
        r["is_video"] = media.startswith("data:video")
    conn.close()
    return jsonify(rows)

@app.route("/api/review_submission", methods=["POST"])
def api_review_submission():
    data = request.json
    user_id = data.get("user_id")
    sub_id = data.get("sub_id")
    action = data.get("action")
    if action not in ("approve", "reject") or not user_id or not sub_id:
        return jsonify({"error": "Invalid"}), 400
    ok, msg = do_review_submission(int(sub_id), action, int(user_id))
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"success": True, "message": msg})

@app.route("/api/deposit", methods=["POST"])
def api_deposit():
    data = request.json
    user_id, amount = data.get("user_id"), float(data.get("amount", 0))
    method, trx_id = data.get("method", ""), data.get("trx_id", "").strip()
    if amount <= 0 or not trx_id or method not in ("bkash", "nagad"):
        return jsonify({"error": "Invalid"}), 400
    get_or_create_user(user_id)
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO deposits (user_id,amount,method,trx_id,status,created_at) VALUES (?,?,?,?,'pending',?)",
              (user_id, amount, method, trx_id, datetime.now().isoformat()))
    conn.commit(); conn.close()
    return jsonify({"success": True, "message": "Deposit সাবমিট হয়েছে।"})

@app.route("/api/withdraw", methods=["POST"])
def api_withdraw():
    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("amount", 0))
    method, number = data.get("method", ""), data.get("number", "").strip()
    user = get_user(user_id) or get_or_create_user(user_id)
    user = get_user(user_id)
    if amount <= 0 or amount > user["balance"]:
        return jsonify({"error": "অপর্যাপ্ত ব্যালেন্স"}), 400
    if method not in ("bkash", "nagad") or not number:
        return jsonify({"error": "Invalid"}), 400
    update_balance(user_id, -amount)
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO withdraws (user_id,amount,method,number,status,created_at) VALUES (?,?,?,?,'pending',?)",
              (user_id, amount, method, number, datetime.now().isoformat()))
    conn.commit(); conn.close()
    return jsonify({"success": True, "message": "Withdraw সাবমিট হয়েছে।"})

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        loop.run_until_complete(application.process_update(update)); loop.close()
        return "ok", 200
    except Exception as e:
        print("Webhook Error:", e); return "error", 500

async def setup_webhook():
    if APP_URL:
        await application.bot.set_webhook(url=f"{APP_URL}/webhook")

def main():
    init_db()
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(setup_webhook())
    print(f"Port {PORT} | Admins {ADMIN_IDS} | DB {DB_NAME}")
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
