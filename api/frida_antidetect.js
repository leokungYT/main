/*
 * Anti-anti-frida v2 — lightweight, no high-frequency native hooks.
 * Previous version hooked strstr/strcmp globally which froze the process.
 * This one only touches:
 *   - prctl(PR_SET_NAME)   — low frequency (thread creation only)
 *   - access()             — low frequency (file existence check)
 *   - Java: File / Debug / Thread / String.contains (only when called)
 */

(function () {
    "use strict";

    var FRIDA_BAD = [
        "frida", "FRIDA", "gum-js-loop", "pool-frida", "gmain",
        "gdbus", "linjector", "re.frida",
        "/data/local/tmp/fs", "/data/local/tmp/re.frida",
        "/data/local/tmp/frida-server", "gadget",
    ];

    function looksBad(s) {
        if (!s) return false;
        for (var i = 0; i < FRIDA_BAD.length; i++) {
            if (s.indexOf(FRIDA_BAD[i]) !== -1) return true;
        }
        return false;
    }

    function readCStr(p) {
        try { return Memory.readUtf8String(p); } catch (_) { return null; }
    }

    /* access(path, mode) — lie about frida files existing */
    var access = Module.findExportByName(null, "access");
    if (access) {
        Interceptor.attach(access, {
            onEnter: function (a) {
                var p = readCStr(a[0]);
                this.hide = looksBad(p);
            },
            onLeave: function (r) {
                if (this.hide) r.replace(ptr(-1));
            },
        });
        console.log("[AD  ] access() hook live");
    }

    /* prctl(PR_SET_NAME) — rename frida threads */
    var prctl = Module.findExportByName(null, "prctl");
    if (prctl) {
        Interceptor.attach(prctl, {
            onEnter: function (a) {
                if (a[0].toInt32() === 15) {  /* PR_SET_NAME */
                    var n = readCStr(a[1]);
                    if (looksBad(n)) {
                        try { Memory.writeUtf8String(a[1], "worker"); } catch (_) {}
                    }
                }
            },
        });
        console.log("[AD  ] prctl() hook live");
    }

    /* Java-side hooks — fire only when app calls them */
    Java.perform(function () {
        try {
            var File = Java.use("java.io.File");
            File.exists.implementation = function () {
                var p = this.getAbsolutePath();
                if (looksBad(p)) {
                    console.log("[AD  ] File.exists(" + p + ") -> false");
                    return false;
                }
                return this.exists();
            };
            File.canRead.implementation = function () {
                var p = this.getAbsolutePath();
                if (looksBad(p)) return false;
                return this.canRead();
            };

            var Debug = Java.use("android.os.Debug");
            Debug.isDebuggerConnected.implementation = function () { return false; };

            var Thread = Java.use("java.lang.Thread");
            Thread.getName.implementation = function () {
                var n = this.getName.call(this);
                if (looksBad(n)) return "worker";
                return n;
            };

            var String_ = Java.use("java.lang.String");
            String_.contains.implementation = function (seq) {
                var s = seq ? seq.toString() : "";
                if (looksBad(s)) return false;
                return this.contains(seq);
            };

            /* /proc/self/maps via FileInputStream */
            var FileInputStream = Java.use("java.io.FileInputStream");
            var ctor1 = FileInputStream.$init.overload("java.io.File");
            ctor1.implementation = function (f) {
                var p = f.getAbsolutePath();
                if (p === "/proc/self/maps" || p === "/proc/net/tcp" ||
                    p === "/proc/self/status") {
                    console.log("[AD  ] FileInputStream(" + p + ") redirecting");
                    /* can't easily redirect — just let it through, native fgets
                       is not hooked, so lines pass through; but we clamp other
                       checks above */
                }
                return this.$init(f);
            };

            console.log("[AD  ] Java hooks live (File, Debug, Thread, String.contains)");
        } catch (e) {
            console.log("[AD  ] Java hook error: " + e);
        }
    });

    console.log("[AD  ] antidetect v2 loaded (lightweight)");
})();
