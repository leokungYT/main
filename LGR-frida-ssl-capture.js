// LGR-frida-ssl-capture.js  (rev.2)
// ดักจับ request/response ของ LINE Rangers ทะลุ SSL pinning
// อ่านหลังถอดรหัสในแอป (SSL_read/SSL_write) → pinning ไม่เกี่ยว
//
// ============================================================================
//  ต้องรันบนเครื่อง arm64 จริง  (มือถือ root / emulator ARM แท้ / Corellium)
//  บน MuMu/LDPlayer x86 (native-bridge) ใช้ไม่ได้ — พิสูจน์แล้ว:
//    - frida เป็น x86_64 มองไม่เห็น libgame.so (arm64) → hook native ไม่ได้
//    - game API เป็น native curl ล้วน (ชั้น Java okhttp โหลดไว้แต่เกมไม่ใช้ยิง API)
//    - MITM โดน CURLOPT_PINNEDPUBLICKEY ปฏิเสธ
//  แต่ frida "ยิงเองได้" (Java) บน x86 ผ่าน spawn-gating — ใช้กับ arm64 ก็ยิ่งได้
// ============================================================================
//
// วิธีรัน (spawn-gating — พิสูจน์แล้วว่าผ่าน LIAPP v5):
//   1) push frida-server-arm64 -> /data/local/tmp/fs ; chmod 755 ; su -c '/data/local/tmp/fs &'
//   2) host:  frida==17.x ; ต้อง bundle java bridge ถ้าใช้ Java (ที่นี่ไม่ต้อง, native ล้วน)
//      python:
//        dev=frida.get_device('<serial>'); pid=dev.spawn(['com.linecorp.LGRGS'])
//        s=dev.attach(pid); sc=s.create_script(open('LGR-frida-ssl-capture.js').read())
//        sc.on('message',cb); sc.load(); dev.resume(pid)
//      *** ต้อง spawn (ไม่ใช่ attach ทีหลัง) เพื่อยึดก่อน LIAPP arm anti-tamper ***
//
// auth ที่จะเห็น (ยืนยันจาก static libgame.so):
//   X-LINEGAME-APPID: LGRGS
//   X-LINEGAME-APPSECRET: <...>   X-LINEGAME-USERKEY: <...>   X-LINEGAME-TIMESTAMP: <ms>
//   X-LINEGAME-MCC/MNC: <...>     Cookie: <name>=<val>; udid=<deviceuuid>;
//   ไม่พบ X-LINEGAME-SIGNATURE → คาดว่าไม่มี HMAC ต่อ body (ยืนยันตอนดักจริง)

'use strict';

function fmt(buf, n) {
  if (n <= 0) return null;
  try {
    var u8 = new Uint8Array(Memory.readByteArray(buf, Math.min(n, 8192)));
    var s = '';
    for (var i = 0; i < u8.length; i++) {
      var c = u8[i];
      s += (c >= 0x20 && c < 0x7f) || c === 0x0a || c === 0x0d ? String.fromCharCode(c) : '.';
    }
    return s;
  } catch (e) { return null; }
}

function hook(mod) {
  var rd = Module.findExportByName(mod, 'SSL_read');
  var wr = Module.findExportByName(mod, 'SSL_write');
  if (!rd || !wr) return false;
  console.log('[+] hooking SSL in ' + mod);
  Interceptor.attach(wr, {
    onEnter: function (a) {
      var t = fmt(a[1], a[2].toInt32());
      if (t && /rangers-api|line-apps|HTTP\/|X-LINEGAME|Cookie|\{"/.test(t))
        console.log('\n>>> TX >>>\n' + t + '\n');
    }
  });
  Interceptor.attach(rd, {
    onEnter: function (a) { this.b = a[1]; },
    onLeave: function (r) {
      var t = fmt(this.b, r.toInt32());
      if (t && /\{"result|HTTP\/|line-apps/.test(t))
        console.log('\n<<< RX <<<\n' + t + '\n');
    }
  });
  return true;
}

function main() {
  var ok = false;
  ['libgame.so', 'libtrident.so', 'libssl.so', 'libcrypto.so'].forEach(function (m) {
    try { if (hook(m)) ok = true; } catch (e) {}
  });
  if (!ok) {
    console.log('[!] ไม่เจอ export SSL_read/SSL_write (อาจ strip)');
    console.log('    modules:'); Process.enumerateModules().forEach(function (m) {
      if (/game|trident|ssl|crypto/i.test(m.name)) console.log('     ' + m.name + ' ' + m.base);
    });
    console.log('    ถ้า strip: หา offset จาก Ghidra บน libgame.so แล้ว');
    console.log('    Interceptor.attach(Module.findBaseAddress("libgame.so").add(0xOFFSET), ...)');
  }
}
setTimeout(main, 800);
