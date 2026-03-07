"""
save_screen.py - แคปจอ emulator เซฟเป็นไฟล์เพื่อตัดรูป popup มาใช้
วิธีใช้: python save_screen.py
แล้วเปิด screenshot_color.png ตัด popup เซฟทับ img/fixnet1.png
"""
import subprocess, numpy as np, cv2, os, sys, shutil, time

def find_adb():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for loc in [os.path.join(script_dir, "adb", "adb.exe"), os.path.join(os.getcwd(), "adb", "adb.exe")]:
        if os.path.exists(loc): return loc
    a = shutil.which("adb")
    if a: return os.path.abspath(a)
    try:
        subprocess.run(["adb","--version"], capture_output=True, timeout=5, check=True)
        return "adb"
    except: pass
    for p in ["F:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe","C:\\Program Files\\Netease\\MuMuPlayerGlobal-12.0\\shell\\adb.exe","C:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe"]:
        if os.path.exists(p): return p
    return None

def main():
    print("=" * 50)
    print("  Save Emulator Screenshot")
    print("=" * 50)
    
    adb = find_adb()
    if not adb:
        print("ADB not found!")
        input("Press Enter...")
        return
    
    kw = {}
    if os.name == 'nt':
        kw['creationflags'] = subprocess.CREATE_NO_WINDOW
    
    # หา devices
    r = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=5, **kw)
    devices = [l.split("\t")[0] for l in r.stdout.strip().split("\n")[1:] if "\tdevice" in l]
    
    if not devices:
        for port in [7555,5555,5557,5559,5561,5563,5565,5567,5569,5571,5573,5575,5577,5579,5581,5583,5585,5587]:
            try: subprocess.run([adb,"connect",f"127.0.0.1:{port}"], capture_output=True, timeout=3, **kw)
            except: pass
        time.sleep(1)
        r = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=5, **kw)
        devices = [l.split("\t")[0] for l in r.stdout.strip().split("\n")[1:] if "\tdevice" in l]
    
    if not devices:
        print("No devices!")
        input("Press Enter...")
        return
    
    print(f"Found {len(devices)} devices")
    
    # แคปจอจากทุก device
    for i, dev in enumerate(devices):
        print(f"\n[{i+1}/{len(devices)}] Capturing {dev}...")
        try:
            result = subprocess.run(
                [adb, "-s", dev, "exec-out", "screencap", "-p"],
                capture_output=True, timeout=10, **kw
            )
            if result.returncode == 0 and len(result.stdout) > 100:
                img = np.frombuffer(result.stdout, np.uint8)
                color = cv2.imdecode(img, cv2.IMREAD_COLOR)
                if color is not None:
                    fname = f"screenshot_{dev.replace(':','_')}.png"
                    cv2.imwrite(fname, color)
                    print(f"  Saved: {fname} ({color.shape[1]}x{color.shape[0]})")
                else:
                    print(f"  Failed to decode!")
            else:
                print(f"  Capture failed!")
        except Exception as e:
            print(f"  Error: {e}")
    
    print("\n" + "=" * 50)
    print("  DONE!")
    print("=" * 50)
    print("\nNext steps:")
    print("1. Open the screenshot file (with Paint, etc)")
    print("2. Find the popup (Unstable network / RETRY)")  
    print("3. Crop JUST the RETRY button")
    print("4. Save as: img\\fixnet1.png")
    print("5. Run: python test_popup.py to verify")
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
