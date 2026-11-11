#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# api/run_frida_spawn.py
# SPAWN mode — ฆ่าเกมแล้ว start ใหม่ ติด hook ก่อน resume
# จับทุกอย่างตั้งแต่ JNI_OnLoad / token decrypt ตอน boot
#
# usage:
#   python run_frida_spawn.py api/frida_call_lspg.js

import sys, time
import frida

PKG  = "com.linecorp.LGRGS"
HOST = "127.0.0.1:27043"

def on_message(msg, data):
    if msg.get("type") == "send":
        print("[FRIDA]", msg.get("payload"))
    elif msg.get("type") == "error":
        print("[ERROR]", msg.get("description"))
        print(msg.get("stack", ""))

def main():
    if len(sys.argv) < 2:
        print("usage: run_frida_spawn.py <script.js>")
        sys.exit(1)

    script_path = sys.argv[1]
    src = open(script_path, "r", encoding="utf-8").read()

    print(f"[*] connecting to {HOST}")
    device = frida.get_device_manager().add_remote_device(HOST)

    # kill existing instance ก่อน spawn ใหม่
    print(f"[*] killing existing {PKG} ...")
    try:
        for p in device.enumerate_processes():
            if p.name == PKG:
                print(f"    kill pid={p.pid}")
                device.kill(p.pid)
        time.sleep(1)
    except Exception as e:
        print(f"[!] kill err: {e}")

    print(f"[*] SPAWN {PKG}")
    pid = device.spawn([PKG])
    print(f"[+] spawned pid={pid}")

    print(f"[*] attaching to pid={pid}")
    session = device.attach(pid)

    print(f"[*] loading script {script_path} ({len(src)} chars)")
    script = session.create_script(src)
    script.on("message", on_message)
    script.load()

    print(f"[*] RESUME pid={pid}")
    device.resume(pid)

    print("[*] script loaded - ctrl+c to exit")
    print("=" * 60)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] detaching")
        try: script.unload()
        except: pass
        try: session.detach()
        except: pass

if __name__ == "__main__":
    main()
