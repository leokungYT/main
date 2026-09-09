# -*- coding: utf-8 -*-
"""เครื่องมือวินิจฉัย: ทำไมบอทไม่เจอปุ่ม RETRY (fixnet) - รันตอนที่ป๊อปอัพขึ้นอยู่บนจอ

วิธีใช้:  python check-fixnet.py                 (ทุกเครื่องที่ต่ออยู่)
          python check-fixnet.py emulator-5554   (เครื่องเดียว)
ผลลัพธ์:  ความละเอียดจอ + คะแนน match ของแต่ละรูปในทุกสเกล + เซฟภาพจอไว้ที่ debug-timeout/
"""
import os
import sys
import subprocess

import cv2
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
_cands = [os.path.join(HERE, "adb", "adb.exe"), os.path.join(HERE, "adb", "adb")]
ADB = next((p for p in _cands if os.path.exists(p)), "adb")

TEMPLATES = ["fixnet-tiket.png", "fixnet.png", "fixnet1.png", "fixnetv3.png",
             "refresh.png", "checkline.png", "fixid.png", "check.png"]
SCALES = [0.5, 0.67, 0.75, 1.0, 1.33, 1.5, 1.67, 2.0]


def devices():
    out = subprocess.run([ADB, "devices"], capture_output=True, text=True).stdout
    return [l.split()[0] for l in out.splitlines()[1:] if l.strip().endswith("device")]


def grab(dev):
    r = subprocess.run([ADB, "-s", dev, "exec-out", "screencap", "-p"], capture_output=True, timeout=20)
    return cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)


def main():
    targets = sys.argv[1:] or devices()
    if not targets:
        print("ไม่พบเครื่องที่ต่ออยู่ (adb devices ว่าง)")
        return
    os.makedirs(os.path.join(HERE, "debug-timeout"), exist_ok=True)
    for dev in targets:
        print("=" * 72)
        print(f"[{dev}]")
        try:
            img = grab(dev)
        except Exception as e:
            print("  จับจอไม่ได้:", e)
            continue
        if img is None:
            print("  จับจอไม่ได้ (decode ล้มเหลว)")
            continue
        h, w = img.shape[:2]
        flag = "" if (w, h) == (960, 540) else "   <-- ไม่ใช่ 960x540 ! (template ทุกรูปตัดจาก 960x540)"
        print(f"  ความละเอียดจอ: {w}x{h}{flag}")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if (w, h) != (960, 540):
            gray = cv2.resize(gray, (960, 540), interpolation=cv2.INTER_AREA)
            print("  (ย่อเป็น 960x540 ก่อนเทียบ เหมือนที่บอทตัวใหม่ทำ)")
        out = os.path.join(HERE, "debug-timeout", f"diag_{dev.replace(':', '_')}.png")
        cv2.imwrite(out, img)
        print(f"  เซฟภาพจอ: {out}")
        print(f"  {'รูป':<18}{'คะแนนสูงสุด':>12}  {'สเกล':>5}  ตำแหน่ง        (ต้อง >= 0.80 ถึงจะกด)")
        for name in TEMPLATES:
            t0 = cv2.imread(os.path.join(HERE, "img", name), 0)
            if t0 is None:
                print(f"  {name:<18} ไม่มีไฟล์")
                continue
            best = (-1.0, 1.0, (0, 0))
            for sc in SCALES:
                if sc == 1.0:
                    t = t0
                else:
                    t = cv2.resize(t0, None, fx=sc, fy=sc,
                                   interpolation=cv2.INTER_AREA if sc < 1 else cv2.INTER_CUBIC)
                if gray.shape[0] < t.shape[0] or gray.shape[1] < t.shape[1]:
                    continue
                _, v, _, loc = cv2.minMaxLoc(cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED))
                if v > best[0]:
                    best = (v, sc, loc)
            v, sc, loc = best
            mark = "  <-- เจอ" if v >= 0.8 else ("  (เกือบ - ลด similarity ได้)" if v >= 0.7 else "")
            print(f"  {name:<18}{v:>12.3f}  {sc:>5.2f}  {str(loc):<14}{mark}")
    print("=" * 72)
    print("ก๊อปข้อความด้านบน + รูปใน debug-timeout/ ส่งมาให้ดูได้เลย")


if __name__ == "__main__":
    main()
