with open('login.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(
'''            self.hero_filter_text = ""
            
            self.setup_ui()
            
            # Use after to start the stats loop without blocking the constructor
            self.after(100, self.update_realtime_stats)
            
            # Ensure window is visible
            self.deiconify()
            self.focus_force()
            print("[GUI] Launched Successfully.")
            
            if getattr(self.args, 'no_start', False):
                print("[GUI] Monitor mode active (No internal threads).")
                self.lbl_auto_start.configure(text="[ DASHBOARD MODE ]", text_color="#ffae42")
            else:
                print("[GUI] Auto-starting bot threads...")
                self.start_bot()''',
'''            self.hero_filter_text = ""
            self.is_started = False
            
            self.setup_ui()
            
            # Use after to start the stats loop without blocking the constructor
            self.after(100, self.update_realtime_stats)
            
            # Ensure window is visible
            self.deiconify()
            self.focus_force()
            print("[GUI] Launched Successfully. Waiting for manual start.")
            
            if getattr(self.args, 'no_start', False):
                print("[GUI] Monitor mode active (No internal threads).")
                self.lbl_auto_start.configure(text="[ DASHBOARD MODE ]", text_color="#ffae42")
            else:
                self.lbl_auto_start.configure(text="[ WAITING FOR START ]", text_color="#aaaaaa")'''
)

text = text.replace(
'''            self.lbl_status.pack(side="left", padx=5)
            
            self.lbl_auto_start = ctk.CTkLabel(toolbar, text="[ AUTO-START ACTIVE ]", font=ctk.CTkFont(size=10, weight="bold"), text_color="#aaaaaa")
            self.lbl_auto_start.pack(side="left", padx=10)''',
'''            self.lbl_status.pack(side="left", padx=5)

            self.btn_start = ctk.CTkButton(toolbar, text="▶ START", font=ctk.CTkFont(size=12, weight="bold"), width=80, height=24, fg_color="#e53935", hover_color="#c62828", command=self.start_bot)
            self.btn_start.pack(side="left", padx=10)
            
            self.lbl_auto_start = ctk.CTkLabel(toolbar, text="[ WAITING FOR START ]", font=ctk.CTkFont(size=10, weight="bold"), text_color="#aaaaaa")
            self.lbl_auto_start.pack(side="left", padx=5)'''
)

text = text.replace(
'''        def start_bot(self):
            self.log("INFO", "Auto-starting Bot Threads...")
            for device_id in self.devices:
                bot = RangerGearBot(device_id, self.args)
                bot.start()
                self.bot_threads.append(bot)''',
'''        def start_bot(self):
            if getattr(self, 'is_started', False):
                self.log("WARN", "Bot is already running.")
                return
            self.is_started = True
            if hasattr(self, 'btn_start'):
                self.btn_start.configure(state="disabled", fg_color="#555555", text="⏳ RUNNING")
            self.lbl_auto_start.configure(text="[ BOT IS RUNNING ]", text_color="#4caf50")
            self.log("INFO", "Starting Bot Threads...")
            for device_id in self.devices:
                bot = RangerGearBot(device_id, self.args)
                bot.start()
                self.bot_threads.append(bot)'''
)

text = text.replace(
'''                    if not getattr(self.args, 'no_start', False):
                        bot = RangerGearBot(dev, self.args)
                        bot.start()
                        self.bot_threads.append(bot)''',
'''                    if getattr(self, 'is_started', False) and not getattr(self.args, 'no_start', False):
                        bot = RangerGearBot(dev, self.args)
                        bot.start()
                        self.bot_threads.append(bot)'''
)

with open('login.py', 'w', encoding='utf-8') as f:
    f.write(text)
print("Patched ModernBotGUI start button successfully.")
