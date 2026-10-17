(function(){
const CART='fashionMartCartV1',KEY='fashionMartProductsV1';const form=document.getElementById('checkout-form');if(!form)return;
const read=(k)=>{try{return JSON.parse(localStorage.getItem(k)||'[]')}catch{return []}};
const products=read(KEY),cart=read(CART);const money=n=>'৳'+Number(n||0).toLocaleString('bn-BD');
const items=cart.map(x=>{const p=products.find(y=>y.id===x.id);return p?{id:p.id,name:p.name,price:Number(p.price),quantity:Number(x.qty)}:null}).filter(Boolean);
const subtotal=items.reduce((s,x)=>s+x.price*x.quantity,0);
document.getElementById('order-lines').innerHTML=items.length?items.map(x=>'<div class="summary-row"><span>'+x.name+' × '+x.quantity+'</span><strong>'+money(x.price*x.quantity)+'</strong></div>').join(''):'<p>কার্ট খালি। <a href="index.html">পণ্য বেছে নিন</a></p>';
document.getElementById('subtotal').textContent=money(subtotal);
document.getElementById('customer-area').addEventListener('change',e=>{const fee=e.target.value==='ঢাকার ভিতরে'?70:e.target.value==='ঢাকার বাইরে'?130:0;document.getElementById('delivery').textContent=fee?money(fee):'এলাকা অনুযায়ী';document.getElementById('grand-total').textContent=money(subtotal+fee)});
form.addEventListener('submit',async e=>{e.preventDefault();const msg=document.getElementById('form-message');if(!items.length){msg.hidden=false;msg.textContent='আপনার কার্ট খালি। আগে পণ্য বেছে নিন।';return}const data=Object.fromEntries(new FormData(form).entries());const order={customer:data,items,subtotal,deliveryFee:data.area==='ঢাকার ভিতরে'?70:130,total:subtotal+(data.area==='ঢাকার ভিতরে'?70:130),payment:'Cash on Delivery'};
msg.hidden=false;msg.textContent='অর্ডার পাঠানো হচ্ছে…';
try{const response=await fetch('/api/store/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(order)});if(!response.ok)throw new Error('API unavailable');const result=await response.json();if(!result.success&&!result.orderId)throw new Error('Order not confirmed');localStorage.removeItem(CART);location.href='success.html?order='+encodeURIComponent(result.orderId||result.order?.id||'');}
catch(err){msg.textContent='অর্ডার এখনো জমা হয়নি: এই সাইটের অর্ডার সার্ভার/API এখনো সংযুক্ত নেই। দয়া করে এই ফর্মে দেওয়া তথ্য পাঠানো হয়েছে ধরে নেবেন না। সার্ভার ও Telegram নোটিফিকেশন যুক্ত করার পর অর্ডার চালু হবে।';}
});
})();