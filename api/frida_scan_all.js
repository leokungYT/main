// api/frida_scan_all.js
// scan ALL loaded modules + anti-anti-frida bypass
// cocos2d เกม static-link SSL ใน libgame.so / libcocos2djs.so

var HOSTS = ['axelth', 'linega', 'linecorp', 'ranger', 'line.me'];
var hooked = {};

// ============ ANTI-ANTI-FRIDA ============
// patch common detection: ptrace, TracerPid, /proc/self/maps scan, port 27042

try {
    // 1) ptrace(PTRACE_TRACEME) — ให้ล้มเหลว silently
    var ptrace = Module.findExportByName(null, 'ptrace');
    if (ptrace) {
        Interceptor.replace(ptrace, new NativeCallback(function () {
            return 0;
        }, 'long', ['int', 'int', 'pointer', 'pointer']));
    }

    // 2) fopen /proc/self/status, /proc/self/maps — filter TracerPid + frida/gum
    var fopen = Module.findExportByName('libc.so', 'fopen');
    var fgets = Module.findExportByName('libc.so', 'fgets');
    var fclose = Module.findExportByName('libc.so', 'fclose');
    if (fopen && fgets) {
        var tracked = {};
        Interceptor.attach(fopen, {
            onEnter: function (args) {
                try {
                    var p = Memory.readCString(args[0]);
                    this.path = p || '';
                } catch (e) { this.path = ''; }
            },
            onLeave: function (retval) {
                if (!retval.isNull() && this.path && (
                    this.path.indexOf('/proc/') >= 0 ||
                    this.path.indexOf('/maps') >= 0 ||
                    this.path.indexOf('/status') >= 0)) {
                    tracked[retval.toString()] = this.path;
                }
            }
        });
        Interceptor.attach(fgets, {
            onEnter: function (args) {
                this.buf = args[0];
                this.fp  = args[2];
            },
            onLeave: function (retval) {
                try {
                    if (retval.isNull()) return;
                    if (!tracked[this.fp.toString()]) return;
                    var line = Memory.readCString(this.buf);
                    if (!line) return;
                    if (line.indexOf('TracerPid') >= 0) {
                        Memory.writeUtf8String(this.buf, 'TracerPid:\t0\n');
                    } else if (line.indexOf('frida') >= 0 || line.indexOf('gum-js') >= 0 ||
                               line.indexOf('/fs') >= 0 || line.indexOf('gadget') >= 0) {
                        Memory.writeUtf8String(this.buf, '\n');
                    }
                } catch (e) {}
            }
        });
    }

    // 3) connect() to localhost:27042 (frida default port) — ให้ fail
    var connect = Module.findExportByName('libc.so', 'connect');
    if (connect) {
        Interceptor.attach(connect, {
            onEnter: function (args) {
                try {
                    var sa = args[1];
                    var port = (Memory.readU8(sa.add(2)) << 8) | Memory.readU8(sa.add(3));
                    if (port === 27042 || port === 27043) {
                        this.block = true;
                    }
                } catch (e) {}
            },
            onLeave: function (retval) {
                if (this.block) retval.replace(-1);
            }
        });
    }

    send('[+] anti-anti-frida installed (ptrace/proc/connect)');
} catch (e) {
    send('[-] anti-anti-frida failed: ' + e);
}

// ============ SSL SCANNER ============
function try_decode(buf, len) {
    try { return Memory.readUtf8String(buf, Math.min(len, 4096)); }
    catch (e) {
        try { return Memory.readCString(buf, Math.min(len, 4096)); }
        catch (e2) { return '<bin ' + len + 'b>'; }
    }
}

function is_interesting(txt) {
    if (!txt || txt.length < 4) return false;
    if (/^(GET |POST|PUT |HEAD|HTTP|\{)/.test(txt)) return true;
    for (var i = 0; i < HOSTS.length; i++) if (txt.indexOf(HOSTS[i]) >= 0) return true;
    return false;
}

function hook_at(name, write_addr, read_addr) {
    if (hooked[name]) return;
    hooked[name] = true;

    if (write_addr) Interceptor.attach(write_addr, {
        onEnter: function (args) {
            try {
                var len = args[2].toInt32();
                if (len <= 0 || len > 65536) return;
                var txt = try_decode(args[1], len);
                if (is_interesting(txt)) {
                    send('[TX ' + name + '] len=' + len + '\n' + txt.substring(0, 4096));
                }
            } catch (e) {}
        }
    });

    if (read_addr) Interceptor.attach(read_addr, {
        onEnter: function (args) { this.buf = args[1]; },
        onLeave: function (retval) {
            try {
                var n = retval.toInt32();
                if (n <= 0 || n > 65536) return;
                var txt = try_decode(this.buf, n);
                if (is_interesting(txt)) {
                    send('[RX ' + name + '] len=' + n + '\n' + txt.substring(0, 4096));
                }
            } catch (e) {}
        }
    });
    send('[+] hooked ' + name);
}

function scan_once() {
    Process.enumerateModules().forEach(function (m) {
        var w = Module.findExportByName(m.name, 'SSL_write');
        var r = Module.findExportByName(m.name, 'SSL_read');
        if (w || r) hook_at(m.name, w, r);
    });
}

scan_once();
setInterval(scan_once, 2000);

// ============ LIBC SOCKET FALLBACK ============
try {
    var sendfn = Module.findExportByName('libc.so', 'send');
    if (sendfn) Interceptor.attach(sendfn, {
        onEnter: function (args) {
            try {
                var len = args[2].toInt32();
                if (len < 50 || len > 8192) return;
                var txt = try_decode(args[1], len);
                if (is_interesting(txt)) {
                    send('[libc send] len=' + len + '\n' + txt.substring(0, 2048));
                }
            } catch (e) {}
        }
    });
} catch (e) {}

send('[+] scanner running — waiting for traffic');
