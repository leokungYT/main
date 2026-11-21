"""ทดสอบ Auto-Cap กับจอเดียว (ไม่ต้องรันบอททั้งตัว)

วิธีใช้: เปิดเกมค้างไว้ที่หน้า Lobby (เจอ stoplogin แล้ว) จากนั้น
    python test_auto_cap.py 127.0.0.1:16384
"""
import os
import sys
import types
import importlib.util

ROOT = os.path.dirname(os.path.abspath(__file__))
DEV = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:16384"
os.chdir(ROOT)
sys.argv = [os.path.join(ROOT, "login.py")]

spec = importlib.util.spec_from_file_location("botmod", os.path.join(ROOT, "login.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.load_config()
m.find_adb_executable()

bot = m.RangerGearBot(DEV, types.SimpleNamespace(device=DEV, no_start=True, no_reset_adb=True, cli=True, minimized=False))
bot._running = False
found = bot.process_auto_cap()
print("\nผล Auto-Cap:", found or "ไม่เจออะไรเลย")
os._exit(0)
