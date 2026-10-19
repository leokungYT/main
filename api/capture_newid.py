#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capture_newid.py — ดัก "ทุก host" ตอนเกมสร้าง guest ID ใหม่ (เปิดครั้งแรกหลังล้างข้อมูล)
เพื่อแกะ flow สร้างบัญชี (LINE Trident handshake + /login + /tutorial/confirm/*) มายิงเองด้วย API ล้วน

ต่างจาก capture_run.py: อันนั้นดักแค่ rangers-api; อันนี้ redirect TCP 443 ทุกปลายทาง
เข้า mitmdump แล้วส่งต่อไป host จริงตาม SNI (reverse mode + เปลี่ยน host รายคำขอ)

ใช้:
  python capture_newid.py 127.0.0.1:16512            # ดักเฉย ๆ (เปิดเกมเอง)
  python capture_newid.py 127.0.0.1:16512 --clear    # สำรอง shared_prefs แล้ว pm clear -> เกมสร้าง guest ใหม่
  แล้วกดในเกมจนผ่าน tutorial (ถึง Lv 3) -> Ctrl+C เพื่อจบ (ถอด routing คืนให้)

ผล: logs/newid_<เวลา>.jsonl  (1 บรรทัด/คำขอ: host, method, url, headers, body ทั้งไป-กลับ)
     + บรรทัด type=tls_fail = host ที่ไม่ยอมรับ cert mitm (ปักหมุด) -> ต้องหาทางอื่นเฉพาะ host นั้น

⚠️ --clear ลบข้อมูลเกมในเครื่องนั้น (บัญชีเดิมหายจากเครื่อง ถ้าไม่ได้ผูก/ไม่มี creds) — สำรอง prefs ไว้ที่ logs/prefs_backup_<เวลา>/

ต้อง: pip install mitmproxy ; เครื่อง root ได้ ; มี iptables
"""
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ADB = os.path.join(ROOT, "adb", "adb.exe")
PKG = "com.linecorp.LGRGS"
PORT = 8443
LOG_DIR = os.path.join(HERE, "logs")

# ------------------------------------------------------------------ mitmproxy addon
# (ไฟล์นี้ถูกโหลดซ้ำเป็น addon โดย mitmdump -s; ส่วนนี้ทำงานเฉพาะตอนนั้น)
try:
    from mitmproxy import http, tls  # noqa: F401
    _IN_MITM = True
except Exception:
    _IN_MITM = False

if _IN_MITM:
    _OUT = os.environ.get("LGR_NEWID_LOG") or os.path.join(LOG_DIR, "newid.jsonl")

    def _w(rec):
        with open(_OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _body(m):
        if not m.raw_content:
            return ""
        try:
            return m.get_text(strict=True)
        except Exception:
            return "b64:" + __import__("base64").b64encode(m.raw_content).decode()

    def request(flow):
        # reverse mode ชี้ปลายทางตายตัว -> เปลี่ยนเป็น host จริงตาม SNI ที่แอปขอ
        sni = flow.client_conn.sni
        if sni:
            flow.request.host = sni
            flow.request.port = 443
            flow.request.headers["Host"] = sni

    _VIA = os.environ.get("LGR_NEWID_VIA")   # "127.0.0.1:1081" = ออกเน็ตผ่าน WG (wireproxy [http])

    def server_connect(data):
        if _VIA:
            h, p = _VIA.rsplit(":", 1)
            data.server.via = ("http", (h, int(p)))

    def response(flow):
        q, r = flow.request, flow.response
        _w({
            "t": time.time(), "type": "http",
            "host": q.host, "method": q.method, "url": q.pretty_url,
            "req_headers": list(q.headers.items(multi=True)), "req_body": _body(q),
            "status": r.status_code,
            "resp_headers": list(r.headers.items(multi=True)), "resp_body": _body(r),
        })
        print(f"[{r.status_code}] {q.method} {q.pretty_url[:140]}", flush=True)

    def tls_failed_client(data):
        sni = data.context.client.sni
        _w({"t": time.time(), "type": "tls_fail", "sni": sni,
            "error": str(data.conn.error)})
        print(f"[TLS-FAIL/pinned?] {sni}: {data.conn.error}", flush=True)


# ------------------------------------------------------------------ runner
def adb(serial, *args):
    import subprocess
    return subprocess.run([ADB, "-s", serial, *args], capture_output=True, text=True)


def su(serial, cmd):
    # adb shell ต่อ argv ด้วยช่องว่าง -> ต้องห่อทั้งคำสั่งเป็นก้อนเดียว ไม่งั้น su -c ได้แค่คำแรก
    return adb(serial, "shell", "su -c '" + cmd.replace("'", "'\\''") + "'")


def backup_and_clear(serial, stamp):
    dst = os.path.join(LOG_DIR, f"prefs_backup_{stamp}")
    os.makedirs(dst, exist_ok=True)
    su(serial, f"rm -rf /sdcard/lgr_prefs_bak; cp -r /data/data/{PKG}/shared_prefs /sdcard/lgr_prefs_bak")
    adb(serial, "pull", "/sdcard/lgr_prefs_bak", dst)
    adb(serial, "shell", "am", "force-stop", PKG)
    adb(serial, "shell", "pm", "clear", PKG)
    print(f"[clear] สำรอง prefs -> {dst} แล้ว pm clear เรียบร้อย")


CA_DIR = "/data/local/tmp/lgr_cacerts"
_SAVED_PROXY = {}


def install_ca(serial):
    """ติดตั้ง CA ของ mitmproxy เป็น system cert ชั่วคราว (bind-mount ทับ cacerts)
    เกม (libcurl) ไม่เช็ค cert อยู่แล้ว แต่ WebView (หน้า game-terms) / ส่วน Java ของ Trident เช็ค"""
    import subprocess
    pem = os.path.join(os.path.expanduser("~"), ".mitmproxy", "mitmproxy-ca-cert.pem")
    if not os.path.exists(pem):
        print("[ca] ยังไม่มี ~/.mitmproxy/mitmproxy-ca-cert.pem (mitmdump ยังไม่เคยรัน) -> ข้าม")
        return
    # ชื่อไฟล์ = subject_hash_old (md5 ของ subject DER, 4 ไบต์แรกแบบ little-endian) ไม่ต้องพึ่ง openssl
    import hashlib
    from cryptography import x509
    cert = x509.load_pem_x509_certificate(open(pem, "rb").read())
    h = "%08x" % int.from_bytes(hashlib.md5(cert.subject.public_bytes()).digest()[:4], "little")
    adb(serial, "push", pem, f"/data/local/tmp/{h}.0")
    su(serial, f"umount /system/etc/security/cacerts 2>/dev/null; rm -rf {CA_DIR}; mkdir -p {CA_DIR}; "
               f"cp /system/etc/security/cacerts/* {CA_DIR}/; mv /data/local/tmp/{h}.0 {CA_DIR}/; "
               f"chmod 644 {CA_DIR}/*; chown root:root {CA_DIR}/*; "
               f"chcon -R u:object_r:system_file:s0 {CA_DIR}; "
               f"mount --bind {CA_DIR} /system/etc/security/cacerts")
    ok = su(serial, f"ls /system/etc/security/cacerts/{h}.0").returncode == 0
    print(f"[ca] mitm CA เป็น system cert: {'OK' if ok else 'ไม่สำเร็จ'} ({h}.0)")


def setup(serial):
    adb(serial, "reverse", f"tcp:{PORT}", f"tcp:{PORT}")
    # ล้างของค้างจาก capture_run (hosts bind-mount + กฎ REDIRECT เก่า) แล้วส่ง
    # ทุก TCP 443 ที่ไม่ใช่ localhost -> mitm (adb reverse) ; DNS ไม่ต้องแตะ
    su(serial, f"umount /system/etc/hosts 2>/dev/null; iptables -t nat -F OUTPUT; "
               f"sysctl -w net.ipv4.conf.all.route_localnet=1 >/dev/null 2>&1; "
               f"iptables -t nat -A OUTPUT -p tcp ! -d 127.0.0.1 --dport 443 "
               f"-j DNAT --to-destination 127.0.0.1:{PORT}")
    # proxy ระบบ (http_proxy) ค้าง/ตาย -> WebView หน้า game-terms ERR_TIMED_OUT (เกม native ไม่สนค่านี้)
    old = adb(serial, "shell", "settings get global http_proxy").stdout.strip()
    if old and old not in ("null", ":0"):
        print(f"[proxy] ปิด proxy ระบบ {old} ชั่วคราว (คืนให้ตอนจบ)")
        _SAVED_PROXY[serial] = old
        adb(serial, "shell", "settings put global http_proxy :0")
    rules = su(serial, "iptables -t nat -S OUTPUT").stdout
    if "DNAT" not in rules:
        print(f"[routing] ⚠️ ติดตั้งกฎ iptables ไม่สำเร็จ:\n{rules}")
    print(f"[routing] {serial}: TCP 443 ทุก host -> mitm:{PORT}")


def find_mitmdump():
    # PATH ของ PowerShell บางเครื่องไม่มีโฟลเดอร์ Scripts ของ Python -> หาข้าง python.exe เอง
    import shutil
    import sysconfig
    for c in (shutil.which("mitmdump"),
              os.path.join(sysconfig.get_path("scripts"), "mitmdump.exe"),
              os.path.join(sysconfig.get_path("scripts", "nt_user"), "mitmdump.exe"),
              os.path.join(os.path.dirname(sys.executable), "Scripts", "mitmdump.exe")):
        if c and os.path.exists(c):
            return c
    sys.exit("[error] หา mitmdump ไม่เจอ -> pip install mitmproxy")


def _port_open(h, p):
    import socket
    try:
        socket.create_connection((h, p), timeout=2).close()
        return True
    except OSError:
        return False


def start_wireproxy(conf_name, bind):
    """เปิด wireproxy ของเราเอง (มีแค่ [http] ที่ bind) -> ไม่ชนพอร์ต 1080/9443 ของ wg-proxy.bat/web_app"""
    import subprocess
    wg_dir = os.path.join(ROOT, "wg")
    if not conf_name:
        confs = sorted(f for f in os.listdir(wg_dir) if f.endswith(".conf")) if os.path.isdir(wg_dir) else []
        sg = [f for f in confs if "Singapore" in f]
        if not confs:
            sys.exit(f"[error] ไม่มีไฟล์ .conf ใน {wg_dir}")
        conf_name = (sg or confs)[0]
    src = os.path.join(wg_dir, conf_name)
    if not os.path.exists(src):
        sys.exit(f"[error] ไม่มีไฟล์ WG {src}")
    conf = os.path.join(LOG_DIR, "wireproxy_newid.conf")
    with open(conf, "w", encoding="utf-8") as f:
        f.write(open(src, encoding="utf-8").read() + f"\n[http]\nBindAddress = {bind}\n")
    p = subprocess.Popen([os.path.join(HERE, "tools", "wireproxy.exe"), "-s", "-c", conf],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    h, port = bind.rsplit(":", 1)
    for _ in range(30):
        if _port_open(h, int(port)):
            print(f"[wg] เปิด wireproxy เอง ({conf_name}) -> http://{bind}")
            return p
        time.sleep(0.5)
    p.terminate()
    sys.exit(f"[error] wireproxy เปิดพอร์ต {bind} ไม่ขึ้น (เช็คไฟล์ {conf_name})")


def teardown(serial):
    adb(serial, "reverse", "--remove", f"tcp:{PORT}")
    su(serial, f"iptables -t nat -F OUTPUT 2>/dev/null; "
               f"umount /system/etc/security/cacerts 2>/dev/null; rm -rf {CA_DIR}")
    if serial in _SAVED_PROXY:
        adb(serial, "shell", f"settings put global http_proxy {_SAVED_PROXY.pop(serial)}")
    print(f"[routing] {serial}: ถอด routing แล้ว")


def main():
    import argparse
    import signal
    import subprocess
    ap = argparse.ArgumentParser()
    ap.add_argument("serial", nargs="?", help="เว้นไว้ = ใช้เครื่องเดียวที่ adb เห็น")
    ap.add_argument("--clear", action="store_true", help="สำรอง prefs + pm clear ก่อนเริ่ม")
    ap.add_argument("--wg", nargs="?", const="127.0.0.1:1081", default="127.0.0.1:1081",
                    help="mitm ออกเน็ตผ่าน WG (HTTP proxy ของ wireproxy) — เปิดเป็นดีฟอลต์ที่ 127.0.0.1:1081")
    ap.add_argument("--no-wg", dest="wg", action="store_const", const=None,
                    help="ต่อตรงด้วย IP ของ PC (ไม่ผ่าน WG)")
    ap.add_argument("--wg-conf", default=None,
                    help="ไฟล์ใน ../wg ที่ใช้ตอนต้องเปิด wireproxy เอง (ไม่ใส่ = Singapore/ไฟล์แรก)")
    a = ap.parse_args()
    if not a.serial:
        out = subprocess.run([ADB, "devices"], capture_output=True, text=True).stdout
        devs = [l.split()[0] for l in out.splitlines()[1:] if l.strip().endswith("device")]
        # MuMu โผล่ 2 พอร์ต (เช่น 16416 + 5557) แต่เป็นเครื่องเดียวกัน -> ยุบตาม android_id
        seen = {}
        for d in devs:
            aid = adb(d, "shell", "settings get secure android_id").stdout.strip()
            if aid and aid not in seen:
                seen[aid] = d
        devs = list(seen.values())
        if len(devs) != 1:
            print(f"[error] adb เห็น {len(devs)} เครื่อง {devs} -> ระบุ serial เอง เช่น "
                  "python capture_newid.py 127.0.0.1:16512 --clear")
            sys.exit(1)
        a.serial = devs[0]
        print(f"[adb] ใช้เครื่อง {a.serial}")

    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = os.path.join(LOG_DIR, f"newid_{stamp}.jsonl")
    env = dict(os.environ, LGR_NEWID_LOG=log)
    wgp = None
    if a.wg:
        h, p = a.wg.rsplit(":", 1)
        if not _port_open(h, int(p)):
            wgp = start_wireproxy(a.wg_conf, a.wg)
        env["LGR_NEWID_VIA"] = a.wg
        print(f"[wg] mitm ออกเน็ตผ่าน WG {a.wg}")

    if a.clear:
        backup_and_clear(a.serial, stamp)

    mitm = subprocess.Popen(
        [find_mitmdump(), "--mode", "reverse:https://rangers-api.line-apps.com",
         "--listen-port", str(PORT), "--set", "connection_strategy=lazy",
         "--set", "keep_host_header=true", "--ssl-insecure",
         "-s", os.path.abspath(__file__), "-q"],
        env=env,
    )
    time.sleep(4)
    setup(a.serial)
    install_ca(a.serial)
    adb(a.serial, "shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    print(f"\n>>> เปิดเกมแล้ว กดผ่าน tutorial ไปจนถึง Lv 3  (log: {log})")
    print(">>> เสร็จแล้วกด Ctrl+C\n")
    try:
        mitm.wait()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            mitm.send_signal(signal.SIGTERM)
        except Exception:
            pass
        teardown(a.serial)
        if wgp:
            wgp.terminate()
        print(f"[done] log -> {log}")


if __name__ == "__main__":
    main()
