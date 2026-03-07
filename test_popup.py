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

# ===== CONFIG =====
ADB_CMD = "adb"
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

def get_devices():
    """หา device ที่เชื่อมต่ออยู่"""
    result = subprocess.run([ADB_CMD, "devices"], capture_output=True, text=True, timeout=5)
    devices = []
    for line in result.stdout.strip().split("\n")[1:]:
        if "\tdevice" in line:
            devices.append(line.split("\t")[0])
    return devices

def capture_screen(device_id):
    """แคปจอ"""
    try:
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            [ADB_CMD, "-s", device_id, "exec-out", "screencap", "-p"],
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
    """หารูปในจอ คืนตำแหน่ง (x, y) หรือ None"""
    if not os.path.exists(template_path):
        return None, 0.0
    tmpl = cv2.imread(template_path, 0)
    if tmpl is None or screen is None:
        return None, 0.0
    try:
        result = cv2.matchTemplate(screen, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= similarity:
            h, w = tmpl.shape
            cx = max_loc[0] + w // 2
            cy = max_loc[1] + h // 2
            return (cx, cy), max_val
    except:
        pass
    return None, 0.0

def tap(device_id, x, y):
    """กดจอที่ตำแหน่ง (x, y)"""
    try:
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        subprocess.run(
            [ADB_CMD, "-s", device_id, "shell", "input", "tap", str(x), str(y)],
            capture_output=True, timeout=5, **kwargs
        )
        return True
    except:
        return False

def main():
    print("=" * 55)
    print("  🔍 Popup Detection Test (fixnet1 / fixnetv2 / etc)")
    print("=" * 55)
    
    # เช็คว่ามีไฟล์รูป popup ไหม
    print("\n[1] Checking popup image files...")
    for img in POPUP_IMAGES:
        exists = os.path.exists(img)
        status = "✅ Found" if exists else "❌ NOT FOUND"
        print(f"  {img}: {status}")
    
    # หา device
    print("\n[2] Finding connected devices...")
    devices = get_devices()
    if not devices:
        print("  ❌ No devices found! Please connect emulator first.")
        return
    
    for d in devices:
        print(f"  ✅ {d}")
    
    # เลือก device ตัวแรก (หรือให้เลือก)
    if len(devices) == 1:
        device = devices[0]
    else:
        print(f"\n  Found {len(devices)} devices. Testing first: {devices[0]}")
        device = devices[0]
    
    # เริ่มเช็คแบบ loop
    print(f"\n[3] Starting popup check loop on [{device}]")
    print(f"    Checking every {CHECK_INTERVAL}s for {MAX_ROUNDS} rounds...")
    print(f"    Press Ctrl+C to stop\n")
    print("-" * 55)
    
    total_found = 0
    total_clicked = 0
    
    try:
        for round_num in range(1, MAX_ROUNDS + 1):
            timestamp = time.strftime("%H:%M:%S")
            print(f"\n[Round {round_num}/{MAX_ROUNDS}] {timestamp}")
            
            # แคปจอ
            screen = capture_screen(device)
            if screen is None:
                print("  ⚠️ Could not capture screen, retrying...")
                time.sleep(CHECK_INTERVAL)
                continue
            
            print(f"  Screen captured: {screen.shape[1]}x{screen.shape[0]}")
            
            found_any = False
            for img_path in POPUP_IMAGES:
                if not os.path.exists(img_path):
                    continue
                
                pos, confidence = find_image(screen, img_path, SIMILARITY)
                img_name = os.path.basename(img_path)
                
                if pos:
                    found_any = True
                    total_found += 1
                    print(f"  🔴 FOUND: {img_name} at ({pos[0]}, {pos[1]}) confidence={confidence:.3f}")
                    
                    # กดเลย!
                    print(f"  👆 CLICKING {img_name} at ({pos[0]}, {pos[1]})...")
                    success = tap(device, pos[0], pos[1])
                    if success:
                        total_clicked += 1
                        print(f"  ✅ CLICKED! (total clicks: {total_clicked})")
                    else:
                        print(f"  ❌ Click failed!")
                    
                    # รอ 1 วิ แล้วแคปจอใหม่เพื่อดูว่าหายไปไหม
                    time.sleep(1)
                    screen2 = capture_screen(device)
                    if screen2 is not None:
                        pos2, conf2 = find_image(screen2, img_path, SIMILARITY)
                        if pos2:
                            print(f"  ⚠️ {img_name} STILL VISIBLE after click! (conf={conf2:.3f})")
                        else:
                            print(f"  ✅ {img_name} disappeared after click!")
                else:
                    # แสดง confidence ถ้าใกล้ threshold
                    if confidence > 0.7:
                        print(f"  🟡 {img_name}: NOT matched but close (confidence={confidence:.3f}, need={SIMILARITY})")
            
            if not found_any:
                print(f"  🟢 No popups detected - screen is clean")
            
            time.sleep(CHECK_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopped by user")
    
    # สรุป
    print("\n" + "=" * 55)
    print(f"  📊 SUMMARY")
    print(f"  Total popups found:   {total_found}")
    print(f"  Total clicks sent:    {total_clicked}")
    print("=" * 55)

if __name__ == "__main__":
    main()
