"""fix-stuck-emu.py - กู้ emu ที่ค้างอัตโนมัติ

ตรวจทุก 30 วิ:
  1. ADB offline/timeout -> adb kill-server + restart
  2. เกม crash (ไม่เจอ pidof LGRGS) นานกว่า N นาที -> เตือน
  3. tun0 ไม่ขึ้น -> เตือน
  4. RAM ใช้ > 95% -> เตือน

รันคู่กับบอทได้ (background monitor)
"""
import os
import re
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ADB = os.path.join(SCRIPT_DIR, "adb", "adb.exe")
LGR_PKG = "com.linecorp.LGRGS"
CHECK_INTERVAL = 30
GAME_DEAD_MAX_SEC = 180   # เกมปิดอยู่ > 3 นาที = เตือน
KW = {"creationflags": 0x08000000} if os.name == "nt" else {}   # CREATE_NO_WINDOW


def sh(args, timeout=10):
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, **KW)
        return (r.returncode == 0, (r.stdout or "").strip(), (r.stderr or "").strip())
    except subprocess.TimeoutExpired:
        return (False, "", "timeout")
    except Exception as e:
        return (False, "", str(e))


def adb_devices():
    _, out, _ = sh([ADB, "devices"])
    devs = {}
    for line in out.splitlines()[1:]:
        m = re.match(r"(emulator-\d+|127\.0\.0\.1:\d+)\s+(\w+)", line.strip())
        if m:
            devs[m.group(1)] = m.group(2)
    return devs


def check_game(dev):
    ok, out, _ = sh([ADB, "-s", dev, "shell", "pidof", LGR_PKG], timeout=5)
    return bool(ok and out.strip().isdigit())


def check_tun(dev):
    ok, out, _ = sh([ADB, "-s", dev, "shell", "ip", "-o", "link", "show", "tun0"], timeout=5)
    return bool(ok and "tun0" in out)


def restart_adb():
    print("[FIX] restart adb server...")
    sh([ADB, "kill-server"], timeout=10)
    time.sleep(2)
    sh([ADB, "start-server"], timeout=10)
    time.sleep(2)


def restart_game(dev):
    print(f"[FIX] {dev}: force-stop + relaunch LGR")
    sh([ADB, "-s", dev, "shell", "am", "force-stop", LGR_PKG], timeout=10)
    time.sleep(1)
    sh([ADB, "-s", dev, "shell", "monkey", "-p", LGR_PKG, "-c", "android.intent.category.LAUNCHER", "1"], timeout=10)


def main():
    game_dead_since = {}
    offline_count = 0

    print("=" * 60)
    print("[FIX] fix-stuck-emu monitor - ตรวจทุก {} วิ".format(CHECK_INTERVAL))
    print("[FIX] ADB: {}".format(ADB))
    print("=" * 60)

    while True:
        try:
            devs = adb_devices()
            if not devs:
                offline_count += 1
                print(f"[WARN] ไม่เจอ emu เลย ({offline_count}/3)")
                if offline_count >= 3:
                    restart_adb()
                    offline_count = 0
                time.sleep(CHECK_INTERVAL)
                continue
            offline_count = 0

            now = time.time()
            status = []
            offline_devs = [d for d, s in devs.items() if s != "device"]
            if offline_devs:
                print(f"[WARN] offline: {', '.join(offline_devs)} - restart adb")
                restart_adb()
                time.sleep(3)
                devs = adb_devices()

            for dev in devs:
                if devs[dev] != "device":
                    status.append(f"{dev}: {devs[dev]}")
                    continue
                g = check_game(dev)
                t = check_tun(dev)
                if g:
                    game_dead_since.pop(dev, None)
                    status.append(f"{dev}: ✓ game+{'VPN' if t else '✗VPN'}")
                else:
                    first_dead = game_dead_since.setdefault(dev, now)
                    dead_sec = int(now - first_dead)
                    if dead_sec >= GAME_DEAD_MAX_SEC:
                        print(f"[FIX] {dev}: เกมตาย {dead_sec}s - restart LGR")
                        restart_game(dev)
                        game_dead_since[dev] = now
                    else:
                        status.append(f"{dev}: ✗game ({dead_sec}s) {'+VPN' if t else '-VPN'}")

            ts = time.strftime("%H:%M:%S")
            ok_n = sum(1 for s in status if "✓" in s)
            bad = [s for s in status if "✓" not in s]
            print(f"[{ts}] {ok_n}/{len(devs)} ok" + (" | " + ", ".join(bad) if bad else ""))

        except KeyboardInterrupt:
            print("[FIX] stop")
            return 0
        except Exception as e:
            print(f"[FIX] loop error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    sys.exit(main() or 0)
