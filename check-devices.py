"""เครื่องมือตรวจว่าทำไมบอทไม่กด - รันตอนบอทกำลังค้างอยู่ได้เลย

    python check-devices.py

ตรวจทุกเครื่องที่ต่ออยู่ แล้วบอกว่า:
  - เกมเปิดอยู่ไหม (ถ้าไม่เปิด บอทควรจะ relaunch)
  - จอตอนนี้ตรงกับ template ตัวไหนมากสุด และได้กี่คะแนน
  - ถ้ามีตัวไหนถึง 0.95 แปลว่าบอท "ควรจะกด" แต่ไม่กด -> ปัญหาอยู่ที่ฝั่งกด
  - ถ้าไม่มีตัวไหนถึงเลย -> บอทไม่มีอะไรให้กด ปัญหาอยู่ที่จอไปอยู่สถานะที่ไม่รู้จัก

เซฟภาพจอของทุกเครื่องไว้ที่ _check/ ให้เปิดดูได้ว่าจริง ๆ ค้างอยู่หน้าไหน
"""
import os
import struct
import subprocess
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_check")
PKG = "com.linecorp.LGRGS"
NW = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def find_adb():
    for p in [os.path.join(HERE, "adb", "adb.exe"),
              os.path.join(HERE, "adb", "adb"), "adb"]:
        try:
            subprocess.run([p, "version"], capture_output=True, timeout=10, **NW)
            return p
        except Exception:
            continue
    return None


ADB = find_adb()
if not ADB:
    print("หา adb ไม่เจอ")
    sys.exit(1)


def adb(dev, args, timeout=20):
    try:
        return subprocess.run([ADB, "-s", dev] + args, capture_output=True,
                              timeout=timeout, **NW)
    except Exception:
        return None


def decode(raw):
    """เหมือนที่บอทใช้: header 12 หรือ 16 ไบต์ แล้วแต่ Android version"""
    if raw is None or len(raw) < 16:
        return None
    w, h, _ = struct.unpack("<III", raw[:12])
    if not (0 < w <= 4096 and 0 < h <= 4096):
        return None
    body = w * h * 4
    off = 16 if len(raw) >= 16 + body else (12 if len(raw) >= 12 + body else None)
    if off is None:
        return None
    rgba = np.frombuffer(raw[off:off + body], np.uint8).reshape((h, w, 4))
    return cv2.cvtColor(cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR), cv2.COLOR_BGR2GRAY)


def load_templates():
    d = os.path.join(HERE, "img")
    out = {}
    for n in sorted(os.listdir(d)):
        if not n.lower().endswith((".png", ".bmp")):
            continue
        t = cv2.imread(os.path.join(d, n), 0)
        if t is not None and t.size:
            out[n] = t
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    tmpl = load_templates()
    print(f"adb       : {ADB}")
    print(f"templates : {len(tmpl)} รูปใน img/\n")

    res = subprocess.run([ADB, "devices"], capture_output=True, text=True, **NW)
    devs = [l.split()[0] for l in res.stdout.splitlines()[1:]
            if l.strip().endswith("device")]
    if not devs:
        print("ไม่มีเครื่องต่ออยู่เลย - บอทกดอะไรไม่ได้อยู่แล้ว")
        print("ลองสั่ง:  adb devices   ดูว่าเห็นกี่เครื่อง")
        return
    print(f"เจอ {len(devs)} เครื่อง\n")
    print(f"{'device':<22} {'เกม':<10} {'จอ':<12} {'template ที่ใกล้สุด':<26} คะแนน")
    print("-" * 88)

    would_click = idle = noscreen = 0
    for d in devs:
        r = adb(d, ["shell", "pidof", PKG], timeout=10)
        alive = bool(r and r.stdout.decode(errors="ignore").strip())

        cap = adb(d, ["exec-out", "screencap"], timeout=25)
        gray = decode(cap.stdout) if cap else None
        if gray is None:
            noscreen += 1
            print(f"{d:<22} {'เปิด' if alive else 'ปิด':<10} {'จับจอไม่ได้':<12}")
            continue

        cv2.imwrite(os.path.join(OUT, f"{d.replace(':', '_')}.png"), gray)
        h, w = gray.shape

        best_n, best_s = "-", -1.0
        for n, t in tmpl.items():
            if t.shape[0] > h or t.shape[1] > w:
                continue
            s = float(cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED).max())
            if s > best_s:
                best_n, best_s = n, s

        if best_s >= 0.95:
            would_click += 1
            note = "  <== ควรกดได้"
        else:
            idle += 1
            note = ""
        print(f"{d:<22} {'เปิด' if alive else 'ปิด':<10} {f'{w}x{h}':<12} "
              f"{best_n:<26} {best_s:.3f}{note}")

    print("-" * 88)
    print(f"\nสรุป: {would_click} เครื่องมีของให้กด, {idle} เครื่องไม่มี, "
          f"{noscreen} เครื่องจับจอไม่ได้")
    print(f"ภาพจอทุกเครื่องอยู่ที่: {OUT}\n")

    if noscreen:
        print("* จับจอไม่ได้ = บอทมองไม่เห็นอะไรเลย ปัญหาอยู่ที่ adb/screencap")
    if would_click:
        print("* มีเครื่องที่ template ตรงถึง 0.95")
        print("  แปลว่า 'หาเจอ' ทำงานปกติ แต่ยังบอกไม่ได้ว่าบอทควรกดตัวนั้นตอนนี้ไหม")
        print("  เพราะแต่ละสเต็ปบอทมองหาเฉพาะรูปที่มันรออยู่ ไม่ได้มองหาทุกรูป")
        print("  -> ต้องดู log ว่าตอนนั้นบอทรออะไรอยู่ (บรรทัด 'Waiting for ...')")
    if idle and not would_click:
        print("* ไม่มีเครื่องไหนเจอ template เลย = บอทไม่มีอะไรให้กดจริง ๆ")
        print("  -> เปิดภาพใน _check/ ดูว่าเกมค้างอยู่หน้าไหน")
        print("  -> ถ้าเป็นหน้าที่ไม่มี template รองรับ ต้องเพิ่มรูปใหม่ใน img/")
    print("\nสิ่งที่ช่วยได้มากสุดคือ log ของบอทตอนที่มันนิ่ง")
    print("ก็อปจากช่อง log ในโปรแกรมมาสัก 30 บรรทัด")


if __name__ == "__main__":
    main()
