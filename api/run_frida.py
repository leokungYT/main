#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# api/run_frida.py
# control timeout + run frida script แบบ attach ผ่าน remote server
#
# usage:
#   python run_frida.py api/frida_call_lspg.js

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
        print("usage: run_frida.py <script.js>")
        sys.exit(1)

    script_path = sys.argv[1]
    src = open(script_path, "r", encoding="utf-8").read()

    print(f"[*] connecting to {HOST}")
    device = frida.get_device_manager().add_remote_device(HOST)

    print(f"[*] attaching to {PKG}")
    session = device.attach(PKG)

    print(f"[*] loading script {script_path} ({len(src)} chars)")
    script = session.create_script(src)
    script.on("message", on_message)
    script.load()

    print("[*] script loaded - ctrl+c to exit")
    print("=" * 60)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] detaching")
        script.unload()
        session.detach()

if __name__ == "__main__":
    main()
