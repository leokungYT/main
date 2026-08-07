"""หาว่าทำไมรูปถึง match ไม่ติด - รันตอนที่ป๊อปอัพ/ปุ่มนั้นอยู่บนจอ

    python check-match.py                     # เช็ค fixgems กับ fixgems1
    python check-match.py fixgems.png ok.png  # เช็ครูปที่ระบุ

จับจอทุกเครื่องที่ต่ออยู่ แล้วรายงานว่า:
  - คะแนนที่ขนาดปกติ (ที่บอทใช้จริง) ได้เท่าไหร่ ผ่านเกณฑ์ 0.8 ไหม
  - ถ้าไม่ผ่าน ลองย่อ/ขยายรูปดูว่าขนาดไหนถึงจะ match
    -> ถ้าต้องย่อ/ขยายถึงจะเจอ = รูปถูกตัดมาจากจอคนละความละเอียด ต้องตัดใหม่
    -> ถ้าขนาดปกติดีที่สุดแต่คะแนนยังต่ำ = รูปในเกมเปลี่ยนไป ต้องตัดใหม่เหมือนกัน
ภาพจอถูกเซฟไว้ที่ _check/ เปิดดูเทียบได้
"""
import os
import struct
import subprocess
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_check")
NW = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
THRESHOLD = 0.8


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


def decode(raw):
    """เหมือนที่บอทใช้ - header 12 หรือ 16 ไบต์ แล้วแต่ Android version"""
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
    return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)


def best_at(screen, tmpl):
    if tmpl.shape[0] > screen.shape[0] or tmpl.shape[1] > screen.shape[1]:
        return None, None
    r = cv2.matchTemplate(screen, tmpl, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(r)
    return float(mx), (loc[0] + tmpl.shape[1] // 2, loc[1] + tmpl.shape[0] // 2)


def main():
    names = sys.argv[1:] or ["fixgems.png", "fixgems1.png"]
    os.makedirs(OUT, exist_ok=True)

    res = subprocess.run([ADB, "devices"], capture_output=True, text=True, **NW)
    devs = [l.split()[0] for l in res.stdout.splitlines()[1:]
            if l.strip().endswith("device")]
    if not devs:
        print("ไม่มีเครื่องต่ออยู่")
        return
    print(f"adb    : {ADB}")
    print(f"เครื่อง : {len(devs)}")
    print(f"เกณฑ์   : {THRESHOLD}\n")

    tmpls = {}
    for n in names:
        p = os.path.join(HERE, "img", n)
        t = cv2.imread(p, cv2.IMREAD_COLOR)
        if t is None:
            print(f"[!] อ่านรูปไม่ได้: img/{n}")
        else:
            tmpls[n] = t
    if not tmpls:
        return

    for d in devs:
        try:
            cap = subprocess.run([ADB, "-s", d, "exec-out", "screencap"],
                                 capture_output=True, timeout=25, **NW)
        except Exception as e:
            print(f"{d}: จับจอไม่ได้ ({e})")
            continue
        scr = decode(cap.stdout)
        if scr is None:
            print(f"{d}: decode จอไม่ได้")
            continue

        path = os.path.join(OUT, f"{d.replace(':', '_')}.png")
        cv2.imwrite(path, scr)
        print(f"=== {d}   จอ {scr.shape[1]}x{scr.shape[0]}   -> {path}")

        for n, t in tmpls.items():
            score, pos = best_at(scr, t)
            if score is None:
                print(f"  {n:<16} รูปใหญ่กว่าจอ")
                continue
            ok = "ผ่าน" if score >= THRESHOLD else "ไม่ผ่าน"
            print(f"  {n:<16} {t.shape[1]}x{t.shape[0]}  ขนาดปกติ={score:.3f} [{ok}] ที่ {pos}")

            if score >= THRESHOLD:
                continue

            # ไม่ผ่าน -> ลองย่อ/ขยายดูว่าขนาดไหนถึงเจอ
            best = (score, 1.0, pos)
            for pct in range(50, 165, 5):
                s = pct / 100.0
                rt = cv2.resize(t, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
                sc, p2 = best_at(scr, rt)
                if sc is not None and sc > best[0]:
                    best = (sc, s, p2)
            if best[1] == 1.0:
                print(f"      ย่อ/ขยายแล้วก็ไม่ดีขึ้น (ดีสุด {best[0]:.3f})")
                print(f"      -> รูปในเกมน่าจะเปลี่ยนไป ต้องแคปใหม่")
            else:
                print(f"      ดีสุดที่ขนาด {best[1]*100:.0f}%  ได้ {best[0]:.3f} ที่ {best[2]}")
                if best[0] >= THRESHOLD:
                    print(f"      -> รูปถูกตัดมาจากจอคนละความละเอียด")
                    print(f"         แคปใหม่จากเครื่องนี้ หรือย่อรูปเดิมเหลือ {best[1]*100:.0f}%")
                else:
                    print(f"      -> ยังไม่ถึงเกณฑ์อยู่ดี ต้องแคปใหม่")
        print()

    print("เปิดภาพใน _check/ เทียบกับ img/ ที่ใช้อยู่ได้เลย")


if __name__ == "__main__":
    main()
