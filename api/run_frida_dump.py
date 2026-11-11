#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# api/run_frida_dump.py
# รัน scan v3 + รับ raw bytes ผ่าน send(payload, data) → save เป็น .bin + decode

import sys, os, time
import frida

PKG  = "com.linecorp.LGRGS"
HOST = "127.0.0.1:27043"
DUMPDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dumps")

os.makedirs(DUMPDIR, exist_ok=True)

def hex_ascii(b, n=120):
    s = ''
    for c in b[:n]:
        s += chr(c) if 32 <= c < 127 else '.'
    return s

def on_message(msg, data):
    t = msg.get("type")
    if t == "send":
        pl = msg.get("payload")
        if isinstance(pl, dict) and data is not None:
            tag = pl.get("tag", "dump")
            addr = pl.get("addr", "?")
            fn = os.path.join(DUMPDIR, f"{tag}_{addr}.bin")
            with open(fn, "wb") as f:
                f.write(data)
            print(f"[DUMP] {tag} @{addr}  {len(data)}B → {fn}")
            print(f"       ascii: {hex_ascii(data)}")
        else:
            print(f"[FRIDA] {pl}")
    elif t == "error":
        print(f"[ERROR] {msg.get('description')}")
        print(msg.get("stack", ""))

def main():
    script_path = sys.argv[1] if len(sys.argv) > 1 else "api/frida_scan_mem.js"
    src = open(script_path, "r", encoding="utf-8").read()

    print(f"[*] connecting to {HOST}")
    device = frida.get_device_manager().add_remote_device(HOST)
    print(f"[*] attaching to {PKG}")
    session = device.attach(PKG)
    print(f"[*] loading {script_path}")
    script = session.create_script(src)
    script.on("message", on_message)
    script.load()

    print(f"[*] dumps → {DUMPDIR}")
    print("=" * 60)
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        try: script.unload()
        except: pass

if __name__ == "__main__":
    main()
