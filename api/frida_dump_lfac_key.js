// frida_dump_lfac_key.js
// hook decrypt functions ใน Line Rangers เพื่อดักกุญแจตอน app ถอด _ENC_LF_AC_KEY
//
// วิธีใช้ (MuMu root + frida-server):
//   1. ส่ง frida-server ลงเครื่อง (ครั้งเดียว)
//   2. frida -U -f com.linecorp.LGRGS -l frida_dump_lfac_key.js --no-pause
//   3. รอจน login (เกมถอด LF_AC) -> script พิมพ์ key + sample ciphertext
//
// สิ่งที่ได้: 16-byte key (hex) + verify ด้วย ciphertext ที่ตรงกับ _ENC_LF_AC_KEY ใน xml

'use strict';

// ---------- helpers ----------
function bufToHex(ptr, len) {
    const bytes = new Uint8Array(ptr.readByteArray(len));
    return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}
function bufToAscii(ptr, len) {
    const bytes = new Uint8Array(ptr.readByteArray(len));
    return Array.from(bytes).map(b => (b >= 32 && b < 127) ? String.fromCharCode(b) : '.').join('');
}

// ---------- native hook (Cocos XXTEA / custom AES) ----------
function hookNative() {
    const mods = Process.enumerateModules().filter(m =>
        m.name.includes('cocos') || m.name.includes('LGR') || m.name.includes('trident')
    );
    console.log('[*] libs:', mods.map(m => m.name).join(', '));

    // candidate function names ที่ Cocos / game ใช้
    const patterns = [
        'xxtea_decrypt', 'xxteaDecrypt', '_Z14xxtea_decrypt',
        'AES_decrypt', 'EVP_DecryptUpdate', 'EVP_aes_128_cbc',
        'decryptLFAC', 'decryptLfAc', 'decrypt_lf_ac',
        'cipher_decrypt', 'decryptString',
    ];

    mods.forEach(mod => {
        const syms = Module.enumerateSymbolsSync(mod.name);
        syms.filter(s =>
            patterns.some(p => s.name.toLowerCase().includes(p.toLowerCase())) ||
            s.name.toLowerCase().includes('decrypt')
        ).forEach(sym => {
            try {
                Interceptor.attach(sym.address, {
                    onEnter(args) {
                        this.name = sym.name;
                        this.a0 = args[0]; this.a1 = args[1];
                        this.a2 = args[2]; this.a3 = args[3];
                        this.a4 = args[4];
                    },
                    onLeave(ret) {
                        try {
                            // dump arg 0..4 อย่างปลอดภัย (16 bytes) + key candidate arg[3] (XXTEA key = 16 bytes)
                            const dump = (p, n) => p && !p.isNull() ? `${bufToHex(p, n)} | ${bufToAscii(p, n)}` : 'null';
                            console.log(`\n[hook] ${this.name}`);
                            console.log('  arg0:', dump(this.a0, 32));
                            console.log('  arg1:', dump(this.a1, 32));
                            console.log('  arg2:', dump(this.a2, 16));
                            console.log('  arg3 (KEY?):', dump(this.a3, 16));
                            console.log('  arg4:', dump(this.a4, 16));
                        } catch (e) { /* skip */ }
                    }
                });
                console.log('[+] hooked native:', sym.name, '@', sym.address);
            } catch (e) { /* skip */ }
        });
    });
}

// ---------- Java hook (SharedPreferences read + possible AES in Java) ----------
function hookJava() {
    Java.perform(() => {
        // scan class ที่น่าจะถอด LF_AC
        Java.enumerateLoadedClasses({
            onMatch(name) {
                if (name.toLowerCase().includes('lf_ac') ||
                    name.toLowerCase().includes('crypto') ||
                    name.toLowerCase().includes('encryption') ||
                    name.includes('linecorp.LGR')) {
                    console.log('[class]', name);
                }
            },
            onComplete() {}
        });

        // hook SharedPreferences.getString เพื่อจับตอนอ่าน _ENC_LF_AC_KEY
        try {
            const SP = Java.use('android.app.SharedPreferencesImpl');
            SP.getString.implementation = function (key, def) {
                const val = this.getString(key, def);
                if (key && (key.includes('LF_AC') || key.includes('ENC'))) {
                    console.log('[SP.getString]', key, '=', val ? val.substring(0, 60) + '...' : null);
                }
                return val;
            };
            console.log('[+] hooked SharedPreferences.getString');
        } catch (e) { console.log('[SP hook fail]', e); }

        // hook javax.crypto.Cipher.doFinal (ดัก AES ใน Java)
        try {
            const Cipher = Java.use('javax.crypto.Cipher');
            Cipher.doFinal.overload('[B').implementation = function (input) {
                const algo = this.getAlgorithm();
                const out = this.doFinal(input);
                if (algo && (algo.toLowerCase().includes('aes') || algo.toLowerCase().includes('des'))) {
                    const preview = out && out.length > 0 ?
                        Java.use('java.lang.String').$new(out, 'UTF-8') : '(empty)';
                    const inHex = Array.prototype.map.call(input.slice(0, 32),
                        b => (b & 0xff).toString(16).padStart(2, '0')).join('');
                    console.log(`\n[Cipher.doFinal algo=${algo}]`);
                    console.log('  input[:32] hex:', inHex);
                    console.log('  output str  :', String(preview).substring(0, 100));
                }
                return out;
            };
            console.log('[+] hooked Cipher.doFinal');
        } catch (e) { console.log('[Cipher hook fail]', e); }

        // hook SecretKeySpec constructor (เห็น key ตรงๆ)
        try {
            const SKS = Java.use('javax.crypto.spec.SecretKeySpec');
            SKS.$init.overload('[B', 'java.lang.String').implementation = function (keyBytes, algo) {
                const hex = Array.prototype.map.call(keyBytes,
                    b => (b & 0xff).toString(16).padStart(2, '0')).join('');
                const ascii = Array.prototype.map.call(keyBytes,
                    b => (b >= 32 && b < 127) ? String.fromCharCode(b) : '.').join('');
                console.log(`\n[SecretKeySpec ${algo}] key hex=${hex}  ascii=${ascii}`);
                return this.$init(keyBytes, algo);
            };
            console.log('[+] hooked SecretKeySpec');
        } catch (e) { console.log('[SKS hook fail]', e); }
    });
}

// ---------- entry ----------
setTimeout(() => {
    console.log('==== LFAC KEY DUMPER ====');
    hookJava();
    hookNative();
}, 500);
