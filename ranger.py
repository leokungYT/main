import cv2
import numpy as np
import subprocess
import os
from time import sleep
import sys
import time
import shutil
import glob
import tempfile
import json

# ... (Previous imports match current file)

# Global Config
config = {
    "first_loop": True
}

def load_config():
    global config
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r") as f:
                config.update(json.load(f))
            print("[OK] Config loaded:", config)
        except Exception as e:
            print(f"[WARN] Error loading config: {e}")
    else:
        # Create default config
        try:
            with open("config.json", "w") as f:
                json.dump(config, f, indent=4)
            print("[OK] Created default config.json")
        except:
            pass
            
# ... (Previous code)

def save_failed_file(original_name):
    """Pull shared_prefs to login-failed folder"""
    failed_path = os.path.join(os.getcwd(), "login-failed")
    if not os.path.exists(failed_path):
        os.makedirs(failed_path)
        
    src_file = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
    dst_file = os.path.join(failed_path, os.path.basename(original_name))
    
    print(f"[{device_id}] 📥 Pulling failed file to: {dst_file}")
    
    adb_cmd = f'"{adb_path}"' if " " in adb_path else adb_path
    
    # 1. Copy to tmp with shell (for permissions)
    temp_remote = "/data/local/tmp/failed_pref.xml"
    subprocess.run([adb_cmd, "-s", device_id, "shell", f"su -c 'cp {src_file} {temp_remote}'"])
    subprocess.run([adb_cmd, "-s", device_id, "shell", f"su -c 'chmod 666 {temp_remote}'"])
    
    # 2. Pull from tmp
    subprocess.run([adb_cmd, "-s", device_id, "pull", temp_remote, dst_file], 
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def main_login(current_filename=None):
    print(f"[{device_id}] Starting main_login...")
    
    # 0. Clear App First
    adb_cmd = f'"{adb_path}"' if " " in adb_path else adb_path
    print(f"[{device_id}] Clearing app before starting...")
    subprocess.run([adb_cmd, "-s", device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
    sleep(2)

    # 1. Click Icon (Optional)
    if exists(r"img\icon.png"):
        print(f"[{device_id}] Found icon, entering game...")
        click(r"img\icon.png")
        sleep(5)

    # 2. Main Loop
    loop_count = 0
    success = False
    status = "unknown"
    
    # Loop until stoplogin found or failed
    while True:
        loop_count += 1
        if loop_count % 5 == 0:
            print(f"[{device_id}] Main Loop #{loop_count} running...")
            
        # Success Condition
        if exists(r"img\stoplogin.png"):
            print(f"[{device_id}] Found stoplogin.png!")
            status = "success"
            break
            
        # Failure Condition
        if exists(r"img\login-failed.png") or exists(r"img\fixid.png"):
            print(f"[{device_id}] ⚠️ Found login-failed.png!")
            status = "failed"
            break

        # Check for event
        if exists(r"img\event.png"):
            print(f"[{device_id}] Found event.png, handling event...")
            click(r"img\event.png")
            sleep(1)
            
            # Press back repeatedly until cancel.png found
            back_attempts = 0
            adb_cmd = f'"{adb_path}"' if " " in adb_path else adb_path
            
            while True:
                # Burst 3 BACK keys
                subprocess.run([adb_cmd, "-s", device_id, "shell", "input keyevent 4 && input keyevent 4 && input keyevent 4"])
                back_attempts += 3
                
                if back_attempts % 9 == 0:
                    print(f"[{device_id}] Checking exit conditions (Attempts: {back_attempts})...")
                    if exists(r"img\cancel.png"):
                        print(f"[{device_id}] Found cancel.png! Clicking and finishing sequence.")
                        click(r"img\cancel.png")
                        break
                        
                    if exists(r"img\stoplogin.png"):
                        print(f"[{device_id}] Found stoplogin.png inside cancel loop!")
                        status = "success"
                        break

                if back_attempts > 60: 
                    print(f"[{device_id}] Too many back attempts, breaking cancel loop...")
                    break
                    
                sleep(0.5) 
        
        if status == "success": break
        
        sleep(1)
        
        if loop_count > 500:
             print(f"[{device_id}] ⚠️ Max loops reached.")
             break

    if status == "success":
        print(f"[{device_id}] Login sequence successful! Clearing app...")
        subprocess.run([adb_cmd, "-s", device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        return "success"
    
    elif status == "failed":
        if current_filename:
            save_failed_file(current_filename)
            
        print(f"[{device_id}] Login FAILED. Clearing app and requesting First Loop reset...")
        subprocess.run([adb_cmd, "-s", device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        return "failed"
    
    return "unknown"

# ... (Previous code remains)


def find_adb_executable():
    global adb_path
    
    # 1. Check local adb folder
    if os.path.exists(r"adb\adb.exe"):
        adb_path = r"adb\adb.exe"
        print(f"[OK] Found local ADB: {adb_path}")
        return True

    # 2. Check system PATH
    try:
        subprocess.run(["adb", "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        adb_path = "adb"
        print("[OK] Found ADB in system PATH")
        return True
    except FileNotFoundError:
        pass

    # 3. Check MuMu specific paths (from main.py)
    mumu_adb_paths = [
        "F:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe",
        "C:\\Program Files\\Netease\\MuMuPlayerGlobal-12.0\\shell\\adb.exe",
        "C:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe",
        "F:\\MuMuPlayerGlobal-12.0\\shell\\adb.exe",
        "D:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe",
        "E:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe"
    ]
    
    for path in mumu_adb_paths:
        if os.path.exists(path):
            adb_path = path
            print(f"[OK] Found MuMu ADB: {path}")
            return True
            
    print("[FAIL] ADB executable not found!")
    return False

def connect_known_ports():
    """Auto-scan and connect to common emulator ports"""
    print("[INFO] Auto-connecting to common emulator ports...")
    
    # Scan from 5555 up to 30 devices
    start_port = 5555
    max_devices = 30
    
    for i in range(max_devices): 
        port = start_port + (i * 2)
        print(f"\r[WAIT] Connecting to 127.0.0.1:{port}...", end="", flush=True)
        cmd = [adb_path, "connect", f"127.0.0.1:{port}"]
        try:
            # Run fast with short timeout (0.5s is enough for localhost)
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=0.5)
        except:
            pass
    print("\n[OK] Finished checking ports.")

def get_connected_devices():
    """Parse 'adb devices' output to get list of serials"""
    try:
        if " " in adb_path:
            # Handle path with spaces
            cmd = f'"{adb_path}" devices'
            result = subprocess.check_output(cmd, shell=True, text=True)
        else:
            result = subprocess.check_output([adb_path, "devices"], text=True)
            
        lines = result.strip().split("\n")[1:]
        devices = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices
    except Exception as e:
        print(f"[FAIL] Error getting devices: {e}")
        return []

def capture_screen():
    # Use proper quoting for paths with spaces
    adb_cmd = f'"{adb_path}"' if " " in adb_path else adb_path
    
    # Try exec-out first (faster)
    cmd = f'{adb_cmd} -s {device_id} exec-out screencap -p > {filename}'
    os.system(cmd)
    
    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
        # Fallback to shell screencap + pull
        os.system(f'{adb_cmd} -s {device_id} shell screencap -p /sdcard/screen.png')
        os.system(f'{adb_cmd} -s {device_id} pull /sdcard/screen.png {filename}')
        
    if not os.path.exists(filename):
         # raise Exception(f"[FAIL] Capture screen failed for {device_id}")
         print(f"❌ Capture screen failed for {device_id}")

def find(template_path, similarity=0.8):
    capture_screen()
    if not os.path.exists(filename): return None
    
    img = cv2.imread(filename, 0)
    template = cv2.imread(template_path, 0)

    if img is None or template is None:
        # print(f"❌ ไม่พบภาพหรือเทมเพลต: {template_path}")
        return None

    result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
    loc = np.where(result >= similarity)
    if len(loc[0]) > 0:
        y, x = loc[0][0], loc[1][0]
        h, w = template.shape
        return x+w//2, y+h//2
    return None

def exists(template_path, similarity=0.8):
    return find(template_path, similarity) is not None

def click(PSMRL, similarity=0.8):
    target = None
    
    if isinstance(PSMRL, str): 
        if os.path.exists(PSMRL):
            # pattern image path
            target = find(PSMRL, similarity)
        else:
            # print(f"Image not found: {PSMRL}")
            pass
    elif isinstance(PSMRL, tuple) and len(PSMRL)==2:
        # (x,y)
        target = PSMRL

    if target:
        x, y = target
        adb_cmd = f'"{adb_path}"' if " " in adb_path else adb_path
        subprocess.run([
            adb_cmd, "-s", device_id, "shell",
            "input", "tap", str(x), str(y)
        ])
        return 1
    else:
        return 0

def swipe(start_x, start_y, end_x, end_y, duration_ms=300):
    adb_cmd = f'"{adb_path}"' if " " in adb_path else adb_path
    os.system(f'{adb_cmd} -s {device_id} shell input swipe {start_x} {start_y} {end_x} {end_y} {duration_ms}')

def inject_file():
    """Inject XML file from backup to device"""
    if not file_queue:
        return None

    xml_file = file_queue.pop(0)
    print(f"[{device_id}] 💉 Injecting file: {xml_file}")
    
    # 1. Prepare paths
    src_path = os.path.abspath(xml_file)
    dst_tmp_path = f"/data/local/tmp/temp_pref.xml"
    final_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
    
    adb_cmd = f'"{adb_path}"' if " " in adb_path else adb_path
    
    try:
        # 2. Push to local/tmp (writable)
        subprocess.run([adb_cmd, "-s", device_id, "push", src_path, dst_tmp_path], 
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        
        # 3. Create dest dir just in case
        subprocess.run([adb_cmd, "-s", device_id, "shell", "su -c 'mkdir -p /data/data/com.linecorp.LGRGS/shared_prefs'"])
        
        # 4. Move and chmod (requres root/su)
        # Use a single shell command to be robust
        shell_cmd = f"su -c 'mv -f {dst_tmp_path} {final_path} && chmod 666 {final_path}'"
        result = subprocess.run([adb_cmd, "-s", device_id, "shell", shell_cmd], 
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if result.returncode == 0:
            print(f"[{device_id}] ✅ File injected successfully.")
            return xml_file
        else:
            print(f"[{device_id}] ❌ Failed to move/chmod file: {result.stderr.decode()}")
            # Put back in queue? Or just skip? User said failed not needed yet.
            return None
            
    except Exception as e:
        print(f"[{device_id}] ❌ Error injecting file: {e}")
        return None



def main_login():
    print(f"[{device_id}] Starting main_login...")
    
    # 0. Clear App First
    adb_cmd = f'"{adb_path}"' if " " in adb_path else adb_path
    print(f"[{device_id}] Clearing app before starting...")
    subprocess.run([adb_cmd, "-s", device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
    sleep(2)

    # 1. Click Icon (Optional, if we are at home screen)
    if exists(r"img\icon.png"):
        print(f"[{device_id}] Found icon, entering game...")
        click(r"img\icon.png")
        sleep(5)

    # 2. Main Loop
    loop_count = 0
    success = False
    
    # Loop until stoplogin found
    while not exists(r"img\stoplogin.png"):
        loop_count += 1
        if loop_count % 5 == 0:
            print(f"[{device_id}] Main Loop #{loop_count} running...")
            
        # Check for event
        if exists(r"img\event.png"):
            print(f"[{device_id}] Found event.png, handling event...")
            click(r"img\event.png")
            sleep(1)
            
            # Press back repeatedly until cancel.png found
            # Mimic main.py: Burst fire BACK keys
            back_attempts = 0
            adb_cmd = f'"{adb_path}"' if " " in adb_path else adb_path
            
            while True:
                # Burst 3 BACK keys in one command for speed
                subprocess.run([adb_cmd, "-s", device_id, "shell", "input keyevent 4 && input keyevent 4 && input keyevent 4"])
                back_attempts += 3
                
                # Safety checks & Exit condition - Check every 9 presses (3 loops) implies faster execution
                # But to be safe and responsive, let's check every loop but avoid full check if possible?
                # No, textocr/exists is slow. match main.py: check periodically.
                
                if back_attempts % 9 == 0:
                    print(f"[{device_id}] Checking exit conditions (Attempts: {back_attempts})...")
                    if exists(r"img\cancel.png"):
                        print(f"[{device_id}] Found cancel.png! Clicking and finishing sequence.")
                        click(r"img\cancel.png")
                        break
                        
                    if exists(r"img\stoplogin.png"):
                        print(f"[{device_id}] Found stoplogin.png inside cancel loop!")
                        success = True
                        break

                if back_attempts > 60: 
                    print(f"[{device_id}] Too many back attempts, breaking cancel loop...")
                    break
                    
                sleep(0.5) # Short sleep between bursts
        
        if success: break # Break outer loop if success found in inner loop
        
        sleep(1)
        
        # Safety break to avoid infinite loop if nothing happens for too long
        if loop_count > 500:
             print(f"[{device_id}] ⚠️ Max loops reached.")
             break

    print(f"[{device_id}] Found stoplogin.png! Clearing app...")
    adb_cmd = f'"{adb_path}"' if " " in adb_path else adb_path
    subprocess.run([adb_cmd, "-s", device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
    print(f"[{device_id}] Login sequence finished!")
    return True
    
    return False

def clear_specific_shared_prefs():
    files_to_delete = [
        "ANALYTICS_COMMON_SHARED_PREFERENCE.xml", "Cocos2dxPrefsFile.xml", 
        "PROMOTION_Cache.xml", "WebViewChromiumPrefs.xml", 
        "_LINE_COCOS_PREF_KEY.xml", "admob.xml", 
        "com.facebook.ads.flash.xml", "com.facebook.internal.MODEL_STORE.xml", 
        "com.facebook.internal.preferences.APP_GATEKEEPERS.xml", 
        "com.facebook.internal.preferences.APP_SETTINGS.xml", 
        "com.facebook.sdk.USER_SETTINGS.xml", "com.facebook.sdk.appEventPreferences.xml", 
        "com.facebook.sdk.attributionTracking.xml", "com.google.android.gms.appid.xml", 
        "com.google.android.gms.measurement.prefs.xml", "com.google.firebase.messaging.xml", 
        "com.linecorp.LGRGS_preferences.xml", "com.linecorp.growthy.internal.PURCHASE.xml", 
        "com.linecorp.linesdk.sharedpreference.encryptionsalt.xml", "line_notice_pref.xml", 
        "paid_storage_sp.xml", "pcvmspf.xml", "trident.preferences.xml"
    ]
    
    adb_cmd = f'"{adb_path}"' if " " in adb_path else adb_path
    base_path = "/data/data/com.linecorp.LGRGS/shared_prefs"
    
    print(f"[{device_id}] Removing specific shared_prefs...")
    for f in files_to_delete:
        cmd = f"rm -f {base_path}/{f}"
        subprocess.run([adb_cmd, "-s", device_id, "shell", f"su -c '{cmd}'"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print(f"[{device_id}] shared_prefs cleanup completed.")

def check_black_screen(threshold=0.8):
    capture_screen()
    if not os.path.exists(filename): return False
    img = cv2.imread(filename)
    if img is None: return False
    return np.mean(img) < (255 * (1 - threshold)) # 0.8 threshold means < 20% brightness? No, prompt used < 255*threshold/100, assuming input logic.
    # main.py logic: is_black = mean_brightness < (255 * threshold / 100)
    # If threshold is 0.8 (0.8%), that's very dark. 
    # If threshold is 80 (80%), that's impossible.
    # main.py passed 0.8. 255*0.8/100 = 2.04. Very dark.
    # Let's use 5.0 as safe black.
    return np.mean(img) < 5.0

def first_loop_process():
    """First loop logic with specific file deletion"""
    try:
        print(f"[{device_id}] Starting first loop process")
        
        # 1. Clear specific data instead of full clear
        clear_specific_shared_prefs()
        sleep(3)
        
        # 2. Open App (Use monkey to launch main activity automatically)
        adb_cmd = f'"{adb_path}"' if " " in adb_path else adb_path
        subprocess.run([adb_cmd, "-s", device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(1)
        # Use monkey -p package -c category.LAUNCHER 1
        subprocess.run([adb_cmd, "-s", device_id, "shell", "monkey", "-p", "com.linecorp.LGRGS", "-c", "android.intent.category.LAUNCHER", "1"])
        sleep(10)
        
        # Wait a bit before proceeding
        sleep(10)


        # Check closeapp
        print(f"[{device_id}] Checking closeapp.png...")
        close_start = time.time()
        while time.time() - close_start < 10:
             if exists(r"img\closeapp.png"):
                 print(f"[{device_id}] Found closeapp.png, restarting...")
                 subprocess.run([adb_cmd, "-s", device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
                 sleep(2)
                 return "restart_first_loop"
             sleep(0.8)
             
        # Check save
        print(f"[{device_id}] Looking for save.png...")
        save_found = False
        save_start = time.time()
        while time.time() - save_start < 20:
             save_loc = find(r"img\save.png")
             if save_loc:
                 click(save_loc)
                 save_found = True
                 print(f"[{device_id}] Found save.png!")
                 break
             
             if exists(r"img\stopcheck.png"):
                 subprocess.run([adb_cmd, "-s", device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
                 return "complete"
                 
             sleep(0.8)
             
        if not save_found:
            print(f"[{device_id}] save.png not found")
            subprocess.run([adb_cmd, "-s", device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
            return "restart_from_test" # Logic says restart
            
        # Sequences
        seq1 = ['apple.png', 'check-l1.png', 'check-l2.png', 'check-l3.png', 'check-l4.png']
        seq2 = ['check-gusetid.png', 'check-gusetid1.png', 'check-l1.png', 'check-l2.png', 'check-l3.png', 'check-l4.png', 'check-ok1.png', 'check-ok2.png', 'check-ok3.png', 'check-ok4.png']
        
        print(f"[{device_id}] Processing Sequence 1...")
        for img_name in seq1:
            start_t = time.time()
            found = False
            while time.time() - start_t < 60:
                loc = find(f"img\\{img_name}")
                if loc:
                    click(loc)
                    found = True
                    print(f"[{device_id}] Found {img_name}")
                    if img_name == 'check-l4.png': sleep(2)
                    sleep(1)
                    break
                sleep(0.8)
        
        print(f"[{device_id}] Seq 1 done. Waiting 8s then BACK...")
        sleep(8)
        subprocess.run([adb_cmd, "-s", device_id, "shell", "input keyevent 4"])
        sleep(2)
        
        print(f"[{device_id}] Processing Sequence 2...")
        for img_name in seq2:
            start_t = time.time()
            found = False
            while time.time() - start_t < 60:
                loc = find(f"img\\{img_name}")
                if loc:
                    click(loc)
                    found = True
                    print(f"[{device_id}] Found {img_name}")
                    sleep(1)
                    break
                sleep(0.8)
                
        print(f"[{device_id}] First loop completed!")
        subprocess.run([adb_cmd, "-s", device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(2)
        return "complete"
    except Exception as e:
        print(f"[{device_id}] Error in first_loop: {e}")
        return "error"

if __name__ == "__main__":
    print("=== Auto ADB Ranger Script ===")
    
    load_config()
    
    # 1. auto find adb
    if not find_adb_executable():
        print("Cannot continue without ADB.")
        sys.exit(1)

    # 2. auto connect ports
    connect_known_ports()
    
    # 3. get devices
    devices = get_connected_devices()
    print(f"[DEV] Connected devices: {devices}")
    
    if not devices:
        print("[FAIL] No devices found.")
        sys.exit(0)

    # 4. Load files

    
    backup_path = os.path.join(os.getcwd(), "backup")
    success_path = os.path.join(os.getcwd(), "login-success")
    
    if not os.path.exists(success_path):
        os.makedirs(success_path)
        
    file_queue = []
    if os.path.exists(backup_path):
        file_queue = glob.glob(os.path.join(backup_path, "*.xml"))
        print(f"[FILE] Found {len(file_queue)} files in backup/")
    else:
        print("[WARN] 'backup' folder not found!")

    # 5. Process Loop
    processed_count = 0
    device_first_loop_done = {d: False for d in devices}
    
    while file_queue:
        files_left = len(file_queue)
        print(f"\n>>>> Queue Status: {files_left} files remaining <<<<")
        
        for dev in devices:
            if not file_queue:
                break
                
            print(f"\n========================================")
            print(f"▶ Processing Device: {dev}")
            print(f"========================================")
            
            # Update globals for this device
            device_id = dev
            # Use temp directory for screenshots
            filename = os.path.join(tempfile.gettempdir(), f"screen-{dev.replace(':', '_')}.png")
            
            try:
                # 0. Check First Loop
                if not device_first_loop_done[dev]:
                    res = first_loop_process()
                    if res == "complete":
                        device_first_loop_done[dev] = True
                    else:
                        print(f"[{dev}] First loop not complete ({res}), retrying next round...")
                        continue # Skip to next device/loop, don't inject yet
                
                # 1. Inject File
                injected_file = inject_file()
                
                if injected_file:
                    # 2. Login
                    is_success = main_login()
                    
                    if is_success:
                        # Move to login-success
                        try:
                            fname = os.path.basename(injected_file)
                            dest = os.path.join(success_path, fname)
                            shutil.move(injected_file, dest)
                            print(f"[{device_id}] [OK] Moved {fname} to login-success")
                            processed_count += 1
                        except Exception as e:
                             print(f"[{device_id}] [WARN] Failed to move file: {e}")
                    else:
                        print(f"[{device_id}] [WARN] Login did not complete. File remains in backup.")
                        
            except Exception as e:
                print(f"[FAIL] Error processing {dev}: {e}")
                
        # Small delay between batches
        sleep(1)
            
    print(f"\n[OK] All files processed. Total success: {processed_count}")

