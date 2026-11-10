// api/bare_test.js
// ทดสอบว่า frida script โหลดและรันได้ไหม (ไม่เรียก Java)
send('[+] bare script loaded ok');
setInterval(function () {
    send('[+] still alive @ ' + Date.now());
}, 2000);
