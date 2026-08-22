import logging
import sqlite3
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

# ================== CONFIG ==================
BOT_TOKEN = "এখানে_তোমার_বট_টোকেন_দাও"
ADMIN_ID = 5851334722

BKASH_NUMBER = "01600170756"
NAGAD_NUMBER = "01727332914"
BINANCE_PAY = "755928565"

# Conversation states
(DEPOSIT_METHOD, DEPOSIT_AMOUNT, DEPOSIT_TRX,
 WITHDRAW_AMOUNT, WITHDRAW_METHOD, WITHDRAW_NUMBER,
 POST_TITLE, POST_DESC, POST_REWARD, POST_MAX, POST_PROOF_TYPE,
 SUBMIT_PROOF_TEXT) = range(12)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== DATABASE ==================
def init_db():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 0,
        joined_at TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        method TEXT,
        amount REAL,
        trx_id TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS withdraws (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        method TEXT,
        amount REAL,
        number TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        poster_id INTEGER,
        title TEXT,
        description TEXT,
        reward REAL,
        max_workers INTEGER,
        current_workers INTEGER DEFAULT 0,
        proof_type TEXT,
        status TEXT DEFAULT 'open',
        created_at TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        worker_id INTEGER,
        proof_text TEXT,
        proof_file_id TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT
    )""")
    
    conn.commit()
    conn.close()

def get_user(user_id, username=None):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (user_id, username, balance, joined_at) VALUES (?, ?, 0, ?)",
                  (user_id, username, datetime.now().isoformat()))
        conn.commit()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = c.fetchone()
    conn.close()
    return user

def update_balance(user_id, amount):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# ================== KEYBOARDS ==================
def main_menu_keyboard():
    keyboard = [
        ["📋 টাস্ক দেখুন", "➕ টাস্ক পোস্ট করুন"],
        ["💰 ডিপোজিট", "💸 উইথড্র"],
        ["👤 আমার অ্যাকাউন্ট", "📊 আমার টাস্ক"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def admin_menu_keyboard():
    keyboard = [
        ["⏳ Pending Deposit", "⏳ Pending Withdraw"],
        ["🔙 মেইন মেনু"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id, user.username)
    
    text = f"""স্বাগতম {user.first_name}!

এই বটে আপনি:
• টাস্ক পোস্ট করতে পারবেন
• টাস্ক করে টাকা আয় করতে পারবেন
• bKash / Nagad / Binance দিয়ে ডিপোজিট করতে পারবেন

নিচের মেনু থেকে বেছে নিন:"""
    
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())

# ================== ACCOUNT ==================
async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    text = f"""👤 **আমার অ্যাকাউন্ট**

🆔 User ID: `{user[0]}`
💰 ব্যালেন্স: **{user[2]:.2f} টাকা**
📅 জয়েন: {user[3][:10]}"""
    await update.message.reply_text(text, parse_mode="Markdown")

# ================== DEPOSIT ==================
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("bKash", callback_data="dep_bkash")],
        [InlineKeyboardButton("Nagad", callback_data="dep_nagad")],
        [InlineKeyboardButton("Binance Pay", callback_data="dep_binance")]
    ]
    await update.message.reply_text("ডিপোজিট মেথড সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(keyboard))
    return DEPOSIT_METHOD

async def deposit_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split("_")[1]
    context.user_data["dep_method"] = method
    await query.edit_message_text(f"আপনি **{method.upper()}** সিলেক্ট করেছেন।\n\nকত টাকা ডিপোজিট করবেন? শুধু সংখ্যা লিখুন:")
    return DEPOSIT_AMOUNT

async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        if amount < 10:
            await update.message.reply_text("সর্বনিম্ন ১০ টাকা ডিপোজিট করতে হবে। আবার লিখুন:")
            return DEPOSIT_AMOUNT
        context.user_data["dep_amount"] = amount
        method = context.user_data["dep_method"]
        
        if method == "bkash":
            number = BKASH_NUMBER
        elif method == "nagad":
            number = NAGAD_NUMBER
        else:
            number = BINANCE_PAY
            
        text = f"""অনুগ্রহ করে **{amount} টাকা** পাঠান:

📌 মেথড: {method.upper()}
📌 নাম্বার/ID: `{number}`

টাকা পাঠানোর পর **Transaction ID** এখানে পাঠান:"""
        await update.message.reply_text(text, parse_mode="Markdown")
        return DEPOSIT_TRX
    except:
        await update.message.reply_text("সঠিক সংখ্যা লিখুন:")
        return DEPOSIT_AMOUNT

async def deposit_trx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trx = update.message.text.strip()
    user_id = update.effective_user.id
    method = context.user_data["dep_method"]
    amount = context.user_data["dep_amount"]
    
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("INSERT INTO deposits (user_id, method, amount, trx_id, created_at) VALUES (?, ?, ?, ?, ?)",
              (user_id, method, amount, trx, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    # Admin কে নোটিফিকেশন
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"🔔 নতুন ডিপোজিট রিকোয়েস্ট!\n\nUser: {user_id}\nMethod: {method}\nAmount: {amount}\nTrxID: {trx}\n\n/pending_deposits দিয়ে চেক করুন"
        )
    except:
        pass
    
    await update.message.reply_text(
        "✅ আপনার ডিপোজিট রিকোয়েস্ট পেন্ডিং-এ আছে। অ্যাডমিন চেক করে Approve করলে ব্যালেন্স যোগ হবে।",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

# ================== WITHDRAW ==================
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user[2] < 50:
        await update.message.reply_text("উইথড্র করতে হলে কমপক্ষে ৫০ টাকা ব্যালেন্স থাকতে হবে।")
        return ConversationHandler.END
    
    await update.message.reply_text(f"আপনার ব্যালেন্স: {user[2]:.2f} টাকা\n\nকত টাকা উইথড্র করবেন?")
    return WITHDRAW_AMOUNT

async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        user = get_user(update.effective_user.id)
        if amount > user[2]:
            await update.message.reply_text("আপনার কাছে এত টাকা নেই। আবার লিখুন:")
            return WITHDRAW_AMOUNT
        if amount < 50:
            await update.message.reply_text("সর্বনিম্ন ৫০ টাকা উইথড্র করা যাবে।")
            return WITHDRAW_AMOUNT
        
        context.user_data["wd_amount"] = amount
        keyboard = [
            [InlineKeyboardButton("bKash", callback_data="wd_bkash")],
            [InlineKeyboardButton("Nagad", callback_data="wd_nagad")],
            [InlineKeyboardButton("Binance", callback_data="wd_binance")]
        ]
        await update.message.reply_text("কোন মেথডে টাকা নিবেন?", reply_markup=InlineKeyboardMarkup(keyboard))
        return WITHDRAW_METHOD
    except:
        await update.message.reply_text("সঠিক সংখ্যা লিখুন:")
        return WITHDRAW_AMOUNT

async def withdraw_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split("_")[1]
    context.user_data["wd_method"] = method
    await query.edit_message_text(f"{method.upper()} নাম্বার/ID লিখুন:")
    return WITHDRAW_NUMBER

async def withdraw_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    number = update.message.text.strip()
    user_id = update.effective_user.id
    amount = context.user_data["wd_amount"]
    method = context.user_data["wd_method"]
    
    # ব্যালেন্স কেটে রাখি
    update_balance(user_id, -amount)
    
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("INSERT INTO withdraws (user_id, method, amount, number, created_at) VALUES (?, ?, ?, ?, ?)",
              (user_id, method, amount, number, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"🔔 নতুন উইথড্র রিকোয়েস্ট!\n\nUser: {user_id}\nMethod: {method}\nAmount: {amount}\nNumber: {number}"
        )
    except:
        pass
    
    await update.message.reply_text(
        "✅ উইথড্র রিকোয়েস্ট পেন্ডিং-এ আছে। অ্যাডমিন চেক করে টাকা পাঠাবে।",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

# ================== POST TASK ==================
async def post_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user[2] < 20:
        await update.message.reply_text("টাস্ক পোস্ট করতে হলে কমপক্ষে ২০ টাকা ব্যালেন্স থাকতে হবে।")
        return ConversationHandler.END
    await update.message.reply_text("টাস্কের **শিরোনাম** লিখুন:")
    return POST_TITLE

async def post_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["task_title"] = update.message.text
    await update.message.reply_text("টাস্কের **বিস্তারিত বর্ণনা** লিখুন:")
    return POST_DESC

async def post_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["task_desc"] = update.message.text
    await update.message.reply_text("প্রতিজনকে কত টাকা দিবেন? (শুধু সংখ্যা):")
    return POST_REWARD

async def post_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        reward = float(update.message.text)
        context.user_data["task_reward"] = reward
        await update.message.reply_text("কতজন ইউজার এই টাস্ক করতে পারবে?")
        return POST_MAX
    except:
        await update.message.reply_text("সঠিক সংখ্যা লিখুন:")
        return POST_REWARD

async def post_max(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        max_w = int(update.message.text)
        context.user_data["task_max"] = max_w
        total = context.user_data["task_reward"] * max_w
        user = get_user(update.effective_user.id)
        
        if user[2] < total:
            await update.message.reply_text(f"আপনার কাছে পর্যাপ্ত ব্যালেন্স নেই। প্রয়োজন: {total} টাকা")
            return ConversationHandler.END
        
        keyboard = [
            [InlineKeyboardButton("শুধু টেক্সট", callback_data="proof_text")],
            [InlineKeyboardButton("টেক্সট + স্ক্রিনশট", callback_data="proof_both")]
        ]
        await update.message.reply_text("প্রুফ কী লাগবে?", reply_markup=InlineKeyboardMarkup(keyboard))
        return POST_PROOF_TYPE
    except:
        await update.message.reply_text("সঠিক সংখ্যা লিখুন:")
        return POST_MAX

async def post_proof_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    proof = query.data.split("_")[1]
    
    title = context.user_data["task_title"]
    desc = context.user_data["task_desc"]
    reward = context.user_data["task_reward"]
    max_w = context.user_data["task_max"]
    total = reward * max_w
    user_id = update.effective_user.id
    
    # ব্যালেন্স কেটে নাও
    update_balance(user_id, -total)
    
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("""INSERT INTO tasks (poster_id, title, description, reward, max_workers, proof_type, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
              (user_id, title, desc, reward, max_w, proof, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    await query.edit_message_text(f"✅ টাস্ক সফলভাবে পোস্ট হয়েছে!\nমোট {total} টাকা কেটে নেওয়া হয়েছে।")
    await context.bot.send_message(user_id, "মেনুতে ফিরে যেতে নিচের বাটন ব্যবহার করুন।", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# ================== BROWSE TASKS ==================
async def browse_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT id, title, reward, max_workers, current_workers FROM tasks WHERE status = 'open' AND current_workers < max_workers ORDER BY id DESC LIMIT 10")
    tasks = c.fetchall()
    conn.close()
    
    if not tasks:
        await update.message.reply_text("এখন কোনো ওপেন টাস্ক নেই।")
        return
    
    for t in tasks:
        text = f"""📌 **{t[1]}**
💰 রিওয়ার্ড: {t[2]} টাকা
👥 {t[4]}/{t[3]} জন নিয়েছে
🆔 টাস্ক আইডি: {t[0]}"""
        keyboard = [[InlineKeyboardButton("কাজটি নিন", callback_data=f"take_{t[0]}")]]
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def take_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split("_")[1])
    user_id = update.effective_user.id
    
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = c.fetchone()
    
    if not task or task[8] != "open" or task[6] >= task[5]:
        await query.edit_message_text("এই টাস্ক আর নেওয়া যাবে না।")
        conn.close()
        return
    
    # ইতিমধ্যে নিয়েছে কিনা চেক
    c.execute("SELECT id FROM submissions WHERE task_id = ? AND worker_id = ?", (task_id, user_id))
    if c.fetchone():
        await query.edit_message_text("আপনি ইতিমধ্যে এই টাস্ক নিয়েছেন।")
        conn.close()
        return
    
    context.user_data["current_task"] = task_id
    context.user_data["proof_type"] = task[7]
    
    text = f"""✅ আপনি টাস্কটি নিয়েছেন!

**{task[2]}**

{task[3]}

রিওয়ার্ড: {task[4]} টাকা

এখন কাজ করে প্রুফ পাঠান।"""
    await query.edit_message_text(text, parse_mode="Markdown")
    
    if task[7] == "text":
        await context.bot.send_message(user_id, "প্রুফ হিসেবে টেক্সট লিখুন:")
    else:
        await context.bot.send_message(user_id, "প্রথমে স্ক্রিনশট পাঠান, তারপর টেক্সট লিখুন:")
    
    conn.close()
    return SUBMIT_PROOF_TEXT

async def submit_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    task_id = context.user_data.get("current_task")
    
    if not task_id:
        await update.message.reply_text("কোনো টাস্ক সিলেক্ট করা নেই।")
        return ConversationHandler.END
    
    proof_text = update.message.text or ""
    file_id = None
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        await update.message.reply_text("স্ক্রিনশট পেয়েছি। এখন টেক্সট প্রুফ লিখুন (না থাকলে 'নাই' লিখুন):")
        context.user_data["temp_file_id"] = file_id
        return SUBMIT_PROOF_TEXT
    
    if "temp_file_id" in context.user_data:
        file_id = context.user_data.pop("temp_file_id")
    
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("INSERT INTO submissions (task_id, worker_id, proof_text, proof_file_id, created_at) VALUES (?, ?, ?, ?, ?)",
              (task_id, user_id, proof_text, file_id, datetime.now().isoformat()))
    c.execute("UPDATE tasks SET current_workers = current_workers + 1 WHERE id = ?", (task_id,))
    conn.commit()
    
    # পোস্টারকে নোটিফিকেশন
    c.execute("SELECT poster_id FROM tasks WHERE id = ?", (task_id,))
    poster = c.fetchone()[0]
    conn.close()
    
    try:
        await context.bot.send_message(poster, f"🔔 নতুন প্রুফ সাবমিট হয়েছে!\nটাস্ক ID: {task_id}\n/my_posted দিয়ে চেক করুন")
    except:
        pass
    
    await update.message.reply_text("✅ প্রুফ সাবমিট হয়েছে! টাস্ক পোস্টার Approve করলে টাকা পাবেন।", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# ================== MY POSTED TASKS (Approve/Reject) ==================
async def my_posted_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("""SELECT s.id, s.task_id, s.worker_id, s.proof_text, s.proof_file_id, t.title, t.reward
                 FROM submissions s
                 JOIN tasks t ON s.task_id = t.id
                 WHERE t.poster_id = ? AND s.status = 'pending'""", (user_id,))
    subs = c.fetchall()
    conn.close()
    
    if not subs:
        await update.message.reply_text("কোনো পেন্ডিং সাবমিশন নেই।")
        return
    
    for s in subs:
        text = f"""📌 টাস্ক: {s[5]}
👤 ওয়ার্কার: {s[2]}
💰 রিওয়ার্ড: {s[6]}
📝 প্রুফ: {s[3]}"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"appr_{s[0]}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"rej_{s[0]}")
            ]
        ]
        msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        if s[4]:
            await context.bot.send_photo(update.effective_chat.id, s[4])

async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, sub_id = query.data.split("_")
    sub_id = int(sub_id)
    
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT worker_id, task_id FROM submissions WHERE id = ?", (sub_id,))
    row = c.fetchone()
    if not row:
        await query.edit_message_text("সাবমিশন পাওয়া যায়নি।")
        conn.close()
        return
    
    worker_id, task_id = row
    c.execute("SELECT reward FROM tasks WHERE id = ?", (task_id,))
    reward = c.fetchone()[0]
    
    if action == "appr":
        c.execute("UPDATE submissions SET status = 'approved' WHERE id = ?", (sub_id,))
        update_balance(worker_id, reward)
        await query.edit_message_text("✅ Approve করা হয়েছে! টাকা ওয়ার্কারকে দেওয়া হয়েছে।")
        try:
            await context.bot.send_message(worker_id, f"🎉 আপনার প্রুফ Approve হয়েছে! {reward} টাকা পাওয়া গেছে।")
        except:
            pass
    else:
        c.execute("UPDATE submissions SET status = 'rejected' WHERE id = ?", (sub_id,))
        await query.edit_message_text("❌ Reject করা হয়েছে।")
        try:
            await context.bot.send_message(worker_id, "আপনার প্রুফ Reject করা হয়েছে।")
        except:
            pass
    
    conn.commit()
    conn.close()

# ================== ADMIN ==================
async def pending_deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT id, user_id, method, amount, trx_id FROM deposits WHERE status = 'pending'")
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        await update.message.reply_text("কোনো পেন্ডিং ডিপোজিট নেই।")
        return
    
    for r in rows:
        text = f"ID: {r[0]}\nUser: {r[1]}\nMethod: {r[2]}\nAmount: {r[3]}\nTrx: {r[4]}"
        keyboard = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"depok_{r[0]}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"deprej_{r[0]}")
        ]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_deposit_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    
    action, dep_id = query.data.split("_")
    dep_id = int(dep_id)
    
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT user_id, amount FROM deposits WHERE id = ?", (dep_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    
    user_id, amount = row
    if action == "depok":
        c.execute("UPDATE deposits SET status = 'approved' WHERE id = ?", (dep_id,))
        update_balance(user_id, amount)
        await query.edit_message_text("✅ ডিপোজিট Approve করা হয়েছে।")
        try:
            await context.bot.send_message(user_id, f"✅ আপনার {amount} টাকার ডিপোজিট Approve হয়েছে!")
        except:
            pass
    else:
        c.execute("UPDATE deposits SET status = 'rejected' WHERE id = ?", (dep_id,))
        await query.edit_message_text("❌ ডিপোজিট Reject করা হয়েছে।")
    
    conn.commit()
    conn.close()

# ================== CANCEL ==================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("বাতিল করা হয়েছে।", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# ================== MAIN ==================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Deposit Conversation
    dep_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("💰 ডিপোজিট"), deposit_start)],
        states={
            DEPOSIT_METHOD: [CallbackQueryHandler(deposit_method, pattern="^dep_")],
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
            DEPOSIT_TRX: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_trx)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Withdraw Conversation
    wd_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("💸 উইথড্র"), withdraw_start)],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_METHOD: [CallbackQueryHandler(withdraw_method, pattern="^wd_")],
            WITHDRAW_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_number)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Post Task Conversation
    post_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("➕ টাস্ক পোস্ট করুন"), post_task_start)],
        states={
            POST_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, post_title)],
            POST_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, post_desc)],
            POST_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, post_reward)],
            POST_MAX: [MessageHandler(filters.TEXT & ~filters.COMMAND, post_max)],
            POST_PROOF_TYPE: [CallbackQueryHandler(post_proof_type, pattern="^proof_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Submit Proof
    proof_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(take_task, pattern="^take_")],
        states={
            SUBMIT_PROOF_TEXT: [MessageHandler(filters.TEXT | filters.PHOTO, submit_proof)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("👤 আমার অ্যাকাউন্ট"), my_account))
    app.add_handler(MessageHandler(filters.Regex("📋 টাস্ক দেখুন"), browse_tasks))
    app.add_handler(MessageHandler(filters.Regex("📊 আমার টাস্ক"), my_posted_tasks))
    app.add_handler(CallbackQueryHandler(handle_approval, pattern="^(appr|rej)_"))
    app.add_handler(CommandHandler("pending_deposits", pending_deposits))
    app.add_handler(CallbackQueryHandler(admin_deposit_action, pattern="^(depok|deprej)_"))
    
    app.add_handler(dep_conv)
    app.add_handler(wd_conv)
    app.add_handler(post_conv)
    app.add_handler(proof_conv)
    
    print("বট চালু হয়েছে...")
    app.run_polling()

if __name__ == "__main__":
    main()
