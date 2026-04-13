from ppadb.client import Client as AdbClient
import cv2
import numpy as np
import time
from threading import Thread, Lock, Semaphore
import os
import subprocess
from queue import Queue
import gc
import psutil
import concurrent.futures
import socket
import re
import shutil
import ctypes
from ctypes import wintypes
from typing import List
import getpass
from datetime import datetime
import colorama
from colorama import Fore, Style
import json
import pyperclip
import sys
import io
import argparse

# Fix encoding issue for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception: pass

# Initialize colorama
colorama.init(autoreset=True)

adb_path = "adb"

# ----- Global Settings & Constants -----
# All images should be located in the "img/" folder relative to this script.
REQUIRED_IMAGES = [
    'img/stoplogin.png', 'img/pull3.png', 'img/pull4.png', 'img/pull5.png',
    'img/apple.png', 'img/test.png', 'img/fixcak.png', 'img/save.png',
    'img/stopcheck.png', 'img/check.png', 'img/ok.png', 'img/refresh.png',
    'img/link1.png', 'img/event.png', 'img/cancel.png', 'img/icon.png',
    'img/closeapp.png', 'img/fixbuglogin.png', 'img/alert1.png', 'img/fixid.png',
    'img/kaiby.png', 'img/fixnetv3.png', 'img/fixnet.png', 'img/fixid1.png',
    'img/checkline.png', 'img/check-l1.png', 'img/check-l4.png', 'img/check-ok1.png'
]

# ----- UI Stats Class -----
class SimpleUIStats:
    def __init__(self):
        self.total_files = 0
        self.successful_logins = 0
        self.failed_logins = 0
        self.processed_files = 0
        self.connected_devices = 0
        self.lock = Lock()
        self.last_update = time.time()
        self.update_interval = 30
        self.total_login_time = 0.0
        self.login_time_count = 0
        
    def record_login_time(self, duration_sec):
        with self.lock:
            self.total_login_time += duration_sec
            self.login_time_count += 1
        
    def should_update(self):
        return time.time() - self.last_update >= self.update_interval
        
    def force_update(self):
        self.last_update = 0
        
    def update(self, total=None, processed=None, success=None, fail=None, devices=None):
        with self.lock:
            if total is not None: self.total_files = total
            if processed is not None: self.processed_files = processed
            if success is not None: self.successful_logins = success
            if fail is not None: self.failed_logins = fail
            if devices is not None: self.connected_devices = devices
            
            if self.should_update():
                self.draw()
                self.last_update = time.time()

    def get_progress_percent(self):
        if self.total_files == 0: 
            return 0
        return int(100 * self.processed_files / self.total_files)

    def draw(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        
        print(f"{Fore.CYAN}╔{'═' * 70}╗{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║{' ' * 21}🚀 LINE RANGER UID LOGIN TOOL 🚀{' ' * 19}║{Style.RESET_ALL}")
        print(f"{Fore.CYAN}╠{'═' * 70}╣{Style.RESET_ALL}")
        
        progress_pct = self.get_progress_percent()
        progress_bar = self._create_progress_bar(progress_pct)
        
        total_files = f"{self.total_files:,}"
        processed_files = f"{self.processed_files:,}"
        successful_logins = f"{self.successful_logins:,}"
        failed_logins = f"{self.failed_logins:,}"
        
        print(f"║ Files: {total_files:<15} Processed: {processed_files:<15}║")
        print(f"║ Success: {Fore.GREEN}{successful_logins:<10}{Style.RESET_ALL} Failed: {Fore.RED}{failed_logins:<10}{Style.RESET_ALL}    ║")
        print(f"║ Devices: {self.connected_devices:<6} Progress: {progress_pct:>3}%{' ' * 28}║")
        print(f"║ {progress_bar} ║")
        print(f"║ Last Update: {datetime.now().strftime('%H:%M:%S'):<12}{' ' * 42}║")
        print(f"{Fore.CYAN}╚{'═' * 70}╝{Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}Status: Running... (Updates every 30s){Style.RESET_ALL}")
        print(f"{Fore.WHITE}Press Ctrl+C to return to menu{Style.RESET_ALL}")
    
    def _create_progress_bar(self, percent, length=30):
        filled = int(length * percent / 100)
        color = Fore.GREEN if percent >= 80 else (Fore.YELLOW if percent >= 40 else Fore.RED)
        bar = f"{color}{'█' * filled}{Fore.WHITE}{'░' * (length - filled)}{Style.RESET_ALL}"
        return bar

    def print_simple_message(self, message):
        current_time = datetime.now().strftime('%H:%M:%S')
        print(f"{Fore.WHITE}[{current_time}] {message}{Style.RESET_ALL}")

# ----- Device State Management -----
class DeviceState:
    def __init__(self):
        self.lock = Lock()
        self.file_queue = Queue()
        self.processed_files = set()
        self.original_filenames = {}
        self.clipboard_lock = Lock()
        self.clipboard_processing = set()

ui_stats = SimpleUIStats()
device_state = DeviceState()
adb_push_semaphore = Semaphore(2)

# ----- Utility Functions -----

def read_config():
    try:
        if os.path.exists("config.json"):
            with open("config.json", 'r') as f:
                return json.load(f)
        return {"loop1": 1}
    except Exception: return {"loop1": 1}

def clean_memory():
    gc.collect()

def get_resource_usage():
    process = psutil.Process()
    return process.cpu_percent(), process.memory_info().rss / 1024 / 1024

def get_backup_folder():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(current_dir, "backup")
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path

source_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup")
if not os.path.exists(source_folder): os.makedirs(source_folder, exist_ok=True)

def has_xml_files():
    try:
        xml_files = [f for f in os.listdir(source_folder) if f.endswith('.xml')]
        return len(xml_files) > 0
    except OSError: return False

def update_file_queue():
    try:
        xml_files = []
        for root, dirs, files in os.walk(source_folder):
            xml_files.extend([f for f in files if f.endswith('.xml')])
        
        ui_stats.update(total=len(xml_files))
        
        with device_state.lock:
            for xml_file in xml_files:
                if xml_file not in device_state.processed_files:
                    device_state.file_queue.put(xml_file)
        return len(xml_files)
    except Exception as e:
        print(f"{Fore.RED}Error updating file queue: {str(e)}{Style.RESET_ALL}")
        return 0

def safe_clipboard_operation(device, callback):
    """
    Safely handles the shared system clipboard for multi-process UID extraction.
    ใช้ Windows Global Mutex เพื่อล้อคข้ามหน้าต่าง CMD (Cross-process synchronization)
    """
    # Create or open a Global Mutex
    # 'Global\\' prefix makes it visible across all user sessions if needed, 
    # but for MuMu usually 'LGR_Clipboard_Lock' is enough.
    mutex_name = "Global\\LGR_Clipboard_Lock"
    kernel32 = ctypes.windll.kernel32
    
    # Try to wait for the mutex
    print(f"[{device.serial}] [CLIPBOARD] Waiting for Global Mutex (Cross-CMD Lock)...")
    
    # CreateMutex will return an existing one if it already exists
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    if not mutex:
        print(f"[{device.serial}] [CLIPBOARD] Error creating mutex")
        return None

    # Wait for ownership (Infinite timeout is risky, but we need the UID)
    # WAIT_OBJECT_0 is 0
    wait_res = kernel32.WaitForSingleObject(mutex, 60000) # Wait up to 60s
    
    if wait_res == 0 or wait_res == 0x80: # WAIT_OBJECT_0 or WAIT_ABANDONED
        try:
            print(f"[{device.serial}] [CLIPBOARD] Global Mutex Acquired.")
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    pyperclip.copy("")
                    result = callback()
                    if result:
                        result = result.strip()
                        if len(result) > 5:
                            # Note: clipboard_processing check here only works within ONE process.
                            # For cross-process dup check, we'd need a shared file/DB.
                            # But with Global Mutex, collision is already prevented.
                            print(f"[{device.serial}] [CLIPBOARD] Successfully captured: {result}")
                            return result
                    
                    print(f"[{device.serial}] [CLIPBOARD] Attempt {attempt+1} empty. Retrying...")
                    time.sleep(2)
                except Exception as e:
                    print(f"[{device.serial}] Clipboard Error: {e}")
                    time.sleep(1)
        finally:
            # Release the mutex and CloseHandle
            kernel32.ReleaseMutex(mutex)
            kernel32.CloseHandle(mutex)
            print(f"[{device.serial}] [CLIPBOARD] Global Mutex Released.")
    else:
        kernel32.CloseHandle(mutex)
        print(f"[{device.serial}] [CLIPBOARD] Timeout waiting for Global Mutex. Mixing possible!")
    
    return None

def release_clipboard_uid(uid):
    with device_state.clipboard_lock:
        if uid in device_state.clipboard_processing:
            device_state.clipboard_processing.remove(uid)

def enable_root(device):
    try:
        subprocess.run([adb_path, "-s", device.serial, "root"], capture_output=True, text=True)
    except Exception: pass

def clear_app(device):
    try:
        device.shell("am force-stop com.linecorp.LGRGS")
        time.sleep(1)
        print(f"{Fore.GREEN}[DEVICE {device.serial}] App cleared successfully{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[DEVICE {device.serial}] Error clearing app: {str(e)}{Style.RESET_ALL}")

def open_app(device):
    try:
        device.shell("monkey -p com.linecorp.LGRGS 1")
        print(f"{Fore.GREEN}[DEVICE {device.serial}] Opening app...{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[DEVICE {device.serial}] Error opening app: {str(e)}{Style.RESET_ALL}")

def ImgSearchADB(adb_img, find_img_path, threshold=0.95):
    try:
        find_img = cv2.imread(find_img_path, cv2.IMREAD_COLOR)
        if find_img is None or adb_img is None: return []
            
        result = cv2.matchTemplate(adb_img, find_img, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)
        locations = list(zip(*locations[::-1]))
        
        if not locations: return []
        
        rectangles = []
        needle_w, needle_h = find_img.shape[1], find_img.shape[0]
        for loc in locations:
            rectangles.append([int(loc[0]), int(loc[1]), needle_w, needle_h])
            rectangles.append([int(loc[0]), int(loc[1]), needle_w, needle_h])
            
        rectangles, _ = cv2.groupRectangles(rectangles, 1, 0.2)
        return [(x + w // 2, y + h // 2) for (x, y, w, h) in rectangles]
    except Exception: return []
def check_floating_popups(device, adb_img):
    """Check and handle common floating popups like checkline, fixnetv2, fixplay."""
    # 1. checkline.png: Handle Checkbox Popup Sequence
    if ImgSearchADB(adb_img, "img/checkline.png"):
        print(f"[{device.serial}] [POPUP] checkline.png detected! Running sequence...")
        pos = ImgSearchADB(adb_img, "img/checkline.png")
        device.shell(f"input tap {pos[0][0]} {pos[0][1]}")
        time.sleep(2)
        
        # Wait for check-l1.png
        start_l1 = time.time()
        while time.time() - start_l1 < 60:
            cap = device.screencap(); cur_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
            if ImgSearchADB(cur_img, "img/check-l1.png"):
                print(f"[{device.serial}] [POPUP] Found check-l1.png")
                break
            time.sleep(1)
            
        # Coordinates for checkboxes
        print(f"[{device.serial}] [POPUP] Clicking checkline coordinates...")
        device.shell("input tap 932 133"); time.sleep(5)
        device.shell("input tap 930 253"); time.sleep(5)
        device.shell("input tap 926 327"); time.sleep(5)
        
        # Wait for check-l4.png
        start_l4 = time.time()
        while time.time() - start_l4 < 60:
            cap = device.screencap(); cur_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
            pos = ImgSearchADB(cur_img, "img/check-l4.png")
            if pos:
                print(f"[{device.serial}] [POPUP] Found and clicking check-l4.png")
                device.shell(f"input tap {pos[0][0]} {pos[0][1]}")
                break
            time.sleep(1)
            
        # End with check-ok1.png
        for _ in range(60):
            cap = device.screencap(); cur_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
            pos = ImgSearchADB(cur_img, "img/check-ok1.png")
            if pos:
                device.shell(f"input tap {pos[0][0]} {pos[0][1]} ")
                print(f"[{device.serial}] [POPUP] Checkline sequence complete!")
                time.sleep(1)
                break
            time.sleep(1)
        return True

    # 2. fixnet (recurring)
    pos = ImgSearchADB(adb_img, "img/fixnet.png", threshold=0.8) or ImgSearchADB(adb_img, "img/fixnet1.png", threshold=0.8)
    if pos:
        print(f"[{device.serial}] [POPUP] fixnet detected, clicking...")
        device.shell(f"input tap {pos[0][0]} {pos[0][1]} ")
        time.sleep(1)
        return True

    return False

def check_black_screen(adb_img, threshold=0.8):
    try:
        if adb_img is None: return False
        gray = cv2.cvtColor(adb_img, cv2.COLOR_BGR2GRAY)
        return np.mean(gray) < (255 * threshold / 100)
    except Exception: return False

def check_critical_errors(device, adb_img, context=""):
    """
    Robust error checker migrated from login.py.
    Returns: 'restart', 'continue', 'kaiby', 'failed', or None
    """
    try:
        # 1. App Closed/Crashed (See phone icon on home screen)
        if ImgSearchADB(adb_img, 'img/icon.png', threshold=0.9):
            print(f"[{device.serial}] 🖥️ App closed/crashed! Found icon.png in {context}")
            return "restart"

        # 2. Bot Block (Kaiby)
        if ImgSearchADB(adb_img, 'img/kaiby.png', threshold=0.8):
            print(f"[{device.serial}] ⚠️ KAIBY detected! Account blocked.")
            return "kaiby"

        # 3. Critical Fix Screens (fixid, fixid1, fixcak, fixbug)
        if ImgSearchADB(adb_img, 'img/fixid1.png', threshold=0.95):
            print(f"[{device.serial}] ❌ Found fixid1.png (Critical Failure)")
            return "failed"
            
        for err_img in ['fixcak.png', 'fixbuglogin.png', 'fixunkown.png']:
            if ImgSearchADB(adb_img, f'img/{err_img}'):
                print(f"[{device.serial}] ⚠️ Found {err_img} in {context}!")
                return "restart"

        # 4. Network Issues
        for net_img in ['fixnet.png', 'fixnet1.png', 'fixnetv3.png']:
            pos = ImgSearchADB(adb_img, f'img/{net_img}')
            if pos:
                print(f"[{device.serial}] 📶 Network popup ({net_img}) - Tapping OK...")
                # Global coordinate for common OK buttons or the detected position
                if net_img == 'fixnetv3.png': device.shell("input tap 472 361")
                else: device.shell(f"input tap {pos[0][0]} {pos[0][1]}")
                time.sleep(1)
                return "continue"
        
        return None
    except Exception as e:
        print(f"[ERROR] check_critical_errors: {e}")
        return None

# ----- Core Logic -----

def save_fail(device):
    """Pull the failure ID for manual inspection."""
    try:
        fail_dir = os.path.join(os.getcwd(), "login-fail")
        os.makedirs(fail_dir, exist_ok=True)
        
        # ใช้ su -c ก้อปปี้ไปที่ tmp ก่อนกดยกออกมา (เลี่ยง Permission Denied)
        tmp_pull = f"/data/local/tmp/dump_{device.serial.replace(':','_')}.xml"
        device.shell(f"su -c 'cp /data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml {tmp_pull} && chmod 666 {tmp_pull}'")
        
        cmd = f'{adb_path} -s {device.serial} pull "{tmp_pull}" "{dst_path}"'
        res = subprocess.run(cmd, shell=True, capture_output=True, timeout=15)
        
        # ล้างไฟล์ชั่วคราวบนเครื่อง
        device.shell(f"su -c 'rm {tmp_pull}'")
        
        if res.returncode == 0 and os.path.exists(dst_path):
            ui_stats.update(fail=ui_stats.failed_logins + 1)
            return True
    except Exception: pass
    return False


def inject_file(device, orig_path):
    """Robust injection from login.py"""
    print(f"[{device.serial}] Injecting file: {os.path.basename(orig_path)} (Robust Mode)...")
    
    # Unlock Read-only (Mumu/Android fix)
    device.shell("su -c 'mount -o remount,rw / 2>/dev/null || mount -o remount,rw /data 2>/dev/null'")
    
    clear_app(device)
    time.sleep(1)
    
    src = os.path.abspath(orig_path)
    safe_ser = str(device.serial).replace(':', '_').replace('.', '_')
    tmp_remote = f"/data/local/tmp/temp_pref_{safe_ser}.xml"
    final_dir = "/data/data/com.linecorp.LGRGS/shared_prefs"
    final = f"{final_dir}/_LINE_COCOS_PREF_KEY.xml"
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            # Push to tmp
            with adb_push_semaphore:
                result = subprocess.run([adb_path, "-s", device.serial, "push", src, tmp_remote], capture_output=True)
            
            if result.returncode != 0:
                print(f"[{device.serial}] Push attempt {attempt} failed: {result.stderr.decode('utf-8', errors='ignore')}")
                time.sleep(2)
                continue
            
            # Copy, set permissions and owner
            shell_cmd = (
                f"su -c '"
                f"mkdir -p {final_dir} && "
                f"cp {tmp_remote} {final} && "
                f"chmod 666 {final} && "
                f"chown $(stat -c %u:%g {final_dir} 2>/dev/null || stat -c %u:%g {final_dir}/.. 2>/dev/null || echo 1000:1000) {final} || true && "
                f"rm -f {tmp_remote}"
                f"'"
            )
            device.shell(shell_cmd)
            
            print(f"[{device.serial}] Injection successful on attempt {attempt}")
            return True
                
        except Exception as e:
            print(f"[{device.serial}] Attempt {attempt} error: {e}")
            time.sleep(2)
    
    print(f"[{device.serial}] Injection FAILED after {max_retries} attempts!")
    return False

# =========================================================
# File Handling (Migrated from login.py)
# =========================================================

def handle_success(file_path, device_serial):
    """Handle successful UID extraction - move file to success folder"""
    dst_dir = "login-success"
    if not os.path.exists(dst_dir): os.makedirs(dst_dir)
    base = os.path.basename(file_path)
    dst = os.path.join(dst_dir, base)
    try:
        shutil.move(file_path, dst)
        print(f"[{device_serial}] Moved success file to {dst_dir}/")
    except Exception as e:
        print(f"[{device_serial}] Move success error: {e}")

def handle_failure(file_path, device_serial):
    """Handle login failure - save remote file for debug and move local to failed folder"""
    dst_dir = "login-failed"
    if not os.path.exists(dst_dir): os.makedirs(dst_dir)
    base = os.path.basename(file_path)
    dst = os.path.join(dst_dir, base)
    
    print(f"[{device_serial}] Login FAILED. Saving fail session...")
    
    src_remote = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
    try:
        # Try to pull the remote state for debugging before moving original
        subprocess.run(f'{adb_path} -s {device_serial} pull {src_remote} "{dst}.remote.xml"', shell=True, capture_output=True)
        if os.path.exists(file_path): 
            shutil.move(file_path, dst)
    except Exception as e:
        print(f"[{device_serial}] Fail handler error: {e}")
        try:
            if os.path.exists(file_path): shutil.move(file_path, dst)
        except: pass

def handle_kaiby(file_path, device_serial):
    """Handle Kaiby detection (bot block)"""
    dst_dir = "kaiby"
    if not os.path.exists(dst_dir): os.makedirs(dst_dir)
    base = os.path.basename(file_path)
    dst = os.path.join(dst_dir, base)
    print(f"[{device_serial}] KAIBY detected. Moving file to {dst_dir}/")
    try:
        if os.path.exists(file_path): shutil.move(file_path, dst)
    except: pass

def main_login(device, current_filename="unknown.xml"):
    """Robust main login logic transformed from the provided class-based version."""
    uid_folder = "uid-check"
    os.makedirs(uid_folder, exist_ok=True)
    cfg = read_config()
    
    print(f"[{device.serial}] Starting Main Login (Robust Transformed Mode)...")
    _login_fixid_count = 0
    
    # เราจะไม่สั่ง clear_app ซ้ำซ้อนที่นี่ เพราะเรียกจาก process_single_device มาแล้ว
    # แค่เช็คเพื่อให้แน่ใจว่าแอปเปิดอยู่จริงๆ
    # check_pid...
    try:
        pid = device.shell("pidof com.linecorp.LGRGS")
        if not pid.strip():
            open_app(device)
            time.sleep(5)
    except: pass
    
    # === Black Screen Check หลังเปิดแอพ ===
    for black_attempt in range(3):
        black_start = time.time()
        is_stuck = False
        while time.time() - black_start < 8:
            cap = device.screencap()
            adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
            if adb_img is not None:
                try:
                    gray = cv2.cvtColor(adb_img, cv2.COLOR_BGR2GRAY)
                    _, thresh = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY_INV)
                    num_black = cv2.countNonZero(thresh)
                    total = gray.shape[0] * gray.shape[1]
                    black_ratio = num_black / total
                    if black_ratio < 0.85:
                        print(f"[{device.serial}] [BLACK] Screen OK! (app loaded)")
                        is_stuck = False
                        break
                    else: is_stuck = True
                except: is_stuck = True
            else: is_stuck = True
            time.sleep(1)
        
        if is_stuck:
            print(f"[{device.serial}] [BLACK] Dark screen 8s after launch! (attempt {black_attempt+1}/3) Clearing...")
            clear_app(device)
            open_app(device)
            time.sleep(3)
        else: break

    loop_count = 0
    event_passed = False
    _fixokk_start_time = None
    _alert2_start_time = None
    no_img_timeout = 400
    no_img_timer = time.time()

    while True:
        try:
            loop_count += 1
            if loop_count % 15 == 0:
                print(f"[{device.serial}] Login loop iteration {loop_count}")

            cap = device.screencap()
            adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
            
            # --- CRASH CHECK ---
            if loop_count % 15 == 0:
                try:
                    pid = device.shell("pidof com.linecorp.LGRGS")
                    if not pid.strip():
                        print(f"[{device.serial}] [CRASH] App PID missing! Relaunching...")
                        open_app(device); time.sleep(5); continue
                except: pass

            # --- FLOATING POPUPS & ERRORS ---
            check_floating_popups(device, adb_img)
            
            err_status = check_critical_errors(device, adb_img, "Main Loop")
            if err_status == "restart": return "restart"
            if err_status == "continue": continue
            if err_status == "kaiby": return "kaiby"
            if err_status == "failed": return "failed"

            # fixnetv3.png Check
            if ImgSearchADB(adb_img, 'img/fixnetv3.png', threshold=0.8):
                print(f"[{device.serial}] [POPUP] fixnetv3.png detected! Tapping (472, 361)...")
                device.shell("input tap 472 361"); time.sleep(0.5); continue

            # fixokk.png Persistence Check (หา cancel ก่อนเสมอ)
            if ImgSearchADB(adb_img, 'img/fixokk.png', threshold=0.8):
                # 1. ลองหา cancel.png ก่อนเลย ไม่ต้องรอ
                pos_cancel = ImgSearchADB(adb_img, 'img/cancel.png', threshold=0.8)
                if pos_cancel:
                    print(f"[{device.serial}] Found cancel.png with fixokk, clicking cancel immediately!")
                    device.shell(f"input tap {pos_cancel[0][0]} {pos_cancel[0][1]}")
                    _fixokk_start_time = None # Reset timer
                    time.sleep(2)
                    continue # เริ่มลูปใหม่เพื่อจับภาพใหม่
                
                # 2. ถ้าไม่เจอ cancel ให้เริ่ม/รอนับเวลา 5 วิ เพื่อกด fixokk
                if _fixokk_start_time is None:
                    _fixokk_start_time = time.time()
                    print(f"[{device.serial}] Detected fixokk.png... waiting 5s (No cancel found)")
                elif time.time() - _fixokk_start_time >= 5:
                    print(f"[{device.serial}] ⚠️ fixokk.png stuck for 5s (Still no cancel)! Tapping OK...")
                    pos_ok = ImgSearchADB(adb_img, 'img/fixokk.png', threshold=0.8)
                    if pos_ok:
                        device.shell(f"input tap {pos_ok[0][0]} {pos_ok[0][1]}")
                    _fixokk_start_time = None
                    time.sleep(2)
            else:
                _fixokk_start_time = None

            # alert2.png Persistence Check (รอค้างครบ 8 วิ ให้ clear app แล้วเปิดใหม่)
            # ปรับ similarity เป็น 0.9 เพื่อป้องกันการจำผิดตอนจอกำลังโหลด
            if ImgSearchADB(adb_img, 'img/alert2.png', threshold=0.9):
                if _alert2_start_time is None:
                    _alert2_start_time = time.time(); print(f"[{device.serial}] Detected alert2.png (Network/Update)... waiting 8s")
                elif time.time() - _alert2_start_time >= 8:
                    print(f"[{device.serial}] alert2.png stuck for 8s! Restarting app...")
                    clear_app(device); open_app(device); _alert2_start_time = None; time.sleep(3); continue
            else: _alert2_start_time = None

            # fixalerterror1.png
            if ImgSearchADB(adb_img, 'img/fixalerterror1.png'):
                print(f"[{device.serial}] Alert error detected. Dismissing...")
                pos = ImgSearchADB(adb_img, 'img/fixalerterror1.png')
                device.shell(f"input tap {pos[0][0]} {pos[0][1]}"); time.sleep(2); continue

            # kaiby check
            if ImgSearchADB(adb_img, 'img/kaiby.png', threshold=0.8) or ImgSearchADB(adb_img, 'img/kaiby1.png', threshold=0.8):
                print(f"[{device.serial}] ⚠️ พบ kaiby.png! (ไก่บี้เด้งระหว่าง Login)")
                clear_app(device); return "kaiby"

            # --- Success -> UID EXTRACTION & DIST ---
            if ImgSearchADB(adb_img, 'img/stoplogin.png', threshold=0.8):
                print(f"[{device.serial}] SUCCESS (stoplogin detected). Checking DIST...")
                
                # Check for DIST sequence
                found_distcheck = False
                found_distskip_early = False
                for _ in range(5):
                    cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if ImgSearchADB(adb_img, 'img/distcheck.png'): found_distcheck = True; break
                    if ImgSearchADB(adb_img, 'img/distskip.png'): found_distskip_early = True; break
                    time.sleep(1)
                
                if found_distskip_early:
                    print(f"[{device.serial}] [DIST] distskip.png found early! Handling sequence...")
                    pos = ImgSearchADB(adb_img, 'img/distskip.png')
                    device.shell(f"input tap {pos[0][0]} {pos[0][1]}"); time.sleep(1)
                    while True:
                        cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                        pos = ImgSearchADB(adb_img, 'img/stagespecal.png')
                        if pos: device.shell(f"input tap {pos[0][0]} {pos[0][1]} "); time.sleep(1); break
                        time.sleep(1)
                    while True:
                        cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                        pos = ImgSearchADB(adb_img, 'img/backdist.png') or ImgSearchADB(adb_img, 'img/backdist1.png')
                        if pos: device.shell(f"input tap {pos[0][0]} {pos[0][1]} "); time.sleep(1.2)
                        else: break

                elif found_distcheck:
                    print(f"[{device.serial}] [DIST] distcheck.png found! Entering full sequence...")
                    # 1. dist1
                    dist1_start = time.time()
                    while True:
                        if time.time() - dist1_start > 120: break
                        cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                        pos = ImgSearchADB(adb_img, 'img/dist1.png', threshold=0.8)
                        if pos: device.shell(f"input tap {pos[0][0]} {pos[0][1]} "); break
                        time.sleep(1)
                    # 2. waitdist
                    dist_pos = None; dist_wait_start = time.time()
                    while dist_pos is None:
                        if time.time() - dist_wait_start > 120: break
                        cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                        res = ImgSearchADB(adb_img, 'img/waitdist.png', threshold=0.8)
                        if res: dist_pos = res[0]
                        time.sleep(1)
                    # 3. dist2
                    if dist_pos:
                        dist2_start = time.time()
                        while True:
                            if time.time() - dist2_start > 120: break
                            cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                            pos = ImgSearchADB(adb_img, 'img/dist2.png', threshold=0.8)
                            if pos: device.shell(f"input tap {pos[0][0]} {pos[0][1]} "); break
                            time.sleep(1)
                        # 4. click pos 30 times
                        print(f"[{device.serial}] [DIST] Clicking waitdist pos 30 times...")
                        for _ in range(30): device.shell(f"input tap {dist_pos[0]} {dist_pos[1]}"); time.sleep(0.05)
                        # 5. dist3
                        dist3_start = time.time()
                        while True:
                            if time.time() - dist3_start > 120: break
                            cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                            pos = ImgSearchADB(adb_img, 'img/dist3.png', threshold=0.8)
                            if pos: device.shell(f"input tap {pos[0][0]} {pos[0][1]} "); break
                            time.sleep(1)
                    # 6. clear ends
                    for img in ['distskip.png', 'stagespecal.png']:
                        while True:
                            cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                            pos = ImgSearchADB(adb_img, f'img/{img}', threshold=0.8)
                            if pos: device.shell(f"input tap {pos[0][0]} {pos[0][1]} "); time.sleep(1); break
                            time.sleep(1)
                    for img in ['backdist.png', 'backdist1.png']:
                        while True:
                            cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                            pos = ImgSearchADB(adb_img, f'img/{img}', threshold=0.8)
                            if pos: device.shell(f"input tap {pos[0][0]} {pos[0][1]} "); time.sleep(1.2)
                            else: break
                
                # --- START UID EXTRACTION ---
                print(f"[{device.serial}] Proceeding to UID Extraction...")
                pull_seq = ['pull3.png', 'pull4.png', 'pull5.png']; pull_idx = 0
                while pull_idx < len(pull_seq):
                    cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                    p_pos = ImgSearchADB(adb_img, f'img/{pull_seq[pull_idx]}')
                    if p_pos:
                        if pull_idx == len(pull_seq) - 1:
                            def get_clipboard():
                                # กดปุ่ม Copy บนหน้าจอ (ตำแหน่ง p_pos) และรอคลิปบอร์ดทำงาน 
                                device.shell(f"input tap {p_pos[0][0]} {p_pos[0][1]}")
                                time.sleep(1.5) # รอให้ระบบ Copy ลงคลิปบอร์ด Windows
                                return pyperclip.paste()
                            
                            uid = safe_clipboard_operation(device, get_clipboard)
                            if uid:
                                orig = device_state.original_filenames.get(device.serial, "unknown.xml")
                                out = os.path.join(uid_folder, f"[{uid}]+{orig}")
                                
                                # ใช้ su -c ก้อปปี้ออกมาที่ tmp ก่อนเพื่อเลี่ยง Permission Denied (MuMu/Root)
                                tmp_pull = f"/data/local/tmp/pull_{device.serial.replace(':','_')}.xml"
                                device.shell(f"su -c 'cp /data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml {tmp_pull} && chmod 666 {tmp_pull}'")
                                
                                subprocess.run(f'{adb_path} -s {device.serial} pull "{tmp_pull}" "{out}"', shell=True)
                                
                                # ลบไฟล์ขยะบนเครื่อง
                                device.shell(f"su -c 'rm {tmp_pull}'")
                                release_clipboard_uid(uid); return "normal_complete"
                            time.sleep(1)
                        else:
                            device.shell(f"input tap {p_pos[0][0]} {p_pos[0][1]}")
                            pull_idx += 1
                            time.sleep(1)
                    else:
                        time.sleep(0.5)
                return "normal_complete"

            # --- fixid Sequence ---
            if ImgSearchADB(adb_img, 'img/fixid.png', threshold=0.95):
                _login_fixid_count += 1
                if _login_fixid_count >= 8: return "failed"
                print(f"[{device.serial}] Found fixid.png ({_login_fixid_count}/8)...")
                for step_img in ['img/fikcheck.png', 'img/refresh.png']:
                    wait_t = 2 if 'fikcheck' in step_img else 3
                    for _ in range(10):
                        cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                        pos = ImgSearchADB(adb_img, step_img, threshold=0.8)
                        if pos: device.shell(f"input tap {pos[0][0]} {pos[0][1]} "); time.sleep(wait_t); break
                        time.sleep(1)
                check_start = time.time()
                while time.time() - check_start < 60:
                    cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                    pos = ImgSearchADB(adb_img, 'img/check.png')
                    if pos:
                        device.shell(f"input tap {pos[0][0]} {pos[0][1]} "); time.sleep(2)
                        # Quick fixid check after
                        for _ in range(2):
                            cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                            if ImgSearchADB(adb_img, 'img/fixid.png'): break
                            time.sleep(1)
                        break
                    time.sleep(1)
                continue

            # --- refresh (without fixid) ---
            if ImgSearchADB(adb_img, 'img/refresh.png'):
                print(f"[{device.serial}] Found refresh.png (standalone). Refreshing...")
                pos = ImgSearchADB(adb_img, 'img/refresh.png')
                device.shell(f"input tap {pos[0][0]} {pos[0][1]} "); time.sleep(3)
                check_start = time.time()
                while time.time() - check_start < 60:
                    cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                    pos = ImgSearchADB(adb_img, 'img/check.png')
                    if pos: device.shell(f"input tap {pos[0][0]} {pos[0][1]} "); time.sleep(2); break
                    time.sleep(1)
                continue

            # --- Popups & Events ---
            if not event_passed and ImgSearchADB(adb_img, 'img/fixok.png', threshold=0.8):
                pos = ImgSearchADB(adb_img, 'img/fixok.png', threshold=0.8); device.shell(f"input tap {pos[0][0]} {pos[0][1]} "); time.sleep(1); continue
            if ImgSearchADB(adb_img, 'img/event.png'):
                event_passed = True; print(f"[{device.serial}] [EVENT] Detected, Triple Back spam...")
                pos = ImgSearchADB(adb_img, 'img/event.png'); device.shell(f"input tap {pos[0][0]} {pos[0][1]} "); time.sleep(1)
                for _ in range(10): # Spam back
                    device.shell("input keyevent 4; input keyevent 4; input keyevent 4"); time.sleep(0.5)
                    cap = device.screencap(); adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if ImgSearchADB(adb_img, 'img/cancel.png') or ImgSearchADB(adb_img, 'img/stoplogin.png'): break
                continue

            # Generic interaction points
            int_points = [('ok.png', 'ok'), ('check.png', 'check'), ('closeapp.png', 'closeapp'), ('link1.png', 'link1'), ('alert1.png', 'alert1'), ('fixcak.png', 'fixcak'), ('apple.png', 'apple')]
            for img_name, key in int_points:
                p = ImgSearchADB(adb_img, f'img/{img_name}')
                if p: device.shell(f"input tap {p[0][0]} {p[0][1]} "); no_img_timer = time.time(); break
            
            # --- REFRESH SYSTEM (if stuck 60s) ---
            if time.time() - no_img_timer > 60:
                print(f"[{device.serial}] [REFRESH] Stuck for 60s! Returning Home and Relaunching...")
                device.shell("input keyevent 3"); time.sleep(1); open_app(device)
                no_img_timer = time.time()
            
            if time.time() - no_img_timer > no_img_timeout: return "restart"
            time.sleep(1.5)

        except Exception as e:
            print(f"Login Loop Error: {e}"); time.sleep(2)

def process_single_device(device):
    """Device thread worker."""
    while True:
        try:
            update_file_queue()
            if device_state.file_queue.empty():
                time.sleep(5)
                continue

            # Get file from queue
            with device_state.lock:
                if device_state.file_queue.empty(): continue
                xml_filename = device_state.file_queue.get()
                device_state.processed_files.add(xml_filename)
                device_state.original_filenames[device.serial] = xml_filename
            
            orig_path = os.path.join(source_folder, xml_filename)
            start_time = time.time()
            
            # Robust Insertion (ระบบส่งไฟล์)
            if inject_file(device, orig_path):
                open_app(device)
                time.sleep(5)
                status = main_login(device)
                
                # Result Folder Handling
                if status == "normal_complete" or status == "stopcheck_complete":
                    handle_success(orig_path, device.serial)
                    ui_stats.update(success=ui_stats.successful_logins + 1, processed=ui_stats.processed_files + 1)
                elif status == "kaiby":
                    handle_kaiby(orig_path, device.serial)
                    ui_stats.update(processed=ui_stats.processed_files + 1)
                elif status == "restart":
                    print(f"[{device.serial}] Login needs restart, retrying injection...")
                    # Return to queue
                    with device_state.lock:
                        device_state.processed_files.remove(xml_filename)
                    # Don't move the file, it stays in backup/
                    ui_stats.update(processed=ui_stats.processed_files)
                    time.sleep(5)
                else: # failed
                    handle_failure(orig_path, device.serial)
                    ui_stats.update(fail=ui_stats.failed_logins + 1, processed=ui_stats.processed_files + 1)
                
                # Stats
                ui_stats.record_login_time(time.time() - start_time)
                clear_app(device)
            else:
                # Injection failed
                handle_failure(orig_path, device.serial)
                ui_stats.update(fail=ui_stats.failed_logins + 1, processed=ui_stats.processed_files + 1)
                time.sleep(5)
                
        except Exception as e:
            print(f"Worker Error [{device.serial}]: {e}")
            time.sleep(5)

# ----- System Operations -----

def find_adb_executable():
    global adb_path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    adb_locations = [
        os.path.join(script_dir, "adb", "adb.exe"),
        os.path.join(script_dir, "adb", "adb"),
        "adb",
    ]
    adb_locations.append(os.path.join(os.getcwd(), "adb", "adb.exe"))
    
    for loc in adb_locations:
        if not loc.endswith(".exe") and os.name == 'nt' and not os.path.isabs(loc):
             pass
        elif os.path.exists(loc):
            try:
                result = subprocess.run([loc, "version"], capture_output=True, text=True, timeout=15, shell=(os.name == 'nt'))
                if result.returncode == 0:
                    adb_path = loc
                    return True
            except Exception: pass
        if loc == "adb":
            try:
                result = subprocess.run([loc, "version"], capture_output=True, text=True, timeout=15, shell=(os.name == 'nt'))
                if result.returncode == 0:
                    adb_path = loc
                    return True
            except: pass
    
    adb_in_path = shutil.which("adb")
    if adb_in_path:
        adb_path = os.path.abspath(adb_in_path)
        return True
    
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
            return True
    return False

def connect_known_ports():
    """Auto-scan ALL emulator ports, connect everything that responds."""
    try:
        subprocess.run([adb_path, "kill-server"], capture_output=True, timeout=3)
        time.sleep(0.1)
        subprocess.run([adb_path, "start-server"], capture_output=True, timeout=3)
        time.sleep(0.5)
        
        # Ports for MuMu and others
        ports = list(range(5555, 5756, 2)) + list(range(16384, 16416)) + [7555]
        connected = []
        
        def try_connect_port(port):
            try:
                addr = f"127.0.0.1:{port}"
                result = subprocess.run([adb_path, "connect", addr], capture_output=True, timeout=1, text=True)
                out = result.stdout.lower()
                if ("connected" in out or "already connected" in out) and "cannot" not in out:
                    return addr
            except Exception: pass
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(try_connect_port, p) for p in ports]
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res: connected.append(res)
        return connected
    except Exception as e:
        print(f"[ADB] Port scan error: {e}")
        return []

def get_connected_devices():
    """Returns list of online devices from adb devices."""
    try:
        result = subprocess.run([adb_path, "devices"], capture_output=True, text=True, timeout=10)
        lines = result.stdout.strip().split("\n")[1:]
        raw_devices = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                raw_devices.append(parts[0])
        
        if not raw_devices: return []
        
        # Deduplication logic
        emulator_adb_ports = set()
        for d in raw_devices:
            if d.startswith("emulator-"):
                try:
                    console_port = int(d.replace("emulator-", ""))
                    emulator_adb_ports.add(console_port + 1)
                except ValueError: pass
        
        final_devices = []
        seen = set()
        for d in raw_devices:
            if d in seen: continue
            if d.startswith("127.0.0.1:"):
                try:
                    port = int(d.split(":")[1])
                    if port in emulator_adb_ports: continue
                except ValueError: pass
            seen.add(d)
            final_devices.append(d)
        
        adb_client = AdbClient(host="127.0.0.1", port=5037)
        devices = []
        for serial in final_devices:
            for dev in adb_client.devices():
                if dev.serial == serial:
                    devices.append(dev)
                    break
        return devices
    except Exception as e:
        print(f"[ERR] get_connected_devices: {e}")
        return []

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", help="Run worker for specific device serial")
    args = parser.parse_args()

    if not find_adb_executable():
        print(f"{Fore.RED}[ERROR] Could not find adb.exe.{Style.RESET_ALL}")
        return

    # --- Mode: Single Device Run (Manual Focus) ---
    if args.device:
        adb_client = AdbClient(host="127.0.0.1", port=5037)
        for dev in adb_client.devices():
            if dev.serial == args.device:
                process_single_device(dev)
                return
        print(f"Device {args.device} not found."); return

    # --- Mode: Unified Master UI (Threads) ---
    # เรากลับมาใช้หน้าต่างเดียว (Integrated) ตามคำขอเพื่อให้ไม่รกหน้าจอ
    # แต่ยังคงใช้ระบบ Global Mutex ล็อคคลิปบอร์ดระดับ Windows เพื่อไม่ให้ข้อมูลมั่ว
    ui_stats.force_update()
    started_serials = set()
    
    print(f"{Fore.CYAN}>>> INTEGRATED MODE: Running all devices in one window <<<{Style.RESET_ALL}")
    
    while True:
        try:
            connect_known_ports()
            devices = get_connected_devices()
            
            # Update Total Files
            xml_count = 0
            if os.path.exists(source_folder):
                xml_count = len([f for f in os.listdir(source_folder) if f.endswith('.xml')])
            ui_stats.update(total=xml_count, devices=len(devices))
            
            for dev in devices:
                if dev.serial not in started_serials:
                    print(f"{Fore.GREEN}[SYSTEM] Integrating device: {dev.serial}{Style.RESET_ALL}")
                    # รันเป็น Thread ในหน้าต่างเดิม แต่ละตัวจะแยกกันทำงานอิสระ
                    worker = Thread(target=process_single_device, args=(dev,))
                    worker.daemon = True
                    worker.start()
                    started_serials.add(dev.serial)
                    time.sleep(2)
            
            ui_stats.update(devices=len(started_serials))
            
            # Monitor loop
            while True:
                cpu, mem = get_resource_usage()
                if cpu > 90 or mem > 2000: clean_memory()
                ui_stats.update()
                
                # Scan for new devices dynamically
                current_devices = get_connected_devices()
                for d in current_devices:
                    if d.serial not in started_serials:
                        print(f"{Fore.GREEN}[SYSTEM] Adding new device: {d.serial}{Style.RESET_ALL}")
                        worker = Thread(target=process_single_device, args=(d,))
                        worker.daemon = True
                        worker.start()
                        started_serials.add(d.serial)
                        time.sleep(2)
                
                ui_stats.update(devices=len(started_serials))
                time.sleep(30)
                
        except KeyboardInterrupt:
            print(f"\n{Fore.GREEN}Stopping all sessions...{Style.RESET_ALL}")
            break
        except Exception as e:
            print(f"Master UI Error: {e}")
            time.sleep(10)

if __name__ == '__main__':
    try:
        main()
    finally:
        colorama.deinit()
