"""windscribe_cli_rotator.py - headless Windscribe rotator

แทน windscribe_gui_rotator.py ที่ใช้ pyautogui คลิกหน้าต่าง
ตัวนี้เรียก windscribe-cli.exe ตรง ๆ ไม่ต้อง focus window, ไม่สะดุด FailSafe,
ไม่ต้องให้หน้าต่าง Windscribe โผล่หน้าจอ ทำงานเงียบ ๆ ใน background

วิธีใช้:
  1. ติดตั้ง Windscribe desktop + ล็อกอินในแอปครั้งแรก (บอทต้องการแค่ CLI)
  2. เปิด configmain.json ตั้ง "use_host_vpn": 1
  3. รัน `python windscribe_cli_rotator.py` ค้างไว้ตลอดบอททำงาน
  4. ตอนบอทเจอ fixnet1 → บอทเขียน .host_wg_trigger → script สั่งสลับ IP

config keys (configmain.json):
  fixnet_rotate_mode   "ip" = ip rotate (เร็ว, ประเทศเดิม IP ใหม่)       ← default
                       "country" = สุ่มประเทศจาก fixnet_rotate_countries
                       "best" = reconnect best (Windscribe เลือกให้)
  fixnet_rotate_countries  ["Thailand","Singapore","Japan","Korea"]  (ใช้เมื่อ mode=country)
  fixnet_cooloff_sec   ขั้นต่ำกี่วิระหว่างสลับ (default 30)
"""
import json
import os
import random
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRIGGER_FILE = os.path.join(SCRIPT_DIR, ".host_wg_trigger")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "configmain.json")

WINDSCRIBE_CLI_CANDIDATES = [
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                 "Windscribe", "windscribe-cli.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 "Windscribe", "windscribe-cli.exe"),
]

DEFAULT_COUNTRIES = ["Thailand", "Singapore", "Japan", "Korea", "Hong Kong", "Taiwan"]


def _cli_path():
    for p in WINDSCRIBE_CLI_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def _read_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _run_cli(cli, args, timeout=90):
    try:
        r = subprocess.run([cli, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode == 0, (r.stdout or "").strip(), (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return False, "", f"timeout {timeout}s"
    except Exception as e:
        return False, "", str(e)


def _status(cli):
    ok, out, _ = _run_cli(cli, ["status"], timeout=20)
    info = {}
    for line in out.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            info[k.strip().lower()] = v.strip()
    return info


def _rotate(cli, cfg):
    mode = str(cfg.get("fixnet_rotate_mode", "ip") or "ip").lower().strip()
    if mode == "country":
        countries = cfg.get("fixnet_rotate_countries") or DEFAULT_COUNTRIES
        choice = random.choice(countries)
        print(f"[WS-CLI] connect {choice}")
        ok, out, err = _run_cli(cli, ["connect", choice], timeout=90)
    elif mode == "best":
        print("[WS-CLI] connect best")
        ok, out, err = _run_cli(cli, ["connect", "best"], timeout=90)
    else:
        print("[WS-CLI] ip rotate")
        ok, out, err = _run_cli(cli, ["ip", "rotate"], timeout=60)
    if not ok:
        print(f"[WS-CLI] FAIL: {err or out}")
        return False
    time.sleep(3)  # รอ tunnel up
    st = _status(cli)
    ip = st.get("vpn ip") or st.get("public ip") or "?"
    state = st.get("connect state", "?")
    print(f"[WS-CLI] ok - {state} - IP {ip}")
    return True


def main():
    cli = _cli_path()
    if not cli:
        print("[WS-CLI] ไม่เจอ windscribe-cli.exe - ติดตั้ง Windscribe desktop ก่อน")
        return 2

    print("=" * 60)
    print("[WS-CLI] Windscribe CLI Rotator - headless")
    print(f"[WS-CLI] CLI: {cli}")
    print(f"[WS-CLI] trigger file: {TRIGGER_FILE}")
    cfg = _read_config()
    mode = str(cfg.get("fixnet_rotate_mode", "ip") or "ip").lower()
    cool = int(cfg.get("fixnet_cooloff_sec", 30) or 30)
    print(f"[WS-CLI] mode={mode}  cool-off={cool}s")
    print("=" * 60)

    st = _status(cli)
    if "logged in" not in st.get("login state", "").lower():
        print("[WS-CLI] ยังไม่ได้ล็อกอิน Windscribe - เปิดแอปแล้วล็อกอินก่อน (จะคอยต่อไป)")

    # ลบ trigger ที่ค้าง
    if os.path.exists(TRIGGER_FILE):
        try: os.remove(TRIGGER_FILE)
        except Exception: pass

    last_rotate = 0.0
    while True:
        try:
            cfg = _read_config()
            cool = int(cfg.get("fixnet_cooloff_sec", 30) or 30)
            if os.path.exists(TRIGGER_FILE):
                gap = time.time() - last_rotate
                if gap < cool:
                    print(f"[WS-CLI] trigger มา แต่เพิ่งสลับไป {gap:.0f}s (<{cool}s) - ข้าม")
                    try: os.remove(TRIGGER_FILE)
                    except Exception: pass
                    time.sleep(2)
                    continue
                try:
                    with open(TRIGGER_FILE, "r", encoding="utf-8", errors="replace") as f:
                        reason = (f.read() or "").strip()[:200]
                except Exception:
                    reason = ""
                try: os.remove(TRIGGER_FILE)
                except Exception: pass
                print(f"[WS-CLI] ★ trigger: {reason or '(ไม่ระบุ)'}")
                if _rotate(cli, cfg):
                    last_rotate = time.time()
        except KeyboardInterrupt:
            print("[WS-CLI] ปิด (Ctrl+C)")
            return 0
        except Exception as e:
            print(f"[WS-CLI] loop error: {e}")
        time.sleep(2)


if __name__ == "__main__":
    sys.exit(main() or 0)
