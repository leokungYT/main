// api/frida_native_ssl.js
// LGR เป็น cocos2d — ใช้ BoringSSL/OpenSSL ใน native code
// hook SSL_write / SSL_read ตรงที่ plaintext อยู่ก่อน encrypt / หลัง decrypt
// ได้ทุก request + response โดยไม่ต้องสน TLS pin
//
// usage (ATTACH mode — เลี่ยง anti-frida ที่เตะตอน spawn):
//   1) เปิด LGR ใน MuMu ให้ถึงหน้า title ก่อน
//   2) แล้วค่อยรัน:
//      frida -U -n com.linecorp.LGRGS -l api/frida_native_ssl.js

var HOSTS = ['axelth', 'linega', 'linecorp', 'ranger'];
var MAX_LEN = 4096;

function hexdump_safe(ptr, len) {
    try {
        return hexdump(ptr, { length: Math.min(len, 256), ansi: false });
    } catch (e) { return '<unreadable>'; }
}

function looks_like_http(buf, len) {
    if (len < 4) return false;
    try {
        var head = Memory.readCString(buf, 8) || '';
        return /^(GET |POST|PUT |HEAD|DELE|PATC|OPTI|HTTP)/.test(head);
    } catch (e) { return false; }
}

function try_decode(buf, len) {
    try { return Memory.readUtf8String(buf, Math.min(len, MAX_LEN)); }
    catch (e) {
        try { return Memory.readCString(buf, Math.min(len, MAX_LEN)); }
        catch (e2) { return '<bin len=' + len + '>'; }
    }
}

function host_match(txt) {
    if (!txt) return false;
    for (var i = 0; i < HOSTS.length; i++) if (txt.indexOf(HOSTS[i]) >= 0) return true;
    return false;
}

function hook_lib(libname) {
    var mod = Process.findModuleByName(libname);
    if (!mod) return false;

    var ssl_write = Module.findExportByName(libname, 'SSL_write');
    var ssl_read  = Module.findExportByName(libname, 'SSL_read');

    if (!ssl_write || !ssl_read) return false;

    Interceptor.attach(ssl_write, {
        onEnter: function (args) {
            try {
                var buf = args[1]; var len = args[2].toInt32();
                if (len <= 0) return;
                var text = try_decode(buf, len);
                if (looks_like_http(buf, len) || host_match(text)) {
                    send('[TX ' + libname + '] len=' + len + '\n' + text.substring(0, MAX_LEN));
                }
            } catch (e) {}
        }
    });

    Interceptor.attach(ssl_read, {
        onEnter: function (args) {
            this.buf = args[1];
        },
        onLeave: function (retval) {
            try {
                var n = retval.toInt32();
                if (n <= 0) return;
                var text = try_decode(this.buf, n);
                if (looks_like_http(this.buf, n) || host_match(text)) {
                    send('[RX ' + libname + '] len=' + n + '\n' + text.substring(0, MAX_LEN));
                }
            } catch (e) {}
        }
    });
    send('[+] hooked SSL_write / SSL_read in ' + libname);
    return true;
}

// ---------- anti-anti-frida (เบาๆ) ----------
try {
    var Debug = Java.use('android.os.Debug');
    Debug.isDebuggerConnected.implementation = function () { return false; };
} catch (e) {}

// ---------- รอให้ libssl load เสร็จก่อน hook ----------
function wait_and_hook() {
    var tries = 0;
    var tick = setInterval(function () {
        tries++;
        var hit = false;
        ['libssl.so', 'libcronet.so', 'libboringssl.so',
         'libcocos2djs.so', 'libgame.so', 'libnative-lib.so'].forEach(function (n) {
            if (hook_lib(n)) hit = true;
        });
        if (hit || tries > 40) {
            clearInterval(tick);
            if (!hit) send('[-] no SSL export found in common libs — เปิด Modules list');
        }
    }, 500);
}

if (Java.available) {
    Java.perform(function () { wait_and_hook(); });
} else {
    wait_and_hook();
}

// ---------- list all loaded modules (ครั้งเดียว) เพื่อหา lib ที่ใช้จริง ----------
setTimeout(function () {
    var mods = Process.enumerateModules();
    var interesting = mods.filter(function (m) {
        var n = m.name.toLowerCase();
        return n.indexOf('ssl') >= 0 || n.indexOf('crypto') >= 0 ||
               n.indexOf('cronet') >= 0 || n.indexOf('curl') >= 0 ||
               n.indexOf('cocos') >= 0 || n.indexOf('native') >= 0 ||
               n.indexOf('game') >= 0 || n.indexOf('lgr') >= 0;
    });
    send('[MODULES] ' + JSON.stringify(interesting.map(function (m) {
        return { name: m.name, base: m.base.toString(), size: m.size };
    }), null, 2));
}, 3000);
