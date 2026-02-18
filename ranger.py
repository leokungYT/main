import cv2
import numpy as np
import subprocess
import os
from time import sleep
import sys
import shutil
import glob
import tempfile
import json
import threading
import queue
import concurrent.futures
import colorama
from colorama import Fore, Style

colorama.init(autoreset=True)

# Global Config
config = {
    "first_loop": True
}
adb_path = "adb" # Will be updated by find_adb_executable

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
        try:
            with open("config.json", "w") as f:
                json.dump(config, f, indent=4)
            print("[OK] Created default config.json")
        except:
            pass

def find_adb_executable():
    global adb_path
    
    # 1. Check local adb folder
    if os.path.exists(r"adb\adb.exe"):
        adb_path = os.path.abspath(r"adb\adb.exe")
        print(f"[OK] Found local ADB: {adb_path}")
        
        # Test ADB Execution (Check for missing DLLs)
        try:
            ver = subprocess.check_output([adb_path, "version"], text=True)
            print(f"[DEBUG] {ver.strip()}")
        except Exception as e:
            print(f"[ERR] Failed to execute ADB (Missing DLLs?): {e}")
            return False
            
        return True

    # 2. Check system PATH
    try:
        subprocess.run(["adb", "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        adb_path = "adb"
        print("[OK] Found ADB in system PATH")
        return True
    except FileNotFoundError:
        pass

    # 3. Check MuMu specific paths
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
    """Auto-scan and connect to common emulator ports using ThreadPoolExecutor"""
    print("[INFO] Auto-connecting to common emulator ports...")
    
    # Specific ports for popular emulators
    manual_ports = [
        7555,   # MuMu Player 6 / X
        62001,  # Nox
        16384, 16416, 16448, # MuMu 12 instances
        21503   # MEmu
    ]
    
    # Standard range (LDPlayer, BlueStacks, etc.) - Expanded
    scan_range = [5555 + (i * 2) for i in range(20)] # Scan up to 5595
    
    all_ports = sorted(list(set(manual_ports + scan_range)))
    
    print(f"[INFO] Scanning {len(all_ports)} ports...")

    def try_connect(port):
        target = f"127.0.0.1:{port}"
        cmd = [adb_path, "connect", target]
        try:
            # print(f"[DEBUG] Scanning {target}...")
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3, text=True)
            output = proc.stdout.strip()
            
            if "connected to" in output:
                 print(f"[OK] Connected to {target}")
            elif "refused" not in output and "cannot connect" not in output:
                 print(f"[DBG] {target} -> {output}")
            # else:
            #      print(f"[FAIL] {target}")
                 
        except subprocess.TimeoutExpired:
            # print(f"[TIMEOUT] {target}")
            pass
        except Exception as e:
            print(f"[ERR] {target}: {e}")

    # Use ThreadPoolExecutor for parallel scanning
    # Force iteration to ensure exceptions are caught/handled if strict=True (though we swallow them)
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(try_connect, all_ports))
            
    print("[OK] Port scan finished.")

def get_connected_devices():
    try:
        # Use simple os.popen or subprocess to be safer with paths
        # Quote path just in case
        adb_cmd = f'"{adb_path}"' if " " in adb_path else adb_path
        cmd = f'{adb_cmd} devices'
        # print(f"[DEBUG] Running: {cmd}")
        result = subprocess.check_output(cmd, shell=True, text=True)
        print(f"[DEBUG] Raw 'adb devices' output:\n{result}")
            
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

class RangerBot(threading.Thread):
    def __init__(self, device_id, file_queue):
        threading.Thread.__init__(self)
        self.device_id = device_id
        self.file_queue = file_queue
        self.daemon = True
        
        # Determine unique filename for this thread
        safe_dev = device_id.replace(":", "_")
        self.filename = os.path.join(tempfile.gettempdir(), f"screen-{safe_dev}.png")
        self.first_loop_done = not config.get("first_loop", True)
        
        # Sequence Definitions
        self.seq1 = ['icon.png', 'apple.png', (932, 133), (930, 253), (926, 327), 'check-l4.png']
        self.seq2 = ['check-gusetid.png', 'check-gusetid1.png', (932, 133), (930, 253), (926, 327), 'check-l4.png', 'check-ok1.png', 'check-ok2.png', 'check-ok3.png', 'check-ok4.png']
        
        self.adb_cmd = f'"{adb_path}"' if " " in adb_path else adb_path

    def run(self):
        try:
            print(f"[{self.device_id}] Bot Thread Started", flush=True)
            
            while True:
                # Check queue first to see if we should just exit if empty? 
                # But maybe we need to process first_loop even if queue is empty?
                # Usually we process files. If no files, we stop.
                if self.file_queue.empty():
                    print(f"[{self.device_id}] Queue is empty. Stopping thread.", flush=True)
                    break

                try:
                    # 0. Check First Loop
                    if not self.first_loop_done:
                        res = self.first_loop_process()
                        if res == "complete":
                            self.first_loop_done = True
                        else:
                            print(f"[{self.device_id}] First loop failed or incomplete. Retrying...")
                            sleep(2)
                            continue # Retry first loop

                    # 1. Get File
                    try:
                        xml_file = self.file_queue.get(timeout=2)
                    except queue.Empty:
                        break
                    
                    print(f"[{self.device_id}] Processing file: {os.path.basename(xml_file)}")

                    # 2. Inject
                    injected_file = self.inject_file(xml_file)
                    
                    if injected_file:
                        # 3. Login
                        status = self.main_login(injected_file)
                        
                        if status == "success":
                            self.handle_success(injected_file)
                        elif status == "failed":
                            self.handle_failure(injected_file)
                            self.first_loop_done = False # Reset flow
                        else:
                            print(f"[{self.device_id}] Unknown status. Moving to next.")
                    else:
                        # Injection failed, maybe try next file or same file? 
                        # For now, it's consumed from queue effectively.
                        print(f"[{self.device_id}] Injection failed for {xml_file}")
                    
                    self.file_queue.task_done()
                    
                except Exception as e:
                    print(f"[{self.device_id}] Critical Thread Error: {e}", flush=True)
                    sleep(5)
        except Exception as e:
            print(f"[{self.device_id}] Thread Crash on Startup: {e}", flush=True)

    def handle_success(self, file_path):
        success_path = os.path.join(os.getcwd(), "login-success")
        if not os.path.exists(success_path): os.makedirs(success_path)
        
        print(f"[{self.device_id}] ✅ Login SUCCESS. Moving file.")
        dst = os.path.join(success_path, os.path.basename(file_path))
        try:
            shutil.move(file_path, dst)
        except Exception as e:
            print(f"[{self.device_id}] Error moving file: {e}")

    def handle_failure(self, file_path):
        failed_path = os.path.join(os.getcwd(), "login-failed")
        if not os.path.exists(failed_path): os.makedirs(failed_path)
        
        # 1. Pull the actual shared_pref that failed (from device)
        # Note: The original 'save_failed_file' logic pulled FROM device TO login-failed
        
        src_remote = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
        dst_local = os.path.join(failed_path, os.path.basename(file_path))
        
        print(f"[{self.device_id}] 📥 Pulling failed file info...")
        
        # Copy to tmp then pull
        temp_remote = f"/data/local/tmp/failed_pref_{self.device_id.replace(':','_')}.xml"
        subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", f"su -c 'cp {src_remote} {temp_remote}'"])
        subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", f"su -c 'chmod 666 {temp_remote}'"])
        subprocess.run([self.adb_cmd, "-s", self.device_id, "pull", temp_remote, dst_local], 
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        print(f"[{self.device_id}] Saved failed file to {dst_local}")
        
        # 2. Delete original from backup (since we moved the result to login-failed)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"[{self.device_id}] 🗑️ Deleted original file from backup.")
        except Exception as e:
            print(f"[{self.device_id}] Error deleting original: {e}")

    # --- Interaction Methods ---
    def capture_screen(self):
        # Optimized capture
        # Try exec-out first
        cmd = f'{self.adb_cmd} -s {self.device_id} exec-out screencap -p > "{self.filename}"'
        os.system(cmd)
        
        if not os.path.exists(self.filename) or os.path.getsize(self.filename) == 0:
            # Fallback
            os.system(f'{self.adb_cmd} -s {self.device_id} shell screencap -p /sdcard/screen.png')
            os.system(f'{self.adb_cmd} -s {self.device_id} pull /sdcard/screen.png "{self.filename}"')
    
    def find(self, template_path, similarity=0.8):
        self.capture_screen()
        if not os.path.exists(self.filename): return None
        
        img = cv2.imread(self.filename, 0)
        template = cv2.imread(template_path, 0)
        
        if img is None or template is None:
            return None
            
        result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
        loc = np.where(result >= similarity)
        
        if len(loc[0]) > 0:
            y, x = loc[0][0], loc[1][0]
            h, w = template.shape
            return x+w//2, y+h//2
        return None
    
    def exists(self, template_path, similarity=0.8):
        return self.find(template_path, similarity) is not None

    def click(self, PSMRL, similarity=0.8):
        target = None
        if isinstance(PSMRL, str):
            if os.path.exists(PSMRL):
                target = self.find(PSMRL, similarity)
        elif isinstance(PSMRL, tuple):
            target = PSMRL
            
        if target:
            x, y = target
            # Use os.system with formatted string to handle adb_cmd quotes correctly
            cmd = f'{self.adb_cmd} -s {self.device_id} shell input tap {x} {y}'
            os.system(cmd)
            return True
        return False
    
    def swipe(self, x1, y1, x2, y2, duration=300):
        os.system(f'{self.adb_cmd} -s {self.device_id} shell input swipe {x1} {y1} {x2} {y2} {duration}')

    def check_error_images(self):
        """Helper to find error images (failed1, fixbuglogin)"""
        error_images = [r"img\fixbuglogin.png", r"img\failed1.png"]
        for err in error_images:
            if self.exists(err):
                return err
        return None

    # --- Logic Methods ---
    def clear_specific_shared_prefs(self):
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
        base = "/data/data/com.linecorp.LGRGS/shared_prefs"
        for f in files_to_delete:
            subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", f"su -c 'rm -f {base}/{f}'"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def inject_file(self, local_xml_path):
        print(f"[{self.device_id}] Injecting file (Robust Mode)...")
        
        # 0. Force Stop App explicitly to release locks
        subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(0.5)

        src = os.path.abspath(local_xml_path)
        tmp = f"/data/local/tmp/temp_pref_{self.device_id.replace(':','_')}.xml"
        final_dir = "/data/data/com.linecorp.LGRGS/shared_prefs"
        final = f"{final_dir}/_LINE_COCOS_PREF_KEY.xml"
        
        try:
            # 1. Push to temp
            subprocess.run([self.adb_cmd, "-s", self.device_id, "push", src, tmp], 
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            
            # 2. Advanced Move & Permission Fix
            # - mkdir -p shared_prefs
            # - mv file
            # - chmod 666
            # - chown to match parent dir (important for some android versions)
            # - restorecon (fix selinux context)
            
            shell_cmd = (
                f"su -c '"
                f"mkdir -p {final_dir} && "
                f"mv -f {tmp} {final} && "
                f"chmod 666 {final} && "
                # Try to emulate chown from parent folder ownership
                f"chown $(stat -c %u:%g {final_dir}) {final} || true && "
                f"restorecon {final} || true"
                f"'"
            )
            
            res = subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", shell_cmd],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if res.returncode == 0:
                print(f"[{self.device_id}] Injection Successful (Permissions Fixed)")
                return local_xml_path
            else:
                print(f"[{self.device_id}] Shell error: {res.stderr.decode()}")
                return None
                
        except Exception as e:
            print(f"[{self.device_id}] Injection Exception: {e}")
        
        return None

    def first_loop_process(self):
        try:
            print(f"[{self.device_id}] Starting First Loop Process...")
            self.clear_specific_shared_prefs()
            sleep(3)
            
            # Restart App
            subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
            sleep(1)
            subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", "input keyevent 3"]) # Home
            sleep(2)
            
            
            print(f"[{self.device_id}] Processing SEQ 1...")
            # Reuse simplified loop logic
            if not self.process_sequence(self.seq1): return "failed_seq1"
            
            print(f"[{self.device_id}] Waiting 8s then Back...")
            sleep(8)
            subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", "input keyevent 4"])
            sleep(2)
            
            print(f"[{self.device_id}] Processing SEQ 2...")
            if not self.process_sequence(self.seq2): return "failed_seq2"
            
            print(f"[{self.device_id}] First Loop Completed!")
            subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
            sleep(2)
            return "complete"
            
        except Exception as e:
            print(f"[{self.device_id}] First Loop Error: {e}")
            return "error"

    def process_sequence(self, sequence):
        for item in sequence:
            # Special handling: if item is tuple (coords), ensure previous image was clicked?
            # User wants: Click check-l1.png THEN click coords.
            
            if isinstance(item, tuple):
                print(f"[{self.device_id}] Tap {item}")
                self.click(item)
                sleep(8)
                continue
                
            img = item
            print(f"[{self.device_id}] Waiting for {img}...")
            
            # If it's check-l1.png, we must ensure it is found.
            # If not found after timeout? User said "sometimes it doesn't click check-l1 and bugs".
            
            wait_limit = 60
            start_wait = 0
            found = False
            
            while start_wait < wait_limit:
                loc = self.find(f"img\\{img}")
                if loc:
                    self.click(loc)
                    print(f"[{self.device_id}] Clicked {img}")
                    if img == 'apple.png':
                        sleep(10)
                    else:
                        sleep(6)
                    found = True
                    break 
                
                # Check for bugs while waiting in sequence?
                if self.check_error_images():
                    print(f"[{self.device_id}] Bug found during sequence! Restarting first_loop...")
                    return False

                sleep(1)
                start_wait += 1
            
            if not found:
                 print(f"[{self.device_id}] ⚠️ Failed to find {img}. Sequence broken.")
                 return False # Fail the sequence
                 
        return True

    def main_login(self, current_filename):
        print(f"[{self.device_id}] Starting Main Login...")
        
        # Clear app
        subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(2)
        
        # Click icon if found
        if self.exists(r"img\icon.png"):
            self.click(r"img\icon.png")
            sleep(5)
            
        loop_count = 0
        status = "unknown"
        
        while True:
            loop_count += 1
            if loop_count % 5 == 0:
                print(f"[{self.device_id}] Login Loop #{loop_count}")

            # Crash/Icon Check (Restart if found)
            if self.exists(r"img\icon.png"):
                print(f"[{self.device_id}] Found icon.png (App Closed?). Relaunching...")
                self.click(r"img\icon.png")
                sleep(5)
                continue
                
            # Success
            if self.exists(r"img\stoplogin.png"):
                print(f"[{self.device_id}] Found stoplogin (Success)")
                status = "success"
                break
                
            # Failed
            if self.exists(r"img\login-failed.png"):
                print(f"[{self.device_id}] Found login-failed. Executing recovery sequence...")
                
                # 1. Click login-failed1
                if self.exists(r"img\login-failed1.png"):
                    self.click(r"img\login-failed1.png")
                    sleep(2)
                
                # 2. Run SEQ1 (Skip icon)
                # subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", "input keyevent 3"])
                # sleep(2)
                
                if self.process_sequence(self.seq1[1:]):
                    # 3. Wait/Back logic (same as first_loop)
                    print(f"[{self.device_id}] SEQ1 done. Waiting 8s then Back...")
                    sleep(8)
                    subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", "input keyevent 4"])
                    sleep(2)
                    
                    # 4. SEQ2
                    print(f"[{self.device_id}] Processing SEQ 2...")
                    self.process_sequence(self.seq2)
                
                # 5. Clear App
                subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
                status = "failed"
                break
                
            # Error/Reset (failed1, fixbuglogin)
            error_images = [r"img\fixbuglogin.png", r"img\failed1.png"]
            error_found = None
            for err in error_images:
                if self.exists(err):
                    error_found = err
                    break
            
            if error_found:
                 print(f"[{self.device_id}] Found {error_found}. Waiting 8s...")
                 sleep(8)
                 if self.exists(error_found):
                     print(f"[{self.device_id}] Error persisted. Restarting App.")
                     subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
                     sleep(2)
                     subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", "input keyevent 3"])
                     sleep(2)
                     if self.exists(r"img\icon.png"):
                         self.click(r"img\icon.png")
                         sleep(5)
                     continue
            
            # Event
            if self.exists(r"img\event.png"):
                print(f"[{self.device_id}] Handling Event...")
                self.click(r"img\event.png")
                sleep(1)
                
                # Back loop
                back_attempts = 0
                while True:
                    # Burst 3 back
                    cmd = f"input keyevent 4 && input keyevent 4 && input keyevent 4"
                    subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", cmd])
                    back_attempts += 3
                    
                    if back_attempts % 9 == 0:
                        if self.exists(r"img\cancel.png"):
                            self.click(r"img\cancel.png")
                            break
                        if self.exists(r"img\stoplogin.png"):
                            status = "success"
                            break
                    
                    if back_attempts > 60: break
                    sleep(0.5)
                
                if status == "success": break
            
            sleep(1)
            if loop_count > 500:
                print(f"[{self.device_id}] Max loops reached.")
                break
        
        # Cleanup
        subprocess.run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        return status


if __name__ == "__main__":
    print("=== Auto ADB Ranger Script (Multi-Threaded) ===")
    
    load_config()
    
    if not find_adb_executable():
        print("ADB Not Found.")
        sys.exit(1)
    
    # Reset ADB to fix stale connections
    print("[INFO] Restarting ADB Server...")
    subprocess.run([adb_path, "kill-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run([adb_path, "start-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
    connect_known_ports()
    devices = get_connected_devices()
    print(f"[DEV] Connected: {devices}")
    
    if not devices:
        print("No devices.")
        sys.exit(0)
        
    # Prepare Queue
    file_queue = queue.Queue()
    backup_path = os.path.join(os.getcwd(), "backup")
    
    if os.path.exists(backup_path):
        files = glob.glob(os.path.join(backup_path, "*.xml"))
        for f in files:
            file_queue.put(f)
        print(f"[FILE] Loaded {len(files)} files into queue.")
    else:
        print("[WARN] No backup folder.")
        
    # Start Threads
    threads = []
    print(f"[INFO] Starting {len(devices)} threads...")
    
    for dev in devices:
        t = RangerBot(dev, file_queue)
        t.start()
        threads.append(t)
        
    # Wait for threads
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n[STOP] Keyboard Interrupt. Stopping...")
        
    print("\n[DONE] All tasks completed.")
