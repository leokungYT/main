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
import ssl

colorama.init(autoreset=True)

# Fix SSL certificate error for downloading EasyOCR models
ssl._create_default_https_context = ssl._create_unverified_context

# =============================================================
# Global Config
# =============================================================
# Default config (will be overridden by config files)
config = {
    "first_loop": True,
    "thread_delay": 5,
    "find_ranger": 0,
    "find_gear": 0,
    "find_all": 1,
    "custommode": 0,
    "custom": {"characters": []},
    "characters": [],
    "ranger_images": {},
    "gearname": {},
    "weaponname": {},
    "ocr_region": {"x": 463, "y": 153, "w": 397, "h": 321}
}

adb_path = "adb"

# EasyOCR reader - loaded once globally
_ocr_reader = None
_ocr_lock = threading.Lock()  # Thread-safe OCR init

def get_ocr_reader():
    """Get or create EasyOCR reader (singleton, thread-safe)"""
    global _ocr_reader
    if _ocr_reader is None:
        with _ocr_lock:
            if _ocr_reader is None:
                import easyocr
                print("[INFO] Loading EasyOCR model (first time only)...")
                _ocr_reader = easyocr.Reader(['en'], gpu=False)
                print("[OK] EasyOCR model loaded!")
    return _ocr_reader


def load_config():
    global config
    
    # Load main config from ranger-gear_config.json
    main_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ranger-gear_config.json")
    if os.path.exists(main_config_file):
        try:
            with open(main_config_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                config.update(loaded)
            print(f"[CONFIG] Loaded: {main_config_file}")
        except Exception as e:
            print(f"[WARN] Error loading config: {e}")
    else:
        print(f"[WARN] Config not found: {main_config_file}")
        print(f"[INFO] Using default config values")
    
    # Load from ranger config file (for override/extend)
    ranger_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "find-ranger_config.json")
    if os.path.exists(ranger_config_file):
        try:
            with open(ranger_config_file, 'r', encoding='utf-8') as f:
                ranger_conf = json.load(f)
                # Only update ranger-specific keys
                for key in ['custommode', 'custom', 'characters', 'ranger_images']:
                    if key in ranger_conf:
                        config[key] = ranger_conf[key]
            print(f"[CONFIG] Extended with ranger config: {ranger_config_file}")
        except Exception as e:
            print(f"[WARN] Error loading ranger config: {e}")
    
    # Load from gear config file (for override/extend)
    gear_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "checkgear_config.json")
    if os.path.exists(gear_config_file):
        try:
            with open(gear_config_file, "r", encoding="utf-8") as f:
                gear_conf = json.load(f)
                # Only update gear-specific keys
                for key in ['gearname', 'weaponname', 'ocr_region']:
                    if key in gear_conf:
                        config[key] = gear_conf[key]
            print(f"[CONFIG] Extended with gear config: {gear_config_file}")
        except Exception as e:
            print(f"[WARN] Error loading gear config: {e}")


def find_adb_executable():
    global adb_path
    
    # Check common locations
    script_dir = os.path.dirname(os.path.abspath(__file__))
    adb_locations = [
        os.path.join(script_dir, "adb", "adb.exe"),
        os.path.join(script_dir, "adb", "adb"),
        "adb",
    ]
    
    for loc in adb_locations:
        try:
            result = subprocess.run(
                [loc, "version"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                adb_path = loc
                print(f"[ADB] Found: {adb_path}")
                return True
        except:
            continue
    
    # Try system PATH
    adb_in_path = shutil.which("adb")
    if adb_in_path:
        adb_path = os.path.abspath(adb_in_path)
        print(f"[ADB] Found in PATH: {adb_path}")
        return True
    
    # Try common fallback "adb" string
    try:
        subprocess.run(["adb", "--version"], capture_output=True, timeout=5, check=True)
        adb_path = "adb"
        print(f"[ADB] Found 'adb' command in system")
        return True
    except:
        pass
    
    # Try MuMu emulator paths
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
            print(f"[ADB] Found MuMu ADB: {path}")
            return True
    
    return False


def connect_known_ports():
    """Auto-scan and connect to common emulator ports using ThreadPoolExecutor"""
    ports = [5555, 5556, 5557, 5558, 5559, 5560, 5561, 5562, 5563, 5564, 5565,
             5575, 5585, 7555, 62001, 62025, 62026, 21503, 21513, 21523, 21533]

    def try_connect(port):
        addr = f"127.0.0.1:{port}"
        try:
            result = subprocess.run(
                [adb_path, "connect", addr],
                capture_output=True, text=True, timeout=3
            )
            out = result.stdout.strip().lower()
            if "connected" in out and "cannot" not in out:
                print(f"[OK] Connected: {addr}")
                return addr
        except:
            pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(try_connect, port): port for port in ports}
        for future in concurrent.futures.as_completed(futures):
            future.result()


def get_connected_devices():
    try:
        result = subprocess.run(
            [adb_path, "devices"],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().split("\n")[1:]
        devices = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices
    except Exception as e:
        print(f"[ERR] get_connected_devices: {e}")
        return []


# =============================================================
# RangerGearBot Class - Unified Bot for Ranger + Gear
# =============================================================
class RangerGearBot(threading.Thread):
    def __init__(self, device_id, file_queue):
        threading.Thread.__init__(self)
        self.device_id = device_id
        self.file_queue = file_queue
        self.daemon = True
        
        # Determine which modes to run
        self.do_ranger = config.get("find_ranger", 0) or config.get("find_all", 1)
        self.do_gear = config.get("find_gear", 0) or config.get("find_all", 1)
        
        print(f"[{self.device_id}] Mode - Ranger: {self.do_ranger}, Gear: {self.do_gear}")
        
        # Unique filename for this thread
        safe_dev = device_id.replace(":", "_")
        self.filename = os.path.join(tempfile.gettempdir(), f"screen-{safe_dev}.png")
        self.first_loop_done = not config.get("first_loop", True)
        
        # Ranger Config
        if self.do_ranger:
            if config.get("custommode") == 1:
                custom_data = config.get("custom", {})
                self.characters = custom_data.get("characters", [])
                print(f"[{self.device_id}] Custom mode (custommode=1) -> searching: {self.characters}")
            else:
                self.characters = config.get("characters", [])
                print(f"[{self.device_id}] Find-all ranger mode -> searching {len(self.characters)} characters")
            
            # Auto-scan img/ranger/ folder for all png files
            self.ranger_image_mapping = config.get("ranger_images", {})
            ranger_folder = os.path.join("img", "ranger")
            self.ranger_files = []
            if os.path.exists(ranger_folder):
                for f in sorted(os.listdir(ranger_folder)):
                    if f.lower().endswith(".png"):
                        self.ranger_files.append(f"ranger/{f}")
                print(f"[{self.device_id}] Auto-loaded {len(self.ranger_files)} ranger images from img/ranger/")
        
        # Gear Config
        if self.do_gear:
            self.gear_names = config.get("gearname", {})
            self.weapon_names = config.get("weaponname", {})
            self.ocr_region = config.get("ocr_region", {"x": 463, "y": 153, "w": 397, "h": 321})
            print(f"[{self.device_id}] Gear mode -> {len(self.gear_names)} gears to check")
        
        # Store original filename for backup
        self.current_original_filename = None
        
        # Sequence Definitions
        self.seq1 = ['icon.png', 'apple.png', '@check-l1.png', (932, 133), (930, 253), (926, 327), 'check-l4.png']
        self.seq2 = ['check-gusetid.png', 'check-gusetid1.png', '@check-l1.png', (932, 133), (930, 253), (926, 327), 'check-l4.png', 'check-ok1.png', 'check-ok2.png', 'check-ok3.png', 'check-ok4.png']
        
        self.adb_cmd = adb_path
        self._screen = None
        self._screen_color = None
        self._template_cache = {}

    def run(self):
        try:
            print(f"[{self.device_id}] RangerGear Bot Thread Started", flush=True)
            
            while True:
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
                            continue

                    # 1. Get File
                    try:
                        xml_file = self.file_queue.get(timeout=2)
                    except queue.Empty:
                        break
                    
                    # Store original filename
                    self.current_original_filename = os.path.basename(xml_file)
                    print(f"[{self.device_id}] Processing file: {self.current_original_filename}")

                    # 2. Inject
                    injected_file = self.inject_file(xml_file)
                    
                    if injected_file:
                        # 3. Login (with ranger/gear flow based on mode)
                        status = self.main_login(injected_file)
                        
                        if status == "success":
                            self.handle_success(xml_file)
                        elif status == "failed":
                            self.handle_failure(xml_file)
                            self.first_loop_done = False
                        else:
                            print(f"[{self.device_id}] Status: {status}. Moving to next.")
                            # For timeout/unknown, we might want to keep or fail it
                            self.handle_failure(xml_file)
                    else:
                        print(f"[{self.device_id}] Injection failed for {xml_file}")
                    
                    self.file_queue.task_done()
                    
                except Exception as e:
                    print(f"[{self.device_id}] Critical Thread Error: {e}", flush=True)
                    sleep(5)
        except Exception as e:
            print(f"[{self.device_id}] Thread Crash on Startup: {e}", flush=True)

    # =========================================================
    # File Handling
    # =========================================================
    def handle_success(self, file_path):
        dst_dir = "login-success"
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
        base = os.path.basename(file_path)
        dst = os.path.join(dst_dir, base)
        try:
            shutil.move(file_path, dst)
            print(f"[{self.device_id}] Moved to {dst_dir}: {base}")
        except Exception as e:
            print(f"[{self.device_id}] Move error: {e}")

    def handle_failure(self, file_path):
        dst_dir = "login-failed"
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
        base = os.path.basename(file_path)
        dst = os.path.join(dst_dir, base)
        
        print(f"[{self.device_id}] Login FAILED. Pulling file from device for debug...")
        
        # Pull the current file from the device to see its state
        src_remote = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
        temp_remote = f"/data/local/tmp/failed_pref_{self.device_id.replace(':','_')}.xml"
        
        try:
            self.adb_shell(f"su -c 'cp {src_remote} {temp_remote}'")
            self.adb_shell(f"su -c 'chmod 666 {temp_remote}'")
            self.adb_run([self.adb_cmd, "-s", self.device_id, "pull", temp_remote, dst])
            print(f"[{self.device_id}] Saved failed session file to {dst}")
        except Exception as e:
            print(f"[{self.device_id}] Failed to pull remote file: {e}")
            # Fallback: move the original local file
            try:
                if os.path.exists(file_path):
                    shutil.move(file_path, dst)
            except: pass

        # Clean up local backup file if it still exists
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except: pass

    # =========================================================
    # Screen & Image Methods  
    # =========================================================
    @classmethod
    def _get_template(cls, template_path):
        if not hasattr(cls, '_template_cache_cls'):
            cls._template_cache_cls = {}
        
        if template_path not in cls._template_cache_cls:
            # Ensure path is absolute relative to script dir
            if not os.path.isabs(template_path):
                script_dir = os.path.dirname(os.path.abspath(__file__))
                full_path = os.path.join(script_dir, template_path)
            else:
                full_path = template_path
                
            # Convert forward slashes to backward slashes for Windows compatibility
            full_path = os.path.normpath(full_path)
            
            if not os.path.exists(full_path):
                print(f"[WARN] Image file not found: {full_path}")
                cls._template_cache_cls[template_path] = None
                return None
                
            tmpl = cv2.imread(full_path, 0)
            if tmpl is None:
                print(f"[WARN] Failed to read image (integrity check): {full_path}")
            cls._template_cache_cls[template_path] = tmpl
            
        return cls._template_cache_cls[template_path]

    def adb_run(self, args, timeout=10, **kwargs):
        return subprocess.run(args, capture_output=True, timeout=timeout, **kwargs)

    def adb_shell(self, shell_cmd, timeout=10):
        return subprocess.run(
            [self.adb_cmd, "-s", self.device_id, "shell", shell_cmd],
            capture_output=True, timeout=timeout)

    def capture_screen(self):
        """Capture screen and load into RAM"""
        try:
            result = subprocess.run(
                [self.adb_cmd, "-s", self.device_id, "exec-out", "screencap", "-p"],
                capture_output=True, timeout=10
            )
            if result.returncode == 0 and len(result.stdout) > 100:
                img_array = np.frombuffer(result.stdout, np.uint8)
                self._screen = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
                self._screen_color = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            else:
                with open(self.filename, "wb") as f:
                    f.write(result.stdout)
                self._screen = cv2.imread(self.filename, 0)
                self._screen_color = cv2.imread(self.filename, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"[{self.device_id}] Capture error: {e}")

    def _find_in_screen(self, template_path, similarity=0.8):
        """Find template in cached screen image (no new capture)"""
        if self._screen is None:
            return None
        tmpl = self._get_template(template_path)
        if tmpl is None:
            return None
        try:
            result = cv2.matchTemplate(self._screen, tmpl, cv2.TM_CCOEFF_NORMED)
            loc = np.where(result >= similarity)
            if len(loc[0]) > 0:
                y, x = loc[0][0], loc[1][0]
                h, w = tmpl.shape
                return (x + w // 2, y + h // 2)
        except:
            pass
        return None

    def find(self, template_path, similarity=0.8):
        """Capture + find"""
        self.capture_screen()
        return self._find_in_screen(template_path, similarity)

    def exists(self, template_path, similarity=0.8):
        return self.find(template_path, similarity) is not None

    def exists_in_cache(self, template_path, similarity=0.8):
        """Check if template exists in already-captured screen"""
        return self._find_in_screen(template_path, similarity) is not None

    def _get_similarity_score(self, template_path):
        """Get max similarity score for template in cached screen"""
        if self._screen is None:
            return 0.0
        tmpl = self._get_template(template_path)
        if tmpl is None:
            return 0.0
        try:
            result = cv2.matchTemplate(self._screen, tmpl, cv2.TM_CCOEFF_NORMED)
            return float(np.max(result))
        except:
            return 0.0

    def click(self, PSMRL, similarity=0.8):
        target = None
        if isinstance(PSMRL, str):
            if os.path.exists(PSMRL):
                target = self._find_in_screen(PSMRL, similarity)
                if target is None:
                    print(f"[{self.device_id}] Template not found: {PSMRL}")
        elif isinstance(PSMRL, tuple):
            target = PSMRL
            
        if target:
            x, y = target
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "input", "tap", str(x), str(y)])
            return True
        return False
    
    def tap(self, x, y):
        """Direct tap without image search"""
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "input", "tap", str(x), str(y)])

    def type_text(self, text):
        """Type text via ADB (for search box)"""
        escaped = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "input", "text", escaped])

    def swipe(self, x1, y1, x2, y2, duration=300):
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "input", "swipe", 
                     str(x1), str(y1), str(x2), str(y2), str(duration)])

    def check_error_images(self):
        """Check error images using cached screen"""
        error_images = ["img/fixbuglogin.png", "img/failed1.png"]
        for err in error_images:
            if self.exists_in_cache(err):
                return err
        return None

    # =========================================================
    # OCR Methods - For Gear Mode
    # =========================================================
    def ocr_read_region(self, x, y, w, h):
        """Read text from a specific region of the cached color screen using EasyOCR."""
        if self._screen_color is None or not self.do_gear:
            return []
        
        # Crop region from color image
        img = self._screen_color[y:y+h, x:x+w]
        
        if img is None or img.size == 0:
            print(f"[{self.device_id}] OCR crop region empty!")
            return []
        
        # Resize 2x for better OCR accuracy
        img = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        
        reader = get_ocr_reader()
        results = reader.readtext(img, detail=1)
        
        text_results = []
        for (bbox, text, conf) in results:
            if conf > 0.3:
                text_results.append((text, conf))
        
        return text_results

    def ocr_read_full_screen(self):
        """Read all text from the full cached color screen."""
        if self._screen_color is None or not self.do_gear:
            return ""
        
        region = self.ocr_region
        return self.ocr_read_region(region["x"], region["y"], region["w"], region["h"])

    def check_gear_by_text(self):
        """Check gear by reading text from screen and matching against config gear names."""
        if not self.do_gear:
            return set()
        
        print(f"[{self.device_id}] Reading screen text with OCR...")
        
        # Capture fresh screen
        self.capture_screen()
        
        # Read text from OCR region
        ocr_results = self.ocr_read_full_screen()
        
        if not ocr_results:
            print(f"[{self.device_id}] OCR returned no results")
            return set()
        
        # Combine all OCR text into one string (lowercase for matching)
        all_text = " ".join([text for text, conf in ocr_results]).lower()
        print(f"[{self.device_id}] OCR Text: {all_text}")
        
        # Match against gear names from config
        found_gears = set()
        for gear_key, gear_data in self.gear_names.items():
            # Support new format: {"ocr": "search text", "name": "custom name"}
            if isinstance(gear_data, dict):
                ocr_text = gear_data.get("ocr", gear_key)
                gear_name = gear_data.get("name", gear_key)
            else:
                ocr_text = gear_data
                gear_name = gear_data
            
            if ocr_text.lower() in all_text:
                found_gears.add(gear_name)
                print(f"[{self.device_id}] Found gear: {gear_name}")
        
        return found_gears

    # =========================================================
    # Logic Methods
    # =========================================================
    def clear_specific_shared_prefs(self):
        """Delete ALL shared_prefs and clear app cache"""
        base = "/data/data/com.linecorp.LGRGS/shared_prefs"
        cache_dir = "/data/data/com.linecorp.LGRGS/cache"
        
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(1)
        
        self.adb_shell(f"su -c 'rm -rf {base}/* && rm -rf {cache_dir}/*'")
        print(f"[{self.device_id}] Cleared shared_prefs + cache")

    def inject_file(self, local_xml_path):
        print(f"[{self.device_id}] Injecting file (Robust Mode)...")
        
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(2)
        
        self.adb_shell("su -c 'killall -9 com.linecorp.LGRGS 2>/dev/null || true'")
        sleep(1)

        src = os.path.abspath(local_xml_path)
        src_size = os.path.getsize(src)
        tmp = f"/data/local/tmp/temp_pref_{self.device_id.replace(':','_')}.xml"
        final_dir = "/data/data/com.linecorp.LGRGS/shared_prefs"
        final = f"{final_dir}/_LINE_COCOS_PREF_KEY.xml"
        
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                # Push to tmp
                result = self.adb_run([self.adb_cmd, "-s", self.device_id, "push", src, tmp], timeout=30)
                if result.returncode != 0:
                    print(f"[{self.device_id}] Push attempt {attempt}: {result.stderr.decode()}")
                    continue
                
                # Verify file size
                result = self.adb_shell(f"wc -c < {tmp}")
                try:
                    pushed_size = int(result.stdout.decode('utf-8', errors='ignore').strip())
                    if pushed_size != src_size:
                        print(f"[{self.device_id}] File size mismatch on attempt {attempt}: expected {src_size}, got {pushed_size}")
                        continue
                except Exception as e:
                    print(f"[{self.device_id}] Size check failed on attempt {attempt}: {e}")
                    continue
                
                # Copy and set permissions
                self.adb_shell(f"su -c 'cp {tmp} {final} && chmod 600 {final}'")
                self.adb_shell(f"su -c 'rm -f {tmp}'")
                
                print(f"[{self.device_id}] Injection successful on attempt {attempt}")
                return local_xml_path
                    
            except Exception as e:
                print(f"[{self.device_id}] Attempt {attempt} error: {e}")
        
        print(f"[{self.device_id}] Injection FAILED after {max_retries} attempts!")
        return None

    def first_loop_process(self):
        try:
            print(f"[{self.device_id}] Starting First Loop Process...")
            self.clear_specific_shared_prefs()
            sleep(3)
            
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
            sleep(1)
            self.adb_shell("input keyevent 3")
            sleep(2)
            
            print(f"[{self.device_id}] Processing SEQ 1...")
            if not self.process_sequence(self.seq1):
                print(f"[{self.device_id}] SEQ 1 failed")
                return "error"
            
            print(f"[{self.device_id}] Waiting 8s then Back...")
            sleep(8)
            self.adb_shell("input keyevent 4")
            sleep(2)
            
            print(f"[{self.device_id}] Processing SEQ 2...")
            if not self.process_sequence(self.seq2):
                print(f"[{self.device_id}] SEQ 2 failed")
                return "error"
            
            print(f"[{self.device_id}] First Loop Completed!")
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
            sleep(2)
            return "complete"
            
        except Exception as e:
            print(f"[{self.device_id}] First Loop Error: {e}")
            return "error"

    def process_sequence(self, sequence):
        for item in sequence:
            if isinstance(item, tuple):
                print(f"[{self.device_id}] Tapping: {item}")
                self.tap(item[0], item[1])
                sleep(0.5)
                continue
            
            if isinstance(item, str) and item.startswith('@'):
                checkpoint_img = item[1:]
                # Add img/ prefix if not already present
                if not checkpoint_img.startswith('img'):
                    checkpoint_img = f"img/{checkpoint_img}"
                print(f"[{self.device_id}] Checkpoint: waiting for {checkpoint_img} (no click)")
                wait_limit = 60
                start_wait = 0
                while start_wait < wait_limit:
                    self.capture_screen()
                    if self.exists_in_cache(checkpoint_img):
                        print(f"[{self.device_id}] Checkpoint reached: {checkpoint_img}")
                        break
                    start_wait += 1
                    sleep(1)
                if start_wait >= wait_limit:
                    print(f"[{self.device_id}] Checkpoint timeout: {checkpoint_img}")
                continue
                
            img = item
            
            # Add img/ prefix to image name if not already present
            if isinstance(img, str) and not img.startswith('img'):
                img_path = f"img/{img}"
            else:
                img_path = img
            
            if item == 'icon.png':
                print(f"[{self.device_id}] Waiting for app icon...")
                for _ in range(30):
                    self.capture_screen()
                    if self.exists_in_cache(img_path):
                        print(f"[{self.device_id}] Found app icon, clicking...")
                        self.click(img_path)
                        sleep(5)
                        break
                    sleep(1)
                continue

            print(f"[{self.device_id}] Waiting for {item}...")
            
            wait_limit = 60
            start_wait = 0
            found = False
            
            while start_wait < wait_limit:
                self.capture_screen()
                if self.exists_in_cache(img_path):
                    print(f"[{self.device_id}] Found {item}, clicking...")
                    self.click(img_path)
                    sleep(1)
                    found = True
                    break
                start_wait += 1
                sleep(1)
            
            if not found:
                print(f"[{self.device_id}] Timeout: {item}")
                print(f"[{self.device_id}] Sequence failed")
                return False
                 
        return True

    def wait_and_click_image(self, img_name, timeout=30):
        """Wait for image and click it, return True if found (timeout in seconds)"""
        # Add img/ prefix if not already present
        if not img_name.startswith('img'):
            img_path = f"img/{img_name}"
        else:
            img_path = img_name
        
        start = 0
        while start < timeout:
            try:
                self.capture_screen()
                if self.exists_in_cache(img_path):
                    print(f"[{self.device_id}] Found {img_name}! Clicking...")
                    self.click(img_path)
                    sleep(0.5)
                    return True
                start += 1
                sleep(1)
            except Exception as e:
                print(f"[{self.device_id}] Error while waiting for {img_name}: {e}")
                
        print(f"[{self.device_id}] Timeout waiting for {img_name} ({timeout}s)")
        return False

    # =========================================================
    # FIND RANGER PROCESS
    # =========================================================
    def process_find_ranger(self, current_file):
        """Process find-ranger sequence - Returns results dict instead of backing up"""
        if not self.do_ranger:
            return {}
        
        print(f"\n[{self.device_id}] === Starting FIND-RANGER Process ===\n")
        
        results = {}
        
        # Step 1 & 2: Navigation to search screen
        print(f"[{self.device_id}] Starting persistent navigation (Searching for sec1/sec2)...")
        sec1_clicked = False
        while True:
            self.capture_screen()
            
            # Check for crash/close while waiting
            if self.exists_in_cache("img/icon.png"):
                print(f"[{self.device_id}] App crashed, restarting...")
                self.click("img/icon.png")
                sleep(5)
                sec1_clicked = False # Reset flag on crash

            # Check if we are already at sec2
            if self.exists_in_cache("img/sec2.png"):
                print(f"[{self.device_id}] Reached search screen (sec2), clicking to confirm...")
                self.click("img/sec2.png")
                break
                
            # Try clicking sec1 only once
            if not sec1_clicked and self.exists_in_cache("img/sec1.png"):
                print(f"[{self.device_id}] Found sec1, clicking once then waiting for sec2...")
                self.click("img/sec1.png")
                sec1_clicked = True
                sleep(3) # Initial wait after click
            
            # If nothing found or already clicked sec1, just wait and loop again
            sleep(1.5)
            
        print(f"[{self.device_id}] Reached search screen successfully.")
        sleep(0.5)
        
        # Loop through each character
        for i, character in enumerate(self.characters):
            print(f"\n[{self.device_id}] --- Character {i+1}/{len(self.characters)}: {character} ---")
            
            # a) Tap search box position first
            print(f"[{self.device_id}] Tapping search box (388, 288)")
            self.tap(388, 288)
            sleep(0.3)
            
            # b) Type character name
            print(f"[{self.device_id}] Typing: {character}")
            self.type_text(character)
            sleep(0.5)
            
            # c) Click sec3
            print(f"[{self.device_id}] Clicking sec3.png")
            if not self.wait_and_click_image("sec3.png", timeout=15):
                print(f"[{self.device_id}] Failed to find sec3, skipping character")
                continue
            sleep(0.3)
            
            # d) Click sec4
            print(f"[{self.device_id}] Clicking sec4.png")
            if not self.wait_and_click_image("sec4.png", timeout=15):
                print(f"[{self.device_id}] Failed to find sec4, skipping character")
                continue
            sleep(0.3)
            
            # e) Scan ALL ranger images from img/ranger/ folder
            self.capture_screen()
            
            for ranger_img in self.ranger_files:
                ranger_path = f"img/{ranger_img}"
                if self.exists_in_cache(ranger_path, similarity=0.95):
                    # Get folder name from config
                    if isinstance(self.ranger_image_mapping, dict) and ranger_img in self.ranger_image_mapping:
                        data = self.ranger_image_mapping[ranger_img]
                        # Support both formats (dict with hero/folder keys OR just string)
                        if isinstance(data, dict):
                            hero_name = data.get("hero", ranger_img.split('/')[-1].replace(".png", ""))
                            folder_name = data.get("folder", hero_name)
                        else:
                            hero_name = ranger_img.split('/')[-1].replace(".png", "")
                            folder_name = str(data)
                    else:
                        hero_name = ranger_img.split('/')[-1].replace(".png", "")
                        folder_name = hero_name
                    
                    results[hero_name] = folder_name
                    print(f"[{self.device_id}] Found ranger: {ranger_img} -> hero: {hero_name}, folder: {folder_name}")
            
            if results:
                print(f"[{self.device_id}] Found results: {results}")
            else:
                print(f"[{self.device_id}] No rangers found yet")
            
            # f) Click sec5
            print(f"[{self.device_id}] Clicking sec5.png")
            if not self.wait_and_click_image("sec5.png", timeout=15):
                print(f"[{self.device_id}] Failed to find sec5, continuing")
            sleep(0.3)
            
            # g) Click sec2 again for next character (if not last)
            if i < len(self.characters) - 1:
                if not self.wait_and_click_image("sec2.png", timeout=15):
                    print(f"[{self.device_id}] Failed to find sec2 for next iteration")
                    break
        
        # Print final results
        print(f"\n[{self.device_id}] ========== FIND-RANGER RESULTS ==========")
        print(f"[{self.device_id}] File: {self.current_original_filename}")
        if results:
            for hero_name, folder_name in results.items():
                print(f"[{self.device_id}]   {hero_name} -> {folder_name}")
        else:
            print(f"[{self.device_id}]   No rangers found for any character")
        print(f"[{self.device_id}] ==========================================\n")
        
        # IMPORTANT: Return results instead of backing up
        # The backup will be done in main_login after combining with gear results
        print(f"[{self.device_id}] Find-Ranger complete - NOT clearing app, continuing to gear...")
        return results

    def backup_ranger_results(self, results):
        """Save backup based on find-ranger results"""
        filename = self.current_original_filename or "unknown.xml"
        source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
        
        self.adb_shell("su -c 'chmod 777 /data/data/com.linecorp.LGRGS/shared_prefs'")
        self.adb_shell(f"su -c 'chmod 777 {source_path}'")
        
        if results:
            # Build folder name from folder values
            folder_parts = sorted(set(results.values()))
            folder_name = "+".join(folder_parts)
            
            backup_dir = os.path.join("backup-id", folder_name)
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            
            dst = os.path.join(backup_dir, filename)
            result = subprocess.run(
                [self.adb_cmd, '-s', self.device_id, 'pull', source_path, dst],
                capture_output=True, text=True
            )
            
            if result.returncode == 0:
                print(f"[{self.device_id}] Backed up to: {dst}")
            else:
                print(f"[{self.device_id}] Backup failed: {result.stderr}")
        else:
            # No results -> not-found
            not_found_dir = "not-found"
            if not os.path.exists(not_found_dir):
                os.makedirs(not_found_dir)
            
            dst = os.path.join(not_found_dir, filename)
            result = subprocess.run(
                [self.adb_cmd, '-s', self.device_id, 'pull', source_path, dst],
                capture_output=True, text=True
            )
            
            if result.returncode == 0:
                print(f"[{self.device_id}] Backed up to not-found: {dst}")
            else:
                print(f"[{self.device_id}] Backup failed: {result.stderr}")

    # =========================================================
    # CHECK GEAR PROCESS
    # =========================================================
    def process_check_gear(self, current_file, ranger_results=None, skip_findgear1=False):
        """Process check-gear sequence
        
        Args:
            current_file: Current file being processed
            ranger_results: Dict of ranger results to combine with gear results
            skip_findgear1: If True, skip findgear1 and go directly to findgear2 (used when coming from ranger process)
        """
        if not self.do_gear:
            return {}
        
        print(f"\n[{self.device_id}] === Starting CHECK-GEAR Process ===\n")
        
        filename = self.current_original_filename or "unknown_LINE_COCOS_PREF_KEY.xml"
        source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
        
        # If skip_findgear1 is True, we're coming from ranger and should go directly to findgear2
        if skip_findgear1:
            print(f"[{self.device_id}] Skipping findgear1 (continuing from ranger process)...")
            sleep(1)
        else:
            # Normal flow: click findgear1.png first
            if not self.wait_and_click_image("findgear1.png"):
                print(f"[{self.device_id}] Failed to find findgear1.png")
                return set()
        
        # Click findgear2.png -> findgear3.png
        if not self.wait_and_click_image("findgear2.png"):
            print(f"[{self.device_id}] Failed to find findgear2.png")
            return set()
        
        if not self.wait_and_click_image("findgear3.png"):
            print(f"[{self.device_id}] Failed to find findgear3.png")
            return set()
        
        # Click checkgear2.png -> checkgear3.png
        if not self.wait_and_click_image("checkgear2.png"):
            print(f"[{self.device_id}] Failed to find checkgear2.png")
        
        if not self.wait_and_click_image("checkgear3.png"):
            print(f"[{self.device_id}] Failed to find checkgear3.png")
        
        # Step 2: Read gear names with OCR
        print(f"\n[{self.device_id}] Starting gear OCR check...")
        all_found_gears = set()
        
        # Round 1: Direct OCR check
        print(f"[{self.device_id}] Round 1: Direct OCR check")
        all_found_gears.update(self.check_gear_by_text())
        sleep(3)
        
        # Round 2: Check weapons tab 1
        self.capture_screen()
        if self.exists_in_cache("img/weapons1.png"):
            self.click("img/weapons1.png")
            sleep(1)
            all_found_gears.update(self.check_gear_by_text())
        
        # Round 3: Check weapons tab 2
        self.capture_screen()
        if self.exists_in_cache("img/weapons2.png"):
            self.click("img/weapons2.png")
            sleep(1)
            all_found_gears.update(self.check_gear_by_text())
        
        # Return gear results (will be combined with ranger results in main_login)
        print(f"\n[{self.device_id}] Gear results: {all_found_gears if all_found_gears else 'none'}")
        return all_found_gears

    def backup_to_not_found(self, filename, source_path):
        """Backup pref file to not-found folder"""
        not_found_dir = "not-found"
        if not os.path.exists(not_found_dir):
            os.makedirs(not_found_dir)
        
        backup_path = os.path.join(not_found_dir, filename)
        
        result = subprocess.run(
            [self.adb_cmd, '-s', self.device_id, 'pull', source_path, backup_path],
            capture_output=True, text=True
        )
        
        if result.returncode == 0:
            print(f"[{self.device_id}] Backed up to not-found: {backup_path}")
        else:
            print(f"[{self.device_id}] Backup failed: {result.stderr}")

    def clear_and_restart(self):
        """Clear app and prepare for next file"""
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(2)

    # =========================================================
    # Main Login
    # =========================================================
    def main_login(self, current_filename):
        print(f"[{self.device_id}] Starting Main Login...")
        
        # Clear app
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(2)
        
        # Click icon if found
        if self.exists("img/icon.png"):
            self.click("img/icon.png")
            sleep(5)
            
        loop_count = 0
        status = "unknown"
        
        while True:
            loop_count += 1
            if loop_count % 5 == 0:
                print(f"[{self.device_id}] Login loop iteration {loop_count}")

            self.capture_screen()

            # Crash/Icon Check
            if self.exists_in_cache("img/icon.png"):
                print(f"[{self.device_id}] App crashed during login. Restarting...")
                self.click("img/icon.png")
                sleep(5)
                loop_count = 0
                continue
            
            # fixalerterror1 Check
            if self.exists_in_cache("img/fixalerterror1.png"):
                print(f"[{self.device_id}] Alert error detected. Dimissing...")
                self.click("img/fixalerterror1.png")
                sleep(2)
                loop_count = 0
                continue
                
            # *** SUCCESS -> Run find-ranger or check-gear ***
            if self.exists_in_cache("img/stoplogin.png"):
                print(f"[{self.device_id}] Login successful! (stoplogin detected)")
                
                ranger_results = {}
                gear_results = set()
                
                # Run ranger process first if enabled
                if self.do_ranger:
                    print(f"[{self.device_id}] Running RANGER process...")
                    ranger_results = self.process_find_ranger(current_filename)
                    print(f"[{self.device_id}] Ranger results: {ranger_results if ranger_results else 'none'}")
                
                # Then run gear process if enabled
                if self.do_gear:
                    print(f"[{self.device_id}] Running GEAR process...")
                    # If both ranger and gear, skip findgear1 since we're already in the app
                    skip_gear1 = self.do_ranger and self.do_gear
                    gear_results = self.process_check_gear(current_filename, ranger_results, skip_findgear1=skip_gear1)
                    print(f"[{self.device_id}] Gear results: {gear_results if gear_results else 'none'}")
                
                # Combine results and backup
                filename = self.current_original_filename or "unknown.xml"
                source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
                
                # Create subfolder name from all found items
                all_names_list = []
                if ranger_results:
                    all_names_list.extend(ranger_results.values())
                if gear_results:
                    all_names_list.extend(gear_results)
                
                found_names = "+".join(sorted(set(all_names_list))) if all_names_list else "unknown"
                
                # Determine category folder name
                # 1. Gear + Ranger found -> "gear+ranger"
                # 2. Only Gear found -> "gear only"
                # 3. Only Ranger found -> "ranger", "ranger(2)", "ranger(3)", etc.
                has_ranger = len(ranger_results) > 0
                has_gear = len(gear_results) > 0
                
                category = "unknown"
                if has_gear and has_ranger:
                    category = "gear+ranger"
                elif has_gear:
                    category = "gear only"
                elif has_ranger:
                    count = len(ranger_results)
                    category = "ranger" if count == 1 else f"ranger({count})"
                
                if category != "unknown":
                    print(f"[{self.device_id}] Success category: {category} -> names: {found_names}")
                    
                    # chmod for pull
                    self.adb_shell("su -c 'chmod 777 /data/data/com.linecorp.LGRGS/shared_prefs'")
                    self.adb_shell(f"su -c 'chmod 777 {source_path}'")
                    
                    # Create backup folder structure: backup-id/category/found_names
                    backup_dir = os.path.join("backup-id", category, found_names)
                    if not os.path.exists(backup_dir):
                        os.makedirs(backup_dir)
                    
                    # Pull file
                    dst = os.path.join(backup_dir, filename)
                    result = subprocess.run(
                        [self.adb_cmd, '-s', self.device_id, 'pull', source_path, dst],
                        capture_output=True, text=True
                    )
                    
                    if result.returncode == 0:
                        print(f"[{self.device_id}] ✓ Backed up to: {dst}")
                    else:
                        print(f"[{self.device_id}] ✗ Backup failed: {result.stderr}")
                else:
                    # No results from either ranger or gear -> backup to not-found
                    print(f"[{self.device_id}] No results from ranger or gear - backing up to not-found")
                    self.adb_shell("su -c 'chmod 777 /data/data/com.linecorp.LGRGS/shared_prefs'")
                    self.adb_shell(f"su -c 'chmod 777 {source_path}'")
                    self.backup_to_not_found(filename, source_path)
                
                # Clear app and restart
                self.clear_and_restart()
                return "success"
                
            # Failed
            if self.exists_in_cache("img/login-failed.png"):
                print(f"[{self.device_id}] Login failed (login-failed detected)")
                status = "failed"
                return status
                
            # Error/Reset
            error_found = self.check_error_images()
            
            if error_found:
                print(f"[{self.device_id}] Error image found: {error_found}. Resetting...")
                self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
                sleep(3)
                if self.exists("img/icon.png"):
                    self.click("img/icon.png")
                    sleep(5)
                loop_count = 0
                continue
            
            # Event / Popups
            if self.exists_in_cache("img/event.png"):
                print(f"[{self.device_id}] Event popup detected. Clicking then Back...")
                self.click("img/event.png")
                sleep(1)
                self.adb_shell("input keyevent 4")  # Back button
                sleep(2)
                loop_count -= 1
                continue

            if self.exists_in_cache("img/cancel.png"):
                print(f"[{self.device_id}] Cancel button detected (Exit prompt?). Clicking...")
                self.click("img/cancel.png")
                sleep(1)
                continue
            
            sleep(2)
            if loop_count > 500:
                print(f"[{self.device_id}] Login timeout after 500 iterations")
                status = "timeout"
                return status
        
        return status


if __name__ == "__main__":
    print("=== Auto Ranger+Gear Script (Combined Mode) ===")
    
    load_config()
    
    if not find_adb_executable():
        print("ADB Not Found.")
        sys.exit(1)
    
    # Reset ADB
    print("[INFO] Restarting ADB Server...")
    subprocess.run([adb_path, "kill-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run([adb_path, "start-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
    connect_known_ports()
    devices = get_connected_devices()
    print(f"[DEV] All detected: {devices}")
    
    if not devices:
        print("No devices.")
        sys.exit(0)
    
    # Use only the first device
    devices = [devices[0]]
    print(f"[DEV] Using: {devices[0]}")
        
    # Check mode
    find_ranger = config.get("find_ranger", 0)
    find_gear = config.get("find_gear", 0)
    find_all = config.get("find_all", 1)
    
    print(f"\n[MODE] find_ranger={find_ranger}, find_gear={find_gear}, find_all={find_all}")
    if find_all:
        print("[MODE] Using FIND ALL mode (both Ranger and Gear)")
    elif find_ranger:
        print("[MODE] Using RANGER only mode")
    elif find_gear:
        print("[MODE] Using GEAR only mode")
    else:
        print("[MODE] No mode selected!")
    
    # Prepare OCR if gear mode enabled
    if find_gear or find_all:
        print("[INFO] Pre-loading OCR model...")
        try:
            get_ocr_reader()
            print("[OK] OCR model loaded.")
        except Exception as e:
            print(f"[WARN] Failed to load OCR: {e}")
            print("[WARN] OCR will be retried when needed.")
    
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
    
    # Print configuration
    if find_ranger or find_all:
        chars_to_show = config.get("characters", [])
        print(f"\n[CONFIG] Ranger mode - Characters ({len(chars_to_show)}):")
        for c in chars_to_show:
            print(f"  - {c}")
        
        ranger_folder = os.path.join("img", "ranger")
        ranger_files = []
        if os.path.exists(ranger_folder):
            ranger_files = sorted([f for f in os.listdir(ranger_folder) if f.lower().endswith(".png")])
        print(f"[CONFIG] Ranger images in img/ranger/ ({len(ranger_files)}):")
        for f in ranger_files:
            print(f"  - {f}")
    
    if find_gear or find_all:
        gear_names = config.get("gearname", {})
        print(f"\n[CONFIG] Gear mode - Gears to check ({len(gear_names)}):")
        for k, v in gear_names.items():
            if isinstance(v, dict):
                print(f"  - {k}: {v.get('name', v.get('ocr', k))}")
            else:
                print(f"  - {k}: {v}")
    
    print()
        
    # Start Threads
    threads = []
    print(f"[INFO] Starting {len(devices)} threads...")
    
    delay = config.get("thread_delay", 5)
    for i, dev in enumerate(devices):
        t = RangerGearBot(dev, file_queue)
        t.start()
        threads.append(t)
        if i < len(devices) - 1:
            print(f"[INFO] Waiting {delay}s before starting next thread...")
            sleep(delay)
        
    # Wait for threads
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n[STOP] Keyboard Interrupt. Stopping...")
        
    print("\n[DONE] All tasks completed.")
