// Hook OpenSSL AES_* functions in libgame.so to dump key + plaintext.
'use strict';

function hex(ptr, len) {
    try { return new Uint8Array(ptr.readByteArray(len)).reduce((s,b)=>s+('0'+b.toString(16)).slice(-2),''); }
    catch(e) { return '<unreadable>'; }
}
function ascii(ptr, len) {
    try {
        const arr = new Uint8Array(ptr.readByteArray(len));
        let s = '';
        for (const b of arr) s += (b>=0x20 && b<0x7f) ? String.fromCharCode(b) : '.';
        return s;
    } catch(e) { return '<unreadable>'; }
}

function tryHook(libName) {
    const mod = Process.findModuleByName(libName);
    if (!mod) { console.log('[-] module not loaded: ' + libName); return false; }
    console.log('[+] module ' + libName + ' @ ' + mod.base + ' size=' + mod.size);

    const targets = ['AES_set_decrypt_key', 'AES_cbc_encrypt', 'AES_decrypt',
                     'EVP_DecryptUpdate', 'EVP_DecryptFinal_ex',
                     'EVP_DecryptInit_ex', 'EVP_CipherInit_ex'];
    let hooked = 0;
    for (const sym of targets) {
        let addr = null;
        try { addr = mod.findExportByName ? mod.findExportByName(sym) : null; } catch(e) {}
        if (!addr) {
            try { addr = Process.getModuleByName(libName).findExportByName(sym); } catch(e) {}
        }
        if (!addr) continue;
        console.log('[+] found ' + sym + ' @ ' + addr);
        hooked++;

        if (sym === 'AES_set_decrypt_key') {
            // int AES_set_decrypt_key(const unsigned char *userKey, int bits, AES_KEY *key)
            Interceptor.attach(addr, {
                onEnter(args) {
                    const bits = args[1].toInt32();
                    const kLen = bits / 8;
                    console.log('[AES_set_decrypt_key] bits=' + bits + ' key_hex=' + hex(args[0], kLen));
                }
            });
        } else if (sym === 'AES_cbc_encrypt') {
            // void AES_cbc_encrypt(in, out, length, key, ivec, enc)
            Interceptor.attach(addr, {
                onEnter(args) {
                    this.out = args[1];
                    this.len = args[2].toInt32();
                    this.iv = args[4];
                    this.enc = args[5].toInt32();
                    if (this.len >= 32 && this.len <= 4096) {
                        console.log('[AES_cbc_encrypt] enc=' + this.enc + ' len=' + this.len
                            + ' iv=' + hex(this.iv, 16));
                        console.log('    in_hex[:32] = ' + hex(args[0], Math.min(32, this.len)));
                    }
                },
                onLeave() {
                    if (this.len >= 32 && this.len <= 4096 && this.enc === 0) {
                        console.log('    out_hex[:64]  = ' + hex(this.out, Math.min(64, this.len)));
                        console.log('    out_ascii[:200] = ' + ascii(this.out, Math.min(200, this.len)));
                    }
                }
            });
        } else if (sym === 'AES_decrypt') {
            // void AES_decrypt(in[16], out[16], key)
            Interceptor.attach(addr, {
                onEnter(args) { this.out = args[1]; },
                onLeave() {
                    const s = ascii(this.out, 16);
                    if (/[a-zA-Z]{4,}/.test(s)) console.log('[AES_decrypt] out_ascii = ' + s);
                }
            });
        } else if (sym === 'EVP_DecryptUpdate' || sym === 'EVP_DecryptFinal_ex') {
            Interceptor.attach(addr, {
                onEnter(args) {
                    this.out = args[1];
                    this.outLenPtr = args[2];
                    this.in = args[3] || null;
                    this.inLen = args[4] ? args[4].toInt32() : 0;
                },
                onLeave(ret) {
                    try {
                        const outLen = this.outLenPtr.readInt();
                        if (outLen >= 16 && outLen <= 4096) {
                            console.log('[' + sym + '] out_len=' + outLen);
                            console.log('    out_ascii[:200] = ' + ascii(this.out, Math.min(200, outLen)));
                        }
                    } catch(e) {}
                }
            });
        } else if (sym === 'EVP_DecryptInit_ex' || sym === 'EVP_CipherInit_ex') {
            // EVP_DecryptInit_ex(ctx, cipher, impl, key, iv) — key is arg[3], iv arg[4]
            Interceptor.attach(addr, {
                onEnter(args) {
                    const keyPtr = args[3];
                    const ivPtr = args[4];
                    if (!keyPtr.isNull()) {
                        console.log('[' + sym + '] key_hex[:32] = ' + hex(keyPtr, 32));
                    }
                    if (ivPtr && !ivPtr.isNull()) {
                        console.log('    iv_hex[:16] = ' + hex(ivPtr, 16));
                    }
                }
            });
        }
    }
    console.log('[+] hooked ' + hooked + ' functions in ' + libName);
    return hooked > 0;
}

function tryAll() {
    const libs = ['libcrypto.so', 'libgame.so', 'libjavacrypto.so',
                  'libchromview_android.so', 'libsqlcipher.so',
                  'libtrident.so', 'libLGRGS.so'];
    let any = false;
    for (const l of libs) if (tryHook(l)) any = true;
    return any;
}

// hook what's available NOW (libcrypto is already loaded).
// then keep trying for libgame/libtrident as they dlopen.
const hookedLibs = new Set();

function tryAllOnce() {
    const libs = ['libcrypto.so', 'libgame.so', 'libjavacrypto.so',
                  'libchromview_android.so', 'libsqlcipher.so',
                  'libtrident.so', 'libLGRGS.so'];
    for (const l of libs) {
        if (hookedLibs.has(l)) continue;
        const mod = Process.findModuleByName(l);
        if (!mod) continue;
        if (tryHook(l)) hookedLibs.add(l);
    }
}

tryAllOnce();
let tries = 0;
const iv = setInterval(function(){
    tries++;
    tryAllOnce();
    if (tries > 120) {
        clearInterval(iv);
        console.log('[*] poll ended. Hooked libs: ' + Array.from(hookedLibs).join(','));
    }
}, 1000);
