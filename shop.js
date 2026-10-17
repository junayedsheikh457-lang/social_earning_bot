(function(){
const KEY='fashionMartProductsV1', CART='fashionMartCartV1';
const starter=[
{id:'fm101',name:'রোজ পিংক ওয়ান পিস',price:850,oldPrice:1050,category:'1 Piece',description:'সফট আরামদায়ক কাপড় · ফ্রি সাইজ',image:'',badge:'বেস্ট সেলার'},
{id:'fm102',name:'এলিগ্যান্ট ব্ল্যাক গাউন',price:1250,oldPrice:1490,category:'1 Piece',description:'বিশেষ দিনের জন্য স্টাইলিশ ডিজাইন',image:'',badge:'জনপ্রিয়'},
{id:'fm103',name:'ফ্লোরাল প্রিন্ট টু পিস',price:990,oldPrice:1190,category:'2 Piece',description:'সুন্দর প্রিন্ট · দৈনন্দিন ব্যবহারে',image:'',badge:'নতুন'},
{id:'fm104',name:'প্যাস্টেল এমব্রয়ডারি সেট',price:1450,oldPrice:1650,category:'2 Piece',description:'ডিটেইলড কাজ ও আরামদায়ক ফিট',image:'',badge:'নতুন'},
{id:'fm105',name:'লিলাক ডেইলি ওয়ান পিস',price:790,oldPrice:0,category:'1 Piece',description:'হালকা কাপড় · ক্যাজুয়াল লুক',image:'',badge:''},
{id:'fm106',name:'মারুন প্রিমিয়াম টু পিস',price:1350,oldPrice:1550,category:'2 Piece',description:'স্মার্ট কাট ও পরিপাটি ফিনিশিং',image:'',badge:'প্রিমিয়াম'},
{id:'fm107',name:'সফট পিঙ্ক কটন ড্রেস',price:920,oldPrice:0,category:'New Arrival',description:'সারা দিনের আরাম ও সহজ স্টাইল',image:'',badge:'নতুন'},
{id:'fm108',name:'মডেস্ট চিক টু পিস',price:1190,oldPrice:1390,category:'2 Piece',description:'সিম্পল, মার্জিত ও ট্রেন্ডি',image:'',badge:''}
];
function read(key,fallback){try{const x=JSON.parse(localStorage.getItem(key));return Array.isArray(x)?x:fallback}catch{return fallback}}
function products(){return read(KEY,starter)}
function saveProducts(p){localStorage.setItem(KEY,JSON.stringify(p))}
function cart(){return read(CART,[])}
function saveCart(c){localStorage.setItem(CART,JSON.stringify(c));updateCartCount();renderCart()}
function money(n){return '৳'+Number(n||0).toLocaleString('bn-BD')}
function escape(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function placeholder(i){const icons=['✿','❀','❋','✾','♡','✽','❁','✺'];return '<span class="product-placeholder">'+icons[i%icons.length]+'</span>'}
function renderProducts(){
const grid=document.getElementById('product-grid');if(!grid)return;
const q=(document.getElementById('product-search')?.value||'').toLowerCase().trim(),cat=document.getElementById('category-filter')?.value||'all';
const list=products().filter(p=>(cat==='all'||p.category===cat)&&(String(p.name+' '+p.description).toLowerCase().includes(q)));
grid.innerHTML=list.map((p,i)=>'<article class="product-card"><div class="product-image">'+(p.image?'<img loading="lazy" src="'+escape(p.image)+'" alt="'+escape(p.name)+'" onerror="this.remove()">':placeholder(i))+(p.badge?'<span class="product-badge">'+escape(p.badge)+'</span>':'')+'</div><div class="product-info"><span class="product-category">'+escape(p.category==='1 Piece'?'ওয়ান পিস':p.category==='2 Piece'?'টু পিস':'নতুন কালেকশন')+'</span><h3>'+escape(p.name)+'</h3><div class="price-line"><span class="product-price">'+money(p.price)+'</span>'+(Number(p.oldPrice)>Number(p.price)?'<span class="old-price">'+money(p.oldPrice)+'</span>':'')+'</div><p class="product-desc">'+escape(p.description||'')+'</p><button class="add-cart" data-add="'+escape(p.id)+'">কার্টে যোগ করুন +</button></div></article>').join('');
document.getElementById('empty-state').hidden=list.length>0;
}
function updateCartCount(){const el=document.getElementById('cart-count');if(el)el.textContent=cart().reduce((s,x)=>s+x.qty,0)}
function renderCart(){const box=document.getElementById('cart-items');if(!box)return;const c=cart(),ps=products();if(!c.length){box.innerHTML='<div class="cart-empty"><span>🛍️</span>তোমার কার্ট এখনো খালি।<br>পছন্দের পোশাক যোগ করো।</div>'}else{box.innerHTML=c.map(x=>{const p=ps.find(y=>y.id===x.id);if(!p)return '';return '<div class="cart-item"><div><h3>'+escape(p.name)+'</h3><small>'+money(p.price)+' / পিস</small><div class="quantity-control"><button data-qty="'+escape(x.id)+'" data-delta="-1" aria-label="পরিমাণ কমান">−</button><span>'+x.qty+'</span><button data-qty="'+escape(x.id)+'" data-delta="1" aria-label="পরিমাণ বাড়ান">+</button><button class="remove-item" data-remove="'+escape(x.id)+'">বাদ দিন</button></div></div><strong class="cart-item-price">'+money(p.price*x.qty)+'</strong></div>'}).join('')}
const total=c.reduce((s,x)=>{const p=ps.find(y=>y.id===x.id);return s+(p?p.price*x.qty:0)},0);const totalEl=document.getElementById('cart-total');if(totalEl)totalEl.textContent=money(total)}
function openCart(open){document.getElementById('cart-drawer')?.classList.toggle('open',open);document.getElementById('cart-backdrop')?.classList.toggle('open',open);document.body.style.overflow=open?'hidden':''}
document.addEventListener('click',e=>{
const add=e.target.closest('[data-add]');if(add){const id=add.dataset.add,p=products().find(x=>x.id===id);if(!p)return;const c=cart(),found=c.find(x=>x.id===id);if(found)found.qty++;else c.push({id,qty:1});saveCart(c);add.textContent='যোগ হয়েছে ✓';setTimeout(()=>{if(add.isConnected)add.textContent='কার্টে যোগ করুন +'},1000);return}
const qty=e.target.closest('[data-qty]');if(qty){const c=cart(),x=c.find(y=>y.id===qty.dataset.qty);if(x)x.qty+=Number(qty.dataset.delta);saveCart(c.filter(y=>y.qty>0));return}
const rem=e.target.closest('[data-remove]');if(rem){saveCart(cart().filter(x=>x.id!==rem.dataset.remove));return}
if(e.target.closest('#cart-open'))openCart(true);if(e.target.closest('#cart-close')||e.target.id==='cart-backdrop')openCart(false);
if(e.target.closest('#checkout-button')){const c=cart();if(!c.length){alert('অর্ডার করার আগে কার্টে পণ্য যোগ করুন।');return}location.href='order.html'}
const category=e.target.closest('[data-category]');if(category){document.getElementById('category-filter').value=category.dataset.category;renderProducts();document.getElementById('products').scrollIntoView({behavior:'smooth'})}
});
document.getElementById('product-search')?.addEventListener('input',renderProducts);document.getElementById('category-filter')?.addEventListener('change',renderProducts);
window.FashionMart={products,saveProducts,cart,saveCart,money,renderProducts};
renderProducts();updateCartCount();renderCart();const year=document.getElementById('year');if(year)year.textContent=new Date().getFullYear();
})();