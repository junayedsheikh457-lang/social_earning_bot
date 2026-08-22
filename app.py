```python
import os, sqlite3, threading
from flask import Flask, jsonify, request, render_template_string
import telebot
from telebot import types

# ===== CONFIG =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PORT = int(os.getenv("PORT", 5000))

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
conn = sqlite3.connect('tasks.db', check_same_thread=False)
c = conn.cursor()

# ===== DATABASE =====
c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, username TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, creator_id INTEGER, title TEXT, reward INTEGER, requirement TEXT, status TEXT DEFAULT 'open', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
c.execute('''CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, user_id INTEGER, proof TEXT, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
c.execute('''CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, txid TEXT, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
c.execute('''CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, account TEXT, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
c.execute('''CREATE TABLE IF NOT EXISTS admin_balance (id INTEGER PRIMARY KEY DEFAULT 1, balance INTEGER DEFAULT 0)''')
conn.commit()

# ===== HELPER =====
def get_balance(uid):
    c.execute("INSERT OR IGNORE INTO users(user_id, username) VALUES (?,?)", (uid, f"user_{uid}"))
    conn.commit()
    c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    return c.fetchone()[0]

def is_admin(uid):
    return uid == ADMIN_ID

# ===== MINI APP HTML =====
HTML = '''<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f172a;color:#e2e8f0;font-family:-apple-system,sans-serif;padding:16px 16px 80px}
h2{font-size:20px;margin-bottom:12px}
.card{background:#1e293b;padding:14px;border-radius:14px;margin:10px 0;border:1px solid #334155}
input,textarea{width:100%;padding:12px;border-radius:10px;border:1px solid #475569;margin:8px 0;background:#334155;color:#fff;font-size:14px}
button.main{background:#3b82f6;border:none;padding:12px;border-radius:10px;color:#fff;width:100%;margin-top:8px;font-weight:600}
button.main:disabled{background:#475569}
.tab{position:fixed;bottom:0;left:0;right:0;display:flex;background:#1e293b;border-top:1px solid #334155}
.tab button{flex:1;padding:14px;border:none;background:none;color:#94a3b8;font-size:13px;font-weight:500}
.tab button.active{color:#3b82f6}
.badge{background:#dcfce7;color:#166534;padding:4px 8px;border-radius:6px;font-size:12px;display:inline-block}
.hidden{display:none}
.row{display:flex;gap:8px}
.row button{flex:1}
</style>
</head>
<body>
<h2>TaskHub <span id="bal" class="badge">৳0</span></h2>

<div id="tasksTab">
  <div id="taskList"></div>
  <button class="main" onclick="showAdd()">+ Add Task</button>
</div>

<div id="addTab" class="hidden">
  <h3>নতুন টাস্ক</h3>
  <input id="tTitle" placeholder="টাস্কের নাম">
  <input id="tReward" type="number" placeholder="রিওয়ার্ড টাকা">
  <textarea id="tReq" placeholder="রিকোয়ারমেন্ট - যেমন: ইউটিউব সাব করে SS দাও"></textarea>
  <p id="fee" style="color:#94a3b8;font-size:13px"></p>
  <button class="main" id="createBtn" onclick="createTask()">টাস্ক বানাও</button>
</div>

<div id="walletTab" class="hidden">
  <div class="card">
    <h3>Wallet</h3>
    <div class="row">
      <button class="main" onclick="showDep()">+ Deposit</button>
      <button class="main" onclick="showWith()">Withdraw</button>
    </div>
  </div>
  <div id="depTab" class="hidden">
    <input id="depAmt" type="number" placeholder="টাকার পরিমাণ">
    <input id="depTxid" placeholder="bKash TXID">
    <button class="main" onclick="deposit()">Submit Deposit</button>
  </div>
  <div id="withTab" class="hidden">
    <input id="withAmt" type="number" placeholder="মিনিমাম ৳100">
    <input id="withAcc" placeholder="তোমার bKash নাম্বার">
    <button class="main" onclick="withdraw()">Submit Withdraw</button>
  </div>
</div>

<div class="tab">
  <button class="active" onclick="switchTab('tasks')">Tasks</button>
  <button onclick="switchTab('wallet')">Wallet</button>
</div>

<script>
let tg = window.Telegram.WebApp; tg.expand(); tg.enableClosingConfirmation();
let uid = tg.initDataUnsafe.user.id;

function load(){
  fetch('/api/balance?uid='+uid).then(r=>r.json()).then(d=>{
    document.getElementById('bal').innerText='৳'+d.balance;
  });
  fetch('/api/tasks?uid='+uid).then(r=>r.jso
