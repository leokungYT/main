"""
test_popup.py - ทดสอบว่า fixnet1.png / fixnetv2.png ถูกตรวจจับและกดจริงไหม
วิธีใช้: python test_popup.py
"""
import subprocess
import numpy as np
import cv2
import os
import time
import sys
import shutil

# ===== CONFIG =====
POPUP_IMAGES = [
    "img/fixnet1.png",
    "img/fixnetv2.png",
    "img/fixnetv2ok.png",
    "img/fixplay.png",
    "img/fixaccep.png",
]
SIMILARITY = 0.95
CHECK_INTERVAL = 2  # วินาที
MAX_ROUNDS = 30     # จำนวนรอบสูงสุด (30 รอบ x 2 วิ = 60 วินาที)

def find_adb():
    """หา adb แบบเดียวกับบอท - รองรับทุกเครื่อง"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. หาในโฟลเดอร์ adb/ ข้างๆ สคริปต์
    candidates = [
        os.path.join(script_dir, "adb", "adb.exe"),
        os.path.join(os.getcwd(), "adb", "adb.exe"),
    ]
    for loc in candidates:
        if os.path.exists(loc):
            print(f"  [ADB] Found: {loc}")
            return loc
    
    # 2. หาใน system PATH
    adb_in_path = shutil.which("adb")
    if adb_in_path:
        print(f"  [ADB] Found in PATH: {adb_in_path}")
        return os.path.abspath(adb_in_path)
    
    # 3. ลองรัน adb ตรงๆ
    try:
        subprocess.run(["adb", "--version"], capture_output=True, timeout=5, check=True)
        print(f"  [ADB] Using system 'adb' command")
        return "adb"
    except:
        pass
    
    # 4. MuMu paths
    mumu_paths = [
        "F:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe",
        "C:\\Program Files\\Netease\\MuMuPlayerGlobal-12.0\\shell\\adb.exe",
        "C:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe",
        "F:\\MuMuPlayerGlobal-12.0\\shell\\adb.exe",
        "D:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe",
    ]
    for p in mumu_paths:
        if os.path.exists(p):
            print(f"  [ADB] Found MuMu ADB: {p}")
            return p
    
    return None

def get_devices(adb_cmd):
    """หา device ที่เชื่อมต่ออยู่"""
    kwargs = {}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run([adb_cmd, "devices"], capture_output=True, text=True, timeout=5, **kwargs)
    devices = []
    for line in result.stdout.strip().split("\n")[1:]:
        if "\tdevice" in line:
            devices.append(line.split("\t")[0])
    return devices

def capture_screen(adb_cmd, device_id):
    """แคปจอ"""
    try:
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            [adb_cmd, "-s", device_id, "exec-out", "screencap", "-p"],
            capture_output=True, timeout=10, **kwargs
        )
        if result.returncode == 0 and len(result.stdout) > 100:
            img_array = np.frombuffer(result.stdout, np.uint8)
            screen = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
            return screen
    except Exception as e:
        print(f"  [ERROR] Capture failed: {e}")
    return None

def find_image(screen, template_path, similarity=0.95):
    """หารูปในจอ คืนตำแหน่ง (x, y) หรือ None + confidence จริงเสมอ"""
    if not os.path.exists(template_path):
        return None, -1.0
    tmpl = cv2.imread(template_path, 0)
    if tmpl is None or screen is None:
        return None, -1.0
    try:
        # เช็คว่า template ไม่ใหญ่กว่า screen
        if tmpl.shape[0] > screen.shape[0] or tmpl.shape[1] > screen.shape[1]:
            return None, -2.0  # template ใหญ่กว่าจอ!
        result = cv2.matchTemplate(screen, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= similarity:
            h, w = tmpl.shape
            cx = max_loc[0] + w // 2
            cy = max_loc[1] + h // 2
            return (cx, cy), max_val
        return None, max_val  # ไม่เจอ แต่คืน confidence จริง
    except Exception as e:
        return None, -3.0

def tap(adb_cmd, device_id, x, y):
    """กดจอที่ตำแหน่ง (x, y)"""
    try:
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        subprocess.run(
            [adb_cmd, "-s", device_id, "shell", "input", "tap", str(x), str(y)],
            capture_output=True, timeout=5, **kwargs
        )
        return True
    except:
        return False

def main():
    print("=" * 55)
    print("  Popup Detection Test (fixnet1 / fixnetv2 / etc)")
    print("=" * 55)
    
    # เช็คว่ามีไฟล์รูป popup ไหม + ขนาด template
    print("\n[1] Checking popup image files...")
    for img in POPUP_IMAGES:
        if os.path.exists(img):
            tmpl = cv2.imread(img)
            if tmpl is not None:
                print(f"  {img}: Found ({tmpl.shape[1]}x{tmpl.shape[0]} px)")
            else:
                print(f"  {img}: Found but CANNOT READ!")
        else:
            print(f"  {img}: NOT FOUND")
    
    # หา ADB
    print("\n[2] Finding ADB...")
    adb_cmd = find_adb()
    if not adb_cmd:
        print("  ERROR: ADB not found!")
        print("  Put adb.exe in the 'adb' folder next to this script")
        input("Press Enter to exit...")
        return
    
    # หา device
    print("\n[3] Finding connected devices...")
    devices = get_devices(adb_cmd)
    if not devices:
        # ลอง connect MuMu ports
        print("  No devices found. Trying to connect MuMu ports...")
        for port in [7555, 5555, 5557, 5559, 5561, 5563, 5565, 5567, 5569, 5571, 5573, 5575, 5577, 5579, 5581, 5583, 5585, 5587]:
            try:
                kwargs = {}
                if os.name == 'nt':
                    kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                subprocess.run([adb_cmd, "connect", f"127.0.0.1:{port}"], capture_output=True, timeout=3, **kwargs)
            except:
                pass
        time.sleep(1)
        devices = get_devices(adb_cmd)
    
    if not devices:
        print("  ERROR: No devices found!")
        input("Press Enter to exit...")
        return
    
    for d in devices:
        print(f"  Device: {d}")
    
    # เริ่มเช็คแบบ loop ทุก device
    print(f"\n[4] Starting popup check on ALL {len(devices)} devices")
    print(f"    Checking every {CHECK_INTERVAL}s for {MAX_ROUNDS} rounds...")
    print(f"    Press Ctrl+C to stop\n")
    print("-" * 55)
    
    total_found = 0
    total_clicked = 0
    
    try:
        for round_num in range(1, MAX_ROUNDS + 1):
            timestamp = time.strftime("%H:%M:%S")
            print(f"\n[Round {round_num}/{MAX_ROUNDS}] {timestamp}")
            
            # วนเช็คทุก device
            for device in devices:
                screen = capture_screen(adb_cmd, device)
                if screen is None:
                    print(f"  [{device}] Cannot capture")
                    continue
                
                for img_path in POPUP_IMAGES:
                    if not os.path.exists(img_path):
                        continue
                    
                    pos, confidence = find_image(screen, img_path, SIMILARITY)
                    img_name = os.path.basename(img_path)
                    
                    if pos:
                        total_found += 1
                        print(f"  [{device}] FOUND: {img_name} conf={confidence:.3f} -> CLICKING ({pos[0]},{pos[1]})")
                        tap(adb_cmd, device, pos[0], pos[1])
                        total_clicked += 1
                        time.sleep(0.5)
            
            time.sleep(CHECK_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    
    # สรุป
    print("\n" + "=" * 55)
    print(f"  SUMMARY")
    print(f"  Total popups found:   {total_found}")
    print(f"  Total clicks sent:    {total_clicked}")
    print("=" * 55)
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
