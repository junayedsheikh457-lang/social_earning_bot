# bot.py
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ============= কনফিগারেশন =============
from config import *

# ============= লগিং =============
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============= ডেটাবেজ =============
DATA_FILE = "data.json"

def load_data():
    """ডেটা লোড করুন"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "users": {},
        "tasks": [],
        "deposits": [],
        "withdrawals": [],
        "proofs": [],
        "transactions": []
    }

def save_data():
    """ডেটা সেভ করুন"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

data = load_data()

# ============= হেল্পার ফাংশন =============
def get_user(user_id: str) -> Dict:
    """ইউজার ডেটা পান"""
    if user_id not in data["users"]:
        data["users"][user_id] = {
            "balance": 0.0,
            "username": "",
            "total_earned": 0.0,
            "total_spent": 0.0,
            "tasks_posted": [],
            "tasks_taken": [],
            "joined_date": datetime.now().isoformat()
        }
        save_data()
    return data["users"][user_id]

def format_balance(amount: float) -> str:
    """ব্যালেন্স ফরম্যাট করুন"""
    return f"{amount:.2f}"

def get_user_name(update: Update) -> str:
    """ইউজারের নাম পান"""
    user = update.effective_user
    return user.username or user.first_name or str(user.id)

def is_admin(user_id: int) -> bool:
    """অ্যাডমিন কিনা চেক করুন"""
    return user_id in ADMIN_IDS

# ============= কিবোর্ড =============
def main_keyboard():
    """মেইন মেনু কিবোর্ড"""
    keyboard = [
        [InlineKeyboardButton("🔍 টাস্ক খুঁজুন", callback_data="find_tasks")],
        [InlineKeyboardButton("📝 টাস্ক পোস্ট করুন", callback_data="post_task")],
        [InlineKeyboardButton("💰 ওয়ালেট", callback_data="wallet")],
        [InlineKeyboardButton("📋 আমার টাস্ক", callback_data="my_tasks")],
    ]
    return InlineKeyboardMarkup(keyboard)

def back_keyboard():
    """ব্যাক বাটন"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
    ])

# ============= মেইন মেনু =============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start কমান্ড"""
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    
    if update.effective_user.username:
        user["username"] = update.effective_user.username
        save_data()
    
    welcome_text = (
        f"🎉 **{BOT_NAME}** এ স্বাগতম!\n\n"
        f"👋 হ্যালো {get_user_name(update)}!\n"
        f"💰 আপনার ব্যালেন্স: **{format_balance(user['balance'])} USDT**\n\n"
        f"📌 **কী করতে পারবেন?**\n"
        f"✅ টাস্ক পোস্ট করুন ও পেমেন্ট দিন\n"
        f"✅ টাস্ক নিন ও পেমেন্ট পান\n"
        f"✅ ডিপোজিট/উইথড্র করুন\n\n"
        f"নিচের অপশন থেকে নির্বাচন করুন:"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None):
    """মেইন মেনু দেখান"""
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    
    menu_text = (
        f"🎉 **{BOT_NAME}**\n\n"
        f"💰 ব্যালেন্স: **{format_balance(user['balance'])} USDT**\n\n"
        f"নিচের অপশন থেকে নির্বাচন করুন:"
    )
    
    if text:
        menu_text = text + "\n\n" + menu_text
    
    keyboard = main_keyboard()
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            menu_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        await update.callback_query.answer()
    else:
        await update.message.reply_text(
            menu_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

# ============= টাস্ক পোস্ট =============
async def post_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """টাস্ক পোস্ট করা শুরু করুন"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    
    if user["balance"] < 5:
        await query.edit_message_text(
            "❌ **পর্যাপ্ত ব্যালেন্স নেই!**\n\n"
            f"আপনার ব্যালেন্স: {format_balance(user['balance'])} USDT\n"
            "টাস্ক পোস্ট করতে নূন্যতম ৫ USDT থাকতে হবে।",
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
        return
    
    context.user_data["task_step"] = "title"
    await query.edit_message_text(
        "📝 **স্টেপ ১/৬: টাস্কের টাইটেল**\n\n"
        "আপনার টাস্কের একটি সংক্ষিপ্ত শিরোনাম লিখুন:\n"
        "যেমন: `Facebook পোস্ট লাইক দিন`\n\n"
        "Type /cancel to cancel",
        reply_markup=back_keyboard()
    )

async def handle_task_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """টাস্ক ইনপুট হ্যান্ডেল করুন"""
    if "task_step" not in context.user_data:
        return
    
    user_id = str(update.effective_user.id)
    text = update.message.text
    step = context.user_data["task_step"]
    
    if text.startswith("/cancel"):
        context.user_data.clear()
        await update.message.reply_text("❌ টাস্ক পোস্ট বাতিল করা হয়েছে।")
        await main_menu(update, context)
        return
    
    if step == "title":
        context.user_data["task_title"] = text
        context.user_data["task_step"] = "description"
        await update.message.reply_text(
            "📝 **স্টেপ ২/৬: টাস্কের বিবরণ**\n\n"
            "ইউজারদের কী করতে হবে তা বিস্তারিত লিখুন:\n"
            "যেমন: আমাদের ফেসবুক পোস্টে লাইক দিন ও কমেন্ট করুন"
        )
    
    elif step == "description":
        context.user_data["task_desc"] = text
        context.user_data["task_step"] = "instructions"
        await update.message.reply_text(
            "📋 **স্টেপ ৩/৬: নির্দেশনা**\n\n"
            "ইউজারদের কীভাবে টাস্ক করবেন তার ধাপগুলো লিখুন:\n"
            "যেমন:\n"
            "১. এই লিংকে যান: facebook.com/...\n"
            "২. পোস্টে লাইক দিন\n"
            "৩. কমেন্ট করুন 'Great!'"
        )
    
    elif step == "instructions":
        context.user_data["task_instructions"] = text
        context.user_data["task_step"] = "reward"
        await update.message.reply_text(
            "💰 **স্টেপ ৪/৬: প্রতি জনকে কত USDT দেবেন?**\n\n"
            "শুধু সংখ্যা লিখুন (দশমিক সহ):\n"
            "যেমন: `2.50`"
        )
    
    elif step == "reward":
        try:
            reward = float(text)
            if reward <= 0:
                raise ValueError
            context.user_data["task_reward"] = reward
            context.user_data["task_step"] = "slots"
            await update.message.reply_text(
                f"✅ প্রতি জনকে {reward} USDT\n\n"
                "👥 **স্টেপ ৫/৬: কয় জন টাস্ক নিতে পারবে?**\n\n"
                "মোট কয়জন ইউজার এই টাস্ক পাবে?\n"
                "যেমন: `10`"
            )
        except:
            await update.message.reply_text("❌ সঠিক সংখ্যা দিন (যেমন: 2.50)")
    
    elif step == "slots":
        try:
            total_slots = int(text)
            if total_slots <= 0:
                raise ValueError
            context.user_data["task_slots"] = total_slots
            context.user_data["task_step"] = "duration"
            await update.message.reply_text(
                f"✅ মোট স্লট: {total_slots}\n\n"
                "⏰ **স্টেপ ৬/৬: কত দিন টাস্ক থাকবে?**\n\n"
                "শুধু সংখ্যা লিখুন (দিনে):\n"
                "যেমন: `3` (৩ দিন)"
            )
        except:
            await update.message.reply_text("❌ সঠিক সংখ্যা দিন (যেমন: 10)")
    
    elif step == "duration":
        try:
            duration = int(text)
            if duration <= 0:
                raise ValueError
            
            title = context.user_data.get("task_title", "No Title")
            desc = context.user_data.get("task_desc", "No Description")
            instructions = context.user_data.get("task_instructions", "No Instructions")
            reward = context.user_data.get("task_reward", 0)
            total_slots = context.user_data.get("task_slots", 0)
            
            total_cost = reward * total_slots
            
            user = get_user(user_id)
            if user["balance"] < total_cost:
                await update.message.reply_text(
                    f"❌ **পর্যাপ্ত ব্যালেন্স নেই!**\n\n"
                    f"দরকার: {format_balance(total_cost)} USDT\n"
                    f"আপনার ব্যালেন্স: {format_balance(user['balance'])} USDT"
                )
                context.user_data.clear()
                return
            
            task = {
                "id": len(data["tasks"]) + 1,
                "title": title,
                "description": desc,
                "instructions": instructions,
                "reward_per_user": reward,
                "total_slots": total_slots,
                "completed_slots": 0,
                "duration_days": duration,
                "posted_by": user_id,
                "total_cost": total_cost,
                "status": "pending",
                "accepted_by": [],
                "created_at": datetime.now().isoformat(),
                "expiry_date": (datetime.now() + timedelta(days=duration)).isoformat()
            }
            
            user["balance"] -= total_cost
            user["total_spent"] += total_cost
            user["tasks_posted"].append(task["id"])
            
            data["tasks"].append(task)
            save_data()
            
            await notify_admin_task(update, context, task)
            
            context.user_data.clear()
            await update.message.reply_text(
                f"✅ **টাস্ক জমা দেওয়া হয়েছে!**\n\n"
                f"📌 {title}\n"
                f"💰 প্রতি জন: {reward} USDT\n"
                f"👥 মোট স্লট: {total_slots}\n"
                f"💵 মোট খরচ: {format_balance(total_cost)} USDT\n"
                f"⏰ মেয়াদ: {duration} দিন\n\n"
                f"⏳ অ্যাডমিন রিভিউ চলছে...\n"
                f"আপনাকে জানানো হবে।"
            )
            await main_menu(update, context)
            
        except Exception as e:
            await update.message.reply_text(f"❌ ত্রুটি: {str(e)}")

# ============= অ্যাডমিন নোটিফিকেশন =============
async def notify_admin_task(update: Update, context: ContextTypes.DEFAULT_TYPE, task: Dict):
    """অ্যাডমিনকে নতুন টাস্কের নোটিফিকেশন"""
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🆕 **নতুন টাস্ক রিভিউয়ের জন্য!**\n\n"
                    f"🆔 টাস্ক আইডি: #{task['id']}\n"
                    f"📌 {task['title']}\n"
                    f"📝 {task['description'][:100]}...\n"
                    f"💰 প্রতি জন: {task['reward_per_user']} USDT\n"
                    f"👥 স্লট: {task['total_slots']}\n"
                    f"💵 মোট খরচ: {format_balance(task['total_cost'])} USDT\n"
                    f"👤 পোস্টার: {task['posted_by']}\n\n"
                    f"ব্যবহার করুন:\n"
                    f"/approve_task {task['id']}\n"
                    f"/reject_task {task['id']} <কারণ>"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"অ্যাডমিন নোটিফিকেশন পাঠাতে ব্যর্থ: {e}")

# ============= অ্যাডমিন কমান্ড =============
async def approve_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """অ্যাডমিন টাস্ক অ্যাপ্রুভ করুন"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ আপন অ্যাডমিন নন!")
        return
    
    try:
        task_id = int(context.args[0])
        
        for task in data["tasks"]:
            if task["id"] == task_id and task["status"] == "pending":
                task["status"] = "active"
                task["expiry_date"] = (datetime.now() + timedelta(days=task["duration_days"])).isoformat()
                save_data()
                
                await context.bot.send_message(
                    chat_id=task["posted_by"],
                    text=(
                        f"✅ **আপনার টাস্ক অ্যাপ্রুভ হয়েছে!**\n\n"
                        f"📌 {task['title']}\n"
                        f"এখন থেকে ইউজাররা টাস্ক নিতে পারবে."
                    )
                )
                
                await update.message.reply_text(f"✅ টাস্ক #{task_id} অ্যাপ্রুভ হয়েছে!")
                return
        
        await update.message.reply_text(f"❌ টাস্ক #{task_id} পাওয়া যায়নি।")
    
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ ব্যবহার: /approve_task <task_id>")

async def reject_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """অ্যাডমিন টাস্ক রিজেক্ট করুন"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ আপন অ্যাডমিন নন!")
        return
    
    try:
        task_id = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "নির্দিষ্ট করা হয়নি"
        
        for task in data["tasks"]:
            if task["id"] == task_id and task["status"] == "pending":
                task["status"] = "rejected"
                
                user = get_user(task["posted_by"])
                user["balance"] += task["total_cost"]
                user["total_spent"] -= task["total_cost"]
                
                save_data()
                
                await context.bot.send_message(
                    chat_id=task["posted_by"],
                    text=(
                        f"❌ **আপনার টাস্ক রিজেক্ট হয়েছে!**\n\n"
                        f"📌 {task['title']}\n"
                        f"💵 {format_balance(task['total_cost'])} USDT ফেরত দেওয়া হয়েছে।\n\n"
                        f"কারণ: {reason}"
                    )
                )
                
                await update.message.reply_text(f"❌ টাস্ক #{task_id} রিজেক্ট করা হয়েছে।")
                return
        
        await update.message.reply_text(f"❌ টাস্ক #{task_id} পাওয়া যায়নি।")
    
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ ব্যবহার: /reject_task <task_id> <কারণ>")

# ============= টাস্ক খোঁজা =============
async def find_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """উপলব্ধ টাস্ক দেখান"""
    query = update.callback_query
    await query.answer()
    
    available_tasks = [
        t for t in data["tasks"] 
        if t["status"] == "active" 
        and len(t["accepted_by"]) < t["total_slots"]
        and datetime.now().isoformat() < t["expiry_date"]
    ]
    
    if not available_tasks:
        await query.edit_message_text(
            "📭 **কোন টাস্ক নেই**\n\n"
            "বর্তমানে কোনো টাস্ক পাওয়া যাচ্ছে না।",
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
        return
    
    text = "📋 **উপলব্ধ টাস্ক:**\n\n"
    keyboard = []
    
    for task in available_tasks[:10]:
        remaining = task["total_slots"] - len(task["accepted_by"])
        text += (
            f"📌 *{task['title']}*\n"
            f"   💰 {format_balance(task['reward_per_user'])} USDT/জন\n"
            f"   👥 বাকি: {remaining}/{task['total_slots']}\n"
            f"   📝 {task['description'][:50]}...\n\n"
        )
        keyboard.append([
            InlineKeyboardButton(f"✅ টাস্ক নিন #{task['id']}", callback_data=f"take_task_{task['id']}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ============= টাস্ক নেওয়া =============
async def take_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """টাস্ক নিন"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    task_id = int(query.data.split("_")[2])
    
    task = None
    for t in data["tasks"]:
        if t["id"] == task_id:
            task = t
            break
    
    if not task:
        await query.edit_message_text("❌ টাস্ক পাওয়া যায়নি!", reply_markup=back_keyboard())
        return
    
    if user_id in task["accepted_by"]:
        await query.edit_message_text("⚠️ আপনি ইতিমধ্যে এই টাস্ক নিয়েছেন!", reply_markup=back_keyboard())
        return
    
    if len(task["accepted_by"]) >= task["total_slots"]:
        await query.edit_message_text("❌ সব স্লট পূর্ণ!", reply_markup=back_keyboard())
        return
    
    if datetime.now().isoformat() > task["expiry_date"]:
        await query.edit_message_text("❌ মেয়াদ শেষ!", reply_markup=back_keyboard())
        return
    
    task["accepted_by"].append(user_id)
    user = get_user(user_id)
    user["tasks_taken"].append(task_id)
    save_data()
    
    await query.edit_message_text(
        f"✅ **টাস্ক নেওয়া হয়েছে!**\n\n"
        f"📌 {task['title']}\n"
        f"💰 রিওয়ার্ড: {format_balance(task['reward_per_user'])} USDT\n\n"
        f"📋 **নির্দেশনা:**\n{task['instructions']}\n\n"
        f"টাস্ক শেষ করে প্রুফ দিন:\n"
        f"/submit_proof {task_id} <আপনার প্রুফ>",
        reply_markup=back_keyboard()
    )

# ============= প্রুফ সাবমিট =============
async def submit_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """প্রুফ জমা দিন"""
    user_id = str(update.effective_user.id)
    
    try:
        task_id = int(context.args[0])
        proof_text = " ".join(context.args[1:]) if len(context.args) > 1 else ""
        
        if not proof_text:
            await update.message.reply_text(
                "⚠️ প্রুফ লিখুন!\nব্যবহার: /submit_proof <task_id> <প্রুফ>"
            )
            return
        
        task = None
        for t in data["tasks"]:
            if t["id"] == task_id:
                task = t
                break
        
        if not task:
            await update.message.reply_text("❌ টাস্ক পাওয়া যায়নি!")
            return
        
        if user_id not in task["accepted_by"]:
            await update.message.reply_text("❌ আপনি এই টাস্ক নেননি!")
            return
        
        for proof in data["proofs"]:
            if proof["task_id"] == task_id and proof["user_id"] == user_id:
                await update.message.reply_text("⚠️ আপনি ইতিমধ্যে প্রুফ দিয়েছেন!")
                return
        
        proof = {
            "id": len(data["proofs"]) + 1,
            "task_id": task_id,
            "user_id": user_id,
            "proof_text": proof_text,
            "status": "pending",
            "submitted_at": datetime.now().isoformat(),
            "reward_amount": task["reward_per_user"]
        }
        data["proofs"].append(proof)
        save_data()
        
        creator_id = task["posted_by"]
        await context.bot.send_message(
            chat_id=creator_id,
            text=(
                f"📨 **নতুন প্রুফ জমা পড়েছে!**\n\n"
                f"📌 টাস্ক: {task['title']} (#{task_id})\n"
                f"👤 ইউজার: {user_id}\n"
                f"📝 প্রুফ: {proof_text}\n"
                f"💰 রিওয়ার্ড: {format_balance(task['reward_per_user'])} USDT\n\n"
                f"/approve_proof {proof['id']}\n"
                f"/reject_proof {proof['id']} <কারণ>"
            )
        )
        
        await update.message.reply_text(
            f"✅ **প্রুফ জমা দেওয়া হয়েছে!**\n\n"
            f"টাস্ক #{task_id} এর প্রুফ পাঠানো হয়েছে।"
        )
        
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ ব্যবহার: /submit_proof <task_id> <প্রুফ>")

# ============= প্রুফ অ্যাপ্রুভ =============
async def approve_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """প্রুফ অ্যাপ্রুভ করুন"""
    user_id = str(update.effective_user.id)
    
    try:
        proof_id = int(context.args[0])
        
        proof = None
        for p in data["proofs"]:
            if p["id"] == proof_id:
                proof = p
                break
        
        if not proof:
            await update.message.reply_text("❌ প্রুফ পাওয়া যায়নি!")
            return
        
        if proof["status"] != "pending":
            await update.message.reply_text(f"⚠️ ইতিমধ্যে {proof['status']}!")
            return
        
        task = None
        for t in data["tasks"]:
            if t["id"] == proof["task_id"]:
                task = t
                break
        
        if not task:
            await update.message.reply_text("❌ টাস্ক পাওয়া যায়নি!")
            return
        
        if task["posted_by"] != user_id:
            await update.message.reply_text("❌ আপনি এই টাস্কের পোস্টার নন!")
            return
        
        proof["status"] = "approved"
        proof["reviewed_at"] = datetime.now().isoformat()
        proof["reviewed_by"] = user_id
        
        worker = get_user(proof["user_id"])
        worker["balance"] += proof["reward_amount"]
        worker["total_earned"] += proof["reward_amount"]
        
        task["completed_slots"] += 1
        
        transaction = {
            "id": len(data["transactions"]) + 1,
            "from_user": task["posted_by"],
            "to_user": proof["user_id"],
            "amount": proof["reward_amount"],
            "type": "task_payment",
            "task_id": task["id"],
            "status": "completed",
            "timestamp": datetime.now().isoformat()
        }
        data["transactions"].append(transaction)
        
        save_data()
        
        await context.bot.send_message(
            chat_id=proof["user_id"],
            text=(
                f"🎉 **অভিনন্দন! প্রুফ অ্যাপ্রুভ হয়েছে!**\n\n"
                f"📌 টাস্ক: {task['title']}\n"
                f"💰 পেয়েছেন: {format_balance(proof['reward_amount'])} USDT\n"
                f"💳 নতুন ব্যালেন্স: {format_balance(worker['balance'])} USDT"
            )
        )
        
        await update.message.reply_text(
            f"✅ **প্রুফ অ্যাপ্রুভ করা হয়েছে!**\n\n"
            f"ইউজারকে {format_balance(proof['reward_amount'])} USDT পেমেন্ট করা হয়েছে।"
        )
        
        if task["completed_slots"] >= task["total_slots"]:
            task["status"] = "completed"
            save_data()
            
            await context.bot.send_message(
                chat_id=task["posted_by"],
                text=(
                    f"🎉 **টাস্ক সম্পূর্ণ!**\n\n"
                    f"📌 {task['title']}\n"
                    f"সব {task['total_slots']}টি স্লট সম্পূর্ণ হয়েছে।"
                )
            )
        
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ ব্যবহার: /approve_proof <proof_id>")

async def reject_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """প্রুফ রিজেক্ট করুন"""
    user_id = str(update.effective_user.id)
    
    try:
        proof_id = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "নির্দিষ্ট করা হয়নি"
        
        proof = None
        for p in data["proofs"]:
            if p["id"] == proof_id:
                proof = p
                break
        
        if not proof:
            await update.message.reply_text("❌ প্রুফ পাওয়া যায়নি!")
            return
        
        if proof["status"] != "pending":
            await update.message.reply_text(f"⚠️ ইতিমধ্যে {proof['status']}!")
            return
        
        task = None
        for t in data["tasks"]:
            if t["id"] == proof["task_id"]:
                task = t
                break
        
        if not task:
            await update.message.reply_text("❌ টাস্ক পাওয়া যায়নি!")
            return
        
        if task["posted_by"] != user_id:
            await update.message.reply_text("❌ আপনি এই টাস্কের পোস্টার নন!")
            return
        
        proof["status"] = "rejected"
        proof["reviewed_at"] = datetime.now().isoformat()
        proof["reviewed_by"] = user_id
        proof["rejection_reason"] = reason
        
        save_data()
        
        await context.bot.send_message(
            chat_id=proof["user_id"],
            text=(
                f"❌ **প্রুফ রিজেক্ট হয়েছে!**\n\n"
                f"📌 টাস্ক: {task['title']}\n"
                f"কারণ: {reason}"
            )
        )
        
        await update.message.reply_text(f"❌ প্রুফ #{proof_id} রিজেক্ট করা হয়েছে।")
        
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ ব্যবহার: /reject_proof <proof_id> <কারণ>")

# ============= ওয়ালেট =============
async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ওয়ালেট দেখান"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    
    text = (
        f"💰 **আপনার ওয়ালেট**\n\n"
        f"📊 ব্যালেন্স: **{format_balance(user['balance'])} USDT**\n"
        f"💱 BDT: **{format_balance(user['balance'] * USDT_TO_BDT_RATE)} BDT**\n\n"
        f"📈 মোট আয়: {format_balance(user['total_earned'])} USDT\n"
        f"📉 মোট খরচ: {format_balance(user['total_spent'])} USDT\n\n"
        f"📌 1 USDT = {USDT_TO_BDT_RATE} BDT"
    )
    
    keyboard = [
        [InlineKeyboardButton("💰 ডিপোজিট", callback_data="deposit_menu")],
        [InlineKeyboardButton("💸 উইথড্র", callback_data="withdraw_menu")],
        [InlineKeyboardButton("📜 ট্রানজেকশন", callback_data="transaction_history")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ============= ডিপোজিট =============
async def deposit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ডিপোজিট অপশন"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🟢 bKash (BDT)", callback_data="deposit_bkash")],
        [InlineKeyboardButton("🔴 Nagad (BDT)", callback_data="deposit_nagad")],
        [InlineKeyboardButton("🔙 Back", callback_data="wallet")]
    ]
    
    await query.edit_message_text(
        "💰 **ডিপোজিট করুন**\n\n"
        "আপনি যেভাবে টাকা জমা দিতে চান সেটি সিলেক্ট করুন:\n\n"
        f"📌 1 USDT = {USDT_TO_BDT_RATE} BDT\n"
        f"⚠️ ন্যূনতম ডিপোজিট: {MIN_DEPOSIT_USDT} USDT",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def deposit_bkash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """bKash ডিপোজিট"""
    query = update.callback_query
    await query.answer()
    
    context.user_data["deposit_method"] = "bKash"
    context.user_data["deposit_step"] = "amount"
    
    await query.edit_message_text(
        f"💳 **bKash ডিপোজিট**\n\n"
        f"আমাদের bKash নম্বর: `{BKASH_NUMBER}`\n\n"
        f"আপনি কত USDT জমা দিতে চান?\n"
        f"(শুধু সংখ্যা লিখুন)\n\n"
        f"যেমন: `10` (={10 * USDT_TO_BDT_RATE} BDT)\n\n"
        f"⚠️ ন্যূনতম {MIN_DEPOSIT_USDT} USDT\n\n"
        f"Type /cancel to cancel",
        parse_mode="Markdown"
    )

async def deposit_nagad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nagad ডিপোজিট"""
    query = update.callback_query
    await query.answer()
    
    context.user_data["deposit_method"] = "Nagad"
    context.user_data["deposit_step"] = "amount"
    
    await query.edit_message_text(
        f"💳 **Nagad ডিপোজিট**\n\n"
        f"আমাদের Nagad নম্বর: `{NAGAD_NUMBER}`\n\n"
        f"আপনি কত USDT জমা দিতে চান?\n"
        f"(শুধু সংখ্যা লিখুন)\n\n"
        f"যেমন: `10` (={10 * USDT_TO_BDT_RATE} BDT)\n\n"
        f"⚠️ ন্যূনতম {MIN_DEPOSIT_USDT} USDT\n\n"
        f"Type /cancel to cancel",
        parse_mode="Markdown"
    )

async def handle_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ডিপোজিট ইনপুট হ্যান্ডেল"""
    if "deposit_step" not in context.user_data:
        return
    
    user_id = str(update.effective_user.id)
    text = update.message.text
    step = context.user_data["deposit_step"]
    method = context.user_data["deposit_method"]
    
    if text.startswith("/cancel"):
        context.user_data.clear()
        await update.message.reply_text("❌ ডিপোজিট বাতিল করা হয়েছে।")
        await main_menu(update, context)
        return
    
    if step == "amount":
        try:
            amount = float(text)
            if amount < MIN_DEPOSIT_USDT:
                await update.message.reply_text(f"⚠️ ন্যূনতম {MIN_DEPOSIT_USDT} USDT।")
                return
            
            context.user_data["deposit_amount"] = amount
            context.user_data["deposit_step"] = "reference"
            
            bdt_amount = amount * USDT_TO_BDT_RATE
            
            await update.message.reply_text(
                f"✅ {amount} USDT = {bdt_amount} BDT\n\n"
                f"📲 **{method}** নম্বরে টাকা পাঠান:\n"
                f"📞 **{method.upper()}:** `{BKASH_NUMBER if method == 'bKash' else NAGAD_NUMBER}`\n\n"
                f"টাকা পাঠানোর পর রেফারেন্স লিখুন:\n"
                f"যেমন: `8C7V9A2B`\n\n"
                f"⚠️ রেফারেন্স ছাড়া ভেরিফাই করা সম্ভব নয়!",
                parse_mode="Markdown"
            )
            
        except ValueError:
            await update.message.reply_text("❌ সঠিক সংখ্যা দিন")
    
    elif step == "reference":
        reference = text.strip()
        
        deposit = {
            "id": f"dep_{len(data['deposits']) + 1}",
            "user_id": user_id,
            "amount": context.user_data["deposit_amount"],
            "amount_bdt": context.user_data["deposit_amount"] * USDT_TO_BDT_RATE,
            "method": method,
            "reference": reference,
            "status": "pending",
            "submitted_at": datetime.now().isoformat(),
            "approved_at": None,
            "admin_notes": ""
        }
        
        data["deposits"].append(deposit)
        save_data()
        
        for admin_id in ADMIN_IDS:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"💰 **নতুন ডিপোজিট!**\n\n"
                    f"🆔 {deposit['id']}\n"
                    f"👤 ইউজার: {user_id}\n"
                    f"💵 {deposit['amount']} USDT ({deposit['amount_bdt']} BDT)\n"
                    f"📲 {method}: {reference}\n\n"
                    f"/approve_deposit {deposit['id']}\n"
                    f"/reject_deposit {deposit['id']} <কারণ>"
                )
            )
        
        context.user_data.clear()
        await update.message.reply_text(
            f"✅ **ডিপোজিট রিকোয়েস্ট জমা হয়েছে!**\n\n"
            f"💵 {deposit['amount']} USDT ({deposit['amount_bdt']} BDT)\n"
            f"📲 {method}: {reference}\n\n"
            f"⏳ অ্যাডমিন ভেরিফাই করছে..."
        )
        await main_menu(update, context)

# ============= উইথড্র =============
async def withdraw_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """উইথড্র অপশন"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    
    keyboard = [
        [InlineKeyboardButton("🟢 bKash (BDT)", callback_data="withdraw_bkash")],
        [InlineKeyboardButton("🔴 Nagad (BDT)", callback_data="withdraw_nagad")],
        [InlineKeyboardButton("🔙 Back", callback_data="wallet")]
    ]
    
    await query.edit_message_text(
        f"💰 **উইথড্র করুন**\n\n"
        f"আপনার ব্যালেন্স: **{format_balance(user['balance'])} USDT**\n\n"
        f"⚠️ ন্যূনতম: {MIN_WITHDRAW_USDT} USDT\n"
        f"💸 চার্জ: {WITHDRAW_FEE_USDT} USDT",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def withdraw_bkash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """bKash উইথড্র"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    
    if user["balance"] < MIN_WITHDRAW_USDT:
        await query.edit_message_text(
            f"❌ ব্যালেন্স কম! ন্যূনতম {MIN_WITHDRAW_USDT} USDT",
            reply_markup=back_keyboard()
        )
        return
    
    context.user_data["withdraw_method"] = "bKash"
    context.user_data["withdraw_step"] = "amount"
    
    await query.edit_message_text(
        f"💳 **bKash উইথড্র**\n\n"
        f"আপনার ব্যালেন্স: {format_balance(user['balance'])} USDT\n\n"
        f"কত USDT তুলতে চান?\n"
        f"(শুধু সংখ্যা)\n\n"
        f"যেমন: `10`\n\n"
        f"BDT পাবেন: {(10 - WITHDRAW_FEE_USDT) * USDT_TO_BDT_RATE} BDT\n\n"
        f"Type /cancel to cancel",
        parse_mode="Markdown"
    )

async def handle_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """উইথড্র ইনপুট হ্যান্ডেল"""
    if "withdraw_step" not in context.user_data:
        return
    
    user_id = str(update.effective_user.id)
    text = update.message.text
    step = context.user_data["withdraw_step"]
    method = context.user_data["withdraw_method"]
    
    if text.startswith("/cancel"):
        context.user_data.clear()
        await update.message.reply_text("❌ উইথড্র বাতিল করা হয়েছে।")
        await main_menu(update, context)
        return
    
    if step == "amount":
        try:
            amount = float(text)
            user = get_user(user_id)
            
            if amount < MIN_WITHDRAW_USDT:
                await update.message.reply_text(f"⚠️ ন্যূনতম {MIN_WITHDRAW_USDT} USDT")
                return
            
            if amount > user["balance"]:
                await update.message.reply_text(f"❌ পর্যাপ্ত ব্যালেন্স নেই!")
                return
            
            context.user_data["withdraw_amount"] = amount
            context.user_data["withdraw_step"] = "account"
            
            await update.message.reply_text(
                f"✅ {amount} USDT = {(amount - WITHDRAW_FEE_USDT) * USDT_TO_BDT_RATE} BDT\n"
                f"(চার্জ বাদে)\n\n"
                f"📲 আপনার {method.upper()} নম্বর লিখুন:"
            )
            
        except ValueError:
            await update.message.reply_text("❌ সঠিক সংখ্যা দিন")
    
    elif step == "account":
        account = text.strip()
        
        withdrawal = {
            "id": f"wd_{len(data['withdrawals']) + 1}",
            "user_id": user_id,
            "amount": context.user_data["withdraw_amount"],
            "amount_bdt": (context.user_data["withdraw_amount"] - WITHDRAW_FEE_USDT) * USDT_TO_BDT_RATE,
            "method": method,
            "account": account,
            "fee": WITHDRAW_FEE_USDT,
            "status": "pending",
            "submitted_at": datetime.now().isoformat(),
            "approved_at": None,
            "admin_notes": ""
        }
        
        data["withdrawals"].append(withdrawal)
        save_data()
        
        for admin_id in ADMIN_IDS:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"💸 **নতুন উইথড্র!**\n\n"
                    f"🆔 {withdrawal['id']}\n"
                    f"👤 ইউজার: {user_id}\n"
                    f"💵 {withdrawal['amount']} USDT ({withdrawal['amount_bdt']} BDT)\n"
                    f"📲 {method}: {account}\n\n"
                    f"/approve_withdraw {withdrawal['id']}\n"
                    f"/reject_withdraw {withdrawal['id']} <কারণ>"
                )
            )
        
        context.user_data.clear()
        await update.message.reply_text(
            f"✅ **উইথড্র রিকোয়েস্ট জমা হয়েছে!**\n\n"
            f"💵 {withdrawal['amount']} USDT\n"
            f"📲 {method}: {account}\n\n"
            f"⏳ অ্যাডমিন প্রসেস করছে..."
        )
        await main_menu(update, context)

# ============= অ্যাডমিন ডিপোজিট/উইথড্র অ্যাপ্রুভ =============
async def admin_approve_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """অ্যাডমিন ডিপোজিট অ্যাপ্রুভ"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ আপন অ্যাডমিন নন!")
        return
    
    try:
        deposit_id = context.args[0]
        
        deposit = None
        for d in data["deposits"]:
            if d["id"] == deposit_id:
                deposit = d
                break
        
        if not deposit:
            await update.message.reply_text("❌ ডিপোজিট পাওয়া যায়নি!")
            return
        
        if deposit["status"] != "pending":
            await update.message.reply_text(f"⚠️ ইতিমধ্যে {deposit['status']}!")
            return
        
        deposit["status"] = "approved"
        deposit["approved_at"] = datetime.now().isoformat()
        
        user = get_user(deposit["user_id"])
        user["balance"] += deposit["amount"]
        
        transaction = {
            "id": f"txn_{len(data['transactions']) + 1}",
            "user_id": deposit["user_id"],
            "amount": deposit["amount"],
            "type": "deposit",
            "method": deposit["method"],
            "status": "completed",
            "timestamp": datetime.now().isoformat()
        }
        data["transactions"].append(transaction)
        
        save_data()
        
        await context.bot.send_message(
            chat_id=deposit["user_id"],
            text=(
                f"✅ **ডিপোজিট অ্যাপ্রুভ হয়েছে!**\n\n"
                f"💵 {format_balance(deposit['amount'])} USDT যোগ হয়েছে।\n"
                f"📲 {deposit['method']}: {deposit['reference']}\n\n"
                f"নতুন ব্যালেন্স: {format_balance(user['balance'])} USDT"
            )
        )
        
        await update.message.reply_text(f"✅ ডিপোজিট {deposit_id} অ্যাপ্রুভ হয়েছে!")
        
    except IndexError:
        await update.message.reply_text("⚠️ ব্যবহার: /approve_deposit <deposit_id>")

async def admin_reject_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """অ্যাডমিন ডিপোজিট রিজেক্ট"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ আপন অ্যাডমিন নন!")
        return
    
    try:
        deposit_id = context.args[0]
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "নির্দিষ্ট করা হয়নি"
        
        deposit = None
        for d in data["deposits"]:
            if d["id"] == deposit_id:
                deposit = d
                break
        
        if not deposit:
            await update.message.reply_text("❌ ডিপোজিট পাওয়া যায়নি!")
            return
        
        if deposit["status"] != "pending":
            await update.message.reply_text(f"⚠️ ইতিমধ্যে {deposit['status']}!")
            return
        
        deposit["status"] = "rejected"
        deposit["admin_notes"] = reason
        
        save_data()
        
        await context.bot.send_message(
            chat_id=deposit["user_id"],
            text=(
                f"❌ **ডিপোজিট রিজেক্ট হয়েছে!**\n\n"
                f"কারণ: {reason}"
            )
        )
        
        await update.message.reply_text(f"❌ ডিপোজিট {deposit_id} রিজেক্ট করা হয়েছে।")
        
    except IndexError:
        await update.message.reply_text("⚠️ ব্যবহার: /reject_deposit <deposit_id> <কারণ>")

async def admin_approve_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """অ্যাডমিন উইথড্র অ্যাপ্রুভ"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ আপন অ্যাডমিন নন!")
        return
    
    try:
        withdrawal_id = context.args[0]
        
        withdrawal = None
        for w in data["withdrawals"]:
            if w["id"] == withdrawal_id:
                withdrawal = w
                break
        
        if not withdrawal:
            await update.message.reply_text("❌ উইথড্র পাওয়া যায়নি!")
            return
        
        if withdrawal["status"] != "pending":
            await update.message.reply_text(f"⚠️ ইতিমধ্যে {withdrawal['status']}!")
            return
        
        user = get_user(withdrawal["user_id"])
        if user["balance"] < withdrawal["amount"]:
            await update.message.reply_text("❌ ইউজারের ব্যালেন্স কম!")
            return
        
        user["balance"] -= withdrawal["amount"]
        
        withdrawal["status"] = "approved"
        withdrawal["approved_at"] = datetime.now().isoformat()
        
        transaction = {
            "id": f"txn_{len(data['transactions']) + 1}",
            "user_id": withdrawal["user_id"],
            "amount": withdrawal["amount"],
            "type": "withdrawal",
            "method": withdrawal["method"],
            "status": "completed",
            "timestamp": datetime.now().isoformat()
        }
        data["transactions"].append(transaction)
        
        save_data()
        
        await context.bot.send_message(
            chat_id=withdrawal["user_id"],
            text=(
                f"✅ **উইথড্র অ্যাপ্রুভ হয়েছে!**\n\n"
                f"💵 {format_balance(withdrawal['amount'])} USDT উইথড্র হয়েছে।\n"
                f"📲 {withdrawal['method']}: {withdrawal['account']}\n\n"
                f"নতুন ব্যালেন্স: {format_balance(user['balance'])} USDT"
            )
        )
        
        await update.message.reply_text(
            f"✅ উইথড্র {withdrawal_id} অ্যাপ্রুভ হয়েছে!"
        )
        
    except IndexError:
        await update.message.reply_text("⚠️ ব্যবহার: /approve_withdraw <withdrawal_id>")

async def admin_reject_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """অ্যাডমিন উইথড্র রিজেক্ট"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ আপন অ্যাডমিন নন!")
        return
    
    try:
        withdrawal_id = context.args[0]
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "নির্দিষ্ট করা হয়নি"
        
        withdrawal = None
        for w in data["withdrawals"]:
            if w["id"] == withdrawal_id:
                withdrawal = w
                break
        
        if not withdrawal:
            await update.message.reply_text("❌ উইথড্র পাওয়া যায়নি!")
            return
        
        if withdrawal["status"] != "pending":
            await update.message.reply_text(f"⚠️ ইতিমধ্যে {withdrawal['status']}!")
            return
        
        withdrawal["status"] = "rejected"
        withdrawal["admin_notes"] = reason
        
        save_data()
        
        await context.bot.send_message(
            chat_id=withdrawal["user_id"],
            text=(
                f"❌ **উইথড্র রিজেক্ট হয়েছে!**\n\n"
                f"কারণ: {reason}"
            )
        )
        
        await update.message.reply_text(f"❌ উইথড্র {withdrawal_id} রিজেক্ট করা হয়েছে।")
        
    except IndexError:
        await update.message.reply_text("⚠️ ব্যবহার: /reject_withdraw <withdrawal_id> <কারণ>")

# ============= আমার টাস্ক =============
async def my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """আমার টাস্ক দেখান"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    
    posted_tasks = [t for t in data["tasks"] if t["posted_by"] == user_id]
    taken_tasks = [t for t in data["tasks"] if user_id in t["accepted_by"]]
    
    if not posted_tasks and not taken_tasks:
        await query.edit_message_text(
            "📋 **আপনার কোনো টাস্ক নেই**",
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
        return
    
    text = "📋 **আমার টাস্ক**\n\n"
    
    if posted_tasks:
        text += "📤 **আমি পোস্ট করেছি:**\n"
        for task in posted_tasks[:5]:
            status = {
                "pending": "⏳ রিভিউতে",
                "active": "✅ চলমান",
                "completed": "✅ সম্পূর্ণ",
                "rejected": "❌ রিজেক্ট",
                "expired": "⏰ মেয়াদ শেষ"
            }.get(task["status"], task["status"])
            
            text += (
                f"  📌 #{task['id']} {task['title']}\n"
                f"     স্ট্যাটাস: {status}\n"
                f"     স্লট: {task['completed_slots']}/{task['total_slots']}\n\n"
            )
    
    if taken_tasks:
        text += "📥 **আমি নিয়েছি:**\n"
        for task in taken_tasks[:5]:
            status = "⏳ চলমান" if task["status"] == "active" else "✅ সম্পূর্ণ"
            text += f"  📌 #{task['id']} {task['title']} - {status}\n"
    
    await query.edit_message_text(
        text,
        reply_markup=back_keyboard(),
        parse_mode="Markdown"
    )

# ============= ট্রানজেকশন হিস্টোরি =============
async def transaction_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ট্রানজেকশন হিস্টোরি"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    
    transactions = [t for t in data["transactions"] if t["user_id"] == user_id]
    
    if not transactions:
        await query.edit_message_text(
            "📜 **কোন ট্রানজেকশন নেই**",
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
        return
    
    text = "📜 **ট্রানজেকশন হিস্টোরি**\n\n"
    for txn in transactions[-10:]:
        type_emoji = "💰" if txn["type"] == "deposit" else "💸"
        text += (
            f"{type_emoji} {txn['type'].title()}: {format_balance(txn['amount'])} USDT\n"
            f"   📅 {txn['timestamp'][:10]}\n"
            f"   📊 {txn['status']}\n\n"
        )
    
    await query.edit_message_text(
        text,
        reply_markup=back_keyboard(),
        parse_mode="Markdown"
    )

# ============= ব্যাক বাটন =============
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """মেইনে ফিরে যান"""
    query = update.callback_query
    await query.answer()
    await main_menu(update, context)

# ============= ক্যানসেল =============
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """বাতিল করুন"""
    if context.user_data:
        context.user_data.clear()
        await update.message.reply_text("❌ অপারেশন বাতিল করা হয়েছে।")
    else:
        await update.message.reply_text("❌ কোনো অপারেশন চলছে না।")
    await main_menu(update, context)

# ============= মেইন ফাংশন =============
def main():
    """বট চালু করুন"""
    app = Application.builder().token(BOT_TOKEN).build()
    
    # কমান্ড
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    
    # টাস্ক কমান্ড
    app.add_handler(CommandHandler("approve_task", approve_task))
    app.add_handler(CommandHandler("reject_task", reject_task))
    app.add_handler(CommandHandler("submit_proof", submit_proof))
    app.add_handler(CommandHandler("approve_proof", approve_proof))
    app.add_handler(CommandHandler("reject_proof", reject_proof))
    
    # ডিপোজিট/উইথড্র কমান্ড (অ্যাডমিন)
    app.add_handler(CommandHandler("approve_deposit", admin_approve_deposit))
    app.add_handler(CommandHandler("reject_deposit", admin_reject_deposit))
    app.add_handler(CommandHandler("approve_withdraw", admin_approve_withdraw))
    app.add_handler(CommandHandler("reject_withdraw", admin_reject_withdraw))
    
    # কলব্যাক কুয়েরি
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_main$"))
    app.add_handler(CallbackQueryHandler(find_tasks, pattern="^find_tasks$"))
    app.add_handler(CallbackQueryHandler(post_task_start, pattern="^post_task$"))
    app.add_handler(CallbackQueryHandler(wallet, pattern="^wallet$"))
    app.add_handler(CallbackQueryHandler(my_tasks, pattern="^my_tasks$"))
    app.add_handler(CallbackQueryHandler(take_task, pattern="^take_task_"))
    
    # ডিপোজিট
    app.add_handler(CallbackQueryHandler(deposit_menu, pattern="^deposit_menu$"))
    app.add_handler(CallbackQueryHandler(deposit_bkash, pattern="^deposit_bkash$"))
    app.add_handler(CallbackQueryHandler(deposit_nagad, pattern="^deposit_nagad$"))
    
    # উইথড্র
    app.add_handler(CallbackQueryHandler(withdraw_menu, pattern="^withdraw_menu$"))
    app.add_handler(CallbackQueryHandler(withdraw_bkash, pattern="^withdraw_bkash$"))
    app.add_handler(CallbackQueryHandler(withdraw_nagad, pattern="^withdraw_nagad$"))
    
    # ট্রানজেকশন
    app.add_handler(CallbackQueryHandler(transaction_history, pattern="^transaction_history$"))
    
    # মেসেজ হ্যান্ডলার
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_task_input
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_deposit
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_withdraw
    ))
    
    print(f"🤖 {BOT_NAME} চালু হয়েছে!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
