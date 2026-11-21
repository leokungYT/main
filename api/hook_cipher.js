// Hook javax.crypto.Cipher + SecretKeySpec to dump AES key + plaintext.
// Triggers when game decrypts _ENC_LF_AC_KEY during login.
'use strict';

function toHex(bytes) {
    let s = '';
    for (let i = 0; i < bytes.length; i++) s += ('0' + (bytes[i] & 0xff).toString(16)).slice(-2);
    return s;
}
function bytesToAscii(bytes) {
    let s = '';
    for (let i = 0; i < bytes.length; i++) {
        const b = bytes[i] & 0xff;
        s += (b >= 0x20 && b < 0x7f) ? String.fromCharCode(b) : '.';
    }
    return s;
}

function waitForJava(cb) {
    if (typeof Java !== 'undefined' && Java.available) { cb(); return; }
    setTimeout(function(){ waitForJava(cb); }, 100);
}

waitForJava(function(){ Java.perform(function () {
    console.log('[+] Java hooks loading...');

    // 1) SecretKeySpec constructor — captures every AES key material + algorithm
    try {
        const SKS = Java.use('javax.crypto.spec.SecretKeySpec');
        SKS.$init.overload('[B', 'java.lang.String').implementation = function (key, algo) {
            const kb = Java.array('byte', key);
            console.log('[SecretKeySpec] algo=' + algo + ' len=' + kb.length);
            console.log('    key hex = ' + toHex(kb));
            console.log('    key ascii= ' + bytesToAscii(kb));
            return this.$init(key, algo);
        };
        SKS.$init.overload('[B', 'int', 'int', 'java.lang.String').implementation = function (key, off, len, algo) {
            const kb = Java.array('byte', key);
            console.log('[SecretKeySpec+off] algo=' + algo + ' len=' + len);
            console.log('    key hex = ' + toHex(kb.slice(off, off + len)));
            return this.$init(key, off, len, algo);
        };
        console.log('[+] SecretKeySpec hooked');
    } catch (e) { console.log('[-] SecretKeySpec hook failed: ' + e); }

    // 2) IvParameterSpec — captures AES IVs
    try {
        const IVS = Java.use('javax.crypto.spec.IvParameterSpec');
        IVS.$init.overload('[B').implementation = function (iv) {
            const b = Java.array('byte', iv);
            console.log('[IvParameterSpec] iv = ' + toHex(b));
            return this.$init(iv);
        };
        console.log('[+] IvParameterSpec hooked');
    } catch (e) { console.log('[-] IvParameterSpec hook failed: ' + e); }

    // 3) Cipher.doFinal(byte[]) — the actual decrypt call
    try {
        const Cipher = Java.use('javax.crypto.Cipher');

        Cipher.doFinal.overload('[B').implementation = function (input) {
            const inB = Java.array('byte', input);
            const result = this.doFinal(input);
            const outB = Java.array('byte', result);
            const algo = this.getAlgorithm();
            // only log if input looks like our target (304 bytes = size of _ENC_LF_AC_KEY blob)
            if (inB.length >= 32 && inB.length <= 2048) {
                console.log('[Cipher.doFinal] algo=' + algo
                    + ' in_len=' + inB.length + ' out_len=' + outB.length);
                console.log('    in_hex[:32]  = ' + toHex(inB.slice(0, 32)));
                console.log('    out_hex[:64] = ' + toHex(outB.slice(0, Math.min(64, outB.length))));
                console.log('    out_ascii    = ' + bytesToAscii(outB.slice(0, Math.min(200, outB.length))));
            }
            return result;
        };

        Cipher.doFinal.overload('[B', 'int', 'int').implementation = function (input, off, len) {
            const inB = Java.array('byte', input);
            const result = this.doFinal(input, off, len);
            const outB = Java.array('byte', result);
            const algo = this.getAlgorithm();
            if (len >= 32 && len <= 2048) {
                console.log('[Cipher.doFinal+off] algo=' + algo + ' in_len=' + len + ' out_len=' + outB.length);
                console.log('    in_hex[:32]  = ' + toHex(inB.slice(off, off + Math.min(32, len))));
                console.log('    out_ascii    = ' + bytesToAscii(outB.slice(0, Math.min(200, outB.length))));
            }
            return result;
        };
        console.log('[+] Cipher.doFinal hooked (2 overloads)');
    } catch (e) { console.log('[-] Cipher hook failed: ' + e); }

    // 4) SharedPreferences.getString — catches when game reads _ENC_LF_AC_KEY from XML
    try {
        const SPImpl = Java.use('android.app.SharedPreferencesImpl');
        SPImpl.getString.implementation = function (key, dflt) {
            const v = this.getString(key, dflt);
            if (key && (key.indexOf('LF_AC') >= 0 || key.indexOf('_ENC_') >= 0)) {
                console.log('[SharedPrefs.getString] key=' + key
                    + ' value[:50]=' + (v ? String(v).substring(0, 50) : 'null'));
            }
            return v;
        };
        console.log('[+] SharedPreferences.getString hooked');
    } catch (e) { console.log('[-] SharedPreferences hook failed: ' + e); }

    console.log('[+] All hooks installed. Trigger login in the game.');
});});
