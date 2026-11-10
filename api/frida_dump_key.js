// api/frida_dump_key.js
// ดึง AES key ของ LGR ครั้งเดียว แล้วใช้ยาวได้
// usage:
//   adb shell "su -c '/data/local/tmp/frida-server &'"
//   frida -U -f com.linecorp.LGRGS -l api/frida_dump_key.js --no-pause
//
// console จะโผล่:  [AES KEY] len=16 hex=XXXXXXXX... algo=AES/CBC/PKCS5Padding
// copy ค่า hex -> setx LGR_AES_KEY <hex>

Java.perform(function () {
    var seen = {};
    var KEY_LEN = [16, 24, 32];

    function hex(raw) {
        var s = '';
        for (var i = 0; i < raw.length; i++) {
            var v = (raw[i] & 0xff).toString(16);
            s += v.length < 2 ? '0' + v : v;
        }
        return s;
    }

    // ---- 1) SecretKeySpec: จุดสร้าง AES key ทุกตัวในแอป ----
    var KeySpec = Java.use('javax.crypto.spec.SecretKeySpec');
    KeySpec.$init.overload('[B', 'java.lang.String').implementation = function (raw, alg) {
        try {
            if (alg && alg.toUpperCase() === 'AES' && KEY_LEN.indexOf(raw.length) >= 0) {
                var h = hex(raw);
                if (!seen[h]) {
                    seen[h] = 1;
                    send('[AES KEY] len=' + raw.length + ' hex=' + h);
                }
            }
        } catch (e) {}
        return this.$init(raw, alg);
    };

    // ---- 2) Cipher.init: ชี้ mode/iv ของแต่ละงาน ----
    var Cipher = Java.use('javax.crypto.Cipher');
    var IvParam = Java.use('javax.crypto.spec.IvParameterSpec');

    Cipher.init.overload('int', 'java.security.Key', 'java.security.spec.AlgorithmParameterSpec')
        .implementation = function (mode, key, spec) {
        try {
            var algo = this.getAlgorithm();
            if (algo && algo.toUpperCase().indexOf('AES') >= 0) {
                var line = '[CIPHER] mode=' + (mode === 1 ? 'ENC' : 'DEC') + ' algo=' + algo;
                try {
                    var iv = Java.cast(spec, IvParam).getIV();
                    line += ' iv=' + hex(iv);
                } catch (e) {}
                try {
                    var kb = key.getEncoded();
                    if (kb) line += ' key=' + hex(kb);
                } catch (e) {}
                send(line);
            }
        } catch (e) {}
        return this.init(mode, key, spec);
    };

    // ---- 3) Cipher.doFinal: ดูขนาด input/output จริง ----
    Cipher.doFinal.overload('[B').implementation = function (b) {
        var out = this.doFinal(b);
        try {
            var algo = this.getAlgorithm();
            if (algo && algo.toUpperCase().indexOf('AES') >= 0) {
                send('[DOFINAL] algo=' + algo + ' in=' + (b ? b.length : 0) + ' out=' + (out ? out.length : 0));
            }
        } catch (e) {}
        return out;
    };

    send('[+] AES sniffer armed — เปิดเกม ค้างหน้า login/title สักครู่');
});
