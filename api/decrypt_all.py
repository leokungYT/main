"""
decrypt_all.py — decrypt every xml_* entry in creds.json using the key-from-udid formula
and replace the encrypted LF_AC with the plaintext guestCookie.

Algorithm (recovered from SimpleCrypto.decrypt2 in classes5.dex):
  key = base64_decode(udid)                       # 32-char hex udid -> 24 bytes = AES-192
  ct  = base64_decode(_ENC_LF_AC_KEY)
  iv  = ct[:16]
  body = ct[16:]
  pt  = AES-192-CBC.decrypt(body, key, iv)  -> PKCS5 unpad  -> utf-8 string (guestCookie)
"""
import argparse
import base64
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

from Crypto.Cipher import AES


def decrypt_entry(udid: str, enc_b64: str) -> str:
    key = base64.b64decode(udid + "==")
    ct = base64.b64decode(enc_b64 + "===")
    iv = ct[:16]
    body = ct[16:]
    pt = AES.new(key, AES.MODE_CBC, iv).decrypt(body)
    pad = pt[-1]
    if 1 <= pad <= 16 and pt[-pad:] == bytes([pad]) * pad:
        pt = pt[:-pad]
    return pt.decode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="api/creds.json")
    ap.add_argument("--out", default="api/creds.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.src, "r", encoding="utf-8") as f:
        data = json.load(f)

    ok = fail = skipped = 0
    for key, entry in list(data.items()):
        if "LF_AC" not in entry or "udid" not in entry:
            skipped += 1; continue
        # already decrypted entries don't have 'source=xml_import'
        if entry.get("source") != "xml_import":
            skipped += 1; continue
        try:
            guest = decrypt_entry(entry["udid"], entry["LF_AC"])
        except Exception as e:
            print(f"  [fail] {key}: {e}")
            fail += 1; continue
        entry["guestCookie"] = guest
        entry["LF_AC"] = ""           # session cookie unknown yet — will be filled on first login
        entry["decrypted"] = True
        ok += 1
        if ok <= 3:
            print(f"  [ok] {key}  udid={entry['udid'][:12]}...  guestCookie[:60]={guest[:60]}...")

    print(f"[done]  decrypted={ok}  failed={fail}  skipped={skipped}")

    if not args.dry_run and ok > 0:
        tmp = args.out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, args.out)
        print(f"[saved] {args.out}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
