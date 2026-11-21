"""windscribe_gui_rotator.py - automate Windscribe desktop app GUI
to rotate country when bot hits fixnet1.

Why this instead of host_wg_rotator.py:
  - Windscribe app generates fresh session keys every connect
    (so handshake always works) while rotator's .conf keypair can
    be revoked and die permanently.
  - User already runs Windscribe app and confirmed it connects fine.
  - We just need to tell it to pick a different country when the bot
    says game is rate-limited (fixnet1).

What this script does:
  1. Poll .host_wg_trigger (same file login.py writes on fixnet1 / login-failed)
  2. On trigger:
       - Bring Windscribe window to front
       - Click on a RANDOM country in the ALL LOCATIONS list
       - Wait for connection to establish (icon turns ON)
  3. Delete trigger, go back to polling

Requires:
  pip install pyautogui pygetwindow pillow

Note:
  - Windscribe window layout is based on the user's screenshot.
  - If Windscribe UI changes -> re-measure coordinates below.
  - Script needs Windscribe window to be VISIBLE (not minimized to tray only).
"""
import glob
import os
import random
import subprocess
import sys
import time

# force UTF-8 output so Thai doesn't print as ???? in Windows cmd
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
try:
    import ctypes
    ctypes.windll.kernel32.SetConsoleOutputCP(65001)   # force code page 65001 (UTF-8)
except Exception:
    pass

try:
    import pyautogui
    import pygetwindow as gw
except ImportError:
    print("[WS-GUI] missing dependencies - run: pip install pyautogui pygetwindow pillow")
    sys.exit(2)

pyautogui.FAILSAFE = True   # move mouse to top-left to abort if something goes wrong

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRIGGER_FILE = os.path.join(SCRIPT_DIR, ".host_wg_trigger")
STATE_FILE = os.path.join(SCRIPT_DIR, "windscribe_gui_state.json")

# default scroll + click offsets (approximate, measured from user's screenshot - 332x560 window)
# the ALL LOCATIONS list starts below "FIREWALL" bar
# each country tile is about 40px tall
TILE_HEIGHT = 40


def _find_windscribe_window():
    """หา Windscribe window - คืน Window object หรือ None"""
    for title in ("Windscribe", "Windscribe PRO", "Windscribe Free"):
        wins = gw.getWindowsWithTitle(title)
        if wins:
            # เอาตัวที่ visible จริง ไม่ใช่ tray
            for w in wins:
                try:
                    if w.visible and w.width > 100 and w.height > 300:
                        return w
                except Exception:
                    pass
            return wins[0]
    return None


def _ensure_window_visible():
    """เปิด window Windscribe ถ้า minimize อยู่ - best effort"""
    w = _find_windscribe_window()
    if w is None:
        # ลองเปิดจาก system tray ด้วย hotkey หรือ start app
        print("[WS-GUI] ไม่เจอ Windscribe window - ลองเปิด Windscribe app จาก Start")
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "Windscribe"], shell=False)
            time.sleep(3)
            w = _find_windscribe_window()
        except Exception as e:
            print(f"[WS-GUI] เปิด Windscribe ไม่สำเร็จ: {e}")
            return None
    if w is None:
        return None
    try:
        if w.isMinimized:
            w.restore()
        w.activate()
        time.sleep(0.5)
    except Exception as e:
        print(f"[WS-GUI] focus window พัง: {e}")
    return w


def _click_random_country(w):
    """สุ่มคลิก country tile ใน ALL LOCATIONS list
    - sidebar: 'ALL LOCATIONS 201' เป็น header
    - ใต้ header: country tiles แต่ละอัน ~40px สูง
    - สุ่ม scroll จำนวน random แล้วคลิกใต้ header"""
    if w is None:
        return False
    try:
        # หา coords ของ window
        x, y, W, H = w.left, w.top, w.width, w.height
        # center of window horizontally, ใต้ FIREWALL bar (ประมาณ 40% จากบน)
        center_x = x + W // 2
        list_top_y = y + int(H * 0.38)     # ใต้ "ALL LOCATIONS 201" header
        list_bot_y = y + int(H * 0.92)     # เหนือ bottom edge
        # ขั้นแรก: scroll แบบสุ่ม (0-30 คลิก) เพื่อให้ list ขึ้นลงมั่วๆ
        scroll_amount = random.choice([-15, -10, -5, 0, 5, 10, 15, 20, 30, -30, 40, -20])
        pyautogui.moveTo(center_x, (list_top_y + list_bot_y) // 2, duration=0.2)
        if scroll_amount != 0:
            pyautogui.scroll(scroll_amount * 100)   # scroll หน่วย pixel (คร่าวๆ)
            time.sleep(0.5)
        # คลิกที่ตำแหน่ง random ในช่วง list
        click_y = random.randint(list_top_y + 10, list_bot_y - 10)
        print(f"[WS-GUI] scroll {scroll_amount}, คลิก ({center_x}, {click_y})")
        pyautogui.click(center_x, click_y)
        time.sleep(2)   # รอ Windscribe เริ่ม connect
        return True
    except pyautogui.FailSafeException:
        print("[WS-GUI] FailSafe triggered (เมาส์ชน top-left) - ยกเลิก")
        return False
    except Exception as e:
        print(f"[WS-GUI] คลิก country พัง: {e}")
        return False


def _rotate():
    print(f"[WS-GUI] ★ sleeping 1s แล้วหา Windscribe window...", flush=True)
    time.sleep(1)
    w = _ensure_window_visible()
    if w is None:
        print(f"[WS-GUI] ไม่เจอ Windscribe window - ข้ามรอบนี้")
        return False
    print(f"[WS-GUI] เจอ window: {w.title} ({w.width}x{w.height} ที่ {w.left},{w.top})")
    ok = _click_random_country(w)
    if ok:
        print(f"[WS-GUI] คลิก country แล้ว - รอ Windscribe connect (10s)")
        time.sleep(10)
    return ok


def main():
    import argparse as _ap
    p = _ap.ArgumentParser(description="Windscribe GUI Rotator")
    p.add_argument("--interval", type=float, default=0,
                   help="สลับประเทศอัตโนมัติทุก N นาที (0 = เฉพาะตอนบอท trigger)")
    p.add_argument("--min-gap", type=float, default=30.0,
                   help="cool-off ขั้นต่ำระหว่างสลับ (วินาที)")
    args = p.parse_args()

    print(f"[WS-GUI] =============================================================")
    print(f"[WS-GUI] Windscribe GUI Rotator - คอยดู {TRIGGER_FILE}")
    if args.interval > 0:
        print(f"[WS-GUI] + สลับประเทศเองทุก {args.interval} นาที (--interval)")
    print(f"[WS-GUI] =============================================================")
    print(f"[WS-GUI] วิธีใช้:")
    print(f"[WS-GUI]   1. เปิด Windscribe app ให้ตัว window โผล่หน้าจอ (ไม่ใช่ tray)")
    print(f"[WS-GUI]   2. ปล่อย script นี้ค้างไว้")
    print(f"[WS-GUI]   3. ตอนบอทเจอ fixnet1 -> เขียน .host_wg_trigger -> script หมุน country")
    print(f"[WS-GUI] =============================================================")
    print(f"[WS-GUI] safety: ย้ายเมาส์ไปมุมบนซ้ายของจอเพื่อหยุด script ทันที (FailSafe)")
    print(f"[WS-GUI]")

    # ลบ trigger file เก่า (ของ host_wg_rotator.py จะไม่ชน)
    try:
        if os.path.exists(TRIGGER_FILE):
            os.remove(TRIGGER_FILE)
    except Exception:
        pass

    # เช็คว่าหา Windscribe window ได้ไหมตอนเริ่ม
    w = _find_windscribe_window()
    if w:
        print(f"[WS-GUI] เจอ Windscribe window: '{w.title}' ({w.width}x{w.height})")
    else:
        print(f"[WS-GUI] ยังไม่เจอ Windscribe window - เปิด app ให้ window โผล่ด้วย")

    last_rotate = 0.0
    min_gap = max(10.0, args.min_gap)
    interval_sec = max(0.0, args.interval * 60.0)
    while True:
        try:
            now = time.time()
            # timer-based rotate (ไม่รอ trigger) ถ้าตั้ง --interval
            if interval_sec > 0 and (now - last_rotate) >= interval_sec:
                print(f"[WS-GUI] ★ timer: ครบ {args.interval} นาที - หมุน country")
                if _rotate():
                    last_rotate = time.time()
            if os.path.exists(TRIGGER_FILE):
                gap = time.time() - last_rotate
                if gap < min_gap:
                    print(f"[WS-GUI] trigger file พบ แต่เพิ่งหมุนไป {gap:.0f}s - ข้าม")
                    try: os.remove(TRIGGER_FILE)
                    except Exception: pass
                    time.sleep(3)
                    continue
                try:
                    with open(TRIGGER_FILE, "r", encoding="utf-8", errors="replace") as f:
                        reason = (f.read() or "").strip()[:200]
                except Exception:
                    reason = ""
                try: os.remove(TRIGGER_FILE)
                except Exception: pass
                print(f"[WS-GUI] ★ trigger: {reason or '(ไม่ระบุ)'} - หมุน country")
                if _rotate():
                    last_rotate = time.time()
        except KeyboardInterrupt:
            print(f"[WS-GUI] ปิด rotator (Ctrl+C)")
            return
        except Exception as e:
            print(f"[WS-GUI] loop error: {e}")
        time.sleep(3)


if __name__ == "__main__":
    main()
