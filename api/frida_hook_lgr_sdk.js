// frida_hook_lgr_sdk.js
// targeted hook สำหรับ com.linecorp.linesdk.internal.security.encryption.*
// ใช้คู่กับ frida_dump_lfac_key.js (อันนี้ focus กว่า)

'use strict';

function bytesToHex(arr) {
    return Array.prototype.map.call(arr, b => (b & 0xff).toString(16).padStart(2, '0')).join('');
}
function bytesToAscii(arr) {
    return Array.prototype.map.call(arr, b => (b >= 32 && b < 127) ? String.fromCharCode(b & 0xff) : '.').join('');
}

Java.perform(() => {
    console.log('==== LGR SDK ENCRYPTION HOOKS ====');

    // 1. StringAesCipher — decrypt ที่เรียกใช้จริงตอน ถอด LF_AC
    try {
        const SAC = Java.use('com.linecorp.linesdk.internal.security.encryption.StringAesCipher');
        const methods = SAC.class.getDeclaredMethods();
        methods.forEach(m => {
            const name = m.getName();
            console.log('[StringAesCipher method]', m.toString());
            if (name === 'decrypt' || name === 'encrypt') {
                try {
                    SAC[name].overloads.forEach(ov => {
                        ov.implementation = function () {
                            const args = Array.from(arguments);
                            console.log(`\n>>> StringAesCipher.${name}(${args.length} args)`);
                            args.forEach((a, i) => console.log(`   arg[${i}]:`, String(a).substring(0, 200)));
                            const r = ov.apply(this, args);
                            console.log(`<<< result:`, String(r).substring(0, 200));
                            return r;
                        };
                    });
                    console.log(`[+] hooked StringAesCipher.${name}`);
                } catch (e) { console.log('err hook', name, e); }
            }
        });
    } catch (e) { console.log('[StringAesCipher fail]', e); }

    // 2. CipherData — เก็บ (iv + ciphertext) ที่ใช้
    try {
        const CD = Java.use('com.linecorp.linesdk.internal.security.encryption.CipherData');
        CD.$init.overloads.forEach(ov => {
            ov.implementation = function () {
                const args = Array.from(arguments);
                console.log('\n[CipherData.$init]');
                args.forEach((a, i) => {
                    try {
                        if (a && a.length !== undefined) {
                            const arr = Java.array('byte', a);
                            console.log(`   arg[${i}] bytes len=${arr.length} hex=${bytesToHex(arr).substring(0, 64)}`);
                        } else {
                            console.log(`   arg[${i}]:`, String(a).substring(0, 100));
                        }
                    } catch (e) { console.log(`   arg[${i}]: (uninspectable)`); }
                });
                return ov.apply(this, args);
            };
        });
        console.log('[+] hooked CipherData.$init');
    } catch (e) { console.log('[CipherData fail]', e); }

    // 3. EncryptorHolder — ที่เก็บ key / dispatcher
    try {
        const EH = Java.use('com.linecorp.linesdk.internal.EncryptorHolder');
        const methods = EH.class.getDeclaredMethods();
        methods.forEach(m => console.log('[EncryptorHolder method]', m.toString()));

        const fields = EH.class.getDeclaredFields();
        fields.forEach(f => console.log('[EncryptorHolder field]', f.toString()));
    } catch (e) { console.log('[EncryptorHolder fail]', e); }

    // 4. StringCipher — interface
    try {
        const SC = Java.use('com.linecorp.linesdk.internal.security.encryption.StringCipher');
        console.log('[StringCipher methods]');
        SC.class.getMethods().forEach(m => console.log('  ', m.toString()));
    } catch (e) { }

    // 5. SimpleCrypto (Cocos)
    try {
        const SimC = Java.use('org.cocos2dx.lib.linecocos.utils.SimpleCrypto');
        const methods = SimC.class.getDeclaredMethods();
        methods.forEach(m => {
            console.log('[SimpleCrypto method]', m.toString());
            const name = m.getName();
            if (name === 'encrypt' || name === 'decrypt') {
                try {
                    SimC[name].overloads.forEach(ov => {
                        ov.implementation = function () {
                            const args = Array.from(arguments);
                            console.log(`\n>>> SimpleCrypto.${name}(${args.length} args)`);
                            args.forEach((a, i) => console.log(`   arg[${i}]:`, String(a).substring(0, 200)));
                            const r = ov.apply(this, args);
                            console.log(`<<< result:`, String(r).substring(0, 200));
                            return r;
                        };
                    });
                    console.log(`[+] hooked SimpleCrypto.${name}`);
                } catch (e) { console.log('err', e); }
            }
        });
    } catch (e) { console.log('[SimpleCrypto fail]', e); }

    // 6. SharedPreferences.getString — จับ _ENC_LF_AC_KEY ตอนอ่าน
    try {
        const SP = Java.use('android.app.SharedPreferencesImpl');
        SP.getString.implementation = function (key, def) {
            const val = this.getString(key, def);
            if (key && (key.includes('LF_AC') || key.includes('ENC') || key.includes('UDID'))) {
                console.log('\n[SP.getString]', key, '=', val ? val.substring(0, 80) + '...' : 'null');
            }
            return val;
        };
        console.log('[+] hooked SharedPreferences.getString');
    } catch (e) { console.log('[SP hook fail]', e); }

    // 7. Cipher.doFinal (universal Java crypto)
    try {
        const Cipher = Java.use('javax.crypto.Cipher');
        Cipher.doFinal.overload('[B').implementation = function (input) {
            const algo = this.getAlgorithm();
            const out = this.doFinal(input);
            if (algo && (algo.toLowerCase().includes('aes') || algo.toLowerCase().includes('des'))) {
                const inHex = bytesToHex(input).substring(0, 64);
                let outStr = '';
                try { outStr = Java.use('java.lang.String').$new(out, 'UTF-8'); } catch (e) { outStr = '(bin)'; }
                console.log(`\n[Cipher.doFinal algo=${algo}]`);
                console.log(`   input[:32] hex: ${inHex}`);
                console.log(`   output str   : ${String(outStr).substring(0, 150)}`);
            }
            return out;
        };
        console.log('[+] hooked Cipher.doFinal');
    } catch (e) { console.log('[Cipher fail]', e); }

    // 8. SecretKeySpec — key constructor (เห็น key ตรงๆ)
    try {
        const SKS = Java.use('javax.crypto.spec.SecretKeySpec');
        SKS.$init.overload('[B', 'java.lang.String').implementation = function (keyBytes, algo) {
            const hex = bytesToHex(keyBytes);
            const ascii = bytesToAscii(keyBytes);
            console.log(`\n>>> SecretKeySpec [${algo}] len=${keyBytes.length}`);
            console.log(`   hex   : ${hex}`);
            console.log(`   ascii : ${ascii}`);
            return this.$init(keyBytes, algo);
        };
        console.log('[+] hooked SecretKeySpec');
    } catch (e) { console.log('[SKS fail]', e); }

    console.log('==== HOOKS INSTALLED ====');
});
