// Scan the game's memory for plaintext tokens that look like the decrypted userToken.
// _ENC_LF_AC_KEY is 304 bytes ciphertext → plaintext is likely a JSON or base64-ish blob.
// We look for common markers found in auth response: "userToken", "refreshUserToken", "guestCookie", userKey patterns.
'use strict';

const MARKERS = ['userToken', 'refreshUserToken', 'guestCookie', 'LF_AC', 'userKey',
                 '_ENC_LF_AC_KEY', 'LGRGS_Agreement'];

function scan() {
    const ranges = Process.enumerateRanges({protection: 'r--', coalesce: true});
    console.log('[*] scanning ' + ranges.length + ' readable ranges...');
    let found = 0;
    for (const r of ranges) {
        if (r.size > 64 * 1024 * 1024) continue; // skip huge regions
        for (const marker of MARKERS) {
            try {
                const matches = Memory.scanSync(r.base, r.size, marker.split('').map(c => c.charCodeAt(0).toString(16).padStart(2,'0')).join(' '));
                for (const m of matches) {
                    found++;
                    // dump context around match (200 bytes before + 400 after)
                    const before = m.address.sub(200);
                    try {
                        const ctx = before.readByteArray(600);
                        const arr = new Uint8Array(ctx);
                        let asciiStr = '';
                        for (const b of arr) asciiStr += (b>=0x20 && b<0x7f) ? String.fromCharCode(b) : '.';
                        console.log('[MATCH] ' + marker + ' @ ' + m.address + ' (range ' + r.base + ' +' + r.size + ')');
                        console.log('  ctx: ' + asciiStr);
                    } catch(e) {
                        console.log('[MATCH] ' + marker + ' @ ' + m.address + ' (ctx-fail: ' + e + ')');
                    }
                    if (found > 40) return;
                }
            } catch(e) {}
        }
    }
    console.log('[*] scan done. matches=' + found);
}

setTimeout(scan, 100);
