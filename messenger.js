const express = require('express');
const crypto = require('crypto');

function createMessengerRouter({ pool }) {
  const router = express.Router();
  const graphVersion = process.env.META_GRAPH_VERSION || 'v23.0';

  router.get('/', (req, res) => {
    const mode = req.query['hub.mode'];
    const token = req.query['hub.verify_token'];
    const challenge = req.query['hub.challenge'];
    if (mode === 'subscribe' && token && token === process.env.META_VERIFY_TOKEN) {
      return res.status(200).send(String(challenge || ''));
    }
    return res.sendStatus(403);
  });

  function validSignature(req) {
    const secret = process.env.META_APP_SECRET;
    if (!secret) return false;
    const signature = req.get('x-hub-signature-256') || '';
    if (!signature.startsWith('sha256=') || !req.rawBody) return false;
    const expected = 'sha256=' + crypto.createHmac('sha256', secret).update(req.rawBody).digest('hex');
    const a = Buffer.from(signature);
    const b = Buffer.from(expected);
    return a.length === b.length && crypto.timingSafeEqual(a, b);
  }

  async function notifyAdmin(message) {
    const token = process.env.TELEGRAM_BOT_TOKEN;
    const chatId = process.env.TELEGRAM_CHAT_ID;
    if (!token || !chatId) return;
    try {
      await fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId, text: message, disable_web_page_preview: true })
      });
    } catch (err) {
      console.error('Telegram admin notification failed:', err.message);
    }
  }

  async function getCatalog() {
    try {
      const result = await pool.query('SELECT data FROM products ORDER BY id DESC LIMIT 100');
      return result.rows.map(row => row.data);
    } catch (err) {
      console.error('Messenger catalog lookup failed:', err.message);
      return [];
    }
  }

  async function makeReply(userText, catalog) {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      return 'আপনার মেসেজটি পেয়েছি 😊 পণ্যের বিস্তারিত নিশ্চিত করে জানাতে আমাদের টিমকে একটু সময় দিন।';
    }
    const compactCatalog = catalog.map(p => ({
      name: p.name,
      price: p.price,
      oldPrice: p.oldPrice || p.old_price || null,
      offer: p.offer || p.offerText || null,
      sizes: p.sizes || [],
      colors: p.colors || [],
      stock: p.stock ?? p.quantity ?? null,
      category: p.category || null,
      description: p.desc || p.description || null
    }));
    const system = [
      'You are the friendly Bengali-language sales assistant for Fashion Mart, a Bangladesh women\'s clothing shop.',
      'Reply naturally and briefly in the customer\'s language, primarily Bangla. Be warm and helpful, not robotic.',
      'Use only the supplied product catalogue for product names, prices, sizes, colors, stock, offers and delivery policies. Never invent missing facts; ask a short follow-up or say the team will confirm.',
      'Never invent an order status, claim an order is placed unless the order system confirms it, or request passwords/OTP/payment card details.',
      'The shop owner must approve every special discount or bargaining request. Do not promise, calculate, or apply a new discount. For a discount request, clearly say you are sending it to the owner for approval.',
      'For complaints, refunds, exchanges, bulk orders, uncertain questions, or a request to speak to a person, politely say the owner/team will follow up.',
      'Ask only for details needed for the next step. Do not claim to be a human; if asked, be transparent that you are the shop\'s virtual assistant.',
      'Do not request full delivery address or phone number in casual chat unless the customer is actively placing an order.'
    ].join(' ');
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: { authorization: 'Bearer ' + apiKey, 'content-type': 'application/json' },
      body: JSON.stringify({
        model: process.env.OPENAI_MODEL || 'gpt-4o-mini',
        temperature: 0.55,
        max_tokens: 220,
        messages: [
          { role: 'system', content: system },
          { role: 'system', content: 'Current product catalogue (JSON): ' + JSON.stringify(compactCatalog) },
          { role: 'user', content: userText }
        ]
      })
    });
    if (!response.ok) {
      console.error('OpenAI reply failed with status:', response.status);
      return 'আপনার মেসেজটি পেয়েছি 😊 একটু পর আবার চেষ্টা করুন, অথবা আমাদের টিমের সাহায্য নিন।';
    }
    const data = await response.json();
    return String(data.choices?.[0]?.message?.content || 'আপনার মেসেজটি পেয়েছি 😊 আমাদের টিম আপনাকে সাহায্য করবে।').slice(0, 1800);
  }

  async function sendMessage(psid, text) {
    const token = process.env.META_PAGE_ACCESS_TOKEN;
    if (!token) throw new Error('META_PAGE_ACCESS_TOKEN is not configured');
    const response = await fetch('https://graph.facebook.com/' + graphVersion + '/me/messages?access_token=' + encodeURIComponent(token), {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        recipient: { id: psid },
        messaging_type: 'RESPONSE',
        message: { text: String(text).slice(0, 1900) }
      })
    });
    if (!response.ok) {
      const body = await response.text();
      console.error('Meta send message failed:', response.status, body.slice(0, 500));
    }
  }

  router.post('/', async (req, res) => {
    if (!validSignature(req)) return res.sendStatus(403);
    const body = req.body || {};
    if (body.object !== 'page') return res.sendStatus(404);
    // Acknowledge Meta quickly; process events asynchronously to avoid webhook retries.
    res.status(200).send('EVENT_RECEIVED');
    for (const entry of (body.entry || [])) {
      for (const event of (entry.messaging || [])) {
        if (!event.sender?.id || event.message?.is_echo || !event.message?.text) continue;
        const psid = event.sender.id;
        const message = String(event.message.text).trim();
        if (!message) continue;
        try {
          const lower = message.toLowerCase();
          const discountRequest = /কম হবে|কম করে|দাম কম|ছাড়|ছাড়|discount|bargain|last price|শেষ দাম|দরদাম/.test(lower);
          const humanRequest = /মানুষের সাথে|মানুষের সঙ্গে|owner|মালিক|অভিযোগ|complaint|refund|ফেরত|exchange|এক্সচেঞ্জ|পাইকারি|wholesale/.test(lower);
          if (discountRequest) {
            await notifyAdmin('Fashion Mart — বিশেষ ছাড়ের অনুমতি প্রয়োজন\nCustomer PSID: ' + psid + '\nMessage: ' + message);
          } else if (humanRequest) {
            await notifyAdmin('Fashion Mart — কাস্টমারের সাহায্য প্রয়োজন\nCustomer PSID: ' + psid + '\nMessage: ' + message);
          }
          const catalog = await getCatalog();
          const reply = await makeReply(message, catalog);
          await sendMessage(psid, reply);
        } catch (err) {
          console.error('Messenger event processing failed:', err.message);
        }
      }
    }
  });

  return router;
}

module.exports = { createMessengerRouter };
