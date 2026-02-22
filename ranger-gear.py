import cv2
import numpy as np
import subprocess
import os
import time
from time import sleep
import sys
import shutil
import glob
import tempfile
import json
import threading
import queue
import concurrent.futures
import argparse
import colorama
from colorama import Fore, Style
import ssl
from datetime import datetime
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

# Try to import customtkinter for the modern UI
try:
    import customtkinter as ctk
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False
    print("[WARN] customtkinter not found. GUI mode will be disabled. Run 'pip install customtkinter' to enable.")

colorama.init(autoreset=True)

# Fix SSL certificate error for downloading EasyOCR models
ssl._create_default_https_context = ssl._create_unverified_context

# =========================================================
# Statistics and GUI Tracking
# =========================================================
# ----- Simplified UI Stats Class -----
class SimpleUIStats:
    def __init__(self):
        self.total_files = 0
        self.successful_logins = 0
        self.failed_logins = 0
        self.processed_files = 0
        self.connected_devices = 0
        self.lock = threading.RLock()
        self.last_update = time.time()
        self.update_interval = 30
        self.device_statuses = {}
        self.hero_counts = {}
        # Counter สำหรับ hero found/not-found
        self.success_count = 0 # Matches bot success_count
        self.fail_count = 0    # Matches bot fail_count
        # hero found list with counts
        self.hero_found_list = {}  # {hero_combo: count} e.g. {'Yor': 1, 'Yor+Anya': 2}
        
    def update(self, total=None, processed=None, success=None, fail=None, devices=None, hero_found=None, hero_not_found=None):
        with self.lock:
            if total is not None: self.total_files = total
            if processed is not None: self.processed_files = processed
            if success is not None: self.success_count = success
            if fail is not None: self.fail_count = fail
            if devices is not None: self.connected_devices = devices
            # อัพเดท hero counters
            if hero_found is not None: self.success_count += hero_found
            if hero_not_found is not None: self.fail_count += hero_not_found
    
    def update_device(self, device_serial, status):
        with self.lock:
            self.device_statuses[device_serial] = status
    
    def update_hero(self, hero_name, count=1):
        with self.lock:
            if hero_name not in self.hero_found_list:
                self.hero_found_list[hero_name] = 0
            self.hero_found_list[hero_name] += count

    def get_hero_combo_stats(self):
        with self.lock:
            return dict(self.hero_found_list)

ui_stats = SimpleUIStats()
GUI_INSTANCE = None

if GUI_AVAILABLE:
    class CollabConfigWindow(ctk.CTkToplevel):
        def __init__(self, parent):
            super().__init__(parent)
            self.title("⚙ Config Settings")
            self.geometry("350x380")
            self.resizable(False, False)
            self.transient(parent)
            self.grab_set()
            
            ctk.CTkLabel(self, text="Application Settings", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(10, 5))
            
            # Use switches for main modes
            self.vars = {}
            self.add_switch("Find Ranger", "find_ranger")
            self.add_switch("Find Gear", "find_gear")
            self.add_switch("Find Both (All)", "find_all")
            self.add_switch("First Loop Process", "first_loop")
            self.add_switch("Custom Mode", "custommode")
            
            # Thread delay entry
            delay_frame = ctk.CTkFrame(self, fg_color="transparent")
            delay_frame.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(delay_frame, text="Thread Delay (sec):").pack(side="left")
            self.ent_delay = ctk.CTkEntry(delay_frame, width=60)
            self.ent_delay.insert(0, str(config.get("thread_delay", 5)))
            self.ent_delay.pack(side="right")
            
            ctk.CTkButton(self, text="💾 Save Changes", command=self.save_config, fg_color="#2cc985", hover_color="#229f69", height=32).pack(pady=20)
            
        def add_switch(self, label, key):
            var = tk.IntVar(value=config.get(key, 0))
            self.vars[key] = var
            chk = ctk.CTkSwitch(self, text=label, variable=var)
            chk.pack(pady=5, padx=25, anchor="w")

        def save_config(self):
            # Update global config and save to file
            for key, var in self.vars.items():
                config[key] = var.get()
            
            try:
                config["thread_delay"] = int(self.ent_delay.get())
            except:
                pass
                
            main_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ranger-gear_config.json")
            try:
                with open(main_config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
                print(f"[CONFIG] Saved updated settings to {main_config_file}")
            except Exception as e:
                print(f"[ERR] Failed to save config: {e}")
            self.destroy()

    class HeroFoldersWindow(ctk.CTkToplevel):
        def __init__(self, parent):
            super().__init__(parent)
            self.title("🦸 Hero Folders")
            self.geometry("320x400")
            self.parent = parent
            self.resizable(False, False)
            self.transient(parent)
            self.grab_set()
            self.focus_force()
            
            ctk.CTkLabel(self, text="Hero Folders", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(8, 5))
            self.scroll_frame = ctk.CTkScrollableFrame(self, width=280, height=300)
            self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)
            self.load_hero_folders()
            
        def load_hero_folders(self):
            # Show "no-find" and categories if they exist
            base_dir = os.path.join(os.getcwd(), "backup-id")
            if os.path.exists(base_dir):
                for folder in os.listdir(base_dir):
                    btn = ctk.CTkButton(self.scroll_frame, text=f"📁 {folder}", fg_color="#2a3a5c", height=28, anchor="w",
                                        command=lambda f=folder: subprocess.Popen(f'explorer "{os.path.join(base_dir, f)}"'))
                    btn.pack(fill="x", pady=1)

    class DeviceMonitorWidget(ctk.CTkFrame):
        def __init__(self, parent, device_id, index):
            super().__init__(parent, fg_color="#383838", corner_radius=6, height=32)
            self.device_id = device_id
            self.pack_propagate(False)
            
            chk = ctk.CTkCheckBox(self, text="", width=20, height=20, checkbox_width=16, checkbox_height=16)
            chk.pack(side="left", padx=(6, 2))
            chk.select()
            
            ctk.CTkLabel(self, text=f"#{index}", font=ctk.CTkFont(size=11, weight="bold"), text_color="#ffffff", width=25).pack(side="left", padx=(0, 4))
            ctk.CTkLabel(self, text=device_id, font=ctk.CTkFont(family="Consolas", size=10), text_color="#ccc").pack(side="left", padx=(0, 6))
            
            self.lbl_status = ctk.CTkLabel(self, text="Ready", font=ctk.CTkFont(size=10, weight="bold"), text_color="#4caf50", width=60)
            self.lbl_status.pack(side="right", padx=6)
            
            ctk.CTkButton(self, text="↺", width=22, height=20, font=ctk.CTkFont(size=11, weight="bold"), fg_color="#e53935").pack(side="right", padx=2)

        def update_state(self, status=None, **kwargs):
            if status:
                color_map = {'working': "#4caf50", 'waiting': "#ff9800", 'error': "#e53935", 'idle': "#888"}
                self.lbl_status.configure(text=status.upper(), text_color=color_map.get(status, "#888"))

    class ModernBotGUI(ctk.CTk):
        def __init__(self, devices, file_queue, args):
            super().__init__()
            global GUI_INSTANCE
            GUI_INSTANCE = self
            
            self.title("Ranger+Gear")
            self.geometry("620x530")
            self.devices = devices
            self.file_queue = file_queue
            self.args = args
            self.bot_threads = []
            self.device_monitors = {}
            self.hero_stats_labels = {}
            
            self.setup_ui()
            
            # Use after to start the stats loop without blocking the constructor
            self.after(100, self.update_realtime_stats)
            
            # Ensure window is visible
            self.deiconify()
            self.focus_force()
            print("[GUI] Launched Successfully.")

        def setup_ui(self):
            # 1. TOP TOOLBAR
            toolbar = ctk.CTkFrame(self, height=40, fg_color="#333333", corner_radius=0)
            toolbar.pack(fill="x")
            toolbar.pack_propagate(False)
            
            self.lbl_status = ctk.CTkLabel(toolbar, text=f"● ONLINE ({len(self.devices)})", font=ctk.CTkFont(size=11, weight="bold"), text_color="#4caf50")
            self.lbl_status.pack(side="left", padx=10)
            
            self.btn_run = ctk.CTkButton(toolbar, text="▶ Start Bot", width=90, height=26, font=ctk.CTkFont(size=11, weight="bold"),
                                        fg_color="#4caf50", command=self.start_bot)
            self.btn_run.pack(side="left", padx=3)
            
            ctk.CTkButton(toolbar, text="■ Stop", width=65, height=26, font=ctk.CTkFont(size=11, weight="bold"), fg_color="#e53935").pack(side="left", padx=3)
            
            # Stats on Toolbar (right)
            counter_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
            counter_frame.pack(side="right", padx=8)
            
            self.lbl_succ_count = ctk.CTkLabel(counter_frame, text="✅ 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#4caf50")
            self.lbl_succ_count.pack(side="right", padx=6)
            
            self.lbl_fail_count = ctk.CTkLabel(counter_frame, text="❌ 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#ff5555")
            self.lbl_fail_count.pack(side="right", padx=6)
            
            self.lbl_file_count = ctk.CTkLabel(counter_frame, text="📁 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa")
            self.lbl_file_count.pack(side="right", padx=6)
            
            # 2. MAIN CONTENT
            main_frame = ctk.CTkFrame(self, fg_color="transparent")
            main_frame.pack(fill="both", expand=True, padx=6, pady=4)
            main_frame.grid_columnconfigure(0, weight=3)
            main_frame.grid_columnconfigure(1, weight=2)
            main_frame.grid_rowconfigure(0, weight=1)
            
            # Left: Devices
            left_frame = ctk.CTkFrame(main_frame, fg_color="#2b2b2b", corner_radius=8)
            left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
            
            dev_header = ctk.CTkFrame(left_frame, fg_color="#383838", corner_radius=0, height=28)
            dev_header.pack(fill="x")
            ctk.CTkLabel(dev_header, text="   DEVICES", font=ctk.CTkFont(size=11, weight="bold"), text_color="#cccccc", anchor="w").pack(side="left")
            
            self.dev_scroll = ctk.CTkScrollableFrame(left_frame, fg_color="transparent")
            self.dev_scroll.pack(fill="both", expand=True, padx=3, pady=3)
            for i, dev in enumerate(self.devices):
                m = DeviceMonitorWidget(self.dev_scroll, dev, i+1)
                m.pack(fill="x", pady=1)
                self.device_monitors[dev] = m
            
            # Right: Heroes
            right_frame = ctk.CTkFrame(main_frame, fg_color="#2b2b2b", corner_radius=8)
            right_frame.grid(row=0, column=1, sticky="nsew", padx=(3, 0))
            
            hero_header = ctk.CTkFrame(right_frame, fg_color="#383838", corner_radius=0, height=28)
            hero_header.pack(fill="x")
            ctk.CTkLabel(hero_header, text="   🏆 HEROES FOUND", font=ctk.CTkFont(size=11, weight="bold"), text_color="#f2c94c", anchor="w").pack(side="left")
            
            self.hero_scroll = ctk.CTkScrollableFrame(right_frame, fg_color="transparent")
            self.hero_scroll.pack(fill="both", expand=True, padx=3, pady=3)
            
            # 3. LOG AREA
            log_frame = ctk.CTkFrame(self, fg_color="#1e1e1e", corner_radius=6, height=80)
            log_frame.pack(fill="x", padx=6, pady=(0, 4))
            log_frame.pack_propagate(False)
            
            self.log_text = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(family="Consolas", size=10), text_color="#8b949e", fg_color="#1e1e1e")
            self.log_text.pack(fill="both", expand=True, padx=2, pady=2)
            self.log_text.configure(state="disabled")
            
            # 4. BOTTOM BAR
            bottom_bar = ctk.CTkFrame(self, height=32, fg_color="#333333", corner_radius=0)
            bottom_bar.pack(fill="x")
            
            base_path = os.path.dirname(os.path.abspath(__file__))
            backup_folder = os.path.join(base_path, "backup")
            heroes_folder = os.path.join(base_path, "backup-id")
            
            ctk.CTkButton(bottom_bar, text="🔌 Start ADB", width=85, height=22, font=ctk.CTkFont(size=10), fg_color="#4caf50").pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="⚙ Config", width=70, height=22, font=ctk.CTkFont(size=10), fg_color="#555555", command=self.open_config).pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="📁 Backup", width=70, height=22, font=ctk.CTkFont(size=10), fg_color="#555555", command=lambda: subprocess.Popen(f'explorer "{backup_folder}"')).pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="🦸 Heroes", width=70, height=22, font=ctk.CTkFont(size=10), fg_color="#555555", command=lambda: subprocess.Popen(f'explorer "{heroes_folder}"')).pack(side="left", padx=3, pady=4)
            ctk.CTkLabel(bottom_bar, text="v3.2.0", font=ctk.CTkFont(size=10), text_color="#888888").pack(side="right", padx=8)

        def log(self, level, message): 
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"[{ts}] {message}\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

        def start_bot(self):
            self.btn_run.configure(text="⏸ Running", fg_color="#ff9800", text_color="black")
            self.log("INFO", "Starting Bot Threads...")
            for device_id in self.devices:
                bot = RangerGearBot(device_id, self.file_queue, self.args)
                bot.start()
                self.bot_threads.append(bot)

        def update_realtime_stats(self):
            try:
                with ui_stats.lock:
                    self.lbl_file_count.configure(text=f"📁 {self.file_queue.qsize()}")
                    self.lbl_succ_count.configure(text=f"✅ {ui_stats.success_count}")
                    self.lbl_fail_count.configure(text=f"❌ {ui_stats.fail_count}")
                    
                    for dev, stat in ui_stats.device_statuses.items():
                        if dev in self.device_monitors:
                            self.device_monitors[dev].update_state(status=stat.get('status'))
                    
                    hero_data = ui_stats.get_hero_combo_stats()
                    if ui_stats.fail_count > 0:
                        hero_data["❌ ไม่เจอ"] = ui_stats.fail_count
                    
                    for hero, count in hero_data.items():
                        if hero not in self.hero_stats_labels:
                            self.add_hero_row(hero, hero == "❌ ไม่เจอ")
                        self.hero_stats_labels[hero].configure(text=str(count))
            except Exception as e:
                print(f"[GUI] Update error: {e}")
            
            self.after(500, self.update_realtime_stats)


        def add_hero_row(self, hero_name, is_not_found):
            bg = "#3d2020" if is_not_found else "#2a3a2a"
            txt_color = "#e53935" if is_not_found else "#4caf50"
            row = ctk.CTkFrame(self.hero_scroll, fg_color=bg, corner_radius=6, height=26)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=f"  {hero_name}", font=ctk.CTkFont(size=11, weight="bold"), text_color="white", anchor="w").pack(side="left", fill="x", expand=True)
            lbl_count = ctk.CTkLabel(row, text="0", font=ctk.CTkFont(size=12, weight="bold"), text_color=txt_color)
            lbl_count.pack(side="right", padx=8)
            self.hero_stats_labels[hero_name] = lbl_count

        def open_config(self): CollabConfigWindow(self)
        def open_heroes(self): HeroFoldersWindow(self)

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
    
    # Load ONLY main config from ranger-gear_config.json
    main_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ranger-gear_config.json")
    if os.path.exists(main_config_file):
        try:
            with open(main_config_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                config.update(loaded)
            print(f"[CONFIG] Base Loaded: {main_config_file}")
        except Exception as e:
            print(f"[WARN] Error loading config: {e}")
    else:
        print(f"[WARN] Config not found: {main_config_file}")


def find_adb_executable():
    global adb_path
    
    # Check common locations
    script_dir = os.path.dirname(os.path.abspath(__file__))
    adb_locations = [
        os.path.join(script_dir, "adb", "adb.exe"),
        os.path.join(script_dir, "adb", "adb"),
        "adb",
    ]
    
    # Add current working directory as another check
    adb_locations.append(os.path.join(os.getcwd(), "adb", "adb.exe"))
    
    for loc in adb_locations:
        if not loc.endswith(".exe") and sys.platform == 'win32' and not os.path.isabs(loc):
             pass # Skip simple "adb" for exists check if it's just a command
        elif os.path.exists(loc):
            print(f"[ADB] Found file at {loc}, testing...")
            try:
                result = subprocess.run(
                    [loc, "version"],
                    capture_output=True, text=True, timeout=5,
                    shell=(sys.platform == 'win32')
                )
                if result.returncode == 0:
                    adb_path = loc
                    print(f"[ADB] Verified: {adb_path}")
                    return True
            except Exception as e:
                print(f"[ADB] Error testing {loc}: {e}")
        
        # Also try running loc directly if it's a command name like "adb"
        if loc == "adb":
            try:
                result = subprocess.run(
                    [loc, "version"],
                    capture_output=True, text=True, timeout=5,
                    shell=(sys.platform == 'win32')
                )
                if result.returncode == 0:
                    adb_path = loc
                    print(f"[ADB] Verified command: {adb_path}")
                    return True
            except:
                pass
    
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
    def __init__(self, device_id, file_queue, args=None):
        threading.Thread.__init__(self)
        self.device_id = device_id
        self.file_queue = file_queue
        self.args = args # Store command line args
        self.daemon = True
        
        def update_gui_status(self, step, status="working"):
            ui_stats.update_device(self.device_id, {'step': step, 'status': status})
        self.update_gui_status = update_gui_status.__get__(self, RangerGearBot)
        
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
        
        # Sequence Definitions (Reverted to use coordinates for checkboxes)
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
                # 0. Reload Config for dynamic changes without restart
                load_config()
                self.do_ranger = config.get("find_ranger", 0) or config.get("find_all", 1)
                self.do_gear = config.get("find_gear", 0) or config.get("find_all", 1)

                if self.file_queue.empty():
                    # Instead of breaking, wait for new files to be dropped into backup
                    self.update_gui_status("Waiting for files", "waiting")
                    
                    # Scan for new files periodically
                    source_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup")
                    new_files = [os.path.join(source_folder, f) for f in os.listdir(source_folder) if f.lower().endswith(".xml")]
                    if new_files:
                        for f in new_files:
                            self.file_queue.put(f)
                        print(f"[{self.device_id}] Found {len(new_files)} new files. Resuming...")
                        # Update total count in UI
                        with ui_stats.lock:
                            ui_stats.total_files += len(new_files)
                        continue
                    
                    sleep(5)
                    continue

                try:
                    # 1. Check First Loop Process Toggle
                    current_first_loop_enabled = config.get("first_loop", True)
                    if current_first_loop_enabled and not self.first_loop_done:
                        self.update_gui_status("First Loop", "working")
                        res = self.first_loop_process()
                        if res == "complete":
                            self.first_loop_done = True
                        elif res == "restart":
                            sleep(2)
                            continue
                    else:
                        # Skip first loop if disabled or already done
                        self.first_loop_done = True

                    # 1. Get File
                    try:
                        xml_file = self.file_queue.get(timeout=2)
                    except queue.Empty:
                        break
                    
                    # Store original filename
                    self.current_original_filename = os.path.basename(xml_file)
                    
                    # --- File Locking Mechanism ---
                    # To prevent multiple CMD windows from processing the same file
                    lock_file = xml_file + ".lock"
                    if os.path.exists(lock_file):
                        # Simple check: if lock file is older than 1 hour, assume it's stale
                        if time.time() - os.path.getmtime(lock_file) > 3600:
                            print(f"[{self.device_id}] Stale lock found for {self.current_original_filename}. Removing...")
                            os.remove(lock_file)
                        else:
                            # Skip this file, someone else is working on it
                            continue
                    
                    # Create lock
                    try:
                        with open(lock_file, "w") as f:
                            f.write(self.device_id)
                    except:
                        continue # If can't create lock, skip
                    
                    print(f"[{self.device_id}] Processing file: {self.current_original_filename}")
                    self.update_gui_status(f"Injecting: {self.current_original_filename}")

                    # 2. Inject
                    injected_file = self.inject_file(xml_file)
                    
                    if injected_file:
                        # 3. Login (with ranger/gear flow based on mode)
                        self.update_gui_status("Logging in...")
                        status = self.main_login(injected_file)
                        
                        if status == "success":
                            self.handle_success(xml_file)
                            if os.path.exists(lock_file): os.remove(lock_file)
                            ui_stats.update(success=ui_stats.success_count + 1, processed=ui_stats.processed_files + 1)
                            self.update_gui_status("Completed", "idle")
                        elif status == "failed":
                            self.handle_failure(xml_file)
                            if os.path.exists(lock_file): os.remove(lock_file)
                            ui_stats.update(fail=ui_stats.fail_count + 1)
                            self.update_gui_status("Failed", "error")
                            self.first_loop_done = False
                        else:
                            print(f"[{self.device_id}] Status: {status}. Moving to next.")
                            self.handle_failure(xml_file)
                            if os.path.exists(lock_file): os.remove(lock_file)
                            ui_stats.update(fail=ui_stats.fail_count + 1)
                            self.update_gui_status(f"Error: {status}", "error")
                    else:
                        print(f"[{self.device_id}] Injection failed for {xml_file}")
                        if os.path.exists(lock_file): os.remove(lock_file)
                        ui_stats.update(fail=ui_stats.fail_count + 1)
                        self.update_gui_status("Inject Failed", "error")
                    
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
        """Capture screen and load into RAM (Robust version)"""
        # Clear previous screen to avoid using stale data if capture fails
        self._screen = None
        self._screen_color = None
        
        try:
            # Try fast method with increased timeout (20s)
            result = subprocess.run(
                [self.adb_cmd, "-s", self.device_id, "exec-out", "screencap", "-p"],
                capture_output=True, timeout=20
            )
            if result.returncode == 0 and len(result.stdout) > 100:
                img_array = np.frombuffer(result.stdout, np.uint8)
                self._screen = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
                self._screen_color = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                return True
        except Exception as e:
            print(f"[{self.device_id}] Fast capture error/timeout: {e}")
        
        # Fallback to slow but reliable method
        try:
            # Use self.filename as temp storage
            self.adb_shell("screencap -p /sdcard/screen.png", timeout=20)
            self.adb_run([self.adb_cmd, "-s", self.device_id, "pull", "/sdcard/screen.png", self.filename], timeout=20)
            if os.path.exists(self.filename):
                self._screen = cv2.imread(self.filename, 0)
                self._screen_color = cv2.imread(self.filename, cv2.IMREAD_COLOR)
                # Cleanup SD card
                self.adb_shell("rm /sdcard/screen.png")
                return self._screen is not None
        except Exception as e:
            print(f"[{self.device_id}] Fallback capture error: {e}")
            
        return False

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
            self.tap(x, y) # Use the improved tap method
            return True
        return False
    
    def tap(self, x, y):
        """Direct tap without image search - uses a short swipe for better reliability"""
        # Short wait before tap to ensure UI is ready and ADB can process
        sleep(0.5)
        # Using swipe with 200ms duration makes it even more reliable than a quick tap
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "input", "swipe", str(x), str(y), str(x), str(y), "200"])

    def type_text(self, text):
        """Type text via ADB (for search box)"""
        escaped = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "input", "text", escaped])

    def swipe(self, x1, y1, x2, y2, duration=300):
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "input", "swipe", 
                     str(x1), str(y1), str(x2), str(y2), str(duration)])

    def check_black_screen(self, threshold=0.8):
        """Check if screen is mostly black"""
        if self._screen is None:
            return False
        # Count black pixels (intensity < 10)
        black_pixels = np.sum(self._screen < 10)
        total_pixels = self._screen.size
        return (black_pixels / total_pixels) > threshold

    def check_error_images(self, skip_fixcak=False, skip_icon=False):
        """Check error images using cached screen"""
        if self._screen is None:
            return None
        # fixcak.png: restart process if found
        if not skip_fixcak:
            fixcak_path = "img/fixcak.png"
            if os.path.exists(fixcak_path) and self.exists_in_cache(fixcak_path):
                return "fixcak"
        
        # stopcheck.png: complete/stop process if found
        # Try multiple thresholds like in example code
        for th in [0.95, 0.9, 0.85, 0.8]:
            if self.exists_in_cache("img/stopcheck.png", similarity=th):
                return "stopcheck"
        
        # Common login errors
        if self.exists_in_cache("img/fixbuglogin.png") or self.exists_in_cache("img/alert2.png") or self.exists_in_cache("img/alert3.png"):
            return "fixbug"
            
        if self.exists_in_cache("img/unkhow.png"):
            return "unkhow"
            
        # Icon check (if app crashed/closed to home screen)
        if not skip_icon:
            if self.exists_in_cache("img/icon.png"):
                return "icon"
            
        error_images = ["img/failed1.png", "img/fixalerterror1.png"]
        for err in error_images:
            if self.exists_in_cache(err):
                return "error_img"
                
        return None

    # =========================================================
    # OCR Methods - For Gear Mode
    # =========================================================
    def ocr_read_region(self, x, y, w, h):
        """Read text from a specific region of the cached color screen using EasyOCR. (Optimized)"""
        if self._screen_color is None or not self.do_gear:
            return []
        
        # Crop region from color image
        img = self._screen_color[y:y+h, x:x+w]
        
        if img is None or img.size == 0:
            print(f"[{self.device_id}] OCR crop region empty!")
            return []
        
        # Reduced scaling (1.5x instead of 2.0x) for major speedup
        img = cv2.resize(img, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_LINEAR)
        
        reader = get_ocr_reader()
        # Performance tuning: paragraph=True makes it MUCH faster for lists
        results = reader.readtext(
            img, 
            detail=1, 
            paragraph=True,
            contrast_ths=0.1, 
            adjust_contrast=False,
            add_margin=0.1,
            width_ths=0.7
        )
        
        text_results = []
        for (bbox, text) in results:
            # When paragraph=True, results is [(bbox, text), ...] instead of [(bbox, text, conf), ...]
            text_results.append((text, 0.99)) # Assume high confidence for paragraphs
        
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
        """Delete specific shared_prefs files only (partial clear)"""
        base = "/data/data/com.linecorp.LGRGS/shared_prefs"
        # Files to delete to clear session but keep game data
        files_to_remove = [
            "_LINE_COCOS_PREF_KEY.xml",
            "com.linecorp.LGRGS.xml",
            "LINE_LGRGS_PREFS.xml",
            "NativeCache.xml",
            "LocalSettings.xml"
        ]
        
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(1)
        
        # Build rm commands for specific files
        rm_cmds = " && ".join([f"rm -f {base}/{f}" for f in files_to_remove])
        # Also include any .bak files to be safe
        rm_cmds += f" && rm -f {base}/*.bak"
        
        # We STOP deleting the entire cache and shared_prefs folder
        self.adb_shell(f"su -c '{rm_cmds}'")
        print(f"[{self.device_id}] Cleared specific shared_prefs (Partial)")

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
                # Clear previous artifacts
                self.adb_shell(f"su -c 'rm -f {final} && rm -f {tmp}'")
                
                # Push to tmp
                self.adb_run([self.adb_cmd, "-s", self.device_id, "push", src, tmp], timeout=30, check=True)
                
                # Verify file size remotely
                size_check = self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", f"stat -c %s {tmp}"], text=True)
                remote_size_str = size_check.stdout.strip()
                remote_size = int(remote_size_str) if remote_size_str.isdigit() else 0
                
                if remote_size != src_size:
                    print(f"[{self.device_id}] Size mismatch! Local:{src_size} Remote:{remote_size} (Attempt {attempt})")
                    sleep(1)
                    continue
                
                # Robust deployment shell command
                shell_cmd = (
                    f"su -c '"
                    f"mkdir -p {final_dir} && "
                    f"cp -f {tmp} {final} && "
                    f"chmod 666 {final} && "
                    f"chown $(stat -c %u:%g {final_dir}) {final} || true && "
                    f"restorecon {final} || true && "
                    f"rm -f {tmp}"
                    f"'"
                )
                self.adb_shell(shell_cmd)
                
                # Final verification
                verify = self.adb_run(
                    [self.adb_cmd, "-s", self.device_id, "shell", f"su -c 'stat -c %s {final}'"], text=True
                )
                final_size_str = verify.stdout.strip()
                final_size = int(final_size_str) if final_size_str.isdigit() else 0
                
                if final_size == src_size:
                    print(f"[{self.device_id}] Injection Verified OK (Size: {final_size} bytes)")
                    return local_xml_path
                else:
                    print(f"[{self.device_id}] Verification FAILED! Expected:{src_size} Got:{final_size} (Attempt {attempt})")
                    sleep(1)
                    
            except Exception as e:
                print(f"[{self.device_id}] Injection Exception (Attempt {attempt}): {e}")
                sleep(1)
        
        print(f"[{self.device_id}] Injection FAILED after {max_retries} attempts!")
        return None

    def first_loop_process(self):
        try:
            print(f"[{self.device_id}] Starting First Loop Process...")
            self.clear_specific_shared_prefs()
            sleep(3)
            
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
            sleep(1)
            # Go to Home screen first so we can see the icon
            self.adb_shell("input keyevent 3")
            print(f"[{self.device_id}] Back to Home, waiting for sequence to click icon...")
            sleep(3)
            
            # --- Sequence 1 ---
            print(f"[{self.device_id}] Processing SEQ 1...")
            res1 = self.process_sequence(self.seq1)
            if res1 == "restart": return "restart"
            if res1 == "complete": return "complete"
            
            # Back logic
            print(f"[{self.device_id}] Waiting 8s then Back...")
            sleep(8)
            self.adb_shell("input keyevent 4")
            sleep(2)
            
            # --- Sequence 2 ---
            print(f"[{self.device_id}] Processing SEQ 2...")
            res2 = self.process_sequence(self.seq2)
            if res2 == "restart": return "restart"
            if res2 == "complete": return "complete"
            
            # End
            print(f"[{self.device_id}] First Loop Completed!")
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
            sleep(2)
            return "complete"
            
        except Exception as e:
            print(f"[{self.device_id}] First Loop Error: {e}")
            return "error"

    def process_sequence(self, sequence):
        for item in sequence:
            # Check for global triggers before each item
            self.capture_screen()
            # Skip icon check if we are currently looking for icon.png in sequence
            skip_icon = (item == 'icon.png')
            err = self.check_error_images(skip_icon=skip_icon)
            if err == "fixcak": return "restart"
            if err == "icon":
                print(f"[{self.device_id}] App closed/crashed! Clicking icon to relaunch...")
                self.click("img/icon.png")
                return "restart"
            if err == "stopcheck": return "complete"

            if isinstance(item, tuple):
                print(f"[{self.device_id}] Tapping: {item}")
                self.tap(item[0], item[1])
                sleep(3.0) # Increased delay to 3s to let UI catch up when running multiple emulators
                continue
            
            if isinstance(item, str) and item.startswith('@'):
                checkpoint_img = item[1:]
                if not checkpoint_img.startswith('img'):
                    checkpoint_img = f"img/{checkpoint_img}"
                print(f"[{self.device_id}] Checkpoint: waiting for {checkpoint_img} (no click)")
                while True:
                    self.capture_screen()
                    err = self.check_error_images()
                    if err == "fixcak": return "restart"
                    if err == "fixbug":
                        self.click("img/fixbuglogin.png")
                        return "restart"
                    if err == "unkhow":
                        self.click("img/unkhow.png")
                        return "restart"
                    if err == "icon":
                        print(f"[{self.device_id}] App closed/crashed! Clicking icon to relaunch...")
                        self.click("img/icon.png")
                        return "restart"
                    if err == "stopcheck": return "complete"
                    
                    if self.exists_in_cache(checkpoint_img, similarity=0.9): 
                        print(f"[{self.device_id}] Checkpoint reached: {checkpoint_img}")
                        break
                    sleep(1.5)
                sleep(1.0)
                continue
                
            img_path = f"img/{item}" if isinstance(item, str) and not item.startswith('img') else item
            
            if item == 'icon.png':
                print(f"[{self.device_id}] Waiting for app icon...")
                for _ in range(30):
                    self.capture_screen()
                    if self.exists_in_cache(img_path):
                        self.click(img_path)
                        sleep(5)
                        break
                    sleep(1)
                continue

            print(f"[{self.device_id}] Waiting for {item}...")
            while True:
                # Check fixcak/stopcheck/blackscreen/fixbug/unkhow
                self.capture_screen() # Ensure screen is captured before checking errors
                err = self.check_error_images()
                if err == "fixcak":
                    print(f"[{self.device_id}] Found fixcak.png! Restarting first loop...")
                    return "restart"
                if err == "fixbug":
                    print(f"[{self.device_id}] Found fixbug/alert detected! Clicking and restarting...")
                    if self.exists_in_cache("img/alert2.png"): self.click("img/alert2.png")
                    elif self.exists_in_cache("img/alert3.png"): self.click("img/alert3.png")
                    else: self.click("img/fixbuglogin.png")
                    return "restart"
                
                if self.exists_in_cache("img/fixplay.png"):
                    print(f"[{self.device_id}] Found fixplay.png! Clicking...")
                    self.click("img/fixplay.png")
                    sleep(1)
                    continue

                if err == "unkhow":
                    print(f"[{self.device_id}] Found unkhow.png! Clicking and restarting...")
                    self.click("img/unkhow.png")
                    return "restart"
                if err == "icon":
                    print(f"[{self.device_id}] App closed/crashed! Clicking icon to relaunch...")
                    self.click("img/icon.png")
                    return "restart"
                if err == "stopcheck":
                    print(f"[{self.device_id}] Found stopcheck.png! Skipping to complete.")
                    return "complete"
                
                if self.exists_in_cache(img_path):
                    print(f"[{self.device_id}] Found {item}, clicking...")
                    self.click(img_path)
                    sleep(1.5)
                    found = True
                    break
                sleep(1.5)
            
        return "success"

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

            # fixcak.png Check
            if self.exists_in_cache("img/fixcak.png"):
                print(f"[{self.device_id}] Fixcak detected (fix bug login). Dismissing...")
                self.click("img/fixcak.png")
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
                    ranger_results = self.process_find_ranger(current_filename)
                
                # Then run gear process if enabled
                if self.do_gear:
                    # If both ranger and gear, skip findgear1 since we're already in the app
                    skip_gear1 = self.do_ranger and self.do_gear
                    gear_results = self.process_check_gear(current_filename, ranger_results, skip_findgear1=skip_gear1)
                
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
                    msg = f"[{self.device_id}] 🏆 Success! Found {category}: {found_names}"
                    if GUI_INSTANCE:
                        GUI_INSTANCE.log("SUCCESS", msg)
                        # ส่งชื่อแบบ Combo (บวกรวมกัน) ไปแสดงในหน้า GUI ตามต้องการ
                        ui_stats.update_hero(found_names)
                    else:
                        print(msg)
                    
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
                    msg = f"[{self.device_id}] ไม่เจอ Ranger/Gear ที่ต้องการ"
                    if GUI_INSTANCE:
                        GUI_INSTANCE.log("INFO", msg)
                        ui_stats.update_hero("ไม่เจอ")
                    else:
                        print(msg)
                    
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
                if error_found == "fixbug":
                    if self.exists_in_cache("img/alert2.png"): self.click("img/alert2.png")
                    elif self.exists_in_cache("img/alert3.png"): self.click("img/alert3.png")
                    else: self.click("img/fixbuglogin.png")
                    sleep(2)
                elif error_found == "unkhow":
                    self.click("img/unkhow.png")
                    sleep(2)
                self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
                sleep(3)
                if self.exists("img/icon.png"):
                    self.click("img/icon.png")
                    sleep(5)
                loop_count = 0
                continue
            
            # fixplay.png Check
            if self.exists_in_cache("img/fixplay.png"):
                print(f"[{self.device_id}] Found fixplay.png! Clicking...")
                self.click("img/fixplay.png")
                sleep(1)
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
    parser = argparse.ArgumentParser(description="Auto Ranger+Gear Script v3.2.0")
    parser.add_argument("--device", type=str, help="Specific device ID/address to run (e.g. 127.0.0.1:5557)")
    parser.add_argument("--no-reset-adb", action="store_true", help="Don't kill/start ADB server")
    parser.add_argument("--cli", action="store_true", help="Launch in Command Line mode (no GUI)")
    args = parser.parse_args()

    print("=== Auto Ranger+Gear Script v3.2.0 ===")
    
    load_config()
    
    if not find_adb_executable():
        print("ADB Not Found.")
        sys.exit(1)
    
    # Reset ADB (Skip if requested)
    if not args.no_reset_adb:
        print("[INFO] Restarting ADB Server...")
        subprocess.run([adb_path, "kill-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run([adb_path, "start-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        sleep(2)
        
    devices = []
    if args.device:
        devices = [args.device]
    else:
        for attempt in range(3):
            devices = get_connected_devices()
            emulator_devices = [d for d in devices if d.startswith("emulator-") or d.startswith("127.0.0.1:")]
            if emulator_devices:
                devices = emulator_devices
                break
            if attempt < 2:
                print(f"[DEV] Attempt {attempt+1}: No devices found yet, waiting 3s...")
                sleep(3)
    
    if not devices:
        print("[ERROR] No devices connected. Make sure your emulator is running.")
        sys.exit(1)

    print(f"[INFO] Connected Devices ({len(devices)}): {', '.join(devices)}")
    
    # Prepare OCR
    find_ranger = config.get("find_ranger", 0)
    find_gear = config.get("find_gear", 0)
    find_all = config.get("find_all", 1)
    if find_gear or find_all:
        print("[INFO] Pre-loading OCR model...")
        try:
            get_ocr_reader()
            print("[OK] OCR model loaded.")
        except Exception as e:
            print(f"[WARN] Failed to load OCR: {e}")
    
    # Setup Queue
    file_queue = queue.Queue()
    source_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup")
    if os.path.exists(source_folder):
        files = [os.path.join(source_folder, f) for f in os.listdir(source_folder) if f.lower().endswith(".xml")]
        for f in files:
            file_queue.put(f)
        ui_stats.update(total=len(files))
        print(f"[FILE] Loaded {len(files)} files into queue from {source_folder}")
    else:
        print(f"[WARN] Backup folder '{source_folder}' not found.")
    
    # Selection
    if not args.cli and GUI_AVAILABLE:
        print(f"{Fore.GREEN}[START] Launching GUI Mode...{Style.RESET_ALL}")
        try:
            print("[DEBUG] Setting CustomTkinter appearance...")
            ctk.set_appearance_mode("Dark")
            print("[DEBUG] Setting CustomTkinter theme...")
            ctk.set_default_color_theme("blue")
            
            print("[DEBUG] Creating ModernBotGUI instance...")
            gui = ModernBotGUI(devices, file_queue, args)
            
            print("[DEBUG] Initializing mainloop...")
            GUI_INSTANCE = gui
            gui.mainloop()
            print("[DEBUG] Mainloop exited.")
            sys.exit(0)
        except Exception as e:
            print(f"{Fore.RED}[ERROR] GUI Failed to start: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            print("[INFO] Falling back to CLI mode...")
            args.cli = True

    # CLI Mode
    print(f"\n{Fore.CYAN}Starting bot in CLI Mode...{Style.RESET_ALL}")
    
    # Start Threads
    threads = []
    print(f"[INFO] Starting {len(devices)} threads...")
    
    delay = config.get("thread_delay", 5)
    for i, dev in enumerate(devices):
        t = RangerGearBot(dev, file_queue, args)
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


