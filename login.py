import cv2
import numpy as np
import subprocess
import os
import struct
import re

# ลดการแย่งชิง CPU สำหรับ OpenCV เมื่อรันหลายเครื่องพร้อมกัน
cv2.setNumThreads(1)
import time
from time import sleep
import sys
import shutil
import glob
import tempfile
import json
import threading
import base64
import contextlib
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
import hashlib
import gc

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

REQUIRED_PY_PACKAGES = [
    "pure-python-adb",
    "opencv-python",
    "numpy",
    "psutil",
    "pytesseract",
    "pyperclip",
    "customtkinter",
    "Pillow",
    "easyocr",
]


def print_startup_banner():
    print("============================================")
    print("  Cloudflare WARP + norandom-reid Bot")
    print("============================================")


def ensure_warp_bootstrap():
    """Match the bot-tiket launcher flow: ensure WARP is installed and connected before bot startup."""
    print("[WARP] ตรวจสอบ Cloudflare WARP...")
    warp_root_candidates = [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Cloudflare", "Cloudflare WARP"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Cloudflare", "Cloudflare WARP"),
    ]
    warp_cli = None
    warp_dir = None
    for candidate in warp_root_candidates:
        cli = os.path.join(candidate, "warp-cli.exe")
        if os.path.exists(cli):
            warp_cli = cli
            warp_dir = candidate
            break

    if not warp_cli:
        print("[WARP] ยังไม่ได้ติดตั้ง - กำลังติดตั้งผ่าน winget...")
        try:
            subprocess.run(["winget", "install", "--id", "Cloudflare.Warp", "-e", "--accept-package-agreements", "--accept-source-agreements"], check=False)
        except Exception as e:
            print(f"[WARP] winget ล้มเหลว: {e}")
        for candidate in warp_root_candidates:
            cli = os.path.join(candidate, "warp-cli.exe")
            if os.path.exists(cli):
                warp_cli = cli
                warp_dir = candidate
                break

    if not warp_cli:
        print("[WARP] winget ไม่ได้ผล - พยายามโหลดตัวติดตั้ง...")
        try:
            msi_path = os.path.join(tempfile.gettempdir(), "warp_installer.msi")
            subprocess.run(["curl", "-k", "-L", "-o", msi_path, "https://1111-releases.cloudflareclient.com/win/latest"], check=False)
            if os.path.exists(msi_path):
                subprocess.run(["msiexec", "/i", msi_path, "/qn", "/norestart"], check=False)
                for candidate in warp_root_candidates:
                    cli = os.path.join(candidate, "warp-cli.exe")
                    if os.path.exists(cli):
                        warp_cli = cli
                        warp_dir = candidate
                        break
        except Exception as e:
            print(f"[WARP] โหลด installer ล้มเหลว: {e}")

    if warp_cli and os.path.exists(warp_cli):
        warp_exe = os.path.join(warp_dir, "Cloudflare WARP.exe")
        try:
            if os.path.exists(warp_exe):
                print("[WARP] เปิดโปรแกรม Cloudflare WARP...")
                subprocess.Popen([warp_exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
                time.sleep(4)
            print("[WARP] กำลังเชื่อมต่อ...")
            subprocess.run([warp_cli, "--accept-tos", "connect"], check=False)
        except Exception as e:
            print(f"[WARP] connect ล้มเหลว: {e}")

        for _ in range(15):
            try:
                status = subprocess.run([warp_cli, "status"], capture_output=True, text=True, check=False)
                out = (status.stdout or "") + (status.stderr or "")
                if "Connected" in out or "connected" in out:
                    print("[WARP] เชื่อมต่อสำเร็จ!")
                    return True
            except Exception:
                pass
            time.sleep(4)
        print("[WARP] ยังไม่ Connected แต่จะรันบอทต่อ...")
        return False

    print("[WARP] ติดตั้ง WARP ไม่สำเร็จ - รันบอทต่อโดยไม่มี VPN")
    return False


def ensure_python_requirements():
    print("[PIP] Installing/checking Python packages the bot needs...")
    cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *REQUIRED_PY_PACKAGES]
    try:
        subprocess.run(cmd, check=False)
    except Exception as e:
        print(f"[PIP] pip install ล้มเหลว: {e}")


# Backward-compatible alias for startup flow compatibility.
ensure_runtime_bootstrap = lambda: (print_startup_banner(), ensure_warp_bootstrap(), ensure_python_requirements())

# =========================================================
# Statistics and GUI Tracking
# =========================================================
# ----- Simplified UI Stats Class -----
class RestartTimeoutError(BaseException):
    """ไม่มีการกดอะไรเลยเกิน 500 วิ -> ต้องเด้งออกไปเริ่มไฟล์ใหม่

    สืบจาก BaseException ไม่ใช่ Exception โดยตั้งใจ: ในไฟล์นี้มี `except Exception`
    กับ bare `except` ครอบ capture_screen() อยู่ 20 กว่าจุด ถ้าเป็น Exception ธรรมดา
    มันจะโดนกลืนหมด แล้ววนอยู่ในลูปเดิมตลอดไป (log จะขึ้นคู่ "TIMEOUT: Inactive for
    500s" + "Error: 500s Timeout" ทุก 500 วิ ไม่จบ) พอเป็น BaseException มันจะทะลุ
    ขึ้นไปถึง handler ที่เขียนดักชื่อนี้ไว้จริง ๆ ใน run() แล้ว clear_and_restart
    ไปทำไฟล์ถัดไปได้ตามที่ตั้งใจไว้แต่แรก
    """
    pass

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
        self.random_fail_count = 0 # Counter for gacha/swap_shop failures
        # hero found list with counts
        self.hero_found_list = {}  # {hero_combo: count} e.g. {'Yor': 1, 'Yor+Anya': 2}
        self.total_login_time = 0.0
        self.login_time_count = 0
        
    def _get_shared_file(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared_stats.json")

    def save_shared(self):
        """Save stats to a shared file for multi-process sync (Atomic write)"""
        try:
            with self.lock:
                data = {
                    "success_count": self.success_count,
                    "fail_count": self.fail_count,
                    "random_fail_count": self.random_fail_count,
                    "hero_found_list": self.hero_found_list,
                    "device_statuses": self.device_statuses,
                    "last_update": time.time(),
                    "total_login_time": getattr(self, "total_login_time", 0),
                    "login_time_count": getattr(self, "login_time_count", 0)
                }
                path = self._get_shared_file()
                tmp_path = path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                # Atomic replace with retry for Windows WinError 32
                for _ in range(5):
                    try:
                        os.replace(tmp_path, path)
                        break
                    except OSError:
                        time.sleep(0.1)
                else:
                    # Fallback
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
        except Exception as e:
            print(f"[DEBUG] save_shared error: {e}")

    def load_shared(self):
        """Load stats from the shared file with retries"""
        shared_file = self._get_shared_file()
        if not os.path.exists(shared_file):
            return
            
        for _ in range(5): # Retry up to 5 times
            try:
                with open(shared_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    if not content: continue
                    data = json.loads(content)
                    with self.lock:
                        # Only update if shared data is newer or to merge
                        self.success_count = max(self.success_count, data.get("success_count", 0))
                        self.fail_count = max(self.fail_count, data.get("fail_count", 0))
                        self.random_fail_count = max(self.random_fail_count, data.get("random_fail_count", 0))
                        
                        # Merge hero lists (take max count)
                        shared_heroes = data.get("hero_found_list", {})
                        for h, count in shared_heroes.items():
                            self.hero_found_list[h] = max(self.hero_found_list.get(h, 0), count)
                            
                        # Load login times
                        self.total_login_time = data.get("total_login_time", self.total_login_time)
                        self.login_time_count = data.get("login_time_count", self.login_time_count)
                            
                        # Update device statuses
                        self.device_statuses.update(data.get("device_statuses", {}))
                break
            except Exception as e:
                time.sleep(0.1)

    def record_login_time(self, duration_sec):
        self.load_shared()
        with self.lock:
            self.total_login_time += duration_sec
            self.login_time_count += 1
            self.save_shared()

    def update(self, total=None, processed=None, success=None, fail=None, random_fail=None, devices=None, hero_found=None, hero_not_found=None):
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
            if random_fail is not None:
                self.random_fail_count = max(self.random_fail_count, random_fail)
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

if GUI_AVAILABLE:
    class MainConfigWindow(ctk.CTkToplevel):
        """Window to edit config.json settings"""
        def __init__(self, parent):
            super().__init__(parent)
            self.title("⚙️ ตั้งค่า Config")
            self.geometry("550x650")
            self.parent = parent
            
            self.transient(parent)
            self.grab_set()
            self.focus_force()
            
            self.cfg = self.load_config()
            self.vars = {}
            
            scroll_frame = ctk.CTkScrollableFrame(self, width=500, height=500)
            scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)
            
            ctk.CTkLabel(scroll_frame, text="🎮 ฟีเจอร์เกม", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5), anchor="w")
            
            self.add_switch(scroll_frame, "Loop1 (เปิดเกมครั้งแรก)", "first_loop")
            
            # Black Screen Timeout - ใส่ตัวเลข
            black_timeout_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            black_timeout_frame.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(black_timeout_frame, text="TimeOut จอดำ (วินาที):", anchor="w").pack(side="left")
            self.black_timeout_entry = ctk.CTkEntry(black_timeout_frame, width=80)
            self.black_timeout_entry.insert(0, str(self.cfg.get("black_screen_timeout", 8)))
            self.black_timeout_entry.pack(side="left", padx=10)

            self.add_switch(scroll_frame, "7-Day (รับของ 7 วัน)", "7day")
            self.add_switch(scroll_frame, "แลกแต้มเขียว Leonard", "shopgacha")
            self.add_switch(scroll_frame, "สุ่มตัว (Swap Shop)", "swap_shop")
            self.add_switch(scroll_frame, "สุ่มตัว Event", "swap_shopevent")
            self.add_switch(scroll_frame, "⚡ หลบไก่บี้ (kaibyskip)", "kaibyskip")
            self.add_switch(scroll_frame, "⏩ ข้ามเช็คไก่บี้ (kaibycheck)", "kaibycheck")
            self.add_switch(scroll_frame, "ใช้ตั๋วทั้งหมด", "all-tiket")
            self.add_switch(scroll_frame, "ระบบ Link", "link")
            self.add_switch(scroll_frame, "🎯 ทำเควส (Mission)", "misson")
            self.add_switch(scroll_frame, "ใช้เพชรในการสุ่ม", "all-in")
            
            # Max Gacha - ใส่ตัวเลข
            max_gacha_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            max_gacha_frame.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(max_gacha_frame, text="จำนวนสุ่มสูงสุด (0=ไม่จำกัด):", anchor="w").pack(side="left")
            self.max_gacha_entry = ctk.CTkEntry(max_gacha_frame, width=80)
            self.max_gacha_entry.insert(0, str(self.cfg.get("max-gacha", 0)))
            self.max_gacha_entry.pack(side="left", padx=10)
            
            ctk.CTkFrame(scroll_frame, height=2, fg_color="gray30").pack(fill="x", pady=10)
            ctk.CTkLabel(scroll_frame, text="⚙️ ตั้งค่า Gear", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(5, 5), anchor="w")
            
            self.add_switch(scroll_frame, "Ruby-Gear 200", "ruby-gear200")
            self.add_switch(scroll_frame, "สุ่ม Gear", "random-gear")
            self.add_switch(scroll_frame, "ตรวจสอบ Gear", "check-gear")
            self.add_switch(scroll_frame, "ใช้ OCR (อ่านข้อความ)", "use_ocr")
            
            ctk.CTkFrame(scroll_frame, height=2, fg_color="gray30").pack(fill="x", pady=10)
            ctk.CTkLabel(scroll_frame, text="🔸 ตัวรอง (Hero_low)", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(5, 5), anchor="w")

            low_cfg = self.cfg.get("Hero_low", {}) or {}
            self.hero_low_search = ctk.BooleanVar(value=bool(low_cfg.get("search", 1)))
            self.hero_low_mode = ctk.BooleanVar(value=bool(low_cfg.get("enabled", 0)))
            ctk.CTkSwitch(scroll_frame, text="หาตัวรอง (low1 / low2)",
                          variable=self.hero_low_search).pack(pady=5, padx=20, anchor="w")
            ctk.CTkSwitch(scroll_frame, text="เจอแล้วสุ่มต่อ  (ปิด = เจอแล้วจบเลย)",
                          variable=self.hero_low_mode).pack(pady=5, padx=20, anchor="w")
            ctk.CTkLabel(scroll_frame,
                         text="ตั้งชื่อรูป/ชื่อที่จะใส่ไฟล์ ได้ที่ปุ่ม 🏷 ตั้งชื่อ Ranger",
                         font=ctk.CTkFont(size=10), text_color="gray").pack(anchor="w", padx=25)

            ctk.CTkFrame(scroll_frame, height=2, fg_color="gray30").pack(fill="x", pady=10)
            ctk.CTkLabel(scroll_frame, text="🚀 ความเร็ว (Performance)", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(5, 5), anchor="w")

            self.add_switch(scroll_frame, "⚡ Minitouch (กดเร็ว ไม่เรียก adb ทุกครั้ง)", "minitouch", default=0)
            self.add_switch(scroll_frame, "🧠 จำตำแหน่งปุ่ม (ไม่สแกนทั้งจอซ้ำ)", "pos_cache", default=1)

            scan_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            scan_frame.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(scan_frame, text="สแกน error ทุกกี่วิ (0=ทุกเฟรม):", anchor="w", width=210).pack(side="left")
            self.scan_interval_entry = ctk.CTkEntry(scan_frame, width=60)
            self.scan_interval_entry.insert(0, str(self.cfg.get("scan_interval", 1.0)))
            self.scan_interval_entry.pack(side="left", padx=5)

            loop_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            loop_frame.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(loop_frame, text="หน่วงลูปหาปุ่ม (ว่าง=ค่าเดิม):", anchor="w", width=210).pack(side="left")
            self.loop_delay_entry = ctk.CTkEntry(loop_frame, width=60)
            if self.cfg.get("loop_delay") is not None:
                self.loop_delay_entry.insert(0, str(self.cfg.get("loop_delay")))
            self.loop_delay_entry.pack(side="left", padx=5)

            ctk.CTkFrame(scroll_frame, height=2, fg_color="gray30").pack(fill="x", pady=10)
            ctk.CTkLabel(scroll_frame, text="📦 ตั้งค่ากล่อง", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(5, 5), anchor="w")
            
            box_settings = self.cfg.get("box_settings", {})
            self.box_first_round = ctk.BooleanVar(value=bool(box_settings.get("first_round", 1)))
            self.box_second_round = ctk.BooleanVar(value=bool(box_settings.get("second_round", 1)))
            
            ctk.CTkSwitch(scroll_frame, text="รอบแรก", variable=self.box_first_round).pack(pady=5, padx=20, anchor="w")
            ctk.CTkSwitch(scroll_frame, text="รอบที่สอง", variable=self.box_second_round).pack(pady=5, padx=20, anchor="w")
            
            ctk.CTkFrame(scroll_frame, height=2, fg_color="gray30").pack(fill="x", pady=10)
            ctk.CTkLabel(scroll_frame, text="📡 ตั้งค่าช่อง", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(5, 5), anchor="w")
            
            self.channel_var = ctk.StringVar(value=self.cfg.get("channel", "ch2"))
            channel_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            channel_frame.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(channel_frame, text="เลือกช่อง:").pack(side="left")
            channel_options = ["ch1", "ch2", "ch3", "ch4", "ch5"]
            ctk.CTkOptionMenu(channel_frame, variable=self.channel_var, values=channel_options, width=100).pack(side="left", padx=10)
            
            self.add_switch(scroll_frame, "ใช้รูปช่อง", "channels_img")
            
            # =============================================
            # ส่วนตั้งค่า Auto Trade
            # =============================================
            ctk.CTkFrame(scroll_frame, height=2, fg_color="gray30").pack(fill="x", pady=10)
            ctk.CTkLabel(scroll_frame, text="🛒 Auto Trade (ซื้อของ Swap Shop)", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(5, 5), anchor="w")
            
            auto_trade_cfg = self.cfg.get("auto_trade", {})
            self.auto_trade_enabled = ctk.BooleanVar(value=bool(auto_trade_cfg.get("enabled", 1)))
            ctk.CTkSwitch(scroll_frame, text="เปิดใช้งาน Auto Trade", variable=self.auto_trade_enabled).pack(pady=5, padx=20, anchor="w")
            
            # Shop1 - เพชร
            shop1_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            shop1_frame.pack(fill="x", padx=20, pady=3)
            ctk.CTkLabel(shop1_frame, text="💎 เพชร (swap_shop1):", anchor="w", width=180).pack(side="left")
            self.auto_trade_shop1 = ctk.CTkEntry(shop1_frame, width=60)
            self.auto_trade_shop1.insert(0, str(auto_trade_cfg.get("swap_shop1", 1)))
            self.auto_trade_shop1.pack(side="left", padx=5)
            ctk.CTkLabel(shop1_frame, text="ครั้ง", anchor="w").pack(side="left")
            
            # Shop2 - ตั๋ว
            shop2_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            shop2_frame.pack(fill="x", padx=20, pady=3)
            ctk.CTkLabel(shop2_frame, text="🎟️ ตั๋ว (swap_shop2):", anchor="w", width=180).pack(side="left")
            self.auto_trade_shop2 = ctk.CTkEntry(shop2_frame, width=60)
            self.auto_trade_shop2.insert(0, str(auto_trade_cfg.get("swap_shop2", 1)))
            self.auto_trade_shop2.pack(side="left", padx=5)
            ctk.CTkLabel(shop2_frame, text="ครั้ง", anchor="w").pack(side="left")
            
            # Shopkom - กบฟ้า
            shopkom_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            shopkom_frame.pack(fill="x", padx=20, pady=3)
            ctk.CTkLabel(shopkom_frame, text="🐸 กบฟ้า (swap_shopkom):", anchor="w", width=180).pack(side="left")
            self.auto_trade_shopkom = ctk.CTkEntry(shopkom_frame, width=60)
            self.auto_trade_shopkom.insert(0, str(auto_trade_cfg.get("swap_shopkom", 1)))
            self.auto_trade_shopkom.pack(side="left", padx=5)
            ctk.CTkLabel(shopkom_frame, text="ครั้ง", anchor="w").pack(side="left")
            
            # Shopkom9star - กบ9ดาว
            shopkom9_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            shopkom9_frame.pack(fill="x", padx=20, pady=3)
            ctk.CTkLabel(shopkom9_frame, text="⭐ กบ9ดาว (swap_shopkom9star):", anchor="w", width=180).pack(side="left")
            self.auto_trade_shopkom9star = ctk.CTkEntry(shopkom9_frame, width=60)
            self.auto_trade_shopkom9star.insert(0, str(auto_trade_cfg.get("swap_shopkom9star", 1)))
            self.auto_trade_shopkom9star.pack(side="left", padx=5)
            ctk.CTkLabel(shopkom9_frame, text="ครั้ง", anchor="w").pack(side="left")

            # =============================================
            # ส่วนย้ายไฟล์ login-success → input-id (ตั้งเวลา + ย้ายเอง)
            # =============================================
            ctk.CTkFrame(scroll_frame, height=2, fg_color="gray30").pack(fill="x", pady=10)
            ctk.CTkLabel(scroll_frame, text="📤 ย้ายไฟล์ Success → input-id", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(5, 5), anchor="w")

            move_cfg = self.cfg.get("move_success", {})
            self.move_success_enabled = ctk.BooleanVar(value=bool(move_cfg.get("enabled", 0)))
            ctk.CTkSwitch(scroll_frame, text="เปิดย้ายอัตโนมัติตามเวลา", variable=self.move_success_enabled).pack(pady=5, padx=20, anchor="w")

            move_time_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            move_time_frame.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(move_time_frame, text="เวลาที่ย้าย (HH:MM):", anchor="w").pack(side="left")
            self.move_time_entry = ctk.CTkEntry(move_time_frame, width=80)
            self.move_time_entry.insert(0, str(move_cfg.get("time", "09:00")))
            self.move_time_entry.pack(side="left", padx=10)

            ctk.CTkButton(scroll_frame, text="📤 ย้ายเลยตอนนี้", command=self.manual_move_success, fg_color="#3b8ed0", hover_color="#2f72a8", width=150).pack(pady=5, padx=20, anchor="w")

            # =============================================
            # ส่วนตั้งค่าหน้าจออีมูเลเตอร์ (ต้องตรง ไม่งั้นบอทกดเพี้ยน)
            # =============================================
            ctk.CTkFrame(scroll_frame, height=2, fg_color="gray30").pack(fill="x", pady=10)
            ctk.CTkLabel(scroll_frame, text="⚙ ตั้งค่าจอ MuMu — ความละเอียด / FPS / CPU / RAM / root / renderer / App running (ปล่อยว่าง = ไม่แตะค่าเดิม)", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(5, 5), anchor="w")

            mumu_row = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            mumu_row.pack(fill="x", padx=20, pady=5)

            def _entry(parent, label, value, width=60, color=None):
                ctk.CTkLabel(parent, text=label, anchor="w",
                             text_color=color or "#dddddd").pack(side="left", padx=(0, 3))
                e = ctk.CTkEntry(parent, width=width)
                e.insert(0, "" if value is None else str(value))
                e.pack(side="left", padx=(0, 10))
                return e

            self.screen_w_entry = _entry(mumu_row, "กว้าง", self.cfg.get("screen_width", 960))
            self.screen_h_entry = _entry(mumu_row, "สูง", self.cfg.get("screen_height", 540))
            self.screen_dpi_entry = _entry(mumu_row, "DPI", self.cfg.get("screen_dpi", 160))
            self.mumu_fps_entry = _entry(mumu_row, "FPS", self.cfg.get("mumu_fps", 120), color="#3b8ed0")
            self.mumu_cpu_entry = _entry(mumu_row, "CPU core", self.cfg.get("mumu_cpu", 2))
            self.mumu_ram_entry = _entry(mumu_row, "RAM GB", self.cfg.get("mumu_ram", 2))

            ctk.CTkLabel(mumu_row, text="root", anchor="w").pack(side="left", padx=(0, 3))
            self.mumu_root_menu = ctk.CTkOptionMenu(mumu_row, width=80, values=["", "เปิด", "ปิด"])
            self.mumu_root_menu.set(str(self.cfg.get("mumu_root", "เปิด")))
            self.mumu_root_menu.pack(side="left", padx=(0, 10))

            ctk.CTkLabel(mumu_row, text="renderer", anchor="w").pack(side="left", padx=(0, 3))
            self.mumu_renderer_menu = ctk.CTkOptionMenu(mumu_row, width=100, values=["", "DirectX", "Vulkan"])
            self.mumu_renderer_menu.set(str(self.cfg.get("mumu_renderer", "DirectX")))
            self.mumu_renderer_menu.pack(side="left", padx=(0, 10))

            ctk.CTkLabel(mumu_row, text="App running", anchor="w").pack(side="left", padx=(0, 3))
            self.mumu_app_menu = ctk.CTkOptionMenu(mumu_row, width=80, values=["", "เปิด", "ปิด"])
            self.mumu_app_menu.set(str(self.cfg.get("mumu_app_running", "เปิด")))
            self.mumu_app_menu.pack(side="left", padx=(0, 10))

            ctk.CTkLabel(scroll_frame, text="ค่าที่ปล่อยว่างจะไม่ถูกแตะ · ความละเอียดต้องใส่ครบทั้ง กว้าง+สูง+DPI ถึงจะมีผล · จอที่ปิดอยู่ค่าจะมีผลตอนเปิดครั้งถัดไป",
                         font=ctk.CTkFont(size=11), text_color="#7a8fa6", anchor="w").pack(padx=20, anchor="w")

            self.screen_check_var = ctk.BooleanVar(value=bool(self.cfg.get("screen_check", 1)))
            ctk.CTkSwitch(scroll_frame, text="เช็คค่าพวกนี้ก่อนเริ่ม (ไม่ตรง = ตั้งให้อัตโนมัติ)", variable=self.screen_check_var).pack(pady=5, padx=20, anchor="w")

            self.screen_auto_apply_all_var = ctk.BooleanVar(value=bool(self.cfg.get("screen_auto_apply_all", 1)))
            ctk.CTkSwitch(scroll_frame, text="auto apply to all devices (ทุกจอใช้ profile เดียว)", variable=self.screen_auto_apply_all_var).pack(pady=5, padx=20, anchor="w")

            self.screen_restart_var = ctk.BooleanVar(value=bool(self.cfg.get("screen_restart_mumu", 1)))
            ctk.CTkSwitch(scroll_frame, text="ตั้งค่าแล้วรี MuMu ให้เอง", variable=self.screen_restart_var).pack(pady=5, padx=20, anchor="w")

            self.screen_relaunch_var = ctk.BooleanVar(value=bool(self.cfg.get("screen_auto_relaunch", 1)))
            ctk.CTkSwitch(scroll_frame, text="รีเสร็จแล้วรันโปรแกรมใหม่เอง (auto)", variable=self.screen_relaunch_var).pack(pady=5, padx=20, anchor="w")

            ctk.CTkButton(scroll_frame, text="⚙ ตั้งค่าจอเลยตอนนี้", command=self.manual_set_display,
                          fg_color="#3b8ed0", hover_color="#2f72a8", width=180).pack(pady=5, padx=20, anchor="w")

            btn_frame = ctk.CTkFrame(self, fg_color="transparent")
            btn_frame.pack(fill="x", padx=20, pady=10)
            
            ctk.CTkButton(btn_frame, text="💾 บันทึก", command=self.save, fg_color="#2cc985", hover_color="#229f69", width=150).pack(side="left", padx=5)
            ctk.CTkButton(btn_frame, text="❌ ยกเลิก", command=self.destroy, fg_color="#555555", hover_color="#444444", width=100).pack(side="right", padx=5)
        
        def load_config(self):
            try:
                if os.path.exists('configmain.json'):
                    with open('configmain.json', 'r', encoding='utf-8') as f:
                        return json.load(f)
            except Exception as e:
                print(f"Error loading config: {e}")
            return {}
        
        def add_switch(self, parent, label, key, default=0):
            val = self.cfg.get(key, default)
            var = ctk.BooleanVar(value=bool(val))
            self.vars[key] = var
            ctk.CTkSwitch(parent, text=label, variable=var).pack(pady=5, padx=20, anchor="w")

        def manual_set_display(self):
            """กดตั้งค่าจอ MuMu ตามช่องข้างบนเดี๋ยวนี้ (บันทึกก่อนแล้วค่อยสั่ง)"""
            try:
                self.save(close=False)
                r = mumu_set_display(restart=bool(config.get("screen_restart_mumu", 1)))
                if r["changed"]:
                    msg = f"ตั้งค่าแล้ว {len(set(r['changed']))} จอ, รีสตาร์ท {len(r['restarted'])} จอ"
                elif r["errors"]:
                    msg = "ตั้งค่าไม่สำเร็จ"
                else:
                    msg = "ทุกจอค่าตรงอยู่แล้ว ไม่ต้องแก้"
                if r["errors"]:
                    msg += chr(10)*2 + chr(10).join(r["errors"][:5])
                messagebox.showinfo("ตั้งค่าจอ MuMu", msg)
            except Exception as e:
                messagebox.showerror("Error", f"ตั้งค่าจอไม่สำเร็จ: {e}")

        def manual_move_success(self):
            """ย้ายไฟล์จาก login-success ไป input-id เดี๋ยวนี้ (กดเอง)"""
            try:
                move_cfg = self.cfg.get("move_success", {})
                src = move_cfg.get("source", "login-success")
                dst = move_cfg.get("dest", "input-id")
                moved, msg = move_success_to_input(src, dst)
                messagebox.showinfo("ย้ายไฟล์", msg)
                try:
                    self.parent.log("INFO", f"📤 {msg}")
                except Exception:
                    pass
            except Exception as e:
                messagebox.showerror("Error", f"ย้ายไม่สำเร็จ: {e}")

        def save(self, close=True):
            """close=False = บันทึกเงียบ ๆ ไม่ปิดหน้าต่าง (ใช้ตอนกดปุ่มตั้งค่าจอ)"""
            try:
                for key, var in self.vars.items():
                    self.cfg[key] = 1 if var.get() else 0
                
                if "box_settings" not in self.cfg:
                    self.cfg["box_settings"] = {}
                self.cfg["box_settings"]["first_round"] = 1 if self.box_first_round.get() else 0
                self.cfg["box_settings"]["second_round"] = 1 if self.box_second_round.get() else 0
                self.cfg["channel"] = self.channel_var.get()
                
                # Save max-gacha as number
                try:
                    self.cfg["max-gacha"] = int(self.max_gacha_entry.get())
                except:
                    self.cfg["max-gacha"] = 0
                
                # Save black_screen_timeout as number
                try:
                    self.cfg["black_screen_timeout"] = int(self.black_timeout_entry.get())
                except:
                    self.cfg["black_screen_timeout"] = 8

                # Hero_low - แตะแค่ 2 สวิตช์นี้ ชื่อรูป/ชื่อไฟล์ (low1, low2) เป็นของ
                # หน้าต่าง "ตั้งชื่อ Ranger" ต้องคงไว้ ไม่งั้นกดบันทึกที่นี่แล้วชื่อหาย
                low_cfg = self.cfg.get("Hero_low")
                if not isinstance(low_cfg, dict):
                    low_cfg = {}
                low_cfg["search"] = 1 if self.hero_low_search.get() else 0
                low_cfg["enabled"] = 1 if self.hero_low_mode.get() else 0
                self.cfg["Hero_low"] = low_cfg

                try:
                    self.cfg["scan_interval"] = float(self.scan_interval_entry.get())
                except:
                    self.cfg["scan_interval"] = 1.0

                # blank = ไม่ override ปล่อยให้แต่ละลูปใช้ค่าเดิมของมัน
                loop_txt = self.loop_delay_entry.get().strip()
                if not loop_txt:
                    self.cfg["loop_delay"] = None
                else:
                    try:
                        self.cfg["loop_delay"] = float(loop_txt)
                    except:
                        self.cfg["loop_delay"] = None
                
                # Save auto_trade settings
                if "auto_trade" not in self.cfg:
                    self.cfg["auto_trade"] = {}
                self.cfg["auto_trade"]["enabled"] = 1 if self.auto_trade_enabled.get() else 0
                try:
                    self.cfg["auto_trade"]["swap_shop1"] = int(self.auto_trade_shop1.get())
                except:
                    self.cfg["auto_trade"]["swap_shop1"] = 1
                try:
                    self.cfg["auto_trade"]["swap_shop2"] = int(self.auto_trade_shop2.get())
                except:
                    self.cfg["auto_trade"]["swap_shop2"] = 1
                try:
                    self.cfg["auto_trade"]["swap_shopkom"] = int(self.auto_trade_shopkom.get())
                except:
                    self.cfg["auto_trade"]["swap_shopkom"] = 1
                try:
                    self.cfg["auto_trade"]["swap_shopkom9star"] = int(self.auto_trade_shopkom9star.get())
                except:
                    self.cfg["auto_trade"]["swap_shopkom9star"] = 1

                # Save move_success settings (ย้ายไฟล์ login-success → input-id)
                if "move_success" not in self.cfg:
                    self.cfg["move_success"] = {}
                self.cfg["move_success"]["enabled"] = 1 if self.move_success_enabled.get() else 0
                self.cfg["move_success"]["time"] = (self.move_time_entry.get().strip() or "09:00")
                self.cfg["move_success"].setdefault("source", "login-success")
                self.cfg["move_success"].setdefault("dest", "input-id")

                # Save screen settings (ตั้งค่าหน้าจออีมูเลเตอร์)
                self.cfg["screen_check"] = 1 if self.screen_check_var.get() else 0
                self.cfg["screen_auto_apply_all"] = 1 if self.screen_auto_apply_all_var.get() else 0
                self.cfg["screen_restart_mumu"] = 1 if self.screen_restart_var.get() else 0
                self.cfg["screen_auto_relaunch"] = 1 if self.screen_relaunch_var.get() else 0
                # ช่องตัวเลข: ว่าง = "" (ไม่แตะค่าเดิมของอีมู), ไม่ใช่เลข = คืนค่าเดิมใน config
                for key, entry in (("screen_width", self.screen_w_entry),
                                   ("screen_height", self.screen_h_entry),
                                   ("screen_dpi", self.screen_dpi_entry),
                                   ("mumu_fps", self.mumu_fps_entry),
                                   ("mumu_cpu", self.mumu_cpu_entry),
                                   ("mumu_ram", self.mumu_ram_entry)):
                    raw = entry.get().strip()
                    if raw == "":
                        self.cfg[key] = ""
                        continue
                    try:
                        self.cfg[key] = int(float(raw))
                    except Exception:
                        pass   # กรอกมั่ว = เก็บค่าเดิมไว้
                self.cfg["mumu_root"] = self.mumu_root_menu.get().strip()
                self.cfg["mumu_renderer"] = self.mumu_renderer_menu.get().strip()
                self.cfg["mumu_app_running"] = self.mumu_app_menu.get().strip()

                with open('configmain.json', 'w', encoding='utf-8') as f:
                    json.dump(self.cfg, f, indent=4, ensure_ascii=False)
                
                if close:
                    messagebox.showinfo("สำเร็จ", "บันทึก Config เรียบร้อย!")
                try:
                    global load_config
                    load_config()
                except Exception as ex:
                    print(ex)
                self.parent.log("INFO", "✅ Config.json อัพเดทแล้ว")
                if close:
                    self.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"บันทึกไม่สำเร็จ: {e}")


    class HeroConfigWindow(ctk.CTkToplevel):
        """
        หน้าต่างตั้งค่าชื่อ Ranger และ Gear
        HERO_MAPPING = ตั้งชื่อ Ranger ที่จะได้เมื่อพบรูป
        เช่น gachahero1.png พบแล้วจะตั้งชื่อไฟล์เป็น "som+"
        """
        def __init__(self, parent):
            super().__init__(parent)
            self.title("🦸 ตั้งชื่อ Ranger & Gear")
            self.geometry("600x700")
            self.parent = parent
            
            self.transient(parent)
            self.grab_set()
            self.focus_force()
            
            self.cfg = self.load_config()
            
            self.tabview = ctk.CTkTabview(self, width=550, height=550)
            self.tabview.pack(fill="both", expand=True, padx=20, pady=10)
            
            self.tabview.add("🦸 Rangers")
            self.tabview.add("⚙️ Gears")
            self.tabview.add("🔫 Weapons")
            
            self.setup_hero_tab()
            self.setup_gear_tab()
            self.setup_weapon_tab()
            
            ctk.CTkButton(self, text="💾 บันทึกทั้งหมด", command=self.save_all, fg_color="#2cc985", hover_color="#229f69").pack(pady=10)
        
        def load_config(self):
            try:
                if os.path.exists('configmain.json'):
                    with open('configmain.json', 'r', encoding='utf-8') as f:
                        return json.load(f)
            except Exception as e:
                print(f"Error loading config: {e}")
            return {}
        
        def setup_hero_tab(self):
            tab = self.tabview.tab("🦸 Rangers")
            
            # คำอธิบาย
            desc_frame = ctk.CTkFrame(tab, fg_color="#2b2b2b", corner_radius=8)
            desc_frame.pack(fill="x", padx=10, pady=(10, 5))
            ctk.CTkLabel(
                desc_frame, 
                text="📌 ตั้งชื่อ Ranger ที่จะบันทึก\\n📂 รูปอยู่ที่: img/ranger/gachaheroX.png\\n💡 เปลี่ยนรูปได้ง่าย แค่วางไฟล์ใหม่ทับ", 
                font=ctk.CTkFont(size=11),
                text_color="gray",
                justify="left"
            ).pack(padx=10, pady=5)
            
            ctk.CTkLabel(tab, text="รูป → ชื่อ Ranger", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=5)
            
            self.hero_entries = {}
            hero_mapping = self.cfg.get("HERO_MAPPING", {})
            
            scroll = ctk.CTkScrollableFrame(tab, width=480, height=300)
            scroll.pack(fill="both", expand=True, padx=10)
            
            for img, name in hero_mapping.items():
                frame = ctk.CTkFrame(scroll, fg_color="transparent")
                frame.pack(fill="x", pady=2)
                ctk.CTkLabel(frame, text=f"{img}.png:", width=130, anchor="e").pack(side="left")
                entry = ctk.CTkEntry(frame, width=200)
                entry.insert(0, name)
                entry.pack(side="left", padx=5)
                self.hero_entries[img] = entry

            # ---- Hero_low: ตัวรอง เจอแล้วไม่จบงาน แค่เอาชื่อไปต่อหน้าชื่อไฟล์ ----
            ctk.CTkFrame(scroll, height=2, fg_color="gray30").pack(fill="x", pady=10)
            ctk.CTkLabel(scroll, text="🔸 ตัวรอง (Hero_low)",
                         font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(5, 2), anchor="w")
            ctk.CTkLabel(
                scroll,
                text="หาตัวรองเสมอถ้าตั้งรูปไว้ สวิตช์ข้างล่างคุมแค่ว่า 'เจอแล้วทำอะไรต่อ'\n"
                     "  เปิด  = จดชื่อไว้แล้วสุ่มต่อ เจอตัวหลักทีหลัง -> ตัวรอง+ตัวหลัก\n"
                     "          สุ่มจนจบไม่เจอตัวหลัก -> เก็บเข้า backup-id ด้วยชื่อตัวรอง\n"
                     "  ปิด   = เจอแล้วจบเลย ส่งไฟล์ออกทันที ไม่สุ่มต่อ\n"
                     "ไม่อยากให้หาเลย -> ลบชื่อในช่องข้างล่างให้ว่าง",
                font=ctk.CTkFont(size=10), text_color="gray", justify="left").pack(anchor="w", padx=5)

            low_cfg = self.cfg.get("Hero_low", {}) or {}
            self.hero_low_enabled = ctk.BooleanVar(value=bool(low_cfg.get("enabled", 0)))
            ctk.CTkSwitch(scroll, text="เจอตัวรองแล้วสุ่มต่อ  (ปิด = เจอแล้วจบเลย)",
                          variable=self.hero_low_enabled).pack(pady=5, padx=5, anchor="w")

            self.hero_low_entries = {}
            for key in sorted(k for k in low_cfg.keys() if k != "enabled") or ["low1", "low2"]:
                item = low_cfg.get(key)
                if isinstance(item, dict):
                    img_v, name_v = item.get("img", f"{key}.bmp"), item.get("name", "")
                elif isinstance(item, str):
                    img_v, name_v = f"{key}.bmp", item
                else:
                    img_v, name_v = f"{key}.bmp", ""
                frame = ctk.CTkFrame(scroll, fg_color="transparent")
                frame.pack(fill="x", pady=2)
                ctk.CTkLabel(frame, text=f"{key}:", width=50, anchor="e").pack(side="left")
                e_img = ctk.CTkEntry(frame, width=120, placeholder_text="low1.bmp")
                e_img.insert(0, img_v)
                e_img.pack(side="left", padx=3)
                ctk.CTkLabel(frame, text="→", width=20).pack(side="left")
                e_name = ctk.CTkEntry(frame, width=150, placeholder_text="kikoru+")
                e_name.insert(0, name_v)
                e_name.pack(side="left", padx=3)
                self.hero_low_entries[key] = (e_img, e_name)

        def setup_gear_tab(self):
            tab = self.tabview.tab("⚙️ Gears")
            
            desc_frame = ctk.CTkFrame(tab, fg_color="#2b2b2b", corner_radius=8)
            desc_frame.pack(fill="x", padx=10, pady=(10, 5))
            ctk.CTkLabel(
                desc_frame, 
                text="📌 ตั้งชื่อ Gear ที่จะบันทึก\\nเมื่อบอทพบรูป gearimgX.png จะตั้งชื่อไฟล์ตามที่กำหนด", 
                font=ctk.CTkFont(size=11),
                text_color="gray",
                justify="left"
            ).pack(padx=10, pady=5)
            
            ctk.CTkLabel(tab, text="รูป → ชื่อ Gear", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=5)
            
            self.gear_entries = {}
            gear_mapping = self.cfg.get("gearname", {})
            
            scroll = ctk.CTkScrollableFrame(tab, width=480, height=300)
            scroll.pack(fill="both", expand=True, padx=10)
            
            for img, name in gear_mapping.items():
                frame = ctk.CTkFrame(scroll, fg_color="transparent")
                frame.pack(fill="x", pady=2)
                ctk.CTkLabel(frame, text=f"{img}.png:", width=130, anchor="e").pack(side="left")
                entry = ctk.CTkEntry(frame, width=200)
                entry.insert(0, name)
                entry.pack(side="left", padx=5)
                self.gear_entries[img] = entry
        
        def setup_weapon_tab(self):
            tab = self.tabview.tab("🔫 Weapons")
            ctk.CTkLabel(tab, text="เปิด/ปิด Weapon ที่ต้องการตรวจสอบ", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)
            
            self.weapon_vars = {}
            weapon_mapping = self.cfg.get("weaponname", {})
            
            for img, enabled in weapon_mapping.items():
                var = ctk.BooleanVar(value=enabled == "true" or enabled == True)
                self.weapon_vars[img] = var
                ctk.CTkSwitch(tab, text=img, variable=var).pack(pady=5, padx=20, anchor="w")
        
        def save_all(self):
            try:
                hero_mapping = {}
                for img, entry in self.hero_entries.items():
                    hero_mapping[img] = entry.get()
                self.cfg["HERO_MAPPING"] = hero_mapping

                # Hero_low - เก็บเฉพาะแถวที่กรอกครบทั้งชื่อรูปและชื่อที่จะใส่ไฟล์
                # "search" เป็นของหน้าต่าง Config ต้องคงค่าเดิมไว้ ไม่งั้นบันทึกที่นี่
                # แล้วสวิตช์ "หาตัวรอง" จะถูกรีเซ็ต
                prev_low = self.cfg.get("Hero_low")
                prev_search = prev_low.get("search", 1) if isinstance(prev_low, dict) else 1
                hero_low = {"search": prev_search,
                            "enabled": 1 if self.hero_low_enabled.get() else 0}
                for key, (e_img, e_name) in self.hero_low_entries.items():
                    img_v, name_v = e_img.get().strip(), e_name.get().strip()
                    if img_v and name_v:
                        hero_low[key] = {"img": img_v, "name": name_v}
                self.cfg["Hero_low"] = hero_low

                gear_mapping = {}
                for img, entry in self.gear_entries.items():
                    gear_mapping[img] = entry.get()
                self.cfg["gearname"] = gear_mapping
                
                weapon_mapping = {}
                for img, var in self.weapon_vars.items():
                    weapon_mapping[img] = "true" if var.get() else "false"
                self.cfg["weaponname"] = weapon_mapping
                
                with open('configmain.json', 'w', encoding='utf-8') as f:
                    json.dump(self.cfg, f, indent=4, ensure_ascii=False)
                
                messagebox.showinfo("สำเร็จ", "บันทึก Ranger & Gear เรียบร้อย!")
                try:
                    global load_config
                    load_config()
                except Exception as ex:
                    print(ex)
                self.parent.log("INFO", "✅ Ranger & Gear อัพเดทแล้ว")
                self.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"บันทึกไม่สำเร็จ: {e}")


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
        def __init__(self, devices, args):
            super().__init__()
            global GUI_INSTANCE
            GUI_INSTANCE = self
            
            self.title("loginสะสม")
            self.geometry("720x550")
            self.devices = devices
            self.args = args
            self.bot_threads = []
            self.device_monitors = {}
            self.hero_stats_labels = {}
            self.hero_rows = {}
            self.hero_filter_text = ""
            self.is_started = False
            self._last_move_date = None  # กันย้ายซ้ำในวันเดียวกัน (scheduled move)

            self.setup_ui()

            # Handle window close
            self.protocol("WM_DELETE_WINDOW", self.on_closing)

            # Use after to start the stats loop without blocking the constructor
            self.after(100, self.update_realtime_stats)
            # Scheduled file-move checker (login-success → input-id)
            self.after(5000, self.check_scheduled_move)
            
            # Ensure window is visible and raised to the front before any auto-start trigger.
            self.deiconify()
            self.lift()
            self.focus_force()
            try:
                self.attributes('-topmost', True)
                self.update_idletasks()
                self.after(50, lambda: self.attributes('-topmost', False))
            except Exception:
                pass
            print("[GUI] Launched Successfully. Waiting for manual start.")
            
            if getattr(self.args, 'no_start', False):
                print("[GUI] Monitor mode active (No internal threads).")
                self.lbl_auto_start.configure(text="[ DASHBOARD MODE ]", text_color="#ffae42")
            else:
                self.lbl_auto_start.configure(text="[ WAITING FOR START ]", text_color="#aaaaaa")
                # Auto-start is opt-in only. Default is disabled to prevent accidental launches.
                cloud_fast_enabled = bool(config.get("cloud_fast_start", config.get("auto_start", 0)))
                delay_sec = float(config.get("cloud_start_delay_sec", 2.0))
                if cloud_fast_enabled:
                    print(f"[GUI] cloud_fast_start=1 - จะเริ่มบอทอัตโนมัติใน {delay_sec:.1f} วินาที")
                    self.lbl_auto_start.configure(text=f"[ AUTO-START IN {delay_sec:.0f}s ]", text_color="#ff9800")
                    self.after(int(delay_sec * 1000), lambda: (self.lift(), self.focus_force(), self.start_bot()))
                else:
                    print("[GUI] Auto-start disabled. Press START to launch the bot.")

            # Initialize cached stats and start background thread to offload disk I/O from Main Thread
            self.qsize = 0
            self.backup_id_counts = {}
            self.folder_counts = {}       # นับไฟล์จริงในโฟลเดอร์ (รีเฟรชทุก 30 วิ)
            self.bg_stats_thread = threading.Thread(target=self._bg_stats_counter_loop, daemon=True)
            self.bg_stats_thread.start()

        def _bg_stats_counter_loop(self):
            while True:
                try:
                    # 1. Count files in queue folders (backup/ + input-id/)
                    _base = os.path.dirname(os.path.abspath(__file__))
                    qsize = 0
                    for _qf in queue_folder_names():
                        source_folder = os.path.join(_base, _qf)
                        if os.path.exists(source_folder):
                            for _root, _dirs, _files in os.walk(source_folder):
                                qsize += len([f for f in _files if f.lower().endswith(".xml")])
                    self.qsize = qsize

                    # 2. Count files in backup-id folder
                    backup_id_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup-id")
                    counts = {}
                    if os.path.exists(backup_id_folder):
                        for f in os.listdir(backup_id_folder):
                            if os.path.isfile(os.path.join(backup_id_folder, f)) and f.lower().endswith(".xml"):
                                prefix = f.split("-")[0].replace(".xml", "").replace(".XML", "")
                                counts[prefix] = counts.get(prefix, 0) + 1
                    self.backup_id_counts = counts
                    # 3. นับไฟล์จริงในโฟลเดอร์ผลลัพธ์ (login-success / login-failed / ฯลฯ)
                    #    ของหนัก -> ทำทุก 30 วิพอ ไม่ให้ดิสก์ทำงานถี่เกิน
                    if time.time() - getattr(self, "_last_folder_scan", 0) >= 30:
                        self._last_folder_scan = time.time()
                        fc = {}
                        for name in ("login-success", "login-failed", "random-fail",
                                     "not-found", "kaiby", "7day-check"):
                            folder = os.path.join(_base, name)
                            n = 0
                            if os.path.isdir(folder):
                                for _root, _dirs, _files in os.walk(folder):
                                    n += len([f for f in _files if f.lower().endswith(".xml")])
                            fc[name] = n
                        self.folder_counts = fc
                except Exception as e:
                    print(f"[GUI BG] Stats helper error: {e}")
                time.sleep(5)  # Scan every 5 seconds

        def setup_ui(self):
            # 1. TOP TOOLBAR
            toolbar = ctk.CTkFrame(self, height=40, fg_color="#333333", corner_radius=0)
            toolbar.pack(fill="x")
            toolbar.pack_propagate(False)
            
            self.lbl_status = ctk.CTkLabel(toolbar, text=f"   ● ONLINE ({len(self.devices)})", font=ctk.CTkFont(size=12, weight="bold"), text_color="#4caf50")
            self.lbl_status.pack(side="left", padx=5)

            self.btn_start = ctk.CTkButton(toolbar, text="▶ START", font=ctk.CTkFont(size=12, weight="bold"), width=80, height=24, fg_color="#e53935", hover_color="#c62828", command=self.start_bot)
            self.btn_start.pack(side="left", padx=10)
            
            self.lbl_auto_start = ctk.CTkLabel(toolbar, text="[ WAITING FOR START ]", font=ctk.CTkFont(size=10, weight="bold"), text_color="#aaaaaa")
            self.lbl_auto_start.pack(side="left", padx=5)
            # Stats on Toolbar (right)
            counter_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
            counter_frame.pack(side="right", padx=10)
            
            self.lbl_file_count = ctk.CTkLabel(counter_frame, text="📁 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa")
            self.lbl_file_count.pack(side="left", padx=8)

            self.lbl_succ_count = ctk.CTkLabel(counter_frame, text="✅ 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#4caf50")
            self.lbl_succ_count.pack(side="left", padx=8)
            
            self.lbl_fail_count = ctk.CTkLabel(counter_frame, text="❌ 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#ff5555")
            self.lbl_fail_count.pack(side="left", padx=8)

            self.lbl_random_fail = ctk.CTkLabel(counter_frame, text="🎲 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#ffa500")
            self.lbl_random_fail.pack(side="left", padx=8)
            
            self.lbl_avg_time = ctk.CTkLabel(toolbar, text="Avg: -", font=ctk.CTkFont(size=12, weight="bold"), text_color="#2196f3")
            self.lbl_avg_time.pack(side="right", padx=15)

            from datetime import datetime
            start_time_str = datetime.now().strftime("%H:%M:%S")
            self.lbl_start_time = ctk.CTkLabel(toolbar, text=f"Started: {start_time_str}", font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa")
            self.lbl_start_time.pack(side="right", padx=15)
            
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
            ctk.CTkLabel(title_row, text="   🏆 HEROES FOUND", font=ctk.CTkFont(size=11, weight="bold"), text_color="#f2c94c", anchor="w").pack(side="left")
            self.lbl_filter_count = ctk.CTkLabel(title_row, text="Filtered: 0", font=ctk.CTkFont(size=10), text_color="#aaaaaa")
            self.lbl_filter_count.pack(side="right", padx=10)
            
            # Filter Entry
            filter_frame = ctk.CTkFrame(hero_header, fg_color="transparent", height=24)
            filter_frame.pack(fill="x", padx=5, pady=2)
            self.ent_filter = ctk.CTkEntry(filter_frame, placeholder_text="🔍 Search heroes or gear (e.g. lapel)...", font=ctk.CTkFont(size=11), height=22, fg_color="#1e1e1e", border_width=1)
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
            backup_folder = os.path.join(base_path, queue_folder_names()[0])   # ปุ่ม Backup เปิดโฟลเดอร์คิว
            heroes_folder = os.path.join(base_path, "backup-id")
            
            ctk.CTkButton(bottom_bar, text="🔌 Connect Missing", width=85, height=22, font=ctk.CTkFont(size=10), fg_color="#4caf50", command=self.connect_missing_devices).pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="⚙ Config", width=70, height=22, font=ctk.CTkFont(size=10), fg_color="#555555", command=self.open_config).pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="📡 Apply All", width=80, height=22, font=ctk.CTkFont(size=10), fg_color="#3b8ed0", hover_color="#2f72a8", command=self.apply_display_to_all_devices_gui).pack(side="left", padx=3, pady=4)
            # HeroConfigWindow เคยไม่มีปุ่มเปิดเลย - ตั้งชื่อ Ranger/Gear/Weapon และ Hero_low อยู่ในนี้
            ctk.CTkButton(bottom_bar, text="🏷 ตั้งชื่อ Ranger", width=100, height=22, font=ctk.CTkFont(size=10), fg_color="#7a5cc4", hover_color="#63499f", command=self.open_heroes).pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="📁 Backup", width=70, height=22, font=ctk.CTkFont(size=10), fg_color="#555555", command=lambda: subprocess.Popen(f'explorer "{backup_folder}"')).pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="🦸 Heroes", width=70, height=22, font=ctk.CTkFont(size=10), fg_color="#555555", command=lambda: subprocess.Popen(f'explorer "{heroes_folder}"')).pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="📤 ย้าย Success", width=85, height=22, font=ctk.CTkFont(size=10), fg_color="#3b8ed0", command=self.move_success_now).pack(side="left", padx=3, pady=4)
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
                    
                    # Start bot process (แยก process เหมือน CLI mode)
                    if getattr(self, 'is_started', False) and not getattr(self.args, 'no_start', False):
                        import multiprocessing
                        args_dict = vars(self.args) if hasattr(self.args, '__dict__') else {}
                        p = multiprocessing.Process(
                            target=run_bot_process,
                            args=(dev, args_dict, getattr(self, "_ready_q", None)),
                            name=f"Bot-{dev}"
                        )
                        p.daemon = True
                        p.start()
                        self.bot_threads.append(p)
                    self.log("SUCCESS", f"Connected new device: {dev}")
            
            if new_count > 0:
                self.lbl_status.configure(text=f"   ● ONLINE ({len(self.devices)})")
            else:
                self.log("INFO", "No new devices found.")

        def apply_display_to_all_devices_gui(self):
            """Push the current resolution/FPS/renderer profile to every connected MuMu device."""
            try:
                self.log("INFO", "Applying display profile to all connected devices...")
                result = apply_display_to_all_devices(self.devices)
                changed = len(set(result.get("changed", []))) if result.get("changed") else 0
                restarted = len(set(result.get("restarted", []))) if result.get("restarted") else 0
                errors = result.get("errors", [])
                if changed or restarted:
                    self.log("SUCCESS", f"Apply all devices: updated {changed} device(s), restarted {restarted} device(s)")
                else:
                    self.log("INFO", "Apply all devices: already aligned with configured profile")
                if errors:
                    self.log("WARN", "; ".join(errors[:3]))
            except Exception as e:
                self.log("ERROR", f"Apply all devices failed: {e}")

        def log(self, level, message): 
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"[{ts}] {message}\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

        def _start_single_bot(self, device_id):
            import multiprocessing
            args_dict = vars(self.args) if hasattr(self.args, '__dict__') else {}
            p = multiprocessing.Process(
                target=run_bot_process,
                args=(device_id, args_dict, getattr(self, "_ready_q", None)),
                name=f"Bot-{device_id}"
            )
            p.daemon = True
            p.start()
            self.bot_threads.append(p)
            self.log("INFO", f"🚀 Started bot process on {device_id} (PID: {p.pid})")

        def _ramp_tick(self):
            """ปล่อยบอทตัวถัดไปทันทีที่ตัวก่อนหน้าพร้อม - ไม่นอนรอเวลาเปล่า ๆ

            เดิมจองเวลาไว้ล่วงหน้าตายตัว (i // batch * delay) เครื่องที่พร้อมเร็ว
            ก็ต้องรอจนครบเวลาอยู่ดี ตอนนี้ delay เหลือเป็นแค่เพดานกันค้าง
            """
            # 1) เก็บสัญญาณ "พร้อมแล้ว" ที่บอทส่งกลับมา
            while True:
                try:
                    dev = self._ready_q.get_nowait()
                except Exception:
                    break
                if self._starting.pop(dev, None) is not None:
                    self.log("SUCCESS", f"✓ {dev} พร้อม (เหลือรอคิว {len(self._pending)})")
            # 2) ตัวที่เงียบเกินเพดาน ไม่รอแล้ว (emulator ค้าง/ยังบูตไม่เสร็จ)
            now = time.time()
            for dev, t0 in list(self._starting.items()):
                if now - t0 > self._start_timeout:
                    self._starting.pop(dev, None)
                    self.log("WARN", f"{dev} ไม่ตอบใน {self._start_timeout:.0f}s - ปล่อยตัวถัดไปเลย")
            # 3) มีสล็อตว่างเท่าไหร่ ปล่อยเท่านั้น - แต่ห้ามปล่อยติดกันเร็วกว่า _gap วิ
            #    (เน็ตดึงกันตอนหลายจอโหลดเกมพร้อมกัน = ค้าง/หลุดตั้งแต่หน้าโหลด)
            while self._pending and len(self._starting) < self._slots:
                wait = self._gap - (time.time() - self._last_launch)
                if wait > 0:
                    break                      # ยังไม่ถึงเวลา - รอ tick ถัดไป (เช็คทุก 200ms)
                dev = self._pending.pop(0)
                self._starting[dev] = time.time()
                self._last_launch = time.time()
                self._start_single_bot(dev)
            if self._pending or self._starting:
                self.after(200, self._ramp_tick)
            else:
                self.log("SUCCESS", f"ปล่อยบอทครบ {len(self.devices)} เครื่องแล้ว "
                                    f"(ใช้เวลา {time.time() - self._ramp_started:.0f}s)")


        def start_bot(self):
            if getattr(self, 'is_started', False):
                self.log("WARN", "Bot is already running.")
                return
            self.is_started = True
            if hasattr(self, 'btn_start'):
                self.btn_start.configure(state="disabled", fg_color="#555555", text="⏳ RUNNING")
            self.lbl_auto_start.configure(text="[ BOT IS RUNNING ]", text_color="#4caf50")
            
            # กด START = ปล่อย "ทีละจอ" ไม่ปล่อยพร้อมกัน - เน็ตจะได้ไม่ดึงกันตอนโหลดเกม
            # ตัวถัดไปออกเมื่อ "ตัวก่อนหน้าพร้อม (หรือเกินเพดาน)" และ "ห่างจากตัวก่อน
            # อย่างน้อย thread_delay วิ" แล้วแต่อย่างไหนช้ากว่า
            import multiprocessing
            self._ready_q = multiprocessing.Queue()
            self._pending = list(self.devices)
            self._starting = {}
            self._slots = max(1, int(config.get("start_slots", 1)))      # 1 = ทีละจอ
            self._gap = float(config.get("thread_delay", 5))             # เว้นระยะระหว่างจอ
            self._last_launch = 0.0
            self._start_timeout = float(config.get("start_timeout", float(config.get("thread_delay", 5)) * 4))
            self._ramp_started = time.time()
            self.log("INFO", f"Starting {len(self._pending)} Bot Processes: ปล่อยทีละ {self._slots} จอ "
                             f"เว้น {self._gap:.0f}s ต่อจอ (เพดานรอต่อจอ {self._start_timeout:.0f}s)")
            self._ramp_tick()

        def on_closing(self):
            if messagebox.askokcancel("Quit", "คุณต้องการหยุดบอทและปิดโปรแกรมใช่หรือไม่?\n(จะทำการ Kill ADB และ Python ทั้งหมด)"):
                print("[GUI] Shutting down... Killing background processes.")
                try:
                    # Kill ADB and Python processes on Windows
                    if os.name == 'nt':
                        subprocess.run("taskkill /F /IM adb.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        # We don't kill python.exe here because it would kill THIS process too early.
                        # We use os._exit(0) at the end.
                except:
                    pass
                self.destroy()
                os._exit(0)

        def update_realtime_stats(self):
            try:
                # Load shared stats from other processes
                ui_stats.load_shared()
                
                with ui_stats.lock:
                    # Get cached file count from background thread
                    qsize = getattr(self, "qsize", 0)
                    
                    # ตัวเลขบนแถบบน = จำนวนไฟล์จริงในโฟลเดอร์ (อัปเดตทุก 30 วิจาก bg thread)
                    # ถ้ายังไม่ได้สแกนรอบแรก ค่อยใช้ตัวนับในหน่วยความจำไปก่อน
                    folder_counts = getattr(self, "folder_counts", {})
                    succ_count = folder_counts.get("login-success", ui_stats.success_count)
                    fail_count = folder_counts.get("login-failed", ui_stats.fail_count)
                    rand_count = folder_counts.get("random-fail", ui_stats.random_fail_count)

                    self.lbl_file_count.configure(text=f"📁 {qsize}")
                    self.lbl_succ_count.configure(text=f"✅ {succ_count}")
                    self.lbl_fail_count.configure(text=f"❌ {fail_count}")
                    self.lbl_random_fail.configure(text=f"🎲 {rand_count}")
                    
                    for dev, stat in ui_stats.device_statuses.items():
                        if dev in self.device_monitors:
                            self.device_monitors[dev].update_state(status=stat.get('status'))
                    
                    hero_raw_data = ui_stats.get_hero_combo_stats()
                    hero_data = hero_raw_data.copy()
                    
                    # Use cached backup-id file counts from background thread
                    backup_id_counts = getattr(self, "backup_id_counts", {})
                    for prefix, count in backup_id_counts.items():
                        hero_data[prefix] = count
                    
                    # Handle Login Failures (fixid x 8) - ใช้จำนวนไฟล์จริงใน login-failed/
                    login_fail_count = fail_count
                    if login_fail_count > 0:
                        hero_data["❌ เข้าไม่ได้ (Login Failed)"] = login_fail_count
                    
                    # Handle Gacha Failures (swap_shop/gachaout)
                    random_fail_count = rand_count
                    # Also collect raw "สุ่มไม่ได้" from hero_found_list
                    raw_random_fail = hero_data.pop("สุ่มไม่ได้", 0)
                    total_gacha_fail = max(random_fail_count, raw_random_fail)
                    if total_gacha_fail > 0:
                        hero_data["❌ สุ่มไม่ได้"] = total_gacha_fail
                    
                    # 2. Handle "Success but No Hero/Gear Found"
                    # Merge various 'Success' or 'Not Found' keys into one positive label
                    not_found_count = (hero_data.pop("ไม่เจอ", 0) + 
                                       hero_data.pop("Not Found", 0) + 
                                       hero_data.pop("Success", 0))
                    
                    # ถ้าสแกนโฟลเดอร์แล้ว ใช้จำนวนไฟล์จริงใน login-success/ เป็นตัวเลขหลัก
                    if "login-success" in folder_counts:
                        not_found_count = folder_counts["login-success"]
                    if not_found_count > 0:
                        # Hide "Success" label if swap_shop is enabled as per user request
                        if not config.get("swap_shop", 0):
                            hero_data["✅ สำเร็จ (Success)"] = not_found_count
                    
                    for hero, count in hero_data.items():
                        if hero not in self.hero_stats_labels:
                            # Color coding: Red for failures, Green for others
                            # Only Login Failed, Cannot Gacha, and Kaiby are real errors
                            is_error_row = "Login Failed" in hero or "สุ่มไม่ได้" in hero or "ไก่บี้" in hero
                            self.add_hero_row(hero, is_error_row)
                        
                        self.hero_stats_labels[hero].configure(text=str(count))
                    
                    # Explicitly hide rows based on conditions
                    to_hide = ["ไม่เจอ", "❌ ไม่เจอ"]
                    if config.get("swap_shop", 0): to_hide.append("✅ สำเร็จ (Success)")
                    for old_key in to_hide:
                        if old_key in self.hero_rows:
                            self.hero_rows[old_key].pack_forget()
                    
                    # Update Filter
                    self.filter_heroes()
                    
                    # Update Avg Time
                    if ui_stats.login_time_count > 0:
                        avg_sec = ui_stats.total_login_time / ui_stats.login_time_count
                        if avg_sec >= 60:
                            self.lbl_avg_time.configure(text=f"Avg: {avg_sec/60:.1f}m")
                        else:
                            self.lbl_avg_time.configure(text=f"Avg: {avg_sec:.0f}s")
            except Exception as e:
                print(f"[GUI] Update error: {e}")
            
            self.after(2000, self.update_realtime_stats)

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

        def open_config(self): MainConfigWindow(self)
        def open_heroes(self): HeroConfigWindow(self)

        def move_success_now(self):
            """ปุ่มย้ายไฟล์เดี๋ยวนี้ (login-success → input-id)"""
            try:
                load_config()
                move_cfg = config.get("move_success", {})
                src = move_cfg.get("source", "login-success")
                dst = move_cfg.get("dest", "input-id")
                moved, msg = move_success_to_input(src, dst)
                self.log("INFO", f"📤 {msg}")
            except Exception as e:
                self.log("ERROR", f"ย้ายไฟล์ไม่สำเร็จ: {e}")

        def check_scheduled_move(self):
            """เช็คทุก 30 วิ ถ้าถึงเวลาที่ตั้งไว้และเปิดใช้งาน -> ย้ายไฟล์ (วันละครั้ง)"""
            try:
                load_config()
                move_cfg = config.get("move_success", {})
                if move_cfg.get("enabled", 0) == 1:
                    target_time = str(move_cfg.get("time", "09:00")).strip()
                    now = datetime.now()
                    current_hm = now.strftime("%H:%M")
                    today = now.strftime("%Y-%m-%d")
                    if current_hm == target_time and self._last_move_date != today:
                        self._last_move_date = today
                        src = move_cfg.get("source", "login-success")
                        dst = move_cfg.get("dest", "input-id")
                        moved, msg = move_success_to_input(src, dst)
                        self.log("INFO", f"📤 [ตั้งเวลา {target_time}] {msg}")
            except Exception as e:
                print(f"[MOVE] scheduler error: {e}")
            self.after(30000, self.check_scheduled_move)

# =============================================================
# Global Config
# =============================================================
# Default config (will be overridden by config files)
config = {
    "first_loop": True,
    "thread_delay": 1,
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
    # Speed options (see touch_helper.py)
    "minitouch": 0,          # 1 = tap via minitouch socket instead of `adb shell input tap`
    "pos_cache": 1,          # 1 = remember where each button was found, re-check only that spot
    "pos_cache_margin": 12,  # px of slack around the remembered spot
    "scan_interval": 0.35,   # sec between full popup/error sweeps (0 = every frame, old behaviour)
    "loop_delay": 0.25,       # lower than the previous safe defaults to keep the bot responsive
    "auto_start": 1,
    "cloud_fast_start": 1,
    "cloud_start_delay_sec": 2.0,
    "auth_queue": 1,
    "auth_slots": 2,
    "auth_max_hold": 15,
    "auth_backoff_min": 2,
    "auth_backoff_max": 8,
    "device_identity_check": 1,
    "device_identity_block_on_duplicate": 1,
    "proxy_enabled": 0,
    "proxy_auto_fetch": 1,
    "proxy_type": "http",
    "proxy_host": "",
    "proxy_port": 0,
    "proxy_username": "",
    "proxy_password": "",
    "proxy_bypass": "localhost,127.0.0.1,10.0.2.2",
    "proxy_timeout_sec": 15,
    "proxy_fetch_urls": [
        "https://proxyscrape.com/free-proxy-list",
        "https://www.free-proxy-list.net/"
    ],
    "proxy_per_device": {}
}

adb_path = "adb"

# EasyOCR reader - loaded once globally
_ocr_reader = None
_ocr_lock = threading.Lock()  # Thread-safe OCR init

# Guards the one-time minitouch startup (shared by every bot thread).
_minitouch_init_lock = threading.Lock()

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


# จำกัดจำนวนจอที่ส่งไฟล์เข้าเครื่องพร้อมกัน - หลายจอยิงพร้อมกันคือต้นเหตุ "ไฟล์เข้าไม่ได้"
_inject_sem = None
_inject_sem_lock = threading.Lock()

# =============================================================
# Device fingerprint checks for cloned MuMu images
# =============================================================
_DEVICE_FINGERPRINT_LOCK = threading.Lock()
_DEVICE_FINGERPRINTS = {}


def _fp_value(value):
    if value is None:
        return ""
    value = str(value).strip().strip('"\'')
    return value.lower()


def _device_identity_snapshot(adb_cmd, device_id):
    """ดึง Android ID / serial / MAC จากเครื่องจริงแบบเร็ว < 10s เพื่อจับ MuMu clone"""
    vals = {
        "android_id": "",
        "serialno": "",
        "boot_serialno": "",
        "product_serial": "",
        "wifi_mac": "",
        "eth_mac": "",
    }
    checks = [
        (["settings", "get", "secure", "android_id"], "android_id"),
        (["getprop", "ro.serialno"], "serialno"),
        (["getprop", "ro.boot.serialno"], "boot_serialno"),
        (["getprop", "ro.product.serial"], "product_serial"),
        (["cat", "/sys/class/net/wlan0/address"], "wifi_mac"),
        (["cat", "/sys/class/net/eth0/address"], "eth_mac"),
    ]
    for cmd, key in checks:
        try:
            proc = subprocess.run([adb_cmd, "-s", device_id, "shell", *cmd],
                                  capture_output=True, text=True, timeout=8)
            out = _fp_value((proc.stdout or "") + (proc.stderr or ""))
            if out and not out.startswith("error:") and out != "null":
                vals[key] = out
        except Exception:
            pass
    return vals


def _device_identity_signature(snapshot):
    non_empty = []
    for key in ("android_id", "serialno", "boot_serialno", "product_serial", "wifi_mac", "eth_mac"):
        value = _fp_value(snapshot.get(key))
        if value:
            non_empty.append(f"{key}={value}")
    return "|".join(non_empty)


def _device_identity_map(sig):
    mapping = {}
    for part in (sig or "").split("|"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        if key:
            mapping[key] = value
    return mapping


def _device_identity_duplicate_check(adb_cmd, device_id):
    """คืน tuple (is_duplicate, reason, self_fingerprint) ถ้าเจอ device clone หรือ shared identity"""
    fp = _device_identity_snapshot(adb_cmd, device_id)
    sig = _device_identity_signature(fp)
    with _DEVICE_FINGERPRINT_LOCK:
        current = _DEVICE_FINGERPRINTS.get(device_id)
        if current is None or current.get("fp") != sig:
            _DEVICE_FINGERPRINTS[device_id] = {"fp": sig, "ts": time.time()}
        seen = {k: v for k, v in _DEVICE_FINGERPRINTS.items() if k != device_id and v.get("fp")}
    if not sig:
        return False, "empty-fingerprint", sig
    duplicates = []
    for other_id, other in seen.items():
        other_sig = other.get("fp") or ""
        if not other_sig:
            continue
        other_map = _device_identity_map(other_sig)
        # exact same signature = definitely cloned
        if other_sig == sig:
            duplicates.append(other_id)
            continue
        for key in ("android_id", "serialno", "boot_serialno", "product_serial", "wifi_mac", "eth_mac"):
            v1 = _fp_value(fp.get(key))
            v2 = _fp_value(other_map.get(key, ""))
            if v1 and v1 == v2:
                duplicates.append(other_id)
                break
    if duplicates:
        reason = ", ".join(sorted(set(duplicates)))
        return True, reason, sig
    return False, "ok", sig


def _fetch_proxy_candidates_from_url(url):
    """Fetch public proxy candidates from a free-proxy page and parse host:port pairs."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", "ignore")
    except Exception:
        return []

    if not html:
        return []
    import re
    matches = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\s*:\s*\d{2,5}\b|\b(?:\d{1,3}\.){3}\d{1,3}\s*\d{2,5}\b", html)
    seen = set()
    proxies = []
    for m in matches:
        text = m.strip().replace(" ", "")
        if ":" not in text:
            continue
        host, port = text.rsplit(":", 1)
        if not host or not port.isdigit():
            continue
        host = host.strip()
        port = int(port)
        if port <= 0 or port > 65535:
            continue
        if host.startswith("http://") or host.startswith("https://"):
            continue
        if host not in seen:
            seen.add(host)
            proxies.append((host, port))
    return proxies


def _auto_fetch_proxy_candidate():
    """Try proxyscrape first, then other public free-proxy sources, and return the first usable host:port."""
    urls = config.get("proxy_fetch_urls") or [
        "https://proxyscrape.com/free-proxy-list",
        "https://www.free-proxy-list.net/",
    ]
    if isinstance(urls, str):
        urls = [urls]
    for url in urls:
        for host, port in _fetch_proxy_candidates_from_url(url):
            if host and port:
                return {"host": host, "port": port, "type": "http"}
    return None


def _proxy_config_for_device(device_id, config_map=None):
    """Return proxy settings for this emulator if enabled.

    This is a best-effort, safe feature: if proxy disabled or host/port empty,
    returns None and the bot keeps its normal behavior.
    """
    if config_map is None:
        config_map = config.get("proxy_per_device", {}) or {}
    if isinstance(config_map, dict):
        cfg = config_map.get(device_id) or config_map.get(device_id.replace(":", "_"))
    else:
        cfg = {}
    enabled = bool((cfg or {}).get("enabled", bool(config.get("proxy_enabled", 0))))
    if not enabled:
        return None
    host = str((cfg or {}).get("host") or config.get("proxy_host") or "").strip()
    port = (cfg or {}).get("port", config.get("proxy_port", 0))
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 0
    if (not host or port <= 0) and bool(config.get("proxy_auto_fetch", 0)):
        auto_proxy = _auto_fetch_proxy_candidate()
        if auto_proxy:
            host = str(auto_proxy.get("host") or "").strip()
            port = int(auto_proxy.get("port") or 0)
    if not host or port <= 0:
        return None
    proxy_type = str((cfg or {}).get("type") or config.get("proxy_type") or "http").lower()
    username = str((cfg or {}).get("username") or config.get("proxy_username") or "").strip()
    password = str((cfg or {}).get("password") or config.get("proxy_password") or "").strip()
    return {
        "enabled": True,
        "host": host,
        "port": port,
        "type": proxy_type,
        "username": username,
        "password": password,
        "bypass": str(config.get("proxy_bypass", "localhost,127.0.0.1,10.0.2.2")).strip(),
    }


@contextlib.contextmanager
def _inject_gate():
    """คิวส่งไฟล์: ให้ส่งพร้อมกันได้ไม่เกิน config "inject_max_concurrent" (0 = ไม่จำกัด)"""
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

# =============================================================
# คิว auth ข้ามโปรเซส - ให้ "จังหวะยืนยันตัวตน" (refresh/check) เกิดทีละไม่กี่จอ
#
# ทำไมต้องมี: จอเดียวล็อกอินผ่าน 100% เสมอ แต่เปิดพร้อมกันหลายจอแล้วบางจอ
# วน fixid/refresh ไม่จบ = เซิร์ฟเวอร์ไม่รับ session ไม่ใช่ไฟล์ไม่เข้า
# (ไฟล์ผ่าน md5 แล้ว และเกมอ่านได้ถึงได้เด้งหน้าขอ auth ใหม่)
# ตัวคิวนี้กันเฉพาะ "ช่วงกด refresh" ซึ่งกินเวลาไม่กี่วินาทีต่อจอ
# งานอื่น (โหลดเกม กล่อง สุ่ม) ยังวิ่งพร้อมกันทุกจอเหมือนเดิม
#
# ใช้ไฟล์ล็อกใน temp เพราะแต่ละจอเป็นคนละ process (multiprocessing)
# =============================================================
_AUTH_DIR = os.path.join(tempfile.gettempdir(), "ranger-locks")


def _auth_cfg():
    """(เปิดใช้ไหม, จำนวนสล็อต, วินาทีที่ถือคิวได้ก่อนโดนยึด, backoff min/max)"""
    enabled = bool(config.get("auth_queue", 1))
    slots = max(1, min(3, int(config.get("auth_slots", 1) or 1)))
    hold = float(config.get("auth_max_hold", 45))
    backoff_min = max(0.0, float(config.get("auth_backoff_min", 30)))
    backoff_max = max(backoff_min, float(config.get("auth_backoff_max", 60)))
    return (enabled, slots, hold, backoff_min, backoff_max)


def _auth_slot_path(i):
    return os.path.join(_AUTH_DIR, f"_auth_slot{i}.lock")


def _auth_cleanup_stale():
    """ล้าง lock auth ที่ค้างเกิน auth_max_hold อัตโนมัติ เพื่อไม่ให้จอ fail ติดคิว"""
    try:
        os.makedirs(_AUTH_DIR, exist_ok=True)
    except OSError:
        return
    _, _, hold, *_ = _auth_cfg()
    stale_after = max(10.0, float(hold))
    try:
        for entry in os.scandir(_AUTH_DIR):
            if not entry.name.startswith("_auth_slot") or not entry.name.endswith(".lock"):
                continue
            try:
                if time.time() - entry.stat().st_mtime > stale_after:
                    os.remove(entry.path)
            except OSError:
                pass
    except OSError:
        pass


def _auth_backoff_delay(blocked_retries=0):
    """คำนวณ cooldown หลังโดนบล็อก auth queue; เพิ่มแบบค่อย ๆ จนถึง auth_backoff_max"""
    on, slots, hold, backoff_min, backoff_max = _auth_cfg()
    if not on or (backoff_min <= 0 and backoff_max <= 0):
        return 0.0
    retry = max(0, int(blocked_retries))
    if retry <= 0:
        return backoff_min
    if backoff_max <= backoff_min:
        return backoff_min
    delay = backoff_min * (2 ** max(0, retry - 1))
    return min(backoff_max, delay)


def _auth_acquire(device_id):
    """ขอคิว auth แบบไม่รอ - คืนหมายเลขสล็อตที่ได้ หรือ None ถ้าเต็ม

    สล็อตที่ถูกถือนานเกิน auth_max_hold (จอค้าง/โปรเซสตาย) จะถูกยึดมาใช้ต่อ
    """
    _auth_cleanup_stale()
    on, slots, hold, *_ = _auth_cfg()
    if not on:
        return -1                      # ปิดคิว = ผ่านตลอด (ใช้ -1 แทนสล็อตจริง)
    try:
        os.makedirs(_AUTH_DIR, exist_ok=True)
    except OSError:
        pass
    for i in range(slots):
        path = _auth_slot_path(i)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(device_id).encode())
            os.close(fd)
            return i
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(path) > hold:
                    os.remove(path)     # คนถือหายไป - ยึดมา
                    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.write(fd, str(device_id).encode())
                    os.close(fd)
                    return i
            except OSError:
                pass
        except OSError:
            pass
    return None


def _auth_touch(i):
    """ยังทำงานอยู่ - เลื่อนเวลาออกไปกันโดนยึดคิวกลางคัน"""
    if i is None or i < 0:
        return
    try:
        os.utime(_auth_slot_path(i), None)
    except OSError:
        pass


def _auth_release(i):
    if i is None or i < 0:
        return
    try:
        os.remove(_auth_slot_path(i))
    except OSError:
        pass

def queue_folder_names():
    """ชื่อโฟลเดอร์คิวตาม config ("queue_folders") - ใช้ร่วมกันทั้ง 3 สคริปต์
    ตั้งที่ ranger-gear_config.json ที่เดียว คุมทั้ง loginสะสม / หาตัว+เกียร์ / หาพร
    """
    folders = config.get("queue_folders") or ["backup", "input-id"]
    if isinstance(folders, str):
        folders = [folders]
    return [str(f) for f in folders]


_last_recycle_ts = 0.0


def recycle_failed_into_queue(source_dir="login-failed"):
    """คิวหมด -> ย้ายไฟล์ใน login-failed/ กลับเข้าโฟลเดอร์คิวตัวสุดท้าย (input-id) เพื่อวนใหม่

    - ปิดได้ด้วย config "recycle_failed": 0
    - กันหลาย process ย้ายพร้อมกันด้วย lock file แบบ O_EXCL
    - ไฟล์ชื่อซ้ำกับที่มีอยู่แล้วในคิว = ข้าม (ไม่ทับของเดิม)
    คืน True ถ้าย้ายได้อย่างน้อย 1 ไฟล์
    """
    global _last_recycle_ts
    if not config.get("recycle_failed", 1):
        return False
    # กันวนรัว ๆ: ไฟล์ที่ล็อกอินไม่ผ่านจริงจะเด้งกลับมา login-failed ทันที
    # ถ้าไม่หน่วงไว้จะกลายเป็นลูปย้ายไฟล์ไม่จบ
    cooldown = float(config.get("recycle_failed_cooldown", 600))
    if time.time() - _last_recycle_ts < cooldown:
        return False
    _last_recycle_ts = time.time()
    base = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(base, source_dir)
    if not os.path.isdir(src):
        return False
    qnames = queue_folder_names()
    dst = os.path.join(base, qnames[-1] if qnames else "input-id")

    lock_path = os.path.join(src, ".recycle.lock")
    try:
        if os.path.exists(lock_path) and time.time() - os.path.getmtime(lock_path) > 300:
            try: os.remove(lock_path)
            except OSError: pass
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except (FileExistsError, OSError):
        return False   # process อื่นกำลังวนอยู่

    moved = 0
    try:
        os.makedirs(dst, exist_ok=True)
        for root, _dirs, filenames in os.walk(src):
            for f in filenames:
                if not f.lower().endswith(".xml"):
                    continue
                s_path = os.path.join(root, f)
                d_path = os.path.join(dst, f)
                if os.path.exists(d_path):
                    continue
                try:
                    shutil.move(s_path, d_path)
                    moved += 1
                except Exception:
                    pass
    finally:
        try: os.remove(lock_path)
        except OSError: pass

    if moved:
        print(f"[QUEUE] คิวหมด - ดึง {moved} ไฟล์จาก {source_dir}/ กลับไปวนต่อที่ {os.path.basename(dst)}/")
    return moved > 0


_last_7day_recycle_ts = 0.0
SEVEN_DAY_PREFIX_RE = re.compile(r"^\[7=(\d+)\]\+")


def recycle_7day_into_queue(source_dir="7day-check"):
    """คิวหมด -> ดึงไฟล์ใน 7day-check/ ที่ยังรับของไม่ครบ (ไม่ใช่ [7=7]) กลับเข้าคิวเพื่อรับต่อ

    ใช้ตอนเปิด box + 7day: จบรอบแล้วไฟล์จะไปกองที่ 7day-check/ ชื่อ "[7=N]+เดิม"
    ไฟล์ที่ N < 7 = ยังรับของ 7 วันไม่ครบ เอากลับไปวนใหม่ได้เรื่อย ๆ จนครบ 7/7
    - ปิดได้ด้วย config "recycle_7day": 0 ; กันวนรัว ๆ ด้วย "recycle_7day_cooldown" (วินาที)
    - ตัดคำนำหน้า "[7=N]+" ออกก่อนย้าย ชื่อไฟล์จะได้ไม่ยาวขึ้นทุกรอบ
    คืน True ถ้าย้ายได้อย่างน้อย 1 ไฟล์
    """
    global _last_7day_recycle_ts
    if not config.get("recycle_7day", 1):
        return False
    if not config.get("7day", 0):
        return False                      # ไม่ได้เปิดโหมด 7 วัน = ไม่ต้องวนกลับ
    target = int(config.get("recycle_7day_target", 7))
    cooldown = float(config.get("recycle_7day_cooldown", 60))
    if time.time() - _last_7day_recycle_ts < cooldown:
        return False
    _last_7day_recycle_ts = time.time()

    base = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(base, source_dir)
    if not os.path.isdir(src):
        return False
    qnames = queue_folder_names()
    dst = os.path.join(base, qnames[-1] if qnames else "input-id")

    lock_path = os.path.join(src, ".recycle7day.lock")
    try:
        if os.path.exists(lock_path) and time.time() - os.path.getmtime(lock_path) > 300:
            try: os.remove(lock_path)
            except OSError: pass
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except (FileExistsError, OSError):
        return False   # process อื่นกำลังวนอยู่

    moved = skipped_done = 0
    try:
        os.makedirs(dst, exist_ok=True)
        for root, _dirs, filenames in os.walk(src):
            for f in filenames:
                if not f.lower().endswith(".xml"):
                    continue
                m = SEVEN_DAY_PREFIX_RE.match(f)
                if not m:
                    continue              # ไม่มี [7=N] = ไม่รู้สถานะ ปล่อยไว้
                if int(m.group(1)) >= target:
                    skipped_done += 1     # ครบ 7/7 แล้ว จบ ไม่ต้องวนอีก
                    continue
                s_path = os.path.join(root, f)
                clean = f[m.end():]        # ตัด "[7=N]+" ออก
                stem, ext = os.path.splitext(clean)
                d_path = os.path.join(dst, clean)
                seq = 2
                while os.path.exists(d_path):
                    d_path = os.path.join(dst, f"{stem}_{seq}{ext}")
                    seq += 1
                try:
                    shutil.move(s_path, d_path)
                    moved += 1
                except Exception:
                    pass
    finally:
        try: os.remove(lock_path)
        except OSError: pass

    if moved:
        print(f"[QUEUE] คิวหมด - ดึง {moved} ไฟล์ที่ยังไม่ครบ {target}/{target} จาก {source_dir}/ "
              f"กลับไปรับของต่อที่ {os.path.basename(dst)}/ (ครบแล้วข้าม {skipped_done} ไฟล์)")
    return moved > 0


def load_config():
    global config
    
    # 1. Load main config from ranger-gear_config.json
    #    ไฟล์นี้ใช้เป็น "ข้อมูลพื้นฐาน" เท่านั้น (ชื่อเกียร์/ตัวละคร/ocr_region/ranger_images)
    #    สวิตช์โหมด find_ranger/find_gear/find_all เป็นของบอท ranger-gear.py (สคริปต์แยก)
    #    login.py ต้องกำหนดโหมด "STRICTLY from configmain.json" จึงตัด key เหล่านี้ทิ้ง
    #    ไม่ให้รั่วมาบังคับให้ login.py วิ่งกระบวนการ FIND-RANGER/CHECK-GEAR เอง
    main_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ranger-gear_config.json")
    if os.path.exists(main_config_file):
        try:
            with open(main_config_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            for mode_key in ("find_ranger", "find_gear", "find_all"):
                loaded.pop(mode_key, None)
            config.update(loaded)
            print(f"[CONFIG] Base Loaded: {main_config_file}")
        except Exception as e:
            print(f"[WARN] Error loading base config: {e}")

    # 2. Load UI settings from configmain.json (Post-login tasks etc.)
    ui_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configmain.json")
    if os.path.exists(ui_config_file):
        try:
            with open(ui_config_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                config.update(loaded)
            print(f"[CONFIG] UI Settings Loaded: {ui_config_file}")
        except Exception as e:
            print(f"[WARN] Error loading UI config: {e}")


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


_MUMU_MANAGER_CACHE = None

def find_mumu_manager():
    """หา path ของ MuMuManager.exe (วิธีเดียวกับ pes) - ลองข้างๆ adb ก่อน แล้วค่อยไล่ตาม install ทั่วไป"""
    global _MUMU_MANAGER_CACHE
    if _MUMU_MANAGER_CACHE and os.path.exists(_MUMU_MANAGER_CACHE):
        return _MUMU_MANAGER_CACHE
    candidates = []
    # ถ้า adb ที่ใช้อยู่เป็นของ MuMu (…\shell\adb.exe) ลองหา MuMuManager ใน install เดียวกันก่อน
    try:
        if adb_path and adb_path.lower().endswith("adb.exe"):
            root = os.path.dirname(os.path.dirname(adb_path))
            candidates.append(os.path.join(root, "nx_main", "MuMuManager.exe"))
            candidates.append(os.path.join(root, "shell", "MuMuManager.exe"))
    except Exception:
        pass
    bases = [r"C:\Program Files\Netease", r"C:\Program Files (x86)\Netease",
             r"D:\Program Files\Netease", r"E:\Program Files\Netease",
             r"F:\Program Files\Netease", r"F:\MuMuPlayerGlobal-12.0"]
    subs = [r"MuMuPlayer\nx_main\MuMuManager.exe",
            r"MuMuPlayerGlobal-12.0\nx_main\MuMuManager.exe",
            r"MuMuPlayer-12.0\nx_main\MuMuManager.exe",
            r"MuMuPlayerGlobal-12.0\shell\MuMuManager.exe",
            r"MuMu Player 12\shell\MuMuManager.exe",
            r"MuMuPlayer\shell\MuMuManager.exe"]
    for b in bases:
        for s in subs:
            candidates.append(os.path.join(b, s))
    # จาก process MuMu ที่รันอยู่ (แม่นสุด - ไม่ต้องเดา path ติดตั้ง): ถาม wmic/PowerShell
    # ว่า MuMuPlayer.exe / MuMuManager.exe / MuMuVMMHeadless.exe อยู่ที่ไหน แล้วไล่หาจาก root นั้น
    try:
        kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}
        q = subprocess.run(["wmic", "process", "where", "name like 'MuMu%'", "get", "ExecutablePath"],
                           capture_output=True, text=True, timeout=10, **kwargs)
        roots = set()
        for line in (q.stdout or "").splitlines():
            line = line.strip()
            if line.lower().endswith(".exe") and os.path.exists(line):
                d = os.path.dirname(line)
                roots.add(d)
                roots.add(os.path.dirname(d))
        for r0 in sorted(roots, key=len):
            for sub_ in ("MuMuManager.exe", os.path.join("nx_main", "MuMuManager.exe"), os.path.join("shell", "MuMuManager.exe")):
                cand = os.path.join(r0, sub_)
                if os.path.exists(cand):
                    candidates.insert(0, cand)
    except Exception:
        pass
    for p in candidates:
        if os.path.exists(p):
            _MUMU_MANAGER_CACHE = p
            return p
    # ท้ายสุด: ไล่ walk หาใน bases
    for b in bases:
        if os.path.isdir(b):
            try:
                for r, _d, files in os.walk(b):
                    if "MuMuManager.exe" in files:
                        _MUMU_MANAGER_CACHE = os.path.join(r, "MuMuManager.exe")
                        return _MUMU_MANAGER_CACHE
            except Exception:
                pass
    return None


def get_mumu_instances():
    """ถาม MuMuManager (info -v all) ว่า instance ไหนเปิด Android อยู่จริง + adb port อะไร
    คืน list ของ (index, "ip:port") เฉพาะที่รันอยู่ / คืน None ถ้าใช้ MuMuManager ไม่ได้ (ให้ fallback วิธีเดิม)
    นี่คือแหล่งความจริง - พอร์ต ghost ที่ไม่ใช่ instance จริงจะไม่อยู่ในลิสต์นี้"""
    exe = find_mumu_manager()
    if not exe:
        return None
    try:
        kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}
        r = subprocess.run([exe, "info", "-v", "all"], capture_output=True,
                           text=True, timeout=30, **kwargs)
        raw = (r.stdout or "").strip()
        if not raw:
            return None
        data = json.loads(raw)
        # กรณีมี instance เดียว MuMuManager คืน object เดี่ยว ไม่ใช่ dict ของหลายตัว
        if "index" in data and "adb_port" in data:
            data = {str(data.get("index", "0")): data}
        out = []
        for key, inf in data.items():
            if not isinstance(inf, dict):
                continue
            if inf.get("is_android_started") and inf.get("adb_port"):
                ip = inf.get("adb_host_ip", "127.0.0.1")
                out.append((str(inf.get("index", key)), f"{ip}:{inf['adb_port']}"))
        return out
    except Exception as e:
        print(f"[MuMu] อ่านข้อมูล instance ไม่ได้: {e}")
        return None


# =========================================================
# ตรวจ/ตั้งค่าความละเอียดหน้าจออีมูเลเตอร์ (default 960x540 dpi 160)
# template ทุกรูปใน img/ ตัดมาจากจอ 960x540 ถ้าจอไม่ตรงบอทจะกดเพี้ยน
# ตั้งค่าได้ใน config: screen_check / screen_width / screen_height / screen_dpi
#                      screen_restart_mumu / screen_boot_wait / screen_auto_relaunch
# =========================================================


def _adb_out(dev, args, timeout=15):
    kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}
    try:
        r = subprocess.run([adb_path, "-s", dev] + args, capture_output=True,
                           text=True, timeout=timeout, **kwargs)
        return (r.stdout or "") + (r.stderr or "")
    except Exception:
        return ""


def get_device_screen(dev):
    """อ่านขนาดจอ+dpi ของเครื่องนี้ คืน dict หรือ None ถ้าอ่านไม่ได้

    {"size": (w, h), "dpi": n, "override": True/False}
    - size/dpi = ค่าที่ Android ใช้จริงตอนนี้ (มี Override ก็เอา Override)
    - override = มีใครไปสั่ง wm size/density ทับไว้ไหม
    """
    size_out = _adb_out(dev, ["shell", "wm", "size"])
    den_out = _adb_out(dev, ["shell", "wm", "density"])
    w = h = dpi = None
    override = False
    for line in size_out.splitlines():
        m = re.search(r"(Override|Physical) size:\s*(\d+)x(\d+)", line)
        if m:
            if m.group(1) == "Override":
                override = True
            if m.group(1) == "Override" or w is None:
                w, h = int(m.group(2)), int(m.group(3))
    for line in den_out.splitlines():
        m = re.search(r"(Override|Physical) density:\s*(\d+)", line)
        if m:
            if m.group(1) == "Override":
                override = True
            if m.group(1) == "Override" or dpi is None:
                dpi = int(m.group(2))
    if w and h and dpi:
        return {"size": (w, h), "dpi": dpi, "override": override}
    return None


def reset_wm_override(dev):
    """ล้าง wm size/density ที่ถูกสั่งทับไว้ ให้กลับไปใช้ค่าของ MuMu เอง

    บอทรุ่นก่อนเคยสั่ง wm size 960x540 ทับ ทั้งที่จอของ MuMu เป็นแนวตั้ง
    (540x960 = จอเดียวกันแค่คนละแนว) ทำให้จอเพี้ยน - เจอ override เมื่อไหร่ล้างทิ้ง
    """
    _adb_out(dev, ["shell", "wm", "size", "reset"], timeout=25)
    _adb_out(dev, ["shell", "wm", "density", "reset"], timeout=25)
    print(f"[SCREEN] {dev} ล้าง wm size/density override แล้ว (กลับไปใช้ค่าของ MuMu)")


def wait_devices_boot(devs, timeout=180):
    """รอให้เครื่องที่รีไปบูตเสร็จ (sys.boot_completed = 1) ภายในเวลาที่กำหนด"""
    deadline = time.time() + timeout
    left = list(devs)
    while left and time.time() < deadline:
        for d in list(left):
            try:
                subprocess.run([adb_path, "connect", d], capture_output=True, timeout=10,
                               **({'creationflags': 0x08000000} if os.name == 'nt' else {}))
            except Exception:
                pass
            if "1" in _adb_out(d, ["shell", "getprop", "sys.boot_completed"], timeout=10):
                print(f"[SCREEN] {d} บูตเสร็จแล้ว")
                left.remove(d)
        if left:
            time.sleep(5)
    if left:
        print(f"[SCREEN] รอบูตไม่ครบ ({', '.join(left)}) - ไปต่อเลย")
    return not left


# =========================================================
# ตั้งค่าจอ MuMu ผ่าน MuMuManager — พอร์ตมาจากตัว remote ที่ใช้งานได้จริง
# (คีย์/รูปแบบคำสั่งอ้างอิงจาก `MuMuManager setting -v 0 -aw` ของ MuMu 12 / nx_main 5.27)
# =========================================================

_MUMU_VFLAGS = ("-v", "--vmindex")
_mumu_vflag = {"ok": None}      # จำ flag ที่เครื่องนี้รับได้ ครั้งต่อไปจะได้ยิงถูกตั้งแต่ครั้งแรก

MUMU_KEEPALIVE_KEY = "app_keptlive"   # "App running" (ตั้งค่า > Others) - ไม่ใช่ app_keptalive


def _run_hidden(args, timeout=30):
    """รันคำสั่งแบบไม่โผล่หน้าต่าง คืน (stdout_text, returncode)"""
    kwargs = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}
    r = subprocess.run(args, capture_output=True, timeout=timeout, **kwargs)
    out = (r.stdout or b"").decode("utf-8", "ignore")
    if not out.strip():
        out = (r.stderr or b"").decode("utf-8", "ignore")
    return out, r.returncode


def _mumu_is_help(out):
    """MuMuManager พ่นหน้า help/error ออกมาแทนที่จะทำงานให้หรือเปล่า"""
    t = out or ""
    return ("OVERVIEW:" in t and "USAGE:" in t) or "error !!!" in t


def _mumu_vflag_order():
    ok = _mumu_vflag["ok"]
    if ok:
        return (ok,) + tuple(f for f in _MUMU_VFLAGS if f != ok)
    return _MUMU_VFLAGS


def _mumu_run_v(mgr, subcmd, vvalue, *rest, timeout=60):
    """เรียกคำสั่งที่ต้องระบุเลขจอ ลองทั้ง -v และ --vmindex

    MuMuManager บางเวอร์ชันไม่รู้จัก -v พอใส่ไปจะพ่นหน้า help ออกมาเฉย ๆ
    (คำสั่งไม่ทำงานแต่ rc=0 - เช็คแค่ returncode จะนึกว่าสำเร็จ)
    คืน (out, rc, flag ที่ใช้ได้ หรือ None ถ้าไม่มีอันไหนผ่าน)"""
    last_out, last_rc = "", -1
    for flag in _mumu_vflag_order():
        out, rc = _run_hidden([mgr, subcmd, flag, str(vvalue), *rest], timeout=timeout)
        if not _mumu_is_help(out):
            _mumu_vflag["ok"] = flag
            return out, rc, flag
        last_out, last_rc = out, rc
    return last_out, last_rc, None


def _mumu_json(out):
    """แกะ JSON ออกจากผลลัพธ์ MuMuManager (บางเครื่องมีข้อความนำหน้า/ต่อท้ายปนมา)"""
    if not out:
        return None
    text = out.strip().lstrip("﻿").strip("\x00")
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        return None
    start = min(starts)
    for end in sorted((text.rfind("}"), text.rfind("]")), reverse=True):
        if end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                continue
    return None


def _mumu_entry_ok(v):
    """จอนี้มีอยู่จริงไหม (จอที่ไม่มีจะตอบ errcode -200)"""
    return isinstance(v, dict) and not v.get("errcode") and not v.get("errmsg")


def mumu_list_instances():
    """รายชื่อ instance ทั้งหมด คืน list ของ {"index", "name", "running"}"""
    mgr = find_mumu_manager()
    if not mgr:
        return []
    data = None
    for flag in _mumu_vflag_order():
        try:
            out, _rc = _run_hidden([mgr, "info", flag, "all"],
                                   timeout=int(config.get("mumu_info_timeout", 25)))
        except Exception:
            continue
        data = _mumu_json(out)
        if data is not None:
            _mumu_vflag["ok"] = flag
            break
    if data is None:
        return []
    if isinstance(data, dict) and ("index" in data or "name" in data) and not any(k.isdigit() for k in data.keys()):
        items = {str(data.get("index", 0)): data}
    elif isinstance(data, dict):
        items = data
    else:
        return []
    out_list = []
    for k, v in items.items():
        if not _mumu_entry_ok(v):
            continue
        idx = v.get("index", k)
        try:
            idx = int(idx)
        except Exception:
            pass
        running = bool(v.get("is_process_started") or v.get("is_android_started")
                       or str(v.get("player_state", "")).lower() in ("start_finished", "starting", "running"))
        out_list.append({"index": idx, "name": v.get("name") or f"MuMu-{idx}", "running": running})
    out_list.sort(key=lambda x: (isinstance(x["index"], str), x["index"]))
    return out_list


def _mumu_apply_kv(mgr, targets, kv, timeout=180):
    """สั่ง setting ชุด key/value เดียวให้ทุกจอใน targets

    ลองรวมเป็นคำสั่งเดียวก่อน (มีหลายสิบจอ ถ้าเปิดโปรเซสทีละจอจะช้ามาก)
    เวอร์ชันเก่าไม่รับหลายจอค่อยไล่ทีละจอ คืน (done_indices, errors)"""
    done, errors = [], []
    idxs = [str(x["index"]) for x in targets]
    bulk_ok = False
    try:
        out, rc, flag = _mumu_run_v(mgr, "setting", ",".join(idxs), *kv, timeout=timeout)
        if flag is not None and rc == 0:
            done = [x["index"] for x in targets]
            bulk_ok = True
        elif flag is not None:
            errors.append(f"ตั้งค่ารวมไม่ผ่าน ({' '.join((out or '').split())[:70]})")
    except Exception as e:
        errors.append(f"ตั้งค่ารวมไม่สำเร็จ: {e}")

    if not bulk_ok:
        for inst in targets:
            idx = inst["index"]
            try:
                out, rc, flag = _mumu_run_v(mgr, "setting", idx, *kv, timeout=60)
                if flag is None:
                    errors.append(f"จอ {idx}: ไม่รับคำสั่ง setting ({' '.join((out or '').split())[:60]})")
                elif rc != 0:
                    errors.append(f"จอ {idx}: ตั้งค่าไม่สำเร็จ ({' '.join((out or '').split())[:60]})")
                else:
                    done.append(idx)
            except Exception as e:
                errors.append(f"จอ {idx}: {e}")
    return done, errors


def _mumu_get_setting(mgr, idx, key):
    """อ่านค่า setting ตัวเดียวกลับมา (ใช้ยืนยันว่าที่สั่งไปติดจริง)"""
    try:
        out, _rc, flag = _mumu_run_v(mgr, "setting", idx, "-k", key, timeout=30)
        if flag is None:
            return None
        data = _mumu_json(out)
        if isinstance(data, dict):
            if key in data:
                return str(data[key])
            if "value" in data:
                return str(data["value"])
            for v in data.values():
                if isinstance(v, dict) and key in v:
                    return str(v[key])
        txt = " ".join((out or "").split())
        return txt[:60] or None
    except Exception:
        return None


def _mumu_get_all_settings(mgr, idx):
    """ดัมป์ setting ทั้งหมดของจอนั้น (setting -v idx -aw) คืน dict ว่างถ้าอ่านไม่ได้"""
    try:
        out, _rc, flag = _mumu_run_v(mgr, "setting", idx, "-aw", timeout=30)
        if flag is None:
            return {}
        data = _mumu_json(out)
        if isinstance(data, dict):
            if str(idx) in data and isinstance(data[str(idx)], dict):
                data = data[str(idx)]
            return {str(k): str(v) for k, v in data.items() if not isinstance(v, (dict, list))}
    except Exception:
        pass
    return {}


def _as_bool(v):
    """เปิด/ปิด, 1/0, true/false -> True/False ; ว่าง -> None (= ไม่แตะของเดิม)"""
    t = str(v if v is not None else "").strip().lower()
    if t == "":
        return None
    if t in ("1", "true", "yes", "on", "เปิด"):
        return True
    if t in ("0", "false", "no", "off", "ปิด"):
        return False
    return None


def _as_int(v):
    """เลขจำนวนเต็ม หรือ None ถ้าว่าง/ไม่ใช่เลข (= ไม่แตะของเดิม)"""
    try:
        t = str(v if v is not None else "").strip()
        return int(float(t)) if t else None
    except Exception:
        return None


def _as_renderer(v):
    """DirectX -> dx, Vulkan -> vk (ค่าที่ MuMuManager รับจริง) ; อย่างอื่น/ว่าง -> None"""
    t = str(v or "").strip().lower()
    if t in ("dx", "directx", "d3d"):
        return "dx"
    if t in ("vk", "vulkan"):
        return "vk"
    return None


def mumu_display_config():
    """ค่าที่ตั้งไว้ใน config -> dict (None = ปล่อยว่าง ไม่แตะของเดิม)"""
    return {
        "width": _as_int(config.get("screen_width", "")),
        "height": _as_int(config.get("screen_height", "")),
        "dpi": _as_int(config.get("screen_dpi", "")),
        "fps": _as_int(config.get("mumu_fps", "")),
        "cpu": _as_int(config.get("mumu_cpu", "")),
        "ram": _as_int(config.get("mumu_ram", "")),
        "root": _as_bool(config.get("mumu_root", "")),
        "renderer": _as_renderer(config.get("mumu_renderer", "")),
        "keepalive": _as_bool(config.get("mumu_app_running", "")),
    }


def _mumu_wanted_kv(c):
    """แปลง config เป็น (kv ของคำสั่งหลัก, dict {key: ค่าที่ต้องการ} ไว้เทียบกับของเดิม)

    ชื่อคีย์ตามที่ MuMuManager ตอบใน `setting -v 0 -aw`:
      resolution_mode / resolution_{width,height,dpi}.custom
      max_frame_rate / performance_mode / performance_{cpu,mem}.custom
      root_permission / app_keptlive   (renderer_mode ยิงแยกทีหลัง)"""
    kv, want = [], {}
    if c["width"] and c["height"] and c["dpi"]:
        want.update({"resolution_mode": "custom",
                     "resolution_width.custom": str(c["width"]),
                     "resolution_height.custom": str(c["height"]),
                     "resolution_dpi.custom": str(c["dpi"])})
    if c["fps"]:
        want["max_frame_rate"] = str(c["fps"])
    if c["cpu"] or c["ram"]:
        want["performance_mode"] = "custom"
        if c["cpu"]:
            want["performance_cpu.custom"] = str(c["cpu"])
        if c["ram"]:
            want["performance_mem.custom"] = str(c["ram"])
    if c["root"] is not None:
        want["root_permission"] = "true" if c["root"] else "false"
    if c["keepalive"] is not None:
        want[MUMU_KEEPALIVE_KEY] = "true" if c["keepalive"] else "false"
    for k, v in want.items():
        kv += ["-k", k, "-val", v]
    return kv, want


def _same_setting(cur, want):
    """ค่าเดิมกับค่าที่ต้องการถือว่าเท่ากันไหม

    MuMuManager คืนตัวเลขเป็นทศนิยม ("960.000000", "2.000000") เทียบเป็น string ตรง ๆ
    จะไม่มีวันตรงเลย -> ตั้งค่า+รีอีมูซ้ำทุกครั้งที่เปิดโปรแกรม
    """
    a, b = str(cur).strip(), str(want).strip()
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return a.lower() == b.lower()


def mumu_set_display(targets=None, restart=True):
    """ตั้งค่าจอ MuMu ตาม config — ความละเอียด / FPS / CPU / RAM / root / renderer / App running

    เขียนเฉพาะจอที่ค่ายังไม่ตรง (อ่านเทียบด้วย setting -aw ก่อน) แล้วรีสตาร์ท
    เฉพาะจอที่เปิดอยู่ จอที่ปิดอยู่ค่าจะมีผลเองตอนเปิดครั้งถัดไป
    คืน {"changed": [...], "restarted": [...], "errors": [...]}"""
    res = {"changed": [], "restarted": [], "errors": []}
    mgr = find_mumu_manager()
    if not mgr:
        res["errors"].append("หา MuMuManager.exe ไม่เจอ")
        return res

    insts = mumu_list_instances()
    if not insts:
        res["errors"].append("อ่านรายชื่อจอจาก MuMuManager ไม่ได้")
        return res
    if targets:
        want_idx = {str(i) for i in targets}
        insts = [x for x in insts if str(x["index"]) in want_idx]
    if not insts:
        return res

    c = mumu_display_config()
    kv, want = _mumu_wanted_kv(c)
    renderer = c["renderer"]
    if not kv and not renderer:
        return res     # ปล่อยว่างหมด = ไม่ต้องทำอะไร

    # จอไหนค่ายังไม่ตรงบ้าง (อ่านค่าไม่ได้ = ถือว่าไม่ตรง จะได้ตั้งให้แน่ ๆ)
    todo, todo_renderer = [], []
    for inst in insts:
        cur = _mumu_get_all_settings(mgr, inst["index"])
        if want:
            if not cur or any(not _same_setting(cur.get(k, ""), v) for k, v in want.items()):
                todo.append(inst)
        if renderer:
            cur_r = cur.get("renderer_mode") if cur else _mumu_get_setting(mgr, inst["index"], "renderer_mode")
            if not cur_r or renderer not in str(cur_r).lower():
                todo_renderer.append(inst)

    if kv and todo:
        done, errs = _mumu_apply_kv(mgr, todo, kv)
        res["changed"] += done
        res["errors"] += errs
        if c["keepalive"] is not None and done:
            cur = _mumu_get_setting(mgr, todo[0]["index"], MUMU_KEEPALIVE_KEY)
            want_v = "true" if c["keepalive"] else "false"
            if cur and len(cur) <= 12 and cur.strip().lower() != want_v:
                res["errors"].append(f"App running: สั่ง '{want_v}' แต่จออ่านค่าได้เป็น '{cur}' "
                                     f"— key '{MUMU_KEEPALIVE_KEY}' อาจไม่ตรงกับ MuMu เวอร์ชันนี้")

    # renderer ยิงเป็นคำสั่งแยก - ถ้า key ไม่ตรงเวอร์ชันจะได้ไม่ทำค่าอื่นพังไปด้วย
    if renderer and todo_renderer:
        rdone, rerrs = _mumu_apply_kv(mgr, todo_renderer, ["-k", "renderer_mode", "-val", renderer])
        res["errors"] += ["renderer: " + e for e in rerrs]
        if rdone:
            res["changed"] += [i for i in rdone if i not in res["changed"]]
            cur = _mumu_get_setting(mgr, todo_renderer[0]["index"], "renderer_mode")
            if cur and renderer not in str(cur).lower() and len(cur) <= 12:
                res["errors"].append(f"renderer: สั่ง '{renderer}' แต่จออ่านค่าได้เป็น '{cur}' "
                                     f"— key/ค่าอาจไม่ตรงกับ MuMu เวอร์ชันนี้")

    if res["changed"]:
        parts = []
        if c["width"] and c["height"] and c["dpi"]:
            parts.append(f"{c['width']}x{c['height']} dpi {c['dpi']}")
        if c["fps"]:
            parts.append(f"{c['fps']} FPS")
        if c["cpu"]:
            parts.append(f"CPU {c['cpu']} core")
        if c["ram"]:
            parts.append(f"RAM {c['ram']} GB")
        if c["root"] is not None:
            parts.append("เปิด root" if c["root"] else "ปิด root")
        if c["keepalive"] is not None:
            parts.append("เปิด App running" if c["keepalive"] else "ปิด App running")
        if renderer:
            parts.append("Vulkan" if renderer == "vk" else "DirectX")
        print(f"[SCREEN] ตั้งค่า MuMu {len(set(res['changed']))} จอ: {', '.join(parts)}")

    # รีเฉพาะจอที่เปิดอยู่และเพิ่งถูกตั้งค่า
    if restart and res["changed"]:
        run_idxs = [x["index"] for x in insts if x.get("running") and x["index"] in res["changed"]]
        if run_idxs:
            csv = ",".join(str(i) for i in run_idxs)
            try:
                _out, rc, flag = _mumu_run_v(mgr, "control", csv, "restart", timeout=180)
                if flag is not None and rc == 0:
                    res["restarted"] = list(run_idxs)
                else:
                    for i in run_idxs:
                        _o, rc2, fl2 = _mumu_run_v(mgr, "control", i, "restart", timeout=60)
                        if fl2 is not None and rc2 == 0:
                            res["restarted"].append(i)
            except Exception as e:
                res["errors"].append(f"รีสตาร์ทไม่สำเร็จ: {e}")
            print(f"[SCREEN] รีสตาร์ท {len(res['restarted'])} จอให้ค่าใหม่มีผล")
    for e in res["errors"]:
        print(f"[SCREEN] ! {e}")
    return res


def apply_display_to_all_devices(devices=None):
    """Apply the current display profile to all connected MuMu devices in one batch.

    This is the safe equivalent of 'auto apply to all devices': it uses the existing MuMuManager
    settings API, then restarts only the devices that actually changed. It does not delete game data.
    """
    if devices is None:
        devices = get_connected_devices()
    if not devices:
        return {"changed": [], "restarted": [], "errors": ["No connected devices"]}
    try:
        result = mumu_set_display(targets=None, restart=bool(config.get("screen_restart_mumu", 1)))
        if result.get("changed"):
            print(f"[SCREEN] auto apply to all devices: {len(set(result['changed']))} device(s) updated")
        return result
    except Exception as e:
        print(f"[SCREEN] apply_display_to_all_devices failed: {e}")
        return {"changed": [], "restarted": [], "errors": [str(e)]}


def ensure_screen_resolution(devices):
    """ตั้งค่าจอ MuMu ให้ตรง config ก่อนเริ่มงาน คืน True ถ้ามีการรีจอ (= ควรรันตัวเองใหม่)

    ทำแบบเดียวกับตัว remote เป๊ะ ๆ คือ **ตั้งผ่าน MuMuManager อย่างเดียว**
    ไม่ไปสั่ง wm size/density ทับ เพราะ:
      - จอของ MuMu เป็นแนวตั้ง (adb รายงาน 540x960) ส่วนเกมหมุนเป็นแนวนอนเอง
        540x960 กับ 960x540 = จอเดียวกัน คนละแนวเท่านั้น
      - สั่ง wm size ทับ = จอเพี้ยนทั้งเครื่อง (บั๊กของรุ่นก่อน) เจอ override เมื่อไหร่ล้างทิ้ง
    """
    if not config.get("screen_check", 1):
        return False

    if bool(config.get("screen_auto_apply_all", 1)):
        apply_display_to_all_devices(devices)

    # 0) ล้างร่องรอย wm override ที่รุ่นก่อนเคยสั่งทับไว้
    if config.get("screen_clear_wm_override", 1):
        for dev in devices:
            cur = get_device_screen(dev)
            if cur and cur["override"]:
                reset_wm_override(dev)

    # 1) ตั้งค่าฝั่ง MuMuManager (ความละเอียด/FPS/CPU/RAM/root/renderer/App running)
    restarted = []
    try:
        r = mumu_set_display(restart=bool(config.get("screen_restart_mumu", 1)))
        restarted = r["restarted"]
    except Exception as e:
        print(f"[SCREEN] ตั้งค่า MuMu ไม่สำเร็จ: {e}")
        return False

    if not restarted:
        # ไม่ได้รีจอไหนเลย = ค่าตรงอยู่แล้ว หรือแก้เฉพาะจอที่ปิดอยู่ (มีผลตอนเปิดเอง)
        _report_screen_mismatch(devices)
        return False

    print(f"[SCREEN] รอจอที่รีสตาร์ท {len(restarted)} จอ บูตกลับมา...")
    time.sleep(8)
    connect_known_ports()
    wait_devices_boot(devices, timeout=int(config.get("screen_boot_wait", 180)))
    return True


def _report_screen_mismatch(devices):
    """เตือนเฉย ๆ ถ้าจอที่ Android เห็นยังไม่ใช่ขนาดที่ตั้งไว้ (ไม่แตะอะไรทั้งนั้น)

    เทียบแบบไม่สนแนวจอ: 540x960 ถือว่าตรงกับ 960x540
    """
    c = mumu_display_config()
    if not (c["width"] and c["height"] and c["dpi"]):
        return
    want = tuple(sorted((c["width"], c["height"])))
    for dev in devices:
        cur = get_device_screen(dev)
        if not cur:
            continue
        got = tuple(sorted(cur["size"]))
        if got != want or cur["dpi"] != c["dpi"]:
            print(f"[SCREEN] {dev} จอ {cur['size'][0]}x{cur['size'][1]} dpi {cur['dpi']} "
                  f"ยังไม่ตรงกับที่ตั้งไว้ ({c['width']}x{c['height']} dpi {c['dpi']}) "
                  f"- ลองปิด/เปิดจอนี้ใน MuMu ใหม่อีกที")


def relaunch_self(reason=""):
    """รันสคริปต์ตัวเองใหม่ (หลังตั้งจอ+รีอีมู) กันลูปด้วยตัวนับใน env"""
    if not config.get("screen_auto_relaunch", 1):
        print("[SCREEN] screen_auto_relaunch=0 - ไม่รันใหม่ ไปต่อเลย")
        return False
    rounds = int(os.environ.get("LGR_SCREEN_FIX_ROUND", "0"))
    if rounds >= int(config.get("screen_max_relaunch", 2)):
        print("[SCREEN] ตั้งจอ+รันใหม่ครบจำนวนรอบแล้ว ยังไม่ตรงอีก - ไปต่อเลย")
        return False
    os.environ["LGR_SCREEN_FIX_ROUND"] = str(rounds + 1)
    print(f"[SCREEN] {reason} -> รันโปรแกรมใหม่ (รอบที่ {rounds + 1})")
    sys.stdout.flush()
    try:
        script = os.path.abspath(__file__)
        # ห้ามใช้ os.execv บน Windows: มันเอา argv ไปต่อเป็นสตริงเดียวแล้ว
        # path ที่มีช่องว่าง ("C:\Program Files\Python311\python.exe") จะโดนตัดกลางคัน
        # -> "C:\Program: can't open file ..." (บั๊กที่เจอ) ใช้ Popen เปิดโปรเซสใหม่แทน
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen([sys.executable, script] + sys.argv[1:],
                         cwd=os.path.dirname(script), env=os.environ.copy(), **kwargs)
    except Exception as e:
        print(f"[SCREEN] รันใหม่ไม่สำเร็จ: {e} - ไปต่อด้วยโปรเซสเดิม")
        return False
    return True


def connect_known_ports():
    """เชื่อมต่อ emulator: kill adb server ก่อนเสมอแล้วค่อยเชื่อมใหม่
    ถาม MuMuManager ก่อน (แม่นสุด ไม่มี ghost) แล้วเช็คซ้ำจนเชื่อมครบทุกตัว
    ถ้าหา MuMuManager ไม่เจอค่อย fallback scan พอร์ต"""
    try:
        # Kill & start adb server - แยก try กันตัวใดตัวหนึ่ง timeout แล้ว
        # เด้งออกทั้งฟังก์ชัน (start-server บนเครื่องช้าใช้เวลาหลายวิ)
        try:
            subprocess.run([adb_path, "kill-server"], capture_output=True, timeout=10)
        except Exception:
            pass
        time.sleep(0.5)
        try:
            subprocess.run([adb_path, "start-server"], capture_output=True, timeout=20)
        except Exception:
            pass
        time.sleep(2)  # รอ daemon พร้อมจริงก่อนยิง connect ไม่งั้นตัวแรก ๆ เชื่อมหลุด

        # === ถาม MuMuManager ตรงๆ ว่ามี instance ไหนเปิดอยู่ ===
        instances = get_mumu_instances()
        if instances:
            targets = [serial for _, serial in instances]
            print(f"\n--- [ADB] MuMuManager รายงาน {len(instances)} instance ที่เปิดอยู่ ---")
            # เชื่อมแล้วเช็คซ้ำสูงสุด 6 ยก ห่างยกละ 3 วิ - instance ที่เพิ่งเปิด
            # Android ยังบูตไม่เสร็จ adb ในเครื่องยังไม่รับการเชื่อมต่อ ต้องรอ
            # และ print คำตอบจริงของ adb ให้เห็นว่าติดเพราะอะไร ไม่กลืนเงียบอีก
            for round_no in range(1, 7):
                online = set(get_connected_devices())
                missing = [s for s in targets if s not in online]
                if not missing:
                    break
                # ยิงพร้อมกัน - เดิมไล่ทีละตัว 19 เครื่องก็รอกันเป็นสิบวินาทีตั้งแต่ยกแรก
                def _connect_one(serial):
                    try:
                        r = subprocess.run([adb_path, "connect", serial],
                                           capture_output=True, timeout=5, text=True)
                        msg_lines = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
                        return serial, (msg_lines[-1] if msg_lines else "")
                    except Exception as e:
                        return serial, type(e).__name__
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(16, len(missing))) as _ex:
                    for serial, msg in _ex.map(_connect_one, missing):
                        print(f"[ADB] เชื่อม {serial} (ยกที่ {round_no}): {msg}")
                # เชื่อมครบแล้วไม่ต้องนอนรอ 3 วิ เปล่า ๆ
                if [s2 for s2 in targets if s2 not in set(get_connected_devices())]:
                    time.sleep(3)
                # ถาม MuMuManager ซ้ำ เผื่อมี instance ที่เพิ่งบูตเสร็จโผล่เพิ่ม
                inst_now = get_mumu_instances()
                if inst_now:
                    for _, s in inst_now:
                        if s not in targets:
                            targets.append(s)
            online = set(get_connected_devices())
            ok = [s for s in targets if s in online]
            missing = [s for s in targets if s not in online]
            if missing:
                print(f"[ADB] เชื่อมสำเร็จ {len(ok)}/{len(targets)} | ยังไม่ติด: {', '.join(missing)}")
            else:
                print(f"[ADB] เชื่อมครบ {len(ok)}/{len(targets)} ตัว")
            print("--- Scan Complete (MuMuManager) ---\n")
            return
        # === Fallback: scan พอร์ต (กรณีหา MuMuManager ไม่เจอ) ===

        # พอร์ตคี่ 5555-5755 (MuMu6/LDPlayer/Nox) + พอร์ต MuMu12: 16384+32n (50 จอ)
        ports = list(range(5555, 5756, 2)) + list(range(16384, 16384 + 32 * 50, 32))

        print(f"\n--- [ADB] Auto-scanning {len(ports)} ports (5555-5755 odd + 16384+32n) ---")
        
        connected = []
        
        def try_connect_port(port):
            """ยิงเชื่อมต่อทีละพอร์ต"""
            try:
                addr = f"127.0.0.1:{port}"
                # เดิม timeout 1 วิ - ตอน adb เพิ่ง restart + เปิดหลายเครื่อง ตอบไม่ทัน
                # เลย "หาเจอแค่ 3 เครื่อง" ทั้งที่เปิดอยู่ 17
                result = subprocess.run(
                    [adb_path, "connect", addr],
                    capture_output=True, timeout=4, text=True
                )
                out = result.stdout.lower()
                if ("connected" in out or "already connected" in out) and "cannot" not in out:
                    return addr
            except Exception:
                pass
            return None

        # ยิงเชื่อมต่อพร้อมกัน
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
        # emulator-XXXX (MuMu แบบ local) adb จะเห็นเองหลัง start-server แต่ใช้เวลาหลายวิ
        # รอจนจำนวนเครื่องนิ่ง (ไม่เพิ่มขึ้น 2 รอบติด) สูงสุด 20 วิ ก่อนไปต่อ
        seen_n, stable = -1, 0
        for _ in range(10):
            now_n = len(get_connected_devices())
            if now_n == seen_n:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
                seen_n = now_n
            time.sleep(2)
        print(f"[ADB] adb devices เห็นทั้งหมด {max(seen_n, 0)} เครื่องหลังรอให้นิ่ง")
                
        print("--- Scan Complete ---\n")
    except Exception as e:
        print(f"[ADB] Port scan error: {e}")


def get_connected_devices():
    """ดึงรายชื่อ devices ที่ online จาก adb devices (ไม่จำกัดจำนวน, กรองซ้ำ)"""
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
                
        # กรองซ้ำ: ถ้ามี emulator-5556 อยู่แล้ว ไม่ต้องเอา 127.0.0.1:5557 อีก
        emulator_adb_ports = set()  # เก็บพอร์ต ADB (คี่) ที่ emulator-xxx ครอง
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
            # ถ้าเป็น 127.0.0.1:port แล้วมี emulator- ครองอยู่แล้ว -> ข้าม
            if d.startswith("127.0.0.1:"):
                try:
                    port = int(d.split(":")[1])
                    if port in emulator_adb_ports:
                        continue  # ซ้ำกับ emulator-xxxx
                except ValueError:
                    pass
            seen.add(d)
            final_devices.append(d)

        # กรองด้วยรายชื่อจริงจาก MuMuManager (ถ้ามี): พอร์ตที่ไม่อยู่ในลิสต์ = ghost -> ตัดทิ้ง
        mumu_instances = get_mumu_instances()
        if mumu_instances:
            allowed = {s for _i, s in mumu_instances}
            filtered = []
            for d in final_devices:
                serial = d
                # แปลง emulator-XXXX -> 127.0.0.1:(XXXX+1) เพื่อเทียบกับลิสต์ MuMuManager
                if d.startswith("emulator-"):
                    try:
                        serial = f"127.0.0.1:{int(d.split('-')[1]) + 1}"
                    except (ValueError, IndexError):
                        pass
                if d in allowed or serial in allowed:
                    filtered.append(d)
                else:
                    print(f"[ADB] ข้าม {d} (ไม่อยู่ในรายชื่อ instance ของ MuMuManager - ghost)")
            final_devices = filtered

        # กรองซ้ำขั้นสอง: เช็ค boot_id ของแต่ละเครื่อง
        # (VM เดียวกันอาจโผล่ 2 ช่องทาง เช่น emulator-5562 กับ 127.0.0.1:5563 หรือพอร์ต TCP แฝด)
        # boot_id เหมือนกัน = เครื่องเดียวกัน -> เก็บไว้ตัวเดียว
        unique_devices = []
        seen_boot_ids = {}
        for d in final_devices:
            boot_id = None
            try:
                r = subprocess.run(
                    [adb_path, "-s", d, "shell", "cat", "/proc/sys/kernel/random/boot_id"],
                    capture_output=True, text=True, timeout=3
                )
                boot_id = (r.stdout or "").strip()
                # boot_id ต้องหน้าตาเป็น uuid ถ้า error/ว่าง ให้ถือว่าเช็คไม่ได้
                if len(boot_id) < 30 or " " in boot_id:
                    boot_id = None
            except Exception:
                pass
            if boot_id:
                if boot_id in seen_boot_ids:
                    print(f"[ADB] ข้าม {d} (เครื่องเดียวกับ {seen_boot_ids[boot_id]} - boot_id ซ้ำ)")
                    continue
                seen_boot_ids[boot_id] = d
            unique_devices.append(d)

        return unique_devices
    except Exception as e:
        print(f"[ERR] get_connected_devices: {e}")
        return []


class DeviceLogTee:
    """เก็บ log ลงไฟล์ .txt แยกราย device (logs/<device>.txt) + รวมทั้งหมดใน logs/all.txt

    ครอบ stdout/stderr เดิม: คอนโซล/GUI เห็นเหมือนเดิมทุกประการ แค่จดลงไฟล์เพิ่ม
    ระบุ device จาก thread ที่พิมพ์ (RangerGearBot มี device_id) เป็นหลัก
    ถ้าพิมพ์จาก thread อื่นจะดู prefix [127.0.0.1:xxxx] / [emulator-xxxx] แทน
    ไฟล์เกิน 20MB สลับไปเป็น .old.txt กันโตไม่จำกัด
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


_imgsearch_err_seen = set()

def ImgSearchADB(adb_img, find_img_path, threshold=0.95, method=cv2.TM_CCOEFF_NORMED):
    """หา template บนภาพจอ คืน list จุดกึ่งกลาง เรียงจากคะแนนมากไปน้อย

    ส่วนคัดจุดเขียนใหม่ด้วย numpy ล้วน - เดิมใช้ cv2.groupRectangles ซึ่งพังเงียบ
    บน OpenCV/numpy บางเวอร์ชัน (อาการ: คะแนน match ถึงเกณฑ์แต่คืนค่าว่างตลอด
    เพราะ except กลืน error) และถ้ามี error จริงจะ print ให้เห็นครั้งแรกเสมอ
    """
    try:
        find_img = cv2.imread(find_img_path, cv2.IMREAD_COLOR)
        if find_img is None or adb_img is None:
            return []
        h, w = find_img.shape[:2]
        result = cv2.matchTemplate(adb_img, find_img, method)
        points = []
        for _ in range(10):  # เก็บสูงสุด 10 จุดต่อรูป เกินพอสำหรับทุกจุดที่ใช้งาน
            idx = int(np.argmax(result))
            y, x = divmod(idx, result.shape[1])
            if float(result[y, x]) < threshold:
                break
            points.append((int(x) + w // 2, int(y) + h // 2))
            # ลบบริเวณรอบจุดที่เจอ (ขนาดเท่า template) กันนับจุดเดิมซ้ำ
            y0 = max(0, y - h // 2)
            x0 = max(0, x - w // 2)
            result[y0:y + h // 2 + 1, x0:x + w // 2 + 1] = -2.0
        return points
    except Exception as e:
        key = f"{find_img_path}:{type(e).__name__}"
        if key not in _imgsearch_err_seen:
            _imgsearch_err_seen.add(key)
            print(f"[ImgSearchADB] ERROR {find_img_path}: {type(e).__name__}: {e}")
        return []

class NetworkMonitor:
    def __init__(self):
        self.last_check = time.time()
        self.check_interval = 10
        
    def check_network(self, bot, adb_img):
        current_time = time.time()
        if current_time - self.last_check >= self.check_interval:
            # Note: bot here is the RangerGearBot instance
            fixnet_pos = ImgSearchADB(adb_img, 'img/fixnet.png')
            if fixnet_pos:
                print(f"[{bot.device_id}] พบปัญหาการเชื่อมต่อ (fixnet.png)")
                bot.tap(fixnet_pos[0][0], fixnet_pos[0][1])
                time.sleep(1)
                return True
            self.last_check = current_time
        return False

def check_critical_errors(bot, adb_img, context=""):
    """
    ตรวจสอบ fixid.png, fixunkown.png, apple.png
    """
    try:
        # ตรวจสอบ fixid.png
        fixid_pos = ImgSearchADB(adb_img, 'img/fixid.png')
        if fixid_pos:
            print(f"[{bot.device_id}] ⚠️ Found fixid.png in {context}!")
            bot.backup_to_backupxml()
            bot.clear_and_restart()
            time.sleep(6)
            return "fixid"
        
        # ตรวจสอบ fixunkown.png
        fixunkown_pos = ImgSearchADB(adb_img, 'img/fixunkown.png')
        if fixunkown_pos:
            print(f"[{bot.device_id}] ⚠️ Found fixunkown.png in {context}!")
            bot.backup_to_backupxml()
            bot.clear_and_restart()
            time.sleep(6)
            return "fixunkown"
        
        # ตรวจสอบ apple.png
        apple_pos = ImgSearchADB(adb_img, 'img/apple.png')
        if apple_pos:
            print(f"[{bot.device_id}] ⚠️ Found apple.png in {context}!")
            bot.backup_failed_login()
            bot.clear_and_restart()
            time.sleep(6)
            return "apple"
            
        # ตรวจสอบ fixnet1.png / fixnet.png (ปัญหาเน็ตหลุดเด้งป๊อปอัพ)
        fixnet_pos = ImgSearchADB(adb_img, 'img/fixnet1.png') or ImgSearchADB(adb_img, 'img/fixnet.png')
        if fixnet_pos:
            print(f"[{bot.device_id}] 📶 พบปัญหาการเชื่อมต่อ (fixnet1/fixnet) ใน {context} - กำลังกด OK...")
            bot.tap(fixnet_pos[0][0], fixnet_pos[0][1])
            time.sleep(1)
            # return None เพื่อให้ลูปทำงานปกติต่อไป (แค่กดป๊อปอัพทิ้ง)
        
        return None
    except Exception as e:
        print(f"[ERROR] check_critical_errors: {e}")
        return None

def load_hero_mapping():
    try:
        # Access global config
        hero_mapping = config.get('HERO_MAPPING', {})
        if not hero_mapping:
            return {
                'heroo1.png': 'Denji',
                'heroo2.png': 'DenjiU',
                'heroo3.png': 'Power',
                'heroo4.png': 'PowerU'
            }
        
        converted_mapping = {}
        for key, value in hero_mapping.items():
            if key == 'gachahero1': converted_mapping['heroo1.png'] = value
            elif key == 'gachahero2': converted_mapping['heroo2.png'] = value
            elif key == 'gachahero3': converted_mapping['heroo3.png'] = value
            elif key == 'gachahero4': converted_mapping['heroo4.png'] = value
            else: converted_mapping[key] = value # Preserve others
        
        return converted_mapping
    except:
        return {'heroo1.png': 'Denji', 'heroo2.png': 'DenjiU', 'heroo3.png': 'Power', 'heroo4.png': 'PowerU'}

def check_hero_images(bot, adb_img):
    try:
        hero_images = ['heroo1.png', 'heroo2.png', 'heroo3.png', 'heroo4.png']
        for hero_img in hero_images:
            hero_pos = ImgSearchADB(adb_img, f'img/ranger/{hero_img}')
            if hero_pos:
                print(f"[{bot.device_id}] พบ {hero_img}")
                return True
        return False
    except: return False


# =============================================================
# Hero_low - ตัวรอง เจอแล้วไม่จบงาน แค่จดชื่อไว้ใส่ในชื่อไฟล์
# =============================================================
def hero_low_keeps_rolling():
    """เจอตัวรองแล้วจะสุ่มต่อไหม

    "enabled" ไม่ใช่สวิตช์เปิด/ปิดการหา - หาเสมอถ้าตั้งค่ารูปไว้ มันบอกแค่ว่า
    เจอแล้วจะเอายังไงต่อ:
        1 = จดชื่อไว้แล้วสุ่มต่อ เผื่อได้ตัวหลักทีหลัง
        0 = เจอแล้วจบเลย ส่งไฟล์ออกทันที ไม่สุ่มต่อ
    ถ้าไม่อยากให้หาเลย ให้ลบรายการ low ออก หรือเคลียร์ช่องชื่อใน GUI
    """
    try:
        return bool((config.get("Hero_low", {}) or {}).get("enabled", 0))
    except Exception:
        return False


def load_hero_low():
    """อ่าน config Hero_low -> [(ชื่อรูป, ชื่อที่จะใส่ในไฟล์), ...]

    รูปแบบใน configmain.json:
        "Hero_low": {
            "search": 1,     <- หาตัวรองไหม (0 = ไม่หาเลย ไม่เสียเวลา match)
            "enabled": 1,    <- เจอแล้วทำอะไร (1 = สุ่มต่อ, 0 = จบเลย)
            "low1": {"img": "low1.bmp", "name": "kikoru+"},
            "low2": {"img": "low2.bmp", "name": "kikoruU+"}
        }
    ไม่มี "search" ถือว่าเปิด (config เก่าจะได้ทำงานเหมือนเดิม)
    ปิด search / ไม่มี key / ไม่ได้ตั้งรูปกับชื่อ = คืน list ว่าง = ไม่ต้องหาอะไรเพิ่ม
    """
    try:
        cfg = config.get("Hero_low", {}) or {}
        if not cfg.get("search", 1):
            return []
        entries = []
        # เรียงตามชื่อ key (low1, low2, ...) ให้ลำดับคงที่ทุกรอบ
        for key in sorted(k for k in cfg.keys() if k != "enabled"):
            item = cfg.get(key)
            if isinstance(item, dict):
                img, name = item.get("img"), item.get("name")
            elif isinstance(item, str):
                # เขียนสั้น ๆ แบบ "low1": "kikoru+" ก็ได้ ชื่อรูปเดาจาก key
                img, name = f"{key}.bmp", item
            else:
                continue
            if img and name:
                entries.append((img, name))
        return entries
    except Exception as e:
        print(f"[WARN] อ่าน Hero_low ไม่ได้: {e}")
        return []


def find_hero_low_images(bot, adb_img, already_found):
    """หา low ทุกตัวบนจอ คืนเฉพาะ 'ชื่อ' ที่ยังไม่เคยเจอมาก่อน (เรียงตามที่เจอ)

    หาไฟล์รูปจาก img/ranger-gacha/ ก่อน แล้วค่อย img/ เผื่อวางไว้คนละที่
    """
    found = []
    for img_name, display in load_hero_low():
        if display in already_found or display in found:
            continue
        # รองรับทั้ง .bmp และ .png: ถ้าชื่อใน config ไม่ตรงนามสกุลไฟล์จริง
        # ลองสลับนามสกุลให้เอง (เช่น config ใส่ low1.bmp แต่ไฟล์จริงเป็น low1.png)
        base, ext = os.path.splitext(img_name)
        alt_ext = ".png" if ext.lower() == ".bmp" else ".bmp"
        candidates = [img_name, base + alt_ext]
        path = None
        for folder in ("img/ranger-gacha", "img"):
            for cand in candidates:
                p = f"{folder}/{cand}"
                if os.path.exists(p):
                    path = p
                    break
            if path:
                break
        if path is None:
            print(f"[{bot.device_id}] [WARN] Hero_low: ไม่พบไฟล์รูป {img_name} "
                  f"(.bmp/.png ก็ได้ วางที่ img/ranger-gacha/ หรือ img/)")
            continue
        try:
            if ImgSearchADB(adb_img, path):
                print(f"[{bot.device_id}] 🔸 พบตัวรอง {os.path.basename(path)} -> {display} (จดไว้ ทำงานต่อ)")
                found.append(display)
        except Exception:
            pass
    return found

def search_gachaslot_image(bot):
    """Search for gachaslot.png with swiping logic from mainLG.py"""
    max_swipes = 5
    swipe_count = 0
    while swipe_count <= max_swipes:
        bot.capture_screen()
        adb_img = bot._screen_color
        gachaslot_pos = ImgSearchADB(adb_img, 'img/gachaslot.png')
        if gachaslot_pos:
            return gachaslot_pos[0]
        # ภาพสี 0.95 ไม่ติด ลดเป็น 0.8 (ภาพสีล้วน ไม่ใช้ขาวดำ)
        gachaslot_pos = ImgSearchADB(adb_img, 'img/gachaslot.png', threshold=0.8)
        if gachaslot_pos:
            return gachaslot_pos[0]
        if swipe_count < max_swipes:
            try:
                _t = cv2.imread('img/gachaslot.png', cv2.IMREAD_COLOR)
                score = float(np.max(cv2.matchTemplate(adb_img, _t, cv2.TM_CCOEFF_NORMED))) if _t is not None else 0.0
            except Exception:
                score = 0.0
            print(f"[{bot.device_id}] ไม่พบ gachaslot.png (match สี {score:.2f}) - เลื่อนหน้าจอครั้งที่ {swipe_count + 1}")
            bot.adb_shell("input swipe 824 240 808 109 5000")
            time.sleep(1)
            swipe_count += 1
        else: return None
    return None

def get_next_backup_id():
    filename_prefix = config.get('filename_prefix', 'conyfly')
    backup_dir = "backup-id"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        return 1, filename_prefix
        
    existing_files = glob.glob(os.path.join(backup_dir, f"{filename_prefix}-id*_LINE_COCOS_PREF_KEY_*.xml"))
    if not existing_files: return 1, filename_prefix
        
    ids = []
    for file in existing_files:
        try:
            id_part = file.split(f"{filename_prefix}-id")[1].split("_")[0]
            if id_part.isdigit(): ids.append(int(id_part))
        except: continue
    return (max(ids) + 1 if ids else 1), filename_prefix


def move_success_to_input(source_dir="login-success", dest_dir="input-id"):
    """ย้ายไฟล์ .xml ทั้งหมดจาก source_dir ไป dest_dir (กันชื่อซ้ำด้วย timestamp)
    คืนค่า (จำนวนไฟล์ที่ย้าย, ข้อความสรุป)
    """
    base = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(base, source_dir)
    dst = os.path.join(base, dest_dir)
    if not os.path.exists(src):
        return 0, f"ไม่พบโฟลเดอร์ {source_dir}"
    os.makedirs(dst, exist_ok=True)
    moved = 0
    for f in os.listdir(src):
        sp = os.path.join(src, f)
        if os.path.isfile(sp) and f.lower().endswith(".xml"):
            try:
                target = os.path.join(dst, f)
                # กันชื่อซ้ำ: ถ้ามีไฟล์ชื่อเดิมอยู่แล้ว เติม timestamp ต่อท้าย
                if os.path.exists(target):
                    name, ext = os.path.splitext(f)
                    target = os.path.join(dst, f"{name}_{int(time.time())}{ext}")
                shutil.move(sp, target)
                moved += 1
            except Exception as e:
                print(f"[MOVE] error moving {f}: {e}")
    return moved, f"ย้าย {moved} ไฟล์ จาก {source_dir} → {dest_dir}"

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
            return default
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def __init__(self, device_id, args=None):
        threading.Thread.__init__(self)
        self.device_id = device_id
        self.args = args # Store command line args
        self.daemon = True
        
        def update_gui_status(self, step, status="working"):
            ui_stats.update_device(self.device_id, {'step': step, 'status': status})
        self.update_gui_status = update_gui_status.__get__(self, RangerGearBot)
        
        # Determine which modes to run STRICTLY from configmain.json toggles
        self.do_ranger = config.get("find_ranger", 0)
        self.do_gear = (config.get("check-gear", 0) or 
                        config.get("ruby-gear200", 0) or 
                        config.get("random-gear", 0))
        
        print(f"[{self.device_id}] Mode - Ranger Scan: {self.do_ranger}, Gear Scan: {self.do_gear}")
        
        # Unique filename for this thread
        safe_dev = device_id.replace(":", "_")
        self.filename = os.path.join(tempfile.gettempdir(), f"screen-{safe_dev}.png")
        self.first_loop_done = not config.get("first_loop", True)
        self.last_activity_time = time.time()
        
        # Ranger Characters List (Always try to get from configmain first)
        if self.do_ranger:
            # Check characters in configmain first, then fallback to base config
            self.characters = config.get("characters", [])
            print(f"[{self.device_id}] Ranger mode -> searching {len(self.characters)} characters")
            
            # Auto-scan img/ranger/ folder - รองรับทั้ง .png และ .bmp
            self.ranger_image_mapping = config.get("ranger_images", {})
            ranger_folder = os.path.join("img", "ranger")
            self.ranger_files = []
            if os.path.exists(ranger_folder):
                for f in sorted(os.listdir(ranger_folder)):
                    if f.lower().endswith((".png", ".bmp")):
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
        self._screen_raw_png = None  # raw PNG for lazy color decode
        self._screen_raw_rgba = None  # raw RGBA data for ultra-fast decode
        self._screen_width = 0
        self._screen_height = 0
        self._template_cache = {}
        self._black_start_time = None
        
        # Post-Login Task Sequences
        self.box_seq = ['box1.png', 'box2.png', 'box3.png', 'box4.png', 'box5.png', 'box6.png', 'end_box.png']
        self.seven_day_seq = ['7day.png', '7day1.png', '7day2.png', 'fixok.png']
        self.shop_gacha_seq = ['gacha.png', 'gacha1.png', 'gacha3.png', 'fixok.png']
        self.swap_shop_seq = ['swap_shop.png', 'swap_shop1.png', 'swap_shop2.png', 'swap_shop3.png', 'swap_shop4.png', 'fixok.png']
        
        self._fixnetv3_count = 0
        # จำนวนเครื่องหมายถูก (check7day) ที่นับได้ตอนจบขั้นตอน 7 วันของ "ไฟล์ที่กำลังทำอยู่"
        # None = ยังไม่ได้ทำ 7 วันรอบนี้ -> ส่งไฟล์ออกทางเดิม (login-success)
        self._check7day_count = None
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

    def _proxy_config_for_device(self):
        """Best-effort proxy setup for this emulator. Returns None when disabled."""
        return _proxy_config_for_device(self.device_id)

    def _apply_proxy_for_device(self):
        """Set Android global HTTP proxy for this emulator if proxy config is present."""
        proxy = self._proxy_config_for_device()
        if not proxy:
            return False
        host = proxy["host"]
        port = int(proxy["port"])
        proxy_value = f"{host}:{port}"
        username = proxy.get("username")
        password = proxy.get("password")
        if username:
            proxy_value = f"{username}:{password}@{host}:{port}" if password else f"{username}@{host}:{port}"
        bypass = proxy.get("bypass", "localhost,127.0.0.1,10.0.2.2")
        print(f"[{self.device_id}] [PROXY] Trying {proxy['type']} proxy {host}:{port} for emulator")
        try:
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "settings", "put", "global", "http_proxy", proxy_value], timeout=12)
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "settings", "put", "global", "proxy_exclusion_list", bypass], timeout=12)
            return True
        except Exception as e:
            print(f"[{self.device_id}] [PROXY] proxy apply failed: {e}")
            return False

    def _clear_proxy_for_device(self):
        """Best-effort clean-up for proxy settings when disabled or restarting."""
        try:
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "settings", "put", "global", "http_proxy", ""], timeout=12)
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "settings", "put", "global", "proxy_exclusion_list", ""], timeout=12)
            return True
        except Exception:
            return False

    def _resolve_game_activity(self):
        """หา launcher activity จริงของเกมจากเครื่อง (ชื่อเปลี่ยนตามเวอร์ชันเกม) แล้ว cache ไว้
        - เดิม hardcode com.linecorp.common.activity.LineActivity ซึ่งเกมเวอร์ชันใหม่เปลี่ยนเป็น .LineRangersAdr แล้ว
        - ถามจากเครื่องตรงๆ จะได้ไม่พังอีกเวลาเกมเปลี่ยนชื่อ activity"""
        cached = getattr(self, "_game_activity", None)
        if cached:
            return cached
        try:
            r = self.adb_run([
                self.adb_cmd, "-s", self.device_id, "shell",
                "cmd", "package", "resolve-activity", "--brief", "com.linecorp.LGRGS"
            ], timeout=8)
            out = (r.stdout or b"").decode("utf-8", "ignore")
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("com.linecorp.LGRGS/"):
                    self._game_activity = line
                    print(f"[{self.device_id}] [APP] Launcher activity: {line}")
                    return line
        except Exception:
            pass
        # fallback: ชื่อ activity ของเกมเวอร์ชันปัจจุบัน
        self._game_activity = "com.linecorp.LGRGS/.LineRangersAdr"
        return self._game_activity

    def _check_device_identity(self):
        """ตรวจสอบว่าเครื่องนี้มี fingerprint ซ้ำกับอีกรายหรือไม่ (MuMu clone)"""
        if not config.get("device_identity_check", 1):
            return True
        try:
            is_dup, dup_with, sig = _device_identity_duplicate_check(self.adb_cmd, self.device_id)
            if not sig:
                print(f"[{self.device_id}] [DEVICE-FP] ไม่ได้อ่าน fingerprint จากเครื่องได้ - ข้ามตรวจเช็คชั่วคราว")
                return True
            if is_dup:
                print(f"[{self.device_id}] [DEVICE-FP] DUPLICATE! fingerprint ซ้ำกับ {dup_with} -> ไม่ควร login ต่อ")
                if config.get("device_identity_block_on_duplicate", 1):
                    self.device_identity_issue = True
                    return False
            else:
                print(f"[{self.device_id}] [DEVICE-FP] OK: android_id/serial/mac unique in this session")
            return True
        except Exception as e:
            print(f"[{self.device_id}] [DEVICE-FP] check failed: {e}")
            return True

    def open_app(self):
        self.last_activity_time = time.time()
        """เปิดแอป LINE Rangers ด้วยคำสั่ง am start / monkey (เร็วกว่าคลิก icon.png)"""
        # Reset stale network/proxy state before each file/job. This prevents a
        # reused emulator from keeping a previous IP/proxy binding across files.
        self._clear_proxy_for_device()
        sleep(0.5)
        # Best-effort per-device proxy activation before launching the game.
        # This keeps the feature enabled without breaking standard runs if proxy
        # config is blank or disabled.
        self._apply_proxy_for_device()
        if not self._check_device_identity():
            print(f"[{self.device_id}] [DEVICE-FP] หยุด login: device identity ซ้ำ/clone -> ข้ามไฟล์นี้ไป")
            self.app_missing = True
            return False
        # เช็คว่าเกมติดตั้งอยู่ไหม - retry 3 รอบก่อนตัดสิน
        # (ตอน VM เพิ่งบูต pm อาจตอบว่างเปล่าทั้งที่แอปติดตั้งอยู่ -> อย่าเพิ่งฟันธงจากรอบเดียว)
        try:
            app_found = False
            for pm_attempt in range(3):
                pm_res = self.adb_run([
                    self.adb_cmd, "-s", self.device_id, "shell",
                    "pm", "list", "packages", "com.linecorp.LGRGS"
                ], timeout=8)
                pm_out = (pm_res.stdout or b"").decode("utf-8", "ignore").strip()
                if "com.linecorp.LGRGS" in pm_out:
                    app_found = True
                    break
                print(f"[{self.device_id}] [WARN] pm ยังไม่เจอแอป (รอบ {pm_attempt+1}/3) - รอ 2 วิแล้วเช็คใหม่...")
                sleep(2)
            if not app_found:
                print(f"[{self.device_id}] ⛔ ไม่พบแอป com.linecorp.LGRGS บนเครื่องนี้! (เช็คแล้ว 3 รอบ - ยังไม่ได้ติดตั้ง/ชื่อ package ไม่ตรง/เครื่อง ghost) - หยุด retry")
                # ปักธงไว้: เครื่องนี้ไม่มีแอป → ห้ามย้ายไฟล์ไปโฟลเดอร์ไหนทั้งนั้น
                # และให้ลูปหลักหยุดหยิบไฟล์ใหม่ (ไฟล์ค้างไว้ในคิวเหมือนเดิม)
                self.app_missing = True
                return False
        except Exception as e:
            print(f"[{self.device_id}] [WARN] เช็ค package ไม่ได้: {e} - ลองเปิดต่อ")

        attempt = 0
        while attempt < 5:
            attempt += 1
            try:
                # สลับวิธีเปิด: am start กับ monkey
                if attempt % 2 == 1:
                    res = self.adb_run([
                        self.adb_cmd, "-s", self.device_id, "shell",
                        "am", "start", "-S", "-n",
                        self._resolve_game_activity()
                    ], timeout=10)
                else:
                    res = self.adb_run([
                        self.adb_cmd, "-s", self.device_id, "shell",
                        "monkey", "-p", "com.linecorp.LGRGS",
                        "-c", "android.intent.category.LAUNCHER", "1"
                    ], timeout=10)

                # เก็บ output ของคำสั่งเปิดแอปไว้ดูสาเหตุจริงตอนเปิดไม่ติด
                launch_out = ""
                try:
                    launch_out = ((res.stdout or b"").decode("utf-8", "ignore") +
                                  (res.stderr or b"").decode("utf-8", "ignore")).strip().replace("\n", " | ")
                except Exception:
                    pass

                sleep(3)

                # ตรวจว่าแอปยังรันอยู่ด้วย pidof
                try:
                    pid_result = subprocess.run(
                        [self.adb_cmd, "-s", self.device_id, "shell", "pidof", "com.linecorp.LGRGS"],
                        capture_output=True, text=True, timeout=5
                    )
                    pid = pid_result.stdout.strip()
                except Exception:
                    pid = ""

                if pid:
                    print(f"[{self.device_id}] ✓ App running (PID: {pid}) - attempt {attempt}")
                    return True
                else:
                    print(f"[{self.device_id}] ✗ App crashed/bounced! (attempt {attempt}) Retrying... | สาเหตุจาก launch: {launch_out[:250] or '(ไม่มี output)'}")
                    sleep(2)

            except Exception as e:
                print(f"[{self.device_id}] Error opening app (attempt {attempt}): {e}")
                sleep(2)

        print(f"[{self.device_id}] Failed to open app after 5 attempts!")
        return False

    def backup_game_data(self, hero_prefix=None):
        try:
            print(f"[{self.device_id}] กำลังสำรองข้อมูลเกม...")
            backup_dir = "backup-id"
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            
            original_name = getattr(self, "current_original_filename", "unknown.xml")
            if not original_name.endswith(".xml"): original_name += ".xml"
            
            # Use hero_prefix if provided, else use config/default
            prefix = hero_prefix or config.get('filename_prefix', 'conyfly')
            dest_filename = f"{prefix}-{original_name}"
            dest_path = os.path.join(backup_dir, dest_filename)
            source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
            temp_path = f"/data/local/tmp/backup_{self.device_id.replace(':','_')}.xml"
            
            self.adb_shell(f"su -c 'cp {source_path} {temp_path}'")
            self.adb_shell(f"su -c 'chmod 666 {temp_path}'")
            res = subprocess.run([self.adb_cmd, "-s", self.device_id, "pull", temp_path, dest_path], 
                                 capture_output=True, timeout=15)
            self.adb_shell(f"su -c 'rm {temp_path}'")
            if os.path.exists(dest_path):
                print(f"[{self.device_id}] สำรองข้อมูลสำเร็จ: {dest_path}")
                return True
            else:
                print(f"[{self.device_id}] สำรองข้อมูลล้มเหลว: {res.stderr.decode()}")
                return False
        except Exception as e:
            print(f"[{self.device_id}] เกิดข้อผิดพลาดในการสำรองข้อมูล: {e}")
            return False

    def backup_failed_game_data(self):
        try:
            print(f"[{self.device_id}] ตรวจไม่พบฮีโร่ - กำลังสำรองข้อมูลไปยัง not-found...")
            backup_dir = "not-found"
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            
            original_name = getattr(self, "current_original_filename", "unknown.xml")
            if not original_name.endswith(".xml"): original_name += ".xml"
            
            dest_filename = f"FAIL-{original_name}"
            dest_path = os.path.join(backup_dir, dest_filename)
            source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
            temp_path = f"/data/local/tmp/fail_backup_{self.device_id.replace(':','_')}.xml"
            
            self.adb_shell(f"su -c 'cp {source_path} {temp_path}'")
            self.adb_shell(f"su -c 'chmod 666 {temp_path}'")
            res = subprocess.run([self.adb_cmd, "-s", self.device_id, "pull", temp_path, dest_path], 
                                 capture_output=True, timeout=15)
            self.adb_shell(f"su -c 'rm {temp_path}'")
            if os.path.exists(dest_path):
                print(f"[{self.device_id}] สำรองข้อมูลล้มเหลวสำเร็จ: {dest_path}")
                return True
            return False
        except Exception as e:
            print(f"[{self.device_id}] Error backup failed data: {e}")
            return False

    def backup_failed_login(self):
        try:
            print(f"[{self.device_id}] ล็อกอินล้มเหลว/ติด apple - กำลังสำรองข้อมูลไปยัง login-fail...")
            filename_prefix = config.get('filename_prefix', 'conyfly')
            backup_dir = "login-fail"
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
                print(f"[{self.device_id}] ย้ายไฟล์ไป login-fail สำเร็จ: {dest_path}")
                return True
            return False
        except Exception as e:
            print(f"[{self.device_id}] Error backup failed login: {e}")
            return False

    def backup_to_backupxml(self):
        try:
            if not self.current_original_filename:
                return False
            current_dir = os.path.dirname(os.path.abspath(__file__))
            queue_dir = os.path.join(current_dir, queue_folder_names()[0])   # โฟลเดอร์คิวตัวแรกตาม config (input-id)
            print(f"[{self.device_id}] ย้ายไฟล์ {self.current_original_filename} กลับเข้าคิว ({os.path.basename(queue_dir)}/) เพื่อวนเข้าใหม่...")
            os.makedirs(queue_dir, exist_ok=True)
            source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
            dest_path = os.path.join(queue_dir, self.current_original_filename)
            self.adb_shell("su -c 'chmod 777 /data/data/com.linecorp.LGRGS/shared_prefs'")
            self.adb_shell(f"su -c 'chmod 777 {source_path}'")
            subprocess.run([self.adb_cmd, "-s", self.device_id, "pull", source_path, dest_path], 
                           capture_output=True, timeout=15)
            if os.path.exists(dest_path):
                print(f"[{self.device_id}] ย้ายไฟล์กลับเข้าคิวสำเร็จ: {dest_path}")
                return True
            return False
        except Exception as e:
            print(f"[{self.device_id}] Error backup back to backupxml: {e}")
            return False

    def auto_trade(self):
        try:
            trade_count_target = config.get('trade_count', 0)
            if trade_count_target <= 0: return "complete"
            print(f"[{self.device_id}] Starting Auto Trade ({trade_count_target} times)")
            current_trades = 0
            while current_trades < trade_count_target:
                self.capture_screen()
                img = self._screen_color
                critical = check_critical_errors(self, img, "auto_trade")
                if critical: return critical
                # First step: buy (272, 396)
                self.tap(272, 396)
                time.sleep(1)
                # Confirm step: buy_confirm (480, 420)
                self.tap(480, 420)
                time.sleep(1.2)
                # Success step: buy_ok (480, 420)
                self.tap(480, 420)
                current_trades += 1
                time.sleep(0.5)
                print(f"[{self.device_id}] Trade {current_trades}/{trade_count_target} complete")
            return "complete"
        except Exception as e:
            print(f"[{self.device_id}] Auto trade error: {e}")
            return "error"



    def _find_all_in_screen(self, template_path, similarity=0.85, min_dist=None):
        """หา 'ทุกตำแหน่ง' ของรูปบนจอล่าสุด (ไม่ใช่แค่จุดที่คะแนนสูงสุด) คืน list ของ (cx, cy, score)

        ใช้กับปุ่ม/การ์ดที่มีหลายใบเหมือนกันบนจอเดียว (เช่น การ์ดรับของ 7 วัน)
        เดิม _find_in_screen คืนแค่จุดเดียว = กดใบเดิมซ้ำแล้วซ้ำอีก ใบอื่นไม่เคยโดนกด
        """
        if self._screen is None:
            return []
        tmpl = self._get_template(template_path)
        if tmpl is None:
            return []
        th, tw = tmpl.shape[:2]
        if self._screen.shape[0] < th or self._screen.shape[1] < tw:
            return []
        res = cv2.matchTemplate(self._screen, tmpl, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(res >= similarity)
        cands = sorted(((float(res[y, x]), int(x), int(y)) for y, x in zip(ys, xs)), reverse=True)
        if min_dist is None:
            min_dist = max(8, min(tw, th) // 2)
        picked = []
        for sc, x, y in cands:
            cx, cy = x + tw // 2, y + th // 2
            if all(abs(cx - px) >= min_dist or abs(cy - py) >= min_dist for px, py, _ in picked):
                picked.append((cx, cy, sc))
        picked.sort(key=lambda t: (t[1] // max(1, th), t[0]))     # เรียงบนลงล่าง ซ้ายไปขวา
        return picked

    # รูปเครื่องหมายถูกบนการ์ดรับของ 7 วัน - นับจำนวนตอนรับของเสร็จ (ดู count_check7day)
    CHECK7DAY_IMG = "img/check7day.bmp"
    CHECK7DAY_DIR = "7day-check"

    def count_check7day(self, samples=3, gap=0.6):
        """นับว่าบนหน้ารับของ 7 วันมีเครื่องหมายถูก (check7day) ทั้งหมดกี่อัน - คืนจำนวน (int)

        เรียกตอน "รับของครบแล้วแต่ยังไม่ปิดหน้าต่าง" เท่านั้น ไอคอนนี้อยู่บนการ์ดในหน้านั้น
        จำนวนที่ได้จะถูกเอาไปใส่หน้าชื่อไฟล์ตอนส่งออกไป 7day-check/ (ดู _export_7day_check)

        จับจอหลายเฟรมแล้วเอาค่ามากที่สุด เพราะบางเฟรมโดนอนิเมชัน/ป๊อปอัพบังไอคอนบางอัน
        min_dist กว้างกว่าค่าปกติ (80% ของขนาดรูป) กันนับไอคอน "อันเดียวกัน" ซ้ำจาก
        match ที่เหลื่อมกันไม่กี่พิกเซล - การ์ดแต่ละใบห่างกันราว 50px อยู่แล้ว
        """
        tmpl = self._get_template(self.CHECK7DAY_IMG)
        if tmpl is None:
            print(f"[{self.device_id}] [7DAY] [WARN] ไม่มีรูป {os.path.basename(self.CHECK7DAY_IMG)} ใน img/ "
                  f"- นับ check7day ไม่ได้ (นับเป็น 0)")
            return 0
        th, tw = tmpl.shape[:2]
        try:
            sim = float(config.get("check7day_similarity", 0.85))
        except Exception:
            sim = 0.85
        min_dist = max(8, int(min(tw, th) * 0.8))
        best = 0
        for i in range(1, max(1, samples) + 1):
            try:
                self.capture_screen()
                hits = self._find_all_in_screen(self.CHECK7DAY_IMG, similarity=sim, min_dist=min_dist)
            except Exception as e:
                print(f"[{self.device_id}] [7DAY] นับ check7day รอบที่ {i} ไม่สำเร็จ: {e}")
                continue
            print(f"[{self.device_id}] [7DAY] นับ check7day รอบที่ {i}/{samples}: เจอ {len(hits)} อัน")
            best = max(best, len(hits))
            if i < samples:
                sleep(gap)
        print(f"[{self.device_id}] [7DAY] สรุป: เจอ check7day ทั้งหมด {best} อัน "
              f"(จะส่งไฟล์ออกไป {self.CHECK7DAY_DIR}/ ตอนจบงานทั้งหมด)")
        return best

    def _export_7day_check(self, file_path, count):
        """ย้ายไฟล์บัญชีไป 7day-check/ ตั้งชื่อ "[7=จำนวนที่เจอ check7day]+ชื่อเดิม" - คืน True ถ้าย้ายสำเร็จ

        ถูกเรียกจาก handle_success ตอนจบไฟล์ = งาน box (ถ้าเปิดไว้) ทำจบไปแล้วแน่นอน
        """
        if getattr(self, "app_missing", False):
            print(f"[{self.device_id}] ⛔ ไม่มีแอปบนเครื่องนี้ — ไม่ย้ายไฟล์ {os.path.basename(file_path)} ปล่อยไว้ที่เดิม")
            return True
        # adb หลุด/offline → ยังเชื่อผลไม่ได้ เก็บไฟล์คาคิวไว้ก่อน
        if not self.device_is_online():
            self._keep_file_in_queue(file_path, "adb offline/หลุดการเชื่อมต่อ")
            return True
        try:
            dst_dir = self.CHECK7DAY_DIR
            os.makedirs(dst_dir, exist_ok=True)
            base = os.path.basename(file_path)
            stem, ext = os.path.splitext(base)
            # [7=จำนวน] ไว้ "ข้างหน้า" ชื่อเดิม - เรียงในโฟลเดอร์แล้วบัญชีที่ได้เท่ากันอยู่ติดกัน
            dst = os.path.join(dst_dir, f"[7={count}]+{base}")
            # ชื่อชนกับไฟล์เดิมในโฟลเดอร์ (บัญชีชื่อซ้ำ/เอากลับมารันอีกรอบ) - เติมลำดับต่อท้าย
            seq = 2
            while os.path.exists(dst):
                dst = os.path.join(dst_dir, f"[7={count}]+{stem}_{seq}{ext}")
                seq += 1
            shutil.move(file_path, dst)
            print(f"[{self.device_id}] [7DAY-CHECK] เจอ check7day {count} อัน -> ส่งไฟล์ออกที่ {dst}")
            return True
        except Exception as e:
            print(f"[{self.device_id}] [7DAY-CHECK] ส่งไฟล์ออกไม่สำเร็จ: {e} - ใช้ทางเดิม (login-success)")
            return False

    def process_7day(self):
        """7-Day login: เข้าหน้ารับของ แล้ววนกด 7day1.png จนกว่าจะไม่เจอ

        ลำดับตามที่ต้องการ:
          1. กด 7day.png "ซ้ำ ๆ" จนไอคอนหายไปจากจอ (= เข้าหน้ารับของแล้ว)
             กันกดรอบเดียวไม่ติดเพราะจอขยับ/ป๊อปอัพบัง/แตะไม่โดน
          2. รอ checkpoint-7day (.png/.bmp) ให้แน่ใจว่าเข้าหน้ารับของแล้วจริง
             ค่อยเริ่มหา 7day1 (ถ้ายังไม่มีไฟล์รูปนี้ จะข้ามขั้นนี้พร้อมเตือน)
          3. วนหา 7day1.png ตลอดเวลา เจอก็กดทันที (ป๊อปอัพยืนยันที่เด้งตามมา
             คือ fixok.png ก็กดปิดให้ในลูปเดียวกัน ไม่งั้นมันบัง 7day1
             ปุ่มถัดไปแล้วลูปเดินต่อไม่ได้)
          4. จบเมื่อ "ไม่เจอ 7day1 ครบ 10 วิ" หรือ "กดครบ 10 ครั้ง"
             -> กด 7day2.png (ปุ่ม X) ปิดหน้าต่าง (ไม่ใช้ BACK/ESC)
          5. จบแล้วไปทำงานอื่นตาม config ต่อ
        """
        print(f"[{self.device_id}] [7DAY] เริ่มขั้นตอนรับของ 7 วัน")

        # 1) เข้าหน้ารับของ - กด 7day.png ซ้ำจนไอคอนหายจากจอ ไม่ใช่กดรอบเดียวแล้วไปต่อ
        #    (กดไม่ติดบ่อยมาก: จอยังขยับ/ป๊อปอัพบัง/แตะพลาด) จบเมื่อไอคอนหาย
        #    หรือครบเพดานกันค้าง แล้วปล่อยให้ขั้น 2 (รอ checkpoint) ตามเก็บต่อ
        ENTER_MAX_CLICKS = 8
        ENTER_DEADLINE = time.time() + 25
        enter_clicks = 0
        while time.time() < ENTER_DEADLINE and enter_clicks < ENTER_MAX_CLICKS:
            self.capture_screen()
            self.check_floating_popups()
            if not self.exists_in_cache("img/7day.png"):
                if enter_clicks:
                    print(f"[{self.device_id}] [7DAY] ไอคอน 7day หายจากจอแล้ว (กดไป {enter_clicks} ครั้ง) - เข้าหน้ารับของแล้ว")
                break
            enter_clicks += 1
            print(f"[{self.device_id}] [7DAY] กด 7day.png เข้าหน้ารับของ (ครั้งที่ {enter_clicks})")
            self.click("img/7day.png")
            sleep(2)
        else:
            print(f"[{self.device_id}] [7DAY] [WARN] กด 7day.png ไป {enter_clicks} ครั้งแล้วไอคอนยังอยู่ - ไปขั้นรอ checkpoint ต่อ")

        # 2) รอ checkpoint-7day ยืนยันว่าเข้าหน้ารับของแล้วจริง ค่อยไปหา 7day1
        #    (รับได้ทั้ง .png และ .bmp ถ้ายังไม่มีไฟล์รูปเลย ให้ข้ามไปเลย
        #    ไม่งั้นจะนั่งรอรูปที่ไม่มีทาง match จนครบ timeout ทุกไฟล์)
        cp_path = None
        for cp_name in ("img/checkpoint-7day.png", "img/checkpoint-7day.bmp"):
            if os.path.exists(cp_name):
                cp_path = cp_name
                break
        if cp_path is None:
            print(f"[{self.device_id}] [7DAY] [WARN] ยังไม่มีรูป checkpoint-7day (.png/.bmp) ใน img/ - ข้ามขั้นรอ checkpoint")
        else:
            print(f"[{self.device_id}] [7DAY] รอ {os.path.basename(cp_path)} ก่อนเริ่มหา 7day1 (สูงสุด 20 วิ)")
            cp_deadline = time.time() + 20
            cp_found = False
            while time.time() < cp_deadline:
                self.capture_screen()
                self.check_floating_popups()
                if self.exists_in_cache(cp_path):
                    print(f"[{self.device_id}] [7DAY] เจอ {os.path.basename(cp_path)} - เข้าหน้ารับของแล้ว เริ่มหา 7day1")
                    cp_found = True
                    break
                # เผื่อกด 7day.png ไม่ติด (จอขยับ/ป๊อปอัพบัง) - เจอไอคอนก็กดใหม่
                if self.exists_in_cache("img/7day.png"):
                    print(f"[{self.device_id}] [7DAY] ยังไม่เข้าหน้ารับของ - กด 7day.png อีกครั้ง")
                    self.click("img/7day.png")
                    sleep(1.5)
                    continue
                sleep(0.5)
            if not cp_found:
                print(f"[{self.device_id}] [7DAY] [WARN] ไม่เจอ checkpoint-7day ใน 20 วิ - ลองหา 7day1 ต่อเลย")

        # 3) วนกด 7day1 จนไม่มีอะไรให้กด (หรือครบเพดาน)
        IDLE_SECS = 10     # ไม่เจอ 7day1 ครบ 10 วิ = ถือว่ารับครบแล้ว
        MAX_TOTAL = 120    # เพดานเวลารวม กันลูปค้าง
        MAX_CLICKS = 30    # เพดานรวม (การ์ดหลายใบ x หลายรอบ) กันลูปค้าง
        clicks = 0
        started = time.time()
        last_hit = time.time()

        while True:
            if time.time() - started > MAX_TOTAL:
                print(f"[{self.device_id}] [7DAY] ครบเพดานเวลา {MAX_TOTAL} วิ - ออกจากขั้นตอน")
                break
            if clicks >= MAX_CLICKS:
                print(f"[{self.device_id}] [7DAY] กด 7day1 ครบ {MAX_CLICKS} ครั้ง - จบเลย ไปกด 7day2 ปิดหน้าต่าง")
                break

            self.capture_screen()
            self.check_floating_popups()

            # ห้ามใส่ 7day2.png ในลูปนี้ - มันคือปุ่ม X ปิดหน้าต่าง ถ้าเผลอกดตอน
            # 7day1 แวบหายไประหว่างอนิเมชัน หน้าต่างจะปิดก่อนรับของครบ
            hit = None
            # fixok (ป๊อปอัพยืนยัน) มาก่อนเสมอ - มันบังการ์ด
            if self.exists_in_cache("img/fixok.png", similarity=0.85):
                hit = "fixok.png"
            else:
                # การ์ด 7day1 มีหลายใบเหมือนกันบนจอ - กด "ทุกใบ" ซ้ายไปขวา ไม่ใช่กดใบที่
                # คะแนนสูงสุดซ้ำ ๆ (เดิมกดใบเดิม 10 ครั้ง ใบอื่นไม่เคยได้)
                cards = self._find_all_in_screen("img/7day1.png", similarity=0.85)
                if cards:
                    hit = "7day1.png"
                    round_no = clicks + 1
                    print(f"[{self.device_id}] [7DAY] เจอการ์ด 7day1 {len(cards)} ใบ - กดให้ครบทุกใบ")
                    for idx, (cx, cy, sc) in enumerate(cards, 1):
                        clicks += 1
                        print(f"[{self.device_id}] [7DAY] กดการ์ดใบที่ {idx}/{len(cards)} ที่ ({cx}, {cy}) score {sc:.2f} (รวมครั้งที่ {clicks})")
                        self.tap(cx, cy)
                        last_hit = time.time()
                        sleep(1.0)
                        # การ์ดที่รับได้จะเด้ง fixok - ปิดให้ก่อนไปใบถัดไป ไม่งั้นบังการ์ดที่เหลือ
                        self.capture_screen()
                        if self.exists_in_cache("img/fixok.png", similarity=0.85):
                            print(f"[{self.device_id}] [7DAY]   -> เด้ง fixok หลังใบที่ {idx} - กดปิด")
                            self.click("img/fixok.png", similarity=0.85)
                            sleep(1.0)
                        if clicks >= MAX_CLICKS:
                            break
                    sleep(0.5)
                    continue

            if hit:
                clicks += 1
                print(f"[{self.device_id}] [7DAY] เจอ {hit} - กด (ครั้งที่ {clicks})")
                self.click(f"img/{hit}", similarity=0.85)
                last_hit = time.time()
                sleep(1.2)

                # หลังกด 7day1 -> แวะหา fixok (ป๊อปอัพยืนยันหลังรับของ) 3 วิ
                # เจอก็กดปิดให้ ไม่งั้นมันบัง 7day1 ปุ่มถัดไป แล้วรอบหน้าจะกด
                # 7day1 ซ้ำที่เดิมโดยไม่ได้ของเพิ่ม
                if hit == "7day1.png":
                    ok_deadline = time.time() + 3
                    while time.time() < ok_deadline:
                        self.capture_screen()
                        ok_hit = None
                        for ok_img in ("fixok.png",):
                            if self.exists_in_cache(f"img/{ok_img}"):
                                ok_hit = ok_img
                                break
                        if ok_hit:
                            print(f"[{self.device_id}] [7DAY] หลังกด 7day1 เจอ {ok_hit} - กดปิด")
                            self.click(f"img/{ok_hit}")
                            last_hit = time.time()
                            sleep(1.0)
                            break
                        sleep(0.4)
                    else:
                        print(f"[{self.device_id}] [7DAY] หลังกด 7day1 ไม่เจอ fixok ใน 3 วิ - วนหา 7day1 ต่อ")
                continue

            idle = time.time() - last_hit
            if idle >= IDLE_SECS:
                print(f"[{self.device_id}] [7DAY] ไม่เจอ 7day1 ครบ {IDLE_SECS} วิ - รับครบแล้ว ไปกด 7day2 ปิดหน้าต่าง")
                break
            sleep(0.5)

        # 4) นับ check7day "ตอนนี้" - ต้องนับก่อนกดปิดหน้าต่าง ไอคอนอยู่บนการ์ดในหน้านี้
        self._check7day_count = self.count_check7day()

        # 5) กด 7day2.png (ปุ่ม X) ปิดหน้าต่าง - ไม่ใช้ BACK แล้ว
        #    หาได้สูงสุด 10 วิ กดได้สูงสุด 3 ครั้งจนหน้าต่างปิดจริง
        closed = False
        close_clicks = 0
        close_deadline = time.time() + 10
        while time.time() < close_deadline and close_clicks < 3:
            self.capture_screen()
            self.check_floating_popups()
            if self.exists_in_cache("img/7day2.png"):
                close_clicks += 1
                print(f"[{self.device_id}] [7DAY] เจอ 7day2 - กดปิดหน้าต่าง (ครั้งที่ {close_clicks})")
                self.click("img/7day2.png")
                sleep(1.2)
                continue
            # ไม่เจอปุ่ม X แล้ว = หน้าต่างปิดไปแล้ว (เช็คว่ากลับถึง Lobby ด้วย)
            if close_clicks > 0 or (self.exists_in_cache("img/7day.png")
                                    or self.exists_in_cache("img/box1.png")
                                    or self.exists_in_cache("img/gacha.png")):
                closed = True
                break
            sleep(0.5)
        if closed:
            print(f"[{self.device_id}] [7DAY] ปิดหน้าต่างเรียบร้อย")
        else:
            print(f"[{self.device_id}] [7DAY] [WARN] ไม่เจอ 7day2 ใน 10 วิ - ไปทำงานต่อเลย")

        print(f"[{self.device_id}] [7DAY] จบขั้นตอน 7 วัน (กดไปทั้งหมด {clicks} ครั้ง) - ไปทำงานตาม config ต่อ")
        return "complete"

    def process_shopgacha(self):
        device = self  # map 'device' to 'self' for snippet compatibility
        shop_gacha_enabled = config.get('shopgacha', 0)
        if not shop_gacha_enabled: return "complete"
        network_monitor = NetworkMonitor()
        print(f"[{device.device_id}] เริ่มกระบวนการ shop gacha")

        # ถ้าเปิด swap_shop คู่กัน ห้าม clear app ตอน shopgacha จบ - ต้องไปทำ swap_shop ต่อ
        swap_shop_enabled = bool(config.get("swap_shop") or config.get("swap_shopevent") or config.get("auto_trade", {}).get("enabled"))

        # เกณฑ์ความเหมือนของ "ปุ่ม" ในร้าน - 0.95 เข้มไปจนกดไม่ติด
        # ใช้เฉพาะปุ่มที่ต้องกด ไม่แตะ shopgachastop/shopgachastop1 ซึ่งเป็นเงื่อนไข
        # จบงาน ถ้าลดด้วยแล้วเจอผิดจะพาไป SOLD OUT / random-Fail ทั้งที่ยังสุ่มได้
        # ประกาศไว้บนสุดเพราะ helper ข้างล่างใช้ และถูกเรียกตั้งแต่ขั้นหาทางเข้าร้าน
        BTN_TH = 0.8

        # เพดานรวมของการเคลียร์ป๊อปอัพเพชรตลอดทั้ง process_shopgacha ครั้งนี้
        # ปกติเด้งไม่กี่ครั้ง ถ้าถึงเพดานแปลว่ากดแล้วมันไม่ยอมปิด - เลิกสนใจมัน
        # แล้วปล่อยให้ตัวนับ/timeout ปกติทำงานแทน ไม่งั้นลูปจะเอาแต่กดป๊อปอัพ
        # จนไม่ได้นับ miss เลยสักครั้ง
        gems_state = {"clears": 0, "max": 15}

        def clear_fixgems():
            """ป๊อปอัพเพชรลอย ๆ - เจอที่ไหนก็เคลียร์ก่อน คืน True ถ้ากดไปจริง

            ใช้จอที่จับไว้ล่าสุด (ไม่จับใหม่เอง) ผู้เรียกต้อง capture_screen() มาก่อน
            ถ้ากดแล้วจะจับจอใหม่ให้ ผู้เรียกจึงอ่าน device._screen_color ต่อได้เลย
            """
            if gems_state["clears"] >= gems_state["max"]:
                return False
            img = device._screen_color
            if img is None:
                return False
            # จับป๊อปอัพด้วย 2 รูป: fixgems.png (คำว่า Gems.) หรือ fixnewgacha.png
            # (ไอคอนเพชรม่วงบนป๊อปอัพเดียวกัน) - fixgems.png เป็น crop ที่บนจอจริง
            # match ไม่ติด ส่วน fixnewgacha.png คือตัวที่ handler ใน swap_shop ใช้
            # จับป๊อปอัพนี้ได้จริงที่ default 0.95 มาตลอด
            hit = ImgSearchADB(img, 'img/fixgems.png', threshold=BTN_TH)
            if not hit:
                hit = ImgSearchADB(img, 'img/fixnewgacha.png')
            if not hit:
                return False
            g = ImgSearchADB(img, 'img/fixgems1.png', threshold=BTN_TH)
            if g and len(g) > 0:
                tap_x, tap_y = g[0][0], g[0][1]
            else:
                # หาปุ่ม OK จากรูปไม่เจอ - ใช้พิกัดปุ่ม OK ของป๊อปอัพนี้
                # พิกัดเดียวกับ handler ใน swap_shop (tap 476,394) ที่ใช้งานจริงมาแล้ว
                tap_x, tap_y = 476, 394
            gems_state["clears"] += 1
            print(f"[{device.device_id}] เจอป๊อปอัพเพชร (fixgems) - กด OK ที่ ({tap_x},{tap_y}) (ครั้งที่ {gems_state['clears']})")
            device.tap(tap_x, tap_y)
            time.sleep(1)
            device.capture_screen()
            if gems_state["clears"] >= gems_state["max"]:
                print(f"[{device.device_id}] [WARN] เคลียร์ fixgems ครบ {gems_state['max']} ครั้งแล้วยังไม่หาย - เลิกสนใจ")
            return True

        def find_btn(name, th=BTN_TH):
            """หาปุ่ม 2 ทางแบบเดียวกับตอนหาทางเข้าร้าน (gacha.png):
            ภาพสี (ImgSearchADB) ก่อน ไม่ติดค่อยลองภาพขาวดำ (_find_in_screen)
            บางเครื่องสีจอเพี้ยนจนภาพสีไม่ผ่านเกณฑ์ แต่ขาวดำยังหาเจอ
            ใช้จอที่ capture ไว้ล่าสุด คืน (x, y) หรือ None"""
            pos = ImgSearchADB(device._screen_color, f'img/{name}', threshold=th)
            if pos and len(pos) > 0:
                return pos[0]
            return device._find_in_screen(f'img/{name}', th)

        def stop_hit(name):
            """เงื่อนไขจบ (shopgachastop / shopgachastop1) - หาลอย ๆ ทั้งจอแบบ 2 ทาง
            ที่ 0.95 เข้มเท่าเดิม: ภาพสีก่อน ไม่ติดค่อยเช็คภาพขาวดำ
            กันเคสจอสีเพี้ยนแล้วมองไม่เห็นจอจบ ทำให้วนต่อทั้งที่ควรรัว BACK ออก"""
            pos = ImgSearchADB(device._screen_color, f'img/{name}')
            if pos and len(pos) > 0:
                return True
            return device.exists_in_cache(f'img/{name}')

        def finish_shopgacha():
            if swap_shop_enabled:
                # เปิด swap_shop คู่กัน - รัว BACK (KEYCODE_BACK) จนเจอ cancel เหมือน event แล้วไป swap_shop
                print(f"[{device.device_id}] เปิด swap_shop คู่กัน - รัว BACK จนเจอ cancel แล้วไป swap_shop")
                back_press_count = 0
                device.capture_screen()
                while True:
                    # เช็ค fixgems ก่อนกด BACK ทุกรอบ - เจอเมื่อไหร่ "หยุดกด BACK"
                    # ไปเคลียร์ป๊อปอัพก่อน ไม่งั้น BACK จะไปโดนป๊อปอัพแทนที่จะถอยออก
                    # (clear_fixgems มีเพดานรวมของตัวเองอยู่แล้ว จึงวนไม่จบไม่ได้)
                    if clear_fixgems():
                        continue          # เคลียร์แล้ววนใหม่ รอบนี้ไม่กด BACK

                    if device.exists_in_cache("img/cancel.png"):
                        print(f"[{device.device_id}] เจอ cancel - กด cancel แล้วหยุด")
                        device.click("img/cancel.png")
                        time.sleep(1)
                        break

                    if back_press_count >= 30:  # ป้องกันลูปค้าง (สูงสุด 30 ครั้ง)
                        print(f"[{device.device_id}] รัว BACK ครบ 30 ครั้ง ไม่เจอ cancel - ไปต่อ swap_shop")
                        break

                    # กด Back ทีเดียว 3 รอบ
                    device.adb_shell("input keyevent KEYCODE_BACK")
                    device.adb_shell("input keyevent KEYCODE_BACK")
                    device.adb_shell("input keyevent KEYCODE_BACK")
                    back_press_count += 3
                    print(f"[{device.device_id}] [SHOPGACHA] Triple Back spam! (Total: {back_press_count})")

                    time.sleep(0.3)  # ให้เวลา UI อัปเดตเล็กน้อย
                    device.capture_screen()
                return "complete"
            device.clear_and_restart()
            time.sleep(6)
            return "complete"

        # ขั้นตอนที่ 1: เข้าหน้าร้านให้ได้ก่อน
        # ปกติเข้าทาง event.png (ป๊อปอัพอีเวนต์) แต่ถ้าตอน login โดนปิดไปแล้ว
        # ป๊อปอัพจะไม่อยู่ ต้องกดไอคอน gacha.png ที่ Lobby เข้าแทน
        # ถ้าไม่กดอะไรเลย ลูปข้างล่างจะหา shopgacha1.png ในร้านที่ยังไม่ได้เปิด = ไม่มีทางเจอ
        def wait_gacha_then_gems():
            """หลังกด shopgacha1: รอจอสุ่ม -> เช็คป๊อปอัพเพชร -> ค่อยไปหา shopgacha2

            ลำดับตามที่ต้องการ:
              1. หา waitgacha.png กับ waitgacha1.png พร้อมกัน เจอตัวไหนก่อนก็ได้
                 (รอได้เรื่อย ๆ เหมือนขั้นรอ shopgacha2 - ถ้าค้างจริงมี 500s คุมอยู่)
              2. เจอแล้วหา fixgems.png ภายใน 8 วิ
                 - เจอ  -> กด fixgems1.png แล้วไปต่อ
                 - ไม่เจอ -> ข้ามไป shopgacha2 เลย
            คืน None = ไปต่อตามปกติ, คืน string = ผลลัพธ์ที่ต้องส่งกลับออกไปเลย
            """
            waits = ('waitgacha.png', 'waitgacha1.png')
            print(f"[{device.device_id}] รอจอสุ่ม (waitgacha / waitgacha1)...")
            rounds = 0
            seen = None
            wait_deadline = time.time() + 600
            while seen is None:
                if time.time() > wait_deadline:
                    # เพดานแข็งกันค้างถาวร - ปกติไม่ควรถึง เพราะจอสุ่มโผล่ในไม่กี่วิ
                    print(f"[{device.device_id}] รอจอสุ่มเกิน 600 วิ - เลิกรอ ไป swap_shop")
                    return finish_shopgacha()

                device.capture_screen()
                if clear_fixgems():          # ป๊อปอัพเพชรลอย ๆ เจอก็เคลียร์
                    continue
                img = device._screen_color

                # เน็ตหลุด / fixid / fixunkown / apple ต้องจัดการเหมือนลูปหลัก
                # ไม่งั้นถ้าโผล่มาบังจอ จะรอ waitgacha ที่ไม่มีวันมาจนครบ 500s
                # แล้วบัญชีถูกส่งไป login-failed แทนที่จะ backup + restart ให้ถูกทาง
                if network_monitor.check_network(device, img):
                    continue
                crit = check_critical_errors(device, img, "process_shopgacha:wait_gacha")
                if crit:
                    print(f"[{device.device_id}] เจอ {crit} ระหว่างรอจอสุ่ม - ออกตามทางของมัน")
                    return crit

                for w in waits:
                    if find_btn(w):
                        seen = w
                        break
                if seen:
                    break
                # จอจบ/ขายหมด อาจโผล่ระหว่างรอ - ต้องออกให้ถูกทาง ไม่ใช่รอค้าง
                if stop_hit('shopgachastop.png'):
                    if swap_shop_enabled:
                        print(f"[{device.device_id}] พบ shopgachastop.png ระหว่างรอจอสุ่ม - ไป swap_shop")
                        return finish_shopgacha()
                    print(f"[{device.device_id}] พบ shopgachastop.png ระหว่างรอจอสุ่ม - backup ไป not-found")
                    device.backup_failed_game_data()
                    device.clear_and_restart()
                    time.sleep(6)
                    return "random-Fail"
                if stop_hit('shopgachastop1.png'):
                    print(f"[{device.device_id}] พบ shopgachastop1.png ระหว่างรอจอสุ่ม - จบ shop gacha")
                    return finish_shopgacha()
                rounds += 1
                if rounds % 20 == 0:
                    s0 = device._get_similarity_score('img/waitgacha.png')
                    s1 = device._get_similarity_score('img/waitgacha1.png')
                    print(f"[{device.device_id}] ยังรอจอสุ่มอยู่ ({rounds} รอบ, match ขาวดำ {s0:.2f}/{s1:.2f}) - รอต่อ")
                time.sleep(0.5)

            print(f"[{device.device_id}] เจอ {seen} - หา fixgems.png ภายใน 8 วิ")
            gems_deadline = time.time() + 8
            while time.time() < gems_deadline:
                device.capture_screen()
                if clear_fixgems():
                    return None
                time.sleep(0.5)

            print(f"[{device.device_id}] ไม่พบ fixgems ใน 8 วิ - ข้ามไป shopgacha2")
            return None

        # วนหา 8 วิเท่ากับ check_task_available ที่เพิ่งยืนยันว่า gacha.png อยู่บนจอ
        # ก่อนเรียกฟังก์ชันนี้ - ยิงครั้งเดียวแล้วพลาดได้ถ้าจอกำลังขยับ/โหลดอยู่
        # และหาด้วยทั้งภาพขาวดำ (แบบเดียวกับตัวเช็คนั้น) และภาพสีที่ 0.8
        print(f"[{device.device_id}] กำลังค้นหาทางเข้าร้าน (event.png / gacha.png)")
        entry_deadline = time.time() + 8
        entered = False
        while time.time() < entry_deadline:
            device.capture_screen()
            if clear_fixgems():     # ป๊อปอัพเพชรอาจค้างมาจากรอบก่อน
                continue
            adb_img = device._screen_color

            event_pos = ImgSearchADB(adb_img, 'img/event.png')
            if event_pos and len(event_pos) > 0:
                print(f"[{device.device_id}] พบและกด event.png")
                device.tap(event_pos[0][0], event_pos[0][1])
                entered = True
                break

            gacha_pt = device._find_in_screen("img/gacha.png", 0.8)
            if gacha_pt is None:
                gacha_pos = ImgSearchADB(adb_img, 'img/gacha.png', threshold=0.8)
                if gacha_pos and len(gacha_pos) > 0:
                    gacha_pt = gacha_pos[0]
            if gacha_pt:
                print(f"[{device.device_id}] ไม่พบ event.png - กด gacha.png เข้าร้านแทน ที่ {gacha_pt}")
                device.tap(gacha_pt[0], gacha_pt[1])
                entered = True
                break

            time.sleep(0.5)

        if entered:
            time.sleep(2)
        else:
            print(f"[{device.device_id}] ไม่พบทั้ง event.png และ gacha.png ใน 8 วิ - ลองหาปุ่มในร้านต่อ")

        # สถานะการทำงาน
        initial_sequence = ['shopgacha1.png', 'shopgacha2.png']
        loop_sequence = ['shopgacha3.png', 'shopgacha4.png', 'shopgacha5.png', 'shopgacha6.png']
        current_initial_step = 0
        in_loop = False

        # ตัวแปรสำหรับติดตามการกดซ้ำ
        repeat_counter = {}
        max_repeats = 2
        last_clicked_img = None

        # ตัวแปรสำหรับวนกลับไปเช็ค shopgacha2.png หลังจากกด shopgacha5.png
        shopgacha5_clicked = False
        check_shopgacha2_count = 0
        max_check_shopgacha2 = 8

        # ตัวแปรสำหรับ timeout
        not_found_count = 0
        max_not_found = 30
        loop_start_time = time.time()
        max_loop_time = 300
        # เพดานแข็งของ "ช่วงรอในร้าน" - taps รีเซ็ตไม่ได้ ต่างจาก 500s inactivity
        # เอาไว้กันเคสที่บอทเผลอกดป๊อปอัพ (fixnet ฯลฯ) วนไปเรื่อย ๆ จนตาข่าย 500s
        # ไม่มีวันทำงาน แล้ว thread ค้างคาไฟล์นั้นถาวร
        wait_in_shop_started = None
        max_wait_in_shop = 600

        while True:
            try:
                # ตรวจสอบ timeout - ยกเว้นตอนที่เข้าร้านได้แล้วและกำลังรอปุ่มถัดไป
                # (in_loop=False + กดปุ่มแรกไปแล้ว) ตรงนั้นให้รอได้เรื่อย ๆ ตามที่ต้องการ
                waiting_in_shop = (not in_loop) and current_initial_step > 0
                if not waiting_in_shop:
                    wait_in_shop_started = None
                    if time.time() - loop_start_time > max_loop_time:
                        print(f"[{device.device_id}] หมดเวลา {max_loop_time} วินาที - รัว BACK จนเจอ cancel แล้วไป swap_shop")
                        return finish_shopgacha()
                else:
                    if wait_in_shop_started is None:
                        wait_in_shop_started = time.time()
                    elif time.time() - wait_in_shop_started > max_wait_in_shop:
                        print(f"[{device.device_id}] รอในร้านเกิน {max_wait_in_shop} วินาที - เลิกรอ ไป swap_shop")
                        return finish_shopgacha()

                device.capture_screen()

                # fixgems ลอย ๆ - เช็คทุกรอบทั้งกระบวนการ เจอก็เคลียร์แล้ววนใหม่
                # ไม่เจอก็ไม่เป็นไร ทำงานต่อตามปกติ
                if clear_fixgems():
                    continue

                adb_img = device._screen_color

                if network_monitor.check_network(device, adb_img):
                    continue

                # ตรวจสอบ fixid, fixunkown, apple
                critical_error = check_critical_errors(device, adb_img, "process_shopgacha")
                if critical_error:
                    return critical_error

                # ตรวจสอบ shopgachastop.png (SOLD OUT) ก่อนเสมอ - หาลอย ๆ ทุกรอบ
                if stop_hit('shopgachastop.png'):
                    if swap_shop_enabled:
                        print(f"[{device.device_id}] พบ shopgachastop.png (SOLD OUT) - เปิด swap_shop คู่กัน ไป swap_shop ต่อ")
                        return finish_shopgacha()
                    print(f"[{device.device_id}] พบ shopgachastop.png (SOLD OUT) - backup ไป not-found")
                    device.backup_failed_game_data()
                    device.clear_and_restart()
                    time.sleep(6)
                    return "random-Fail"

                # ตรวจสอบ shopgachastop1.png - หาลอย ๆ ทุกรอบ เจอปุ๊บรัว BACK ออกเลย
                # ไม่ต้องรอเช็ค shopgacha2 ให้ครบ 8 รอบ
                if stop_hit('shopgachastop1.png'):
                    print(f"[{device.device_id}] พบ shopgachastop1.png - จบ shop gacha")
                    return finish_shopgacha()

                # ขั้นตอนแรก: ทำตามลำดับ shopgacha1.png -> shopgacha2.png
                if not in_loop:
                    if current_initial_step < len(initial_sequence):
                        current_img = initial_sequence[current_initial_step]
                        pt = find_btn(current_img)
                        if pt:
                            print(f"[{device.device_id}] พบและกด {current_img}")
                            if current_img == 'shopgacha2.png':
                                print(f"[{device.device_id}] รอ 5 วินาทีก่อนกด shopgacha2.png...")
                                time.sleep(5)
                            device.tap(pt[0], pt[1])
                            current_initial_step += 1
                            last_clicked_img = current_img
                            if current_img == 'shopgacha2.png':
                                time.sleep(3)
                            else:
                                time.sleep(1)

                            # ตรวจสอบ shopgachastop หลังจากกด
                            device.capture_screen()
                            check_img = device._screen_color
                            if stop_hit('shopgachastop.png'):
                                if swap_shop_enabled:
                                    print(f"[{device.device_id}] พบ shopgachastop.png (SOLD OUT) หลังกด {current_img} - เปิด swap_shop คู่กัน ไป swap_shop ต่อ")
                                    return finish_shopgacha()
                                print(f"[{device.device_id}] พบ shopgachastop.png (SOLD OUT) หลังกด {current_img} - backup ไป not-found")
                                device.backup_failed_game_data()
                                device.clear_and_restart()
                                time.sleep(6)
                                return "random-Fail"
                            if stop_hit('shopgachastop1.png'):
                                print(f"[{device.device_id}] พบ shopgachastop1.png หลังกด {current_img} - จบ shop gacha")
                                return finish_shopgacha()

                            # หลังกด shopgacha1: รอจอสุ่ม (waitgacha / waitgacha1)
                            # แล้วแวะเช็คป๊อปอัพเพชร (fixgems) ก่อนค่อยไปหา shopgacha2
                            if current_img == 'shopgacha1.png':
                                res_wait = wait_gacha_then_gems()
                                if res_wait:
                                    return res_wait

                            not_found_count = 0
                        else:
                            not_found_count += 1
                            if current_initial_step > 0:
                                # เข้าร้านได้แล้ว (กดปุ่มแรกไปแล้ว) - รอปุ่มถัดไปได้เรื่อย ๆ
                                # ไม่ตัดที่ max_not_found เพราะเกมอาจโหลด/เล่นอนิเมชันนาน
                                # ตาข่ายที่ยังคุมอยู่คือ 500s ไม่มีการกดเลย ซึ่งจะเด้งไป
                                # ไฟล์ถัดไปให้เอง ไม่มีทางค้างถาวร
                                if not_found_count % 20 == 0:
                                    score = device._get_similarity_score(f'img/{current_img}')
                                    print(f"[{device.device_id}] ยังรอ {current_img} อยู่ ({not_found_count} รอบ, match ขาวดำ {score:.2f}) - รอต่อ")
                            else:
                                # หา shopgacha1 ไม่เจอครบ 30 ครั้ง: ไม่ต้องรัว BACK ออกไป
                                # swap_shop - ข้ามไปขั้น shopgacha2 ต่อเลย (บางจอไม่มี
                                # shopgacha1 หรือเลยหน้านั้นมาแล้ว)
                                if not_found_count >= max_not_found:
                                    print(f"[{device.device_id}] ไม่พบ {current_img} ติดต่อกัน {max_not_found} ครั้ง - ข้ามไปหา shopgacha2 ต่อเลย")
                                    current_initial_step = 1
                                    not_found_count = 0
                                    continue
                                if not_found_count % 5 == 0:
                                    score = device._get_similarity_score(f'img/{current_img}')
                                    print(f"[{device.device_id}] ยังไม่พบ {current_img} - ครั้งที่ {not_found_count}/{max_not_found} (match ขาวดำ {score:.2f})")
                            time.sleep(0.5)
                        continue
                    else:
                        in_loop = True
                        last_clicked_img = None
                        # เริ่มจับเวลา 300 วิใหม่ตรงนี้ ไม่งั้นเวลาที่ใช้รอในร้าน
                        # (ซึ่งตั้งใจให้ไม่มี timeout) จะกินโควตาของลูป shopgacha3-6
                        # ไปหมด แล้วลูปได้วิ่งรอบเดียวก็โดนตัดจบ
                        loop_start_time = time.time()

                # ขั้นตอนที่สอง: วนลูปตามลำดับ
                if in_loop:
                    found_any = False

                    # ถ้ากด shopgacha5.png แล้ว ให้วนกลับไปเช็ค shopgacha2.png ก่อน
                    if shopgacha5_clicked and check_shopgacha2_count < max_check_shopgacha2:
                        print(f"[{device.device_id}] วนกลับไปเช็ค shopgacha2.png (รอบที่ {check_shopgacha2_count + 1}/{max_check_shopgacha2})")
                        pt = find_btn('shopgacha2.png')
                        if pt:
                            print(f"[{device.device_id}] พบและกด shopgacha2.png อีกครั้ง (รอ 5 วินาที)")
                            time.sleep(5)
                            device.tap(pt[0], pt[1])
                            time.sleep(3)
                            shopgacha5_clicked = False
                            check_shopgacha2_count = 0
                            found_any = True
                            not_found_count = 0
                        else:
                            check_shopgacha2_count += 1
                            if check_shopgacha2_count >= max_check_shopgacha2:
                                # ครบ 3 รอบแล้วยังไม่เจอ shopgacha2 = ไปต่อไม่ได้แล้ว
                                # รัว BACK จนเจอ cancel แล้วหยุด ค่อยไปทำ swap_shop ต่อ
                                print(f"[{device.device_id}] ไม่พบ shopgacha2.png หลังเช็ค {max_check_shopgacha2} รอบ - รัว BACK จนเจอ cancel แล้วไป swap_shop")
                                return finish_shopgacha()
                        if found_any:
                            time.sleep(0.5)
                            continue

                    # วนลูปตามปกติ
                    for img in loop_sequence:
                        pt = find_btn(img)
                        if pt:
                            # ตรวจสอบการกดซ้ำ
                            if img == last_clicked_img:
                                repeat_counter[img] = repeat_counter.get(img, 0) + 1
                                if repeat_counter[img] >= max_repeats:
                                    print(f"[{device.device_id}] พบ {img} ซ้ำเกิน {max_repeats} ครั้ง - ข้ามไปรูปถัดไป")
                                    continue
                            else:
                                repeat_counter[img] = 1

                            # ก่อนกด shopgacha4.png ให้เช็ค gachaout.png ก่อน 5 วินาที
                            if img == 'shopgacha4.png':
                                print(f"[{device.device_id}] พบ shopgacha4 - เช็ค gachaout.png ก่อนกด 5 วินาที")
                                gachaout_check_start = time.time()
                                gachaout_found = False
                                while time.time() - gachaout_check_start < 5:
                                    try:
                                        device.capture_screen()
                                        if ImgSearchADB(device._screen_color, 'img/gachaout.png'):
                                            print(f"[{device.device_id}] พบ gachaout.png ก่อนกด shopgacha4 - จบการทำงาน shopgacha")
                                            gachaout_found = True
                                            break
                                        time.sleep(0.5)
                                    except Exception as e:
                                        print(f"[{device.device_id}] Error เช็ค gachaout ก่อน shopgacha4: {e}")
                                        time.sleep(0.5)
                                if gachaout_found:
                                    return finish_shopgacha()
                                print(f"[{device.device_id}] ไม่พบ gachaout.png - กด shopgacha4.png ต่อ")

                            print(f"[{device.device_id}] พบและกด {img}")
                            device.tap(pt[0], pt[1])
                            last_clicked_img = img
                            found_any = True
                            not_found_count = 0

                            # ถ้ากด shopgacha5.png ให้เปิดสถานะวนกลับไปเช็ค shopgacha2.png
                            if img == 'shopgacha5.png':
                                shopgacha5_clicked = True
                                check_shopgacha2_count = 0

                            time.sleep(2)

                            # ตรวจสอบ shopgachastop หลังจากกดแต่ละปุ่ม
                            device.capture_screen()
                            check_img = device._screen_color
                            if stop_hit('shopgachastop.png'):
                                if swap_shop_enabled:
                                    print(f"[{device.device_id}] พบ shopgachastop.png (SOLD OUT) หลังกด {img} - เปิด swap_shop คู่กัน ไป swap_shop ต่อ")
                                    return finish_shopgacha()
                                print(f"[{device.device_id}] พบ shopgachastop.png (SOLD OUT) หลังกด {img} - backup ไป not-found")
                                device.backup_failed_game_data()
                                device.clear_and_restart()
                                time.sleep(6)
                                return "random-Fail"
                            if stop_hit('shopgachastop1.png'):
                                print(f"[{device.device_id}] พบ shopgachastop1.png หลังกด {img} - จบ shop gacha")
                                return finish_shopgacha()
                            break

                    if not found_any:
                        not_found_count += 1
                        if not_found_count >= max_not_found:
                            print(f"[{device.device_id}] ไม่พบปุ่มใดติดต่อกัน {max_not_found} ครั้ง - รัว BACK จนเจอ cancel แล้วไป swap_shop")
                            return finish_shopgacha()
                        if not_found_count % 5 == 0:
                            print(f"[{device.device_id}] ไม่พบปุ่มใดในลำดับการวนลูป - ครั้งที่ {not_found_count}/{max_not_found}")
                        last_clicked_img = None
                        repeat_counter.clear()
                        time.sleep(1)

                time.sleep(0.5)

            except Exception as e:
                print(f"[{device.device_id}] เกิดข้อผิดพลาดในกระบวนการ shop gacha: {e}")
                time.sleep(1)



    def process_swap_shopevent(self):
        print(f"[{self.device_id}] เริ่ม swap shop event")
        try:
            # Stage 1
            if check_critical_errors(self, self._screen_color, "stage1"): return "restart"
            if self.exists_in_cache("img/stopstep2.png"):
                self.clear_and_restart()
                return "stopped_by_stopstep2"
            
            # Sequence for Stage 1
            for img in ['gachaevent1.png', 'gachaevent2.png', 'gachaevent3.png']:
                pos = self._find_img_in_any_screen(self._screen_color, f"img/{img}")
                if pos:
                    self.tap(pos[0], pos[1])
                    time.sleep(1)
                    if self.exists("img/stopstep2.png"):
                        self.clear_and_restart()
                        return "stopped_by_stopstep2"

            # gachaevent4 x 20
            pos4 = self._find_img_in_any_screen(self._screen_color, "img/gachaevent4.png")
            if pos4:
                for _ in range(20):
                    self.tap(pos4[0], pos4[1])
                    time.sleep(0.3)
            
            # Hero event scan
            if check_hero_images(self, self._screen_color):
                self.backup_game_data()

            # Stage 2 Loop
            step2_start = time.time()
            while time.time() - step2_start < 300:
                self.capture_screen()
                img = self._screen_color
                if self.exists_in_cache("img/stopstep2.png"): break
                
                # Random swap_shopgachaevent check
                if random.random() < 0.2: # 20% chance per capture
                    pos_ev = self._find_img_in_any_screen(img, "img/swap_shopgachaevent.png")
                    if pos_ev: self.tap(pos_ev[0], pos_ev[1])

                # Sequence 5, 6, 3
                for ev_img in ['gachaevent5.png', 'gachaevent6.png', 'gachaevent3.png']:
                    pos_ev = self._find_img_in_any_screen(img, f"img/{ev_img}")
                    if pos_ev:
                        self.tap(pos_ev[0], pos_ev[1])
                        time.sleep(1)
            
            # Stage 3
            print(f"[{self.device_id}] Stage 3 swap_shopevent")
            for step_img in ['step3ok.png', 'step3skip.png']:
                self.click(f"img/{step_img}")
                time.sleep(1)
            
            # Step 3 Loop
            all_tiket = config.get('all_tiket', 0)
            step3_start = time.time()
            while time.time() - step3_start < 300:
                self.capture_screen()
                if self.exists_in_cache("img/stopstep2.png"): break
                for loop_img in ['step3loop1.png', 'step3loop2.png']:
                    if self.exists_in_cache(f"img/{loop_img}"):
                        self.click(f"img/{loop_img}")
                        time.sleep(1)
            
            if all_tiket == 0:
                self.clear_and_restart()
            return "complete"
        except Exception as e:
            print(f"[{self.device_id}] Swap shopevent error: {e}")
            return "error"

    @classmethod
    def _find_img_in_any_screen(cls, screen_img, template_path, similarity=0.9):
        """Helper for ImgSearchADB to use the bot's template cache on arbitrary images"""
        if screen_img is None: return None
        if len(screen_img.shape) == 3:
            gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = screen_img
            
        tmpl = cls._get_template(template_path)
        if tmpl is None: return None
        try:
            result = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
            loc = np.where(result >= similarity)
            if len(loc[0]) > 0:
                y, x = loc[0][0], loc[1][0]
                h, w = tmpl.shape
                return (x + w // 2, y + h // 2)
        except: pass
        return None

    def process_swap_shop(self):
        """Standard process_swap_shop logic integrated from user snippet"""
        device = self # map 'device' to 'self' for snippet compatibility
        network_monitor = NetworkMonitor()

        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] เริ่ม swap shop - Device: {device.device_id}")
        
        # โหลด config สำหรับตรวจสอบ all-in mode และ max-gacha
        try:
            all_in_mode = config.get('all-in', 0)
            max_gacha = config.get('max-gacha', 0)
            swap_shopevent_enabled = config.get('swap_shopevent', 0)
            
            if all_in_mode:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] โหมด All-In เปิดใช้งาน - ไม่ตรวจสอบ gachaout.png")
            else:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] โหมดปกติ - ตรวจสอบ gachaout.png")
            
            if max_gacha > 0:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] กำหนดจำนวนการสุ่มสูงสุด: {max_gacha} ครั้ง")
            else:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ไม่จำกัดจำนวนการสุ่ม")
        except Exception as e:
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error loading config: {e} - ใช้โหมดปกติ")
            all_in_mode = 0
            max_gacha = 0
            swap_shopevent_enabled = 0
        
        found_initial_swap_shop = False
        entry_miss_count = 0
        loop_beat = 0
        checked_waitgacha = False
        running = True
        first_sequence_position = 0
        second_sequence_position = 0
        gacha_count = 0

        # Hero_low: ตัวรอง หาเสมอถ้าตั้งรูปไว้ ต่างกันแค่ "เจอแล้วทำอะไรต่อ"
        #   enabled = 1 -> จดชื่อไว้ แล้วสุ่มต่อ เผื่อได้ตัวหลัก
        #   enabled = 0 -> เจอแล้วจบเลย ส่งไฟล์ออกทันที
        found_low_names = []
        hero_low_entries = load_hero_low()
        hero_low_continue = hero_low_keeps_rolling()
        if hero_low_entries:
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Hero_low - "
                  f"หาเพิ่ม {len(hero_low_entries)} ตัว "
                  f"({', '.join(n for _, n in hero_low_entries)}) | "
                  f"เจอแล้ว: {'สุ่มต่อ' if hero_low_continue else 'จบเลย'}")

        def build_prefix(main_name=None):
            """ชื่อไฟล์ = ตัวรองที่เจอ (ตามลำดับ) + ตัวหลัก เช่น kikoru+Kafka+"""
            parts = list(found_low_names)
            if main_name:
                parts.append(main_name)
            return "".join(parts) if parts else None

        def keep_low_if_any(reason):
            """เงื่อนไขออกแบบไม่เจอตัวหลัก

            ถ้าระหว่างทางเจอตัวรองไว้ ก็ยังเก็บไฟล์เข้า backup-id พร้อมชื่อตัวรอง
            แทนที่จะทิ้งไป not-found คืน "backup_complete" ถ้าเก็บแล้ว
            คืน None ถ้าไม่มีตัวรอง (ให้ผู้เรียกทำ flow เดิมต่อ)
            """
            if not found_low_names:
                return None
            low_prefix = build_prefix()
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] "
                  f"{reason} - ไม่เจอตัวหลัก แต่ได้ตัวรอง {low_prefix} เก็บเข้า backup-id")
            device.backup_game_data(low_prefix)
            ui_stats.update_hero(low_prefix)
            device.clear_and_restart()
            time.sleep(2)
            return "backup_complete"
        
        last_click_position = None
        last_image_hash = None
        last_image_time = time.time()
        
        stopgacha4_last_seen = None
        stopgacha4_last_position = None
        gachafix_last_seen = None
        
        stopgacha4_clicked = False
        gacha3_start_time = None
        gacha3_timeout = 1.5 
        
        last_gacha1_check = time.time()
        gacha1_check_interval = 15 
        current_image_start_time = time.time()
        sequence_timeout = 2.0 

        def color_score(path):
            """คะแนน match สูงสุดของภาพสี (เอาไว้ดูใน log ว่าใกล้เกณฑ์แค่ไหน)"""
            try:
                tmpl = cv2.imread(path, cv2.IMREAD_COLOR)
                if tmpl is None or device._screen_color is None:
                    return 0.0
                return float(np.max(cv2.matchTemplate(device._screen_color, tmpl, cv2.TM_CCOEFF_NORMED)))
            except Exception:
                return 0.0

        def find_btn2(path):
            """ปุ่มกด (กดตำแหน่งที่เจอ): ภาพสีล้วนแบบ ImgSearchADB เดิม
            เริ่ม 0.95 ไม่เจอค่อยลด 0.8 - ไม่ใช้ภาพขาวดำ"""
            pos = ImgSearchADB(device._screen_color, path, threshold=0.95)
            if pos and len(pos) > 0:
                return pos
            pos = ImgSearchADB(device._screen_color, path, threshold=0.8)
            if pos and len(pos) > 0:
                return pos
            return []

        def find_cond(path):
            """เงื่อนไขจบ + ปุ่มที่กดพิกัดตายตัว: ภาพสีที่ 0.95 เท่านั้น (แบบเดิมเป๊ะ)
            ห้ามลดเป็น 0.8 - เคยเจอ clear-ruby มั่วและกดพิกัดมั่วมาแล้ว"""
            pos = ImgSearchADB(device._screen_color, path, threshold=0.95)
            return pos if pos and len(pos) > 0 else []
        
        def check_gachaout_after_click(timeout=3):
            if all_in_mode: return False
            start_time = time.time()
            gachaout_found_time = None
            while time.time() - start_time < timeout:
                try:
                    device.capture_screen()
                    adb_img = device._screen_color
                    gachaout_pos = find_cond('img/gachaout.png')
                    if gachaout_pos:
                        if gachaout_found_time is None:
                            gachaout_found_time = time.time()
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ gachaout.png หลังกดปุ่ม - เริ่มนับเวลา")
                        elapsed = time.time() - gachaout_found_time
                        if elapsed >= 3:
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] gachaout.png ค้างครบ 3 วินาที - clear app")
                            device.clear_and_restart()
                            time.sleep(6)
                            return True
                    else:
                        if gachaout_found_time is not None:
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] gachaout.png หายไป - รีเซ็ต")
                            gachaout_found_time = None
                    time.sleep(0.8)
                except Exception as e:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error check gachaout: {e}")
                    time.sleep(0.8)
            return False
        
        def priority_check_gachaout(action_name, timeout=8):
            nonlocal stopgacha4_clicked
            if all_in_mode or not stopgacha4_clicked: return False
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🔎 [PRIORITY CHECK] ก่อน {action_name} - เช็คลอยๆ {timeout} วิ...")
            check_start = time.time()
            check_count = 0
            while time.time() - check_start < timeout:
                try:
                    remaining = timeout - (time.time() - check_start)
                    check_count += 1
                    device.capture_screen()
                    img = device._screen_color
                    gachaout_pos = find_cond('img/gachaout.png') or find_cond('img/gachaout1.png')
                    if gachaout_pos:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ❌ พบ gachaout.png ก่อน {action_name} - จบ swap_shop ทันที! (ไม่ใช้เพชร)")
                        ui_stats.update_hero("สุ่มไม่ได้")
                        device.clear_and_restart()
                        time.sleep(6)
                        return True
                except Exception as e:
                    pass
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ✅ [PRIORITY CHECK] ผ่าน - ไม่พบ gachaout.png ({timeout} วิ)")
            return False
        
        def safe_tap(x, y, image_name, delay_before=0, delay_after=0, check_gachaout_time=0.3):
            if delay_before > 0:
                time.sleep(delay_before)
            
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ⚡ กดปุ่ม: {image_name}")
            device.tap(x, y)
            
            if delay_after > 0:
                time.sleep(delay_after)
            
            if not all_in_mode and check_gachaout_time > 0:
                check_start = time.time()
                while time.time() - check_start < check_gachaout_time:
                    try:
                        device.capture_screen()
                        img = device._screen_color
                        gachaout_pos = find_cond('img/gachaout.png') or find_cond('img/gachaout1.png')
                        if gachaout_pos:
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ❌ [SAFE TAP] พบ gachaout.png หลังกด {image_name}! จบ swap_shop ทันที!")
                            ui_stats.update_hero("สุ่มไม่ได้")
                            device.clear_and_restart()
                            time.sleep(6)
                            return "gachaout_found"
                        time.sleep(0.1)
                    except Exception as e:
                        time.sleep(0.1)

            return "ok"
        
        def check_and_count_swapgacha1():
            nonlocal gacha_count
            if max_gacha <= 0: return False
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] รอ 3 วินาทีก่อนตรวจสอบ swapgacha1.png")
            time.sleep(3)
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] เริ่มตรวจสอบ swapgacha1.png เป็นเวลา 3 วินาที")
            check_start_time = time.time()
            swapgacha1_found = False
            while time.time() - check_start_time < 3:
                try:
                    device.capture_screen()
                    check_img = device._screen_color
                    swapgacha1_pos = find_cond('img/swapgacha1.png')
                    if swapgacha1_pos:
                        if not swapgacha1_found:
                            gacha_count += 1
                            swapgacha1_found = True
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ swapgacha1.png - นับ poin ครั้งที่ {gacha_count}/{max_gacha}")
                            if gacha_count >= max_gacha:
                                return "complete_gacha"
                            break
                    time.sleep(0.2)
                except Exception as e:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error checking swapgacha1.png: {e}")
                    break
            return False
        
        def check_gacha1(adb_img):
            try:
                gacha1_pos = find_btn2('img/gacha1.png')
                if gacha1_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] กด gacha1")
                    device.tap(gacha1_pos[0][0], gacha1_pos[0][1])
                    time.sleep(1.5)
                    if check_gachaout_after_click(): return "random-Fail"
                    return True
                return False
            except Exception as e:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error gacha1: {e}")
                return False
        
        def check_fixbuggacha(adb_img):
            try:
                fixbuggacha_pos = find_btn2('img/fixbuggacha.png')
                if fixbuggacha_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] กด fixbuggacha")
                    device.tap(fixbuggacha_pos[0][0], fixbuggacha_pos[0][1])
                    time.sleep(1.5)
                    if check_gachaout_after_click(): return "random-Fail"
                    return True
                return False
            except Exception as e:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error fixbuggacha: {e}")
                return False
        
        def check_hero_images(adb_img):
            # ค้นหาจาก img/ranger-gacha/ ก่อน (ตรงกับ HERO_MAPPING keys โดยตรง)
            gacha_hero_images = ['gachahero1.png', 'gachahero2.png', 'gachahero3.png', 'gachahero4.png']
            for hero_img in gacha_hero_images:
                hero_pos = ImgSearchADB(adb_img, f'img/ranger-gacha/{hero_img}')
                if hero_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ {hero_img} (ranger-gacha)")
                    return hero_img
            # Fallback: ค้นหาจาก img/ranger/ (heroo1-4.png)
            hero_images = ['heroo1.png', 'heroo2.png', 'heroo3.png', 'heroo4.png']
            for hero_img in hero_images:
                hero_pos = ImgSearchADB(adb_img, f'img/ranger/{hero_img}')
                if hero_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ {hero_img} (ranger)")
                    return hero_img
            return None

        def get_image_hash(adb_img):
            return hashlib.md5(adb_img.tobytes()).hexdigest()

        def get_channel_position():
            try:
                channels_img_enabled = config.get('channels_img', 0)
                if channels_img_enabled == 1:
                    return search_gachaslot_image(device)
                else:
                    selected_channel = config.get('channel', 'ch2')
                    if 'channels' not in config or selected_channel not in config['channels']: return None
                    channel_pos = config['channels'][selected_channel]
                    if not isinstance(channel_pos, list) or len(channel_pos) != 2: return None
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ช่อง: {selected_channel}")
                    if selected_channel in ['ch4', 'ch5']:
                        for _ in range(2):
                            device.swipe(852, 316, 855, 116, 2000)
                            time.sleep(0.2)
                    return channel_pos
            except Exception as e:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error config: {e}")
                return None

        device.capture_screen()
        adb_img = device._screen_color
        event_pos = find_btn2('img/event.png')
        if event_pos:
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] กด event")
            device.tap(event_pos[0][0], event_pos[0][1])
            last_click_position = event_pos[0]
            time.sleep(2)
            if check_gachaout_after_click(): return "random-Fail"
            time.sleep(1)
        
        while running:
            try:
                device.capture_screen()
                adb_img = device._screen_color
                current_time = time.time()
                loop_beat += 1
                if loop_beat % 30 == 0:
                    hb = color_score('img/gacha.png')
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] [HB] ลูป swap_shop รอบ {loop_beat} | เข้าห้องสุ่มแล้ว: {found_initial_swap_shop} | seq {first_sequence_position}/{second_sequence_position} | match gacha(สี) {hb:.2f}")

                # Hero_low: หาตัวรองทุกรอบ ก่อนเช็คเงื่อนไขออกทุกตัว
                if hero_low_entries:
                    new_lows = find_hero_low_images(device, adb_img, found_low_names)
                    if new_lows:
                        found_low_names.extend(new_lows)
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] "
                              f"ตัวรองสะสม: {''.join(found_low_names)}")

                        if not hero_low_continue:
                            # enabled = 0 -> เจอแล้วจบเลย ไม่สุ่มต่อ
                            # เช็คตัวหลักบนเฟรมเดียวกันก่อน เผื่อโผล่มาพร้อมกัน
                            # จะได้ไม่ทิ้งตัวหลักไปเพราะรีบจบ
                            main_hero = check_hero_images(adb_img)
                            main_name = None
                            if main_hero:
                                hero_key = main_hero.replace(".png", "").replace("heroo", "gachahero")
                                main_name = config.get("HERO_MAPPING", {}).get(hero_key, main_hero)
                            prefix = build_prefix(main_name)
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] "
                                  f"เจอตัวรอง -> จบเลย (Hero_low enabled=0) ส่งไฟล์ {prefix}")
                            device.backup_game_data(prefix)
                            ui_stats.update_hero(main_name or prefix)
                            device.clear_and_restart()
                            time.sleep(2)
                            return "backup_complete"

                # ⭐ เช็ค fixrandom1 ลอยๆ ตลอดทั้งกระบวนการ - เจอเมื่อไหร่กด fixrandom2 ทันที
                if find_btn2('img/fixrandom1.bmp'):
                    fixrandom2_pos = find_btn2('img/fixrandom2.bmp')
                    if fixrandom2_pos:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🎲 พบ fixrandom1 - กด fixrandom2")
                        device.tap(fixrandom2_pos[0][0], fixrandom2_pos[0][1])
                        time.sleep(1)
                        continue

                critical_error = check_critical_errors(device, adb_img, "process_swap_shop")
                if critical_error: return critical_error

                # Check for kaibyswap_shop.png
                kaibyswap_pos = find_cond('img/kaibyswap_shop.png')
                if kaibyswap_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ พบ kaibyswap_shop.png - ส่งไปห้องไก่บี้")
                    device.clear_and_restart()
                    time.sleep(6)
                    return "kaiby"

                # Check for clear-ruby -> clear app + ส่งไป random-fail + เริ่มไฟล์ใหม่
                clearruby_pos = find_cond('img/clear-ruby.bmp')
                if clearruby_pos:
                    kept = keep_low_if_any("พบ clear-ruby")
                    if kept: return kept
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ❌ พบ clear-ruby - clear app + ส่งไป random-fail")
                    ui_stats.update_hero("สุ่มไม่ได้")
                    device.clear_and_restart()
                    time.sleep(6)
                    return "random-Fail"

                if not all_in_mode:
                    gachaout_priority_pos = find_cond('img/gachaout.png') or find_cond('img/gachaout1.png')
                    if gachaout_priority_pos:
                        kept = keep_low_if_any("พบ gachaout.png")
                        if kept: return kept
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ❌ พบ gachaout.png - จบ swap_shop")
                        ui_stats.update_hero("สุ่มไม่ได้")
                        device.clear_and_restart()
                        time.sleep(6)
                        return "random-Fail"
                else:
                    # all-in: สุ่มด้วยเพชรไปเรื่อยๆ - หยุดเฉพาะเมื่อเจอ gachaout1 (ทับทิมหมดจริง) เท่านั้น
                    gachaout1_pos = find_cond('img/gachaout1.png')
                    if gachaout1_pos:
                        kept = keep_low_if_any("[ALL-IN] พบ gachaout1.png (ทับทิมหมด)")
                        if kept: return kept
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ❌ [ALL-IN] พบ gachaout1.png (ทับทิมหมด) - จบ swap_shop")
                        ui_stats.update_hero("สุ่มไม่ได้")
                        device.backup_failed_game_data()
                        device.clear_and_restart()
                        time.sleep(6)
                        return "random-Fail"
                
                # CONTINUOUS CHECK removed to let outer loop handle gachaout natively (0 delay)

                if network_monitor.check_network(device, adb_img): continue
                fixunkown_pos = find_cond('img/fixunkown.png')
                if fixunkown_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ fixunkown - กด (477,349)")
                    device.tap(477, 349)
                    time.sleep(1.5)
                    if check_gachaout_after_click(): return "random-Fail"
                    continue
                check_result = check_fixbuggacha(adb_img)
                if check_result == "restart": return "restart"
                elif check_result:
                    last_click_position = None
                    continue
                stopgacha7_pos = find_cond('img/stopgacha7.png')
                if stopgacha7_pos:
                    found_hero = check_hero_images(adb_img)
                    if not found_hero and all_in_mode:
                        # all-in: stopgacha7 = จอ "จ่าย 50 ทับทิม" (เหมือน gachaout) - ไม่ใช่จอจบ
                        # กด OK (stopgacha6) เพื่อจ่ายเพชรแล้วสุ่มต่อ แทนการ clear app
                        ok_pos = find_btn2('img/stopgacha6.png')
                        if ok_pos:
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 💎 [ALL-IN] พบจอจ่ายทับทิม (stopgacha7) - กด OK สุ่มต่อด้วยเพชร")
                            safe_tap(ok_pos[0][0], ok_pos[0][1], "stopgacha6 (confirm spend - all-in)", 0, 0, 0)
                        continue
                    if not found_hero:
                        kept = keep_low_if_any("พบ stopgacha7 (จบการสุ่ม)")
                        if kept: return kept
                        device.backup_failed_game_data()
                        ui_stats.update_hero("สุ่มไม่ได้")
                        device.clear_and_restart()
                        time.sleep(2)
                        return "random-Fail"
                    else:
                        hero_key = found_hero.replace(".png", "").replace("heroo", "gachahero")
                        display_name = config.get("HERO_MAPPING", {}).get(hero_key, found_hero)
                        ui_stats.update_hero(display_name)
                        device.backup_game_data(build_prefix(display_name))
                        device.clear_and_restart()
                        time.sleep(2)
                        return "backup_complete"
                gacha3_pos = find_cond('img/gacha3.png')
                if gacha3_pos:
                    if gacha3_start_time is None: gacha3_start_time = current_time
                    else:
                        if current_time - gacha3_start_time >= 0.1:
                            stopgachaok_pos = find_cond('img/stopgachaok.png')
                            if stopgachaok_pos:
                                device.tap(480, 353)
                                if not all_in_mode:
                                    gachaout_check_start = time.time()
                                    found_gachaout = False
                                    while time.time() - gachaout_check_start < 5:
                                        try:
                                            device.capture_screen()
                                            if find_cond('img/gachaout.png'):
                                                found_gachaout = True
                                                break
                                            time.sleep(0.5)
                                        except RestartTimeoutError: raise
                                        except Exception: time.sleep(0.5)
                                    if found_gachaout:
                                        device.clear_and_restart()
                                        time.sleep(6)
                                        return "random-Fail"
                            gacha3_start_time = None
                            continue
                else: gacha3_start_time = None
                if current_time - last_gacha1_check >= gacha1_check_interval:
                    check_result = check_gacha1(adb_img)
                    if check_result == "restart": return "restart"
                    last_gacha1_check = current_time
                found_hero = check_hero_images(adb_img)
                if found_hero:
                    hero_key = found_hero.replace(".png", "").replace("heroo", "gachahero")
                    display_name = config.get("HERO_MAPPING", {}).get(hero_key, found_hero)
                    # เจอตัวหลักแล้วจบเลย ไม่หาตัวรองต่อ แต่ชื่อไฟล์เอาตัวรองที่เจอมาก่อนหน้ามาต่อหัว
                    if device.backup_game_data(build_prefix(display_name)):
                        ui_stats.update_hero(display_name)
                        device.clear_and_restart()
                        time.sleep(2)
                        return "backup_complete"
                    else:
                        time.sleep(1)
                        continue
                stopgachaok_pos = find_cond('img/stopgachaok.png')
                if stopgachaok_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ stopgachaok - กด (480,353)")
                    device.tap(480, 353)
                    time.sleep(2)
                    if check_gachaout_after_click(timeout=5): return "random-Fail"
                    continue
                stopgacha4_pos = find_btn2('img/stopgacha4.png')
                if stopgacha4_pos:
                    stopgacha4_clicked = True
                    stopgacha4_last_position = stopgacha4_pos[0]
                    stopgacha4_last_seen = current_time
                    if safe_tap(stopgacha4_pos[0][0], stopgacha4_pos[0][1], "stopgacha4 (1)", 0, 0, 0) == "gachaout_found": return "random-Fail"
                    if safe_tap(stopgacha4_pos[0][0], stopgacha4_pos[0][1], "stopgacha4 (2)", 0, 0, 0.3) == "gachaout_found": return "random-Fail"
                    if check_and_count_swapgacha1() == "complete_gacha":
                        device.clear_and_restart()
                        time.sleep(2)
                        return "random-Fail"
                    continue
                gachafix_pos = find_btn2('img/gachafix.png')
                if gachafix_pos:
                    if priority_check_gachaout("stopgacha6", 0.1): return "random-Fail"
                    stopgacha6_pos = find_btn2('img/stopgacha6.png')
                    if stopgacha6_pos:
                        last_click_position = stopgacha6_pos[0]
                        if safe_tap(stopgacha6_pos[0][0], stopgacha6_pos[0][1], "stopgacha6 (1)", 0, 0, 0) == "gachaout_found": return "random-Fail"
                        if safe_tap(stopgacha6_pos[0][0], stopgacha6_pos[0][1], "stopgacha6 (2)", 0, 0, 0.3) == "gachaout_found": return "random-Fail"
                        if check_and_count_swapgacha1() == "complete_gacha":
                            ui_stats.update_hero("สุ่มไม่ได้")
                            device.backup_failed_game_data()
                            device.clear_and_restart()
                            time.sleep(2)
                            return "random-Fail"
                current_hash = get_image_hash(adb_img)
                if current_hash == last_image_hash:
                    if current_time - last_image_time >= 1800:
                        if last_click_position:
                            device.tap(last_click_position[0], last_click_position[1])
                            if check_gachaout_after_click(): return "random-Fail"
                        last_image_time = current_time
                else:
                    last_image_hash = current_hash
                    last_image_time = current_time
                all_in_spent_ruby = False
                for stop_img in ['stopgacha5.png', 'stopgacha7.png', 'stopgacha8.png']:
                    if find_cond(f'img/{stop_img}'):
                        found_hero = check_hero_images(adb_img)
                        # all-in: จอทับทิม (stopgacha5/7/8) ไม่ใช่จอจบ - กด OK สุ่มต่อด้วยเพชร (ไม่ clear app)
                        # การหยุดจะถูกจัดการโดย gachaout1 (ทับทิมหมดจริง) ที่ priority check ด้านบนเท่านั้น
                        if not found_hero and all_in_mode:
                            ok_pos = find_btn2('img/stopgacha6.png')
                            if ok_pos:
                                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 💎 [ALL-IN] พบจอจ่ายทับทิม ({stop_img}) - กด OK สุ่มต่อด้วยเพชร")
                                safe_tap(ok_pos[0][0], ok_pos[0][1], "stopgacha6 (confirm spend - all-in)", 0, 0, 0)
                            all_in_spent_ruby = True
                            break
                        if not found_hero:
                            device.backup_failed_game_data()
                            ui_stats.update_hero("สุ่มไม่ได้")
                            device.clear_and_restart()
                            time.sleep(2)
                            return "random-Fail"
                        else:
                            hero_key = found_hero.replace(".png", "").replace("heroo", "gachahero")
                            display_name = config.get("HERO_MAPPING", {}).get(hero_key, found_hero)
                            ui_stats.update_hero(display_name)
                            device.backup_game_data(display_name)
                            device.clear_and_restart()
                            time.sleep(2)
                            return "backup_complete"
                if all_in_spent_ruby:
                    continue
                if not found_initial_swap_shop:
                    swap_shop_pos = find_btn2('img/gacha.png')
                    if not swap_shop_pos:
                        entry_miss_count += 1
                        if entry_miss_count % 20 == 0:
                            score = color_score('img/gacha.png')
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ยังหา gacha.png เข้าห้องสุ่มไม่เจอ ({entry_miss_count} รอบ, match สี {score:.2f})")
                    if swap_shop_pos:
                        device.tap(swap_shop_pos[0][0], swap_shop_pos[0][1])
                        last_click_position = swap_shop_pos[0]
                        found_initial_swap_shop = True
                        time.sleep(2)
                        if check_gachaout_after_click(): return "random-Fail"
                        start_time = time.time()
                        found_waitgacha = False
                        while True:
                            try:
                                device.capture_screen()
                                if not found_waitgacha:
                                    if find_btn2('img/waitgacha.png'):
                                        found_waitgacha = True
                                        start_time = time.time()
                                    elif time.time() - start_time > 60:
                                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] รอ waitgacha เกิน 60 วิ - ไปต่อขั้นเลือกช่อง")
                                        checked_waitgacha = True
                                        break
                                if found_waitgacha:
                                    fixnewgacha_pos = find_cond('img/fixnewgacha.png')
                                    if fixnewgacha_pos:
                                        device.tap(476, 394)
                                        checked_waitgacha = True
                                        if check_gachaout_after_click(): return "random-Fail"
                                        break
                                    if time.time() - start_time > 10:
                                        checked_waitgacha = True
                                        break
                                time.sleep(0.5)
                            except RestartTimeoutError: raise
                            except Exception: continue
                        channel_pos = get_channel_position()
                        if channel_pos and len(channel_pos) == 2:
                            device.tap(channel_pos[0], channel_pos[1])
                            if check_gachaout_after_click(): return "random-Fail"
                            if swap_shopevent_enabled: return "swap_shopevent"
                        continue
                if not checked_waitgacha:
                    if find_btn2('img/waitgacha.png'):
                        checked_waitgacha = True
                        time.sleep(1.5)
                        continue
                if first_sequence_position < 3:
                    purchase_sequence = ['stopgacha.png', 'stopgacha1.png', 'stopgacha2.png']
                    current_img = purchase_sequence[first_sequence_position]
                    pos = find_btn2(f'img/{current_img}')
                    if pos:
                        last_click_position = pos[0]
                        first_sequence_position += 1
                        if safe_tap(pos[0][0], pos[0][1], f"{current_img}", 0, 0, 0.3) == "gachaout_found": return "random-Fail"
                        if check_and_count_swapgacha1() == "complete_gacha":
                            ui_stats.update_hero("สุ่มไม่ได้")
                            device.clear_and_restart()
                            time.sleep(2)
                            return "random-Fail"
                        if current_img == 'stopgacha2.png': first_sequence_position = 3
                        continue
                if first_sequence_position >= 3:
                    second_sequence = ['stopgacha4.png', 'stopgacha6.png', 'stopgacha2.png']
                    current_img = second_sequence[second_sequence_position]
                    if current_time - current_image_start_time >= sequence_timeout:
                        second_sequence_position = (second_sequence_position + 1) % len(second_sequence)
                        current_image_start_time = current_time
                        continue
                    pos = find_btn2(f'img/{current_img}')
                    if pos:
                        last_click_position = pos[0]
                        second_sequence_position = (second_sequence_position + 1) % len(second_sequence)
                        current_image_start_time = current_time
                        if safe_tap(pos[0][0], pos[0][1], f"{current_img}", 0, 0, 0.3) == "gachaout_found": return "random-Fail"
                        if check_and_count_swapgacha1() == "complete_gacha":
                            device.clear_and_restart()
                            time.sleep(2)
                            return "random-Fail"
                if time.time() % 300 < 1: gc.collect()
            except Exception as e:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error: {e}")
                time.sleep(2)
        return "complete"


    def _is_app_installed(self, tries=3):
        """เช็คว่าเครื่องนี้มีแอปติดตั้งอยู่จริงไหม (retry เผื่อ VM เพิ่งบูต pm ตอบว่าง)

        คืน True = มีแอป / False = pm ตอบมาแล้วว่า "ไม่มี" / None = เช็คไม่ได้เลย (adb ค้าง/timeout)
        เดิม timeout ถูกนับเป็น "ไม่มีแอป" -> ตอนเปิด 17 เครื่องพร้อมกัน adb ตอบไม่ทัน
        บอทเลยตัดสินว่าไม่มีแอปแล้วหยุดตัวเองถาวรทั้งแถวภายใน 40 วิ (ERROR แดงยกจอ)
        """
        answered = False
        for attempt in range(tries):
            try:
                pm_res = self.adb_run([
                    self.adb_cmd, "-s", self.device_id, "shell",
                    "pm", "list", "packages", "com.linecorp.LGRGS"
                ], timeout=15)
                out = (pm_res.stdout or b"").decode("utf-8", "ignore")
                if "com.linecorp.LGRGS" in out:
                    return True
                if pm_res.returncode == 0:
                    answered = True      # pm ตอบจริง แต่ไม่มีแพ็กเกจนี้
            except Exception as e:
                print(f"[{self.device_id}] [WARN] เช็ค package ไม่ได้ (ครั้งที่ {attempt + 1}/{tries}): {e}")
            if attempt < tries - 1:
                sleep(3)
        return False if answered else None

    def _signal_ready(self):
        """บอกตัวปล่อยบอทว่าเครื่องนี้พร้อมแล้ว เพื่อให้ปล่อยเครื่องถัดไปได้ทันที

        ใช้การจับจอรอบแรกเป็นตัววัด: ผ่านแล้วแปลว่า adb ต่อติดและงานหนักตอน
        สตาร์ต (import / ต่อ adb / จับจอ) จบจริง ไม่ใช่เดาเอาจากนาฬิกา
        """
        q = getattr(self, "_ready_q", None)
        if q is None:
            return
        self._ready_q = None          # ส่งครั้งเดียวพอ
        try:
            self.capture_screen()
        except Exception:
            pass
        try:
            q.put(self.device_id)
        except Exception:
            pass

    def run(self):
        try:
            print(f"[{self.device_id}] RangerGear Bot Thread Started", flush=True)
            self._signal_ready()   # พร้อมแล้ว -> ปล่อยเครื่องถัดไปได้เลย

            # ── เช็คก่อนเริ่ม: ไม่มีแอปบนเครื่องนี้ = หยุดเลย "ก่อน" จะไปหยิบไฟล์ ──
            #    (ไม่ล็อกไฟล์ ไม่ inject ไม่ย้ายไฟล์ไปไหน — ไฟล์ค้างอยู่ในคิวครบเหมือนเดิม)
            installed = self._is_app_installed()
            if installed is False:
                self.app_missing = True
                print(f"[{self.device_id}] ⛔ เครื่องนี้ไม่มีแอป com.linecorp.LGRGS — หยุดบอทเครื่องนี้ "
                      f"ไม่หยิบ/ไม่ย้ายไฟล์ใดๆ (ไฟล์อยู่ครบในคิวเหมือนเดิม)", flush=True)
                self.update_gui_status("No app - stopped", "error")
                return
            if installed is None:
                # adb ตอบไม่ทัน (เปิดหลายเครื่องพร้อมกัน) - ไม่ใช่หลักฐานว่าไม่มีแอป เดินต่อ
                # ถ้าแอปหายจริงจะไปเจอตอน open_app ระหว่างรันแล้วหยุดตรงนั้นแทน
                print(f"[{self.device_id}] [WARN] เช็คแอปไม่ได้ (adb ช้า/ค้าง) - ไม่ถือว่าไม่มีแอป เดินต่อ", flush=True)
                self.update_gui_status("adb ช้า - เดินต่อ", "waiting")

            while True:
                # 0. Reload Config
                load_config()

                # แอปหายระหว่างทาง (crash loop / ถอนแอป) → หยุดหยิบไฟล์ใหม่ทันที
                if getattr(self, "app_missing", False):
                    print(f"[{self.device_id}] ⛔ แอปหายจากเครื่องนี้ — หยุดส่งไฟล์ ไฟล์ที่เหลืออยู่ในคิวครบเหมือนเดิม", flush=True)
                    self.update_gui_status("No app - stopped", "error")
                    break
                # Strict Toggles from configmain.json
                self.do_ranger = config.get("find_ranger", 0)
                self.do_gear = (config.get("check-gear", 0) or 
                                config.get("ruby-gear200", 0) or 
                                config.get("random-gear", 0))

                # 1. Look for next available file (Atomic Locking)
                xml_file = self._get_next_available_file()
                
                if not xml_file:
                    self.update_gui_status("Waiting for files", "waiting")
                    # Log only once every 60 seconds to avoid spam
                    if not hasattr(self, '_last_wait_log') or time.time() - self._last_wait_log > 60:
                        print(f"[{self.device_id}] File queue empty. Waiting for new files...")
                        self._last_wait_log = time.time()
                    sleep(10)
                    continue
                
                # Reset wait log once we get a file
                self._last_wait_log = 0

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
                        login_start_time = time.time()
                        try:
                            status = self.main_login(injected_file)
                        except RestartTimeoutError:
                            status = "timeout"
                            print(f"[{self.device_id}] Caught 500s Timeout!")
                            self.clear_and_restart()
                        
                        if status == "success":
                            ui_stats.record_login_time(time.time() - login_start_time)
                            self.handle_success(xml_file)
                            ui_stats.update(success=ui_stats.success_count + 1, processed=ui_stats.processed_files + 1)
                            self.update_gui_status("Completed", "idle")
                        elif status == "kaiby":
                            self.handle_kaiby(xml_file)
                            ui_stats.update_hero("❌ ไก่บี้")
                            self.update_gui_status("Kaiby Detected", "error")
                            self.first_loop_done = False
                        elif status == "random-Fail":
                            self.handle_random_fail(xml_file)
                            ui_stats.update(random_fail=ui_stats.random_fail_count + 1)
                            self.update_gui_status("Random/Gacha Failed", "error")
                            self.first_loop_done = False
                        elif status == "failed":
                            _rec = None
                            if config.get("recover_failed", 1) and not getattr(self, "_recovering", False):
                                self._recovering = True
                                try:
                                    _rec = self._recover_failed_id(xml_file)
                                finally:
                                    self._recovering = False
                            if _rec == "success":
                                self.handle_success(xml_file)
                                ui_stats.update(success=ui_stats.success_count + 1, processed=ui_stats.processed_files + 1)
                                self.update_gui_status("Completed (recovered)", "idle")
                            elif _rec == "kaiby":
                                self.handle_kaiby(xml_file)
                                ui_stats.update_hero("❌ ไก่บี้")
                                self.update_gui_status("Kaiby (recover)", "error")
                                self.first_loop_done = False
                            elif _rec == "random-Fail":
                                self.handle_random_fail(xml_file)
                                ui_stats.update(random_fail=ui_stats.random_fail_count + 1)
                                self.update_gui_status("Random/Gacha (recover)", "error")
                                self.first_loop_done = False
                            else:
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
                    
                except RestartTimeoutError:
                    # หมดเวลาที่จุดอื่นนอกเหนือจาก main_login (first_loop / inject / ฯลฯ)
                    # เก็บกวาดแล้วไปไฟล์ถัดไป ไม่ให้ thread ตายไปเงียบ ๆ
                    print(f"[{self.device_id}] 500s ไม่มีการกดอะไรเลย - เคลียร์แอพแล้วข้ามไฟล์นี้")
                    try:
                        self.clear_and_restart()
                    except Exception:
                        pass
                    self._release_file_lock(xml_file)
                    self.first_loop_done = False
                    sleep(2)
                except Exception as e:
                    print(f"[{self.device_id}] Critical Error with {xml_file}: {e}")
                    self._release_file_lock(xml_file)
                    sleep(5)
        except RestartTimeoutError:
            # ตาข่ายชั้นสุดท้าย - ไม่ควรมาถึงตรงนี้ แต่ถ้ามาก็อย่าให้บอทตายเงียบ
            print(f"[{self.device_id}] Thread หลุดด้วย 500s Timeout - เริ่ม thread ใหม่", flush=True)
            sleep(5)
            return self.run()
        except Exception as e:
            print(f"[{self.device_id}] Thread Crash: {e}", flush=True)

    def _get_lock_path(self, xml_file):
        """Get lock file path in temp directory (ไม่รก backup folder)"""
        lock_dir = os.path.join(tempfile.gettempdir(), "ranger-locks")
        if not os.path.exists(lock_dir):
            os.makedirs(lock_dir, exist_ok=True)
        # ใช้ hash ของ full path กัน lock ชนกันกรณีไฟล์ชื่อซ้ำในคนละโฟลเดอร์ย่อย
        full = os.path.abspath(xml_file)
        lock_name = hashlib.md5(full.encode("utf-8")).hexdigest() + "_" + os.path.basename(xml_file) + ".lock"
        return os.path.join(lock_dir, lock_name)

    @staticmethod
    def _prune_if_empty(folder, root_folder):
        """ลบโฟลเดอร์ย่อยใน backup/ ที่ไม่เหลืออะไรแล้ว

        ใช้ os.rmdir เป็นตัวตัดสินเลย เพราะมันลบได้เฉพาะตอนที่โฟลเดอร์ว่างจริง ๆ
        และเป็น operation เดียวจบ - ถ้าอีกเครื่องเพิ่งหย่อนไฟล์เข้ามาพอดี rmdir
        จะ error แล้วเราข้ามไป ไม่มีทางลบไฟล์ของใครหาย
        โฟลเดอร์ backup/ ตัวแม่ไม่ลบ และโฟลเดอร์ที่ยังมีไฟล์อื่นค้าง (เช่น .txt)
        ก็ไม่ลบ เพื่อไม่ให้ข้อมูลใครหายโดยไม่ตั้งใจ
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
        print(f"[QUEUE] ใช้ไฟล์หมดแล้ว ลบโฟลเดอร์ว่าง: {os.path.basename(root_folder)}/{rel}")
        return True

    def _get_next_available_file(self):
        """หาไฟล์ .xml ตัวถัดไปแล้วจองแบบ atomic

        ดึงจาก 2 โฟลเดอร์: backup/ ก่อนเสมอ ถ้าในนั้นไม่เหลือไฟล์ที่จองได้แล้ว
        ค่อยไปหาต่อใน input-id/ (โฟลเดอร์ไหนไม่มีก็ข้าม)
        เดินเข้าทุกโฟลเดอร์ย่อย (ลากทั้งโฟลเดอร์มาวางได้เลย) และเก็บกวาด
        โฟลเดอร์ย่อยที่ใช้ไฟล์หมดแล้วทิ้งไปด้วย
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        for folder_name in queue_folder_names():
            picked = self._pick_file_from(os.path.join(script_dir, folder_name))
            if picked:
                return picked

        # คิวหมดแล้ว -> เอา login-failed กลับมาวนใหม่ (ปิดได้ด้วย recycle_failed=0)
        if recycle_failed_into_queue():
            for folder_name in queue_folder_names():
                picked = self._pick_file_from(os.path.join(script_dir, folder_name))
                if picked:
                    return picked

        # ยังไม่มีอะไรให้ทำ -> ดึงไฟล์ใน 7day-check/ ที่ยังไม่ครบ 7/7 กลับมารับของต่อ
        if recycle_7day_into_queue():
            for folder_name in queue_folder_names():
                picked = self._pick_file_from(os.path.join(script_dir, folder_name))
                if picked:
                    return picked
        return None

    def _pick_file_from(self, source_folder):
        """หา+จองไฟล์ .xml จากโฟลเดอร์เดียว คืน path ที่จองได้ หรือ None"""
        if not os.path.exists(source_folder): return None

        files = []
        # topdown=False = เดินจากในสุดออกมา โฟลเดอร์ซ้อนหลายชั้นที่ว่างหมดแล้ว
        # จะถูกลบไล่จากชั้นในออกมาได้ครบในรอบเดียว
        for root, dirs, filenames in os.walk(source_folder, topdown=False):
            for f in filenames:
                if f.lower().endswith(".xml"):
                    files.append(os.path.join(root, f))
            self._prune_if_empty(root, source_folder)
        # Shuffle files so multiple processes don't hit the exact same order
        import random
        random.shuffle(files)
        
        for xml_file in files:
            lock_file = self._get_lock_path(xml_file)
            
            # 1. Clean stale locks (> 30 mins)
            if os.path.exists(lock_file):
                if time.time() - os.path.getmtime(lock_file) > 1800:
                    try: os.remove(lock_file)
                    except: pass
                else: continue
            
            # 2. Try Atomic Lock (O_CREAT | O_EXCL)
            try:
                fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, 'w') as f:
                    f.write(self.device_id)
                # ไฟล์อาจถูกอีกเครื่องหยิบไปย้ายเรียบร้อยแล้วตั้งแต่ตอนที่เราไล่ list
                # ถ้าหายไปแล้วก็คืน lock แล้วไปตัวถัดไป ดีกว่าเอา path ที่ไม่มีอยู่จริง
                # ไปให้ inject_file แล้วไปเด้ง error ทีหลัง
                if not os.path.exists(xml_file):
                    try: os.remove(lock_file)
                    except OSError: pass
                    continue
                return xml_file
            except FileExistsError:
                continue
            except Exception as e:
                print(f"[LOCK] Error creating lock for {xml_file}: {e}")
                continue
                
        return None

    def _release_file_lock(self, xml_file):
        lock_file = self._get_lock_path(xml_file)
        if os.path.exists(lock_file):
            try: os.remove(lock_file)
            except: pass

    def handle_dead_file(self, file_path):
        """Move file that failed injection or has other issues"""
        # แอปไม่มีบนเครื่องนี้ → ห้ามย้ายไฟล์ไปไหน ปล่อยไว้ในคิวเหมือนเดิม
        if getattr(self, "app_missing", False):
            print(f"[{self.device_id}] ⛔ ไม่มีแอปบนเครื่องนี้ — ไม่ย้ายไฟล์ {os.path.basename(file_path)} ปล่อยไว้ที่เดิม")
            return
        # adb หลุด/offline → ผลที่อ่านได้เชื่อไม่ได้ ห้ามตัดสินว่าล็อกอินไม่ผ่าน
        if not self.device_is_online():
            self._keep_file_in_queue(file_path, "adb offline/หลุดการเชื่อมต่อ")
            return
        dst_dir = "login-failed"
        if not os.path.exists(dst_dir): os.makedirs(dst_dir)
        base = os.path.basename(file_path)
        try: shutil.move(file_path, os.path.join(dst_dir, base))
        except: pass

    # =========================================================
    # File Handling
    # =========================================================
    def handle_success(self, file_path):
        # ทำ 7 วันมาในรอบนี้ -> ส่งออกไป 7day-check/ ชื่อ "[7=จำนวน check7day]+เดิม" แทน login-success
        # ตรงนี้คือตอนจบไฟล์ งาน box ที่เปิดไว้ทำเสร็จไปก่อนหน้านี้แล้ว
        count7 = getattr(self, "_check7day_count", None)
        if count7 is not None:
            self._check7day_count = None      # ใช้ครั้งเดียวต่อไฟล์
            if self._export_7day_check(file_path, count7):
                return

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

    def _recover_failed_id(self, xml_file):
        """id ติด failed -> ล้าง shared_prefs หมด -> เข้าเกม 1 รอบ (state สะอาด) -> ล้างอีก -> ฉีดใหม่ -> login"""
        try:
            print(f"[{self.device_id}] [RECOVER] failed -> ล้างหมด -> เข้าเกม 1 รอบ -> ล้าง -> ฉีดใหม่ -> login", flush=True)
            self.clear_specific_shared_prefs()          # ล้าง shared_prefs + cache หมด
            self.open_app()                              # เข้าเกม 1 รอบ (สร้าง guest ใหม่ state สะอาด)
            sleep(float(config.get("recover_fresh_wait", 12)))
            self.clear_specific_shared_prefs()           # ล้างอีกรอบ
            # ปิดแอพให้สนิทก่อนฉีด (กันเกมยังรันแล้วเขียนทับไฟล์ที่เพิ่งฉีด)
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"], timeout=15)
            self.adb_shell("su -c 'killall -9 com.linecorp.LGRGS 2>/dev/null || true'", timeout=15)
            for _ in range(10):   # รอจน process ตายจริง (สูงสุด ~10 วิ)
                _pr = self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "pidof", "com.linecorp.LGRGS"], timeout=8)
                if not (_pr.stdout or b"").strip():
                    break
                sleep(1)
            injected = self.inject_file(xml_file)        # ฉีดไฟล์บัญชีใหม่
            if not injected:
                return "failed"
            self.first_loop_done = False
            try:
                return self.main_login(injected)
            except RestartTimeoutError:
                try:
                    self.clear_and_restart()
                except Exception:
                    pass
                return "timeout"
        except Exception as e:
            print(f"[{self.device_id}] [RECOVER] error: {e}", flush=True)
            return "failed"

    def handle_failure(self, file_path):
        # แอปไม่มีบนเครื่องนี้ → ห้ามย้ายไฟล์ไปไหน ปล่อยไว้ในคิวเหมือนเดิม
        if getattr(self, "app_missing", False):
            print(f"[{self.device_id}] ⛔ ไม่มีแอปบนเครื่องนี้ — ไม่ย้ายไฟล์ {os.path.basename(file_path)} ปล่อยไว้ที่เดิม")
            return
        # adb หลุด/offline → ผลที่อ่านได้เชื่อไม่ได้ ห้ามตัดสินว่าล็อกอินไม่ผ่าน
        if not self.device_is_online():
            self._keep_file_in_queue(file_path, "adb offline/หลุดการเชื่อมต่อ")
            return
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


    def handle_random_fail(self, file_path):
        # แอปไม่มีบนเครื่องนี้ → ห้ามย้ายไฟล์ไปไหน ปล่อยไว้ในคิวเหมือนเดิม
        if getattr(self, "app_missing", False):
            print(f"[{self.device_id}] ⛔ ไม่มีแอปบนเครื่องนี้ — ไม่ย้ายไฟล์ {os.path.basename(file_path)} ปล่อยไว้ที่เดิม")
            return
        # adb หลุด/offline → ผลที่อ่านได้เชื่อไม่ได้ ห้ามตัดสินว่าล็อกอินไม่ผ่าน
        if not self.device_is_online():
            self._keep_file_in_queue(file_path, "adb offline/หลุดการเชื่อมต่อ")
            return
        """สุ่มไม่ได้ -> เก็บไว้ที่ random-fail/ ใช้ชื่อไฟล์เดิม

        ชื่อไฟล์คงเดิมทั้งดุ้น (ไม่เติม prefix อะไร) จะได้เอากลับไปใช้ต่อได้เลย
        """
        dst_dir = "random-fail"
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
        base = os.path.basename(file_path)
        dst = os.path.join(dst_dir, base)

        print(f"[{self.device_id}] RANDOM/GACHA FAILED. Pulling file from device and moving to {dst_dir}/...")

        src_remote = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
        temp_remote = f"/data/local/tmp/random_fail_pref_{self.device_id.replace(':','_')}.xml"
        
        try:
            self.adb_shell(f"su -c 'cp {src_remote} {temp_remote}'")
            self.adb_shell(f"su -c 'chmod 666 {temp_remote}'")
            self.adb_run([self.adb_cmd, "-s", self.device_id, "pull", temp_remote, dst])
            self.adb_shell(f"su -c 'rm -f {temp_remote}'")
        except Exception as e:
            print(f"[{self.device_id}] Failed to pull remote file for random-fail: {e}")

        # adb pull คืน exit code ไม่ raise ต่อให้ล้มเหลว เลยต้องเช็คว่าไฟล์โผล่จริงไหม
        # ก่อนจะไปลบต้นทาง ไม่งั้นดึงไม่สำเร็จ = บัญชีหายไปเฉย ๆ ทั้งใบ
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            print(f"[{self.device_id}] Saved random-fail file to {dst}")
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
        else:
            # ดึงจากเครื่องไม่ได้ - ย้ายไฟล์ต้นฉบับไปแทน ดีกว่าปล่อยให้หาย
            print(f"[{self.device_id}] ดึงไฟล์จากเครื่องไม่สำเร็จ - ย้ายไฟล์ต้นฉบับไป {dst_dir}/ แทน")
            try:
                if os.path.exists(file_path):
                    shutil.move(file_path, dst)
            except Exception as e:
                print(f"[{self.device_id}] ย้ายไฟล์ต้นฉบับไม่สำเร็จ: {e} (ไฟล์ยังอยู่ที่เดิม)")

    def handle_kaiby(self, file_path):
        """Handle kaiby error by moving file to kaiby/ folder and clearing app"""
        # แอปไม่มีบนเครื่องนี้ → ห้ามย้ายไฟล์ไปไหน ปล่อยไว้ในคิวเหมือนเดิม
        if getattr(self, "app_missing", False):
            print(f"[{self.device_id}] ⛔ ไม่มีแอปบนเครื่องนี้ — ไม่ย้ายไฟล์ {os.path.basename(file_path)} ปล่อยไว้ที่เดิม")
            return
        # adb หลุด/offline → ผลที่อ่านได้เชื่อไม่ได้ ห้ามตัดสินว่าล็อกอินไม่ผ่าน
        if not self.device_is_online():
            self._keep_file_in_queue(file_path, "adb offline/หลุดการเชื่อมต่อ")
            return
        dst_dir = "kaiby"
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
        base = os.path.basename(file_path)
        dst = os.path.join(dst_dir, base)
        
        print(f"[{self.device_id}] KAIBY detected. Moving file to {dst_dir}/")
        
        # Clear app immediately
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(1)
        
        try:
            if os.path.exists(file_path):
                shutil.move(file_path, dst)
                print(f"[{self.device_id}] ✓ Moved to {dst_dir}: {base}")
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
                cls._template_cache_cls[template_path] = None
                return None
                
            tmpl = cv2.imread(full_path, 0)
            if tmpl is None:
                print(f"[WARN] Failed to read image (integrity check): {full_path}")
            cls._template_cache_cls[template_path] = tmpl
            
        return cls._template_cache_cls[template_path]

    def adb_run(self, args, timeout=10, **kwargs):
        if 'creationflags' not in kwargs and os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        return subprocess.run(args, capture_output=True, timeout=timeout, **kwargs)

    def adb_shell(self, shell_cmd, timeout=10):
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        return subprocess.run(
            [self.adb_cmd, "-s", self.device_id, "shell", shell_cmd],
            capture_output=True, timeout=timeout, **kwargs)

    def device_is_online(self, retries=2):
        """เครื่องนี้ยังต่อ adb อยู่จริงไหม (get-state == device)

        กันเคส adb offline/หลุด แล้วบอทเข้าใจผิดว่า "ล็อกอินไม่ผ่าน"
        จนไฟล์ไหลไป login-failed ทั้งที่ไอดีไม่ได้พัง
        """
        for i in range(max(1, retries)):
            try:
                r = self.adb_run([self.adb_cmd, "-s", self.device_id, "get-state"], timeout=8)
                state = (r.stdout or b"").decode(errors="ignore").strip().lower()
                if state == "device":
                    return True
            except Exception:
                pass
            if i + 1 < retries:
                try:
                    self.adb_run([self.adb_cmd, "-s", self.device_id, "reconnect"], timeout=8)
                except Exception:
                    pass
                time.sleep(1.5)
        return False

    def _keep_file_in_queue(self, file_path, reason):
        """ไม่ย้ายไฟล์ไปไหน ปล่อยคาคิวไว้ให้รอบหน้าหยิบใหม่"""
        print(f"[{self.device_id}] ⛔ {reason} — ไม่ย้ายไฟล์ {os.path.basename(file_path)} ปล่อยไว้ที่เดิม")

    def _decode_raw_screencap(self, raw_data):
        """Decode raw screencap data (ไม่ต้อง encode/decode PNG = เร็วกว่า 50-100x)
        Raw format: 4 bytes width + 4 bytes height + 4 bytes pixel_format + RGBA pixel data
        """
        try:
            if len(raw_data) < 16:
                return False
            # Header is width(4) + height(4) + format(4), and on Android 9+ a
            # 4-byte colorSpace field as well. Pick the offset from the actual
            # payload size instead of assuming - MuMu (Android 12) sends 16, and
            # assuming 12 there shifts the whole image by one pixel.
            w, h, fmt = struct.unpack('<III', raw_data[:12])

            # Validate dimensions (ป้องกัน corrupt data)
            if w <= 0 or h <= 0 or w > 4096 or h > 4096:
                return False

            body = w * h * 4
            if len(raw_data) == 16 + body:
                offset = 16
            elif len(raw_data) == 12 + body:
                offset = 12
            elif len(raw_data) >= 16 + body:
                offset = 16
            elif len(raw_data) >= 12 + body:
                offset = 12
            else:
                return False

            # Create numpy array from raw RGBA data (ข้ามการ encode/decode PNG ทั้งหมด)
            pixel_data = raw_data[offset:offset + body]
            rgba = np.frombuffer(pixel_data, dtype=np.uint8).reshape((h, w, 4))

            # cv2.cvtColor แทน np.dot: np.dot สร้าง float64 กลางทาง (540x960x3 = 12MB
            # ต่อเฟรม) วัดแล้วช้ากว่า 25 เท่า (22ms -> 0.9ms) ผลลัพธ์สีเหมือนกันเป๊ะ
            # ส่วน grayscale ต่างกันไม่เกิน 1 ระดับ (ปัดเศษ, BT.601 ทั้งคู่)
            self._screen_color = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
            self._screen = cv2.cvtColor(self._screen_color, cv2.COLOR_BGR2GRAY)
            self._screen_raw_rgba = None  # ไม่ต้องเก็บแล้ว ประหยัด memory
            self._screen_raw_png = None
            self._screen_width = w
            self._screen_height = h
            return True
        except Exception:
            return False

    def _save_debug_screen(self, reason):
        """เก็บภาพจอล่าสุดไว้ดูว่าไปค้างอยู่หน้าไหน

        ไม่มีภาพก็ไล่สาเหตุไม่ได้เลยว่าเป็นป๊อปอัพตัวใหม่ เน็ตหลุด หรือแอปเด้ง
        เก็บลง debug-timeout/ (อยู่ใน .gitignore ไม่ขึ้น GitHub)
        """
        screen = getattr(self, "_screen_color", None)
        if screen is None:
            return None
        try:
            folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug-timeout")
            os.makedirs(folder, exist_ok=True)
            name = (f"{self.device_id.replace(':', '_')}_"
                    f"{time.strftime('%Y%m%d-%H%M%S')}_{reason}.png")
            path = os.path.join(folder, name)
            cv2.imwrite(path, screen)
            return os.path.join("debug-timeout", name)
        except Exception:
            return None

    def capture_screen(self):
        """Capture screen and load into RAM (optimized: raw screencap = 50-100x เร็วกว่า PNG)"""
        if getattr(self, "last_activity_time", 0) and (time.time() - self.last_activity_time) > 500:
            # ค้างที่จอไหนไม่มีใครรู้ถ้าไม่เก็บภาพไว้ - บันทึกก่อนเด้งออก
            shot = self._save_debug_screen("timeout")
            being = getattr(self, "current_original_filename", None) or "?"
            print(f"[{self.device_id}] TIMEOUT: ไม่ได้กดอะไรเลย 500 วิ (ไฟล์: {being})"
                  + (f" - เก็บภาพจอที่ค้างไว้ที่ {shot}" if shot else " - ไม่มีภาพจอให้เก็บ"))
            self.last_activity_time = time.time()
            raise RestartTimeoutError("500s Timeout")
        try:
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            
            # ใช้ raw screencap (ไม่มี -p = ไม่ encode PNG = เร็วกว่ามาก)
            result = subprocess.run(
                [self.adb_cmd, "-s", self.device_id, "exec-out", "screencap"],
                capture_output=True, timeout=10, **kwargs
            )
            if result.returncode == 0 and len(result.stdout) > 100:
                # ลอง decode raw format ก่อน (เร็วที่สุด)
                if not self._decode_raw_screencap(result.stdout):
                    # Fallback: ลองเป็น PNG (บาง emulator อาจส่ง PNG มาเสมอ)
                    img_array = np.frombuffer(result.stdout, np.uint8)
                    self._screen = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
                    self._screen_color = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    self._screen_raw_png = None
                    self._screen_raw_rgba = None
            else:
                # Final fallback: save to file
                with open(self.filename, "wb") as f:
                    f.write(result.stdout)
                self._screen = cv2.imread(self.filename, 0)
                self._screen_raw_png = None
                self._screen_raw_rgba = None
                self._screen_color = cv2.imread(self.filename, cv2.IMREAD_COLOR)

            # New frame -> any popup-free verdict from the previous frame is stale.
            self._normalize_frame()   # ให้เฟรมเป็น 960x540 เสมอ (template ทุกรูปตัดจากขนาดนี้)
            self._screen_gen += 1
            self._cap_fail = 0
            # === fixnet1/fixnet: เช็คก่อนทุกอย่าง ทุกครั้งที่จับจอ (แบบ bot-tiket) ===
            # ป๊อปอัพเน็ตหลุดบังทุกอย่าง จึงเคลียร์ตรงนี้ก่อนคืนภาพให้ใครใช้ - ครอบคลุม
            # ทุกลูป/ทุกฟังก์ชันในไฟล์อัตโนมัติ เจอก็กด รอให้หาย แล้วจับใหม่ให้ผู้เรียก
            if not getattr(self, "_in_net_check", False):
                self._in_net_check = True
                try:
                    _hit = self._dismiss_net_popup(self._screen)
                    if _hit:
                        self._clear_net_popup_loop(_hit)   # กดซ้ำจนกว่าป๊อปอัพจะหาย แล้วค่อยคืนภาพให้ผู้เรียก
                finally:
                    self._in_net_check = False

            # Popup check every 3rd capture to reduce CPU (background thread also monitors)
            self._capture_count += 1
            if self._capture_count % 3 == 0:
                if not getattr(self, "_in_popup_check", False):
                    self._in_popup_check = True
                    try:
                        self.check_floating_popups()
                    except Exception as e:
                        print(f"[{self.device_id}] Popup check error: {e}")
                    self._in_popup_check = False
                
        except RestartTimeoutError:
            raise
        except Exception as e:
            print(f"[{self.device_id}] Capture error: {e}")
            # นับ screencap ที่ล้มติดกัน - ล้มแล้ว _screen ยังเป็นภาพเก่า บอทจะ 'มองไม่เห็น' ป๊อปอัพ/ปุ่มใด ๆ
            # (เคสจริง: 20 เครื่องแย่ง adb กัน screencap ค้างเกิน 10 วิ) บอกให้ชัดและลอง reconnect เครื่องนั้น
            self._cap_fail = getattr(self, "_cap_fail", 0) + 1
            if self._cap_fail in (3, 10) or self._cap_fail % 30 == 0:
                print(f"[{self.device_id}] [CAPTURE] screencap ล้มเหลวติดกัน {self._cap_fail} ครั้ง - บอทเห็นแต่ภาพเก่า จะหาอะไรไม่เจอทั้งนั้น (adb หรือเครื่องค้าง)")
            if self._cap_fail % 5 == 0:
                try:
                    self.adb_run([self.adb_cmd, "-s", self.device_id, "reconnect"], timeout=10)
                    print(f"[{self.device_id}] [CAPTURE] สั่ง adb reconnect {self.device_id} แล้ว")
                except Exception:
                    pass
            if hasattr(self, "_in_popup_check"):
                self._in_popup_check = False

    def get_screen_color(self):
        """คืน color screen ที่ decode ไว้แล้ว (eager decode ตอน capture)"""
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
        """Check if template exists in already-captured screen.

        If the screen has not been captured yet or the last frame looks stale,
        grab a fresh one first so the login loop does not keep acting on an old
        screenshot that can never match the current UI.
        """
        if self._screen is None:
            try:
                self.capture_screen()
            except Exception:
                return False
        hit = self._find_in_screen(template_path, similarity) is not None
        if hit:
            return True
        # One fresh retry avoids the common stale-frame problem where the bot
        # keeps looking at an old screenshot and never taps the current button.
        try:
            self.capture_screen()
        except Exception:
            return False
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
        self.last_activity_time = time.time()
        target = None
        if isinstance(PSMRL, str):
            candidate = PSMRL
            if not os.path.isabs(candidate):
                candidate = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), candidate))
            if os.path.exists(candidate):
                target = self._find_in_screen(candidate, similarity)
                if target is None:
                    try:
                        self.capture_screen()
                        target = self._find_in_screen(candidate, similarity)
                    except Exception:
                        pass
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
        self.last_activity_time = time.time()
        """Direct tap without image search"""
        self._tap_count += 1   # lets check_floating_popups() tell "nothing fired" apart
        ctrl = self._touch()
        if ctrl is not None and ctrl.tap(int(x), int(y)):
            return
        dx, dy = self._dev_xy(x, y)
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "input", "tap",
                     str(dx), str(dy)])

    def type_text(self, text):
        self.last_activity_time = time.time()
        """Type text via ADB (for search box) - clears it first to avoid double typing"""
        # 1. Clear text (Move to end then send backspaces)
        self.adb_shell("input keyevent 123") # MOVE_END
        for _ in range(3):
            self.adb_shell("input keyevent 67 67 67 67 67 67 67 67 67 67") # 10 backspaces at once

        # 2. Type new text
        escaped = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "input", "text", escaped])
        sleep(0.5) # Wait for UI to process text input

    # รูปไก่บี้ทุกแบบ - เพิ่มตัวใหม่ที่นี่ที่เดียว ทุกจุดที่เช็คใช้ลิสต์นี้ร่วมกัน
    KAIBY_IMAGES = ("img/kaiby.png", "img/kaiby1.png", "img/kaiby2.bmp")

    def find_kaiby(self, similarity=0.95):
        """คืนชื่อรูปไก่บี้ตัวแรกที่เจอบนจอที่จับไว้ (None = ไม่เจอ)

        คืนชื่อไฟล์กลับไปด้วย จะได้ log ได้ว่าเจอตัวไหน โดยไม่ต้องไล่เช็คซ้ำอีกรอบ
        """
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

    # ป๊อปอัพเน็ตหลุดที่ต้องกดปิดให้ได้ ไม่ว่าบอทจะอยู่ลูปไหน
    NET_POPUPS = ("img/fixnet-tiket.png", "img/fixnet1.png", "img/fixnet.png")   # ตัวแรก = รูปจาก bot-tiket
    NET_POPUP_LIMIT = 10   # กดครบเท่านี้แล้วยังไม่หาย = เด้งแอปใหม่ ดีกว่าค้างรอเฉย ๆ

    def _match_score(self, template_path):
        """คะแนน match สูงสุดของรูปบนจอล่าสุด (0-1) - ไว้บอกใน log ว่า 'เกือบเจอ' หรือ 'ไม่เจอเลย'"""
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

    # template ทุกรูปใน img/ ถูกตัดมาจากจอ 960x540 (เหมือน bot-tiket ที่บังคับ "ต้องเป็น 960x540")
    # เครื่องไหนตั้งความละเอียดอื่น ปุ่มบนจอจะใหญ่/เล็กกว่ารูป -> matchTemplate หาไม่เจอทั้งไฟล์
    BASE_W, BASE_H = 960, 540

    def _normalize_frame(self):
        """ย่อ/ขยายเฟรมให้เป็น 960x540 เสมอ แล้วจำอัตราส่วนไว้สเกลจุดกดกลับเป็นพิกัดจริง"""
        self._screen_ts = time.time()   # เวลาที่ได้เฟรมล่าสุด (monitor ใช้ดูว่าเฟรมค้างไหม)
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
            print(f"[{self.device_id}] [SCREEN] จอ {w}x{h} ไม่ใช่ 960x540 -> ย่อภาพให้ตรง template "
                  f"และสเกลจุดกด x{sx:.2f}/x{sy:.2f} ให้อัตโนมัติ")
        self._screen = cv2.resize(scr, (self.BASE_W, self.BASE_H), interpolation=cv2.INTER_AREA)
        if getattr(self, "_screen_color", None) is not None:
            self._screen_color = cv2.resize(self._screen_color, (self.BASE_W, self.BASE_H), interpolation=cv2.INTER_AREA)
        self._tap_scale = (sx, sy)

    def _dev_xy(self, x, y):
        """พิกัดบนภาพ 960x540 -> พิกัดจริงบนเครื่อง (สำหรับ adb input tap/swipe)"""
        sx, sy = getattr(self, "_tap_scale", (1.0, 1.0))
        return int(round(x * sx)), int(round(y * sy))

    def _adb_tap(self, x, y):
        """กดด้วย adb shell input tap ตรง ๆ (ไม่ผ่าน minitouch) - เหมือน bot-tiket

        minitouch คืน True แค่ 'ส่งคำสั่งลง socket ได้' ไม่รู้ว่าสัมผัสถึงจอจริงไหม
        พอ minitouch ค้าง บอทจะคิดว่ากดแล้วทั้งที่ป๊อปอัพยังอยู่ (log: กดปิดให้แล้ว #3 แต่ไม่หาย)
        ป๊อปอัพเน็ตสำคัญเกินกว่าจะเสี่ยง จึงยิง input tap ตรง ๆ เสมอ
        """
        dx, dy = self._dev_xy(x, y)
        try:
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "input", "tap", str(dx), str(dy)], timeout=8)
            return True
        except Exception as e:
            print(f"[{self.device_id}] [NET] adb input tap ไม่สำเร็จ: {e}")
            return False

    # สเกลที่ monitor เบื้องหลังลองไล่ (เผื่อเกมวาด UI ใหญ่/เล็กกว่ารูปที่ตัดไว้ แม้จอจะ 960x540)
    NET_SCALES = (1.0, 1.33, 1.5, 0.75, 1.67, 0.67, 2.0, 0.5)
    # ป๊อปอัพที่ 'รูปตรวจจับ' กับ 'ปุ่มที่ต้องกด' เป็นคนละรูป: เจอตัวซ้าย -> หาแล้วกดตัวขวา
    NET_DETECT_THEN_TAP = (("img/fixnetv2.png", "img/fixnetv2ok.png"),)

    def _best_match(self, screen, path, similarity, scales):
        """คืน (score, cx, cy, scale) ที่ดีที่สุดของรูปบนจอ หรือ None ถ้าต่ำกว่า similarity"""
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

    NET_RETRY_ROUNDS = 25   # กดซ้ำสูงสุดต่อรอบ (ห่างกัน ~1.2 วิ = ราว 30 วิ) ก่อนปล่อยให้รอบถัดไปลองต่อ

    def _clear_net_popup_loop(self, first_hit):
        """กดป๊อปอัพเน็ตซ้ำ ๆ จนกว่าจะหายไปจากจอ (เน็ตสะดุด RETRY ครั้งเดียวมักไม่พอ)

        เรียกหลังจากกดครั้งแรกไปแล้ว: รอ -> จับจอใหม่ -> ยังเห็นอยู่ก็กดอีก วนจนหาย
        หรือครบ NET_RETRY_ROUNDS แล้วปล่อย (monitor เบื้องหลังจะเก็บต่อ / เกิน limit จะเด้งแอป)
        """
        rounds = 1
        while rounds < self.NET_RETRY_ROUNDS:
            sleep(1.2)
            try:
                self._raw_capture()
            except Exception:
                pass
            self._netpopup_last_click = 0          # ให้กดซ้ำได้ทันที ไม่ติด cooldown
            hit = self._dismiss_net_popup(self._screen, scales=(getattr(self, "_net_scale", 1.0),))
            if not hit:
                print(f"[{self.device_id}] [NET] {first_hit} หายแล้วหลังกด {rounds} ครั้ง")
                return True
            rounds += 1
        print(f"[{self.device_id}] [NET] กด {first_hit} ไป {rounds} ครั้งแล้วยังไม่หาย (เน็ตยังไม่กลับมา) - ปล่อยให้รอบถัดไปลองต่อ")
        return False

    def _dismiss_net_popup(self, screen, similarity=0.8, scales=None):
        """หาป๊อปอัพเน็ต (RETRY / network-OK) บนจอที่ให้มาแล้วกดปิด - คืนชื่อรูปที่กด หรือ None

        กดด้วย adb input tap ตรง ๆ เสมอ (ไม่ผ่าน minitouch) เหมือน bot-tiket
        scales=None       -> ใช้สเกลที่เคยเจอ (เริ่ม 1.0) ราคาถูก เรียกได้ทุกครั้งที่จับจอ
        scales=NET_SCALES -> ไล่ทุกสเกล (monitor เบื้องหลังใช้) เจอสเกลไหนจำไว้ให้รอบต่อไป
        """
        if screen is None:
            return None
        if scales is None:
            scales = (getattr(self, "_net_scale", 1.0),)
        hit = None   # (score, path_to_report, cx, cy, scale)
        for path in self.NET_POPUPS:
            b = self._best_match(screen, path, similarity, scales)
            if b and (hit is None or b[0] > hit[0]):
                hit = (b[0], path, b[1], b[2], b[3])
        if hit is None:
            for detect, target in self.NET_DETECT_THEN_TAP:
                d = self._best_match(screen, detect, similarity, scales)
                if not d:
                    continue
                t = self._best_match(screen, target, similarity, (d[3],))
                if t:
                    hit = (t[0], target, t[1], t[2], t[3])
                else:
                    print(f"[{self.device_id}] [NET] เจอ {os.path.basename(detect)} แต่ยังไม่เห็นปุ่ม {os.path.basename(target)} - รอเฟรมถัดไป")
                break
        if hit is None:
            return None
        score, path, cx, cy, sc = hit
        now = time.time()
        if now - getattr(self, "_netpopup_last_click", 0) < 1.0:
            return None          # เพิ่งกดไป รอป๊อปอัพหายก่อน ไม่กดรัว (cooldown 1 วิ)
        self._netpopup_last_click = now
        if sc != getattr(self, "_net_scale", 1.0):
            self._net_scale = sc
            print(f"[{self.device_id}] [NET] ป๊อปอัพเน็ตบนเครื่องนี้สเกล x{sc:.2f} ของรูป - จำไว้ใช้ทุกครั้ง")
        # จงใจไม่ให้การกดนี้นับเป็น activity (เหมือน bot-tiket): ถ้าเน็ตหลุดวนไม่จบ
        # ตัวจับเวลากันค้าง 500 วิ จะได้ยังทำงานและเด้งไปไฟล์ถัดไปเอง
        self._adb_tap(cx, cy)
        print(f"[{self.device_id}] [NET] พบ {os.path.basename(path)} (score {score:.2f}, x{sc:.2f}) -> adb tap ทันที ({cx}, {cy})")
        return os.path.basename(path)

    def _popup_monitor_loop(self):
        """Background thread to monitor fixnetv3.png - reuses main thread's screen to save CPU"""
        while self._running:
            self._log_pos_cache()
            try:
                # thread หลักตาย/ค้างในคำสั่งยาว -> เฟรมไม่ขยับ monitor จับจอเองจะได้ยังเห็นป๊อปอัพ
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
                    # fixnet1/fixnet: กดปิดจากตรงนี้ด้วย เพราะลูปรอส่วนใหญ่ไม่ได้
                    # เรียก check_floating_popups() เอง
                    hit = self._dismiss_net_popup(mon_screen, scales=self.NET_SCALES)   # monitor ไล่ทุกสเกล
                    if hit:
                        self._clear_net_popup_loop(hit)   # กดซ้ำจนหาย
                        self._netpopup_count = getattr(self, "_netpopup_count", 0) + 1
                        print(f"[{self.device_id}] [MONITOR] {hit} เด้ง (#{self._netpopup_count}) - กดปิดให้แล้ว")
                        if self._netpopup_count >= self.NET_POPUP_LIMIT:
                            print(f"[{self.device_id}] [MONITOR] {hit} กดไป {self.NET_POPUP_LIMIT} ครั้งแล้วยังไม่หาย - เด้งแอปใหม่")
                            self._need_restart = True
                            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell",
                                          "am", "force-stop", "com.linecorp.LGRGS"])
                            self._netpopup_count = 0
                    elif getattr(self, "_netpopup_count", 0):
                        self._netpopup_count = 0

                    tmpl = self._get_template("img/fixnetv3.png")
                    if tmpl is not None:
                        res = cv2.matchTemplate(mon_screen, tmpl, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, _ = cv2.minMaxLoc(res)
                        
                        if max_val >= 0.8:
                            self._fixnetv3_count += 1
                            print(f"[{self.device_id}] [MONITOR] fixnetv3.png detected (#{self._fixnetv3_count})! Tapping (472, 361)...")
                            self._adb_tap(472, 361)   # ป๊อปอัพเน็ต: กดผ่าน adb ตรง ๆ เหมือน bot-tiket
                            
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
            time.sleep(3)

    def swipe(self, x1, y1, x2, y2, duration=300):
        self.last_activity_time = time.time()
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
        เจอก็กด วนเช็คซ้ำจนกว่าจะไม่เจอ popup ใดๆ
        ทำงานทุกรอบ capture_screen() คลุมทั้งไฟล์

        เช็คซ้ำบนภาพเดิมไม่ได้อะไรเพิ่ม (matchTemplate ให้ผลเดิมเป๊ะ) — ปกติรอบนึง
        โดนเรียก 2 ครั้ง (ในลูป 1 + ใน check_error_images อีก 1) = สแกนทิ้ง 8 รูป
        เลยจำไว้ว่าเฟรมไหนเช็คจนจบแล้วไม่เจออะไร แล้วข้ามรอบซ้ำของเฟรมนั้น
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
            sleep(2)
            
            # 1. Wait for @check-l1.png
            start_l1 = time.time()
            while time.time() - start_l1 < 60:
                self._raw_capture()
                if self.exists_in_cache("img/check-l1.png", similarity=0.85):
                    print(f"[{self.device_id}] [POPUP] Found check-l1.png")
                    break
                sleep(1)
            
            else:
                _sc = self._match_score("img/check-l1.png")
                _shot = self._save_debug_screen("checkline-miss")
                print(f"[{self.device_id}] [CHECKLINE] รอ check-l1.png จนหมดเวลาแล้วไม่เจอ (คะแนนสูงสุด {_sc:.2f} / ต้องการ 0.85)"
                      + (f" - เก็บภาพไว้ที่ {_shot}" if _shot else ""))
            # 2. Coordinates
            print(f"[{self.device_id}] [POPUP] Clicking coordinates (932, 133), (930, 253), (926, 327)...")
            self.tap(932, 133)
            sleep(5)
            self.tap(930, 253)
            sleep(5)
            self.tap(926, 327)
            sleep(5)
            
            # 3. Wait for check-l4.png
            start_l4 = time.time()
            while time.time() - start_l4 < 60:
                self._raw_capture()
                if self.exists_in_cache("img/check-l4.png", similarity=0.8):
                    print(f"[{self.device_id}] [POPUP] Found and clicking check-l4.png")
                    self.click("img/check-l4.png", similarity=0.8)
                    break
                sleep(1)
                
            else:
                _sc = self._match_score("img/check-l4.png")
                _shot = self._save_debug_screen("checkline-miss")
                print(f"[{self.device_id}] [CHECKLINE] รอ check-l4.png จนหมดเวลาแล้วไม่เจอ (คะแนนสูงสุด {_sc:.2f} / ต้องการ 0.80)"
                      + (f" - เก็บภาพไว้ที่ {_shot}" if _shot else ""))
            # 4. Click check-ok1.png
            print(f"[{self.device_id}] [POPUP] Waiting for check-ok1.png to finish...")
            for _ in range(60):
                self._raw_capture()
                if self.exists_in_cache("img/check-ok1.png", similarity=0.8):
                    self.click("img/check-ok1.png", similarity=0.8)
                    print(f"[{self.device_id}] [POPUP] Checkline sequence complete!")
                    sleep(1)
                    self._raw_capture() # Update cache for caller
                    break
                sleep(1)
            else:
                _sc = self._match_score("img/check-ok1.png")
                _shot = self._save_debug_screen("checkline-miss")
                print(f"[{self.device_id}] [CHECKLINE] รอ check-ok1.png จนหมดเวลาแล้วไม่เจอ (คะแนนสูงสุด {_sc:.2f} / ต้องการ 0.80)"
                      + (f" - เก็บภาพไว้ที่ {_shot}" if _shot else ""))
            return

        # fixnetv2.png: เจอก็กด แล้วรอกด fixnetv2ok.png
        if self.exists_in_cache("img/fixnetv2.png", similarity=0.8):
            print(f"[{self.device_id}] [POPUP] fixnetv2.png detected, clicking...")
            self.click("img/fixnetv2.png", similarity=0.8)
            sleep(2)
            self._raw_capture()
            if self.exists_in_cache("img/fixnetv2ok.png", similarity=0.8):
                self.click("img/fixnetv2ok.png", similarity=0.8)
                sleep(1)
                self._raw_capture() # Update cache for caller
            return

        if self.exists_in_cache("img/fixplay.png"):
            print(f"[{self.device_id}] [POPUP] fixplay.png detected, clicking...")
            self.click("img/fixplay.png")
            sleep(2)
            # After fixplay, FORCE wait and click check-ok1.png
            print(f"[{self.device_id}] [POPUP] Waiting for check-ok1.png after fixplay...")
            for _ in range(120):  # Wait up to 120 seconds
                self._raw_capture()
                if self.exists_in_cache("img/check-ok1.png"):
                    print(f"[{self.device_id}] [POPUP] check-ok1.png found after fixplay, clicking...")
                    self.click("img/check-ok1.png")
                    sleep(1)
                    self._raw_capture() # Update cache for caller
                    break
                sleep(1)

        # fixnet.png: เช็คตลอดเจอก็กดรัวๆ ไม่มีหยุดจนกว่าจะหายไป
        fixnet_clicks = 0
        while self.exists_in_cache("img/fixnet.png", similarity=0.8):
            fixnet_clicks += 1
            print(f"[{self.device_id}] [POPUP] fixnet.png detected (click #{fixnet_clicks}), clicking...")
            self.click("img/fixnet.png", similarity=0.8)
            sleep(1.5)
            self._raw_capture()
            if fixnet_clicks >= 10:
                print(f"[{self.device_id}] [POPUP] fixnet.png clicked 10 times, breaking to avoid infinite loop")
                break

        # fixnet1.png: วนเช็คซ้ำจนกว่าจะไม่เจอ (re-capture ทุกรอบ) - ปรับ similarity เป็น 0.8 เพื่อความชัวร์
        fixnet1_clicks = 0
        while self.exists_in_cache("img/fixnet1.png", similarity=0.8):
            fixnet1_clicks += 1
            print(f"[{self.device_id}] [POPUP] fixnet1.png detected (click #{fixnet1_clicks}), clicking...")
            self.click("img/fixnet1.png", similarity=0.8)
            sleep(1.5)
            self._raw_capture()  # จับภาพใหม่เพื่อเช็คซ้ำ (ไม่วนกลับ popup check)
            if fixnet1_clicks >= 10:
                print(f"[{self.device_id}] [POPUP] fixnet1.png clicked 10 times, breaking to avoid infinite loop")
                break

        # fixnetv3.png: Network error popup - tap (472, 361) to dismiss
        if self.exists_in_cache("img/fixnetv3.png", similarity=0.8):
            self._fixnetv3_count += 1
            print(f"[{self.device_id}] [POPUP] fixnetv3.png detected (#{self._fixnetv3_count}), tapping (472, 361)...")
            self._adb_tap(472, 361)   # ป๊อปอัพเน็ต: กดผ่าน adb ตรง ๆ เหมือน bot-tiket
            sleep(1.5)
            self._raw_capture()
            
            if self._fixnetv3_count >= 8:
                print(f"[{self.device_id}] [POPUP] fixnetv3.png persists after 8 clicks! Force-stopping app...")
                self._need_restart = True
                self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
                self._fixnetv3_count = 0

        # fixface.bmp: จอสแกนหน้า/ยืนยันตัวตน - กด BACK 1 ครั้งถอยออก (ห้ามกดบนจอ)
        if self.exists_in_cache("img/fixface.bmp", similarity=0.8):
            print(f"[{self.device_id}] [POPUP] fixface.bmp detected, pressing BACK once...")
            self.adb_shell("input keyevent 4")
            sleep(1.5)
            self._raw_capture()

        if self.exists_in_cache("img/fixaccep.png"):
            print(f"[{self.device_id}] [POPUP] fixaccep.png detected, clicking...")
            self.click("img/fixaccep.png")
            sleep(1)

        # fixpop.png: เช็คตลอดเจอก็กดรัวๆ เหมือน fixnet (ลอยๆ เจอก็กด)
        fixpop_clicks = 0
        while self.exists_in_cache("img/fixpop.png", similarity=0.8):
            fixpop_clicks += 1
            print(f"[{self.device_id}] [POPUP] fixpop.png detected (click #{fixpop_clicks}), clicking...")
            self.click("img/fixpop.png", similarity=0.8)
            sleep(1.5)
            self._raw_capture()
            if fixpop_clicks >= 10:
                print(f"[{self.device_id}] [POPUP] fixpop.png clicked 10 times, breaking to avoid infinite loop")
                break

        # Mark this frame popup-free ONLY if the pass did nothing at all: no new
        # frame AND no input sent. Every popup branch above taps or clicks, so a
        # tap counter is a reliable "something fired" signal - checking the frame
        # generation alone is not (fixaccep clicks without re-capturing).
        if self._screen_gen == gen_at_entry and self._tap_count == taps_at_entry:
            self._popups_clean_gen = gen_at_entry

    def _raw_capture(self):
        """Capture screen WITHOUT triggering popup checks (ป้องกันวนซ้อน) - ใช้ raw screencap เร็วขึ้น"""
        try:
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                [self.adb_cmd, "-s", self.device_id, "exec-out", "screencap"],
                capture_output=True, timeout=10, **kwargs
            )
            if result.returncode == 0 and len(result.stdout) > 100:
                # ลอง raw format ก่อน (เร็วที่สุด)
                if not self._decode_raw_screencap(result.stdout):
                    # Fallback PNG
                    img_array = np.frombuffer(result.stdout, np.uint8)
                    self._screen = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
                    self._screen_color = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    self._screen_raw_png = None
                    self._screen_raw_rgba = None
            else:
                with open(self.filename, "wb") as f:
                    f.write(result.stdout)
                self._screen = cv2.imread(self.filename, 0)
                self._screen_raw_png = None
                self._screen_raw_rgba = None
                self._screen_color = cv2.imread(self.filename, cv2.IMREAD_COLOR)
            self._normalize_frame()   # ให้เฟรมเป็น 960x540 เสมอ (template ทุกรูปตัดจากขนาดนี้)
            self._screen_gen += 1
            # === fixnet1/fixnet: เช็คก่อนทุกอย่าง ทุกครั้งที่จับจอ (แบบ bot-tiket) ===
            # ป๊อปอัพเน็ตหลุดบังทุกอย่าง จึงเคลียร์ตรงนี้ก่อนคืนภาพให้ใครใช้ - ครอบคลุม
            # ทุกลูป/ทุกฟังก์ชันในไฟล์อัตโนมัติ เจอก็กด รอให้หาย แล้วจับใหม่ให้ผู้เรียก
            if not getattr(self, "_in_net_check", False):
                self._in_net_check = True
                try:
                    _hit = self._dismiss_net_popup(self._screen)
                    if _hit:
                        self._clear_net_popup_loop(_hit)   # กดซ้ำจนกว่าป๊อปอัพจะหาย แล้วค่อยคืนภาพให้ผู้เรียก
                finally:
                    self._in_net_check = False
        except Exception as e:
            print(f"[{self.device_id}] Raw capture error: {e}")

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

        # ===== FLOATING POPUP CHECKS (กดแล้วทำงานต่อ ไม่ return error) =====
        self.check_floating_popups()

        # Same throttle as the popup pass: none of the errors below are transient
        # (they are dialogs that stay up), so scanning for them a few times a second
        # is enough. Returning None just means "nothing wrong right now", which is
        # what the callers already handle every iteration.
        #
        # The app-alive check runs BEFORE this throttle: if the app died, every
        # template scan below is pointless anyway, and delaying the relaunch is
        # the one thing here that actually costs a lot of wall-clock. It has its
        # own PIDOF_INTERVAL throttle so it still is not one adb call per frame.
        if not skip_icon:
            crashed = self._app_is_gone()
            if crashed:
                return "icon"

        now = time.time()
        if self.SCAN_INTERVAL > 0 and (now - self._last_error_scan) < self.SCAN_INTERVAL:
            return None
        self._last_error_scan = now

        # Check for Black/Stuck screen
        # [REMOVED] User requested to only check black screen upon startup.

        # fixcak.png: restart process if found
        if not skip_fixcak:
            fixcak_path = "img/fixcak.png"
            if os.path.exists(fixcak_path) and self.exists_in_cache(fixcak_path):
                return "fixcak"
        
        # stopcheck.png: complete/stop process if found.
        # เดิมวน [0.95, 0.9, 0.85, 0.8] = matchTemplate ภาพเดิม 4 รอบ ได้ผลเท่ากันทุกรอบ
        # ต่างแค่ค่าที่เอาไปเทียบ ซึ่งเทียบเท่ากับเช็คที่ค่าหลวมสุดครั้งเดียวเป๊ะ ๆ
        if self.exists_in_cache("img/stopcheck.png", similarity=0.8):
            return "stopcheck"
        
        # Common login errors
        if self.exists_in_cache("img/fixbuglogin.png"):
            return "fixbug"
            
        if self.exists_in_cache("img/unkhow.png"):
            return "unkhow"
            
        # ตรวจ kaiby เฉพาะเมื่อเปิด kaibyskip (ปิด = ไม่ต้องหลบ, login ปกติ)
        if config.get("kaibyskip", 0) == 1 and self.find_kaiby():
            return "kaiby"

        error_images = ["img/failed1.png", "img/fixalerterror1.png"]
        for err in error_images:
            if self.exists_in_cache(err):
                return "error_img"
                
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
            return []
        
        region = self.ocr_region
        return self.ocr_read_region(region["x"], region["y"], region["w"], region["h"])

    def check_gears_on_screen(self):
        """Check for specific gear names using OCR on target region"""
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

    def handle_post_login_tasks(self):
        """Perform additional tasks after reaching the lobby (Boxes, 7-Day, etc.)"""
        print(f"[{self.device_id}] Starting Post-Login Tasks...")
        # เริ่มไฟล์/รอบใหม่ -> ล้างจำนวน check7day ของรอบก่อน ไม่งั้นไฟล์นี้จะถูกส่งออก
        # ด้วยจำนวนของบัญชีก่อนหน้า (process_7day จะตั้งค่าใหม่ให้เองถ้าได้ทำงาน)
        self._check7day_count = None
        try:
            load_config() # Reload global config (consolidated)
            self.cfg = config 
        except:
            pass
        
        # Helper to check first image with timeout
        def check_task_available(img_name, timeout=8):
            start = time.time()
            while time.time() - start < timeout:
                self.capture_screen()
                if self.exists_in_cache(img_name): return True
                sleep(1)
            return False

        # --- เพิ่มการรอหน้า Lobby ให้ชัวร์ก่อนเริ่ม (รอสูงสุด 20 วินาที) ---
        print(f"[{self.device_id}] Waiting for Lobby icons to load (up to 20s)...")
        lobby_ready = False
        lobby_start = time.time()
        while time.time() - lobby_start < 20:
            self.capture_screen()
            # เช็คว่าเจอไอคอนหลักๆ ในหน้า Lobby หรือยัง (เช่น กล่อง หรือ กาชา หรือ 7วัน)
            if self.exists_in_cache("img/box1.png") or self.exists_in_cache("img/gacha.png") or self.exists_in_cache("img/7day.png"):
                print(f"[{self.device_id}] Lobby ready! Icons detected.")
                lobby_ready = True
                break
            sleep(1.5)
        
        if not lobby_ready:
            print(f"[{self.device_id}] [WARN] Lobby icons not found after 20s wait. Proceeding anyway...")
        # -----------------------------------------------------------

        # 1. Check 7-Day Login
        if self.cfg.get("7day"):
            print(f"[{self.device_id}] Task Check: 7-Day Login...")
            if check_task_available("img/7day.png"):
                self.process_7day()
                sleep(2)
            else:
                print(f"[{self.device_id}] 7-Day icon not found, skipping.")

        # 2. Open Gift Boxes (Round 1)
        box_cfg = self.cfg.get("box_settings", {})
        if box_cfg.get("first_round"):
            print(f"[{self.device_id}] Task Check: Opening Boxes (Round 1)...")
            # Usually box icon is always there or we can just try once
            if check_task_available("img/box1.png"):
                self.process_sequence(self.box_seq)
                sleep(2)
            else:
                print(f"[{self.device_id}] Box icon not found, skipping.")

        # 3. LEONARD Gacha Shop
        if self.cfg.get("shopgacha"):
            print(f"[{self.device_id}] Task Check: Leonard Gacha Shop...")
            if check_task_available("img/gacha.png"):
                res = self.process_shopgacha()
                if res in ["restart", "fixid", "fixunkown", "apple"]: return "restart"
                if res == "random-Fail": return "random-Fail"
                sleep(2)
            else:
                print(f"[{self.device_id}] Gacha icon not found, skipping.")

        # 4. Swap Shop (Auto Trade)
        if self.cfg.get("swap_shop") or self.cfg.get("swap_shopevent") or self.cfg.get("auto_trade", {}).get("enabled"):
            print(f"[{self.device_id}] Task Check: Auto Trade / Swap Shop...")
            # We check for gacha.png as entry point for the new process_swap_shop
            # รอนานขึ้น (15 วิ) เผื่อเพิ่งกลับจาก shopgacha (back→cancel) แล้ว Lobby ยังโหลดไม่เสร็จ
            if check_task_available("img/gacha.png", timeout=15):
                res = self.process_swap_shop()
                if res in ["restart", "fixid", "fixunkown", "apple"]: return "restart"
                if res == "random-Fail": return "random-Fail"
                if res == "backup_complete": return "backup_complete"
                if res == "kaiby": return "kaiby"
                if res == "swap_shopevent":
                    self.process_swap_shopevent()
                
                # Check for individual auto_trade counts from config
                auto_trade_cfg = self.cfg.get("auto_trade", {})
                if auto_trade_cfg.get("enabled"):
                    self.auto_trade()
                
                sleep(2)
            else:
                print(f"[{self.device_id}] Gacha icon (for Swap Shop) not found, skipping.")
            
        # 5. Open Gift Boxes (Round 2)
        if box_cfg.get("second_round"):
            print(f"[{self.device_id}] Task Check: Opening Boxes (Round 2)...")
            if check_task_available("img/box1.png"):
                self.process_sequence(self.box_seq)
                sleep(2)
            else:
                print(f"[{self.device_id}] Box icon (Round 2) not found, skipping.")
            
        # 6. Gear / Ruby Gacha / Check Gear (Placeholders)
        if self.cfg.get("ruby-gear200") or self.cfg.get("random-gear") or self.cfg.get("check-gear"):
            print(f"[{self.device_id}] Task Check: Gear Functions (In development)...")

        # 7. Channel Switching (Placeholder)
        if self.cfg.get("channels_img"):
            print(f"[{self.device_id}] Task Check: Channel Switch to {self.cfg.get('channel', 'ch2')}...")

        if self._check7day_count is not None:
            print(f"[{self.device_id}] [7DAY-CHECK] งานทั้งหมด (รวม box ถ้าเปิดไว้) เสร็จแล้ว - "
                  f"รอส่งไฟล์ออกไป {self.CHECK7DAY_DIR}/ พร้อมจำนวน {self._check7day_count}")

        print(f"[{self.device_id}] Post-Login Tasks Completed.")

    # =========================================================
    # FIND RANGER PROCESS (Unified from ranger-gear.py)
    # =========================================================
    def process_find_ranger(self, current_file):
        """Process find-ranger sequence - Returns results dict"""
        # Check both global and UI config
        is_enabled = self.do_ranger or config.get("find_ranger", 0)
        if not is_enabled:
            return {}
        
        print(f"\n[{self.device_id}] === Starting FIND-RANGER Process ===\n")
        results = {}
        
        # Step 1 & 2: Navigation to search screen
        # เพดาน nav_timeout วิ - เดิมลูปนี้ไม่มีเพดานเลย ถ้า sec1/sec2 ไม่โผล่
        # (เน็ตหลุด/จอค้าง/แอปเด้ง) thread จะวนตรงนี้ตลอดกาลทั้งที่ยังถือ lock ไฟล์อยู่
        nav_timeout = config.get("nav_timeout", 180)
        print(f"[{self.device_id}] Starting persistent navigation (Searching for sec1/sec2, เพดาน {nav_timeout} วิ)...")
        sec1_clicked = False
        nav_deadline = time.time() + nav_timeout
        while True:
            if time.time() > nav_deadline:
                print(f"[{self.device_id}] [NAVI] หา sec1/sec2 ไม่เจอใน {nav_timeout} วิ - ยกเลิก find-ranger รอบนี้")
                return results
            self.capture_screen()
            self.check_floating_popups()
            
            # Check for crash while waiting
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
            except: pass

            if self.exists_in_cache("img/sec2.png"):
                print(f"[{self.device_id}] Reached search screen (sec2), clicking to confirm...")
                self.click("img/sec2.png")
                break
                
            if not sec1_clicked and self.exists_in_cache("img/sec1.png"):
                print(f"[{self.device_id}] Found sec1, clicking once then waiting for sec2...")
                self.click("img/sec1.png")
                sec1_clicked = True
                sleep(3)
            sleep(1.5)
            
        print(f"[{self.device_id}] Reached search screen successfully.")
        
        for i, character in enumerate(self.characters):
            print(f"\n[{self.device_id}] --- Character {i+1}/{len(self.characters)}: {character} ---")
            self.tap(388, 288) # Search box
            sleep(0.3)
            self.type_text(character)
            sleep(0.5)
            
            if not self.wait_and_click_image("sec3.png", timeout=15, similarity=0.95): continue
            if not self.wait_and_click_image("sec4.png", timeout=15, similarity=0.95): continue
            
            sleep(2.0) # Wait for results
            
            current_found = False
            matching_files = self.ranger_files
            for attempt in range(2):
                if attempt > 0: sleep(1.0)
                self.capture_screen()
                self.check_floating_popups()
                for ranger_img in matching_files:
                    if self.exists_in_cache(f"img/{ranger_img}", similarity=0.95):
                        file_base = os.path.splitext(ranger_img.split('/')[-1])[0]
                        found_hero_name = file_base
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
                        current_found = True
                        print(f"[{self.device_id}] Found ranger: {ranger_img} -> hero: {hero_name}, folder: {folder_name}")
                if current_found: break
            
            if not self.wait_and_click_image("sec5.png", timeout=15): pass
            if i < len(self.characters) - 1:
                if not self.wait_and_click_image("sec2.png", timeout=15): break
        
        print(f"[{self.device_id}] Find-Ranger complete.")
        return results

    def run_fixbylv_sequence(self):
        """[FIXBYLV] วนกดตัวที่เจอ (fixbylv1 ถึง fixbylv9) จนกว่าจะไม่เจอ
        กันกดซ้ำ: รูปเดิมกดได้สูงสุด 3 ครั้ง ครบแล้วข้ามรูปนั้นเลย (เช่นปุ่ม SKIP ที่อยู่บนจอตลอด)"""
        print(f"[{self.device_id}] [FIXBYLV] Clicking fixbylv1-9 until gone (max 3 clicks each)...")
        fixbylv_start = time.time()
        fixbylv_click_counts = {}
        while True:
            if time.time() - fixbylv_start > 120:
                print(f"[{self.device_id}] [FIXBYLV] Timeout (120s). Stopping.")
                break
            self.capture_screen()
            if self.check_error_images() == "icon": self.open_app()
            clicked_any = False
            for i in range(1, 10):
                if fixbylv_click_counts.get(i, 0) >= 3:
                    continue  # กดครบ 3 ครั้งแล้ว ข้ามรูปนี้
                fixbylv_img = f"img/fixbylv{i}.bmp"
                # fixbylv1 เป็นข้อความ ใช้ 0.7 (0.8 จับไม่ติด) / ปุ่ม 2-9 คง 0.8 กัน false match
                sim = 0.7 if i == 1 else 0.8
                if self.exists_in_cache(fixbylv_img, similarity=sim):
                    self.click(fixbylv_img, similarity=sim)
                    fixbylv_click_counts[i] = fixbylv_click_counts.get(i, 0) + 1
                    print(f"[{self.device_id}] [FIXBYLV] Clicked fixbylv{i}.bmp ({fixbylv_click_counts[i]}/3)")
                    clicked_any = True
                    sleep(1.2)
                    break
            if not clicked_any:
                print(f"[{self.device_id}] [FIXBYLV] No fixbylv left to click - sequence complete.")
                break

    def backup_ranger_results(self, results, gear_results=None):
        """Save backup based on results"""
        filename = self.current_original_filename or "unknown.xml"
        source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
        safe_dev = self.device_id.replace(":", "_")
        temp_remote = f"/data/local/tmp/backup_{safe_dev}.xml"
        
        try:
            self.adb_shell(f"su -c 'cp {source_path} {temp_remote}'")
            self.adb_shell(f"su -c 'chmod 666 {temp_remote}'")
            
            # Combine all names for folder
            all_names = []
            if results: all_names.extend(results.values())
            if gear_results: all_names.extend(list(gear_results))
            
            if all_names:
                folder_name = "+".join(sorted(set(all_names)))
                backup_dir = os.path.join("backup-id", folder_name)
                if not os.path.exists(backup_dir): os.makedirs(backup_dir)
                dst = os.path.join(backup_dir, filename)
                self.adb_run([self.adb_cmd, '-s', self.device_id, 'pull', temp_remote, dst])
                print(f"[{self.device_id}] Backed up to: {dst}")
            else:
                # ล็อกอินสำเร็จแต่ไม่เจอ hero/gear -> เก็บเข้า login-success (ไม่ใช่ not-found)
                success_dir = "login-success"
                if not os.path.exists(success_dir): os.makedirs(success_dir)
                dst = os.path.join(success_dir, filename)
                self.adb_run([self.adb_cmd, '-s', self.device_id, 'pull', temp_remote, dst])
                print(f"[{self.device_id}] Backed up to login-success: {dst}")
            
            self.adb_shell(f"rm -f {temp_remote}")
        except Exception as e:
            print(f"[{self.device_id}] Backup error: {e}")

    # =========================================================
    # CHECK GEAR PROCESS (Unified from ranger-gear.py)
    # =========================================================
    def process_check_gear(self, current_file, ranger_results=None, skip_findgear1=False):
        """Process check-gear sequence"""
        # Check all possible gear toggles from both configs
        is_enabled = (self.do_gear or 
                      config.get("check-gear", 0) or 
                      config.get("ruby-gear200", 0) or 
                      config.get("random-gear", 0))
        
        if not is_enabled:
            return set()
        
        print(f"\n[{self.device_id}] === Starting CHECK-GEAR Process ===\n")
        if not skip_findgear1:
            if not self.wait_and_click_image("findgear1.png"): return set()
        
        if not self.wait_and_click_image("findgear2.png"): return set()
        if not self.wait_and_click_image("findgear3.png"): return set()
        
        all_found_gears = set()
        # Attempt 1
        if self.wait_and_click_image("checkgear2.png") and self.wait_and_click_image("checkgear3.png", timeout=15):
            all_found_gears.update(self.check_gears_on_screen())
            sleep(1)
            # Tabs
            for tab in ["weapons1.png", "weapons2.png"]:
                self.capture_screen()
                if self.exists_in_cache(f"img/{tab}"):
                    self.click(f"img/{tab}")
                    sleep(2)
                    all_found_gears.update(self.check_gears_on_screen())
        else:
            # Fallback
            for tab in ["weapons1.png", "weapons2.png"]:
                self.capture_screen()
                if self.exists_in_cache(f"img/{tab}"):
                    self.click(f"img/{tab}")
                    sleep(2)
                    all_found_gears.update(self.check_gears_on_screen())
        
        return all_found_gears


    # =========================================================
    # ADB & Interaction
    # =========================================================
    def clear_specific_shared_prefs(self):
        """Soft reset only: keep the game's saved data intact while clearing stale runtime state.

        We intentionally avoid deleting /data/data/com.linecorp.LGRGS/* because that is the
        game's real saved state and user data. We only stop the app, clear proxy settings,
        and reset the transient runtime state needed to stop stale login/session loops.
        """
        app_pkg = "com.linecorp.LGRGS"

        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", app_pkg])
        self.adb_shell(f"su -c 'killall -9 {app_pkg} 2>/dev/null || true'")
        self._clear_proxy_for_device()
        sleep(1)

        # Only clear transient Android/global proxy state. Never delete the game's actual data folder.
        self.adb_shell("settings put global http_proxy ''")
        self.adb_shell("settings put global https_proxy ''")
        self.adb_shell("settings put global proxy_exclusion_list ''")
        print(f"[{self.device_id}] Soft reset only: force-stopped app and cleared proxy/runtime state (no game data deletion)")

    def _remote_size(self, remote_path):
        """ขนาดไฟล์บนเครื่อง (ไบต์) หรือ None ถ้าไม่มีไฟล์/อ่านไม่ได้"""
        try:
            r = self.adb_shell(f"su -c 'stat -c %s {remote_path} 2>/dev/null || wc -c < {remote_path}'", timeout=15)
            txt = (r.stdout or b"").decode("utf-8", "ignore").strip()
            for tok in txt.split():
                if tok.isdigit():
                    return int(tok)
        except Exception:
            pass
        return None

    # ---------------------------------------------------------
    # ส่งไฟล์เข้าเครื่อง (โหมด "คัดลอก-วาง" ไม่ใช้ adb push)
    # ---------------------------------------------------------
    def _remote_md5(self, remote_path):
        """md5 ของไฟล์บนเครื่อง หรือ None ถ้าอ่านไม่ได้"""
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
        """เขียนไฟล์ลงเครื่องด้วย echo base64 ทีละท่อน แล้ว decode บนเครื่อง

        ทำไมไม่ใช้ adb push: push ใช้ sync service ของ adb ซึ่งพอเปิดหลายจอพร้อมกัน
        จะแย่งคิวกันจนค้าง/หลุดกลางทาง = "ไฟล์เข้าไม่ได้เลย" ทั้งที่ไฟล์ไม่ได้พัง
        วิธีนี้ส่งผ่าน adb shell ธรรมดา (ไฟล์ pref แค่ ~1 KB) เหมือนพิมพ์วางเอง
        คืน True ถ้าเขียนครบและ md5 ตรงกับต้นทาง
        """
        b64 = base64.b64encode(data).decode("ascii")
        want_md5 = hashlib.md5(data).hexdigest()
        b64_path = remote_path + ".b64"
        try:
            r = self.adb_shell(f"rm -f {b64_path} {remote_path}", timeout=20)
            for i in range(0, len(b64), chunk):
                part = b64[i:i + chunk]
                # base64 มีแค่ A-Za-z0-9+/= จึงไม่มีอักขระที่ทำให้ quote พัง
                r = self.adb_shell(f"echo -n '{part}' >> {b64_path}", timeout=25)
                if r.returncode != 0:
                    err = ((r.stderr or b"")).decode("utf-8", "ignore").strip()
                    print(f"[{self.device_id}] [PUT] เขียนท่อนที่ {i // chunk + 1} ไม่ผ่าน: {err[:120]}")
                    return False
            # decode บนเครื่อง (toybox base64 ก่อน ไม่มีค่อย busybox)
            dec = self.adb_shell(
                f"base64 -d {b64_path} > {remote_path} 2>/dev/null || "
                f"busybox base64 -d {b64_path} > {remote_path}", timeout=30)
            got = self._remote_md5(remote_path)
            if got != want_md5:
                out = (((dec.stdout or b"") + (dec.stderr or b"")).decode("utf-8", "ignore")).strip()
                print(f"[{self.device_id}] [PUT] decode แล้ว md5 ไม่ตรง ({got} != {want_md5})"
                      + (f" | {out[:120]}" if out else ""))
                return False
            return True
        except Exception as e:
            print(f"[{self.device_id}] [PUT] ส่งแบบ base64 ไม่สำเร็จ: {e}")
            return False
        finally:
            try: self.adb_shell(f"rm -f {b64_path}", timeout=15)
            except Exception: pass

    def _put_remote_file(self, src, remote_path):
        """เอาไฟล์ local ไปวางที่ remote_path ให้ได้ - คืน (ok, ขนาดไฟล์ต้นทาง)

        ลำดับ: base64-over-shell (ปลอดภัยสุด ไม่แย่ง sync service) -> ถ้าไม่ได้ค่อย adb push
        สลับลำดับได้ด้วย config "inject_method": "shell" (บังคับ) / "push" (แบบเดิม) / "auto"
        """
        try:
            with open(src, "rb") as f:
                data = f.read()
        except OSError as e:
            print(f"[{self.device_id}] อ่านไฟล์ต้นทางไม่ได้: {e}")
            return False, 0
        if not data:
            print(f"[{self.device_id}] ไฟล์ต้นทางว่างเปล่า ({src}) - ไม่ inject")
            return False, 0

        method = str(config.get("inject_method", "auto")).lower()
        limit = int(config.get("inject_shell_max_bytes", 262144))
        use_shell = method == "shell" or (method == "auto" and len(data) <= limit)

        with _inject_gate():
            if use_shell and self._write_remote_b64(data, remote_path):
                return True, len(data)

            # สำรอง: adb push แบบเดิม (ไฟล์ใหญ่ หรือเครื่องไม่มี base64)
            try:
                result = self.adb_run([self.adb_cmd, "-s", self.device_id, "push", src, remote_path], timeout=60)
                if result.returncode != 0:
                    err = result.stderr.decode("utf-8", errors="ignore") if result.stderr else "Unknown Error"
                    print(f"[{self.device_id}] [PUT] push ไม่ผ่าน: {err.strip()[:200]}")
                    return False, len(data)
            except Exception as e:
                print(f"[{self.device_id}] [PUT] push error: {e}")
                return False, len(data)
        if self._remote_size(remote_path) != len(data):
            print(f"[{self.device_id}] [PUT] push แล้วขนาดไม่ตรง")
            return False, len(data)
        return True, len(data)

    def inject_file(self, local_xml_path):
        print(f"[{self.device_id}] Injecting file (Robust Mode)...")

        # ขั้นเตรียมทั้งหมดเป็น best-effort: timeout/พัง = เตือนแล้วไปต่อ ไม่ให้ล้มทั้ง inject
        # (เดิมคำสั่ง mount ค้างเกิน 10 วิ -> TimeoutExpired เด้งออกเป็น Critical Error ทั้งที่เป็นแค่ขั้นเตรียม)
        # ปลดล็อก Read-only (ถ้ามี)
        try:
            self.adb_shell("su -c 'mount -o remount,rw / 2>/dev/null || mount -o remount,rw /data 2>/dev/null'", timeout=15)
        except Exception as e:
            print(f"[{self.device_id}] [WARN] remount ข้ามไป (ไม่ critical): {e}")

        try:
            self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"], timeout=15)
        except Exception as e:
            print(f"[{self.device_id}] [WARN] force-stop ข้ามไป (ไม่ critical): {e}")
        sleep(2)

        try:
            self.adb_shell("su -c 'killall -9 com.linecorp.LGRGS 2>/dev/null || true'", timeout=15)
        except Exception as e:
            print(f"[{self.device_id}] [WARN] killall ข้ามไป (ไม่ critical): {e}")
        sleep(1)

        src = os.path.abspath(local_xml_path)

        tmp = f"/data/local/tmp/temp_pref_{self.device_id.replace(':','_')}.xml"
        pkg_dir = "/data/data/com.linecorp.LGRGS"
        final_dir = f"{pkg_dir}/shared_prefs"
        final = f"{final_dir}/_LINE_COCOS_PREF_KEY.xml"

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                # 1) วางไฟล์ลง /data/local/tmp ก่อน (base64 ผ่าน shell, สำรองด้วย adb push)
                ok, local_size = self._put_remote_file(src, tmp)
                if not local_size:
                    return None                    # ไฟล์ต้นทางพัง/ว่าง - ไม่ต้องลองซ้ำ
                if not ok:
                    print(f"[{self.device_id}] Put attempt {attempt}: ส่งไฟล์เข้าเครื่องไม่สำเร็จ - ลองใหม่")
                    sleep(2)
                    continue

                # 2) แอปที่เพิ่งลง/เพิ่งถูกล้างจะยังไม่มีโฟลเดอร์ shared_prefs -> cp ล้มเงียบ ๆ
                #    (เคสนี้แหละที่ทำให้ "ไฟล์ไม่เข้า" ทั้งที่ไฟล์ไม่เสีย) สร้างให้ก่อนพร้อมตั้งเจ้าของ
                self.adb_shell(
                    f"su -c 'mkdir -p {final_dir} && "
                    f"chown $(stat -c %u:%g {pkg_dir} 2>/dev/null || echo 1000:1000) {final_dir} && "
                    f"chmod 771 {final_dir}'", timeout=20)

                # 3) copy เข้าที่จริง + ตั้งสิทธิ์/เจ้าของให้เหมือนไฟล์ที่แอปสร้างเอง
                shell_cmd = (
                    f"su -c '"
                    f"cp {tmp} {final} && "
                    f"chmod 666 {final} && "
                    f"chown $(stat -c %u:%g {final_dir} 2>/dev/null || stat -c %u:%g {pkg_dir} 2>/dev/null || echo 1000:1000) {final}"
                    f"'"
                )
                res = self.adb_shell(shell_cmd, timeout=20)
                out = ((res.stdout or b"") + (res.stderr or b"")).decode("utf-8", "ignore").strip()

                # 4) ยืนยันว่าไฟล์เข้าจริงและครบ - คำสั่งชุดบนคืน rc=0 ได้ทั้งที่ cp ล้มเหลว
                #    (su สำเร็จ ไม่ได้แปลว่า cp สำเร็จ) ของเดิมไม่เช็คเลย เลยรายงานว่า
                #    "Injection successful" ทั้งที่ไฟล์ไม่เข้า แล้วไปล็อกอินเป็นไอดีใหม่
                final_size = self._remote_size(final)
                if final_size != local_size:
                    print(f"[{self.device_id}] Inject attempt {attempt}: ไฟล์ไม่เข้า/ไม่ครบ "
                          f"(บนเครื่อง {final_size} ไบต์, ต้นทาง {local_size} ไบต์)"
                          + (f" | {out[:200]}" if out else ""))
                    sleep(2)
                    continue

                # 5) ขนาดเท่ากันแต่ไฟล์เพี้ยนก็เป็นไปได้ - ตรวจ md5 ซ้ำอีกชั้น (เครื่องไหนไม่มี md5sum = ข้าม)
                remote_md5 = self._remote_md5(final)
                if remote_md5 is not None:
                    try:
                        with open(src, "rb") as _f:
                            local_md5 = hashlib.md5(_f.read()).hexdigest()
                    except OSError:
                        local_md5 = None
                    if local_md5 and remote_md5 != local_md5:
                        print(f"[{self.device_id}] Inject attempt {attempt}: md5 ไม่ตรง "
                              f"({remote_md5} != {local_md5}) - ลองใหม่")
                        sleep(2)
                        continue

                self.adb_shell(f"su -c 'rm -f {tmp}'", timeout=15)
                print(f"[{self.device_id}] Injection successful on attempt {attempt} ({local_size} ไบต์)")
                return local_xml_path

            except Exception as e:
                print(f"[{self.device_id}] Attempt {attempt} error: {e}")
                sleep(2)

        print(f"[{self.device_id}] Injection FAILED after {max_retries} attempts!")
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
            if err == "icon":
                print(f"[{self.device_id}] App closed/crashed! Relaunching with am start...")
                self.open_app()
                return "restart"
            if err == "stopcheck": return "complete"

            if isinstance(item, tuple):
                print(f"[{self.device_id}] Tapping: {item}")
                self.tap(item[0], item[1])
                sleep(3.5) # Increased to 3.5s for coordinate taps (checkboxes)
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
                    sleep(self.loop_delay(1.5))   # was 1.5
                sleep(1.0)
                continue
                
            img_path = f"img/{item}" if isinstance(item, str) and not item.startswith('img') else item
            
            if item == 'icon.png':
                print(f"[{self.device_id}] Opening app via am start (instead of icon click)...")
                self.open_app()
                print(f"[{self.device_id}] App launched, waiting 4s...")
                sleep(4)
                continue

            # === SPECIAL CASE: apple.png ===
            # เจอ apple.png ให้กดด้วย และทำลูป fixid ต่อ
            # เจอ fixid ก่อน -> กด fixok -> refresh -> check -> วนเช็ค fixid ไปเรื่อยๆ
            # ถ้าเจอ fixid ครบ 8 รอบ -> return "failed" ส่งไป login-failed
            # ถ้าไม่เจอ fixid -> ผ่านไปต่อ step ถัดไป
            if item == 'apple.png':
                print(f"[{self.device_id}] Apple step: clicking apple.png (if found) and checking for fixid loop...")
                if not self._auth_take_turn("auth"):
                    sleep(1)
                    continue
                fixid_count = 0
                max_fixid_retries = 8
                apple_start_wait = time.time()
                try:
                    while True:
                        self.capture_screen()
                        
                        # ---- Check floating popups on every iteration ----
                        self.check_floating_popups()
                        # --------------------------------------------------
                        
                        # Check errors first
                        err = self.check_error_images()
                        if err == "fixcak": return "restart"
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
                        
                        # === คลิก apple.png ถ้าเจอ ===
                        if self.exists_in_cache("img/apple.png"):
                            print(f"[{self.device_id}] Found apple.png! Clicking...")
                            self.click("img/apple.png")
                            sleep(2)
                            # ไม่ break นะครับ เพราะต้องเช็ค fixid ต่อ
                        
                        # === fixid1.png → failed ทันที ===
                        if self.exists_in_cache("img/fixid1.png", similarity=0.95):
                            print(f"[{self.device_id}] Found fixid1.png! -> login-failed immediately")
                            return "failed"

                        # === เจอ fixid.png -> เริ่ม loop: fixok -> refresh -> check ===
                        if self.exists_in_cache("img/fixid.png", similarity=0.95):
                            fixid_count += 1
                            print(f"[{self.device_id}] Found fixid.png ({fixid_count}/{max_fixid_retries})")
                            
                            if fixid_count >= max_fixid_retries:
                                print(f"[{self.device_id}] fixid limit reached ({max_fixid_retries} times)! Sending to login-failed...")
                                return "failed"
                            
                            # 1) กด fikcheck
                            print(f"[{self.device_id}] Step 1: clicking fikcheck.png...")
                            for _ in range(10): # Timeout 10s
                                self.capture_screen()
                                if self.exists_in_cache("img/fikcheck.png", similarity=0.8):
                                    self.click("img/fikcheck.png", similarity=0.8)
                                    print(f"[{self.device_id}] Clicked fikcheck.png")
                                    sleep(2)
                                    break
                                sleep(1)
                            
                            # 2) กด refresh
                            print(f"[{self.device_id}] Step 2: clicking refresh.png...")
                            for _ in range(10): # Timeout 10s
                                self.capture_screen()
                                if self.exists_in_cache("img/refresh.png", similarity=0.8):
                                    self.click("img/refresh.png", similarity=0.8)
                                    print(f"[{self.device_id}] Clicked refresh.png")
                                    sleep(3)
                                    break
                                sleep(1)
                            
                            else:
                                # ครบเวลาแล้วไม่เจอ refresh.png - เดิมเงียบไปเฉย ๆ ไล่ไม่ได้ว่ารูปไม่แมตช์หรือจอไม่มา
                                _sc = self._match_score("img/refresh.png")
                                _shot = self._save_debug_screen("refresh-miss")
                                print(f"[{self.device_id}] [REFRESH] ไม่เจอ refresh.png (คะแนนสูงสุด {_sc:.2f} / ต้องการ 0.80)"
                                      + (f" - เก็บภาพไว้ที่ {_shot}" if _shot else ""))
                            # 3) รอ check.png แล้วกด (timeout 60 วิ)
                            print(f"[{self.device_id}] Step 3: waiting for check.png...")
                            check_wait_start = time.time()
                            while time.time() - check_wait_start < 60:
                                self.capture_screen()
                                
                                err2 = self.check_error_images()
                                if err2 == "fixcak": return "restart"
                                if err2 == "fixbug":
                                    self.click("img/fixbuglogin.png")
                                    return "restart"
                                if err2 == "icon":
                                    self.click("img/icon.png")
                                    return "restart"
                                if err2 == "stopcheck": return "complete"
                                
                                if self.exists_in_cache("img/check.png"):
                                    print(f"[{self.device_id}] Found check.png! Clicking...")
                                    self.click("img/check.png")
                                    sleep(2)
                                    # หลังกด check -> รอดู fixid ก่อน 2 วิ
                                    found_fixid_after_check = False
                                    for _ in range(2):
                                        self.capture_screen()
                                        if self.exists_in_cache("img/fixid.png"):
                                            print(f"[{self.device_id}] Found fixid.png right after check! Re-routing...")
                                            found_fixid_after_check = True
                                            break
                                        sleep(1)
                                    
                                    if found_fixid_after_check:
                                        break

                                    if self.exists_in_cache("img/fikcheck.png", similarity=0.8):
                                        print(f"[{self.device_id}] Found fikcheck.png after check! Clicking...")
                                        self.click("img/fikcheck.png", similarity=0.8)
                                        sleep(1)
                                    break
                                
                                sleep(1)
                            
                            # วนกลับไปเช็ค fixid อีกรอบ
                            continue
                        
                        # === ไม่เจอ fixid และถ้าคลิก apple ไปแล้ว หรือรอสักพักแล้วไม่เจอ fixid -> ผ่านไปได้เลย ===
                        # ตรวจสอบเพิ่มเติมว่าเราข้ามขั้นตอน apple ได้เมื่อไหร่
                        if time.time() - apple_start_wait > 30:
                            print(f"[{self.device_id}] Apple step finished (waited 30s or check passed).")
                            break
                        
                        sleep(1)

                finally:
                    self._auth_done("apple-fixid")

                continue  # ไปต่อ item ถัดไปใน sequence

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
                if err == "kaiby":
                    print(f"[{self.device_id}] ⚠️ พบไก่บี้! (เด้งต้อนรับ) ยกเลิกการ Login ทันที...")
                    self.clear_and_restart()
                    sleep(2)
                    return "kaiby"
                
                pos = self._find_in_screen(img_path)
                if pos:
                    print(f"[{self.device_id}] Found {item}, clicking...")
                    self.click(pos)
                    sleep(0.8) # Fast transition for images

                    # === SPECIAL CASE: box1.png logic ===
                    if item == 'box1.png':
                        print(f"[{self.device_id}] [BOX] box1 clicked. Waiting 20s for box2.png or end_box.png...")
                        found_cont = False
                        wait_box_started = time.time()
                        while time.time() - wait_box_started < 20:
                            self.capture_screen()
                            if self.exists_in_cache("img/box2.png"):
                                print(f"[{self.device_id}] [BOX] box2.png detected. Proceeding...")
                                found_cont = True
                                break
                            if self.exists_in_cache("img/end_box.png"):
                                print(f"[{self.device_id}] [BOX] end_box.png detected. Stopping box sequence.")
                                # We don't set found_cont=True because we want to jump to box5
                                break
                            sleep(1)
                        
                        if not found_cont:
                            print(f"[{self.device_id}] [BOX] Box2 not found or end reached. Clicking box5.png and finishing.")
                            # Try to click box5.png to close
                            for _ in range(10):
                                self.capture_screen()
                                if self.exists_in_cache("img/box5.png"):
                                    self.click("img/box5.png")
                                    print(f"[{self.device_id}] [BOX] Clicked box5.png")
                                    break
                                sleep(1)
                            return "success" # Exit this sequence early

                    break
                sleep(self.loop_delay(0.5)) # Fast loop search (was 0.5)

        return "success"

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
            sleep(self.loop_delay(0.2))   # was 0.2

        print(f"[{self.device_id}] Timeout waiting for {img_name} ({timeout}s)")
        return False

    # =========================================================
    # LOGIN SUCCESS BACKUP
    # =========================================================
    def backup_to_success(self, filename, source_path):
        # Disabled moving to login-success folder
        pass

    def clear_and_restart(self):
        """Soft restart for the next file without deleting the game's saved data."""
        self._auth_done("clear_and_restart")
        _auth_cleanup_stale()
        self.clear_specific_shared_prefs()
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(2)

    # =========================================================
    # Mission Sequence (ported from misson.py)
    # =========================================================
    def process_mission_sequence(self):
        """ทำ mission sequence - มีการตรวจสอบ fixnet.png อย่างต่อเนื่อง (ผ่าน check_floating_popups)"""
        MISSION_SIM = 0.95
        try:
            print(f"[{self.device_id}] Starting mission sequence")

            # ขั้นตอนที่ 1: หา misson.png
            mission_found = False
            timeout = 30
            start_time = time.time()

            print(f"[{self.device_id}] Looking for misson.png...")
            while time.time() - start_time < timeout:
                try:
                    self.capture_screen()
                    self.check_floating_popups()  # ⭐ ตรวจสอบ fixnet.png ก่อนเสมอ

                    mission_pos = self._find_in_screen('img/misson.png', MISSION_SIM)
                    if mission_pos:
                        self.tap(mission_pos[0], mission_pos[1])
                        mission_found = True
                        print(f"[{self.device_id}] Found misson.png!")
                        sleep(2)
                        break

                    sleep(1)
                except Exception:
                    continue

            if not mission_found:
                print(f"[{self.device_id}] misson.png not found")
                return False

            # วนลูปทำ mission จนกว่าจะหา misson2.png ไม่เจอ
            mission_cycle = 1
            while True:
                print(f"[{self.device_id}] Mission cycle {mission_cycle}")

                # ขั้นตอนที่ 2: หา misson1.png
                print(f"[{self.device_id}] Looking for misson1.png...")
                misson1_click_count = 0
                misson1_ever_found = False

                while True:
                    try:
                        self.capture_screen()
                        self.check_floating_popups()  # ⭐ ตรวจสอบ fixnet.png ก่อนเสมอ

                        mission1_pos = self._find_in_screen('img/misson1.png', MISSION_SIM)
                        if mission1_pos:
                            self.tap(mission1_pos[0], mission1_pos[1])
                            misson1_click_count += 1
                            misson1_ever_found = True
                            print(f"[{self.device_id}] Clicked misson1.png #{misson1_click_count}")
                            sleep(1)
                        else:
                            if misson1_ever_found:
                                print(f"[{self.device_id}] misson1.png gone after {misson1_click_count} clicks")
                                break
                            sleep(1)
                    except Exception as e:
                        print(f"[{self.device_id}] Error: {str(e)}")
                        continue

                # ขั้นตอนที่ 3: หา missonnew1.png และกดตำแหน่งเดิม 25 รอบ
                missonnew1_found = False
                saved_position = None
                timeout = 5
                start_time = time.time()

                print(f"[{self.device_id}] Looking for missonnew1.png...")
                while time.time() - start_time < timeout:
                    try:
                        self.capture_screen()
                        self.check_floating_popups()  # ⭐ ตรวจสอบ fixnet.png ก่อนเสมอ

                        missonnew1_pos = self._find_in_screen('img/missonnew1.png', MISSION_SIM)
                        if missonnew1_pos:
                            saved_position = (missonnew1_pos[0], missonnew1_pos[1])
                            self.tap(saved_position[0], saved_position[1])
                            missonnew1_found = True
                            print(f"[{self.device_id}] Found missonnew1.png!")
                            sleep(1)
                            break

                        sleep(1)
                    except Exception:
                        continue

                # กดตำแหน่งเดิม 25 รอบ (พร้อมเช็ค fixnet)
                if missonnew1_found and saved_position:
                    print(f"[{self.device_id}] Tapping saved position 25 times...")
                    for i in range(25):
                        # ⭐ เช็ค fixnet.png ทุกๆ 5 ครั้ง
                        if i % 5 == 0:
                            try:
                                self.capture_screen()
                                self.check_floating_popups()
                            except Exception:
                                pass

                        self.tap(saved_position[0], saved_position[1])
                        print(f"[{self.device_id}] Tap {i+1}/25")
                        sleep(0.5)

                # ขั้นตอนที่ 4: หา misson2.png
                mission2_found = False
                timeout = 5
                start_time = time.time()

                print(f"[{self.device_id}] Looking for misson2.png...")
                while time.time() - start_time < timeout:
                    try:
                        self.capture_screen()
                        self.check_floating_popups()  # ⭐ ตรวจสอบ fixnet.png ก่อนเสมอ

                        mission2_pos = self._find_in_screen('img/misson2.png', MISSION_SIM)
                        if mission2_pos:
                            self.tap(mission2_pos[0], mission2_pos[1])
                            mission2_found = True
                            print(f"[{self.device_id}] Found misson2.png!")
                            sleep(2)
                            break

                        sleep(1)
                    except Exception:
                        continue

                if not mission2_found:
                    print(f"[{self.device_id}] misson2.png not found - mission complete!")
                    print(f"[{self.device_id}] Clearing app...")
                    self.clear_and_restart()
                    sleep(2)
                    return True

                # ขั้นตอนที่ 5-6: วนหา misson3.png และ missonnew4.png
                mission3_cycle = 1
                while True:
                    print(f"[{self.device_id}] Mission3 cycle {mission3_cycle}")

                    # ขั้นตอนที่ 5: หา misson3.png
                    mission3_found = False
                    timeout = 15
                    start_time = time.time()

                    print(f"[{self.device_id}] Looking for misson3.png (15s timeout)...")
                    while time.time() - start_time < timeout:
                        try:
                            self.capture_screen()
                            self.check_floating_popups()  # ⭐ ตรวจสอบ fixnet.png ก่อนเสมอ

                            mission3_pos = self._find_in_screen('img/misson3.png', 0.95)
                            if mission3_pos:
                                self.tap(mission3_pos[0], mission3_pos[1])
                                print(f"[{self.device_id}] Found misson3.png!")
                                mission3_found = True
                                sleep(3)
                                break

                            elapsed = time.time() - start_time
                            print(f"[{self.device_id}] Searching... ({elapsed:.1f}s / 15s)")
                            sleep(1)
                        except Exception:
                            continue

                    if not mission3_found:
                        print(f"[{self.device_id}] misson3.png timeout - completing")
                        self.clear_and_restart()
                        sleep(2)
                        return True

                    print(f"[{self.device_id}] Looking for missonnew4.png...")

                    # ขั้นตอนที่ 6: หา missonnew4.png
                    missonnew4_found = False
                    timeout = 5
                    start_time = time.time()

                    while time.time() - start_time < timeout:
                        try:
                            self.capture_screen()
                            self.check_floating_popups()  # ⭐ ตรวจสอบ fixnet.png ก่อนเสมอ

                            missonnew4_pos = self._find_in_screen('img/missonnew4.png', MISSION_SIM)
                            if missonnew4_pos:
                                self.tap(missonnew4_pos[0], missonnew4_pos[1])
                                missonnew4_found = True
                                print(f"[{self.device_id}] Found missonnew4.png!")
                                sleep(2)
                                break

                            sleep(1)
                        except Exception:
                            continue

                    if not missonnew4_found:
                        print(f"[{self.device_id}] missonnew4.png not found")
                    else:
                        print(f"[{self.device_id}] Mission3 cycle completed!")

                    mission3_cycle += 1

                    if mission3_cycle > 20:
                        print(f"[{self.device_id}] Mission3 limit reached")
                        self.clear_and_restart()
                        sleep(2)
                        return True

                mission_cycle += 1

                if mission_cycle > 10:
                    print(f"[{self.device_id}] Mission cycle limit reached")
                    self.clear_and_restart()
                    sleep(2)
                    return True

        except Exception as e:
            print(f"[{self.device_id}] Error: {str(e)}")
            self.clear_and_restart()
            sleep(2)
            return False

    # =========================================================
    # Main Login
    # =========================================================
    # ---------- คิว auth (ดูคำอธิบายที่ _auth_acquire ด้านบนไฟล์) ----------
    def _auth_take_turn(self, what="auth"):
        """ขอคิวก่อนกด refresh/auth - คืน True ถ้าถึงตาเรา (ถือคิวอยู่แล้วก็ True)"""
        if getattr(self, "_auth_slot", None) is not None:
            _auth_touch(self._auth_slot)
            return True

        _auth_cleanup_stale()

        backoff_until = float(getattr(self, "_auth_backoff_until", 0.0) or 0.0)
        if backoff_until > time.time():
            remaining = max(0.0, backoff_until - time.time())
            if time.time() - getattr(self, "_auth_wait_logged", 0) > 15:
                self._auth_wait_logged = time.time()
                print(f"[{self.device_id}] [AUTH-Q] cooldown {what} เหลืออีก {remaining:.0f}s ก่อนลองใหม่...")
            sleep(min(1.0, max(0.5, remaining)))
            return False

        slot = _auth_acquire(self.device_id)
        if slot is None:
            _auth_cleanup_stale()
            slot = _auth_acquire(self.device_id)
        if slot is None:
            blocked_retries = int(getattr(self, "_auth_blocked_retries", 0) or 0) + 1
            self._auth_blocked_retries = blocked_retries
            delay = _auth_backoff_delay(blocked_retries)
            self._auth_backoff_until = time.time() + delay
            if time.time() - getattr(self, "_auth_wait_logged", 0) > 15:
                self._auth_wait_logged = time.time()
                print(f"[{self.device_id}] [AUTH-Q] รอคิว {what} (จออื่นกำลังยืนยันตัวตนอยู่) - cooldown {delay:.0f}s")
            return False

        self._auth_blocked_retries = 0
        self._auth_backoff_until = 0.0
        self._auth_slot = slot
        if slot >= 0:
            print(f"[{self.device_id}] [AUTH-Q] ได้คิวแล้ว (สล็อต {slot}) - เริ่ม {what}")
        return True

    def _auth_done(self, why=""):
        """ปล่อยคิวให้จอถัดไป - เรียกซ้ำได้ ไม่พัง"""
        slot = getattr(self, "_auth_slot", None)
        if slot is None:
            return
        self._auth_slot = None
        self._auth_blocked_retries = 0
        self._auth_backoff_until = 0.0
        _auth_release(slot)
        if slot >= 0:
            print(f"[{self.device_id}] [AUTH-Q] ปล่อยคิวให้จอถัดไป" + (f" ({why})" if why else ""))

    def main_login(self, current_filename):
        print(f"[{self.device_id}] Starting Main Login...")
        self._login_fixid_count = 0  # Reset fixid counter for each new ID
        
        # Clear app
        self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
        sleep(2)
        
        # เปิดแอปด้วย am start (เร็วกว่าและเสถียรกว่าคลิก icon.png)
        self.open_app()
        sleep(3)
        
        # === Black Screen Check หลังเปิดแอพ (8 วิ ถ้ายังดำ/เทา > 75% → clear + restart) ===
        for black_attempt in range(3):  # ลองได้ 3 ครั้ง
            black_start = time.time()
            is_stuck = False
            while time.time() - black_start < 8:
                self.capture_screen()
                if self._screen is not None:
                    try:
                        _, thresh = cv2.threshold(self._screen, 50, 255, cv2.THRESH_BINARY_INV)
                        num_black = cv2.countNonZero(thresh)
                        total = self._screen.shape[0] * self._screen.shape[1]
                        black_ratio = num_black / total
                        if black_ratio < 0.85:
                            # จอสว่างแล้ว (>15% pixels not black)
                            print(f"[{self.device_id}] [BLACK] Screen OK! (app loaded)")
                            is_stuck = False
                            break
                        else:
                            is_stuck = True
                    except:
                        is_stuck = True
                else:
                    is_stuck = True
                sleep(1)
            
            if is_stuck:
                print(f"[{self.device_id}] [BLACK] Dark screen 8s after launch! (attempt {black_attempt+1}/3) Clearing...")
                self.clear_and_restart()
                self.open_app()
                sleep(3)
            else:
                break  # แอพโหลดสำเร็จ ออกจาก loop
            
        loop_count = 0
        status = "unknown"
        event_passed = False  # หลังเจอ event.png แล้วหยุดเช็ค fixok
        login_idle_loops = 0

        
        while True:
            # 0. Check if background monitor triggered a restart
            if self._need_restart:
                print(f"[{self.device_id}] Main loop detected restart request from monitor.")
                self._need_restart = False
                # On restart, we continue the loop which will naturally restart the login flow
                self.clear_and_restart()
                self.open_app()
                sleep(5)
                continue

            loop_count += 1
            if loop_count % 5 == 0:
                print(f"[{self.device_id}] Login loop iteration {loop_count}")

            self.capture_screen()

            # === เช็คว่าเกมยังรันอยู่จริงไหม (เช็คทุกๆ 15 รอบ ป้องกันหน่วง) ===
            if loop_count % 15 == 0:
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

            # ===== FLOATING POPUP CHECKS (กดแล้วทำงานต่อ) =====
            self.check_floating_popups()

            # Hard recovery for the case where the app is alive but the login
            # screen has gone dead (no expected login UI for many cycles).
            if loop_count % 10 == 0:
                login_idle_hits = False
                for p in [
                    "img/fixid.png",
                    "img/fixid1.png",
                    "img/refresh.png",
                    "img/check.png",
                    "img/fixok.png",
                    "img/stoplogin.png",
                    "img/fixnetv3.png",
                    "img/fikcheck.png",
                ]:
                    try:
                        if self.exists_in_cache(p, similarity=0.8):
                            login_idle_hits = True
                            break
                    except Exception:
                        pass
                if login_idle_hits:
                    login_idle_loops = 0
                else:
                    login_idle_loops += 1
                    if login_idle_loops >= 3:
                        print(f"[{self.device_id}] [LOGIN-RECOVER] ไม่มี UI login ที่จับได้ใน 3 รอบ -> รีสตาร์ทแอปและเริ่มใหม่")
                        self.clear_and_restart()
                        self.open_app()
                        sleep(3)
                        login_idle_loops = 0
                        continue

            # fixnetv3.png Check in login loop
            if self.exists_in_cache("img/fixnetv3.png", similarity=0.8):
                print(f"[{self.device_id}] [POPUP] fixnetv3.png detected in login loop! Tapping (472, 361)...")
                self._adb_tap(472, 361)   # ป๊อปอัพเน็ต: กดผ่าน adb ตรง ๆ เหมือน bot-tiket
                sleep(0.5)
                continue

            # === fixokk.png Persistence Check (รอค้างครบ 5 วิ ถึงจะกด) ===
            if self.exists_in_cache("img/fixokk.png", similarity=0.8):
                if not hasattr(self, '_fixokk_start_time') or self._fixokk_start_time is None:
                    self._fixokk_start_time = time.time()
                    print(f"[{self.device_id}] Detected fixokk.png... waiting 5s")
                elif time.time() - self._fixokk_start_time >= 5:
                    print(f"[{self.device_id}] ⚠️ fixokk.png ค้างอยู่ครบ 5 วินาที! ทำการกด...")
                    self.click("img/fixokk.png", similarity=0.8)
                    self._fixokk_start_time = None
                    sleep(2)
            else:
                self._fixokk_start_time = None

            # === alert2.png Persistence Check (รอค้างครบ 8 วิ ให้ clear app แล้วเปิดใหม่) ===
            if self.exists_in_cache("img/alert2.png", similarity=0.8):
                if not hasattr(self, '_alert2_start_time') or self._alert2_start_time is None:
                    self._alert2_start_time = time.time()
                    print(f"[{self.device_id}] Detected alert2.png... waiting 8s to clear app")
                elif time.time() - self._alert2_start_time >= 8:
                    print(f"[{self.device_id}] ⚠️ alert2.png ค้างอยู่ครบ 8 วินาที! เคลียร์แอพและเข้าใหม่...")
                    self.clear_and_restart()
                    self.open_app()
                    self._alert2_start_time = None
                    sleep(3)
                    continue
            else:
                self._alert2_start_time = None


            # === fixid1.png → failed ทันที ===
            if self.exists_in_cache("img/fixid1.png", similarity=0.95):
                print(f"[{self.device_id}] Found fixid1.png! -> login-failed immediately")
                self._login_fixid_count = 0
                return "failed"

            # === fixid.png Check (เช็คทุกรอบ) -> fixok -> refresh -> check ===
            if self.exists_in_cache("img/fixid.png", similarity=0.95):
                if not self._auth_take_turn("auth"):
                    sleep(1)
                    continue
                try:
                    self._login_fixid_count += 1
                    print(f"[{self.device_id}] Found fixid.png ({self._login_fixid_count}/8), fixok -> refresh -> check...")
                    
                    if self._login_fixid_count >= 8:
                        print(f"[{self.device_id}] fixid limit reached (8 times)! Failing...")
                        self._login_fixid_count = 0
                        return "failed"
                    
                    # 1) กด fikcheck
                    print(f"[{self.device_id}] Step 1: waiting for fikcheck.png (10s timeout)...")
                    sleep(1.5) # ให้หน้าจอเสถียรหลัง re-route
                    for _ in range(10): # Timeout 10s
                        self.capture_screen()
                        if self.exists_in_cache("img/fikcheck.png", similarity=0.8):
                            self.click("img/fikcheck.png", similarity=0.8)
                            print(f"[{self.device_id}] Clicked fikcheck.png")
                            sleep(2)
                            break
                        sleep(1)
                    
                    # 2) กด refresh
                    print(f"[{self.device_id}] Step 2: clicking refresh.png (10s timeout)...")
                    for _ in range(10): # Timeout 10s
                        self.capture_screen()
                        if self.exists_in_cache("img/refresh.png", similarity=0.8):
                            self.click("img/refresh.png", similarity=0.8)
                            print(f"[{self.device_id}] Clicked refresh.png")
                            sleep(3)
                            break
                        sleep(1)
                    
                    else:
                        # ครบเวลาแล้วไม่เจอ refresh.png - เดิมเงียบไปเฉย ๆ ไล่ไม่ได้ว่ารูปไม่แมตช์หรือจอไม่มา
                        _sc = self._match_score("img/refresh.png")
                        _shot = self._save_debug_screen("refresh-miss")
                        print(f"[{self.device_id}] [REFRESH] ไม่เจอ refresh.png (คะแนนสูงสุด {_sc:.2f} / ต้องการ 0.80)"
                              + (f" - เก็บภาพไว้ที่ {_shot}" if _shot else ""))
                    # 3) รอ check.png แล้วกด
                    print(f"[{self.device_id}] Step 3: waiting for check.png (60s timeout)...")
                    check_wait_start = time.time()
                    while time.time() - check_wait_start < 60:
                        self.capture_screen()
                        if self.exists_in_cache("img/check.png"):
                            print(f"[{self.device_id}] Found check.png! Clicking...")
                            self.click("img/check.png")
                            sleep(2)
                            # หลังกด check -> รอดู fixid ก่อน 2 วิ
                            found_fixid_after_check = False
                            for _ in range(2):
                                self.capture_screen()
                                if self.exists_in_cache("img/fixid.png"):
                                    print(f"[{self.device_id}] Found fixid.png right after check! Re-routing...")
                                    found_fixid_after_check = True
                                    break
                                sleep(1)
                            
                            if found_fixid_after_check:
                                break

                            if self.exists_in_cache("img/fikcheck.png", similarity=0.8):
                                print(f"[{self.device_id}] Found fikcheck.png after check! Clicking...")
                                self.click("img/fikcheck.png", similarity=0.8)
                                sleep(1)
                            break
                        sleep(1)
                    
                    continue
                finally:
                    self._auth_done("fixid")

            # === เจอ refresh.png (ไม่มี fixid) -> กด refresh -> check ===
            if self.exists_in_cache("img/refresh.png", similarity=0.8):
                if not self._auth_take_turn("refresh"):
                    sleep(1)
                    continue
                try:
                    print(f"[{self.device_id}] Found refresh.png (no fixid), clicking refresh -> check...")
                    self.click("img/refresh.png", similarity=0.8)
                    sleep(3)
                    
                    check_wait_start = time.time()
                    while time.time() - check_wait_start < 60:
                        self.capture_screen()
                        if self.exists_in_cache("img/check.png"):
                            print(f"[{self.device_id}] Found check.png! Clicking...")
                            self.click("img/check.png")
                            sleep(2)
                            # หลังกด check -> รอดู fixid ก่อน 2 วิ
                            found_fixid_after_check = False
                            for _ in range(2):
                                self.capture_screen()
                                if self.exists_in_cache("img/fixid.png"):
                                    print(f"[{self.device_id}] Found fixid.png right after check! Re-routing...")
                                    found_fixid_after_check = True
                                    break
                                sleep(1)
                            
                            if found_fixid_after_check:
                                break
                            
                            # หลังกด check -> หา fixok ด้วย
                            self.capture_screen()
                            if self.exists_in_cache("img/fixok.png"):
                                print(f"[{self.device_id}] Found fixok.png after check! Clicking...")
                                self.click("img/fixok.png")
                                sleep(1)
                            break
                        sleep(1)
                    
                    continue
                finally:
                    self._auth_done("refresh")
            # ====================================================

            # Crash Check: ใช้ open_app แทนคลิก icon.png
            try:
                pid_result = subprocess.run(
                    [self.adb_cmd, "-s", self.device_id, "shell", "pidof", "com.linecorp.LGRGS"],
                    capture_output=True, text=True, timeout=5
                )
                if not pid_result.stdout.strip():
                    print(f"[{self.device_id}] App crashed during login. Relaunching...")
                    self.open_app()
                    sleep(5)
                    loop_count = 0
                    continue
            except:
                pass
            
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
                
            # ไก่บี้ทุกแบบ (เฉพาะเมื่อเปิด kaibyskip)
            if config.get("kaibyskip", 0) == 1:
                kaiby_hit = self.find_kaiby(similarity=0.8)
                if kaiby_hit:
                    print(f"[{self.device_id}] ⚠️ พบ {kaiby_hit}! (ไก่บี้เด้งระหว่าง Login) เคลียร์แอพและส่งเข้าโฟลเดอร์ kaiby...")
                    self.clear_and_restart()
                    sleep(2)
                    return "kaiby"
                
            # *** SUCCESS -> Just Login and Backup ***
            if self.exists_in_cache("img/stoplogin.png", similarity=0.8):
                # [BINGO] ป๊อปอัพบิงโกที่เด้งหลัง login - เคลียร์ก่อนขั้นอื่นทั้งหมด
                # เจอ bingo.bmp -> กด bingo1.bmp -> รัว ESC จนเจอ cancel -> กด cancel
                # แล้วหยุด (จากนั้นไปทำงานตาม config ตามปกติ)
                # หา 3 วิ เผื่อป๊อปอัพยังเด้งไม่ทันตอนเจอ stoplogin พอดี
                bingo_deadline = time.time() + 3
                while time.time() < bingo_deadline:
                    if self.exists_in_cache("img/bingo.bmp", similarity=0.8):
                        print(f"[{self.device_id}] [BINGO] เจอ bingo.bmp - กด bingo1.bmp")
                        if self.exists_in_cache("img/bingo1.bmp", similarity=0.8):
                            self.click("img/bingo1.bmp", similarity=0.8)
                        else:
                            print(f"[{self.device_id}] [BINGO] [WARN] ไม่เจอปุ่ม bingo1.bmp - ข้ามไปรัว ESC เลย")
                        sleep(1.5)

                        # รัว ESC ไปเรื่อย ๆ ไม่มีเพดาน จนกว่าจะเจอ cancel
                        # (ตาข่ายกันค้างถาวรคือ 500s inactivity ใน capture_screen
                        #  ซึ่งจะโยน RestartTimeoutError ให้ลูปใหญ่จัดการเอง)
                        esc_i = 0
                        while True:
                            esc_i += 1
                            self.adb_shell("input keyevent 4")
                            sleep(0.6)
                            self.capture_screen()
                            if self.exists_in_cache("img/cancel.png"):
                                print(f"[{self.device_id}] [BINGO] ESC ครั้งที่ {esc_i} เจอ cancel - กด cancel แล้วหยุด")
                                self.click("img/cancel.png")
                                sleep(1)
                                break
                            if esc_i % 10 == 0:
                                print(f"[{self.device_id}] [BINGO] รัว ESC ไปแล้ว {esc_i} ครั้ง - ยังไม่เจอ cancel รัวต่อ")
                        self.capture_screen()
                        break
                    sleep(0.5)
                    self.capture_screen()

                # [DIST CHECK] แวะเช็คหา fixbylv / distcheck / distskip 5วิ (ตามลำดับนี้)
                print(f"[{self.device_id}] stoplogin found, checking for fixbylv/distcheck/distskip (5s)...")
                found_distcheck = False
                found_distskip_early = False
                found_fixbylv = False
                for _ in range(5):
                    # เช็ค fixbylv ก่อน โดยใช้ fixbylv1.bmp ("for you") เป็นตัวจับสัญญาณ (anchor) เท่านั้น
                    # -> จะเข้าขั้นตอน fixbylv ก็ต่อเมื่อเจอ fixbylv1.bmp เท่านั้น (กัน fixbylv2-9 ปุ่มต่างๆ ทำงานเองโดยผิด)
                    # -> similarity 0.7: fixbylv1 เป็นข้อความ ค่าจริงมักได้ ~0.75 (0.8 สูงไปเลยจับไม่ติด)
                    #    วัดจริงบนจอที่ไม่มีข้อความนี้ได้แค่ ~0.35 จึงมี margin เหลือเยอะ ไม่เสี่ยง false match
                    if self.exists_in_cache("img/fixbylv1.bmp", similarity=0.7):
                        found_fixbylv = True
                        break
                    if self.exists_in_cache("img/distcheck.png"):
                        found_distcheck = True
                        break
                    if self.exists_in_cache("img/distskip.png"):
                        found_distskip_early = True
                        break
                    sleep(1)
                    self.capture_screen()
                
                if found_distskip_early:
                    print(f"[{self.device_id}] [DIST] distskip.png found early! Handling sequence...")
                    self.click("img/distskip.png", similarity=0.8)
                    sleep(1)
                    
                    print(f"[{self.device_id}] [DIST] Waiting for stagespecal.png...")
                    while not self.exists("img/stagespecal.png", similarity=0.8):
                        sleep(1)
                    self.click("img/stagespecal.png", similarity=0.8)
                    sleep(1)

                    print(f"[{self.device_id}] [DIST] Waiting and clicking backdist.png until gone...")
                    # Wait for it to appear first
                    while not self.exists("img/backdist.png", similarity=0.8):
                        sleep(1)
                    # Click until it disappears
                    while True:
                        self.capture_screen()
                        if self.exists_in_cache("img/backdist.png", similarity=0.8):
                            self.click("img/backdist.png", similarity=0.8)
                            sleep(1.2)
                        else:
                            break

                    print(f"[{self.device_id}] [DIST] Waiting and clicking backdist1.png until gone...")
                    # Wait for it to appear first
                    while not self.exists("img/backdist1.png", similarity=0.8):
                        sleep(1)
                    # Click until it disappears
                    while True:
                        self.capture_screen()
                        if self.exists_in_cache("img/backdist1.png", similarity=0.8):
                            self.click("img/backdist1.png", similarity=0.8)
                            sleep(1.2)
                        else:
                            break
                    
                    print(f"[{self.device_id}] [DIST] dist sequence complete.")

                elif found_distcheck:
                    print(f"[{self.device_id}] [DIST] distcheck.png found! Entering full dist sequence...")
                    
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
                            print(f"[{self.device_id}] ⚠️ Found kaibyswap_shop.png before DIST! Returning kaiby...")
                            self.clear_and_restart()
                            return "kaiby"
                    # ====================================================================

                    # 1. รอเจอ dist1.png แล้วกดซ้ำๆ จนกว่าจะเจอ waitdist.png ค่อยหยุด
                    print(f"[{self.device_id}] [DIST] Waiting for dist1.png (click repeatedly until waitdist appears)...")
                    dist_pos = None
                    dist1_start = time.time()
                    while dist_pos is None:
                        if time.time() - dist1_start > 120:
                            print(f"[{self.device_id}] [DIST] Timeout waiting for waitdist.png (120s). Skipping.")
                            break
                        self.capture_screen()
                        if self.check_error_images() == "icon": self.open_app()
                        # เจอ waitdist ค่อยหยุด
                        dist_pos = self._find_in_screen("img/waitdist.png", similarity=0.8)
                        if dist_pos:
                            print(f"[{self.device_id}] [DIST] Found waitdist at {dist_pos} - stop clicking dist1")
                            break
                        # ยังไม่เจอ waitdist -> กด dist1.png ซ้ำๆ
                        if self.exists_in_cache("img/dist1.png", similarity=0.8):
                            self.click("img/dist1.png", similarity=0.8)
                            print(f"[{self.device_id}] [DIST] Clicked dist1.png")
                        sleep(1)

                    # 2. หลังเจอ waitdist -> กด BACK รัวๆ จนเจอ cancel.png แล้วกด cancel -> ไปขั้นตอน distskip เลย
                    if dist_pos:
                        print(f"[{self.device_id}] [DIST] waitdist found - spamming BACK until cancel.png appears...")
                        back_press_count = 0
                        while True:
                            self.adb_shell("input keyevent KEYCODE_BACK")
                            self.adb_shell("input keyevent KEYCODE_BACK")
                            self.adb_shell("input keyevent KEYCODE_BACK")
                            back_press_count += 3
                            print(f"[{self.device_id}] [DIST] Triple Back spam! (Total: {back_press_count})")
                            sleep(0.3)
                            self.capture_screen()
                            if self.exists_in_cache("img/cancel.png", similarity=0.8):
                                print(f"[{self.device_id}] [DIST] cancel.png appeared - clicking cancel, stop back spam")
                                self.click("img/cancel.png", similarity=0.8)
                                sleep(1)
                                break
                            if back_press_count >= 30:
                                print(f"[{self.device_id}] [DIST] BACK spam reached 30 - proceeding to distskip step")
                                break

                    # 2.5 แวะหา fixbylv1.bmp อีก 3 วิ - เจอค่อยเข้าลูป fixbylv / ไม่เจอข้ามไป distskip เลย
                    print(f"[{self.device_id}] [DIST] Checking for fixbylv1.bmp (3s)...")
                    fixbylv_found_mid = False
                    fixbylv_check_start = time.time()
                    while time.time() - fixbylv_check_start < 3:
                        self.capture_screen()
                        if self.exists_in_cache("img/fixbylv1.bmp", similarity=0.7):
                            fixbylv_found_mid = True
                            break
                        sleep(0.5)
                    if fixbylv_found_mid:
                        print(f"[{self.device_id}] [DIST] fixbylv1 found! Running fixbylv sequence...")
                        self.run_fixbylv_sequence()
                    else:
                        print(f"[{self.device_id}] [DIST] fixbylv1 not found in 3s - skipping to distskip step")

                    # 6. distskip -> stagespecal.png -> backdist -> กด ESC
                    print(f"[{self.device_id}] [DIST] Waiting for distskip.png...")
                    skip_start = time.time()
                    while not self.exists("img/distskip.png", similarity=0.8):
                        if time.time() - skip_start > 60: break
                        sleep(1)
                    self.click("img/distskip.png", similarity=0.8)
                    sleep(1)

                    print(f"[{self.device_id}] [DIST] Waiting for stagespecal.png...")
                    spec_start = time.time()
                    while not self.exists("img/stagespecal.png", similarity=0.8):
                        if time.time() - spec_start > 60: break
                        sleep(1)
                    self.click("img/stagespecal.png", similarity=0.8)
                    sleep(1)

                    print(f"[{self.device_id}] [DIST] Waiting and clicking backdist.png until gone...")
                    # Wait for it to appear first
                    backdist_wait_start = time.time()
                    while not self.exists("img/backdist.png", similarity=0.8):
                        if time.time() - backdist_wait_start > 60: break
                        sleep(1)
                    # Click until it disappears
                    while True:
                        self.capture_screen()
                        if self.exists_in_cache("img/backdist.png", similarity=0.8):
                            self.click("img/backdist.png", similarity=0.8)
                            sleep(1.2)
                        else:
                            break

                    print(f"[{self.device_id}] [DIST] Waiting and clicking backdist1.png until gone...")
                    # Wait for it to appear first
                    back1_wait_start = time.time()
                    while not self.exists("img/backdist1.png", similarity=0.8):
                        if time.time() - back1_wait_start > 60: break
                        sleep(1)
                    # Click until it disappears
                    while True:
                        self.capture_screen()
                        if self.exists_in_cache("img/backdist1.png", similarity=0.8):
                            self.click("img/backdist1.png", similarity=0.8)
                            sleep(1.2)
                        else:
                            break
                    
                    print(f"[{self.device_id}] [DIST] dist sequence complete.")

                elif found_fixbylv:
                    # [FIXBYLV] เจอ fixbylv1 -> เข้าลูปกด fixbylv1-9
                    print(f"[{self.device_id}] [FIXBYLV] fixbylv detected!")
                    self.run_fixbylv_sequence()


                print(f"[{self.device_id}] Login successful! (stoplogin detected)")

                # --- Mission Sequence (config misson=1) ---
                if config.get("misson", 0) == 1:
                    print(f"[{self.device_id}] config misson=1: Running mission sequence...")
                    self.update_gui_status("Mission Sequence")
                    self.process_mission_sequence()

                # --- NEW: Perform tasks and scans according to config ---
                ranger_results = {}
                gear_results = set()

                # 1. Post-Login Tasks (Boxes, 7-Day, etc.)
                self.update_gui_status("Post-Login Tasks")
                post_status = self.handle_post_login_tasks()
                if post_status == "restart":
                    print(f"[{self.device_id}] Post-login task requested restart.")
                    continue
                if post_status == "random-Fail":
                    print(f"[{self.device_id}] Post-login task failed (random/gacha).")
                    return "random-Fail"
                if post_status == "backup_complete":
                     print(f"[{self.device_id}] Backup complete during post-login. Success.")
                     return "success"
                if post_status == "kaiby":
                     print(f"[{self.device_id}] Kaiby detected during post-login tasks.")
                     return "kaiby"
                
                # 2. Ranger Scan (Strict check)
                if self.do_ranger == 1 or self.cfg.get("find_ranger") == 1:
                    self.update_gui_status("Ranger Scan")
                    ranger_results = self.process_find_ranger(current_filename)
                
                # 3. Gear Scan (Strict check for any gear toggle)
                if (self.do_gear == 1 or 
                    self.cfg.get("check-gear") == 1 or 
                    self.cfg.get("ruby-gear200") == 1 or 
                    self.cfg.get("random-gear") == 1):
                    self.update_gui_status("Gear Scan")
                    gear_results = self.process_check_gear(current_filename, ranger_results)

                # 4. Backup Results
                self.update_gui_status("Backing up")
                self.backup_ranger_results(ranger_results, gear_results)

                # Update stats for display
                if ranger_results or gear_results:
                    all_found = list(ranger_results.keys()) + list(gear_results)
                    ui_stats.update_hero(f"Found: {len(all_found)} items")
                else:
                    ui_stats.update_hero("Success")
                
                msg = f"[{self.device_id}] 🏆 Success Login & Tasks!"
                if GUI_INSTANCE:
                    GUI_INSTANCE.log("SUCCESS", msg)
                else:
                    print(msg)

                # Clear app and restart for next ID (Wait 8s as requested by user)
                print(f"[{self.device_id}] Success! Waiting 8s before clearing...")
                self.update_gui_status("Cleaning up")
                sleep(8.0)
                self.clear_and_restart()
                return "success"
                
            # ไก่บี้ทุกแบบ (High Priority) — เฉพาะเมื่อเปิด kaibyskip
            if config.get("kaibyskip", 0) == 1:
                reason = self.find_kaiby()
                if reason:
                    print(f"[{self.device_id}] {reason} detected! Stopping login...")
                    return "kaiby"

            # Failed
            if self.exists_in_cache("img/login-failed.png"):
                print(f"[{self.device_id}] Login failed (login-failed.png detected)")
                self._login_fixid_count = 0
                return "failed"
                
            # Error/Reset
            error_found = self.check_error_images()
            
            if error_found:
                print(f"[{self.device_id}] Error image found: {error_found}. Resetting...")
                if error_found in ["fixbug", "unkhow"]:
                    img = "img/fixbuglogin.png" if error_found == "fixbug" else "img/unkhow.png"
                    self.click(img)
                    sleep(2)
                self.adb_run([self.adb_cmd, "-s", self.device_id, "shell", "am", "force-stop", "com.linecorp.LGRGS"])
                sleep(3)
                self.open_app()
                sleep(5)
                loop_count = 0
                continue
            
            # === fixok.png Check (เช็คตลอด แต่หยุดหลัง event) ===
            if not event_passed and self.exists_in_cache("img/fixok.png", similarity=0.8):
                print(f"[{self.device_id}] Found fixok.png! Clicking...")
                self.click("img/fixok.png", similarity=0.8)
                sleep(1)
                continue

            # Event / Popups -> กด event แล้วรัว BACK จนเจอ cancel.png หรือ stoplogin.png (Triple Back Mode)
            if self.exists_in_cache("img/event.png"):
                event_passed = True
                print(f"[{self.device_id}] [EVENT] Detected event.png, clicking and starting Triple Back spam...")
                self.click("img/event.png")
                sleep(1)
                
                back_press_count = 0
                while True:
                    # กด Back ทีเดียว 3 รอบ
                    self.adb_shell("input keyevent KEYCODE_BACK")
                    self.adb_shell("input keyevent KEYCODE_BACK")
                    self.adb_shell("input keyevent KEYCODE_BACK")
                    back_press_count += 3
                    print(f"[{self.device_id}] [EVENT] Triple Back spam! (Total: {back_press_count})")
                    
                    sleep(0.3) # ให้เวลา UI อัปเดตเล็กน้อย
                    self.capture_screen()
                    
                    # ถ้าเจอ cancel.png หรือ stoplogin.png ให้หยุด
                    if self.exists_in_cache("img/cancel.png"):
                        print(f"[{self.device_id}] [EVENT] Found cancel.png, clicking...")
                        self.click("img/cancel.png")
                        sleep(1)
                        break
                    
                    if self.exists_in_cache("img/stoplogin.png"):
                        print(f"[{self.device_id}] [EVENT] Found stoplogin.png, breaking loop.")
                        break
                        
                    if back_press_count >= 30: # ป้องกันลูปค้าง (สูงสุด 30 ครั้ง)
                        print(f"[{self.device_id}] [EVENT] Max BACK presses reached (30), continuing...")
                        break
                
                continue
            
            sleep(2)
            if loop_count > 500:
                print(f"[{self.device_id}] Login timeout after 500 iterations")
                status = "timeout"
                return status
        
        return status

def run_bot_process(device_id, cli_args_dict, ready_q=None):
    """แต่ละ process จะรัน bot สำหรับ 1 device (แยก CPU core กัน)
    ต้องอยู่นอก if __name__ == '__main__' เพื่อให้ Windows multiprocessing (spawn) หาเจอ
    """
    try:
        # Re-initialize everything in the new process
        load_config()
        find_adb_executable()
        
        # Recreate args namespace from dict
        class Args:
            pass
        _args = Args()
        for k, v in cli_args_dict.items():
            setattr(_args, k, v)
        
        bot = RangerGearBot(device_id, _args)
        bot._ready_q = ready_q   # แจ้ง GUI ว่าพร้อมแล้ว -> ปล่อยเครื่องถัดไปทันที
        bot.run()  # Call run() directly (not start() since we're already in a separate process)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[{device_id}] Process crashed: {e}")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()  # จำเป็นสำหรับ Windows multiprocessing

    # เก็บ log ทุกบรรทัดลงไฟล์ .txt แยกราย device ในโฟลเดอร์ logs/
    # (คอนโซล/GUI แสดงผลเหมือนเดิม แค่จดลงไฟล์เพิ่ม)
    sys.stdout = DeviceLogTee(sys.stdout)
    sys.stderr = DeviceLogTee(sys.stderr)

    parser = argparse.ArgumentParser(description="Auto Ranger+Gear Script v3.2.0")
    parser.add_argument("--device", type=str, help="Specific device ID/address to run (e.g. 127.0.0.1:5557)")
    parser.add_argument("--no-start", action="store_true", help="Don't auto-start bot threads in GUI")
    parser.add_argument("--no-reset-adb", action="store_true", help="Don't kill/start ADB server")
    parser.add_argument("--cli", action="store_true", help="Launch in Command Line mode (no GUI)")
    parser.add_argument("--minimized", action="store_true", help="Minimize window")
    parser.add_argument("--skip-warp", action="store_true", help="Skip Cloudflare WARP bootstrap")
    parser.add_argument("--skip-pip", action="store_true", help="Skip Python dependency check/install")
    args = parser.parse_args()

    print_startup_banner()
    if not args.skip_warp:
        ensure_warp_bootstrap()
    if not args.skip_pip:
        ensure_python_requirements()

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
    print(f"[VERSION] build 2026-09-09 net-v2 | ไฟล์แก้ล่าสุด {time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(os.path.abspath(__file__))))}")
    
    load_config()
    
    # ลบไฟล์ .lock ทั้งหมดตอนเริ่มรัน (ทั้ง backup/ และ temp/)
    cleanup_count = 0
    # 1. ลบ lock เก่าที่อาจค้างในโฟลเดอร์คิว (backup/ + input-id/)
    for _qf in queue_folder_names():
        queue_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), _qf)
        if os.path.exists(queue_folder):
            for lf in glob.glob(os.path.join(queue_folder, "*.lock")):
                try: os.remove(lf); cleanup_count += 1
                except: pass
    # 2. ลบ lock ใน temp/ranger-locks/
    temp_lock_dir = os.path.join(tempfile.gettempdir(), "ranger-locks")
    if os.path.exists(temp_lock_dir):
        for lf in glob.glob(os.path.join(temp_lock_dir, "*.lock")):
            try: os.remove(lf); cleanup_count += 1
            except: pass
    if cleanup_count > 0:
        print(f"[CLEANUP] Removed {cleanup_count} stale .lock file(s)")

    # 3. ลบไฟล์ shared_stats.json เพื่อล้างค่าจากรอบเก่า
    shared_stats_file = ui_stats._get_shared_file()
    if os.path.exists(shared_stats_file):
        try:
            os.remove(shared_stats_file)
            print("[CLEANUP] Removed old shared_stats.json")
        except: pass
    
    # รีเซ็ตค่าในหน่วยความจำด้วย
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

    # === ตั้งค่าจอ MuMu ให้ตรง config ก่อนเริ่ม (ความละเอียด/FPS/CPU/RAM/root/renderer/App running) ===
    # ค่าไม่ตรง -> ตั้งผ่าน MuMuManager -> รีเฉพาะจอที่เปิดอยู่ -> รอบูต -> รันโปรแกรมใหม่
    try:
        if ensure_screen_resolution(devices):
            if relaunch_self("ตั้งค่าจอใหม่แล้ว"):
                sys.exit(0)
            # ไม่ได้รันใหม่ -> อ่านรายชื่อเครื่องรอบสอง (พอร์ตอาจเปลี่ยนหลังรีจอ)
            redetect = [d for d in get_connected_devices()
                        if d.startswith("emulator-") or d.startswith("127.0.0.1:")]
            if redetect:
                devices = redetect
                print(f"[INFO] Devices after screen fix ({len(devices)}): {', '.join(devices)}")
    except Exception as e:
        print(f"[SCREEN] ตั้งค่าจอไม่สำเร็จ: {e} - ไปต่อตามปกติ")

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
    files = []
    for _qf in queue_folder_names():
        source_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), _qf)
        if not os.path.exists(source_folder):
            continue
        folder_files = []
        for _root, _dirs, _fs in os.walk(source_folder):
            folder_files += [f for f in _fs if f.lower().endswith(".xml")]
        files += folder_files
        print(f"[FILE] Found {len(folder_files)} files in {source_folder} (รวมโฟลเดอร์ย่อย)")
    if files:
        ui_stats.update(total=len(files))
        print(f"[FILE] คิวรวมทั้งหมด {len(files)} ไฟล์ (backup + input-id)")
    
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

    # CLI Mode - ใช้ Multiprocessing (แยก process เหมือนในรูป Task Manager)
    print(f"\n{Fore.CYAN}Starting bot in CLI Mode (Multiprocessing)...{Style.RESET_ALL}")
    
    import multiprocessing
    # If device is specified, only run that one (useful for multi-window mode)
    targets = [args.device] if args.device else devices
    
    # Convert args to dict for pickling across processes
    args_dict = vars(args)
    
    # ปล่อยพร้อมกัน start_batch ตัว แล้วเติมตัวถัดไปทันทีที่ตัวก่อนหน้าส่งสัญญาณพร้อม
    delay = float(config.get("thread_delay", 5))
    batch = max(1, int(config.get("start_batch", 4)))
    start_timeout = float(config.get("start_timeout", delay * 4))
    print(f"[INFO] Starting {len(targets)} processes (1 per device): ปล่อยพร้อมกัน {batch} ตัว "
          f"แล้วต่อคิวทันทีที่แต่ละตัวพร้อม (เพดาน {start_timeout:.0f}s/ตัว)")
    ready_q = multiprocessing.Queue()
    inflight = 0
    for dev in targets:
        while inflight >= batch:
            try:
                print(f"[INFO] {ready_q.get(timeout=start_timeout)} พร้อมแล้ว")
            except queue.Empty:
                print(f"[WARN] ไม่มีสัญญาณพร้อมใน {start_timeout:.0f}s - ปล่อยตัวถัดไปเลย")
            inflight -= 1
        p = multiprocessing.Process(
            target=run_bot_process, 
            args=(dev, args_dict, ready_q),
            name=f"Bot-{dev}"
        )
        p.daemon = True
        p.start()
        processes.append(p)
        print(f"[INFO] Started process for {dev} (PID: {p.pid})")
        inflight += 1
        
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("\n[STOP] Keyboard Interrupt. Stopping all processes...")
        for p in processes:
            if p.is_alive():
                p.terminate()
    print("\n[DONE] All tasks completed.")
