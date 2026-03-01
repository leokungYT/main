with open('login.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Add RestartTimeoutError
if "class RestartTimeoutError" not in text:
    text = text.replace("class SimpleUIStats:", "class RestartTimeoutError(Exception): pass\n\nclass SimpleUIStats:")

# 2. SimpleUIStats additions
if "self.total_login_time = 0.0" not in text:
    text = text.replace(
        "self.hero_found_list = {}  # {hero_combo: count} e.g. {'Yor': 1, 'Yor+Anya': 2}",
        "self.hero_found_list = {}  # {hero_combo: count} e.g. {'Yor': 1, 'Yor+Anya': 2}\n        self.total_login_time = 0.0\n        self.login_time_count = 0"
    )

if '"total_login_time": self.total_login_time' not in text:
    text = text.replace(
        '"device_statuses": self.device_statuses,\n                    "last_update": time.time()\n                }',
        '"device_statuses": self.device_statuses,\n                    "last_update": time.time(),\n                    "total_login_time": self.total_login_time,\n                    "login_time_count": self.login_time_count\n                }'
    )

if 'self.total_login_time = data.get("total_login_time"' not in text:
    text = text.replace(
        'self.device_statuses = data.get("device_statuses", self.device_statuses)\n                except Exception as eval_e:',
        'self.device_statuses = data.get("device_statuses", self.device_statuses)\n                    self.total_login_time = data.get("total_login_time", self.total_login_time)\n                    self.login_time_count = data.get("login_time_count", self.login_time_count)\n                except Exception as eval_e:'
    )

if 'def record_login_time' not in text:
    text = text.replace(
        'def update(self, total=None, processed=None, success=None, fail=None, devices=None, hero_found=None, \nhero_not_found=None):',
        'def record_login_time(self, duration_sec):\n        self.load_shared()\n        with self.lock:\n            self.total_login_time += duration_sec\n            self.login_time_count += 1\n            self.save_shared()\n\n    def update(self, total=None, processed=None, success=None, fail=None, devices=None, hero_found=None, \nhero_not_found=None):'
    )
    # in case \nhero is not split like that, fallback:
    if 'def update(self, total=None, processed=None' in text and 'def record_login_time' not in text:
        text = text.replace(
            'def update(self, total=None, processed=None',
            'def record_login_time(self, duration_sec):\n        self.load_shared()\n        with self.lock:\n            self.total_login_time += duration_sec\n            self.login_time_count += 1\n            self.save_shared()\n\n    def update(self, total=None, processed=None'
        )

# 3. ModernBotGUI additions
if 'self.lbl_start_time = ctk.CTkLabel' not in text:
    text = text.replace(
        'self.lbl_auto_start.pack(side="left", padx=5)',
        'self.lbl_auto_start.pack(side="left", padx=5)\n            from datetime import datetime\n            start_time_str = datetime.now().strftime("%H:%M:%S")\n            self.lbl_start_time = ctk.CTkLabel(toolbar, text=f"Started: {start_time_str}", font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa")\n            self.lbl_start_time.pack(side="right", padx=10)\n            self.lbl_avg_time = ctk.CTkLabel(toolbar, text="Avg Time: -", font=ctk.CTkFont(size=12, weight="bold"), text_color="#2196f3")\n            self.lbl_avg_time.pack(side="right", padx=10)'
    )

if 'self.lbl_avg_time.configure(' not in text:
    text = text.replace(
        'stat.load_shared()\n            \n            # --- Device Lists ---',
        'stat.load_shared()\n            if stat.login_time_count > 0:\n                avg = stat.total_login_time / stat.login_time_count\n                self.lbl_avg_time.configure(text=f"Avg Time: {avg:.1f}s")\n            \n            # --- Device Lists ---'
    )

# 4. RangerGearBot Last Activity Resetters
if 'self.last_activity_time = time.time()' not in text:
    text = text.replace(
        'self.first_loop_done = not config.get("first_loop", True)',
        'self.first_loop_done = not config.get("first_loop", True)\n        self.last_activity_time = time.time()'
    )

# Adding to action functions:
text = text.replace('def click(self, PSMRL, similarity=0.8):\n', 'def click(self, PSMRL, similarity=0.8):\n        self.last_activity_time = time.time()\n')
text = text.replace('def tap(self, x, y):\n', 'def tap(self, x, y):\n        self.last_activity_time = time.time()\n')
text = text.replace('def type_text(self, text):\n', 'def type_text(self, text):\n        self.last_activity_time = time.time()\n')
text = text.replace('def swipe(self, x1, y1, x2, y2, duration=300):\n', 'def swipe(self, x1, y1, x2, y2, duration=300):\n        self.last_activity_time = time.time()\n')
text = text.replace('def open_app(self):\n', 'def open_app(self):\n        self.last_activity_time = time.time()\n')

# 5. Capture timeout check
if "RestartTimeoutError" not in text.split("def capture_screen")[1][:100]:
    text = text.replace(
        'def capture_screen(self):\n        """Capture screen and load into RAM"""\n        try:',
        'def capture_screen(self):\n        """Capture screen and load into RAM"""\n        if getattr(self, "last_activity_time", 0) and (time.time() - self.last_activity_time) > 500:\n            print(f"[{self.device_id}] TIMEOUT: Inactive for 500s. Restarting bot sequence.")\n            self.last_activity_time = time.time()\n            raise RestartTimeoutError("500s Timeout")\n        try:'
    )

# 6. Try catch main_login and record login time
if 'except RestartTimeoutError:' not in text:
    text = text.replace(
        'status = self.main_login(injected_file)\n                        \n                        if status == "success":',
        'login_start_time = time.time()\n                        try:\n                            status = self.main_login(injected_file)\n                        except RestartTimeoutError:\n                            status = "timeout"\n                            print(f"[{self.device_id}] Caught 500s Timeout!")\n                            self.clear_and_restart()\n                        \n                        if status == "success":\n                            ui_stats.record_login_time(time.time() - login_start_time)'
    )

# 7. Add fixnetv2 inside floating popups
if 'fixnetv2' not in text:
    text = text.replace(
        'if self.exists_in_cache("img/fixplay.png"):',
        'if self.exists_in_cache("img/fixnetv2.png"):\n            print(f"[{self.device_id}] [POPUP] fixnetv2.png detected, clicking...")\n            self.click("img/fixnetv2.png")\n            sleep(2)\n            self.capture_screen()\n            if self.exists_in_cache("img/fixnetv2ok.png"):\n                self.click("img/fixnetv2ok.png")\n                sleep(1)\n            return\n\n        if self.exists_in_cache("img/fixplay.png"):'
    )

with open('login.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("Applied time tracking and fixnetv2 modifications successfully.")
