// frida_dump_hardened.js
// run:  frida -D 127.0.0.1:7555 -f com.linecorp.LGRGS -l frida_dump_hardened.js
//
// LIAPP v5 ฆ่า process ถ้าเจอ frida. script นี้ hook ทางออกทุกบานก่อน
// แล้วค่อย hook Java crypto ต่อ. ยิง exit/abort/kill/Process.killProcess = no-op.
//
// output ที่ต้องรอ:
//   [SecretKeySpec AES] len=16 hex=<32HEX>  ascii=<ascii>
//   [IvParameterSpec]   hex=<32HEX>

'use strict';

// ===== ด่านแรก: ตัดทางให้ LIAPP ฆ่า process =====
(function neuterExit() {
    const names = ['exit', '_exit', 'abort', 'raise', 'kill', 'tgkill', 'pthread_exit'];
    for (const nm of names) {
        try {
            const p = Module.findExportByName(null, nm);
            if (!p) continue;
            Interceptor.replace(p, new NativeCallback(function () {
                console.log('[neutered] ' + nm + ' called — blocked');
                return 0;
            }, 'int', []));
            console.log('[+] neutered ' + nm);
        } catch (e) { /* skip */ }
    }
    // บางเวอร์ชัน LIAPP ส่ง SIGKILL ผ่าน syscall ตรง — ไม่สน (ใน emu ไม่ค่อยเจอ)
})();

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

Java.perform(function () {
    console.log('==== LFAC KEY DUMPER (hardened) ====');

    // ===== ด่านสอง: ตัด LIAPP ฝั่ง Java =====
    safe('android.os.Process.killProcess neutered', function () {
        const P = Java.use('android.os.Process');
        P.killProcess.implementation = function (pid) {
            console.log('[neutered] Process.killProcess(' + pid + ')');
        };
    });
    safe('java.lang.Runtime.exit neutered', function () {
        const R = Java.use('java.lang.Runtime');
        R.exit.implementation = function (code) {
            console.log('[neutered] Runtime.exit(' + code + ')');
        };
    });
    safe('java.lang.System.exit neutered', function () {
        const S = Java.use('java.lang.System');
        S.exit.implementation = function (code) {
            console.log('[neutered] System.exit(' + code + ')');
        };
    });

    // ===== ด่านสาม: Java crypto hooks =====
    safe('SecretKeySpec', function () {
        const KS = Java.use('javax.crypto.spec.SecretKeySpec');
        KS.$init.overload('[B', 'java.lang.String').implementation = function (key, algo) {
            console.log('[SecretKeySpec ' + algo + '] len=' + key.length +
                        ' hex=' + hex(key) + ' ascii=' + ascii(key));
            return this.$init(key, algo);
        };
    });

    safe('IvParameterSpec', function () {
        const IV = Java.use('javax.crypto.spec.IvParameterSpec');
        IV.$init.overload('[B').implementation = function (iv) {
            console.log('[IvParameterSpec] len=' + iv.length + ' hex=' + hex(iv));
            return this.$init(iv);
        };
    });

    safe('Cipher.init(Key)', function () {
        const C = Java.use('javax.crypto.Cipher');
        C.init.overload('int', 'java.security.Key').implementation = function (op, k) {
            try {
                const enc = k.getEncoded();
                if (enc) console.log('[Cipher.init op=' + op + ' algo=' + this.getAlgorithm() +
                                     '] key hex=' + hex(enc) + ' ascii=' + ascii(enc));
            } catch (_) {}
            return this.init(op, k);
        };
        C.init.overload('int', 'java.security.Key', 'java.security.spec.AlgorithmParameterSpec').implementation = function (op, k, p) {
            try {
                const enc = k.getEncoded();
                if (enc) console.log('[Cipher.init+iv op=' + op + ' algo=' + this.getAlgorithm() +
                                     '] key hex=' + hex(enc));
            } catch (_) {}
            return this.init(op, k, p);
        };
    });

    safe('Cipher.doFinal', function () {
        const C = Java.use('javax.crypto.Cipher');
        C.doFinal.overload('[B').implementation = function (input) {
            const out = this.doFinal(input);
            console.log('[Cipher.doFinal algo=' + this.getAlgorithm() +
                        '] in[' + input.length + ']=' + hex(input).substring(0, 64) +
                        ' out[' + out.length + ']=' + hex(out).substring(0, 64) +
                        ' asciiOut=' + ascii(out).substring(0, 40));
            return out;
        };
    });

    safe('SharedPreferences.getString', function () {
        const SP = Java.use('android.app.SharedPreferencesImpl');
        SP.getString.implementation = function (k, d) {
            const v = this.getString(k, d);
            if (v && (k.indexOf('LF_AC') >= 0 || k.indexOf('ENC') >= 0 ||
                      k.indexOf('udid') >= 0 || k.indexOf('UDID') >= 0 ||
                      k.indexOf('COCOS') >= 0)) {
                console.log('[SP.getString] k=' + k + ' v=' + (v ? v.substring(0, 80) : 'null'));
            }
            return v;
        };
    });

    // ===== ด่านสี่: SimpleCrypto (Cocos helper ของ LGR) =====
    safe('SimpleCrypto widenet', function () {
        const SC = Java.use('org.cocos2dx.lib.linecocos.utils.SimpleCrypto');
        const methods = SC.class.getDeclaredMethods();
        for (let i = 0; i < methods.length; i++) {
            const name = methods[i].getName();
            try {
                const overloads = SC[name].overloads;
                for (let k = 0; k < overloads.length; k++) {
                    (function (ov, nm) {
                        ov.implementation = function () {
                            const args = [];
                            for (let a = 0; a < arguments.length; a++) {
                                const v = arguments[a];
                                if (v === null) { args.push('null'); continue; }
                                if (typeof v === 'string') { args.push('"' + v.substring(0, 60) + '"'); continue; }
                                try {
                                    if (v.length !== undefined && typeof v[0] === 'number') {
                                        args.push('bytes[' + v.length + ']=' + hex(v).substring(0, 64));
                                    } else {
                                        args.push(String(v).substring(0, 60));
                                    }
                                } catch (_) { args.push(String(v).substring(0, 60)); }
                            }
                            const ret = ov.apply(this, arguments);
                            let rs = '<ret>';
                            try {
                                if (ret === null) rs = 'null';
                                else if (typeof ret === 'string') rs = '"' + ret.substring(0, 120) + '"';
                                else if (ret.length !== undefined && typeof ret[0] === 'number')
                                    rs = 'bytes[' + ret.length + ']=' + hex(ret).substring(0, 80);
                                else rs = String(ret).substring(0, 120);
                            } catch (_) {}
                            console.log('[SimpleCrypto.' + nm + '] ' + args.join(', ') + ' -> ' + rs);
                            return ret;
                        };
                    })(overloads[k], name);
                }
            } catch (_) {}
        }
    });

    console.log('==== hooks live, LIAPP neutered. open game -> lobby ====');
});
