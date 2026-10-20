#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capture_run.py — ตั้ง MITM + routing ให้อัตโนมัติ เพื่อจับ credential ของ 1 เครื่อง
(ไม่ต้องพิมพ์ adb/iptables เอง) จบแล้วเก็บกวาดคืนสภาพเดิมให้

ใช้:  python capture_run.py 127.0.0.1:16512
      แล้วเปิดเกมในอีมูฯ เครื่องนั้น กด PLAY ให้ล็อกอิน 1 ครั้ง
      พอเห็น "[creds] saved acct=..." = ได้แล้ว กด Ctrl+C เพื่อเลิก (มันจะถอด routing ให้)

ต้อง: pip install mitmproxy ; เครื่อง root ได้ ; อีมูฯ มี iptables (MuMu/LDPlayer มี)
creds.json จะถูกเขียนโดย capture_credential.py
"""
import subprocess
import sys
import os
import time
import signal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)   # โฟลเดอร์โปรเจคหลัก (มี adb/)
ADB = os.path.join(ROOT, "adb", "adb.exe")
PORT = 8443
UP = "https://rangers-api.line-apps.com"


def find_mitmdump():
    # ตัวเดียวกับ capture_newid (PATH ของบางเครื่องไม่มีโฟลเดอร์ Scripts ของ Python)
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    from capture_newid import find_mitmdump as _find
    return _find()


def adb(serial, *args, **kw):
    return subprocess.run([ADB, "-s", serial, *args], capture_output=True, text=True, **kw)


def sh_quote(s):
    """single-quote สำหรับ POSIX sh: ปิด quote -> \\' -> เปิดใหม่  (a'b -> 'a'\\''b')
    (เดิมเขียน "'\\''" แบบไม่ใช่ raw ใน Python = ''' -> quote แตก คำสั่งที่มี ' ถูกตัดกลางทาง)"""
    return "'" + s.replace("'", "'\\''") + "'"


def su_command(cmd):
    """สตริงที่ส่งให้ adb shell: ทั้งคำสั่งเป็น argument เดียวของ su -c"""
    return "su -c " + sh_quote(cmd)


def su(serial, cmd):
    # adb shell ต่อ argv ด้วยช่องว่าง -> ต้องห่อทั้งคำสั่งเป็นก้อนเดียว ไม่งั้น su -c ได้แค่คำแรก
    # (adbd ของ MuMu ไม่ใช่ root -> mount/iptables ที่หลุดออกนอก su จะล้ม)
    return adb(serial, "shell", su_command(cmd))


RULE = "OUTPUT -p tcp -d 127.0.0.1 --dport 443 -j REDIRECT --to-ports %d" % PORT
HOSTS = "/system/etc/hosts"
# ไฟล์ hosts สำเนาของสคริปต์นี้เอง (ชื่อเฉพาะ ไม่ชนกับ /data/local/tmp/hosts ของ capture_auto)
HOSTS_COPY = "/data/local/tmp/lgr_capture_run_hosts"
_CREATED = {}   # serial -> {"reverse","hosts_copy","hosts","rule"} ที่สคริปต์นี้สร้างเอง (teardown ถอนเฉพาะนี้)


def _hosts_mounted(serial):
    return (" %s " % HOSTS) in su(serial, "cat /proc/mounts").stdout


def _rule_exists(serial):
    return su(serial, "iptables -t nat -C " + RULE).returncode == 0


def setup(serial):
    """ตั้ง routing เฉพาะ rangers-api -> mitm. ถ้าเจอของเดิมค้างอยู่ -> หยุด (ไม่แตะของคนอื่น)
    คืน True เมื่อตั้งครบและตรวจแล้ว"""
    made = _CREATED.setdefault(serial, {})
    if f"tcp:{PORT}" in adb(serial, "reverse", "--list").stdout:
        print(f"[routing] หยุด: มี adb reverse tcp:{PORT} อยู่ก่อนแล้ว (ไม่ใช่ของสคริปต์นี้)")
        return False
    if _hosts_mounted(serial) or _rule_exists(serial):
        print(f"[routing] หยุด: มี bind-mount {HOSTS} หรือกฎ REDIRECT ค้างอยู่ก่อนแล้ว")
        return False

    if su(serial, f"test -e {HOSTS_COPY}").returncode == 0:
        print(f"[routing] หยุด: มี {HOSTS_COPY} ค้างอยู่ก่อนแล้ว (ตรวจ/ลบเองก่อน)")
        return False

    # บันทึก ownership หลังยืนยันว่าแต่ละขั้นสำเร็จจริงเท่านั้น -> teardown ถอนเฉพาะของที่ตั้งได้
    adb(serial, "reverse", f"tcp:{PORT}", f"tcp:{PORT}")
    if f"tcp:{PORT}" in adb(serial, "reverse", "--list").stdout:
        made["reverse"] = True
    su(serial, f"cp {HOSTS} {HOSTS_COPY} && "
               f"{{ grep -q rangers-api {HOSTS_COPY} || "
               f"echo '127.0.0.1 rangers-api.line-apps.com' >> {HOSTS_COPY}; }}")
    if su(serial, f"test -e {HOSTS_COPY}").returncode == 0:
        made["hosts_copy"] = True
        su(serial, f"mount --bind {HOSTS_COPY} {HOSTS}")
        if _hosts_mounted(serial):
            made["hosts"] = True
    if made.get("hosts"):
        su(serial, "iptables -t nat -A " + RULE)
        if _rule_exists(serial):
            made["rule"] = True

    ok = made.get("reverse") and made.get("hosts") and made.get("rule")
    print(f"[routing] {serial}: reverse={bool(made.get('reverse'))} "
          f"hosts={bool(made.get('hosts'))} rule={bool(made.get('rule'))} -> {'OK' if ok else 'ไม่ครบ'}")
    return bool(ok)


def teardown(serial):
    """ถอนเฉพาะที่ setup() สร้าง: ลบกฎตัวเดียว (-D ไม่ใช่ -F), umount hosts, ลบสำเนา hosts, ลบ reverse
    แล้วตรวจซ้ำ -> คืน list ของ resource ที่ยังค้าง (ว่าง = ถอนครบ) ; ค้าง = แจ้ง ไม่ลบแบบกว้าง"""
    made = _CREATED.pop(serial, {})
    left = []
    if made.get("rule"):
        su(serial, "iptables -t nat -D " + RULE)
        if _rule_exists(serial):
            left.append(f"iptables -t nat {RULE}")
    if made.get("hosts"):
        su(serial, f"umount {HOSTS}")
        if _hosts_mounted(serial):
            left.append(f"bind-mount {HOSTS}")
    if made.get("hosts_copy") and f"bind-mount {HOSTS}" not in left:
        su(serial, f"rm -f {HOSTS_COPY}")
        if su(serial, f"test -e {HOSTS_COPY}").returncode == 0:
            left.append(HOSTS_COPY)
    if made.get("reverse"):
        adb(serial, "reverse", "--remove", f"tcp:{PORT}")
        if f"tcp:{PORT}" in adb(serial, "reverse", "--list").stdout:
            left.append(f"adb reverse tcp:{PORT}")
    print(f"[routing] ถอด routing เครื่อง {serial} (เฉพาะที่สคริปต์สร้าง: {sorted(made) or 'ไม่มี'})")
    if left:
        print(f"[routing] ⚠️ ยังค้าง ต้องตรวจ/ถอนเอง: {left}")
    return left


def main():
    if len(sys.argv) < 2:
        print("usage: python capture_run.py <serial>   (เช่น 127.0.0.1:16512)")
        sys.exit(1)
    serial = sys.argv[1]
    addon = os.path.join(HERE, "capture_credential.py")
    mitm = subprocess.Popen(
        [find_mitmdump(), "--mode", f"reverse:{UP}", "--listen-port", str(PORT), "-s", addon, "-q"],
    )
    time.sleep(4)
    if not setup(serial):
        print("[routing] ตั้งค่าไม่ครบ -> ยกเลิก (ถอนเฉพาะที่ตั้งไปแล้ว)")
        mitm.terminate()
        teardown(serial)
        sys.exit(2)
    print("\n>>> เปิดเกมในอีมูฯ เครื่องนี้ กด PLAY ให้ล็อกอิน 1 ครั้ง")
    print(">>> รอจนเห็น '[creds] saved acct=...' แล้วกด Ctrl+C เพื่อจบ\n")
    try:
        mitm.wait()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            mitm.send_signal(signal.SIGTERM)
        except Exception:
            pass
        teardown(serial)


if __name__ == "__main__":
    main()
