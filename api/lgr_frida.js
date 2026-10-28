// C:\Users\Administrator\Downloads\LGR\api\lgr_frida.js
// ใช้: frida -U -f com.linecorp.LGRGS -l api/lgr_frida.js --no-pause
// hook ครบ: OkHttp response rewrite + JSON flag flip + Build spoof + Network type spoof + pinning kill

Java.perform(function () {
    // 1) OkHttp response rewrite ที่ client-side
    try {
        var Response = Java.use("okhttp3.Response");
        Response.code.implementation = function () {
            var c = this.code.call(this);
            if (c === 403 || c === 429) {
                console.log("[frida] rewrite response " + c + " -> 200");
                return 200;
            }
            return c;
        };
    } catch (e) { console.log("okhttp hook skip: " + e); }

    // 2) JSON parser - flip block flag
    try {
        var JSONObject = Java.use("org.json.JSONObject");
        var killBool = ["blocked", "ipBlocked", "deviceBlocked", "banned", "restricted"];
        var killInt = ["loginCount", "loginLimit", "dailyLoginCount"];
        JSONObject.getBoolean.overload('java.lang.String').implementation = function (n) {
            if (killBool.indexOf(n) !== -1) return false;
            return this.getBoolean.call(this, n);
        };
        JSONObject.optBoolean.overload('java.lang.String', 'boolean').implementation = function (n, d) {
            if (killBool.indexOf(n) !== -1) return false;
            return this.optBoolean.call(this, n, d);
        };
        JSONObject.optInt.overload('java.lang.String', 'int').implementation = function (n, d) {
            if (killInt.indexOf(n) !== -1) return 0;
            return this.optInt.call(this, n, d);
        };
    } catch (e) { console.log("JSONObject hook skip: " + e); }

    // 3) Build spoof -> Pixel 7 LTE
    try {
        var Build = Java.use("android.os.Build");
        Build.FINGERPRINT.value = "google/panther/panther:14/UP1A.231105.003/10817346:user/release-keys";
        Build.MODEL.value = "Pixel 7";
        Build.MANUFACTURER.value = "Google";
        Build.BRAND.value = "google";
        Build.DEVICE.value = "panther";
        Build.HARDWARE.value = "panther";
        Build.PRODUCT.value = "panther";
    } catch (e) { console.log("Build spoof skip: " + e); }

    // 4) NETWORK TYPE SPOOF - ให้ ConnectivityManager รายงาน TYPE_MOBILE แทน TYPE_WIFI
    try {
        var NetworkInfo = Java.use("android.net.NetworkInfo");
        NetworkInfo.getType.implementation = function () {
            // TYPE_MOBILE = 0 (SIM data), TYPE_WIFI = 1
            return 0;
        };
        NetworkInfo.getTypeName.implementation = function () {
            return "MOBILE";
        };
        NetworkInfo.getSubtype.implementation = function () {
            // TelephonyManager.NETWORK_TYPE_LTE = 13
            return 13;
        };
        NetworkInfo.getSubtypeName.implementation = function () {
            return "LTE";
        };
        NetworkInfo.isConnected.implementation = function () { return true; };
        NetworkInfo.isConnectedOrConnecting.implementation = function () { return true; };
        NetworkInfo.isAvailable.implementation = function () { return true; };
        console.log("[frida] NetworkInfo spoofed -> MOBILE/LTE");
    } catch (e) { console.log("NetworkInfo spoof skip: " + e); }

    try {
        var TelephonyManager = Java.use("android.telephony.TelephonyManager");
        TelephonyManager.getNetworkType.implementation = function () { return 13; };  // LTE
        TelephonyManager.getDataNetworkType.implementation = function () { return 13; };
        TelephonyManager.getPhoneType.implementation = function () { return 1; };     // GSM
        TelephonyManager.getSimState.implementation = function () { return 5; };      // READY
        TelephonyManager.getNetworkOperator.implementation = function () { return "52003"; };
        TelephonyManager.getNetworkOperatorName.implementation = function () { return "AIS"; };
        TelephonyManager.getSimOperator.implementation = function () { return "52003"; };
        TelephonyManager.getSimOperatorName.implementation = function () { return "AIS"; };
        TelephonyManager.getNetworkCountryIso.overload().implementation = function () { return "th"; };
        TelephonyManager.getSimCountryIso.overload().implementation = function () { return "th"; };
        console.log("[frida] TelephonyManager spoofed -> AIS Thailand LTE");
    } catch (e) { console.log("TelephonyManager spoof skip: " + e); }

    // 5) ConnectivityManager.getActiveNetworkInfo -> fake mobile
    try {
        var ConnMgr = Java.use("android.net.ConnectivityManager");
        ConnMgr.getActiveNetworkInfo.implementation = function () {
            var ni = this.getActiveNetworkInfo();
            if (ni) {
                // ไม่ create ใหม่ แค่ให้ hook ที่ NetworkInfo กินต่อ
                return ni;
            }
            return ni;
        };
    } catch (e) { console.log("ConnMgr skip: " + e); }

    // 6a) POPUP KILLER - ซ่อน Toast / Dialog ที่แสดงข้อความ block
    try {
        var Toast = Java.use("android.widget.Toast");
        Toast.show.implementation = function () {
            console.log("[frida] Toast suppressed");
        };
    } catch (e) {}
    try {
        var AlertBuilder = Java.use("android.app.AlertDialog$Builder");
        AlertBuilder.show.implementation = function () {
            console.log("[frida] AlertDialog suppressed");
            return this.create();
        };
    } catch (e) {}

    // 6b) STRING INTERCEPT - ข้อความ "Authentication failed" / "Unstable network"
    //     เกมอ่านจาก resources -> hook getString ให้คืนข้อความ "ok"
    try {
        var Resources = Java.use("android.content.res.Resources");
        var killStr = ["Authentication failed", "Unstable network",
                       "cannot connect", "login failed", "blocked",
                       "ตรวจสอบการเชื่อมต่อ", "ไม่สามารถ"];
        Resources.getString.overload('int').implementation = function (id) {
            var s = this.getString(id);
            for (var i = 0; i < killStr.length; i++) {
                if (s && s.indexOf(killStr[i]) !== -1) {
                    console.log("[frida] blocked string hidden: " + s.substring(0, 40));
                    return "";
                }
            }
            return s;
        };
    } catch (e) {}

    // 7) kill SSL pinning
    try {
        var CertPinner = Java.use("okhttp3.CertificatePinner");
        CertPinner.check.overload('java.lang.String', 'java.util.List').implementation = function () {};
    } catch (e) {}
    try {
        var X509TM = Java.use("javax.net.ssl.X509TrustManager");
        var SSLContext = Java.use("javax.net.ssl.SSLContext");
        var TM = Java.registerClass({
            name: 'org.wooyun.TrustAllCerts',
            implements: [X509TM],
            methods: {
                checkClientTrusted: function (chain, authType) {},
                checkServerTrusted: function (chain, authType) {},
                getAcceptedIssuers: function () { return []; }
            }
        });
        SSLContext.init.overload('[Ljavax.net.ssl.KeyManager;', '[Ljavax.net.ssl.TrustManager;',
            'java.security.SecureRandom').implementation = function (km, tm, sr) {
            this.init(km, [TM.$new()], sr);
        };
    } catch (e) {}
});
