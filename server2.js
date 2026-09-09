const express=require('express');
const cors=require('cors');
const bcrypt=require('bcryptjs');
const jwt=require('jsonwebtoken');
const fs=require('fs');
const path=require('path');
const {Pool}=require('pg');

const app=express();
app.use(cors());
app.use(express.json());
const usePg=/^postgres(ql)?:\/\//i.test(process.env.DATABASE_URL||'');
const pool=usePg?new Pool({connectionString:process.env.DATABASE_URL,ssl:{rejectUnauthorized:false}}):null;
const FILE=path.join(__dirname,'data.json');
const JWT_SECRET=process.env.JWT_SECRET||'change-this-in-render';
const ADMIN_KEY=process.env.ADMIN_KEY||'set-an-admin-key';
const prices={1000:22,2000:40,5000:80,10000:150};
const sizes=[1000,2000,5000,10000];

function fileInit(){
  if(!fs.existsSync(FILE))fs.writeFileSync(FILE,JSON.stringify({users:[],orders:[],accounts:[],trades:[],notifications:[],next:{user:1,order:1,account:1,trade:1,notification:1}},null,2));
  const d=JSON.parse(fs.readFileSync(FILE,'utf8'));
  if(!d.notifications)d.notifications=[];
  if(!d.next.notification)d.next.notification=1;
  fs.writeFileSync(FILE,JSON.stringify(d,null,2));
}
function dbRead(){fileInit();return JSON.parse(fs.readFileSync(FILE,'utf8'))}
function dbWrite(d){fs.writeFileSync(FILE,JSON.stringify(d,null,2))}

async function init(){
  if(usePg){
    await pool.query(`CREATE TABLE IF NOT EXISTS users(id SERIAL PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created_at TIMESTAMPTZ DEFAULT now());
    CREATE TABLE IF NOT EXISTS orders(id SERIAL PRIMARY KEY,user_id INT REFERENCES users(id) ON DELETE CASCADE,mode TEXT NOT NULL,size INT NOT NULL,price NUMERIC(10,2) NOT NULL,payment_ref TEXT,status TEXT NOT NULL DEFAULT 'pending',created_at TIMESTAMPTZ DEFAULT now(),approved_at TIMESTAMPTZ);
    CREATE TABLE IF NOT EXISTS accounts(id SERIAL PRIMARY KEY,user_id INT REFERENCES users(id) ON DELETE CASCADE,account_no TEXT UNIQUE NOT NULL,mode TEXT NOT NULL,size INT NOT NULL,balance NUMERIC(14,2) NOT NULL,equity NUMERIC(14,2) NOT NULL,total_pnl NUMERIC(14,2) NOT NULL DEFAULT 0,daily_pnl NUMERIC(14,2) NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'active',created_at TIMESTAMPTZ DEFAULT now());
    CREATE TABLE IF NOT EXISTS trades(id SERIAL PRIMARY KEY,account_id INT REFERENCES accounts(id) ON DELETE CASCADE,direction TEXT NOT NULL,amount NUMERIC(14,2) NOT NULL,entry_price NUMERIC(14,2) NOT NULL,exit_price NUMERIC(14,2) NOT NULL,result TEXT NOT NULL,pnl NUMERIC(14,2) NOT NULL,expiry TEXT NOT NULL,created_at TIMESTAMPTZ DEFAULT now());
    CREATE TABLE IF NOT EXISTS notifications(id SERIAL PRIMARY KEY,user_id INT REFERENCES users(id) ON DELETE CASCADE,title TEXT NOT NULL,message TEXT NOT NULL,type TEXT NOT NULL DEFAULT 'info',read_at TIMESTAMPTZ,created_at TIMESTAMPTZ DEFAULT now());`);
  }else fileInit();
}
function token(u){return jwt.sign({id:u.id,email:u.email},JWT_SECRET,{expiresIn:'7d'})}
async function auth(req,res,next){try{const h=req.headers.authorization||'';req.user=jwt.verify(h.startsWith('Bearer ')?h.slice(7):'',JWT_SECRET);next()}catch(e){res.status(401).json({error:'Authentication required'})}}
function admin(req,res,next){if(req.headers['x-admin-key']!==ADMIN_KEY)return res.status(403).json({error:'Admin access denied'});next()}

async function coinbaseTicker(product){
  const r=await fetch('https://api.exchange.coinbase.com/products/'+product+'/ticker',{headers:{accept:'application/json'}});
  if(!r.ok)throw new Error('Coinbase market unavailable');
  const j=await r.json();
  const price=Number(j.price);
  if(!Number.isFinite(price))throw new Error('Invalid Coinbase price');
  return price;
}

const OANDA_INSTRUMENTS={XAUUSD:'XAU_USD',EURUSD:'EUR_USD',JPYUSD:'JPY_USD',CHFUSD:'CHF_USD',GBPUSD:'GBP_USD',AUDUSD:'AUD_USD'};
const OTC_BASE={BTCUSD:78000,ETHUSD:3200,XAUUSD:2350,EURUSD:1.085,JPYUSD:0.0067,CHFUSD:1.12,GBPUSD:1.27,AUDUSD:0.66};
function otcPrice(key,ms=Date.now()){
  const base=OTC_BASE[key];
  if(!base)throw new Error('Unknown OTC market');
  const t=ms/1000;
  const wave=Math.sin(t/19)+0.55*Math.sin(t/7.3)+0.25*Math.sin(t/3.1);
  const pct=key==='BTCUSD'||key==='ETHUSD'?0.00035:0.00018;
  return base*(1+pct*wave);
}
async function oandaTicker(key){
  const token=process.env.OANDA_TOKEN;
  const account=process.env.OANDA_ACCOUNT_ID;
  const instrument=OANDA_INSTRUMENTS[key];
  if(!token||!account||!instrument)throw new Error('OANDA not configured');
  const host=process.env.OANDA_ENV==='live'?'https://api-fxtrade.oanda.com':'https://api-fxpractice.oanda.com';
  const r=await fetch(host+'/v3/accounts/'+encodeURIComponent(account)+'/pricing?instruments='+encodeURIComponent(instrument),{headers:{Authorization:'Bearer '+token,accept:'application/json'}});
  if(!r.ok)throw new Error('OANDA market unavailable');
  const j=await r.json();
  const q=j.prices&&j.prices[0];
  const bid=Number(q&&q.bids&&q.bids[0]&&q.bids[0].price),ask=Number(q&&q.asks&&q.asks[0]&&q.asks[0].price);
  const price=(bid+ask)/2;
  if(!Number.isFinite(price))throw new Error('Invalid OANDA price');
  return price;
}
function marketCandles(key,current,sec,count=100){
  const now=Math.floor(Date.now()/1000/sec)*sec,arr=[];
  for(let i=count-1;i>=0;i--){
    const t=(now-i*sec)*1000;
    const c=otcPrice(key,t),o=otcPrice(key,t-sec*1000),h=Math.max(o,c)*(1+0.00005),l=Math.min(o,c)*(1-0.00005);
    arr.push({time:Math.floor(t/1000),open:o,high:h,low:l,close:c});
  }
  if(arr.length)arr[arr.length-1]={...arr[arr.length-1],close:current,high:Math.max(arr[arr.length-1].high,current),low:Math.min(arr[arr.length-1].low,current)};
  return arr;
}
async function marketTicker(symbol){
  const otc=/^(.+)-OTC$/.exec(symbol);
  if(otc)return {price:otcPrice(otc[1]),source:'FundedEdge simulated OTC'};
  if(symbol==='BTC-USD')return {price:await coinbaseTicker('BTC-USD'),source:'Coinbase'};
  if(symbol==='ETH-USD')return {price:await coinbaseTicker('ETH-USD'),source:'Coinbase'};
  const key=symbol.replace('=X','');
  return {price:await oandaTicker(key),source:'OANDA'};
}

app.get('/api/health',(req,res)=>res.json({ok:true,service:'FundedEdge API',storage:usePg?'postgres':'fallback-file',market:'Coinbase BTC/ETH + OANDA FX/Gold + simulated OTC',time:new Date().toISOString()}));
app.get('/api/market/:symbol',async(req,res)=>{try{const symbol=decodeURIComponent(req.params.symbol);const m=await marketTicker(symbol);res.set('Cache-Control','no-store');res.json({symbol,displaySymbol:symbol.replace('=X','').replace('-OTC',' OTC'),price:m.price,timestamp:Date.now(),source:m.source});}catch(e){res.status(503).json({error:'Market temporarily unavailable'});}});

app.post('/api/auth/register',async(req,res)=>{try{const{name,email,password}=req.body;if(!name||!email||!password||password.length<8)return res.status(400).json({error:'Name, email and an 8+ character password are required'});const em=email.toLowerCase().trim();const hash=await bcrypt.hash(password,12);if(usePg){const r=await pool.query('INSERT INTO users(name,email,password_hash) VALUES($1,$2,$3) RETURNING id,name,email',[name,em,hash]);return res.json({token:token(r.rows[0]),user:r.rows[0]})}const d=dbRead();if(d.users.some(x=>x.email===em))return res.status(400).json({error:'Email already registered'});const u={id:d.next.user++,name,email:em,password_hash:hash,created_at:new Date().toISOString()};d.users.push(u);dbWrite(d);res.json({token:token(u),user:{id:u.id,name:u.name,email:u.email}})}catch(e){res.status(400).json({error:'Registration failed'})}});
app.post('/api/auth/login',async(req,res)=>{try{const em=String(req.body.email||'').toLowerCase().trim();const pw=req.body.password||'';let u;if(usePg){const r=await pool.query('SELECT * FROM users WHERE email=$1',[em]);u=r.rows[0]}else u=dbRead().users.find(x=>x.email===em);if(!u||!(await bcrypt.compare(pw,u.password_hash)))return res.status(401).json({error:'Invalid email or password'});res.json({token:token(u),user:{id:u.id,name:u.name,email:u.email}})}catch(e){res.status(500).json({error:'Login failed'})}});
app.get('/api/me',auth,async(req,res)=>{if(usePg){const u=(await pool.query('SELECT id,name,email,created_at FROM users WHERE id=$1',[req.user.id])).rows[0];if(!u)return res.status(404).json({error:'User not found'});const a=(await pool.query('SELECT * FROM accounts WHERE user_id=$1 ORDER BY id DESC',[req.user.id])).rows;return res.json({user:u,accounts:a})}const d=dbRead();const u=d.users.find(x=>x.id===req.user.id);if(!u)return res.status(404).json({error:'User not found'});res.json({user:{id:u.id,name:u.name,email:u.email,created_at:u.created_at},accounts:d.accounts.filter(x=>x.user_id===req.user.id).sort((a,b)=>b.id-a.id)})});
app.get('/api/notifications',auth,async(req,res)=>{if(usePg){const r=await pool.query('SELECT id,title,message,type,read_at,created_at FROM notifications WHERE user_id=$1 ORDER BY id DESC LIMIT 50',[req.user.id]);return res.json({notifications:r.rows})}const d=dbRead();res.json({notifications:d.notifications.filter(x=>x.user_id===req.user.id).sort((a,b)=>b.id-a.id).slice(0,50)})});
app.post('/api/notifications/:id/read',auth,async(req,res)=>{if(usePg){const r=await pool.query('UPDATE notifications SET read_at=COALESCE(read_at,now()) WHERE id=$1 AND user_id=$2 RETURNING *',[req.params.id,req.user.id]);if(!r.rows[0])return res.status(404).json({error:'Notification not found'});return res.json({ok:true,notification:r.rows[0]})}const d=dbRead();const n=d.notifications.find(x=>x.id===Number(req.params.id)&&x.user_id===req.user.id);if(!n)return res.status(404).json({error:'Notification not found'});n.read_at=n.read_at||new Date().toISOString();dbWrite(d);res.json({ok:true,notification:n})});
async function createNotification(userId,title,message,type='info'){if(usePg){const r=await pool.query('INSERT INTO notifications(user_id,title,message,type) VALUES($1,$2,$3,$4) RETURNING *',[userId,title,message,type]);return r.rows[0]}const d=dbRead();const n={id:d.next.notification++,user_id:userId,title,message,type,read_at:null,created_at:new Date().toISOString()};d.notifications.push(n);dbWrite(d);return n}
app.post('/api/orders',auth,async(req,res)=>{const{mode,size,price,paymentRef}=req.body;const s=Number(size),p=Number(price);if(!['1 Step','2 Step'].includes(mode)||!sizes.includes(s)||p!==prices[s])return res.status(400).json({error:'Invalid challenge'});if(usePg){const r=await pool.query('INSERT INTO orders(user_id,mode,size,price,payment_ref) VALUES($1,$2,$3,$4,$5) RETURNING *',[req.user.id,mode,s,p,paymentRef||null]);await createNotification(req.user.id,'Payment submitted','Your '+mode+' $'+(s/1000)+'K challenge order #'+r.rows[0].id+' is waiting for manual payment verification.','payment');return res.json({order:r.rows[0]})}const d=dbRead();const o={id:d.next.order++,user_id:req.user.id,mode,size:s,price:p,payment_ref:paymentRef||null,status:'pending',created_at:new Date().toISOString(),approved_at:null};d.orders.push(o);dbWrite(d);await createNotification(req.user.id,'Payment submitted','Your '+mode+' $'+(s/1000)+'K challenge order #'+o.id+' is waiting for manual payment verification.','payment');res.json({order:o})});
app.get('/api/orders',auth,async(req,res)=>{if(usePg){const r=await pool.query('SELECT * FROM orders WHERE user_id=$1 ORDER BY id DESC',[req.user.id]);return res.json({orders:r.rows})}res.json({orders:dbRead().orders.filter(x=>x.user_id===req.user.id).sort((a,b)=>b.id-a.id)})});
app.get('/api/accounts/:id',auth,async(req,res)=>{if(usePg){const r=await pool.query('SELECT * FROM accounts WHERE id=$1 AND user_id=$2',[req.params.id,req.user.id]);if(!r.rows[0])return res.status(404).json({error:'Account not found'});const t=await pool.query('SELECT * FROM trades WHERE account_id=$1 ORDER BY id DESC LIMIT 100',[req.params.id]);return res.json({account:r.rows[0],trades:t.rows})}const d=dbRead(),a=d.accounts.find(x=>x.id===Number(req.params.id)&&x.user_id===req.user.id);if(!a)return res.status(404).json({error:'Account not found'});res.json({account:a,trades:d.trades.filter(x=>x.account_id===a.id).sort((a,b)=>b.id-a.id).slice(0,100)})});

app.post('/api/trades',auth,async(req,res)=>{try{const{accountId,direction,amount,expiry}=req.body;const amt=Number(amount);if(!['CALL','PUT'].includes(direction)||!['60s','5m','15m'].includes(expiry)||!Number.isFinite(amt)||amt<=0)return res.status(400).json({error:'Invalid trade'});let a;if(usePg)a=(await pool.query('SELECT * FROM accounts WHERE id=$1 AND user_id=$2 AND status=$3',[accountId,req.user.id,'active'])).rows[0];else a=dbRead().accounts.find(x=>x.id===Number(accountId)&&x.user_id===req.user.id&&x.status==='active');if(!a)return res.status(404).json({error:'Active account not found'});if(amt>Number(a.balance)*0.2)return res.status(400).json({error:'Trade amount exceeds 20% account limit'});
  const entry=await coinbaseTicker('BTC-USD');
  await new Promise(r=>setTimeout(r,900));
  const exit=await coinbaseTicker('BTC-USD');
  const win=direction==='CALL'?exit>entry:exit<entry;
  const pnl=win?amt*.8:-amt,result=win?'WIN':'LOSS',created_at=new Date().toISOString();
  if(usePg){const nr=await pool.query('INSERT INTO trades(account_id,direction,amount,entry_price,exit_price,result,pnl,expiry) VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *',[accountId,direction,amt,entry,exit,result,pnl,expiry]);await pool.query('UPDATE accounts SET balance=balance+$1,equity=equity+$1,total_pnl=total_pnl+$1,daily_pnl=daily_pnl+$1 WHERE id=$2',[pnl,accountId]);return res.json({trade:nr.rows[0],market:{source:'Coinbase',entry,exit}})}
  const d=dbRead();const t={id:d.next.trade++,account_id:a.id,direction,amount:amt,entry_price:entry,exit_price:exit,result,pnl,expiry,created_at,market_source:'Coinbase'};d.trades.push(t);const ac=d.accounts.find(x=>x.id===a.id);ac.balance=Number(ac.balance)+pnl;ac.equity=Number(ac.equity)+pnl;ac.total_pnl=Number(ac.total_pnl)+pnl;ac.daily_pnl=Number(ac.daily_pnl)+pnl;dbWrite(d);res.json({trade:t,market:{source:'Coinbase',entry,exit}})
}catch(e){console.error(e);res.status(503).json({error:'Live market unavailable; trade not executed'})}});

app.get('/api/admin/orders',admin,async(req,res)=>{if(usePg){const r=await pool.query(`SELECT o.*,u.name,u.email,a.account_no,a.status AS account_status FROM orders o JOIN users u ON u.id=o.user_id LEFT JOIN accounts a ON a.user_id=o.user_id AND a.id=(SELECT MAX(id) FROM accounts aa WHERE aa.user_id=o.user_id) ORDER BY o.id DESC`);return res.json({orders:r.rows})}const d=dbRead();res.json({orders:d.orders.sort((a,b)=>b.id-a.id).map(o=>{const u=d.users.find(x=>x.id===o.user_id)||{};const a=d.accounts.filter(x=>x.user_id===o.user_id).sort((x,y)=>y.id-x.id)[0];return {...o,name:u.name||'',email:u.email||'',account_no:a?.account_no||'',account_status:a?.status||''}})})});
async function issueAccount(orderId){if(usePg){const c=await pool.connect();try{await c.query('BEGIN');const o=(await c.query('SELECT * FROM orders WHERE id=$1 FOR UPDATE',[orderId])).rows[0];if(!o)throw Error('Order not found');if(o.status==='approved'){const ex=(await c.query('SELECT * FROM accounts WHERE user_id=$1 ORDER BY id DESC LIMIT 1',[o.user_id])).rows[0];await c.query('COMMIT');return{order:o,account:ex,already:true}}const no='FE-'+String(Date.now()).slice(-7)+String(Math.floor(Math.random()*90+10));const a=(await c.query('INSERT INTO accounts(user_id,account_no,mode,size,balance,equity,total_pnl) VALUES($1,$2,$3,$4,$4,$4,0) RETURNING *',[o.user_id,no,o.mode,o.size])).rows[0];const updated=(await c.query("UPDATE orders SET status='approved',approved_at=now() WHERE id=$1 RETURNING *",[o.id])).rows[0];await c.query('COMMIT');return{order:updated,account:a}}finally{c.release()}}const d=dbRead();const o=d.orders.find(x=>x.id===Number(orderId));if(!o)throw Error('Order not found');if(o.status==='approved')return{order:o,account:d.accounts.filter(x=>x.user_id===o.user_id).sort((a,b)=>b.id-a.id)[0],already:true};const no='FE-'+String(Date.now()).slice(-7)+String(Math.floor(Math.random()*90+10));const a={id:d.next.account++,user_id:o.user_id,account_no:no,mode:o.mode,size:o.size,balance:o.size,equity:o.size,total_pnl:0,daily_pnl:0,status:'active',created_at:new Date().toISOString()};d.accounts.push(a);o.status='approved';o.approved_at=new Date().toISOString();dbWrite(d);return{order:o,account:a}}
app.post('/api/admin/orders/:id/approve',admin,async(req,res)=>{try{const x=await issueAccount(req.params.id);if(!x.already)await createNotification(x.order.user_id,'Payment approved — account issued','Your payment for Order #'+x.order.id+' has been approved. Your simulated trading account '+x.account.account_no+' is now active. Log in with your registered email and password to open the dashboard.','success');res.json({ok:true,account:x.account,order:x.order,already:x.already})}catch(e){res.status(400).json({error:e.message})}});
app.post('/api/admin/orders/:id/reject',admin,async(req,res)=>{try{let o;if(usePg)o=(await pool.query("UPDATE orders SET status='rejected' WHERE id=$1 RETURNING *",[req.params.id])).rows[0];else{const d=dbRead();o=d.orders.find(x=>x.id===Number(req.params.id));if(o){o.status='rejected';dbWrite(d)}}if(!o)return res.status(404).json({error:'Order not found'});await createNotification(o.user_id,'Payment review update','Your Order #'+o.id+' was not approved. Please review your payment reference and contact support if you believe this is an error.','warning');res.json({ok:true})}catch(e){res.status(400).json({error:e.message})}});
app.post('/api/admin/notify',admin,async(req,res)=>{try{const{orderId,title,message,type='info'}=req.body;if(!orderId||!title||!message)return res.status(400).json({error:'Order, title and message are required'});let o;if(usePg)o=(await pool.query('SELECT * FROM orders WHERE id=$1',[orderId])).rows[0];else o=dbRead().orders.find(x=>x.id===Number(orderId));if(!o)return res.status(404).json({error:'Order not found'});const n=await createNotification(o.user_id,String(title).slice(0,120),String(message).slice(0,1000),type);res.json({ok:true,notification:n})}catch(e){res.status(400).json({error:e.message})}});

const PORT=process.env.PORT||10000;
init().then(()=>app.listen(PORT,()=>console.log('FundedEdge API listening on '+PORT))).catch(e=>{console.error(e);process.exit(1)});
