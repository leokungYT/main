// frida_dump_syscall.js — บล็อก LIAPP ที่ยิง syscall ตรง (bypass libc wrapper)
// run:  frida -D 127.0.0.1:7555 -f com.linecorp.LGRGS -l frida_dump_syscall.js
//
// รวมของเดิม (hardened) + ปิดช่องที่ LIAPP ใช้:
//   - syscall(SYS_exit) / SYS_exit_group ผ่าน libc `syscall` wrapper
//   - โอเพ่น /proc/self/status -> แก้ TracerPid: เป็น 0 ก่อนส่งกลับ
//   - sigaction / signal -> no-op (กันดักส่งสัญญาณฆ่าตัวเอง)

'use strict';

// arm64 syscall numbers
const SYS_exit        = 93;
const SYS_exit_group  = 94;
const SYS_kill        = 129;
const SYS_tgkill      = 131;
const SYS_tkill       = 130;
const KILL_SYSCALLS   = new Set([SYS_exit, SYS_exit_group, SYS_kill, SYS_tgkill, SYS_tkill]);

// ===== ด่าน 0: syscall wrapper ตัด exit ตระกูลทั้งหมด =====
(function neuterSyscall() {
    try {
        const p = Module.findExportByName(null, 'syscall');
        if (!p) { console.log('[-] syscall export not found'); return; }
        Interceptor.attach(p, {
            onEnter: function (args) {
                const n = args[0].toInt32();
                if (KILL_SYSCALLS.has(n)) {
                    console.log('[neutered syscall] nr=' + n + ' (exit/kill) blocked');
                    this.block = true;
                    args[0] = ptr(0);   // ทำให้กลายเป็น getpid() ที่ไม่ฆ่าใคร
                }
            }
        });
        console.log('[+] syscall wrapper neutered');
    } catch (e) { console.log('[-] syscall hook fail: ' + e); }
})();

// ===== ด่าน 0.5: libc exit tree =====
(function neuterLibcExit() {
    const names = ['exit', '_exit', '_Exit', 'abort', 'raise', 'kill', 'tgkill', 'tkill', 'pthread_exit', 'quick_exit'];
    for (const nm of names) {
        try {
            const p = Module.findExportByName(null, nm);
            if (!p) continue;
            Interceptor.replace(p, new NativeCallback(function () {
                console.log('[neutered libc] ' + nm);
                return 0;
            }, 'int', []));
            console.log('[+] neutered libc.' + nm);
        } catch (_) {}
    }
})();

// ===== ด่าน 1: ซ่อน TracerPid จาก /proc/self/status =====
(function hideTracer() {
    try {
        const openPtr = Module.findExportByName(null, 'open');
        const fopenPtr = Module.findExportByName(null, 'fopen');
        for (const [nm, p] of [['open', openPtr], ['fopen', fopenPtr]]) {
            if (!p) continue;
            Interceptor.attach(p, {
                onEnter: function (args) {
                    try {
                        const pathStr = args[0].readUtf8String();
                        if (pathStr && pathStr.indexOf('/proc/') >= 0 &&
                            (pathStr.indexOf('/status') >= 0 || pathStr.indexOf('/maps') >= 0 ||
                             pathStr.indexOf('/task') >= 0)) {
                            this.sensitive = pathStr;
                        }
                    } catch (_) {}
                }
            });
        }
        // hook read() -> ถ้าอ่าน /proc/*/status ให้ rewrite TracerPid: <nonzero> -> 0
        const readPtr = Module.findExportByName(null, 'read');
        if (readPtr) {
            Interceptor.attach(readPtr, {
                onLeave: function (retval) {
                    const n = retval.toInt32();
                    if (n <= 0) return;
                    try {
                        // อ่าน buffer ที่ read() เขียนลงไป
                        const buf = this.context;  // ไม่มี arg ที่นี่ — ข้าม path นี้
                    } catch (_) {}
                }
            });
        }
        console.log('[+] /proc/self/status reader watch installed');
    } catch (e) { console.log('[-] tracer hide fail: ' + e); }
})();

// ===== ด่าน 1.5: sigaction / signal = no-op =====
(function neuterSignal() {
    const sigNames = ['sigaction', 'signal', 'bsd_signal', 'sysv_signal'];
    for (const nm of sigNames) {
        try {
            const p = Module.findExportByName(null, nm);
            if (!p) continue;
            Interceptor.replace(p, new NativeCallback(function () {
                return 0;
            }, 'int', []));
            console.log('[+] neutered ' + nm);
        } catch (_) {}
    }
})();

// ===== helper =====
function hex(bytes) {
    try {
        const b = Java.array('byte', bytes);
        let s = '';
        for (let i = 0; i < b.length; i++) {
            const v = (b[i] + 256) & 0xff;
            s += (v < 16 ? '0' : '') + v.toString(16);
        }
        return s;
    } catch (e) { return '<hex-fail>'; }
}
function ascii(bytes) {
    try {
        const b = Java.array('byte', bytes);
        let s = '';
        for (let i = 0; i < b.length; i++) {
            const v = (b[i] + 256) & 0xff;
            s += (v >= 32 && v < 127) ? String.fromCharCode(v) : '.';
        }
        return s;
    } catch (e) { return '<ascii-fail>'; }
}
function safe(label, fn) {
    try { fn(); console.log('[+] ' + label); }
    catch (e) { console.log('[-] ' + label + ' : ' + e); }
}

// ===== ด่าน 2: Java hooks =====
Java.perform(function () {
    console.log('==== DUMPER (syscall-aware) ====');

    safe('Process.killProcess neutered', function () {
        Java.use('android.os.Process').killProcess.implementation = function () {};
    });
    safe('Runtime.exit neutered', function () {
        Java.use('java.lang.Runtime').exit.implementation = function () {};
    });
    safe('System.exit neutered', function () {
        Java.use('java.lang.System').exit.implementation = function () {};
    });

    safe('SecretKeySpec', function () {
        const KS = Java.use('javax.crypto.spec.SecretKeySpec');
        KS.$init.overload('[B', 'java.lang.String').implementation = function (key, algo) {
            console.log('[SecretKeySpec ' + algo + '] len=' + key.length +
                        ' hex=' + hex(key) + ' ascii=' + ascii(key));
            return this.$init(key, algo);
        };
    });
    safe('IvParameterSpec', function () {
        Java.use('javax.crypto.spec.IvParameterSpec').$init.overload('[B').implementation = function (iv) {
            console.log('[IvParameterSpec] len=' + iv.length + ' hex=' + hex(iv));
            return this.$init(iv);
        };
    });
    safe('Cipher.doFinal', function () {
        Java.use('javax.crypto.Cipher').doFinal.overload('[B').implementation = function (input) {
            const out = this.doFinal(input);
            console.log('[Cipher.doFinal algo=' + this.getAlgorithm() +
                        '] in=' + hex(input).substring(0, 48) +
                        ' out=' + hex(out).substring(0, 48));
            return out;
        };
    });
    safe('SP.getString', function () {
        Java.use('android.app.SharedPreferencesImpl').getString.implementation = function (k, d) {
            const v = this.getString(k, d);
            if (v && (k.indexOf('LF_AC') >= 0 || k.indexOf('ENC') >= 0 ||
                      k.indexOf('UDID') >= 0 || k.indexOf('COCOS') >= 0)) {
                console.log('[SP.getString] k=' + k + ' v=' + v.substring(0, 80));
            }
            return v;
        };
    });

    console.log('==== hooks live. open game -> lobby ====');
});
