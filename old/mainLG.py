from ppadb.client import Client as AdbClient
import cv2
import numpy as np
import time
from threading import Thread, Event, Lock
import os
import subprocess
from queue import Queue
import time
import random
import gc  # Garbage collection for memory management
import os
import datetime
import getpass
import glob
from datetime import datetime, timezone
import json
import hashlib
import gc
from pathlib import Path
import re
from typing import Dict, Optional
import platform
import socket
import psutil
import concurrent.futures
from colorama import Fore, Style
import time
import numpy as np
import cv2
from multiprocessing import Process, Manager, Event, Lock, Queue
import multiprocessing
# ลบ: from threading import Thread, Event, Lock
# ลบ: from queue import Queue

# แก้ไข DeviceState เป็น Manager-based
class DeviceState:
    def __init__(self, manager):
        self.lock = manager.Lock()
        self.devices_status = manager.dict()
        self.file_queue = manager.Queue()
        self.processed_files = manager.dict()  # Changed from list to dict
        self.original_filenames = manager.dict()
        self.hero_counts = manager.dict()  # นับจำนวน hero ที่พบ
        self.gear_counts = manager.dict()  # นับจำนวน gear ที่พบ
        self.total_gacha = manager.Value('i', 0)  # รวมจำนวน gacha ทั้งหมด
        self.success_count = manager.Value('i', 0) # นับจำนวนไฟล์ที่ทำงานสำเร็จ
        self.fail_count = manager.Value('i', 0)    # นับจำนวนไฟล์ที่เข้าไม่ได้/ล้มเหลว

# Global device_state for multiprocessing
device_state = None
_device_state_local = None  # Process-local storage

# Helper function to get device_state
def get_device_state():
    global device_state, _device_state_local
    # ถ้าเรียกจาก subprocess ให้ใช้ _device_state_local
    if _device_state_local is not None:
        return _device_state_local
    return device_state

# ============================================
# GUI Helper Functions
# ============================================
def load_collab_config():
    """Load collab configuration from config.json"""
    try:
        if os.path.exists('config.json'):
            with open('config.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading collab config: {e}")
        return {}

def save_collab_config(cfg):
    """Save collab configuration to config.json"""
    try:
        # Load existing config first
        existing = {}
        if os.path.exists('config.json'):
            with open('config.json', 'r', encoding='utf-8') as f:
                existing = json.load(f)
        
        # Merge with new values
        existing.update(cfg)
        
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving collab config: {e}")
        return False

def load_config_json():
    """Load main config.json"""
    try:
        if os.path.exists('config.json'):
            with open('config.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading config.json: {e}")
        return {}

# Device reset signal flags (per device serial)
_manual_reset_flags = {}

def trigger_manual_reset(device_serial):
    """Trigger a manual reset for specific device"""
    global _manual_reset_flags
    _manual_reset_flags[device_serial] = True
    print(f"[GUI] Manual reset triggered for {device_serial}")

def check_manual_reset(device_serial):
    """Check if manual reset was triggered for device"""
    global _manual_reset_flags
    if _manual_reset_flags.get(device_serial, False):
        _manual_reset_flags[device_serial] = False
        return True
    return False

# ============================================
# GUI MODULE - Integrated into mainLG.py
# ============================================
try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox
    import customtkinter as ctk 
    from PIL import Image, ImageTk
    import threading

    GUI_ENABLED = True
    print(f"{Fore.CYAN}[GUI] Modern Control Panel libraries loaded{Style.RESET_ALL}")
    
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")


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
            
            self.add_switch(scroll_frame, "Loop1 (เปิดเกมครั้งแรก)", "loop1")
            self.add_switch(scroll_frame, "7-Day (รับของ 7 วัน)", "7day")
            self.add_switch(scroll_frame, "แลกแต้มเขียว Leonard", "shopgacha")
            self.add_switch(scroll_frame, "สุ่มตัว (Swap Shop)", "swap_shop")
            self.add_switch(scroll_frame, "สุ่มตัว Event", "swap_shopevent")
            self.add_switch(scroll_frame, "ใช้ตั๋วทั้งหมด", "all-tiket")
            self.add_switch(scroll_frame, "ระบบ Link", "link")
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
            
            btn_frame = ctk.CTkFrame(self, fg_color="transparent")
            btn_frame.pack(fill="x", padx=20, pady=10)
            
            ctk.CTkButton(btn_frame, text="💾 บันทึก", command=self.save, fg_color="#2cc985", hover_color="#229f69", width=150).pack(side="left", padx=5)
            ctk.CTkButton(btn_frame, text="❌ ยกเลิก", command=self.destroy, fg_color="#555555", hover_color="#444444", width=100).pack(side="right", padx=5)
        
        def load_config(self):
            try:
                if os.path.exists('config.json'):
                    with open('config.json', 'r', encoding='utf-8') as f:
                        return json.load(f)
            except Exception as e:
                print(f"Error loading config: {e}")
            return {}
        
        def add_switch(self, parent, label, key):
            val = self.cfg.get(key, 0)
            var = ctk.BooleanVar(value=bool(val))
            self.vars[key] = var
            ctk.CTkSwitch(parent, text=label, variable=var).pack(pady=5, padx=20, anchor="w")
            
        def save(self):
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
                
                with open('config.json', 'w', encoding='utf-8') as f:
                    json.dump(self.cfg, f, indent=4, ensure_ascii=False)
                
                messagebox.showinfo("สำเร็จ", "บันทึก Config เรียบร้อย!")
                self.parent.log("✅ Config.json อัพเดทแล้ว")
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
                if os.path.exists('config.json'):
                    with open('config.json', 'r', encoding='utf-8') as f:
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
                text="📌 ตั้งชื่อ Ranger ที่จะบันทึก\n📂 รูปอยู่ที่: img/ranger/gachaheroX.png\n💡 เปลี่ยนรูปได้ง่าย แค่วางไฟล์ใหม่ทับ", 
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
        
        def setup_gear_tab(self):
            tab = self.tabview.tab("⚙️ Gears")
            
            desc_frame = ctk.CTkFrame(tab, fg_color="#2b2b2b", corner_radius=8)
            desc_frame.pack(fill="x", padx=10, pady=(10, 5))
            ctk.CTkLabel(
                desc_frame, 
                text="📌 ตั้งชื่อ Gear ที่จะบันทึก\nเมื่อบอทพบรูป gearimgX.png จะตั้งชื่อไฟล์ตามที่กำหนด", 
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
                
                gear_mapping = {}
                for img, entry in self.gear_entries.items():
                    gear_mapping[img] = entry.get()
                self.cfg["gearname"] = gear_mapping
                
                weapon_mapping = {}
                for img, var in self.weapon_vars.items():
                    weapon_mapping[img] = "true" if var.get() else "false"
                self.cfg["weaponname"] = weapon_mapping
                
                with open('config.json', 'w', encoding='utf-8') as f:
                    json.dump(self.cfg, f, indent=4, ensure_ascii=False)
                
                messagebox.showinfo("สำเร็จ", "บันทึก Ranger & Gear เรียบร้อย!")
                self.parent.log("✅ Ranger & Gear อัพเดทแล้ว")
                self.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"บันทึกไม่สำเร็จ: {e}")


    class ModernBotGUI(ctk.CTk):
        instance = None

        def __init__(self):
            super().__init__()
            ModernBotGUI.instance = self
            self.title("🎮 BOT LINE RANGERS - MINI")
            self.geometry("850x600")
            
            self.bot_running = False

            self.adb_connected = False
            self.connected_devices = []
            self.bot_threads = []
            self.device_monitors = {} 
            self.bot_processes = []
            self.stop_event = None
            
            self.mode_var = ctk.StringVar(value="login")
            self.hack_var = ctk.BooleanVar(value=True)
            
            self.load_initial_config()
            self.setup_ui()
            
            self.log("✅ ระบบพร้อมใช้งาน")
            self.log("กำลังเชื่อมต่อ ADB...")
            self.after(500, self.connect_adb)
            
            self.gift_found_count = 0
            self.hero_counts = {}
            self.gear_counts = {}
            self.update_realtime_stats()

        def load_initial_config(self):
            try:
                if os.path.exists('configgame.json'):
                    with open('configgame.json', 'r') as f:
                        cfg = json.load(f)
                        self.hack_var.set(cfg.get('hack', 1) == 1)
                        self.mode_var.set(cfg.get('mode', 'login'))
                
                if os.path.exists('config.json'):
                    with open('config.json', 'r', encoding='utf-8') as f:
                        self.main_config = json.load(f)
                else:
                    self.main_config = {}
            except Exception as e:
                print(f"Config load error: {e}")
                self.main_config = {}

        def setup_ui(self):
            self.grid_columnconfigure(1, weight=1)
            self.grid_rowconfigure(0, weight=1)

            left_panel = ctk.CTkFrame(self, width=220, corner_radius=0)
            left_panel.grid(row=0, column=0, sticky="nsew")
            left_panel.grid_propagate(False)


            right_panel_container = ctk.CTkFrame(self, fg_color="transparent")
            right_panel_container.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
            
            self.setup_left_panel(left_panel)
            self.setup_monitor_panel(right_panel_container)

        def setup_left_panel(self, parent):
            ctk.CTkLabel(parent, text="🤖 BOT LINE RANGERS", font=ctk.CTkFont(size=16, weight="bold")).pack(padx=10, pady=(20, 5), fill="x")
            ctk.CTkLabel(parent, text="v3.3.0 • GUI Mode", font=ctk.CTkFont(size=10), text_color="gray").pack(padx=10, pady=(0, 10))

            self.btn_start = ctk.CTkButton(
                parent, text="▶ เริ่มบอท",
                font=ctk.CTkFont(size=14, weight="bold"), height=35,
                fg_color="#2cc985", hover_color="#229f69",
                command=self.toggle_bot
            )
            self.btn_start.pack(padx=10, pady=5, fill="x")
            
            self.lbl_status = ctk.CTkLabel(parent, text="กำลังเชื่อมต่อ ADB...", font=ctk.CTkFont(size=11, weight="bold"), text_color="#F2C94C")
            self.lbl_status.pack(pady=5)

            ctk.CTkFrame(parent, height=2, fg_color="gray30").pack(fill="x", padx=10, pady=5)
            
            buttons_frame = ctk.CTkFrame(parent, fg_color="transparent")
            buttons_frame.pack(padx=10, pady=2, fill="x")
            
            ctk.CTkLabel(buttons_frame, text="⚙️ ตั้งค่า", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", pady=(2, 2))
            
            ctk.CTkButton(buttons_frame, text="📝 ตั้งค่า Config", fg_color="#3d5a80", hover_color="#2c4a6e", height=28, command=self.open_main_config, font=ctk.CTkFont(size=11)).pack(fill="x", pady=2)
            ctk.CTkButton(buttons_frame, text="🦸 ตั้งชื่อ Ranger & Gear", fg_color="#555555", hover_color="#444444", height=28, command=self.open_hero_config, font=ctk.CTkFont(size=11)).pack(fill="x", pady=2)
            
            ctk.CTkFrame(parent, height=2, fg_color="gray30").pack(fill="x", padx=10, pady=5)
            
            folders_frame = ctk.CTkFrame(parent, fg_color="transparent")
            folders_frame.pack(padx=10, pady=2, fill="x")
            
            ctk.CTkLabel(folders_frame, text="📁 โฟลเดอร์", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", pady=(2, 2))
            
            # BackupXML button with file count
            self.btn_backupxml = ctk.CTkButton(folders_frame, text="📁 เปิด BackupXML (0 ไฟล์)", fg_color="#3d5a80", hover_color="#2c4a6e", height=28, command=self.open_backup_folder, font=ctk.CTkFont(size=11))
            self.btn_backupxml.pack(fill="x", pady=2)
            ctk.CTkButton(folders_frame, text="📁 เปิด Backup-ID", fg_color="#3d5a80", hover_color="#2c4a6e", height=28, command=self.open_backup_id_folder, font=ctk.CTkFont(size=11)).pack(fill="x", pady=2)
            
            # Ranger images folder button
            self.btn_ranger = ctk.CTkButton(folders_frame, text="🦸 เปิด Ranger Images (0 รูป)", fg_color="#2cc985", hover_color="#229f69", height=28, command=self.open_ranger_folder, font=ctk.CTkFont(size=11))
            self.btn_ranger.pack(fill="x", pady=2)
            
            # Update file counts
            self.update_backupxml_count()
            self.update_ranger_count()

            ctk.CTkFrame(parent, height=2, fg_color="gray30").pack(fill="x", padx=10, pady=5)
            
            config_display = ctk.CTkFrame(parent, fg_color="#1e1e1e", corner_radius=8)
            config_display.pack(padx=10, pady=5, fill="x")
            
            ctk.CTkLabel(config_display, text="📋 สถานะ Config", font=ctk.CTkFont(size=10, weight="bold")).pack(pady=(3, 2))
            
            self.config_status_labels = {}
            features = [("loop1", "Loop1"), ("7day", "7-Day"), ("swap_shop", "สุ่มตัว"), ("random-gear", "สุ่ม Gear"), ("check-gear", "ตรวจ Gear")]
            
            for key, label in features:
                frame = ctk.CTkFrame(config_display, fg_color="transparent")
                frame.pack(fill="x", padx=5)
                ctk.CTkLabel(frame, text=f"{label}:", font=ctk.CTkFont(size=10), width=70, anchor="w").pack(side="left")

                status_lbl = ctk.CTkLabel(frame, text="ปิด", font=ctk.CTkFont(size=10, weight="bold"), text_color="gray")
                status_lbl.pack(side="right", padx=5)
                self.config_status_labels[key] = status_lbl
            
            self.update_config_display()

            ctk.CTkFrame(parent, height=2, fg_color="gray30").pack(fill="x", padx=20, pady=5)
            
            ctk.CTkLabel(parent, text="📜 LOG", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=20, pady=(10, 0))

            self.log_text = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=11), text_color="#cdd6f4")
            self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
            self.log_text.configure(state="disabled")

        def update_config_display(self):
            """อัพเดทสถานะ config - ทำงานใน background thread เพื่อไม่ block UI"""
            def _load_config():
                try:
                    if os.path.exists('config.json'):
                        with open('config.json', 'r', encoding='utf-8') as f:
                            return json.load(f)
                except:
                    pass
                return None
            
            def _update_ui(cfg):
                if cfg is None:
                    return
                try:
                    for key, label in self.config_status_labels.items():
                        val = cfg.get(key, 0)
                        if val:
                            label.configure(text="เปิด", text_color="#2cc985")
                        else:
                            label.configure(text="ปิด", text_color="gray")
                except:
                    pass
            
            # โหลด config ใน background thread
            def _background_load():
                cfg = _load_config()
                if cfg:
                    self.after(0, lambda: _update_ui(cfg))
            
            threading.Thread(target=_background_load, daemon=True).start()
            
            # เพิ่มเป็น 10 วินาที แทน 5 วินาที
            self.after(10000, self.update_config_display)

        def setup_monitor_panel(self, parent):
            # Main stats frame
            stats_frame = ctk.CTkFrame(parent, fg_color="#1e1e1e", corner_radius=10)
            stats_frame.pack(fill="x", pady=(0, 10), ipady=5)
            
            # Title
            ctk.CTkLabel(stats_frame, text="📊 สถิติการทำงาน", font=ctk.CTkFont(size=13, weight="bold"), text_color="#F2C94C").pack(pady=(5, 5))

            # Grid for stats (Processed / Failed)
            grid_frame = ctk.CTkFrame(stats_frame, fg_color="transparent")
            grid_frame.pack(fill="x", padx=10, pady=2)
            grid_frame.columnconfigure(0, weight=1)
            grid_frame.columnconfigure(1, weight=1)

            # Success Card
            self.card_success = ctk.CTkFrame(grid_frame, fg_color="#2b2b2b", corner_radius=8)
            self.card_success.grid(row=0, column=0, padx=5, pady=2, sticky="ew")
            ctk.CTkLabel(self.card_success, text="✅ ทำงานสำเร็จ", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(pady=(5,0))
            self.lbl_success_count = ctk.CTkLabel(self.card_success, text="0", font=ctk.CTkFont(size=20, weight="bold"), text_color="#2cc985")
            self.lbl_success_count.pack(pady=(0,5))

            # Failed Card
            self.card_fail = ctk.CTkFrame(grid_frame, fg_color="#2b2b2b", corner_radius=8)
            self.card_fail.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
            ctk.CTkLabel(self.card_fail, text="❌ เข้าไม่ได้", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(pady=(5,0))
            self.lbl_fail_count = ctk.CTkLabel(self.card_fail, text="0", font=ctk.CTkFont(size=20, weight="bold"), text_color="#ff5555")
            self.lbl_fail_count.pack(pady=(0,5))
            
            # Divider
            ctk.CTkFrame(stats_frame, height=2, fg_color="gray30").pack(fill="x", padx=10, pady=5)
            
            # Ranger Stats
            ctk.CTkLabel(stats_frame, text="🏆 RANGERS & GEARS ที่พบ", font=ctk.CTkFont(size=12, weight="bold"), text_color="#F2C94C").pack(pady=(0, 5))
            
            self.hero_stats_container = ctk.CTkFrame(stats_frame, fg_color="transparent")
            self.hero_stats_container.pack(fill="x", padx=10)

            self.hero_stats_labels = {} 
            self.hero_stats_frames = {}

            for i in range(5):
                self.hero_stats_container.grid_columnconfigure(i, weight=1)

            ctk.CTkLabel(parent, text="📡 DEVICE MONITOR", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 5))


            self.monitor_frame = ctk.CTkScrollableFrame(parent, label_text="อุปกรณ์ที่เชื่อมต่อ")
            self.monitor_frame.pack(fill="both", expand=True)


        def update_realtime_stats(self):
            """อัพเดทสถิติแบบ real-time - ปรับให้ลดการใช้ memory"""
            # ตัวแปรสำหรับนับรอบ garbage collection
            if not hasattr(self, '_gc_counter'):
                self._gc_counter = 0
            
            try:
                ds = get_device_state()
                if ds:
                     # Update Success/Fail
                     if hasattr(self, 'lbl_success_count'):
                         self.lbl_success_count.configure(text=str(ds.success_count.value))
                     if hasattr(self, 'lbl_fail_count'):
                         self.lbl_fail_count.configure(text=str(ds.fail_count.value))

                     # Sync dictionaries - ใช้ try/except ป้องกัน crash
                     try:
                         self.hero_counts = dict(ds.hero_counts)
                         self.gear_counts = dict(ds.gear_counts)
                     except:
                         pass

                if hasattr(self, 'hero_stats_labels'):
                    current_heroes = set(self.hero_stats_labels.keys())
                    found_heroes = set(self.hero_counts.keys())
                    found_gears = set(self.gear_counts.keys())
                    
                    all_found = found_heroes | found_gears
                    new_items = all_found - current_heroes
                    
                    for item in new_items:
                        self.add_hero_stat_widget(item)
                        
                    for item, label in self.hero_stats_labels.items():
                        count = self.hero_counts.get(item, 0) or self.gear_counts.get(item, 0)
                        label.configure(text=str(count))
                        
            except Exception as e:
                pass
            
            # Garbage collection ทุก 30 รอบ (30 วินาที) เพื่อป้องกัน memory leak
            self._gc_counter += 1
            if self._gc_counter >= 30:
                self._gc_counter = 0
                gc.collect()
            
            # เพิ่มเป็น 2 วินาที แทน 1 วินาที เพื่อลด CPU usage
            self.after(2000, self.update_realtime_stats)


        def add_hero_stat_widget(self, hero_name):
            index = len(self.hero_stats_labels)
            cols = 5
            row = index // cols
            col = index % cols
            
            frame = ctk.CTkFrame(self.hero_stats_container, fg_color="#2b2b2b")
            frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            
            ctk.CTkLabel(frame, text=hero_name, font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack()
            lbl_count = ctk.CTkLabel(frame, text="0", font=ctk.CTkFont(size=18, weight="bold"), text_color="#2cc985")
            lbl_count.pack()
            
            self.hero_stats_labels[hero_name] = lbl_count
            self.hero_stats_frames[hero_name] = frame

        def connect_adb(self):
            self.log("🔌 กำลังเชื่อมต่อ ADB...")
            threading.Thread(target=self._connect_thread, daemon=True).start()

        def _connect_thread(self):
            try:
                if not check_adb_available():
                    self.after(0, lambda: self.log("❌ ไม่พบ ADB"))
                    return
                adb, devices = connect_to_mumu()
                if devices:
                    dev_list = devices if isinstance(devices, list) else [devices]
                    self.connected_devices = dev_list
                    self.adb_connected = True
                    self.after(0, self._on_connect_success)
                else:
                    self.after(0, lambda: self.log("❌ ไม่พบอุปกรณ์"))
            except Exception as e:
                self.after(0, lambda: self.log(f"❌ Error: {e}"))

        def _on_connect_success(self):
            count = len(self.connected_devices)
            self.lbl_status.configure(text=f"● ออนไลน์ ({count} อุปกรณ์)", text_color="#2cc985")
            self.log(f"✅ เชื่อมต่อ {count} อุปกรณ์")
            
            for widget in self.monitor_frame.winfo_children():
                widget.destroy()
            self.device_monitors.clear()
            
            for i, dev in enumerate(self.connected_devices):
                monitor = DeviceMonitorWidget(self.monitor_frame, dev.serial, i+1)
                monitor.pack(fill="x", pady=5, padx=5)
                self.device_monitors[dev.serial] = monitor

        def toggle_bot(self):
            if not self.bot_running:
                if not self.adb_connected:
                    messagebox.showerror("Error", "กรุณาเชื่อมต่อ ADB ก่อน!")
                    return
                
                self.save_game_config()
                
                self.bot_running = True
                self.btn_start.configure(text="⏹ หยุดบอท (ปิดโปรแกรม)", fg_color="#ff5555", hover_color="#cc4444")
                self.log("▶ เริ่มบอท...")
                
                threading.Thread(target=self._start_bot_processes, daemon=True).start()
            else:
                if messagebox.askyesno("Exit", "ต้องการหยุดบอทและปิดโปรแกรมใช่หรือไม่?"):
                    self.bot_running = False
                    self.log("🛑 กำลังปิดโปรแกรม...")
                    if self.stop_event:
                        self.stop_event.set()
                    
                    # Kill adb server maybe? No, just exit.
                    self.after(500, self.destroy)
                    try:
                        import sys
                        sys.exit(0)
                    except:
                        pass


        def _start_bot_processes(self):
            try:
                manager = Manager()
                manager_dict = manager.dict()
                self.stop_event = manager.Event()
                
                # Create and expose global device state
                global device_state
                ds = DeviceState(manager)
                device_state = ds
                
                self.bot_processes = []
                
                for i, dev in enumerate(self.connected_devices):
                    device_serial = dev.serial
                    self.after(0, lambda s=device_serial: self.log(f"🚀 เริ่ม process: {s}"))
                    
                    main_process = Process(
                        target=process_single_device,
                        args=(device_serial, manager_dict, ds),
                        name=f"MainProcess-{device_serial}"
                    )
                    main_process.daemon = True
                    main_process.start()
                    self.bot_processes.append(main_process)
                    
                    network_process = Process(
                        target=check_fixnet_worker,
                        args=(device_serial, self.stop_event),
                        name=f"NetworkProcess-{device_serial}"
                    )
                    network_process.daemon = True
                    network_process.start()
                    self.bot_processes.append(network_process)
                
                self.after(0, lambda: self.log(f"✅ เริ่ม {len(self.connected_devices)} process"))
                
                while self.bot_running:
                    time.sleep(1)
                
            except Exception as e:
                self.after(0, lambda: self.log(f"❌ Error: {e}"))
                import traceback
                traceback.print_exc()

        def save_game_config(self):
            try:
                existing_cfg = {}
                if os.path.exists('configgame.json'):
                     try:
                         with open('configgame.json', 'r') as f:
                             existing_cfg = json.load(f)
                     except: pass

                cfg = {
                    'hack': 1 if self.hack_var.get() else 0,
                    'mode': self.mode_var.get(),
                    'stage': existing_cfg.get('stage', "1"),
                    'gear': existing_cfg.get('gear', "2"),
                    'ruby': existing_cfg.get('ruby', "40")
                }
                
                with open('configgame.json', 'w') as f:
                    json.dump(cfg, f, indent=4)
                self.log(f"💾 บันทึก Config")
            except Exception as e:
                self.log(f"❌ Config Error: {e}")

        def log(self, msg):
            timestamp = datetime.now().strftime("%H:%M:%S")
            try:
                self.log_text.configure(state="normal")
                self.log_text.insert("end", f"[{timestamp}] {msg}\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
            except:
                pass

        def update_device(self, serial, **kwargs):
            if serial in self.device_monitors:
                self.device_monitors[serial].update_state(**kwargs)

        def open_main_config(self):
            MainConfigWindow(self)

        def open_hero_config(self):
            HeroConfigWindow(self)

        def open_backup_folder(self):
            backup_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup", "backupxml")
            if os.path.exists(backup_path):
                subprocess.Popen(f'explorer "{backup_path}"')
                self.log(f"📁 เปิด: backup/backupxml")
            else:
                messagebox.showerror("Error", f"ไม่พบโฟลเดอร์: {backup_path}")

        def open_backup_id_folder(self):
            backup_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup-id")
            if os.path.exists(backup_path):
                subprocess.Popen(f'explorer "{backup_path}"')
                self.log(f"📁 เปิด: backup-id")
            else:
                messagebox.showerror("Error", f"ไม่พบโฟลเดอร์: {backup_path}")

        def update_backupxml_count(self):
            """Update file count in backupxml folder - ทำงานใน background thread"""
            def _count_files():
                try:
                    backup_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup", "backupxml")
                    if os.path.exists(backup_path):
                        file_count = len([f for f in os.listdir(backup_path) if os.path.isfile(os.path.join(backup_path, f))])
                        self.after(0, lambda: self.btn_backupxml.configure(text=f"📁 เปิด BackupXML ({file_count} ไฟล์)"))
                    else:
                        self.after(0, lambda: self.btn_backupxml.configure(text="📁 เปิด BackupXML (ไม่พบโฟลเดอร์)"))
                except:
                    pass
            
            threading.Thread(target=_count_files, daemon=True).start()
            
            # เพิ่มเป็น 15 วินาที แทน 5 วินาที
            self.after(15000, self.update_backupxml_count)

        def open_ranger_folder(self):
            """Open img/ranger folder for easy image management"""
            ranger_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img", "ranger")
            if os.path.exists(ranger_path):
                subprocess.Popen(f'explorer "{ranger_path}"')
                self.log(f"🦸 เปิด: img/ranger")
            else:
                # Create folder if not exists
                os.makedirs(ranger_path, exist_ok=True)
                subprocess.Popen(f'explorer "{ranger_path}"')
                self.log(f"🦸 สร้างและเปิด: img/ranger")

        def update_ranger_count(self):
            """Update image count in ranger folder - ทำงานใน background thread"""
            def _count_images():
                try:
                    ranger_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img", "ranger")
                    if os.path.exists(ranger_path):
                        img_count = len([f for f in os.listdir(ranger_path) if f.endswith(('.png', '.jpg', '.jpeg'))])
                        self.after(0, lambda: self.btn_ranger.configure(text=f"🦸 เปิด Ranger Images ({img_count} รูป)"))
                    else:
                        self.after(0, lambda: self.btn_ranger.configure(text="🦸 เปิด Ranger Images (ยังไม่มีโฟลเดอร์)"))
                except:
                    pass
            
            threading.Thread(target=_count_images, daemon=True).start()
            
            # เพิ่มเป็น 15 วินาที แทน 5 วินาที
            self.after(15000, self.update_ranger_count)


    class DeviceMonitorWidget(ctk.CTkFrame):
        def __init__(self, parent, serial, index):
            super().__init__(parent)
            self.serial = serial
            
            self.grid_columnconfigure(0, weight=1)
            self.grid_columnconfigure(1, weight=0)
            
            info_panel = ctk.CTkFrame(self, fg_color="transparent")
            info_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
            
            header = ctk.CTkFrame(info_panel, fg_color="transparent")
            header.pack(fill="x")
            
            ctk.CTkLabel(header, text=f"#{index}", font=ctk.CTkFont(size=14, weight="bold"), text_color="gray").pack(side="left")
            ctk.CTkLabel(header, text=f"  {serial}", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
            
            self.btn_reset = ctk.CTkButton(
                header, text="↺ RESET", width=60, height=20,
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color="#ff5555", hover_color="#cc4444",
                command=lambda: trigger_manual_reset(serial)
            )
            self.btn_reset.pack(side="right", padx=(5, 0))
            
            self.lbl_status = ctk.CTkLabel(header, text="IDLE", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray")
            self.lbl_status.pack(side="right")
            
            self.lbl_step = ctk.CTkLabel(info_panel, text="Current: Ready", anchor="w")
            self.lbl_step.pack(fill="x", pady=(5,0))
            
            self.lbl_log = ctk.CTkLabel(info_panel, text="...", font=ctk.CTkFont(size=11), text_color="gray70", anchor="w")
            self.lbl_log.pack(fill="x")

            self.img_frame = ctk.CTkFrame(self, width=160, height=90, fg_color="black", corner_radius=5)
            self.img_frame.grid(row=0, column=1, padx=10, pady=10)
            self.img_frame.pack_propagate(False)
            
            self.img_label = ctk.CTkLabel(self.img_frame, text="NO SIGNAL", text_color="gray")
            self.img_label.pack(fill="both", expand=True)

        def update_state(self, step=None, status=None, log=None, screenshot=None):
            if step: self.lbl_step.configure(text=f"Step: {step}")
            if log: self.lbl_log.configure(text=f"> {log}")
            if status:
                color = "gray"
                if status == 'working': color = "#2cc985"
                elif status == 'stuck': color = "#ff5555"
                elif status == 'waiting': color = "#F2C94C"
                elif 'RESET' in status: color = "#ff5555"
                self.lbl_status.configure(text=status.upper(), text_color=color)
            
            if screenshot is not None:
                try:
                    # ลบ image เก่าก่อนเพื่อป้องกัน memory leak
                    if hasattr(self.img_label, 'image') and self.img_label.image:
                        del self.img_label.image
                    
                    pil_img = Image.fromarray(cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB))
                    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(160, 90))
                    self.img_label.configure(image=ctk_img, text="")
                    self.img_label.image = ctk_img
                    
                    # เคลียร์ reference เก่า
                    del pil_img
                except:
                    pass


    def update_device_status(serial, **kwargs):
        if ModernBotGUI.instance:
            try:
                ModernBotGUI.instance.after(0, lambda: ModernBotGUI.instance.update_device(serial, **kwargs))
            except:
                pass

    def log_to_gui(message):
        if ModernBotGUI.instance:
            try:
                ModernBotGUI.instance.after(0, lambda: ModernBotGUI.instance.log(message))
            except:
                pass

    def start_gui():
        app = ModernBotGUI()
        app.mainloop()

except ImportError as e:
    GUI_ENABLED = False
    print(f"[GUI] ไม่พบ library: {e}")
    print(f"[INFO] ติดตั้ง: pip install customtkinter pillow")
    
    class ModernBotGUI:
        instance = None
        def __init__(self): pass
        def mainloop(self): pass
    
    class DeviceMonitorWidget:
        pass
    
    def update_device_status(*args, **kwargs):
        pass
    
    def log_to_gui(message):
        pass
    
    def start_gui():
        print("[ERROR] GUI ไม่พร้อมใช้งาน ใช้ Console mode แทน")


def sanitize_filename(filename):
    name, ext = os.path.splitext(filename)
    number_match = re.search(r'\((\d+)\)', name)
    number = f"({number_match.group(1)})" if number_match else ""
    clean_name = re.sub(r'[<>:"/\\|?*]', '', name)
    return f"{clean_name}{number}{ext}"

def update_file_queue(device_state):
    try:
        xml_files = [f for f in os.listdir(source_folder) if f.endswith('.xml')]
        with device_state.lock:
            for xml_file in xml_files:
                if xml_file not in device_state.processed_files:
                    device_state.file_queue.put(xml_file)
                    device_state.processed_files[xml_file] = True
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการอัพเดทคิวไฟล์: {e}")

def get_next_backup_id():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        filename_prefix = config.get('filename_prefix', 'conyfly')
    except:
        filename_prefix = 'conyfly'
    
    backup_dir = "backup-id"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        return 1, filename_prefix
        
    existing_files = glob.glob(os.path.join(backup_dir, f"{filename_prefix}-id*_LINE_COCOS_PREF_KEY_*.xml"))
    
    if not existing_files:
        return 1, filename_prefix
        
    ids = []
    for file in existing_files:
        try:
            id_part = file.split(f"{filename_prefix}-id")[1].split("_")[0]
            if id_part.isdigit():
                ids.append(int(id_part))
        except:
            continue
            
    if not ids:
        return 1, filename_prefix
        
    return max(ids) + 1, filename_prefix

def get_backup_folder():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    backup_path = os.path.join(current_dir, "backup", "backupxml")
    
    if not os.path.exists(backup_path):
        try:
            os.makedirs(backup_path)
            print(f"Created backup folder at: {backup_path}")
        except Exception as e:
            print(f"Error creating backup folder: {e}")
    
    return backup_path

source_folder = get_backup_folder()

def has_xml_files():
    try:
        xml_files = [f for f in os.listdir(source_folder) if f.endswith('.xml')]
        return len(xml_files) > 0
    except FileNotFoundError:
        return False

def clear_app(device):
    try:
        # time.sleep(0.1)
        device.shell("am force-stop com.google.android.googlequicksearchbox")
        device.shell("am force-stop com.android.browser")
        device.shell("am force-stop com.linecorp.LGRGS")
        # print(f"หยุดแอปทั้งหมดบนอุปกรณ์ {device.serial} สำเร็จ")
        time.sleep(0.2)
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการหยุดแอปบนอุปกรณ์ {device.serial}: {e}")
        try:
            time.sleep(1)
            device.shell("am force-stop com.linecorp.LGRGS")
            print(f"พยายามหยุดแอป Line Ranger อีกครั้งบนอุปกรณ์ {device.serial} สำเร็จ")
        except Exception as retry_error:
            print(f"ไม่สามารถหยุดแอปในการพยายามครั้งที่สองบนอุปกรณ์ {device.serial}: {retry_error}")

# ADB Functions (ใหม่)
def start_adb_server():
    try:
        kill_existing_adb()
        result = subprocess.run(["adb", "start-server"], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE, 
                              text=True)
        
        if result.returncode == 0:
            return True
        else:
            mumu_adb_path = "C:\\Program Files\\Netease\\MuMuPlayerGlobal-12.0\\shell\\adb.exe"
            if os.path.exists(mumu_adb_path):
                result = subprocess.run([mumu_adb_path, "start-server"],
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE,
                                     text=True)
                if result.returncode == 0:
                    return True
            return False
            
    except Exception:
        return False

def kill_existing_adb():
    try:
        if os.name == 'nt':
            subprocess.run(["taskkill", "/F", "/IM", "adb.exe"], 
                         stdout=subprocess.PIPE, 
                         stderr=subprocess.PIPE)
        else:
            subprocess.run(["killall", "adb"], 
                         stdout=subprocess.PIPE, 
                         stderr=subprocess.PIPE)
        time.sleep(0.1)
    except Exception:
        pass

def check_adb_available():
    try:
        result = subprocess.run(["adb", "version"], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE, 
                              text=True)
        
        if result.returncode == 0:
            if start_adb_server():
                time.sleep(0.5)
                return True
            return False

        mumu_adb_path = "C:\\Program Files\\Netease\\MuMuPlayerGlobal-12.0\\shell\\adb.exe"
        if os.path.exists(mumu_adb_path):
            os.environ["PATH"] = os.environ["PATH"] + os.pathsep + os.path.dirname(mumu_adb_path)
            
            result = subprocess.run(["adb", "version"], 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE, 
                                 text=True)
            
            if result.returncode == 0:
                if start_adb_server():
                    time.sleep(0.5)
                    return True
            return False

        return False

    except Exception:
        return False

START_PORT = 5557
MAX_DEVICES = 30
MUMU_PORTS = [START_PORT + (i * 2) for i in range(MAX_DEVICES)]  # [5557, 5559, 5561, ..., 5615]

# ============================================
# ส่วนที่ 2: แทนที่ฟังก์ชัน connect_to_mumu เดิมทั้งหมด
# ============================================

def connect_to_mumu():
    """
    ⭐ ฟังก์ชันเชื่อมต่อ MuMu Player แบบ Auto-scan ports
    - สแกน port อัตโนมัติจาก 5557 ขึ้นไป
    - รองรับหลายจอ (สูงสุด 30 จอ)
    - ตรวจสอบ devices ที่เชื่อมต่ออยู่แล้วก่อน
    """
    try:
        # Kill และ start adb server ใหม่
        subprocess.run(["adb", "kill-server"], capture_output=True, timeout=3)
        time.sleep(0.1)
        
        # ตั้งค่า MuMu path
        mumu_path = get_mumu_path()
        if mumu_path:
            os.environ["PATH"] = os.environ["PATH"] + os.pathsep + mumu_path
        
        subprocess.run(["adb", "start-server"], capture_output=True, timeout=3)
        time.sleep(0.5)

        # ⭐ ขั้นตอนที่ 1: ตรวจสอบ devices ที่เชื่อมต่ออยู่แล้ว
        print(f"{Fore.CYAN}[INFO] Checking already connected devices...{Style.RESET_ALL}")
        adb = AdbClient(host="127.0.0.1", port=5037)
        
        try:
            existing_devices = adb.devices()
            if existing_devices:
                print(f"{Fore.GREEN}[INFO] Found {len(existing_devices)} device(s) already connected!{Style.RESET_ALL}")
                for device in existing_devices:
                    print(f"{Fore.GREEN}  ✓ {device.serial}{Style.RESET_ALL}")
                return adb, existing_devices if len(existing_devices) > 1 else existing_devices[0]
        except Exception as e:
            print(f"{Fore.YELLOW}[WARNING] Could not get existing devices: {str(e)}{Style.RESET_ALL}")

        # ⭐ ขั้นตอนที่ 2: Auto-scan ports
        print(f"{Fore.CYAN}[INFO] Auto-scanning ports from {START_PORT} ({MAX_DEVICES} devices)...{Style.RESET_ALL}")

        connected_devices = []
        
        def try_connect_port(port):
            """ลองเชื่อมต่อ port เดียว"""
            try:
                result = subprocess.run(
                    ["adb", "connect", f"127.0.0.1:{port}"],
                    capture_output=True,
                    timeout=2,
                    text=True
                )
                time.sleep(0.3)
                
                # ตรวจสอบว่าเชื่อมต่อสำเร็จหรือไม่
                if "connected" in result.stdout.lower() or "already connected" in result.stdout.lower():
                    # ดึง device object
                    try:
                        devices = adb.devices()
                        for device in devices:
                            if f":{port}" in device.serial or f"emulator-{port}" in device.serial:
                                print(f"{Fore.GREEN}  ✓ Connected: 127.0.0.1:{port} ({device.serial}){Style.RESET_ALL}")
                                return device
                    except Exception:
                        pass
            except Exception:
                pass
            return None

        # ⭐ สแกน port ทีละตัวแบบ parallel เพื่อความเร็ว
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(try_connect_port, port): port for port in MUMU_PORTS}
            
            for future in concurrent.futures.as_completed(futures):
                device = future.result()
                if device:
                    connected_devices.append(device)

        if connected_devices:
            print(f"\n{Fore.GREEN}[SUCCESS] Total {len(connected_devices)} device(s) connected!{Style.RESET_ALL}")
            for i, device in enumerate(connected_devices, 1):
                print(f"{Fore.GREEN}  Device {i}: {device.serial}{Style.RESET_ALL}")
            return adb, connected_devices if len(connected_devices) > 1 else connected_devices[0]
        
        print(f"{Fore.RED}[ERROR] No devices found.Please check if MuMu Player is running.{Style.RESET_ALL}")
        return None, []

    except Exception as e:
        print(f"{Fore.RED}[ERROR] connect_to_mumu exception: {str(e)}{Style.RESET_ALL}")
        return None, []


# ============================================
# ส่วนที่ 3: แทนที่ฟังก์ชัน get_mumu_path
# ============================================

def get_mumu_path():
    """ค้นหา MuMu Player path จากตำแหน่งที่เป็นไปได้"""
    possible_paths = [
        # ⭐ Path ทั่วไปสำหรับ MuMu Player
        "F:\\Program Files\\Netease\\MuMuPlayer\\shell",
        "F:\\Program Files\\Netease\\MuMuPlayer",
        "F:\\Program Files\\Netease\\MuMuPlayer\\nx_main",
        "C:\\Program Files\\Netease\\MuMuPlayerGlobal-12.0\\shell",
        "C:\\Program Files\\Netease\\MuMuPlayer\\shell",
        "F:\\MuMuPlayerGlobal-12.0\\shell",
        "D:\\MuMuPlayerGlobal-12.0\\shell",
        "E:\\MuMuPlayerGlobal-12.0\\shell",
        "D:\\Program Files\\Netease\\MuMuPlayer\\shell",
        "E:\\Program Files\\Netease\\MuMuPlayer\\shell",
        os.path.join(os.environ.get('LOCALAPPDATA', ''), "Netease\\MuMuPlayerGlobal-12.0\\shell"),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), "Netease\\MuMuPlayer\\shell"),
        os.path.join(os.environ.get('PROGRAMFILES', ''), "Netease\\MuMuPlayerGlobal-12.0\\shell"),
        os.path.join(os.environ.get('PROGRAMFILES', ''), "Netease\\MuMuPlayer\\shell"),
        os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), "Netease\\MuMuPlayerGlobal-12.0\\shell"),
        os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), "Netease\\MuMuPlayer\\shell")
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            print(f"พบ MuMu path: {path}")
            return path
    
    print("ไม่พบ MuMu path ในตำแหน่งมาตรฐาน")
    return None


# ============================================
# ส่วนที่ 4: เพิ่ม/แทนที่ฟังก์ชัน check_mumu_running
# ============================================

def check_mumu_running():
    """ตรวจสอบว่า MuMu Player กำลังทำงานอยู่หรือไม่"""
    try:
        # ⭐ วิธีที่ 1: ตรวจสอบจาก adb devices
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if "emulator-" in result.stdout or "127.0.0.1:" in result.stdout:
                print("พบ device ผ่าน ADB")
                return True
        except Exception as e:
            print(f"ADB devices check ล้มเหลว: {str(e)}")
        
        # ⭐ วิธีที่ 2: ตรวจสอบจาก process name
        for proc in psutil.process_iter(['name']):
            proc_name = proc.info['name']
            if any(name in proc_name for name in ['MuMuPlayer', 'MuMu', 'NemuPlayer', 'nemu']):
                print(f"พบ MuMu process: {proc_name}")
                return True
        
        print("ไม่พบ MuMu Player กำลังทำงาน")
        return False
    except Exception as e:
        print(f"Error check_mumu_running: {str(e)}")
        return False




def scan_mumu_directory():
    common_paths = [
        "F:\\MuMuPlayerGlobal-12.0\\shell",
        "C:\\Program Files\\Netease\\MuMuPlayerGlobal-12.0\\shell",
        "D:\\MuMuPlayerGlobal-12.0\\shell",
        "E:\\MuMuPlayerGlobal-12.0\\shell",
        os.path.join(os.environ.get('LOCALAPPDATA', ''), "Netease\\MuMuPlayerGlobal-12.0\\shell"),
        os.path.join(os.environ.get('PROGRAMFILES', ''), "Netease\\MuMuPlayerGlobal-12.0\\shell"),
        os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), "Netease\\MuMuPlayerGlobal-12.0\\shell")
    ]
    
    ports = set()
    
    for path in common_paths:
        if os.path.exists(path):
            try:
                config_files = [f for f in os.listdir(path) if f.endswith('.config')]
                for config_file in config_files:
                    try:
                        with open(os.path.join(path, config_file), 'r') as f:
                            content = f.read()
                            port_match = re.search(r'adb_port=(\d+)', content)
                            if port_match:
                                ports.add(port_match.group(1))
                    except:
                        continue
            except:
                continue
    
    return list(ports)

def scan_ports_from_netstat():
    try:
        process = subprocess.run(
            'netstat -ano', 
            shell=True, 
            capture_output=True, 
            timeout=5
        )
        output = process.stdout.decode()
        
        ports = []
        for line in output.split('\n'):
            if '127.0.0.1' in line and 'LISTENING' in line:
                match = re.search(r':(\d+)', line)
                if match:
                    port = match.group(1)
                    if 16416 <= int(port) <= 18999:
                        ports.append(port)
    except Exception:
        ports = []
    return list(set(ports))

def find_mumu_processes():
    mumu_processes = []
    try:
        process_list = subprocess.check_output('tasklist /FI "IMAGENAME eq MuMu*"', shell=True).decode()
        for line in process_list.split('\n'):
            if 'MuMu' in line:
                try:
                    pid = int(re.search(r'\b(\d+)\b', line).group(1))
                    cmd = subprocess.check_output(f'wmic process where ProcessId={pid} get CommandLine', shell=True).decode()
                    port_match = re.search(r'-port (\d+)', cmd)
                    if port_match:
                        mumu_processes.append((pid, port_match.group(1)))
                except:
                    continue
    except:
        pass
    return mumu_processes

def find_mumu_adb_ports():
    try:
        result = subprocess.run(
            ['adb', 'devices'], 
            capture_output=True, 
            text=True,
            timeout=5
        )
        ports = re.findall(r'127\.0\.0\.1:(\d+)', result.stdout)
        return ports
    except Exception:
        return []

def scan_all_possible_ports():
    all_ports = set()
    base_ports = [16416, 16448, 16480, 16512, 16544, 16576, 16608, 16640, 16672, 16704]
    
    for port in base_ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.1)
            result = sock.connect_ex(('127.0.0.1', port))
            if result == 0:
                all_ports.add(str(port))
            sock.close()
        except:
            continue
    
    try:
        netstat = subprocess.check_output('netstat -an | findstr "16"', shell=True).decode()
        for line in netstat.split('\n'):
            if '127.0.0.1' in line and 'LISTENING' in line:
                port_match = re.search(r':(\d+)', line)
                if port_match:
                    port = port_match.group(1)
                    if port.isdigit() and 16416 <= int(port) <= 18999:
                        all_ports.add(port)
    except:
        pass
    
    return list(all_ports)



def enable_root(device):
    try:
        adb_command = f"adb -s {device.serial} root"
        result = subprocess.run(adb_command.split(), stdout=subprocess.PIPE, text=True, timeout=5)
        print(f"เปิดใช้งาน root สำหรับ {device.serial}: {result.stdout.strip()}")
    except Exception as e:
        print(f"ไม่สามารถเปิดใช้งาน root สำหรับ {device.serial}: {e}")

def ImgSearchADB(adb_img, find_img_path, threshold=0.95, method=cv2.TM_CCOEFF_NORMED):
    try:
        find_img = cv2.imread(find_img_path, cv2.IMREAD_COLOR)
        if find_img is None:
            print(f"ไม่สามารถโหลดรูปภาพ {find_img_path}")
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
        rectangles, _ = cv2.groupRectangles(rectangles, groupThreshold=1, eps=1)
        points = []
        if len(rectangles):
            for (x, y, w, h) in rectangles:
                center_x = x + int(w / 2)
                center_y = y + int(h / 2)
                points.append((center_x, center_y))
        return points
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการค้นหารูปภาพ: {e}")
        return []

def get_link_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        link_setting = config.get('link', 0)
        # ลบบรรทัดนี้: print(f"Link config setting: {link_setting}")
        
        return link_setting
        
    except Exception as e:
        print(f"Error loading link config: {e} - using default 0")
        return 0

def load_link_url():
    try:
        link_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'link.txt')
        
        if os.path.exists(link_file_path):
            with open(link_file_path, 'r', encoding='utf-8') as f:
                url = f.read().strip()
                if url:
                    # ลบบรรทัดนี้: print(f"โหลด URL จากไฟล์ link.txt สำเร็จ: {url[:50]}...")
                    return url
                else:
                    print(f"ไฟล์ link.txt ว่างเปล่า - ใช้ URL เริ่มต้น")
        else:
            print(f"ไม่พบไฟล์ link.txt - ใช้ URL เริ่มต้น")
            
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการอ่านไฟล์ link.txt: {e} - ใช้ URL เริ่มต้น")
    
    default_url = "https://game-api.line.me/tracking/v1.0/link/LGRGS/TRACKING-LINK-LGRGS-267dea39-c44f-4a89-805d-b41da106b0ad/click?fbclid=IwY2xjawL8HsVleHRuA2FlbQIxMABicmlkETFJd0RWTUx6eHdXdUsyR3ZEAR54csNDu-YoEmcd12fGntcYxQEZSq8b1z2VLoZjMaYn3021EZNeXIQJzXsfNw_aem_Spp05nEXoGcFSpYbMW5rfw"
    # ลบบรรทัดนี้: print(f"ใช้ URL เริ่มต้น: {default_url[:50]}...")
    return default_url

def process_link_sequence(device, adb_img):
    link_setting = get_link_config()
    
    fixling_start_time = None
    fixling_timeout = 15
    
    link_url = load_link_url()
    
    def check_fixling_and_handle(device, adb_img):
        nonlocal fixling_start_time
        
        fixling_pos = ImgSearchADB(adb_img, 'img/fixling.png')
        current_time = time.time()
        
        if fixling_pos:
            if fixling_start_time is None:
                fixling_start_time = current_time
                print(f"พบ fixling.png บนอุปกรณ์ {device.serial} - เริ่มนับเวลา {fixling_timeout} วินาที")
            else:
                elapsed_time = current_time - fixling_start_time
                if elapsed_time >= fixling_timeout:
                    print(f"พบ fixling.png ค้างนานเกิน {fixling_timeout} วินาที บนอุปกรณ์ {device.serial}")
                    print(f"กำลัง clear app และเริ่มขั้นตอน link ใหม่...")
                    clear_app(device)
                    time.sleep(6)
                    return "restart_link"
                else:
                    remaining_time = fixling_timeout - elapsed_time
                    print(f"fixling.png ค้างมาแล้ว {elapsed_time:.1f} วินาที - เหลือเวลาอีก {remaining_time:.1f} วินาที")
        else:
            if fixling_start_time is not None:
                print(f"ไม่พบ fixling.png แล้ว - รีเซ็ตการนับเวลา")
                fixling_start_time = None
        
        return None
    
    if link_setting == 1:
        # print(f"Link setting = 1: ค้นหา link.png ก่อน บนอุปกรณ์ {device.serial}")
        link_pos = ImgSearchADB(adb_img, 'img/link.png')
        
        if link_pos:
            print(f"พบ 'link.png' บนอุปกรณ์ {device.serial} ที่ตำแหน่ง: {link_pos[0][0]}, {link_pos[0][1]}")
            device.shell(f"input tap {link_pos[0][0]} {link_pos[0][1]}")
            time.sleep(1)
            
            # print(f"หลังจากกด link.png แล้ว กำลังค้นหา link1.png บนอุปกรณ์ {device.serial}")
            
            max_wait_time = 30
            wait_start = time.time()
            
            while time.time() - wait_start < max_wait_time:
                time.sleep(1)
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img_new = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                fixling_result = check_fixling_and_handle(device, adb_img_new)
                if fixling_result == "restart_link":
                    return "restart_link"
                
                link1_pos = ImgSearchADB(adb_img_new, 'img/link1.png')
                if link1_pos:
                    print(f"พบ 'link1.png' บนอุปกรณ์ {device.serial} ที่ตำแหน่ง: {link1_pos[0][0]}, {link1_pos[0][1]}")
                    device.shell(f"input tap {link1_pos[0][0]} {link1_pos[0][1]}")
                    time.sleep(1)
                    print(f"กำลังป้อน URL จากไฟล์ link.txt บนอุปกรณ์ {device.serial}")
                    device.shell(f'input text "{link_url}"')
                    time.sleep(15)
                    device.shell("input keyevent KEYCODE_ENTER")
                    time.sleep(1)
                    print(f"ทำงาน link sequence สำเร็จ (link.png -> link1.png) บนอุปกรณ์ {device.serial}")
                    return True
            
            print(f"ไม่พบ link1.png หลังจากรอ {max_wait_time} วินาที บนอุปกรณ์ {device.serial}")
            return True
        else:
            link1_pos = ImgSearchADB(adb_img, 'img/link1.png')
            if link1_pos:
                print(f"ไม่พบ link.png แต่พบ 'link1.png' บนอุปกรณ์ {device.serial} ที่ตำแหน่ง: {link1_pos[0][0]}, {link1_pos[0][1]}")
                device.shell(f"input tap {link1_pos[0][0]} {link1_pos[0][1]}")
                time.sleep(1)
                print(f"กำลังป้อน URL จากไฟล์ link.txt บนอุปกรณ์ {device.serial}")
                device.shell(f'input text "{link_url}"')
                time.sleep(15)
                device.shell("input keyevent KEYCODE_ENTER")
                time.sleep(1)
                return True
    else:
        # print(f"Link setting = 0: ใช้ test.png แบบเดิม บนอุปกรณ์ {device.serial}")
        test_pos = ImgSearchADB(adb_img, 'img/test.png')
        
        if test_pos:
            print(f"พบ 'test.png' บนอุปกรณ์ {device.serial} ที่ตำแหน่ง: {test_pos[0][0]}, {test_pos[0][1]}")
            device.shell(f"input tap {test_pos[0][0]} {test_pos[0][1]}")
            time.sleep(1)
            print(f"กำลังป้อน URL จากไฟล์ link.txt บนอุปกรณ์ {device.serial}")
            device.shell(f'input text "{link_url}"')
            time.sleep(15)
            device.shell("input keyevent KEYCODE_ENTER")
            time.sleep(1)
            return True
    
    return False

def search_gachaslot_image(device):
    max_swipes = 5
    swipe_count = 0
    
    print(f"เริ่มค้นหา gachaslot.png บนอุปกรณ์ {device.serial}")
    
    while swipe_count <= max_swipes:
        try:
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            gachaslot_pos = ImgSearchADB(adb_img, 'img/gachaslot.png')
            if gachaslot_pos:
                print(f"พบ gachaslot.png ที่ตำแหน่ง: {gachaslot_pos[0]} บนอุปกรณ์ {device.serial}")
                return gachaslot_pos[0]
            
            # ✅ เช็คก่อน ถ้าไม่เจอค่อยเลื่อน
            if swipe_count < max_swipes:
                print(f"ไม่พบ gachaslot.png - เลื่อนหน้าจอครั้งที่ {swipe_count + 1} บนอุปกรณ์ {device.serial}")
                device.shell(f"input swipe 824 240 808 109 1000")
                time.sleep(1)
                swipe_count += 1
            else:
                print(f"ไม่พบ gachaslot.png หลังจากเลื่อน {max_swipes} ครั้ง บนอุปกรณ์ {device.serial}")
                return None
                
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการค้นหา gachaslot.png บนอุปกรณ์ {device.serial}: {e}")
            return None
    
    return None

def check_for_heroes(device):
    try:
        print(f"กำลังค้นหา hero images บนอุปกรณ์ {device.serial}")
        cap = device.screencap()
        image = np.frombuffer(cap, dtype=np.uint8)
        adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
        
        hero_images = ['heroo1.png', 'heroo2.png', 'heroo3.png', 'heroo4.png']
        for hero_img in hero_images:
            hero_pos = ImgSearchADB(adb_img, f'img/ranger/{hero_img}')
            if hero_pos:
                print(f"พบ {hero_img} บนอุปกรณ์ {device.serial}")
                return True
        return False
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการค้นหา hero images: {e}")
        return False

def process_apple_event(device):
    print(f"{Fore.MAGENTA}[DEVICE {device.serial}] SPECIAL EVENT: Found apple.png! Starting sequence...{Style.RESET_ALL}")
    
    sequence1 = [
        'apple.png', 'check-l1.png', 'check-l2.png', 
        'check-l3.png', 'check-l4.png'
    ]
    
    # Sequence 1
    for img_name in sequence1:
        for attempt in range(5): # Try 5 times for each image
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            pos = ImgSearchADB(adb_img, f'img/{img_name}')
            if pos:
                print(f"{Fore.GREEN}[DEVICE {device.serial}] Found {img_name}!{Style.RESET_ALL}")
                device.shell(f"input tap {pos[0][0]} {pos[0][1]}")
                time.sleep(1)
                break
            time.sleep(0.5)
            
    print(f"{Fore.CYAN}[DEVICE {device.serial}] Sequence 1 completed, waiting 8s then pressing BACK...{Style.RESET_ALL}")
    time.sleep(8)
    device.shell("input keyevent 4")
    time.sleep(2)
    
    sequence2 = [
        'check-gusetid.png', 'check-gusetid1.png',
        'check-l1.png', 'check-l2.png', 'check-l3.png', 'check-l4.png'
    ]
    
    # Sequence 2
    for img_name in sequence2:
        for attempt in range(5):
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            pos = ImgSearchADB(adb_img, f'img/{img_name}')
            if pos:
                print(f"{Fore.GREEN}[DEVICE {device.serial}] Found {img_name}!{Style.RESET_ALL}")
                device.shell(f"input tap {pos[0][0]} {pos[0][1]}")
                time.sleep(1)
                break
            time.sleep(0.5)
            
    print(f"{Fore.MAGENTA}[DEVICE {device.serial}] Special apple event completed.{Style.RESET_ALL}")
    return True

# ============================================
# ⭐ ฟังก์ชันกลางสำหรับเช็ค fixid, fixunkown, apple
# เรียกใช้ได้ทุกที่ในโปรแกรม
# ============================================
def check_critical_errors(device, adb_img, context=""):
    """
    ตรวจสอบ fixid.png, fixunkown.png, apple.png
    
    Returns:
        - "fixid" ถ้าพบ fixid.png
        - "fixunkown" ถ้าพบ fixunkown.png  
        - "apple" ถ้าพบ apple.png
        - None ถ้าไม่พบอะไร
    """
    try:
        # ตรวจสอบ fixid.png
        fixid_pos = ImgSearchADB(adb_img, 'img/fixid.png')
        if fixid_pos:
            print(f"{Fore.RED}[DEVICE {device.serial}] ⚠️ Found fixid.png in {context}!{Style.RESET_ALL}")
            if backup_to_backupxml(device):
                print(f"✅ Backup ไป backupxml สำเร็จ")
            clear_app(device)
            time.sleep(6)
            return "fixid"
        
        # ตรวจสอบ fixunkown.png
        fixunkown_pos = ImgSearchADB(adb_img, 'img/fixunkown.png')
        if fixunkown_pos:
            print(f"{Fore.RED}[DEVICE {device.serial}] ⚠️ Found fixunkown.png in {context}!{Style.RESET_ALL}")
            if backup_to_backupxml(device):
                print(f"✅ Backup ไป backupxml สำเร็จ")
            clear_app(device)
            time.sleep(6)
            return "fixunkown"
        
        # ตรวจสอบ apple.png
        apple_pos = ImgSearchADB(adb_img, 'img/apple.png')
        if apple_pos:
            print(f"{Fore.RED}[DEVICE {device.serial}] ⚠️ Found apple.png in {context}!{Style.RESET_ALL}")
            if backup_failed_login(device):
                print(f"✅ Backup ไป login-fail สำเร็จ")
            clear_app(device)
            time.sleep(6)
            return "apple"
        
        return None
    except Exception as e:
        print(f"[ERROR] check_critical_errors: {e}")
        return None

class NetworkMonitor:
    def __init__(self):
        self.last_check = time.time()
        self.check_interval = 10
        
    def check_network(self, device, adb_img):
        current_time = time.time()
        if current_time - self.last_check >= self.check_interval:
            # Check for apple.png (Special Event)
            apple_pos = ImgSearchADB(adb_img, 'img/apple.png')
            if apple_pos:
                return process_apple_event(device)

            # ตรวจสอบ stopcheck.png (Hard Reset & Re-queue XML)
            stopcheck_pos = ImgSearchADB(adb_img, 'img/stopcheck.png')
            if stopcheck_pos:
                print(f"{Fore.RED}[DEVICE {device.serial}] พบ stopcheck.png -> กำลังดึงไฟล์กลับและรีเซ็ตระบบ...{Style.RESET_ALL}")
                try:
                    # 1. Retrieve original filename
                    global _device_state_local
                    original_filename = None
                    try:
                        if _device_state_local:
                            original_filename = _device_state_local.original_filenames.get(device.serial)
                    except NameError:
                        pass

                    if original_filename:
                        # 2. Recycle XML to backup/backupxml
                        print(f"{Fore.YELLOW}[DEVICE {device.serial}] กำลังนำไฟล์ {original_filename} กลับเข้าคิว...{Style.RESET_ALL}")
                        current_dir = os.path.dirname(os.path.abspath(__file__))
                        backup_xml_dir = os.path.join(current_dir, "backup", "backupxml")
                        if not os.path.exists(backup_xml_dir):
                            os.makedirs(backup_xml_dir)
                            
                        source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
                        dest_path = os.path.join(backup_xml_dir, original_filename)
                        
                        device.shell("su -c 'chmod 777 /data/data/com.linecorp.LGRGS/shared_prefs'")
                        device.shell(f"su -c 'chmod 777 {source_path}'")
                        
                        subprocess.run(['adb', '-s', device.serial, 'pull', source_path, dest_path], 
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                                     
                        if os.path.exists(dest_path):
                            print(f"{Fore.GREEN}[DEVICE {device.serial}] นำไฟล์ {original_filename} กลับมาสำเร็จ{Style.RESET_ALL}")
                            # Add back to queue safely
                            try:
                                with _device_state_local.lock:
                                    _device_state_local.file_queue.put(original_filename)
                            except:
                                pass
                        else:
                            print(f"{Fore.RED}[DEVICE {device.serial}] ไม่สามารถนำไฟล์ XML กลับมาได้{Style.RESET_ALL}")

                    # 3. Clear App & Data
                    clear_app(device)
                    device.shell("pm clear com.linecorp.LGRGS")
                    time.sleep(2)
                except Exception as e:
                    print(f"{Fore.RED}[DEVICE {device.serial}] เกิดข้อผิดพลาดขณะรีเซ็ต stopcheck: {e}{Style.RESET_ALL}")
                return "reset_first_loop"
                
            fixnet_pos = ImgSearchADB(adb_img, 'img/fixnet.png')
            if fixnet_pos:
                print(f"พบปัญหาการเชื่อมต่อ (fixnet.png) บนอุปกรณ์ {device.serial}")
                device.shell(f"input tap {fixnet_pos[0][0]} {fixnet_pos[0][1]}")
                time.sleep(1)
                return True
            self.last_check = current_time
        return False




def func_7day(device):
    network_monitor = NetworkMonitor()

    print(f"กำลังตรวจสอบกิจกรรม 7 วันสำหรับอุปกรณ์: {device.serial}")
    
    for attempt in range(1):
        try:
            print(f"กำลังค้นหา 7day.png (พยายามครั้งที่ {attempt + 1}/1)")
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            if network_monitor.check_network(device, adb_img):
                continue
            
            # ⭐ ตรวจสอบ fixid, fixunkown, apple
            critical_error = check_critical_errors(device, adb_img, "func_7day_main")
            if critical_error:
                return critical_error
            
            pos_adb = ImgSearchADB(adb_img, 'img/7day.png')
            if pos_adb:
                print(f"พบ '7day.png' ที่ตำแหน่ง: {pos_adb[0][0]}, {pos_adb[0][1]}")
                device.shell(f"input tap {pos_adb[0][0]} {pos_adb[0][1]}")
                time.sleep(1)
                break
            time.sleep(1)
        except Exception as e:
            print(f"เกิดข้อผิดพลาด: {e}")
            time.sleep(1)

    no_7day1_count = 0
    max_no_find = 1
    
    while True:
        try:
            print("กำลังค้นหา 7day1.png...")
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            # ⭐ ตรวจสอบ fixid, fixunkown, apple
            critical_error = check_critical_errors(device, adb_img, "func_7day")
            if critical_error:
                return critical_error  # Return เพื่อให้ main loop จัดการ
            
            pos_7day1 = ImgSearchADB(adb_img, 'img/7day1.png')
            
            if pos_7day1:
                print(f"พบ '7day1.png' ที่ตำแหน่ง: {pos_7day1[0][0]}, {pos_7day1[0][1]}")
                device.shell(f"input tap {pos_7day1[0][0]} {pos_7day1[0][1]}")
                time.sleep(1)
                
                print("กำลังค้นหา ok.png...")
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                pos_ok = ImgSearchADB(adb_img, 'img/ok.png')
                if pos_ok:
                    print(f"พบ 'ok.png' ที่ตำแหน่ง: {pos_ok[0][0]}, {pos_ok[0][1]}")
                    device.shell(f"input tap {pos_ok[0][0]} {pos_ok[0][1]}")
                    time.sleep(1)
                
                no_7day1_count = 0
            else:
                print("ไม่พบ 7day1.png")
                no_7day1_count += 1
                if no_7day1_count >= max_no_find:
                    print(f"ไม่พบ 7day1.png ติดต่อกัน {max_no_find} ครั้ง - เริ่มค้นหา 7day2.png")
                    break
                time.sleep(1)
                
        except Exception as e:
            print(f"เกิดข้อผิดพลาด: {e}")
            time.sleep(1)

    for attempt in range(1):
        try:
            print(f"กำลังค้นหา 7day2.png (พยายามครั้งที่ {attempt + 1}/1)")
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            # ⭐ ตรวจสอบ fixid, fixunkown, apple
            critical_error = check_critical_errors(device, adb_img, "func_7day_7day2")
            if critical_error:
                return critical_error
            
            pos_7day2 = ImgSearchADB(adb_img, 'img/7day2.png')
            if pos_7day2:
                print(f"พบ '7day2.png' ที่ตำแหน่ง: {pos_7day2[0][0]}, {pos_7day2[0][1]}")
                device.shell(f"input tap {pos_7day2[0][0]} {pos_7day2[0][1]}")
                time.sleep(1)
                break
            time.sleep(1)
        except Exception as e:
            print(f"เกิดข้อผิดพลาด: {e}")
            time.sleep(1)

    for attempt in range(1):
        try:
            print(f"กำลังค้นหา event.png (พยายามครั้งที่ {attempt + 1}/1)")
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            # ⭐ ตรวจสอบ fixid, fixunkown, apple
            critical_error = check_critical_errors(device, adb_img, "func_7day_event")
            if critical_error:
                return critical_error
            
            pos_event = ImgSearchADB(adb_img, 'img/event.png')
            if pos_event:
                print(f"พบ 'event.png' ที่ตำแหน่ง: {pos_event[0][0]}, {pos_event[0][1]}")
                device.shell(f"input tap {pos_event[0][0]} {pos_event[0][1]}")
                time.sleep(1)
                break
            time.sleep(1)
        except Exception as e:
            print(f"เกิดข้อผิดพลาด: {e}")
            time.sleep(1)

    print(f"ตรวจสอบกิจกรรม 7 วันเสร็จสิ้นสำหรับอุปกรณ์ {device.serial}")




def main_box(device):
    network_monitor = NetworkMonitor()

    print(f"เริ่มลำดับการกดกล่องสำหรับอุปกรณ์: {device.serial}")
    
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        box_settings = config.get('box_settings', {
            'first_round': 1,
            'second_round': 1
        })
    except Exception as e:
        print(f"ไม่สามารถโหลด config.json: {e} - ใช้ค่าเริ่มต้น")
        box_settings = {
            'first_round': 1,
            'second_round': 1
        }

    def check_first_round_boxes():
        print(f"กำลังตรวจสอบกล่องรอบแรกสำหรับอุปกรณ์: {device.serial}")
        image_sequence = ['box1.png', 'box2.png', 'box3.png', 'box4.png', 'box5.png']
        sequence_index = 0
        start_time = time.time()
        timeout = 180  # เพิ่ม timeout เป็น 180 วินาที (3 นาที)
        not_found_count = 0  # เพิ่มตัวนับครั้งที่ไม่พบรูป
        max_not_found = 15  # ถ้าไม่พบติดต่อกัน 15 ครั้ง ให้ออก
        
        while sequence_index < len(image_sequence):
            try:
                current_time = time.time()
                
                print(f"กำลังค้นหา {image_sequence[sequence_index]} บนอุปกรณ์ {device.serial} (ครั้งที่ {not_found_count + 1})")
                time.sleep(0.5)  # ⭐ หน่วงก่อน screencap
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                # ตรวจสอบ network ก่อน
                network_status = network_monitor.check_network(device, adb_img)
                if network_status == "reset_first_loop":
                    return "reset_first_loop"
                if network_status:
                    time.sleep(1)  # ⭐ หน่วงหลัง network check
                    continue
                
                # ⭐ ตรวจสอบ fixid, fixunkown, apple
                critical_error = check_critical_errors(device, adb_img, "main_box")
                if critical_error:
                    return critical_error
                
                pos_adb = ImgSearchADB(adb_img, f'img/{image_sequence[sequence_index]}')
                if pos_adb:
                    print(f"พบ '{image_sequence[sequence_index]}' บนอุปกรณ์ {device.serial} ที่ตำแหน่ง: {pos_adb[0][0]}, {pos_adb[0][1]}")
                    time.sleep(0.3)  # ⭐ หน่วงก่อนกด
                    device.shell(f"input tap {pos_adb[0][0]} {pos_adb[0][1]}")
                    sequence_index += 1
                    not_found_count = 0  # รีเซ็ตตัวนับเมื่อพบรูป
                    start_time = time.time()  # รีเซ็ตเวลาเมื่อพบรูป
                    time.sleep(2)  # ⭐ หน่วงหลังกดนานขึ้น จาก 1 เป็น 2 วินาที
                else:
                    not_found_count += 1
                    
                    # ถ้าไม่พบติดต่อกันเกินกว่าที่กำหนด
                    if not_found_count >= max_not_found:
                        print(f"ไม่พบ {image_sequence[sequence_index]} ติดต่อกัน {max_not_found} ครั้ง บนอุปกรณ์ {device.serial}")
                        print(f"กำลังคลิก event.png และออกจากรอบแรก")
                        event_pos = ImgSearchADB(adb_img, 'img/event.png')
                        if event_pos:
                            time.sleep(0.5)  # ⭐ หน่วงก่อนกด
                            device.shell(f"input tap {event_pos[0][0]} {event_pos[0][1]}")
                            time.sleep(2)  # ⭐ หน่วงหลังกด
                        return False
                    
                    # แสดงสถานะทุก 5 ครั้ง
                    if not_found_count % 5 == 0:
                        print(f"ยังค้นหา {image_sequence[sequence_index]} อยู่...({not_found_count}/{max_not_found})")
                    
                    time.sleep(1.5)  # ⭐ หน่วงเมื่อไม่พบ จาก 1 เป็น 1.5 วินาที
                    
            except Exception as e:
                print(f"เกิดข้อผิดพลาด: {e}")
                time.sleep(3)  # ⭐ หน่วงเมื่อ error จาก 2 เป็น 3 วินาที
        
        print(f"เสร็จสิ้นรอบแรกสำหรับอุปกรณ์ {device.serial}")
        return True

    def check_box1():
        try:
            print(f"กำลังค้นหา box1.png บนอุปกรณ์ {device.serial}")
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            # ⭐ ตรวจสอบ fixid, fixunkown, apple
            critical_error = check_critical_errors(device, adb_img, "main_box_check_box1")
            if critical_error:
                return critical_error
            
            pos_adb = ImgSearchADB(adb_img, 'img/box1.png')
            if pos_adb:
                print(f"พบ 'box1.png' บนอุปกรณ์ {device.serial} ที่ตำแหน่ง: {pos_adb[0][0]}, {pos_adb[0][1]}")
                device.shell(f"input tap {pos_adb[0][0]} {pos_adb[0][1]}")
                time.sleep(1)
                return True
            return False
        except Exception as e:
            print(f"เกิดข้อผิดพลาด: {e}")
            time.sleep(2)
            return False

    def check_accept_and_tap():
        try:
            time.sleep(0.5)  # ⭐ หน่วงก่อน screencap
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            # ⭐ ตรวจสอบ fixid, fixunkown, apple
            critical_error = check_critical_errors(device, adb_img, "main_box_check_accept")
            if critical_error:
                return critical_error  # Return string เพื่อให้ main loop จัดการ
            
            accept_pos = ImgSearchADB(adb_img, 'img/accept.png')
            
            if accept_pos:
                print(f"พบ accept.png บนอุปกรณ์ {device.serial} ที่ตำแหน่ง: {accept_pos[0][0]}, {accept_pos[0][1]}")
                time.sleep(0.5)  # ⭐ หน่วงก่อนกด
                device.shell(f"input tap {accept_pos[0][0]} {accept_pos[0][1]}")
                time.sleep(3)  # ⭐ หน่วงหลังกด จาก 2 เป็น 3 วินาที
                
                for i in range(2):
                    print(f"กำลังแตะตำแหน่ง 469 352 ครั้งที่ {i+1}")
                    device.shell("input tap 469 352")
                    time.sleep(0.8)  # ⭐ หน่วงระหว่าง tap จาก 0.5 เป็น 0.8 วินาที
                
                for i in range(5):
                    print(f"กำลังแตะตำแหน่ง 504 464 ครั้งที่ {i+1}")
                    device.shell("input tap 504 464")
                    time.sleep(0.8)  # ⭐ หน่วงระหว่าง tap จาก 0.5 เป็น 0.8 วินาที
                
                return True
            else:
                print("ไม่พบ accept.png - กำลังเลื่อนหน้าจอขึ้น (ช้าลง)")
                device.shell(f"input swipe 613 296 616 251 800")  # ⭐ เลื่อนช้าลง จาก 500 เป็น 800ms
                time.sleep(2.5)  # ⭐ หน่วงหลังเลื่อน จาก 2 เป็น 2.5 วินาที
                
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                # ⭐ เช็ค critical error หลังเลื่อนหน้าจอด้วย
                critical_error = check_critical_errors(device, adb_img, "main_box_after_scroll")
                if critical_error:
                    return critical_error
                
                accept_pos = ImgSearchADB(adb_img, 'img/accept.png')
                
                if accept_pos:
                    print(f"พบ accept.png หลังเลื่อนหน้าจอ ที่ตำแหน่ง: {accept_pos[0][0]}, {accept_pos[0][1]}")
                    return True
                
                return False
                
        except Exception as e:
            print(f"เกิดข้อผิดพลาด: {e}")
            time.sleep(3)  # ⭐ หน่วง error จาก 2 เป็น 3 วินาที
            return False

    try:
        if box_settings.get('first_round', 1):
            print("เริ่มการทำงานรอบแรก...")
            result_first = check_first_round_boxes()
            # ⭐ เช็คว่าเป็น critical error หรือไม่
            if isinstance(result_first, str) and result_first in ["fixid", "fixunkown", "apple", "reset_first_loop"]:
                return result_first
            if not result_first:
                return
            time.sleep(2)
        else:
            print("ข้ามการทำงานรอบแรก (ปิดใช้งานใน config)")
        
        if box_settings.get('second_round', 1):
            print("เริ่มการทำงานรอบถัดไป...")
            no_accept_count = 0
            
            while True:
                result_box1 = check_box1()
                # ⭐ เช็คว่าเป็น critical error หรือไม่
                if isinstance(result_box1, str) and result_box1 in ["fixid", "fixunkown", "apple"]:
                    return result_box1
                    
                time.sleep(2.5)  # ⭐ หน่วงหลัง check_box1 จาก 2 เป็น 2.5 วินาที
                
                result_accept = check_accept_and_tap()
                # ⭐ เช็คว่าเป็น critical error หรือไม่
                if isinstance(result_accept, str) and result_accept in ["fixid", "fixunkown", "apple"]:
                    return result_accept
                
                if result_accept == True:
                    time.sleep(3)  # ⭐ หน่วงหลัง accept จาก 2 เป็น 3 วินาที
                    no_accept_count = 0
                    continue
                else:
                    no_accept_count += 1
                    if no_accept_count >= 3:
                        print(f"ไม่พบ accept 3 ครั้งติดต่อกัน - จบกระบวนการสำหรับอุปกรณ์ {device.serial}")
                        return
                    else:
                        print(f"ไม่พบ accept ครั้งที่ {no_accept_count}")
                        time.sleep(1.5)  # ⭐ หน่วงเมื่อไม่พบ accept
                        continue
        else:
            print("ข้ามการทำงานรอบที่สอง (ปิดใช้งานใน config)")
            
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการทำงาน: {e}")
        return




# =============================================
# ฟังก์ชัน auto_trade - ซื้อสินค้าใน swap shop อัตโนมัติ
# =============================================
def auto_trade(device, config=None):
    """
    ฟังก์ชันสำหรับประมวลผล auto trade โดยทำตามลำดับ shop1 -> shop2 -> shopkom
    Args:
        device: อุปกรณ์ที่ต้องการทำงาน
        config (dict): dictionary ของการตั้งค่า จำนวนครั้งที่ต้องการซื้อแต่ละร้าน (ถ้าไม่ส่งจะอ่านจาก config.json)
    """
    # อ่านค่าจาก config.json
    if config is None:
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                json_config = json.load(f)
            auto_trade_config = json_config.get('auto_trade', {})
            config = {
                'swap_shop1': auto_trade_config.get('swap_shop1', 1),
                'swap_shop2': auto_trade_config.get('swap_shop2', 1),
                'swap_shopkom': auto_trade_config.get('swap_shopkom', 1),
                'swap_shopkom9star': auto_trade_config.get('swap_shopkom9star', 1)
            }
            print(f"[AUTO_TRADE] โหลด config จาก config.json สำเร็จ")
        except Exception as e:
            print(f"[AUTO_TRADE] ไม่สามารถอ่าน config.json ได้: {e} - ใช้ค่าเริ่มต้น")
            config = {
                'swap_shop1': 1,
                'swap_shop2': 1,
                'swap_shopkom': 1,
                'swap_shopkom9star': 1
            }
    
    print(f"\n[AUTO_TRADE] เริ่มกระบวนการ auto trade สำหรับอุปกรณ์: {device.serial}")
    print(f"[AUTO_TRADE] Config: Shop1: {config['swap_shop1']}, Shop2: {config['swap_shop2']}, Shopkom: {config['swap_shopkom']}, Shopkom9star: {config['swap_shopkom9star']}")
    
    def perform_purchase(img_name, position):
        """
        ฟังก์ชันซื้อสินค้า - เวอร์ชันเร็ว (FAST MODE)
        ลด timeout และ delay เพื่อให้ซื้อได้เร็วขึ้น
        """
        try:
            print(f"\n[AUTO_TRADE] กำลังซื้อ {img_name}")
            device.shell(f"input tap {position[0][0]} {position[0][1]}")
            time.sleep(1.5)  # ลดจาก 3 เป็น 1.5 วินาที
            
            def check_and_click_fast(target_img, step_name, max_time=8, stuck_time=2):
                """
                เช็คและกดรูปแบบเร็ว (FAST MODE)
                - max_time: เวลารวม 8 วินาที (ลดจาก 15)
                - stuck_time: กดซ้ำถ้าค้าง 2 วินาที ⭐ ลดจาก 3 เป็น 2
                - delay น้อยลง
                """
                start_time = time.time()
                last_found_time = None
                click_count = 0
                
                while time.time() - start_time < max_time:
                    try:
                        cap = device.screencap()
                        img_check = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                        
                        # ⭐ ตรวจสอบ fixid, fixunkown, apple
                        critical_error = check_critical_errors(device, img_check, "auto_trade")
                        if critical_error:
                            return False  # Return False เพื่อหยุด auto_trade
                        
                        pos = ImgSearchADB(img_check, f'img/{target_img}')
                        
                        if pos:
                            current_time = time.time()
                            
                            # พบรูปครั้งแรก - กดเลย
                            if last_found_time is None:
                                last_found_time = current_time
                                click_count += 1
                                print(f"[AUTO_TRADE] พบ {target_img} - กดครั้งที่ {click_count}")
                                device.shell(f"input tap {pos[0][0]} {pos[0][1]}")
                                time.sleep(0.5)  # ลดจาก 1 เป็น 0.5 วินาที
                            else:
                                # รูปค้าง - กดซ้ำ
                                if current_time - last_found_time >= stuck_time:
                                    click_count += 1
                                    print(f"[AUTO_TRADE] {target_img} ค้าง - กดซ้ำครั้งที่ {click_count}")
                                    device.shell(f"input tap {pos[0][0]} {pos[0][1]}")
                                    last_found_time = current_time
                                    time.sleep(0.5)
                                else:
                                    time.sleep(0.3)  # รอสั้นๆ
                        else:
                            # ไม่พบรูป = สำเร็จแล้ว
                            if click_count > 0:
                                print(f"[AUTO_TRADE] {step_name} สำเร็จ!")
                                return True
                            time.sleep(0.3)  # ลดจาก 0.5
                            
                    except Exception as e:
                        time.sleep(0.3)
                
                # หมดเวลา
                if click_count > 0:
                    return True
                print(f"[AUTO_TRADE] ไม่พบ {target_img}")
                return False
            
            # ขั้นตอน 1: sw_buy.png
            if not check_and_click_fast('sw_buy.png', 'sw_buy'):
                print("[AUTO_TRADE] ไม่พบ sw_buy.png - ข้าม")
                return False
            
            time.sleep(0.5)  # ลดจาก 1 วินาที
            
            # ขั้นตอน 2: sw_buy1.png
            if not check_and_click_fast('sw_buy1.png', 'sw_buy1'):
                print("[AUTO_TRADE] ไม่พบ sw_buy1.png - ข้าม")
                return False
            
            time.sleep(0.5)  # ลดจาก 1 วินาที
            
            # ขั้นตอน 3: sw_buy2.png
            if check_and_click_fast('sw_buy2.png', 'sw_buy2'):
                print("[AUTO_TRADE] ซื้อสำเร็จ!")
                time.sleep(1)  # ลดจาก 2 วินาที
                return True
            
            # ไม่พบ sw_buy2 แต่ผ่านขั้นตอนก่อนหน้า = สำเร็จ
            print("[AUTO_TRADE] ซื้อสำเร็จ (ไม่พบ sw_buy2)")
            return True
            
        except Exception as e:
            print(f"[AUTO_TRADE] Error: {e}")
            return False

    def check_and_click_event():
        try:
            cap = device.screencap()
            img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
            event_pos = ImgSearchADB(img, 'img/event.png')
            if event_pos:
                print("[AUTO_TRADE] กด event.png")
                device.shell(f"input tap {event_pos[0][0]} {event_pos[0][1]}")
                time.sleep(3)
                return True
            return False
        except Exception as e:
            print(f"[AUTO_TRADE] เกิดข้อผิดพลาดในการเช็ค event: {e}")
            return False

    try:
        check_and_click_event()

        print("\n[AUTO_TRADE] กำลังค้นหา swap_shop.png...")
        swap_shop_found = False
        for attempt in range(3):  # ลดจาก 5 เป็น 3
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            swap_shop_pos = ImgSearchADB(adb_img, 'img/swap_shop.png')
            if swap_shop_pos:
                print("[AUTO_TRADE] พบและกด swap_shop.png")
                device.shell(f"input tap {swap_shop_pos[0][0]} {swap_shop_pos[0][1]}")
                swap_shop_found = True
                time.sleep(1.5)  # ลดจาก 3 เป็น 1.5
                break
            print(f"[AUTO_TRADE] ไม่พบ swap_shop.png ครั้งที่ {attempt + 1}")
            time.sleep(0.5)  # ลดจาก 2 เป็น 0.5

        if swap_shop_found:
            print("\n[AUTO_TRADE] กำลังรอ waitsawpshop.png... (ไม่มี timeout)")
            wait_count = 0
            
            while True:  # รอไปเรื่อยๆ ไม่มี timeout
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                # ⭐ เช็ค fixid ตลอดเวลาในขณะรอ waitsawpshop
                fixid_pos = ImgSearchADB(adb_img, 'img/fixid.png')
                if fixid_pos:
                    print(f"[AUTO_TRADE] ⚠️ พบ fixid.png ขณะรอหน้าร้าน! Backup ไป backupxml และเริ่ม first_loop ใหม่...")
                    if backup_to_backupxml(device):
                        print(f"[AUTO_TRADE] ✅ Backup ไป backupxml สำเร็จ")
                    clear_app(device)
                    time.sleep(6)
                    return "restart_with_new_file"
                
                wait_pos = ImgSearchADB(adb_img, 'img/waitsawpshop.png')
                if wait_pos:
                    print("[AUTO_TRADE] พบ waitsawpshop.png - เริ่มกระบวนการซื้อ")
                    time.sleep(1)
                    break
                
                wait_count += 1
                if wait_count % 10 == 0:  # แสดงสถานะทุก 10 รอบ
                    print(f"[AUTO_TRADE] ยังรอหน้าร้านอยู่... ({wait_count} รอบ)")
                time.sleep(0.5)

            shops = [
                ('swap_shop1.png', config['swap_shop1']),
                ('swap_shopkom9star.png', config['swap_shopkom9star']),
                ('swap_shop2.png', config['swap_shop2']),
                ('swap_shopkom.png', config['swap_shopkom'])
            ]
            
            for shop_img, max_purchases in shops:
                if max_purchases <= 0:
                    continue
                    
                print(f"\n[AUTO_TRADE] เริ่มการซื้อ {shop_img} จำนวน {max_purchases} ครั้ง")
                purchases = 0
                
                while purchases < max_purchases:
                    # ⭐ เช็ค fixid ก่อนทุกรอบการซื้อ
                    try:
                        cap_check = device.screencap()
                        img_check = cv2.imdecode(np.frombuffer(cap_check, dtype=np.uint8), cv2.IMREAD_COLOR)
                        fixid_pos = ImgSearchADB(img_check, 'img/fixid.png')
                        if fixid_pos:
                            print(f"[AUTO_TRADE] ⚠️ พบ fixid.png ในรอบซื้อ! Backup ไป backupxml และเริ่ม first_loop ใหม่...")
                            if backup_to_backupxml(device):
                                print(f"[AUTO_TRADE] ✅ Backup ไป backupxml สำเร็จ")
                            clear_app(device)
                            time.sleep(6)
                            return "restart_with_new_file"
                    except Exception as e:
                        print(f"[AUTO_TRADE] Error checking fixid: {e}")
                    
                    # ขั้นตอนที่ 1: กลับไปหน้า event และเข้า swap shop ใหม่ทุกครั้ง
                    print(f"[AUTO_TRADE] กำลังกลับไปหน้า swap shop...")
                    
                    # กด event.png
                    event_found = False
                    for ev_attempt in range(3):  # ลดจาก 5 เป็น 3
                        cap = device.screencap()
                        adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                        
                        # ⭐ เช็ค fixid ในขณะหา event.png
                        fixid_pos = ImgSearchADB(adb_img, 'img/fixid.png')
                        if fixid_pos:
                            print(f"[AUTO_TRADE] ⚠️ พบ fixid.png! Backup ไป backupxml และเริ่ม first_loop ใหม่...")
                            if backup_to_backupxml(device):
                                print(f"[AUTO_TRADE] ✅ Backup ไป backupxml สำเร็จ")
                            clear_app(device)
                            time.sleep(6)
                            return "restart_with_new_file"
                        
                        event_pos = ImgSearchADB(adb_img, 'img/event.png')
                        if event_pos:
                            print("[AUTO_TRADE] กด event.png")
                            device.shell(f"input tap {event_pos[0][0]} {event_pos[0][1]}")
                            event_found = True
                            time.sleep(1)  # ลดจาก 2 เป็น 1
                            break
                        time.sleep(0.3)  # ลดจาก 1 เป็น 0.3
                    
                    if not event_found:
                        print("[AUTO_TRADE] ไม่พบ event.png - ลองต่อไป")
                    
                    # กด swap_shop.png เพื่อเข้าหน้าร้าน
                    shop_entered = False
                    for ss_attempt in range(3):  # ลดจาก 5 เป็น 3
                        cap = device.screencap()
                        adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                        swap_shop_pos = ImgSearchADB(adb_img, 'img/swap_shop.png')
                        if swap_shop_pos:
                            print("[AUTO_TRADE] กด swap_shop.png")
                            device.shell(f"input tap {swap_shop_pos[0][0]} {swap_shop_pos[0][1]}")
                            shop_entered = True
                            time.sleep(1.5)  # ลดจาก 3 เป็น 1.5
                            break
                        time.sleep(0.3)  # ลดจาก 1 เป็น 0.3
                    
                    if not shop_entered:
                        print("[AUTO_TRADE] ไม่พบ swap_shop.png - ลองต่อไป")
                    
                    # รอให้หน้าร้านโหลด (waitsawpshop.png) - ไม่มี timeout
                    shop_ready = False
                    inner_wait_count = 0
                    while True:  # รอไปเรื่อยๆ ไม่มี timeout
                        cap = device.screencap()
                        adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                        
                        # ⭐ เช็ค fixid ในขณะรอหน้าร้าน (inner loop)
                        fixid_pos = ImgSearchADB(adb_img, 'img/fixid.png')
                        if fixid_pos:
                            print(f"[AUTO_TRADE] ⚠️ พบ fixid.png ขณะรอหน้าร้าน (inner)! Backup ไป backupxml และเริ่ม first_loop ใหม่...")
                            if backup_to_backupxml(device):
                                print(f"[AUTO_TRADE] ✅ Backup ไป backupxml สำเร็จ")
                            clear_app(device)
                            time.sleep(6)
                            return "restart_with_new_file"
                        
                        wait_pos = ImgSearchADB(adb_img, 'img/waitsawpshop.png')
                        if wait_pos:
                            print("[AUTO_TRADE] หน้าร้านพร้อมแล้ว")
                            shop_ready = True
                            time.sleep(0.5)
                            break
                        inner_wait_count += 1
                        if inner_wait_count % 10 == 0:
                            print(f"[AUTO_TRADE] รอหน้าร้าน... ({inner_wait_count} รอบ)")
                        time.sleep(0.3)
                    
                    # ขั้นตอนที่ 2: ค้นหาปุ่มร้านที่ต้องการซื้อ (ลอง 5 ครั้ง)
                    shop_found = False
                    shop_pos = None
                    for find_attempt in range(5):  # ลดจาก 10 เป็น 5
                        cap = device.screencap()
                        adb_img = cv2.imdecode(np.frombuffer(cap, dtype=np.uint8), cv2.IMREAD_COLOR)
                        shop_pos = ImgSearchADB(adb_img, f'img/{shop_img}')
                        if shop_pos:
                            shop_found = True
                            print(f"[AUTO_TRADE] พบ {shop_img}")
                            break
                        print(f"[AUTO_TRADE] ค้นหา {shop_img} ({find_attempt + 1}/5)")
                        time.sleep(0.3)  # ลดจาก 1 เป็น 0.3
                    
                    if not shop_found:
                        print(f"[AUTO_TRADE] ไม่พบ {shop_img} - ข้ามไปร้านถัดไป")
                        break
                    
                    # ขั้นตอนที่ 3: ทำการซื้อ
                    if perform_purchase(shop_img, shop_pos):
                        purchases += 1
                        print(f"[AUTO_TRADE] ซื้อสำเร็จ {purchases}/{max_purchases}")
                    else:
                        print(f"[AUTO_TRADE] ซื้อไม่สำเร็จ - ลองใหม่")
                    
                    time.sleep(0.5)  # ลดจาก 2 เป็น 0.5
                
                print(f"[AUTO_TRADE] ซื้อ {shop_img} สำเร็จ {purchases}/{max_purchases} ครั้ง")
                time.sleep(1)
        else:
            print("[AUTO_TRADE] ไม่พบ swap_shop.png - ยกเลิกการซื้อทั้งหมด")

    except Exception as e:
        print(f"\n[AUTO_TRADE] เกิดข้อผิดพลาดในการทำงาน: {e}")
    finally:
        print(f"\n[AUTO_TRADE] จบการทำงาน auto_trade สำหรับอุปกรณ์ {device.serial}")
        clear_app(device)
        time.sleep(5)
        return "complete"


def process_shopgacha(device):
    network_monitor = NetworkMonitor()
    print(f"เริ่มกระบวนการ shop gacha สำหรับอุปกรณ์: {device.serial}")
    
    # ขั้นตอนที่ 1: ค้นหาและกด event.png (รอ 2 วินาที)
    print(f"กำลังค้นหา event.png บนอุปกรณ์ {device.serial}")
    cap = device.screencap()
    image = np.frombuffer(cap, dtype=np.uint8)
    adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
    
    event_pos = ImgSearchADB(adb_img, 'img/event.png')
    if event_pos and len(event_pos) > 0:
        print(f"พบและกด event.png บนอุปกรณ์ {device.serial}")
        device.shell(f"input tap {event_pos[0][0]} {event_pos[0][1]}")
        time.sleep(2)  # รอ 2 วินาที
    else:
        print(f"ไม่พบ event.png - ข้ามไปขั้นตอนถัดไป")
    
    # สถานะการทำงาน
    initial_sequence = ['shopgacha1.png', 'shopgacha2.png']
    loop_sequence = ['shopgacha3.png', 'shopgacha4.png', 'shopgacha5.png', 'shopgacha6.png']
    current_initial_step = 0
    in_loop = False
    
    # เพิ่มตัวแปรสำหรับติดตามการกดซ้ำ
    repeat_counter = {}
    max_repeats = 2
    last_clicked_img = None
    
    # ตัวแปรสำหรับวนกลับไปเช็ค shopgacha2.png หลังจากกด shopgacha5.png
    shopgacha5_clicked = False
    check_shopgacha2_count = 0
    max_check_shopgacha2 = 3  # เช็ค shopgacha2.png สูงสุด 3 รอบ
    
    # เพิ่มตัวแปรสำหรับ timeout
    not_found_count = 0
    max_not_found = 30  # ถ้าไม่พบปุ่มติดต่อกัน 30 ครั้ง (30 วินาที) ให้ออก
    loop_start_time = time.time()
    max_loop_time = 300  # timeout 5 นาที
    
    while True:
        try:
            # ตรวจสอบ timeout
            if time.time() - loop_start_time > max_loop_time:
                print(f"หมดเวลา {max_loop_time} วินาที - ออกจากลูปและ backup ไปที่ random-Fail")
                if backup_failed_game_data(device):
                    print(f"Backup ไปที่ random-Fail สำเร็จ")
                clear_app(device)
                time.sleep(6)
                return "restart"
            
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            network_status = network_monitor.check_network(device, adb_img)
            if network_status == "reset_first_loop":
                return "reset_first_loop"
            if network_status:
                continue
            
            # ⭐ ตรวจสอบ fixid, fixunkown, apple
            critical_error = check_critical_errors(device, adb_img, "process_shopgacha")
            if critical_error:
                return critical_error
            
            # ตรวจสอบ shopgachastop.png ก่อนเสมอ
            shopgachastop_pos = ImgSearchADB(adb_img, 'img/shopgachastop.png')
            if shopgachastop_pos and len(shopgachastop_pos) > 0:
                print(f"พบ shopgachastop.png บนอุปกรณ์ {device.serial}")
                print(f"กำลังทำ backup ไปที่ random-Fail...")
                if backup_failed_game_data(device):
                    print(f"Backup ไปที่ random-Fail สำเร็จ")
                else:
                    print(f"Backup ไปที่ random-Fail ล้มเหลว")
                
                print(f"กำลัง clear app และเริ่มการทำงานใหม่...")
                clear_app(device)
                time.sleep(6)
                return "restart"
            
            # ตรวจสอบ shopgachastop1.png
            shopgachastop1_pos = ImgSearchADB(adb_img, 'img/shopgachastop1.png')
            if shopgachastop1_pos and len(shopgachastop1_pos) > 0:
                print(f"พบ shopgachastop1.png บนอุปกรณ์ {device.serial}")
                print(f"จบการทำงาน - กำลัง clear app และเริ่มการทำงานใหม่...")
                clear_app(device)
                time.sleep(6)
                return "restart"
            
            # ขั้นตอนแรก: ทำตามลำดับ shopgacha1.png -> shopgacha2.png
            if not in_loop:
                if current_initial_step < len(initial_sequence):
                    current_img = initial_sequence[current_initial_step]
                    pos = ImgSearchADB(adb_img, f'img/{current_img}')
                    if pos and len(pos) > 0:
                        print(f"พบและกด {current_img} บนอุปกรณ์ {device.serial}")
                        
                        # ถ้าเป็น shopgacha2.png ให้รอก่อนกด
                        if current_img == 'shopgacha2.png':
                            print(f"รอ 5 วินาทีก่อนกด shopgacha2.png...")
                            time.sleep(5)
                        
                        device.shell(f"input tap {pos[0][0]} {pos[0][1]}")
                        print(f"กด {current_img} แล้ว")
                        
                        current_initial_step += 1
                        last_clicked_img = current_img
                        
                        # รอนานขึ้นหลังจากกด shopgacha2.png
                        if current_img == 'shopgacha2.png':
                            time.sleep(3)
                        else:
                            time.sleep(1)
                        
                        # ตรวจสอบ shopgachastop.png หลังจากกด
                        cap = device.screencap()
                        image = np.frombuffer(cap, dtype=np.uint8)
                        check_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                        
                        # ตรวจสอบทั้ง shopgachastop.png และ shopgachastop1.png
                        shopgachastop_check = ImgSearchADB(check_img, 'img/shopgachastop.png')
                        if shopgachastop_check:
                            print(f"พบ shopgachastop.png หลังจากกด {current_img}")
                            print(f"กำลังทำ backup ไปที่ random-Fail...")
                            if backup_failed_game_data(device):
                                print(f"Backup ไปที่ random-Fail สำเร็จ")
                            print(f"กำลัง clear app และเริ่มการทำงานใหม่...")
                            clear_app(device)
                            time.sleep(6)
                            return "restart"
                        
                        shopgachastop1_check = ImgSearchADB(check_img, 'img/shopgachastop1.png')
                        if shopgachastop1_check:
                            print(f"พบ shopgachastop1.png หลังจากกด {current_img}")
                            print(f"จบการทำงาน - กำลัง clear app และเริ่มการทำงานใหม่...")
                            clear_app(device)
                            time.sleep(6)
                            return "restart"
                    continue
                else:
                    in_loop = True
                    last_clicked_img = None  # รีเซ็ตเมื่อเข้าสู่โหมดวนลูป
            
            # ขั้นตอนที่สอง: วนลูปตามลำดับ
            if in_loop:
                found_any = False
                
                # ถ้ากด shopgacha5.png แล้ว ให้วนกลับไปเช็ค shopgacha2.png ก่อน
                if shopgacha5_clicked and check_shopgacha2_count < max_check_shopgacha2:
                    print(f"วนกลับไปเช็ค shopgacha2.png (รอบที่ {check_shopgacha2_count + 1}/{max_check_shopgacha2})")
                    pos = ImgSearchADB(adb_img, 'img/shopgacha2.png')
                    if pos and len(pos) > 0:
                        print(f"พบและกด shopgacha2.png อีกครั้ง บนอุปกรณ์ {device.serial}")
                        print(f"รอ 5 วินาทีก่อนกด shopgacha2.png...")
                        time.sleep(5)
                        device.shell(f"input tap {pos[0][0]} {pos[0][1]}")
                        print(f"กด shopgacha2.png แล้ว")
                        time.sleep(3)
                        
                        # รีเซ็ตสถานะ
                        shopgacha5_clicked = False
                        check_shopgacha2_count = 0
                        found_any = True
                        not_found_count = 0
                    else:
                        check_shopgacha2_count += 1
                        if check_shopgacha2_count >= max_check_shopgacha2:
                            print(f"ไม่พบ shopgacha2.png หลังจากเช็ค {max_check_shopgacha2} รอบ - ดำเนินการต่อ")
                            shopgacha5_clicked = False
                            check_shopgacha2_count = 0
                    
                    if found_any:
                        time.sleep(0.5)
                        continue
                
                # วนลูปตามปกติ
                for img in loop_sequence:
                    pos = ImgSearchADB(adb_img, f'img/{img}')
                    if pos and len(pos) > 0:
                        # ตรวจสอบการกดซ้ำ
                        if img == last_clicked_img:
                            repeat_counter[img] = repeat_counter.get(img, 0) + 1
                            if repeat_counter[img] >= max_repeats:
                                print(f"พบ {img} ซ้ำเกิน {max_repeats} ครั้ง - ข้ามไปรูปถัดไป")
                                continue
                        else:
                            repeat_counter[img] = 1
                        
                        # ⭐⭐⭐ ก่อนกด shopgacha4.png ให้เช็ค gachaout.png ก่อน 5 วินาที
                        if img == 'shopgacha4.png':
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ shopgacha4 - เช็ค gachaout.png ก่อนกด 5 วินาที")
                            gachaout_check_start = time.time()
                            gachaout_found = False
                            
                            while time.time() - gachaout_check_start < 5:
                                try:
                                    cap_check = device.screencap()
                                    img_check = np.frombuffer(cap_check, dtype=np.uint8)
                                    adb_check = cv2.imdecode(img_check, cv2.IMREAD_COLOR)
                                    
                                    gachaout_pos = ImgSearchADB(adb_check, 'img/gachaout.png')
                                    if gachaout_pos:
                                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ gachaout.png ก่อนกด shopgacha4 - จบการทำงาน shopgacha")
                                        gachaout_found = True
                                        break
                                    time.sleep(0.5)
                                except Exception as e:
                                    print(f"Error เช็ค gachaout ก่อน shopgacha4: {e}")
                                    time.sleep(0.5)
                            
                            if gachaout_found:
                                # จบการทำงาน shopgacha - ไม่กด shopgacha4
                                clear_app(device)
                                time.sleep(6)
                                return "complete"
                            
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ไม่พบ gachaout.png - กด shopgacha4.png ต่อ")
                        
                        print(f"พบและกด {img} บนอุปกรณ์ {device.serial}")
                        device.shell(f"input tap {pos[0][0]} {pos[0][1]}")
                        last_clicked_img = img
                        found_any = True
                        not_found_count = 0  # รีเซ็ตตัวนับเมื่อพบปุ่ม
                        
                        # ถ้ากด shopgacha5.png ให้เปิดสถานะวนกลับไปเช็ค shopgacha2.png
                        if img == 'shopgacha5.png':
                            shopgacha5_clicked = True
                            check_shopgacha2_count = 0
                        
                        time.sleep(2)  # เพิ่มเวลารอให้หน้าจอโหลด
                        
                        # ตรวจสอบ shopgachastop.png หลังจากกดแต่ละปุ่ม
                        cap = device.screencap()
                        image = np.frombuffer(cap, dtype=np.uint8)
                        check_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                        
                        # ตรวจสอบทั้ง shopgachastop.png และ shopgachastop1.png
                        shopgachastop_check = ImgSearchADB(check_img, 'img/shopgachastop.png')
                        if shopgachastop_check:
                            print(f"พบ shopgachastop.png หลังจากกด {img}")
                            print(f"กำลังทำ backup ไปที่ random-Fail...")
                            if backup_failed_game_data(device):
                                print(f"Backup ไปที่ random-Fail สำเร็จ")
                            print(f"กำลัง clear app และเริ่มการทำงานใหม่...")
                            clear_app(device)
                            time.sleep(6)
                            return "restart"
                        
                        shopgachastop1_check = ImgSearchADB(check_img, 'img/shopgachastop1.png')
                        if shopgachastop1_check:
                            print(f"พบ shopgachastop1.png หลังจากกด {img}")
                            print(f"จบการทำงาน - กำลัง clear app และเริ่มการทำงานใหม่...")
                            clear_app(device)
                            time.sleep(6)
                            return "restart"
                        break
                
                if not found_any:
                    not_found_count += 1
                    if not_found_count >= max_not_found:
                        print(f"ไม่พบปุ่มใดในลำดับการวนลูปติดต่อกัน {max_not_found} ครั้ง")
                        print(f"กำลัง backup ไปที่ random-Fail และเริ่มการทำงานใหม่...")
                        if backup_failed_game_data(device):
                            print(f"Backup ไปที่ random-Fail สำเร็จ")
                        clear_app(device)
                        time.sleep(6)
                        return "restart"
                    
                    # แสดงสถานะทุก 5 ครั้ง
                    if not_found_count % 5 == 0:
                        print(f"ไม่พบปุ่มใดในลำดับการวนลูป - ครั้งที่ {not_found_count}/{max_not_found}")
                    
                    last_clicked_img = None  # รีเซ็ตเมื่อไม่พบปุ่มใด
                    repeat_counter.clear()  # ล้างตัวนับการกดซ้ำ
                    time.sleep(1)
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในกระบวนการ shop gacha: {e}")
            time.sleep(1)
    
    return False



def process_swap_shop(device):
    network_monitor = NetworkMonitor()

    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] เริ่ม swap shop - Device: {device.serial}")
    
    # โหลด config สำหรับตรวจสอบ all-in mode และ max-gacha
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
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
    checked_waitgacha = False
    running = True
    first_sequence_position = 0
    second_sequence_position = 0
    gacha_count = 0
    
    last_click_position = None
    last_image_hash = None
    last_image_time = time.time()
    
    stopgacha4_last_seen = None
    stopgacha4_last_position = None
    gachafix_last_seen = None
    
    # ⭐⭐⭐ Flag ใหม่: หลังกด stopgacha4 จะเช็ค gachaout ทุกครั้งก่อนกดปุ่มอื่น
    stopgacha4_clicked = False
    
    gacha3_start_time = None
    gacha3_timeout = 1.5  # ⭐ เพิ่ม timeout จาก 0.1 เป็น 1.5 วินาที
    
    last_gacha1_check = time.time()
    gacha1_check_interval = 15  # ⭐ เพิ่ม interval จาก 10 เป็น 15 วินาที
    current_image_start_time = time.time()
    sequence_timeout = 2.0  # ⭐ เพิ่ม timeout จาก 0.1 เป็น 2 วินาที
    
    # ฟังก์ชันตรวจสอบ gachaout.png หลังกดปุ่ม (ใช้เฉพาะเมื่อ all-in = 0)
    def check_gachaout_after_click(timeout=3):
        """ตรวจสอบ gachaout.png เป็นเวลา 3 วินาทีหลังกดปุ่ม"""
        if all_in_mode:
            return False
            
        start_time = time.time()
        gachaout_found_time = None
        
        while time.time() - start_time < timeout:
            try:
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                gachaout_pos = ImgSearchADB(adb_img, 'img/gachaout.png')
                
                if gachaout_pos:
                    if gachaout_found_time is None:
                        gachaout_found_time = time.time()
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ gachaout.png หลังกดปุ่ม - เริ่มนับเวลา")
                    
                    elapsed = time.time() - gachaout_found_time
                    if elapsed >= 3:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] gachaout.png ค้างครบ 3 วินาที - clear app")
                        clear_app(device)
                        time.sleep(6)
                        return True
                else:
                    if gachaout_found_time is not None:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] gachaout.png หายไป - รีเซ็ต")
                        gachaout_found_time = None
                
                time.sleep(0.8)  # ⭐ เพิ่ม delay จาก 0.2 เป็น 0.8 วินาที
            except Exception as e:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error check gachaout: {e}")
                time.sleep(0.8)  # ⭐ เพิ่ม delay จาก 0.2 เป็น 0.8 วินาที
        
        return False
    
    # ⭐⭐⭐ ฟังก์ชัน PRIORITY เช็ค gachaout ก่อนกดปุ่มใดๆ หลังจากกด stopgacha4
    def priority_check_gachaout(action_name, timeout=8):
        """เช็ค gachaout.png แบบ priority ก่อนกดปุ่ม พร้อม print ละเอียด"""
        nonlocal stopgacha4_clicked
        
        if all_in_mode or not stopgacha4_clicked:
            return False
        
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🔎 [PRIORITY CHECK] ก่อน {action_name} - เช็ค gachaout.png {timeout} วินาที...")
        
        check_start = time.time()
        check_count = 0
        
        while time.time() - check_start < timeout:
            try:
                remaining = timeout - (time.time() - check_start)
                check_count += 1
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 [รอบ {check_count}] กำลังเช็ค gachaout.png... (เหลือ {remaining:.1f} วิ)")
                
                cap = device.screencap()
                img = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(img, cv2.IMREAD_COLOR)
                
                gachaout_pos = ImgSearchADB(adb_img, 'img/gachaout.png')
                if gachaout_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ❌ พบ gachaout.png ก่อน {action_name} - จบ swap_shop ทันที! (ไม่ใช้เพชร)")
                    clear_app(device)
                    time.sleep(6)
                    return True
                
                time.sleep(0.5)
            except Exception as e:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Error เช็ค gachaout: {e}")
                time.sleep(0.5)
        
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ✅ [PRIORITY CHECK] ผ่าน - ไม่พบ gachaout.png ({timeout} วิ) - ปลอดภัยดำเนินการ {action_name}")
        return False
    
    # ⭐⭐⭐⭐⭐ ฟังก์ชันกดปุ่มแบบปลอดภัย - DELAY + เช็ค gachaout หลังทุกการกด!
    def safe_tap(x, y, image_name, delay_before=1, delay_after=2, check_gachaout_time=5):
        """
        กดปุ่มแบบปลอดภัย:
        1. Delay ก่อนกด
        2. กดปุ่ม
        3. Delay หลังกด
        4. เช็ค gachaout เป็นเวลา X วินาที
        
        Returns: 
            "gachaout_found" ถ้าพบ gachaout
            "ok" ถ้าปลอดภัย
        """
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ⏸️ [SAFE TAP] รอ {delay_before} วิ ก่อนกด {image_name}...")
        time.sleep(delay_before)
        
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🔵 [SAFE TAP] กำลังกด: {image_name} ที่ตำแหน่ง ({x}, {y})")
        device.shell(f"input tap {x} {y}")
        
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ⏸️ [SAFE TAP] รอ {delay_after} วิ หลังกด {image_name}...")
        time.sleep(delay_after)
        
        # เช็ค gachaout หลังกดปุ่ม (ถ้าไม่ใช่ all-in mode)
        if not all_in_mode:
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 [SAFE TAP] เช็ค gachaout.png หลังกด {image_name} ({check_gachaout_time} วิ)...")
            
            check_start = time.time()
            check_count = 0
            
            while time.time() - check_start < check_gachaout_time:
                try:
                    remaining = check_gachaout_time - (time.time() - check_start)
                    check_count += 1
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 [SAFE TAP รอบ {check_count}] เช็ค gachaout.png... (เหลือ {remaining:.1f} วิ)")
                    
                    cap = device.screencap()
                    img = np.frombuffer(cap, dtype=np.uint8)
                    adb_check = cv2.imdecode(img, cv2.IMREAD_COLOR)
                    
                    gachaout_pos = ImgSearchADB(adb_check, 'img/gachaout.png')
                    if gachaout_pos:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ❌ [SAFE TAP] พบ gachaout.png หลังกด {image_name}! จบ swap_shop ทันที!")
                        clear_app(device)
                        time.sleep(6)
                        return "gachaout_found"
                    
                    time.sleep(0.5)
                except Exception as e:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ [SAFE TAP] Error: {e}")
                    time.sleep(0.5)
            
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ✅ [SAFE TAP] ผ่าน {check_gachaout_time} วิ - ไม่พบ gachaout.png หลัง {image_name}")
        
        return "ok"
    
    # ✅ ฟังก์ชันตรวจสอบและนับ swapgacha1 (เช็ค poin)
    def check_and_count_swapgacha1():
        """ตรวจสอบ swapgacha1 เป็นเวลา 3 วินาที และนับการสุ่ม"""
        nonlocal gacha_count
        
        if max_gacha <= 0:
            return False  # ถ้าไม่มี max_gacha ให้ข้ามการตรวจสอบ
        
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] รอ 3 วินาทีก่อนตรวจสอบ swapgacha1.png")
        time.sleep(3)
        
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] เริ่มตรวจสอบ swapgacha1.png เป็นเวลา 3 วินาที")
        
        check_start_time = time.time()
        swapgacha1_found = False
        
        while time.time() - check_start_time < 3:
            try:
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                check_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                swapgacha1_pos = ImgSearchADB(check_img, 'img/swapgacha1.png')
                if swapgacha1_pos:
                    if not swapgacha1_found:
                        gacha_count += 1
                        swapgacha1_found = True
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ swapgacha1.png - นับ poin ครั้งที่ {gacha_count}/{max_gacha}")
                        
                        # ✅ ถ้าครบจำนวนให้ส่งสัญญาณกลับ
                        if gacha_count >= max_gacha:
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ครบจำนวนการสุ่ม {max_gacha} ครั้งแล้ว")
                            return "complete_gacha"
                        break
                
                time.sleep(0.2)
            except Exception as e:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error checking swapgacha1.png: {e}")
                break
        
        # ✅ ถ้าไม่พบ swapgacha1.png ก็ข้ามไป ไม่ต้อง clear app
        if not swapgacha1_found:
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ไม่พบ swapgacha1.png ภายใน 3 วินาที - ข้ามไปต่อ")
        
        return False
    
    def check_gacha1(adb_img):
        try:
            gacha1_pos = ImgSearchADB(adb_img, 'img/gacha1.png')
            if gacha1_pos:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] กด gacha1")
                device.shell(f"input tap {gacha1_pos[0][0]} {gacha1_pos[0][1]}")
                time.sleep(1.5)  # ⭐ เพิ่ม delay จาก 0.1 เป็น 1.5 วินาที
                if check_gachaout_after_click():
                    return "restart"
                return True
            return False
        except Exception as e:
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error gacha1: {e}")
            return False
    
    def check_fixbuggacha(adb_img):
        try:
            fixbuggacha_pos = ImgSearchADB(adb_img, 'img/fixbuggacha.png')
            if fixbuggacha_pos:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] กด fixbuggacha")
                device.shell(f"input tap {fixbuggacha_pos[0][0]} {fixbuggacha_pos[0][1]}")
                time.sleep(1.5)  # ⭐ เพิ่ม delay จาก 0.1 เป็น 1.5 วินาที
                if check_gachaout_after_click():
                    return "restart"
                return True
            return False
        except Exception as e:
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error fixbuggacha: {e}")
            return False
    
    def check_hero_images(adb_img):
        hero_mapping = load_hero_mapping()
        hero_images = ['heroo1.png', 'heroo2.png', 'heroo3.png', 'heroo4.png']
        for hero_img in hero_images:
            hero_pos = ImgSearchADB(adb_img, f'img/ranger/{hero_img}')
            if hero_pos:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ {hero_img}")
                return True
        return False

    def get_image_hash(adb_img):
        return hashlib.md5(adb_img.tobytes()).hexdigest()

    def get_channel_position():
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            channels_img_enabled = config.get('channels_img', 0)
            
            if channels_img_enabled == 1:
                return search_gachaslot_image(device)
            else:
                selected_channel = config.get('channel', 'ch2')
                
                if 'channels' not in config or selected_channel not in config['channels']:
                    return None

                channel_pos = config['channels'][selected_channel]
                if not isinstance(channel_pos, list) or len(channel_pos) != 2:
                    return None

                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ช่อง: {selected_channel}")
                    
                if selected_channel in ['ch4', 'ch5']:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] เลื่อนช่อง 5 รอบ")
                    for _ in range(5):
                        device.shell(f"input swipe 852 316 855 116 600")
                        time.sleep(0.2)

                return channel_pos
                
        except Exception as e:
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error config: {e}")
            return None

    cap = device.screencap()
    image = np.frombuffer(cap, dtype=np.uint8)
    adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
    event_pos = ImgSearchADB(adb_img, 'img/event.png')
    if event_pos:
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] กด event")
        device.shell(f"input tap {event_pos[0][0]} {event_pos[0][1]}")
        last_click_position = event_pos[0]
        time.sleep(2)  # ⭐ เพิ่ม delay จาก 0.1 เป็น 2 วินาที
        if check_gachaout_after_click():
            return "restart"
        time.sleep(1)  # ⭐ หน่วงหลังเช็ค gachaout ก่อนกดปุ่มถัดไป
    
    while running:
        try:
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            current_time = time.time()
            
            # ⭐ ตรวจสอบ fixid, fixunkown, apple ก่อนทำอะไร
            critical_error = check_critical_errors(device, adb_img, "process_swap_shop")
            if critical_error:
                return critical_error
            
            # ⭐⭐⭐ เช็ค gachaout.png เป็นอันดับแรกทุกรอบ - เจอปุ๊บจบเลย ป้องกันใช้เพชร!
            if not all_in_mode:
                gachaout_priority_pos = ImgSearchADB(adb_img, 'img/gachaout.png')
                if gachaout_priority_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ❌ พบ gachaout.png - จบ swap_shop ทันที! (ไม่ใช้เพชร)")
                    clear_app(device)
                    time.sleep(6)
                    return "complete"
            
            # ⭐⭐⭐ หลังจาก stopgacha4_clicked = True ให้เช็ค gachaout ต่อเนื่อง 5 วินาที ทุก loop!
            if stopgacha4_clicked and not all_in_mode:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🔴 [CONTINUOUS CHECK] หลัง stopgacha4 - เช็ค gachaout.png 5 วินาที ก่อนทำอะไรต่อ...")
                
                continuous_check_start = time.time()
                continuous_check_count = 0
                found_gachaout_continuous = False
                
                while time.time() - continuous_check_start < 5:
                    remaining = 5 - (time.time() - continuous_check_start)
                    continuous_check_count += 1
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 [CONTINUOUS รอบ {continuous_check_count}] กำลังเช็ค gachaout.png... (เหลือ {remaining:.1f} วิ)")
                    
                    try:
                        cap_continuous = device.screencap()
                        img_continuous = np.frombuffer(cap_continuous, dtype=np.uint8)
                        adb_continuous = cv2.imdecode(img_continuous, cv2.IMREAD_COLOR)
                        
                        gachaout_continuous = ImgSearchADB(adb_continuous, 'img/gachaout.png')
                        if gachaout_continuous:
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ❌ [CONTINUOUS] พบ gachaout.png! - จบ swap_shop ทันที! (ไม่ใช้เพชร)")
                            found_gachaout_continuous = True
                            break
                        
                        time.sleep(0.5)
                    except Exception as e:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ [CONTINUOUS] Error: {e}")
                        time.sleep(0.5)
                
                if found_gachaout_continuous:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🛑 กำลัง clear app เนื่องจากพบ gachaout.png...")
                    clear_app(device)
                    time.sleep(6)
                    return "complete"
                
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ✅ [CONTINUOUS] ผ่าน 5 วิ - ไม่พบ gachaout.png - ปลอดภัยทำงานต่อ")
            
            if network_monitor.check_network(device, adb_img):
                continue
            
            fixunkown_pos = ImgSearchADB(adb_img, 'img/fixunkown.png')
            if fixunkown_pos:
                device.shell(f"input tap 477 349")
                time.sleep(1.5)  # ⭐ เพิ่ม delay จาก 0.1 เป็น 1.5 วินาที
                if check_gachaout_after_click():
                    return "restart"
                time.sleep(1)  # ⭐ หน่วงหลังเช็ค gachaout ก่อนกดปุ่มถัดไป
                continue

            check_result = check_fixbuggacha(adb_img)
            if check_result == "restart":
                return "restart"
            elif check_result:
                last_click_position = None
                continue

            # ตรวจสอบ stopgacha7 ก่อนเสมอ
            stopgacha7_pos = ImgSearchADB(adb_img, 'img/stopgacha7.png')
            if stopgacha7_pos:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ stopgacha7 - จบการทำงาน")
                if not check_hero_images(adb_img):
                    backup_failed_game_data(device)
                clear_app(device)
                time.sleep(2)  # ⭐ เพิ่ม delay จาก 0.1 เป็น 2 วินาที
                return "complete"
            
            gacha3_pos = ImgSearchADB(adb_img, 'img/gacha3.png')
            if gacha3_pos:
                if gacha3_start_time is None:
                    gacha3_start_time = current_time
                else:
                    if current_time - gacha3_start_time >= 0.1:
                        stopgachaok_pos = ImgSearchADB(adb_img, 'img/stopgachaok.png')
                        if stopgachaok_pos:
                            device.shell(f"input tap 480 353")
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] กด gacha3 - เริ่มเช็ค gachaout 5 วินาที ก่อนทำอะไรต่อ")
                            
                            # ⭐⭐⭐ วน loop เช็ค gachaout 5 วินาที ก่อนกดปุ่มอื่น
                            gachaout_check_start = time.time()
                            found_gachaout = False
                            
                            while time.time() - gachaout_check_start < 5:
                                try:
                                    cap_check = device.screencap()
                                    img_check = np.frombuffer(cap_check, dtype=np.uint8)
                                    adb_check = cv2.imdecode(img_check, cv2.IMREAD_COLOR)
                                    
                                    gachaout_pos = ImgSearchADB(adb_check, 'img/gachaout.png')
                                    if gachaout_pos:
                                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ❌ พบ gachaout.png หลัง gacha3 - จบ swap_shop ทันที! (ไม่ใช้เพชร)")
                                        found_gachaout = True
                                        break
                                    time.sleep(0.5)
                                except Exception as e:
                                    print(f"Error เช็ค gachaout หลัง gacha3: {e}")
                                    time.sleep(0.5)
                            
                            if found_gachaout:
                                clear_app(device)
                                time.sleep(6)
                                return "complete"
                            
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ✅ ไม่พบ gachaout หลัง gacha3 (5 วิ) - ทำงานต่อ")
                            time.sleep(1)  # ⭐ หน่วงเพิ่มก่อนวน loop ใหม่
                        gacha3_start_time = None
                        continue  # ⭐⭐⭐ วน loop ใหม่ทันที ไม่ตกไปเช็ครูปอื่น!
            else:
                gacha3_start_time = None
                
            if current_time - last_gacha1_check >= gacha1_check_interval:
                check_result = check_gacha1(adb_img)
                if check_result == "restart":
                    return "restart"
                last_gacha1_check = current_time
                
            if check_hero_images(adb_img):
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ hero - backup")
                if backup_game_data(device):
                    clear_app(device)
                    time.sleep(2)
                    return "backup_complete"
                else:
                    time.sleep(1)
                    continue

            stopgachaok_pos = ImgSearchADB(adb_img, 'img/stopgachaok.png')
            if stopgachaok_pos:
                device.shell(f"input tap 480 353")
                time.sleep(2)  # ⭐ หน่วง 2 วินาทีหลังกด
                # ⭐ เช็ค gachaout นานขึ้น 5 วินาที เพื่อป้องกันใช้เพชร
                if check_gachaout_after_click(timeout=5):
                    return "restart"
                time.sleep(1)  # ⭐ หน่วงเพิ่มหลังเช็ค gachaout
                continue

            # ✅ stopgacha4 - ใช้ safe_tap!
            stopgacha4_pos = ImgSearchADB(adb_img, 'img/stopgacha4.png')
            if stopgacha4_pos:
                # ⭐⭐⭐ SET FLAG ก่อน: หลังจากนี้เช็ค gachaout ทุกครั้ง
                stopgacha4_clicked = True
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🚨 [FLAG SET] stopgacha4_clicked = True")
                
                stopgacha4_last_position = stopgacha4_pos[0]
                stopgacha4_last_seen = current_time
                
                # กดครั้งที่ 1 - ใช้ safe_tap
                result1 = safe_tap(stopgacha4_pos[0][0], stopgacha4_pos[0][1], "stopgacha4 (ครั้งที่ 1)", 
                                   delay_before=1, delay_after=2, check_gachaout_time=5)
                if result1 == "gachaout_found":
                    return "complete"
                
                # กดครั้งที่ 2 - ใช้ safe_tap
                result2 = safe_tap(stopgacha4_pos[0][0], stopgacha4_pos[0][1], "stopgacha4 (ครั้งที่ 2)", 
                                   delay_before=1, delay_after=2, check_gachaout_time=5)
                if result2 == "gachaout_found":
                    return "complete"
                
                # ✅ เช็ค swapgacha1 หลังกด stopgacha4
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 📊 กำลังเช็ค swapgacha1.png (นับ poin)...")
                gacha_result = check_and_count_swapgacha1()
                if gacha_result == "complete_gacha":
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ครบจำนวนการสุ่ม - ส่งไป random-Fail")
                    clear_app(device)
                    time.sleep(2)
                    return "random-Fail"
                
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🔄 วน loop ใหม่ - กลับไปเริ่มต้น loop...")
                continue  # ⭐⭐⭐ วน loop ใหม่ทันที ไม่ตกไปเช็ค stopgacha6!

            # ✅ gachafix + stopgacha6 - ใช้ safe_tap!
            gachafix_pos = ImgSearchADB(adb_img, 'img/gachafix.png')
            if gachafix_pos:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🟡 พบ gachafix.png - เริ่มกระบวนการ stopgacha6...")
                
                # ⭐⭐⭐ เช็ค gachaout 8 วินาทีก่อนกด stopgacha6!
                if priority_check_gachaout("กด gachafix/stopgacha6", timeout=8):
                    return "complete"
                
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ✅ ผ่าน priority check - กำลังค้นหา stopgacha6.png...")
                stopgacha6_pos = ImgSearchADB(adb_img, 'img/stopgacha6.png')
                if stopgacha6_pos:
                    last_click_position = stopgacha6_pos[0]
                    
                    # กดครั้งที่ 1 - ใช้ safe_tap
                    result1 = safe_tap(stopgacha6_pos[0][0], stopgacha6_pos[0][1], "stopgacha6 (ครั้งที่ 1)", 
                                       delay_before=1, delay_after=2, check_gachaout_time=7)
                    if result1 == "gachaout_found":
                        return "complete"
                    
                    # กดครั้งที่ 2 - ใช้ safe_tap
                    result2 = safe_tap(stopgacha6_pos[0][0], stopgacha6_pos[0][1], "stopgacha6 (ครั้งที่ 2)", 
                                       delay_before=1, delay_after=2, check_gachaout_time=7)
                    if result2 == "gachaout_found":
                        return "complete"
                    
                    # ✅ เช็ค swapgacha1 หลังกด stopgacha6
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 📊 กำลังเช็ค swapgacha1.png (นับ poin)...")
                    gacha_result = check_and_count_swapgacha1()
                    if gacha_result == "complete_gacha":
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ครบจำนวนการสุ่ม - ส่งไป random-Fail")
                        clear_app(device)
                        time.sleep(2)
                        return "random-Fail"
                
                gachafix_last_seen = current_time
            
            current_hash = get_image_hash(adb_img)
            if current_hash == last_image_hash:
                if current_time - last_image_time >= 1800:
                    if last_click_position:
                        device.shell(f"input tap {last_click_position[0]} {last_click_position[1]}")
                        time.sleep(1.5)  # ⭐ เพิ่ม delay จาก 0.1 เป็น 1.5 วินาที
                        if check_gachaout_after_click():
                            return "restart"
                        time.sleep(1)  # ⭐ หน่วงหลังเช็ค gachaout ก่อนกดปุ่มถัดไป
                    last_image_time = current_time
            else:
                last_image_hash = current_hash
                last_image_time = current_time
            
            for stop_img in ['stopgacha5.png', 'stopgacha7.png', 'stopgacha8.png']:
                stop_pos = ImgSearchADB(adb_img, f'img/{stop_img}')
                if stop_pos:
                    if not check_hero_images(adb_img):
                        backup_failed_game_data(device)
                    clear_app(device)
                    time.sleep(2)  # ⭐ เพิ่ม delay จาก 0.1 เป็น 2 วินาที
                    return "complete"

            if not found_initial_swap_shop:
                swap_shop_pos = ImgSearchADB(adb_img, 'img/gacha.png')
                if swap_shop_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] กด gacha")
                    device.shell(f"input tap {swap_shop_pos[0][0]} {swap_shop_pos[0][1]}")
                    last_click_position = swap_shop_pos[0]
                    found_initial_swap_shop = True
                    time.sleep(2)  # ⭐ เพิ่ม delay จาก 0.1 เป็น 2 วินาที
                    if check_gachaout_after_click():
                        return "restart"
                    time.sleep(1)  # ⭐ หน่วงหลังเช็ค gachaout ก่อนกดปุ่มถัดไป
                    
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] เริ่มตรวจสอบ waitgacha และ fixnewgacha")
                    
                    start_time = time.time()
                    found_waitgacha = False
                    
                    while True:
                        try:
                            cap = device.screencap()
                            image = np.frombuffer(cap, dtype=np.uint8)
                            check_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                            
                            if not found_waitgacha:
                                waitgacha_pos = ImgSearchADB(check_img, 'img/waitgacha.png')
                                if waitgacha_pos:
                                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ waitgacha - รอตรวจสอบ fixnewgacha")
                                    found_waitgacha = True
                                    start_time = time.time()
                            
                            if found_waitgacha:
                                fixnewgacha_pos = ImgSearchADB(check_img, 'img/fixnewgacha.png')
                                if fixnewgacha_pos:
                                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ fixnewgacha - กดที่ตำแหน่ง [476, 394]")
                                    device.shell(f"input tap 476 394")
                                    checked_waitgacha = True
                                    time.sleep(1.5)  # ⭐ เพิ่ม delay จาก 0.1 เป็น 1.5 วินาที
                                    if check_gachaout_after_click():
                                        return "restart"
                                    time.sleep(1)  # ⭐ หน่วงหลังเช็ค gachaout ก่อนกดปุ่มถัดไป
                                    break
                                
                                if time.time() - start_time > 10:
                                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ครบ 10 วินาที - ไม่พบ fixnewgacha")
                                    checked_waitgacha = True
                                    break
                            
                            time.sleep(0.5)
                            
                        except Exception as e:
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error checking images: {e}")
                            continue
                    
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] เรียก get_channel_position")
                    channel_pos = get_channel_position()
                    if channel_pos and len(channel_pos) == 2:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] กดตำแหน่งช่อง: {channel_pos}")
                        device.shell(f"input tap {channel_pos[0]} {channel_pos[1]}")
                        time.sleep(2)  # ⭐ เพิ่ม delay จาก 0.1 เป็น 2 วินาที
                        if check_gachaout_after_click():
                            return "restart"
                        time.sleep(1)  # ⭐ หน่วงหลังเช็ค gachaout ก่อนกดปุ่มถัดไป
                        
                        # ✅ ถ้า swap_shopevent เปิดให้หยุดที่นี่และให้ process_swap_shopevent ทำงานต่อ
                        if swap_shopevent_enabled:
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] swap_shopevent enabled - ส่งต่อไปยัง process_swap_shopevent")
                            return "swap_shopevent"
                    
                    time.sleep(1.5)  # ⭐ เพิ่ม delay จาก 0.1 เป็น 1.5 วินาที
                    continue

            if not checked_waitgacha:
                wait_pos = ImgSearchADB(adb_img, 'img/waitgacha.png')
                if wait_pos:
                    checked_waitgacha = True
                    time.sleep(1.5)  # ⭐ เพิ่ม delay จาก 0.1 เป็น 1.5 วินาที
                    continue

            if first_sequence_position < 3:
                purchase_sequence = ['stopgacha.png', 'stopgacha1.png', 'stopgacha2.png']
                current_img = purchase_sequence[first_sequence_position]
                
                pos = ImgSearchADB(adb_img, f'img/{current_img}')
                if pos:
                    last_click_position = pos[0]
                    first_sequence_position += 1
                    
                    # ⭐⭐⭐ ใช้ safe_tap แทน device.shell โดยตรง!
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🔄 [FIRST SEQUENCE] พบ {current_img} - ใช้ safe_tap")
                    result = safe_tap(pos[0][0], pos[0][1], f"{current_img} (first_sequence)", 
                                      delay_before=1, delay_after=2, check_gachaout_time=5)
                    if result == "gachaout_found":
                        return "complete"
                    
                    # ✅ เช็ค swapgacha1 หลังกด stopgacha (หรือ stopgacha1, stopgacha2 ทั้งหมด)
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 📊 กำลังเช็ค swapgacha1.png (นับ poin)...")
                    gacha_result = check_and_count_swapgacha1()
                    if gacha_result == "complete_gacha":
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ครบจำนวนการสุ่ม - ส่งไป random-Fail")
                        clear_app(device)
                        time.sleep(2)
                        return "random-Fail"
                    
                    if current_img == 'stopgacha2.png':
                        first_sequence_position = 3
                    continue

            if first_sequence_position >= 3:
                second_sequence = ['stopgacha4.png', 'stopgacha6.png', 'stopgacha2.png']
                current_img = second_sequence[second_sequence_position]
                
                if current_time - current_image_start_time >= sequence_timeout:
                    second_sequence_position = (second_sequence_position + 1) % len(second_sequence)
                    current_image_start_time = current_time
                    continue
                
                pos = ImgSearchADB(adb_img, f'img/{current_img}')
                if pos:
                    last_click_position = pos[0]
                    second_sequence_position = (second_sequence_position + 1) % len(second_sequence)
                    current_image_start_time = current_time
                    
                    # ⭐⭐⭐ ใช้ safe_tap แทน device.shell โดยตรง!
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 🔄 [SECOND SEQUENCE] พบ {current_img} - ใช้ safe_tap")
                    result = safe_tap(pos[0][0], pos[0][1], f"{current_img} (second_sequence)", 
                                      delay_before=1, delay_after=2, check_gachaout_time=5)
                    if result == "gachaout_found":
                        return "complete"
                    
                    # ✅ เช็ค swapgacha1 หลังกด stopgacha (ในลูป second sequence)
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] 📊 กำลังเช็ค swapgacha1.png (นับ poin)...")
                    gacha_result = check_and_count_swapgacha1()
                    if gacha_result == "complete_gacha":
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ครบจำนวนการสุ่ม - ส่งไป random-Fail")
                        clear_app(device)
                        time.sleep(2)
                        return "random-Fail"

            if time.time() % 30 < 1:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Status: {device.serial} - S1:{first_sequence_position}/3, S2:{second_sequence_position}/3, Gacha:{gacha_count}/{max_gacha if max_gacha > 0 else 'unlimited'}")

            if time.time() % 300 < 1:
                gc.collect()
            
        except Exception as e:
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error: {e}")
            time.sleep(2)  # ⭐ เพิ่ม delay หลัง error จาก 0.1 เป็น 2 วินาที
    
    return "complete"


def process_swap_shopevent(device):
    """
    Process swap shop event with proper stages:
    - Stage 1: gachaevent1 -> gachaevent2 -> gachaevent3 -> find gachaevent4 -> click 9 times
    - Stage 2: gachaevent5 -> gachaevent6 -> gachaevent3 loop until stopstep2
    - Stage 3: step3ok -> step3skip -> loop step3loop1/step3loop2 until stopstep2 -> clear app
    """
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] เริ่ม swap shop event - Device: {device.serial}")
    
    try:
        # === STAGE 1: gachaevent1 -> gachaevent2 -> gachaevent3 -> find gachaevent4 -> click 9 times ===
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] === STAGE 1: เริ่ม ===")
        
        # ✅ เช็ค stopstep2.png ตั้งแต่ต้น - ถ้าเจอให้จบเลย
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] เช็ค stopstep2.png ก่อน")
        cap = device.screencap()
        image = np.frombuffer(cap, dtype=np.uint8)
        adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
        stopstep2_pos = ImgSearchADB(adb_img, 'img/stopstep2.png')
        if stopstep2_pos:
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ stopstep2.png - ทำการ clear app และจบเลย")
            clear_app(device)
            time.sleep(2)
            return "gachaevent_stopped_by_stopstep2"
        
        # กด gachaevent1
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ค้นหา gachaevent1")
        for attempt in range(20):
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            # ⭐ ตรวจสอบ fixid, fixunkown, apple
            critical_error = check_critical_errors(device, adb_img, "process_swap_shopevent")
            if critical_error:
                return critical_error
            
            gachaevent1_pos = ImgSearchADB(adb_img, 'img/gachaevent1.png')
            if gachaevent1_pos:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ gachaevent1 - กด")
                device.shell(f"input tap {gachaevent1_pos[0][0]} {gachaevent1_pos[0][1]}")
                time.sleep(1)  # Delay 1 วินาทีหลังจากกด gachaevent1
                
                # ✅ เช็ค stopstep2.png หลังจากกด gachaevent1
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] เช็ค stopstep2.png หลังจากกด gachaevent1")
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                stopstep2_pos = ImgSearchADB(adb_img, 'img/stopstep2.png')
                if stopstep2_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ stopstep2.png - ทำการ clear app และจบเลย")
                    clear_app(device)
                    time.sleep(2)
                    return "gachaevent_stopped_by_stopstep2"
                
                break
            time.sleep(0.5)
        
        # กด gachaevent2
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ค้นหา gachaevent2")
        for attempt in range(20):
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            gachaevent2_pos = ImgSearchADB(adb_img, 'img/gachaevent2.png')
            if gachaevent2_pos:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ gachaevent2 - กด")
                device.shell(f"input tap {gachaevent2_pos[0][0]} {gachaevent2_pos[0][1]}")
                time.sleep(0.5)
                break
            time.sleep(0.5)
        
        # ค้นหา gachaevent3
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ค้นหา gachaevent3")
        for attempt in range(15):
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            gachaevent3_pos = ImgSearchADB(adb_img, 'img/gachaevent3.png')
            if gachaevent3_pos:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ gachaevent3")
                break
            time.sleep(0.5)
        
        # ค้นหา gachaevent4 และกด 20 ครั้ง
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ค้นหา gachaevent4")
        gachaevent4_pos = None
        for attempt in range(20):
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            gachaevent4_pos = ImgSearchADB(adb_img, 'img/gachaevent4.png')
            if gachaevent4_pos:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ gachaevent4 - คลิก 20 ครั้งที่ตำแหน่งเดิม")
                for i in range(20):
                    device.shell(f"input tap {gachaevent4_pos[0][0]} {gachaevent4_pos[0][1]}")
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] คลิก {i+1}/20")
                    time.sleep(0.3)
                break
            time.sleep(0.5)
        
        # ✅ เช็คหา heroevent.png เป็นเวลา 2 วินาที
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] เช็คหา heroevent.png เป็นเวลา 2 วินาที")
        hero_check_start = time.time()
        while time.time() - hero_check_start < 2:
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            heroevent_pos = ImgSearchADB(adb_img, 'img/heroevent.png')
            if heroevent_pos:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ heroevent.png - ทำการ backup")
                # ทำการ backup ที่นี่ถ้าต้องการ
                break
            time.sleep(0.2)
        
        time.sleep(1)
        
        # === STAGE 2: gachaevent5 -> gachaevent6 -> gachaevent3 loop until stopstep2 ===
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] === STAGE 2: เริ่ม ===")
        
        step2_start_time = time.time()
        step2_timeout = 300  # 5 minutes timeout
        step2_sequence = 1  # 1: gachaevent5, 2: gachaevent6, 3: gachaevent3
        gachaevent5_time = None  # ติดตามเวลาที่พบ gachaevent5
        gachaevent3_time = None  # ติดตามเวลาที่พบ gachaevent3
        last_swap_shopgachaevent_check = time.time()  # ติดตามเวลาสุดท้ายที่เช็ค swap_shopgachaevent
        swap_shopgachaevent_interval = random.randint(5, 15)  # สุ่มเช็ค swap_shopgachaevent ทุก 5-15 วิ
        
        while time.time() - step2_start_time < step2_timeout:
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            # ✅ เช็ค swap_shopgachaevent แบบสุ่ม ขนาน
            current_time = time.time()
            if current_time - last_swap_shopgachaevent_check >= swap_shopgachaevent_interval:
                swap_shopgachaevent_pos = ImgSearchADB(adb_img, 'img/swap_shopgachaevent.png')
                if swap_shopgachaevent_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ⚡ พบ swap_shopgachaevent - กด")
                    device.shell(f"input tap {swap_shopgachaevent_pos[0][0]} {swap_shopgachaevent_pos[0][1]}")
                    time.sleep(1)
                
                last_swap_shopgachaevent_check = current_time
                swap_shopgachaevent_interval = random.randint(5, 15)  # สุ่มเช็คใหม่ 5-15 วิ
            
            # ✅ ตรวจสอบ stopstep2 ก่อน - ออกจาก stage 2
            stopstep2_pos = ImgSearchADB(adb_img, 'img/stopstep2.png')
            if stopstep2_pos:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ stopstep2 - จบ Stage 2")
                break
            
            # ✅ ลำดับการเช็ค: gachaevent5 -> gachaevent6 -> gachaevent3 -> วนลูป
            if step2_sequence == 1:
                gachaevent5_pos = ImgSearchADB(adb_img, 'img/gachaevent5.png')
                if gachaevent5_pos:
                    # ติดตามเวลาเมื่อพบ gachaevent5
                    if gachaevent5_time is None:
                        gachaevent5_time = time.time()
                    
                    elapsed_time = time.time() - gachaevent5_time
                    # เช็คว่าค้างครบ 15 วิหรือไม่
                    if elapsed_time >= 15:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ gachaevent5 ค้างมา {elapsed_time:.0f} วิ - กดเพื่อข้าม -> gachaevent6")
                        device.shell(f"input tap {gachaevent5_pos[0][0]} {gachaevent5_pos[0][1]}")
                        step2_sequence = 2
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] รอ 5 วินาทีก่อนเช็ค gachaevent6")
                        time.sleep(5)
                        gachaevent5_time = None  # รีเซ็ต timer
                        continue
                    else:
                        # ยังไม่ครบ 15 วิ ให้กดแบบปกติ
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ gachaevent5 - กด")
                        device.shell(f"input tap {gachaevent5_pos[0][0]} {gachaevent5_pos[0][1]}")
                        step2_sequence = 2
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] รอ 5 วินาทีก่อนเช็ค gachaevent6")
                        time.sleep(5)
                        gachaevent5_time = None  # รีเซ็ต timer
                        continue
                else:
                    # ไม่พบ gachaevent5 ให้รีเซ็ต timer
                    gachaevent5_time = None
            
            elif step2_sequence == 2:
                gachaevent6_pos = ImgSearchADB(adb_img, 'img/gachaevent6.png')
                if gachaevent6_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ gachaevent6 - กด")
                    device.shell(f"input tap {gachaevent6_pos[0][0]} {gachaevent6_pos[0][1]}")
                    step2_sequence = 3
                    time.sleep(0.5)
                    continue
            
            elif step2_sequence == 3:
                gachaevent3_pos = ImgSearchADB(adb_img, 'img/gachaevent3.png')
                if gachaevent3_pos:
                    # ติดตามเวลาเมื่อพบ gachaevent3
                    if gachaevent3_time is None:
                        gachaevent3_time = time.time()
                    
                    elapsed_time = time.time() - gachaevent3_time
                    # เช็คว่าค้างครบ 10 วิหรือไม่
                    if elapsed_time >= 10:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ gachaevent3 ค้างมา {elapsed_time:.0f} วิ - ข้ามไป")
                        step2_sequence = 1  # ข้ามกลับไป gachaevent5
                        gachaevent3_time = None  # รีเซ็ต timer
                        continue
                    else:
                        # ยังไม่ครบ 10 วิ ให้กดแบบปกติ
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ gachaevent3 - กด")
                        device.shell(f"input tap {gachaevent3_pos[0][0]} {gachaevent3_pos[0][1]}")
                        
                        # ✅ เช็คหา heroevent.png เป็นเวลา 2 วินาที
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] เช็คหา heroevent.png เป็นเวลา 2 วินาที")
                        hero_check_start = time.time()
                        while time.time() - hero_check_start < 2:
                            cap = device.screencap()
                            image = np.frombuffer(cap, dtype=np.uint8)
                            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                            
                            heroevent_pos = ImgSearchADB(adb_img, 'img/heroevent.png')
                            if heroevent_pos:
                                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ heroevent.png - ทำการ backup")
                                break
                            time.sleep(0.2)
                        
                        step2_sequence = 1  # วนลูปกลับไป gachaevent5
                        gachaevent3_time = None  # รีเซ็ต timer
                        time.sleep(0.5)
                        continue
                else:
                    # ไม่พบ gachaevent3 ให้รีเซ็ต timer
                    gachaevent3_time = None
            
            time.sleep(0.5)
        
        # ✅ เมื่อพบ stopstep2 ใน Stage 2 → กด step2ok แล้วกด okstop
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] === Stage 2 สิ้นสุด - ค้นหา step2ok ===")
        step2ok_found = False
        for attempt in range(20):
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            step2ok_pos = ImgSearchADB(adb_img, 'img/step2ok.png')
            if step2ok_pos:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ step2ok - กด")
                device.shell(f"input tap {step2ok_pos[0][0]} {step2ok_pos[0][1]}")
                step2ok_found = True
                time.sleep(1)
                break
            time.sleep(0.5)
        
        # ✅ กด okstop เพื่อจบ Stage 2
        if step2ok_found:
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ค้นหา okstop")
            for attempt in range(20):
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                okstop_pos = ImgSearchADB(adb_img, 'img/okstop.png')
                if okstop_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ okstop - กด")
                    device.shell(f"input tap {okstop_pos[0][0]} {okstop_pos[0][1]}")
                    time.sleep(1)
                    break
                time.sleep(0.5)
        
        time.sleep(1)
        
        # === STAGE 3: step3 loop until stopstep2 ===
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] === STAGE 3: เริ่ม ===")
        
        # ✅ เช็ค all-tiket config ว่าควรทำ stage 3 หรือไม่
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            all_tiket = config.get('all-tiket', 1)  # Default = 1 (เปิด)
        except:
            all_tiket = 1  # Default = 1 ถ้าอ่าน config ไม่ได้
        
        if all_tiket == 0:
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] all-tiket = 0 - ข้าม STAGE 3 clear app และจบเลย")
            clear_app(device)
            time.sleep(2)
        else:
            # ✅ กด step3 ก่อน
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ค้นหา step3")
            for attempt in range(20):
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                step3_pos = ImgSearchADB(adb_img, 'img/step3.png')
                if step3_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ step3 - กด")
                    device.shell(f"input tap {step3_pos[0][0]} {step3_pos[0][1]}")
                    time.sleep(1)
                    break
                time.sleep(0.5)
            
            step3_start_time = time.time()
            step3_timeout = 300  # 5 minutes timeout
            step3_sequence = 1  # 1: step3ok, 2: step3skip, 3: loop step3loop1/step3loop2
            step3_loop_toggle = 1  # 1: step3loop1, 2: step3loop2
            stage3_complete = False
            
            while time.time() - step3_start_time < step3_timeout:
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                # ✅ ตรวจสอบ stopstep2 - ออกจาก stage 3 เมื่อเจอ
                stopstep2_pos = ImgSearchADB(adb_img, 'img/stopstep2.png')
                if stopstep2_pos:
                    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ stopstep2 - จบ Stage 3 และเตรียมเคลียร์แอป")
                    stage3_complete = True
                    break
                
                if step3_sequence == 1:
                    step3ok_pos = ImgSearchADB(adb_img, 'img/step3ok.png')
                    if step3ok_pos:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ step3ok - กด")
                        device.shell(f"input tap {step3ok_pos[0][0]} {step3ok_pos[0][1]}")
                        step3_sequence = 2
                        time.sleep(0.5)
                        continue
                
                elif step3_sequence == 2:
                    step3skip_pos = ImgSearchADB(adb_img, 'img/step3skip.png')
                    if step3skip_pos:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ step3skip - กด")
                        device.shell(f"input tap {step3skip_pos[0][0]} {step3skip_pos[0][1]}")
                        step3_sequence = 3
                        time.sleep(0.5)
                        continue
                
                elif step3_sequence == 3:
                    # ✅ ตรวจสอบ stopstep2 ก่อนเสมอในลูป
                    stopstep2_pos = ImgSearchADB(adb_img, 'img/stopstep2.png')
                    if stopstep2_pos:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ stopstep2 - จบ Stage 3 และเตรียมเคลียร์แอป")
                        stage3_complete = True
                        break
                    
                    # ✅ วนลูปกด step3loop1 -> step3loop2 -> step3skip จนเจอ stopstep2
                    if step3_loop_toggle == 1:
                        step3loop1_pos = ImgSearchADB(adb_img, 'img/step3loop1.png')
                        if step3loop1_pos:
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ step3loop1 - รอ 5 วิ ก่อนจะกด")
                            time.sleep(5)
                            # ✅ Capture image ใหม่และเช็ค stopstep2 ก่อนกด
                            cap = device.screencap()
                            image = np.frombuffer(cap, dtype=np.uint8)
                            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                            stopstep2_pos = ImgSearchADB(adb_img, 'img/stopstep2.png')
                            if stopstep2_pos:
                                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ stopstep2 - จบ Stage 3")
                                stage3_complete = True
                                break
                            step3loop1_pos = ImgSearchADB(adb_img, 'img/step3loop1.png')
                            if step3loop1_pos:
                                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] กด step3loop1")
                                device.shell(f"input tap {step3loop1_pos[0][0]} {step3loop1_pos[0][1]}")
                            step3_loop_toggle = 2
                            time.sleep(0.3)
                            continue
                    elif step3_loop_toggle == 2:
                        step3loop2_pos = ImgSearchADB(adb_img, 'img/step3loop2.png')
                        if step3loop2_pos:
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ step3loop2 - รอ 8 วิ ก่อนจะกด")
                            time.sleep(8)
                            # ✅ Capture image ใหม่และเช็ค stopstep2 ก่อนกด
                            cap = device.screencap()
                            image = np.frombuffer(cap, dtype=np.uint8)
                            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                            stopstep2_pos = ImgSearchADB(adb_img, 'img/stopstep2.png')
                            if stopstep2_pos:
                                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ stopstep2 - จบ Stage 3")
                                stage3_complete = True
                                break
                            step3loop2_pos = ImgSearchADB(adb_img, 'img/step3loop2.png')
                            if step3loop2_pos:
                                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] กด step3loop2")
                                device.shell(f"input tap {step3loop2_pos[0][0]} {step3loop2_pos[0][1]}")
                            step3_loop_toggle = 1  # สลับกลับไปหา step3loop1
                            time.sleep(0.3)
                            continue
                    elif step3_loop_toggle == 3:
                        step3skip_pos = ImgSearchADB(adb_img, 'img/step3skip.png')
                        if step3skip_pos:
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ step3skip - กด")
                            device.shell(f"input tap {step3skip_pos[0][0]} {step3skip_pos[0][1]}")
                            step3_loop_toggle = 1  # วนลูปกลับไปที่ step3loop1
                            time.sleep(0.3)
                            continue
                    
                    time.sleep(0.5)
            
            # ✅ Clear app เฉพาะเมื่อพบ stopstep2 (เมื่อเปิด all-tiket)
            if stage3_complete:
                print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] === สิ้นสุด swap shop event - ทำการ clear app ===")
                clear_app(device)
                time.sleep(2)
        
        # ✅ ถ้า all-tiket = 0 ให้ clear app แล้วจบเลย (ไม่ทำ stage 3)
        if all_tiket == 0:
            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] all-tiket = 0 - clear app และจบการทำงาน")
            clear_app(device)
            time.sleep(2)
        
        return "swap_shopevent_complete"
        
    except Exception as e:
        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Error in process_swap_shopevent: {e}")
        try:
            clear_app(device)
        except:
            pass
        return "swap_shopevent_error"


def check_black_screen(adb_img, threshold=0.8):
    try:
        if adb_img is None:
            return False
        
        gray = cv2.cvtColor(adb_img, cv2.COLOR_BGR2GRAY)
        mean_brightness = np.mean(gray)
        is_black = mean_brightness < (255 * threshold / 100)
        
        return is_black
    except Exception:
        return False



def main_login(device):
    """ฟังก์ชันจัดการ login พร้อมตรวจสอบ fixcak.png"""
    print(f"เริ่มการล็อกอินสำหรับอุปกรณ์: {device.serial}")
    
    stoplogin_count = 0
    fixbug_timer = None
    no_image_timer = None
    fixid_count = 0
    back_press_mode = False
    black_screen_timer = None
    
    fixling_start_time = None
    fixling_timeout = 15
    
    # ⭐ เพิ่ม timer สำหรับ fixid ค้าง
    fixid_timer = None
    fixid_timeout = 20  # ถ้า fixid ค้างเกิน 20 วินาที → backup กลับ backupxml
    
    # ⭐ เพิ่ม timer สำหรับ fixunkown ค้าง
    fixunkown_timer = None
    fixunkown_timeout = 20  # ถ้า fixunkown ค้างเกิน 20 วินาที → backup กลับ backupxml
    fixunkown_count = 0
    
    last_image = None
    repeat_count = {}
    max_repeat = 3
    
    def check_fixling_and_clear(adb_img):
        nonlocal fixling_start_time
        
        fixling_pos = ImgSearchADB(adb_img, 'img/fixling.png')
        current_time = time.time()
        
        if fixling_pos:
            if fixling_start_time is None:
                fixling_start_time = current_time
                print(f"พบ fixling.png บนอุปกรณ์ {device.serial} - เริ่มนับเวลา {fixling_timeout} วินาที")
            else:
                elapsed_time = current_time - fixling_start_time
                if elapsed_time >= fixling_timeout:
                    print(f"พบ fixling.png ค้างนานเกิน {fixling_timeout} วินาที บนอุปกรณ์ {device.serial}")
                    print(f"กำลัง clear app และเริ่มขั้นตอน login ใหม่...")
                    clear_app(device)
                    time.sleep(6)
                    fixling_start_time = None
                    return True
                else:
                    remaining_time = fixling_timeout - elapsed_time
                    if int(elapsed_time) % 3 == 0:
                        print(f"fixling.png ค้างมาแล้ว {elapsed_time:.1f} วินาที - เหลือเวลาอีก {remaining_time:.1f} วินาที")
        else:
            if fixling_start_time is not None:
                print(f"ไม่พบ fixling.png แล้ว - รีเซ็ตการนับเวลา")
                fixling_start_time = None
        
        return False
    
    while True:
        try:
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            if check_fixling_and_clear(adb_img):
                print(f"Restarting login process due to fixling timeout on device {device.serial}")
                continue
            
            found_any_image = False
            current_image = None

            if check_black_screen(adb_img, threshold=0.8):
                if black_screen_timer is None:
                    black_screen_timer = time.time()
                    print(f"{Fore.YELLOW}[DEVICE {device.serial}] Black screen detected, starting timer...{Style.RESET_ALL}")
                else:
                    elapsed = time.time() - black_screen_timer
                    if elapsed >= 8:
                        print(f"{Fore.RED}[DEVICE {device.serial}] Black screen > 8s, clearing app and restarting...{Style.RESET_ALL}")
                        clear_app(device)
                        time.sleep(3)
                        device.shell("am start -n com.linecorp.LGRGS/com.linecorp.common.activity.LineActivity")
                        time.sleep(2)
                        black_screen_timer = None
                        continue
            else:
                black_screen_timer = None

            # ตรวจสอบ stoplogin
            stoplogin_pos = ImgSearchADB(adb_img, 'img/stoplogin.png')
            if stoplogin_pos:
                found_any_image = True
                stoplogin_count += 1
                print(f"พบ stoplogin บนอุปกรณ์ {device.serial} - ครั้งที่: {stoplogin_count}")
                if stoplogin_count >= 1:
                    print(f"ล็อกอินสำเร็จสำหรับอุปกรณ์ {device.serial}")
                    return "normal_complete"
                continue

            # ตรวจสอบ apple.png (Special Event) ใน main_login
            apple_pos = ImgSearchADB(adb_img, 'img/apple.png')
            if apple_pos:
                found_any_image = True
                print(f"[DEVICE {device.serial}] Found apple.png! Moving XML to login-fail and restarting loop 1...")
                
                # ส่งไฟล์ไป login-fail (ถือว่าเป็นไฟล์เสีย)
                if backup_failed_login(device):
                    print(f"[DEVICE {device.serial}] XML moved to login-fail successfully")
                else:
                    print(f"[DEVICE {device.serial}] Failed to move XML to login-fail")

                clear_app(device)
                time.sleep(6)
                return "restart_loop1"

            # ตรวจสอบ alert1
            alert1_pos = ImgSearchADB(adb_img, 'img/alert1.png')
            if alert1_pos:
                found_any_image = True
                current_image = 'alert1.png'
                print(f"พบ alert1.png บนอุปกรณ์ {device.serial}")
                clear_app(device)
                time.sleep(1)
                continue

            # ตรวจสอบ alert3
            alert3_pos = ImgSearchADB(adb_img, 'img/alert3.png')
            if alert3_pos:
                found_any_image = True
                clear_app(device)
                time.sleep(0.2)
                continue

            # *** ตรวจสอบ fixcak.png แยกต่างหาก - ให้ clear app และ restart loop1 ***
            fixcak_pos = ImgSearchADB(adb_img, 'img/fixcak.png')
            if fixcak_pos:
                found_any_image = True
                current_image = 'fixcak.png'
                print(f"พบ fixcak.png บนอุปกรณ์ {device.serial}")
                print(f"กำลัง clear app และ reset กลับไปเริ่ม loop1 ใหม่...")
                clear_app(device)
                time.sleep(6)
                return "restart_loop1"

            # ⭐ ตรวจสอบ fixid - เจอปุ๊บทำงานทันที!
            fixid_pos = ImgSearchADB(adb_img, 'img/fixid.png')
            if fixid_pos:
                found_any_image = True
                current_image = 'fixid.png'
                print(f"⚠️ พบ fixid.png บนอุปกรณ์ {device.serial} - ทำงานทันที!")
                print(f"กำลัง backup ไฟล์กลับไป backupxml เพื่อวนเข้าใหม่...")
                
                # Backup ไฟล์กลับไป backupxml
                if backup_to_backupxml(device):
                    print(f"✅ Backup ไป backupxml สำเร็จ - ไฟล์จะถูกนำมาวนเข้าใหม่")
                else:
                    print(f"❌ Backup ไป backupxml ล้มเหลว")
                
                # Clear app และ restart with new file
                clear_app(device)
                time.sleep(6)
                # ⭐ return ทันทีเพื่อไปหยิบไฟล์ใหม่และเริ่ม first_loop ใหม่
                return "restart_with_new_file"

            # ⭐ ตรวจสอบ fixunkown.png (ค้างเกิน 20 วิ → backup กลับ backupxml)
            fixunkown_pos = ImgSearchADB(adb_img, 'img/fixunkown.png')
            if fixunkown_pos:
                found_any_image = True
                current_image = 'fixunkown.png'
                fixunkown_count += 1
                
                # เริ่มจับเวลาถ้ายังไม่ได้เริ่ม
                if fixunkown_timer is None:
                    fixunkown_timer = time.time()
                    print(f"พบ fixunkown บนอุปกรณ์ {device.serial} - เริ่มจับเวลา (timeout: {fixunkown_timeout} วิ)")
                else:
                    elapsed_fixunkown = time.time() - fixunkown_timer
                    print(f"พบ fixunkown บนอุปกรณ์ {device.serial} - ครั้งที่: {fixunkown_count} (ค้าง: {elapsed_fixunkown:.1f}/{fixunkown_timeout} วิ)")
                    
                    # ถ้า fixunkown ค้างเกิน 20 วินาที → backup กลับ backupxml และ restart first_loop
                    if elapsed_fixunkown >= fixunkown_timeout:
                        print(f"⚠️ fixunkown.png ค้างนานเกิน {fixunkown_timeout} วินาที บนอุปกรณ์ {device.serial}")
                        print(f"กำลัง backup ไฟล์กลับไป backupxml เพื่อวนเข้าใหม่...")
                        
                        # Backup ไฟล์กลับไป backupxml
                        if backup_to_backupxml(device):
                            print(f"✅ Backup ไป backupxml สำเร็จ - ไฟล์จะถูกนำมาวนเข้าใหม่")
                        else:
                            print(f"❌ Backup ไป backupxml ล้มเหลว")
                        
                        # Clear app และ restart with new file
                        clear_app(device)
                        time.sleep(6)
                        # ⭐ ใช้ return value ใหม่เพื่อบอกให้หยิบไฟล์ใหม่ก่อนเริ่ม first_loop
                        return "restart_with_new_file"
            else:
                # ถ้าไม่พบ fixunkown → รีเซ็ต timer
                fixunkown_timer = None

            fixbug_pos = ImgSearchADB(adb_img, 'img/fixbuglogin.png')
            if fixbug_pos:
                found_any_image = True
                current_image = 'fixbuglogin.png'
                if fixbug_timer is None:
                    fixbug_timer = time.time()
                    print(f"พบ fixbuglogin บนอุปกรณ์ {device.serial} เริ่มนับเวลา 15 วินาที")
                else:
                    elapsed_time = time.time() - fixbug_timer
                    if elapsed_time >= 15:
                        print(f"เจอ fixbuglogin นานเกิน 15 วินาที กำลังเคลียร์แอปบนอุปกรณ์ {device.serial}")
                        clear_app(device)
                        time.sleep(6)
                        fixbug_timer = None
                    else:
                        print(f"พบ fixbuglogin บนอุปกรณ์ {device.serial} - เหลือเวลาอีก {15 - elapsed_time:.1f} วินาที")
            else:
                fixbug_timer = None

            # ตรวจสอบ alert2
            alert2_pos = ImgSearchADB(adb_img, 'img/alert2.png')
            if alert2_pos:
                found_any_image = True
                current_image = 'alert2.png'
                if fixbug_timer is None:
                    fixbug_timer = time.time()
                    print(f"พบ alert2 บนอุปกรณ์ {device.serial} เริ่มนับเวลา 15 วินาที")
                else:
                    elapsed_time = time.time() - fixbug_timer
                    if elapsed_time >= 15:
                        print(f"เจอ alert2 นานเกิน 15 วินาที กำลังเคลียร์แอปบนอุปกรณ์ {device.serial}")
                        clear_app(device)
                        time.sleep(6)
                        fixbug_timer = None
                    else:
                        print(f"พบ alert2 บนอุปกรณ์ {device.serial} - เหลือเวลาอีก {15 - elapsed_time:.1f} วินาที")
            else:
                fixbug_timer = None

            # ตรวจสอบ refresh
            refresh_pos = ImgSearchADB(adb_img, 'img/refresh.png')
            if refresh_pos:
                found_any_image = True
                current_image = 'refresh.png'
                
                if current_image == last_image:
                    repeat_count['refresh'] = repeat_count.get('refresh', 0) + 1
                    if repeat_count['refresh'] >= max_repeat:
                        print(f"พบ refresh.png ซ้ำเกิน {max_repeat} ครั้ง - ข้ามไปตรวจสอบรูปอื่น")
                        repeat_count['refresh'] = 0
                        time.sleep(1)
                        continue
                else:
                    repeat_count['refresh'] = 1

                print(f"พบ 'refresh.png' บนอุปกรณ์ {device.serial} ที่ตำแหน่ง: {refresh_pos[0][0]}, {refresh_pos[0][1]}")
                device.shell(f"input tap {refresh_pos[0][0]} {refresh_pos[0][1]}")
                time.sleep(1)

                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                check_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                check_pos = ImgSearchADB(check_img, 'img/check.png')
                if check_pos:
                    print(f"พบ 'check.png' หลังจากกด refresh บนอุปกรณ์ {device.serial}")
                    device.shell(f"input tap {check_pos[0][0]} {check_pos[0][1]}")
                    time.sleep(1)
                no_image_timer = None

            # ตรวจสอบ link sequence
            link_result = process_link_sequence(device, adb_img)
            if link_result == "restart_link":
                print(f"พบ fixling.png ค้างเกิน 15 วินาที ใน link sequence - เริ่มขั้นตอน link ใหม่บนอุปกรณ์ {device.serial}")
                found_any_image = True
                current_image = 'fixling_restart'
                no_image_timer = None
            elif link_result:
                found_any_image = True
                current_image = 'link_sequence'
                no_image_timer = None

            # ⭐ ตรวจสอบ event - กดก่อนเสมอ แล้วค่อยกด BACK รัวๆ
            event_pos = ImgSearchADB(adb_img, 'img/event.png')
            if event_pos:
                found_any_image = True
                current_image = 'event.png'
                print(f"พบ 'event.png' บนอุปกรณ์ {device.serial} ที่ตำแหน่ง: {event_pos[0][0]}, {event_pos[0][1]}")
                
                # ⭐ กด event.png ก่อนเสมอ
                device.shell(f"input tap {event_pos[0][0]} {event_pos[0][1]}")
                print(f"กด event.png เรียบร้อยแล้ว รอ 1 วินาที...")
                time.sleep(1)
                no_image_timer = None
                
                # ⭐ เริ่มกด BACK รัวๆ จนเจอ cancel.png
                back_press_mode = True
                back_press_count = 0
                
                print(f"เริ่มกด BACK รัวๆ จนกว่าจะเจอ cancel.png...")
                while back_press_mode:
                    # กด BACK ก่อน (รัวๆ)
                    device.shell("input keyevent KEYCODE_BACK")
                    back_press_count += 1
                    print(f"กด BACK ครั้งที่ {back_press_count} บนอุปกรณ์ {device.serial}")
                    time.sleep(0.3)  # รอสั้นๆ ระหว่างการกด BACK
                    
                    # ค่อยตรวจสอบว่าเจอ cancel.png หรือยัง
                    cap = device.screencap()
                    image = np.frombuffer(cap, dtype=np.uint8)
                    check_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                    
                    cancel_pos = ImgSearchADB(check_img, 'img/cancel.png')
                    if cancel_pos:
                        print(f"✓ พบ 'cancel.png' หลังจากกด BACK {back_press_count} ครั้ง บนอุปกรณ์ {device.serial}")
                        device.shell(f"input tap {cancel_pos[0][0]} {cancel_pos[0][1]}")
                        back_press_mode = False
                        time.sleep(1)
                        break

            # ตรวจสอบรูปภาพทั่วไป (ลบ fixcak.png ออกแล้ว)
            general_images = [
                ('ok.png', 'ok'),('fixnet.png', 'fixnet'),
                ('fixplay.png', 'fixplay'),('oknet.png', 'oknet'),('fixalerterror1.png','fixalerterror1'),
                ('check.png', 'check'), ('closeapp.png', 'closeapp'),
                ('okwhite.png', 'okwhite'), ('fixback.png', 'fixback'),
                ('fixout.png', 'fixout'), ('fixok.png', 'fixok')
            ]

            for img_name, img_key in general_images:
                pos_adb = ImgSearchADB(adb_img, f'img/{img_name}')
                if pos_adb:
                    found_any_image = True
                    current_image = img_name
                    
                    if current_image == last_image:
                        repeat_count[img_key] = repeat_count.get(img_key, 0) + 1
                        if repeat_count[img_key] >= max_repeat:
                            print(f"พบ {img_name} ซ้ำเกิน {max_repeat} ครั้ง - ข้ามไปตรวจสอบรูปอื่น")
                            repeat_count[img_key] = 0
                            continue
                    else:
                        repeat_count[img_key] = 1
                    
                    print(f"พบ '{img_name}' บนอุปกรณ์ {device.serial} ที่ตำแหน่ง: {pos_adb[0][0]}, {pos_adb[0][1]}")
                    device.shell(f"input tap {pos_adb[0][0]} {pos_adb[0][1]}")
                    no_image_timer = None
                    time.sleep(1)
                    break

            last_image = current_image

            # จัดการกรณีไม่พบรูปภาพใดๆ
            if not found_any_image:
                if no_image_timer is None:
                    no_image_timer = time.time()
                    print(f"ไม่พบรูปภาพใดๆ บนอุปกรณ์ {device.serial} เริ่มนับเวลา 800 วินาที")
                else:
                    elapsed_time = time.time() - no_image_timer
                    if elapsed_time >= 800:
                        print(f"ไม่พบรูปภาพใดๆ นานเกิน 800 วินาที กำลังเคลียร์แอปบนอุปกรณ์ {device.serial}")
                        clear_app(device)
                        no_image_timer = None
                    else:
                        if int(elapsed_time) % 30 == 0:
                            print(f"ไม่พบรูปภาพใดๆ บนอุปกรณ์ {device.serial} - เหลือเวลาอีก {800 - elapsed_time:.1f} วินาที")
            else:
                no_image_timer = None
            
            time.sleep(1)
            
        except Exception as e:
            print(f"เกิดข้อผิดพลาด: {e}")
            time.sleep(1)
    
    return False



def load_hero_mapping():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        hero_mapping = config.get('HERO_MAPPING', {})
        
        if not hero_mapping:
            print("ไม่พบการตั้งค่า HERO_MAPPING ใน config.json - ใช้ค่าเริ่มต้น")
            return {
                'heroo1.png': 'Denji',
                'heroo2.png': 'DenjiU',
                'heroo3.png': 'Power',
                'heroo4.png': 'PowerU'
            }
        
        converted_mapping = {}
        for key, value in hero_mapping.items():
            if key == 'gachahero1':
                converted_mapping['heroo1.png'] = value
            elif key == 'gachahero2':
                converted_mapping['heroo2.png'] = value
            elif key == 'gachahero3':
                converted_mapping['heroo3.png'] = value
            elif key == 'gachahero4':
                converted_mapping['heroo4.png'] = value
        
        print(f"โหลด HERO_MAPPING จาก config.json สำเร็จ: {converted_mapping}")
        return converted_mapping
        
    except FileNotFoundError:
        print("ไม่พบไฟล์ config.json - ใช้ค่าเริ่มต้น")
        return {
            'heroo1.png': 'Denji',
            'heroo2.png': 'DenjiU',
            'heroo3.png': 'Power',
            'heroo4.png': 'PowerU'
        }
    except json.JSONDecodeError:
        print("รูปแบบไฟล์ config.json ไม่ถูกต้อง - ใช้ค่าเริ่มต้น")
        return {
            'heroo1.png': 'Denji',
            'heroo2.png': 'DenjiU',
            'heroo3.png': 'Power',
            'heroo4.png': 'PowerU'
        }
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการโหลด HERO_MAPPING: {e} - ใช้ค่าเริ่มต้น")
        return {
            'heroo1.png': 'Denji',
            'heroo2.png': 'DenjiU',
            'heroo3.png': 'Power',
            'heroo4.png': 'PowerU'
        }

def check_hero_images(adb_img) -> Optional[str]:
    hero_mapping = load_hero_mapping()
    
    hero_images = ['heroo1.png', 'heroo2.png', 'heroo3.png', 'heroo4.png']
    for hero_img in hero_images:
        hero_pos = ImgSearchADB(adb_img, f'img/ranger/{hero_img}')
        if hero_pos:
            hero_name = hero_mapping.get(hero_img, 'unknown')
            print(f"พบ {hero_img} ({hero_name}) ")
            
            # Track hero count
            ds = get_device_state()
            if ds:
                with ds.lock:
                    current_count = ds.hero_counts.get(hero_name, 0)
                    ds.hero_counts[hero_name] = current_count + 1
            
            filename_prefix = f"heroo{hero_images.index(hero_img) + 1}"
            return hero_name, filename_prefix
    return None, None

def backup_game_data(device):
    try:
        cap = device.screencap()
        image = np.frombuffer(cap, dtype=np.uint8)
        adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
        
        hero_result = check_hero_images(adb_img)
        if not hero_result:
            print(f"ไม่พบ hero images บนอุปกรณ์ {device.serial}")
            return False
            
        hero_name, filename_prefix = hero_result

        ds = get_device_state()
        if ds is None:
            print(f"Error during backup: device_state is None")
            return False
        
        original_filename = ds.original_filenames.get(device.serial)

        backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup-id")
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
            print(f"Created backup directory at: {backup_dir}")

        if original_filename:
            base_name = os.path.splitext(original_filename)[0]
            backup_filename = f"{hero_name}+{base_name}.xml"
        else:
            next_id, _ = get_next_backup_id()
            backup_filename = f"{hero_name}-id{next_id}_LINE_COCOS_PREF_KEY.xml"

        backup_path = os.path.join(backup_dir, backup_filename)

        source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"

        print(f"Device {device.serial}: === Starting Backup Process ===")
        print(f"Hero detected: {hero_name}")
        if original_filename:
            print(f"Using hero name + original filename: {backup_filename}")
        print(f"Backup ID: {next_id if not original_filename else 'using original'}")
        print(f"Backup path: {backup_path}")

        device.shell("su -c 'chmod 777 /data/data/com.linecorp.LGRGS/shared_prefs'")
        device.shell(f"su -c 'chmod 777 {source_path}'")

        pull_command = f'adb -s {device.serial} pull "{source_path}" "{backup_path}"'
        result = subprocess.run(
            pull_command, 
            shell=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode == 0 and os.path.exists(backup_path):
            file_size = os.path.getsize(backup_path)
            print(f"Device {device.serial}: === Backup Successful ===")
            print(f"Hero: {hero_name}")
            if original_filename:
                print(f"Original filename: {original_filename}")
            print(f"New filename: {backup_filename}")
            print(f"Backup location: {backup_path}")
            print(f"File size: {file_size} bytes")
            return True
        else:
            print(f"Device {device.serial}: Backup failed: {result.stderr}")
            return False

    except Exception as e:
        print(f"Error during backup: {str(e)}")
        return False



def backup_failed_game_data(device):
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        random_fail_dir = os.path.join(current_dir, "random-Fail")
        if not os.path.exists(random_fail_dir):
            os.makedirs(random_fail_dir)
            print(f"Created random-Fail folder at: {random_fail_dir}")

        source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
        
        ds = get_device_state()
        if ds is None:
            print(f"Error during backup: device_state is None")
            original_filename = None
        else:
            original_filename = ds.original_filenames.get(device.serial)
        
        if original_filename:
            base_name = os.path.splitext(original_filename)[0]
            backup_filename = f"{base_name}.xml"
        else:
            backup_filename = "(B)Sally.xml"
            
        backup_path = os.path.join(random_fail_dir, backup_filename)

        print(f"Device {device.serial}: === Starting Failed Backup Process ===")
        print(f"Backup path: {backup_path}")

        device.shell("su -c 'chmod 777 /data/data/com.linecorp.LGRGS/shared_prefs'")
        device.shell(f"su -c 'chmod 777 {source_path}'")

        pull_command = f'adb -s {device.serial} pull "{source_path}" "{backup_path}"'
        result = subprocess.run(
            pull_command, 
            shell=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode == 0 and os.path.exists(backup_path):
            file_size = os.path.getsize(backup_path)
            print(f"Device {device.serial}: === Failed Backup Successful ===")
            print(f"Backup location: {backup_path}")
            print(f"File size: {file_size} bytes")
            return True
        else:
            print(f"Device {device.serial}: Backup failed: {result.stderr}")
            return False

    except Exception as e:
        print(f"Error during failed backup: {str(e)}")
        return False

def backup_failed_login(device):
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        login_fail_dir = os.path.join(current_dir, "login-fail")
        if not os.path.exists(login_fail_dir):
            os.makedirs(login_fail_dir)
            print(f"Created login-fail folder at: {login_fail_dir}")

        source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
        
        ds = get_device_state()
        if ds is None:
            print(f"Error during backup: device_state is None")
            original_filename = None
        else:
            original_filename = ds.original_filenames.get(device.serial)
        
        if original_filename:
            backup_filename = original_filename
        else:
            backup_filename = f"login-fail_{device.serial}.xml"
            
        backup_path = os.path.join(login_fail_dir, backup_filename)

        print(f"Device {device.serial}: === Starting Login-Fail Backup Process ===")
        print(f"Backup path: {backup_path}")

        device.shell("su -c 'chmod 777 /data/data/com.linecorp.LGRGS/shared_prefs'")
        device.shell(f"su -c 'chmod 777 {source_path}'")

        pull_command = f'adb -s {device.serial} pull "{source_path}" "{backup_path}"'
        result = subprocess.run(
            pull_command, 
            shell=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode == 0 and os.path.exists(backup_path):
            file_size = os.path.getsize(backup_path)
            print(f"Device {device.serial}: === Login-Fail Backup Successful ===")
            print(f"Backup location: {backup_path}")
            print(f"File size: {file_size} bytes")
            return True
        else:
            print(f"Device {device.serial}: Login-Fail Backup failed: {result.stderr}")
            return False

    except Exception as e:
        print(f"Error during login-fail backup: {str(e)}")
        return False

def backup_to_backupxml(device):
    """
    Backup ไฟล์ XML กลับไป backupxml เพื่อนำมาวนเข้าใหม่
    ใช้เมื่อไม่เจอ fixid.png (timeout)
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        backupxml_dir = os.path.join(current_dir, "backup", "backupxml")
        if not os.path.exists(backupxml_dir):
            os.makedirs(backupxml_dir)
            print(f"Created backupxml folder at: {backupxml_dir}")

        source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
        
        ds = get_device_state()
        if ds is None:
            print(f"Error during backup: device_state is None")
            original_filename = None
        else:
            original_filename = ds.original_filenames.get(device.serial)
        
        if original_filename:
            backup_filename = original_filename  # ใช้ชื่อไฟล์เดิม
        else:
            backup_filename = f"retry_{device.serial}_{int(time.time())}.xml"
            
        backup_path = os.path.join(backupxml_dir, backup_filename)

        print(f"Device {device.serial}: === Backup to BackupXML (for retry) ===")
        print(f"Backup path: {backup_path}")

        device.shell("su -c 'chmod 777 /data/data/com.linecorp.LGRGS/shared_prefs'")
        device.shell(f"su -c 'chmod 777 {source_path}'")

        pull_command = f'adb -s {device.serial} pull "{source_path}" "{backup_path}"'
        result = subprocess.run(
            pull_command, 
            shell=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode == 0 and os.path.exists(backup_path):
            file_size = os.path.getsize(backup_path)
            print(f"Device {device.serial}: === Backup to BackupXML Successful ===")
            print(f"Backup location: {backup_path}")
            print(f"File size: {file_size} bytes")
            print(f"ไฟล์ {backup_filename} จะถูกนำมาวนเข้าใหม่")
            
            # ⭐ ลบไฟล์ออกจาก processed_files เพื่อให้สามารถหยิบมาใช้ใหม่ได้
            if ds and backup_filename in ds.processed_files:
                try:
                    del ds.processed_files[backup_filename]
                    print(f"✅ ลบ {backup_filename} ออกจาก processed_files แล้ว - พร้อมนำมาวนใหม่")
                except Exception as del_e:
                    print(f"⚠️ ไม่สามารถลบ {backup_filename} ออกจาก processed_files: {del_e}")
            
            return True
        else:
            print(f"Device {device.serial}: Backup to BackupXML failed: {result.stderr}")
            return False

    except Exception as e:
        print(f"Error during backup to backupxml: {str(e)}")
        return False

def process_single_file_for_device(device, device_state):
    try:
        update_file_queue(device_state)
        
        if device_state.file_queue.empty():
            return False

        with device_state.lock:
            xml_file = device_state.file_queue.get()
            device_state.processed_files[xml_file] = True
            device_state.original_filenames[device.serial] = xml_file

        safe_xml_file = sanitize_filename(xml_file)
        
        original_file_path = Path(source_folder) / xml_file
        safe_file_path = Path(source_folder) / safe_xml_file
        device_specific_temp_file = f"_LINE_COCOS_PREF_KEY_{device.serial}.xml"
        temp_file_path = Path(source_folder) / device_specific_temp_file

        print(f"Device {device.serial}: === เริ่มประมวลผลไฟล์ ===")
        print(f"ไฟล์: {xml_file}")

        if not original_file_path.exists():
            print(f"ไม่พบไฟล์ต้นฉบับ: {original_file_path}")
            return False

        try:
            print(f"กำลังประมวลผลไฟล์ {xml_file} สำหรับอุปกรณ์ {device.serial}")

            max_retries = 3
            success = False
            
            for attempt in range(max_retries):
                try:
                    with original_file_path.open('rb') as src:
                        with temp_file_path.open('wb') as dst:
                            dst.write(src.read())
                    success = True
                    print(f"คัดลอกไฟล์สำเร็จ")
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        print(f"ไม่สามารถคัดลอกไฟล์: {str(e)}")
                        return False
                    time.sleep(1)

            if not success:
                print("ไม่สามารถคัดลอกไฟล์หลังจากพยายามหลายครั้ง")
                return False

            try:
                original_file_path.unlink()
            except Exception as e:
                print(f"ไม่สามารถลบไฟล์ต้นฉบับ: {str(e)}")

            destination_path = "/data/data/com.linecorp.LGRGS/shared_prefs/"
            
            enable_root(device)
            time.sleep(1)
            
            try:
                device.shell(f"su -c 'mkdir -p {destination_path}'")
                device.shell(f"su -c 'chmod 777 {destination_path}'")
                device.shell(f"su -c 'rm -f {destination_path}_LINE_COCOS_PREF_KEY.xml'")
            except Exception as e:
                print(f"ไม่สามารถเตรียมโฟลเดอร์บนอุปกรณ์: {str(e)}")
                return False
            
            for attempt in range(max_retries):
                try:
                    push_command = [
                        'adb',
                        '-s', device.serial,
                        'push',
                        str(temp_file_path),
                        f"{destination_path}_LINE_COCOS_PREF_KEY.xml"
                    ]
                    
                    process = subprocess.Popen(
                        push_command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding='utf-8'
                    )
                    stdout, stderr = process.communicate(timeout=10)
                    
                    if process.returncode != 0:
                        if attempt == max_retries - 1:
                            print(f"ไม่สามารถส่งไฟล์ไปยังอุปกรณ์: {stderr}")
                            return False
                        time.sleep(1)
                        continue
                    
                    print("ส่งไฟล์ไปยังอุปกรณ์สำเร็จ")
                    break

                except subprocess.TimeoutExpired:
                    process.kill()
                    print(f"ส่งไฟล์หมดเวลา (Timeout)")
                    if attempt == max_retries - 1:
                        return False
                    time.sleep(1)
                    continue

                except Exception as e:
                    if attempt == max_retries - 1:
                        print(f"เกิดข้อผิดพลาดในการส่งไฟล์: {str(e)}")
                        return False
                    time.sleep(1)

            try:
                device.shell(f"su -c 'chmod 666 {destination_path}_LINE_COCOS_PREF_KEY.xml'")
            except Exception as e:
                print(f"ไม่สามารถกำหนดสิทธิ์ไฟล์บนอุปกรณ์: {str(e)}")
                return False
            
            print(f"ส่งไฟล์ {xml_file} ไปยังอุปกรณ์ {device.serial} สำเร็จ")
            
            if temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except Exception:
                    pass
            
            return True

        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการประมวลผลไฟล์สำหรับอุปกรณ์ {device.serial}: {str(e)}")
            if temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except Exception:
                    pass
            return False

    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการประมวลผลไฟล์: {str(e)}")
        return False

def clear_game_data(device):
    """ลบข้อมูลเกม"""
    try:
        device.shell("pm clear com.linecorp.LGRGS")
        time.sleep(2)
        return True
    except Exception:
        return False

def check_stopcheck_with_multiple_thresholds(adb_img, device):  # เพิ่ม device parameter
    """ตรวจสอบ stopcheck.png ด้วย threshold หลายระดับ"""
    try:
        thresholds = [0.95, 0.9, 0.85, 0.8]
        
        for threshold in thresholds:
            stopcheck_pos = ImgSearchADB(adb_img, 'img/stopcheck.png', threshold=threshold)
            if stopcheck_pos:
                print(f"{Fore.GREEN}[DEVICE {device.serial}] Found stopcheck.png with threshold {threshold}{Style.RESET_ALL}")
                # เพิ่มการ clear app เมื่อเจอ stopcheck
                clear_app(device)
                time.sleep(2)
                return stopcheck_pos
        
        return []
    except Exception:
        return []



def first_loop_process(device):
    """ขั้นตอนการทำงาน loop แรก พร้อมตรวจสอบ fixcak.png"""
    try:
        print(f"{Fore.CYAN}[DEVICE {device.serial}] Starting first loop process{Style.RESET_ALL}")
        
        # ลบข้อมูลเกมก่อน
        clear_game_data(device)
        time.sleep(3)
        
        # เปิดแอป
        device.shell("am force-stop com.linecorp.LGRGS")
        time.sleep(1)
        device.shell("am start -n com.linecorp.LGRGS/com.linecorp.common.activity.LineActivity")
        time.sleep(10)
        
        # ตรวจหา test.png
        test_found = False
        test_timeout = 120  # เพิ่มเวลา timeout
        test_start_time = time.time()
        
        print(f"{Fore.YELLOW}[DEVICE {device.serial}] Looking for test.png (timeout: {test_timeout}s)...{Style.RESET_ALL}")
        
        while time.time() - test_start_time < test_timeout:
            try:
                elapsed_time = time.time() - test_start_time
                
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                # *** ตรวจสอบ fixcak.png ก่อนเสมอ ***
                fixcak_pos = ImgSearchADB(adb_img, 'img/fixcak.png')
                if fixcak_pos:
                    print(f"{Fore.RED}[DEVICE {device.serial}] Found fixcak.png in first_loop!{Style.RESET_ALL}")
                    print(f"{Fore.RED}[DEVICE {device.serial}] Clearing app and restarting first_loop...{Style.RESET_ALL}")
                    clear_app(device)
                    time.sleep(6)
                    return "restart_first_loop"
                
                if check_black_screen(adb_img, threshold=0.8):
                    if black_screen_timer is None:
                        black_screen_timer = time.time()
                        print(f"{Fore.YELLOW}[DEVICE {device.serial}] Black screen detected, starting timer...{Style.RESET_ALL}")
                    else:
                        elapsed = time.time() - black_screen_timer
                        if elapsed >= 8:
                            print(f"{Fore.RED}[DEVICE {device.serial}] Black screen > 8s, clearing app and restarting...{Style.RESET_ALL}")
                            clear_app(device)
                            time.sleep(3)
                            device.shell("am start -n com.linecorp.LGRGS/com.linecorp.common.activity.LineActivity")
                            time.sleep(2)
                            black_screen_timer = None
                            continue
                else:
                    black_screen_timer = None
                
                # ตรวจสอบ stopcheck.png
                thresholds = [0.95, 0.9, 0.85, 0.8]
                for threshold in thresholds:
                    stopcheck_pos = ImgSearchADB(adb_img, 'img/stopcheck.png', threshold=threshold)
                    if stopcheck_pos:
                        print(f"{Fore.RED}[DEVICE {device.serial}] Found stopcheck.png!{Style.RESET_ALL}")
                        clear_app(device)
                        time.sleep(2)
                        return "complete"
                
                test_pos = ImgSearchADB(adb_img, 'img/test.png')
                if test_pos:
                    print(f"{Fore.GREEN}[DEVICE {device.serial}] Found test.png!{Style.RESET_ALL}")
                    device.shell(f"input tap {test_pos[0][0]} {test_pos[0][1]}")
                    test_found = True
                    break
                
                if int(elapsed_time) % 10 == 0:
                    print(f"{Fore.YELLOW}[DEVICE {device.serial}] Still searching for test.png...({int(elapsed_time)}s elapsed){Style.RESET_ALL}")
                
                time.sleep(1)
                
            except Exception as e:
                print(f"{Fore.RED}[DEVICE {device.serial}] Error: {str(e)}{Style.RESET_ALL}")
                continue
        
        if not test_found:
            print(f"{Fore.RED}[DEVICE {device.serial}] test.png not found, restarting{Style.RESET_ALL}")
            return False
        
        # ตรวจสอบ closeapp.png หลังจากกด test.png
        print(f"{Fore.YELLOW}[DEVICE {device.serial}] Checking for closeapp.png (10 seconds)...{Style.RESET_ALL}")
        closeapp_timeout = 10
        closeapp_start_time = time.time()
        closeapp_found = False
        
        while time.time() - closeapp_start_time < closeapp_timeout:
            try:
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                # *** ตรวจสอบ fixcak.png ***
                fixcak_pos = ImgSearchADB(adb_img, 'img/fixcak.png')
                if fixcak_pos:
                    print(f"{Fore.RED}[DEVICE {device.serial}] Found fixcak.png!{Style.RESET_ALL}")
                    clear_app(device)
                    time.sleep(6)
                    return "restart_first_loop"
                
                closeapp_pos = ImgSearchADB(adb_img, 'img/closeapp.png')
                if closeapp_pos:
                    print(f"{Fore.RED}[DEVICE {device.serial}] Found closeapp.png! Clearing app and restarting first_loop...{Style.RESET_ALL}")
                    clear_app(device)
                    time.sleep(2)
                    closeapp_found = True
                    return "restart_first_loop"
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"{Fore.RED}[DEVICE {device.serial}] Error checking closeapp.png: {str(e)}{Style.RESET_ALL}")
                continue
        
        if not closeapp_found:
            print(f"{Fore.GREEN}[DEVICE {device.serial}] closeapp.png not found within 10 seconds, continuing...{Style.RESET_ALL}")
        
        # ตรวจหา save.png
        save_found = False
        save_timeout = 20
        save_start_time = time.time()
        
        print(f"{Fore.YELLOW}[DEVICE {device.serial}] Looking for save.png...{Style.RESET_ALL}")
        
        while time.time() - save_start_time < save_timeout:
            try:
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                # *** ตรวจสอบ fixcak.png ***
                fixcak_pos = ImgSearchADB(adb_img, 'img/fixcak.png')
                if fixcak_pos:
                    print(f"{Fore.RED}[DEVICE {device.serial}] Found fixcak.png!{Style.RESET_ALL}")
                    clear_app(device)
                    time.sleep(6)
                    return "restart_first_loop"
                
                # ตรวจสอบ stopcheck.png
                thresholds = [0.95, 0.9, 0.85, 0.8]
                for threshold in thresholds:
                    stopcheck_pos = ImgSearchADB(adb_img, 'img/stopcheck.png', threshold=threshold)
                    if stopcheck_pos:
                        print(f"{Fore.RED}[DEVICE {device.serial}] Found stopcheck.png!{Style.RESET_ALL}")
                        clear_app(device)
                        time.sleep(2)
                        return "complete"
                
                save_pos = ImgSearchADB(adb_img, 'img/save.png')
                if save_pos:
                    device.shell(f"input tap {save_pos[0][0]} {save_pos[0][1]}")
                    save_found = True
                    print(f"{Fore.GREEN}[DEVICE {device.serial}] Found save.png!{Style.RESET_ALL}")
                    break
                    
                time.sleep(0.5)
                
            except Exception as e:
                print(f"{Fore.RED}[DEVICE {device.serial}] Error: {str(e)}{Style.RESET_ALL}")
                continue
        
        if not save_found:
            print(f"{Fore.RED}[DEVICE {device.serial}] save.png not found, clearing app{Style.RESET_ALL}")
            clear_app(device)
            time.sleep(2)
            return "restart_from_test"
        
        # ลำดับการตรวจสอบรูปภาพ
        sequence1 = [
            'apple.png', 'check-l1.png', 'check-l2.png', 
            'check-l3.png', 'check-l4.png'
        ]
        
        sequence2 = [
            'check-gusetid.png', 'check-gusetid1.png',
            'check-l1.png', 'check-l2.png', 'check-l3.png', 'check-l4.png',
            'check-ok1.png', 'check-ok2.png', 'check-ok3.png', 'check-ok4.png'
        ]
        
        print(f"{Fore.YELLOW}[DEVICE {device.serial}] Processing sequence 1...{Style.RESET_ALL}")
        
        # ทำงานตาม sequence1 - ไม่ข้ามรูปไหน แค่นับเวลา
        for i, img_name in enumerate(sequence1):
            print(f"{Fore.CYAN}[DEVICE {device.serial}] Looking for {img_name} ({i+1}/{len(sequence1)}){Style.RESET_ALL}")
            found = False
            timeout = 60  # เพิ่มเวลา timeout
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    elapsed_time = time.time() - start_time
                    cap = device.screencap()
                    image = np.frombuffer(cap, dtype=np.uint8)
                    adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                    
                    # *** ตรวจสอบ fixcak.png ***
                    fixcak_pos = ImgSearchADB(adb_img, 'img/fixcak.png')
                    if fixcak_pos:
                        print(f"{Fore.RED}[DEVICE {device.serial}] Found fixcak.png in sequence1!{Style.RESET_ALL}")
                        clear_app(device)
                        time.sleep(6)
                        return "restart_first_loop"
                    
                    # ตรวจสอบ stopcheck.png
                    for threshold in thresholds:
                        stopcheck_pos = ImgSearchADB(adb_img, 'img/stopcheck.png', threshold=threshold)
                        if stopcheck_pos:
                            print(f"{Fore.RED}[DEVICE {device.serial}] Found stopcheck.png!{Style.RESET_ALL}")
                            clear_app(device)
                            time.sleep(2)
                            return "complete"
                    
                    pos = ImgSearchADB(adb_img, f'img/{img_name}')
                    if pos:
                        device.shell(f"input tap {pos[0][0]} {pos[0][1]}")
                        found = True
                        print(f"{Fore.GREEN}[DEVICE {device.serial}] Found {img_name}!{Style.RESET_ALL}")
                        
                        if img_name == 'check-l4.png':
                           print(f"{Fore.YELLOW}[DEVICE {device.serial}] Found check-l4.png, waiting 2s...{Style.RESET_ALL}")
                           time.sleep(2)

                        time.sleep(1)
                        break
                    
                    if int(elapsed_time) % 10 == 0:
                        print(f"{Fore.YELLOW}[DEVICE {device.serial}] Searching for {img_name}...({int(elapsed_time)}s elapsed){Style.RESET_ALL}")
                        
                    time.sleep(0.5)
                except Exception:
                    continue
            
            if not found:
                print(f"{Fore.YELLOW}[DEVICE {device.serial}] {img_name} not found, continuing...{Style.RESET_ALL}")
                continue
        
        print(f"{Fore.CYAN}[DEVICE {device.serial}] Sequence 1 completed, waiting 8s then pressing BACK...{Style.RESET_ALL}")
        time.sleep(8)
        device.shell("input keyevent 4")
        time.sleep(2)

        print(f"{Fore.YELLOW}[DEVICE {device.serial}] Processing sequence 2...{Style.RESET_ALL}")
        
        # ทำงานตาม sequence2 - ไม่ข้ามรูปไหน แค่นับเวลา
        for i, img_name in enumerate(sequence2):
            print(f"{Fore.CYAN}[DEVICE {device.serial}] Looking for {img_name} ({i+1}/{len(sequence2)}){Style.RESET_ALL}")
            found = False
            timeout = 60  # เพิ่มเวลา timeout
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    elapsed_time = time.time() - start_time
                    cap = device.screencap()
                    image = np.frombuffer(cap, dtype=np.uint8)
                    adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                    
                    # *** ตรวจสอบ fixcak.png ***
                    fixcak_pos = ImgSearchADB(adb_img, 'img/fixcak.png')
                    if fixcak_pos:
                        print(f"{Fore.RED}[DEVICE {device.serial}] Found fixcak.png in sequence2!{Style.RESET_ALL}")
                        clear_app(device)
                        time.sleep(6)
                        return "restart_first_loop"
                    
                    # ตรวจสอบ stopcheck.png
                    for threshold in thresholds:
                        stopcheck_pos = ImgSearchADB(adb_img, 'img/stopcheck.png', threshold=threshold)
                        if stopcheck_pos:
                            print(f"{Fore.RED}[DEVICE {device.serial}] Found stopcheck.png!{Style.RESET_ALL}")
                            clear_app(device)
                            time.sleep(2)
                            return "complete"
                    
                    pos = ImgSearchADB(adb_img, f'img/{img_name}')
                    if pos:
                        device.shell(f"input tap {pos[0][0]} {pos[0][1]}")
                        found = True
                        print(f"{Fore.GREEN}[DEVICE {device.serial}] Found {img_name}!{Style.RESET_ALL}")
                        time.sleep(1)
                        break
                    
                    if int(elapsed_time) % 10 == 0:
                        print(f"{Fore.YELLOW}[DEVICE {device.serial}] Searching for {img_name}...({int(elapsed_time)}s elapsed){Style.RESET_ALL}")
                        
                    time.sleep(0.5)
                except Exception:
                    continue
            
            if not found:
                print(f"{Fore.YELLOW}[DEVICE {device.serial}] {img_name} not found, continuing...{Style.RESET_ALL}")
                continue

        print(f"{Fore.GREEN}[DEVICE {device.serial}] First loop process completed!{Style.RESET_ALL}")
        clear_app(device)
        time.sleep(2)
        print(f"{Fore.GREEN}[DEVICE {device.serial}] App cleared after completion{Style.RESET_ALL}")
        return "complete"
        
    except Exception as e:
        print(f"{Fore.RED}[DEVICE {device.serial}] Error in first loop: {str(e)}{Style.RESET_ALL}")
        clear_app(device)
        time.sleep(2)
        return False




# ========================================
# เพิ่มฟังก์ชัน process_ruby_gear200 ใหม่
# วางไว้ก่อนฟังก์ชัน process_random_gear
# ========================================

def process_ruby_gear200(device):
    """
    ฟังก์ชันจัดการ ruby-gear200
    - ทำงานหลังจากเลือก channel และก่อนกด gear1 ใน random-gear
    - วนลูปกด rubytwo3 -> rubytwo4 -> rubytwo5 จนกว่าจะเจอ stoprubygear200.png
    """
    print(f"\n=== เริ่มกระบวนการ ruby-gear200 สำหรับอุปกรณ์: {device.serial} ===\n")
    
    def check_stoprubygear200(adb_img):
        """ตรวจสอบ stoprubygear200.png"""
        stoprubygear_pos = ImgSearchADB(adb_img, 'img/stoprubygear200.png')
        return bool(stoprubygear_pos)
    
    def click_cancel_sequence():
        """กดลำดับ cancelgear1 -> cancelgear2"""
        print("พบ stoprubygear200.png - เริ่มกดลำดับ cancel")
        
        # กด cancelgear1
        retry_count = 0
        max_retries = 5
        while retry_count < max_retries:
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            cancelgear1_pos = ImgSearchADB(adb_img, 'img/cancelgear1.png')
            if cancelgear1_pos:
                print(f"พบและกด cancelgear1.png")
                device.shell(f"input tap {cancelgear1_pos[0][0]} {cancelgear1_pos[0][1]}")
                time.sleep(1)
                break
            
            retry_count += 1
            if retry_count < max_retries:
                print(f"ไม่พบ cancelgear1.png (พยายามครั้งที่ {retry_count}/{max_retries})")
                time.sleep(1)
        
        # กด cancelgear2
        retry_count = 0
        while retry_count < max_retries:
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            cancelgear2_pos = ImgSearchADB(adb_img, 'img/cancelgear2.png')
            if cancelgear2_pos:
                print(f"พบและกด cancelgear2.png")
                device.shell(f"input tap {cancelgear2_pos[0][0]} {cancelgear2_pos[0][1]}")
                time.sleep(1)
                break
            
            retry_count += 1
            if retry_count < max_retries:
                print(f"ไม่พบ cancelgear2.png (พยายามครั้งที่ {retry_count}/{max_retries})")
                time.sleep(1)
        
        print("เสร็จสิ้นการกดลำดับ cancel")
    
    try:
        # ขั้นตอนที่ 1: ค้นหาและกด rubytwo1
        print("\n1. ค้นหาและกด rubytwo1.png...")
        rubytwo1_found = False
        retry_count = 0
        max_retries = 5
        
        while retry_count < max_retries:
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            # ตรวจสอบ stoprubygear200 ก่อนเสมอ
            if check_stoprubygear200(adb_img):
                print("พบ stoprubygear200.png ก่อนกด rubytwo1 - จบการทำงาน")
                click_cancel_sequence()
                return True
            
            rubytwo1_pos = ImgSearchADB(adb_img, 'img/rubytwo1.png')
            if rubytwo1_pos:
                print(f"พบและกด rubytwo1.png ที่ตำแหน่ง {rubytwo1_pos[0]}")
                device.shell(f"input tap {rubytwo1_pos[0][0]} {rubytwo1_pos[0][1]}")
                rubytwo1_found = True
                time.sleep(1)
                break
            
            retry_count += 1
            if retry_count < max_retries:
                print(f"ไม่พบ rubytwo1.png (พยายามครั้งที่ {retry_count}/{max_retries})")
                time.sleep(1)
        
        if not rubytwo1_found:
            print("ไม่พบ rubytwo1.png - จบการทำงาน ruby-gear200")
            return False
        
        # ขั้นตอนที่ 2: ค้นหาและกด rubytwo2
        print("\n2. ค้นหาและกด rubytwo2.png...")
        retry_count = 0
        
        while retry_count < max_retries:
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            if check_stoprubygear200(adb_img):
                print("พบ stoprubygear200.png ก่อนกด rubytwo2 - จบการทำงาน")
                click_cancel_sequence()
                return True
            
            rubytwo2_pos = ImgSearchADB(adb_img, 'img/rubytwo2.png')
            if rubytwo2_pos:
                print(f"พบและกด rubytwo2.png ที่ตำแหน่ง {rubytwo2_pos[0]}")
                device.shell(f"input tap {rubytwo2_pos[0][0]} {rubytwo2_pos[0][1]}")
                time.sleep(1)
                break
            
            retry_count += 1
            if retry_count < max_retries:
                print(f"ไม่พบ rubytwo2.png (พยายามครั้งที่ {retry_count}/{max_retries})")
                time.sleep(1)
        
        # ขั้นตอนที่ 3: วนลูปหลัก rubytwo3 -> rubytwo4 -> rubytwo5
        print("\n3. เริ่มวนลูปหลัก (rubytwo3 -> rubytwo4 -> rubytwo5)...")
        loop_count = 0
        
        while True:
            loop_count += 1
            print(f"\n--- รอบที่ {loop_count} ---")
            
            # 3.1: กด rubytwo3 (6 ครั้ง)
            print("3.1: กด rubytwo3.png ตำแหน่งเดิม 6 รอบ...")
            rubytwo3_position = None
            
            # หาตำแหน่ง rubytwo3 ครั้งแรก
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            if check_stoprubygear200(adb_img):
                print("พบ stoprubygear200.png - จบการทำงาน")
                click_cancel_sequence()
                return True
            
            rubytwo3_pos = ImgSearchADB(adb_img, 'img/rubytwo3.png')
            if rubytwo3_pos:
                rubytwo3_position = rubytwo3_pos[0]
                print(f"พบ rubytwo3.png ที่ตำแหน่ง {rubytwo3_position}")
                
                # กดตำแหน่งเดิม 6 ครั้ง
                for i in range(6):
                    print(f"  กด rubytwo3 ครั้งที่ {i+1}/6")
                    device.shell(f"input tap {rubytwo3_position[0]} {rubytwo3_position[1]}")
                    time.sleep(0.5)
                    
                    # ตรวจสอบ stoprubygear200 ระหว่างกด
                    cap = device.screencap()
                    image = np.frombuffer(cap, dtype=np.uint8)
                    adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                    
                    if check_stoprubygear200(adb_img):
                        print("พบ stoprubygear200.png ระหว่างกด rubytwo3 - จบการทำงาน")
                        click_cancel_sequence()
                        return True
                
                time.sleep(1)
            else:
                print("ไม่พบ rubytwo3.png - ลองใหม่ในรอบถัดไป")
            
            # 3.2: กด rubytwo4
            print("3.2: กด rubytwo4.png...")
            retry_count = 0
            
            while retry_count < max_retries:
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                if check_stoprubygear200(adb_img):
                    print("พบ stoprubygear200.png - จบการทำงาน")
                    click_cancel_sequence()
                    return True
                
                rubytwo4_pos = ImgSearchADB(adb_img, 'img/rubytwo4.png')
                if rubytwo4_pos:
                    print(f"พบและกด rubytwo4.png ที่ตำแหน่ง {rubytwo4_pos[0]}")
                    device.shell(f"input tap {rubytwo4_pos[0][0]} {rubytwo4_pos[0][1]}")
                    time.sleep(1)
                    break
                
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(1)
            
            # 3.3: กด rubytwo5
            print("3.3: กด rubytwo5.png...")
            retry_count = 0
            
            while retry_count < max_retries:
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                if check_stoprubygear200(adb_img):
                    print("พบ stoprubygear200.png - จบการทำงาน")
                    click_cancel_sequence()
                    return True
                
                rubytwo5_pos = ImgSearchADB(adb_img, 'img/rubytwo5.png')
                if rubytwo5_pos:
                    print(f"พบและกด rubytwo5.png ที่ตำแหน่ง {rubytwo5_pos[0]}")
                    device.shell(f"input tap {rubytwo5_pos[0][0]} {rubytwo5_pos[0][1]}")
                    time.sleep(1)
                    break
                
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(1)
            
            # ตรวจสอบ stoprubygear200 หลังจบ 1 รอบ
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            if check_stoprubygear200(adb_img):
                print("พบ stoprubygear200.png หลังจบรอบ - จบการทำงาน")
                click_cancel_sequence()
                return True
            
            print(f"จบรอบที่ {loop_count} - เริ่มรอบถัดไป...")
            time.sleep(1)
    
    except Exception as e:
        print(f"\nเกิดข้อผิดพลาดในกระบวนการ ruby-gear200: {e}")
        return False


def process_random_gear(device):
    """ฟังก์ชันจัดการ random-gear พร้อมระบบบันทึกชื่อไฟล์เดิม"""
    print(f"\n=== เริ่มกระบวนการ random-gear สำหรับอุปกรณ์: {device.serial} ===\n")

    def get_gear_name(img_name):
        """แปลงชื่อรูปเป็นชื่อ gear ตาม config"""
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
                gear_mapping = config.get('gearname', {})
                return gear_mapping.get(img_name, '')
        except Exception as e:
            print(f"Error loading gear mapping: {e}")
            return ''

    def check_gear_images(adb_img):
        """ตรวจสอบรูป gear ทั้งหมด"""
        found_gears = set()
        for i in range(1, 5):
            gear_pos = ImgSearchADB(adb_img, f'img/gearimg{i}.png')
            if gear_pos:
                gear_name = get_gear_name(f'gearimg{i}')
                if gear_name:
                    found_gears.add(gear_name)
                    print(f"พบ {gear_name} จาก gearimg{i}.png")
        return found_gears

    def check_stopgear(adb_img):
        """ตรวจสอบรูป stopgear.png"""
        stopgear_pos = ImgSearchADB(adb_img, 'img/stopgear.png')
        return bool(stopgear_pos)

    def get_and_click_channel():
        """ดึงและคลิกตำแหน่งช่องจาก config"""
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            
            channels_img_enabled = config.get('channels_img', 0)
            
            if channels_img_enabled == 1:
                print("ใช้การค้นหาตำแหน่งช่องจากรูปภาพ")
                channel_pos = search_gachaslot_image(device)
            else:
                selected_channel = config.get('channel', 'ch2')
                if 'channels' not in config or selected_channel not in config['channels']:
                    print("ไม่พบข้อมูลช่องในไฟล์ config")
                    return False

                channel_pos = config['channels'][selected_channel]
                print(f"ใช้ช่อง: {selected_channel} ตำแหน่ง: {channel_pos}")
                
                if selected_channel in ['ch4', 'ch5']:
                    print(f"เลื่อนช่อง 5 รอบ")
                    for _ in range(5):
                        device.shell("input swipe 852 316 855 116 600")
                        time.sleep(0.2)

            if channel_pos and len(channel_pos) == 2:
                # คลิก 3 ครั้งเพื่อความแน่นอน
                for i in range(3):
                    device.shell(f"input tap {channel_pos[0]} {channel_pos[1]}")
                    time.sleep(0.5)
                print(f"คลิกตำแหน่งช่องที่ {channel_pos} สำเร็จ")
                return True
            return False

        except Exception as e:
            print(f"Error in channel selection: {e}")
            return False

    try:
        # ========================================
        # ⭐ ขั้นตอนที่ 0: กด gachagear.png ก่อนทำอะไรทั้งหมด
        # ========================================
        print("\n0. ค้นหาและกด gachagear.png ก่อนเสมอ...")
        gachagear_clicked = False
        max_gachagear_retries = 10
        gachagear_retry_count = 0
        
        while gachagear_retry_count < max_gachagear_retries and not gachagear_clicked:
            try:
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                if check_stopgear(adb_img):
                    print("พบ stopgear.png - จบการทำงาน")
                    backup_failed_game_data(device)
                    clear_app(device)
                    time.sleep(6)
                    return True
                
                # ⭐ ตรวจสอบ fixid, fixunkown, apple
                critical_error = check_critical_errors(device, adb_img, "process_random_gear")
                if critical_error:
                    return False
                
                gachagear_pos = ImgSearchADB(adb_img, 'img/gachagear.png')
                if gachagear_pos:
                    print(f"✓ พบและกด gachagear.png ที่ตำแหน่ง {gachagear_pos[0]}")
                    device.shell(f"input tap {gachagear_pos[0][0]} {gachagear_pos[0][1]}")
                    gachagear_clicked = True
                    time.sleep(3)  # รอให้หน้าจอโหลด
                    print("✓ กด gachagear.png สำเร็จ - รอ 3 วินาที")
                    break
                else:
                    gachagear_retry_count += 1
                    print(f"ไม่พบ gachagear.png (พยายามครั้งที่ {gachagear_retry_count}/{max_gachagear_retries})")
                    time.sleep(1)
                    
            except Exception as e:
                print(f"Error clicking gachagear.png: {e}")
                gachagear_retry_count += 1
                time.sleep(1)
        
        if not gachagear_clicked:
            print("⚠️ ไม่พบ gachagear.png หลังจากพยายาม 10 ครั้ง - ดำเนินการต่อ")
        
        # ========================================
        # ขั้นตอนที่ 1: ค้นหา shopgacha1.png
        # ========================================
        print("\n1. เริ่มค้นหา shopgacha1.png...")
        retries = 5
        found_initial_swap_shop = False
        last_click_position = None
        
        for attempt in range(retries):
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            if check_stopgear(adb_img):
                print("พบ stopgear.png - จบการทำงาน")
                backup_failed_game_data(device)
                clear_app(device)
                time.sleep(6)
                return True
            
            shopgacha1_pos = ImgSearchADB(adb_img, 'img/shopgacha1.png')
            if shopgacha1_pos:
                print(f"พบ shopgacha1.png ที่ {shopgacha1_pos[0]}")
                device.shell(f"input tap {shopgacha1_pos[0][0]} {shopgacha1_pos[0][1]}")
                last_click_position = shopgacha1_pos[0]
                found_initial_swap_shop = True
                time.sleep(2)
                break
                
            if attempt < retries - 1:
                print(f"ไม่พบ shopgacha1.png (พยายามครั้งที่ {attempt + 1}/{retries})")
                time.sleep(1)

        print(f"\n2. เริ่มตรวจสอบ waitgacha และ fixnewgacha...")
        found_waitgacha = False
        checked_waitgacha = False
        start_time = time.time()
        max_initial_wait = 8000
        
        while not checked_waitgacha:
            try:
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                check_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                if check_stopgear(check_img):
                    print("พบ stopgear.png - จบการทำงาน")
                    backup_failed_game_data(device)
                    clear_app(device)
                    time.sleep(6)
                    return True
                
                # ⭐ ตรวจสอบ fixid, fixunkown, apple
                critical_error = check_critical_errors(device, check_img, "process_random_gear_loop")
                if critical_error:
                    return False
                
                if not found_waitgacha:
                    waitgacha_pos = ImgSearchADB(check_img, 'img/waitgacha.png')
                    if waitgacha_pos:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ waitgacha - รอตรวจสอบ fixnewgacha เป็นเวลา 10 วินาที")
                        found_waitgacha = True
                        start_time = time.time()
                    else:
                        if time.time() - start_time > max_initial_wait:
                            print(f"รอ waitgacha เกิน {max_initial_wait} วินาที - ข้ามไปขั้นตอนถัดไป")
                            checked_waitgacha = True
                            break
                
                if found_waitgacha:
                    fixnewgacha_pos = ImgSearchADB(check_img, 'img/fixnewgacha.png')
                    if fixnewgacha_pos:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] พบ fixnewgacha - เริ่มกดตำแหน่ง [471, 417] เป็นเวลา 10 วินาที")
                        
                        click_start_time = time.time()
                        click_duration = 10
                        click_interval = 0.5
                        
                        while time.time() - click_start_time < click_duration:
                            cap = device.screencap()
                            image = np.frombuffer(cap, dtype=np.uint8)
                            temp_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                            
                            if check_stopgear(temp_img):
                                print("พบ stopgear.png ระหว่างคลิกตำแหน่ง [471, 417] - จบการทำงาน")
                                backup_failed_game_data(device)
                                clear_app(device)
                                time.sleep(6)
                                return True
                            
                            device.shell("input tap 471 406")
                            elapsed_time = time.time() - click_start_time
                            print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] กดตำแหน่ง [471, 417] - เวลาที่ผ่านไป: {elapsed_time:.1f}/{click_duration} วินาที")
                            time.sleep(click_interval)
                        
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] เสร็จสิ้นการกดตำแหน่ง [471, 417] ครบ 10 วินาที")
                        checked_waitgacha = True
                        time.sleep(2)
                        break
                    
                    if time.time() - start_time > 10:
                        print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] ครบ 10 วินาที - ไม่พบ fixnewgacha")
                        checked_waitgacha = True
                        break
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการตรวจสอบ waitgacha/fixnewgacha: {e}")
                checked_waitgacha = True
                break

        # ========================================
        # ⭐ ขั้นตอนที่ 3: ค้นหาและกด gear1.png ก่อน
        # ========================================
        print("\n3. ค้นหาและคลิก gear1.png...")
        gear1_found = False
        max_retries = 5
        retry_count = 0
        
        while retry_count < max_retries and not gear1_found:
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            if check_stopgear(adb_img):
                print("พบ stopgear.png - จบการทำงาน")
                backup_failed_game_data(device)
                clear_app(device)
                time.sleep(6)
                return True
            
            gear1_pos = ImgSearchADB(adb_img, 'img/gear1.png')
            if gear1_pos:
                print(f"พบ gear1.png ที่ {gear1_pos[0]}")
                for _ in range(2):
                    device.shell(f"input tap {gear1_pos[0][0]} {gear1_pos[0][1]}")
                    time.sleep(0.5)
                gear1_found = True
                break
            
            retry_count += 1
            if retry_count < max_retries:
                print(f"ไม่พบ gear1.png (พยายามครั้งที่ {retry_count}/{max_retries})")
                time.sleep(1)

        # ========================================
        # ⭐ ขั้นตอนที่ 4: เลือกช่องหลังกด gear1
        # ========================================
        print("\n4. เลือกช่อง...")
        if not get_and_click_channel():
            print("ไม่สามารถคลิกช่องได้ ใช้การกดตามลำดับ gear ตามปกติ")

        # ========================================
        # ⭐ ขั้นตอนที่ 5: เรียก ruby-gear200 หลังเลือกช่อง
        # ========================================
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            ruby_gear_enabled = config.get('ruby-gear200', 0)
            
            if ruby_gear_enabled:
                print("\n=== ruby-gear200 เปิดใช้งาน - เริ่มกระบวนการ ===")
                process_ruby_gear200(device)
                print("=== ruby-gear200 เสร็จสิ้น - กลับมาทำงาน random-gear ต่อ ===\n")
            else:
                print("\nrubby-gear200 ปิดใช้งาน - ข้ามขั้นตอนนี้")
        except Exception as e:
            print(f"Error checking ruby-gear200 config: {e}")
        # ========================================

        print("\n5. กดปุ่ม gear2-4...")
        for gear_num in range(2, 5):
            retry_count = 0
            max_retries = 5
            
            while retry_count < max_retries:
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                if check_stopgear(adb_img):
                    print("พบ stopgear.png - จบการทำงาน")
                    backup_failed_game_data(device)
                    clear_app(device)
                    time.sleep(6)
                    return True
                
                gear_pos = ImgSearchADB(adb_img, f'img/gear{gear_num}.png')
                if gear_pos:
                    print(f"พบ gear{gear_num}.png ที่ {gear_pos[0]}")
                    for _ in range(2):
                        device.shell(f"input tap {gear_pos[0][0]} {gear_pos[0][1]}")
                        time.sleep(0.5)
                    break
                
                retry_count += 1
                if retry_count < max_retries:
                    print(f"ไม่พบ gear{gear_num}.png (พยายามครั้งที่ {retry_count}/{max_retries})")
                    time.sleep(1)
            
            time.sleep(1)

        print("\n6. เริ่ม Loop2 (gear5-7)...")
        while True:
            found_stoploop2 = False
            for gear_num in range(5, 8):
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                if check_stopgear(adb_img):
                    print("พบ stopgear.png - จบการทำงาน")
                    backup_failed_game_data(device)
                    clear_app(device)
                    time.sleep(6)
                    return True
                
                stoploop2_pos = ImgSearchADB(adb_img, 'img/stoploop2.png')
                if stoploop2_pos:
                    print("พบ stoploop2.png")
                    found_stoploop2 = True
                    break
                
                gear_pos = ImgSearchADB(adb_img, f'img/gear{gear_num}.png')
                if gear_pos:
                    print(f"พบและคลิก gear{gear_num}.png")
                    device.shell(f"input tap {gear_pos[0][0]} {gear_pos[0][1]}")
                    time.sleep(1)
            
            if found_stoploop2:
                break

        print("\n7. ดำเนินการขั้นตอนสุดท้าย...")
        final_sequence = ['stoploop1.png', 'checkgear1.png', 'checkgear2.png', 'checkgear3.png']
        for img in final_sequence:
            retry_count = 0
            max_retries = 5
            
            while retry_count < max_retries:
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                if check_stopgear(adb_img):
                    print("พบ stopgear.png - จบการทำงาน")
                    backup_failed_game_data(device)
                    clear_app(device)
                    time.sleep(6)
                    return True
                
                pos = ImgSearchADB(adb_img, f'img/{img}')
                if pos:
                    print(f"พบและคลิก {img}")
                    device.shell(f"input tap {pos[0][0]} {pos[0][1]}")
                    time.sleep(1)
                    break
                
                retry_count += 1
                if retry_count < max_retries:
                    print(f"ไม่พบ {img} (พยายามครั้งที่ {retry_count}/{max_retries})")
                    time.sleep(1)

        print("\n8. เริ่มตรวจสอบ gear...")
        all_found_gears = set()
        
        cap = device.screencap()
        image = np.frombuffer(cap, dtype=np.uint8)
        adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
        
        if check_stopgear(adb_img):
            print("พบ stopgear.png - จบการทำงาน")
            backup_failed_game_data(device)
            clear_app(device)
            time.sleep(6)
            return True
        
        print("รอบที่ 1: ตรวจสอบโดยตรง")
        all_found_gears.update(check_gear_images(adb_img))
        time.sleep(5)
        
        weapons1_pos = ImgSearchADB(adb_img, 'img/weapons1.png')
        if weapons1_pos:
            print("\nรอบที่ 2: ตรวจสอบหลังกด weapons1.png")
            device.shell(f"input tap {weapons1_pos[0][0]} {weapons1_pos[0][1]}")
            time.sleep(2)
            
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            if check_stopgear(adb_img):
                print("พบ stopgear.png - จบการทำงาน")
                backup_failed_game_data(device)
                clear_app(device)
                time.sleep(6)
                return True
            
            all_found_gears.update(check_gear_images(adb_img))
            time.sleep(5)
        
        weapons2_pos = ImgSearchADB(adb_img, 'img/weapons2.png')
        if weapons2_pos:
            print("\nรอบที่ 3: ตรวจสอบหลังกด weapons2.png")
            device.shell(f"input tap {weapons2_pos[0][0]} {weapons2_pos[0][1]}")
            time.sleep(2)
            
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            if check_stopgear(adb_img):
                print("พบ stopgear.png - จบการทำงาน")
                backup_failed_game_data(device)
                clear_app(device)
                time.sleep(6)
                return True
            
            all_found_gears.update(check_gear_images(adb_img))
            time.sleep(5)

        print("\n9. เริ่มการ backup...")
        if all_found_gears:
            ds = get_device_state()
            if ds is None:
                print(f"Error during backup: device_state is None")
                original_filename = None
            else:
                original_filename = ds.original_filenames.get(device.serial)
            
            if original_filename:
                base_name, ext = os.path.splitext(original_filename)
                if len(all_found_gears) > 1:
                    gear_prefix = "+".join(sorted(all_found_gears))
                else:
                    gear_prefix = next(iter(all_found_gears))
                filename = f"{gear_prefix}+{base_name}{ext}"
            else:
                if len(all_found_gears) > 1:
                    filename = "+".join(sorted(all_found_gears))
                else:
                    filename = next(iter(all_found_gears))
                filename += "_LINE_COCOS_PREF_KEY.xml"
            
            print(f"พบ gear ทั้งหมด: {', '.join(all_found_gears)}")
            print(f"ชื่อไฟล์ที่จะ backup: {filename}")
            
            backup_dir = "backup-id"
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
                print(f"สร้างโฟลเดอร์ backup-id")
            
            source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
            backup_path = os.path.join(backup_dir, filename)
            
            device.shell("su -c 'chmod 777 /data/data/com.linecorp.LGRGS/shared_prefs'")
            device.shell(f"su -c 'chmod 777 {source_path}'")
            
            result = subprocess.run(['adb', '-s', device.serial, 'pull', source_path, backup_path],
                                 capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"Backup สำเร็จ: {backup_path}")
            else:
                print(f"Backup ล้มเหลว: {result.stderr}")
                backup_failed_game_data(device)
        else:
            print("ไม่พบ gear ใดๆ - ทำการ backup ไปที่ random-Fail")
            backup_failed_game_data(device)

        print("\n10. เสร็จสิ้นกระบวนการ - ทำการ clear app")
        clear_app(device)
        time.sleep(6)
        return True

    except Exception as e:
        print(f"\nเกิดข้อผิดพลาดในกระบวนการ random-gear: {e}")
        clear_app(device)
        time.sleep(6)
        return False


import pytesseract
from PIL import Image
import io
import os
import tempfile

# ===== ตั้งค่า Tesseract Path (ปรับตามที่ติดตั้งในเครื่อง) =====
try:
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
except:
    pass

# ===== ฟังก์ชันจัดการไฟล์ภาพชั่วคราว =====

def get_temp_screenshot_path(device_serial):
    """
    สร้างพาธสำหรับไฟล์ screenshot ชั่วคราว
    แยกตาม device serial (port) เพื่อไม่ให้ปนกัน
    """
    try:
        # สร้างโฟลเดอร์ temp-screenshots ถ้ายังไม่มี
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp-screenshots")
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
        
        # ดึง port จาก serial (เช่น 127.0.0.1:5557 -> 5557)
        port = device_serial.split(':')[-1] if ':' in device_serial else device_serial
        
        # สร้างชื่อไฟล์แยกตาม port
        filename = f"screenshot_{port}.png"
        filepath = os.path.join(temp_dir, filename)
        
        return filepath
    except Exception as e:
        print(f"Error creating temp path: {e}")
        return None

def save_screenshot_temp(device, filepath):
    """
    บันทึก screenshot เป็นไฟล์ชั่วคราว
    """
    try:
        # จับภาพหน้าจอ
        cap = device.screencap()
        image = np.frombuffer(cap, dtype=np.uint8)
        adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
        
        # บันทึกเป็นไฟล์
        cv2.imwrite(filepath, adb_img)
        print(f"  ✓ บันทึก screenshot: {filepath}")
        
        return adb_img
    except Exception as e:
        print(f"Error saving screenshot: {e}")
        return None

def delete_temp_screenshot(filepath):
    """
    ลบไฟล์ screenshot ชั่วคราว
    """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"  ✓ ลบไฟล์ชั่วคราว: {filepath}")
            return True
        return False
    except Exception as e:
        print(f"Error deleting temp file: {e}")
        return False

def cleanup_all_temp_screenshots():
    """
    ลบไฟล์ screenshot ชั่วคราวทั้งหมด (ใช้เมื่อจบโปรแกรม)
    """
    try:
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp-screenshots")
        if os.path.exists(temp_dir):
            for filename in os.listdir(temp_dir):
                if filename.endswith('.png'):
                    filepath = os.path.join(temp_dir, filename)
                    try:
                        os.remove(filepath)
                        print(f"  ✓ ลบ {filename}")
                    except:
                        pass
            print("  ✓ ล้างไฟล์ชั่วคราวทั้งหมดสำเร็จ")
        return True
    except Exception as e:
        print(f"Error cleanup temp files: {e}")
        return False

# ===== OCR Functions =====

def search_gear_text_in_screenshot(screenshot_path, gear_names, threshold=0.95):
    """
    ค้นหาชื่อ gear ในไฟล์ screenshot
    - สแกนทั้งภาพโดยไม่แบ่ง region
    - ใช้ threshold 0.95 ในการจับคู่ข้อความ
    """
    found_gears = set()
    
    try:
        print(f"  กำลังสแกนข้อความทั้งหมดในรูป: {os.path.basename(screenshot_path)}")
        print(f"  ใช้ threshold: {threshold}")
        
        # สแกนทั้งภาพเลย ไม่แบ่ง region
        extracted_text = extract_text_from_region(screenshot_path, region_percent=None)
        
        if extracted_text:
            print(f"  ข้อความที่พบ: '{extracted_text[:200]}...'")  # แสดงแค่ 200 ตัวอักษรแรก
            
            # ตรวจสอบแต่ละ gear name
            for gear_name in gear_names:
                if gear_name in found_gears:
                    continue
                
                # ทำความสะอาดข้อความ
                clean_gear = gear_name.lower().replace(' ', '').replace('-', '').replace('_', '')
                clean_extracted = extracted_text.lower().replace(' ', '').replace('-', '').replace('_', '')
                
                # 1. Exact match (100%)
                if clean_gear == clean_extracted:
                    found_gears.add(gear_name)
                    print(f"  ✓ พบ (exact match 100%): {gear_name}")
                    continue
                
                # 2. Contains with exact substring
                if clean_gear in clean_extracted:
                    found_gears.add(gear_name)
                    print(f"  ✓ พบ (contains): {gear_name}")
                    continue
                
                # 3. Similarity >= threshold (0.95)
                max_len = max(len(clean_gear), len(clean_extracted))
                if max_len > 0:
                    # คำนวณความคล้าย
                    matches = sum(c1 == c2 for c1, c2 in zip(clean_gear, clean_extracted))
                    similarity = matches / max_len
                    
                    if similarity >= threshold:
                        found_gears.add(gear_name)
                        print(f"  ✓ พบ (similarity {similarity:.2%}): {gear_name}")
                        continue
        else:
            print("  ไม่พบข้อความในรูป")
        
        return found_gears
        
    except Exception as e:
        print(f"Error in search_gear_text_in_screenshot: {e}")
        return set()




def extract_text_from_region(image_path, region_percent=None, scales=[1.0]):
    """
    ดึงข้อความจากรูปภาพพร้อมปรับปรุงคุณภาพ
    - ปรับความคมชัด แปลงเป็นขาวดำ
    - ลอง scale หลายขนาด
    - ใช้ config หลายแบบ
    """
    all_texts = []
    
    try:
        # อ่านภาพต้นฉบับ
        img = cv2.imread(image_path)
        if img is None:
            return ""
        
        # ถ้าระบุ region ให้ crop
        if region_percent:
            h, w = img.shape[:2]
            x_percent, y_percent, w_percent, h_percent = region_percent
            x = int(w * x_percent)
            y = int(h * y_percent)
            region_w = int(w * w_percent)
            region_h = int(h * h_percent)
            img = img[y:y+region_h, x:x+region_w]
        
        # ⭐ ปรับปรุงภาพสำหรับ OCR
        def preprocess_image(image):
            """ปรับแต่งภาพให้เหมาะกับ OCR"""
            # แปลงเป็น grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # เพิ่มความคมชัด (Sharpening)
            kernel = np.array([[-1,-1,-1],
                              [-1, 9,-1],
                              [-1,-1,-1]])
            sharpened = cv2.filter2D(gray, -1, kernel)
            
            # ทำ Otsu's thresholding (แปลงเป็นขาวดำอัตโนมัติ)
            _, thresh = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            return thresh
        
        # ⭐ ลองหลาย scale
        scales_to_try = [1.0, 1.5, 2.0, 2.5]
        
        for scale in scales_to_try:
            # ขยายภาพ
            if scale != 1.0:
                h, w = img.shape[:2]
                scaled_img = cv2.resize(img, (int(w * scale), int(h * scale)), 
                                       interpolation=cv2.INTER_CUBIC)
            else:
                scaled_img = img.copy()
            
            # ลอง 3 แบบ: ปกติ, ปรับแต่งแล้ว, และ invert
            versions = [
                ('original', scaled_img),
                ('preprocessed', preprocess_image(scaled_img)),
            ]
            
            # เพิ่ม inverted version (ขาวเป็นดำ, ดำเป็นขาว)
            preprocessed = preprocess_image(scaled_img)
            inverted = cv2.bitwise_not(preprocessed)
            versions.append(('inverted', inverted))
            
            for version_name, processed_img in versions:
                # ⭐ ลอง config หลายแบบ
                custom_configs = [
                    r'--oem 3 --psm 6',   # Block of text
                    r'--oem 3 --psm 11',  # Sparse text
                    r'--oem 3 --psm 3',   # Fully automatic
                    r'--oem 3 --psm 4',   # Single column
                    r'--oem 1 --psm 6',   # LSTM only
                ]
                
                for config in custom_configs:
                    try:
                        text = pytesseract.image_to_string(processed_img, config=config)
                        text = text.strip()
                        text = ' '.join(text.split())
                        
                        if text and len(text) > 2:  # เก็บเฉพาะข้อความที่มีความยาว > 2
                            all_texts.append(text)
                    except:
                        continue
        
        # รวมข้อความทั้งหมด (ไม่ซ้ำ)
        if all_texts:
            unique_texts = list(set(all_texts))
            return ' '.join(unique_texts)
        
        return ""
        
    except Exception as e:
        print(f"Error in extract_text_from_region: {e}")
        return ""






def check_gear_images_with_ocr(device):
    """
    ✨ ฟังก์ชันหลัก - ตรวจสอบ gear ด้วย OCR
    
    ขั้นตอน:
    1. แคปรูปหน้าจอ → บันทึกเป็นไฟล์ชั่วคราว
    2. ใช้ OCR สแกนข้อความทั้งหมดในรูป
    3. ลบไฟล์ชั่วคราวทิ้ง
    """
    temp_file = None
    
    try:
        print("\n" + "="*60)
        print(f"=== เริ่มตรวจสอบ gear ด้วย OCR (Device: {device.serial}) ===")
        print("="*60)
        
        # โหลด config
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
                gear_mapping = config.get('gearname', {})
                use_ocr = config.get('use_ocr', True)
                
                if not use_ocr:
                    print("  OCR ถูกปิดใน config - ใช้การจับภาพแบบเดิม")
                    cap = device.screencap()
                    image = np.frombuffer(cap, dtype=np.uint8)
                    adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                    return check_gear_images_fallback(adb_img, gear_mapping)
                    
        except Exception as e:
            print(f"Error loading config: {e}")
            gear_mapping = {
                'gearimg1': 'Leonard Ring',
                'gearimg2': 'Eden-Uniform',
                'gearimg3': 'Thorn-weapons',
                'gearimg4': 'MoonlitDagger'
            }
        
        gear_names = list(gear_mapping.values())
        print(f"  กำลังค้นหา: {gear_names}")
        
        # ขั้นตอนที่ 1: แคปและบันทึกเป็นไฟล์ชั่วคราว
        print("\n[1/3] กำลังแคปหน้าจอ...")
        temp_file = get_temp_screenshot_path(device.serial)
        
        if not temp_file:
            print("  ✗ สร้างพาธไฟล์ล้มเหลว - ใช้วิธีเดิม")
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            return check_gear_images_fallback(adb_img, gear_mapping)
        
        adb_img = save_screenshot_temp(device, temp_file)
        
        if adb_img is None:
            print("  ✗ บันทึก screenshot ล้มเหลว - ใช้วิธีเดิม")
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            return check_gear_images_fallback(adb_img, gear_mapping)
        
        # ขั้นตอนที่ 2: ใช้ OCR สแกนทั้งภาพ
        print("\n[2/3] กำลังใช้ OCR สแกนทั้งภาพ...")
        found_gears = search_gear_text_in_screenshot(temp_file, gear_names)
        
        # ขั้นตอนที่ 3: ลบไฟล์ชั่วคราว
        print("\n[3/3] ลบไฟล์ชั่วคราว...")
        delete_temp_screenshot(temp_file)
        
        # แสดงผลลัพธ์
        print("\n" + "="*60)
        if found_gears:
            print(f"✓ พบ gear ทั้งหมด {len(found_gears)} ชิ้น:")
            for i, gear in enumerate(found_gears, 1):
                print(f"  {i}. {gear}")
        else:
            print("✗ ไม่พบ gear ด้วย OCR - ลองใช้วิธีเดิม...")
            found_gears = check_gear_images_fallback(adb_img, gear_mapping)
            
            if found_gears:
                print(f"✓ พบ gear ด้วยวิธีเดิม {len(found_gears)} ชิ้น:")
                for i, gear in enumerate(found_gears, 1):
                    print(f"  {i}. {gear}")
        print("="*60 + "\n")
        
        return found_gears
        
    except Exception as e:
        print(f"Error in check_gear_images_with_ocr: {e}")
        
        # ลบไฟล์ชั่วคราวถ้ามี error
        if temp_file and os.path.exists(temp_file):
            try:
                delete_temp_screenshot(temp_file)
            except:
                pass
        
        # Fallback
        try:
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            return check_gear_images_fallback(adb_img, {})
        except:
            return set()


def check_gear_images(device_or_image):
    """
    ฟังก์ชันหลัก - บังคับใช้วิธีเดิม (ไม่ใช้ OCR)
    รองรับการหารูปตามจำนวนที่กำหนดใน config.json
    
    รองรับทั้ง:
    - device object → แคปรูปก่อน แล้วใช้วิธีเดิม
    - adb_img → ใช้วิธีเดิมโดยตรง
    
    Returns:
        set: เซ็ตของชื่อ gear ที่พบ
    """
    try:
        # โหลด config สำหรับ gear mapping
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
                gear_mapping = config.get('gearname', {})
        except Exception as e:
            print(f"Error loading config: {e} - ใช้ค่าเริ่มต้น")
            gear_mapping = {
                'gearimg1': 'Leonard Ring',
                'gearimg2': 'Eden-Uniform',
                'gearimg3': 'Thorn-weapons',
                'gearimg4': 'MoonlitDagger'
            }
        
        # นับจำนวน gear ที่ต้องตรวจสอบจาก config
        gear_count = len(gear_mapping)
        print(f"  จำนวน gear ที่ต้องตรวจสอบ: {gear_count} รูป")
        
        # ดึงรูปภาพ
        if hasattr(device_or_image, 'screencap'):
            # เป็น device object → แคปรูปก่อน
            print(f"  กำลังแคปหน้าจอจาก device {device_or_image.serial}...")
            cap = device_or_image.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
        else:
            # เป็น image อยู่แล้ว
            print("  ใช้รูปภาพที่ส่งมาโดยตรง...")
            adb_img = device_or_image
        
        # ใช้วิธีเดิม (จับรูป) ด้วย threshold 0.95
        print("  กำลังตรวจสอบ gear ด้วยการจับรูปภาพ (threshold=0.95)...")
        return check_gear_images_fallback(adb_img, gear_mapping)
        
    except Exception as e:
        print(f"Error in check_gear_images: {e}")
        return set()


def check_gear_images_fallback(adb_img, gear_mapping):
    """
    ระบบสำรอง: ใช้การจับภาพแบบเดิม
    ใช้ threshold 0.95 เท่านั้น
    รองรับจำนวน gear ไม่จำกัด (ตามที่กำหนดใน config)
    """
    try:
        found_gears = set()
        
        # ใช้ค่าเริ่มต้นถ้าไม่มี gear_mapping
        if not gear_mapping:
            print("  ⚠️ ไม่พบ gearname ใน config - ใช้ค่าเริ่มต้น")
            gear_mapping = {
                'gearimg1': 'Leonard Ring',
                'gearimg2': 'Eden-Uniform',
                'gearimg3': 'Thorn-weapons',
                'gearimg4': 'MoonlitDagger'
            }
        
        print(f"  ใช้การจับภาพแบบเดิม (threshold=0.95)...")
        
        # ใช้ threshold 0.95 เท่านั้น
        threshold = 0.95
        
        # วนลูปตามจำนวน gear ใน config
        for gear_key, gear_name in gear_mapping.items():
            # ดึงเลขจาก key (เช่น gearimg1 -> 1, gearimg5 -> 5)
            try:
                gear_num = gear_key.replace('gearimg', '')
                if not gear_num.isdigit():
                    print(f"  ⚠️ ข้ามรูป {gear_key} (รูปแบบไม่ถูกต้อง)")
                    continue
                
                # ตรวจสอบว่ามีไฟล์รูปหรือไม่
                img_path = f'img/{gear_key}.png'
                if not os.path.exists(img_path):
                    print(f"  ⚠️ ไม่พบไฟล์รูป: {img_path}")
                    continue
                
                # จับรูป
                gear_pos = ImgSearchADB(adb_img, img_path, threshold=threshold)
                if gear_pos:
                    found_gears.add(gear_name)
                    print(f"  ✓ พบ {gear_name} จาก {gear_key}.png")
                    
                    # Track gear count
                    ds = get_device_state()
                    if ds:
                        with ds.lock:
                            current_count = ds.gear_counts.get(gear_name, 0)
                            ds.gear_counts[gear_name] = current_count + 1
                else:
                    print(f"  ✗ ไม่พบ {gear_name} ({gear_key}.png)")
                    
            except Exception as e:
                print(f"  ⚠️ Error checking {gear_key}: {e}")
                continue
        
        return found_gears
        
    except Exception as e:
        print(f"Error in check_gear_images_fallback: {e}")
        return set()



# ===== ฟังก์ชันทดสอบ =====

def test_ocr_detection(device):
    """
    ทดสอบระบบ OCR
    """
    print("\n" + "="*70)
    print("=== ทดสอบระบบ OCR (Temporary Screenshot Method) ===")
    print("="*70 + "\n")
    
    print("กำลังทดสอบ...")
    found_gears = check_gear_images(device)
    
    print("\n" + "="*70)
    print("=== สรุปผลการทดสอบ ===")
    print("="*70)
    print(f"พบ gear ทั้งหมด: {len(found_gears)} ชิ้น")
    
    if found_gears:
        for i, gear in enumerate(found_gears, 1):
            print(f"  {i}. {gear}")
    else:
        print("  ไม่พบ gear")
    
    print("="*70 + "\n")
    
    return found_gears


def process_check_gear(device):
    """Process check-gear sequence"""
    print(f"\n=== เริ่มกระบวนการ check-gear สำหรับอุปกรณ์: {device.serial} ===\n")
    network_monitor = NetworkMonitor()
    
    # ค้นหาและกด findgear1.png
    while True:
        try:
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            network_status = network_monitor.check_network(device, adb_img)
            if network_status == "reset_first_loop":
                return "reset_first_loop"
            if network_status:
                continue
                
            findgear1_pos = ImgSearchADB(adb_img, 'img/findgear1.png')
            if findgear1_pos:
                tap_x, tap_y = findgear1_pos[0][0], findgear1_pos[0][1]
                print(f"พบ findgear1.png บนอุปกรณ์ {device.serial} - กดที่ตำแหน่ง ({tap_x}, {tap_y})")
                device.shell(f"input tap {tap_x} {tap_y}")
                time.sleep(1.5)  # เพิ่ม delay หลังกด
                break
            time.sleep(0.5)
        except Exception as e:
            print(f"Error finding findgear1.png: {e}")
            time.sleep(1)
    
    # ค้นหาและกด findgear2.png
    while True:
        try:
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            network_status = network_monitor.check_network(device, adb_img)
            if network_status == "reset_first_loop":
                return "reset_first_loop"
            if network_status:
                continue

            findgear2_pos = ImgSearchADB(adb_img, 'img/findgear2.png')
            if findgear2_pos:
                tap_x, tap_y = findgear2_pos[0][0], findgear2_pos[0][1]
                print(f"พบ findgear2.png บนอุปกรณ์ {device.serial} - กดที่ตำแหน่ง ({tap_x}, {tap_y})")
                device.shell(f"input tap {tap_x} {tap_y}")
                time.sleep(1.5)  # เพิ่ม delay หลังกด
                break
            time.sleep(0.5)
        except Exception as e:
            print(f"Error finding findgear2.png: {e}")
            time.sleep(1)
    
    # ค้นหาและกด findgear3.png
    while True:
        try:
            cap = device.screencap()
            image = np.frombuffer(cap, dtype=np.uint8)
            adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            
            network_status = network_monitor.check_network(device, adb_img)
            if network_status == "reset_first_loop":
                return "reset_first_loop"
            if network_status:
                continue

            findgear3_pos = ImgSearchADB(adb_img, 'img/findgear3.png')
            if findgear3_pos:
                tap_x, tap_y = findgear3_pos[0][0], findgear3_pos[0][1]
                print(f"พบ findgear3.png บนอุปกรณ์ {device.serial} - กดที่ตำแหน่ง ({tap_x}, {tap_y})")
                device.shell(f"input tap {tap_x} {tap_y}")
                time.sleep(1.5)  # เพิ่ม delay หลังกด
                break
            time.sleep(0.5)
        except Exception as e:
            print(f"Error finding findgear3.png: {e}")
            time.sleep(1)
    
    # ดำเนินการตามลำดับ checkgear2 และ checkgear3
    for check_img in ['checkgear2.png', 'checkgear3.png']:
        while True:
            try:
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                network_status = network_monitor.check_network(device, adb_img)
                if network_status == "reset_first_loop":
                    return "reset_first_loop"
                if network_status:
                    continue

                check_pos = ImgSearchADB(adb_img, f'img/{check_img}')
                if check_pos:
                    tap_x, tap_y = check_pos[0][0], check_pos[0][1]
                    print(f"พบ {check_img} บนอุปกรณ์ {device.serial} - กดที่ตำแหน่ง ({tap_x}, {tap_y})")
                    device.shell(f"input tap {tap_x} {tap_y}")
                    time.sleep(1.5)  # เพิ่ม delay หลังกด
                    break
                time.sleep(0.5)
            except Exception as e:
                print(f"Error finding {check_img}: {e}")
                time.sleep(1)
    
    print("\nเริ่มตรวจสอบ gear...")
    all_found_gears = set()

    # ⭐⭐⭐ แก้ไขตรงนี้: ส่ง device แทน adb_img ⭐⭐⭐
    print("รอบที่ 1: ตรวจสอบโดยตรง")
    all_found_gears.update(check_gear_images(device))  # ← เปลี่ยนจาก adb_img เป็น device
    time.sleep(5)
    
    # ตรวจสอบว่ามี weapons1.png หรือไม่
    cap = device.screencap()
    image = np.frombuffer(cap, dtype=np.uint8)
    adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
    
    weapons1_pos = ImgSearchADB(adb_img, 'img/weapons1.png')
    if weapons1_pos:
        print("\nรอบที่ 2: ตรวจสอบหลังกด weapons1.png")
        device.shell(f"input tap {weapons1_pos[0][0]} {weapons1_pos[0][1]}")
        time.sleep(2)
        
        # ⭐⭐⭐ แก้ไขตรงนี้: ส่ง device แทน adb_img ⭐⭐⭐
        all_found_gears.update(check_gear_images(device))  # ← เปลี่ยนจาก adb_img เป็น device
        time.sleep(5)
    
    # ดึง image ใหม่เพื่อเช็ค weapons2
    cap = device.screencap()
    image = np.frombuffer(cap, dtype=np.uint8)
    adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
    
    weapons2_pos = ImgSearchADB(adb_img, 'img/weapons2.png')
    if weapons2_pos:
        print("\nรอบที่ 3: ตรวจสอบหลังกด weapons2.png")
        device.shell(f"input tap {weapons2_pos[0][0]} {weapons2_pos[0][1]}")
        time.sleep(2)
        
        # ⭐⭐⭐ แก้ไขตรงนี้: ส่ง device แทน adb_img ⭐⭐⭐
        all_found_gears.update(check_gear_images(device))  # ← เปลี่ยนจาก adb_img เป็น device
        time.sleep(5)

    print("\nเริ่มการ backup...")
    
    # ⭐ ดึง device_state ก่อน - ใช้ได้ทั้งกรณีพบและไม่พบ gear
    ds = get_device_state()
    
    if all_found_gears:
        if ds is None:
            print(f"Error during backup: device_state is None")
            original_filename = None
        else:
            original_filename = ds.original_filenames.get(device.serial)
        
        if original_filename:
            base_name, ext = os.path.splitext(original_filename)
            if len(all_found_gears) > 1:
                gear_prefix = "+".join(sorted(all_found_gears))
            else:
                gear_prefix = next(iter(all_found_gears))
            filename = f"{gear_prefix}+{base_name}{ext}"
        else:
            if len(all_found_gears) > 1:
                filename = "+".join(sorted(all_found_gears))
            else:
                filename = next(iter(all_found_gears))
            filename += "_LINE_COCOS_PREF_KEY.xml"
        
        print(f"พบ gear ทั้งหมด: {', '.join(all_found_gears)}")
        print(f"ชื่อไฟล์ที่จะ backup: {filename}")
        
        backup_dir = "backup-id"
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
            print(f"สร้างโฟลเดอร์ backup-id")
        
        source_path = "/data/data/com.linecorp.LGRGS/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
        backup_path = os.path.join(backup_dir, filename)
        
        device.shell("su -c 'chmod 777 /data/data/com.linecorp.LGRGS/shared_prefs'")
        device.shell(f"su -c 'chmod 777 {source_path}'")
        
        result = subprocess.run(['adb', '-s', device.serial, 'pull', source_path, backup_path],
                             capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"Backup สำเร็จ: {backup_path}")
            # Increment success count
            if ds:
                with ds.lock:
                    ds.success_count.value += 1
        else:
            print(f"Backup ล้มเหลว: {result.stderr}")
            backup_failed_game_data(device)
            # กรณี Backup ล้มเหลว ก็ยังถือว่าจบ process แล้ว ให้เป็น success
            if ds:
                with ds.lock:
                    ds.success_count.value += 1
    else:
        print("ไม่พบ gear ใดๆ - ทำการ backup ไปที่ random-Fail")
        backup_failed_game_data(device)
        # ไม่เจอ gear แต่ทำงานจนจบ ถือว่า success
        if ds:
            with ds.lock:
                ds.success_count.value += 1

    print("\nเสร็จสิ้นกระบวนการ check-gear - ทำการ clear app และเริ่มใหม่")
    clear_app(device)
    time.sleep(6)
    return True


def process_single_device(device_serial, manager_dict, device_state):
    """
    ฟังก์ชันหลักในการประมวลผลอุปกรณ์แต่ละตัว
    แก้ไขให้รับ device_serial แทน device object
    """
    # Make device_state available globally in this subprocess
    global _device_state_local
    _device_state_local = device_state
    
    try:
        # เชื่อมต่ออุปกรณ์ใหม่ใน process นี้ (พร้อม retry)
        max_retries = 5
        adb = None
        device = None
        
        for attempt in range(max_retries):
            try:
                adb = AdbClient(host="127.0.0.1", port=5037)
                devices_list = adb.devices()
                
                # ค้นหา device ที่ต้องการ
                device = None
                for d in devices_list:
                    if d.serial == device_serial:
                        device = d
                        break
                
                if device:
                    print(f"[INFO] เชื่อมต่อ device {device_serial} สำเร็จ (attempt {attempt + 1})")
                    break
                else:
                    print(f"[WARNING] ไม่พบ device {device_serial} (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        time.sleep(2)
            except Exception as e:
                print(f"[WARNING] เชื่อมต่อล้มเหลว (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        
        if not device:
            print(f"[ERROR] ไม่สามารถเชื่อมต่ออุปกรณ์ {device_serial} หลังจากลองไป {max_retries} ครั้ง")
            return
            
    except Exception as e:
        print(f"[ERROR] เชื่อมต่อ device {device_serial} ล้มเหลว: {e}")
        return
    
    device_first_loop = False
    network_monitor = NetworkMonitor()
    
    def load_feature_config():
        """โหลดการตั้งค่าฟีเจอร์จาก config.json"""
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Error loading config: {e}")
            return {
                'loop1': 1,
                '7day': 0, 
                'shopgacha': 0,
                'swap_shop': 1,
                'box_settings': {'first_round': 1, 'second_round': 1},
                'random-gear': 0,
                'check-gear': 0
            }

    def log_status(message, level="INFO"):
        """แสดงสถานะพร้อม timestamp"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [{level}] Device {device.serial}: {message}")

    def cleanup_resources():
        """ล้างหน่วยความจำ"""
        gc.collect()

    def check_device_connection():
        """ตรวจสอบการเชื่อมต่ออุปกรณ์"""
        try:
            device.shell("echo 'test connection'")
            return True
        except:
            log_status("Lost connection, attempting to reconnect...", "WARNING")
            try:
                subprocess.run(["adb", "connect", device.serial])
                time.sleep(2)
                device.shell("echo 'test connection'")
                log_status("Reconnection successful")
                return True
            except:
                log_status("Reconnection failed", "ERROR")
                return False

    # ⭐ INITIAL CLEAR - Clear app ครั้งแรก ก่อนเริ่มทำงาน
    print(f"[INIT] ล้างแอป Line Ranger บน {device.serial} ก่อนเริ่มทำงาน...")
    clear_app(device)
    time.sleep(0.5)
    print(f"[INIT] ล้างเสร็จแล้ว เริ่มทำงานปกติ...")

    first_loop_mode = 0  # 0=normal, 1=force
    
    while True:
        try:
            # ตรวจสอบและฟื้นตัวการเชื่อมต่อ ADB หากขาดหาย
            if not check_device_connection():
                print(f"[WARNING] Device {device.serial} not responding, retrying connection...")
                time.sleep(3)
                continue
            
            # ⭐⭐⭐ เช็ค fixid, fixunkown, apple ทุกรอบ - ไม่ว่าจะอยู่ขั้นตอนไหน!
            try:
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                critical_error = check_critical_errors(device, adb_img, "main_loop")
                if critical_error in ["fixid", "fixunkown"]:
                    log_status(f"Found {critical_error}! Backing up to backupxml and getting new file...", "WARNING")
                    device_first_loop = False
                    first_loop_mode = 1
                    continue  # วนกลับไปหยิบไฟล์ใหม่
                elif critical_error == "apple":
                    log_status("Found apple! Backing up to login-fail and restarting...", "WARNING")
                    device_first_loop = False
                    first_loop_mode = 1
                    continue
            except Exception as e:
                log_status(f"Error checking critical images: {e}", "ERROR")
            
            log_status("=== Device Status ===")
            
            # โหลดการตั้งค่า
            config = load_feature_config()
            first_loop_enabled = config.get('loop1', 1)
            seven_day_enabled = config.get('7day', 0) 
            swap_shop_enabled = config.get('swap_shop', 0)
            shopgacha_enabled = config.get('shopgacha', 0)
            random_gear_enabled = config.get('random-gear', 0)
            check_gear_enabled = config.get('check-gear', 0)
            auto_trade_config = config.get('auto_trade', {})
            auto_trade_enabled = auto_trade_config.get('enabled', 1) if isinstance(auto_trade_config, dict) else 0

            log_status(f"""Feature Status:
            First Loop: {'Enabled' if first_loop_enabled else 'Disabled'}
            7 Day: {'Enabled' if seven_day_enabled else 'Disabled'}
            Swap Shop: {'Enabled' if swap_shop_enabled else 'Disabled'} 
            Shop Gacha: {'Enabled' if shopgacha_enabled else 'Disabled'}
            Random Gear: {'Enabled' if random_gear_enabled else 'Disabled'}
            Check Gear: {'Enabled' if check_gear_enabled else 'Disabled'}
            Auto Trade: {'Enabled' if auto_trade_enabled else 'Disabled'}
            """)

            # ตรวจสอบและทำ first loop
            # Logic ใหม่: ทำถ้า device_first_loop เป็น False และ (เปิด config หรือเป็นการบังคับ force reset)
            should_run_first_loop = not device_first_loop and (first_loop_enabled or first_loop_mode == 1)

            if should_run_first_loop:
                log_status(f"Starting first loop process (Mode: {'Forced' if first_loop_mode == 1 else 'Normal'})")
                
                while True:
                    result = first_loop_process(device)
                    if result == "complete":
                        device_first_loop = True
                        first_loop_mode = 0  # Reset force mode
                        log_status("First loop completed successfully!")
                        break
                    elif result == "restart_from_test":
                        log_status("Restarting from test.png", "WARNING")
                        continue
                    elif result == "restart_first_loop":
                        log_status("Found closeapp.png or fixcak.png, restarting entire first_loop process", "WARNING")
                        continue
                    # ⭐ เพิ่มการจัดการ restart_with_new_file จาก first_loop (fixid.png)
                    elif result == "restart_with_new_file":
                        log_status("Found fixid.png in first_loop! Restarting first_loop immediately...", "WARNING")
                        # ⭐ Continue วนกลับไปเริ่ม first_loop ใหม่เลย - ไม่ต้องหยิบไฟล์ก่อน
                        # ไฟล์ถูก backup ไป backupxml แล้ว จะถูกหยิบมาใช้หลังจาก first_loop เสร็จ
                        continue  # วนกลับไปเริ่ม first_loop ใหม่ทันที
                    else:
                        log_status("First loop failed, retrying in 5 seconds...", "ERROR")
                        time.sleep(5)
                        continue
            
            elif not device_first_loop and not first_loop_enabled:
                log_status("First loop is disabled, skipping...")
                device_first_loop = True

            # ตรวจสอบไฟล์ XML
            if not has_xml_files():
                log_status("No XML files available, waiting...")
                time.sleep(5)
                continue

            # ประมวลผลไฟล์ XML
            if process_single_file_for_device(device, device_state):
                log_status("Starting login process")
                
                login_result = main_login(device)
                
                if login_result == "restart_loop1" or login_result == "reset_first_loop":
                    log_status("Reset signal received from Apple.png - Forcing new first loop", "WARNING")
                    device_first_loop = False
                    first_loop_mode = 1  # Enable force mode to bypass config check
                    cleanup_resources()
                    continue
                
                # ⭐ เพิ่มการจัดการ restart_with_new_file (fixid/fixunkown ค้าง timeout)
                elif login_result == "restart_with_new_file":
                    log_status("fixid/fixunkown timeout - File backed up to backupxml, restarting first_loop first...", "WARNING")
                    device_first_loop = False
                    first_loop_mode = 1  # Enable force mode to bypass config check
                    cleanup_resources()
                    # ⭐ Continue กลับไปต้น loop → first_loop จะรันก่อน → แล้วค่อยหยิบไฟล์ใหม่
                    continue
                
                elif login_result == "restart":
                    log_status("Found fixid 30 times, backing up to login-fail", "WARNING")
                    if backup_failed_login(device):
                        log_status("Backup to login-fail successful")
                        # Increment fail count
                        ds_local = get_device_state()
                        if ds_local:
                            with ds_local.lock:
                                ds_local.fail_count.value += 1
                    else:
                        log_status("Backup to login-fail failed", "ERROR")

                    
                    cleanup_resources()
                    clear_app(device)
                    time.sleep(6)
                    continue
                
                elif login_result == "normal_complete":
                    log_status("Login completed successfully")
                    
                    # 7-day process
                    log_status("Starting 7-day process")
                    try:
                        result_7day = func_7day(device)
                        # ⭐ เช็ค return value - ถ้าพบ fixid/fixunkown/apple ให้ restart first_loop
                        if result_7day in ["fixid", "fixunkown", "apple"]:
                            log_status(f"Found {result_7day} in 7-day! Restarting first_loop...", "WARNING")
                            device_first_loop = False
                            first_loop_mode = 1  # Enable force mode
                            cleanup_resources()
                            continue  # กลับไปต้น loop → first_loop ก่อน → แล้วค่อยหยิบไฟล์ใหม่
                        log_status("7-day process completed")
                    except Exception as e:
                        log_status(f"7-day process error: {e}", "ERROR")
                    time.sleep(2)
                    
                    # Box process
                    log_status("Starting box process")
                    try:
                        result_box = main_box(device)
                        # ⭐ เช็ค return value - ถ้าพบ fixid/fixunkown/apple ให้ restart first_loop
                        if result_box in ["fixid", "fixunkown", "apple"]:
                            log_status(f"Found {result_box} in box! Restarting first_loop...", "WARNING")
                            device_first_loop = False
                            first_loop_mode = 1  # Enable force mode
                            cleanup_resources()
                            continue  # กลับไปต้น loop → first_loop ก่อน → แล้วค่อยหยิบไฟล์ใหม่
                        log_status("Box process completed")
                    except Exception as e:
                        log_status(f"Box process error: {e}", "ERROR")
                    time.sleep(2)
                    
                    # Auto trade process (ซื้อสินค้าใน swap shop อัตโนมัติ)
                    if auto_trade_enabled:
                        log_status("Starting auto trade process")
                        try:
                            auto_trade_result = auto_trade(device)
                            # ⭐ เช็ค return value จาก auto_trade - ถ้าเจอ fixid ให้ restart first_loop
                            if auto_trade_result == "restart_with_new_file":
                                log_status("Found fixid in auto_trade! Backing up to backupxml and restarting first_loop...", "WARNING")
                                device_first_loop = False
                                first_loop_mode = 1  # Enable force mode
                                cleanup_resources()
                                continue  # กลับไปต้น loop → first_loop ก่อน → แล้วค่อยหยิบไฟล์ใหม่
                            log_status("Auto trade process completed")
                        except Exception as e:
                            log_status(f"Auto trade process error: {e}", "ERROR")
                        time.sleep(2)
                    
                    # Shop gacha process
                    if shopgacha_enabled:
                        log_status("Starting shop gacha process")
                        try:
                            result_shopgacha = process_shopgacha(device)
                            # ⭐ เช็ค return value - ถ้าพบ fixid/fixunkown/apple ให้ restart first_loop
                            if result_shopgacha in ["fixid", "fixunkown", "apple"]:
                                log_status(f"Found {result_shopgacha} in shopgacha! Restarting first_loop...", "WARNING")
                                device_first_loop = False
                                first_loop_mode = 1  # Enable force mode
                                cleanup_resources()
                                continue  # กลับไปต้น loop → first_loop ก่อน → แล้วค่อยหยิบไฟล์ใหม่
                            log_status("Shop gacha process completed")
                        except Exception as e:
                            log_status(f"Shop gacha process error: {e}", "ERROR")
                        time.sleep(1)
                    
                    # Swap shop process
                    if swap_shop_enabled:
                        log_status("Starting swap shop process")
                        try:
                            swap_result = process_swap_shop(device)
                            log_status(f"Swap shop result: {swap_result}")
                            
                            # ⭐ เช็ค return value - ถ้าพบ fixid/fixunkown/apple ให้ restart first_loop
                            if swap_result in ["fixid", "fixunkown", "apple"]:
                                log_status(f"Found {swap_result} in swap_shop! Restarting first_loop...", "WARNING")
                                device_first_loop = False
                                first_loop_mode = 1  # Enable force mode
                                cleanup_resources()
                                continue  # กลับไปต้น loop → first_loop ก่อน → แล้วค่อยหยิบไฟล์ใหม่
                            
                            # ✅ ถ้า process_swap_shop ส่งกลับ "swap_shopevent" ให้รัน process_swap_shopevent
                            if swap_result == "swap_shopevent":
                                log_status("Starting swap shop event process (after channel selection)")
                                try:
                                    event_result = process_swap_shopevent(device)
                                    log_status(f"Swap shop event result: {event_result}")
                                    # ⭐ เช็ค return value จาก swap_shopevent
                                    if event_result in ["fixid", "fixunkown", "apple"]:
                                        log_status(f"Found {event_result} in swap_shopevent! Restarting first_loop...", "WARNING")
                                        device_first_loop = False
                                        first_loop_mode = 1
                                        cleanup_resources()
                                        continue  # กลับไปต้น loop → first_loop ก่อน → แล้วค่อยหยิบไฟล์ใหม่
                                except Exception as e:
                                    log_status(f"Swap shop event error: {e}", "ERROR")
                                time.sleep(1)
                        except Exception as e:
                            log_status(f"Swap shop process error: {e}", "ERROR")
                        time.sleep(1)
                    
                    # Random Gear process
                    if random_gear_enabled:
                        log_status("Starting random-gear process")
                        try:
                            if process_random_gear(device):
                                log_status("Random gear process completed")
                            else:
                                log_status("Random gear process failed", "ERROR")
                        except Exception as e:
                            log_status(f"Random gear process error: {e}", "ERROR")
                        cleanup_resources()
                        continue
                    
                    # Check Gear process
                    elif check_gear_enabled:
                        log_status("Starting check-gear process")
                        try:
                            if process_check_gear(device):
                                log_status("Check gear process completed")
                            else:
                                log_status("Check gear process failed", "ERROR")
                        except Exception as e:
                            log_status(f"Check gear process error: {e}", "ERROR")
                        cleanup_resources()
                        continue
                    
                    # Final backup
                    else:
                        log_status("Performing backup to random-Fail")
                        try:
                            if backup_failed_game_data(device):
                                log_status("Backup successful")
                                # ถือว่าทำงานจบ process (แม้ไม่เจออะไร) -> Success
                                ds_local = get_device_state()
                                if ds_local:
                                    with ds_local.lock:
                                        ds_local.success_count.value += 1
                            else:
                                log_status("Backup failed", "ERROR")
                                # Backup ไม่ได้จริงๆ -> อาจจะนับ fail หรือ success ก็ได้ แต่น่าจะ success เพราะเล่นจบ
                                ds_local = get_device_state()
                                if ds_local:
                                    with ds_local.lock:
                                        ds_local.success_count.value += 1
                        except Exception as e:
                            log_status(f"Backup error: {e}", "ERROR")
                    
                    clear_app(device)
                    cleanup_resources()
                    continue

            else:
                log_status("File processing failed, retrying...", "WARNING")
                time.sleep(5)
            
            # อัพเดทสถานะเป็นระยะ
            if time.time() % 30 < 1:
                cleanup_resources()

        except Exception as e:
            log_status(f"Process error: {str(e)}", "ERROR")
            log_status("Retrying in 5 seconds...", "WARNING")
            time.sleep(5)
            
            if not check_device_connection():
                log_status("Device connection check failed", "WARNING")
                time.sleep(5)
                continue

            cleanup_resources()


def check_fixnet_worker(device_serial, stop_event):
    """
    Process แยกสำหรับตรวจสอบ fixnet.png
    """
    try:
        adb = AdbClient(host="127.0.0.1", port=5037)
        device = adb.device(device_serial)
        
        if not device:
            print(f"[ERROR] Network monitor: ไม่สามารถเชื่อมต่อ {device_serial}")
            return
        
        while not stop_event.is_set():
            try:
                cap = device.screencap()
                image = np.frombuffer(cap, dtype=np.uint8)
                adb_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
                
                fixnet_pos = ImgSearchADB(adb_img, 'img/fixnet.png')
                if fixnet_pos:
                    print(f"พบปัญหาการเชื่อมต่อ (fixnet.png) บนอุปกรณ์ {device_serial}")
                    device.shell(f"input tap {fixnet_pos[0][0]} {fixnet_pos[0][1]}")
                    time.sleep(1)
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการตรวจสอบ fixnet.png: {e}")
            
            time.sleep(2)
    except Exception as e:
        print(f"[ERROR] Network monitor process: {e}")

def stats_monitor_worker(device_state, stop_event):
    """
    Process แยกสำหรับแสดง dashboard สถิติ
    """
    last_display = time.time()
    display_interval = 30  # แสดงทุก 30 วินาที
    
    while not stop_event.is_set():
        try:
            current_time = time.time()
            if current_time - last_display >= display_interval:
                # display_stats_dashboard(device_state) # User requested to disable dashboard
                last_display = current_time
        except Exception as e:
            print(f"[ERROR] Stats monitor process: {e}")
        
        time.sleep(5)


def display_stats_dashboard(device_state):
    """แสดง dashboard สถิติการสุ่มที่ด้านล่างของ terminal"""
    try:
        if device_state is None:
            return
        
        os.system('clear' if os.name == 'posix' else 'cls')
        
        print("\n" + "="*80)
        print("📊 LINE RANGER GACHA STATISTICS DASHBOARD")
        print("="*80)
        
        # Hero statistics
        print("\n🎯 HERO STATISTICS:")
        print("-" * 40)
        hero_counts = dict(device_state.hero_counts)
        if hero_counts:
            total_heroes = sum(hero_counts.values())
            for hero_name, count in sorted(hero_counts.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total_heroes * 100) if total_heroes > 0 else 0
                print(f"  {hero_name}: {count}x ({percentage:.1f}%)")
            print(f"  Total Heroes: {total_heroes}")
        else:
            print("  No heroes found yet")
        
        # Gear statistics
        print("\n⚙️ GEAR STATISTICS:")
        print("-" * 40)
        gear_counts = dict(device_state.gear_counts)
        if gear_counts:
            total_gears = sum(gear_counts.values())
            for gear_name, count in sorted(gear_counts.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total_gears * 100) if total_gears > 0 else 0
                print(f"  {gear_name}: {count}x ({percentage:.1f}%)")
            print(f"  Total Gears: {total_gears}")
        else:
            print("  No gears found yet")
        
        # Backup-id files check
        print("\n📁 BACKUP-ID FILES:")
        print("-" * 40)
        backup_id_dir = "backup-id"
        if os.path.exists(backup_id_dir):
            files = [f for f in os.listdir(backup_id_dir) if f.endswith('.xml')]
            print(f"  Total backup files: {len(files)}")
            for filename in sorted(files)[:10]:  # แสดงแค่ 10 ไฟล์แรก
                print(f"    - {filename}")
            if len(files) > 10:
                print(f"    ... and {len(files) - 10} more files")
        else:
            print("  No backup-id directory found")
        
        # Total gacha count
        print("\n🎰 TOTAL GACHA:")
        print("-" * 40)
        total_gacha = device_state.total_gacha.value
        print(f"  Total gacha attempts: {total_gacha}")
        
        print("\n" + "="*80)
        print(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"[ERROR] Failed to display dashboard: {e}")

def Main():
    print("เริ่มต้นโปรแกรม Line Ranger Auto Bot (Multiprocessing Mode)...")
    
    # ตั้งค่าให้ multiprocessing ใช้ spawn method (สำคัญสำหรับ Windows)
    multiprocessing.set_start_method('spawn', force=True)
    
    if not check_adb_available():
        print("ไม่สามารถตั้งค่า ADB ได้")
        input("กด Enter เพื่อออกจากโปรแกรม...")
        return
    
    while True:
        try:
            adb, devices = connect_to_mumu()
            
            if not devices:
                print("ไม่พบอุปกรณ์ที่เชื่อมต่อ กำลังลองเชื่อมต่อใหม่...")
                time.sleep(5)
                continue
            
            # แปลงเป็น list
            if isinstance(devices, list):
                print(f"พบอุปกรณ์: {[device.serial for device in devices]}")
                device_list = devices
            else:
                print(f"พบอุปกรณ์: {devices.serial}")
                device_list = [devices]
            
            # สร้าง Manager สำหรับแชร์ข้อมูลระหว่าง processes
            manager = Manager()
            manager_dict = manager.dict()
            stop_event = manager.Event()
            
            # สร้าง global device_state ด้วย Manager
            global device_state
            device_state = DeviceState(manager)
            
            processes = []
            network_processes = []
            
            # สร้าง process สำหรับแต่ละอุปกรณ์
            for index, device in enumerate(device_list):
                device_serial = device.serial
                
                print(f"เริ่มต้น Device #{index + 1}: {device_serial}")
                
                # สร้าง main process
                main_process = Process(
                    target=process_single_device,
                    args=(device_serial, manager_dict, device_state),
                    name=f"MainProcess-{device_serial}"
                )
                main_process.daemon = True
                main_process.start()
                processes.append(main_process)
                
                # สร้าง network monitoring process
                network_process = Process(
                    target=check_fixnet_worker,
                    args=(device_serial, stop_event),
                    name=f"NetworkProcess-{device_serial}"
                )
                network_process.daemon = True
                network_process.start()
                network_processes.append(network_process)
            
            print(f"\n{'='*60}")
            print(f"เริ่มต้นทุก device เรียบร้อยแล้ว (รวม {len(device_list)} devices)")
            print(f"CPU Usage: แต่ละ device ใช้ process แยกกัน")
            print(f"{'='*60}\n")
            
            # สร้าง stats monitor process
            stats_process = Process(
                target=stats_monitor_worker,
                args=(device_state, stop_event),
                name="StatsMonitor"
            )
            stats_process.daemon = True
            stats_process.start()
            network_processes.append(stats_process)
            
            try:
                # รอให้ทุก process ทำงานเสร็จ
                for process in processes:
                    process.join()
            except KeyboardInterrupt:
                print("\nได้รับสัญญาณหยุดการทำงาน กำลังปิดโปรแกรม...")
                stop_event.set()
                
                # รอให้ทุก process หยุด (timeout 5 วินาที)
                for process in processes + network_processes:
                    process.join(timeout=5)
                    if process.is_alive():
                        print(f"Force terminating {process.name}...")
                        process.terminate()
                
                # ล้างไฟล์ชั่วคราว
                cleanup_all_temp_screenshots()
                break
                
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการทำงาน: {e}")
                stop_event.set()
                
                for process in processes + network_processes:
                    process.join(timeout=5)
                    if process.is_alive():
                        process.terminate()
                
                print("กำลังเริ่มต้นใหม่...")
                time.sleep(5)
                continue

        except KeyboardInterrupt:
            print("กำลังปิดโปรแกรม...")
            cleanup_all_temp_screenshots()
            break
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการทำงาน: {e}")
            print("กำลังเริ่มต้นใหม่...")
            time.sleep(5)


def Main_GUI():
    """Start bot with GUI interface - GUI code is now integrated in this file"""
    print("🎮 เริ่มต้น BOT LINE RANGERS พร้อม GUI...")
    
    # ตั้งค่าให้ multiprocessing ใช้ spawn method (สำคัญสำหรับ Windows)
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # Already set
    
    try:
        if not GUI_ENABLED:
            print("❌ GUI library ไม่พร้อมใช้งาน")
            print("💡 ติดตั้ง: pip install customtkinter pillow")
            print("📌 ใช้ Console mode แทน...")
            Main()
            return
        
        print("✅ GUI พร้อมใช้งาน!")
        print("🚀 กำลังเปิด GUI...")
        
        # Start GUI
        start_gui()
        
    except Exception as e:
        print(f"❌ GUI Error: {e}")
        print("📌 ใช้ Console mode แทน...")
        import traceback
        traceback.print_exc()
        Main()


if __name__ == '__main__':
    # สำคัญ: ต้องมี freeze_support() สำหรับ Windows
    multiprocessing.freeze_support()
    
    import sys
    
    # Check command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--console' or sys.argv[1] == '-c':
            print("📟 Running in Console Mode...")
            Main()
        elif sys.argv[1] == '--gui' or sys.argv[1] == '-g':
            print("🖥️ Running in GUI Mode...")
            Main_GUI()
        elif sys.argv[1] == '--help' or sys.argv[1] == '-h':
            print("""
╔══════════════════════════════════════════════════════════════╗
║           🎮 BOT LINE RANGERS - HELP                        ║
╠══════════════════════════════════════════════════════════════╣
║  Usage: python mainLG.py [options]                          ║
║                                                              ║
║  Options:                                                    ║
║    --gui, -g      Run with GUI interface (default)          ║
║    --console, -c  Run in console mode only                  ║
║    --help, -h     Show this help message                    ║
║                                                              ║
║  Default: GUI mode if no arguments provided                  ║
╚══════════════════════════════════════════════════════════════╝
            """)
        else:
            print(f"Unknown option: {sys.argv[1]}")
            print("Use --help for usage information")
    else:
        # Default: Run GUI mode
        print("🎮 Starting BOT LINE RANGERS...")
        print("💡 Use --console flag for console-only mode")
        print("")
        Main_GUI()