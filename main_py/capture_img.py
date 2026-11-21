# -*- coding: utf-8 -*-
"""จับภาพจอ emulator ผ่าน adb (ได้ภาพเดียวกับที่บอทเห็นเป๊ะ) เอาไว้ crop รูป template ใหม่

วิธีใช้ (รันบนเครื่องที่มี MuMu/บอท):
    python capture_img.py                  -> จับจาก 127.0.0.1:16448
    python capture_img.py 127.0.0.1:16480  -> ระบุ device เอง

ได้ไฟล์ capture/screen_<เวลา>.png แล้วเอาไปเปิดใน Paint
crop เฉพาะส่วนปุ่ม -> save ทับรูปชื่อเดิมในโฟลเดอร์ img/

ห้ามใช้ปุ่ม PrintScreen หรือโปรแกรมจับหน้าจอ Windows เด็ดขาด
เพราะขนาดและสีจะไม่ตรงกับที่บอท capture ผ่าน adb
"""
import os
import sys
import shutil
import datetime
import subprocess


def find_adb():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(here, "adb", "adb.exe"), shutil.which("adb"), "adb"]
    for c in candidates:
        if not c:
            continue
        try:
            subprocess.run([c, "--version"], capture_output=True, timeout=5, check=True)
            return c
        except Exception:
            continue
    return None


def main():
    device = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:16448"
    adb = find_adb()
    if not adb:
        print("หา adb ไม่เจอ - วางโฟลเดอร์ adb ไว้ข้างไฟล์นี้ หรือติดตั้ง adb ใน PATH")
        return
    subprocess.run([adb, "connect", device], capture_output=True, timeout=10)
    r = subprocess.run(
        [adb, "-s", device, "exec-out", "screencap", "-p"],
        capture_output=True, timeout=15,
    )
    if r.returncode != 0 or len(r.stdout) < 100:
        print(f"จับภาพไม่สำเร็จ - เช็คว่า emulator เปิดอยู่และ device ถูกต้อง: {device}")
        return
    os.makedirs("capture", exist_ok=True)
    name = os.path.join(
        "capture", "screen_" + datetime.datetime.now().strftime("%H%M%S") + ".png"
    )
    with open(name, "wb") as f:
        f.write(r.stdout)
    print(f"บันทึกแล้ว: {name} ({len(r.stdout)} bytes)")


if __name__ == "__main__":
    main()
