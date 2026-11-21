#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""decrypt_lfac.py - ถอด _ENC_LF_AC_KEY จาก SharedPreferences XML
ลอง 3 algo (XXTEA / AES-CBC / AES-ECB) + 3 encoding (b64 / hex / raw)

ใช้:
  python decrypt_lfac.py <xml_path> --key <HEX_16_BYTES>
  python decrypt_lfac.py input-id/foo.xml --key 32aabb...  --algo auto
  python decrypt_lfac.py input-id/foo.xml --key 2dxLua2015 --algo xxtea

Shortcut: ลอง default Cocos key ก่อน (บาง game dev ไม่เปลี่ยน):
  python decrypt_lfac.py foo.xml --try-defaults
"""
import argparse, base64, os, re, sys, xml.etree.ElementTree as ET

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------- key candidates ที่เจอบ่อยใน Cocos games ----------
DEFAULT_KEYS_ASCII = [
    "2dxLua", "cocos2d-lua", "cocosbuilder", "linerangers",
    "LineRangers", "LGRGS", "linegame", "LFACKEY",
    "RangersSecret", "cocos_xxtea_key",
]


def read_enc_lfac(xml_path):
    """return (raw_b64_or_hex_string, encoding_hint)"""
    try:
        tree = ET.parse(xml_path)
        for s in tree.getroot().iter("string"):
            name = s.attrib.get("name", "")
            if name in ("_ENC_LF_AC_KEY", "ENC_LF_AC_KEY", "LF_AC_ENC"):
                return s.text or "", name
    except ET.ParseError:
        txt = open(xml_path, encoding="utf-8", errors="ignore").read()
        m = re.search(r'name="(_?ENC_LF_AC_KEY)">([^<]+)</string>', txt)
        if m:
            return m.group(2), m.group(1)
    return None, None


def decode_candidates(s):
    """ลอง decode ciphertext จาก str เป็น bytes หลายรูปแบบ"""
    out = []
    try: out.append(("b64", base64.b64decode(s + "===")))
    except Exception: pass
    try: out.append(("hex", bytes.fromhex(s)))
    except Exception: pass
    try: out.append(("b64url", base64.urlsafe_b64decode(s + "===")))
    except Exception: pass
    return out


def try_xxtea(cipher, key_bytes):
    try:
        import xxtea
    except ImportError:
        return None, "pip install xxtea"
    # xxtea key ต้อง 16 bytes; pad/trunc
    k = (key_bytes + b"\0" * 16)[:16]
    try:
        out = xxtea.decrypt(cipher, k)
        return out, None
    except Exception as e:
        return None, f"xxtea err: {e}"


def try_aes(cipher, key_bytes, mode="cbc"):
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        return None, "pip install cryptography"
    k = (key_bytes + b"\0" * 32)[:16]  # AES-128
    iv = cipher[:16] if mode == "cbc" and len(cipher) > 16 else b"\0" * 16
    body = cipher[16:] if mode == "cbc" and len(cipher) > 16 else cipher
    try:
        m = modes.CBC(iv) if mode == "cbc" else modes.ECB()
        dec = Cipher(algorithms.AES(k), m).decryptor()
        out = dec.update(body) + dec.finalize()
        # strip PKCS7 pad
        if out and 1 <= out[-1] <= 16:
            out = out[:-out[-1]]
        return out, None
    except Exception as e:
        return None, f"aes-{mode} err: {e}"


def looks_cookie(b):
    """ดูว่าผลลัพธ์เหมือน guestCookie (base64/hex ASCII ยาว 32-128)"""
    if not b or len(b) < 16:
        return False
    try:
        s = b.decode("utf-8", errors="strict")
    except Exception:
        return False
    if not all(32 <= ord(c) < 127 for c in s):
        return False
    if re.fullmatch(r"[A-Za-z0-9+/=_-]{16,256}", s):
        return True
    return False


def attempt(cipher_bytes, key_bytes, label=""):
    hits = []
    for algo_name, fn in [("xxtea", try_xxtea),
                           ("aes-cbc", lambda c, k: try_aes(c, k, "cbc")),
                           ("aes-ecb", lambda c, k: try_aes(c, k, "ecb"))]:
        out, err = fn(cipher_bytes, key_bytes)
        if out and looks_cookie(out):
            hits.append((algo_name, out.decode("utf-8", "ignore")))
            print(f"  [HIT] {label} + {algo_name}: {out.decode('utf-8', 'ignore')[:80]}")
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xml")
    ap.add_argument("--key", help="key hex (เช่น 32aabb..) หรือ ascii (ใส่ --ascii)")
    ap.add_argument("--ascii", action="store_true", help="--key เป็น ASCII ตรงๆ")
    ap.add_argument("--algo", default="auto", choices=["auto", "xxtea", "aes-cbc", "aes-ecb"])
    ap.add_argument("--try-defaults", action="store_true", help="ลอง key คอมมอนของ Cocos ก่อน")
    args = ap.parse_args()

    raw, name = read_enc_lfac(args.xml)
    if not raw:
        print(f"ERR: ไม่เจอ _ENC_LF_AC_KEY ใน {args.xml}")
        sys.exit(2)
    print(f"[xml] {name} = {raw[:60]}... (len={len(raw)})")

    cipher_candidates = decode_candidates(raw)
    if not cipher_candidates:
        print("ERR: decode ciphertext ไม่ได้ (ลอง b64/hex ไม่ผ่าน)")
        sys.exit(3)
    for enc, c in cipher_candidates:
        print(f"[cipher {enc}] {c.hex()[:40]}... (len={len(c)})")

    keys = []
    if args.try_defaults:
        for k in DEFAULT_KEYS_ASCII:
            keys.append(("default-" + k, k.encode()))
    if args.key:
        if args.ascii:
            keys.append(("--key ascii", args.key.encode()))
        else:
            try:
                keys.append(("--key hex", bytes.fromhex(args.key)))
            except ValueError:
                keys.append(("--key ascii-fallback", args.key.encode()))

    if not keys:
        print("ไม่มี key - ใส่ --key หรือ --try-defaults")
        sys.exit(1)

    any_hit = False
    for klabel, kb in keys:
        print(f"\n=== try key: {klabel} (len={len(kb)}) ===")
        for enc_name, cbytes in cipher_candidates:
            hits = attempt(cbytes, kb, label=f"cipher={enc_name}")
            if hits:
                any_hit = True

    if not any_hit:
        print("\n[MISS] ไม่มี combo ไหนให้ guestCookie ที่อ่านออก - ลอง Frida dump key จริงก่อน")
        sys.exit(4)


if __name__ == "__main__":
    main()
