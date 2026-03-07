"""
recapture_popup.py - แคปรูป popup ใหม่จากจอ emulator
วิธีใช้: python recapture_popup.py
"""
import subprocess
import numpy as np
import cv2
import os
import sys
import shutil
import time

def find_adb():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "adb", "adb.exe"),
        os.path.join(os.getcwd(), "adb", "adb.exe"),
    ]
    for loc in candidates:
        if os.path.exists(loc):
            return loc
    adb_in_path = shutil.which("adb")
    if adb_in_path:
        return os.path.abspath(adb_in_path)
    try:
        subprocess.run(["adb", "--version"], capture_output=True, timeout=5, check=True)
        return "adb"
    except:
        pass
    mumu_paths = [
        "F:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe",
        "C:\\Program Files\\Netease\\MuMuPlayerGlobal-12.0\\shell\\adb.exe",
        "C:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe",
    ]
    for p in mumu_paths:
        if os.path.exists(p):
            return p
    return None

def get_devices(adb_cmd):
    kwargs = {}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run([adb_cmd, "devices"], capture_output=True, text=True, timeout=5, **kwargs)
    devices = []
    for line in result.stdout.strip().split("\n")[1:]:
        if "\tdevice" in line:
            devices.append(line.split("\t")[0])
    return devices

def capture_color(adb_cmd, device_id):
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
            color = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            gray = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
            return color, gray
    except Exception as e:
        print(f"  Capture error: {e}")
    return None, None

def main():
    print("=" * 55)
    print("  Recapture Popup Templates")
    print("=" * 55)
    
    adb_cmd = find_adb()
    if not adb_cmd:
        print("ERROR: ADB not found!")
        input("Press Enter...")
        return
    print(f"ADB: {adb_cmd}")
    
    devices = get_devices(adb_cmd)
    if not devices:
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
        print("ERROR: No devices!")
        input("Press Enter...")
        return
    
    print(f"\nDevices found: {len(devices)}")
    for i, d in enumerate(devices):
        print(f"  [{i}] {d}")
    
    # แคปจอจากทุก device ที่มีและเซฟ
    print(f"\nCapturing from first device: {devices[0]}")
    device = devices[0]
    
    color, gray = capture_color(adb_cmd, device)
    if color is None:
        print("ERROR: Cannot capture screen!")
        input("Press Enter...")
        return
    
    h, w = color.shape[:2]
    print(f"Screen size: {w}x{h}")
    
    # เซฟ screenshot เต็มจอ
    cv2.imwrite("full_screenshot.png", color)
    print(f"\nSaved full_screenshot.png ({w}x{h})")
    
    # แสดงขนาด template เดิม
    print("\n--- Current Templates ---")
    templates = {
        "img/fixnet1.png": "RETRY button (network error popup)",
        "img/fixnetv2.png": "Network error v2 popup",
        "img/fixnetv2ok.png": "OK button after fixnetv2", 
        "img/fixplay.png": "Play/reconnect popup",
        "img/fixaccep.png": "Accept popup",
    }
    
    for path, desc in templates.items():
        if os.path.exists(path):
            t = cv2.imread(path)
            if t is not None:
                th, tw = t.shape[:2]
                # ทดสอบ match กับจอปัจจุบัน
                t_gray = cv2.cvtColor(t, cv2.COLOR_BGR2GRAY)
                if t_gray.shape[0] <= gray.shape[0] and t_gray.shape[1] <= gray.shape[1]:
                    result = cv2.matchTemplate(gray, t_gray, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(result)
                    status = "MATCH!" if max_val >= 0.90 else ("close" if max_val >= 0.70 else "NO MATCH")
                    print(f"  {path}: {tw}x{th}px  conf={max_val:.3f} [{status}]  ({desc})")
                    
                    # ถ้า match ได้ ตัด crop ออกมาให้เทียบ
                    if max_val >= 0.30:
                        crop = color[max_loc[1]:max_loc[1]+th, max_loc[0]:max_loc[0]+tw]
                        crop_name = f"compare_{os.path.basename(path)}"
                        cv2.imwrite(crop_name, crop)
                else:
                    print(f"  {path}: {tw}x{th}px  TEMPLATE BIGGER THAN SCREEN!")
        else:
            print(f"  {path}: NOT FOUND  ({desc})")
    
    # ค้นหา popup อัตโนมัติโดยหาปุ่ม RETRY สีส้ม/เหลือง
    print("\n--- Auto-detecting RETRY button ---")
    hsv = cv2.cvtColor(color, cv2.COLOR_BGR2HSV)
    
    # หาสีส้ม/เหลืองของปุ่ม RETRY (ดูจาก screenshot)
    # สีส้ม: H=10-25, S=150-255, V=150-255
    lower_orange = np.array([8, 120, 150])
    upper_orange = np.array([30, 255, 255])
    mask = cv2.inRange(hsv, lower_orange, upper_orange)
    
    # หา contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # กรอง contours ที่มีขนาดพอเป็นปุ่ม
    buttons = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        area = bw * bh
        if 500 < area < 50000 and bw > 30 and bh > 15:  # ขนาดพอเป็นปุ่ม
            buttons.append((x, y, bw, bh, area))
    
    if buttons:
        # เรียงตามขนาด
        buttons.sort(key=lambda b: b[4], reverse=True)
        print(f"  Found {len(buttons)} potential buttons!")
        
        # เอาปุ่มใหญ่สุด + เพิ่ม padding สำหรับ popup ทั้งก้อน
        bx, by, bw, bh, _ = buttons[0]
        print(f"  Largest button at: ({bx}, {by}) size: {bw}x{bh}")
        
        # ตัดแค่ปุ่ม RETRY
        pad = 5
        btn_crop = color[max(0,by-pad):by+bh+pad, max(0,bx-pad):bx+bw+pad]
        cv2.imwrite("detected_retry_button.png", btn_crop)
        print(f"  Saved: detected_retry_button.png ({btn_crop.shape[1]}x{btn_crop.shape[0]})")
        
        # ตัด popup ทั้งก้อน (ขยายขึ้นไปอีก)
        popup_pad_top = 80
        popup_pad_side = 30
        popup_pad_bottom = 10
        px1 = max(0, bx - popup_pad_side)
        py1 = max(0, by - popup_pad_top)
        px2 = min(w, bx + bw + popup_pad_side)
        py2 = min(h, by + bh + popup_pad_bottom)
        popup_crop = color[py1:py2, px1:px2]
        cv2.imwrite("detected_popup_full.png", popup_crop)
        print(f"  Saved: detected_popup_full.png ({popup_crop.shape[1]}x{popup_crop.shape[0]})")
        
        print(f"\n  ======================================")
        print(f"  TO FIX: Copy one of these files:")
        print(f"    detected_retry_button.png -> img/fixnet1.png")
        print(f"    detected_popup_full.png   -> img/fixnetv2.png") 
        print(f"  ======================================")
    else:
        print("  No orange/yellow buttons detected.")
        print("  Please manually crop the popup from full_screenshot.png")
    
    print("\nFiles saved in current directory.")
    print("Open full_screenshot.png to see what the bot sees.")
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
