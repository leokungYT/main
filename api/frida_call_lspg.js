// api/frida_call_lspg.js  v15  (SPAWN-safe + retry + enumerate)
// รัน spawn mode → Java VM ยังไม่ขึ้นตอน script load → ต้อง Java.perform รอ
// hook dlopen FIRST ให้เจอ libline-sdk-encryption.so โหลด → hook exports ตอนนั้น
// RegisterNatives hook ต้องรอ Java VM ขึ้น

send('[+] v14 loaded (spawn-safe)');

function b2hex(b) {
    if (!b) return '<null>';
    var s = '';
    for (var i = 0; i < b.length; i++) {
        var v = (b[i] & 0xff).toString(16);
        s += v.length < 2 ? '0' + v : v;
    }
    return s;
}

var _hooked_natives = {};
var _hooked_libs = {};

function findModuleFuzzy(name) {
    // exact
    var m = Process.findModuleByName(name);
    if (m) return m;
    // enum + substring match
    var mods = Process.enumerateModules();
    var nl = name.toLowerCase();
    for (var i = 0; i < mods.length; i++) {
        if (mods[i].name.toLowerCase().indexOf(nl) >= 0 ||
            mods[i].path.toLowerCase().indexOf(nl) >= 0) return mods[i];
    }
    return null;
}

function hookExportsOf(name) {
    if (_hooked_libs[name]) return;
    try {
        var m = findModuleFuzzy(name);
        if (!m) { send('[hookExports] ' + name + ' not loaded yet'); return; }
        _hooked_libs[name] = true;
        _hooked_libs[m.name] = true;
        var exps = m.enumerateExports();
        send('[module] ' + m.name + ' base=' + m.base + ' exports=' + exps.length);

        exps.forEach(function (e) {
            if (_hooked_natives[e.address.toString()]) return;
            var n = e.name;
            var ln = n.toLowerCase();
            if (n.indexOf('Java_') === 0 ||
                ln.indexOf('encrypt') >= 0 ||
                ln.indexOf('decrypt') >= 0 ||
                ln.indexOf('key') >= 0 ||
                ln.indexOf('_gk') >= 0 ||
                ln.indexOf('lspg') >= 0 ||
                ln.indexOf('cipher') >= 0 ||
                ln.indexOf('aes') >= 0) {
                try {
                    Interceptor.attach(e.address, {
                        onEnter: function (args) {
                            this.name = n;
                            this.lib = name;
                            send('[NATIVE→] ' + name + '!' + n);
                        },
                        onLeave: function (retval) {
                            if (retval.isNull()) return;
                            try {
                                var env = Java.vm.getEnv();
                                // try byte array
                                try {
                                    var len = env.getArrayLength(retval);
                                    if (len > 0 && len < 256) {
                                        var p = env.getByteArrayElements(retval, null);
                                        var hex = b2hex(new Uint8Array(Memory.readByteArray(p, len)));
                                        env.releaseByteArrayElements(retval, p, 2);
                                        send('[NATIVE←] ' + this.name + ' bytes[' + len + ']=' + hex);
                                        return;
                                    }
                                } catch (er) {}
                                // try string
                                try {
                                    var ps = env.getStringUtfChars(retval, null);
                                    var s = ps.readCString();
                                    env.releaseStringUtfChars(retval, ps);
                                    if (s && s.length < 512) send('[NATIVE←] ' + this.name + ' str="' + s + '"');
                                } catch (er) {}
                            } catch (er) {}
                        }
                    });
                    _hooked_natives[e.address.toString()] = true;
                } catch (err) {}
            }
        });
    } catch (e) { send('[hookExportsOf ' + name + ' err] ' + e); }
}

// ────────────────────────────────────────────────────────────
// STAGE 1 — hook dlopen FIRST (ตอน VM ยังไม่ขึ้นก็ hook ได้)
// ────────────────────────────────────────────────────────────
function hookDlopen() {
    var dlopen_ext = Module.findExportByName(null, 'android_dlopen_ext');
    var dlopen = Module.findExportByName(null, 'dlopen');

    function install(ptr, tag) {
        if (!ptr) return;
        Interceptor.attach(ptr, {
            onEnter: function (args) { this.path = args[0] ? args[0].readCString() : null; },
            onLeave: function (retval) {
                if (!this.path) return;
                var pl = this.path.toLowerCase();
                // log ทุก .so ที่ไม่ใช่ system เพื่อเห็นลำดับ
                if (pl.indexOf('/app/') >= 0 || pl.indexOf('/data/') >= 0 ||
                    pl.indexOf('line-sdk') >= 0 || pl.indexOf('trident') >= 0 ||
                    pl.indexOf('tzyxaxtyd') >= 0 || pl.indexOf('linesdk') >= 0) {
                    send('[' + tag + '] ' + this.path);
                }
                // keyword match → hook
                if (pl.indexOf('line-sdk') >= 0 ||
                    pl.indexOf('trident') >= 0 ||
                    pl.indexOf('tzyxaxtyd') >= 0 ||
                    pl.indexOf('linesdk') >= 0 ||
                    pl.indexOf('encrypt') >= 0 ||
                    pl.indexOf('crypto') >= 0) {
                    var basename = this.path.substring(this.path.lastIndexOf('/') + 1);
                    // ! ใน path (split APK) → ตัดเอา basename หลัง /
                    if (basename.indexOf('!') >= 0) basename = basename.split('!/').pop().split('/').pop();
                    // retry 5 ครั้ง, 100/300/600/1000/1500 ms
                    [100, 300, 600, 1000, 1500].forEach(function (d) {
                        setTimeout(function () { hookExportsOf(basename); }, d);
                    });
                }
            }
        });
    }
    install(dlopen_ext, 'dlopen_ext');
    install(dlopen, 'dlopen');
    send('[+] dlopen hooks installed');
}

// ────────────────────────────────────────────────────────────
// STAGE 2 — RegisterNatives (ต้องรอ Java VM)
// ────────────────────────────────────────────────────────────
function hookRegisterNatives() {
    try {
        var env = Java.vm.getEnv();
        var jniEnv = Memory.readPointer(env.handle);
        var regNativesPtr = Memory.readPointer(jniEnv.add(215 * Process.pointerSize));
        Interceptor.attach(regNativesPtr, {
            onEnter: function (args) {
                var clazz = args[1];
                var methods = args[2];
                var count = args[3].toInt32();
                try {
                    var envW = Java.vm.getEnv();
                    var clsName = '';
                    try { clsName = envW.getClassName(clazz); } catch (e) { return; }
                    for (var i = 0; i < count; i++) {
                        var base = methods.add(i * Process.pointerSize * 3);
                        var nm = Memory.readPointer(base);
                        var sg = Memory.readPointer(base.add(Process.pointerSize));
                        var fn = Memory.readPointer(base.add(Process.pointerSize * 2));
                        var nmS = nm.readCString();
                        var sgS = sg.readCString();
                        var cl = clsName.toLowerCase();
                        var nl = (nmS || '').toLowerCase();
                        if (cl.indexOf('lspg') >= 0 ||
                            cl.indexOf('encrypt') >= 0 ||
                            cl.indexOf('cipher') >= 0 ||
                            cl.indexOf('trident') >= 0 ||
                            nl.indexOf('gk') >= 0 ||
                            nl.indexOf('key') >= 0 ||
                            nl.indexOf('decrypt') >= 0 ||
                            nl.indexOf('encrypt') >= 0) {
                            send('[RegNatives] ' + clsName + '.' + nmS + sgS + ' @ ' + fn);
                            try {
                                var captured = { cls: clsName, nm: nmS };
                                Interceptor.attach(fn, {
                                    onEnter: function () { send('[DYN→] ' + captured.cls + '.' + captured.nm); },
                                    onLeave: function (retval) {
                                        if (retval.isNull()) return;
                                        try {
                                            var e = Java.vm.getEnv();
                                            try {
                                                var len = e.getArrayLength(retval);
                                                if (len > 0 && len < 256) {
                                                    var p = e.getByteArrayElements(retval, null);
                                                    var hex = b2hex(new Uint8Array(Memory.readByteArray(p, len)));
                                                    e.releaseByteArrayElements(retval, p, 2);
                                                    send('[DYN←] ' + captured.cls + '.' + captured.nm + ' bytes[' + len + ']=' + hex);
                                                    return;
                                                }
                                            } catch (er) {}
                                            try {
                                                var ps = e.getStringUtfChars(retval, null);
                                                var s = ps.readCString();
                                                e.releaseStringUtfChars(retval, ps);
                                                if (s) send('[DYN←] ' + captured.cls + '.' + captured.nm + ' str="' + s + '"');
                                            } catch (er) {}
                                        } catch (er) {}
                                    }
                                });
                            } catch (er) {}
                        }
                    }
                } catch (e) { send('[regNative parse err] ' + e); }
            }
        });
        send('[+] RegisterNatives hooked');
    } catch (e) { send('[regNatives install err] ' + e); }
}

// ────────────────────────────────────────────────────────────
// STAGE 3 — Java hooks (Cipher + SAC)
// ────────────────────────────────────────────────────────────
function installJavaHooks() {
    // SecretKeySpec
    try {
        var KeySpec = Java.use('javax.crypto.spec.SecretKeySpec');
        KeySpec.$init.overload('[B', 'java.lang.String').implementation = function (raw, alg) {
            try {
                if (alg && alg.toUpperCase() === 'AES' && [16,24,32].indexOf(raw.length) >= 0) {
                    send('[KEY/SecretKeySpec] ' + b2hex(raw));
                }
            } catch (e) {}
            return this.$init(raw, alg);
        };
    } catch (e) {}

    // Cipher.init
    try {
        var Cipher = Java.use('javax.crypto.Cipher');
        var IvParam = Java.use('javax.crypto.spec.IvParameterSpec');
        Cipher.init.overload('int', 'java.security.Key', 'java.security.spec.AlgorithmParameterSpec')
            .implementation = function (mode, key, spec) {
            try {
                var algo = this.getAlgorithm();
                if (algo && algo.toUpperCase().indexOf('AES') >= 0) {
                    var ln = '[Cipher.init] ' + (mode === 1 ? 'ENC' : 'DEC') + ' ' + algo;
                    try { ln += ' iv=' + b2hex(Java.cast(spec, IvParam).getIV()); } catch (e) {}
                    try { var k = key.getEncoded(); if (k) ln += ' key=' + b2hex(k); } catch (e) {}
                    send(ln);
                }
            } catch (e) {}
            return this.init(mode, key, spec);
        };
    } catch (e) {}

    // Cipher.doFinal
    try {
        var Cipher2 = Java.use('javax.crypto.Cipher');
        Cipher2.doFinal.overload('[B').implementation = function (buf) {
            var algo = this.getAlgorithm();
            var r = this.doFinal(buf);
            if (algo && algo.toUpperCase().indexOf('AES') >= 0 && buf) {
                send('[doFinal] ' + algo + ' in=' + b2hex(buf).substring(0, 64) + ' out=' + (r ? b2hex(r).substring(0, 96) : 'null'));
                try {
                    var ss = Java.use('java.lang.String').$new(r).toString();
                    if (ss.length > 4 && ss.length < 2048) send('[doFinal/text] ' + ss.substring(0, 300));
                } catch (e) {}
            }
            return r;
        };
    } catch (e) {}

    // StringAesCipher
    try {
        var SAC = Java.use('com.linecorp.linesdk.internal.security.encryption.StringAesCipher');
        SAC.decrypt.overload('android.content.Context', 'java.lang.String').implementation = function (ctx, input) {
            send('[SAC.decrypt] in_prefix=' + (input ? input.substring(0, 60) : 'null'));
            var r = this.decrypt(ctx, input);
            send('[SAC.decrypt] out=' + (r == null ? 'null' : r.toString()));
            return r;
        };
    } catch (e) {}

    send('[+] java hooks installed');
}

// ────────────────────────────────────────────────────────────
// Boot — ไม่ใช้ setTimeout เพราะ spawn → Java VM ยังไม่ขึ้น
// ────────────────────────────────────────────────────────────
hookDlopen();  // native hook ทำได้ทันที

// Java.perform รอ VM ขึ้นจบก่อน
Java.perform(function () {
    installJavaHooks();
    hookRegisterNatives();
    // scan ทุก module ที่โหลดอยู่แล้วตอน VM ขึ้น
    scanAllLoadedModules();
    // periodic rescan เผื่อ library โหลดช้า
    setInterval(scanAllLoadedModules, 2000);
    send('[+] boot complete — resume');
});

function scanAllLoadedModules() {
    try {
        var mods = Process.enumerateModules();
        mods.forEach(function (m) {
            if (_hooked_libs[m.name]) return;
            var nl = m.name.toLowerCase();
            if (nl.indexOf('line-sdk') >= 0 ||
                nl.indexOf('linesdk') >= 0 ||
                nl.indexOf('trident') >= 0 ||
                nl.indexOf('tzyxaxtyd') >= 0 ||
                nl.indexOf('encrypt') >= 0 ||
                nl.indexOf('crypto') >= 0) {
                hookExportsOf(m.name);
            }
        });
    } catch (e) {}
}
