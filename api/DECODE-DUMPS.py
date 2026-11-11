#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# api/DECODE-DUMPS.py
# ไล่ไฟล์ใน api/dumps/ → หา HTTP header + msgpack body → decode
# print udid / guestCookie / session / LF_AC ที่เจอ

import os, re, sys, json
from pathlib import Path

try:
    import msgpack
except ImportError:
    print("pip install msgpack")
    sys.exit(1)

DUMPDIR = Path(os.path.dirname(os.path.abspath(__file__))) / "dumps"

def extract_http_and_body(blob):
    """find HTTP header block + content-length + body"""
    # find Content-Length
    m = re.search(rb'Content-Length:\s*(\d+)\r\n', blob, re.I)
    if not m:
        return None
    clen = int(m.group(1))
    # find end of headers
    end = blob.find(b'\r\n\r\n', m.start())
    if end < 0:
        return None
    header = blob[:end].decode('latin1', errors='ignore')
    body = blob[end+4 : end+4+clen]
    return header, body

def try_msgpack(body):
    try:
        return msgpack.unpackb(body, raw=False, strict_map_key=False)
    except Exception as e:
        return None

def try_json(body):
    try:
        return json.loads(body.decode('utf-8', errors='ignore'))
    except Exception:
        return None

def show_interesting(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            sk = str(k).lower()
            if any(x in sk for x in ['udid', 'guest', 'cookie', 'token', 'session', 'auth', 'key', 'secret', 'lf_ac']):
                print(f"   {prefix}{k} = {v!r}")
            show_interesting(v, prefix + f"{k}.")
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            show_interesting(x, prefix + f"[{i}].")

def hex_ascii(b, n=160):
    return ''.join(chr(c) if 32 <= c < 127 else '.' for c in b[:n])

def main():
    if not DUMPDIR.exists():
        print(f"ไม่มี {DUMPDIR} — รัน CALL-SCANDUMP.bat ก่อน")
        return

    files = sorted(DUMPDIR.glob("*.bin"))
    print(f"ไฟล์ทั้งหมด: {len(files)}\n")

    for f in files:
        data = f.read_bytes()
        # 1) look for HTTP structure
        pair = extract_http_and_body(data)
        if pair:
            hdr, body = pair
            print(f"═══ {f.name} ═══")
            print("─── header ───")
            print(hdr[:800])
            print(f"─── body ({len(body)}B) ───")
            print("ascii: " + hex_ascii(body, 200))
            obj = try_msgpack(body) or try_json(body)
            if obj:
                print("decoded:")
                print(json.dumps(obj, ensure_ascii=False, indent=2, default=str)[:2000])
                print("— interesting fields —")
                show_interesting(obj)
            print()
            continue

        # 2) look for interesting ASCII
        ascii_txt = hex_ascii(data, 400)
        if any(x in ascii_txt for x in ['udid=', 'LF_AC', 'guestCookie', 'POST /', 'sessionKey', 'x-lf', 'X-Lf']):
            print(f"═══ {f.name} (text) ═══")
            print(ascii_txt)
            print()

if __name__ == "__main__":
    main()
