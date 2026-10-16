<?php
$botToken = "6514219229:AAGnAcKQjPysxW2nGkXcyyUNhd-9kPWi-oE";
$chatId   = "5851334722";

$name     = htmlspecialchars($_POST['name'] ?? '');
$phone    = htmlspecialchars($_POST['phone'] ?? '');
$address  = htmlspecialchars($_POST['address'] ?? '');
$product  = htmlspecialchars($_POST['product'] ?? '');
$price    = htmlspecialchars($_POST['price'] ?? '');
$quantity = htmlspecialchars($_POST['quantity'] ?? '1');
$note     = htmlspecialchars($_POST['note'] ?? 'কোনো নোট নেই');

$total = (int)$price * (int)$quantity;

$message  = "🛒 *নতুন COD অর্ডার এসেছে!*\n\n";
$message .= "👗 জামা: *$product*\n";
$message .= "💰 দাম: *৳$price*\n";
$message .= "🔢 পরিমাণ: *$quantity পিস*\n";
$message .= "🧾 মোট: *৳$total*\n\n";
$message .= "👤 নাম: *$name*\n";
$message .= "📱 মোবাইল: *$phone*\n";
$message .= "📍 ঠিকানা: *$address*\n";
$message .= "📝 নোট: *$note*\n\n";
$message .= "⏰ সময়: " . date("d M Y, h:i A");

$url = "https://api.telegram.org/bot$botToken/sendMessage";
$data = [
    'chat_id' => $chatId,
    'text' => $message,
    'parse_mode' => 'Markdown'
];

$options = [
    'http' => [
        'header'  => "Content-type: application/x-www-form-urlencoded\r\n",
        'method'  => 'POST',
        'content' => http_build_query($data)
    ]
];
$context = stream_context_create($options);
$result = @file_get_contents($url, false, $context);

if ($result) {
    echo '<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>সফল</title><link rel="stylesheet" href="style.css"></head><body>';
    echo '<div class="success-box"><h2>✅ অর্ডার সফল!</h2><p>আপনার অর্ডারটি গ্রহণ করা হয়েছে। শীঘ্রই যোগাযোগ করা হবে।</p><a href="index.html" class="btn">হোমে ফিরে যান</a></div>';
    echo '</body></html>';
} else {
    echo '<h2 style="text-align:center;margin-top:80px;color:red;">❌ সমস্যা হয়েছে। আবার চেষ্টা করুন।</h2>';
}
?>