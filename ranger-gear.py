import cv2
import numpy as np
import subprocess
import os
# à¸—à¸³à¸‡à¸²à¸™à¹ƒà¸™à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸‚à¸­à¸‡à¹„à¸Ÿà¸¥à¹Œà¸™à¸µà¹‰à¹€à¸ªà¸¡à¸­ - à¹€à¸›à¸´à¸”à¸ˆà¸²à¸à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸­à¸·à¹ˆà¸™ (à¹€à¸Šà¹ˆà¸™ VS Code à¸—à¸µà¹ˆà¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¹à¸¡à¹ˆ) à¹à¸¥à¹‰à¸§à¸«à¸² img/... à¹„à¸¡à¹ˆà¹€à¸ˆà¸­
try:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
except Exception:
    pass
import struct
import hashlib
import time
from time import sleep
import sys
# à¸šà¸±à¸‡à¸„à¸±à¸š stdout/stderr à¹€à¸›à¹‡à¸™ UTF-8 à¸šà¸™ Windows - à¹à¸à¹‰ 'charmap' codec can't encode à¹€à¸§à¸¥à¸² print à¸ à¸²à¸©à¸²à¹„à¸—à¸¢
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import shutil
import glob
import tempfile
import json
import threading
import base64
import contextlib
import traceback
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

# Shared tap/position helpers (minitouch + remembered button positions).
# Optional: if the file is missing the bot keeps working the old way.
try:
    import touch_helper
    TOUCH_HELPER_AVAILABLE = True
except Exception as _touch_err:
    touch_helper = None
    TOUCH_HELPER_AVAILABLE = False
    print(f"[WARN] touch_helper.py not loaded ({_touch_err}). Using plain ADB taps + full-screen search.")

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
        # Counter à¸ªà¸³à¸«à¸£à¸±à¸š hero found/not-found
        self.success_count = 0 # Matches bot success_count
        self.fail_count = 0    # Matches bot fail_count
        # hero found list with counts
        self.hero_found_list = {}  # {hero_combo: count} e.g. {'Yor': 1, 'Yor+Anya': 2}
        # --- Disk sync throttling (à¸à¸±à¸™ UI à¸„à¹‰à¸²à¸‡à¸•à¸­à¸™à¸£à¸±à¸™à¸«à¸¥à¸²à¸¢à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™) ---
        self._last_save = 0.0
        self._save_interval = 2.0   # à¹€à¸‚à¸µà¸¢à¸™ shared_stats.json à¸­à¸¢à¹ˆà¸²à¸‡à¸¡à¸²à¸à¸—à¸¸à¸ 2 à¸§à¸´
        self._last_load = 0.0
        self._load_interval = 1.0   # à¸­à¹ˆà¸²à¸™ shared_stats.json à¸­à¸¢à¹ˆà¸²à¸‡à¸¡à¸²à¸à¸—à¸¸à¸ 1 à¸§à¸´
        self._dirty = False

    def _get_shared_file(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared_stats.json")

    def save_shared(self, force=False):
        """Save stats to shared file (debounced + disk I/O à¸™à¸­à¸ lock à¸à¸±à¸™ UI à¸„à¹‰à¸²à¸‡)"""
        now = time.time()
        # snapshot à¸‚à¹‰à¸­à¸¡à¸¹à¸¥à¹ƒà¸•à¹‰ lock à¸­à¸¢à¹ˆà¸²à¸‡à¹€à¸£à¹‡à¸§ à¹à¸¥à¹‰à¸§à¸„à¹ˆà¸­à¸¢à¹€à¸‚à¸µà¸¢à¸™à¸”à¸´à¸ªà¸à¹Œà¸‚à¹‰à¸²à¸‡à¸™à¸­à¸
        with self.lock:
            if not force and (now - self._last_save) < self._save_interval:
                self._dirty = True   # à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸–à¸¶à¸‡à¹€à¸§à¸¥à¸²à¹€à¸‚à¸µà¸¢à¸™ à¸„à¹ˆà¸­à¸¢à¹€à¸‚à¸µà¸¢à¸™à¸£à¸­à¸šà¸–à¸±à¸”à¹„à¸›
                return
            self._last_save = now
            self._dirty = False
            data = {
                "success_count": self.success_count,
                "fail_count": self.fail_count,
                "hero_found_list": dict(self.hero_found_list),
                "device_statuses": dict(self.device_statuses),
                "last_update": now
            }
        # ---- disk I/O à¸­à¸¢à¸¹à¹ˆà¸™à¸­à¸ lock: à¹„à¸¡à¹ˆà¸šà¸¥à¹‡à¸­à¸ worker à¸­à¸·à¹ˆà¸™/GUI ----
        try:
            path = self._get_shared_file()
            tmp_path = f"{path}.{os.getpid()}.tmp"  # tmp à¹à¸¢à¸à¸•à¹ˆà¸­ process à¸à¸±à¸™à¸Šà¸™à¸à¸±à¸™
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            for _ in range(5):
                try:
                    os.replace(tmp_path, path)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        except Exception as e:
            print(f"[DEBUG] save_shared error: {e}")

    def load_shared(self, force=False):
        """Load stats from shared file (throttled + parse à¸™à¸­à¸ lock à¸à¸±à¸™ UI à¸„à¹‰à¸²à¸‡)"""
        now = time.time()
        with self.lock:
            if not force and (now - self._last_load) < self._load_interval:
                return
            self._last_load = now

        shared_file = self._get_shared_file()
        if not os.path.exists(shared_file):
            return

        data = None
        for _ in range(3):  # à¸­à¹ˆà¸²à¸™à¸”à¸´à¸ªà¸à¹Œà¸™à¸­à¸ lock
            try:
                with open(shared_file, "r", encoding="utf-8") as f:
                    content = f.read()
                if not content:
                    time.sleep(0.02); continue
                data = json.loads(content)
                break
            except Exception:
                time.sleep(0.02)
        if data is None:
            return

        with self.lock:  # merge à¹ƒà¸•à¹‰ lock (à¹€à¸£à¹‡à¸§ à¹„à¸¡à¹ˆà¸¡à¸µ disk I/O)
            self.success_count = max(self.success_count, data.get("success_count", 0))
            self.fail_count = max(self.fail_count, data.get("fail_count", 0))
            for h, count in data.get("hero_found_list", {}).items():
                self.hero_found_list[h] = max(self.hero_found_list.get(h, 0), count)
            self.device_statuses.update(data.get("device_statuses", {}))

    def update(self, total=None, processed=None, success=None, fail=None, devices=None, hero_found=None, hero_not_found=None):
        self.load_shared() # Pull latest from others first to avoid overwriting counts
        with self.lock:
            if total is not None: self.total_files = total
            if processed is not None: self.processed_files = processed
            if success is not None: 
                # For success/fail, we take the max of (local incremented) vs (shared latest)
                # This is safer than just setting it.
                self.success_count = max(self.success_count, success)
            if fail is not None: 
                self.fail_count = max(self.fail_count, fail)
            if devices is not None: self.connected_devices = devices
            if hero_found is not None: self.success_count += hero_found
            if hero_not_found is not None: self.fail_count += hero_not_found
            self.save_shared()
    
    def update_device(self, device_serial, status):
        """Update device status and sync with shared file"""
        self.load_shared() # Pull latest from others first
        with self.lock:
            self.device_statuses[device_serial] = status
            self.save_shared() # Save merged state back
    
    def update_hero(self, hero_name, count=1):
        """Update hero found count and sync"""
        self.load_shared() # Pull latest first
        with self.lock:
            if hero_name not in self.hero_found_list:
                self.hero_found_list[hero_name] = 0
            self.hero_found_list[hero_name] += count
            self.save_shared()

    def get_hero_combo_stats(self):
        self.load_shared() # Always refresh before getting
        with self.lock:
            return dict(self.hero_found_list)

ui_stats = SimpleUIStats()
GUI_INSTANCE = None
_PUT_FAIL_STREAK = {}   # device_id -> consecutive Injection FAILED count (auto-recover stuck emu)

if GUI_AVAILABLE:
    class CollabConfigWindow(ctk.CTkToplevel):
        def __init__(self, parent):
            super().__init__(parent)
            self.title("âš™ Config Settings")
            self.geometry("350x660")
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
            self.add_switch("Check Ruby/Ticket", "check_ruby_ticket")
            self.add_switch("OCR Scans Debug (Images)", "debug_ocr")
            self.add_switch("Skip Kaiby Shop (3s)", "kaibyskip")
            self.add_switch("Force Kaiby Check (Proceed)", "kaibycheck")
            self.add_switch("âš¡ Minitouch (à¸à¸”à¹€à¸£à¹‡à¸§)", "minitouch")
            self.add_switch("ðŸ§  à¸ˆà¸³à¸•à¸³à¹à¸«à¸™à¹ˆà¸‡à¸›à¸¸à¹ˆà¸¡ (Pos Cache)", "pos_cache")

            # Thread delay entry
            delay_frame = ctk.CTkFrame(self, fg_color="transparent")
            delay_frame.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(delay_frame, text="Thread Delay (sec):").pack(side="left")
            self.ent_delay = ctk.CTkEntry(delay_frame, width=60)
            self.ent_delay.insert(0, str(config.get("thread_delay", 5)))
            self.ent_delay.pack(side="right")

            scan_frame = ctk.CTkFrame(self, fg_color="transparent")
            scan_frame.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(scan_frame, text="à¸ªà¹à¸à¸™ error à¸—à¸¸à¸à¸à¸µà¹ˆà¸§à¸´ (0=à¸—à¸¸à¸à¹€à¸Ÿà¸£à¸¡):").pack(side="left")
            self.ent_scan = ctk.CTkEntry(scan_frame, width=60)
            self.ent_scan.insert(0, str(config.get("scan_interval", 1.0)))
            self.ent_scan.pack(side="right")

            loop_frame = ctk.CTkFrame(self, fg_color="transparent")
            loop_frame.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(loop_frame, text="à¸«à¸™à¹ˆà¸§à¸‡à¸¥à¸¹à¸›à¸«à¸²à¸›à¸¸à¹ˆà¸¡ (à¸§à¹ˆà¸²à¸‡=à¸„à¹ˆà¸²à¹€à¸”à¸´à¸¡):").pack(side="left")
            self.ent_loop = ctk.CTkEntry(loop_frame, width=60)
            if config.get("loop_delay") is not None:
                self.ent_loop.insert(0, str(config.get("loop_delay")))
            self.ent_loop.pack(side="right")

            stagger_frame = ctk.CTkFrame(self, fg_color="transparent")
            stagger_frame.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(stagger_frame, text="à¹€à¸£à¸´à¹ˆà¸¡à¸—à¸µà¸¥à¸°à¸ˆà¸­ à¸«à¸™à¹ˆà¸§à¸‡à¸à¸µà¹ˆà¸§à¸´ (à¸à¸±à¸™à¹€à¸™à¹‡à¸•à¸”à¸¶à¸‡):").pack(side="left")
            self.ent_stagger = ctk.CTkEntry(stagger_frame, width=60)
            self.ent_stagger.insert(0, str(config.get("start_stagger", 5.0)))
            self.ent_stagger.pack(side="right")

            ctk.CTkButton(self, text="ðŸ’¾ Save Changes", command=self.save_config, fg_color="#2cc985", hover_color="#229f69", height=32).pack(pady=20)
            
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

            try:
                config["scan_interval"] = float(self.ent_scan.get())
            except:
                pass

            # blank = à¹„à¸¡à¹ˆ override à¸›à¸¥à¹ˆà¸­à¸¢à¹ƒà¸«à¹‰à¹à¸•à¹ˆà¸¥à¸°à¸¥à¸¹à¸›à¹ƒà¸Šà¹‰à¸„à¹ˆà¸²à¹€à¸”à¸´à¸¡à¸‚à¸­à¸‡à¸¡à¸±à¸™
            loop_txt = self.ent_loop.get().strip()
            if not loop_txt:
                config["loop_delay"] = None
            else:
                try:
                    config["loop_delay"] = float(loop_txt)
                except:
                    pass

            try:
                config["start_stagger"] = max(0.0, float(self.ent_stagger.get()))
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
            self.title("ðŸ¦¸ Hero Folders")
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
                    btn = ctk.CTkButton(self.scroll_frame, text=f"ðŸ“ {folder}", fg_color="#2a3a5c", height=28, anchor="w",
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
            
            ctk.CTkButton(self, text="â†º", width=22, height=20, font=ctk.CTkFont(size=11, weight="bold"), fg_color="#e53935").pack(side="right", padx=2)

        def update_state(self, status=None, **kwargs):
            if status:
                color_map = {'working': "#4caf50", 'waiting': "#ff9800", 'error': "#e53935", 'idle': "#888"}
                self.lbl_status.configure(text=status.upper(), text_color=color_map.get(status, "#888"))

    class ConsoleRedirector:
        """Redirect print() output to both console AND GUI log area"""
        def __init__(self, original_stdout, log_queue):
            self.original_stdout = original_stdout
            self.log_queue = log_queue
        
        def write(self, message):
            if self.original_stdout:
                self.original_stdout.write(message)
            # Only queue non-empty, non-newline messages
            if message and message.strip():
                try:
                    self.log_queue.put_nowait(message.strip())
                except:
                    pass
        
        def flush(self):
            if self.original_stdout:
                self.original_stdout.flush()

    class ModernBotGUI(ctk.CTk):
        def __init__(self, devices, args):
            super().__init__()
            global GUI_INSTANCE
            GUI_INSTANCE = self
            
            self.title("Ranger+Gear")
            self.geometry("620x530")
            self.devices = devices
            self.args = args
            self.bot_threads = []
            self.device_monitors = {}
            self.hero_stats_labels = {}
            self.hero_rows = {}
            self.hero_filter_text = ""
            self.is_started = False
            
            self.setup_ui()
            
            # Setup console redirect to GUI log
            # à¸„à¸£à¸­à¸š sys.stdout "à¸•à¸±à¸§à¸›à¸±à¸ˆà¸ˆà¸¸à¸šà¸±à¸™" (DeviceLogTee) à¹„à¸¡à¹ˆà¹ƒà¸Šà¹ˆ sys.__stdout__
            # à¹„à¸¡à¹ˆà¸‡à¸±à¹‰à¸™à¸•à¸±à¸§à¹€à¸à¹‡à¸š log à¸£à¸²à¸¢ device à¸ˆà¸°à¹‚à¸”à¸™à¸–à¸­à¸”à¸­à¸­à¸à¸—à¸±à¸™à¸—à¸µà¸—à¸µà¹ˆ GUI à¹€à¸›à¸´à¸”
            self._log_queue = queue.Queue()
            sys.stdout = ConsoleRedirector(sys.stdout, self._log_queue)
            
            # Handle window close
            self.protocol("WM_DELETE_WINDOW", self.on_closing)
            
            # Use after to start the stats loop without blocking the constructor
            self.after(100, self.update_realtime_stats)
            self.after(100, self.process_log_queue)
            
            # Ensure window is visible
            self.deiconify()
            self.focus_force()
            print("[GUI] Launched Successfully. Waiting for manual start.")
            
            if getattr(self.args, 'no_start', False):
                print("[GUI] Monitor mode active (No internal threads).")
                self.lbl_auto_start.configure(text="[ DASHBOARD MODE ]", text_color="#ffae42")
            else:
                self.lbl_auto_start.configure(text="[ WAITING FOR START ]", text_color="#aaaaaa")
                # auto_start à¹ƒà¸™ config = 1 -> à¸à¸” START à¹ƒà¸«à¹‰à¹€à¸­à¸‡à¸«à¸¥à¸±à¸‡ GUI à¸‚à¸¶à¹‰à¸™ 2 à¸§à¸´
                # (à¸•à¸±à¹‰à¸‡à¹ƒà¸™ ranger-gear_config.json, à¸„à¹ˆà¸²à¹€à¸£à¸´à¹ˆà¸¡à¸•à¹‰à¸™ 0 = à¸£à¸­à¸à¸”à¹€à¸­à¸‡)
                if config.get("auto_start", 0):
                    print("[GUI] auto_start=1 - à¸ˆà¸°à¹€à¸£à¸´à¹ˆà¸¡à¸šà¸­à¸—à¸­à¸±à¸•à¹‚à¸™à¸¡à¸±à¸•à¸´à¹ƒà¸™ 2 à¸§à¸´à¸™à¸²à¸—à¸µ")
                    self.lbl_auto_start.configure(text="[ AUTO-START IN 2s ]", text_color="#ff9800")
                    self.after(2000, self.start_bot)

            # Initialize cached stats and start background thread to offload disk I/O from Main Thread
            self.qsize = 0
            self.bg_stats_thread = threading.Thread(target=self._bg_stats_counter_loop, daemon=True)
            self.bg_stats_thread.start()

        def _bg_stats_counter_loop(self):
            while True:
                try:
                    # à¸™à¸±à¸šà¸—à¸¸à¸à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸„à¸´à¸§ + à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸¢à¹ˆà¸­à¸¢ à¹ƒà¸«à¹‰à¸•à¸£à¸‡à¸à¸±à¸šà¸—à¸µà¹ˆ _get_next_available_file() à¸«à¸¢à¸´à¸šà¹„à¸”à¹‰à¸ˆà¸£à¸´à¸‡
                    qsize = 0
                    for source_folder in queue_folder_paths():
                        if not os.path.exists(source_folder):
                            continue
                        for _root, _dirs, _files in os.walk(source_folder):
                            qsize += len([f for f in _files if f.lower().endswith(".xml")])
                    self.qsize = qsize
                except Exception as e:
                    print(f"[GUI BG] Stats helper error: {e}")
                time.sleep(5)  # Scan every 5 seconds

        def setup_ui(self):
            # 1. TOP TOOLBAR
            toolbar = ctk.CTkFrame(self, height=40, fg_color="#333333", corner_radius=0)
            toolbar.pack(fill="x")
            toolbar.pack_propagate(False)
            
            self.lbl_status = ctk.CTkLabel(toolbar, text=f"   â— ONLINE ({len(self.devices)})", font=ctk.CTkFont(size=12, weight="bold"), text_color="#4caf50")
            self.lbl_status.pack(side="left", padx=5)

            self.btn_start = ctk.CTkButton(toolbar, text="â–¶ START", font=ctk.CTkFont(size=12, weight="bold"), width=80, height=24, fg_color="#e53935", hover_color="#c62828", command=self.start_bot)
            self.btn_start.pack(side="left", padx=10)
            
            self.lbl_auto_start = ctk.CTkLabel(toolbar, text="[ WAITING FOR START ]", font=ctk.CTkFont(size=10, weight="bold"), text_color="#aaaaaa")
            self.lbl_auto_start.pack(side="left", padx=5)
            
            # Stats on Toolbar (right)
            counter_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
            counter_frame.pack(side="right", padx=8)
            
            self.lbl_succ_count = ctk.CTkLabel(counter_frame, text="âœ… 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#4caf50")
            self.lbl_succ_count.pack(side="right", padx=6)
            
            self.lbl_fail_count = ctk.CTkLabel(counter_frame, text="âŒ 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#ff5555")
            self.lbl_fail_count.pack(side="right", padx=6)
            
            self.lbl_file_count = ctk.CTkLabel(counter_frame, text="ðŸ“ 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa")
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
            
            hero_header = ctk.CTkFrame(right_frame, fg_color="#383838", corner_radius=0, height=56)
            hero_header.pack(fill="x")
            hero_header.pack_propagate(False)
            
            title_row = ctk.CTkFrame(hero_header, fg_color="transparent", height=28)
            title_row.pack(fill="x")
            ctk.CTkLabel(title_row, text="   ðŸ† HEROES FOUND", font=ctk.CTkFont(size=11, weight="bold"), text_color="#f2c94c", anchor="w").pack(side="left")
            self.lbl_filter_count = ctk.CTkLabel(title_row, text="Filtered: 0", font=ctk.CTkFont(size=10), text_color="#aaaaaa")
            self.lbl_filter_count.pack(side="right", padx=10)
            
            # Filter Entry
            filter_frame = ctk.CTkFrame(hero_header, fg_color="transparent", height=24)
            filter_frame.pack(fill="x", padx=5, pady=2)
            self.ent_filter = ctk.CTkEntry(filter_frame, placeholder_text="ðŸ” Search heroes or gear (e.g. lapel)...", font=ctk.CTkFont(size=11), height=22, fg_color="#1e1e1e", border_width=1)
            self.ent_filter.pack(fill="x", expand=True)
            self.ent_filter.bind("<KeyRelease>", lambda e: self.on_filter_changed())
            
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
            backup_folder = queue_folder_paths()[0]   # à¸›à¸¸à¹ˆà¸¡ Backup à¹€à¸›à¸´à¸”à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸„à¸´à¸§
            heroes_folder = os.path.join(base_path, "backup-id")
            
            ctk.CTkButton(bottom_bar, text="ðŸ”Œ Connect Missing", width=85, height=22, font=ctk.CTkFont(size=10), fg_color="#4caf50", command=self.connect_missing_devices).pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="âš™ Config", width=70, height=22, font=ctk.CTkFont(size=10), fg_color="#555555", command=self.open_config).pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="ðŸ“ Backup", width=70, height=22, font=ctk.CTkFont(size=10), fg_color="#555555", command=lambda: subprocess.Popen(f'explorer "{backup_folder}"')).pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="ðŸ¦¸ Heroes", width=70, height=22, font=ctk.CTkFont(size=10), fg_color="#555555", command=lambda: subprocess.Popen(f'explorer "{heroes_folder}"')).pack(side="left", padx=3, pady=4)
            ctk.CTkLabel(bottom_bar, text="v3.2.0", font=ctk.CTkFont(size=10), text_color="#888888").pack(side="right", padx=8)

        def connect_missing_devices(self):
            """Scan for missing adb connections and start them dynamically"""
            self.log("INFO", "Scanning for missing emulators...")
            # Automatically perform port scan before checking devices
            connect_known_ports()
            
            current_devices = get_connected_devices()
            emulator_devices = [d for d in current_devices if d.startswith("emulator-") or d.startswith("127.0.0.1:")]
            
            new_count = 0
            for dev in emulator_devices:
                if dev not in self.devices:
                    new_count += 1
                    self.devices.append(dev)
                    # Add to UI
                    m = DeviceMonitorWidget(self.dev_scroll, dev, len(self.devices))
                    m.pack(fill="x", pady=1)
                    self.device_monitors[dev] = m
                    
                    # Start bot thread
                    if getattr(self, 'is_started', False) and not getattr(self.args, 'no_start', False):
                        bot = RangerGearBot(dev, self.args)
                        bot.start()
                        self.bot_threads.append(bot)
                    self.log("SUCCESS", f"Connected new device: {dev}")
            
            if new_count > 0:
                self.lbl_status.configure(text=f"   â— ONLINE ({len(self.devices)})")
            else:
                self.log("INFO", "No new devices found.")

        def log(self, level, message): 
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"[{ts}] {message}\n")
            # Keep log area from growing too large (max 500 lines)
            line_count = int(self.log_text.index('end-1c').split('.')[0])
            if line_count > 500:
                self.log_text.delete('1.0', f'{line_count - 400}.0')
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

        def process_log_queue(self):
            """Process pending log messages from bot threads"""
            try:
                max_per_tick = 20  # Process up to 20 messages per tick to avoid freezing
                count = 0
                while not self._log_queue.empty() and count < max_per_tick:
                    msg = self._log_queue.get_nowait()
                    self.log("BOT", msg)
                    count += 1
            except:
                pass
            self.after(200, self.process_log_queue)

        def _start_single_bot(self, device_id):
            bot = RangerGearBot(device_id, self.args)
            bot._ready_q = getattr(self, "_ready_q", None)
            bot.start()
            self.bot_threads.append(bot)
            self.log("INFO", f"ðŸš€ Started bot on {device_id}")

        def _ramp_tick(self):
            """à¸›à¸¥à¹ˆà¸­à¸¢à¸šà¸­à¸—à¸•à¸±à¸§à¸–à¸±à¸”à¹„à¸›à¸—à¸±à¸™à¸—à¸µà¸—à¸µà¹ˆà¸•à¸±à¸§à¸à¹ˆà¸­à¸™à¸«à¸™à¹‰à¸²à¸žà¸£à¹‰à¸­à¸¡ - à¹„à¸¡à¹ˆà¸™à¸­à¸™à¸£à¸­à¹€à¸§à¸¥à¸²à¹€à¸›à¸¥à¹ˆà¸² à¹†

            à¹€à¸”à¸´à¸¡à¸ˆà¸­à¸‡à¹€à¸§à¸¥à¸²à¹„à¸§à¹‰à¸¥à¹ˆà¸§à¸‡à¸«à¸™à¹‰à¸²à¸•à¸²à¸¢à¸•à¸±à¸§ (i // batch * delay) à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸—à¸µà¹ˆà¸žà¸£à¹‰à¸­à¸¡à¹€à¸£à¹‡à¸§
            à¸à¹‡à¸¢à¸±à¸‡à¸•à¹‰à¸­à¸‡à¸£à¸­à¸ˆà¸™à¸„à¸£à¸šà¹€à¸§à¸¥à¸²à¸­à¸¢à¸¹à¹ˆà¸”à¸µ à¸•à¸­à¸™à¸™à¸µà¹‰ delay à¹€à¸«à¸¥à¸·à¸­à¹€à¸›à¹‡à¸™à¹à¸„à¹ˆà¹€à¸žà¸”à¸²à¸™à¸à¸±à¸™à¸„à¹‰à¸²à¸‡
            """
            # 1) à¹€à¸à¹‡à¸šà¸ªà¸±à¸à¸à¸²à¸“ "à¸žà¸£à¹‰à¸­à¸¡à¹à¸¥à¹‰à¸§" à¸—à¸µà¹ˆà¸šà¸­à¸—à¸ªà¹ˆà¸‡à¸à¸¥à¸±à¸šà¸¡à¸²
            while True:
                try:
                    dev = self._ready_q.get_nowait()
                except Exception:
                    break
                if self._starting.pop(dev, None) is not None:
                    self.log("SUCCESS", f"âœ“ {dev} à¸žà¸£à¹‰à¸­à¸¡ (à¹€à¸«à¸¥à¸·à¸­à¸£à¸­à¸„à¸´à¸§ {len(self._pending)})")
            # 2) à¸•à¸±à¸§à¸—à¸µà¹ˆà¹€à¸‡à¸µà¸¢à¸šà¹€à¸à¸´à¸™à¹€à¸žà¸”à¸²à¸™ à¹„à¸¡à¹ˆà¸£à¸­à¹à¸¥à¹‰à¸§ (emulator à¸„à¹‰à¸²à¸‡/à¸¢à¸±à¸‡à¸šà¸¹à¸•à¹„à¸¡à¹ˆà¹€à¸ªà¸£à¹‡à¸ˆ)
            now = time.time()
            for dev, t0 in list(self._starting.items()):
                if now - t0 > self._start_timeout:
                    self._starting.pop(dev, None)
                    self.log("WARN", f"{dev} à¹„à¸¡à¹ˆà¸•à¸­à¸šà¹ƒà¸™ {self._start_timeout:.0f}s - à¸›à¸¥à¹ˆà¸­à¸¢à¸•à¸±à¸§à¸–à¸±à¸”à¹„à¸›à¹€à¸¥à¸¢")
            # 3) à¸›à¸¥à¹ˆà¸­à¸¢à¸•à¸±à¸§à¸–à¸±à¸”à¹„à¸›: à¸•à¹‰à¸­à¸‡à¸¡à¸µà¸ªà¸¥à¹‡à¸­à¸•à¸§à¹ˆà¸²à¸‡ + à¸œà¹ˆà¸²à¸™à¹€à¸§à¸¥à¸²à¸«à¸™à¹ˆà¸§à¸‡à¸‚à¸±à¹‰à¸™à¸•à¹ˆà¸³ (à¸à¸±à¸™à¸«à¸¥à¸²à¸¢à¸ˆà¸­à¸¢à¸´à¸‡à¹€à¸™à¹‡à¸•à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™)
            while self._pending and len(self._starting) < self._slots:
                now = time.time()
                if getattr(self, "_stagger", 0) > 0 and (now - self._last_start_ts) < self._stagger:
                    break   # à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸–à¸¶à¸‡à¹€à¸§à¸¥à¸² à¸£à¸­ tick à¸–à¸±à¸”à¹„à¸› (poll à¸—à¸¸à¸ 200ms)
                dev = self._pending.pop(0)
                self._starting[dev] = now
                self._last_start_ts = now
                self._start_single_bot(dev)
                self.log("INFO", f"â–¶ à¹€à¸£à¸´à¹ˆà¸¡à¸ˆà¸­ {dev} (à¹€à¸«à¸¥à¸·à¸­à¸„à¸´à¸§ {len(self._pending)})")
            if self._pending or self._starting:
                self.after(200, self._ramp_tick)
            else:
                self.log("SUCCESS", f"à¸›à¸¥à¹ˆà¸­à¸¢à¸šà¸­à¸—à¸„à¸£à¸š {len(self.devices)} à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¹à¸¥à¹‰à¸§ "
                                    f"(à¹ƒà¸Šà¹‰à¹€à¸§à¸¥à¸² {time.time() - self._ramp_started:.0f}s)")


        def start_bot(self):
            if getattr(self, 'is_started', False):
                self.log("WARN", "Bot is already running.")
                return
            self.is_started = True
            if hasattr(self, 'btn_start'):
                self.btn_start.configure(state="disabled", fg_color="#555555", text="â³ RUNNING")
            self.lbl_auto_start.configure(text="[ BOT IS RUNNING ]", text_color="#4caf50")
            
            # à¸›à¸¥à¹ˆà¸­à¸¢à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™ start_batch à¸•à¸±à¸§ à¹à¸¥à¹‰à¸§à¹€à¸•à¸´à¸¡à¸•à¸±à¸§à¸–à¸±à¸”à¹„à¸› "à¸—à¸±à¸™à¸—à¸µà¸—à¸µà¹ˆà¸•à¸±à¸§à¸à¹ˆà¸­à¸™à¸«à¸™à¹‰à¸²à¸žà¸£à¹‰à¸­à¸¡"
            # à¹„à¸¡à¹ˆà¸«à¸™à¹ˆà¸§à¸‡à¸•à¸²à¸¡à¸™à¸²à¸¬à¸´à¸à¸²à¸­à¸µà¸ - thread_delay à¹€à¸«à¸¥à¸·à¸­à¹€à¸›à¹‡à¸™à¸à¸²à¸™à¸‚à¸­à¸‡à¹€à¸žà¸”à¸²à¸™à¸à¸±à¸™à¸„à¹‰à¸²à¸‡à¹€à¸—à¹ˆà¸²à¸™à¸±à¹‰à¸™
            self._ready_q = queue.Queue()
            self._pending = list(self.devices)
            self._starting = {}
            self._slots = max(1, int(config.get("start_batch", 1)))
            self._stagger = max(0.0, float(config.get("start_stagger", 5.0)))
            self._last_start_ts = 0.0   # 0 = à¸ˆà¸­à¹à¸£à¸à¹€à¸£à¸´à¹ˆà¸¡à¹„à¸”à¹‰à¸—à¸±à¸™à¸—à¸µ
            self._start_timeout = float(config.get("start_timeout", float(config.get("thread_delay", 5)) * 4))
            self._ramp_started = time.time()
            self.log("INFO", f"Starting {len(self._pending)} Bot Threads: à¹€à¸£à¸´à¹ˆà¸¡à¸—à¸µà¸¥à¸° {self._slots} à¸ˆà¸­ "
                             f"à¸«à¸™à¹ˆà¸§à¸‡ {self._stagger:.0f}s/à¸ˆà¸­ à¸à¸±à¸™à¹€à¸™à¹‡à¸•à¸”à¸¶à¸‡ (à¹€à¸žà¸”à¸²à¸™ {self._start_timeout:.0f}s/à¸ˆà¸­)")
            self._ramp_tick()

        def on_closing(self):
            if messagebox.askokcancel("Quit", "à¸„à¸¸à¸“à¸•à¹‰à¸­à¸‡à¸à¸²à¸£à¸«à¸¢à¸¸à¸”à¸šà¸­à¸—à¹à¸¥à¸°à¸›à¸´à¸”à¹‚à¸›à¸£à¹à¸à¸£à¸¡à¹ƒà¸Šà¹ˆà¸«à¸£à¸·à¸­à¹„à¸¡à¹ˆ?\n(à¸ˆà¸°à¸—à¸³à¸à¸²à¸£ Kill ADB à¹à¸¥à¸° Python à¸—à¸±à¹‰à¸‡à¸«à¸¡à¸”)"):
                print("[GUI] Shutting down... Killing background processes.")
                try:
                    # Kill ADB and Python processes on Windows
                    if os.name == 'nt':
                        subprocess.run("taskkill /F /IM adb.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        subprocess.run("taskkill /F /IM python.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except:
                    pass
                sys.exit(0)

        def update_realtime_stats(self):
            try:
                # Load shared stats from other processes
                ui_stats.load_shared()
                
                with ui_stats.lock:
                    # Get cached file count from background thread
                    qsize = getattr(self, "qsize", 0)
                    
                    self.lbl_file_count.configure(text=f"ðŸ“ {qsize}")
                    self.lbl_succ_count.configure(text=f"âœ… {ui_stats.success_count}")
                    self.lbl_fail_count.configure(text=f"âŒ {ui_stats.fail_count}")
                    
                    for dev, stat in ui_stats.device_statuses.items():
                        if dev in self.device_monitors:
                            self.device_monitors[dev].update_state(status=stat.get('status'))
                    
                    hero_raw_data = ui_stats.get_hero_combo_stats()
                    hero_data = hero_raw_data.copy()
                    
                    # 1. Handle Login Failures separately from Scan Failures
                    login_fail_count = ui_stats.fail_count
                    if login_fail_count > 0:
                        hero_data["âŒ à¹€à¸‚à¹‰à¸²à¹„à¸¡à¹ˆà¹„à¸”à¹‰ (Login Failed)"] = login_fail_count
                    
                    # 2. Handle "Success but No Hero/Gear Found"
                    not_found_success = hero_data.pop("à¹„à¸¡à¹ˆà¹€à¸ˆà¸­", 0)
                    if not_found_success > 0:
                        hero_data["ðŸ” à¸ªà¹à¸à¸™à¹„à¸¡à¹ˆà¹€à¸ˆà¸­ (Not Found)"] = not_found_success
                    
                    for hero, count in hero_data.items():
                        if hero not in self.hero_stats_labels:
                            # Color coding: Red for failures/not found, Green for success
                            is_error_row = any(x in hero for x in ["à¹€à¸‚à¹‰à¸²à¹„à¸¡à¹ˆà¹„à¸”à¹‰", "à¸ªà¹à¸à¸™à¹„à¸¡à¹ˆà¹€à¸ˆà¸­"])
                            self.add_hero_row(hero, is_error_row)
                        
                        self.hero_stats_labels[hero].configure(text=str(count))
                    
                    # Explicitly hide old "à¹„à¸¡à¹ˆà¹€à¸ˆà¸­" or "âŒ à¹„à¸¡à¹ˆà¹€à¸ˆà¸­" rows if they exist from previous versions
                    for old_key in ["à¹„à¸¡à¹ˆà¹€à¸ˆà¸­", "âŒ à¹„à¸¡à¹ˆà¹€à¸ˆà¸­"]:
                        if old_key in self.hero_rows:
                            self.hero_rows[old_key].pack_forget()
                    
                    # Update Filter
                    self.filter_heroes()
            except Exception as e:
                print(f"[GUI] Update error: {e}")
            
            self.after(500, self.update_realtime_stats)

        def on_filter_changed(self):
            self.hero_filter_text = self.ent_filter.get().lower()
            self.filter_heroes()

        def filter_heroes(self):
            total_filtered = 0
            for hero, row in self.hero_rows.items():
                if not self.hero_filter_text or self.hero_filter_text in hero.lower():
                    row.pack(fill="x", pady=1)
                    # Get count from label text
                    try:
                        count = int(self.hero_stats_labels[hero].cget("text"))
                        total_filtered += count
                    except: pass
                else:
                    row.pack_forget()
            
            if hasattr(self, 'lbl_filter_count'):
                self.lbl_filter_count.configure(text=f"Filtered: {total_filtered}")


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
            self.hero_rows[hero_name] = row

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
    "ocr_region": {"x": 463, "y": 153, "w": 397, "h": 321},
    "check_ruby_ticket": 0,
    # Speed options (see touch_helper.py)
    "minitouch": 0,          # 1 = tap via minitouch socket instead of `adb shell input tap`
    "pos_cache": 1,          # 1 = remember where each button was found, re-check only that spot
    "pos_cache_margin": 12,  # px of slack around the remembered spot
    "scan_interval": 1.0,    # sec between full popup/error sweeps (0 = every frame, old behaviour)
    "loop_delay": None       # override the wait-loop poll delay; None = each loop's own default
}

adb_path = "adb"

# EasyOCR reader - loaded once globally
_ocr_reader = None
_ocr_lock = threading.Lock()      # Thread-safe OCR init
_ocr_run_lock = threading.Lock()  # Serialize readtext à¸à¸±à¸™ CPU à¸•à¸±à¸™à¸•à¸­à¸™à¸£à¸±à¸™à¸«à¸¥à¸²à¸¢à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™

# Guards the one-time minitouch startup. Module-level on purpose: bot instances
# must stay picklable for the multiprocessing variant of this bot family.
_minitouch_init_lock = threading.Lock()

def get_ocr_reader():
    """Get or create EasyOCR reader (singleton, thread-safe)"""
    global _ocr_reader
    if _ocr_reader is None:
        with _ocr_lock:
            if _ocr_reader is None:
                import easyocr
                # à¸ˆà¸³à¸à¸±à¸” PyTorch à¹ƒà¸«à¹‰à¹ƒà¸Šà¹‰ 1 thread/à¸à¸²à¸£à¸­à¹ˆà¸²à¸™ à¸à¸±à¸™ CPU oversubscribe à¸•à¸­à¸™à¸£à¸±à¸™à¸«à¸¥à¸²à¸¢à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡
                try:
                    import torch
                    torch.set_num_threads(1)
                except Exception:
                    pass
                print("[INFO] Loading EasyOCR model (first time only)...")
                _ocr_reader = easyocr.Reader(['en'], gpu=False)
                print("[OK] EasyOCR model loaded!")
    return _ocr_reader


_config_sig = None


def queue_folder_paths():
    """à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸„à¸´à¸§à¸—à¸±à¹‰à¸‡à¸«à¸¡à¸”à¸•à¸²à¸¡ config - à¹ƒà¸«à¹‰à¸•à¸±à¸§à¸™à¸±à¸šà¸šà¸™à¸ˆà¸­à¸à¸±à¸šà¸—à¸µà¹ˆà¸šà¸­à¸—à¸«à¸¢à¸´à¸šà¸ˆà¸£à¸´à¸‡à¸•à¸£à¸‡à¸à¸±à¸™à¹€à¸ªà¸¡à¸­"""
    folders = config.get("queue_folders") or ["backup"]
    if isinstance(folders, str):
        folders = [folders]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return [os.path.join(script_dir, str(f)) for f in folders]


# à¸ˆà¸³à¸à¸±à¸”à¸ˆà¸³à¸™à¸§à¸™à¸ˆà¸­à¸—à¸µà¹ˆà¸ªà¹ˆà¸‡à¹„à¸Ÿà¸¥à¹Œà¹€à¸‚à¹‰à¸²à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™ - à¸«à¸¥à¸²à¸¢à¸ˆà¸­à¸¢à¸´à¸‡à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™à¸„à¸·à¸­à¸•à¹‰à¸™à¹€à¸«à¸•à¸¸ "à¹„à¸Ÿà¸¥à¹Œà¹€à¸‚à¹‰à¸²à¹„à¸¡à¹ˆà¹„à¸”à¹‰"
_inject_sem = None
_inject_sem_lock = threading.Lock()


@contextlib.contextmanager
def _inject_gate():
    """à¸„à¸´à¸§à¸ªà¹ˆà¸‡à¹„à¸Ÿà¸¥à¹Œ: à¹ƒà¸«à¹‰à¸ªà¹ˆà¸‡à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™à¹„à¸”à¹‰à¹„à¸¡à¹ˆà¹€à¸à¸´à¸™ config "inject_max_concurrent" (0 = à¹„à¸¡à¹ˆà¸ˆà¸³à¸à¸±à¸”)"""
    global _inject_sem
    n = int(config.get("inject_max_concurrent", 2) or 0)
    if n <= 0:
        yield
        return
    with _inject_sem_lock:
        if _inject_sem is None or getattr(_inject_sem, "_lgr_n", None) != n:
            _inject_sem = threading.BoundedSemaphore(n)
            _inject_sem._lgr_n = n
        sem = _inject_sem
    sem.acquire()
    try:
        yield
    finally:
        try: sem.release()
        except ValueError: pass

_configmain_sig = None


def load_config(quiet=False):
    """quiet=True -> à¸žà¸´à¸¡à¸žà¹Œà¹€à¸‰à¸žà¸²à¸°à¸•à¸­à¸™à¹„à¸Ÿà¸¥à¹Œ config à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™à¸ˆà¸£à¸´à¸‡

    run() à¹€à¸£à¸µà¸¢à¸à¸Ÿà¸±à¸‡à¸à¹Œà¸Šà¸±à¸™à¸™à¸µà¹‰à¸—à¸¸à¸à¸§à¸´à¸™à¸²à¸—à¸µ à¹€à¸”à¸´à¸¡à¸žà¸´à¸¡à¸žà¹Œà¸—à¸¸à¸à¸„à¸£à¸±à¹‰à¸‡à¸ˆà¸™ log à¸à¸¥à¸²à¸¢à¹€à¸›à¹‡à¸™
    [CONFIG] Base Loaded à¹„à¸¥à¹ˆà¸¢à¸²à¸§ à¸à¸¥à¸šà¸šà¸£à¸£à¸—à¸±à¸”à¸—à¸µà¹ˆà¸šà¸­à¸à¸ªà¸²à¹€à¸«à¸•à¸¸à¸ˆà¸£à¸´à¸‡à¸ˆà¸™à¹„à¸¥à¹ˆà¸›à¸±à¸à¸«à¸²à¹„à¸¡à¹ˆà¹„à¸”à¹‰
    """
    global config, _config_sig
    
    # Load ONLY main config from ranger-gear_config.json
    main_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ranger-gear_config.json")
    if os.path.exists(main_config_file):
        try:
            with open(main_config_file, 'r', encoding='utf-8') as f:
                raw = f.read()
            loaded = json.loads(raw)
            config.update(loaded)
            sig = hashlib.md5(raw.encode("utf-8")).hexdigest()
            if not quiet or sig != _config_sig:
                print(f"[CONFIG] Base Loaded: {main_config_file}")
            _config_sig = sig
        except Exception as e:
            print(f"[WARN] Error loading config: {e}")
    else:
        print(f"[WARN] Config not found: {main_config_file}")

    # à¸„à¹ˆà¸² WireGuard (wg_*) à¸­à¸¢à¸¹à¹ˆà¹ƒà¸™ configmain.json à¹€à¸«à¸¡à¸·à¸­à¸™ login.py (login.py à¹‚à¸«à¸¥à¸”à¹„à¸Ÿà¸¥à¹Œà¸™à¸µà¹‰à¸—à¸±à¸š ranger-gear_config.json)
    # à¸”à¸¶à¸‡à¸¡à¸²à¹€à¸‰à¸žà¸²à¸°à¸„à¸µà¸¢à¹Œ VPN/à¹€à¸™à¹‡à¸• - à¹„à¸¡à¹ˆà¹€à¸­à¸²à¸ªà¸§à¸´à¸•à¸Šà¹Œà¹‚à¸«à¸¡à¸”à¸­à¸·à¹ˆà¸™à¸‚à¸­à¸‡ login.py à¸¡à¸²à¸—à¸±à¸šà¸à¸²à¸£à¸—à¸³à¸‡à¸²à¸™à¸‚à¸­à¸‡ ranger-gear
    global _configmain_sig
    ui_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configmain.json")
    if os.path.exists(ui_config_file):
        try:
            with open(ui_config_file, 'r', encoding='utf-8') as f:
                raw = f.read()
            loaded = json.loads(raw)
            config.update({k: v for k, v in loaded.items()
                           if k.startswith("wg_")
                           or k.startswith("ip_meter")
                           or k in ("reset_network_on_start", "net_reset_wait", "block_log",
                                    "no_proxy_mode", "login_min_gap_sec")})
            sig = hashlib.md5(raw.encode("utf-8")).hexdigest()
            if not quiet or sig != _configmain_sig:
                print(f"[CONFIG] WG Settings Loaded: {ui_config_file}")
            _configmain_sig = sig
        except Exception as e:
            print(f"[WARN] Error loading configmain.json (wg_*): {e}")

    # wg_profile: à¸ªà¸¥à¸±à¸šà¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œ IP - à¸‚à¹‰à¸²à¸¡à¸–à¹‰à¸² wg_enabled=0 (à¹„à¸¡à¹ˆà¹€à¸ªà¸µà¸¢à¹€à¸§à¸¥à¸² startup à¸Ÿà¸£à¸µ)
    # KILL_VPN_HARDCODED=True -> à¸›à¸´à¸” VPN à¸–à¸²à¸§à¸£à¸—à¸±à¹ˆà¸§à¸—à¸±à¹‰à¸‡à¸à¸¹à¸‡ (à¸­à¹ˆà¸²à¸™à¹„à¸¡à¹ˆà¹€à¸­à¸²à¸„à¹ˆà¸²à¸ˆà¸²à¸ config remote)
    # no_proxy_mode=1 -> kill switch à¸Šà¸™à¸°à¸—à¸¸à¸ flag à¸­à¸·à¹ˆà¸™ (à¸£à¸§à¸¡ wg_enabled=1 à¸—à¸µà¹ˆà¸„à¹‰à¸²à¸‡à¸ˆà¸²à¸à¸£à¸­à¸šà¹€à¸à¹ˆà¸²)
    # use_host_vpn=1 -> à¸‚à¹‰à¸²à¸¡à¸—à¸±à¹‰à¸‡à¸«à¸¡à¸” (VPN à¸­à¸¢à¸¹à¹ˆà¸šà¸™ Windows host)
    if _no_proxy_mode():
        print("[CONFIG] no_proxy_mode / KILL_VPN=on - à¸‚à¹‰à¸²à¸¡ wg_profile/FORCE Proton/wg_gen à¸—à¸¸à¸à¸­à¸¢à¹ˆà¸²à¸‡ (à¹ƒà¸Šà¹‰ IP à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸•à¸£à¸‡ à¹†)")
    elif int(config.get("use_host_vpn", 0) or 0):
        print("[CONFIG] use_host_vpn=1 - à¸‚à¹‰à¸²à¸¡ wg_profile resolve + wg_gen (VPN à¸­à¸¢à¸¹à¹ˆà¸šà¸™ Windows host)")
    elif int(config.get("wg_enabled", 1) or 0):
        _wg_resolve_profile()
    else:
        print("[CONFIG] wg_enabled=0 - à¸‚à¹‰à¸²à¸¡ wg_profile resolve + wg_gen (à¹ƒà¸Šà¹‰ IP à¸‚à¸­à¸‡ PC à¸•à¸£à¸‡ à¹†)")


def _wg_resolve_profile():
    """à¸­à¹ˆà¸²à¸™ config['wg_profile'] -> à¸•à¸±à¹‰à¸‡ config['wg_dir']  (sync à¸à¸±à¸š login.py à¹€à¸›à¹Šà¸° à¹†)
    - string à¹€à¸”à¸µà¸¢à¸§: "ip-chan/main-1" -> wg_dir='wg/ip-chan/main-1'
    - list / comma: ["ip-chan/main-1","ip-chan/main-2"] -> à¸£à¸§à¸¡ .conf à¸—à¸¸à¸à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¹€à¸‚à¹‰à¸² wg/.pool/
      (blacklist/cooldown à¹€à¸‚à¸µà¸¢à¸™à¸—à¸µà¹ˆ pool - restart bot à¸à¹‡ rebuild à¹ƒà¸«à¹‰à¹ƒà¸«à¸¡à¹ˆ)

    wg_profile_clear_on_start=1 (default 1): à¸¥à¸š Windscribe-*.conf à¸—à¸¸à¸ sub + .pool/ + .blocked.json
      à¹€à¸à¹‡à¸šà¹€à¸‰à¸žà¸²à¸° key*.conf / template.conf (keypair à¸•à¹‰à¸™à¹à¸šà¸š) à¹à¸¥à¹‰à¸§à¹ƒà¸«à¹‰ wg_gen generate IP à¹ƒà¸«à¸¡à¹ˆà¸—à¸±à¹‰à¸‡à¸«à¸¡à¸”
    """
    prof = config.get("wg_profile", "")
    if isinstance(prof, (list, tuple)):
        profs = [str(p).strip() for p in prof if str(p).strip()]
    else:
        s = str(prof or "").strip()
        profs = [p.strip() for p in s.split(",") if p.strip()] if s else []
    if not profs:
        return
    script_dir = os.path.dirname(os.path.abspath(__file__))
    resolved = []
    for p in profs:
        for cand in (os.path.join("wg", p), p):
            if os.path.isdir(os.path.join(script_dir, cand)):
                resolved.append(cand.replace("\\", "/"))
                break
        else:
            print(f"[CONFIG] wg_profile='{p}' à¹„à¸¡à¹ˆà¸žà¸šà¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œ - à¸‚à¹‰à¸²à¸¡")
    if not resolved:
        print(f"[CONFIG] wg_profile: à¹„à¸¡à¹ˆà¸žà¸šà¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸—à¸µà¹ˆà¹ƒà¸Šà¹‰à¹„à¸”à¹‰à¹€à¸¥à¸¢ ({profs}) - à¹ƒà¸Šà¹‰ wg_dir='{config.get('wg_dir', 'wg')}' à¹€à¸”à¸´à¸¡")
        return

    # === FORCE Proton mode: à¸šà¸±à¸‡à¸„à¸±à¸šà¹ƒà¸Šà¹‰ Proton à¹€à¸—à¹ˆà¸²à¸™à¸±à¹‰à¸™ - à¸›à¸´à¸” wg_gen + clear_on_start à¸—à¸¸à¸à¸à¸£à¸“à¸µ
    forced = []
    if int(config.get("wg_auto_gen", 1) or 0):
        config["wg_auto_gen"] = 0
        forced.append("wg_auto_gen=0")
    if int(config.get("wg_profile_clear_on_start", 1) or 0):
        config["wg_profile_clear_on_start"] = 0
        forced.append("wg_profile_clear_on_start=0")
    if int(config.get("wg_clear_on_start", 1) or 0):
        config["wg_clear_on_start"] = 0
        forced.append("wg_clear_on_start=0")
    if float(config.get("wg_regen_every_min", 0) or 0) > 0:
        config["wg_regen_every_min"] = 0
        forced.append("wg_regen_every_min=0")
    if forced:
        print(f"[CONFIG] FORCE Proton mode - override: {', '.join(forced)}")
    else:
        print(f"[CONFIG] FORCE Proton mode - config already set")

    # === FORCE Proton: à¸¥à¸šà¹„à¸Ÿà¸¥à¹Œ .conf à¸—à¸µà¹ˆà¹„à¸¡à¹ˆà¹ƒà¸Šà¹ˆ proton-*.conf à¸­à¸­à¸à¸ˆà¸²à¸à¸—à¸¸à¸ sub-folder
    # (Windscribe/wg_gen à¸ªà¸£à¹‰à¸²à¸‡à¸—à¸´à¹‰à¸‡à¹„à¸§à¹‰à¸ˆà¸²à¸à¸£à¸­à¸šà¸à¹ˆà¸­à¸™ - à¸•à¹‰à¸­à¸‡à¹€à¸„à¸¥à¸µà¸¢à¸£à¹Œà¹€à¸žà¸·à¹ˆà¸­à¹„à¸¡à¹ˆà¹ƒà¸«à¹‰ bot à¹„à¸›à¹ƒà¸Šà¹‰)
    try:
        purged = 0
        for d in resolved:
            d_abs = os.path.join(script_dir, d)
            try:
                for f in os.listdir(d_abs):
                    low = f.lower()
                    if not low.endswith(".conf"):
                        continue
                    if low.startswith("proton-"):
                        continue        # à¹€à¸à¹‡à¸šà¹„à¸Ÿà¸¥à¹Œ Proton
                    try:
                        os.remove(os.path.join(d_abs, f))
                        purged += 1
                    except OSError:
                        pass
            except OSError:
                continue
        if purged:
            print(f"[CONFIG] FORCE Proton mode - à¸¥à¸š non-Proton .conf à¹€à¸à¹ˆà¸² {purged} à¹„à¸Ÿà¸¥à¹Œ (Windscribe/key*.conf)")
    except Exception as e:
        print(f"[CONFIG] FORCE Proton cleanup à¸¥à¹‰à¸¡à¹€à¸«à¸¥à¸§: {e}")

    # Auto-promote keypair.txt -> key.conf
    for d in resolved:
        d_abs = os.path.join(script_dir, d)
        try:
            files = os.listdir(d_abs)
        except OSError:
            continue
        has_conf = any(f.lower().endswith(".conf") for f in files)
        has_keypair_txt = "keypair.txt" in [f.lower() for f in files]
        if not has_conf and has_keypair_txt:
            src = os.path.join(d_abs, [f for f in files if f.lower() == "keypair.txt"][0])
            dst = os.path.join(d_abs, "key.conf")
            try:
                shutil.copy2(src, dst)
                print(f"[CONFIG] wg_profile: {d} à¹€à¸ˆà¸­ keypair.txt (à¹„à¸¡à¹ˆà¸¡à¸µ .conf) - copy à¹€à¸›à¹‡à¸™ key.conf à¹ƒà¸«à¹‰ wg_gen à¹ƒà¸Šà¹‰")
            except OSError as e:
                print(f"[CONFIG] wg_profile: {d} copy keypair.txt -> key.conf à¸¥à¹‰à¸¡à¹€à¸«à¸¥à¸§: {e}")

    # à¸¥à¸š IP à¹€à¸”à¸´à¸¡à¸—à¸¸à¸à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸à¹ˆà¸­à¸™ generate à¹ƒà¸«à¸¡à¹ˆ (à¹€à¸à¹‡à¸šà¹€à¸‰à¸žà¸²à¸° key*.conf / template.conf = keypair à¸•à¹‰à¸™à¹à¸šà¸š)
    if int(config.get("wg_profile_clear_on_start", 1) or 0):
        total_deleted = 0
        for d in resolved:
            d_abs = os.path.join(script_dir, d)
            try:
                for f in os.listdir(d_abs):
                    low = f.lower()
                    if not low.endswith(".conf"):
                        continue
                    if low.startswith("key") or low == "template.conf":
                        continue
                    try:
                        os.remove(os.path.join(d_abs, f))
                        total_deleted += 1
                    except OSError:
                        pass
            except OSError:
                pass
        for junk in (os.path.join(script_dir, "wg", ".pool"),
                     os.path.join(script_dir, "wg", ".blocked.json"),
                     os.path.join(script_dir, "wg", ".cooldown.json")):
            try:
                if os.path.isdir(junk):
                    for f in os.listdir(junk):
                        try:
                            os.remove(os.path.join(junk, f))
                        except OSError:
                            pass
                elif os.path.isfile(junk):
                    os.remove(junk)
            except OSError:
                pass
        print(f"[CONFIG] wg_profile_clear_on_start: à¸¥à¸š IP à¹€à¸à¹ˆà¸² {total_deleted} à¹„à¸Ÿà¸¥à¹Œ + .pool/ + blacklist - à¸ˆà¸° generate IP à¹ƒà¸«à¸¡à¹ˆà¸—à¸±à¹‰à¸‡à¸«à¸¡à¸”")
    if len(resolved) == 1:
        config["wg_dir"] = resolved[0]
        print(f"[CONFIG] wg_profile -> wg_dir='{resolved[0]}'")
        return
    pool = "wg/.pool"
    pool_abs = os.path.join(script_dir, pool)
    try:
        os.makedirs(pool_abs, exist_ok=True)
        for f in os.listdir(pool_abs):
            if f.lower().endswith(".conf"):
                try:
                    os.remove(os.path.join(pool_abs, f))
                except OSError:
                    pass
    except OSError:
        pass
    # wg_auto_gen=0 (Proton mode) -> à¸‚à¹‰à¸²à¸¡ pre-generate (wg_gen à¹ƒà¸Šà¹‰à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸à¸±à¸š Proton + à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¹€à¸•à¸´à¸¡)
    if int(config.get("wg_auto_gen", 1) or 0):
        try:
            import wg_gen
            _per = int(config.get("wg_per_machine", 15) or 15)
            for d in resolved:
                d_abs = os.path.join(script_dir, d)
                try:
                    n_cur = len([f for f in os.listdir(d_abs) if f.lower().endswith(".conf")])
                except OSError:
                    n_cur = 0
                if n_cur == 0:
                    print(f"[CONFIG] wg_profile: {d} à¹„à¸¡à¹ˆà¸¡à¸µà¹„à¸Ÿà¸¥à¹Œ .conf à¹€à¸¥à¸¢ - à¹‚à¸¢à¸™à¹„à¸Ÿà¸¥à¹Œà¸ˆà¸²à¸ Windscribe 1 à¹„à¸Ÿà¸¥à¹Œà¸¥à¸‡à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸™à¸µà¹‰")
                    continue
                if n_cur < _per:
                    print(f"[CONFIG] wg_profile: {d} à¸¡à¸µ {n_cur} à¹„à¸Ÿà¸¥à¹Œ (<{_per}) - generate à¹€à¸žà¸´à¹ˆà¸¡à¸ˆà¸²à¸ keypair à¸‚à¸­à¸‡ sub à¸™à¸µà¹‰")
                    wg_gen.generate(_per, config.get("wg_gen_countries") or None, d, 0, "", 0)
        except Exception as e:
            print(f"[CONFIG] wg_profile pre-generate à¸¥à¹‰à¸¡à¹€à¸«à¸¥à¸§: {e}")
    n = 0
    for d in resolved:
        d_abs = os.path.join(script_dir, d)
        try:
            for f in os.listdir(d_abs):
                if not f.lower().endswith(".conf"):
                    continue
                src = os.path.join(d_abs, f)
                prefix = d.replace("/", "__").replace("\\", "__")
                dst = os.path.join(pool_abs, f"{prefix}__{f}")
                try:
                    shutil.copy2(src, dst)
                    n += 1
                except OSError:
                    pass
        except OSError:
            pass
    config["wg_dir"] = pool
    print(f"[CONFIG] wg_profile -> à¸£à¸§à¸¡ {n} à¹„à¸Ÿà¸¥à¹Œà¸ˆà¸²à¸ {len(resolved)} à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œ ({', '.join(resolved)}) -> wg_dir='{pool}'")


# =========================================================
# WireGuard (VPN à¹à¸¢à¸à¸•à¹ˆà¸­à¸ˆà¸­) - à¸žà¸­à¸£à¹Œà¸•à¸¡à¸²à¸ˆà¸²à¸ login.py à¹ƒà¸«à¹‰à¸—à¸³à¸‡à¸²à¸™à¹€à¸«à¸¡à¸·à¸­à¸™à¸à¸±à¸™
# =========================================================
_real_sleep = time.sleep   # à¸žà¸±à¸à¸ˆà¸£à¸´à¸‡ (à¹„à¸¡à¹ˆà¸œà¹ˆà¸²à¸™à¸•à¸±à¸§à¸›à¸£à¸±à¸šà¸„à¸§à¸²à¸¡à¹€à¸£à¹‡à¸§) à¹ƒà¸«à¹‰à¹€à¸«à¸¡à¸·à¸­à¸™ login.py


# ============================================================
# IP-METER / NO-PROXY / LOGIN-PACE  - sync 100% à¸à¸±à¸š login.py
# configmain.json:
#   no_proxy_mode        1 = à¹ƒà¸Šà¹‰ IP à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸•à¸£à¸‡ à¹† (à¸›à¸´à¸” VPN) + à¹€à¸›à¸´à¸” ip_meter + login_pace
#   ip_meter_endpoint    URL à¸”à¸¶à¸‡ public IP (default https://api.ipify.org, "" = à¹ƒà¸Šà¹‰à¸„à¸µà¸¢à¹Œ 'local')
#   ip_meter_force       1 = à¹€à¸›à¸´à¸” ip_meter à¹à¸¡à¹‰à¹„à¸¡à¹ˆ no_proxy_mode (à¹ƒà¸Šà¹‰à¸•à¸­à¸™ VPN à¹€à¸žà¸·à¹ˆà¸­à¸•à¸±à¸” cap à¸•à¹ˆà¸­ IP à¸‚à¸²à¸­à¸­à¸)
#   login_min_gap_sec    à¹€à¸§à¹‰à¸™à¸£à¸°à¸¢à¸°à¸£à¸°à¸«à¸§à¹ˆà¸²à¸‡ login à¸‚à¸­à¸‡à¸šà¸­à¸•à¹€à¸”à¸µà¸¢à¸§à¸à¸±à¸™ (default 45s, jitter 0-30%)
# ============================================================
import json as _json_ipm
import random as _random_ipm
import threading as _threading_ipm

_IP_METER_PATH = "ip_meter.json"
_IP_METER_LOCK = _threading_ipm.Lock()
_IP_WINDOWS = [(3600, 3), (6 * 3600, 8), (24 * 3600, 20)]


# === HARDCODED KILL SWITCH: à¸›à¸´à¸” VPN à¸–à¸²à¸§à¸£à¸—à¸±à¹ˆà¸§à¸—à¸±à¹‰à¸‡à¸à¸¹à¸‡à¸šà¸­à¸• (à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¹à¸à¹‰ config à¸£à¸²à¸¢ remote) ===
# à¹€à¸«à¸•à¸¸à¸œà¸¥: configmain.json à¸–à¸¹à¸ untrack à¹à¸¥à¹‰à¸§ à¸šà¸­à¸• remote config à¸•à¹ˆà¸²à¸‡à¸à¸±à¸™ -> code-level à¸Šà¸±à¸§à¸£à¹Œà¸à¸§à¹ˆà¸²
# à¸–à¹‰à¸²à¸­à¸¢à¸²à¸à¹€à¸›à¸´à¸” VPN à¸à¸¥à¸±à¸š: à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™ True -> False à¹à¸¥à¹‰à¸§ git push
KILL_VPN_HARDCODED = True


def _no_proxy_mode():
    if KILL_VPN_HARDCODED:
        return True
    try:
        return bool(int(globals().get("config", {}).get("no_proxy_mode", 0) or 0))
    except Exception:
        return False


def _signal_host_vpn_rotate(reason=""):
    """à¹€à¸‚à¸µà¸¢à¸™à¹„à¸Ÿà¸¥à¹Œ trigger à¹€à¸žà¸·à¹ˆà¸­à¹ƒà¸«à¹‰ swap_bot.exe (host_wg_rotator) à¸ªà¸¥à¸±à¸š IP à¸—à¸±à¸™à¸—à¸µ
    - à¹ƒà¸Šà¹‰à¸•à¸­à¸™ IP à¹‚à¸”à¸™ cap / login fail / fixnet detect
    - swap_bot à¹€à¸Šà¹‡à¸„à¸—à¸¸à¸ 5 à¸§à¸´ à¹€à¸ˆà¸­à¹„à¸Ÿà¸¥à¹Œ -> rotate + à¸¥à¸šà¹„à¸Ÿà¸¥à¹Œ (à¸¡à¸µ cool-off 30s à¸à¸±à¸™à¸ªà¸¥à¸±à¸šà¸£à¸±à¸§)
    - à¹€à¸‚à¸µà¸¢à¸™à¹€à¸ªà¸¡à¸­ à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸ªà¸™ VPN mode à¸–à¹‰à¸²à¹„à¸¡à¹ˆà¸¡à¸µ rotator à¸à¹‡à¹€à¸‚à¸µà¸¢à¸™à¸—à¸´à¹‰à¸‡à¹„à¸¡à¹ˆà¸¡à¸µà¸œà¸¥"""
    try:
        import os as _os
        _script_dir = _os.path.dirname(_os.path.abspath(__file__))
        _trigger = _os.path.join(_script_dir, ".host_wg_trigger")
        with open(_trigger, "w", encoding="utf-8") as f:
            f.write(str(reason)[:200])
    except Exception:
        pass


def _ensure_swap_bot_running():
    """à¹€à¸Šà¹‡à¸„ swap_bot.py à¸§à¹ˆà¸²à¸£à¸±à¸™à¸­à¸¢à¸¹à¹ˆà¹„à¸«à¸¡ - à¸–à¹‰à¸²à¹„à¸¡à¹ˆ à¹€à¸›à¸´à¸”à¹ƒà¸«à¹‰ (à¸£à¸±à¸™ .py à¸•à¸£à¸‡à¹† à¹„à¸¡à¹ˆà¹ƒà¸Šà¹‰ .exe)
    - à¸£à¸±à¸™à¹„à¸”à¹‰à¸—à¸±à¹‰à¸‡à¸ˆà¸²à¸ ranger-gear.py / .bat à¸•à¹ˆà¸²à¸‡à¹†
    - à¹€à¸‡à¸µà¸¢à¸š: à¹„à¸¡à¹ˆ error à¸–à¹‰à¸²à¸«à¸² .py à¹„à¸¡à¹ˆà¹€à¸ˆà¸­"""
    try:
        import os as _os
        import sys as _sys
        import subprocess as _sp
        _CREATE_NO_WINDOW = getattr(_sp, "CREATE_NO_WINDOW", 0x08000000)
        try:
            r = _sp.run(["wmic", "process", "where", "name='python.exe' or name='pythonw.exe'",
                         "get", "CommandLine", "/FORMAT:LIST"],
                        capture_output=True, text=True, timeout=15,
                        creationflags=_CREATE_NO_WINDOW)
            if "swap_bot.py" in (r.stdout or "").lower():
                print("[SWAP_BOT] already running - à¹„à¸¡à¹ˆà¹€à¸›à¸´à¸”à¸‹à¹‰à¸³")
                return
        except Exception:
            pass
        _script_dir = _os.path.dirname(_os.path.abspath(__file__))
        candidates = [
            _os.path.join(_script_dir, "swap_bot", "swap_bot.py"),
            _os.path.join(_script_dir, "swap_bot.py"),
        ]
        py = next((p for p in candidates if _os.path.isfile(p)), None)
        if not py:
            print("[SWAP_BOT] à¹„à¸¡à¹ˆà¸žà¸š swap_bot.py (à¸ˆà¸°à¸‚à¹‰à¸²à¸¡ - trigger à¹€à¸‚à¸µà¸¢à¸™à¸—à¸´à¹‰à¸‡à¹€à¸‰à¸¢à¹†)")
            return
        exe_dir = _os.path.dirname(_sys.executable)
        pyw = _os.path.join(exe_dir, "pythonw.exe")
        interp = pyw if _os.path.isfile(pyw) else _sys.executable
        print(f"[SWAP_BOT] launching: {interp} {py}")
        _sp.Popen([interp, py], cwd=_os.path.dirname(py),
                  creationflags=0x00000008 | 0x00000200,
                  close_fds=True, stdin=_sp.DEVNULL,
                  stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
    except Exception as e:
        print(f"[SWAP_BOT] launch à¸¥à¹‰à¸¡à¹€à¸«à¸¥à¸§ (à¹„à¸¡à¹ˆà¸à¸£à¸°à¸—à¸šà¸šà¸­à¸—): {e}")


_ensure_swap_bot_running()


def _ip_meter_load():
    try:
        with open(_IP_METER_PATH, "r", encoding="utf-8") as f:
            return _json_ipm.load(f)
    except Exception:
        return {}


def _ip_meter_save(d):
    tmp = _IP_METER_PATH + f".{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            _json_ipm.dump(d, f)
        os.replace(tmp, _IP_METER_PATH)
    except Exception:
        try: os.remove(tmp)
        except Exception: pass


def _current_public_ip():
    """à¸”à¸¶à¸‡ public IP à¸‚à¸­à¸‡à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸™à¸µà¹‰ - à¹ƒà¸Šà¹‰à¹à¸¢à¸ bucket per-IP à¹ƒà¸™ state file
    (à¸›à¸´à¸”à¹„à¸”à¹‰à¸”à¹‰à¸§à¸¢ ip_meter_endpoint = "" à¹ƒà¸™ config -> à¹ƒà¸Šà¹‰ 'local' à¹€à¸›à¹‡à¸™à¸„à¸µà¸¢à¹Œà¹à¸—à¸™)"""
    url = str(globals().get("config", {}).get("ip_meter_endpoint", "https://api.ipify.org") or "")
    if not url:
        return "local"
    try:
        import urllib.request as _ur
        with _ur.urlopen(url, timeout=6) as r:
            ip = r.read().decode("ascii").strip()
            if ip and len(ip) <= 45:
                return ip
    except Exception:
        pass
    return "local"


def _ip_meter_cap_wait(ip):
    """à¸Šà¸™ cap à¸«à¸™à¹‰à¸²à¸•à¹ˆà¸²à¸‡à¹„à¸«à¸™ -> à¸„à¸·à¸™à¸§à¸´à¸™à¸²à¸—à¸µà¸—à¸µà¹ˆà¸•à¹‰à¸­à¸‡à¸£à¸­à¹ƒà¸«à¹‰à¸«à¸¥à¸¸à¸”à¸«à¸™à¹‰à¸²à¸•à¹ˆà¸²à¸‡à¸™à¸±à¹‰à¸™ (à¹€à¸­à¸²à¸¡à¸²à¸à¸—à¸µà¹ˆà¸ªà¸¸à¸”). 0 = à¸¢à¸´à¸‡à¹„à¸”à¹‰"""
    with _IP_METER_LOCK:
        d = _ip_meter_load()
        hist = [t for t in d.get(ip, []) if t > time.time() - 48 * 3600]
        now = time.time()
        max_wait = 0.0
        for window, cap in _IP_WINDOWS:
            recent = [t for t in hist if t > now - window]
            if len(recent) >= cap:
                oldest = min(recent)
                wait = (oldest + window) - now
                if wait > max_wait:
                    max_wait = wait
        return max_wait


def _ip_meter_mark(ip):
    with _IP_METER_LOCK:
        d = _ip_meter_load()
        hist = [t for t in d.get(ip, []) if t > time.time() - 48 * 3600]
        hist.append(time.time())
        d[ip] = hist
        _ip_meter_save(d)


def _ip_meter_gate():
    """à¹€à¸£à¸µà¸¢à¸à¸à¹ˆà¸­à¸™ login à¸—à¸¸à¸à¸„à¸£à¸±à¹‰à¸‡: à¸–à¹‰à¸²à¸Šà¸™ cap -> à¸¢à¸´à¸‡ trigger à¹ƒà¸«à¹‰ swap_bot à¸ªà¸¥à¸±à¸š IP à¹à¸¥à¹‰à¸§à¸£à¸­à¸«à¸¥à¸¸à¸”"""
    if not _no_proxy_mode() and not int(globals().get("config", {}).get("ip_meter_force", 0) or 0):
        return
    ip = _current_public_ip()
    wait = _ip_meter_cap_wait(ip)
    if wait > 0:
        mins = wait / 60.0
        # à¸¢à¸´à¸‡ trigger à¹ƒà¸«à¹‰ swap_bot à¸ªà¸¥à¸±à¸š IP à¸—à¸±à¸™à¸—à¸µ (à¸”à¸µà¸à¸§à¹ˆà¸²à¸£à¸­ 59 à¸™à¸²à¸—à¸µ)
        _signal_host_vpn_rotate(f"ip-meter-cap {ip} wait={int(wait)}s")
        print(f"[IP-METER] IP {ip} à¸Šà¸™ cap - signal swap_bot rotate + à¸£à¸­ {mins:.1f} à¸™à¸²à¸—à¸µ (à¸«à¸£à¸·à¸­à¸ˆà¸™ IP à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™)")
        # à¸£à¸­à¸ªà¸±à¹‰à¸™à¸¥à¸‡: à¹ƒà¸«à¹‰à¹‚à¸­à¸à¸²à¸ª swap_bot à¸ªà¸¥à¸±à¸šà¸à¹ˆà¸­à¸™ à¹à¸¥à¹‰à¸§à¸„à¹ˆà¸­à¸¢à¸¥à¸­à¸‡à¹ƒà¸«à¸¡à¹ˆ
        # à¹€à¸”à¸´à¸¡à¸£à¸­à¸—à¸±à¹‰à¸‡ window (= 59 à¸™à¸²à¸—à¸µ) à¸•à¸­à¸™à¸™à¸µà¹‰à¸£à¸­à¹à¸„à¹ˆ 90s à¹à¸¥à¹‰à¸§à¸­à¸­à¸ - à¸£à¸­à¸šà¸«à¸™à¹‰à¸² gate à¸ˆà¸°à¹€à¸Šà¹‡à¸„ IP à¹ƒà¸«à¸¡à¹ˆ
        _real_sleep(min(wait + 5, 90))
    _ip_meter_mark(ip)


_LAST_LOGIN_T = [0.0]
def _login_pace():
    """à¹€à¸§à¹‰à¸™à¸Šà¹ˆà¸§à¸‡à¸£à¸°à¸«à¸§à¹ˆà¸²à¸‡ login à¸‚à¸­à¸‡à¸šà¸­à¸•à¹€à¸”à¸µà¸¢à¸§à¸à¸±à¸™ - IP à¹€à¸”à¸µà¸¢à¸§à¸¢à¸´à¸‡à¸–à¸µà¹ˆ = à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¸¡à¸­à¸‡à¹€à¸›à¹‡à¸™ bot à¹à¸™à¹ˆà¸™à¸­à¸™"""
    if not _no_proxy_mode():
        return
    try:
        gap = float(globals().get("config", {}).get("login_min_gap_sec", 45) or 0)
    except Exception:
        gap = 45.0
    wait = (_LAST_LOGIN_T[0] + gap + _random_ipm.uniform(0, gap * 0.3)) - time.time()
    if wait > 0:
        _real_sleep(wait)
    _LAST_LOGIN_T[0] = time.time()


def _pool_pick_ip(wg_dir="wg"):
    """à¹€à¸¥à¸·à¸­à¸ IP à¸ˆà¸²à¸ wg/ pool à¸—à¸µà¹ˆ 'à¹ƒà¸à¸¥à¹‰à¸§à¹ˆà¸²à¸‡à¸ªà¸¸à¸”' (à¸£à¸­à¸™à¹‰à¸­à¸¢à¸ªà¸¸à¸”)
    à¸„à¸·à¸™ (conf_path, endpoint_ip, wait_seconds). à¸§à¹ˆà¸²à¸‡à¸—à¸±à¸™à¸—à¸µ wait=0.
    à¹„à¸¡à¹ˆà¸¡à¸µà¹„à¸Ÿà¸¥à¹Œà¹€à¸¥à¸¢ -> à¸„à¸·à¸™ (None, 'local', wait=per-IP cap à¸›à¸±à¸ˆà¸ˆà¸¸à¸šà¸±à¸™)"""
    confs = _wg_list_configs(wg_dir) if "_wg_list_configs" in globals() else []
    if not confs:
        return None, "local", _ip_meter_cap_wait("local")
    best = None
    for c in confs:
        try:
            ep = _wg_endpoint(c)
        except Exception:
            ep = os.path.basename(c)
        w = _ip_meter_cap_wait(ep)
        if best is None or w < best[2]:
            best = (c, ep, w)
        if w <= 0:
            return c, ep, 0
    return best


class RestartTimeoutError(Exception):
    """wg_required: à¸•à¹ˆà¸­ VPN à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™ -> à¹€à¸”à¹‰à¸‡à¸­à¸­à¸à¸ˆà¸²à¸à¹„à¸Ÿà¸¥à¹Œà¸™à¸µà¹‰ (_main_loop à¸ˆà¸±à¸šà¹à¸¥à¹‰à¸§à¸›à¸¥à¹ˆà¸­à¸¢à¸¥à¹‡à¸­à¸ à¸«à¸¢à¸´à¸šà¹„à¸Ÿà¸¥à¹Œà¹ƒà¸«à¸¡à¹ˆ)
    à¹ƒà¸Šà¹‰ Exception (à¹„à¸¡à¹ˆà¹ƒà¸Šà¹ˆ BaseException à¹à¸šà¸š login.py) à¹€à¸žà¸·à¹ˆà¸­à¹ƒà¸«à¹‰ except à¸‚à¸­à¸‡ _main_loop à¸ˆà¸±à¸šà¹„à¸”à¹‰ à¹„à¸¡à¹ˆà¹ƒà¸«à¹‰ thread à¸•à¸²à¸¢"""


def _wg_endpoint(conf):
    """host à¸‚à¸­à¸‡ Endpoint à¹ƒà¸™à¹„à¸Ÿà¸¥à¹Œ .conf (= IP à¸‚à¸²à¸­à¸­à¸à¸‚à¸­à¸‡ VPN)"""
    try:
        with open(conf, encoding="utf-8-sig") as f:
            for l in f:
                if l.strip().lower().startswith("endpoint"):
                    return l.split("=", 1)[1].strip().rsplit(":", 1)[0]
    except Exception:
        pass
    return os.path.basename(conf)


def _wg_generate_more(wg_dir, want, dev=""):
    """à¸ªà¸£à¹‰à¸²à¸‡à¹„à¸Ÿà¸¥à¹Œà¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹€à¸žà¸´à¹ˆà¸¡à¹ƒà¸«à¹‰à¸¡à¸µ want à¹„à¸Ÿà¸¥à¹Œ (à¸¥à¹‡à¸­à¸à¹ƒà¸«à¹‰à¸ªà¸£à¹‰à¸²à¸‡à¸—à¸µà¸¥à¸°à¸ˆà¸­) - à¸„à¸·à¸™ True à¸–à¹‰à¸²à¸¡à¸µà¹„à¸Ÿà¸¥à¹Œà¹€à¸žà¸´à¹ˆà¸¡à¸ˆà¸£à¸´à¸‡"""
    os.makedirs(wg_dir, exist_ok=True)   # à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸«à¸²à¸¢ -> à¸ªà¸£à¹‰à¸²à¸‡à¹„à¸Ÿà¸¥à¹Œà¸¥à¹‡à¸­à¸à¹„à¸¡à¹ˆà¹„à¸”à¹‰ à¹à¸¥à¹‰à¸§à¹€à¸¥à¸´à¸à¹€à¸‡à¸µà¸¢à¸š à¹†
    lock = os.path.join(wg_dir, ".gen.lock")
    try:
        if os.path.exists(lock) and time.time() - os.path.getmtime(lock) > 300:
            os.remove(lock)
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except Exception:
        return False
    try:
        before = len(_wg_list_configs(wg_dir))
        managed = os.path.exists(os.path.join(wg_dir, ".managed"))
        kp = os.path.join(wg_dir, "keypair.txt")
        confs = _wg_list_configs(wg_dir)
        if managed and not os.path.exists(kp) and confs:
            with open(confs[0], "rb") as f_src, open(kp, "wb") as f_dst:
                f_dst.write(f_src.read())
        print(f"[{dev}] [WG] à¹„à¸Ÿà¸¥à¹Œ VPN à¸§à¹ˆà¸²à¸‡à¹„à¸¡à¹ˆà¸žà¸­ - à¸ªà¸£à¹‰à¸²à¸‡à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹ƒà¸«à¸¡à¹ˆà¹€à¸žà¸´à¹ˆà¸¡ (à¸¡à¸µ {before} -> {want})")
        import wg_gen
        if managed:
            wg_gen.generate(want, config.get("wg_gen_countries") or None, wg_dir, 0, "", 0, managed_ok=True)
        else:
            wg_gen.generate(want, config.get("wg_gen_countries") or None, wg_dir,
                            int(config.get("wg_machine", 0) or 0),
                            str(config.get("wg_account", "") or "").strip() or None,
                            int(config.get("wg_total_machines", 30) or 30))
        return len(_wg_list_configs(wg_dir)) > before
    except Exception as e:
        print(f"[{dev}] [WG] à¸ªà¸£à¹‰à¸²à¸‡à¹„à¸Ÿà¸¥à¹Œà¹€à¸žà¸´à¹ˆà¸¡à¹„à¸¡à¹ˆà¸ªà¸³à¹€à¸£à¹‡à¸ˆ: {e}")
        return False
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def _wg_replace_blocked(conf, dev=""):
    """à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¸™à¸µà¹‰à¹‚à¸”à¸™à¹€à¸à¸¡à¸šà¸¥à¹‡à¸­à¸ -> à¸ˆà¸”à¸¥à¸‡ wg/.blocked.json (wg_gen à¹„à¸¡à¹ˆà¸ªà¸£à¹‰à¸²à¸‡à¸‹à¹‰à¸³), à¸¥à¸šà¹„à¸Ÿà¸¥à¹Œà¸—à¸´à¹‰à¸‡,
    à¹à¸¥à¹‰à¸§à¸ªà¸±à¹ˆà¸‡ wg_gen à¸ªà¸£à¹‰à¸²à¸‡à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹ƒà¸«à¸¡à¹ˆà¸¡à¸²à¹à¸—à¸™à¹ƒà¸«à¹‰à¸ˆà¸³à¸™à¸§à¸™à¹„à¸Ÿà¸¥à¹Œà¹€à¸—à¹ˆà¸²à¹€à¸”à¸´à¸¡
    (à¸‚à¹‰à¸²à¸¡à¸–à¹‰à¸²à¹„à¸Ÿà¸¥à¹Œà¸¡à¸²à¸ˆà¸²à¸ server RemoteFileManager (.managed) ; à¸«à¸¥à¸²à¸¢à¸ˆà¸­à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™ -> à¸¥à¹‡à¸­à¸à¹ƒà¸«à¹‰à¸ªà¸£à¹‰à¸²à¸‡à¸—à¸µà¸¥à¸°à¸ˆà¸­)"""
    wg_dir = os.path.dirname(conf) or "."
    managed = os.path.exists(os.path.join(wg_dir, ".managed"))
    if not os.path.exists(conf) or (managed and not int(config.get("wg_regen_managed", 1) or 0)):
        return
    os.makedirs(wg_dir, exist_ok=True)   # à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸«à¸²à¸¢ -> à¸ªà¸£à¹‰à¸²à¸‡à¹„à¸Ÿà¸¥à¹Œà¸¥à¹‡à¸­à¸à¹„à¸¡à¹ˆà¹„à¸”à¹‰ à¹à¸¥à¹‰à¸§à¹€à¸¥à¸´à¸à¹€à¸‡à¸µà¸¢à¸š à¹†
    lock = os.path.join(wg_dir, ".gen.lock")
    try:
        if os.path.exists(lock) and time.time() - os.path.getmtime(lock) > 300:
            os.remove(lock)                 # à¸¥à¹‡à¸­à¸à¸„à¹‰à¸²à¸‡à¸ˆà¸²à¸ process à¸—à¸µà¹ˆà¸•à¸²à¸¢à¹„à¸›
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except Exception:
        return                              # à¸ˆà¸­à¸­à¸·à¹ˆà¸™à¸à¸³à¸¥à¸±à¸‡à¸ªà¸£à¹‰à¸²à¸‡à¸­à¸¢à¸¹à¹ˆ - à¸£à¸­à¸šà¸™à¸±à¹‰à¸™à¸ˆà¸°à¹€à¸•à¸´à¸¡à¹ƒà¸«à¹‰à¸„à¸£à¸šà¹€à¸­à¸‡
    try:
        ep = _wg_endpoint(conf)
        bp = os.path.join(wg_dir, ".blocked.json")
        try:
            with open(bp, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            d = {}
        d[ep] = time.time()
        with open(bp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        want = len(_wg_list_configs(wg_dir))
        kp = os.path.join(wg_dir, "keypair.txt")
        if managed and not os.path.exists(kp):
            # à¹„à¸Ÿà¸¥à¹Œà¸ˆà¸²à¸ server: à¹€à¸à¹‡à¸šà¸à¸¸à¸à¹à¸ˆà¹„à¸§à¹‰à¸à¹ˆà¸­à¸™à¸¥à¸š -> à¹„à¸Ÿà¸¥à¹Œà¹ƒà¸™ wg/ à¸«à¸¡à¸”à¹€à¸à¸¥à¸µà¹‰à¸¢à¸‡à¸à¹‡à¸¢à¸±à¸‡à¸ªà¸£à¹‰à¸²à¸‡à¹ƒà¸«à¸¡à¹ˆà¹„à¸”à¹‰
            with open(conf, "rb") as f_src, open(kp, "wb") as f_dst:
                f_dst.write(f_src.read())
        # à¹„à¸Ÿà¸¥à¹Œà¸—à¸µà¹ˆà¸­à¸­à¸ IP à¹€à¸”à¸µà¸¢à¸§à¸à¸±à¸™ (à¹à¸Šà¸£à¹Œà¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¸«à¸¥à¸²à¸¢à¸ˆà¸­ à¸„à¸™à¸¥à¸°à¸à¸¸à¸à¹à¸ˆ) à¹‚à¸”à¸™à¸šà¸¥à¹‡à¸­à¸à¸”à¹‰à¸§à¸¢à¸à¸±à¸™à¸«à¸¡à¸” -> à¸¥à¸šà¸—à¸¸à¸à¸•à¸±à¸§
        gone = [c for c in _wg_list_configs(wg_dir) if _wg_endpoint(c) == ep] or [conf]
        for c in gone:
            try:
                os.remove(c)
            except OSError:
                pass
        print(f"[{dev}] [WG] à¸¥à¸š {', '.join(os.path.basename(c) for c in gone)} (à¹€à¸à¸¡à¸šà¸¥à¹‡à¸­à¸ IP {ep}) - à¸ªà¸£à¹‰à¸²à¸‡à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹ƒà¸«à¸¡à¹ˆà¸¡à¸²à¹à¸—à¸™")
        import wg_gen
        if managed:
            # à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸—à¸µà¹ˆà¸£à¸±à¸šà¹„à¸Ÿà¸¥à¹Œà¸ˆà¸²à¸ server: à¹ƒà¸Šà¹‰à¸à¸¸à¸à¹à¸ˆà¹€à¸”à¸´à¸¡à¸‚à¸­à¸‡à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ (keypair.txt) à¸ªà¸£à¹‰à¸²à¸‡à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹ƒà¸«à¸¡à¹ˆà¸—à¸µà¹ˆà¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸¡à¸µà¹ƒà¸™à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡
            wg_gen.generate(want, config.get("wg_gen_countries") or None, wg_dir, 0, "", 0, managed_ok=True)
        else:
            wg_gen.generate(want, config.get("wg_gen_countries") or None, wg_dir,
                            int(config.get("wg_machine", 0) or 0),
                            str(config.get("wg_account", "") or "").strip() or None,
                            int(config.get("wg_total_machines", 30) or 30))
    except Exception as e:
        print(f"[{dev}] [WG] à¸ªà¸£à¹‰à¸²à¸‡à¹„à¸Ÿà¸¥à¹Œà¹à¸—à¸™à¹„à¸¡à¹ˆà¸ªà¸³à¹€à¸£à¹‡à¸ˆ: {e}")
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def _wg_cooldown_load(wg_dir):
    """{endpoint: à¸«à¸¡à¸”à¹€à¸§à¸¥à¸²à¸žà¸±à¸} à¸—à¸µà¹ˆà¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸«à¸¡à¸” (à¹ƒà¸Šà¹‰à¸£à¹ˆà¸§à¸¡à¸—à¸¸à¸à¸ˆà¸­à¸œà¹ˆà¸²à¸™à¹„à¸Ÿà¸¥à¹Œ wg/.cooldown.json)"""
    try:
        with open(os.path.join(wg_dir, ".cooldown.json"), encoding="utf-8") as f:
            d = json.load(f)
        now = time.time()
        return {k: v for k, v in d.items() if v > now}
    except Exception:
        return {}


def _wg_cooldown_add(wg_dir, endpoint):
    h = float(config.get("wg_cooldown_hours", 6) or 0)
    if h <= 0 or not endpoint:
        return
    d = _wg_cooldown_load(wg_dir)
    d[endpoint] = time.time() + h * 3600
    try:
        tmp = os.path.join(wg_dir, f".cooldown.{os.getpid()}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, os.path.join(wg_dir, ".cooldown.json"))
    except Exception:
        pass


def _wg_list_configs(wg_dir=None):
    """à¸£à¸²à¸¢à¸à¸²à¸£à¹„à¸Ÿà¸¥à¹Œ config WireGuard à¸•à¸²à¸¡à¸¥à¸³à¸”à¸±à¸šà¸ˆà¸­ (path à¹ƒà¸™à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡)

    1) wg/wg.txt (Notepad à¹„à¸Ÿà¸¥à¹Œà¹€à¸”à¸µà¸¢à¸§) - à¸§à¸²à¸‡ config à¸•à¹ˆà¸­à¸à¸±à¸™à¹„à¸”à¹‰à¸«à¸¥à¸²à¸¢à¸­à¸±à¸™ à¹à¸•à¹ˆà¸¥à¸°à¸­à¸±à¸™à¹€à¸£à¸´à¹ˆà¸¡à¸”à¹‰à¸§à¸¢ [Interface]
       à¸­à¸±à¸™à¹à¸£à¸ = à¸ˆà¸­ 1, à¸­à¸±à¸™à¸—à¸µà¹ˆà¸ªà¸­à¸‡ = à¸ˆà¸­ 2 ... à¸šà¸£à¸£à¸—à¸±à¸”à¸—à¸µà¹ˆà¸‚à¸¶à¹‰à¸™à¸•à¹‰à¸™à¸”à¹‰à¸§à¸¢ # à¸„à¸·à¸­à¸«à¸¡à¸²à¸¢à¹€à¸«à¸•à¸¸ à¹„à¸¡à¹ˆà¸ªà¸™à¹ƒà¸ˆ
       (à¹à¸¢à¸à¹€à¸à¹‡à¸šà¹€à¸›à¹‡à¸™à¹„à¸Ÿà¸¥à¹Œà¹„à¸§à¹‰à¹ƒà¸™ wg/.split/ à¹ƒà¸«à¹‰à¸šà¸­à¸—à¸ªà¹ˆà¸‡à¹€à¸‚à¹‰à¸²à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡)
    2) à¸•à¸²à¸¡à¸”à¹‰à¸§à¸¢à¹„à¸Ÿà¸¥à¹Œ *.conf à¹ƒà¸™à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œ wg/ à¹€à¸£à¸µà¸¢à¸‡à¸•à¸²à¸¡à¸Šà¸·à¹ˆà¸­
    """
    if wg_dir is None:
        wg_dir = str(config.get("wg_dir", "wg"))
    out = []
    txt = os.path.join(wg_dir, "wg.txt")
    if os.path.exists(txt):
        try:
            with open(txt, "r", encoding="utf-8-sig", errors="replace") as f:
                lines = [ln.rstrip() for ln in f if not ln.lstrip().startswith(("#", "//"))]
            blocks, cur = [], []
            for ln in lines:
                if ln.strip().lower() == "[interface]" and cur:
                    blocks.append(cur)
                    cur = []
                cur.append(ln)
            if cur:
                blocks.append(cur)
            split_dir = os.path.join(wg_dir, ".split")
            os.makedirs(split_dir, exist_ok=True)
            for i, blk in enumerate(blocks, 1):
                text = "\n".join(blk).strip()
                if "privatekey" not in text.lower() or "endpoint" not in text.lower():
                    continue
                p = os.path.join(split_dir, f"wg{i:02d}.conf")
                old = open(p, encoding="utf-8").read() if os.path.exists(p) else None
                if old != text + "\n":
                    with open(p, "w", encoding="utf-8", newline="\n") as f:
                        f.write(text + "\n")
                out.append(p)
        except Exception as e:
            print(f"[WG] à¸­à¹ˆà¸²à¸™ wg.txt à¹„à¸¡à¹ˆà¹„à¸”à¹‰: {e}")
    try:
        out += [os.path.join(wg_dir, f) for f in sorted(os.listdir(wg_dir)) if f.lower().endswith(".conf")]
    except Exception:
        pass
    # à¸•à¸±à¸”à¹„à¸Ÿà¸¥à¹Œà¸—à¸µà¹ˆà¸‚à¹‰à¸²à¸‡à¹ƒà¸™à¸‹à¹‰à¸³à¸à¸±à¸™: à¸à¸¸à¸à¹à¸ˆ (PrivateKey) à¹€à¸”à¸µà¸¢à¸§à¸à¸±à¸™ + à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œ (Endpoint) à¹€à¸”à¸µà¸¢à¸§à¸à¸±à¸™
    # à¸•à¹ˆà¸­à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™à¸«à¸¥à¸²à¸¢à¸ˆà¸­ = à¹à¸¢à¹ˆà¸‡à¸à¸±à¸™à¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”à¸—à¸¸à¸à¸ˆà¸­ (à¹€à¸Šà¹ˆà¸™à¹‚à¸«à¸¥à¸” Singapore à¸‹à¹‰à¸³ à¹† à¸”à¹‰à¸§à¸¢ Key Pair à¹€à¸”à¸´à¸¡) -> à¹ƒà¸Šà¹‰à¹„à¸”à¹‰à¹à¸„à¹ˆà¹„à¸Ÿà¸¥à¹Œà¹€à¸”à¸µà¸¢à¸§
    seen, uniq, dup = {}, [], []
    for p in out:
        try:
            with open(p, encoding="utf-8-sig", errors="replace") as f:
                kv = {}
                for ln in f:
                    if "=" in ln:
                        k, v = ln.split("=", 1)
                        kv[k.strip().lower()] = v.strip()
            ident = (kv.get("privatekey", ""), kv.get("endpoint", "").rsplit(":", 1)[0].lower())
        except Exception:
            ident = (p, "")
        if ident in seen:
            dup.append((os.path.basename(p), os.path.basename(seen[ident])))
            continue
        seen[ident] = p
        uniq.append(p)
    if dup and not _wg_dup_warned:
        _wg_dup_warned.append(1)
        print(f"[WG] à¹€à¸•à¸·à¸­à¸™: à¸¡à¸µ {len(dup)} à¹„à¸Ÿà¸¥à¹Œà¸‹à¹‰à¸³ (à¸à¸¸à¸à¹à¸ˆ+à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹€à¸”à¸µà¸¢à¸§à¸à¸±à¸™ à¹ƒà¸Šà¹‰à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™à¹„à¸¡à¹ˆà¹„à¸”à¹‰) - à¹„à¸¡à¹ˆà¹ƒà¸Šà¹‰à¹„à¸Ÿà¸¥à¹Œà¸žà¸§à¸à¸™à¸µà¹‰:")
        for a, b in dup:
            print(f"[WG]   {a}  à¸‹à¹‰à¸³à¸à¸±à¸š  {b}")
        print("[WG]   à¹à¸à¹‰: à¹‚à¸«à¸¥à¸”à¹ƒà¸«à¸¡à¹ˆà¹€à¸›à¹‡à¸™ 'à¸„à¸™à¸¥à¸°à¹€à¸¡à¸·à¸­à¸‡' à¸«à¸£à¸·à¸­à¹€à¸¡à¸·à¸­à¸‡à¹€à¸”à¸´à¸¡à¹à¸•à¹ˆà¹€à¸¥à¸·à¸­à¸ New Key Pair")
    return uniq


_wg_dup_warned = []   # à¹€à¸•à¸·à¸­à¸™à¹„à¸Ÿà¸¥à¹Œà¸‹à¹‰à¸³à¸„à¸£à¸±à¹‰à¸‡à¹€à¸”à¸µà¸¢à¸§à¸•à¹ˆà¸­ process


WG_APK_URL = "https://download.wireguard.com/android-client/com.wireguard.android-1.0.20260315.apk"
_wg_apk_lock = threading.Lock()


def _wg_apk_path():
    """à¹„à¸Ÿà¸¥à¹Œà¸•à¸´à¸”à¸•à¸±à¹‰à¸‡à¹à¸­à¸› WireGuard (Android) - sync à¸à¸±à¸š login.py: à¸«à¸²à¸ˆà¸²à¸ central à¸à¹ˆà¸­à¸™
    à¸¥à¸³à¸”à¸±à¸š: script_dir/wg/wireguard.apk, wg/wireguard.apk, <wg_dir>/wireguard.apk
    à¹„à¸¡à¹ˆà¹€à¸ˆà¸­ -> à¹‚à¸«à¸¥à¸”à¸¥à¸‡ wg/wireguard.apk (central) à¸—à¸¸à¸ sub à¹ƒà¸Šà¹‰à¸£à¹ˆà¸§à¸¡"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    wg_dir = str(config.get("wg_dir", "wg"))
    candidates = [
        os.path.join(script_dir, "wg", "wireguard.apk"),
        os.path.join("wg", "wireguard.apk"),
        os.path.join(wg_dir, "wireguard.apk"),
    ]
    with _wg_apk_lock:
        for p in candidates:
            if os.path.exists(p) and os.path.getsize(p) > 1_000_000:
                return p
        central_dir = os.path.join(script_dir, "wg")
        try:
            os.makedirs(central_dir, exist_ok=True)
            import urllib.request
            print("[WG] à¸à¸³à¸¥à¸±à¸‡à¹‚à¸«à¸¥à¸”à¹à¸­à¸› WireGuard (à¸„à¸£à¸±à¹‰à¸‡à¹à¸£à¸à¸„à¸£à¸±à¹‰à¸‡à¹€à¸”à¸µà¸¢à¸§) à¸¥à¸‡ wg/wireguard.apk...")
            path = os.path.join(central_dir, "wireguard.apk")
            tmp = path + ".part"
            urllib.request.urlretrieve(str(config.get("wg_apk_url", WG_APK_URL)), tmp)
            os.replace(tmp, path)
            return path
        except Exception as e:
            print(f"[WG] à¹‚à¸«à¸¥à¸”à¹à¸­à¸› WireGuard à¹„à¸¡à¹ˆà¹„à¸”à¹‰: {e}")
            return None


def reset_network_all(devices):
    """à¸à¹ˆà¸­à¸™à¹€à¸£à¸´à¹ˆà¸¡à¸šà¸­à¸—: à¸¥à¹‰à¸²à¸‡à¸‚à¸­à¸‡à¸„à¹‰à¸²à¸‡à¸—à¸¸à¸à¸ˆà¸­ (à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™) - tunnel WireGuard, à¹à¸­à¸› WireGuard, proxy
    à¹à¸¥à¹‰à¸§ ping 1.1.1.1 à¸ˆà¸²à¸à¹ƒà¸™à¸­à¸µà¸¡à¸¹à¸¯ à¸šà¸­à¸à¹ƒà¸™ log à¸§à¹ˆà¸²à¸ˆà¸­à¹„à¸«à¸™à¹€à¸™à¹‡à¸•à¹ƒà¸Šà¹‰à¹„à¸”à¹‰/à¹„à¸¡à¹ˆà¹„à¸”à¹‰
    à¸›à¸´à¸”à¹„à¸”à¹‰à¸”à¹‰à¸§à¸¢ config "reset_network_on_start": 0

    wg_enabled=0 (proxy mode): à¸‚à¹‰à¸²à¸¡à¸—à¸±à¹‰à¸‡à¸«à¸¡à¸” - à¹„à¸¡à¹ˆà¸¥à¹‰à¸²à¸‡ http_proxy à¸‚à¸­à¸‡ Android
      (à¸—à¸µà¹ˆ proxy_switcher.py à¸•à¸±à¹‰à¸‡à¹„à¸§à¹‰à¹ƒà¸«à¹‰ emulator à¸§à¸´à¹ˆà¸‡à¸œà¹ˆà¸²à¸™ TOT/ISP à¹„à¸—à¸¢)
    """
    if not int(config.get("reset_network_on_start", 1) or 0):
        return
    if _no_proxy_mode():
        print("[NET-RESET] no_proxy_mode / KILL_VPN=on - à¸‚à¹‰à¸²à¸¡ VPN reset / WG-INSTALL / hard-reset à¸—à¸±à¹‰à¸‡à¸«à¸¡à¸” (à¹ƒà¸Šà¹‰ IP à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸•à¸£à¸‡ à¹†)")
        return
    if int(config.get("use_host_vpn", 0) or 0):
        print("[NET-RESET] use_host_vpn=1 - host_wg_rotator à¸„à¸¸à¸¡à¸šà¸™ Windows (à¸‚à¹‰à¸²à¸¡ VPN setup à¹ƒà¸™à¸­à¸µà¸¡à¸¹à¸¯)")
        # à¸à¸³à¸ˆà¸±à¸” WireGuard app à¸„à¹‰à¸²à¸‡à¹ƒà¸™à¸—à¸¸à¸à¸­à¸µà¸¡à¸¹ - à¸›à¹‰à¸­à¸‡à¸à¸±à¸™à¸«à¸™à¹‰à¸²à¸ˆà¸­à¹à¸­à¸› WG à¹‚à¸œà¸¥à¹ˆ/à¸„à¹‰à¸²à¸‡à¸ˆà¸²à¸à¸£à¸­à¸šà¸à¹ˆà¸­à¸™
        if int(config.get("host_vpn_purge_emu_wg", 1) or 0):
            pkg = "com.wireguard.android"
            kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            def _purge(dev):
                try:
                    subprocess.run([adb_path, "-s", dev, "shell",
                                    f"su -c 'am broadcast -f 0x20 -p {pkg} -a {pkg}.action.SET_TUNNEL_DOWN --es tunnel wg0'"],
                                   capture_output=True, timeout=10, **kw)
                    subprocess.run([adb_path, "-s", dev, "shell", f"am force-stop {pkg}"],
                                   capture_output=True, timeout=10, **kw)
                    if int(config.get("host_vpn_uninstall_emu_wg", 1) or 0):
                        r = subprocess.run([adb_path, "-s", dev, "uninstall", pkg],
                                           capture_output=True, text=True, timeout=30, **kw)
                        out = (r.stdout or "") + (r.stderr or "")
                        if "Success" in out:
                            print(f"[NET-RESET] {dev}: à¸–à¸­à¸™à¹à¸­à¸› WireGuard à¸­à¸­à¸à¸ˆà¸²à¸à¸­à¸µà¸¡à¸¹à¹à¸¥à¹‰à¸§ âœ“")
                except Exception:
                    pass
            _threads = []
            for d in devices:
                t = threading.Thread(target=_purge, args=(d,), daemon=True)
                t.start()
                _threads.append(t)
            for t in _threads:
                t.join(timeout=35)
        return
    if not int(config.get("wg_enabled", 1) or 0):
        print("[NET-RESET] wg_enabled=0 (proxy mode) - à¸‚à¹‰à¸²à¸¡ VPN reset à¸—à¸±à¹‰à¸‡à¸«à¸¡à¸”")
        print("            Android http_proxy à¸—à¸µà¹ˆ proxy_switcher à¸•à¸±à¹‰à¸‡à¹„à¸§à¹‰à¸„à¸‡à¸­à¸¢à¸¹à¹ˆ")
        return
    pkg = "com.wireguard.android"
    kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}

    def sh(dev, cmd, timeout=20):
        try:
            return subprocess.run([adb_path, "-s", dev, "shell", cmd], capture_output=True,
                                  text=True, errors="replace", timeout=timeout, **kw).stdout or ""
        except Exception:
            return ""

    def ensure_wg_installed(dev):
        """à¸•à¸´à¸”à¸•à¸±à¹‰à¸‡à¹à¸­à¸› WireGuard à¸¥à¸‡à¸­à¸µà¸¡à¸¹à¸¯ à¸–à¹‰à¸²à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸¡à¸µ (sync à¸à¸±à¸š login.py)
        à¹€à¸Šà¹‡à¸„ 2 à¸Šà¸±à¹‰à¸™: pm path (à¹€à¸£à¹‡à¸§ à¹„à¸¡à¹ˆà¸žà¸¶à¹ˆà¸‡ su) -> fallback su test -d"""
        if not int(config.get("wg_enabled", 1) or 0):
            return
        got = sh(dev, f"pm path {pkg}", timeout=8)
        if "package:" in (got or "").lower():
            print(f"[WG-INSTALL] {dev}: à¸¡à¸µà¹à¸­à¸› WireGuard à¸­à¸¢à¸¹à¹ˆà¹à¸¥à¹‰à¸§ âœ“")
            return
        got2 = sh(dev, f"su -c 'test -d /data/data/{pkg} && echo YES'", timeout=10)
        if "YES" in (got2 or ""):
            print(f"[WG-INSTALL] {dev}: à¸¡à¸µà¹à¸­à¸› WireGuard à¸­à¸¢à¸¹à¹ˆà¹à¸¥à¹‰à¸§ âœ“ (via su)")
            return
        apk = _wg_apk_path()
        if not apk:
            print(f"[WG-INSTALL] {dev}: à¹„à¸¡à¹ˆà¸žà¸šà¹à¸­à¸› + à¹‚à¸«à¸¥à¸”à¹„à¸Ÿà¸¥à¹Œ wg/wireguard.apk à¹„à¸¡à¹ˆà¹„à¸”à¹‰ - à¸‚à¹‰à¸²à¸¡à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸™à¸µà¹‰")
            return
        print(f"[WG-INSTALL] {dev}: à¹„à¸¡à¹ˆà¸žà¸šà¹à¸­à¸› WireGuard - à¸à¸³à¸¥à¸±à¸‡à¸•à¸´à¸”à¸•à¸±à¹‰à¸‡à¸ˆà¸²à¸ {apk}...")
        try:
            r = subprocess.run([adb_path, "-s", dev, "install", "-r", apk],
                               capture_output=True, text=True, errors="replace",
                               timeout=180, **kw)
            out = (r.stdout or "") + (r.stderr or "")
            if "Success" in out:
                print(f"[WG-INSTALL] {dev}: à¸•à¸´à¸”à¸•à¸±à¹‰à¸‡ WireGuard à¸ªà¸³à¹€à¸£à¹‡à¸ˆ âœ“")
            else:
                print(f"[WG-INSTALL] {dev}: à¸•à¸´à¸”à¸•à¸±à¹‰à¸‡à¹„à¸¡à¹ˆà¸ªà¸³à¹€à¸£à¹‡à¸ˆ -> {out.strip()[:200]}")
        except Exception as e:
            print(f"[WG-INSTALL] {dev}: à¸•à¸´à¸”à¸•à¸±à¹‰à¸‡à¸œà¸´à¸”à¸žà¸¥à¸²à¸” {e}")

    def hard_reset_vpn(dev):
        """hard reset VPN state (sync à¸à¸±à¸š login.py) - à¹„à¸¡à¹ˆ pm clear à¹€à¸žà¸£à¸²à¸°à¸ˆà¸°à¸—à¸³à¹ƒà¸«à¹‰ apk à¸«à¸²à¸¢ -> reinstall timeout
        à¸£à¸§à¸¡à¸—à¸¸à¸à¸„à¸³à¸ªà¸±à¹ˆà¸‡à¹€à¸›à¹‡à¸™ script à¹€à¸”à¸µà¸¢à¸§ timeout 15s - à¸›à¸¥à¸­à¸”à¸ à¸±à¸¢à¸–à¹‰à¸² adb/emulator à¹€à¸™à¹ˆà¸²"""
        print(f"[NET-RESET-HARD] {dev}: hard reset VPN state (keep app)...")
        script = (
            f"am broadcast -f 0x20 -p {pkg} -a {pkg}.action.SET_TUNNEL_DOWN --es tunnel lgr 2>/dev/null; "
            f"sleep 1; "
            f"am force-stop {pkg} 2>/dev/null; "
            f"su -c 'rm -f /data/data/{pkg}/files/*.conf; "
            f"rm -rf /data/data/{pkg}/databases/*; "
            f"rm -rf /data/data/{pkg}/shared_prefs/*; "
            f"ip link delete tun0; ip link delete wg0; "
            f"iptables -t mangle -F; iptables -t nat -F; "
            f"ndc resolver clearnetdns wlan0; ndc resolver flushnet wlan0' 2>/dev/null; "
            f"settings delete global always_on_vpn_app 2>/dev/null; "
            f"settings delete global always_on_vpn_lockdown 2>/dev/null; "
            f"settings put global http_proxy :0 2>/dev/null; "
            f"settings delete global http_proxy 2>/dev/null; "
            f"settings delete global global_http_proxy_host 2>/dev/null; "
            f"settings delete global global_http_proxy_port 2>/dev/null; "
            f"echo DONE_HARD_RESET"
        )
        out = sh(dev, script, timeout=15)
        done = "DONE_HARD_RESET" in (out or "")
        tag = "à¸¥à¹‰à¸²à¸‡ tunnels/configs/iptables/DNS/proxy - WG app à¸¢à¸±à¸‡à¸­à¸¢à¸¹à¹ˆ" if done else "à¸¥à¹‰à¸²à¸‡à¸„à¹‰à¸²à¸‡ - à¸šà¸²à¸‡à¸„à¸³à¸ªà¸±à¹ˆà¸‡ timeout (à¸‚à¹‰à¸²à¸¡à¹„à¸›à¸•à¹ˆà¸­)"
        print(f"[NET-RESET-HARD] {dev}: {tag}")

    def one(dev):
        if int(config.get("wg_hard_reset_on_start", 1) or 0):
            hard_reset_vpn(dev)
        ensure_wg_installed(dev)
        had = bool(sh(dev, "ip -o link show 2>/dev/null | grep -E ' tun[0-9]+:' || true").strip())
        if int(config.get("wg_enabled", 1) or 0) and int(config.get("wg_once", 1) or 0):
            # wg_once: VPN à¸•à¹‰à¸­à¸‡à¹€à¸›à¸´à¸”à¹à¸Šà¹ˆà¹„à¸§à¹‰ - à¸•à¸­à¸™à¹€à¸£à¸´à¹ˆà¸¡à¸«à¹‰à¸²à¸¡à¸›à¸´à¸” tunnel à¸—à¸µà¹ˆà¹€à¸›à¸´à¸”à¸­à¸¢à¸¹à¹ˆ à¸¥à¹‰à¸²à¸‡à¹à¸„à¹ˆ proxy à¸„à¹‰à¸²à¸‡
            sh(dev, "settings put global http_proxy :0; settings delete global http_proxy; "
                    "settings delete global global_http_proxy_host; settings delete global global_http_proxy_port")
            print(f"[NET-RESET] {dev}: VPN {'à¹€à¸›à¸´à¸”à¸­à¸¢à¸¹à¹ˆà¹à¸¥à¹‰à¸§ - à¹„à¸¡à¹ˆà¸¢à¸¸à¹ˆà¸‡' if had else 'à¸›à¸´à¸”à¸­à¸¢à¸¹à¹ˆ - à¸ˆà¸°à¹€à¸›à¸´à¸”à¹ƒà¸«à¹‰à¸à¹ˆà¸­à¸™à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡'}")
            return
        sh(dev, f"su -c 'am broadcast -f 0x20 -p {pkg} -a {pkg}.action.SET_TUNNEL_DOWN --es tunnel lgr'")
        time.sleep(1.5)
        sh(dev, f"su -c 'am force-stop {pkg}'")
        sh(dev, "settings put global http_proxy :0; settings delete global http_proxy; "
                "settings delete global global_http_proxy_host; settings delete global global_http_proxy_port")
        still = bool(sh(dev, "ip -o link show 2>/dev/null | grep -E ' tun[0-9]+:' || true").strip())
        ping = sh(dev, "ping -c 1 -W 3 1.1.1.1 >/dev/null 2>&1 && echo OK || echo FAIL", timeout=10).strip()
        state = ("à¸›à¸´à¸” VPN à¸„à¹‰à¸²à¸‡à¹à¸¥à¹‰à¸§" if had else "à¹„à¸¡à¹ˆà¸¡à¸µ VPN à¸„à¹‰à¸²à¸‡") + (" (à¹à¸•à¹ˆ tunnel à¸¢à¸±à¸‡à¸­à¸¢à¸¹à¹ˆ!)" if still else "")
        print(f"[NET-RESET] {dev}: {state} | à¹€à¸™à¹‡à¸•: {'à¹ƒà¸Šà¹‰à¹„à¸”à¹‰' if ping == 'OK' else 'à¸­à¸­à¸à¹€à¸™à¹‡à¸•à¹„à¸¡à¹ˆà¹„à¸”à¹‰!'}")

    print(f"[NET-RESET] à¸¥à¹‰à¸²à¸‡ VPN/proxy à¸„à¹‰à¸²à¸‡à¸—à¸¸à¸à¸ˆà¸­à¸à¹ˆà¸­à¸™à¹€à¸£à¸´à¹ˆà¸¡ ({len(devices)} à¸ˆà¸­)...")
    ts = [threading.Thread(target=one, args=(d,), daemon=True) for d in devices]
    for t in ts:
        t.start()
    for t in ts:
        t.join(60)
    wait = float(config.get("net_reset_wait", 30) or 0)
    if int(config.get("wg_enabled", 1) or 0) and int(config.get("wg_once", 1) or 0):
        wait = 0                     # wg_once: à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸›à¸´à¸” VPN -> à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸£à¸­à¹€à¸™à¹‡à¸•à¸™à¸´à¹ˆà¸‡
    if wait > 0:
        print(f"[NET-RESET] à¸›à¸´à¸” VPN à¸—à¸¸à¸à¸ˆà¸­à¹à¸¥à¹‰à¸§ - à¸£à¸­à¹€à¸™à¹‡à¸•à¸™à¸´à¹ˆà¸‡ {wait:.0f} à¸§à¸´ à¸à¹ˆà¸­à¸™à¹€à¸£à¸´à¹ˆà¸¡à¸—à¸³à¸‡à¸²à¸™...")
        time.sleep(wait)


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
                    capture_output=True, text=True, timeout=15,
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
                    capture_output=True, text=True, timeout=15,
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
    """Auto-scan ALL emulator ports, connect everything that responds"""
    try:
        # Kill & start adb server
        subprocess.run([adb_path, "kill-server"], capture_output=True, timeout=3)
        time.sleep(0.1)
        subprocess.run([adb_path, "start-server"], capture_output=True, timeout=3)
        time.sleep(0.5)

        # à¸ªà¹à¸à¸™à¸žà¸­à¸£à¹Œà¸•à¸„à¸µà¹ˆà¸•à¸±à¹‰à¸‡à¹à¸•à¹ˆ 5555-5755 (à¸£à¸­à¸‡à¸£à¸±à¸š 100 à¸ˆà¸­ MuMu)
        ports = list(range(5555, 5756, 2))  # [5555, 5557, 5559, ..., 5755]

        print(f"\n--- [ADB] Auto-scanning {len(ports)} ports (5555-5755 odd) ---")
        
        connected = []
        
        def try_connect_port(port):
            """à¸¢à¸´à¸‡à¹€à¸Šà¸·à¹ˆà¸­à¸¡à¸•à¹ˆà¸­à¸—à¸µà¸¥à¸°à¸žà¸­à¸£à¹Œà¸•"""
            try:
                addr = f"127.0.0.1:{port}"
                result = subprocess.run(
                    [adb_path, "connect", addr],
                    capture_output=True, timeout=1, text=True
                )
                out = result.stdout.lower()
                if ("connected" in out or "already connected" in out) and "cannot" not in out:
                    return addr
            except Exception:
                pass
            return None

        # à¸¢à¸´à¸‡à¹€à¸Šà¸·à¹ˆà¸­à¸¡à¸•à¹ˆà¸­à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = {executor.submit(try_connect_port, p): p for p in ports}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    connected.append(result)
        
        if connected:
            print(f"[ADB] Port scan found {len(connected)} device(s): {', '.join(sorted(connected))}")
        else:
            print("[ADB] Port scan found no devices.")
                
        print("--- Scan Complete ---\n")
    except Exception as e:
        print(f"[ADB] Port scan error: {e}")


def get_connected_devices():
    """à¸”à¸¶à¸‡à¸£à¸²à¸¢à¸Šà¸·à¹ˆà¸­ devices à¸—à¸µà¹ˆ online à¸ˆà¸²à¸ adb devices (à¹„à¸¡à¹ˆà¸ˆà¸³à¸à¸±à¸”à¸ˆà¸³à¸™à¸§à¸™, à¸à¸£à¸­à¸‡à¸‹à¹‰à¸³)"""
    try:
        result = subprocess.run(
            [adb_path, "devices"],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().split("\n")[1:]
        raw_devices = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                raw_devices.append(parts[0])
        
        if not raw_devices:
            return []
                
        # à¸à¸£à¸­à¸‡à¸‹à¹‰à¸³: à¸–à¹‰à¸²à¸¡à¸µ emulator-5556 à¸­à¸¢à¸¹à¹ˆà¹à¸¥à¹‰à¸§ à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¹€à¸­à¸² 127.0.0.1:5557 à¸­à¸µà¸
        emulator_adb_ports = set()  # à¹€à¸à¹‡à¸šà¸žà¸­à¸£à¹Œà¸• ADB (à¸„à¸µà¹ˆ) à¸—à¸µà¹ˆ emulator-xxx à¸„à¸£à¸­à¸‡
        for d in raw_devices:
            if d.startswith("emulator-"):
                try:
                    console_port = int(d.replace("emulator-", ""))
                    emulator_adb_ports.add(console_port + 1)  # emulator-5556 -> ADB port 5557
                except ValueError:
                    pass
        
        final_devices = []
        seen = set()
        for d in raw_devices:
            if d in seen:
                continue
            # à¸–à¹‰à¸²à¹€à¸›à¹‡à¸™ 127.0.0.1:port à¹à¸¥à¹‰à¸§à¸¡à¸µ emulator- à¸„à¸£à¸­à¸‡à¸­à¸¢à¸¹à¹ˆà¹à¸¥à¹‰à¸§ -> à¸‚à¹‰à¸²à¸¡
            if d.startswith("127.0.0.1:"):
                try:
                    port = int(d.split(":")[1])
                    if port in emulator_adb_ports:
                        continue  # à¸‹à¹‰à¸³à¸à¸±à¸š emulator-xxxx
                except ValueError:
                    pass
            seen.add(d)
            final_devices.append(d)
        
        return final_devices
    except Exception as e:
        print(f"[ERR] get_connected_devices: {e}")
        return []


def ImgSearchADB(adb_img, find_img_path, threshold=0.95, method=cv2.TM_CCOEFF_NORMED):
    try:
        find_img = cv2.imread(find_img_path, cv2.IMREAD_COLOR)
        if find_img is None:
            return []
        
        needle_w = find_img.shape[1]
        needle_h = find_img.shape[0]
        result = cv2.matchTemplate(adb_img, find_img, method)
        locations = np.where(result >= threshold)
        locations = list(zip(*locations[::-1]))
        rectangles = []
        for loc in locations:
            rect = [int(loc[0]), int(loc[1]), needle_w, needle_h]
            rectangles.append(rect)
            rectangles.append(rect)
        if len(rectangles):
            rectangles, _ = cv2.groupRectangles(rectangles, groupThreshold=1, eps=1)
        points = []
        if len(rectangles):
            for (x, y, w, h) in rectangles:
                center_x = x + int(w / 2)
                center_y = y + int(h / 2)
                points.append((center_x, center_y))
        return points
    except Exception as e:
        return []

class NetworkMonitor:
    def __init__(self):
        self.last_check = time.time()
        self.check_interval = 10
        
    def check_network(self, bot, adb_img):
        current_time = time.time()
        if current_time - self.last_check >= self.check_interval:
            fixnet_pos = ImgSearchADB(adb_img, 'img/fixnet.png')
            if fixnet_pos:
                print(f"[{bot.device_id}] à¸žà¸šà¸›à¸±à¸à¸«à¸²à¸à¸²à¸£à¹€à¸Šà¸·à¹ˆà¸­à¸¡à¸•à¹ˆà¸­ (fixnet.png)")
                bot.tap(fixnet_pos[0][0], fixnet_pos[0][1])
                time.sleep(1)
                return True
            self.last_check = current_time
        return False

def check_critical_errors(bot, adb_img, context=""):
    """
    à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸š fixid.png, fixunkown.png, apple.png
    """
    try:
        # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸š fixid.png
        fixid_pos = ImgSearchADB(adb_img, 'img/fixid.png')
        if fixid_pos:
            print(f"[{bot.device_id}] âš ï¸ Found fixid.png in {context}!")
            bot.backup_to_backupxml()
            bot.clear_and_restart()
            time.sleep(6)
            return "fixid"
        
        # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸š fixunkown.png
        fixunkown_pos = ImgSearchADB(adb_img, 'img/fixunkown.png')
        if fixunkown_pos:
            print(f"[{bot.device_id}] âš ï¸ Found fixunkown.png in {context}!")
            bot.backup_to_backupxml()
            bot.clear_and_restart()
            time.sleep(6)
            return "fixunkown"
        
        # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸š apple.png
        apple_pos = ImgSearchADB(adb_img, 'img/apple.png')
        if apple_pos:
            print(f"[{bot.device_id}] âš ï¸ Found apple.png in {context}!")
            bot.backup_failed_login()
            bot.clear_and_restart()
            time.sleep(6)
            return "apple"
            
        # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸š fixnet1.png / fixnet.png (à¸›à¸±à¸à¸«à¸²à¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”à¹€à¸”à¹‰à¸‡à¸›à¹Šà¸­à¸›à¸­à¸±à¸ž)
        fixnet_pos = ImgSearchADB(adb_img, 'img/fixnet1.png') or ImgSearchADB(adb_img, 'img/fixnet.png')
        if fixnet_pos:
            print(f"[{bot.device_id}] ðŸ“¶ à¸žà¸šà¸›à¸±à¸à¸«à¸²à¸à¸²à¸£à¹€à¸Šà¸·à¹ˆà¸­à¸¡à¸•à¹ˆà¸­ (fixnet1/fixnet) à¹ƒà¸™ {context} - à¸à¸³à¸¥à¸±à¸‡à¸à¸” OK...")
            _signal_host_vpn_rotate(f"fixnet {bot.device_id} {context}")
            bot.tap(fixnet_pos[0][0], fixnet_pos[0][1])
            time.sleep(1)
        
        return None
    except Exception as e:
        print(f"[ERROR] check_critical_errors: {e}")
        return None

# =============================================================
# RangerGearBot Class - Unified Bot for Ranger + Gear
# =============================================================
class RangerGearBot(threading.Thread):
    PIDOF_INTERVAL = 3.0   # seconds between app-alive checks (see check_error_images)

    @property
    def SCAN_INTERVAL(self):
        """Seconds between full popup/error sweeps. 0 = every frame (old behaviour)."""
        try:
            return float(config.get("scan_interval", 1.0))
        except (TypeError, ValueError):
            return 1.0

    def loop_delay(self, default):
        """Pause between polls in a wait-for-image loop.

        Returns `default` (whatever that loop used before) unless "loop_delay" is
        set in the config, so behaviour is unchanged out of the box. Lower = spots
        a button sooner but issues more screencaps, which is adb-bound, so the
        right value depends on how many emulators are running - tune per machine.
        """
        v = config.get("loop_delay")
        if v is None:
            return max(default, self._adb_backoff())
        try:
            return max(float(v), self._adb_backoff())
        except (TypeError, ValueError):
            return default

    def _adb_backoff(self):
        """à¹€à¸£à¹‡à¸§à¸ªà¸¸à¸”à¹à¸•à¹ˆà¹„à¸¡à¹ˆà¹ƒà¸«à¹‰ offline: à¹à¸„à¸›à¸ˆà¸­ timeout -> à¸Šà¸°à¸¥à¸­ adb_backoff_delay à¸§à¸´ à¸™à¸²à¸™ adb_backoff_sec à¸§à¸´ à¹à¸¥à¹‰à¸§à¸à¸¥à¸±à¸šà¸¡à¸²à¹€à¸£à¹‡à¸§à¹€à¸­à¸‡"""
        t = getattr(self, "_adb_slow_until", 0)
        return float(config.get("adb_backoff_delay", 1.0)) if time.time() < t else 0.0

    def __init__(self, device_id, args=None):
        threading.Thread.__init__(self)
        self.device_id = device_id
        self.args = args # Store command line args
        self.daemon = True
        
        def update_gui_status(self, step, status="working"):
            ui_stats.update_device(self.device_id, {'step': step, 'status': status})
        self.update_gui_status = update_gui_status.__get__(self, RangerGearBot)
        
        # 1. Initialize attributes with defaults (CRITICAL Fix: prevents missing attribute errors)
        self.characters = []
        self.ranger_files = []
        self.ranger_image_mapping = {}
        self.gear_names = {}
        self.weapon_names = {}
        self.ocr_region = {"x": 463, "y": 153, "w": 397, "h": 321}
        self.current_original_filename = None
        
        # 2. Determine initial modes and load values
        self.do_ranger = config.get("find_ranger", 0) or config.get("find_all", 1)
        self.do_gear = config.get("find_gear", 0) or config.get("find_all", 1)
        print(f"[{self.device_id}] Mode - Ranger: {self.do_ranger}, Gear: {self.do_gear}")
        
        # Unique filename for this thread
        safe_dev = device_id.replace(":", "_")
        self.filename = os.path.join(tempfile.gettempdir(), f"screen-{safe_dev}.png")
        self.first_loop_done = not config.get("first_loop", True)
        
        # Load values from config regardless of current mode to allow switching
        if config.get("custommode") == 1:
            custom_data = config.get("custom", {})
            self.characters = custom_data.get("characters", [])
        else:
            self.characters = config.get("characters", [])
        
        self.ranger_image_mapping = config.get("ranger_images", {})
        ranger_folder = os.path.normpath(os.path.join("img", "ranger"))
        if os.path.exists(ranger_folder):
            for f in sorted(os.listdir(ranger_folder)):
                if f.lower().endswith(".png"):
                    self.ranger_files.append(f"ranger/{f}")
        
        self.gear_names = config.get("gearname", {})
        self.weapon_names = config.get("weaponname", {})
        self.ocr_region = config.get("ocr_region", self.ocr_region)
        
        # Sequence Definitions (Reverted to use coordinates for checkboxes)
        self.seq1 = ['icon.png', 'apple.png', '@check-l1.png', (932, 133), (930, 253), (926, 327), 'check-l4.png']
        self.seq2 = ['check-gusetid.png', 'check-gusetid1.png', '@check-l1.png', (932, 133), (930, 253), (926, 327), 'check-l4.png', 'check-ok1.png', 'check-ok2.png', 'check-ok3.png', 'check-ok4.png']
        
        self.adb_cmd = adb_path
        self._screen = None
        self._screen_color = None
        self._screen_raw_png = None  # raw PNG bytes for lazy color decode (fallback path)
        self._screen_rgba = None     # raw RGBA frame for lazy color decode (fast path)
        self._template_cache = {}
        self._black_start_time = None
        self._fixnetv3_count = 0
        self._need_restart = False
        self._running = True
        self._capture_count = 0  # throttle popup checks

        # Bumped on every new frame. check_floating_popups() uses it to avoid
        # re-scanning the same frame twice (it gets called from the loop AND
        # from check_error_images).
        self._screen_gen = 0
        self._popups_clean_gen = -1
        self._tap_count = 0
        self._last_pidof_check = 0.0
        self._app_gone_cached = False
        self._last_popup_scan = 0.0
        self._last_error_scan = 0.0

        # --- Speed helpers ---------------------------------------------------
        # Remembered button positions: after the first full-screen match we only
        # re-check a small ROI around the last hit instead of scanning again.
        if TOUCH_HELPER_AVAILABLE:
            self._pos_mem = touch_helper.PositionMemory(
                enabled=bool(config.get("pos_cache", 1)),
                margin=int(config.get("pos_cache_margin", 12)),
                label=self.device_id,
            )
        else:
            self._pos_mem = None
        # minitouch is started lazily on the first tap so startup stays fast.
        self._minitouch = None
        self._minitouch_tried = False

        # Start background monitor thread
        self.monitor_thread = threading.Thread(target=self._popup_monitor_loop, daemon=True)
        self.monitor_thread.start()

    # à¸£à¸¹à¸›à¹„à¸à¹ˆà¸šà¸µà¹‰à¸—à¸¸à¸à¹à¸šà¸š - à¹€à¸žà¸´à¹ˆà¸¡à¸•à¸±à¸§à¹ƒà¸«à¸¡à¹ˆà¸—à¸µà¹ˆà¸™à¸µà¹ˆà¸—à¸µà¹ˆà¹€à¸”à¸µà¸¢à¸§ à¸—à¸¸à¸à¸ˆà¸¸à¸”à¸—à¸µà¹ˆà¹€à¸Šà¹‡à¸„à¹ƒà¸Šà¹‰à¸¥à¸´à¸ªà¸•à¹Œà¸™à¸µà¹‰à¸£à¹ˆà¸§à¸¡à¸à¸±à¸™
    KAIBY_IMAGES = ("img/kaiby.png", "img/kaiby1.png", "img/kaiby2.bmp")

    def find_kaiby(self, similarity=0.95):
        """à¸„à¸·à¸™à¸Šà¸·à¹ˆà¸­à¸£à¸¹à¸›à¹„à¸à¹ˆà¸šà¸µà¹‰à¸•à¸±à¸§à¹à¸£à¸à¸—à¸µà¹ˆà¹€à¸ˆà¸­à¸šà¸™à¸ˆà¸­à¸—à¸µà¹ˆà¸ˆà¸±à¸šà¹„à¸§à¹‰ (None = à¹„à¸¡à¹ˆà¹€à¸ˆà¸­)"""
        for path in self.KAIBY_IMAGES:
            if self.exists_in_cache(path, similarity=similarity):
                return os.path.basename(path)
        return None

    def _log_pos_cache(self, every_sec=120):
        """Occasionally report how often the remembered positions are paying off."""
        if self._pos_mem is None or not self._pos_mem.enabled:
            return
        now = time.time()
        if now - getattr(self, "_pos_cache_logged_at", 0) < every_sec:
            return
        self._pos_cache_logged_at = now
        print(f"[{self.device_id}] {self._pos_mem.summary()}")

    # à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”à¸—à¸µà¹ˆà¸•à¹‰à¸­à¸‡à¸à¸”à¸›à¸´à¸”à¹ƒà¸«à¹‰à¹„à¸”à¹‰ à¹„à¸¡à¹ˆà¸§à¹ˆà¸²à¸šà¸­à¸—à¸ˆà¸°à¸­à¸¢à¸¹à¹ˆà¸¥à¸¹à¸›à¹„à¸«à¸™
    NET_POPUPS = ("img/fixnet-tiket.png", "img/fixnet1.png", "img/fixnet.png",   # à¸•à¸±à¸§à¹à¸£à¸ = à¸£à¸¹à¸›à¸ˆà¸²à¸ bot-tiket
                  "img/fixplay.png")   # PLAY: à¹€à¸Šà¹‡à¸„à¸•à¸¥à¸­à¸”à¹€à¸«à¸¡à¸·à¸­à¸™ fixnet (à¸—à¸¸à¸à¸„à¸£à¸±à¹‰à¸‡à¸—à¸µà¹ˆà¸ˆà¸±à¸šà¸ˆà¸­ + monitor à¹€à¸šà¸·à¹‰à¸­à¸‡à¸«à¸¥à¸±à¸‡ à¸à¸”à¸‹à¹‰à¸³à¸ˆà¸™à¸«à¸²à¸¢)
    NET_POPUP_LIMIT = 10   # à¸à¸”à¸„à¸£à¸šà¹€à¸—à¹ˆà¸²à¸™à¸µà¹‰à¹à¸¥à¹‰à¸§à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸«à¸²à¸¢ = à¹€à¸”à¹‰à¸‡à¹à¸­à¸›à¹ƒà¸«à¸¡à¹ˆ à¸”à¸µà¸à¸§à¹ˆà¸²à¸„à¹‰à¸²à¸‡à¸£à¸­à¹€à¸‰à¸¢ à¹†
    # à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•à¸—à¸µà¹ˆà¸à¸”à¸›à¸´à¸”à¹à¸¥à¹‰à¸§à¸¡à¸µà¸«à¸™à¹‰à¸²à¸•à¹ˆà¸²à¸‡à¸•à¹ˆà¸­à¸—à¹‰à¸²à¸¢à¹ƒà¸«à¹‰à¸à¸”à¸­à¸µà¸à¸—à¸µ: à¸Šà¸·à¹ˆà¸­à¸£à¸¹à¸›à¸—à¸µà¹ˆà¸à¸” -> (à¸£à¸¹à¸›à¸›à¸¸à¹ˆà¸¡à¸•à¹ˆà¸­à¸—à¹‰à¸²à¸¢, à¸£à¸­à¸ªà¸¹à¸‡à¸ªà¸¸à¸”à¸à¸µà¹ˆà¸§à¸´)
    NET_FOLLOWUP = {"fixplay.png": ("img/check-ok1.png", 120)}   # à¸à¸” PLAY à¹à¸¥à¹‰à¸§à¸•à¹‰à¸­à¸‡à¸£à¸­à¸à¸” OK à¸•à¹ˆà¸­

    def _match_score(self, template_path):
        """à¸„à¸°à¹à¸™à¸™ match à¸ªà¸¹à¸‡à¸ªà¸¸à¸”à¸‚à¸­à¸‡à¸£à¸¹à¸›à¸šà¸™à¸ˆà¸­à¸¥à¹ˆà¸²à¸ªà¸¸à¸” (0-1) - à¹„à¸§à¹‰à¸šà¸­à¸à¹ƒà¸™ log à¸§à¹ˆà¸² 'à¹€à¸à¸·à¸­à¸šà¹€à¸ˆà¸­' à¸«à¸£à¸·à¸­ 'à¹„à¸¡à¹ˆà¹€à¸ˆà¸­à¹€à¸¥à¸¢'"""
        try:
            tmpl = self._get_template(template_path)
            if self._screen is None or tmpl is None:
                return 0.0
            th, tw = tmpl.shape[:2]
            if self._screen.shape[0] < th or self._screen.shape[1] < tw:
                return 0.0
            res = cv2.matchTemplate(self._screen, tmpl, cv2.TM_CCOEFF_NORMED)
            return float(cv2.minMaxLoc(res)[1])
        except Exception:
            return 0.0

    def _save_debug_screen(self, reason):
        """à¹€à¸à¹‡à¸šà¸ à¸²à¸žà¸ˆà¸­à¸¥à¹ˆà¸²à¸ªà¸¸à¸”à¹„à¸§à¹‰à¸”à¸¹à¸§à¹ˆà¸²à¸„à¹‰à¸²à¸‡/à¸«à¸²à¹„à¸¡à¹ˆà¹€à¸ˆà¸­à¸­à¸¢à¸¹à¹ˆà¸«à¸™à¹‰à¸²à¹„à¸«à¸™ (à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œ debug-timeout/)"""
        if not int(config.get("debug_screens", 0) or 0):
            return None   # à¸›à¸´à¸”à¹„à¸§à¹‰: 15 à¸ˆà¸­à¹€à¸‚à¸µà¸¢à¸™à¸ à¸²à¸žà¸¥à¸‡à¸”à¸´à¸ªà¸à¹Œà¸šà¹ˆà¸­à¸¢à¹€à¸à¸´à¸™ à¹€à¸›à¸¥à¸·à¸­à¸‡à¸”à¸´à¸ªà¸à¹Œ+à¹€à¸§à¸¥à¸² (à¹€à¸›à¸´à¸”à¸”à¹‰à¸§à¸¢ "debug_screens": 1)
        screen = getattr(self, "_screen_color", None)
        if screen is None:
            return None
        try:
            folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug-timeout")
            os.makedirs(folder, exist_ok=True)
            name = f"{self.device_id.replace(':', '_')}_{time.strftime('%Y%m%d-%H%M%S')}_{reason}.png"
            cv2.imwrite(os.path.join(folder, name), screen)
            return os.path.join("debug-timeout", name)
        except Exception:
            return None

    # template à¸—à¸¸à¸à¸£à¸¹à¸›à¹ƒà¸™ img/ à¸–à¸¹à¸à¸•à¸±à¸”à¸¡à¸²à¸ˆà¸²à¸à¸ˆà¸­ 960x540 (à¹€à¸«à¸¡à¸·à¸­à¸™ bot-tiket à¸—à¸µà¹ˆà¸šà¸±à¸‡à¸„à¸±à¸š "à¸•à¹‰à¸­à¸‡à¹€à¸›à¹‡à¸™ 960x540")
    # à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¹„à¸«à¸™à¸•à¸±à¹‰à¸‡à¸„à¸§à¸²à¸¡à¸¥à¸°à¹€à¸­à¸µà¸¢à¸”à¸­à¸·à¹ˆà¸™ à¸›à¸¸à¹ˆà¸¡à¸šà¸™à¸ˆà¸­à¸ˆà¸°à¹ƒà¸«à¸à¹ˆ/à¹€à¸¥à¹‡à¸à¸à¸§à¹ˆà¸²à¸£à¸¹à¸› -> matchTemplate à¸«à¸²à¹„à¸¡à¹ˆà¹€à¸ˆà¸­à¸—à¸±à¹‰à¸‡à¹„à¸Ÿà¸¥à¹Œ
    BASE_W, BASE_H = 960, 540

    def _normalize_frame(self):
        """à¸¢à¹ˆà¸­/à¸‚à¸¢à¸²à¸¢à¹€à¸Ÿà¸£à¸¡à¹ƒà¸«à¹‰à¹€à¸›à¹‡à¸™ 960x540 à¹€à¸ªà¸¡à¸­ à¹à¸¥à¹‰à¸§à¸ˆà¸³à¸­à¸±à¸•à¸£à¸²à¸ªà¹ˆà¸§à¸™à¹„à¸§à¹‰à¸ªà¹€à¸à¸¥à¸ˆà¸¸à¸”à¸à¸”à¸à¸¥à¸±à¸šà¹€à¸›à¹‡à¸™à¸žà¸´à¸à¸±à¸”à¸ˆà¸£à¸´à¸‡"""
        self._screen_ts = time.time()   # à¹€à¸§à¸¥à¸²à¸—à¸µà¹ˆà¹„à¸”à¹‰à¹€à¸Ÿà¸£à¸¡à¸¥à¹ˆà¸²à¸ªà¸¸à¸” (monitor à¹ƒà¸Šà¹‰à¸”à¸¹à¸§à¹ˆà¸²à¹€à¸Ÿà¸£à¸¡à¸„à¹‰à¸²à¸‡à¹„à¸«à¸¡)
        scr = self._screen
        if scr is None:
            self._tap_scale = (1.0, 1.0)
            return
        h, w = scr.shape[:2]
        if (w, h) == (self.BASE_W, self.BASE_H):
            self._tap_scale = (1.0, 1.0)
            return
        sx, sy = w / self.BASE_W, h / self.BASE_H
        if getattr(self, "_res_notice", None) != (w, h):
            self._res_notice = (w, h)
            print(f"[{self.device_id}] [SCREEN] à¸ˆà¸­ {w}x{h} à¹„à¸¡à¹ˆà¹ƒà¸Šà¹ˆ 960x540 -> à¸¢à¹ˆà¸­à¸ à¸²à¸žà¹ƒà¸«à¹‰à¸•à¸£à¸‡ template "
                  f"à¹à¸¥à¸°à¸ªà¹€à¸à¸¥à¸ˆà¸¸à¸”à¸à¸” x{sx:.2f}/x{sy:.2f} à¹ƒà¸«à¹‰à¸­à¸±à¸•à¹‚à¸™à¸¡à¸±à¸•à¸´")
        self._screen = cv2.resize(scr, (self.BASE_W, self.BASE_H), interpolation=cv2.INTER_AREA)
        if getattr(self, "_screen_color", None) is not None:
            self._screen_color = cv2.resize(self._screen_color, (self.BASE_W, self.BASE_H), interpolation=cv2.INTER_AREA)
        self._tap_scale = (sx, sy)

    def _dev_xy(self, x, y):
        """à¸žà¸´à¸à¸±à¸”à¸šà¸™à¸ à¸²à¸ž 960x540 -> à¸žà¸´à¸à¸±à¸”à¸ˆà¸£à¸´à¸‡à¸šà¸™à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ (à¸ªà¸³à¸«à¸£à¸±à¸š adb input tap/swipe)"""
        sx, sy = getattr(self, "_tap_scale", (1.0, 1.0))
        return int(round(x * sx)), int(round(y * sy))

    def _adb_tap(self, x, y):
        """à¸à¸”à¸”à¹‰à¸§à¸¢ adb shell input tap à¸•à¸£à¸‡ à¹† (à¹„à¸¡à¹ˆà¸œà¹ˆà¸²à¸™ minitouch) - à¹€à¸«à¸¡à¸·à¸­à¸™ bot-tiket

        minitouch à¸„à¸·à¸™ True à¹à¸„à¹ˆ 'à¸ªà¹ˆà¸‡à¸„à¸³à¸ªà¸±à¹ˆà¸‡à¸¥à¸‡ socket à¹„à¸”à¹‰' à¹„à¸¡à¹ˆà¸£à¸¹à¹‰à¸§à¹ˆà¸²à¸ªà¸±à¸¡à¸œà¸±à¸ªà¸–à¸¶à¸‡à¸ˆà¸­à¸ˆà¸£à¸´à¸‡à¹„à¸«à¸¡
        à¸žà¸­ minitouch à¸„à¹‰à¸²à¸‡ à¸šà¸­à¸—à¸ˆà¸°à¸„à¸´à¸”à¸§à¹ˆà¸²à¸à¸”à¹à¸¥à¹‰à¸§à¸—à¸±à¹‰à¸‡à¸—à¸µà¹ˆà¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¸¢à¸±à¸‡à¸­à¸¢à¸¹à¹ˆ (log: à¸à¸”à¸›à¸´à¸”à¹ƒà¸«à¹‰à¹à¸¥à¹‰à¸§ #3 à¹à¸•à¹ˆà¹„à¸¡à¹ˆà¸«à¸²à¸¢)
        à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•à¸ªà¸³à¸„à¸±à¸à¹€à¸à¸´à¸™à¸à¸§à¹ˆà¸²à¸ˆà¸°à¹€à¸ªà¸µà¹ˆà¸¢à¸‡ à¸ˆà¸¶à¸‡à¸¢à¸´à¸‡ input tap à¸•à¸£à¸‡ à¹† à¹€à¸ªà¸¡à¸­
        """
        dx, dy = self._dev_xy(x, y)
        try:
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "input", "tap", str(dx), str(dy)], timeout=8)
            return True
        except Exception as e:
            print(f"[{self.device_id}] [NET] adb input tap à¹„à¸¡à¹ˆà¸ªà¸³à¹€à¸£à¹‡à¸ˆ: {e}")
            return False

    # à¸ªà¹€à¸à¸¥à¸—à¸µà¹ˆ monitor à¹€à¸šà¸·à¹‰à¸­à¸‡à¸«à¸¥à¸±à¸‡à¸¥à¸­à¸‡à¹„à¸¥à¹ˆ (à¹€à¸œà¸·à¹ˆà¸­à¹€à¸à¸¡à¸§à¸²à¸” UI à¹ƒà¸«à¸à¹ˆ/à¹€à¸¥à¹‡à¸à¸à¸§à¹ˆà¸²à¸£à¸¹à¸›à¸—à¸µà¹ˆà¸•à¸±à¸”à¹„à¸§à¹‰ à¹à¸¡à¹‰à¸ˆà¸­à¸ˆà¸° 960x540)
    # à¹„à¸¥à¹ˆà¸–à¸µà¹ˆà¸‚à¸¶à¹‰à¸™: à¹€à¸­à¸²à¸£à¸¹à¸› RETRY 3 à¹€à¸§à¸­à¸£à¹Œà¸Šà¸±à¸™à¸¡à¸² match à¸à¸±à¸™à¹€à¸­à¸‡ à¸ªà¹€à¸à¸¥à¹€à¸žà¸µà¹‰à¸¢à¸™à¹à¸„à¹ˆ 5% à¸„à¸°à¹à¸™à¸™à¸à¹‡à¸•à¸à¹€à¸«à¸¥à¸·à¸­ ~0.80 à¸žà¸­à¸”à¸µà¹€à¸à¸“à¸‘à¹Œà¹à¸¥à¹‰à¸§
    # à¸Šà¸¸à¸”à¹€à¸”à¸´à¸¡à¸à¸£à¸°à¹‚à¸”à¸”à¸ˆà¸²à¸ 1.0 à¹„à¸› 1.33 à¹€à¸¥à¸¢ à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸—à¸µà¹ˆà¸§à¸²à¸” UI à¹ƒà¸«à¸à¹ˆà¸à¸§à¹ˆà¸²à¸£à¸¹à¸› 10-25% à¸ˆà¸¶à¸‡à¸žà¸¥à¸²à¸”à¸—à¸¸à¸à¸ªà¹€à¸à¸¥à¹à¸šà¸šà¹€à¸‡à¸µà¸¢à¸š à¹† (fixnet à¹„à¸¡à¹ˆà¸à¸”)
    NET_SCALES = (1.0, 1.1, 0.9, 1.2, 1.25, 0.8, 1.33, 1.4, 0.75, 1.5, 0.67, 0.6, 1.67, 2.0, 0.5)
    NET_SIM_GREEN = 0.65   # à¸›à¸¸à¹ˆà¸¡à¹ƒà¸™ NET_POPUPS à¹€à¸›à¹‡à¸™à¸›à¸¸à¹ˆà¸¡à¹€à¸‚à¸µà¸¢à¸§à¸ªà¸”à¸—à¸±à¹‰à¸‡à¸«à¸¡à¸”: à¸ˆà¸¸à¸”à¸—à¸µà¹ˆà¹€à¸ˆà¸­à¹€à¸›à¹‡à¸™à¸ªà¸µà¹€à¸‚à¸µà¸¢à¸§à¸ˆà¸£à¸´à¸‡ (à¹€à¸Šà¹‡à¸„à¸ˆà¸²à¸à¸ à¸²à¸žà¸ªà¸µ) à¸¢à¸­à¸¡à¸£à¸±à¸šà¸„à¸°à¹à¸™à¸™à¸•à¹ˆà¸³à¸¥à¸‡à¹„à¸”à¹‰
    NET_NEAR_MISS = 0.55   # à¸„à¸°à¹à¸™à¸™à¸•à¸±à¹‰à¸‡à¹à¸•à¹ˆà¸™à¸µà¹‰à¹à¸•à¹ˆà¹„à¸¡à¹ˆà¸–à¸¶à¸‡à¹€à¸à¸“à¸‘à¹Œ = "à¹€à¸à¸·à¸­à¸šà¹€à¸ˆà¸­" -> log + à¹€à¸à¹‡à¸šà¸ à¸²à¸žà¹„à¸§à¹‰à¹ƒà¸«à¹‰à¸”à¸¹ (à¹„à¸¡à¹ˆà¸à¸”)
    # à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¸—à¸µà¹ˆ 'à¸£à¸¹à¸›à¸•à¸£à¸§à¸ˆà¸ˆà¸±à¸š' à¸à¸±à¸š 'à¸›à¸¸à¹ˆà¸¡à¸—à¸µà¹ˆà¸•à¹‰à¸­à¸‡à¸à¸”' à¹€à¸›à¹‡à¸™à¸„à¸™à¸¥à¸°à¸£à¸¹à¸›: à¹€à¸ˆà¸­à¸•à¸±à¸§à¸‹à¹‰à¸²à¸¢ -> à¸«à¸²à¹à¸¥à¹‰à¸§à¸à¸”à¸•à¸±à¸§à¸‚à¸§à¸²
    NET_DETECT_THEN_TAP = (("img/fixnetv2.png", "img/fixnetv2ok.png"),)

    def _best_match(self, screen, path, similarity, scales):
        """à¸„à¸·à¸™ (score, cx, cy, scale) à¸—à¸µà¹ˆà¸”à¸µà¸—à¸µà¹ˆà¸ªà¸¸à¸”à¸‚à¸­à¸‡à¸£à¸¹à¸›à¸šà¸™à¸ˆà¸­ à¸«à¸£à¸·à¸­ None à¸–à¹‰à¸²à¸•à¹ˆà¸³à¸à¸§à¹ˆà¸² similarity"""
        tmpl0 = self._get_template(path)
        if tmpl0 is None:
            return None
        best = None
        for sc in scales:
            if sc == 1.0:
                tmpl = tmpl0
            else:
                tmpl = cv2.resize(tmpl0, None, fx=sc, fy=sc,
                                  interpolation=cv2.INTER_AREA if sc < 1 else cv2.INTER_CUBIC)
            th, tw = tmpl.shape[:2]
            if screen.shape[0] < th or screen.shape[1] < tw:
                continue
            res = cv2.matchTemplate(screen, tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val >= similarity and (best is None or max_val > best[0]):
                best = (max_val, max_loc[0] + tw // 2, max_loc[1] + th // 2, sc)
        return best

    NET_RETRY_ROUNDS = 25   # à¸à¸”à¸‹à¹‰à¸³à¸ªà¸¹à¸‡à¸ªà¸¸à¸”à¸•à¹ˆà¸­à¸£à¸­à¸š (à¸«à¹ˆà¸²à¸‡à¸à¸±à¸™ ~1.2 à¸§à¸´ = à¸£à¸²à¸§ 30 à¸§à¸´) à¸à¹ˆà¸­à¸™à¸›à¸¥à¹ˆà¸­à¸¢à¹ƒà¸«à¹‰à¸£à¸­à¸šà¸–à¸±à¸”à¹„à¸›à¸¥à¸­à¸‡à¸•à¹ˆà¸­

    def _clear_net_popup_loop(self, first_hit):
        """à¸à¸”à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•à¸‹à¹‰à¸³ à¹† à¸ˆà¸™à¸à¸§à¹ˆà¸²à¸ˆà¸°à¸«à¸²à¸¢à¹„à¸›à¸ˆà¸²à¸à¸ˆà¸­ (à¹€à¸™à¹‡à¸•à¸ªà¸°à¸”à¸¸à¸” RETRY à¸„à¸£à¸±à¹‰à¸‡à¹€à¸”à¸µà¸¢à¸§à¸¡à¸±à¸à¹„à¸¡à¹ˆà¸žà¸­)

        à¹€à¸£à¸µà¸¢à¸à¸«à¸¥à¸±à¸‡à¸ˆà¸²à¸à¸à¸”à¸„à¸£à¸±à¹‰à¸‡à¹à¸£à¸à¹„à¸›à¹à¸¥à¹‰à¸§: à¸£à¸­ -> à¸ˆà¸±à¸šà¸ˆà¸­à¹ƒà¸«à¸¡à¹ˆ -> à¸¢à¸±à¸‡à¹€à¸«à¹‡à¸™à¸­à¸¢à¸¹à¹ˆà¸à¹‡à¸à¸”à¸­à¸µà¸ à¸§à¸™à¸ˆà¸™à¸«à¸²à¸¢
        à¸«à¸£à¸·à¸­à¸„à¸£à¸š NET_RETRY_ROUNDS à¹à¸¥à¹‰à¸§à¸›à¸¥à¹ˆà¸­à¸¢ (monitor à¹€à¸šà¸·à¹‰à¸­à¸‡à¸«à¸¥à¸±à¸‡à¸ˆà¸°à¹€à¸à¹‡à¸šà¸•à¹ˆà¸­ / à¹€à¸à¸´à¸™ limit à¸ˆà¸°à¹€à¸”à¹‰à¸‡à¹à¸­à¸›)
        """
        rounds = 1
        while rounds < self.NET_RETRY_ROUNDS:
            sleep(1.2)
            try:
                self._raw_capture()
            except Exception:
                pass
            self._netpopup_last_click = 0          # à¹ƒà¸«à¹‰à¸à¸”à¸‹à¹‰à¸³à¹„à¸”à¹‰à¸—à¸±à¸™à¸—à¸µ à¹„à¸¡à¹ˆà¸•à¸´à¸” cooldown
            hit = self._dismiss_net_popup(self._screen, scales=(getattr(self, "_net_scale", 1.0),))
            if not hit:
                print(f"[{self.device_id}] [NET] {first_hit} à¸«à¸²à¸¢à¹à¸¥à¹‰à¸§à¸«à¸¥à¸±à¸‡à¸à¸” {rounds} à¸„à¸£à¸±à¹‰à¸‡")
                self._net_followup(first_hit)   # à¹€à¸Šà¹ˆà¸™ PLAY à¸«à¸²à¸¢à¹à¸¥à¹‰à¸§à¸•à¹‰à¸­à¸‡à¸£à¸­à¸à¸” OK à¸•à¹ˆà¸­ (NET_FOLLOWUP)
                return True
            rounds += 1
        print(f"[{self.device_id}] [NET] à¸à¸” {first_hit} à¹„à¸› {rounds} à¸„à¸£à¸±à¹‰à¸‡à¹à¸¥à¹‰à¸§à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸«à¸²à¸¢ (à¹€à¸™à¹‡à¸•à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸à¸¥à¸±à¸šà¸¡à¸²) - à¸›à¸¥à¹ˆà¸­à¸¢à¹ƒà¸«à¹‰à¸£à¸­à¸šà¸–à¸±à¸”à¹„à¸›à¸¥à¸­à¸‡à¸•à¹ˆà¸­")
        return False

    def _net_followup(self, first_hit):
        """à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•à¸šà¸²à¸‡à¸•à¸±à¸§à¸à¸”à¸›à¸´à¸”à¹à¸¥à¹‰à¸§à¸¡à¸µà¸«à¸™à¹‰à¸²à¸•à¹ˆà¸²à¸‡à¸•à¹ˆà¸­à¸—à¹‰à¸²à¸¢à¹ƒà¸«à¹‰à¸à¸”à¸­à¸µà¸à¸—à¸µ (PLAY -> OK) à¸”à¸¹ NET_FOLLOWUP

        à¹€à¸£à¸µà¸¢à¸à¸«à¸¥à¸±à¸‡à¸ˆà¸²à¸ _clear_net_popup_loop à¹€à¸«à¹‡à¸™à¸§à¹ˆà¸²à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¸«à¸²à¸¢à¹à¸¥à¹‰à¸§: à¸ˆà¸±à¸šà¸ˆà¸­à¸§à¸™à¸£à¸­à¸ˆà¸™à¹€à¸ˆà¸­à¸›à¸¸à¹ˆà¸¡à¸•à¹ˆà¸­à¸—à¹‰à¸²à¸¢
        à¹à¸¥à¹‰à¸§à¸à¸”à¸œà¹ˆà¸²à¸™ adb à¸•à¸£à¸‡ à¹† (à¹€à¸«à¸¡à¸·à¸­à¸™à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•à¸•à¸±à¸§à¸­à¸·à¹ˆà¸™) à¸£à¸°à¸«à¸§à¹ˆà¸²à¸‡à¸£à¸­à¸–à¹‰à¸²à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•à¹€à¸”à¹‰à¸‡à¸à¸¥à¸±à¸šà¸¡à¸²
        (PLAY à¸­à¸µà¸à¸£à¸­à¸š / RETRY) à¸à¹‡à¸à¸”à¹ƒà¸«à¹‰à¹€à¸¥à¸¢ à¸£à¸­à¸ˆà¸™à¸«à¸¡à¸”à¹€à¸§à¸¥à¸²à¹à¸¥à¹‰à¸§à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¹€à¸ˆà¸­à¸à¹‡à¸›à¸¥à¹ˆà¸­à¸¢à¸œà¹ˆà¸²à¸™à¹ƒà¸«à¹‰à¸šà¸­à¸—à¸—à¸³à¸‡à¸²à¸™à¸•à¹ˆà¸­
        à¸œà¸¹à¹‰à¹€à¸£à¸µà¸¢à¸à¸—à¸¸à¸à¸—à¸²à¸‡à¸–à¸·à¸­ _in_net_check à¸­à¸¢à¸¹à¹ˆà¹à¸¥à¹‰à¸§ _raw_capture à¸‚à¹‰à¸²à¸‡à¹ƒà¸™à¸ˆà¸¶à¸‡à¹„à¸¡à¹ˆà¸§à¸™à¸à¸¥à¸±à¸šà¸¡à¸²à¹€à¸Šà¹‡à¸„à¹€à¸™à¹‡à¸•à¸‹à¹‰à¸­à¸™
        """
        spec = self.NET_FOLLOWUP.get(first_hit)
        if not spec:
            return False
        target, wait_sec = spec
        name = os.path.basename(target)
        print(f"[{self.device_id}] [NET] {first_hit} à¸«à¸²à¸¢à¹à¸¥à¹‰à¸§ -> à¸£à¸­à¸à¸” {name} à¸•à¹ˆà¸­ (à¸ªà¸¹à¸‡à¸ªà¸¸à¸” {wait_sec} à¸§à¸´)")
        deadline = time.time() + wait_sec
        while time.time() < deadline and getattr(self, "_running", True):
            try:
                self._raw_capture()
            except Exception:
                pass
            scr = self._screen
            if scr is not None:
                b = self._best_match(scr, target, 0.8, (getattr(self, "_net_scale", 1.0),))
                if b:
                    score, cx, cy, _ = b
                    self._adb_tap(cx, cy)
                    print(f"[{self.device_id}] [NET] à¸žà¸š {name} à¸«à¸¥à¸±à¸‡ {first_hit} (score {score:.2f}) -> adb tap ({cx}, {cy})")
                    sleep(1)
                    try:
                        self._raw_capture()   # à¸„à¸·à¸™à¸ à¸²à¸žà¸¥à¹ˆà¸²à¸ªà¸¸à¸”à¹ƒà¸«à¹‰à¸œà¸¹à¹‰à¹€à¸£à¸µà¸¢à¸
                    except Exception:
                        pass
                    return True
                # à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•à¹€à¸”à¹‰à¸‡à¸à¸¥à¸±à¸šà¸¡à¸²à¸£à¸°à¸«à¸§à¹ˆà¸²à¸‡à¸£à¸­ (PLAY à¸­à¸µà¸à¸£à¸­à¸š / RETRY) -> à¸à¸”à¹ƒà¸«à¹‰à¹€à¸¥à¸¢ à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸£à¸­à¸£à¸­à¸šà¸–à¸±à¸”à¹„à¸›
                self._netpopup_last_click = 0
                self._dismiss_net_popup(scr)
            sleep(1)
        print(f"[{self.device_id}] [NET] à¸£à¸­ {name} à¸«à¸¥à¸±à¸‡ {first_hit} à¸ˆà¸™à¸«à¸¡à¸”à¹€à¸§à¸¥à¸² {wait_sec} à¸§à¸´ à¹à¸¥à¹‰à¸§à¹„à¸¡à¹ˆà¹€à¸ˆà¸­ - à¸—à¸³à¸‡à¸²à¸™à¸•à¹ˆà¸­")
        return False

    def _best_match_any(self, screen, path, scales):
        """à¹€à¸«à¸¡à¸·à¸­à¸™ _best_match à¹à¸•à¹ˆà¸„à¸·à¸™à¸•à¸±à¸§à¸—à¸µà¹ˆà¸”à¸µà¸—à¸µà¹ˆà¸ªà¸¸à¸”à¹€à¸ªà¸¡à¸­à¹„à¸¡à¹ˆà¸¡à¸µà¹€à¸à¸“à¸‘à¹Œ: (score, cx, cy, scale, tw, th) à¸«à¸£à¸·à¸­ None"""
        tmpl0 = self._get_template(path)
        if tmpl0 is None:
            return None
        best = None
        for sc in scales:
            if sc == 1.0:
                tmpl = tmpl0
            else:
                tmpl = cv2.resize(tmpl0, None, fx=sc, fy=sc,
                                  interpolation=cv2.INTER_AREA if sc < 1 else cv2.INTER_CUBIC)
            th, tw = tmpl.shape[:2]
            if screen.shape[0] < th or screen.shape[1] < tw:
                continue
            res = cv2.matchTemplate(screen, tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if best is None or max_val > best[0]:
                best = (float(max_val), max_loc[0] + tw // 2, max_loc[1] + th // 2, sc, tw, th)
        return best

    def _is_green_button(self, cx, cy, tw, th):
        """à¸à¸£à¸­à¸šà¸—à¸µà¹ˆ match à¹€à¸›à¹‡à¸™à¸›à¸¸à¹ˆà¸¡à¸ªà¸µà¹€à¸‚à¸µà¸¢à¸§à¸ˆà¸£à¸´à¸‡à¹„à¸«à¸¡ - à¸”à¸¹à¸ˆà¸²à¸à¸ à¸²à¸žà¸ªà¸µà¸¥à¹ˆà¸²à¸ªà¸¸à¸”à¸•à¸£à¸‡à¸‚à¸­à¸šà¸‹à¹‰à¸²à¸¢/à¸‚à¸§à¸²/à¸šà¸™/à¸¥à¹ˆà¸²à¸‡ (à¹€à¸¥à¸µà¹ˆà¸¢à¸‡à¸•à¸±à¸§à¸«à¸™à¸±à¸‡à¸ªà¸·à¸­à¸‚à¸²à¸§à¸•à¸£à¸‡à¸à¸¥à¸²à¸‡)

        à¸›à¸¸à¹ˆà¸¡ RETRY / PLAY / OK à¸‚à¸­à¸‡à¹€à¸à¸¡à¸žà¸·à¹‰à¸™à¹€à¸‚à¸µà¸¢à¸§à¸ªà¸” (B,G,R à¸£à¸²à¸§ 49,194,8) à¸•à¹‰à¸­à¸‡à¹€à¸‚à¸µà¸¢à¸§à¸­à¸¢à¹ˆà¸²à¸‡à¸™à¹‰à¸­à¸¢ 3 à¹ƒà¸™ 4 à¸ˆà¸¸à¸”
        à¹„à¸¡à¹ˆà¸¡à¸µà¸ à¸²à¸žà¸ªà¸µ (à¹€à¸Ÿà¸£à¸¡à¹€à¸à¹ˆà¸²/decode à¹„à¸¡à¹ˆà¹„à¸”à¹‰) -> False = à¹ƒà¸Šà¹‰à¹€à¸à¸“à¸‘à¹Œà¸›à¸à¸•à¸´
        """
        color = getattr(self, "_screen_color", None)
        if color is None or getattr(color, "ndim", 0) != 3:
            return False
        H, W = color.shape[:2]
        x0, y0 = cx - tw // 2, cy - th // 2
        mx, my = max(1, int(tw * 0.05)), max(1, int(th * 0.12))
        pts = ((x0 + mx, cy), (x0 + tw - 1 - mx, cy), (cx, y0 + my), (cx, y0 + th - 1 - my))
        ok = 0
        for x, y in pts:
            if 0 <= x < W and 0 <= y < H:
                b, g, r = (int(v) for v in color[y, x])
                if g >= 120 and g > r + 60 and g > b + 60:
                    ok += 1
        return ok >= 3

    def _net_popup_paths(self):
        """NET_POPUPS à¸—à¸µà¹ˆà¸•à¸±à¸”à¸£à¸¹à¸›à¸‹à¹‰à¸³à¸­à¸­à¸ (à¹€à¸™à¸·à¹‰à¸­à¸«à¸²à¹€à¸«à¸¡à¸·à¸­à¸™à¸à¸±à¸™à¹€à¸›à¹Šà¸° à¹€à¸Šà¹ˆà¸™ fixnet.png à¸à¸±à¸š fixnet-tiket.png) - à¸›à¸£à¸°à¸«à¸¢à¸±à¸” matchTemplate"""
        cached = getattr(self, "_net_paths_cache", None)
        if cached is not None:
            return cached
        out, seen = [], []
        for p in self.NET_POPUPS:
            t = self._get_template(p)
            if t is None:
                continue
            if any(t.shape == s.shape and np.array_equal(t, s) for s in seen):
                continue
            seen.append(t)
            out.append(p)
        self._net_paths_cache = tuple(out)
        return self._net_paths_cache

    def _log_net_near_miss(self, score, path, sc):
        """à¹€à¸«à¹‡à¸™à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•à¹à¸šà¸š "à¹€à¸à¸·à¸­à¸šà¹€à¸ˆà¸­" (à¸„à¸°à¹à¸™à¸™à¹„à¸¡à¹ˆà¸–à¸¶à¸‡à¹€à¸à¸“à¸‘à¹Œ) - à¸šà¸­à¸à¹ƒà¸™ log à¸—à¸¸à¸ 30 à¸§à¸´ + à¹€à¸à¹‡à¸šà¸ à¸²à¸žà¸—à¸¸à¸ 5 à¸™à¸²à¸—à¸µ

        à¹„à¸§à¹‰à¹„à¸¥à¹ˆà¸ˆà¸²à¸ log à¹„à¸”à¹‰à¹€à¸¥à¸¢à¸§à¹ˆà¸²à¸£à¸¹à¸›à¸•à¸±à¸”à¹„à¸¡à¹ˆà¸•à¸£à¸‡/à¸ªà¹€à¸à¸¥à¹„à¸¡à¹ˆà¸•à¸£à¸‡à¸à¸±à¸šà¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸™à¸±à¹‰à¸™ à¹‚à¸”à¸¢à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¹„à¸›à¸™à¸±à¹ˆà¸‡à¹€à¸à¹‰à¸²à¸«à¸™à¹‰à¸²à¸ˆà¸­
        """
        now = time.time()
        if now - getattr(self, "_net_near_logged", 0) < 30:
            return
        self._net_near_logged = now
        shot = None
        if now - getattr(self, "_net_near_shot", 0) > 300:
            self._net_near_shot = now
            shot = self._save_debug_screen("net-nearmiss")
        print(f"[{self.device_id}] [NET] à¹€à¸à¸·à¸­à¸šà¹€à¸ˆà¸­ {os.path.basename(path)} (score {score:.2f} à¸—à¸µà¹ˆà¸ªà¹€à¸à¸¥ x{sc:.2f} / "
              f"à¸•à¹‰à¸­à¸‡à¸à¸²à¸£ 0.80 à¸«à¸£à¸·à¸­ {self.NET_SIM_GREEN:.2f}+à¸›à¸¸à¹ˆà¸¡à¹€à¸‚à¸µà¸¢à¸§) à¹„à¸¡à¹ˆà¸à¸” - à¸£à¸¹à¸›à¸­à¸²à¸ˆà¸•à¸±à¸”à¹„à¸¡à¹ˆà¸•à¸£à¸‡à¸à¸±à¸šà¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸™à¸µà¹‰"
              + (f" à¹€à¸à¹‡à¸šà¸ à¸²à¸žà¹„à¸§à¹‰à¸—à¸µà¹ˆ {shot}" if shot else ""))

    def _dismiss_net_popup(self, screen, similarity=0.8, scales=None):
        """à¸«à¸²à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸• (RETRY / PLAY / network-OK) à¸šà¸™à¸ˆà¸­à¸—à¸µà¹ˆà¹ƒà¸«à¹‰à¸¡à¸²à¹à¸¥à¹‰à¸§à¸à¸”à¸›à¸´à¸” - à¸„à¸·à¸™à¸Šà¸·à¹ˆà¸­à¸£à¸¹à¸›à¸—à¸µà¹ˆà¸à¸” à¸«à¸£à¸·à¸­ None

        à¸à¸”à¸”à¹‰à¸§à¸¢ adb input tap à¸•à¸£à¸‡ à¹† à¹€à¸ªà¸¡à¸­ (à¹„à¸¡à¹ˆà¸œà¹ˆà¸²à¸™ minitouch) à¹€à¸«à¸¡à¸·à¸­à¸™ bot-tiket
        scales=None       -> à¹ƒà¸Šà¹‰à¸ªà¹€à¸à¸¥à¸—à¸µà¹ˆà¹€à¸„à¸¢à¹€à¸ˆà¸­ (à¹€à¸£à¸´à¹ˆà¸¡ 1.0) à¸£à¸²à¸„à¸²à¸–à¸¹à¸ à¹€à¸£à¸µà¸¢à¸à¹„à¸”à¹‰à¸—à¸¸à¸à¸„à¸£à¸±à¹‰à¸‡à¸—à¸µà¹ˆà¸ˆà¸±à¸šà¸ˆà¸­
        scales=NET_SCALES -> à¹„à¸¥à¹ˆà¸—à¸¸à¸à¸ªà¹€à¸à¸¥ (monitor à¹€à¸šà¸·à¹‰à¸­à¸‡à¸«à¸¥à¸±à¸‡à¹ƒà¸Šà¹‰) à¹€à¸ˆà¸­à¸ªà¹€à¸à¸¥à¹„à¸«à¸™à¸ˆà¸³à¹„à¸§à¹‰à¹ƒà¸«à¹‰à¸£à¸­à¸šà¸•à¹ˆà¸­à¹„à¸›
        à¸„à¸°à¹à¸™à¸™à¹„à¸¡à¹ˆà¸–à¸¶à¸‡ similarity à¹à¸•à¹ˆ >= NET_SIM_GREEN à¹à¸¥à¸°à¸à¸£à¸­à¸šà¸™à¸±à¹‰à¸™à¹€à¸›à¹‡à¸™à¸›à¸¸à¹ˆà¸¡à¹€à¸‚à¸µà¸¢à¸§à¸ˆà¸£à¸´à¸‡ -> à¸™à¸±à¸šà¸§à¹ˆà¸²à¹€à¸ˆà¸­ (à¸—à¸™à¸£à¸¹à¸›à¹€à¸žà¸µà¹‰à¸¢à¸™à¹€à¸¥à¹‡à¸à¸™à¹‰à¸­à¸¢)
        à¹„à¸¡à¹ˆà¸–à¸¶à¸‡à¸—à¸±à¹‰à¸‡à¸„à¸¹à¹ˆà¹à¸•à¹ˆ >= NET_NEAR_MISS à¸•à¸­à¸™à¹„à¸¥à¹ˆà¸«à¸¥à¸²à¸¢à¸ªà¹€à¸à¸¥ -> log "à¹€à¸à¸·à¸­à¸šà¹€à¸ˆà¸­" + à¹€à¸à¹‡à¸šà¸ à¸²à¸ž à¹ƒà¸«à¹‰à¹„à¸¥à¹ˆà¸ªà¸²à¹€à¸«à¸•à¸¸à¸ˆà¸²à¸ log à¹„à¸”à¹‰
        """
        if screen is None:
            return None
        if scales is None:
            scales = (getattr(self, "_net_scale", 1.0),)
        hit = None    # (score, path_to_report, cx, cy, scale)
        near = None   # (score, path, scale) à¸”à¸µà¸ªà¸¸à¸”à¸—à¸µà¹ˆà¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸–à¸¶à¸‡à¹€à¸à¸“à¸‘à¹Œ
        for path in self._net_popup_paths():
            b = self._best_match_any(screen, path, scales)
            if not b:
                continue
            score, cx, cy, sc, tw, th = b
            if score >= similarity or (score >= self.NET_SIM_GREEN and self._is_green_button(cx, cy, tw, th)):
                if hit is None or score > hit[0]:
                    hit = (score, path, cx, cy, sc)
            elif score >= self.NET_NEAR_MISS and (near is None or score > near[0]):
                near = (score, path, sc)
        if hit is None:
            for detect, target in self.NET_DETECT_THEN_TAP:
                d = self._best_match(screen, detect, similarity, scales)
                if not d:
                    continue
                t = self._best_match(screen, target, similarity, (d[3],))
                if t:
                    hit = (t[0], target, t[1], t[2], t[3])
                else:
                    print(f"[{self.device_id}] [NET] à¹€à¸ˆà¸­ {os.path.basename(detect)} à¹à¸•à¹ˆà¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¹€à¸«à¹‡à¸™à¸›à¸¸à¹ˆà¸¡ {os.path.basename(target)} - à¸£à¸­à¹€à¸Ÿà¸£à¸¡à¸–à¸±à¸”à¹„à¸›")
                break
        if hit is None:
            if near is not None and len(scales) > 1:   # log à¹€à¸‰à¸žà¸²à¸°à¸•à¸­à¸™à¸à¸§à¸²à¸”à¸«à¸¥à¸²à¸¢à¸ªà¹€à¸à¸¥ (monitor) à¹„à¸¡à¹ˆà¹ƒà¸«à¹‰à¸—à¹ˆà¸§à¸¡à¸—à¸¸à¸à¹€à¸Ÿà¸£à¸¡
                self._log_net_near_miss(*near)
            return None
        score, path, cx, cy, sc = hit
        now = time.time()
        if now - getattr(self, "_netpopup_last_click", 0) < 1.0:
            return None          # à¹€à¸žà¸´à¹ˆà¸‡à¸à¸”à¹„à¸› à¸£à¸­à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¸«à¸²à¸¢à¸à¹ˆà¸­à¸™ à¹„à¸¡à¹ˆà¸à¸”à¸£à¸±à¸§ (cooldown 1 à¸§à¸´)
        self._netpopup_last_click = now
        if sc != getattr(self, "_net_scale", None):
            if getattr(self, "_net_scale", None) is not None or sc != 1.0:
                print(f"[{self.device_id}] [NET] à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•à¸šà¸™à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸™à¸µà¹‰à¸ªà¹€à¸à¸¥ x{sc:.2f} à¸‚à¸­à¸‡à¸£à¸¹à¸› - à¸ˆà¸³à¹„à¸§à¹‰à¹ƒà¸Šà¹‰à¸—à¸¸à¸à¸„à¸£à¸±à¹‰à¸‡")
            self._net_scale = sc   # à¸ˆà¸³à¹€à¸ªà¸¡à¸­ (à¸£à¸§à¸¡ 1.0) monitor à¸ˆà¸°à¹„à¸”à¹‰à¹€à¸¥à¸´à¸à¸à¸§à¸²à¸”à¸—à¸¸à¸à¸ªà¹€à¸à¸¥à¸—à¸¸à¸à¸£à¸­à¸š
        # fixnet1 à¸šà¸™à¸ˆà¸­à¸—à¸µà¹ˆà¸•à¹ˆà¸­ VPN -> à¹„à¸¡à¹ˆà¸à¸” RETRY: à¸›à¸´à¸”à¹€à¸à¸¡ + à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™ IP à¸—à¸±à¸™à¸—à¸µ + à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¹ƒà¸«à¸¡à¹ˆ (config "wg_fixnet1_switch")
        if (os.path.basename(path) in ("fixnet1.png", "fixnet.png") and int(config.get("wg_fixnet1_switch", 1) or 0)
                and self._wg_request_net_recover("fixnet1", switch_now=True)):
            return os.path.basename(path)
        # à¸ˆà¸‡à¹ƒà¸ˆà¹„à¸¡à¹ˆà¹ƒà¸«à¹‰à¸à¸²à¸£à¸à¸”à¸™à¸µà¹‰à¸™à¸±à¸šà¹€à¸›à¹‡à¸™ activity (à¹€à¸«à¸¡à¸·à¸­à¸™ bot-tiket): à¸–à¹‰à¸²à¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”à¸§à¸™à¹„à¸¡à¹ˆà¸ˆà¸š
        # à¸•à¸±à¸§à¸ˆà¸±à¸šà¹€à¸§à¸¥à¸²à¸à¸±à¸™à¸„à¹‰à¸²à¸‡ 500 à¸§à¸´ à¸ˆà¸°à¹„à¸”à¹‰à¸¢à¸±à¸‡à¸—à¸³à¸‡à¸²à¸™à¹à¸¥à¸°à¹€à¸”à¹‰à¸‡à¹„à¸›à¹„à¸Ÿà¸¥à¹Œà¸–à¸±à¸”à¹„à¸›à¹€à¸­à¸‡
        self._adb_tap(cx, cy)
        print(f"[{self.device_id}] [NET] à¸žà¸š {os.path.basename(path)} (score {score:.2f}, x{sc:.2f}) -> adb tap à¸—à¸±à¸™à¸—à¸µ ({cx}, {cy})")
        return os.path.basename(path)
    def _popup_monitor_loop(self):
        """Background thread to monitor fixnetv3.png - reuses main thread's screen to save CPU"""
        while self._running:
            self._log_pos_cache()
            try:
                # Reuse the main thread's last captured screen instead of doing a separate screencap
                # thread à¸«à¸¥à¸±à¸à¸•à¸²à¸¢/à¸„à¹‰à¸²à¸‡à¹ƒà¸™à¸„à¸³à¸ªà¸±à¹ˆà¸‡à¸¢à¸²à¸§ -> à¹€à¸Ÿà¸£à¸¡à¹„à¸¡à¹ˆà¸‚à¸¢à¸±à¸š monitor à¸ˆà¸±à¸šà¸ˆà¸­à¹€à¸­à¸‡à¸ˆà¸°à¹„à¸”à¹‰à¸¢à¸±à¸‡à¹€à¸«à¹‡à¸™à¸›à¹Šà¸­à¸›à¸­à¸±à¸ž
                if time.time() - getattr(self, "_screen_ts", 0) > 5 and not getattr(self, "_in_net_check", False):
                    self._in_net_check = True
                    try:
                        self._raw_capture()
                    except Exception:
                        pass
                    finally:
                        self._in_net_check = False
                mon_screen = self._screen
                if mon_screen is not None:
                    # fixnet1/fixnet/fixplay (NET_POPUPS): à¸à¸”à¸›à¸´à¸”à¸ˆà¸²à¸à¸•à¸£à¸‡à¸™à¸µà¹‰à¸”à¹‰à¸§à¸¢ à¹€à¸žà¸£à¸²à¸°à¸¥à¸¹à¸›à¸£à¸­à¸ªà¹ˆà¸§à¸™à¹ƒà¸«à¸à¹ˆà¹„à¸¡à¹ˆà¹„à¸”à¹‰
                    # à¹€à¸£à¸µà¸¢à¸ check_floating_popups() à¹€à¸­à¸‡
                    # à¸–à¸·à¸­ _in_net_check à¹„à¸§à¹‰à¸£à¸°à¸«à¸§à¹ˆà¸²à¸‡à¸—à¸³ - thread à¸«à¸¥à¸±à¸à¸à¸³à¸¥à¸±à¸‡à¹€à¸„à¸¥à¸µà¸¢à¸£à¹Œà¸­à¸¢à¸¹à¹ˆà¸à¹‡à¸‚à¹‰à¸²à¸¡à¸£à¸­à¸šà¸™à¸µà¹‰
                    # (à¹„à¸¡à¹ˆà¸‡à¸±à¹‰à¸™à¸ªà¸­à¸‡à¸à¸±à¹ˆà¸‡à¸à¸”à¸‹à¹‰à¸³/à¸£à¸­à¸›à¸¸à¹ˆà¸¡à¸•à¹ˆà¸­à¸—à¹‰à¸²à¸¢à¸‹à¹‰à¸­à¸™à¸à¸±à¸™)
                    hit = None
                    skipped = getattr(self, "_in_net_check", False)
                    if not skipped:
                        self._in_net_check = True
                        try:
                            # à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¹€à¸„à¸¢à¹€à¸ˆà¸­ = à¸à¸§à¸²à¸”à¸—à¸¸à¸à¸ªà¹€à¸à¸¥à¸—à¸¸à¸à¸£à¸­à¸š / à¸£à¸¹à¹‰à¸ªà¹€à¸à¸¥à¸‚à¸­à¸‡à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¹à¸¥à¹‰à¸§ = à¹€à¸Šà¹‡à¸„à¸ªà¹€à¸à¸¥à¸™à¸±à¹‰à¸™
                            # à¹à¸¥à¸°à¸à¸§à¸²à¸”à¸—à¸¸à¸à¸ªà¹€à¸à¸¥à¸‹à¹‰à¸³à¸—à¸¸à¸à¸£à¸­à¸šà¸—à¸µà¹ˆ 5 (~15 à¸§à¸´) à¹€à¸œà¸·à¹ˆà¸­à¹€à¸à¸¡à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™à¸‚à¸™à¸²à¸” UI
                            self._mon_round = getattr(self, "_mon_round", 0) + 1
                            learned = getattr(self, "_net_scale", None)
                            sweep = self.NET_SCALES if (learned is None or self._mon_round % 5 == 0) else (learned,)
                            hit = self._dismiss_net_popup(mon_screen, scales=sweep)
                            if hit:
                                self._clear_net_popup_loop(hit)   # à¸à¸”à¸‹à¹‰à¸³à¸ˆà¸™à¸«à¸²à¸¢ (à¹à¸¥à¹‰à¸§à¸£à¸­à¸à¸”à¸›à¸¸à¹ˆà¸¡à¸•à¹ˆà¸­à¸—à¹‰à¸²à¸¢à¸–à¹‰à¸²à¸¡à¸µ)
                        finally:
                            self._in_net_check = False
                    if hit:
                        self._netpopup_count = getattr(self, "_netpopup_count", 0) + 1
                        print(f"[{self.device_id}] [MONITOR] {hit} à¹€à¸”à¹‰à¸‡ (#{self._netpopup_count}) - à¸à¸”à¸›à¸´à¸”à¹ƒà¸«à¹‰à¹à¸¥à¹‰à¸§")
                        if self._netpopup_count >= self.NET_POPUP_LIMIT:
                            print(f"[{self.device_id}] [MONITOR] {hit} à¸à¸”à¹„à¸› {self.NET_POPUP_LIMIT} à¸„à¸£à¸±à¹‰à¸‡à¹à¸¥à¹‰à¸§à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸«à¸²à¸¢ - à¹€à¸”à¹‰à¸‡à¹à¸­à¸›à¹ƒà¸«à¸¡à¹ˆ")
                            self._need_restart = True
                            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell",
                                          "am", "force-stop", "com.linecorp.LGRGS"])
                            self._netpopup_count = 0
                    elif not skipped and getattr(self, "_netpopup_count", 0):
                        self._netpopup_count = 0

                    tmpl = self._get_template("img/fixnetv3.png")
                    if tmpl is not None:
                        res = cv2.matchTemplate(mon_screen, tmpl, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, _ = cv2.minMaxLoc(res)
                        
                        if max_val >= 0.8:
                            self._fixnetv3_count += 1
                            print(f"[{self.device_id}] [MONITOR] fixnetv3.png detected (#{self._fixnetv3_count})! Tapping (472, 361)...")
                            self._adb_tap(472, 361)   # à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•: à¸à¸”à¸œà¹ˆà¸²à¸™ adb à¸•à¸£à¸‡ à¹† à¹€à¸«à¸¡à¸·à¸­à¸™ bot-tiket
                            
                            if self._fixnetv3_count >= 8:
                                print(f"[{self.device_id}] [MONITOR] fixnetv3.png persists after 8 clicks! Force-stopping app...")
                                self._need_restart = True
                                self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
                                self._fixnetv3_count = 0
                        else:
                            if self._fixnetv3_count > 0:
                                self._fixnetv3_count = 0
                
            except Exception:
                pass
            time.sleep(3)  # Check every 3 seconds (lighter than 2.5)

    # =========================================================
    # WireGuard à¸•à¹ˆà¸­à¸ˆà¸­ (IP à¹„à¸¡à¹ˆà¸‹à¹‰à¸³à¸à¸±à¸™à¹à¸•à¹ˆà¸¥à¸°à¸­à¸µà¸¡à¸¹à¸¯) - à¹ƒà¸Šà¹‰à¹„à¸Ÿà¸¥à¹Œ .conf à¸ˆà¸²à¸ Windscribe Config Generator
    # à¸§à¸²à¸‡à¹„à¸Ÿà¸¥à¹Œà¹„à¸§à¹‰à¹ƒà¸™à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œ wg/ (à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™ git) à¸ˆà¸­à¸—à¸µà¹ˆ i à¹„à¸”à¹‰à¹„à¸Ÿà¸¥à¹Œà¸—à¸µà¹ˆ i à¸•à¸²à¸¡à¸¥à¸³à¸”à¸±à¸šà¸Šà¸·à¹ˆà¸­
    # à¸«à¸£à¸·à¸­à¸à¸³à¸«à¸™à¸”à¹€à¸­à¸‡à¹ƒà¸™ config "wg_per_device": {"127.0.0.1:16384": "Tokyo.conf", ...}
    # à¸‚à¸±à¹‰à¸™à¸•à¸­à¸™ (à¸•à¹‰à¸­à¸‡ root): à¸¥à¸‡à¹à¸­à¸› WireGuard -> à¹€à¸‚à¸µà¸¢à¸™à¹„à¸Ÿà¸¥à¹Œ tunnel à¸¥à¸‡ data à¸‚à¸­à¸‡à¹à¸­à¸› ->
    #   à¹€à¸›à¸´à¸” "allow remote control" + à¸­à¸™à¸¸à¸à¸²à¸• VPN à¸¥à¹ˆà¸§à¸‡à¸«à¸™à¹‰à¸² -> à¸¢à¸´à¸‡ intent SET_TUNNEL_UP
    # =========================================================
    WG_PKG = "com.wireguard.android"
    WG_TUNNEL = "lgr"

    def _wg_conf_for_device(self):
        """à¹„à¸Ÿà¸¥à¹Œ .conf à¸‚à¸­à¸‡à¸ˆà¸­à¸™à¸µà¹‰ (None = à¹„à¸¡à¹ˆà¸¡à¸µà¹„à¸Ÿà¸¥à¹Œ/à¹„à¸¡à¹ˆà¹€à¸›à¸´à¸”à¹ƒà¸Šà¹‰)

        wg_stick_on_success=1 (default 1): IP à¹„à¸«à¸™ login à¸œà¹ˆà¸²à¸™à¹à¸¥à¹‰à¸§ (._wg_ok() fired)
          -> à¸¢à¸¶à¸” IP à¸™à¸±à¹‰à¸™à¸–à¸²à¸§à¸£ à¹„à¸¡à¹ˆà¸ªà¸¥à¸±à¸š à¸ˆà¸™à¸à¸§à¹ˆà¸²à¸ˆà¸°à¹€à¸ˆà¸­ fixnet1 à¸—à¸µà¹ˆ start à¹€à¸à¸¡ (_wg_failover clear)
        """
        # sticky: à¹€à¸„à¸¢ login à¸œà¹ˆà¸²à¸™à¸”à¹‰à¸§à¸¢ IP à¸™à¸µà¹‰ -> à¹ƒà¸Šà¹‰à¸‹à¹‰à¸³à¹„à¸›à¹€à¸£à¸·à¹ˆà¸­à¸¢ à¹† à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸„à¸³à¸™à¸§à¸“à¹ƒà¸«à¸¡à¹ˆ
        stuck = getattr(self, "_wg_stuck_conf", None)
        if stuck and os.path.exists(stuck) and int(config.get("wg_stick_on_success", 1) or 0):
            return stuck
        wg_dir = str(config.get("wg_dir", "wg"))
        mapped = (config.get("wg_per_device") or {}).get(self.device_id)
        if mapped:
            p = mapped if os.path.isabs(mapped) else os.path.join(wg_dir, mapped)
            return p if os.path.exists(p) else None
        confs = _wg_list_configs(wg_dir)
        if (not confs and int(config.get("wg_regen_blocked", 1) or 0)
                and time.time() - getattr(self, "_wg_empty_gen_t", 0) > 60):
            # à¹„à¸¡à¹ˆà¸¡à¸µà¹„à¸Ÿà¸¥à¹Œ IP à¹€à¸¥à¸¢ (à¸–à¸¹à¸à¸¥à¸š/à¸«à¸²à¸¢) -> à¸ªà¸£à¹‰à¸²à¸‡à¹ƒà¸«à¸¡à¹ˆà¹€à¸­à¸‡à¸—à¸±à¸™à¸—à¸µ (à¹‚à¸«à¸¡à¸”à¸šà¸±à¸à¸Šà¸µà¹„à¸¡à¹ˆà¸¡à¸µ keypair.txt à¸à¹‡à¸ªà¸£à¹‰à¸²à¸‡à¹„à¸”à¹‰)
            self._wg_empty_gen_t = time.time()
            # à¹„à¸Ÿà¸¥à¹Œà¹ƒà¸™ wg/ à¸«à¸¡à¸” (à¸¥à¸šà¸•à¸±à¸§à¸—à¸µà¹ˆà¹‚à¸”à¸™à¸šà¸¥à¹‡à¸­à¸à¹„à¸›à¸«à¸¡à¸”) à¹à¸•à¹ˆà¸¢à¸±à¸‡à¸¡à¸µà¸à¸¸à¸à¹à¸ˆ -> à¸ªà¸£à¹‰à¸²à¸‡à¸Šà¸¸à¸”à¹ƒà¸«à¸¡à¹ˆ
            _wg_generate_more(wg_dir, int(config.get("wg_gen_extra", 5)) + 10, self.device_id)
            confs = _wg_list_configs(wg_dir)

        # Sub-folder round-robin: sync à¸à¸±à¸š login.py - à¸¥à¹‡à¸­à¸ sub à¹€à¸”à¸µà¸¢à¸§à¸•à¹ˆà¸­à¸£à¸­à¸š
        # fixnet1 -> _wg_failover à¸‚à¸¢à¸±à¸š _wg_sub_idx -> à¸£à¸­à¸šà¸«à¸™à¹‰à¸²à¹„à¸› sub à¸–à¸±à¸”à¹„à¸›
        if int(config.get("wg_sub_round_robin", 1) or 0) and confs:
            subs = []
            for c in confs:
                bn = os.path.basename(c)
                parts = bn.split("__")
                if len(parts) >= 4 and parts[0] == "wg":
                    sub = "__".join(parts[:3])
                    if sub not in subs:
                        subs.append(sub)
            if len(subs) >= 2:
                subs.sort()
                cur_idx = getattr(self, "_wg_sub_idx", None)
                if cur_idx is None:
                    try:
                        port = int(self.device_id.rsplit(":", 1)[1])
                        cur_idx = ((port - 16384) // 32) % len(subs) if port >= 16384 else 0
                    except Exception:
                        cur_idx = sum(map(ord, self.device_id)) % len(subs)
                    self._wg_sub_idx = cur_idx
                cur_sub = subs[cur_idx % len(subs)]
                filtered = [c for c in confs if os.path.basename(c).startswith(cur_sub + "__")]
                if filtered:
                    confs = filtered
        if not confs:
            return None
        # à¹à¸•à¹ˆà¸¥à¸°à¸ˆà¸­ "à¸ˆà¸­à¸‡" à¹„à¸Ÿà¸¥à¹Œà¸‚à¸­à¸‡à¸•à¸±à¸§à¹€à¸­à¸‡ à¹„à¸¡à¹ˆà¹ƒà¸Šà¹‰à¸‹à¹‰à¸³à¸à¸±à¸šà¸ˆà¸­à¸­à¸·à¹ˆà¸™ (à¸à¸¸à¸à¹à¸ˆà¹€à¸”à¸µà¸¢à¸§à¸à¸±à¸™à¸•à¹ˆà¸­à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™ = à¸•à¸µà¸à¸±à¸™à¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”)
        # à¸¥à¸­à¸‡à¹„à¸Ÿà¸¥à¹Œà¸•à¸²à¸¡à¸¥à¸³à¸”à¸±à¸šà¸ˆà¸­ MuMu à¸à¹ˆà¸­à¸™ (à¸žà¸­à¸£à¹Œà¸• 16384 + 32*i) à¸ˆà¸°à¹„à¸”à¹‰à¹„à¸Ÿà¸¥à¹Œà¹€à¸”à¸´à¸¡à¸—à¸¸à¸à¸„à¸£à¸±à¹‰à¸‡à¸—à¸µà¹ˆà¹€à¸›à¸´à¸”à¸šà¸­à¸•
        try:
            port = int(self.device_id.rsplit(":", 1)[1])
            idx = (port - 16384) // 32 if port >= 16384 else port
        except Exception:
            idx = sum(map(ord, self.device_id))
        # à¹à¸•à¹ˆà¸¥à¸°à¸ˆà¸­à¹€à¸›à¹‡à¸™à¸„à¸™à¸¥à¸° process -> à¸ˆà¸­à¸‡à¸”à¹‰à¸§à¸¢à¹„à¸Ÿà¸¥à¹Œà¸¥à¹‡à¸­à¸ wg/.claims/<à¸Šà¸·à¹ˆà¸­à¹„à¸Ÿà¸¥à¹Œ>.lock (à¸ªà¸£à¹‰à¸²à¸‡à¹à¸šà¸š O_EXCL = à¹„à¸”à¹‰à¸„à¸™à¹€à¸”à¸µà¸¢à¸§)
        claim_dir = os.path.join(wg_dir, ".claims")
        os.makedirs(claim_dir, exist_ok=True)

        def _owner(p):
            try:
                with open(os.path.join(claim_dir, os.path.basename(p) + ".lock"), encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                return None

        bad = set(getattr(self, "_wg_bad", set()))   # à¹„à¸Ÿà¸¥à¹Œà¸—à¸µà¹ˆà¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”à¸‹à¹‰à¸³à¸šà¸™à¸ˆà¸­à¸™à¸µà¹‰ (auto failover) - à¹„à¸¡à¹ˆà¸à¸¥à¸±à¸šà¹„à¸›à¹ƒà¸Šà¹‰
        # à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œ (IP à¸‚à¸²à¸­à¸­à¸) à¸—à¸µà¹ˆà¸ˆà¸­à¹„à¸«à¸™à¸à¹‡à¸•à¸²à¸¡à¹€à¸žà¸´à¹ˆà¸‡à¹‚à¸”à¸™ block -> à¸žà¸±à¸à¹„à¸§à¹‰ wg_cooldown_hours à¸Šà¸¡. à¸—à¸¸à¸à¸ˆà¸­à¹€à¸¥à¸µà¹ˆà¸¢à¸‡
        cool = {} if getattr(self, "_wg_ignore_cool", False) else _wg_cooldown_load(wg_dir)
        bad |= {c for c in confs if _wg_endpoint(c) in cool}
        # à¸ˆà¸³à¸à¸±à¸”à¸ˆà¸³à¸™à¸§à¸™à¸ˆà¸­à¸•à¹ˆà¸­à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹€à¸”à¸µà¸¢à¸§à¸à¸±à¸™ (IP à¸‚à¸²à¸­à¸­à¸à¹€à¸”à¸µà¸¢à¸§à¸à¸±à¸™) ; 0 = à¹„à¸¡à¹ˆà¸ˆà¸³à¸à¸±à¸”
        max_ip = int(config.get("wg_max_per_ip", 0) or 0)
        if max_ip > 0:
            used = {}
            for c in confs:
                o = _owner(c)
                if o and o != self.device_id:
                    e = _wg_endpoint(c)
                    used[e] = used.get(e, 0) + 1
            full = {c for c in confs if used.get(_wg_endpoint(c), 0) >= max_ip}
            if len(full | bad) < len(confs):
                bad |= full
        for p in confs:                      # à¸ˆà¸­à¸‡à¹„à¸§à¹‰à¹à¸¥à¹‰à¸§à¸ˆà¸²à¸à¸£à¸­à¸šà¸à¹ˆà¸­à¸™ -> à¹ƒà¸Šà¹‰à¸­à¸±à¸™à¹€à¸”à¸´à¸¡
            if _owner(p) == self.device_id and p not in bad:
                return p
        order = confs[idx % len(confs):] + confs[:idx % len(confs)]
        for p in order:
            if p in bad:
                continue
            lock = os.path.join(claim_dir, os.path.basename(p) + ".lock")
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                continue
            except Exception:
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(self.device_id)
            return p
        if (not getattr(self, "_wg_gen_tried", False) and int(config.get("wg_regen_blocked", 1) or 0)
                and time.time() - getattr(self, "_wg_gen_last_t", 0) > 600):   # à¸ªà¸£à¹‰à¸²à¸‡à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¹à¸¥à¹‰à¸§ à¸­à¸¢à¹ˆà¸²à¸¥à¸­à¸‡à¸‹à¹‰à¸³à¸—à¸¸à¸à¸£à¸­à¸š (à¹€à¸ªà¸µà¸¢à¹€à¸§à¸¥à¸²à¹‚à¸«à¸¥à¸”à¸£à¸²à¸¢à¸Šà¸·à¹ˆà¸­à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œ)
            self._wg_gen_last_t = time.time()
            # à¹„à¸¡à¹ˆà¸¡à¸µà¹„à¸Ÿà¸¥à¹Œà¸§à¹ˆà¸²à¸‡à¹ƒà¸«à¹‰à¹ƒà¸Šà¹‰à¹€à¸¥à¸¢ (à¹‚à¸”à¸™à¸šà¸¥à¹‡à¸­à¸/à¸žà¸±à¸/à¸ˆà¸­à¸‡à¹€à¸•à¹‡à¸¡) -> à¸ªà¸£à¹‰à¸²à¸‡à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹ƒà¸«à¸¡à¹ˆà¹€à¸žà¸´à¹ˆà¸¡à¹à¸¥à¹‰à¸§à¸¥à¸­à¸‡à¸­à¸µà¸à¸£à¸­à¸š (à¹„à¸¡à¹ˆà¸›à¸¥à¹ˆà¸­à¸¢à¸ˆà¸­à¹„à¸›à¹ƒà¸Šà¹‰à¹€à¸™à¹‡à¸•à¸šà¹‰à¸²à¸™)
            self._wg_gen_tried = True
            try:
                if _wg_generate_more(wg_dir, len(confs) + int(config.get("wg_gen_extra", 5)), self.device_id):
                    return self._wg_conf_for_device()
            finally:
                self._wg_gen_tried = False
        if bad and len(bad) >= len(confs):
            # à¸¥à¸­à¸‡à¸„à¸£à¸šà¸—à¸¸à¸à¹„à¸Ÿà¸¥à¹Œà¹à¸¥à¹‰à¸§ -> à¹ƒà¸«à¹‰à¹‚à¸­à¸à¸²à¸ªà¹ƒà¸«à¸¡à¹ˆà¸—à¸±à¹‰à¸‡à¸«à¸¡à¸” (à¸§à¸™à¸£à¸­à¸šà¹ƒà¸«à¸¡à¹ˆ) à¹à¸—à¸™à¸—à¸µà¹ˆà¸ˆà¸°à¹„à¸¡à¹ˆà¸¡à¸µ VPN
            print(f"[{self.device_id}] [WG] à¸¥à¸­à¸‡à¸„à¸£à¸šà¸—à¸¸à¸à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹à¸¥à¹‰à¸§ - à¹€à¸£à¸´à¹ˆà¸¡à¸§à¸™à¹ƒà¸«à¸¡à¹ˆ")
            if not getattr(self, "_wg_bad", None):
                # à¸—à¸¸à¸à¸•à¸±à¸§à¸•à¸´à¸”à¸žà¸±à¸ -> à¸¢à¸­à¸¡à¹ƒà¸Šà¹‰à¸•à¸±à¸§à¸—à¸µà¹ˆà¸•à¸´à¸”à¸žà¸±à¸à¹„à¸›à¸à¹ˆà¸­à¸™ à¸”à¸µà¸à¸§à¹ˆà¸²à¹„à¸¡à¹ˆà¸¡à¸µ VPN à¹€à¸¥à¸¢ (wg_required à¸«à¹‰à¸²à¸¡à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡à¸”à¹‰à¸§à¸¢à¹€à¸™à¹‡à¸•à¸šà¹‰à¸²à¸™)
                if getattr(self, "_wg_ignore_cool", False):
                    if int(config.get("wg_lock", 1) or 0) and confs:
                        # wg_lock: à¹„à¸¡à¹ˆà¸¡à¸µà¹„à¸Ÿà¸¥à¹Œà¸§à¹ˆà¸²à¸‡ -> à¸«à¹‰à¸²à¸¡à¸›à¸¥à¹ˆà¸­à¸¢à¸ˆà¸­à¹„à¸¡à¹ˆà¸¡à¸µ IP: à¹ƒà¸Šà¹‰ IP à¹€à¸”à¸´à¸¡à¸‚à¸­à¸‡à¸ˆà¸­ à¸–à¹‰à¸²à¹„à¸¡à¹ˆà¸¡à¸µà¸à¹‡à¹ƒà¸Šà¹‰à¹„à¸Ÿà¸¥à¹Œà¸£à¹ˆà¸§à¸¡à¸à¸±à¸šà¸ˆà¸­à¸­à¸·à¹ˆà¸™
                        last = getattr(self, "_wg_last_conf", None)
                        pick = last if last and os.path.isfile(last) else confs[idx % len(confs)]
                        if not getattr(self, "_wg_share_warned", False):
                            self._wg_share_warned = True
                            print(f"[{self.device_id}] [WG] à¹„à¸Ÿà¸¥à¹Œà¸§à¹ˆà¸²à¸‡à¹„à¸¡à¹ˆà¸žà¸­ - à¹ƒà¸Šà¹‰ {os.path.basename(pick)} à¸£à¹ˆà¸§à¸¡à¸à¸±à¸šà¸ˆà¸­à¸­à¸·à¹ˆà¸™à¹„à¸›à¸à¹ˆà¸­à¸™ (à¹„à¸¡à¹ˆà¸›à¸¥à¹ˆà¸­à¸¢à¹ƒà¸«à¹‰à¹„à¸¡à¹ˆà¸¡à¸µ IP)")
                        return pick
                    return None              # à¹„à¸¡à¹ˆà¸ªà¸™à¸à¸²à¸£à¸žà¸±à¸à¹à¸¥à¹‰à¸§à¸à¹‡à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸§à¹ˆà¸²à¸‡ = à¹„à¸Ÿà¸¥à¹Œà¸–à¸¹à¸à¸ˆà¸­à¸­à¸·à¹ˆà¸™à¸ˆà¸­à¸‡à¸«à¸¡à¸”à¸ˆà¸£à¸´à¸‡
                self._wg_ignore_cool = True
                try:
                    return self._wg_conf_for_device()
                finally:
                    self._wg_ignore_cool = False
            self._wg_bad = set()
            return self._wg_conf_for_device()
        if not getattr(self, "_wg_short_warned", False):
            self._wg_short_warned = True
            print(f"[{self.device_id}] [WG] à¹„à¸Ÿà¸¥à¹Œ config à¹„à¸¡à¹ˆà¸žà¸­ ({len(confs)} à¹„à¸Ÿà¸¥à¹Œ à¸–à¸¹à¸à¸ˆà¸­à¸­à¸·à¹ˆà¸™à¸ˆà¸­à¸‡à¸«à¸¡à¸”à¹à¸¥à¹‰à¸§) - à¸ˆà¸­à¸™à¸µà¹‰à¹„à¸¡à¹ˆà¸•à¹ˆà¸­ VPN "
                  f"(à¹‚à¸«à¸¥à¸” .conf à¹€à¸žà¸´à¹ˆà¸¡à¸¡à¸²à¹ƒà¸ªà¹ˆ {wg_dir}/)")
        if int(config.get("wg_lock", 1) or 0) and confs:
            # wg_lock: à¹„à¸¡à¹ˆà¸¡à¸µà¹„à¸Ÿà¸¥à¹Œà¸§à¹ˆà¸²à¸‡ -> à¸«à¹‰à¸²à¸¡à¸›à¸¥à¹ˆà¸­à¸¢à¸ˆà¸­à¹„à¸¡à¹ˆà¸¡à¸µ IP: à¹ƒà¸Šà¹‰ IP à¹€à¸”à¸´à¸¡à¸‚à¸­à¸‡à¸ˆà¸­ à¸–à¹‰à¸²à¹„à¸¡à¹ˆà¸¡à¸µà¸à¹‡à¹ƒà¸Šà¹‰à¹„à¸Ÿà¸¥à¹Œà¸£à¹ˆà¸§à¸¡à¸à¸±à¸šà¸ˆà¸­à¸­à¸·à¹ˆà¸™
            last = getattr(self, "_wg_last_conf", None)
            pick = last if last and os.path.isfile(last) else confs[idx % len(confs)]
            if not getattr(self, "_wg_share_warned", False):
                self._wg_share_warned = True
                print(f"[{self.device_id}] [WG] à¹„à¸Ÿà¸¥à¹Œà¸§à¹ˆà¸²à¸‡à¹„à¸¡à¹ˆà¸žà¸­ - à¹ƒà¸Šà¹‰ {os.path.basename(pick)} à¸£à¹ˆà¸§à¸¡à¸à¸±à¸šà¸ˆà¸­à¸­à¸·à¹ˆà¸™à¹„à¸›à¸à¹ˆà¸­à¸™ (à¹„à¸¡à¹ˆà¸›à¸¥à¹ˆà¸­à¸¢à¹ƒà¸«à¹‰à¹„à¸¡à¹ˆà¸¡à¸µ IP)")
            return pick
        return None

    def _wg_after_refresh(self):
        """wg_after_login: à¸à¸” refresh à¹à¸¥à¹‰à¸§ -> à¸•à¹ˆà¸­ VPN à¸•à¸£à¸‡à¸™à¸µà¹‰à¹€à¸¥à¸¢ (à¸ªà¹ˆà¸‡à¹„à¸Ÿà¸¥à¹Œ/à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¹„à¸›à¸”à¹‰à¸§à¸¢à¹€à¸™à¹‡à¸•à¸›à¸à¸•à¸´à¹à¸¥à¹‰à¸§)"""
        if int(config.get("use_host_vpn", 0) or 0):
            return   # host VPN mode: VPN à¸­à¸¢à¸¹à¹ˆà¸™à¸­à¸à¸­à¸µà¸¡à¸¹à¸¯ à¹„à¸¡à¹ˆà¹à¸•à¸°
        if int(config.get("wg_after_login", 0) or 0):
            self._ensure_wireguard()

    def _wg_vpn_active(self):
        """Android à¸¢à¸±à¸‡à¸¡à¸µ VPN à¸•à¹ˆà¸­à¸­à¸¢à¸¹à¹ˆà¹„à¸«à¸¡ (à¸”à¸¹à¸—à¸±à¹‰à¸‡ tun interface à¹à¸¥à¸° VPN network à¹ƒà¸™ connectivity)"""
        if self._wg_is_up():
            return True
        r = self.adb_shell("dumpsys connectivity 2>/dev/null | grep -c 'VPN CONNECTED' || true", timeout=15)
        try:
            return int((r.stdout or b"0").strip().splitlines()[0] or 0) > 0
        except Exception:
            return False

    # cache: à¸ˆà¸­à¹„à¸«à¸™ clear WG à¹„à¸›à¹à¸¥à¹‰à¸§à¸£à¸­à¸šà¸™à¸µà¹‰ - à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸—à¸³à¸‹à¹‰à¸³à¸—à¸¸à¸à¹„à¸Ÿà¸¥à¹Œ (à¸£à¸µà¸ªà¸•à¸²à¸£à¹Œà¸— process à¸„à¹ˆà¸­à¸¢à¸—à¸³à¹ƒà¸«à¸¡à¹ˆ)
    _WG_CLEARED_DEVICES = set()

    def _force_kill_wg_on_emu(self):
        """KILL_VPN mode: clear WireGuard à¸šà¸™ emulator à¹€à¸”à¹‡à¸”à¸‚à¸²à¸” à¸„à¸£à¸±à¹‰à¸‡à¹€à¸”à¸µà¸¢à¸§à¸•à¹ˆà¸­ process
        - à¸†à¹ˆà¸²à¹à¸­à¸› WireGuard (force-stop)
        - disable tunnel à¸—à¸±à¹‰à¸‡à¸«à¸¡à¸” (set-tunnel-down à¸—à¸¸à¸ tunnel)
        - clear app data (à¸¥à¸š tunnel config à¸«à¸¡à¸”)
        - à¹ƒà¸Šà¹‰à¸•à¸­à¸™ user à¸¢à¹‰à¸²à¸¢à¹„à¸› ExpressVPN à¸šà¸™ Windows à¹à¸—à¸™ -> à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸¡à¸µ VPN à¸šà¸™ emulator"""
        dev = self.device_id
        if dev in self._WG_CLEARED_DEVICES:
            return   # à¸—à¸³à¸„à¸£à¸šà¹à¸¥à¹‰à¸§ à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸—à¸³à¸‹à¹‰à¸³
        try:
            print(f"[{dev}] [WG-CLEAR] kill WireGuard + clear all tunnels (KILL_VPN mode)")
            # 1) kill WG app
            try:
                self.adb_shell(f"su -c 'am force-stop {self.WG_PKG}'", timeout=10)
                self.adb_shell(f"am force-stop {self.WG_PKG}", timeout=10)
            except Exception:
                pass
            # 2) set all possible tunnels down (broadcast)
            for tun in (self.WG_TUNNEL, "lgr", "default"):
                try:
                    self.adb_shell(f"su -c 'am broadcast -f 0x20 -p {self.WG_PKG} "
                                   f"-a {self.WG_PKG}.action.SET_TUNNEL_DOWN --es tunnel {tun}'",
                                   timeout=10)
                except Exception:
                    pass
            # 3) clear WG app data - à¸¥à¸š tunnel config à¸«à¸¡à¸” (à¸•à¹‰à¸­à¸‡ login à¹ƒà¸«à¸¡à¹ˆà¸–à¹‰à¸²à¸à¸¥à¸±à¸šà¸¡à¸²à¹ƒà¸Šà¹‰)
            try:
                self.adb_shell(f"pm clear {self.WG_PKG}", timeout=15)
            except Exception:
                pass
            self._WG_CLEARED_DEVICES.add(dev)
            print(f"[{dev}] [WG-CLEAR] done - ExpressVPN à¸šà¸™ Windows à¸ˆà¸°à¸„à¸¸à¸¡ IP à¹à¸—à¸™")
        except Exception as e:
            print(f"[{dev}] [WG-CLEAR] error (non-fatal): {e}")

    def _wg_down(self):
        """à¸›à¸´à¸” VPN à¸‚à¸­à¸‡à¸ˆà¸­à¸™à¸µà¹‰ "à¸ªà¸™à¸´à¸—" à¸à¹ˆà¸­à¸™à¸ªà¹ˆà¸‡à¹„à¸Ÿà¸¥à¹Œ/à¹€à¸›à¸´à¸”à¹€à¸à¸¡ à¹ƒà¸«à¹‰à¸­à¸­à¸à¹€à¸™à¹‡à¸•à¸”à¹‰à¸§à¸¢ IP à¸›à¸à¸•à¸´

        à¸—à¸³à¸—à¸¸à¸à¸„à¸£à¸±à¹‰à¸‡ (à¹„à¸¡à¹ˆà¹ƒà¸Šà¹ˆà¹€à¸‰à¸žà¸²à¸°à¸•à¸­à¸™à¹€à¸«à¹‡à¸™ tun): à¸ªà¸±à¹ˆà¸‡à¸›à¸´à¸” tunnel -> à¸†à¹ˆà¸²à¹à¸­à¸› WireGuard ->
        à¸£à¸­à¸ˆà¸™ Android à¹„à¸¡à¹ˆà¸¡à¸µ VPN à¸„à¹‰à¸²à¸‡ -> à¸£à¸­à¸ˆà¸™à¸­à¸­à¸à¹€à¸™à¹‡à¸•à¹„à¸”à¹‰à¸ˆà¸£à¸´à¸‡ (ping) -> à¸žà¸±à¸à¹ƒà¸«à¹‰à¹€à¸™à¹‡à¸•à¸™à¸´à¹ˆà¸‡ à¹à¸¥à¹‰à¸§à¸„à¹ˆà¸­à¸¢à¹„à¸›à¸•à¹ˆà¸­
        """
        if int(config.get("use_host_vpn", 0) or 0):
            return None   # host VPN mode: VPN à¸­à¸¢à¸¹à¹ˆà¸™à¸­à¸à¸­à¸µà¸¡à¸¹à¸¯ à¹„à¸¡à¹ˆà¹à¸•à¸°
        if int(config.get("wg_lock", 1) or 0):
            return None   # wg_lock: à¸«à¹‰à¸²à¸¡à¸›à¸´à¸” VPN à¹€à¸”à¹‡à¸”à¸‚à¸²à¸” (à¸›à¸´à¸”à¹à¸¥à¹‰à¸§à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡à¹„à¸¡à¹ˆà¹„à¸”à¹‰)
        if not int(config.get("wg_enabled", 1) or 0):
            return
        try:
            was = self._wg_vpn_active()
            self.adb_shell(f"su -c 'am broadcast -f 0x20 -p {self.WG_PKG} "
                           f"-a {self.WG_PKG}.action.SET_TUNNEL_DOWN --es tunnel {self.WG_TUNNEL}'", timeout=20)
            _real_sleep(1)
            self.adb_shell(f"su -c 'am force-stop {self.WG_PKG}'", timeout=15)
            self._wg_conf_applied = None
            gone = False
            for _ in range(10):
                if not self._wg_vpn_active():
                    gone = True
                    break
                _real_sleep(1)
            net = False
            for _ in range(10):
                r = self.adb_shell("ping -c 1 -W 2 1.1.1.1 >/dev/null 2>&1 && echo OK || echo FAIL", timeout=8)
                if b"OK" in (r.stdout or b""):
                    net = True
                    break
                _real_sleep(1)
            if was or not gone or not net:
                _real_sleep(float(config.get("wg_down_settle", 0.5)))   # à¹€à¸™à¹‡à¸•à¹€à¸žà¸´à¹ˆà¸‡à¸ªà¸¥à¸±à¸š - à¸žà¸±à¸à¹ƒà¸«à¹‰à¸™à¸´à¹ˆà¸‡à¸à¹ˆà¸­à¸™à¹€à¸›à¸´à¸”à¹€à¸à¸¡
                print(f"[{self.device_id}] [WG] à¸›à¸´à¸” VPN à¸à¹ˆà¸­à¸™à¹€à¸›à¸´à¸”à¹€à¸à¸¡: "
                      f"{'à¸›à¸´à¸”à¸ªà¸™à¸´à¸—à¹à¸¥à¹‰à¸§' if gone else 'à¸¢à¸±à¸‡à¹€à¸«à¹‡à¸™ VPN à¸„à¹‰à¸²à¸‡!'} | à¹€à¸™à¹‡à¸•: {'à¹ƒà¸Šà¹‰à¹„à¸”à¹‰' if net else 'à¸¢à¸±à¸‡à¸­à¸­à¸à¹„à¸¡à¹ˆà¹„à¸”à¹‰!'}")
        except Exception as e:
            print(f"[{self.device_id}] [WG] à¸›à¸´à¸” VPN à¹„à¸¡à¹ˆà¸ªà¸³à¹€à¸£à¹‡à¸ˆ: {e}")

    def _wg_request_net_recover(self, where, switch_now=False):
        """à¹€à¸ˆà¸­ Unstable network (fixnetv3) à¸šà¸™à¸ˆà¸­à¸—à¸µà¹ˆà¸•à¹ˆà¸­ VPN à¸­à¸¢à¸¹à¹ˆ -> à¸—à¸³à¸—à¸±à¸™à¸—à¸µà¸•à¸£à¸‡à¸™à¸µà¹‰ (à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸£à¸­à¸¥à¸¹à¸›à¸¥à¹‡à¸­à¸à¸­à¸´à¸™):
        à¸›à¸´à¸”à¹€à¸à¸¡ -> à¸›à¸´à¸” VPN à¸ªà¸™à¸´à¸— -> à¹€à¸›à¸´à¸” VPN à¹ƒà¸«à¸¡à¹ˆ -> à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¹ƒà¸«à¸¡à¹ˆ
        à¹„à¸¡à¹ˆà¸¥à¹‰à¸²à¸‡ shared_prefs (à¹„à¸Ÿà¸¥à¹Œà¸šà¸±à¸à¸Šà¸µà¸—à¸µà¹ˆà¸ªà¹ˆà¸‡à¹€à¸‚à¹‰à¸²à¹„à¸›à¸¢à¸±à¸‡à¸­à¸¢à¸¹à¹ˆ à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¹à¸¥à¹‰à¸§à¹€à¸›à¹‡à¸™à¹„à¸­à¸”à¸µà¹€à¸”à¸´à¸¡)
        à¸„à¸·à¸™ True = à¸ˆà¸±à¸”à¸à¸²à¸£à¹à¸¥à¹‰à¸§ (à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸à¸” RETRY) ; à¸ˆà¸­à¸—à¸µà¹ˆà¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸•à¹ˆà¸­ VPN / à¸„à¸£à¸šà¹‚à¸„à¸§à¸•à¸² -> False (à¸à¸” RETRY à¹à¸šà¸šà¹€à¸”à¸´à¸¡)"""
        if int(config.get("wg_lock", 1) or 0):
            return False   # wg_lock: à¹„à¸¡à¹ˆà¸›à¸´à¸”/à¸ªà¸¥à¸±à¸š VPN à¸•à¸­à¸™à¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸” -> à¸à¸” RETRY à¹à¸šà¸šà¹€à¸”à¸´à¸¡
        if not int(config.get("wg_enabled", 1) or 0):
            return False
        if int(config.get("wg_once", 1) or 0):
            # wg_once: à¹€à¸™à¹‡à¸•à¹à¸à¸§à¹ˆà¸‡à¸„à¸£à¸±à¹‰à¸‡à¹€à¸”à¸µà¸¢à¸§à¹„à¸¡à¹ˆà¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™ IP (à¸à¸” RETRY) à¹à¸•à¹ˆà¸–à¹‰à¸²à¹€à¸ˆà¸­à¸‹à¹‰à¸³à¸„à¸£à¸š wg_net_switch_after à¸„à¸£à¸±à¹‰à¸‡
            # = IP à¸™à¸µà¹‰à¹ƒà¸Šà¹‰à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¹à¸¥à¹‰à¸§ -> à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™ IP à¸—à¸±à¸™à¸—à¸µ (VPN à¸›à¸´à¸”à¹à¸„à¹ˆà¸Šà¹ˆà¸§à¸‡à¸ªà¸¥à¸±à¸š à¹à¸¥à¹‰à¸§à¸•à¹ˆà¸­à¸•à¸±à¸§à¹ƒà¸«à¸¡à¹ˆà¸à¹ˆà¸­à¸™à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¹€à¸ªà¸¡à¸­)
            self._wg_net_hits = getattr(self, "_wg_net_hits", 0) + 1
            lim = int(config.get("wg_net_switch_after", 1) or 1)   # 1 = à¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”à¸„à¸£à¸±à¹‰à¸‡à¹à¸£à¸à¸à¹‡ à¸›à¸´à¸”à¹à¸­à¸› -> IP à¹ƒà¸«à¸¡à¹ˆ -> à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¹ƒà¸«à¸¡à¹ˆ
            if self._wg_net_hits < lim:
                # à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸„à¸£à¸š -> à¸›à¸´à¸”à¹à¸­à¸›à¹à¸¥à¹‰à¸§à¹€à¸›à¸´à¸”à¹ƒà¸«à¸¡à¹ˆà¸”à¹‰à¸§à¸¢ IP à¹€à¸”à¸´à¸¡à¸à¹ˆà¸­à¸™ (VPN à¹„à¸¡à¹ˆà¹à¸•à¸° à¹€à¸›à¸´à¸”à¸„à¹‰à¸²à¸‡à¹„à¸§à¹‰)
                print(f"[{self.device_id}] [WG] à¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸” ({where}) {self._wg_net_hits}/{lim} - à¸›à¸´à¸”à¹à¸­à¸›à¹€à¸‚à¹‰à¸²à¹ƒà¸«à¸¡à¹ˆ (IP à¹€à¸”à¸´à¸¡) à¸„à¸£à¸šà¹à¸¥à¹‰à¸§à¸ˆà¸°à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™ IP")
                try:
                    self.last_activity_time = time.time()
                    self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
                    _real_sleep(2)
                    self._wg_must_be_up()     # VPN à¸¢à¸±à¸‡à¸•à¹ˆà¸­à¸­à¸¢à¸¹à¹ˆ = à¸‚à¹‰à¸²à¸¡à¹€à¸£à¹‡à¸§ ; à¸«à¸¥à¸¸à¸” = à¸•à¹ˆà¸­à¹ƒà¸«à¸¡à¹ˆà¸à¹ˆà¸­à¸™à¹€à¸›à¸´à¸”à¹€à¸à¸¡
                    self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "start", "-n", "com.linecorp.LGRGS/com.linecorp.common.activity.LineActivity"], timeout=15)
                    self.last_activity_time = time.time()
                    _real_sleep(3)
                    return True
                except Exception as e:
                    print(f"[{self.device_id}] [WG] à¸›à¸´à¸”à¹à¸­à¸›à¹€à¸‚à¹‰à¸²à¹ƒà¸«à¸¡à¹ˆà¹„à¸¡à¹ˆà¸ªà¸³à¹€à¸£à¹‡à¸ˆ: {e}")
                    return False
            self._wg_net_hits = 0
            switch_now = True
        if not getattr(self, "_wg_conf_applied", None):
            return False                      # à¸ˆà¸­à¸™à¸µà¹‰à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸•à¹ˆà¸­ VPN -> à¹„à¸¡à¹ˆà¹ƒà¸Šà¹ˆà¹€à¸£à¸·à¹ˆà¸­à¸‡ VPN
        lock = self.__dict__.setdefault("_wg_recover_lock", threading.Lock())
        if not lock.acquire(blocking=False):
            return True                       # à¸­à¸µà¸à¹€à¸˜à¸£à¸”à¸à¸³à¸¥à¸±à¸‡à¸à¸¹à¹‰à¸­à¸¢à¸¹à¹ˆ -> à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸à¸”à¸­à¸°à¹„à¸£
        try:
            n = getattr(self, "_wg_recover_n", 0)
            if n >= int(config.get("wg_net_recover_max", 10)):
                return False                  # à¸„à¸£à¸šà¹‚à¸„à¸§à¸•à¸²à¹à¸¥à¹‰à¸§ -> à¸à¸¥à¸±à¸šà¹„à¸›à¸à¸” RETRY à¹à¸šà¸šà¹€à¸”à¸´à¸¡
            self._wg_recover_n = n + 1
            print(f"[{self.device_id}] [WG] à¹€à¸ˆà¸­ Unstable network ({where}) - à¸›à¸´à¸”à¹€à¸à¸¡ + à¸›à¸´à¸”/à¹€à¸›à¸´à¸” VPN à¹ƒà¸«à¸¡à¹ˆ + à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¹ƒà¸«à¸¡à¹ˆ "
                  f"(à¸„à¸£à¸±à¹‰à¸‡à¸—à¸µà¹ˆ {n + 1})")
            self.last_activity_time = time.time()
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
            self._wg_down()
            if switch_now:
                # fixnet1: à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™ IP à¸—à¸±à¸™à¸—à¸µ (à¹„à¸¡à¹ˆà¸£à¸­à¸™à¸±à¸š 2 à¸„à¸£à¸±à¹‰à¸‡) - à¸žà¸±à¸à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¸™à¸µà¹‰à¹„à¸§à¹‰ à¹à¸•à¹ˆà¹„à¸¡à¹ˆà¸¥à¸šà¹„à¸Ÿà¸¥à¹Œ
                cur = getattr(self, "_wg_last_conf", None)
                if cur:
                    self.__dict__.setdefault("_wg_bad", set()).add(cur)
                    if not str(where).startswith("fixnet"):
                        # à¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸” (fixnet) à¹„à¸¡à¹ˆà¹ƒà¸Šà¹ˆà¹‚à¸”à¸™à¸šà¸¥à¹‡à¸­à¸ -> à¹„à¸¡à¹ˆà¸žà¸±à¸à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œ 6 à¸Šà¸¡. (à¹€à¸„à¸¢à¸žà¸±à¸à¸ˆà¸™à¸«à¸¡à¸”à¸—à¸¸à¸à¸•à¸±à¸§ à¹„à¸¡à¹ˆà¹€à¸«à¸¥à¸·à¸­à¹ƒà¸«à¹‰à¸•à¹ˆà¸­)
                        _wg_cooldown_add(os.path.dirname(cur), _wg_endpoint(cur))
                    try:
                        os.remove(os.path.join(os.path.dirname(cur), ".claims", os.path.basename(cur) + ".lock"))
                    except OSError:
                        pass
                    self._wg_conf_written = None
                    print(f"[{self.device_id}] [WG] {where}: à¹€à¸¥à¸´à¸à¹ƒà¸Šà¹‰ {os.path.basename(cur)} - à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™ IP")
            else:
                # à¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”à¸‹à¹‰à¸³à¸šà¸™à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹€à¸”à¸´à¸¡ -> à¸ªà¸¥à¸±à¸šà¹„à¸›à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¸ªà¸³à¸£à¸­à¸‡à¸—à¸µà¹ˆà¸§à¹ˆà¸²à¸‡à¸­à¸¢à¸¹à¹ˆ (auto failover)
                self._wg_strike("Unstable network")
            self._wg_must_be_up()
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "start", "-n",
                          "com.linecorp.LGRGS/com.linecorp.common.activity.LineActivity"], timeout=15)
            self.last_activity_time = time.time()
            print(f"[{self.device_id}] [WG] à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¹ƒà¸«à¸¡à¹ˆà¹à¸¥à¹‰à¸§ (VPN: {os.path.basename(str(getattr(self, '_wg_conf_applied', '') or '-'))})")
            _real_sleep(3)
            return True
        except Exception as e:
            print(f"[{self.device_id}] [WG] à¸à¸¹à¹‰à¹€à¸™à¹‡à¸•à¹„à¸¡à¹ˆà¸ªà¸³à¹€à¸£à¹‡à¸ˆ: {e}")
            return False
        finally:
            lock.release()

    def _wg_auth_failed(self):
        """Authentication failed (fixid) à¸•à¸­à¸™à¸•à¹ˆà¸­ VPN -> à¸”à¹ˆà¸²à¸™ login à¸‚à¸­à¸‡ LINE à¹„à¸¡à¹ˆà¸£à¸±à¸š IP à¸‚à¸­à¸‡ VPN
        à¹€à¸ˆà¸­à¸„à¸£à¸š wg_auth_fallback à¹„à¸­à¸”à¸µ (default 2) -> à¸›à¸´à¸” VPN à¸‚à¸­à¸‡à¸ˆà¸­à¸™à¸µà¹‰à¹„à¸›à¸ˆà¸™à¸›à¸´à¸”à¸šà¸­à¸— à¹ƒà¸Šà¹‰à¹€à¸™à¹‡à¸•à¸šà¹‰à¸²à¸™à¹à¸—à¸™ (0 = à¹„à¸¡à¹ˆà¸›à¸´à¸”)"""
        if int(config.get("wg_lock", 1) or 0):
            return None   # wg_lock: à¹„à¸¡à¹ˆà¸›à¸´à¸” VPN à¹à¸¡à¹‰ login à¹„à¸¡à¹ˆà¸œà¹ˆà¸²à¸™
        if not int(config.get("wg_enabled", 1) or 0) or not getattr(self, "_wg_conf_applied", None):
            return
        lim = int(config.get("wg_auth_fallback", 0) or 0)
        if lim <= 0:
            return
        self._wg_auth_fail = getattr(self, "_wg_auth_fail", 0) + 1
        print(f"[{self.device_id}] [WG] Authentication failed à¸œà¹ˆà¸²à¸™ VPN ({self._wg_auth_fail}/{lim})")
        if self._wg_auth_fail >= lim:
            self._wg_off = True
            self._wg_down()
            print(f"[{self.device_id}] [WG] à¸”à¹ˆà¸²à¸™ login LINE à¹„à¸¡à¹ˆà¸£à¸±à¸š IP VPN - à¸›à¸´à¸” VPN à¸ˆà¸­à¸™à¸µà¹‰ à¹ƒà¸Šà¹‰à¹€à¸™à¹‡à¸•à¸šà¹‰à¸²à¸™à¹à¸—à¸™ (à¸ˆà¸™à¸à¸§à¹ˆà¸²à¸ˆà¸°à¹€à¸›à¸´à¸”à¸šà¸­à¸—à¹ƒà¸«à¸¡à¹ˆ)")

    def _wg_strike(self, reason, now_switch=False):
        """à¸ˆà¸­à¸™à¸µà¹‰à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸šà¸™à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œ VPN à¸›à¸±à¸ˆà¸ˆà¸¸à¸šà¸±à¸™ 1 à¸„à¸£à¸±à¹‰à¸‡ (Unstable network / fixid à¸„à¸£à¸š / LINE GAME à¸„à¹‰à¸²à¸‡ /
        à¸ˆà¸­à¸”à¸³ / login failed) - à¸„à¸£à¸š wg_failover_after (2) à¸„à¸£à¸±à¹‰à¸‡à¸šà¸™à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹€à¸”à¸´à¸¡ -> à¹€à¸¥à¸´à¸à¹ƒà¸Šà¹‰ à¹à¸¥à¹‰à¸§à¸ˆà¸­à¸‡à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¸­à¸·à¹ˆà¸™
        (à¸¡à¸µà¸œà¸¥à¸•à¸­à¸™à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¸„à¸£à¸±à¹‰à¸‡à¸–à¸±à¸”à¹„à¸›: open_app à¸ˆà¸°à¸•à¹ˆà¸­ VPN à¸•à¸±à¸§à¹ƒà¸«à¸¡à¹ˆà¹ƒà¸«à¹‰à¹€à¸­à¸‡) ; à¸„à¸·à¸™ True = à¸ªà¸¥à¸±à¸šà¹à¸¥à¹‰à¸§"""
        if int(config.get("wg_lock", 1) or 0):
            # wg_lock: à¹ƒà¸Šà¹‰ IP à¹€à¸”à¸´à¸¡à¸•à¹ˆà¸­à¹„à¸› - à¸¢à¸à¹€à¸§à¹‰à¸™à¸„à¹‰à¸²à¸‡à¸«à¸™à¹‰à¸² LINE GAME à¸‹à¹‰à¸³ (LINE à¹„à¸¡à¹ˆà¸£à¸±à¸š IP à¸™à¸µà¹‰ = à¹„à¸¡à¹ˆà¸¡à¸µà¸—à¸²à¸‡à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡à¹„à¸”à¹‰)
            if not any(k in str(reason) for k in ("LINE GAME", "fixid", "login failed")):   # fixid/login failed à¸„à¸£à¸š = LINE à¹„à¸¡à¹ˆà¸£à¸±à¸š IP à¸™à¸µà¹‰ -> à¸ªà¸¥à¸±à¸šà¸”à¹‰à¸§à¸¢
                return False
            self._wg_line_stuck = getattr(self, "_wg_line_stuck", 0) + 1
            lim = int(config.get("wg_line_stuck_switch", 2) or 2)
            cur = getattr(self, "_wg_conf_applied", None) or getattr(self, "_wg_last_conf", None)
            print(f"[{self.device_id}] [WG] à¸„à¹‰à¸²à¸‡à¸«à¸™à¹‰à¸² LINE GAME {self._wg_line_stuck}/{lim} à¸šà¸™ {os.path.basename(str(cur or '-'))}")
            if self._wg_line_stuck < lim or not cur or not os.path.isfile(str(cur)):
                return False
            self._wg_line_stuck = 0
            self.__dict__.setdefault("_wg_bad", set()).add(cur)
            try:
                os.remove(os.path.join(os.path.dirname(cur), ".claims", os.path.basename(cur) + ".lock"))
            except OSError:
                pass
            self._wg_conf_applied = None      # open_app à¸„à¸£à¸±à¹‰à¸‡à¸–à¸±à¸”à¹„à¸›à¸ˆà¸°à¸•à¹ˆà¸­ IP à¸•à¸±à¸§à¹ƒà¸«à¸¡à¹ˆ (VPN à¹„à¸¡à¹ˆà¸›à¸´à¸” à¹à¸„à¹ˆà¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™à¹„à¸Ÿà¸¥à¹Œ)
            self._wg_conf_written = None
            print(f"[{self.device_id}] [WG] LINE à¹„à¸¡à¹ˆà¸£à¸±à¸š IP {os.path.basename(cur)} - à¸ªà¸¥à¸±à¸š IP à¹ƒà¸«à¸¡à¹ˆà¸•à¸­à¸™à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¸£à¸­à¸šà¸«à¸™à¹‰à¸²")
            return True
        if not int(config.get("wg_enabled", 1) or 0) or getattr(self, "_wg_off", False):
            return False
        if int(config.get("wg_once", 1) or 0) and not any(k in str(reason) for k in ("fixid", "login failed")):
            return False                      # wg_once: à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹€à¸‰à¸žà¸²à¸°à¹‚à¸”à¸™à¸šà¸¥à¹‡à¸­à¸ (fixid / login failed) - à¹€à¸™à¹‡à¸•à¹à¸à¸§à¹ˆà¸‡/à¸ˆà¸­à¸”à¸³/à¸„à¹‰à¸²à¸‡ à¹„à¸¡à¹ˆà¸™à¸±à¸š
        cur = getattr(self, "_wg_conf_applied", None) or getattr(self, "_wg_last_conf", None)
        if not cur:
            return False
        strikes = self.__dict__.setdefault("_wg_strikes", {})
        strikes[cur] = strikes.get(cur, 0) + 1
        lim = int(config.get("wg_failover_after", 2))
        print(f"[{self.device_id}] [WG] à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡à¹„à¸¡à¹ˆà¹„à¸”à¹‰ ({reason}) à¸šà¸™ {os.path.basename(cur)} - à¸„à¸£à¸±à¹‰à¸‡à¸—à¸µà¹ˆ {strikes[cur]}/{lim}")
        self._block_evidence(reason, cur)
        if strikes[cur] >= lim:
            self._wg_down()
            self._wg_failover(cur)
            return True
        return False

    def _net_probe(self):
        """(IP à¸‚à¸²à¸­à¸­à¸, HTTP code à¸‚à¸­à¸‡à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹€à¸à¸¡) à¸œà¹ˆà¸²à¸™à¹€à¸™à¹‡à¸•à¸—à¸µà¹ˆà¹€à¸à¸¡à¹ƒà¸Šà¹‰à¸ˆà¸£à¸´à¸‡
        à¸§à¸±à¸”à¸”à¹‰à¸§à¸¢ UID à¸‚à¸­à¸‡à¹€à¸à¸¡ (com.linecorp.LGRGS) à¹‚à¸”à¸¢à¸•à¸£à¸‡ - split tunnel IncludedApplications à¹ƒà¸Šà¹‰ UID filter
        à¸–à¹‰à¸²à¹ƒà¸Šà¹‰ UID 0 (root) à¸ˆà¸°à¹„à¸”à¹‰ IP à¸ˆà¸£à¸´à¸‡à¹€à¸ªà¸¡à¸­à¹€à¸žà¸£à¸²à¸° root à¹„à¸¡à¹ˆà¸­à¸¢à¸¹à¹ˆà¹ƒà¸™ IncludedApplications
        code: 401 = à¸•à¹ˆà¸­à¹„à¸”à¹‰à¸›à¸à¸•à¸´ (à¹à¸„à¹ˆà¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸¥à¹‡à¸­à¸à¸­à¸´à¸™) / 000 = à¹„à¸¡à¹ˆà¸•à¸­à¸š (IP à¹‚à¸”à¸™à¸šà¸¥à¹‡à¸­à¸à¸«à¸£à¸·à¸­à¹€à¸™à¹‡à¸•à¹„à¸¡à¹ˆà¸­à¸­à¸) / 403,429 = à¸–à¸¹à¸à¸›à¸à¸´à¹€à¸ªà¸˜"""
        safe = self.device_id.replace(":", "_")
        sh = f"/data/local/tmp/probe_{safe}.sh"
        local = os.path.join(tempfile.gettempdir(), f"probe_{safe}.sh")
        script = chr(10).join([
            "command -v curl >/dev/null 2>&1 || { echo 'P NA NA'; rm -f " + sh + "; exit 0; }",
            # à¸«à¸² UID à¸‚à¸­à¸‡à¹€à¸à¸¡ LGR - split tunnel à¹ƒà¸Šà¹‰ UID filter à¸œà¹ˆà¸²à¸™ IncludedApplications
            "UID=$(stat -c %u /data/data/com.linecorp.LGRGS 2>/dev/null)",
            "if [ -z \"$UID\" ] || [ \"$UID\" = \"0\" ]; then",
            "  # à¹„à¸¡à¹ˆà¸¡à¸µà¹€à¸à¸¡ -> probe UID 0 à¹à¸šà¸šà¹€à¸”à¸´à¸¡ (à¹ƒà¸Šà¹‰ ip rule trick)",
            "  R=0",
            "  if ip -o link | grep -q ' tun0'; then ip rule add pref 10500 uidrange 0-0 lookup tun0 2>/dev/null && R=1; fi",
            "  IP=$(curl -s -m 8 https://api.ipify.org)",
            "  C=$(curl -s -m 12 -o /dev/null -w '%{http_code}' https://rangers-api.line-apps.com/v12.3/home)",
            "  [ $R = 1 ] && ip rule del pref 10500",
            "else",
            "  # à¸¢à¸´à¸‡ curl à¸œà¹ˆà¸²à¸™ UID à¸‚à¸­à¸‡à¹€à¸à¸¡ - traffic à¸ˆà¸°à¹€à¸‚à¹‰à¸² split tunnel à¹€à¸«à¸¡à¸·à¸­à¸™à¹€à¸à¸¡à¸ˆà¸£à¸´à¸‡",
            "  IP=$(su $UID -c 'curl -s -m 8 https://api.ipify.org' 2>/dev/null)",
            "  [ -z \"$IP\" ] && IP=$(su -c \"su $UID -c 'curl -s -m 8 https://api.ipify.org'\" 2>/dev/null)",
            "  C=$(su $UID -c 'curl -s -m 12 -o /dev/null -w %{http_code} https://rangers-api.line-apps.com/v12.3/home' 2>/dev/null)",
            "  [ -z \"$C\" ] && C=$(su -c \"su $UID -c 'curl -s -m 12 -o /dev/null -w %{http_code} https://rangers-api.line-apps.com/v12.3/home'\" 2>/dev/null)",
            "fi",
            "echo \"P ${IP:--} ${C:-000}\"",
            f"rm -f {sh}",
            "",
        ])
        with open(local, "w", newline=chr(10)) as f:
            f.write(script)
        self.adb_run([self.adb_cmd, "-s", self.device_id, "push", local, sh], timeout=20)
        r = self.adb_shell(f"su -c 'sh {sh}'", timeout=40)
        for line in (r.stdout or b"").decode("utf-8", "ignore").splitlines():
            if line.startswith("P "):
                parts = line.split()
                return parts[1], parts[2]
        return "-", "000"

    def _block_evidence(self, reason, conf=None):
        """à¹€à¸à¹‡à¸šà¸«à¸¥à¸±à¸à¸à¸²à¸™à¸•à¸­à¸™à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡à¹„à¸¡à¹ˆà¹„à¸”à¹‰ -> logs/block_log.csv + à¸£à¸¹à¸›à¸ˆà¸­ logs/block/ (à¹ƒà¸Šà¹‰à¸«à¸²à¸§à¹ˆà¸²à¹‚à¸”à¸™ block à¹€à¸žà¸£à¸²à¸°à¸­à¸°à¹„à¸£)
        api = HTTP code à¸ˆà¸²à¸à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹€à¸à¸¡à¸œà¹ˆà¸²à¸™à¹€à¸™à¹‡à¸•à¸‚à¸­à¸‡à¸ˆà¸­à¸™à¸µà¹‰: 401 = IP à¹ƒà¸Šà¹‰à¹„à¸”à¹‰à¸›à¸à¸•à¸´ / 403,429,000 = IP à¹‚à¸”à¸™ block à¸«à¸£à¸·à¸­à¹€à¸™à¹‡à¸•à¹„à¸¡à¹ˆà¸­à¸­à¸"""
        if not int(config.get("block_log", 1) or 0):
            return
        try:
            ip, code = self._net_probe()
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            os.makedirs(os.path.join("logs", "block"), exist_ok=True)
            shot = os.path.join("logs", "block", time.strftime("%Y%m%d_%H%M%S_") + self.device_id.replace(":", "_") + ".png")
            try:
                with open(shot, "wb") as f:
                    f.write(self.adb_run(["exec-out", "screencap", "-p"], timeout=20).stdout or b"")
            except Exception:
                shot = "-"
            new = not os.path.exists(os.path.join("logs", "block_log.csv"))
            with open(os.path.join("logs", "block_log.csv"), "a", encoding="utf-8-sig") as f:
                if new:
                    f.write("time,device,reason,server,exit_ip,api_code,screenshot" + chr(10))
                f.write(f"{ts},{self.device_id},{reason},{_wg_endpoint(conf) if conf else '-'},{ip},{code},{shot}" + chr(10))
            print(f"[{self.device_id}] [BLOCK] {reason} | IP {ip} | game api {code} | {shot}")
        except Exception as e:
            print(f"[{self.device_id}] [BLOCK] à¹€à¸à¹‡à¸šà¸«à¸¥à¸±à¸à¸à¸²à¸™à¹„à¸¡à¹ˆà¹„à¸”à¹‰: {e}")

    def _wg_ok(self):
        """à¸¥à¹‡à¸­à¸à¸­à¸´à¸™à¸œà¹ˆà¸²à¸™à¸šà¸™à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¸™à¸µà¹‰ -> à¸¥à¹‰à¸²à¸‡à¸•à¸±à¸§à¸™à¸±à¸š (à¸™à¸±à¸šà¹€à¸‰à¸žà¸²à¸°à¸„à¸£à¸±à¹‰à¸‡à¸—à¸µà¹ˆà¸¥à¹‰à¸¡à¸•à¸´à¸”à¸à¸±à¸™) + à¸¢à¸¶à¸” IP à¹„à¸§à¹‰à¸–à¸²à¸§à¸£"""
        cur = getattr(self, "_wg_conf_applied", None) or getattr(self, "_wg_last_conf", None)
        if cur:
            self.__dict__.setdefault("_wg_strikes", {})[cur] = 0
            # sticky: à¸¢à¸¶à¸” IP à¸™à¸µà¹‰à¸–à¸²à¸§à¸£ - _wg_conf_for_device à¸ˆà¸°à¸„à¸·à¸™ cur à¹€à¸ªà¸¡à¸­ à¸ˆà¸™à¸à¸§à¹ˆà¸² _wg_failover
            # à¸ˆà¸° clear (à¹€à¸‰à¸žà¸²à¸°à¸•à¸­à¸™à¹€à¸ˆà¸­ fixnet1 à¸—à¸µà¹ˆ start à¹€à¸à¸¡)
            if int(config.get("wg_stick_on_success", 1) or 0):
                prev = getattr(self, "_wg_stuck_conf", None)
                if prev != cur:
                    self._wg_stuck_conf = cur
                    print(f"[{self.device_id}] [WG] à¸¥à¹‡à¸­à¸ IP à¸™à¸µà¹‰à¹„à¸§à¹‰à¸–à¸²à¸§à¸£ ({os.path.basename(cur)}) - à¸ˆà¸°à¸ªà¸¥à¸±à¸šà¹€à¸‰à¸žà¸²à¸°à¹€à¸ˆà¸­ fixnet1")
            # à¸ªà¸¥à¸±à¸š IP à¹€à¸›à¹‡à¸™à¸Šà¹ˆà¸§à¸‡: à¹ƒà¸Šà¹‰à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹€à¸”à¸´à¸¡à¸„à¸£à¸š wg_rotate_logins à¸£à¸­à¸š -> à¸›à¸¥à¹ˆà¸­à¸¢à¹„à¸Ÿà¸¥à¹Œà¸™à¸µà¹‰à¹ƒà¸«à¹‰à¸ˆà¸­à¸­à¸·à¹ˆà¸™
            # à¹à¸¥à¹‰à¸§à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¸£à¸­à¸šà¸«à¸™à¹‰à¸²à¸ˆà¸°à¸•à¹ˆà¸­à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹ƒà¸«à¸¡à¹ˆ (à¹„à¸¡à¹ˆà¸•à¸±à¸”à¹€à¸™à¹‡à¸•à¸•à¸­à¸™à¸à¸³à¸¥à¸±à¸‡à¹€à¸¥à¹ˆà¸™ ; à¹„à¸¡à¹ˆà¸™à¸±à¸šà¹€à¸›à¹‡à¸™à¹‚à¸”à¸™à¸šà¸¥à¹‡à¸­à¸ à¹„à¸¡à¹ˆà¸•à¸´à¸”à¸žà¸±à¸)
            n = int(config.get("wg_rotate_logins", 0) or 0)
            if n > 0:
                used = self.__dict__.setdefault("_wg_uses", {})
                used[cur] = used.get(cur, 0) + 1
                if used[cur] >= n:
                    used[cur] = 0
                    self.__dict__.setdefault("_wg_bad", set()).add(cur)
                    try:
                        os.remove(os.path.join(os.path.dirname(cur), ".claims", os.path.basename(cur) + ".lock"))
                    except OSError:
                        pass
                    print(f"[{self.device_id}] [WG] à¹ƒà¸Šà¹‰ {os.path.basename(cur)} à¸„à¸£à¸š {n} à¸£à¸­à¸š - à¸£à¸­à¸šà¸«à¸™à¹‰à¸²à¸ªà¸¥à¸±à¸š IP")

    def _wg_failover(self, conf, confirmed=False):
        """à¹€à¸¥à¸´à¸à¹ƒà¸Šà¹‰à¹„à¸Ÿà¸¥à¹Œà¸™à¸µà¹‰à¸šà¸™à¸ˆà¸­à¸™à¸µà¹‰ (à¸›à¸¥à¹ˆà¸­à¸¢à¸à¸²à¸£à¸ˆà¸­à¸‡) -> à¸£à¸­à¸šà¸«à¸™à¹‰à¸² _wg_conf_for_device à¸ˆà¸°à¸ˆà¸­à¸‡à¹„à¸Ÿà¸¥à¹Œà¸ªà¸³à¸£à¸­à¸‡à¸­à¸±à¸™à¸­à¸·à¹ˆà¸™à¹ƒà¸«à¹‰"""
        if _no_proxy_mode():
            return None   # KILL_VPN: à¹„à¸¡à¹ˆà¸¡à¸µ WG à¹ƒà¸«à¹‰ failover
        if int(config.get("wg_lock", 1) or 0):
            return None   # wg_lock: à¹„à¸¡à¹ˆà¸ªà¸¥à¸±à¸šà¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œ
        # clear sticky lock - IP à¸—à¸µà¹ˆà¹€à¸„à¸¢à¸¢à¸¶à¸”à¹„à¸§à¹‰à¸•à¸­à¸™ login success à¸•à¸­à¸™à¸™à¸µà¹‰ fail -> à¸›à¸¥à¹ˆà¸­à¸¢à¹ƒà¸«à¹‰à¸ªà¸¥à¸±à¸šà¹„à¸”à¹‰
        if getattr(self, "_wg_stuck_conf", None) == conf:
            print(f"[{self.device_id}] [WG] à¸›à¸¥à¸”à¸¥à¹‡à¸­à¸ IP ({os.path.basename(conf)}) - à¸ˆà¸°à¸«à¸²à¹ƒà¸«à¸¡à¹ˆ")
            self._wg_stuck_conf = None
        # sub-folder round-robin: à¸‚à¸¢à¸±à¸š sub -> à¸£à¸­à¸šà¸«à¸™à¹‰à¸²à¹„à¸› sub à¸–à¸±à¸”à¹„à¸› (sync à¸à¸±à¸š login.py)
        if int(config.get("wg_sub_round_robin", 1) or 0):
            cur_idx = getattr(self, "_wg_sub_idx", 0)
            self._wg_sub_idx = cur_idx + 1
            bn = os.path.basename(conf)
            parts = bn.split("__")
            cur_sub = "__".join(parts[:3]) if len(parts) >= 4 else "?"
            print(f"[{self.device_id}] [WG] à¸ªà¸¥à¸±à¸š sub-pool: {cur_sub} -> next (idx {self._wg_sub_idx})")
        self.__dict__.setdefault("_wg_bad", set()).add(conf)
        _wg_cooldown_add(os.path.dirname(conf), _wg_endpoint(conf))
        # à¸¥à¸šà¹„à¸Ÿà¸¥à¹Œ + à¸ˆà¸”à¸§à¹ˆà¸²à¹‚à¸”à¸™à¸šà¸¥à¹‡à¸­à¸ 7 à¸§à¸±à¸™ à¹€à¸‰à¸žà¸²à¸°à¸•à¸­à¸™ "à¸¢à¸·à¸™à¸¢à¸±à¸™à¹à¸¥à¹‰à¸§" (à¸—à¸”à¸ªà¸­à¸šà¸œà¹ˆà¸²à¸™ VPN à¹„à¸”à¹‰ IP à¸ˆà¸£à¸´à¸‡à¹à¸•à¹ˆà¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹€à¸à¸¡à¹„à¸¡à¹ˆà¸•à¸­à¸š)
        # à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¹€à¸‰à¸¢ à¹† à¸­à¸²à¸ˆà¹€à¸›à¹‡à¸™à¹€à¸™à¹‡à¸•à¸à¸£à¸°à¸•à¸¸à¸/à¹„à¸­à¸”à¸µà¹€à¸ªà¸µà¸¢ -> à¹à¸„à¹ˆà¸žà¸±à¸à¹„à¸§à¹‰ (cooldown) à¹„à¸¡à¹ˆà¸¥à¸šà¸—à¸´à¹‰à¸‡
        if confirmed and int(config.get("wg_regen_blocked", 1) or 0):
            _wg_replace_blocked(conf, self.device_id)
        try:
            os.remove(os.path.join(os.path.dirname(conf), ".claims", os.path.basename(conf) + ".lock"))
        except OSError:
            pass
        self._wg_conf_applied = None
        self._wg_conf_written = None
        print(f"[{self.device_id}] [WG] à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸‹à¹‰à¸³à¸šà¸™ {os.path.basename(conf)} - à¸ªà¸¥à¸±à¸šà¹„à¸›à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œ/à¸›à¸£à¸°à¹€à¸—à¸¨à¸­à¸·à¹ˆà¸™")

    def _wg_tuned_conf(self, conf):
        """à¸›à¸£à¸±à¸šà¹„à¸Ÿà¸¥à¹Œà¸à¹ˆà¸­à¸™à¸ªà¹ˆà¸‡à¹€à¸‚à¹‰à¸²à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ (à¹„à¸¡à¹ˆà¹à¸à¹‰à¹„à¸Ÿà¸¥à¹Œà¸•à¹‰à¸™à¸‰à¸šà¸±à¸š):
        - IncludedApplications = à¹€à¸à¸¡  -> à¹ƒà¸«à¹‰à¹€à¸‰à¸žà¸²à¸°à¹€à¸à¸¡à¸œà¹ˆà¸²à¸™ VPN (split tunnel) à¸£à¸°à¸šà¸š/à¹à¸­à¸›à¸­à¸·à¹ˆà¸™à¹ƒà¸Šà¹‰à¹€à¸™à¹‡à¸•à¸›à¸à¸•à¸´
        - PersistentKeepalive = 25    -> à¸ªà¹ˆà¸‡à¸ªà¸±à¸à¸à¸²à¸“à¹€à¸¥à¸µà¹‰à¸¢à¸‡ tunnel à¸à¸±à¸™à¹€à¸£à¸²à¹€à¸•à¸­à¸£à¹Œ/NAT à¸•à¸±à¸”à¸—à¸´à¹‰à¸‡à¸•à¸­à¸™à¹€à¸à¸¡à¹€à¸‡à¸µà¸¢à¸š"""
        try:
            with open(conf, encoding="utf-8-sig") as f:
                lines = f.read().replace(chr(13), "").split(chr(10))
        except Exception:
            return conf
        apps = str(config.get("wg_split_apps", "com.linecorp.LGRGS") or "").strip()   # à¸”à¸µà¸Ÿà¸­à¸¥à¸•à¹Œ = à¹€à¸‰à¸žà¸²à¸°à¹€à¸à¸¡à¸œà¹ˆà¸²à¸™ VPN - à¸–à¹‰à¸²à¸—à¸±à¹‰à¸‡à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸œà¹ˆà¸²à¸™ VPN adbd à¸•à¸­à¸šà¸à¸¥à¸±à¸šà¹„à¸¡à¹ˆà¸–à¸¶à¸‡à¸žà¸µà¸‹à¸µ -> adb offline/not found à¸—à¸¸à¸à¸ˆà¸­ ("" = à¸—à¸±à¹‰à¸‡à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡)
        ka = int(config.get("wg_keepalive", 25) or 0)
        low = [l.strip().lower() for l in lines]
        out = []
        section = ""
        for l in lines:
            s = l.strip().lower()
            if s.startswith("[") and section == "[interface]" and apps and not any(x.startswith("includedapplications") for x in low):
                out.append(f"IncludedApplications = {apps}")
            if s.startswith("["):
                section = s
            out.append(l)
        if ka and not any(x.startswith("persistentkeepalive") for x in low):
            while out and not out[-1].strip():
                out.pop()
            out.append(f"PersistentKeepalive = {ka}")
        tuned = os.path.join(tempfile.gettempdir(), f"wg_tuned_{self.device_id.replace(':', '_')}.conf")
        with open(tuned, "w", encoding="utf-8", newline=chr(10)) as f:
            f.write(chr(10).join(out).rstrip() + chr(10))
        return tuned

    def _wg_is_up(self):
        r = self.adb_shell("ip -o link show 2>/dev/null | grep -E ' tun[0-9]+:' || true", timeout=10)
        return bool((r.stdout or b"").strip())

    def _ensure_wireguard(self):
        """à¸•à¹ˆà¸­ WireGuard à¹ƒà¸™à¸­à¸µà¸¡à¸¹à¸¯ à¸ˆà¸­à¸™à¸µà¹‰ (à¹€à¸£à¸µà¸¢à¸à¸à¹ˆà¸­à¸™à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¸—à¸¸à¸à¸„à¸£à¸±à¹‰à¸‡ - à¸•à¹ˆà¸­à¸­à¸¢à¸¹à¹ˆà¹à¸¥à¹‰à¸§à¸ˆà¸°à¸‚à¹‰à¸²à¸¡à¹€à¸£à¹‡à¸§)"""
        if _no_proxy_mode():
            self._wg_off = True
            return   # KILL_VPN_HARDCODED / no_proxy_mode: à¹ƒà¸Šà¹‰à¹€à¸™à¹‡à¸•à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡/exness VPN - à¹„à¸¡à¹ˆà¸•à¹ˆà¸­ WG à¹ƒà¸™à¸­à¸µà¸¡à¸¹à¸¯
        if int(config.get("use_host_vpn", 0) or 0):
            self._wg_off = True
            return   # host VPN mode: VPN à¸­à¸¢à¸¹à¹ˆà¸™à¸­à¸à¸­à¸µà¸¡à¸¹à¸¯ à¹„à¸¡à¹ˆà¸•à¹ˆà¸­à¹ƒà¸™
        if not int(config.get("wg_enabled", 1) or 0) or getattr(self, "_wg_off", False):
            return
        conf = self._wg_conf_for_device()
        if not conf and not getattr(self, "_wg_down_done", False):
            # à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¹„à¸Ÿà¸¥à¹Œà¸£à¸­à¸šà¸™à¸µà¹‰ à¹à¸•à¹ˆ tunnel à¹€à¸à¹ˆà¸²à¸ˆà¸²à¸à¸£à¸­à¸šà¸à¹ˆà¸­à¸™à¸¢à¸±à¸‡à¸„à¹‰à¸²à¸‡ (à¸­à¸²à¸ˆà¹ƒà¸Šà¹‰à¸à¸¸à¸à¹à¸ˆà¸Šà¸™à¸à¸±à¸šà¸ˆà¸­à¸­à¸·à¹ˆà¸™) -> à¸›à¸´à¸”à¸—à¸´à¹‰à¸‡
            self._wg_down_done = True
            if self._wg_is_up() and not int(config.get("wg_lock", 1) or 0):   # wg_lock: tunnel à¸—à¸µà¹ˆà¹€à¸›à¸´à¸”à¸­à¸¢à¸¹à¹ˆà¸«à¹‰à¸²à¸¡à¸›à¸´à¸”
                self.adb_shell(f"su -c 'am broadcast -f 0x20 -p {self.WG_PKG} "
                               f"-a {self.WG_PKG}.action.SET_TUNNEL_DOWN --es tunnel {self.WG_TUNNEL}'", timeout=20)
                print(f"[{self.device_id}] [WG] à¸›à¸´à¸” tunnel à¹€à¸à¹ˆà¸²à¸—à¸µà¹ˆà¸„à¹‰à¸²à¸‡à¸­à¸¢à¸¹à¹ˆ (à¸ˆà¸­à¸™à¸µà¹‰à¹„à¸¡à¹ˆà¸¡à¸µà¹„à¸Ÿà¸¥à¹Œ config à¸‚à¸­à¸‡à¸•à¸±à¸§à¹€à¸­à¸‡)")
        if not conf:
            if not getattr(self, "_wg_warned", False):
                self._wg_warned = True
                print(f"[{self.device_id}] [WG] à¹„à¸¡à¹ˆà¸¡à¸µà¹„à¸Ÿà¸¥à¹Œ .conf à¹ƒà¸™à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œ {config.get('wg_dir', 'wg')}/ - à¸‚à¹‰à¸²à¸¡ (à¹ƒà¸Šà¹‰à¹€à¸™à¹‡à¸•à¸›à¸à¸•à¸´)")
            return
        if getattr(self, "_wg_conf_applied", None) == conf and self._wg_is_up():
            return
        if getattr(self, "_wg_fail", 0) >= 2:
            return                          # à¸ˆà¸­à¸™à¸µà¹‰à¸•à¹ˆà¸­ VPN à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™à¸¡à¸² 2 à¸£à¸­à¸šà¹à¸¥à¹‰à¸§ - à¹€à¸¥à¸´à¸à¸¥à¸­à¸‡ (à¹„à¸¡à¹ˆà¹€à¸ªà¸µà¸¢à¹€à¸§à¸¥à¸²à¸—à¸¸à¸à¹„à¸­à¸”à¸µ)
        try:
            self._wg_setup(conf)
            if getattr(self, "_wg_conf_applied", None) == conf and int(config.get("wg_probe", 1) or 0):
                # à¸•à¹ˆà¸­à¹à¸¥à¹‰à¸§ -> à¸¢à¸´à¸‡à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹€à¸à¸¡à¸œà¹ˆà¸²à¸™ VPN à¸—à¸±à¸™à¸—à¸µ: à¹„à¸¡à¹ˆà¸•à¸­à¸š/à¸–à¸¹à¸à¸›à¸à¸´à¹€à¸ªà¸˜ = IP à¸™à¸µà¹‰à¹‚à¸”à¸™à¸šà¸¥à¹‡à¸­à¸ -> à¸ªà¸¥à¸±à¸šà¹€à¸¥à¸¢ à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸£à¸­à¹€à¸à¸¡à¸žà¸±à¸‡
                ip, code = self._net_probe()
                # à¸—à¸”à¸ªà¸­à¸šà¹„à¸¡à¹ˆà¹„à¸”à¹‰ (à¹„à¸¡à¹ˆà¸¡à¸µ curl / ip rule à¹ƒà¸Šà¹‰à¹„à¸¡à¹ˆà¹„à¸”à¹‰ -> IP à¹€à¸›à¹‡à¸™ "-") = à¹„à¸¡à¹ˆà¸•à¸±à¸”à¸ªà¸´à¸™ à¸›à¸¥à¹ˆà¸­à¸¢à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡
                # (à¹€à¸”à¸´à¸¡à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸—à¸µà¹ˆà¸—à¸”à¸ªà¸­à¸šà¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸–à¸¹à¸à¸™à¸±à¸šà¸§à¹ˆà¸²à¹‚à¸”à¸™à¸šà¸¥à¹‡à¸­à¸à¸—à¸¸à¸à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œ -> à¸ªà¸¥à¸±à¸šà¸§à¸™à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡à¹€à¸¥à¸¢)
                if code == "NA" or ip in ("-", "", "NA"):
                    print(f"[{self.device_id}] [WG] à¸—à¸”à¸ªà¸­à¸šà¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹€à¸à¸¡à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸šà¸™à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸™à¸µà¹‰ (IP {ip}) - à¸‚à¹‰à¸²à¸¡à¸à¸²à¸£à¸—à¸”à¸ªà¸­à¸š à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡à¹€à¸¥à¸¢")
                    code = "skip"
                if code in ("000", "403", "429") and not int(config.get("wg_lock", 1) or 0):   # wg_lock: à¹‚à¸”à¸™ block à¸à¹‡à¹ƒà¸Šà¹‰à¸•à¹ˆà¸­
                    print(f"[{self.device_id}] [WG] à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹€à¸à¸¡à¹„à¸¡à¹ˆà¸£à¸±à¸š IP {ip} ({os.path.basename(conf)}, code {code}) - à¸ªà¸¥à¸±à¸šà¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œ")
                    self._wg_down()
                    self._wg_failover(conf, confirmed=True)
                    tries = getattr(self, "_wg_probe_tries", 0) + 1
                    self._wg_probe_tries = tries
                    if tries < int(config.get("wg_probe_max", 5)):
                        return self._ensure_wireguard()
                    print(f"[{self.device_id}] [WG] à¸¥à¸­à¸‡à¹à¸¥à¹‰à¸§ {tries} à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸œà¹ˆà¸²à¸™ - à¹€à¸¥à¹ˆà¸™à¸•à¹ˆà¸­à¹à¸šà¸šà¹„à¸¡à¹ˆà¸¡à¸µ VPN à¸£à¸­à¸šà¸™à¸µà¹‰")
                    self._wg_probe_tries = 0
                    return
                self._wg_probe_tries = 0
                print(f"[{self.device_id}] [WG] à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹€à¸à¸¡à¸•à¸­à¸šà¸›à¸à¸•à¸´à¸œà¹ˆà¸²à¸™ IP {ip} (code {code})")
            if getattr(self, "_wg_conf_applied", None) == conf:
                self._wg_fail = 0
            else:
                self._wg_fail = getattr(self, "_wg_fail", 0) + 1
                if self._wg_fail >= 2:
                    print(f"[{self.device_id}] [WG] à¸•à¹ˆà¸­ VPN à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™ 2 à¸£à¸­à¸šà¸•à¸´à¸” - à¸›à¸´à¸” VPN à¸‚à¸­à¸‡à¸ˆà¸­à¸™à¸µà¹‰à¹„à¸›à¸ˆà¸™à¸à¸§à¹ˆà¸²à¸ˆà¸°à¹€à¸›à¸´à¸”à¸šà¸­à¸—à¹ƒà¸«à¸¡à¹ˆ "
                          f"(à¸–à¹‰à¸²à¹€à¸ˆà¸­ 'pm à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¹€à¸ˆà¸­à¹à¸­à¸›' à¸”à¹‰à¸§à¸¢ = MuMu à¸ˆà¸­à¸™à¸µà¹‰à¸„à¹‰à¸²à¸‡ à¹ƒà¸«à¹‰à¸£à¸µà¸ªà¸•à¸²à¸£à¹Œà¸—à¸ˆà¸­)")
        except Exception as e:
            print(f"[{self.device_id}] [WG] à¸•à¹ˆà¸­à¹„à¸¡à¹ˆà¸ªà¸³à¹€à¸£à¹‡à¸ˆ: {e} - à¹€à¸¥à¹ˆà¸™à¸•à¹ˆà¸­à¸”à¹‰à¸§à¸¢à¹€à¸™à¹‡à¸•à¸›à¸à¸•à¸´")

    def _wg_device_is_split(self):
        """tunnel à¸—à¸µà¹ˆà¹€à¸›à¸´à¸”à¸„à¹‰à¸²à¸‡à¹ƒà¸™à¸ˆà¸­à¹€à¸›à¹‡à¸™à¹à¸šà¸š "à¹€à¸‰à¸žà¸²à¸°à¹€à¸à¸¡" à¹„à¸«à¸¡ (à¸¡à¸µ IncludedApplications)
        à¹„à¸Ÿà¸¥à¹Œà¸—à¸µà¹ˆà¹€à¸‚à¸µà¸¢à¸™à¸Šà¹ˆà¸§à¸‡ 4-8 à¸•.à¸„. à¹€à¸›à¹‡à¸™à¹à¸šà¸šà¸—à¸±à¹‰à¸‡à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ -> adbd à¸•à¸­à¸šà¸à¸¥à¸±à¸šà¹„à¸¡à¹ˆà¸–à¸¶à¸‡à¸žà¸µà¸‹à¸µ = adb timeout/offline
        à¸–à¹‰à¸²à¹„à¸¡à¹ˆà¹ƒà¸Šà¹ˆà¹à¸šà¸šà¹€à¸‰à¸žà¸²à¸°à¹€à¸à¸¡ -> à¸„à¸·à¸™ False à¹ƒà¸«à¹‰à¹€à¸‚à¸µà¸¢à¸™à¹„à¸Ÿà¸¥à¹Œà¹ƒà¸«à¸¡à¹ˆà¸—à¸±à¸š (à¸–à¹‰à¸²à¸•à¸±à¹‰à¸‡ wg_split_apps à¹€à¸›à¹‡à¸™ "" = à¸—à¸±à¹‰à¸‡à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¹‚à¸”à¸¢à¸•à¸±à¹‰à¸‡à¹ƒà¸ˆ à¸à¹‡à¸›à¸¥à¹ˆà¸­à¸¢)"""
        if not str(config.get("wg_split_apps", "com.linecorp.LGRGS") or "").strip():
            return True
        try:
            r = self.adb_shell(f"su -c 'grep -c IncludedApplications /data/data/{self.WG_PKG}/files/{self.WG_TUNNEL}.conf'", timeout=10)
            n = int(((r.stdout or b"0").decode(errors="ignore").strip().splitlines() or ["0"])[0] or 0)
        except Exception:
            n = 0
        if n <= 0:
            print(f"[{self.device_id}] [WG] tunnel à¸—à¸µà¹ˆà¹€à¸›à¸´à¸”à¸­à¸¢à¸¹à¹ˆà¹€à¸›à¹‡à¸™à¹à¸šà¸šà¸—à¸±à¹‰à¸‡à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ (à¸—à¸³ adb à¸«à¸¥à¸¸à¸”) - à¹€à¸‚à¸µà¸¢à¸™à¹ƒà¸«à¸¡à¹ˆà¹€à¸›à¹‡à¸™à¹à¸šà¸šà¹€à¸‰à¸žà¸²à¸°à¹€à¸à¸¡")
        return n > 0

    def _wg_must_be_up(self):
        """wg_required (default 1): à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¹„à¸”à¹‰à¹€à¸‰à¸žà¸²à¸°à¸•à¸­à¸™ VPN à¸•à¹ˆà¸­à¸­à¸¢à¸¹à¹ˆ - à¹€à¸™à¹‡à¸•à¸šà¹‰à¸²à¸™à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡à¹„à¸¡à¹ˆà¹„à¸”à¹‰
        à¸¥à¹‰à¸²à¸‡à¸•à¸±à¸§à¸™à¸±à¸šà¸—à¸µà¹ˆà¸—à¸³à¹ƒà¸«à¹‰ _ensure_wireguard à¸¢à¸­à¸¡à¹à¸žà¹‰ (_wg_fail / _wg_off / probe) à¹à¸¥à¹‰à¸§à¸¥à¸­à¸‡à¹ƒà¸«à¸¡à¹ˆà¹€à¸£à¸·à¹ˆà¸­à¸¢ à¹†
        à¸„à¸£à¸š wg_required_tries à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™ -> RestartTimeoutError (clear + à¹€à¸£à¸´à¹ˆà¸¡à¹ƒà¸«à¸¡à¹ˆ) à¹à¸—à¸™à¸à¸²à¸£à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡à¸”à¹‰à¸§à¸¢à¹€à¸™à¹‡à¸•à¸šà¹‰à¸²à¸™"""
        if _no_proxy_mode():
            # KILL_VPN / no_proxy_mode: à¹ƒà¸Šà¹‰ IP à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸•à¸£à¸‡ à¹† - ip_meter_gate à¸à¸±à¸™ cap + login_pace jitter
            _ip_meter_gate()
            _login_pace()
            return
        if int(config.get("use_host_vpn", 0) or 0):
            return   # host VPN mode: VPN à¸­à¸¢à¸¹à¹ˆà¸šà¸™ Windows host - à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¹€à¸Šà¹‡à¸„ tunnel à¹ƒà¸™à¸­à¸µà¸¡à¸¹à¸¯
        if not int(config.get("wg_enabled", 1) or 0):
            return
        if not int(config.get("wg_required", 0) or 0):   # 0 = VPN à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™à¸à¹‡à¹€à¸¥à¹ˆà¸™à¸•à¹ˆà¸­à¸”à¹‰à¸§à¸¢à¹€à¸™à¹‡à¸•à¸šà¹‰à¸²à¸™ (à¹à¸šà¸šà¹€à¸”à¸´à¸¡)
            return self._ensure_wireguard()
        if (int(config.get("wg_once", 1) or 0) and not getattr(self, "_wg_conf_applied", None)
                and not getattr(self, "_wg_started", False) and self._wg_is_up()
                and self._wg_device_is_split()):
            # à¸•à¸­à¸™à¹€à¸£à¸´à¹ˆà¸¡: tunnel à¹€à¸›à¸´à¸”à¹à¸Šà¹ˆà¸­à¸¢à¸¹à¹ˆà¹à¸¥à¹‰à¸§ -> à¹ƒà¸Šà¹‰à¸•à¹ˆà¸­à¹€à¸¥à¸¢ à¸«à¹‰à¸²à¸¡à¸¢à¸¸à¹ˆà¸‡ (à¹„à¸¡à¹ˆà¹€à¸‚à¸µà¸¢à¸™à¹„à¸Ÿà¸¥à¹Œà¹ƒà¸«à¸¡à¹ˆ/à¹„à¸¡à¹ˆà¸›à¸´à¸”à¹€à¸›à¸´à¸”)
            self._wg_started = True
            self._wg_conf_applied = self._wg_conf_for_device() or "(à¹€à¸›à¸´à¸”à¸­à¸¢à¸¹à¹ˆà¹à¸¥à¹‰à¸§)"
            self._wg_last_conf = self._wg_conf_applied if os.path.isfile(str(self._wg_conf_applied)) else None
            print(f"[{self.device_id}] [WG] VPN à¹€à¸›à¸´à¸”à¸­à¸¢à¸¹à¹ˆà¹à¸¥à¹‰à¸§ - à¹ƒà¸Šà¹‰à¸•à¹ˆà¸­ à¹„à¸¡à¹ˆà¸¢à¸¸à¹ˆà¸‡")
            return
        if (int(config.get("wg_once", 1) or 0) and getattr(self, "_wg_started", False)
                and getattr(self, "_wg_conf_applied", None) and self._wg_is_up()):
            return                          # à¹€à¸›à¸´à¸”à¹à¸Šà¹ˆà¸­à¸¢à¸¹à¹ˆ -> à¸«à¹‰à¸²à¸¡à¸¢à¸¸à¹ˆà¸‡ (à¹à¸¡à¹‰à¹„à¸Ÿà¸¥à¹Œà¹ƒà¸™ wg/ à¸–à¸¹à¸à¸ªà¸£à¹‰à¸²à¸‡à¹ƒà¸«à¸¡à¹ˆà¸•à¸²à¸¡à¸£à¸­à¸šà¹à¸¥à¹‰à¸§à¸à¹‡à¸•à¸²à¸¡)
        self._wg_started = True
        tries = int(config.get("wg_required_tries", 10) or 10)
        for n in range(1, tries + 1):
            self._wg_off = False
            self._wg_fail = 0
            self._wg_probe_tries = 0
            self.last_activity_time = time.time()
            self._ensure_wireguard()
            if getattr(self, "_wg_conf_applied", None) and self._wg_is_up():
                return
            _c = self._wg_conf_for_device()
            _why = ("à¹„à¸¡à¹ˆà¸¡à¸µà¹„à¸Ÿà¸¥à¹Œ .conf à¹ƒà¸™ " + str(config.get("wg_dir", "wg")) + "/") if not _c else ("à¹ƒà¸Šà¹‰ " + os.path.basename(_c) + " à¹à¸•à¹ˆ tunnel à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™")
            print(f"[{self.device_id}] [WG] VPN à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™ ({n}/{tries}) - {_why} - à¸¥à¸­à¸‡à¹ƒà¸«à¸¡à¹ˆ...")
            if _c:
                self.__dict__.setdefault("_wg_bad", set()).add(_c)
                self._wg_rand_conf = None
                # sub-round-robin: VPN à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™ 2 à¸£à¸­à¸š -> à¸‚à¸¢à¸±à¸š sub-pool
                if int(config.get("wg_sub_round_robin", 1) or 0) and n >= 2:
                    cur_idx = getattr(self, "_wg_sub_idx", 0)
                    self._wg_sub_idx = cur_idx + 1
                    print(f"[{self.device_id}] [WG] VPN à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™ {n} à¸£à¸­à¸š -> à¸ªà¸¥à¸±à¸š sub-pool (idx {self._wg_sub_idx})")
            else:
                self._wg_bad = set()        # à¹ƒà¸«à¹‰à¸§à¸™à¸à¸¥à¸±à¸šà¹„à¸›à¸¥à¸­à¸‡à¸—à¸¸à¸à¹€à¸‹à¸´à¸£à¹Œà¸Ÿà¹€à¸§à¸­à¸£à¹Œà¹„à¸”à¹‰à¸­à¸µà¸
            _real_sleep(5)
        print(f"[{self.device_id}] [WG] à¸•à¹ˆà¸­ VPN à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™ {tries} à¸£à¸­à¸š - à¸£à¸µà¸ªà¸•à¸²à¸£à¹Œà¸—à¹„à¸Ÿà¸¥à¹Œà¸™à¸µà¹‰à¹à¸—à¸™à¸à¸²à¸£à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡à¸”à¹‰à¸§à¸¢à¹€à¸™à¹‡à¸•à¸šà¹‰à¸²à¸™")
        raise RestartTimeoutError("wg_required: VPN not up")

    def _wg_setup(self, conf):
        if _no_proxy_mode():
            return   # KILL_VPN: à¹„à¸¡à¹ˆà¸•à¹ˆà¸­ WG à¹ƒà¸” à¹†
        pkg, name = self.WG_PKG, self.WG_TUNNEL
        # à¸—à¸²à¸‡à¸¥à¸±à¸”: à¹„à¸Ÿà¸¥à¹Œ config à¸™à¸µà¹‰à¹€à¸„à¸¢à¹€à¸‚à¸µà¸¢à¸™à¸¥à¸‡à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¹à¸¥à¹‰à¸§ (à¹à¸„à¹ˆà¸›à¸´à¸”à¹„à¸›à¸•à¸­à¸™à¸ªà¹ˆà¸‡à¹„à¸Ÿà¸¥à¹Œ) -> à¸ªà¸±à¹ˆà¸‡à¹€à¸›à¸´à¸” tunnel à¸­à¸¢à¹ˆà¸²à¸‡à¹€à¸”à¸µà¸¢à¸§ à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸ªà¹ˆà¸‡à¹„à¸Ÿà¸¥à¹Œà¹ƒà¸«à¸¡à¹ˆ
        # (à¹€à¸—à¸µà¸¢à¸šà¹€à¸§à¸¥à¸²à¹à¸à¹‰à¹„à¸Ÿà¸¥à¹Œà¸”à¹‰à¸§à¸¢ - server à¸ªà¹ˆà¸‡à¹„à¸Ÿà¸¥à¹Œà¸Šà¸·à¹ˆà¸­à¹€à¸”à¸´à¸¡à¹à¸•à¹ˆà¹€à¸™à¸·à¹‰à¸­à¸«à¸²à¹ƒà¸«à¸¡à¹ˆà¸¡à¸² à¸•à¹‰à¸­à¸‡à¹€à¸‚à¸µà¸¢à¸™à¸¥à¸‡à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¹ƒà¸«à¸¡à¹ˆ)
        if getattr(self, "_wg_conf_written", None) == (conf, os.path.getmtime(conf)):
            self.adb_shell(f"su -c 'am broadcast -f 0x20 -p {pkg} -a {pkg}.action.SET_TUNNEL_UP --es tunnel {name}'",
                           timeout=20)
            for _ in range(8):
                _real_sleep(0.5)
                if self._wg_is_up():
                    self._wg_conf_applied = conf
                    print(f"[{self.device_id}] [WG] à¸•à¹ˆà¸­ VPN à¹à¸¥à¹‰à¸§ ({os.path.basename(conf)})")
                    return
            self._wg_conf_written = None    # à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™ -> à¸£à¸­à¸šà¸™à¸µà¹‰à¸—à¸³à¹à¸šà¸šà¹€à¸•à¹‡à¸¡à¸•à¹ˆà¸­à¹€à¸¥à¸¢
        # 1) à¸¥à¸‡à¹à¸­à¸› WireGuard à¸–à¹‰à¸²à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸¡à¸µ - à¹€à¸Šà¹‡à¸„à¸ˆà¸²à¸à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¹à¸­à¸›à¹ƒà¸™à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ (à¹„à¸¡à¹ˆà¸žà¸¶à¹ˆà¸‡ pm à¸—à¸µà¹ˆà¸•à¸­à¸šà¸Šà¹‰à¸²à¸•à¸­à¸™à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¹‚à¸«à¸¥à¸”à¸«à¸™à¸±à¸)
        #    à¹€à¸„à¸¢à¹€à¸ˆà¸­: pm à¸•à¸­à¸šà¹„à¸¡à¹ˆà¸—à¸±à¸™ -> à¸™à¸¶à¸à¸§à¹ˆà¸²à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸¥à¸‡ -> à¸•à¸´à¸”à¸•à¸±à¹‰à¸‡ 17 MB à¸‹à¹‰à¸³à¸—à¸¸à¸à¸ˆà¸­à¸—à¸¸à¸à¸£à¸­à¸š -> pm à¸¢à¸´à¹ˆà¸‡à¸Šà¹‰à¸² à¸«à¸²à¹à¸¡à¹‰à¹à¸•à¹ˆà¸•à¸±à¸§à¹€à¸à¸¡à¹„à¸¡à¹ˆà¹€à¸ˆà¸­
        if not getattr(self, "_wg_installed", False):
            r = self.adb_shell(f"su -c 'test -d /data/data/{pkg} && echo YES'", timeout=15)
            if b"YES" in (r.stdout or b""):
                self._wg_installed = True
            elif getattr(self, "_wg_install_tried", False):
                print(f"[{self.device_id}] [WG] à¸•à¸´à¸”à¸•à¸±à¹‰à¸‡ WireGuard à¹„à¸›à¹à¸¥à¹‰à¸§à¸£à¸­à¸šà¸™à¸µà¹‰à¹à¸•à¹ˆà¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¹€à¸«à¹‡à¸™à¹à¸­à¸› - à¹„à¸¡à¹ˆà¸•à¸´à¸”à¸•à¸±à¹‰à¸‡à¸‹à¹‰à¸³ (à¸‚à¹‰à¸²à¸¡ VPN à¸‚à¸­à¸‡à¸ˆà¸­à¸™à¸µà¹‰à¹„à¸›à¸à¹ˆà¸­à¸™)")
                return
            else:
                apk = _wg_apk_path()
                if not apk:
                    print(f"[{self.device_id}] [WG] à¹„à¸¡à¹ˆà¸¡à¸µà¹„à¸Ÿà¸¥à¹Œà¹à¸­à¸› WireGuard (à¹‚à¸«à¸¥à¸”à¹„à¸¡à¹ˆà¹„à¸”à¹‰) - à¸‚à¹‰à¸²à¸¡")
                    return
                self._wg_install_tried = True
                print(f"[{self.device_id}] [WG] à¸•à¸´à¸”à¸•à¸±à¹‰à¸‡à¹à¸­à¸› WireGuard (à¸„à¸£à¸±à¹‰à¸‡à¹€à¸”à¸µà¸¢à¸§)...")
                self.adb_run([self.adb_cmd, "-s", self.device_id, "install", "-r", apk], timeout=180)
                r = self.adb_shell(f"su -c 'test -d /data/data/{pkg} && echo YES'", timeout=15)
                self._wg_installed = b"YES" in (r.stdout or b"")

        # 2) à¹€à¸‚à¸µà¸¢à¸™à¹„à¸Ÿà¸¥à¹Œ tunnel + à¸•à¸±à¹‰à¸‡à¸„à¹ˆà¸²à¹à¸­à¸› (à¸•à¹‰à¸­à¸‡à¸›à¸´à¸”à¹à¸­à¸›à¸à¹ˆà¸­à¸™ à¹„à¸¡à¹ˆà¸‡à¸±à¹‰à¸™à¸¡à¸±à¸™à¹€à¸‚à¸µà¸¢à¸™à¸—à¸±à¸š)
        self.adb_shell(f"am force-stop {pkg}")
        safe_dev = self.device_id.replace(":", "_")
        tmp_conf = f"/data/local/tmp/wg_{safe_dev}.conf"
        tmp_pb = f"/data/local/tmp/wg_{safe_dev}.pb"
        local_pb = os.path.join(tempfile.gettempdir(), f"wg_{safe_dev}.pb")
        # DataStore (protobuf) à¸‚à¸­à¸‡à¹à¸­à¸›: allow_remote_control_intents = true
        key = b"allow_remote_control_intents"
        entry = b"\x0a" + bytes([len(key)]) + key + b"\x12\x02\x08\x01"
        with open(local_pb, "wb") as f:
            f.write(b"\x0a" + bytes([len(entry)]) + entry)
        # à¸„à¸³à¸ªà¸±à¹ˆà¸‡ root à¹€à¸‚à¸µà¸¢à¸™à¹€à¸›à¹‡à¸™à¸ªà¸„à¸£à¸´à¸›à¸•à¹Œà¹à¸¥à¹‰à¸§à¸£à¸±à¸™à¸—à¸µà¹€à¸”à¸µà¸¢à¸§ - su à¸‚à¸­à¸‡ MuMu à¸à¸´à¸™ $ / quote à¸–à¹‰à¸²à¸ªà¹ˆà¸‡à¹€à¸›à¹‡à¸™à¸ªà¸•à¸£à¸´à¸‡à¸•à¸£à¸‡ à¹†
        d = f"/data/data/{pkg}"
        tmp_sh = f"/data/local/tmp/wg_{safe_dev}.sh"
        local_sh = os.path.join(tempfile.gettempdir(), f"wg_{safe_dev}.sh")
        script = chr(10).join([
            f"mkdir -p {d}/files/datastore",
            f"cp {tmp_conf} {d}/files/{name}.conf",
            f"cp {tmp_pb} {d}/files/datastore/settings.preferences_pb",
            f"U=$(stat -c %u {d})",
            f"chown -R $U:$U {d}/files",
            f"chmod -R 700 {d}/files",
            f"restorecon -R {d}/files 2>/dev/null",
            f"rm -f {tmp_conf} {tmp_pb}",
            # à¸­à¸™à¸¸à¸à¸²à¸•à¸ªà¸£à¹‰à¸²à¸‡ VPN à¸¥à¹ˆà¸§à¸‡à¸«à¸™à¹‰à¸² (à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸à¸”à¸¢à¸·à¸™à¸¢à¸±à¸™à¸šà¸™à¸ˆà¸­)
            f"cmd appops set {pkg} ACTIVATE_VPN allow",
            # Android 12 à¸«à¹‰à¸²à¸¡à¹à¸­à¸›à¹€à¸›à¸´à¸” VpnService à¸ˆà¸²à¸à¹€à¸šà¸·à¹‰à¸­à¸‡à¸«à¸¥à¸±à¸‡ -> à¹ƒà¸ªà¹ˆà¹„à¸§à¹‰à¹ƒà¸™à¸£à¸²à¸¢à¸à¸²à¸£à¸¢à¸à¹€à¸§à¹‰à¸™à¸›à¸£à¸°à¸«à¸¢à¸±à¸”à¹à¸šà¸• (à¸—à¸”à¸ªà¸­à¸šà¸šà¸™ MuMu à¹à¸¥à¹‰à¸§à¸œà¹ˆà¸²à¸™)
            f"cmd deviceidle whitelist +{pkg}",
            # à¸ªà¸±à¹ˆà¸‡à¹€à¸›à¸´à¸” tunnel à¹€à¸›à¹‡à¸™ root (à¸œà¹ˆà¸²à¸™à¸ªà¸´à¸—à¸˜à¸´à¹Œ CONTROL_TUNNELS) ; -f 0x20 = à¸ªà¹ˆà¸‡à¸–à¸¶à¸‡à¹à¸­à¸›à¸—à¸µà¹ˆà¸–à¸¹à¸ force-stop
            f"am broadcast -f 0x20 -p {pkg} -a {pkg}.action.SET_TUNNEL_UP --es tunnel {name}",
            f"rm -f {tmp_sh}",
            "",
        ])
        with open(local_sh, "w", newline=chr(10)) as f:   # à¹„à¸Ÿà¸¥à¹Œ sh à¸•à¹‰à¸­à¸‡à¹€à¸›à¹‡à¸™ LF
            f.write(script)
        self._wg_last_conf = conf
        for src, dst in ((self._wg_tuned_conf(conf), tmp_conf), (local_pb, tmp_pb), (local_sh, tmp_sh)):
            self.adb_run([self.adb_cmd, "-s", self.device_id, "push", src, dst], timeout=30)
        self.adb_shell(f"su -c 'sh {tmp_sh}'", timeout=30)   # à¸•à¹‰à¸­à¸‡à¸„à¸£à¸­à¸š quote: su à¸‚à¸­à¸‡ MuMu à¸£à¸±à¸šà¹à¸„à¹ˆà¸„à¸³à¸–à¸±à¸”à¹„à¸›à¸„à¸³à¹€à¸”à¸µà¸¢à¸§
        for _ in range(10):
            _real_sleep(1)
            if self._wg_is_up():
                self._wg_conf_applied = conf
                self._wg_conf_written = (conf, os.path.getmtime(conf))
                print(f"[{self.device_id}] [WG] à¸•à¹ˆà¸­ VPN à¹à¸¥à¹‰à¸§ ({os.path.basename(conf)})")
                return
        print(f"[{self.device_id}] [WG] à¸ªà¸±à¹ˆà¸‡à¸•à¹ˆà¸­à¹à¸¥à¹‰à¸§à¹à¸•à¹ˆà¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¹€à¸«à¹‡à¸™ tunnel à¸ à¸²à¸¢à¹ƒà¸™ 10 à¸§à¸´ ({os.path.basename(conf)})")

    def open_app(self):
        """à¹€à¸›à¸´à¸”à¹à¸­à¸› LINE Rangers à¸”à¹‰à¸§à¸¢à¸„à¸³à¸ªà¸±à¹ˆà¸‡ am start / monkey (à¹€à¸£à¹‡à¸§à¸à¸§à¹ˆà¸²à¸„à¸¥à¸´à¸ icon.png)"""
        self.last_activity_time = time.time()
        # KILL_VPN mode: à¸›à¸´à¸” WireGuard app + à¸¥à¸š tunnel config à¸šà¸™ emulator à¸à¹ˆà¸­à¸™
        # (à¸šà¸²à¸‡à¸ˆà¸­ WG app à¹€à¸›à¸´à¸”à¸„à¹‰à¸²à¸‡ popup à¸—à¸±à¸šà¹€à¸à¸¡ + tunnel 'lgr' à¸¢à¸±à¸‡ config à¸„à¹‰à¸²à¸‡)
        if _no_proxy_mode():
            self._force_kill_wg_on_emu()
        elif int(config.get("wg_after_login", 0) or 0):
            self._wg_down()          # wg_after_login: à¸ªà¹ˆà¸‡à¹„à¸Ÿà¸¥à¹Œ+à¸¥à¹‡à¸­à¸à¸­à¸´à¸™à¸”à¹‰à¸§à¸¢à¹€à¸™à¹‡à¸•à¸›à¸à¸•à¸´ à¹à¸¥à¹‰à¸§à¸„à¹ˆà¸­à¸¢à¸•à¹ˆà¸­ VPN à¸«à¸¥à¸±à¸‡à¹€à¸‚à¹‰à¸²à¹€à¸à¸¡
        else:
            self._wg_must_be_up()    # wg_enabled: à¸•à¹ˆà¸­ VPN à¹à¸¢à¸à¸‚à¸­à¸‡à¸ˆà¸­à¸™à¸µà¹‰ (IP à¹„à¸¡à¹ˆà¸‹à¹‰à¸³à¸ˆà¸­à¸­à¸·à¹ˆà¸™) - à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™à¸«à¹‰à¸²à¸¡à¹€à¸›à¸´à¸”à¹€à¸à¸¡
        attempt = 0
        while attempt < 5:
            attempt += 1
            try:
                if attempt % 2 == 1:
                    self.adb_run([
                        self.adb_cmd, "-s", self.device_id, "shell",
                        "am", "start", "-S", "-n",
                        "com.linecorp.LGRGS/com.linecorp.common.activity.LineActivity"
                    ], timeout=10)
                else:
                    self.adb_run([
                        self.adb_cmd, "-s", self.device_id, "shell",
                        "monkey", "-p", "com.linecorp.LGRGS",
                        "-c", "android.intent.category.LAUNCHER", "1"
                    ], timeout=10)
                
                sleep(1)
                
                try:
                    pid_result = subprocess.run(
                        [self.adb_cmd, "-s", self.device_id, "shell", "pidof", "com.linecorp.LGRGS"],
                        capture_output=True, text=True, timeout=5
                    )
                    pid = pid_result.stdout.strip()
                except Exception:
                    pid = ""
                
                if pid:
                    print(f"[{self.device_id}] âœ“ App running (PID: {pid}) - attempt {attempt}")
                    return True
                else:
                    print(f"[{self.device_id}] âœ— App crashed/bounced! (attempt {attempt}) Retrying...")
                    sleep(0.5)
                    
            except Exception as e:
                sleep(0.5)
        
        print(f"[{self.device_id}] Failed to open app after 5 attempts!")
        return False

    def _signal_ready(self):
        """à¸šà¸­à¸à¸•à¸±à¸§à¸›à¸¥à¹ˆà¸­à¸¢à¸šà¸­à¸—à¸§à¹ˆà¸²à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸™à¸µà¹‰à¸žà¸£à¹‰à¸­à¸¡à¹à¸¥à¹‰à¸§ à¹€à¸žà¸·à¹ˆà¸­à¹ƒà¸«à¹‰à¸›à¸¥à¹ˆà¸­à¸¢à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸–à¸±à¸”à¹„à¸›à¹„à¸”à¹‰à¸—à¸±à¸™à¸—à¸µ

        à¹ƒà¸Šà¹‰à¸à¸²à¸£à¸ˆà¸±à¸šà¸ˆà¸­à¸£à¸­à¸šà¹à¸£à¸à¹€à¸›à¹‡à¸™à¸•à¸±à¸§à¸§à¸±à¸”: à¸œà¹ˆà¸²à¸™à¹à¸¥à¹‰à¸§à¹à¸›à¸¥à¸§à¹ˆà¸² adb à¸•à¹ˆà¸­à¸•à¸´à¸”à¹à¸¥à¸°à¸‡à¸²à¸™à¸«à¸™à¸±à¸à¸•à¸­à¸™
        à¸ªà¸•à¸²à¸£à¹Œà¸• (import / à¸•à¹ˆà¸­ adb / à¸ˆà¸±à¸šà¸ˆà¸­) à¸ˆà¸šà¸ˆà¸£à¸´à¸‡ à¹„à¸¡à¹ˆà¹ƒà¸Šà¹ˆà¹€à¸”à¸²à¹€à¸­à¸²à¸ˆà¸²à¸à¸™à¸²à¸¬à¸´à¸à¸²
        """
        q = getattr(self, "_ready_q", None)
        if q is None:
            return
        self._ready_q = None          # à¸ªà¹ˆà¸‡à¸„à¸£à¸±à¹‰à¸‡à¹€à¸”à¸µà¸¢à¸§à¸žà¸­
        try:
            self.capture_screen()
        except Exception:
            pass
        try:
            q.put(self.device_id)
        except Exception:
            pass

    def run(self):
        print(f"[{self.device_id}] RangerGear Bot Thread Started", flush=True)
        self._signal_ready()   # à¸žà¸£à¹‰à¸­à¸¡à¹à¸¥à¹‰à¸§ -> à¸›à¸¥à¹ˆà¸­à¸¢à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸–à¸±à¸”à¹„à¸›à¹„à¸”à¹‰à¹€à¸¥à¸¢
        # à¹€à¸”à¸´à¸¡ try à¸„à¸£à¸­à¸š while True à¹„à¸§à¹‰à¸—à¸±à¹‰à¸‡à¸à¹‰à¸­à¸™ = à¸žà¸±à¸‡à¸„à¸£à¸±à¹‰à¸‡à¹€à¸”à¸µà¸¢à¸§ thread à¸•à¸²à¸¢à¸–à¸²à¸§à¸£
        # à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸™à¸±à¹‰à¸™à¹€à¸‡à¸µà¸¢à¸šà¹„à¸›à¹€à¸¥à¸¢à¸—à¸±à¹‰à¸‡à¸—à¸µà¹ˆà¹‚à¸›à¸£à¹à¸à¸£à¸¡à¸¢à¸±à¸‡à¹€à¸›à¸´à¸”à¸­à¸¢à¸¹à¹ˆ à¸•à¸­à¸™à¸™à¸µà¹‰à¹à¸¢à¸à¸¥à¸¹à¸›à¸­à¸­à¸à¸¡à¸²à¹à¸¥à¹‰à¸§
        # supervise à¹ƒà¸«à¹‰à¸à¸¥à¸±à¸šà¸¡à¸²à¹€à¸”à¸´à¸™à¸•à¹ˆà¸­à¹€à¸­à¸‡à¹„à¸”à¹‰
        crash_count = 0
        while getattr(self, "_running", True):
            try:
                self._main_loop()
                crash_count = 0   # loop à¸ˆà¸šà¹€à¸­à¸‡ (à¹€à¸Šà¹ˆà¸™ à¸„à¸´à¸§à¸«à¸¡à¸”) - reset
            except Exception as e:
                crash_count += 1
                print(f"[{self.device_id}] Thread Crash #{crash_count}: {e} - recover", flush=True)
                traceback.print_exc()
                # recover: reconnect ADB + à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸š device à¸à¹ˆà¸­à¸™à¹€à¸‚à¹‰à¸² loop à¹ƒà¸«à¸¡à¹ˆ
                # (à¹€à¸„à¸ªà¸«à¸¥à¸±à¸‡ VPN swap: ADB/MuMu à¸­à¸²à¸ˆà¸„à¹‰à¸²à¸‡ thread à¸•à¸²à¸¢ à¸•à¹‰à¸­à¸‡à¸›à¸¥à¸¸à¸ device à¸à¹ˆà¸­à¸™)
                try:
                    self._adb_recover_device()
                except Exception as rec_e:
                    print(f"[{self.device_id}] ADB recover failed: {rec_e}", flush=True)
                # exponential backoff à¸–à¹‰à¸² crash à¸‹à¹‰à¸³ à¹† (à¸à¸±à¸™ loop à¸žà¸±à¸‡à¸•à¸¥à¸­à¸”)
                delay = min(60, 5 * (2 ** min(crash_count - 1, 4)))   # 5, 10, 20, 40, 60, 60...
                sleep(delay)

    def _adb_recover_device(self):
        """à¸›à¸¥à¸¸à¸ ADB device à¸—à¸µà¹ˆà¸«à¸¥à¸¸à¸”/offline (à¸«à¸¥à¸±à¸‡ VPN swap / emulator sleep / timeout)
        - adb disconnect + reconnect
        - restart-server à¸–à¹‰à¸² device status 'offline'"""
        dev = self.device_id
        # à¹„à¸¡à¹ˆà¹ƒà¸Šà¹ˆ TCP device (emulator-xxxx) -> à¹„à¸¡à¹ˆà¸¡à¸µà¸­à¸°à¹„à¸£à¹ƒà¸«à¹‰ reconnect
        if ":" not in dev:
            return
        print(f"[{dev}] [RECOVER] adb reconnect...", flush=True)
        try:
            subprocess.run([adb_path, "disconnect", dev], capture_output=True, timeout=10)
        except Exception:
            pass
        try:
            r = subprocess.run([adb_path, "connect", dev], capture_output=True, text=True, timeout=10)
            print(f"[{dev}] [RECOVER] {(r.stdout or '').strip()[:80]}", flush=True)
        except Exception as e:
            print(f"[{dev}] [RECOVER] connect error: {e}", flush=True)
        # à¹€à¸Šà¹‡à¸„ device state - à¸–à¹‰à¸²à¸¢à¸±à¸‡ offline à¸¥à¸­à¸‡ restart ADB server
        try:
            r = subprocess.run([adb_path, "-s", dev, "get-state"], capture_output=True, text=True, timeout=10)
            state = (r.stdout or "").strip()
            if state != "device":
                print(f"[{dev}] [RECOVER] state={state} -> restart ADB server", flush=True)
                subprocess.run([adb_path, "kill-server"], capture_output=True, timeout=15)
                sleep(2)
                subprocess.run([adb_path, "start-server"], capture_output=True, timeout=15)
                sleep(2)
                subprocess.run([adb_path, "connect", dev], capture_output=True, timeout=10)
        except Exception as e:
            print(f"[{dev}] [RECOVER] state check error: {e}", flush=True)

    # à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸„à¸´à¸§à¸—à¸µà¹ˆà¸¢à¸­à¸¡à¸«à¸¢à¸´à¸šà¹„à¸Ÿà¸¥à¹Œà¸¡à¸²à¸—à¸³ = backup/ à¹€à¸—à¹ˆà¸²à¸™à¸±à¹‰à¸™ (à¸•à¸±à¹‰à¸‡à¸—à¸±à¸šà¹„à¸”à¹‰à¹ƒà¸™ config "queue_folders"
    # à¹à¸•à¹ˆà¸„à¹ˆà¸²à¹€à¸£à¸´à¹ˆà¸¡à¸•à¹‰à¸™à¸ˆà¸‡à¹ƒà¸ˆà¹„à¸¡à¹ˆà¹à¸•à¸° input-id/ à¸—à¸µà¹ˆ loginà¸ªà¸°à¸ªà¸¡à¹ƒà¸Šà¹‰ à¸à¸±à¸™à¸ªà¸­à¸‡à¹‚à¸›à¸£à¹à¸à¸£à¸¡à¹à¸¢à¹ˆà¸‡à¹„à¸Ÿà¸¥à¹Œà¸à¸±à¸™)
    # à¹€à¸œà¸·à¹ˆà¸­à¸­à¸¢à¸²à¸à¹ƒà¸«à¹‰à¸”à¸¶à¸‡à¸ˆà¸²à¸ input-id/ à¸—à¸µà¹ˆ loginà¸ªà¸°à¸ªà¸¡ (login.py) à¹ƒà¸Šà¹‰à¸£à¹ˆà¸§à¸¡à¸”à¹‰à¸§à¸¢
    QUEUE_FOLDERS_DEFAULT = ["backup"]
    # à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸—à¸µà¹ˆà¹„à¸¡à¹ˆà¹ƒà¸Šà¹ˆà¸„à¸´à¸§ à¹à¸•à¹ˆà¸¡à¸±à¸à¸¡à¸µà¹„à¸Ÿà¸¥à¹Œà¸„à¹‰à¸²à¸‡ - à¹ƒà¸Šà¹‰à¸šà¸­à¸à¹ƒà¸™ log à¸•à¸­à¸™à¸§à¹ˆà¸²à¸‡à¸‡à¸²à¸™à¸§à¹ˆà¸²à¹„à¸Ÿà¸¥à¹Œà¹„à¸›à¸à¸­à¸‡à¸­à¸¢à¸¹à¹ˆà¹„à¸«à¸™
    OTHER_FOLDERS = ["backup", "input-id", "input", "backup-xml", "login-success", "login-failed"]

    def _queue_folders(self):
        folders = config.get("queue_folders") or self.QUEUE_FOLDERS_DEFAULT
        if isinstance(folders, str):
            folders = [folders]
        return [str(f) for f in folders]

    @staticmethod
    def _count_xml(folder):
        n = 0
        if os.path.isdir(folder):
            for _r, _d, _fs in os.walk(folder):
                n += sum(1 for f in _fs if f.lower().endswith(".xml"))
        return n

    def _report_idle_queue(self, every_sec=30):
        """à¸šà¸­à¸à¸ªà¸²à¹€à¸«à¸•à¸¸à¸—à¸µà¹ˆà¹„à¸¡à¹ˆà¸¡à¸µà¸‡à¸²à¸™à¸—à¸³

        à¹€à¸”à¸´à¸¡à¸•à¸­à¸™à¸„à¸´à¸§à¸§à¹ˆà¸²à¸‡ log à¸¡à¸µà¹à¸•à¹ˆ [CONFIG] Base Loaded à¸§à¸´à¸™à¸²à¸—à¸µà¸¥à¸°à¸šà¸£à¸£à¸—à¸±à¸” à¹à¸¢à¸à¹„à¸¡à¹ˆà¸­à¸­à¸à¸§à¹ˆà¸²
        à¸„à¸´à¸§à¸«à¸¡à¸”à¸ˆà¸£à¸´à¸‡ à¹„à¸Ÿà¸¥à¹Œà¸•à¸´à¸” lock à¸„à¹‰à¸²à¸‡ à¸«à¸£à¸·à¸­à¹„à¸Ÿà¸¥à¹Œà¹„à¸›à¸à¸­à¸‡à¸­à¸¢à¸¹à¹ˆà¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸—à¸µà¹ˆà¸ªà¸„à¸£à¸´à¸›à¸•à¹Œà¸™à¸µà¹‰à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸­à¹ˆà¸²à¸™
        """
        now = time.time()
        if now - getattr(self, "_idle_logged_at", 0) < every_sec:
            return
        self._idle_logged_at = now
        total, locked = getattr(self, "_queue_stats", (0, 0))
        qnames = " + ".join(f + "/" for f in self._queue_folders())
        if total:
            print(f"[{self.device_id}] [QUEUE] à¸§à¹ˆà¸²à¸‡à¸‡à¸²à¸™: à¹€à¸ˆà¸­ {total} à¹„à¸Ÿà¸¥à¹Œà¹ƒà¸™ {qnames} "
                  f"à¹à¸•à¹ˆà¸•à¸´à¸” lock à¸­à¸¢à¸¹à¹ˆ {locked} à¹„à¸Ÿà¸¥à¹Œ (à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸­à¸·à¹ˆà¸™à¸–à¸·à¸­à¸­à¸¢à¸¹à¹ˆ à¸«à¸£à¸·à¸­ lock à¸„à¹‰à¸²à¸‡)")
            return
        # à¸„à¸´à¸§à¸«à¸¡à¸”à¸ˆà¸£à¸´à¸‡ - à¸šà¸­à¸à¸”à¹‰à¸§à¸¢à¸§à¹ˆà¸²à¹„à¸Ÿà¸¥à¹Œà¸—à¸µà¹ˆà¸¢à¸±à¸‡à¹€à¸«à¸¥à¸·à¸­à¹ƒà¸™à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¹„à¸›à¸à¸­à¸‡à¸­à¸¢à¸¹à¹ˆà¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¹„à¸«à¸™
        script_dir = os.path.dirname(os.path.abspath(__file__))
        queue_set = set(self._queue_folders())
        elsewhere = []
        for name in self.OTHER_FOLDERS:
            if name in queue_set:
                continue
            n = self._count_xml(os.path.join(script_dir, name))
            if n:
                elsewhere.append(f"{name}/={n}")
        msg = f"[{self.device_id}] [QUEUE] à¸§à¹ˆà¸²à¸‡à¸‡à¸²à¸™: à¹„à¸¡à¹ˆà¸¡à¸µà¹„à¸Ÿà¸¥à¹Œ .xml à¹€à¸«à¸¥à¸·à¸­à¹ƒà¸™ {qnames}"
        if elsewhere:
            msg += (f" | à¹„à¸Ÿà¸¥à¹Œà¸—à¸µà¹ˆà¸¢à¸±à¸‡à¹€à¸«à¸¥à¸·à¸­à¹„à¸›à¸à¸­à¸‡à¸­à¸¢à¸¹à¹ˆà¸—à¸µà¹ˆ {', '.join(elsewhere)}"
                    f" - à¸–à¹‰à¸²à¸­à¸¢à¸²à¸à¹ƒà¸«à¹‰à¸”à¸¶à¸‡à¸¡à¸²à¸—à¸³à¸”à¹‰à¸§à¸¢ à¹ƒà¸ªà¹ˆà¸Šà¸·à¹ˆà¸­à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¹ƒà¸™ config \"queue_folders\"")
        print(msg)


    def _main_loop(self):
            while True:
                # 0. Check if background monitor triggered a restart
                if self._need_restart:
                    print(f"[{self.device_id}] Main loop detected restart request from monitor.")
                    self._need_restart = False
                    # No need to release lock yet if we haven't started processing, 
                    # but if we have a file, we should probably keep it and just restart the logic.
                    # For simplicity, we just continue which will pick up next or same file.

                # 0. Reload Config (à¹€à¸‡à¸µà¸¢à¸š - à¸žà¸´à¸¡à¸žà¹Œà¹€à¸‰à¸žà¸²à¸°à¸•à¸­à¸™à¸„à¹ˆà¸²à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™à¸ˆà¸£à¸´à¸‡)
                load_config(quiet=True)
                self.do_ranger = config.get("find_ranger", 0) or config.get("find_all", 1)
                self.do_gear = config.get("find_gear", 0) or config.get("find_all", 1)
                self.do_ruby_ticket = config.get("check_ruby_ticket", 0) or config.get("find_all", 1) # Support 'All' mode too

                # 1. Look for next available file (Atomic Locking)
                xml_file = self._get_next_available_file()
                
                if not xml_file:
                    self.update_gui_status("Waiting for files", "waiting")
                    self._report_idle_queue()
                    sleep(1)
                    continue

                try:
                    # Store original filename
                    self.current_original_filename = os.path.basename(xml_file)
                    
                    # 1. Check First Loop Process Toggle
                    current_first_loop_enabled = config.get("first_loop", True)
                    if current_first_loop_enabled and not self.first_loop_done:
                        self.update_gui_status("First Loop", "working")
                        res = self.first_loop_process()
                        if res == "complete":
                            self.first_loop_done = True
                        elif res == "restart":
                            # Cleanup lock if we need to restart the whole login
                            self._release_file_lock(xml_file)
                            sleep(2)
                            continue
                        elif res == "failed":
                            # Apple refresh limit reached -> move to login-failed and skip to next ID
                            print(f"[{self.device_id}] First loop FAILED (apple limit). Moving to login-failed and next ID...")
                            self.handle_failure(xml_file)
                            ui_stats.update(fail=ui_stats.fail_count + 1)
                            self.update_gui_status("Apple Failed", "error")
                            self._release_file_lock(xml_file)
                            self.first_loop_done = False
                            sleep(2)
                            continue
                    else:
                        self.first_loop_done = True
                    
                    print(f"[{self.device_id}] Processing file: {self.current_original_filename}")
                    self.update_gui_status(f"Injecting: {self.current_original_filename}")

                    # 2. Inject
                    injected_file = self.inject_file(xml_file)
                    
                    if injected_file:
                        # 3. Login
                        self.update_gui_status("Logging in...")
                        status = self.main_login(injected_file)
                        
                        if status == "success":
                            self.handle_success(xml_file)
                            ui_stats.update(success=ui_stats.success_count + 1, processed=ui_stats.processed_files + 1)
                            self.update_gui_status("Completed", "idle")
                        elif status == "kaiby":
                            self.handle_kaiby(xml_file)
                            ui_stats.update(fail=ui_stats.fail_count + 1)
                            self.update_gui_status("Kaiby Detected", "error")
                            self.first_loop_done = False
                        elif status == "failed":
                            self.handle_failure(xml_file)
                            ui_stats.update(fail=ui_stats.fail_count + 1)
                            self.update_gui_status("Failed", "error")
                            self.first_loop_done = False
                        else:
                            print(f"[{self.device_id}] Status: {status}. Moving to next.")
                            self.handle_failure(xml_file)
                            ui_stats.update(fail=ui_stats.fail_count + 1)
                            self.update_gui_status(f"Error: {status}", "error")
                    else:
                        print(f"[{self.device_id}] Injection failed for {xml_file}")
                        self.handle_dead_file(xml_file) # Move to failed if we can't even inject
                        ui_stats.update(fail=ui_stats.fail_count + 1)
                        self.update_gui_status("Inject Failed", "error")
                    
                    # Always ensure lock is removed after processing (handle_success/failure moves the file)
                    self._release_file_lock(xml_file)
                    
                except Exception as e:
                    print(f"[{self.device_id}] Critical Error with {xml_file}: {e}")
                    self._release_file_lock(xml_file)
                    sleep(1)

    def _get_lock_path(self, xml_file):
        """Get lock file path in temp directory (à¹„à¸¡à¹ˆà¸£à¸ backup folder)"""
        lock_dir = os.path.join(tempfile.gettempdir(), "ranger-locks")
        if not os.path.exists(lock_dir):
            os.makedirs(lock_dir, exist_ok=True)
        # à¹ƒà¸Šà¹‰ hash à¸‚à¸­à¸‡ full path à¸à¸±à¸™ lock à¸Šà¸™à¸à¸±à¸™à¸à¸£à¸“à¸µà¹„à¸Ÿà¸¥à¹Œà¸Šà¸·à¹ˆà¸­à¸‹à¹‰à¸³à¹ƒà¸™à¸„à¸™à¸¥à¸°à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸¢à¹ˆà¸­à¸¢
        full = os.path.abspath(xml_file)
        lock_name = hashlib.md5(full.encode("utf-8")).hexdigest() + "_" + os.path.basename(xml_file) + ".lock"
        return os.path.join(lock_dir, lock_name)

    # lock à¸—à¸µà¹ˆà¸„à¹‰à¸²à¸‡à¹€à¸à¸´à¸™à¹€à¸§à¸¥à¸²à¸™à¸µà¹‰à¸–à¸·à¸­à¸§à¹ˆà¸²à¹€à¸ˆà¹‰à¸²à¸‚à¸­à¸‡à¸•à¸²à¸¢à¹„à¸›à¹à¸¥à¹‰à¸§ (à¸à¸±à¸™à¹„à¸Ÿà¸¥à¹Œà¸„à¹‰à¸²à¸‡à¸–à¸²à¸§à¸£)
    _STALE_LOCK_SEC = 1800

    @staticmethod
    def _pid_alive(pid):
        """à¹€à¸ˆà¹‰à¸²à¸‚à¸­à¸‡ lock à¸¢à¸±à¸‡à¸£à¸±à¸™à¸­à¸¢à¸¹à¹ˆà¹„à¸«à¸¡ - à¸–à¹‰à¸²à¸•à¸²à¸¢à¹à¸¥à¹‰à¸§à¸¢à¸¶à¸” lock à¸„à¸·à¸™à¹„à¸”à¹‰à¹€à¸¥à¸¢ à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸£à¸­à¸„à¸£à¸š 30 à¸™à¸²à¸—à¸µ"""
        if pid <= 0:
            return True
        try:
            if sys.platform == "win32":
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                STILL_ACTIVE = 259
                h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if not h:
                    return False
                code = ctypes.c_ulong()
                ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
                ctypes.windll.kernel32.CloseHandle(h)
                return (not ok) or code.value == STILL_ACTIVE
            os.kill(pid, 0)   # POSIX à¹€à¸—à¹ˆà¸²à¸™à¸±à¹‰à¸™ - à¸šà¸™ Windows os.kill à¸†à¹ˆà¸²à¹‚à¸›à¸£à¹€à¸‹à¸ªà¸ˆà¸£à¸´à¸‡
            return True
        except OSError:
            return False
        except Exception:
            return True   # à¹€à¸Šà¹‡à¸„à¹„à¸¡à¹ˆà¹„à¸”à¹‰ = à¸–à¸·à¸­à¸§à¹ˆà¸²à¸¢à¸±à¸‡à¸­à¸¢à¸¹à¹ˆ à¸›à¸¥à¹ˆà¸­à¸¢à¹ƒà¸«à¹‰à¸à¸Ž 30 à¸™à¸²à¸—à¸µà¸ˆà¸±à¸”à¸à¸²à¸£à¹à¸—à¸™

    @staticmethod
    def _lock_owner(lock_file):
        """à¸„à¸·à¸™ (pid, device) à¸‚à¸­à¸‡à¹€à¸ˆà¹‰à¸²à¸‚à¸­à¸‡ lock - lock à¸£à¸¹à¸›à¹à¸šà¸šà¹€à¸à¹ˆà¸²à¹€à¸à¹‡à¸šà¹à¸„à¹ˆ device à¸ˆà¸°à¹„à¸”à¹‰ pid = 0"""
        try:
            with open(lock_file, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read().strip()
        except OSError:
            return 0, ""
        pid, sep, dev = raw.partition("|")
        if not sep:
            return 0, raw
        try:
            return int(pid), dev
        except ValueError:
            return 0, raw

    @staticmethod
    def _prune_if_empty(folder, root_folder):
        """à¸¥à¸šà¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸¢à¹ˆà¸­à¸¢à¹ƒà¸™ backup/ à¸—à¸µà¹ˆà¹„à¸¡à¹ˆà¹€à¸«à¸¥à¸·à¸­à¸­à¸°à¹„à¸£à¹à¸¥à¹‰à¸§

        à¹ƒà¸Šà¹‰ os.rmdir à¹€à¸›à¹‡à¸™à¸•à¸±à¸§à¸•à¸±à¸”à¸ªà¸´à¸™à¹€à¸¥à¸¢ à¹€à¸žà¸£à¸²à¸°à¸¡à¸±à¸™à¸¥à¸šà¹„à¸”à¹‰à¹€à¸‰à¸žà¸²à¸°à¸•à¸­à¸™à¸—à¸µà¹ˆà¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸§à¹ˆà¸²à¸‡à¸ˆà¸£à¸´à¸‡ à¹†
        à¹à¸¥à¸°à¹€à¸›à¹‡à¸™ operation à¹€à¸”à¸µà¸¢à¸§à¸ˆà¸š - à¸–à¹‰à¸²à¸­à¸µà¸à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¹€à¸žà¸´à¹ˆà¸‡à¸«à¸¢à¹ˆà¸­à¸™à¹„à¸Ÿà¸¥à¹Œà¹€à¸‚à¹‰à¸²à¸¡à¸²à¸žà¸­à¸”à¸µ rmdir
        à¸ˆà¸° error à¹à¸¥à¹‰à¸§à¹€à¸£à¸²à¸‚à¹‰à¸²à¸¡à¹„à¸› à¹„à¸¡à¹ˆà¸¡à¸µà¸—à¸²à¸‡à¸¥à¸šà¹„à¸Ÿà¸¥à¹Œà¸‚à¸­à¸‡à¹ƒà¸„à¸£à¸«à¸²à¸¢
        à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œ backup/ à¸•à¸±à¸§à¹à¸¡à¹ˆà¹„à¸¡à¹ˆà¸¥à¸š à¹à¸¥à¸°à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸—à¸µà¹ˆà¸¢à¸±à¸‡à¸¡à¸µà¹„à¸Ÿà¸¥à¹Œà¸­à¸·à¹ˆà¸™à¸„à¹‰à¸²à¸‡ (à¹€à¸Šà¹ˆà¸™ .txt)
        à¸à¹‡à¹„à¸¡à¹ˆà¸¥à¸š à¹€à¸žà¸·à¹ˆà¸­à¹„à¸¡à¹ˆà¹ƒà¸«à¹‰à¸‚à¹‰à¸­à¸¡à¸¹à¸¥à¹ƒà¸„à¸£à¸«à¸²à¸¢à¹‚à¸”à¸¢à¹„à¸¡à¹ˆà¸•à¸±à¹‰à¸‡à¹ƒà¸ˆ
        """
        if os.path.abspath(folder) == os.path.abspath(root_folder):
            return False
        try:
            os.rmdir(folder)
        except OSError:
            return False
        try:
            rel = os.path.relpath(folder, root_folder)
        except ValueError:
            rel = folder
        print(f"[QUEUE] à¹ƒà¸Šà¹‰à¹„à¸Ÿà¸¥à¹Œà¸«à¸¡à¸”à¹à¸¥à¹‰à¸§ à¸¥à¸šà¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸§à¹ˆà¸²à¸‡: backup/{rel}")
        return True

    def _get_next_available_file(self):
        """à¸«à¸²à¹„à¸Ÿà¸¥à¹Œ .xml à¸•à¸±à¸§à¸–à¸±à¸”à¹„à¸›à¸ˆà¸²à¸à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸„à¸´à¸§à¹à¸¥à¹‰à¸§à¸ˆà¸­à¸‡à¹à¸šà¸š atomic

        à¹„à¸¥à¹ˆà¸•à¸²à¸¡à¸¥à¸³à¸”à¸±à¸šà¹ƒà¸™ queue_folders à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¹à¸£à¸à¸—à¸µà¹ˆà¸ˆà¸­à¸‡à¹„à¸”à¹‰à¸à¹‡à¸„à¸·à¸™à¹€à¸¥à¸¢
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        total = locked = 0
        for name in self._queue_folders():
            picked, n_files, n_locked = self._pick_file_from(os.path.join(script_dir, name))
            total += n_files
            locked += n_locked
            if picked:
                return picked
        # à¹€à¸à¹‡à¸šà¸ªà¸–à¸´à¸•à¸´à¹„à¸§à¹‰à¹ƒà¸«à¹‰ _report_idle_queue() à¸šà¸­à¸à¹„à¸”à¹‰à¸§à¹ˆà¸²à¸§à¹ˆà¸²à¸‡à¸‡à¸²à¸™à¹€à¸žà¸£à¸²à¸°à¸­à¸°à¹„à¸£
        self._queue_stats = (total, locked)
        return None

    def _pick_file_from(self, source_folder):
        """à¸«à¸²+à¸ˆà¸­à¸‡à¹„à¸Ÿà¸¥à¹Œ .xml à¸ˆà¸²à¸à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¹€à¸”à¸µà¸¢à¸§

        à¸„à¸·à¸™ (path à¸—à¸µà¹ˆà¸ˆà¸­à¸‡à¹„à¸”à¹‰ à¸«à¸£à¸·à¸­ None, à¸ˆà¸³à¸™à¸§à¸™à¹„à¸Ÿà¸¥à¹Œà¸—à¸µà¹ˆà¹€à¸ˆà¸­, à¸ˆà¸³à¸™à¸§à¸™à¸—à¸µà¹ˆà¸•à¸´à¸” lock)
        à¹€à¸”à¸´à¸™à¹€à¸‚à¹‰à¸²à¸—à¸¸à¸à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸¢à¹ˆà¸­à¸¢ (à¸¥à¸²à¸à¸—à¸±à¹‰à¸‡à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸¡à¸²à¸§à¸²à¸‡à¹„à¸”à¹‰à¹€à¸¥à¸¢) à¹à¸¥à¸°à¹€à¸à¹‡à¸šà¸à¸§à¸²à¸”
        à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸¢à¹ˆà¸­à¸¢à¸—à¸µà¹ˆà¹ƒà¸Šà¹‰à¹„à¸Ÿà¸¥à¹Œà¸«à¸¡à¸”à¹à¸¥à¹‰à¸§à¸—à¸´à¹‰à¸‡à¹„à¸›à¸”à¹‰à¸§à¸¢
        """
        if not os.path.exists(source_folder):
            return None, 0, 0

        files = []
        # topdown=False = à¹€à¸”à¸´à¸™à¸ˆà¸²à¸à¹ƒà¸™à¸ªà¸¸à¸”à¸­à¸­à¸à¸¡à¸² à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸‹à¹‰à¸­à¸™à¸«à¸¥à¸²à¸¢à¸Šà¸±à¹‰à¸™à¸—à¸µà¹ˆà¸§à¹ˆà¸²à¸‡à¸«à¸¡à¸”à¹à¸¥à¹‰à¸§
        # à¸ˆà¸°à¸–à¸¹à¸à¸¥à¸šà¹„à¸¥à¹ˆà¸ˆà¸²à¸à¸Šà¸±à¹‰à¸™à¹ƒà¸™à¸­à¸­à¸à¸¡à¸²à¹„à¸”à¹‰à¸„à¸£à¸šà¹ƒà¸™à¸£à¸­à¸šà¹€à¸”à¸µà¸¢à¸§
        for root, dirs, filenames in os.walk(source_folder, topdown=False):
            for f in filenames:
                if f.lower().endswith(".xml"):
                    files.append(os.path.join(root, f))
            self._prune_if_empty(root, source_folder)
        # Shuffle files so multiple processes don't hit the exact same order
        import random
        random.shuffle(files)

        locked_count = 0
        for xml_file in files:
            lock_file = self._get_lock_path(xml_file)

            # 1. Clean stale locks: à¹€à¸ˆà¹‰à¸²à¸‚à¸­à¸‡à¸•à¸²à¸¢à¹„à¸›à¹à¸¥à¹‰à¸§ à¸«à¸£à¸·à¸­à¸„à¹‰à¸²à¸‡à¹€à¸à¸´à¸™ 30 à¸™à¸²à¸—à¸µ
            #    getmtime à¸­à¸²à¸ˆ error à¸–à¹‰à¸² thread à¸­à¸·à¹ˆà¸™à¹€à¸žà¸´à¹ˆà¸‡à¸›à¸¥à¹ˆà¸­à¸¢ lock à¸žà¸­à¸”à¸µ - à¹€à¸”à¸´à¸¡à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸”à¸±à¸
            #    exception à¸•à¸±à¸§à¸™à¸µà¹‰à¹€à¸¥à¸¢à¸«à¸¥à¸¸à¸”à¸­à¸­à¸à¹„à¸›à¸†à¹ˆà¸² thread à¸—à¸±à¹‰à¸‡à¸•à¸±à¸§
            if os.path.exists(lock_file):
                try:
                    age = time.time() - os.path.getmtime(lock_file)
                except OSError:
                    age = None   # à¸«à¸²à¸¢à¹„à¸›à¹à¸¥à¹‰à¸§à¸£à¸°à¸«à¸§à¹ˆà¸²à¸‡à¹€à¸Šà¹‡à¸„ - à¸¥à¸­à¸‡à¸¢à¸¶à¸”à¸•à¹ˆà¸­à¹„à¸”à¹‰à¹€à¸¥à¸¢
                owner_pid, owner_dev = self._lock_owner(lock_file)
                dead_owner = owner_pid > 0 and not self._pid_alive(owner_pid)
                if age is None or dead_owner or age > self._STALE_LOCK_SEC:
                    if dead_owner:
                        print(f"[{self.device_id}] [LOCK] à¹€à¸ˆà¹‰à¸²à¸‚à¸­à¸‡ lock (pid {owner_pid} / {owner_dev}) à¹„à¸¡à¹ˆà¸­à¸¢à¸¹à¹ˆà¹à¸¥à¹‰à¸§ - à¸¢à¸¶à¸”à¸„à¸·à¸™: {os.path.basename(xml_file)}")
                    try: os.remove(lock_file)
                    except OSError: pass
                else:
                    locked_count += 1
                    continue

            # 2. Try Atomic Lock (O_CREAT | O_EXCL)
            try:
                fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, 'w') as f:
                    f.write(f"{os.getpid()}|{self.device_id}")
                # à¹„à¸Ÿà¸¥à¹Œà¸­à¸²à¸ˆà¸–à¸¹à¸à¸­à¸µà¸à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸«à¸¢à¸´à¸šà¹„à¸›à¸¢à¹‰à¸²à¸¢à¹€à¸£à¸µà¸¢à¸šà¸£à¹‰à¸­à¸¢à¹à¸¥à¹‰à¸§à¸•à¸±à¹‰à¸‡à¹à¸•à¹ˆà¸•à¸­à¸™à¸—à¸µà¹ˆà¹€à¸£à¸²à¹„à¸¥à¹ˆ list
                # à¸–à¹‰à¸²à¸«à¸²à¸¢à¹„à¸›à¹à¸¥à¹‰à¸§à¸à¹‡à¸„à¸·à¸™ lock à¹à¸¥à¹‰à¸§à¹„à¸›à¸•à¸±à¸§à¸–à¸±à¸”à¹„à¸› à¸”à¸µà¸à¸§à¹ˆà¸²à¹€à¸­à¸² path à¸—à¸µà¹ˆà¹„à¸¡à¹ˆà¸¡à¸µà¸­à¸¢à¸¹à¹ˆà¸ˆà¸£à¸´à¸‡
                # à¹„à¸›à¹ƒà¸«à¹‰ inject_file à¹à¸¥à¹‰à¸§à¹„à¸›à¹€à¸”à¹‰à¸‡ error à¸—à¸µà¸«à¸¥à¸±à¸‡
                if not os.path.exists(xml_file):
                    try: os.remove(lock_file)
                    except OSError: pass
                    continue
                return xml_file, len(files), locked_count
            except FileExistsError:
                locked_count += 1
                continue
            except Exception as e:
                print(f"[LOCK] Error creating lock for {xml_file}: {e}")
                continue

        return None, len(files), locked_count

    def _release_file_lock(self, xml_file):
        lock_file = self._get_lock_path(xml_file)
        if os.path.exists(lock_file):
            try: os.remove(lock_file)
            except: pass

    def handle_dead_file(self, file_path):
        """Move file that failed injection or has other issues"""
        dst_dir = "login-failed"
        if not os.path.exists(dst_dir): os.makedirs(dst_dir)
        base = os.path.basename(file_path)
        try: shutil.move(file_path, os.path.join(dst_dir, base))
        except: pass

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

    def clear_specific_shared_prefs(self):
        """Delete ALL shared_prefs and clear app cache"""
        base = "/data/data/com.linecorp.LGRGS/shared_prefs"
        cache_dir = "/data/data/com.linecorp.LGRGS/cache"
        
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(1)
        
        # Total clear including cache (Restore to Full Clear)
        self.adb_shell(f"su -c 'rm -rf {base}/* && rm -rf {cache_dir}/*'")
        print(f"[{self.device_id}] Cleared shared_prefs + cache (Full)")

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

        # Clear app and shared prefs to ensure device is clean
        print(f"[{self.device_id}] Clearing app data after failure...")
        self.clear_specific_shared_prefs()
        self.clear_and_restart()

    def backup_to_backupxml(self):
        try:
            if not self.current_original_filename:
                return False
            current_dir = os.path.dirname(os.path.abspath(__file__))
            queue_dir = queue_folder_paths()[0]   # à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸„à¸´à¸§à¸•à¸±à¸§à¹à¸£à¸à¸•à¸²à¸¡ config (input-id)
            print(f"[{self.device_id}] à¸¢à¹‰à¸²à¸¢à¹„à¸Ÿà¸¥à¹Œ {self.current_original_filename} à¸à¸¥à¸±à¸šà¹€à¸‚à¹‰à¸²à¸„à¸´à¸§ ({os.path.basename(queue_dir)}/) à¹€à¸žà¸·à¹ˆà¸­à¸§à¸™à¹€à¸‚à¹‰à¸²à¹ƒà¸«à¸¡à¹ˆ...")
            os.makedirs(queue_dir, exist_ok=True)
            source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
            dest_path = os.path.join(queue_dir, self.current_original_filename)
            self.adb_shell("su -c 'chmod 777 /data/data/com.linecorp.LGRGS/shared_prefs'")
            self.adb_shell(f"su -c 'chmod 777 {source_path}'")
            subprocess.run([self.adb_cmd, "-s", self.device_id, "pull", source_path, dest_path], 
                           capture_output=True, timeout=15)
            if os.path.exists(dest_path):
                print(f"[{self.device_id}] à¸¢à¹‰à¸²à¸¢à¹„à¸Ÿà¸¥à¹Œà¸à¸¥à¸±à¸šà¹€à¸‚à¹‰à¸²à¸„à¸´à¸§à¸ªà¸³à¹€à¸£à¹‡à¸ˆ: {dest_path}")
                return True
            return False
        except Exception as e:
            print(f"[{self.device_id}] Error backup back to backupxml: {e}")
            return False

    def backup_failed_login(self):
        try:
            print(f"[{self.device_id}] à¸¥à¹‡à¸­à¸à¸­à¸´à¸™à¸¥à¹‰à¸¡à¹€à¸«à¸¥à¸§/à¸•à¸´à¸” apple - à¸à¸³à¸¥à¸±à¸‡à¸ªà¸³à¸£à¸­à¸‡à¸‚à¹‰à¸­à¸¡à¸¹à¸¥à¹„à¸›à¸¢à¸±à¸‡ login-failed...")
            filename_prefix = config.get('filename_prefix', 'conyfly')
            backup_dir = "login-failed"
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            file_count = len([f for f in os.listdir(backup_dir) if f.startswith(filename_prefix)])
            next_num = file_count + 1
            source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
            dest_path = os.path.join(backup_dir, f"{filename_prefix}-loginfail{next_num}_LINE_COCOS_PREF_KEY_.xml")
            self.adb_shell("su -c 'chmod 777 /data/data/com.linecorp.LGRGS/shared_prefs'")
            self.adb_shell(f"su -c 'chmod 777 {source_path}'")
            subprocess.run([self.adb_cmd, "-s", self.device_id, "pull", source_path, dest_path], 
                           capture_output=True, timeout=15)
            if os.path.exists(dest_path):
                print(f"[{self.device_id}] à¸¢à¹‰à¸²à¸¢à¹„à¸Ÿà¸¥à¹Œà¹„à¸› login-failed à¸ªà¸³à¹€à¸£à¹‡à¸ˆ: {dest_path}")
                return True
            return False
        except Exception as e:
            print(f"[{self.device_id}] Error backup failed login: {e}")
            return False

    def clear_and_restart(self):
        """Clear app and prepare for next file"""
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(0.5)

    def handle_kaiby(self, file_path):
        """Handle kaiby error by moving file to kaiby/ folder and clearing app"""
        dst_dir = "kaiby"
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
        base = os.path.basename(file_path)
        dst = os.path.join(dst_dir, base)
        
        print(f"[{self.device_id}] KAIBY detected. Moving file to {dst_dir}/")
        
        # Clear app immediately
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(0.5)
        
        try:
            if os.path.exists(file_path):
                shutil.move(file_path, dst)
                print(f"[{self.device_id}] âœ“ Moved to {dst_dir}: {base}")
        except Exception as e:
            print(f"[{self.device_id}] Kaiby move error: {e}")

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

    def _decode_raw_screencap(self, raw_data):
        """Decode a raw (un-encoded) screencap frame.

        `screencap` without -p returns width(4) + height(4) + pixel_format(4)
        followed by RGBA bytes. Skipping -p avoids a PNG encode on the device
        AND a decode here. Returns False if the data is not in that layout, so
        the caller can fall back to treating it as PNG.
        """
        try:
            if len(raw_data) < 16:
                return False
            w, h, _fmt = struct.unpack('<III', raw_data[:12])
            if w <= 0 or h <= 0 or w > 4096 or h > 4096:
                return False

            # Android 9+ appends a 4-byte colorSpace to the header. Pick the
            # offset from the payload size rather than assuming - MuMu (Android
            # 12) sends 16, and assuming 12 shifts the image by one pixel.
            body = w * h * 4
            if len(raw_data) >= 16 + body:
                offset = 16
            elif len(raw_data) >= 12 + body:
                offset = 12
            else:
                return False

            rgba = np.frombuffer(raw_data[offset:offset + body],
                                 dtype=np.uint8).reshape((h, w, 4))
            # cvtColor, not np.dot: np.dot builds a float64 intermediate and
            # measured 25x slower for an identical result.
            self._screen = cv2.cvtColor(rgba, cv2.COLOR_RGBA2GRAY)
            self._screen_rgba = rgba      # colour stays lazy - see get_screen_color()
            self._screen_raw_png = None
            self._screen_color = None
            return True
        except Exception:
            return False

    def capture_screen(self):
        """Capture screen and load into RAM (raw screencap + lazy color decode)"""
        try:
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

            # à¹„à¸¡à¹ˆà¸¡à¸µ -p = à¹„à¸¡à¹ˆ encode PNG à¸šà¸™à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ Android à¹à¸¥à¸°à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡ decode à¸à¸±à¹ˆà¸‡à¸™à¸µà¹‰
            result = subprocess.run(
                [self.adb_cmd, "-s", self.device_id, "exec-out", "screencap"] + (["-p"] if int(config.get("screencap_png", 1) or 0) else []),
                capture_output=True, timeout=10, **kwargs
            )

            if result.returncode == 0 and len(result.stdout) > 100:
                if not self._decode_raw_screencap(result.stdout):
                    # Fallback: some emulators hand back PNG regardless
                    img_array = np.frombuffer(result.stdout, np.uint8)
                    self._screen = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
                    self._screen_raw_png = result.stdout  # for lazy color decode
                    self._screen_rgba = None
                    self._screen_color = None
            else:
                with open(self.filename, "wb") as f:
                    f.write(result.stdout)
                self._screen = cv2.imread(self.filename, 0)
                self._screen_raw_png = None
                self._screen_rgba = None
                self._screen_color = cv2.imread(self.filename, cv2.IMREAD_COLOR)

            # New frame -> any popup-free verdict from the previous frame is stale.
            self._normalize_frame()   # à¹ƒà¸«à¹‰à¹€à¸Ÿà¸£à¸¡à¹€à¸›à¹‡à¸™ 960x540 à¹€à¸ªà¸¡à¸­ (template à¸—à¸¸à¸à¸£à¸¹à¸›à¸•à¸±à¸”à¸ˆà¸²à¸à¸‚à¸™à¸²à¸”à¸™à¸µà¹‰)
            self._screen_gen += 1
            self._cap_fail = 0
            # === fixnet1/fixnet/fixplay (NET_POPUPS): à¹€à¸Šà¹‡à¸„à¸à¹ˆà¸­à¸™à¸—à¸¸à¸à¸­à¸¢à¹ˆà¸²à¸‡ à¸—à¸¸à¸à¸„à¸£à¸±à¹‰à¸‡à¸—à¸µà¹ˆà¸ˆà¸±à¸šà¸ˆà¸­ (à¹à¸šà¸š bot-tiket) ===
            # à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”à¸šà¸±à¸‡à¸—à¸¸à¸à¸­à¸¢à¹ˆà¸²à¸‡ à¸ˆà¸¶à¸‡à¹€à¸„à¸¥à¸µà¸¢à¸£à¹Œà¸•à¸£à¸‡à¸™à¸µà¹‰à¸à¹ˆà¸­à¸™à¸„à¸·à¸™à¸ à¸²à¸žà¹ƒà¸«à¹‰à¹ƒà¸„à¸£à¹ƒà¸Šà¹‰ - à¸„à¸£à¸­à¸šà¸„à¸¥à¸¸à¸¡
            # à¸—à¸¸à¸à¸¥à¸¹à¸›/à¸—à¸¸à¸à¸Ÿà¸±à¸‡à¸à¹Œà¸Šà¸±à¸™à¹ƒà¸™à¹„à¸Ÿà¸¥à¹Œà¸­à¸±à¸•à¹‚à¸™à¸¡à¸±à¸•à¸´ à¹€à¸ˆà¸­à¸à¹‡à¸à¸” à¸£à¸­à¹ƒà¸«à¹‰à¸«à¸²à¸¢ à¹à¸¥à¹‰à¸§à¸ˆà¸±à¸šà¹ƒà¸«à¸¡à¹ˆà¹ƒà¸«à¹‰à¸œà¸¹à¹‰à¹€à¸£à¸µà¸¢à¸
            if not getattr(self, "_in_net_check", False):
                self._in_net_check = True
                try:
                    _hit = self._dismiss_net_popup(self._screen)
                    if _hit:
                        self._clear_net_popup_loop(_hit)   # à¸à¸”à¸‹à¹‰à¸³à¸ˆà¸™à¸à¸§à¹ˆà¸²à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¸ˆà¸°à¸«à¸²à¸¢ à¹à¸¥à¹‰à¸§à¸„à¹ˆà¸­à¸¢à¸„à¸·à¸™à¸ à¸²à¸žà¹ƒà¸«à¹‰à¸œà¸¹à¹‰à¹€à¸£à¸µà¸¢à¸
                finally:
                    self._in_net_check = False

            # Popup check every 3rd capture to reduce CPU load (background thread also monitors)
            self._capture_count += 1
            if self._capture_count % 3 == 0:
                if not getattr(self, "_in_popup_check", False):
                    self._in_popup_check = True
                    try:
                        self.check_floating_popups()
                    except Exception as e:
                        print(f"[{self.device_id}] Popup check error: {e}")
                    self._in_popup_check = False
                
        except Exception as e:
            print(f"[{self.device_id}] Capture error: {e}")
            if "timed out" in str(e):
                self._adb_slow_until = time.time() + float(config.get("adb_backoff_sec", 60))
            # à¸™à¸±à¸š screencap à¸—à¸µà¹ˆà¸¥à¹‰à¸¡à¸•à¸´à¸”à¸à¸±à¸™ - à¸¥à¹‰à¸¡à¹à¸¥à¹‰à¸§ _screen à¸¢à¸±à¸‡à¹€à¸›à¹‡à¸™à¸ à¸²à¸žà¹€à¸à¹ˆà¸² à¸šà¸­à¸—à¸ˆà¸° 'à¸¡à¸­à¸‡à¹„à¸¡à¹ˆà¹€à¸«à¹‡à¸™' à¸›à¹Šà¸­à¸›à¸­à¸±à¸ž/à¸›à¸¸à¹ˆà¸¡à¹ƒà¸” à¹†
            # (à¹€à¸„à¸ªà¸ˆà¸£à¸´à¸‡: 20 à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¹à¸¢à¹ˆà¸‡ adb à¸à¸±à¸™ screencap à¸„à¹‰à¸²à¸‡à¹€à¸à¸´à¸™ 10 à¸§à¸´) à¸šà¸­à¸à¹ƒà¸«à¹‰à¸Šà¸±à¸”à¹à¸¥à¸°à¸¥à¸­à¸‡ reconnect à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸™à¸±à¹‰à¸™
            self._cap_fail = getattr(self, "_cap_fail", 0) + 1
            if self._cap_fail in (3, 10) or self._cap_fail % 30 == 0:
                print(f"[{self.device_id}] [CAPTURE] screencap à¸¥à¹‰à¸¡à¹€à¸«à¸¥à¸§à¸•à¸´à¸”à¸à¸±à¸™ {self._cap_fail} à¸„à¸£à¸±à¹‰à¸‡ - à¸šà¸­à¸—à¹€à¸«à¹‡à¸™à¹à¸•à¹ˆà¸ à¸²à¸žà¹€à¸à¹ˆà¸² à¸ˆà¸°à¸«à¸²à¸­à¸°à¹„à¸£à¹„à¸¡à¹ˆà¹€à¸ˆà¸­à¸—à¸±à¹‰à¸‡à¸™à¸±à¹‰à¸™ (adb à¸«à¸£à¸·à¸­à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸„à¹‰à¸²à¸‡)")
            if self._cap_fail % 5 == 0:
                try:
                    self.adb_run([self.adb_cmd, "-s", self.device_id, "reconnect"], timeout=10)
                    print(f"[{self.device_id}] [CAPTURE] à¸ªà¸±à¹ˆà¸‡ adb reconnect {self.device_id} à¹à¸¥à¹‰à¸§")
                except Exception:
                    pass
            if hasattr(self, "_in_popup_check"):
                self._in_popup_check = False

    def get_screen_color(self):
        """Lazy-load color screen (only decode when actually needed)"""
        if self._screen_color is None:
            if getattr(self, "_screen_rgba", None) is not None:
                self._screen_color = cv2.cvtColor(self._screen_rgba, cv2.COLOR_RGBA2BGR)
            elif self._screen_raw_png is not None:
                img_array = np.frombuffer(self._screen_raw_png, np.uint8)
                self._screen_color = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return self._screen_color

    def _find_in_screen(self, template_path, similarity=0.95):
        """Find template in cached screen image (no new capture).

        With pos_cache on, the first hit for a template is remembered and later
        lookups only re-check a small ROI around it; a miss there falls straight
        back to the full-screen scan below, so a moved button is still found.
        """
        if self._screen is None:
            return None
        tmpl = self._get_template(template_path)
        if tmpl is None:
            return None

        if self._pos_mem is not None:
            # Cache key includes the threshold: the same image searched at a
            # different similarity is a different question.
            return self._pos_mem.find(self._screen, tmpl,
                                      (template_path, similarity), similarity)

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

    def find(self, template_path, similarity=0.95):
        """Capture + find"""
        self.capture_screen()
        return self._find_in_screen(template_path, similarity)

    def exists(self, template_path, similarity=0.95):
        return self.find(template_path, similarity) is not None

    def exists_in_cache(self, template_path, similarity=0.95):
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

    def click(self, PSMRL, similarity=0.95):
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
    
    def _touch(self):
        """Return a live minitouch controller, or None to use ADB.

        Started lazily on the first tap and only attempted once - if the binary
        or the device says no, we quietly stay on ADB for the whole session.
        """
        if not config.get("minitouch", 0) or not TOUCH_HELPER_AVAILABLE:
            return None
        if self._minitouch is None and not self._minitouch_tried:
            with _minitouch_init_lock:
                if self._minitouch is None and not self._minitouch_tried:
                    self._minitouch_tried = True
                    self._minitouch = touch_helper.make_minitouch(
                        self.adb_cmd, self.device_id, log=print)
        ctrl = self._minitouch
        if ctrl is not None and ctrl.ok:
            # Taps are written in screenshot coordinates - keep minitouch scaled to them.
            if self._screen is not None:
                h, w = self._screen.shape[:2]
                ctrl.update_screen_size(w, h)
            return ctrl
        return None

    def tap(self, x, y):
        """Direct tap without image search"""
        self._tap_count += 1   # lets check_floating_popups() tell "nothing fired" apart
        ctrl = self._touch()
        if ctrl is not None and ctrl.tap(int(x), int(y)):
            return
        dx, dy = self._dev_xy(x, y)
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "input", "tap",
                     str(dx), str(dy)])

    def type_text(self, text):
        """Type text via ADB (for search box) - clears it first to avoid double typing"""
        # 1. Clear text (Move to end then send backspaces)
        self.adb_shell("input keyevent 123") # MOVE_END
        for _ in range(3):
            self.adb_shell("input keyevent 67 67 67 67 67 67 67 67 67 67") # 10 backspaces at once
        
        # 2. Type new text
        escaped = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "input", "text", escaped])
        sleep(0.2) # Brief wait for UI to process text input

    def swipe(self, x1, y1, x2, y2, duration=300):
        ctrl = self._touch()
        if ctrl is not None and ctrl.swipe(int(x1), int(y1), int(x2), int(y2), duration):
            return
        (x1, y1), (x2, y2) = self._dev_xy(x1, y1), self._dev_xy(x2, y2)
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "input", "swipe",
                     str(x1), str(y1), str(x2), str(y2), str(duration)])

    def check_black_screen(self):
        """Check if screen is mostly black (>80% black pixels) using persistence (15s)"""
        if self._screen is None:
            return False 
            
        try:
            # Thresholding to find black pixels (brightness < 50)
            _, thresh = cv2.threshold(self._screen, 50, 255, cv2.THRESH_BINARY_INV)
            num_black = cv2.countNonZero(thresh)
            total = self._screen.shape[0] * self._screen.shape[1]
            black_ratio = num_black / total
            is_black_now = black_ratio > 0.85
        except:
            is_black_now = False

        if not is_black_now:
            self._black_start_time = None
            return False
            
        if not hasattr(self, '_black_start_time') or self._black_start_time is None:
            self._black_start_time = time.time()
            return False
            
        duration = time.time() - self._black_start_time
        if duration >= 10:
            print(f"[{self.device_id}] STUCK/BLACK screen persisted for {duration:.1f}s. Triggering recovery...")
            self._black_start_time = None 
            return True
            
        return False

    def check_floating_popups(self):
        """
        Check and click floating popups (checkline / fixnetv2 / fixplay / fixnet1).
        à¹€à¸ˆà¸­à¸à¹‡à¸à¸” à¸§à¸™à¹€à¸Šà¹‡à¸„à¸‹à¹‰à¸³à¸ˆà¸™à¸à¸§à¹ˆà¸²à¸ˆà¸°à¹„à¸¡à¹ˆà¹€à¸ˆà¸­ popup à¹ƒà¸”à¹†
        à¸—à¸³à¸‡à¸²à¸™à¸—à¸¸à¸à¸£à¸­à¸š capture_screen() à¸„à¸¥à¸¸à¸¡à¸—à¸±à¹‰à¸‡à¹„à¸Ÿà¸¥à¹Œ

        à¹€à¸Šà¹‡à¸„à¸‹à¹‰à¸³à¸šà¸™à¸ à¸²à¸žà¹€à¸”à¸´à¸¡à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸­à¸°à¹„à¸£à¹€à¸žà¸´à¹ˆà¸¡ (matchTemplate à¹ƒà¸«à¹‰à¸œà¸¥à¹€à¸”à¸´à¸¡à¹€à¸›à¹Šà¸°) â€” à¸›à¸à¸•à¸´à¸£à¸­à¸šà¸™à¸¶à¸‡
        à¹‚à¸”à¸™à¹€à¸£à¸µà¸¢à¸ 2 à¸„à¸£à¸±à¹‰à¸‡ (à¹ƒà¸™à¸¥à¸¹à¸› 1 + à¹ƒà¸™ check_error_images à¸­à¸µà¸ 1) = à¸ªà¹à¸à¸™à¸—à¸´à¹‰à¸‡à¸Ÿà¸£à¸µ
        à¹€à¸¥à¸¢à¸ˆà¸³à¹„à¸§à¹‰à¸§à¹ˆà¸²à¹€à¸Ÿà¸£à¸¡à¹„à¸«à¸™à¹€à¸Šà¹‡à¸„à¸ˆà¸™à¸ˆà¸šà¹à¸¥à¹‰à¸§à¹„à¸¡à¹ˆà¹€à¸ˆà¸­à¸­à¸°à¹„à¸£ à¹à¸¥à¹‰à¸§à¸‚à¹‰à¸²à¸¡à¸£à¸­à¸šà¸‹à¹‰à¸³à¸‚à¸­à¸‡à¹€à¸Ÿà¸£à¸¡à¸™à¸±à¹‰à¸™
        """
        gen_at_entry = self._screen_gen
        if self._popups_clean_gen == gen_at_entry:
            return

        # Time throttle. These popups sit on screen until something dismisses them,
        # so sampling a few times a second is as good as sampling every frame - it
        # only delays the click by at most SCAN_INTERVAL. Set scan_interval to 0 in
        # the config to restore the old scan-every-frame behaviour.
        now = time.time()
        if self.SCAN_INTERVAL > 0 and (now - self._last_popup_scan) < self.SCAN_INTERVAL:
            return
        self._last_popup_scan = now
        taps_at_entry = self._tap_count

        # checkline.png: Handle Checkbox Popup Sequence
        if self.exists_in_cache("img/checkline.png", similarity=0.8):
            print(f"[{self.device_id}] [POPUP] checkline.png detected! Running special sequence...")
            self.click("img/checkline.png", similarity=0.8)
            sleep(0.5)
            # 1. Wait for @check-l1.png
            start_l1 = time.time()
            while time.time() - start_l1 < 60:
                self._raw_capture()
                if self.exists_in_cache("img/check-l1.png", similarity=0.85):
                    print(f"[{self.device_id}] [POPUP] Found check-l1.png")
                    break
                sleep(0.3)
            else:
                _sc = self._match_score("img/check-l1.png")
                print(f"[{self.device_id}] [CHECKLINE] check-l1.png timeout (score {_sc:.2f})")
            # 2. Coordinates
            print(f"[{self.device_id}] [POPUP] Clicking coordinates (932, 133), (930, 253), (926, 327)...")
            self.tap(932, 133)
            sleep(0.2)
            self.tap(930, 253)
            sleep(0.2)
            self.tap(926, 327)
            sleep(0.3)
            # 3. Wait for check-l4.png
            start_l4 = time.time()
            while time.time() - start_l4 < 60:
                self._raw_capture()
                if self.exists_in_cache("img/check-l4.png", similarity=0.8):
                    print(f"[{self.device_id}] [POPUP] Found and clicking check-l4.png")
                    self.click("img/check-l4.png", similarity=0.8)
                    break
                sleep(0.3)
            else:
                _sc = self._match_score("img/check-l4.png")
                print(f"[{self.device_id}] [CHECKLINE] check-l4.png timeout (score {_sc:.2f})")
            # 4. Click check-ok1.png
            print(f"[{self.device_id}] [POPUP] Waiting for check-ok1.png to finish...")
            for _ in range(60):
                self._raw_capture()
                if self.exists_in_cache("img/check-ok1.png", similarity=0.8):
                    self.click("img/check-ok1.png", similarity=0.8)
                    print(f"[{self.device_id}] [POPUP] Checkline sequence complete!")
                    sleep(0.3)
                    break
                sleep(0.3)
            else:
                _sc = self._match_score("img/check-ok1.png")
                print(f"[{self.device_id}] [CHECKLINE] check-ok1.png timeout (score {_sc:.2f})")
            return
        # fixnetv2.png: à¹€à¸ˆà¸­à¸à¹‡à¸à¸” à¹à¸¥à¹‰à¸§à¸£à¸­à¸à¸” fixnetv2ok.png
        if self.exists_in_cache("img/fixnetv2.png", similarity=0.8):
            print(f"[{self.device_id}] [POPUP] fixnetv2.png detected, clicking...")
            self.click("img/fixnetv2.png", similarity=0.8)
            sleep(0.5)
            self._raw_capture()
            if self.exists_in_cache("img/fixnetv2ok.png", similarity=0.8):
                self.click("img/fixnetv2ok.png", similarity=0.8)
                sleep(0.3)
            return

        # fixplay.png (PLAY): à¹€à¸Šà¹‡à¸„à¸•à¸¥à¸­à¸”à¹€à¸«à¸¡à¸·à¸­à¸™ fixnet - à¸­à¸¢à¸¹à¹ˆà¹ƒà¸™ NET_POPUPS à¹à¸¥à¹‰à¸§ (à¸—à¸¸à¸à¸„à¸£à¸±à¹‰à¸‡à¸—à¸µà¹ˆà¸ˆà¸±à¸šà¸ˆà¸­ + monitor
        # à¹€à¸šà¸·à¹‰à¸­à¸‡à¸«à¸¥à¸±à¸‡ à¸à¸”à¸œà¹ˆà¸²à¸™ adb à¸‹à¹‰à¸³à¸ˆà¸™à¸«à¸²à¸¢ à¹à¸¥à¹‰à¸§à¸£à¸­à¸à¸” check-ok1.png à¸•à¹ˆà¸­ à¸•à¸²à¸¡ NET_FOLLOWUP)
        # à¸•à¸£à¸‡à¸™à¸µà¹‰à¹€à¸œà¸·à¹ˆà¸­à¸«à¸¥à¸¸à¸”à¸¡à¸²à¸–à¸¶à¸‡ (à¸•à¸´à¸” cooldown / à¹€à¸Šà¹‡à¸„à¸‹à¹‰à¸­à¸™): à¸ªà¹ˆà¸‡à¹€à¸‚à¹‰à¸²à¸—à¸²à¸‡à¹€à¸”à¸µà¸¢à¸§à¸à¸±à¸™ à¹„à¸¡à¹ˆà¸à¸”/à¸£à¸­ OK à¸‹à¹‰à¸³à¸ªà¸­à¸‡à¸Šà¸±à¹‰à¸™
        if self.exists_in_cache("img/fixplay.png", similarity=0.8) and not getattr(self, "_in_net_check", False):
            print(f"[{self.device_id}] [POPUP] fixplay.png detected, clearing via net-popup path...")
            self._in_net_check = True
            try:
                self._netpopup_last_click = 0
                _hit = self._dismiss_net_popup(self._screen)
                if _hit:
                    self._clear_net_popup_loop(_hit)
            finally:
                self._in_net_check = False

        # fixnet.png: à¹€à¸Šà¹‡à¸„à¸•à¸¥à¸­à¸”à¹€à¸ˆà¸­à¸à¹‡à¸à¸”à¸£à¸±à¸§à¹† à¹„à¸¡à¹ˆà¸¡à¸µà¸«à¸¢à¸¸à¸”à¸ˆà¸™à¸à¸§à¹ˆà¸²à¸ˆà¸°à¸«à¸²à¸¢à¹„à¸›
        fixnet_clicks = 0
        while self.exists_in_cache("img/fixnet.png", similarity=0.8):
            fixnet_clicks += 1
            print(f"[{self.device_id}] [POPUP] fixnet.png detected (click #{fixnet_clicks}), clicking...")
            self.click("img/fixnet.png", similarity=0.8)
            sleep(0.5)
            self._raw_capture()
            if fixnet_clicks >= 10:
                print(f"[{self.device_id}] [POPUP] fixnet.png clicked 10 times, breaking to avoid infinite loop")
                break

        # fixnet1.png: à¸§à¸™à¹€à¸Šà¹‡à¸„à¸‹à¹‰à¸³à¸ˆà¸™à¸à¸§à¹ˆà¸²à¸ˆà¸°à¹„à¸¡à¹ˆà¹€à¸ˆà¸­ (re-capture à¸—à¸¸à¸à¸£à¸­à¸š) - à¸›à¸£à¸±à¸š similarity à¹€à¸›à¹‡à¸™ 0.8 à¹€à¸žà¸·à¹ˆà¸­à¸„à¸§à¸²à¸¡à¸Šà¸±à¸§à¸£à¹Œ
        fixnet1_clicks = 0
        while self.exists_in_cache("img/fixnet1.png", similarity=0.8):
            fixnet1_clicks += 1
            print(f"[{self.device_id}] [POPUP] fixnet1.png detected (click #{fixnet1_clicks}), clicking...")
            self.click("img/fixnet1.png", similarity=0.8)
            sleep(0.5)
            self._raw_capture()  # à¸ˆà¸±à¸šà¸ à¸²à¸žà¹ƒà¸«à¸¡à¹ˆà¹€à¸žà¸·à¹ˆà¸­à¹€à¸Šà¹‡à¸„à¸‹à¹‰à¸³ (à¹„à¸¡à¹ˆà¸§à¸™à¸à¸¥à¸±à¸š popup check)
            if fixnet1_clicks >= 10:
                print(f"[{self.device_id}] [POPUP] fixnet1.png clicked 10 times, breaking to avoid infinite loop")
                break

        # fixface.bmp: à¸ˆà¸­à¸ªà¹à¸à¸™à¸«à¸™à¹‰à¸²/à¸¢à¸·à¸™à¸¢à¸±à¸™à¸•à¸±à¸§à¸•à¸™ - à¸à¸” BACK 1 à¸„à¸£à¸±à¹‰à¸‡à¸–à¸­à¸¢à¸­à¸­à¸ (à¸«à¹‰à¸²à¸¡à¸à¸”à¸šà¸™à¸ˆà¸­)
        if self.exists_in_cache("img/fixface.bmp", similarity=0.8):
            print(f"[{self.device_id}] [POPUP] fixface.bmp detected, pressing BACK once...")
            self.adb_shell("input keyevent 4")
            sleep(1.0)
            self._raw_capture()

        if self.exists_in_cache("img/fixaccep.png"):
            print(f"[{self.device_id}] [POPUP] fixaccep.png detected, clicking...")
            self.click("img/fixaccep.png")
            sleep(0.3)

        # fixnetv3.png: Global Network Popup Check (Special coordinates 472, 361)
        if self.exists_in_cache("img/fixnetv3.png", similarity=0.8):
            self._fixnetv3_count += 1
            print(f"[{self.device_id}] [POPUP] fixnetv3.png detected (#{self._fixnetv3_count})! Tapping (472, 361)...")
            self._adb_tap(472, 361)   # à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•: à¸à¸”à¸œà¹ˆà¸²à¸™ adb à¸•à¸£à¸‡ à¹† à¹€à¸«à¸¡à¸·à¸­à¸™ bot-tiket
            sleep(0.5)
            
            if self._fixnetv3_count >= 8:
                print(f"[{self.device_id}] [POPUP] fixnetv3.png persists after 8 clicks! Force-stopping app...")
                self._need_restart = True
                self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
                self._fixnetv3_count = 0
        else:
            # We don't reset here necessarily because multiple popups might be checked
            pass

        # Mark this frame popup-free ONLY if the pass did nothing at all: no new
        # frame AND no input sent. Every popup branch above taps or clicks, so a
        # tap counter is a reliable "something fired" signal - checking the frame
        # generation alone is not (some branches click without re-capturing).
        if self._screen_gen == gen_at_entry and self._tap_count == taps_at_entry:
            self._popups_clean_gen = gen_at_entry

    def _raw_capture(self):
        """Capture screen WITHOUT triggering popup checks (à¸›à¹‰à¸­à¸‡à¸à¸±à¸™à¸§à¸™à¸‹à¹‰à¸­à¸™)"""
        try:
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                [self.adb_cmd, "-s", self.device_id, "exec-out", "screencap"] + (["-p"] if int(config.get("screencap_png", 1) or 0) else []),
                capture_output=True, timeout=10, **kwargs
            )
            if result.returncode == 0 and len(result.stdout) > 100:
                if not self._decode_raw_screencap(result.stdout):
                    img_array = np.frombuffer(result.stdout, np.uint8)
                    self._screen = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
                    self._screen_raw_png = result.stdout
                    self._screen_rgba = None
                    self._screen_color = None  # lazy decode
            else:
                with open(self.filename, "wb") as f:
                    f.write(result.stdout)
                self._screen = cv2.imread(self.filename, 0)
                self._screen_raw_png = None
                self._screen_rgba = None
                self._screen_color = cv2.imread(self.filename, cv2.IMREAD_COLOR)
            self._normalize_frame()   # à¹ƒà¸«à¹‰à¹€à¸Ÿà¸£à¸¡à¹€à¸›à¹‡à¸™ 960x540 à¹€à¸ªà¸¡à¸­ (template à¸—à¸¸à¸à¸£à¸¹à¸›à¸•à¸±à¸”à¸ˆà¸²à¸à¸‚à¸™à¸²à¸”à¸™à¸µà¹‰)
            self._screen_gen += 1
            # === fixnet1/fixnet/fixplay (NET_POPUPS): à¹€à¸Šà¹‡à¸„à¸à¹ˆà¸­à¸™à¸—à¸¸à¸à¸­à¸¢à¹ˆà¸²à¸‡ à¸—à¸¸à¸à¸„à¸£à¸±à¹‰à¸‡à¸—à¸µà¹ˆà¸ˆà¸±à¸šà¸ˆà¸­ (à¹à¸šà¸š bot-tiket) ===
            # à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”à¸šà¸±à¸‡à¸—à¸¸à¸à¸­à¸¢à¹ˆà¸²à¸‡ à¸ˆà¸¶à¸‡à¹€à¸„à¸¥à¸µà¸¢à¸£à¹Œà¸•à¸£à¸‡à¸™à¸µà¹‰à¸à¹ˆà¸­à¸™à¸„à¸·à¸™à¸ à¸²à¸žà¹ƒà¸«à¹‰à¹ƒà¸„à¸£à¹ƒà¸Šà¹‰ - à¸„à¸£à¸­à¸šà¸„à¸¥à¸¸à¸¡
            # à¸—à¸¸à¸à¸¥à¸¹à¸›/à¸—à¸¸à¸à¸Ÿà¸±à¸‡à¸à¹Œà¸Šà¸±à¸™à¹ƒà¸™à¹„à¸Ÿà¸¥à¹Œà¸­à¸±à¸•à¹‚à¸™à¸¡à¸±à¸•à¸´ à¹€à¸ˆà¸­à¸à¹‡à¸à¸” à¸£à¸­à¹ƒà¸«à¹‰à¸«à¸²à¸¢ à¹à¸¥à¹‰à¸§à¸ˆà¸±à¸šà¹ƒà¸«à¸¡à¹ˆà¹ƒà¸«à¹‰à¸œà¸¹à¹‰à¹€à¸£à¸µà¸¢à¸
            if not getattr(self, "_in_net_check", False):
                self._in_net_check = True
                try:
                    _hit = self._dismiss_net_popup(self._screen)
                    if _hit:
                        self._clear_net_popup_loop(_hit)   # à¸à¸”à¸‹à¹‰à¸³à¸ˆà¸™à¸à¸§à¹ˆà¸²à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¸ˆà¸°à¸«à¸²à¸¢ à¹à¸¥à¹‰à¸§à¸„à¹ˆà¸­à¸¢à¸„à¸·à¸™à¸ à¸²à¸žà¹ƒà¸«à¹‰à¸œà¸¹à¹‰à¹€à¸£à¸µà¸¢à¸
                finally:
                    self._in_net_check = False
        except Exception as e:
            print(f"[{self.device_id}] Raw capture error: {e}")
            if "timed out" in str(e):
                self._adb_slow_until = time.time() + float(config.get("adb_backoff_sec", 60))

    def _app_is_gone(self):
        """True when the game process is not running.

        Uses `pidof`, which needs a fresh adb process, so it is rate-limited to
        one call per PIDOF_INTERVAL seconds. Between calls it reports the last
        known answer rather than guessing, so a crash is spotted within one
        interval instead of on every single frame.
        """
        now = time.time()
        if (now - self._last_pidof_check) < self.PIDOF_INTERVAL:
            return self._app_gone_cached
        self._last_pidof_check = now
        try:
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            pid_result = subprocess.run(
                [self.adb_cmd, "-s", self.device_id, "shell", "pidof", "com.linecorp.LGRGS"],
                capture_output=True, text=True, timeout=5, **kwargs
            )
            self._app_gone_cached = not pid_result.stdout.strip()
        except Exception:
            self._app_gone_cached = False   # can't tell -> assume alive, as before
        return self._app_gone_cached

    def check_error_images(self, skip_fixcak=False, skip_icon=False):
        """Check error images using cached screen"""

        # ===== FLOATING POPUP CHECKS (à¸à¸”à¹à¸¥à¹‰à¸§à¸—à¸³à¸‡à¸²à¸™à¸•à¹ˆà¸­ à¹„à¸¡à¹ˆ return error) =====
        self.check_floating_popups()

        # Same throttle as the popup pass. check_critical_errors() below is the most
        # expensive thing in the whole loop (5 colour matches, ~250ms) and none of
        # these errors are transient, so a few sweeps a second is enough. Returning
        # None just means "nothing wrong right now" - what callers already expect.
        #
        # The app-alive check runs BEFORE the throttle: if the app died, every
        # scan below is pointless anyway, and delaying the relaunch is the one
        # thing here that really costs wall-clock. It has its own PIDOF_INTERVAL.
        if not skip_icon and self._app_is_gone():
            return "icon"

        now = time.time()
        if self.SCAN_INTERVAL > 0 and (now - self._last_error_scan) < self.SCAN_INTERVAL:
            return None
        self._last_error_scan = now

        # ===== CRITICAL ERROR CHECKS (à¸¢à¹‰à¸²à¸¢à¹„à¸Ÿà¸¥à¹Œà¸à¸¥à¸±à¸š/à¸ªà¸³à¸£à¸­à¸‡à¸¥à¹‰à¸§ restart) =====
        critical = check_critical_errors(self, self.get_screen_color(), "check_error_images")
        if critical: return critical
        
        # Check for Black/Stuck screen
        if self.check_black_screen():
            return "fixcak"

        # fixcak.png: restart process if found
        if not skip_fixcak:
            fixcak_path = "img/fixcak.png"
            if os.path.exists(fixcak_path) and self.exists_in_cache(fixcak_path):
                return "fixcak"
        
        # stopcheck.png: complete/stop process if found.
        # à¹€à¸”à¸´à¸¡à¸§à¸™ [0.95, 0.9, 0.85, 0.8] = matchTemplate à¸ à¸²à¸žà¹€à¸”à¸´à¸¡ 4 à¸£à¸­à¸š à¹„à¸”à¹‰à¸œà¸¥à¹€à¸—à¹ˆà¸²à¸à¸±à¸™à¸—à¸¸à¸à¸£à¸­à¸š
        # à¸•à¹ˆà¸²à¸‡à¹à¸„à¹ˆà¸„à¹ˆà¸²à¸—à¸µà¹ˆà¹€à¸­à¸²à¹„à¸›à¹€à¸—à¸µà¸¢à¸š à¸‹à¸¶à¹ˆà¸‡à¹€à¸—à¸µà¸¢à¸šà¹€à¸—à¹ˆà¸²à¸à¸±à¸šà¹€à¸Šà¹‡à¸„à¸—à¸µà¹ˆà¸„à¹ˆà¸²à¸«à¸¥à¸§à¸¡à¸ªà¸¸à¸”à¸„à¸£à¸±à¹‰à¸‡à¹€à¸”à¸µà¸¢à¸§à¹€à¸›à¹Šà¸° à¹†
        if self.exists_in_cache("img/stopcheck.png", similarity=0.8):
            return "stopcheck"

        # Common login errors
        if self.exists_in_cache("img/fixbuglogin.png"):
            return "fixbug"

        if self.exists_in_cache("img/unkhow.png"):
            return "unkhow"

        if self.find_kaiby():
            return "kaiby"

        error_images = ["img/failed1.png", "img/fixalerterror1.png"]
        for err in error_images:
            if self.exists_in_cache(err):
                return "error_img"
                
        return None

    # =========================================================
    # Ruby and Ticket OCR - Derived from check-rubyandtiket.py
    # =========================================================
    def find_template_ocr(self, img, template_path, threshold=0.7):
        """Find template in image and return position (for OCR regions)"""
        try:
            template = cv2.imread(template_path)
            if template is None:
                return None
            
            img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            
            result = cv2.matchTemplate(img_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            
            if max_val >= threshold:
                h, w = template_gray.shape
                return {
                    'x': max_loc[0], 'y': max_loc[1],
                    'width': w, 'height': h,
                    'confidence': max_val
                }
            return None
        except Exception:
            return None

    def read_number_from_region(self, img, x, y, width, height, label="OCR"):
        """Read number from specified region using EasyOCR"""
        try:
            h, w = img.shape[:2]
            
            # --- Padding Selection ---
            # RUBY/TICKET à¹ƒà¸Šà¹‰ pad à¸™à¹‰à¸­à¸¢ à¸à¸±à¸™à¸‚à¸¢à¸²à¸¢à¸à¸£à¸­à¸šà¹„à¸›à¸ˆà¸±à¸šà¹„à¸­à¸„à¸­à¸™à¸‚à¹‰à¸²à¸‡à¹† (à¹„à¸­à¸„à¸­à¸™à¸—à¸³ OCR à¸ªà¸±à¸šà¸ªà¸™)
            PAD = 2 if ("RUBY" in label or "TICKET" in label) else 10
            x1 = max(0, int(x) - PAD)
            y1 = max(0, int(y) - PAD)
            x2 = min(w, int(x + width) + PAD)
            y2 = min(h, int(y + height) + PAD)
            
            cropped = img[y1:y2, x1:x2]
            if cropped is None or cropped.size == 0:
                return None
            
            # --- Visual Debug Save (Red Rectangle) ---
            if config.get("debug_ocr", 0) == 1:
                debug_dir = "debug_ocr"
                if not os.path.exists(debug_dir):
                    os.makedirs(debug_dir)
                
                debug_img = img.copy()
                cv2.rectangle(debug_img, (int(x), int(y)), (int(x + width), int(y + height)), (0, 0, 255), 2)
                cv2.putText(debug_img, label, (int(x), int(y) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                safe_dev = self.device_id.replace(":", "_")
                save_path = os.path.join(debug_dir, f"debug_ocr_{safe_dev}_{label}.png")
                cv2.imwrite(save_path, debug_img)
            # ------------------------------------------

            # Pre-processing
            gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
            
            # Scale based on height like test_ocr.py (6x for small, 3x for others)
            scale = 6 if height < 30 else 3
            v_scaled = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            
            # --- Preprocessing Selection (All use manual_180 threshold for precision) ---
            # manual_180 is very reliable for white text on dark background
            _, v_bin = cv2.threshold(v_scaled, 180, 255, cv2.THRESH_BINARY_INV)

            # à¹€à¸•à¸´à¸¡à¸‚à¸­à¸šà¸‚à¸²à¸§à¸£à¸­à¸šà¸ à¸²à¸ž à¸Šà¹ˆà¸§à¸¢à¹ƒà¸«à¹‰ EasyOCR à¸•à¸£à¸§à¸ˆà¹€à¸¥à¸‚à¸«à¸¥à¸±à¸à¹€à¸”à¸µà¸¢à¸§à¹‚à¸”à¸”à¹† (à¹€à¸Šà¹ˆà¸™ "4") à¹„à¸”à¹‰ (BINARY_INV -> à¸žà¸·à¹‰à¸™à¸«à¸¥à¸±à¸‡à¸‚à¸²à¸§=255)
            v_bin = cv2.copyMakeBorder(v_bin, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)

            reader = get_ocr_reader()
            with _ocr_run_lock:  # OCR à¸—à¸µà¸¥à¸°à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ à¸à¸±à¸™ CPU à¸•à¸±à¸™
                # text_threshold/low_text à¸•à¹ˆà¸³à¸¥à¸‡ = detect à¹€à¸¥à¸‚à¸«à¸¥à¸±à¸à¹€à¸”à¸µà¸¢à¸§à¹€à¸¥à¹‡à¸à¹† à¹„à¸”à¹‰à¹„à¸§à¸‚à¸¶à¹‰à¸™
                results = reader.readtext(v_bin, allowlist='0123456789,', detail=0,
                                          text_threshold=0.5, low_text=0.3)
            
            if results:
                print(f"[{self.device_id}] [STRICT-OCR] {label} raw={results}")
                combined = "".join(results)
                final_digits = "".join([c for c in combined if c.isdigit()])
                if final_digits:
                    print(f"[{self.device_id}] [STRICT-OCR] {label} Final: {final_digits}")
                    return final_digits
                
            return None
        except Exception as e:
            print(f"[{self.device_id}] [STRICT-OCR ERROR] {label} failed: {e}")
            return None

    def read_ticket_and_ruby(self):
        """Read Ticket and Ruby counts from screen using OCR"""
        color = self.get_screen_color()
        if color is None: return None, None
            
        img = color
        ticket_value = None
        ruby_value = None
        
        # --- HYBRID PRECISION ROI ---
        # Ruby area (New Expanded for Thousands)
        rx, ry, rw, rh = 427, 20, 51, 16
        ruby_value = self.read_number_from_region(img, rx, ry, rw, rh, label="RUBY")
        
        # Ticket area (Reverted to Classic)
        tx, ty, tw, th = 558, 20, 56, 16
        ticket_value = self.read_number_from_region(img, tx, ty, tw, th, label="TICKET")
        
        # Backup: Template search à¹à¸¢à¸à¸­à¸´à¸ªà¸£à¸°à¸•à¹ˆà¸­à¸„à¹ˆà¸² (à¹€à¸ˆà¸­à¸•à¸±à¸§à¹„à¸«à¸™ None à¸à¹‡ backup à¸•à¸±à¸§à¸™à¸±à¹‰à¸™)
        if ruby_value is None:
            print(f"[{self.device_id}] [RESOURCE] RUBY fixed ROI failed, trying Template backup...")
            ruby_match = self.find_template_ocr(img, 'img/checkruby.png', threshold=0.7)
            if ruby_match:
                rx_b, ry_b, rw_b, rh_b = ruby_match['x'], ruby_match['y'], ruby_match['width'], ruby_match['height']
                ruby_value = self.read_number_from_region(img, rx_b + int(rw_b * 0.45), ry_b + 2, int(rw_b * 0.50), rh_b - 4, label="RUBY_B")

        if ticket_value is None:
            print(f"[{self.device_id}] [RESOURCE] TICKET fixed ROI failed, trying Template backup...")
            ticket_match = self.find_template_ocr(img, 'img/checktiket.png', threshold=0.65)
            if ticket_match:
                tx_b, ty_b, tw_b, th_b = ticket_match['x'], ticket_match['y'], ticket_match['width'], ticket_match['height']
                ticket_value = self.read_number_from_region(img, tx_b + int(tw_b * 0.45), ty_b + 2, int(tw_b * 0.50), th_b - 4, label="TICKET_B")

        return ticket_value, ruby_value


    def process_check_ruby_ticket(self):
        """Navigate to gacha screen and check rubies/tickets"""
        print(f"[{self.device_id}] Starting Ruby and Ticket check...")

        # Mode Check: Pure Resource Scan (do_ranger=0, do_gear=0) or Mixed Scan
        is_pure_resource_check = (not self.do_ranger and not self.do_gear)
        
        if is_pure_resource_check:
            # === Pure Resource Mode ===
            print(f"[{self.device_id}] [NAVI-RUBY] Resource check only -> Searching for gacha.png...")
            self.wait_and_click_image("gacha.png", timeout=15)
        else:
            # === Mixed Mode ===
            print(f"[{self.device_id}] [NAVI-RUBY] Mixed mode -> Navigating to Gacha screen...")
            if not self.wait_and_click_image("gotogacha1.png", timeout=15):
                 print(f"[{self.device_id}] gotogacha1.png not found")
            sleep(0.5)
            if not self.wait_and_click_image("gotogacha2.png", timeout=15):
                 print(f"[{self.device_id}] gotogacha2.png not found")
        
        # --- Mandatory Stable Wait ---
        # à¸«à¸² fixgems à¸•à¸¥à¸­à¸” (à¸¥à¸­à¸¢à¹†) à¹€à¸ˆà¸­ popup gems à¸à¸”à¸›à¸´à¸” 1 à¸£à¸­à¸š à¹à¸¥à¹‰à¸§à¸§à¸™à¸à¸¥à¸±à¸šà¹„à¸›à¸«à¸² waitgacha
        # à¹€à¸ˆà¸­ waitgacha.png à¸„à¹ˆà¸­à¸¢à¹€à¸£à¸´à¹ˆà¸¡à¸ªà¹à¸à¸™ (à¹€à¸žà¸”à¸²à¸™ 90 à¸§à¸´ - à¹€à¸”à¸´à¸¡à¹„à¸¡à¹ˆà¸¡à¸µ timeout
        # à¸žà¸­à¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”à¸•à¸­à¸™à¹€à¸‚à¹‰à¸²à¸«à¸™à¹‰à¸²à¸à¸²à¸Šà¸² waitgacha à¹„à¸¡à¹ˆà¸¡à¸µà¸§à¸±à¸™à¹‚à¸œà¸¥à¹ˆ = à¸„à¹‰à¸²à¸‡à¸–à¸²à¸§à¸£)
        WAITGACHA_SIM = 0.95
        FIXGEMS_SIM = 0.85
        print(f"[{self.device_id}] [RESOURCE-WAIT] Waiting for waitgacha.png (stable screen)...")
        wait_deadline = time.time() + 90
        while True:
            if time.time() > wait_deadline:
                print(f"[{self.device_id}] [RESOURCE-WAIT] waitgacha à¹„à¸¡à¹ˆà¸¡à¸²à¹ƒà¸™ 90 à¸§à¸´ (à¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”/à¸ˆà¸­à¹„à¸¡à¹ˆà¸¡à¸²) - à¸‚à¹‰à¸²à¸¡à¸à¸²à¸£à¹€à¸Šà¹‡à¸„ Ruby/Ticket")
                return None, None
            self.capture_screen()

            # à¸«à¸² fixgems à¸•à¸¥à¸­à¸” â€” à¹€à¸ˆà¸­ fixgems à¹à¸¥à¹‰à¸§à¸à¸” fixgems1 (1 à¸£à¸­à¸š) à¹à¸¥à¹‰à¸§à¸à¸¥à¸±à¸šà¹„à¸›à¸«à¸² waitgacha
            if self.exists_in_cache("img/fixgems.png", similarity=FIXGEMS_SIM):
                print(f"[{self.device_id}] [RESOURCE-WAIT] fixgems found -> clicking fixgems1.")
                self.click("img/fixgems1.png", similarity=FIXGEMS_SIM)
                sleep(1.0)
                continue

            # à¹€à¸ˆà¸­ waitgacha à¹à¸¥à¹‰à¸§à¹€à¸£à¸´à¹ˆà¸¡à¸ªà¹à¸à¸™ (ONLY Check visibility, DO NOT CLICK)
            if self.exists_in_cache("img/waitgacha.png", similarity=WAITGACHA_SIM):
                print(f"[{self.device_id}] [RESOURCE-WAIT] Screen confirmed stable (waitgacha found). Scanning now.")
                break

            # Auto-clear popups if they appear during transition
            self.check_floating_popups()
            sleep(0.5)
        
        # Settle wait
        sleep(1.0)
        
        ruby = None
        ticket = None
        
        # Retry loop for OCR (Up to 3 attempts, total wait approx 5-8s)
        for attempt in range(3):
            if attempt > 0:
                print(f"[{self.device_id}] OCR returned None, retrying in 1s (Attempt {attempt+1}/3)...")
                sleep(1.0)
            
            self.capture_screen()
            ticket, ruby = self.read_ticket_and_ruby()

            # retry à¸ˆà¸™à¸à¸§à¹ˆà¸²à¸ˆà¸°à¸­à¹ˆà¸²à¸™à¹„à¸”à¹‰à¸„à¸£à¸šà¸—à¸±à¹‰à¸‡ ruby à¹à¸¥à¸° ticket (à¸«à¸£à¸·à¸­à¸„à¸£à¸š 3 à¸£à¸­à¸š)
            if ruby is not None and ticket is not None:
                break
        
        print(f"[{self.device_id}] Result -> Ruby: {ruby}, Ticket: {ticket}")
        return ruby, ticket

    def wait_and_click_image(self, img_name, timeout=30, similarity=0.95):
        """Wait for image and click it, return True if found (timeout in seconds)"""
        if not img_name.startswith('img'):
            img_path = f"img/{img_name}"
        else:
            img_path = img_name
        
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.capture_screen()
                # ---- Check floating popups on every iteration ----
                self.check_floating_popups()
                # --------------------------------------------------
                # Match once and click the position we just got (the old code
                # searched, then made click() search the very same screen again).
                pos = self._find_in_screen(img_path, similarity)
                if pos:
                    print(f"[{self.device_id}] Found {img_name} (sim={similarity})! Clicking...")
                    self.click(pos)
                    return True
            except Exception as e:
                print(f"[{self.device_id}] Error while waiting for {img_name}: {e}")
            sleep(self.loop_delay(0.2))

        print(f"[{self.device_id}] Timeout waiting for {img_name} ({timeout}s)")
        return False

    # =========================================================
    # OCR Methods - For Gear Mode
    # =========================================================
    def ocr_read_region(self, x, y, w, h):
        """Read text from a specific region of the cached color screen using EasyOCR."""
        color = self.get_screen_color()
        if color is None or not self.do_gear:
            return []
        
        # Crop region from color image
        img = color[y:y+h, x:x+w]
        
        if img is None or img.size == 0:
            print(f"[{self.device_id}] OCR crop region empty!")
            return []
        
        try:
            reader = get_ocr_reader()
            with _ocr_run_lock:  # OCR à¸—à¸µà¸¥à¸°à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ à¸à¸±à¸™ CPU à¸•à¸±à¸™
                results = reader.readtext(img, detail=1)
            
            text_results = []
            for (bbox, text, conf) in results:
                if conf > 0.3:
                    text_results.append((text, conf))
            
            return text_results
        except Exception as e:
            print(f"[{self.device_id}] [OCR ERROR] OCR failed: {e}")
            print(f"[{self.device_id}] [OCR ERROR] Please install Visual C++ Redistributable: https://aka.ms/vs/17/release/vc_redist.x64.exe")
            return []

    def ocr_read_full_screen(self):
        """Read all text from the full cached color screen."""
        color = self.get_screen_color()
        if color is None or not self.do_gear:
            return ""
        
        region = self.ocr_region
        return self.ocr_read_region(region["x"], region["y"], region["w"], region["h"])

    def check_gear_by_text(self):
        """Check gear by reading text from screen and matching against config gear names."""
        if not self.do_gear:
            return set()
        
        try:
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
            print(f"[{self.device_id}] Reading screen text with OCR...")
            print(f"[{self.device_id}] OCR Text: {all_text}")
            
            found_gears = set()
            
            # Check config gears (Only what user specified)
            for gear_key, gear_data in self.gear_names.items():
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
        except Exception as e:
            print(f"[{self.device_id}] [OCR ERROR] check_gear_by_text failed: {e}")
            print(f"[{self.device_id}] [OCR ERROR] Gear scan skipped due to OCR error")
            return set()

    # =========================================================
    # Logic Methods
    # =========================================================
    def clear_specific_shared_prefs(self):
        """Delete ALL shared_prefs and clear app cache"""
        base = "/data/data/com.linecorp.LGRGS/shared_prefs"
        cache_dir = "/data/data/com.linecorp.LGRGS/cache"
        
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(1)
        
        # Total clear including cache (Restore to Full Clear)
        self.adb_shell(f"su -c 'rm -rf {base}/* && rm -rf {cache_dir}/*'")
        print(f"[{self.device_id}] Cleared shared_prefs + cache (Full)")

    # ---------------------------------------------------------
    # à¸ªà¹ˆà¸‡à¹„à¸Ÿà¸¥à¹Œà¹€à¸‚à¹‰à¸²à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ (à¹‚à¸«à¸¡à¸” "à¸„à¸±à¸”à¸¥à¸­à¸-à¸§à¸²à¸‡" à¹„à¸¡à¹ˆà¹ƒà¸Šà¹‰ adb push)
    # ---------------------------------------------------------
    def _remote_md5(self, remote_path):
        """md5 à¸‚à¸­à¸‡à¹„à¸Ÿà¸¥à¹Œà¸šà¸™à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ à¸«à¸£à¸·à¸­ None à¸–à¹‰à¸²à¸­à¹ˆà¸²à¸™à¹„à¸¡à¹ˆà¹„à¸”à¹‰"""
        try:
            r = self.adb_shell(f"su -c 'md5sum {remote_path} 2>/dev/null'", timeout=20)
            txt = ((r.stdout or b"") + b" ").decode("utf-8", "ignore").strip()
            tok = txt.split()[0].lower() if txt.split() else ""
            if len(tok) == 32 and all(c in "0123456789abcdef" for c in tok):
                return tok
        except Exception:
            pass
        return None

    def _write_remote_b64(self, data, remote_path, chunk=1200):
        """à¹€à¸‚à¸µà¸¢à¸™à¹„à¸Ÿà¸¥à¹Œà¸¥à¸‡à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¸”à¹‰à¸§à¸¢ echo base64 à¸—à¸µà¸¥à¸°à¸—à¹ˆà¸­à¸™ à¹à¸¥à¹‰à¸§ decode à¸šà¸™à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡

        à¸—à¸³à¹„à¸¡à¹„à¸¡à¹ˆà¹ƒà¸Šà¹‰ adb push: push à¹ƒà¸Šà¹‰ sync service à¸‚à¸­à¸‡ adb à¸‹à¸¶à¹ˆà¸‡à¸žà¸­à¹€à¸›à¸´à¸”à¸«à¸¥à¸²à¸¢à¸ˆà¸­à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™
        à¸ˆà¸°à¹à¸¢à¹ˆà¸‡à¸„à¸´à¸§à¸à¸±à¸™à¸ˆà¸™à¸„à¹‰à¸²à¸‡/à¸«à¸¥à¸¸à¸”à¸à¸¥à¸²à¸‡à¸—à¸²à¸‡ = "à¹„à¸Ÿà¸¥à¹Œà¹€à¸‚à¹‰à¸²à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¹€à¸¥à¸¢" à¸—à¸±à¹‰à¸‡à¸—à¸µà¹ˆà¹„à¸Ÿà¸¥à¹Œà¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸žà¸±à¸‡
        à¸§à¸´à¸˜à¸µà¸™à¸µà¹‰à¸ªà¹ˆà¸‡à¸œà¹ˆà¸²à¸™ adb shell à¸˜à¸£à¸£à¸¡à¸”à¸² (à¹„à¸Ÿà¸¥à¹Œ pref à¹à¸„à¹ˆ ~1 KB) à¹€à¸«à¸¡à¸·à¸­à¸™à¸žà¸´à¸¡à¸žà¹Œà¸§à¸²à¸‡à¹€à¸­à¸‡
        à¸„à¸·à¸™ True à¸–à¹‰à¸²à¹€à¸‚à¸µà¸¢à¸™à¸„à¸£à¸šà¹à¸¥à¸° md5 à¸•à¸£à¸‡à¸à¸±à¸šà¸•à¹‰à¸™à¸—à¸²à¸‡
        """
        b64 = base64.b64encode(data).decode("ascii")
        want_md5 = hashlib.md5(data).hexdigest()
        b64_path = remote_path + ".b64"
        try:
            r = self.adb_shell(f"rm -f {b64_path} {remote_path}", timeout=20)
            for i in range(0, len(b64), chunk):
                part = b64[i:i + chunk]
                # base64 à¸¡à¸µà¹à¸„à¹ˆ A-Za-z0-9+/= à¸ˆà¸¶à¸‡à¹„à¸¡à¹ˆà¸¡à¸µà¸­à¸±à¸à¸‚à¸£à¸°à¸—à¸µà¹ˆà¸—à¸³à¹ƒà¸«à¹‰ quote à¸žà¸±à¸‡
                r = self.adb_shell(f"echo -n '{part}' >> {b64_path}", timeout=25)
                if r.returncode != 0:
                    err = ((r.stderr or b"")).decode("utf-8", "ignore").strip()
                    print(f"[{self.device_id}] [PUT] à¹€à¸‚à¸µà¸¢à¸™à¸—à¹ˆà¸­à¸™à¸—à¸µà¹ˆ {i // chunk + 1} à¹„à¸¡à¹ˆà¸œà¹ˆà¸²à¸™: {err[:120]}")
                    return False
            # decode à¸šà¸™à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ (toybox base64 à¸à¹ˆà¸­à¸™ à¹„à¸¡à¹ˆà¸¡à¸µà¸„à¹ˆà¸­à¸¢ busybox)
            dec = self.adb_shell(
                f"base64 -d {b64_path} > {remote_path} 2>/dev/null || "
                f"busybox base64 -d {b64_path} > {remote_path}", timeout=30)
            got = self._remote_md5(remote_path)
            if got != want_md5:
                out = (((dec.stdout or b"") + (dec.stderr or b"")).decode("utf-8", "ignore")).strip()
                print(f"[{self.device_id}] [PUT] decode à¹à¸¥à¹‰à¸§ md5 à¹„à¸¡à¹ˆà¸•à¸£à¸‡ ({got} != {want_md5})"
                      + (f" | {out[:120]}" if out else ""))
                return False
            return True
        except Exception as e:
            print(f"[{self.device_id}] [PUT] à¸ªà¹ˆà¸‡à¹à¸šà¸š base64 à¹„à¸¡à¹ˆà¸ªà¸³à¹€à¸£à¹‡à¸ˆ: {e}")
            return False
        finally:
            try: self.adb_shell(f"rm -f {b64_path}", timeout=15)
            except Exception: pass

    def _put_remote_file(self, src, remote_path):
        """à¹€à¸­à¸²à¹„à¸Ÿà¸¥à¹Œ local à¹„à¸›à¸§à¸²à¸‡à¸—à¸µà¹ˆ remote_path à¹ƒà¸«à¹‰à¹„à¸”à¹‰ - à¸„à¸·à¸™ (ok, à¸‚à¸™à¸²à¸”à¹„à¸Ÿà¸¥à¹Œà¸•à¹‰à¸™à¸—à¸²à¸‡)

        à¸¥à¸³à¸”à¸±à¸š: base64-over-shell (à¸›à¸¥à¸­à¸”à¸ à¸±à¸¢à¸ªà¸¸à¸” à¹„à¸¡à¹ˆà¹à¸¢à¹ˆà¸‡ sync service) -> à¸–à¹‰à¸²à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸„à¹ˆà¸­à¸¢ adb push
        à¸ªà¸¥à¸±à¸šà¸¥à¸³à¸”à¸±à¸šà¹„à¸”à¹‰à¸”à¹‰à¸§à¸¢ config "inject_method": "shell" (à¸šà¸±à¸‡à¸„à¸±à¸š) / "push" (à¹à¸šà¸šà¹€à¸”à¸´à¸¡) / "auto"
        """
        try:
            with open(src, "rb") as f:
                data = f.read()
        except OSError as e:
            print(f"[{self.device_id}] à¸­à¹ˆà¸²à¸™à¹„à¸Ÿà¸¥à¹Œà¸•à¹‰à¸™à¸—à¸²à¸‡à¹„à¸¡à¹ˆà¹„à¸”à¹‰: {e}")
            return False, 0
        if not data:
            print(f"[{self.device_id}] à¹„à¸Ÿà¸¥à¹Œà¸•à¹‰à¸™à¸—à¸²à¸‡à¸§à¹ˆà¸²à¸‡à¹€à¸›à¸¥à¹ˆà¸² ({src}) - à¹„à¸¡à¹ˆ inject")
            return False, 0

        method = str(config.get("inject_method", "auto")).lower()
        limit = int(config.get("inject_shell_max_bytes", 262144))
        use_shell = method == "shell" or (method == "auto" and len(data) <= limit)

        with _inject_gate():
            if use_shell and self._write_remote_b64(data, remote_path):
                return True, len(data)

            # à¸ªà¸³à¸£à¸­à¸‡: adb push à¹à¸šà¸šà¹€à¸”à¸´à¸¡ (à¹„à¸Ÿà¸¥à¹Œà¹ƒà¸«à¸à¹ˆ à¸«à¸£à¸·à¸­à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¹„à¸¡à¹ˆà¸¡à¸µ base64)
            try:
                result = self.adb_run([self.adb_cmd, "-s", self.device_id, "push", src, remote_path], timeout=60)
                if result.returncode != 0:
                    err = result.stderr.decode("utf-8", errors="ignore") if result.stderr else "Unknown Error"
                    print(f"[{self.device_id}] [PUT] push à¹„à¸¡à¹ˆà¸œà¹ˆà¸²à¸™: {err.strip()[:200]}")
                    return False, len(data)
            except Exception as e:
                print(f"[{self.device_id}] [PUT] push error: {e}")
                return False, len(data)
        if self._remote_size(remote_path) != len(data):
            print(f"[{self.device_id}] [PUT] push à¹à¸¥à¹‰à¸§à¸‚à¸™à¸²à¸”à¹„à¸¡à¹ˆà¸•à¸£à¸‡")
            return False, len(data)
        return True, len(data)

    def _remote_size(self, remote_path):
        """à¸‚à¸™à¸²à¸”à¹„à¸Ÿà¸¥à¹Œà¸šà¸™à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ (à¹„à¸šà¸•à¹Œ) à¸«à¸£à¸·à¸­ None à¸–à¹‰à¸²à¹„à¸¡à¹ˆà¸¡à¸µà¹„à¸Ÿà¸¥à¹Œ/à¸­à¹ˆà¸²à¸™à¹„à¸¡à¹ˆà¹„à¸”à¹‰"""
        try:
            r = self.adb_shell(f"su -c 'stat -c %s {remote_path} 2>/dev/null || wc -c < {remote_path}'", timeout=15)
            txt = (r.stdout or b"").decode("utf-8", "ignore").strip()
            for tok in txt.split():
                if tok.isdigit():
                    return int(tok)
        except Exception:
            pass
        return None

    def inject_file(self, local_xml_path):
        print(f"[{self.device_id}] Injecting file (Robust Mode)...")

        # à¸›à¸¥à¸”à¸¥à¹‡à¸­à¸ Read-only (à¸–à¹‰à¸²à¸¡à¸µ)
        self.adb_shell("su -c 'mount -o remount,rw / 2>/dev/null || mount -o remount,rw /data 2>/dev/null'")

        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(2)

        self.adb_shell("su -c 'killall -9 com.linecorp.LGRGS 2>/dev/null || true'")
        sleep(1)

        src = os.path.abspath(local_xml_path)
        tmp = f"/data/local/tmp/temp_pref_{self.device_id.replace(':','_')}.xml"
        pkg_dir = "/data/data/com.linecorp.LGRGS"
        final_dir = f"{pkg_dir}/shared_prefs"
        final = f"{final_dir}/_LINE_COCOS_PREF_KEY.xml"

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                # 1) à¸§à¸²à¸‡à¹„à¸Ÿà¸¥à¹Œà¸¥à¸‡ /data/local/tmp à¸à¹ˆà¸­à¸™ (base64 à¸œà¹ˆà¸²à¸™ shell, à¸ªà¸³à¸£à¸­à¸‡à¸”à¹‰à¸§à¸¢ adb push)
                ok, local_size = self._put_remote_file(src, tmp)
                if not local_size:
                    return None                    # à¹„à¸Ÿà¸¥à¹Œà¸•à¹‰à¸™à¸—à¸²à¸‡à¸žà¸±à¸‡/à¸§à¹ˆà¸²à¸‡ - à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸¥à¸­à¸‡à¸‹à¹‰à¸³
                if not ok:
                    print(f"[{self.device_id}] Put attempt {attempt}: à¸ªà¹ˆà¸‡à¹„à¸Ÿà¸¥à¹Œà¹€à¸‚à¹‰à¸²à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¹„à¸¡à¹ˆà¸ªà¸³à¹€à¸£à¹‡à¸ˆ - à¸¥à¸­à¸‡à¹ƒà¸«à¸¡à¹ˆ")
                    sleep(2)
                    continue

                # 2) à¹à¸­à¸›à¸—à¸µà¹ˆà¹€à¸žà¸´à¹ˆà¸‡à¸–à¸¹à¸à¸¥à¹‰à¸²à¸‡à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸¡à¸µà¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œ shared_prefs -> cp à¸¥à¹‰à¸¡à¹€à¸‡à¸µà¸¢à¸š à¹† à¸ªà¸£à¹‰à¸²à¸‡à¹ƒà¸«à¹‰à¸à¹ˆà¸­à¸™
                self.adb_shell(
                    f"su -c 'mkdir -p {final_dir} && "
                    f"chown $(stat -c %u:%g {pkg_dir} 2>/dev/null || echo 1000:1000) {final_dir} && "
                    f"chmod 771 {final_dir}'", timeout=20)

                # 3) copy à¹€à¸‚à¹‰à¸²à¸—à¸µà¹ˆà¸ˆà¸£à¸´à¸‡ + à¸•à¸±à¹‰à¸‡à¸ªà¸´à¸—à¸˜à¸´à¹Œ/à¹€à¸ˆà¹‰à¸²à¸‚à¸­à¸‡à¹ƒà¸«à¹‰à¹€à¸«à¸¡à¸·à¸­à¸™à¹„à¸Ÿà¸¥à¹Œà¸—à¸µà¹ˆà¹à¸­à¸›à¸ªà¸£à¹‰à¸²à¸‡à¹€à¸­à¸‡
                shell_cmd = (
                    f"su -c '"
                    f"cp {tmp} {final} && "
                    f"chmod 666 {final} && "
                    f"chown $(stat -c %u:%g {final_dir} 2>/dev/null || stat -c %u:%g {pkg_dir} 2>/dev/null || echo 1000:1000) {final}"
                    f"'"
                )
                res = self.adb_shell(shell_cmd, timeout=20)
                out = ((res.stdout or b"") + (res.stderr or b"")).decode("utf-8", "ignore").strip()

                # 4) su à¸ªà¸³à¹€à¸£à¹‡à¸ˆ à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¹à¸›à¸¥à¸§à¹ˆà¸² cp à¸ªà¸³à¹€à¸£à¹‡à¸ˆ - à¸¢à¸·à¸™à¸¢à¸±à¸™à¸‚à¸™à¸²à¸” + md5 à¸à¹ˆà¸­à¸™à¸šà¸­à¸à¸§à¹ˆà¸²à¹€à¸‚à¹‰à¸²à¹à¸¥à¹‰à¸§
                final_size = self._remote_size(final)
                if final_size != local_size:
                    print(f"[{self.device_id}] Inject attempt {attempt}: à¹„à¸Ÿà¸¥à¹Œà¹„à¸¡à¹ˆà¹€à¸‚à¹‰à¸²/à¹„à¸¡à¹ˆà¸„à¸£à¸š "
                          f"(à¸šà¸™à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ {final_size} à¹„à¸šà¸•à¹Œ, à¸•à¹‰à¸™à¸—à¸²à¸‡ {local_size} à¹„à¸šà¸•à¹Œ)"
                          + (f" | {out[:200]}" if out else ""))
                    sleep(2)
                    continue

                remote_md5 = self._remote_md5(final)
                if remote_md5 is not None:
                    try:
                        with open(src, "rb") as _f:
                            local_md5 = hashlib.md5(_f.read()).hexdigest()
                    except OSError:
                        local_md5 = None
                    if local_md5 and remote_md5 != local_md5:
                        print(f"[{self.device_id}] Inject attempt {attempt}: md5 à¹„à¸¡à¹ˆà¸•à¸£à¸‡ "
                              f"({remote_md5} != {local_md5}) - à¸¥à¸­à¸‡à¹ƒà¸«à¸¡à¹ˆ")
                        sleep(2)
                        continue

                self.adb_shell(f"su -c 'rm -f {tmp}'", timeout=15)
                print(f"[{self.device_id}] Injection successful on attempt {attempt} ({local_size} à¹„à¸šà¸•à¹Œ)")
                _PUT_FAIL_STREAK[self.device_id] = 0   # success - reset streak
                return local_xml_path

            except Exception as e:
                print(f"[{self.device_id}] Attempt {attempt} error: {e}")
                sleep(2)

        print(f"[{self.device_id}] Injection FAILED after {max_retries} attempts!")
        # auto-recover: push à¸¥à¹‰à¸¡à¹€à¸«à¸¥à¸§à¸•à¸´à¸”à¸•à¹ˆà¸­à¸à¸±à¸™ -> emu/adb à¹€à¸™à¹ˆà¸² (md5 mismatch, ADB protocol corrupt)
        # 3 à¹„à¸Ÿà¸¥à¹Œà¸•à¸´à¸” -> reconnect adb ; 5 à¹„à¸Ÿà¸¥à¹Œà¸•à¸´à¸” -> adb reboot à¹€à¸‰à¸žà¸²à¸°à¸ˆà¸­à¸™à¸µà¹‰
        _PUT_FAIL_STREAK[self.device_id] = _PUT_FAIL_STREAK.get(self.device_id, 0) + 1
        streak = _PUT_FAIL_STREAK[self.device_id]
        try:
            if streak >= 5:
                print(f"[{self.device_id}] [RECOVER] push à¸¥à¹‰à¸¡ {streak} à¹„à¸Ÿà¸¥à¹Œà¸•à¸´à¸” - à¸ªà¸±à¹ˆà¸‡ reboot emu")
                subprocess.run([self.adb_cmd, "-s", self.device_id, "reboot"],
                               capture_output=True, timeout=15)
                _PUT_FAIL_STREAK[self.device_id] = 0   # reset à¸«à¸¥à¸±à¸‡ reboot (à¹ƒà¸«à¹‰à¸¥à¸­à¸‡à¹ƒà¸«à¸¡à¹ˆà¸«à¸¥à¸±à¸‡ boot à¹€à¸ªà¸£à¹‡à¸ˆ)
            elif streak == 3:
                print(f"[{self.device_id}] [RECOVER] push à¸¥à¹‰à¸¡ 3 à¹„à¸Ÿà¸¥à¹Œà¸•à¸´à¸” - à¸•à¹ˆà¸­ adb à¹ƒà¸«à¸¡à¹ˆ")
                subprocess.run([self.adb_cmd, "disconnect", self.device_id],
                               capture_output=True, timeout=10)
                sleep(1)
                subprocess.run([self.adb_cmd, "connect", self.device_id],
                               capture_output=True, timeout=10)
        except Exception as _e:
            print(f"[{self.device_id}] [RECOVER] error: {_e}")
        return None

    def first_loop_process(self):
        try:
            print(f"[{self.device_id}] Starting First Loop Process (Turbo Mode)...")
            self.clear_specific_shared_prefs()
            sleep(1.5)
            
            # 1. Ensure we are at Home screen
            self.adb_shell("input keyevent 3")
            sleep(0.5)

            # 2. Sequence 1
            print(f"[{self.device_id}] Processing SEQ 1...")
            res1 = self.process_sequence(self.seq1)
            if res1 == "restart": return "restart"
            if res1 == "complete": return "complete"
            if res1 == "failed": return "failed"
            
            # 3. Back logic - Speed Mode (Triple Back)
            print(f"[{self.device_id}] Back Speed Mode: Executing Triple Back...")
            sleep(1) # Reduced from 4s
            for _ in range(3):
                self.adb_shell("input keyevent 4")
                sleep(0.2)
            sleep(0.5)
            
            # 4. Sequence 2
            print(f"[{self.device_id}] Processing SEQ 2...")
            res2 = self.process_sequence(self.seq2)
            if res2 == "restart": return "restart"
            if res2 == "complete": return "complete"
            if res2 == "failed": return "failed"
            
            # 5. End and Close App
            print(f"[{self.device_id}] First Loop Finished. Clearing app...")
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
            sleep(0.5)
            return "complete"
            
        except Exception as e:
            print(f"[{self.device_id}] First Loop Error: {e}")
            return "error"

    def process_sequence(self, sequence):
        idx = 0
        for item in sequence:
            idx += 1
            # Check for global triggers before each item
            self.capture_screen()
            # Skip icon check if we are currently looking for icon.png in sequence 
            # OR if we are at the very beginning of the sequence (app still launching)
            skip_icon = (item == 'icon.png' or idx <= 3)
            err = self.check_error_images(skip_icon=skip_icon)
            if err == "fixcak": return "restart"
            if err in ["fixid", "apple", "fixunkown"]: return "restart"
            if err == "icon":
                print(f"[{self.device_id}] App closed/crashed! Relaunching with am start...")
                self.open_app()
                return "restart"
            if err == "stopcheck": return "complete"

            if isinstance(item, tuple):
                print(f"[{self.device_id}] Tapping: {item}")
                self.tap(item[0], item[1])
                sleep(1.5) # Wait for checkbox animation
                continue
            
            if isinstance(item, str) and item.startswith('@'):
                checkpoint_img = item[1:]
                if not checkpoint_img.startswith('img'):
                    checkpoint_img = f"img/{checkpoint_img}"
                print(f"[{self.device_id}] Checkpoint: waiting for {checkpoint_img} (no click)")
                start_wait = time.time()
                while True:
                    if time.time() - start_wait > 480: # 8 minutes timeout
                        print(f"[{self.device_id}] TIMEOUT waiting for checkpoint {checkpoint_img}. Restarting first_loop...")
                        return "restart"

                    self.capture_screen()
                    
                    # ---- Check floating popups on every iteration ----
                    self.check_floating_popups()
                    # --------------------------------------------------
                    
                    err = self.check_error_images(skip_icon=skip_icon)
                    if err == "fixcak": return "restart"
                    if err in ["fixid", "apple", "fixunkown"]: return "restart"
                    if err == "fixbug":
                        self.click("img/fixbuglogin.png")
                        return "restart"
                    if err == "unkhow":
                        self.click("img/unkhow.png")
                        return "restart"
                    if err == "icon":
                        print(f"[{self.device_id}] App closed/crashed! Relaunching with am start...")
                        self.open_app()
                        return "restart"
                    if err == "stopcheck": return "complete"
                    
                    if self.exists_in_cache(checkpoint_img, similarity=0.95):
                        print(f"[{self.device_id}] Checkpoint reached: {checkpoint_img}")
                        break
                    sleep(self.loop_delay(0.3))   # was 0.3
                sleep(0.3)
                continue
                
            img_path = f"img/{item}" if isinstance(item, str) and not item.startswith('img') else item
            
            if item == 'icon.png':
                print(f"[{self.device_id}] Opening app via am start (instead of icon click)...")
                self.open_app()
                print(f"[{self.device_id}] App launched, waiting 4s...")
                sleep(4)
                continue

            # Handle standard click for apple.png as a regular sequence item
            # The global check_critical_errors (via check_error_images) will handle any popups.
            if item == 'apple.png':
                self.click("img/apple.png")
                sleep(2)
                continue

            print(f"[{self.device_id}] Waiting for {item}...")
            start_wait = time.time()
            
            # Custom timeout for specific images
            item_timeout = 480
            if item in ['box6.png', 'end_box.png']:
                item_timeout = 5

            while True:
                if time.time() - start_wait > item_timeout:
                    if item in ['box6.png', 'end_box.png']:
                        print(f"[{self.device_id}] Timeout 5s for {item}, skipping to next step.")
                        break # Continue to next item in sequence
                    print(f"[{self.device_id}] TIMEOUT waiting for {item}. Restarting first_loop...")
                    return "restart"

                # Check fixcak/stopcheck/blackscreen/fixbug/unkhow
                self.capture_screen() # Ensure screen is captured before checking errors
                
                # ---- Check floating popups on every iteration ----
                self.check_floating_popups()
                # --------------------------------------------------
                
                err = self.check_error_images()
                if err == "fixcak":
                    print(f"[{self.device_id}] Found fixcak.png! Restarting first loop...")
                    return "restart"
                if err == "fixbug":
                    print(f"[{self.device_id}] Found fixbuglogin.png! Clicking and restarting...")
                    self.click("img/fixbuglogin.png")
                    return "restart"
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
                
                pos = self._find_in_screen(img_path)
                if pos:
                    print(f"[{self.device_id}] Found {item}, clicking...")
                    self.click(pos)
                    sleep(0.3) # Fast transition for images
                    break
                sleep(self.loop_delay(0.2)) # Fast loop search
            
        return "success"



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
        # à¹€à¸žà¸”à¸²à¸™ nav_timeout à¸§à¸´ - à¹€à¸”à¸´à¸¡à¸¥à¸¹à¸›à¸™à¸µà¹‰à¹„à¸¡à¹ˆà¸¡à¸µà¹€à¸žà¸”à¸²à¸™à¹€à¸¥à¸¢ à¸–à¹‰à¸² sec1/sec2 à¹„à¸¡à¹ˆà¹‚à¸œà¸¥à¹ˆ
        # (à¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”/à¸ˆà¸­à¸„à¹‰à¸²à¸‡/à¹à¸­à¸›à¹€à¸”à¹‰à¸‡) thread à¸ˆà¸°à¸§à¸™à¸•à¸£à¸‡à¸™à¸µà¹‰à¸•à¸¥à¸­à¸”à¸à¸²à¸¥à¸—à¸±à¹‰à¸‡à¸—à¸µà¹ˆà¸¢à¸±à¸‡à¸–à¸·à¸­ lock à¹„à¸Ÿà¸¥à¹Œà¸­à¸¢à¸¹à¹ˆ
        nav_timeout = config.get("nav_timeout", 180)
        print(f"[{self.device_id}] Starting persistent navigation (Searching for sec1/sec2, à¹€à¸žà¸”à¸²à¸™ {nav_timeout} à¸§à¸´)...")
        sec1_clicked = False
        nav_deadline = time.time() + nav_timeout
        while True:
            if time.time() > nav_deadline:
                print(f"[{self.device_id}] [NAVI] à¸«à¸² sec1/sec2 à¹„à¸¡à¹ˆà¹€à¸ˆà¸­à¹ƒà¸™ {nav_timeout} à¸§à¸´ - à¸¢à¸à¹€à¸¥à¸´à¸ find-ranger à¸£à¸­à¸šà¸™à¸µà¹‰")
                return results
            self.capture_screen()

            # ---- Check floating popups ----
            self.check_floating_popups()
            # --------------------------------
            
            # Check for crash while waiting (à¹ƒà¸Šà¹‰ pidof à¹à¸—à¸™ icon.png)
            try:
                pid_result = subprocess.run(
                    [self.adb_cmd, "-s", self.device_id, "shell", "pidof", "com.linecorp.LGRGS"],
                    capture_output=True, text=True, timeout=5
                )
                if not pid_result.stdout.strip():
                    print(f"[{self.device_id}] App crashed, relaunching...")
                    self.open_app()
                    sleep(5)
                    sec1_clicked = False
            except:
                pass

            # Check if we are already at sec2
            if self.exists_in_cache("img/sec2.png", similarity=0.95):
                print(f"[{self.device_id}] Reached search screen (sec2), clicking to confirm...")
                self.click("img/sec2.png")
                break
                
            # Try clicking sec1 only once
            if not sec1_clicked and self.exists_in_cache("img/sec1.png", similarity=0.95):
                print(f"[{self.device_id}] Found sec1, clicking once then waiting for sec2...")
                self.click("img/sec1.png")
                sec1_clicked = True
                sleep(1) # Brief wait after click
            
            # If nothing found or already clicked sec1, just wait and loop again
            sleep(0.3)
            
        print(f"[{self.device_id}] Reached search screen successfully.")
        sleep(0.2)
        
        # Loop through each character
        for i, character in enumerate(self.characters):
            print(f"\n[{self.device_id}] --- Character {i+1}/{len(self.characters)}: {character} ---")
            
            # 0. Safety Check: Close popups like Detail window if it accidentally opened
            if self.exists_in_cache("img/cancelsec.png", similarity=0.9):
                print(f"[{self.device_id}] Recovery: Closing detail popup (cancelsec.png)")
                self.click("img/cancelsec.png")
                sleep(0.5)

            # a) Tap search box position first
            print(f"[{self.device_id}] Tapping search box (388, 288)")
            self.tap(388, 288)
            sleep(0.3) # Increased to wait for keyboard
            
            # b) Type character name
            print(f"[{self.device_id}] Typing: {character}")
            self.type_text(character)
            sleep(0.2)
            # Auto-Enter to dismiss keyboard so sec3 is visible
            self.adb_shell("input keyevent 66") 
            sleep(0.6) # Wait for keyboard to disappear and UI to settle
            
            # c) Click sec3
            print(f"[{self.device_id}] Clicking sec3.png")
            if not self.wait_and_click_image("sec3.png", timeout=15, similarity=0.95):
                print(f"[{self.device_id}] Failed to find sec3, skipping character")
                continue
            sleep(0.3) # Wait for animation
            
            # d) Click sec4
            print(f"[{self.device_id}] Clicking sec4.png")
            if not self.wait_and_click_image("sec4.png", timeout=15, similarity=0.95):
                print(f"[{self.device_id}] Failed to find sec4, skipping character")
                continue
            
            # Add longer wait for search results to appear fully
            print(f"[{self.device_id}] Waiting 1.0s for results...")
            sleep(1.0)
            
            # e) Scan ranger images with RETRY (to be sure)
            current_found_in_iteration = False
            # Revert to full folder scan as requested ("à¸‚à¸­à¹à¸šà¸šà¹€à¸”à¸´à¸¡à¹€à¸¥à¸¢")
            matching_files = self.ranger_files

            for attempt in range(2):
                if attempt > 0:
                    print(f"[{self.device_id}] Retry scanning ranger (Attempt {attempt+1})...")
                    sleep(0.3)
                    
                self.capture_screen()
                self.check_floating_popups()
                
                for ranger_img in matching_files:
                    ranger_path = f"img/{ranger_img}"
                    # Use very high similarity 0.95 for strict matching (Original images)
                    if self.exists_in_cache(ranger_path, similarity=0.95):
                        # Get base filename
                        file_base = ranger_img.split('/')[-1].replace(".png", "")
                        found_hero_name = file_base
                            
                        # Get folder name from config or default to found_hero_name
                        if isinstance(self.ranger_image_mapping, dict) and ranger_img in self.ranger_image_mapping:
                            data = self.ranger_image_mapping[ranger_img]
                            if isinstance(data, dict):
                                hero_name = data.get("hero", found_hero_name)
                                folder_name = data.get("folder", hero_name)
                            else:
                                hero_name = found_hero_name
                                folder_name = str(data)
                        else:
                            hero_name = found_hero_name
                            folder_name = hero_name
                        
                        results[hero_name] = folder_name
                        current_found_in_iteration = True
                        print(f"[{self.device_id}] Found ranger: {ranger_img} -> hero: {hero_name}, folder: {folder_name}")
                
                if current_found_in_iteration:
                    break # Stop retrying if found
            
            if current_found_in_iteration:
                print(f"[{self.device_id}] Iteration results: {results}")
            else:
                print(f"[{self.device_id}] No rangers found for character: {character}")
            
            # f) Click sec5 (Close)
            print(f"[{self.device_id}] Clicking sec5.png")
            if not self.wait_and_click_image("sec5.png", timeout=15, similarity=0.95):
                print(f"[{self.device_id}] Failed to find sec5, continuing")
            sleep(0.6) # Give time for search results to close
            
            # g) Click sec2 again for next character (if not last)
            if i < len(self.characters) - 1:
                # Extra check for Detail window before next
                if self.exists_in_cache("img/cancelsec.png", similarity=0.9):
                    self.click("img/cancelsec.png")
                    sleep(0.5)

                print(f"[{self.device_id}] Waiting 0.5s for UI to settle before sec2...")
                sleep(0.5)
                print(f"[{self.device_id}] Clicking sec2.png to start search for next character...")
                if not self.wait_and_click_image("sec2.png", timeout=15, similarity=0.95):
                    print(f"[{self.device_id}] CRITICAL: Failed to find sec2 for next iteration. Search might be blocked.")
                    break
                sleep(0.5) # Wait for input box to open
        
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
        
        # à¸§à¸´à¸˜à¸µà¸—à¸µà¹ˆà¹„à¸”à¹‰à¸œà¸¥ 100%: cp à¹„à¸› /data/local/tmp â†’ chmod â†’ pull
        safe_dev = self.device_id.replace(":", "_")
        temp_remote = f"/data/local/tmp/backup_{safe_dev}.xml"
        
        try:
            self.adb_shell(f"su -c 'cp {source_path} {temp_remote}'")
            self.adb_shell(f"su -c 'chmod 666 {temp_remote}'")
            
            if results:
                # Build folder name from folder values
                folder_parts = sorted(set(results.values()))
                folder_name = "+".join(folder_parts)
                
                backup_dir = os.path.join("backup-id", folder_name)
                if not os.path.exists(backup_dir):
                    os.makedirs(backup_dir)
                
                dst = os.path.join(backup_dir, filename)
                result = subprocess.run(
                    [self.adb_cmd, '-s', self.device_id, 'pull', temp_remote, dst],
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
                    [self.adb_cmd, '-s', self.device_id, 'pull', temp_remote, dst],
                    capture_output=True, text=True
                )
                
                if result.returncode == 0:
                    print(f"[{self.device_id}] Backed up to not-found: {dst}")
                else:
                    print(f"[{self.device_id}] Backup failed: {result.stderr}")
            
            # Cleanup temp
            self.adb_shell(f"rm -f {temp_remote}")
        except Exception as e:
            print(f"[{self.device_id}] Backup error: {e}")

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
        
        # Phase 1: Navigation with Home-screen recovery
        print(f"[{self.device_id}] Navigating to Gear screen...")
        
        # 1. Back to home screen if needed (press Back until findgear1.png or findgear2.png is visible)
        for i in range(8):
             self.capture_screen()
             if self.exists_in_cache("img/findgear1.png") or self.exists_in_cache("img/findgear2.png"):
                 print(f"[{self.device_id}] [NAVI-GEAR] At Gear-accessible screen.")
                 break
             print(f"[{self.device_id}] [NAVI-GEAR] Not at Gear screen (attempt {i+1}/8), pressing BACK...")
             self.adb_shell("input keyevent 4")
             sleep(0.5)
             self.capture_screen()
             if self.exists_in_cache("img/cancel.png"):
                 self.click("img/cancel.png")
                 sleep(0.3)

        # 2. Click findgear1.png if visible (Main menu Gear button)
        self.capture_screen()
        if self.exists_in_cache("img/findgear1.png"):
            if not self.wait_and_click_image("findgear1.png", timeout=10):
                print(f"[{self.device_id}] Failed to click findgear1.png")
                return set()
            sleep(0.5)
        
        # 3. Click findgear2.png (Gear inventory tab)
        if not self.wait_and_click_image("findgear2.png", timeout=15):
            print(f"[{self.device_id}] Failed to find findgear2.png")
            return set()
        
        # 4. Click findgear3.png (Ranger gear button)
        if not self.wait_and_click_image("findgear3.png", timeout=15):
            print(f"[{self.device_id}] Failed to find findgear3.png")
            return set()

        # à¸£à¸­à¸ˆà¸­ Gear à¹‚à¸«à¸¥à¸”à¸ˆà¸£à¸´à¸‡à¸à¹ˆà¸­à¸™à¹€à¸£à¸´à¹ˆà¸¡à¹€à¸Šà¹‡à¸„: à¸«à¸² weapons1/weapons2 à¹„à¸›à¹€à¸£à¸·à¹ˆà¸­à¸¢ à¹†
        # à¹€à¸ˆà¸­à¸•à¸±à¸§à¹ƒà¸”à¸•à¸±à¸§à¸«à¸™à¸¶à¹ˆà¸‡ = à¸ˆà¸­à¸¡à¸²à¹à¸¥à¹‰à¸§ à¸„à¹ˆà¸­à¸¢à¹€à¸£à¸´à¹ˆà¸¡à¸«à¸² checkgear2
        # à¸à¸±à¸™à¹€à¸„à¸ªà¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”/à¸ˆà¸­à¹‚à¸«à¸¥à¸”à¸Šà¹‰à¸²à¹à¸¥à¹‰à¸§à¸£à¸µà¸šà¸ªà¸£à¸¸à¸›à¸§à¹ˆà¸²à¹„à¸¡à¹ˆà¸¡à¸µà¸‚à¸­à¸‡ à¸£à¸°à¸«à¸§à¹ˆà¸²à¸‡à¸£à¸­à¹€à¸„à¸¥à¸µà¸¢à¸£à¹Œà¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹ƒà¸«à¹‰
        # à¹€à¸žà¸”à¸²à¸™ gear_wait_timeout à¸§à¸´ - à¹€à¸”à¸´à¸¡à¹€à¸›à¹‡à¸™ while True à¹€à¸›à¸¥à¹ˆà¸² à¹† (à¸„à¸­à¸¡à¹€à¸¡à¸™à¸•à¹Œà¹€à¸‚à¸µà¸¢à¸™à¹„à¸§à¹‰à¹€à¸­à¸‡à¸§à¹ˆà¸²
        # "à¹„à¸¡à¹ˆà¸¡à¸µ timeout") à¸žà¸­ weapons1/weapons2 à¹„à¸¡à¹ˆà¸¡à¸²à¸ªà¸±à¸à¸—à¸µ thread à¸„à¹‰à¸²à¸‡à¸•à¸£à¸‡à¸™à¸µà¹‰à¸•à¸¥à¸­à¸”à¸à¸²à¸¥
        # à¸—à¸±à¹‰à¸‡à¸—à¸µà¹ˆà¸¢à¸±à¸‡à¸–à¸·à¸­ lock à¸‚à¸­à¸‡à¹„à¸Ÿà¸¥à¹Œà¸­à¸¢à¸¹à¹ˆ = à¸šà¸­à¸—à¸”à¸¹à¹€à¸«à¸¡à¸·à¸­à¸™à¸«à¸¢à¸¸à¸”à¸—à¸³à¸‡à¸²à¸™ à¹à¸•à¹ˆà¹„à¸Ÿà¸¥à¹Œà¸¢à¸±à¸‡à¸„à¹‰à¸²à¸‡à¹ƒà¸™ backup/
        gear_wait_timeout = config.get("gear_wait_timeout", 120)
        print(f"[{self.device_id}] [GEAR-WAIT] à¸£à¸­ weapons1/weapons2 à¹‚à¸œà¸¥à¹ˆà¸à¹ˆà¸­à¸™à¹€à¸£à¸´à¹ˆà¸¡à¹€à¸Šà¹‡à¸„à¹€à¸à¸µà¸¢à¸£à¹Œ (à¹€à¸žà¸”à¸²à¸™ {gear_wait_timeout} à¸§à¸´)...")
        gear_wait_rounds = 0
        gear_wait_deadline = time.time() + gear_wait_timeout
        while True:
            if time.time() > gear_wait_deadline:
                print(f"[{self.device_id}] [GEAR-WAIT] weapons1/weapons2 à¹„à¸¡à¹ˆà¸¡à¸²à¹ƒà¸™ {gear_wait_timeout} à¸§à¸´ - à¹„à¸›à¸•à¹ˆà¸­à¸”à¹‰à¸§à¸¢ checkgear2 à¹à¸—à¸™ (à¹„à¸¡à¹ˆà¸„à¹‰à¸²à¸‡à¸£à¸­à¸–à¸²à¸§à¸£)")
                break
            self.capture_screen()
            if (self.exists_in_cache("img/weapons1.png", similarity=0.9)
                    or self.exists_in_cache("img/weapons2.png", similarity=0.9)):
                print(f"[{self.device_id}] [GEAR-WAIT] à¸ˆà¸­ Gear à¸žà¸£à¹‰à¸­à¸¡à¹à¸¥à¹‰à¸§ - à¹€à¸£à¸´à¹ˆà¸¡à¹€à¸Šà¹‡à¸„à¹€à¸à¸µà¸¢à¸£à¹Œ")
                break
            self.check_floating_popups()
            gear_wait_rounds += 1
            if gear_wait_rounds % 30 == 0:
                print(f"[{self.device_id}] [GEAR-WAIT] à¸¢à¸±à¸‡à¸£à¸­ weapons1/weapons2 à¸­à¸¢à¸¹à¹ˆ ({gear_wait_rounds} à¸£à¸­à¸š)")
            sleep(0.5)

        # Step 2: Read gear names with OCR (Linear, one-way scan)
        print(f"\n[{self.device_id}] Starting streamlined gear OCR check...")
        all_found_gears = set()
        
        # 1. Try initial screen scan (checkgear2/3 point)
        print(f"[{self.device_id}] [GEAR] Phase 1: checkgear2 -> checkgear3...")
        checkgear2_ok = self.wait_and_click_image("checkgear2.png", timeout=8, similarity=0.92)
        if not checkgear2_ok:
            # à¹€à¸›à¸´à¸”à¸«à¸™à¹‰à¸²à¸£à¸²à¸¢à¸à¸²à¸£ gear à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™à¹€à¸¥à¸¢ - à¸ªà¹ˆà¸§à¸™à¹ƒà¸«à¸à¹ˆà¸„à¸·à¸­à¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”/à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¸šà¸±à¸‡à¸•à¸­à¸™
            # à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™à¸ˆà¸­ (fixnet à¹€à¸”à¹‰à¸‡) - à¹€à¸„à¸¥à¸µà¸¢à¸£à¹Œà¸›à¹Šà¸­à¸›à¸­à¸±à¸ž à¸£à¸­à¹€à¸à¸¡à¹‚à¸«à¸¥à¸” à¹à¸¥à¹‰à¸§à¹€à¸”à¸´à¸™à¹€à¸‚à¹‰à¸²à¹ƒà¸«à¸¡à¹ˆ
            # à¸­à¸µà¸à¸¢à¸à¹€à¸”à¸µà¸¢à¸§à¸à¹ˆà¸­à¸™à¸¢à¸­à¸¡à¸ªà¸£à¸¸à¸›à¸§à¹ˆà¸²à¹„à¸¡à¹ˆà¸¡à¸µ gear à¹„à¸¡à¹ˆà¸‡à¸±à¹‰à¸™à¹„à¸Ÿà¸¥à¹Œà¹‚à¸”à¸™à¸•à¸±à¸”à¸ªà¸´à¸™à¸œà¸´à¸”à¹€à¸žà¸£à¸²à¸°à¹€à¸™à¹‡à¸•à¸ªà¸°à¸”à¸¸à¸”
            print(f"[{self.device_id}] [GEAR] checkgear2 à¹„à¸¡à¹ˆà¸¡à¸² (à¹€à¸™à¹‡à¸•à¸«à¸¥à¸¸à¸”/à¸›à¹Šà¸­à¸›à¸­à¸±à¸ž?) - à¸¥à¸­à¸‡à¹€à¸‚à¹‰à¸²à¸«à¸™à¹‰à¸² gear à¹ƒà¸«à¸¡à¹ˆà¸­à¸µà¸à¸¢à¸")
            self.capture_screen()
            self.check_floating_popups()
            sleep(3)
            self.wait_and_click_image("findgear2.png", timeout=10)
            self.wait_and_click_image("findgear3.png", timeout=10)
            checkgear2_ok = self.wait_and_click_image("checkgear2.png", timeout=10, similarity=0.92)
        if checkgear2_ok:
            if self.wait_and_click_image("checkgear3.png", timeout=10, similarity=0.92):
                print(f"[{self.device_id}] [GEAR] Detailed view opened, scanning...")
                all_found_gears.update(self.check_gear_by_text())
                sleep(0.5)
        
        # 2. Sequential tab scan (Always move forward and scan all steps)
        # We explicitly wait and click each tab to ensure they are visited
        gear_tabs = ["weapons1.png", "weapons2.png"]
        for tab_img in gear_tabs:
            print(f"[{self.device_id}] [GEAR] Attempting to access tab: {tab_img}...")
            # Use lower similarity for tab buttons as they might be partially obscured or highlighted
            if self.wait_and_click_image(tab_img, timeout=10, similarity=0.90):
                print(f"[{self.device_id}] [GEAR] Tab {tab_img} opened, waiting for content...")
                sleep(1.2) # Increased to ensure gear icons load fully
                self.capture_screen()
                self.check_floating_popups()
                all_found_gears.update(self.check_gear_by_text())
                sleep(0.3)
            else:
                print(f"[{self.device_id}] [GEAR] Warning: Failed to find/click tab {tab_img}")
        
        # Return gear results (will be combined with ranger results in main_login)
        print(f"\n[{self.device_id}] Gear scan done. Found: {all_found_gears if all_found_gears else 'none'}")
        return all_found_gears

    def backup_to_not_found(self, filename, source_path):
        """Backup pref file to not-found folder (à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™ prefix à¸Šà¸·à¹ˆà¸­à¸®à¸µà¹‚à¸£à¹ˆ -> noherofound)"""
        not_found_dir = "not-found"
        if not os.path.exists(not_found_dir):
            os.makedirs(not_found_dir)

        # à¹„à¸¡à¹ˆà¹€à¸ˆà¸­à¸®à¸µà¹‚à¸£à¹ˆ -> à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™ prefix à¸Šà¸·à¹ˆà¸­à¸®à¸µà¹‚à¸£à¹ˆà¹€à¸›à¹‡à¸™ noherofound (à¸„à¸‡ ruby[]+ticket[] à¸‚à¹‰à¸²à¸‡à¸«à¸™à¹‰à¸²à¹„à¸§à¹‰)
        import re
        # à¹à¸¢à¸à¸ªà¹ˆà¸§à¸™ tag ruby[]+ticket[] à¸‚à¹‰à¸²à¸‡à¸«à¸™à¹‰à¸²à¸­à¸­à¸à¸à¹ˆà¸­à¸™
        mtag = re.match(r'^((?:ruby\[[^\]]*\]\+)?(?:ticket\[[^\]]*\]\+)?)(.*)$', filename)
        tag_prefix, rest = mtag.group(1), mtag.group(2)
        # account id à¸‚à¸¶à¹‰à¸™à¸•à¹‰à¸™à¸”à¹‰à¸§à¸¢à¸•à¸±à¸§à¹€à¸¥à¸‚à¹€à¸ªà¸¡à¸­, prefix à¹€à¸›à¹‡à¸™à¸•à¸±à¸§à¸­à¸±à¸à¸©à¸£ -> à¸•à¸±à¸”à¸•à¸±à¸§à¸­à¸±à¸à¸©à¸£à¸™à¸³à¸«à¸™à¹‰à¸²à¸­à¸­à¸
        m = re.match(r'^(?:\(D\d+\))?[A-Za-z]*(\d.*)$', rest)
        if m:
            rest = "noherofound" + m.group(1)
        filename = tag_prefix + rest

        backup_path = os.path.join(not_found_dir, filename)
        
        # à¸§à¸´à¸˜à¸µà¸—à¸µà¹ˆà¹„à¸”à¹‰à¸œà¸¥ 100%: cp à¹„à¸› /data/local/tmp â†’ chmod â†’ pull
        safe_dev = self.device_id.replace(":", "_")
        temp_remote = f"/data/local/tmp/backup_{safe_dev}.xml"
        
        try:
            self.adb_shell(f"su -c 'cp {source_path} {temp_remote}'")
            self.adb_shell(f"su -c 'chmod 666 {temp_remote}'")
            result = subprocess.run(
                [self.adb_cmd, '-s', self.device_id, 'pull', temp_remote, backup_path],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"[{self.device_id}] Backed up to not-found: {backup_path}")
            else:
                print(f"[{self.device_id}] Backup failed: {result.stderr}")
            # Cleanup temp
            self.adb_shell(f"rm -f {temp_remote}")
        except Exception as e:
            print(f"[{self.device_id}] Backup error: {e}")

    def clear_and_restart(self):
        """Clear app and prepare for next file"""
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(0.5)

    # =========================================================
    # Main Login
    # =========================================================
    def main_login(self, current_filename):
        print(f"[{self.device_id}] Starting Main Login...")
        self._login_fixid_count = 0  # Reset fixid counter for each new ID
        self._fixid_seen = False
        self._wg_net_hits = 0
        self._wg_recover_n = 0       # à¹‚à¸„à¸§à¸•à¸²à¹€à¸„à¸¥à¸µà¸¢à¸£à¹Œà¹à¸­à¸›+à¸›à¸´à¸”/à¹€à¸›à¸´à¸” VPN à¹€à¸¡à¸·à¹ˆà¸­à¹€à¸ˆà¸­ Unstable network (à¸•à¹ˆà¸­à¹„à¸­à¸”à¸µ)
        
        # Clear app
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(0.5)
        
        # à¹€à¸›à¸´à¸”à¹à¸­à¸›à¸”à¹‰à¸§à¸¢ am start (à¹€à¸£à¹‡à¸§à¸à¸§à¹ˆà¸²à¹à¸¥à¸°à¹€à¸ªà¸–à¸µà¸¢à¸£à¸à¸§à¹ˆà¸²à¸„à¸¥à¸´à¸ icon.png)
        self.open_app()
        sleep(1)
        
        # === Black Screen Check à¸«à¸¥à¸±à¸‡à¹€à¸›à¸´à¸”à¹à¸­à¸ž (15 à¸§à¸´ à¸–à¹‰à¸²à¸¢à¸±à¸‡à¸”à¸³/à¹€à¸—à¸² > 80% â†’ clear + restart) ===
        for black_attempt in range(3):  # à¸¥à¸­à¸‡à¹„à¸”à¹‰ 3 à¸„à¸£à¸±à¹‰à¸‡
            black_start = time.time()
            is_stuck = False
            while time.time() - black_start < 10:
                self.capture_screen()
                if self._screen is not None:
                    try:
                        _, thresh = cv2.threshold(self._screen, 50, 255, cv2.THRESH_BINARY_INV)
                        num_black = cv2.countNonZero(thresh)
                        total = self._screen.shape[0] * self._screen.shape[1]
                        black_ratio = num_black / total
                        if black_ratio < 0.85:
                            # à¸ˆà¸­à¸ªà¸§à¹ˆà¸²à¸‡à¹à¸¥à¹‰à¸§ (>15% pixels not black)
                            print(f"[{self.device_id}] [BLACK] Screen OK! (app loaded)")
                            is_stuck = False
                            break
                        else:
                            is_stuck = True
                    except:
                        is_stuck = True
                else:
                    is_stuck = True
                sleep(0.5)
            
            if is_stuck:
                print(f"[{self.device_id}] [BLACK] Dark screen 15s after launch! (attempt {black_attempt+1}/3) Clearing...")
                self._wg_strike("à¸ˆà¸­à¸”à¸³à¸«à¸¥à¸±à¸‡à¹€à¸›à¸´à¸”à¹€à¸à¸¡")
                self.clear_and_restart()
                self.open_app()
                sleep(1)
            else:
                break  # à¹à¸­à¸žà¹‚à¸«à¸¥à¸”à¸ªà¸³à¹€à¸£à¹‡à¸ˆ à¸­à¸­à¸à¸ˆà¸²à¸ loop
            
        loop_count = 0
        status = "unknown"
        event_passed = False  # à¸«à¸¥à¸±à¸‡à¹€à¸ˆà¸­ event.png à¹à¸¥à¹‰à¸§à¸«à¸¢à¸¸à¸”à¹€à¸Šà¹‡à¸„ fixok
        event_popup_count = 0  # à¸à¸±à¸™ event popup à¹€à¸”à¹‰à¸‡à¸§à¸™à¹„à¸¡à¹ˆà¸ˆà¸š (à¸ˆà¸³à¸à¸±à¸”à¸ˆà¸³à¸™à¸§à¸™à¸„à¸£à¸±à¹‰à¸‡à¸—à¸µà¹ˆà¸à¸”)
        
        while True:
            loop_count += 1
            if loop_count % 5 == 0:
                print(f"[{self.device_id}] Login loop iteration {loop_count}")

            self.capture_screen()

            # === à¹€à¸Šà¹‡à¸„à¸§à¹ˆà¸²à¹€à¸à¸¡à¸¢à¸±à¸‡à¸£à¸±à¸™à¸­à¸¢à¸¹à¹ˆà¸ˆà¸£à¸´à¸‡à¹„à¸«à¸¡ (à¸—à¸¸à¸à¸£à¸­à¸š) ===
            try:
                pid_result = subprocess.run(
                    [self.adb_cmd, "-s", self.device_id, "shell", "pidof", "com.linecorp.LGRGS"],
                    capture_output=True, text=True, timeout=5
                )
                if not pid_result.stdout.strip():
                    print(f"[{self.device_id}] [CRASH] App not running! Relaunching...")
                    self.open_app()
                    sleep(5)
                    continue
            except:
                pass

            # ===== FLOATING POPUP CHECKS (à¸à¸”à¹à¸¥à¹‰à¸§à¸—à¸³à¸‡à¸²à¸™à¸•à¹ˆà¸­) =====
            # checkline.png: à¸¥à¸³à¸”à¸±à¸šà¹€à¸Šà¹‡à¸„à¸šà¸¥à¹‡à¸­à¸à¸žà¸´à¹€à¸¨à¸©
            if self.exists_in_cache("img/checkline.png"):
                self.check_floating_popups()
                continue

            # fixnetv2.png: à¹€à¸ˆà¸­à¸à¹‡à¸à¸” à¹à¸¥à¹‰à¸§à¸£à¸­à¸à¸” fixnetv2ok.png
            if self.exists_in_cache("img/fixnetv2.png", similarity=0.8):
                print(f"[{self.device_id}] [POPUP] fixnetv2.png detected in login loop, clicking...")
                self.click("img/fixnetv2.png", similarity=0.8)
                sleep(0.5)
                self.capture_screen()
                if self.exists_in_cache("img/fixnetv2ok.png", similarity=0.8):
                    self.click("img/fixnetv2ok.png", similarity=0.8)
                    sleep(0.3)
                continue

            # fixplay.png (PLAY): à¹€à¸Šà¹‡à¸„à¸•à¸¥à¸­à¸”à¹€à¸«à¸¡à¸·à¸­à¸™ fixnet - capture_screen() à¹€à¸„à¸¥à¸µà¸¢à¸£à¹Œà¹ƒà¸«à¹‰à¹à¸¥à¹‰à¸§à¸—à¸²à¸‡ NET_POPUPS
            # (à¸à¸”à¸‹à¹‰à¸³à¸ˆà¸™à¸«à¸²à¸¢ à¹à¸¥à¹‰à¸§à¸£à¸­à¸à¸” check-ok1.png à¸•à¹ˆà¸­) à¸•à¸£à¸‡à¸™à¸µà¹‰à¹€à¸œà¸·à¹ˆà¸­à¸«à¸¥à¸¸à¸”à¸¡à¸²à¸–à¸¶à¸‡ à¸ªà¹ˆà¸‡à¹€à¸‚à¹‰à¸²à¸—à¸²à¸‡à¹€à¸”à¸µà¸¢à¸§à¸à¸±à¸™
            if self.exists_in_cache("img/fixplay.png", similarity=0.8) and not getattr(self, "_in_net_check", False):
                print(f"[{self.device_id}] [POPUP] fixplay.png detected in login loop, clearing via net-popup path...")
                self._in_net_check = True
                try:
                    self._netpopup_last_click = 0
                    _hit = self._dismiss_net_popup(self._screen)
                    if _hit:
                        self._clear_net_popup_loop(_hit)
                finally:
                    self._in_net_check = False
                continue

            # fixnet1.png: à¸§à¸™à¹€à¸Šà¹‡à¸„à¸‹à¹‰à¸³à¸ˆà¸™à¸à¸§à¹ˆà¸²à¸ˆà¸°à¹„à¸¡à¹ˆà¹€à¸ˆà¸­ (à¸›à¸£à¸±à¸š similarity 0.8)
            fixnet1_login_clicks = 0
            while self.exists_in_cache("img/fixnet1.png", similarity=0.8):
                fixnet1_login_clicks += 1
                print(f"[{self.device_id}] [POPUP] fixnet1.png detected in login loop (click #{fixnet1_login_clicks}), clicking...")
                self.click("img/fixnet1.png", similarity=0.8)
                sleep(1.5)
                self.capture_screen()  # à¸ˆà¸±à¸šà¸ à¸²à¸žà¹ƒà¸«à¸¡à¹ˆà¹€à¸žà¸·à¹ˆà¸­à¹€à¸Šà¹‡à¸„à¸‹à¹‰à¸³
                if fixnet1_login_clicks >= 10:
                    print(f"[{self.device_id}] [POPUP] fixnet1.png clicked 10 times in login, breaking")
                    break
            if fixnet1_login_clicks > 0:
                continue

            # fixnetv3.png Check in login loop
            if self.exists_in_cache("img/fixnetv3.png", similarity=0.8) and self._wg_request_net_recover("login loop"):
                continue                      # à¸›à¸´à¸”à¹€à¸à¸¡ + à¸›à¸´à¸”/à¹€à¸›à¸´à¸” VPN + à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¹ƒà¸«à¸¡à¹ˆà¹à¸¥à¹‰à¸§ (wg_once=1 à¸ˆà¸°à¹„à¸¡à¹ˆà¸—à¸³ -> à¸à¸”à¹à¸šà¸šà¹€à¸”à¸´à¸¡)
            if self.exists_in_cache("img/fixnetv3.png", similarity=0.8):
                print(f"[{self.device_id}] [POPUP] fixnetv3.png detected in login loop! Tapping (472, 361)...")
                self._adb_tap(472, 361)   # à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸™à¹‡à¸•: à¸à¸”à¸œà¹ˆà¸²à¸™ adb à¸•à¸£à¸‡ à¹† à¹€à¸«à¸¡à¸·à¸­à¸™ bot-tiket
                sleep(0.5)
                continue

            # === fixokk.png Persistence Check (à¸£à¸­à¸„à¹‰à¸²à¸‡à¸„à¸£à¸š 5 à¸§à¸´ à¸–à¸¶à¸‡à¸ˆà¸°à¸à¸”) ===
            if self.exists_in_cache("img/fixokk.png", similarity=0.8):
                if not hasattr(self, '_fixokk_start_time') or self._fixokk_start_time is None:
                    self._fixokk_start_time = time.time()
                    if getattr(self, '_fixid_seen', False):
                        # à¹€à¸„à¸¢à¹€à¸ˆà¸­ fixid à¹ƒà¸™à¹„à¸­à¸”à¸µà¸™à¸µà¹‰à¹à¸¥à¹‰à¸§ -> à¹„à¸¡à¹ˆà¸•à¹‰à¸­à¸‡à¸£à¸­ 5 à¸§à¸´ à¸à¸” fixokk à¹€à¸¥à¸¢
                        print(f"[{self.device_id}] à¹€à¸ˆà¸­ fixokk.png (à¹€à¸„à¸¢à¹€à¸ˆà¸­ fixid à¹à¸¥à¹‰à¸§) -> à¸à¸”à¹€à¸¥à¸¢")
                        self.click("img/fixokk.png", similarity=0.8)
                        self._fixokk_start_time = None
                        sleep(2)
                    else:
                        print(f"[{self.device_id}] Detected fixokk.png... waiting 5s")
                elif getattr(self, '_fixid_seen', False) or time.time() - self._fixokk_start_time >= 5:
                    print(f"[{self.device_id}] âš ï¸ fixokk.png à¸„à¹‰à¸²à¸‡à¸­à¸¢à¸¹à¹ˆà¸„à¸£à¸š 5 à¸§à¸´à¸™à¸²à¸—à¸µ! à¸—à¸³à¸à¸²à¸£à¸à¸”...")
                    self.click("img/fixokk.png", similarity=0.8)
                    self._fixokk_start_time = None
                    sleep(0.5)
            else:
                self._fixokk_start_time = None

            # === alert2.png Persistence Check (à¸£à¸­à¸„à¹‰à¸²à¸‡à¸„à¸£à¸š 15 à¸§à¸´ à¹ƒà¸«à¹‰ clear app à¹à¸¥à¹‰à¸§à¹€à¸›à¸´à¸”à¹ƒà¸«à¸¡à¹ˆ) ===
            if self.exists_in_cache("img/alert2.png", similarity=0.8):
                if not hasattr(self, '_alert2_start_time') or self._alert2_start_time is None:
                    self._alert2_start_time = time.time()
                    print(f"[{self.device_id}] Detected alert2.png... waiting 15s to clear app")
                elif time.time() - self._alert2_start_time >= 15:
                    print(f"[{self.device_id}] âš ï¸ alert2.png à¸„à¹‰à¸²à¸‡à¸­à¸¢à¸¹à¹ˆà¸„à¸£à¸š 15 à¸§à¸´à¸™à¸²à¸—à¸µ! à¹€à¸„à¸¥à¸µà¸¢à¸£à¹Œà¹à¸­à¸žà¹à¸¥à¸°à¹€à¸‚à¹‰à¸²à¹ƒà¸«à¸¡à¹ˆ...")
                    self._wg_strike("LINE GAME à¸„à¹‰à¸²à¸‡")
                    self.clear_and_restart()
                    self.open_app()
                    self._alert2_start_time = None
                    sleep(1)
                    continue
            else:
                self._alert2_start_time = None

            # === fixid1.png â†’ failed à¸—à¸±à¸™à¸—à¸µ ===
            if self.exists_in_cache("img/fixid1.png", similarity=0.95):
                print(f"[{self.device_id}] Found fixid1.png! -> login-failed immediately")
                self._login_fixid_count = 0
                return "failed"

            # === fixid.png Check (à¹€à¸Šà¹‡à¸„à¸—à¸¸à¸à¸£à¸­à¸š) -> fixok -> refresh -> check ===
            if self.exists_in_cache("img/fixid.png", similarity=0.95):
                self._fixid_seen = True   # à¸ˆà¸³à¹„à¸§à¹‰: à¸•à¹ˆà¸­à¸ˆà¸²à¸à¸™à¸µà¹‰à¹€à¸ˆà¸­ fixokk à¸à¸”à¸—à¸±à¸™à¸—à¸µ
                # Authentication failed à¸•à¸­à¸™à¸•à¹ˆà¸­ VPN = IP à¸™à¸µà¹‰à¹‚à¸”à¸™à¸šà¸¥à¹‡à¸­à¸ -> à¸›à¸´à¸”à¹€à¸à¸¡ + à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™ IP à¸—à¸±à¸™à¸—à¸µ + à¹€à¸›à¸´à¸”à¹€à¸à¸¡à¹ƒà¸«à¸¡à¹ˆ (config "wg_fixid_switch")
                if (int(config.get("wg_fixid_switch", 1) or 0)
                        and self._wg_request_net_recover("Authentication failed", switch_now=True)):
                    self._login_fixid_count = 0
                    sleep(2)
                    continue
                self._login_fixid_count += 1
                print(f"[{self.device_id}] Found fixid.png ({self._login_fixid_count}/15), fixok -> refresh -> check...")
                
                if self._login_fixid_count >= 15:
                    print(f"[{self.device_id}] fixid limit reached (15 times)! Failing...")
                    self._wg_auth_failed()
                    self._wg_strike("fixid à¸„à¸£à¸š 15")
                    self._login_fixid_count = 0
                    return "failed"
                
                # 1) à¸à¸” fikcheck
                print(f"[{self.device_id}] Step 1: waiting for fikcheck.png (10s timeout)...")
                sleep(0.5) # à¹ƒà¸«à¹‰à¸«à¸™à¹‰à¸²à¸ˆà¸­à¹€à¸ªà¸–à¸µà¸¢à¸£à¸«à¸¥à¸±à¸‡ re-route
                for _ in range(10): # Timeout 10s
                    self.capture_screen()
                    if self.exists_in_cache("img/fikcheck.png", similarity=0.8):
                        self.click("img/fikcheck.png", similarity=0.8)
                        print(f"[{self.device_id}] Clicked fikcheck.png")
                        sleep(0.5)
                        break
                    sleep(0.5)
                
                # 2) à¸à¸” refresh
                print(f"[{self.device_id}] Step 2: clicking refresh.png (10s timeout)...")
                for _ in range(10): # Timeout 10s
                    self.capture_screen()
                    if self.exists_in_cache("img/refresh.png", similarity=0.8):
                        self.click("img/refresh.png", similarity=0.8)
                        print(f"[{self.device_id}] Clicked refresh.png")
                        self._wg_after_refresh()
                        sleep(0.5)
                        break
                    sleep(0.5)
                
                else:
                    # à¸„à¸£à¸šà¹€à¸§à¸¥à¸²à¹à¸¥à¹‰à¸§à¹„à¸¡à¹ˆà¹€à¸ˆà¸­ refresh.png - à¹€à¸”à¸´à¸¡à¹€à¸‡à¸µà¸¢à¸šà¹„à¸›à¹€à¸‰à¸¢ à¹† à¹„à¸¥à¹ˆà¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸§à¹ˆà¸²à¸£à¸¹à¸›à¹„à¸¡à¹ˆà¹à¸¡à¸•à¸Šà¹Œà¸«à¸£à¸·à¸­à¸ˆà¸­à¹„à¸¡à¹ˆà¸¡à¸²
                    _sc = self._match_score("img/refresh.png")
                    _shot = self._save_debug_screen("refresh-miss")
                    print(f"[{self.device_id}] [REFRESH] à¹„à¸¡à¹ˆà¹€à¸ˆà¸­ refresh.png (à¸„à¸°à¹à¸™à¸™à¸ªà¸¹à¸‡à¸ªà¸¸à¸” {_sc:.2f} / à¸•à¹‰à¸­à¸‡à¸à¸²à¸£ 0.80)"
                          + (f" - à¹€à¸à¹‡à¸šà¸ à¸²à¸žà¹„à¸§à¹‰à¸—à¸µà¹ˆ {_shot}" if _shot else ""))
                # 3) à¸£à¸­ check.png à¹à¸¥à¹‰à¸§à¸à¸”
                print(f"[{self.device_id}] Step 3: waiting for check.png (60s timeout)...")
                check_wait_start = time.time()
                while time.time() - check_wait_start < 60:
                    self.capture_screen()
                    if self.exists_in_cache("img/check.png"):
                        print(f"[{self.device_id}] Found check.png! Clicking...")
                        self.click("img/check.png")
                        sleep(0.5)
                        # à¸«à¸¥à¸±à¸‡à¸à¸” check -> à¸£à¸­à¸”à¸¹ fixid à¸à¹ˆà¸­à¸™ 2 à¸§à¸´
                        found_fixid_after_check = False
                        for _ in range(2):
                            self.capture_screen()
                            if self.exists_in_cache("img/fixid.png"):
                                print(f"[{self.device_id}] Found fixid.png right after check! Re-routing...")
                                found_fixid_after_check = True
                                break
                            sleep(0.5)
                        
                        if found_fixid_after_check:
                            break

                        if self.exists_in_cache("img/fikcheck.png", similarity=0.8):
                            print(f"[{self.device_id}] Found fikcheck.png after check! Clicking...")
                            self.click("img/fikcheck.png", similarity=0.8)
                            sleep(0.5)
                        break
                    sleep(0.5)
                
                continue

            # === à¹€à¸ˆà¸­ refresh.png (à¹„à¸¡à¹ˆà¸¡à¸µ fixid) -> à¸à¸” refresh -> check ===
            if self.exists_in_cache("img/refresh.png", similarity=0.8):
                print(f"[{self.device_id}] Found refresh.png (no fixid), clicking refresh -> check...")
                self.click("img/refresh.png", similarity=0.8)
                self._wg_after_refresh()
                sleep(0.5)
                
                check_wait_start = time.time()
                while time.time() - check_wait_start < 60:
                    self.capture_screen()
                    if self.exists_in_cache("img/check.png"):
                        print(f"[{self.device_id}] Found check.png! Clicking...")
                        self.click("img/check.png")
                        sleep(0.5)
                        # à¸«à¸¥à¸±à¸‡à¸à¸” check -> à¸£à¸­à¸”à¸¹ fixid à¸à¹ˆà¸­à¸™ 2 à¸§à¸´
                        found_fixid_after_check = False
                        for _ in range(4):
                            self.capture_screen()
                            if self.exists_in_cache("img/fixid.png"):
                                print(f"[{self.device_id}] Found fixid.png right after check! Re-routing...")
                                found_fixid_after_check = True
                                break
                            sleep(0.5)
                        
                        if found_fixid_after_check:
                            break
 
                        if self.exists_in_cache("img/fikcheck.png", similarity=0.8):
                            print(f"[{self.device_id}] Found fikcheck.png after check! Clicking...")
                            self.click("img/fikcheck.png", similarity=0.8)
                            sleep(0.3)
                        break
                    sleep(0.5)
                
                continue
            # ====================================================

            # Crash Check: à¹ƒà¸Šà¹‰ pidof + open_app à¹à¸—à¸™à¸„à¸¥à¸´à¸ icon.png
            try:
                pid_result = subprocess.run(
                    [self.adb_cmd, "-s", self.device_id, "shell", "pidof", "com.linecorp.LGRGS"],
                    capture_output=True, text=True, timeout=5
                )
                if not pid_result.stdout.strip():
                    print(f"[{self.device_id}] App crashed during login. Relaunching...")
                    self.open_app()
                    sleep(1)
                    loop_count = 0
                    continue
            except:
                pass
            
            # fixalerterror1 Check
            if self.exists_in_cache("img/fixalerterror1.png"):
                print(f"[{self.device_id}] Alert error detected. Dimissing...")
                self.click("img/fixalerterror1.png")
                sleep(0.5)
                loop_count = 0
                continue

            # fixcak.png Check
            if self.exists_in_cache("img/fixcak.png"):
                print(f"[{self.device_id}] Fixcak detected (fix bug login). Dismissing...")
                self.click("img/fixcak.png")
                sleep(0.5)
                loop_count = 0
                continue
                
            # à¹„à¸à¹ˆà¸šà¸µà¹‰à¸—à¸¸à¸à¹à¸šà¸š
            kaiby_hit = self.find_kaiby(similarity=0.8)
            if kaiby_hit:
                print(f"[{self.device_id}] âš ï¸ à¸žà¸š {kaiby_hit}! (à¹„à¸à¹ˆà¸šà¸µà¹‰à¹€à¸”à¹‰à¸‡à¸£à¸°à¸«à¸§à¹ˆà¸²à¸‡ Login) à¹€à¸„à¸¥à¸µà¸¢à¸£à¹Œà¹à¸­à¸žà¹à¸¥à¸°à¸ªà¹ˆà¸‡à¹€à¸‚à¹‰à¸²à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œ kaiby...")
                self.clear_and_restart()
                sleep(0.5)
                return "kaiby"

            # *** SUCCESS -> Just Login and Backup ***
            if self.exists_in_cache("img/stoplogin.png", similarity=0.8):
                print(f"[{self.device_id}] Login successful! (stoplogin detected)")
                self._wg_ok()
                self._wg_auth_fail = 0
                if int(config.get("wg_after_login", 0) or 0):
                    self._ensure_wireguard()   # à¸¥à¹‡à¸­à¸à¸­à¸´à¸™à¸œà¹ˆà¸²à¸™à¹à¸¥à¹‰à¸§ -> à¸„à¹ˆà¸­à¸¢à¸•à¹ˆà¸­ VPN (à¹€à¸‹à¸´à¸£à¹Œà¸Ÿ LINE à¹„à¸¡à¹ˆà¸¢à¸­à¸¡à¹ƒà¸«à¹‰à¸¥à¹‡à¸­à¸à¸­à¸´à¸™à¸œà¹ˆà¸²à¸™ VPN)
                
                # === Check for kaibyswap_shop.png before proceeding (if configured) ===
                kaibyskip_enabled = config.get("kaibyskip", 0)
                kaibycheck_enabled = config.get("kaibycheck", 0)
                
                if kaibycheck_enabled == 1:
                    print(f"[{self.device_id}] config kaibycheck=1: Skipping kaibyswap_shop check, proceeding normally...")
                elif kaibyskip_enabled == 1:
                    print(f"[{self.device_id}] config kaibyskip=1: Checking for kaibyswap_shop.png (3s)...")
                    kaibyswap_found = False
                    kaiby_start = time.time()
                    while time.time() - kaiby_start < 3:
                        self.capture_screen()
                        if self.exists_in_cache("img/kaibyswap_shop.png"):
                            kaibyswap_found = True
                            break
                        sleep(0.5)
                    
                    if kaibyswap_found:
                        print(f"[{self.device_id}] âš ï¸ Found kaibyswap_shop.png! Returning kaiby...")
                        self.clear_and_restart()
                        return "kaiby"
                # ====================================================================

                print(f"[{self.device_id}] [DEBUG] Modes -> do_ranger={self.do_ranger}, do_gear={self.do_gear}")
                
                ranger_results = {}
                gear_results = set()
                
                # Run ranger process first if enabled
                if self.do_ranger:
                    print(f"[{self.device_id}] [DEBUG] Starting Ranger scan...")
                    ranger_results = self.process_find_ranger(current_filename)
                    print(f"[{self.device_id}] [DEBUG] Ranger results: {ranger_results}")
                else:
                    print(f"[{self.device_id}] [DEBUG] Ranger scan SKIPPED (do_ranger={self.do_ranger})")
                
                # Then run gear process if enabled
                # Then run gear process if enabled
                if self.do_gear:
                    self.update_gui_status("Checking Gear")
                    print(f"[{self.device_id}] Starting Gear scan (do_gear={self.do_gear})...")
                    gear_results = self.process_check_gear(current_filename, ranger_results)
                    print(f"[{self.device_id}] Gear scan done. Found: {gear_results}")
                else:
                    print(f"[{self.device_id}] Gear scan SKIPPED (do_gear={self.do_gear})")
                
                # Ruby and Ticket Check
                ruby_count = None
                ticket_count = None
                is_rt_enabled = (config.get("check_ruby_ticket", 0) == 1) or (config.get("find_all", 1) == 1)
                
                if is_rt_enabled:
                    self.update_gui_status("Ruby/Ticket Check")
                    print(f"[{self.device_id}] Starting Resource check (is_rt_enabled={is_rt_enabled})...")
                    ruby_count, ticket_count = self.process_check_ruby_ticket()
                    print(f"[{self.device_id}] Resource check done. Ruby: {ruby_count}, Ticket: {ticket_count}")
                
                # Combine results and backup
                filename = self.current_original_filename or "unknown.xml"
                
                # Handle Ruby/Ticket in filename â€” à¸¢à¹‰à¸²à¸¢ tag à¸¡à¸²à¹„à¸§à¹‰à¸‚à¹‰à¸²à¸‡à¸«à¸™à¹‰à¸²: ruby[]+ticket[]+à¸Šà¸·à¹ˆà¸­
                import re
                # strip tag ruby/ticket à¹€à¸”à¸´à¸¡ (à¸­à¸¢à¸¹à¹ˆà¸«à¸™à¹‰à¸²à¸«à¸£à¸·à¸­à¸«à¸¥à¸±à¸‡à¸à¹‡à¹„à¸”à¹‰) à¹ƒà¸«à¹‰à¹€à¸«à¸¥à¸·à¸­à¸Šà¸·à¹ˆà¸­ base à¸ªà¸°à¸­à¸²à¸”
                base = os.path.splitext(filename)[0]
                base = re.sub(r'\+?ruby\[[^\]]*\]', '', base)
                base = re.sub(r'\+?ticket\[[^\]]*\]', '', base)
                base = re.sub(r'\+{2,}', '+', base).strip('+')
                clean_filename = base + ".xml"
                if ruby_count is not None or ticket_count is not None:
                    ruby_str = ruby_count if ruby_count else "0"
                    ticket_str = ticket_count if ticket_count else "0"
                    filename = f"ruby[{ruby_str}]+ticket[{ticket_str}]+{base}.xml"
                else:
                    filename = clean_filename
                
                source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
                
                # Create subfolder name from all found items
                all_names_list = []
                if ranger_results:
                    all_names_list.extend(ranger_results.values())
                if gear_results:
                    all_names_list.extend(gear_results)
                
                found_names = "+".join(sorted(set(all_names_list))) if all_names_list else "unknown"
                print(f"[{self.device_id}] [DEBUG] all_names_list={all_names_list}, found_names={found_names}")
                
                # Determine category folder name
                has_ranger = len(ranger_results) > 0
                has_gear = len(gear_results) > 0
                print(f"[{self.device_id}] [DEBUG] has_ranger={has_ranger}, has_gear={has_gear}")
                
                category = "unknown"
                if has_gear and has_ranger:
                    category = "gear+ranger"
                elif has_gear:
                    category = "gear only"
                elif has_ranger:
                    count = len(ranger_results)
                    category = "ranger" if count == 1 else f"ranger({count})"
                
                print(f"[{self.device_id}] [DEBUG] category={category}")
                
                if category != "unknown":
                    msg = f"[{self.device_id}] ðŸ† Success! Found {category}: {found_names}"
                    print(msg)
                    
                    # ALWAYS update hero stats for shared Dashboard (even in CLI mode)
                    ui_stats.update_hero(found_names)
                    
                    # chmod for pull (à¸§à¸´à¸˜à¸µà¸—à¸µà¹ˆà¹„à¸”à¹‰à¸œà¸¥ 100%: cp â†’ tmp â†’ chmod â†’ pull)
                    safe_dev = self.device_id.replace(":", "_")
                    temp_remote = f"/data/local/tmp/backup_{safe_dev}.xml"
                    self.adb_shell(f"su -c 'cp {source_path} {temp_remote}'")
                    self.adb_shell(f"su -c 'chmod 666 {temp_remote}'")
                    
                    # Create backup folder structure: backup-id/category/found_names
                    backup_dir = os.path.join("backup-id", category, found_names)
                    if not os.path.exists(backup_dir):
                        os.makedirs(backup_dir)
                    
                    # Delete old files for the same account to avoid accumulation (as requested)
                    clean_base = os.path.splitext(clean_filename)[0]
                    if os.path.exists(backup_dir):
                        for old_f in os.listdir(backup_dir):
                            # match à¸—à¸±à¹‰à¸‡à¸Šà¸·à¹ˆà¸­à¹€à¸à¹ˆà¸² (tag à¸‚à¹‰à¸²à¸‡à¸«à¸¥à¸±à¸‡) à¹à¸¥à¸°à¹ƒà¸«à¸¡à¹ˆ (tag à¸‚à¹‰à¸²à¸‡à¸«à¸™à¹‰à¸²) à¸”à¹‰à¸§à¸¢ account base
                            is_match = old_f.endswith(".xml") and (
                                old_f == (clean_base + ".xml")
                                or old_f.startswith(clean_base + "+")          # à¹€à¸à¹ˆà¸²: base+ruby[]+ticket[]
                                or old_f.endswith("+" + clean_base + ".xml")   # à¹ƒà¸«à¸¡à¹ˆ: ruby[]+ticket[]+base
                            )
                            if is_match:
                                try:
                                    os.remove(os.path.join(backup_dir, old_f))
                                except:
                                    pass

                    # Pull file
                    dst = os.path.join(backup_dir, filename)
                    result = subprocess.run(
                        [self.adb_cmd, '-s', self.device_id, 'pull', temp_remote, dst],
                        capture_output=True, text=True
                    )
                    
                    if result.returncode == 0:
                        print(f"[{self.device_id}] âœ“ Backed up to: {dst}")
                    else:
                        print(f"[{self.device_id}] âœ— Backup failed: {result.stderr}")
                    # Cleanup temp
                    self.adb_shell(f"rm -f {temp_remote}")
                else:
                    # No results from either ranger or gear -> backup to not-found
                    msg = f"[{self.device_id}] à¹„à¸¡à¹ˆà¹€à¸ˆà¸­ Ranger/Gear à¸—à¸µà¹ˆà¸•à¹‰à¸­à¸‡à¸à¸²à¸£"
                    print(msg)
                    
                    # ALWAYS update hero stats for shared Dashboard (even in CLI mode)
                    ui_stats.update_hero("à¹„à¸¡à¹ˆà¹€à¸ˆà¸­")
                    
                    print(f"[{self.device_id}] No results from ranger or gear - backing up to not-found")
                    self.backup_to_not_found(filename, source_path)
                
                # Clear app and restart (Wait 8s as requested by user to ensure completion)
                print(f"[{self.device_id}] Success! Waiting 8s before clearing...")
                sleep(8.0)
                self.clear_and_restart()
                return "success"
                
            # à¹„à¸à¹ˆà¸šà¸µà¹‰à¸—à¸¸à¸à¹à¸šà¸š (High Priority)
            reason = self.find_kaiby()
            if reason:
                print(f"[{self.device_id}] {reason} detected! Stopping login...")
                return "kaiby"

            # Failed
            if self.exists_in_cache("img/login-failed.png"):
                print(f"[{self.device_id}] Login failed (login-failed.png detected)")
                _signal_host_vpn_rotate(f"login-failed {self.device_id}")
                self._wg_strike("login failed")
                self._login_fixid_count = 0
                return "failed"
                
            # Error/Reset
            error_found = self.check_error_images()
            
            if error_found:
                print(f"[{self.device_id}] Error image found: {error_found}. Resetting...")
                if error_found in ["fixbug", "unkhow"]:
                    img = "img/fixbuglogin.png" if error_found == "fixbug" else "img/unkhow.png"
                    self.click(img)
                    sleep(0.5)
                self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
                sleep(0.5)
                self.open_app()
                sleep(1)
                loop_count = 0
                continue
            
            # === fixok.png Check (à¹€à¸Šà¹‡à¸„à¸•à¸¥à¸­à¸” à¹à¸•à¹ˆà¸«à¸¢à¸¸à¸”à¸«à¸¥à¸±à¸‡ event) ===
            if not event_passed and self.exists_in_cache("img/fixok.png"):
                print(f"[{self.device_id}] Found fixok.png! Clicking...")
                self.click("img/fixok.png")
                sleep(1)
                continue

            # Event / Popups
            if self.exists_in_cache("img/event.png"):
                event_passed = True  # à¸«à¸¥à¸±à¸‡à¸ˆà¸²à¸à¸™à¸µà¹‰à¸«à¸¢à¸¸à¸”à¹€à¸Šà¹‡à¸„ fixok
                event_popup_count += 1
                if event_popup_count > 15:
                    # à¸›à¹Šà¸­à¸›à¸­à¸±à¸žà¹€à¸”à¹‰à¸‡à¸à¸¥à¸±à¸šà¸¡à¸²à¹„à¸¡à¹ˆà¸ˆà¸š - à¹€à¸¥à¸´à¸à¸à¸”à¸¡à¸±à¸™ à¸›à¸¥à¹ˆà¸­à¸¢à¸¥à¸¹à¸›à¹€à¸”à¸´à¸™à¸•à¹ˆà¸­à¹ƒà¸«à¹‰à¹€à¸žà¸”à¸²à¸™
                    # 500 à¸£à¸­à¸šà¸ˆà¸±à¸”à¸à¸²à¸£à¹à¸—à¸™ (à¹€à¸”à¸´à¸¡ loop_count -= 1 à¸•à¸£à¸‡à¸™à¸µà¹‰à¸—à¸³à¹ƒà¸«à¹‰à¸•à¸±à¸§à¸™à¸±à¸š
                    # à¹„à¸¡à¹ˆà¸‚à¸¢à¸±à¸š = à¸¥à¸¹à¸›à¸§à¸™à¸•à¸¥à¸­à¸”à¸à¸²à¸¥ à¹„à¸¡à¹ˆà¸¡à¸µà¸§à¸±à¸™à¸–à¸¶à¸‡ timeout)
                    if event_popup_count == 16:
                        print(f"[{self.device_id}] Event popup keeps returning (>15) - stop clicking, let timeout handle it")
                else:
                    print(f"[{self.device_id}] Event popup detected ({event_popup_count}/15). Clicking then Back...")
                    self.click("img/event.png")
                    sleep(0.5)
                    self.adb_shell("input keyevent 4")  # Back button
                    sleep(1)

                    # à¹€à¸Šà¹‡à¸„ cancel.png à¹€à¸‰à¸žà¸²à¸°à¸«à¸¥à¸±à¸‡à¹€à¸ˆà¸­ event à¹€à¸—à¹ˆà¸²à¸™à¸±à¹‰à¸™
                    self.capture_screen()
                    if self.exists_in_cache("img/cancel.png"):
                        print(f"[{self.device_id}] Cancel button after event. Clicking...")
                        self.click("img/cancel.png")
                        sleep(1)
                    continue
            
            sleep(0.5)
            # à¸—à¸¸à¸ 100 à¸£à¸­à¸šà¸—à¸µà¹ˆà¹„à¸¡à¹ˆà¸¡à¸µà¸à¸²à¸£ match (= à¸„à¹‰à¸²à¸‡à¸«à¸™à¹‰à¸² splash/LINE login) -> restart app à¸„à¸£à¸±à¹‰à¸‡à¹€à¸”à¸µà¸¢à¸§
            # à¹à¸¥à¹‰à¸§à¸–à¹‰à¸²à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸‚à¸¶à¹‰à¸™à¸„à¹ˆà¸­à¸¢ timeout à¸—à¸µà¹ˆ 300 à¸£à¸­à¸š (= ~2.5 à¸™à¸²à¸—à¸µ) à¹à¸—à¸™à¸£à¸­à¸„à¸£à¸š 500 (~4 à¸™à¸²à¸—à¸µ)
            if loop_count == 100 and not event_passed:
                print(f"[{self.device_id}] [STUCK] 100 iter no progress - force relaunch app")
                try:
                    self.clear_and_restart()
                    self.open_app()
                    sleep(3)
                except Exception as e:
                    print(f"[{self.device_id}] [STUCK] relaunch failed: {e}")
            if loop_count > 300:
                print(f"[{self.device_id}] Login timeout after 300 iterations (~2.5 min)")
                _signal_host_vpn_rotate(f"login-timeout {self.device_id}")
                status = "timeout"
                return status
        
        return status


class DeviceLogTee:
    """à¹€à¸à¹‡à¸š log à¸¥à¸‡à¹„à¸Ÿà¸¥à¹Œ .txt à¹à¸¢à¸à¸£à¸²à¸¢ device (logs/<device>.txt) + à¸£à¸§à¸¡à¸—à¸±à¹‰à¸‡à¸«à¸¡à¸”à¹ƒà¸™ logs/all.txt

    à¸„à¸£à¸­à¸š stdout/stderr à¹€à¸”à¸´à¸¡: à¸„à¸­à¸™à¹‚à¸‹à¸¥/GUI à¹€à¸«à¹‡à¸™à¹€à¸«à¸¡à¸·à¸­à¸™à¹€à¸”à¸´à¸¡à¸—à¸¸à¸à¸›à¸£à¸°à¸à¸²à¸£ à¹à¸„à¹ˆà¸ˆà¸”à¸¥à¸‡à¹„à¸Ÿà¸¥à¹Œà¹€à¸žà¸´à¹ˆà¸¡
    à¸£à¸°à¸šà¸¸ device à¸ˆà¸²à¸ thread à¸—à¸µà¹ˆà¸žà¸´à¸¡à¸žà¹Œ (RangerGearBot à¸¡à¸µ device_id) à¹€à¸›à¹‡à¸™à¸«à¸¥à¸±à¸
    à¸–à¹‰à¸²à¸žà¸´à¸¡à¸žà¹Œà¸ˆà¸²à¸ thread à¸­à¸·à¹ˆà¸™à¸ˆà¸°à¸”à¸¹ prefix [127.0.0.1:xxxx] / [emulator-xxxx] à¹à¸—à¸™
    à¹„à¸Ÿà¸¥à¹Œà¹€à¸à¸´à¸™ 20MB à¸ªà¸¥à¸±à¸šà¹„à¸›à¹€à¸›à¹‡à¸™ .old.txt à¸à¸±à¸™à¹‚à¸•à¹„à¸¡à¹ˆà¸ˆà¸³à¸à¸±à¸”
    """

    MAX_BYTES = 20 * 1024 * 1024

    def __init__(self, real):
        self.real = real
        self.lock = threading.Lock()
        self.bufs = {}
        self.dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        try:
            os.makedirs(self.dir, exist_ok=True)
        except Exception:
            pass

    def write(self, text):
        try:
            self.real.write(text)
        except Exception:
            pass
        try:
            tid = threading.get_ident()
            buf = self.bufs.get(tid, "") + str(text)
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                self._emit(line.rstrip("\r"))
            self.bufs[tid] = buf
        except Exception:
            pass
        return len(text) if isinstance(text, str) else 0

    def _emit(self, line):
        if not line.strip():
            return
        dev = getattr(threading.current_thread(), "device_id", None)
        if not dev and (line.startswith("[127.0.0.1:") or line.startswith("[emulator-")):
            end = line.find("]")
            if end > 1:
                dev = line[1:end]
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with self.lock:
            self._append("all", stamp, line)
            if dev:
                self._append(str(dev).replace(":", "_"), stamp, line)

    def _append(self, name, stamp, line):
        try:
            path = os.path.join(self.dir, f"{name}.txt")
            try:
                if os.path.getsize(path) > self.MAX_BYTES:
                    old = os.path.join(self.dir, f"{name}.old.txt")
                    if os.path.exists(old):
                        os.remove(old)
                    os.rename(path, old)
            except OSError:
                pass
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"[{stamp}] {line}\n")
        except Exception:
            pass

    def flush(self):
        try:
            self.real.flush()
        except Exception:
            pass

    def isatty(self):
        try:
            return self.real.isatty()
        except Exception:
            return False


if __name__ == "__main__":
    # à¹€à¸à¹‡à¸š log à¸—à¸¸à¸à¸šà¸£à¸£à¸—à¸±à¸”à¸¥à¸‡à¹„à¸Ÿà¸¥à¹Œ .txt à¹à¸¢à¸à¸£à¸²à¸¢ device à¹ƒà¸™à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œ logs/
    # (à¸„à¸­à¸™à¹‚à¸‹à¸¥/GUI à¹à¸ªà¸”à¸‡à¸œà¸¥à¹€à¸«à¸¡à¸·à¸­à¸™à¹€à¸”à¸´à¸¡ à¹à¸„à¹ˆà¸ˆà¸”à¸¥à¸‡à¹„à¸Ÿà¸¥à¹Œà¹€à¸žà¸´à¹ˆà¸¡)
    sys.stdout = DeviceLogTee(sys.stdout)
    sys.stderr = DeviceLogTee(sys.stderr)

    parser = argparse.ArgumentParser(description="Auto Ranger+Gear Script v3.2.0")
    parser.add_argument("--device", type=str, help="Specific device ID/address to run (e.g. 127.0.0.1:5557)")
    parser.add_argument("--no-start", action="store_true", help="Don't auto-start bot threads in GUI")
    parser.add_argument("--no-reset-adb", action="store_true", help="Don't kill/start ADB server")
    parser.add_argument("--cli", action="store_true", help="Launch in Command Line mode (no GUI)")
    parser.add_argument("--minimized", action="store_true", help="Minimize window")
    args = parser.parse_args()

    if args.minimized:
        try:
            import ctypes
            # SW_MINIMIZE = 6 or SW_HIDE = 0. Using 2 (SW_SHOWMINIMIZED) or 6.
            # 2 is show minimized, 0 is hide. Let's use 2 as requested "minimized".
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 2)
        except: pass

    print("=== Auto Ranger+Gear Script v3.2.0 ===")
    print(f"[VERSION] build 2026-10-12 gacha-v1 | à¹„à¸Ÿà¸¥à¹Œà¹à¸à¹‰à¸¥à¹ˆà¸²à¸ªà¸¸à¸” {time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(os.path.abspath(__file__))))}")
    
    load_config()
    
    # à¸¥à¸šà¹„à¸Ÿà¸¥à¹Œ .lock à¸—à¸±à¹‰à¸‡à¸«à¸¡à¸”à¸•à¸­à¸™à¹€à¸£à¸´à¹ˆà¸¡à¸£à¸±à¸™ (à¸—à¸±à¹‰à¸‡ backup/ à¹à¸¥à¸° temp/)
    cleanup_count = 0
    # 1. à¸¥à¸š lock à¹€à¸à¹ˆà¸²à¸—à¸µà¹ˆà¸­à¸²à¸ˆà¸„à¹‰à¸²à¸‡à¹ƒà¸™à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸„à¸´à¸§
    for queue_folder in queue_folder_paths():
        if not os.path.exists(queue_folder):
            continue
        for lf in glob.glob(os.path.join(queue_folder, "*.lock")):
            try: os.remove(lf); cleanup_count += 1
            except: pass
    # 2. à¸¥à¸š lock à¹ƒà¸™ temp/ranger-locks/
    temp_lock_dir = os.path.join(tempfile.gettempdir(), "ranger-locks")
    if os.path.exists(temp_lock_dir):
        for lf in glob.glob(os.path.join(temp_lock_dir, "*.lock")):
            try: os.remove(lf); cleanup_count += 1
            except: pass
    # 2b. à¸¥à¹‰à¸²à¸‡à¸£à¸²à¸¢à¸Šà¸·à¹ˆà¸­ IP à¸—à¸µà¹ˆà¸ˆà¸”à¸§à¹ˆà¸²à¹‚à¸”à¸™à¸šà¸¥à¹‡à¸­à¸/à¸žà¸±à¸à¹„à¸§à¹‰à¸ˆà¸²à¸à¸£à¸­à¸šà¸à¹ˆà¸­à¸™ (wg_reset_blocked_on_start, default 1)
    #     à¸à¸±à¸™à¸£à¸²à¸¢à¸Šà¸·à¹ˆà¸­à¸—à¸µà¹ˆà¸ˆà¸”à¸œà¸´à¸”à¸ªà¸°à¸ªà¸¡à¸ˆà¸™à¹„à¸¡à¹ˆà¸¡à¸µ IP à¹ƒà¸«à¹‰à¹ƒà¸Šà¹‰/à¸ªà¸£à¹‰à¸²à¸‡à¹ƒà¸«à¸¡à¹ˆà¹„à¸¡à¹ˆà¹„à¸”à¹‰ - à¸•à¸±à¸§à¸—à¸µà¹ˆà¹‚à¸”à¸™à¸ˆà¸£à¸´à¸‡à¸šà¸­à¸—à¸ˆà¸°à¸—à¸”à¸ªà¸­à¸šà¹€à¸ˆà¸­à¹ƒà¸«à¸¡à¹ˆà¹€à¸­à¸‡
    if int(config.get("wg_reset_blocked_on_start", 1) or 0):
        for _bf in (".blocked.json", ".cooldown.json"):
            try: os.remove(os.path.join(str(config.get("wg_dir", "wg")), _bf)); cleanup_count += 1
            except OSError: pass
    # 2c. à¸¥à¹‰à¸²à¸‡à¸à¸²à¸£à¸ˆà¸­à¸‡à¹„à¸Ÿà¸¥à¹Œ WireGuard à¸‚à¸­à¸‡à¸£à¸­à¸šà¸à¹ˆà¸­à¸™ (à¹à¸•à¹ˆà¸¥à¸°à¸ˆà¸­à¸ˆà¸°à¸ˆà¸­à¸‡à¹ƒà¸«à¸¡à¹ˆà¹„à¸¡à¹ˆà¸‹à¹‰à¸³à¸à¸±à¸™)
    for lf in glob.glob(os.path.join(str(config.get("wg_dir", "wg")), ".claims", "*.lock")):
        try: os.remove(lf); cleanup_count += 1
        except: pass
    if cleanup_count > 0:
        print(f"[CLEANUP] Removed {cleanup_count} stale .lock file(s)")

    # 3. à¸¥à¸šà¹„à¸Ÿà¸¥à¹Œ shared_stats.json à¹€à¸žà¸·à¹ˆà¸­à¸¥à¹‰à¸²à¸‡à¸„à¹ˆà¸²à¸ˆà¸²à¸à¸£à¸­à¸šà¹€à¸à¹ˆà¸²
    shared_stats_file = ui_stats._get_shared_file()
    if os.path.exists(shared_stats_file):
        try:
            os.remove(shared_stats_file)
            print("[CLEANUP] Removed old shared_stats.json")
        except: pass
    
    # à¸£à¸µà¹€à¸‹à¹‡à¸•à¸„à¹ˆà¸²à¹ƒà¸™à¸«à¸™à¹ˆà¸§à¸¢à¸„à¸§à¸²à¸¡à¸ˆà¸³à¸”à¹‰à¸§à¸¢
    ui_stats.success_count = 0
    ui_stats.fail_count = 0
    ui_stats.hero_found_list = {}
    ui_stats.device_statuses = {}
    ui_stats.save_shared()
    
    if not find_adb_executable():
        print("ADB Not Found.")
        sys.exit(1)
    
    # Reset ADB and execute port scan (Skip if requested)
    if not args.no_reset_adb:
        print("[INFO] Connecting to all MuMu ports (ADB Restart inside)...")
        connect_known_ports()
        
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
    
    # === à¸¥à¹‰à¸²à¸‡à¹€à¸™à¹‡à¸•à¸—à¸¸à¸à¸ˆà¸­à¸à¹ˆà¸­à¸™à¹€à¸£à¸´à¹ˆà¸¡: à¸›à¸´à¸” VPN (WireGuard) à¸—à¸µà¹ˆà¸„à¹‰à¸²à¸‡ + à¸¥à¹‰à¸²à¸‡ proxy à¸„à¹‰à¸²à¸‡ à¹à¸¥à¹‰à¸§à¹€à¸Šà¹‡à¸„à¸§à¹ˆà¸²à¸­à¸­à¸à¹€à¸™à¹‡à¸•à¹„à¸”à¹‰ ===
    reset_network_all(devices)

    # === à¹„à¸Ÿà¸¥à¹Œ WireGuard à¹„à¸¡à¹ˆà¸žà¸­à¸ˆà¸³à¸™à¸§à¸™à¸ˆà¸­ -> à¸ªà¸£à¹‰à¸²à¸‡à¹€à¸žà¸´à¹ˆà¸¡à¸­à¸±à¸•à¹‚à¸™à¸¡à¸±à¸•à¸´à¸ˆà¸²à¸ Key Pair à¸—à¸µà¹ˆà¸¡à¸µ (wg_gen.py) ===
    # use_host_vpn=1: VPN à¸­à¸¢à¸¹à¹ˆà¸šà¸™ Windows host - à¸‚à¹‰à¸²à¸¡ auto-gen (à¹„à¸¡à¹ˆà¹à¸•à¸°à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œ wg/)
    # wg_auto_gen=0: Proton mode - wg_gen à¹ƒà¸Šà¹‰à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¸à¸±à¸š Proton conf (à¹„à¸¡à¹ˆà¸¡à¸µ PresharedKey)
    if (int(config.get("wg_enabled", 1) or 0)
            and int(config.get("wg_auto_gen", 1) or 0)
            and not int(config.get("use_host_vpn", 0) or 0)):
        try:
            import wg_gen
            _mach = int(config.get("wg_machine", 0) or 0)   # à¹€à¸¥à¸‚à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡ (à¸«à¸¥à¸²à¸¢à¹€à¸„à¸£à¸·à¹ˆà¸­à¸‡à¹ƒà¸Šà¹‰à¸à¸¸à¸à¹à¸ˆà¹€à¸”à¸µà¸¢à¸§à¸à¸±à¸™) 0 = à¸›à¸´à¸”
            _per = int(config.get("wg_per_machine", 0) or 0) or (len(devices) + int(config.get("wg_gen_spare", 2)))
            wg_gen.generate(_per, config.get("wg_gen_countries") or None, str(config.get("wg_dir", "wg")), _mach,
                            str(config.get("wg_account", "") or "").strip() or None,   # à¹€à¸¥à¸·à¸­à¸à¸šà¸±à¸à¸Šà¸µ: wg_accounts/<à¸Šà¸·à¹ˆà¸­>/
                            int(config.get("wg_total_machines", 30) or 30))
        except Exception as e:
            print(f"[WG-GEN] à¸ªà¸£à¹‰à¸²à¸‡à¹„à¸Ÿà¸¥à¹Œà¸­à¸±à¸•à¹‚à¸™à¸¡à¸±à¸•à¸´à¹„à¸¡à¹ˆà¸ªà¸³à¹€à¸£à¹‡à¸ˆ: {e}")

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
    
    # Setup Queue (Still needed for GUI but threads will use directory scanning)
    # à¹€à¸”à¸´à¸¡à¸™à¸±à¸šà¹€à¸‰à¸žà¸²à¸°à¸Šà¸±à¹‰à¸™à¸šà¸™à¸ªà¸¸à¸”à¸‚à¸­à¸‡ backup/ à¹€à¸¥à¸¢à¹„à¸¡à¹ˆà¸•à¸£à¸‡à¸à¸±à¸šà¸—à¸µà¹ˆà¸šà¸­à¸—à¸«à¸¢à¸´à¸šà¹„à¸”à¹‰à¸ˆà¸£à¸´à¸‡
    total_files = 0
    for source_folder in queue_folder_paths():
        if not os.path.exists(source_folder):
            continue
        n = 0
        for _root, _dirs, _fs in os.walk(source_folder):
            n += len([f for f in _fs if f.lower().endswith(".xml")])
        total_files += n
        print(f"[FILE] Found {n} files in {source_folder} (à¸£à¸§à¸¡à¹‚à¸Ÿà¸¥à¹€à¸”à¸­à¸£à¹Œà¸¢à¹ˆà¸­à¸¢)")
    ui_stats.update(total=total_files)
    print(f"[FILE] à¸„à¸´à¸§à¸£à¸§à¸¡à¸—à¸±à¹‰à¸‡à¸«à¸¡à¸” {total_files} à¹„à¸Ÿà¸¥à¹Œ")
    
    # Selection
    if not args.cli and GUI_AVAILABLE:
        print(f"{Fore.GREEN}[START] Launching GUI Mode...{Style.RESET_ALL}")
        try:
            ctk.set_appearance_mode("Dark")
            ctk.set_default_color_theme("blue")
            gui = ModernBotGUI(devices, args)
            GUI_INSTANCE = gui
            gui.mainloop()
            sys.exit(0)
        except Exception as e:
            print(f"{Fore.RED}[ERROR] GUI Failed: {e}{Style.RESET_ALL}")
            args.cli = True

    # CLI Mode
    print(f"\n{Fore.CYAN}Starting bot in CLI Mode...{Style.RESET_ALL}")
    
    threads = []
    # If device is specified, only run that one (useful for multi-window mode)
    targets = [args.device] if args.device else devices
    
    # à¸›à¸¥à¹ˆà¸­à¸¢à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™ start_batch à¸•à¸±à¸§ à¹à¸¥à¹‰à¸§à¹€à¸•à¸´à¸¡à¸•à¸±à¸§à¸–à¸±à¸”à¹„à¸›à¸—à¸±à¸™à¸—à¸µà¸—à¸µà¹ˆà¸•à¸±à¸§à¸à¹ˆà¸­à¸™à¸«à¸™à¹‰à¸²à¸ªà¹ˆà¸‡à¸ªà¸±à¸à¸à¸²à¸“à¸žà¸£à¹‰à¸­à¸¡
    delay = float(config.get("thread_delay", 5))
    batch = max(1, int(config.get("start_batch", 4)))
    start_timeout = float(config.get("start_timeout", delay * 4))
    print(f"[INFO] Starting {len(targets)} threads: à¸›à¸¥à¹ˆà¸­à¸¢à¸žà¸£à¹‰à¸­à¸¡à¸à¸±à¸™ {batch} à¸•à¸±à¸§ "
          f"à¹à¸¥à¹‰à¸§à¸•à¹ˆà¸­à¸„à¸´à¸§à¸—à¸±à¸™à¸—à¸µà¸—à¸µà¹ˆà¹à¸•à¹ˆà¸¥à¸°à¸•à¸±à¸§à¸žà¸£à¹‰à¸­à¸¡ (à¹€à¸žà¸”à¸²à¸™ {start_timeout:.0f}s/à¸•à¸±à¸§)")
    ready_q = queue.Queue()
    inflight = 0
    for dev in targets:
        while inflight >= batch:
            try:
                print(f"[INFO] {ready_q.get(timeout=start_timeout)} à¸žà¸£à¹‰à¸­à¸¡à¹à¸¥à¹‰à¸§")
            except queue.Empty:
                print(f"[WARN] à¹„à¸¡à¹ˆà¸¡à¸µà¸ªà¸±à¸à¸à¸²à¸“à¸žà¸£à¹‰à¸­à¸¡à¹ƒà¸™ {start_timeout:.0f}s - à¸›à¸¥à¹ˆà¸­à¸¢à¸•à¸±à¸§à¸–à¸±à¸”à¹„à¸›à¹€à¸¥à¸¢")
            inflight -= 1
        t = RangerGearBot(dev, args)
        t._ready_q = ready_q
        t.start()
        threads.append(t)
        inflight += 1
        
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n[STOP] Keyboard Interrupt. Stopping...")
    print("\n[DONE] All tasks completed.")