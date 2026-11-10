#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# scan_aes_candidates.py
# 1) sweep .so หา string candidate ที่น่าจะเป็น AES key
# 2) ลอง decrypt enc_LF_AC ใน xml ทีละตัว
# 3) พิมพ์ตัวที่ decrypt ผ่าน (padding ถูก + ASCII output)
#
# usage: python scan_aes_candidates.py <dir_with_so> <path_to_xml>

import base64, glob, os, re, sys
from pathlib import Path
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


def extract_enc_blob(xml_path):
    txt = Path(xml_path).read_text(encoding="utf-8", errors="ignore")
    m = re.search(r'name="_ENC_LF_AC_KEY">([^<]+)</string>', txt, re.S)
    if not m: return None
    b = m.group(1)
    # strip ALL whitespace + xml entities
    b = re.sub(r'\s+', '', b)
    b = b.replace('&#10;', '').replace('&#13;', '').replace('&#9;', '')
    # fix base64 padding
    b += '=' * (-len(b) % 4)
    return base64.b64decode(b)


def harvest_candidates(so_path):
    """ดึง string ที่อาจเป็น AES key: printable 16/24/32 bytes + hex 32/48/64 + base64 24/32/44"""
    data = Path(so_path).read_bytes()
    cands = set()

    # printable ASCII 16/24/32 bytes contiguous
    for match in re.finditer(rb'[\x20-\x7e]{16,64}', data):
        s = match.group(0)
        for L in (16, 24, 32):
            if len(s) >= L:
                for i in range(len(s) - L + 1):
                    cands.add(bytes(s[i:i+L]))

    # hex strings
    for m in re.finditer(rb'[0-9a-fA-F]{32,64}', data):
        hx = m.group(0).decode('ascii', 'ignore')
        for L in (32, 48, 64):
            if len(hx) >= L:
                for i in range(len(hx) - L + 1):
                    try:
                        cands.add(bytes.fromhex(hx[i:i+L]))
                    except Exception:
                        pass

    # base64 strings
    for m in re.finditer(rb'[A-Za-z0-9+/]{20,100}={0,2}', data):
        b64 = m.group(0).decode('ascii', 'ignore')
        try:
            raw = base64.b64decode(b64 + '=' * (4 - len(b64) % 4))
            if len(raw) in (16, 24, 32):
                cands.add(raw)
        except Exception:
            pass

    return cands


def try_decrypt(ct, key):
    """ลอง CBC with IV = first 16 of ct, ECB, CBC with zero IV"""
    outs = []
    if len(ct) <= 16: return outs
    iv_first = ct[:16]
    body = ct[16:]
    tries = [
        ("CBC_iv_prefix", AES.new(key, AES.MODE_CBC, iv_first), body),
        ("CBC_iv_zero",   AES.new(key, AES.MODE_CBC, b'\x00'*16), ct),
        ("ECB",           AES.new(key, AES.MODE_ECB), ct),
    ]
    for name, cipher, data in tries:
        if len(data) % 16 != 0: continue
        try:
            pt = unpad(cipher.decrypt(data), AES.block_size)
        except Exception:
            continue
        # ต้องเป็น ASCII printable + ไม่มี null byte
        if all(32 <= c <= 126 for c in pt) and len(pt) >= 8:
            outs.append((name, pt.decode('ascii', 'ignore')))
    return outs


def main():
    if len(sys.argv) < 3:
        print("usage: scan_aes_candidates.py <so_dir> <xml_path>")
        sys.exit(1)

    so_dir, xml_path = sys.argv[1], sys.argv[2]
    enc = extract_enc_blob(xml_path)
    if not enc:
        print(f"ไม่เจอ _ENC_LF_AC_KEY ใน {xml_path}")
        sys.exit(1)

    print(f"enc_LF_AC length = {len(enc)} bytes")
    print(f"first 16 bytes (as IV) = {enc[:16].hex()}")
    print()

    so_files = sorted(glob.glob(os.path.join(so_dir, "*.so")))
    if not so_files:
        print(f"ไม่เจอ .so ใน {so_dir}")
        sys.exit(1)

    hits = []
    for so in so_files:
        print(f"[SCAN] {os.path.basename(so)} ({os.path.getsize(so)} bytes)...", end=" ", flush=True)
        cands = harvest_candidates(so)
        print(f"{len(cands)} candidates")
        for i, k in enumerate(cands):
            outs = try_decrypt(enc, k)
            if outs:
                for mode, pt in outs:
                    print(f"  *** HIT *** so={os.path.basename(so)} key={k.hex()} mode={mode}")
                    print(f"      plaintext: {pt[:200]}")
                    hits.append({"so": os.path.basename(so), "key": k.hex(), "mode": mode, "plain": pt})

    print()
    print(f"=== total hits: {len(hits)} ===")
    if hits:
        print("\nkey ที่ใช้ได้ (copy ไปใส่ env LGR_AES_KEY):")
        for h in hits[:5]:
            print(f"  setx LGR_AES_KEY {h['key']}")
    else:
        print("ไม่เจอ key — อาจ derived runtime, ต้อง Ghidra/IDA ขุด")


if __name__ == "__main__":
    main()
