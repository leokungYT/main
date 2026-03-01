import os
import re

main_lg_path = 'C:/Users/jirasak/Desktop/bot-line/mumu-normalnew/mainLG.py'
login_path = 'c:/Users/jirasak/Downloads/main/login.py'

with open(main_lg_path, 'r', encoding='utf-8') as f:
    lg_text = f.read()

# Extract GUI classes from mainLG.py
match = re.search(r'    class MainConfigWindow\(ctk\.CTkToplevel\):.*?    class ModernBotGUI\(ctk\.CTk\):', lg_text, re.DOTALL)
ui_code = lg_text[match.start():match.end() - len('    class ModernBotGUI(ctk.CTk):')]

# Replace string configurations
ui_code = ui_code.replace("'config.json'", "'configmain.json'")
ui_code = ui_code.replace('"config.json"', '"configmain.json"')

# Fix string literal formatting issues from multiline strings (the syntax errors)
ui_code = ui_code.replace('text="📌 ตั้งชื่อ Ranger ที่จะบันทึก\n📂 รูปอยู่ที่: img/ranger/gachaheroX.png\n💡 เปลี่ยนรูปได้ง่าย แค่วางไฟล์ใหม่ทับ"', 
                          'text="📌 ตั้งชื่อ Ranger ที่จะบันทึก\\n📂 รูปอยู่ที่: img/ranger/gachaheroX.png\\n💡 เปลี่ยนรูปได้ง่าย แค่วางไฟล์ใหม่ทับ"')
ui_code = ui_code.replace('text="📌 ตั้งชื่อ Gear ที่จะบันทึก\nเมื่อบอทพบรูป gearimgX.png จะตั้งชื่อไฟล์ตามที่กำหนด"',
                          'text="📌 ตั้งชื่อ Gear ที่จะบันทึก\\nเมื่อบอทพบรูป gearimgX.png จะตั้งชื่อไฟล์ตามที่กำหนด"')

# Fix save and reload logic
ui_code = ui_code.replace('self.parent.log("✅ Config.json อัพเดทแล้ว")\n                self.destroy()', 
                          'try:\n                    global load_config\n                    load_config()\n                except Exception as ex:\n                    print(ex)\n                self.parent.log("INFO", "✅ Config.json อัพเดทแล้ว")\n                self.destroy()')
ui_code = ui_code.replace('self.parent.log("✅ Ranger & Gear อัพเดทแล้ว")\n                self.destroy()', 
                          'try:\n                    global load_config\n                    load_config()\n                except Exception as ex:\n                    print(ex)\n                self.parent.log("INFO", "✅ Ranger & Gear อัพเดทแล้ว")\n                self.destroy()')

# Apply to login.py
with open(login_path, 'r', encoding='utf-8') as f:
    login_str = f.read()

# Insert the exact GUI
pattern = re.compile(r'    class CollabConfigWindow.*?(?=    class DeviceMonitorWidget)', re.DOTALL)
new_login = pattern.sub(ui_code, login_str, count=1)

# Correct the button commands invoking the GUI
new_login = new_login.replace("def open_config(self): CollabConfigWindow(self)", "def open_config(self): MainConfigWindow(self)")
new_login = new_login.replace("def open_heroes(self): HeroFoldersWindow(self)", "def open_heroes(self): HeroConfigWindow(self)")

# Replace the known ports function entirely to cover all 50+ ports
port_func_old = re.compile(r'def connect_known_ports\(\).*?executor\.submit\(try_connect, port\): port for port in ports\}', re.DOTALL)

port_func_new = """def connect_known_ports():
    \"\"\"Auto-scan and connect to common emulator ports using ThreadPoolExecutor (รองรับ 50 จอ)\"\"\"
    ports = list(range(5555, 5666, 2))  # LDPlayer 
    ports += [7555] # MuMu 
    ports += [16384 + (i * 32) for i in range(40)]  # MuMu 12
    ports += [62001] + [62025 + i for i in range(40)]  # Nox
    ports += [21503 + (i * 10) for i in range(40)] # Memu

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

    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(try_connect, port): port for port in ports}"""
new_login = port_func_old.sub(port_func_new, new_login, count=1)

# Remove the 'login-success' physical move
success_move_old = re.compile(r'    def handle_success\(self, file_path\):.*?self\.device_id\] Move error: \{e\}"\)', re.DOTALL)
success_move_new = """    def handle_success(self, file_path):
        # Do not send to any login-success folder, just remove the backup to avoid reprocessing
        try:
            os.remove(file_path)
        except:
            pass"""
new_login = success_move_old.sub(success_move_new, new_login, count=1)

# Remove the copy of login-success in backup_to_success
backup_move_old = re.compile(r'    def backup_to_success\(self, filename, source_path\):.*?Backup failed: \{result\.stderr\}"\)', re.DOTALL)
backup_move_new = """    def backup_to_success(self, filename, source_path):
        # Disabled moving to login-success folder
        pass"""
new_login = backup_move_old.sub(backup_move_new, new_login, count=1)

with open(login_path, 'w', encoding='utf-8') as f:
    f.write(new_login)

print("Restored GUI, ADB ports, and removed login-success!")
