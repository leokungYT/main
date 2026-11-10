// api/frida_call_lspg.js  v7
// hook StringAesCipher + EncryptorHolder ของ linesdk
// log ทุก encrypt/decrypt call → เห็น key + plaintext

send('[+] v7 loaded');

function b2hex(b) {
    if (!b) return '<null>';
    var s = '';
    for (var i = 0; i < b.length; i++) {
        var v = (b[i] & 0xff).toString(16);
        s += v.length < 2 ? '0' + v : v;
    }
    return s;
}

function b2ascii(b) {
    if (!b) return '<null>';
    var s = '';
    for (var i = 0; i < b.length; i++) {
        var c = b[i] & 0xff;
        s += (c >= 32 && c <= 126) ? String.fromCharCode(c) : '.';
    }
    return s;
}

Java.perform(function () {
    try {
        // ---- 1) SecretKeySpec constructor — ดักทุกครั้งที่สร้าง AES key ----
        var KeySpec = Java.use('javax.crypto.spec.SecretKeySpec');
        KeySpec.$init.overload('[B', 'java.lang.String').implementation = function (raw, alg) {
            try {
                if (alg && alg.toUpperCase() === 'AES' && [16,24,32].indexOf(raw.length) >= 0) {
                    send('[KEY SecretKeySpec] len=' + raw.length + ' hex=' + b2hex(raw) + ' ascii=' + b2ascii(raw));
                }
            } catch (e) {}
            return this.$init(raw, alg);
        };
        send('[+] SecretKeySpec hooked');

        // ---- 2) Cipher.init — บอก mode + IV ----
        var Cipher = Java.use('javax.crypto.Cipher');
        var IvParam = Java.use('javax.crypto.spec.IvParameterSpec');
        Cipher.init.overload('int', 'java.security.Key', 'java.security.spec.AlgorithmParameterSpec')
            .implementation = function (mode, key, spec) {
            try {
                var algo = this.getAlgorithm();
                if (algo && algo.toUpperCase().indexOf('AES') >= 0) {
                    var line = '[Cipher.init] mode=' + (mode === 1 ? 'ENC' : 'DEC') + ' algo=' + algo;
                    try {
                        var iv = Java.cast(spec, IvParam).getIV();
                        line += ' iv=' + b2hex(iv);
                    } catch (e) {}
                    try {
                        var kb = key.getEncoded();
                        if (kb) line += ' key=' + b2hex(kb);
                    } catch (e) {}
                    send(line);
                }
            } catch (e) {}
            return this.init(mode, key, spec);
        };
        send('[+] Cipher.init hooked');

        // ---- 3) Cipher.doFinal(byte[]) — เห็น input/output ----
        Cipher.doFinal.overload('[B').implementation = function (b) {
            var out = this.doFinal(b);
            try {
                var algo = this.getAlgorithm();
                if (algo && algo.toUpperCase().indexOf('AES') >= 0) {
                    send('[doFinal] algo=' + algo + ' in_len=' + (b ? b.length : 0) + ' out_len=' + (out ? out.length : 0));
                    if (b && b.length < 512)   send('           in_hex=' + b2hex(b));
                    if (out && out.length < 512) send('           out_hex=' + b2hex(out) + ' out_ascii=' + b2ascii(out));
                }
            } catch (e) {}
            return out;
        };
        send('[+] doFinal hooked');

        // ---- 4) hook StringAesCipher ถ้าเจอ ----
        try {
            var SAC = Java.use('com.linecorp.linesdk.internal.security.encryption.StringAesCipher');
            send('[+] StringAesCipher loaded');
            var ms = SAC.class.getDeclaredMethods();
            for (var i = 0; i < ms.length; i++) send('   SAC.method: ' + ms[i].toString());
            // hook encrypt + decrypt methods ที่มี
            ms.forEach(function (m) {
                var name = m.getName();
                if (name === 'encrypt' || name === 'decrypt') {
                    try {
                        SAC[name].overloads.forEach(function (ov) {
                            ov.implementation = function () {
                                var args = Array.prototype.slice.call(arguments);
                                send('[SAC.' + name + '] args=' + args.map(function (a) { return a == null ? 'null' : a.toString().substring(0, 200); }).join(' | '));
                                var r = ov.apply(this, args);
                                send('[SAC.' + name + '] ret=' + (r == null ? 'null' : r.toString().substring(0, 500)));
                                return r;
                            };
                        });
                        send('[+] hooked SAC.' + name);
                    } catch (e) { send('[SAC.' + name + ' hook err] ' + e); }
                }
            });
        } catch (e) { send('[-] StringAesCipher not in default loader: ' + e.message); }

        // ---- 5) EncryptorHolder ----
        try {
            var EH = Java.use('com.linecorp.linesdk.internal.EncryptorHolder');
            send('[+] EncryptorHolder loaded');
            var ehm = EH.class.getDeclaredMethods();
            for (var i = 0; i < ehm.length; i++) send('   EH.method: ' + ehm[i].toString());
        } catch (e) { send('[-] EncryptorHolder not in default loader: ' + e.message); }

        send('[+] all hooks installed — เล่น LGR ให้มัน login/decrypt');
    } catch (e) { send('[fatal] ' + e); }
});
