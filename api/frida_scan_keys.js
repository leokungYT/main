// frida_scan_keys.js
// scan Java heap หา instance ของ SecretKeySpec + SecretKey ที่ cache อยู่
// ไม่ต้อง restart app - ดึง key ที่โหลดไว้แล้วตอน app start

'use strict';

function hex(buf) {
    return Array.prototype.map.call(buf, b => (b & 0xff).toString(16).padStart(2, '0')).join('');
}
function ascii(buf) {
    return Array.prototype.map.call(buf, b => (b >= 32 && b < 127) ? String.fromCharCode(b & 0xff) : '.').join('');
}

Java.perform(() => {
    console.log('\n==== HEAP KEY SCAN ====\n');

    // 1. ทุก SecretKeySpec instance ใน heap
    console.log('[1] scanning SecretKeySpec instances...');
    try {
        Java.choose('javax.crypto.spec.SecretKeySpec', {
            onMatch(inst) {
                try {
                    const algo = inst.getAlgorithm();
                    const enc = inst.getEncoded();
                    const h = hex(enc);
                    const a = ascii(enc);
                    console.log(`[SecretKeySpec] algo=${algo} len=${enc.length}`);
                    console.log(`   hex   : ${h}`);
                    console.log(`   ascii : ${a}`);
                } catch (e) { }
            },
            onComplete() { console.log('[1] done'); }
        });
    } catch (e) { console.log('[1 err]', e); }

    // 2. StringAesCipher instances → เรียก getAesSecretKey() ตรงๆ
    console.log('\n[2] scanning StringAesCipher...');
    try {
        Java.choose('com.linecorp.linesdk.internal.security.encryption.StringAesCipher', {
            onMatch(inst) {
                try {
                    // call private getAesSecretKey via reflection
                    const cls = inst.getClass();
                    const methods = ['getAesSecretKey', 'getIntegrityKey'];
                    methods.forEach(mname => {
                        try {
                            const m = cls.getDeclaredMethod(mname);
                            m.setAccessible(true);
                            const key = m.invoke(inst);
                            if (key) {
                                const algo = key.getAlgorithm();
                                const enc = key.getEncoded();
                                if (enc) {
                                    console.log(`[StringAesCipher.${mname}] algo=${algo} len=${enc.length}`);
                                    console.log(`   hex   : ${hex(enc)}`);
                                    console.log(`   ascii : ${ascii(enc)}`);
                                } else {
                                    console.log(`[StringAesCipher.${mname}] key is Android Keystore (no raw export)`);
                                }
                            }
                        } catch (e) { console.log(`   ${mname} err:`, e); }
                    });
                } catch (e) { console.log('[SAC inst err]', e); }
            },
            onComplete() { console.log('[2] done'); }
        });
    } catch (e) { console.log('[2 err]', e); }

    // 3. EncryptorHolder ENCRYPTOR field → ตัวจริงที่ถูกใช้
    console.log('\n[3] EncryptorHolder.ENCRYPTOR...');
    try {
        const EH = Java.use('com.linecorp.linesdk.internal.EncryptorHolder');
        const encField = EH.class.getDeclaredField('ENCRYPTOR');
        encField.setAccessible(true);
        const encInst = encField.get(null);
        console.log(`[EncryptorHolder.ENCRYPTOR] = ${encInst}`);
    } catch (e) { console.log('[3 err]', e); }

    // 4. ทดสอบ decrypt ตรงๆ ด้วย ciphertext จาก xml ของเรา
    console.log('\n[4] test decrypt กับ ciphertext ของ xml...');
    try {
        // encrypted LF_AC จาก input-id/Lelouch+-kappa+-norandom608e58b0_...
        const encLfacBase64 = "Yin0NdTkVyGUx3fZlC8pZov5MTSvDdGghGFkCdbiUhA+Z9+SJGkuOWjGPCCGX01KzP/1OvyNm12F4ftIdnEzA+BBZl0YdpcmRLkN+n7CdtvrTz7uMA8lJBKiMrbmdnc5sDv7iIhfMpOzqpgjd66IktIeCKgMxCFvmtg43WNJZXZOw8IE0eCDPKg19ZqwyCCKVt2Lyrci+TDaugZjJKXXLnrAxXOmxZEZ4EYlxdKIhQOyWj34VcoNvdU+UNQCXDzY2tRAC2S6MVdx/N5VuHqKDzWKd4Ykvqd3Lr46lX37Tb3lKBetBuyMbo1k5AhQhVYz";

        const Context = Java.use('android.app.ActivityThread').currentApplication().getApplicationContext();
        const EH = Java.use('com.linecorp.linesdk.internal.EncryptorHolder');
        const encryptor = EH.getEncryptor();
        if (encryptor) {
            console.log(`[EncryptorHolder.getEncryptor()] = ${encryptor}`);
            try {
                const out = encryptor.decrypt(Context, encLfacBase64);
                console.log(`[decrypt SUCCESS] ouput=${out}`);
                console.log('\n>>> ===== GUEST COOKIE (ของ account นี้) ===== <<<');
                console.log(`>>> ${out}`);
                console.log('>>> ============================================ <<<\n');
            } catch (e) {
                console.log('[decrypt err]', e);
            }
        } else {
            console.log('[getEncryptor] = null (not initialized)');
        }
    } catch (e) { console.log('[4 err]', e); }

    console.log('\n==== SCAN DONE ====\n');
});
