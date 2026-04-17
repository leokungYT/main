"""Click on image to get coordinates - for finding Region values
Supports: MuMu, LDPlayer, Nox, BlueStacks (auto-detect)
"""
import cv2
import subprocess
import os
import sys
import shutil
import time
import numpy as np

# ─────────────────────────────────────────────
#  ADB helper functions
# ─────────────────────────────────────────────

def find_adb():
    """Auto-find ADB executable from multiple locations"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)

    # Check local adb folder (script dir and parent dir)
    for base in [script_dir, parent_dir, os.getcwd()]:
        local = os.path.join(base, "adb", "adb.exe")
        if os.path.exists(local):
            print(f"✅ Found local ADB: {local}")
            return local

    # Check system PATH
    found = shutil.which("adb")
    if found:
        print(f"✅ Found ADB in PATH: {found}")
        return os.path.abspath(found)

    # Check MuMu / LDPlayer specific paths
    known_paths = [
        r"F:\Program Files\Netease\MuMuPlayer\shell\adb.exe",
        r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0\shell\adb.exe",
        r"C:\Program Files\Netease\MuMuPlayer\shell\adb.exe",
        r"D:\Program Files\Netease\MuMuPlayer\shell\adb.exe",
        r"E:\Program Files\Netease\MuMuPlayer\shell\adb.exe",
        # LDPlayer common paths
        r"C:\LDPlayer\LDPlayer9\adb.exe",
        r"D:\LDPlayer\LDPlayer9\adb.exe",
        r"C:\Program Files\LDPlayer\LDPlayer9\adb.exe",
        r"C:\LDPlayer\LDPlayer4.0\adb.exe",
    ]
    for p in known_paths:
        if os.path.exists(p):
            print(f"✅ Found ADB: {p}")
            return p

    return None


def connect_emulator_ports(adb):
    """Auto-connect to common emulator ports (MuMu, LDPlayer, Nox, BlueStacks)"""
    print("🔄 Scanning emulator ports...")
    kw = {}
    if os.name == 'nt':
        kw['creationflags'] = subprocess.CREATE_NO_WINDOW

    # Common ports:
    #   MuMu:      7555
    #   Nox:       62001
    #   LDPlayer:  5555, 5557, 5559, ... (odd ports)
    #   BlueStacks: 5555, 5565, 5575, ...
    ports = [7555, 62001]
    # Add LDPlayer/BlueStacks style ports: 5555, 5557, 5559, ..., 5599
    for i in range(25):
        ports.append(5555 + i * 2)

    for port in ports:
        try:
            subprocess.run(
                [adb, "connect", f"127.0.0.1:{port}"],
                capture_output=True, timeout=1, **kw
            )
        except:
            pass

    time.sleep(0.5)


def get_devices(adb):
    """Get list of connected ADB devices"""
    kw = {}
    if os.name == 'nt':
        kw['creationflags'] = subprocess.CREATE_NO_WINDOW

    r = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=5, **kw)
    devices = []
    for line in r.stdout.strip().split("\n")[1:]:
        if "\tdevice" in line:
            devices.append(line.split("\t")[0])
    return devices


def choose_device(devices):
    """Let user choose a device if more than one is connected"""
    if len(devices) == 1:
        print(f"📱 Using device: {devices[0]}")
        return devices[0]

    print(f"\n📱 Found {len(devices)} devices:")
    for i, dev in enumerate(devices):
        print(f"  [{i}] {dev}")

    while True:
        try:
            choice = input(f"\nSelect device [0-{len(devices)-1}]: ").strip()
            idx = int(choice)
            if 0 <= idx < len(devices):
                return devices[idx]
        except (ValueError, KeyboardInterrupt):
            pass
        print("Invalid choice, try again.")


def capture_screen(adb, device_id, filename):
    """Capture screen from device via ADB"""
    kw = {}
    if os.name == 'nt':
        kw['creationflags'] = subprocess.CREATE_NO_WINDOW

    # Try exec-out (fast, pipe binary directly)
    try:
        result = subprocess.run(
            [adb, "-s", device_id, "exec-out", "screencap", "-p"],
            capture_output=True, timeout=10, **kw
        )
        if result.returncode == 0 and len(result.stdout) > 100:
            img_arr = np.frombuffer(result.stdout, np.uint8)
            img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
            if img is not None:
                cv2.imwrite(filename, img)
                return True
    except:
        pass

    # Fallback: shell screencap + pull
    try:
        subprocess.run(
            [adb, "-s", device_id, "shell", "screencap", "-p", "/sdcard/screen_coord_tmp.png"],
            capture_output=True, timeout=10, **kw
        )
        subprocess.run(
            [adb, "-s", device_id, "pull", "/sdcard/screen_coord_tmp.png", filename],
            capture_output=True, timeout=10, **kw
        )
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            return True
    except:
        pass

    # Last resort: old exec-out redirect (works on some MuMu)
    os.system(f'"{adb}" -s {device_id} exec-out screencap -p > {filename}')
    return os.path.exists(filename) and os.path.getsize(filename) > 0


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  Get Coordinates Tool")
    print("  Supports: MuMu / LDPlayer / Nox / BlueStacks")
    print("=" * 50)

    # 1. Find ADB
    adb = find_adb()
    if not adb:
        print("❌ ADB not found! Place adb.exe in adb/ folder or install it.")
        input("Press Enter to exit...")
        sys.exit(1)

    # 2. Auto-connect emulator ports
    connect_emulator_ports(adb)

    # 3. Get devices
    devices = get_devices(adb)

    if not devices:
        print("❌ No devices found! Make sure your emulator is running.")
        input("Press Enter to exit...")
        sys.exit(1)

    # 4. Choose device
    device_id = choose_device(devices)

    # 5. Capture screen
    filename = "screen_coord.png"
    print(f"\n📸 Capturing screen from {device_id}...")
    if not capture_screen(adb, device_id, filename):
        print("❌ Failed to capture screen!")
        input("Press Enter to exit...")
        sys.exit(1)

    print(f"✅ Screenshot saved: {filename}")

    # 6. Open coordinate picker
    img = cv2.imread(filename)
    if img is None:
        print("❌ Failed to read screenshot!")
        sys.exit(1)

    clicks = []
    window_name = "Click to get coordinates (ESC=exit, R=reset, C=recapture)"

    def mouse_callback(event, x, y, flags, param):
        nonlocal img, clicks
        if event == cv2.EVENT_LBUTTONDOWN:
            clicks.append((x, y))
            print(f"Click #{len(clicks)}: ({x}, {y})")

            # Draw circle
            cv2.circle(img, (x, y), 5, (0, 0, 255), -1)
            cv2.putText(img, f"({x},{y})", (x+10, y-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            if len(clicks) == 2:
                x1, y1 = clicks[0]
                x2, y2 = clicks[1]
                w = x2 - x1
                h = y2 - y1
                print(f"\n===== RESULT =====")
                print(f"Top-Left:     ({x1}, {y1})")
                print(f"Bottom-Right: ({x2}, {y2})")
                print(f"Region({x1}, {y1}, {w}, {h})")
                print(f"==================")

                # Draw rectangle
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)

            cv2.imshow(window_name, img)

    cv2.imshow(window_name, img)
    cv2.setMouseCallback(window_name, mouse_callback)

    print("\nClick TOP-LEFT corner first, then BOTTOM-RIGHT corner")
    print("Press R to reset clicks, C to recapture screen, ESC to exit")

    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            break
        elif key == ord('r') or key == ord('R'):
            # Reset: reload image and clear clicks
            clicks = []
            img = cv2.imread(filename)
            cv2.imshow(window_name, img)
            print("\n🔄 Reset! Click again.")
        elif key == ord('c') or key == ord('C'):
            # Recapture screen
            print(f"\n📸 Recapturing screen from {device_id}...")
            if capture_screen(adb, device_id, filename):
                clicks = []
                img = cv2.imread(filename)
                cv2.imshow(window_name, img)
                print("✅ Recaptured! Click again.")
            else:
                print("❌ Recapture failed!")

    cv2.destroyAllWindows()
    print("\nDone!")


if __name__ == "__main__":
    main()
