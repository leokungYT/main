// Scan Java heap for long base64-like strings that may be the decrypted userToken/guestCookie.
'use strict';

function waitJava(cb) {
    if (typeof Java !== 'undefined' && Java.available) { cb(); return; }
    setTimeout(() => waitJava(cb), 100);
}

waitJava(() => { Java.perform(() => {
    console.log('[*] enumerating java.lang.String instances...');
    const seen = new Set();
    let n = 0, hits = 0;

    const String_ = Java.use('java.lang.String');
    Java.choose('java.lang.String', {
        onMatch(obj) {
            n++;
            try {
                const s = Java.cast(obj, String_).toString();
                if (!s) return;
                const L = s.length;
                // base64-ish and 100-500 chars — our encrypted blob is ~408 chars
                if (L < 100 || L > 500) return;
                // allow typical base64 chars
                if (!/^[A-Za-z0-9+/=_\-]+$/.test(s)) return;
                if (seen.has(s)) return;
                seen.add(s);
                hits++;
                console.log(`[STR len=${L}] ${s.substring(0, 160)}${L > 160 ? '...' : ''}`);
                if (hits > 50) return 'stop';
            } catch(e) {}
        },
        onComplete() {
            console.log(`[*] scanned ${n} strings, ${hits} base64-ish matches`);
        }
    });
});});
