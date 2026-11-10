// api/frida_creds_grabber.js
// ลักค่า udid + guestCookie + LF_AC ของ LGR ตรงจาก HTTP client ของเกม
// ไม่ต้องตั้ง proxy, ไม่ต้อง cert, ไม่ต้อง MITM
//
// usage:
//   adb -s 127.0.0.1:7555 shell "su -c '/data/local/tmp/frida-server &'"
//   frida -U -f com.linecorp.LGRGS -l api/frida_creds_grabber.js --no-pause
//
// output บน console:
//   [LOGIN REQ] udid=xxx guestCookie=yyy nation=TH
//   [LOGIN RES] LF_AC=zzz status=200 body={...}
//   [HOME REQ]  cookie=udid=xxx; LF_AC=zzz
//
// copy ค่า udid + guestCookie ไป:
//   python api\lgr_requests.py --udid <udid> --guest <guestCookie>

Java.perform(function () {
    send('[+] creds grabber armed — เปิดเกม ค้างหน้า title/login');

    // ---- 1) OkHttp3 Interceptor pattern ----
    try {
        var RequestBuilder = Java.use('okhttp3.Request$Builder');
        var Buffer         = Java.use('okio.Buffer');
        var RealCall       = Java.use('okhttp3.RealCall');

        RealCall.execute.implementation = function () {
            var req = this.request();
            try {
                var url = req.url().toString();
                if (url.indexOf('axelth') >= 0 || url.indexOf('linega') >= 0 ||
                    url.indexOf('linecorp') >= 0 || url.indexOf('ranger') >= 0) {
                    dumpRequest('OKHTTP', req);
                }
            } catch (e) {}
            var res = this.execute();
            try {
                var url = req.url().toString();
                if (url.indexOf('axelth') >= 0 || url.indexOf('linega') >= 0 ||
                    url.indexOf('linecorp') >= 0 || url.indexOf('ranger') >= 0) {
                    dumpResponse('OKHTTP', req, res);
                }
            } catch (e) {}
            return res;
        };

        function dumpRequest(tag, req) {
            var url = req.url().toString();
            var headers = req.headers().toString();
            var bodyStr = '';
            try {
                var body = req.body();
                if (body !== null) {
                    var sink = Buffer.$new();
                    body.writeTo(sink);
                    bodyStr = sink.readUtf8();
                }
            } catch (e) {}
            send('[REQ ' + tag + '] ' + req.method() + ' ' + url);
            send('       headers: ' + headers.replace(/\n/g, ' | '));
            if (bodyStr) send('       body: ' + bodyStr.substring(0, 2000));
        }

        function dumpResponse(tag, req, res) {
            var status = res.code();
            var sc = '';
            try {
                var vals = res.headers().values('Set-Cookie');
                var it = vals.iterator();
                while (it.hasNext()) { sc += it.next().toString() + ' | '; }
            } catch (e) {}
            var bodyStr = '';
            try {
                var peek = res.peekBody(8192);
                bodyStr = peek.string();
            } catch (e) {}
            send('[RES ' + tag + '] ' + status + ' ' + req.url().toString());
            if (sc)      send('       set-cookie: ' + sc);
            if (bodyStr) send('       body: ' + bodyStr.substring(0, 2000));
        }
        send('[+] OkHttp hooks live');
    } catch (e) { send('[-] OkHttp hook failed: ' + e); }

    // ---- 2) HttpURLConnection fallback ----
    try {
        var URL = Java.use('java.net.URL');
        URL.openConnection.overload().implementation = function () {
            var c = this.openConnection();
            try {
                var u = this.toString();
                if (u.indexOf('axelth') >= 0 || u.indexOf('linega') >= 0 || u.indexOf('ranger') >= 0) {
                    send('[URL-OPEN] ' + u);
                }
            } catch (e) {}
            return c;
        };
        send('[+] URL hooks live');
    } catch (e) { send('[-] URL hook failed: ' + e); }

    // ---- 3) SharedPreferences read — ดัก enc_guestCookie + udid ตอน app อ่าน ----
    try {
        var SP = Java.use('android.app.SharedPreferencesImpl');
        SP.getString.implementation = function (key, def) {
            var v = this.getString(key, def);
            if (key && (key === '_DEVICE_UUID_KEY' ||
                        key === '_ENC_LF_AC_KEY' ||
                        key === 'USER_NATION_CODE' ||
                        key === '_LF_UT_KEY')) {
                send('[SP READ] ' + key + ' = ' + (v ? v.substring(0, 200) : v));
            }
            return v;
        };
        send('[+] SharedPreferences hooks live');
    } catch (e) { send('[-] SP hook failed: ' + e); }

    // ---- 4) String decrypt — จับ guestCookie plain หลัง decrypt ----
    try {
        var Str = Java.use('java.lang.String');
        Str.$init.overload('[B', 'java.lang.String').implementation = function (b, enc) {
            var r = this.$init(b, enc);
            try {
                if (b.length >= 8 && b.length <= 256 && enc.toUpperCase().indexOf('UTF') >= 0) {
                    var s = Java.use('java.lang.String').$new(b, enc);
                    // guestCookie ปกติเป็น hex/base64 ยาว 16-128
                    if (s.length() >= 16 && s.length() <= 128 &&
                        /^[A-Za-z0-9+/=_\-]+$/.test(s)) {
                        send('[PLAIN?] len=' + s.length() + ' val=' + s);
                    }
                }
            } catch (e) {}
            return r;
        };
    } catch (e) {}
});
