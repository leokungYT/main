/*
 * Hook javax.crypto.Cipher + SecretKeySpec + IvParameterSpec
 * Log key bytes, IV, input, output for every AES op.
 * Filter by algorithm = "AES*" to cut noise.
 *
 * Attach:
 *   frida -U -f com.linecorp.LGRGS -l frida_cipher_hook.js --no-pause
 *   (replace package if different)
 */

function b2hex(b) {
    if (!b) return "<null>";
    var s = "";
    for (var i = 0; i < b.length; i++) {
        var v = (b[i] & 0xff).toString(16);
        if (v.length < 2) v = "0" + v;
        s += v;
    }
    return s;
}

function b2printable(b, max) {
    if (!b) return "<null>";
    max = max || 64;
    var out = "";
    var n = Math.min(b.length, max);
    for (var i = 0; i < n; i++) {
        var c = b[i] & 0xff;
        if (c >= 0x20 && c < 0x7f) out += String.fromCharCode(c);
        else out += "\\x" + (c < 16 ? "0" : "") + c.toString(16);
    }
    if (b.length > max) out += "...";
    return out;
}

function stack(label) {
    var Exception = Java.use("java.lang.Exception");
    var frames = Exception.$new().getStackTrace();
    console.log("    stack[" + label + "]:");
    for (var i = 0; i < Math.min(frames.length, 8); i++) {
        console.log("      " + frames[i].toString());
    }
}

Java.perform(function () {
    console.log("[*] frida_cipher_hook attached");

    var SecretKeySpec = Java.use("javax.crypto.spec.SecretKeySpec");
    var IvParameterSpec = Java.use("javax.crypto.spec.IvParameterSpec");
    var Cipher = Java.use("javax.crypto.Cipher");
    var String_ = Java.use("java.lang.String");
    var Base64 = Java.use("android.util.Base64");

    // 1) SecretKeySpec(byte[], String algorithm)
    SecretKeySpec.$init.overload("[B", "java.lang.String").implementation = function (keyBytes, algo) {
        if (algo && algo.toUpperCase().indexOf("AES") >= 0) {
            var buf = [];
            for (var i = 0; i < keyBytes.length; i++) buf.push(keyBytes[i]);
            console.log("");
            console.log("[KEY ] SecretKeySpec(algo=" + algo + ", len=" + keyBytes.length + ")");
            console.log("       hex = " + b2hex(buf));
            console.log("       asc = " + b2printable(buf, 48));
        }
        return this.$init(keyBytes, algo);
    };

    // 2) SecretKeySpec(byte[], int, int, String)
    SecretKeySpec.$init.overload("[B", "int", "int", "java.lang.String").implementation = function (k, off, len, algo) {
        if (algo && algo.toUpperCase().indexOf("AES") >= 0) {
            var buf = [];
            for (var i = off; i < off + len; i++) buf.push(k[i]);
            console.log("");
            console.log("[KEY ] SecretKeySpec(algo=" + algo + ", off=" + off + ", len=" + len + ")");
            console.log("       hex = " + b2hex(buf));
            console.log("       asc = " + b2printable(buf, 48));
        }
        return this.$init(k, off, len, algo);
    };

    // 3) IvParameterSpec(byte[])
    IvParameterSpec.$init.overload("[B").implementation = function (iv) {
        var buf = [];
        for (var i = 0; i < iv.length; i++) buf.push(iv[i]);
        console.log("[IV  ] IvParameterSpec(len=" + iv.length + ") hex=" + b2hex(buf));
        return this.$init(iv);
    };

    // 4) IvParameterSpec(byte[], int, int)
    IvParameterSpec.$init.overload("[B", "int", "int").implementation = function (iv, off, len) {
        var buf = [];
        for (var i = off; i < off + len; i++) buf.push(iv[i]);
        console.log("[IV  ] IvParameterSpec(off=" + off + ", len=" + len + ") hex=" + b2hex(buf));
        return this.$init(iv, off, len);
    };

    // 5) Cipher.getInstance(String)  -- just log transformation
    Cipher.getInstance.overload("java.lang.String").implementation = function (t) {
        var c = this.getInstance(t);
        if (t && t.toUpperCase().indexOf("AES") >= 0) {
            console.log("[TXF ] Cipher.getInstance('" + t + "')");
        }
        return c;
    };

    // 6) Cipher.doFinal(byte[])  -- log in/out
    Cipher.doFinal.overload("[B").implementation = function (data) {
        var algo = this.getAlgorithm();
        var out = this.doFinal(data);
        if (algo && algo.toUpperCase().indexOf("AES") >= 0) {
            var inBuf = [];
            for (var i = 0; i < data.length; i++) inBuf.push(data[i]);
            var outBuf = [];
            for (var j = 0; j < out.length; j++) outBuf.push(out[j]);
            var opMode = this.getOpmode();   // 1=ENC, 2=DEC
            var modeStr = opMode === 1 ? "ENCRYPT" : opMode === 2 ? "DECRYPT" : "mode=" + opMode;
            console.log("");
            console.log("[OP  ] Cipher.doFinal  " + modeStr + "  algo=" + algo);
            console.log("       in.len  = " + data.length + "  hex[:32]=" + b2hex(inBuf.slice(0, 32)));
            console.log("       in.asc  = " + b2printable(inBuf, 48));
            console.log("       out.len = " + out.length + "  hex[:32]=" + b2hex(outBuf.slice(0, 32)));
            console.log("       out.asc = " + b2printable(outBuf, 48));
            stack("doFinal");
        }
        return out;
    };

    // 7) Cipher.doFinal(byte[], int, int)
    Cipher.doFinal.overload("[B", "int", "int").implementation = function (data, off, len) {
        var algo = this.getAlgorithm();
        var out = this.doFinal(data, off, len);
        if (algo && algo.toUpperCase().indexOf("AES") >= 0) {
            var inBuf = [];
            for (var i = off; i < off + len; i++) inBuf.push(data[i]);
            var outBuf = [];
            for (var j = 0; j < out.length; j++) outBuf.push(out[j]);
            var opMode = this.getOpmode();
            var modeStr = opMode === 1 ? "ENCRYPT" : opMode === 2 ? "DECRYPT" : "mode=" + opMode;
            console.log("");
            console.log("[OP  ] Cipher.doFinal(off,len)  " + modeStr + "  algo=" + algo);
            console.log("       in.len  = " + len + "  hex[:32]=" + b2hex(inBuf.slice(0, 32)));
            console.log("       out.len = " + out.length + "  hex[:32]=" + b2hex(outBuf.slice(0, 32)));
            console.log("       out.asc = " + b2printable(outBuf, 48));
        }
        return out;
    };

    console.log("[*] hooks live: SecretKeySpec, IvParameterSpec, Cipher.getInstance, Cipher.doFinal");
    console.log("[*] trigger the app to read/write _ENC_LF_AC — login screen is enough");
});
