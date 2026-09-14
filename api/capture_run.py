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


def adb(serial, *args, **kw):
    return subprocess.run([ADB, "-s", serial, *args], capture_output=True, text=True, **kw)


def setup(serial):
    adb(serial, "reverse", f"tcp:{PORT}", f"tcp:{PORT}")
    sh = (
        "cp /system/etc/hosts /data/local/tmp/hosts 2>/dev/null; "
        "grep -q rangers-api /data/local/tmp/hosts || "
        "echo '127.0.0.1 rangers-api.line-apps.com' >> /data/local/tmp/hosts; "
        "mount --bind /data/local/tmp/hosts /system/etc/hosts; "
        "iptables -t nat -A OUTPUT -p tcp -d 127.0.0.1 --dport 443 -j REDIRECT --to-ports %d" % PORT
    )
    adb(serial, "shell", "su", "-c", sh)
    print(f"[routing] ตั้งค่าเครื่อง {serial} แล้ว (hosts+iptables+reverse)")


def teardown(serial):
    adb(serial, "reverse", "--remove", f"tcp:{PORT}")
    adb(serial, "shell", "su", "-c",
        "iptables -t nat -F OUTPUT 2>/dev/null; umount /system/etc/hosts 2>/dev/null")
    print(f"[routing] ถอด routing เครื่อง {serial} คืนสภาพเดิมแล้ว")


def main():
    if len(sys.argv) < 2:
        print("usage: python capture_run.py <serial>   (เช่น 127.0.0.1:16512)")
        sys.exit(1)
    serial = sys.argv[1]
    addon = os.path.join(HERE, "capture_credential.py")
    mitm = subprocess.Popen(
        ["mitmdump", "--mode", f"reverse:{UP}", "--listen-port", str(PORT), "-s", addon, "-q"],
    )
    time.sleep(4)
    setup(serial)
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
