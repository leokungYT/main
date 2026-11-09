#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_xml_pool.py - scan โฟลเดอร์ xml -> decrypt -> login API -> รายงานสถานะ

ใช้:
  # ตั้ง key ที่ Frida dump ได้ (env var หรือ --key)
  set LFAC_KEY=aabbccdd11223344...
  python api/check_xml_pool.py input-id/

  # หรือใส่ key ตอนเรียก
  python api/check_xml_pool.py input-id/ --key aabb... --algo aes-cbc

  # เช็คเดี่ยว
  python api/check_xml_pool.py input-id/foo.xml --key aabb...

Output:
  xml_name                                      status   ruby   ticket  note
  Lelouch+-norandom608e58b0_LINE_COCOS_...xml   OK        34        0  -
  Lelouch+-norandom108c5c8a_LINE_COCOS_...xml   BAN     -     -      401 blocked
  ...
"""
import argparse, base64, glob, json, os, re, sys, time
import xml.etree.ElementTree as ET

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# bootstrap import lgr_api + decrypt_lfac
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

try:
    from decrypt_lfac import read_enc_lfac, decode_candidates, try_xxtea, try_aes
except ImportError:
    print("ERR: decrypt_lfac.py ไม่เจอ (ต้องอยู่คู่กันที่ api/)")
    sys.exit(1)

try:
    from lgr_api import LGRClient
except ImportError:
    print("ERR: lgr_api.py ไม่เจอ")
    sys.exit(1)


def read_pref(xml_path):
    """ดึง field ที่ต้องใช้จาก xml: udid, _ENC_LF_AC_KEY, _LF_UT_KEY, nation"""
    out = {}
    try:
        tree = ET.parse(xml_path)
        for s in tree.getroot():
            name = s.attrib.get("name", "")
            if s.text is None:
                continue
            if name == "_DEVICE_UUID_KEY":
                out["udid"] = s.text.strip()
            elif name in ("_ENC_LF_AC_KEY", "ENC_LF_AC_KEY"):
                out["enc_lfac"] = s.text.strip()
            elif name == "_LF_UT_KEY":
                out["user_type"] = s.text.strip()
            elif name == "USER_NATION_CODE":
                out["nation"] = s.text.strip()
    except ET.ParseError:
        txt = open(xml_path, encoding="utf-8", errors="ignore").read()
        m = re.search(r'name="_DEVICE_UUID_KEY">([^<]+)</string>', txt)
        if m: out["udid"] = m.group(1).strip()
        m = re.search(r'name="_?ENC_LF_AC_KEY">([^<]+)</string>', txt)
        if m: out["enc_lfac"] = m.group(1).strip()
    return out


def decrypt_cookie(enc_b64, key_bytes, algo="aes-cbc"):
    """ถอด enc -> guestCookie string. คืน None ถ้าถอดไม่ได้"""
    for enc_name, cipher in decode_candidates(enc_b64):
        if algo == "xxtea":
            out, _ = try_xxtea(cipher, key_bytes)
        elif algo == "aes-cbc":
            out, _ = try_aes(cipher, key_bytes, "cbc")
        elif algo == "aes-ecb":
            out, _ = try_aes(cipher, key_bytes, "ecb")
        else:
            # auto: ลองทุกอัน
            for fn in (lambda c, k: try_aes(c, k, "cbc"),
                        lambda c, k: try_aes(c, k, "ecb"),
                        try_xxtea):
                out, _ = fn(cipher, key_bytes)
                if out and _looks_cookie(out):
                    return out.decode("utf-8", "ignore")
            continue
        if out and _looks_cookie(out):
            return out.decode("utf-8", "ignore")
    return None


def _looks_cookie(b):
    if not b or len(b) < 8:
        return False
    try:
        s = b.decode("utf-8", "strict")
    except Exception:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9+/=_\-\.]{8,256}", s.strip()))


def check_one(xml_path, key_bytes, algo="aes-cbc", app_ver="12.3.1"):
    """เช็ค 1 account. คืน dict {status, ruby, ticket, note}"""
    pref = read_pref(xml_path)
    if "udid" not in pref:
        return {"status": "SKIP", "note": "no udid"}
    if "enc_lfac" not in pref:
        return {"status": "SKIP", "note": "no _ENC_LF_AC_KEY"}
    cookie = decrypt_cookie(pref["enc_lfac"], key_bytes, algo=algo)
    if not cookie:
        return {"status": "DEC_FAIL", "note": "ถอดไม่ได้"}
    try:
        c = LGRClient(udid=pref["udid"], lf_ac="",
                      nation=pref.get("nation", "TH"),
                      app_version=app_ver)
        code, data = c.login(guest_cookie=cookie)
    except Exception as e:
        return {"status": "NET", "note": f"{type(e).__name__}: {e}"}

    if code == 200 and isinstance(data, dict):
        player = ((data.get("result") or {}).get("player") or {}) if isinstance(data.get("result"), dict) else {}
        ruby = player.get("ruby", "?")
        ticket = player.get("ticket", player.get("gachaTicket", "?"))
        return {"status": "OK", "ruby": ruby, "ticket": ticket,
                "udid8": pref["udid"][:8], "note": "-"}
    if code == 401:
        return {"status": "BAN", "note": "401 - account banned or cookie expired"}
    if code == 403:
        return {"status": "IP_BAN", "note": "403 - IP blocked"}
    return {"status": f"HTTP{code}", "note": str(data)[:60]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="โฟลเดอร์ หรือ xml เดี่ยว")
    ap.add_argument("--key", default=os.environ.get("LFAC_KEY", ""),
                    help="AES key (hex) ที่ Frida dump ได้")
    ap.add_argument("--ascii", action="store_true", help="--key เป็น ASCII")
    ap.add_argument("--algo", default="auto", choices=["auto", "xxtea", "aes-cbc", "aes-ecb"])
    ap.add_argument("--limit", type=int, default=0, help="จำกัดจำนวน xml (0 = ทั้งหมด)")
    ap.add_argument("--sleep", type=float, default=0.3, help="ดีเลย์ระหว่าง API call (s)")
    ap.add_argument("--json", action="store_true", help="output JSON")
    args = ap.parse_args()

    if not args.key:
        print("ERR: ต้องมี --key หรือ env LFAC_KEY (Frida dump)")
        sys.exit(2)
    try:
        key = args.key.encode() if args.ascii else bytes.fromhex(args.key)
    except ValueError:
        key = args.key.encode()
        print(f"[WARN] key เป็น hex ไม่ได้ -> ใช้เป็น ASCII ({len(key)} bytes)")

    if os.path.isdir(args.target):
        xmls = sorted(glob.glob(os.path.join(args.target, "*.xml")))
    else:
        xmls = [args.target]
    if args.limit:
        xmls = xmls[:args.limit]
    if not xmls:
        print(f"ไม่เจอ xml ที่ {args.target}")
        sys.exit(1)

    print(f"[CFG] key_len={len(key)} algo={args.algo} files={len(xmls)}")
    print(f"{'xml':<60} {'status':<10} {'ruby':>8} {'ticket':>7}  note")
    print("-" * 110)

    stats = {}
    rows = []
    for xml in xmls:
        name = os.path.basename(xml)[:58]
        r = check_one(xml, key, algo=args.algo)
        rows.append({"xml": xml, **r})
        tag = r["status"]
        stats[tag] = stats.get(tag, 0) + 1
        ruby = r.get("ruby", "-")
        ticket = r.get("ticket", "-")
        print(f"{name:<60} {tag:<10} {str(ruby):>8} {str(ticket):>7}  {r.get('note', '')}")
        time.sleep(args.sleep)

    print("-" * 110)
    print("== สรุป ==")
    for k in sorted(stats, key=lambda x: -stats[x]):
        print(f"  {k:10s} {stats[k]:4d}")

    if args.json:
        out = os.path.splitext(args.target.rstrip("/\\"))[0] + "_report.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False, default=str)
        print(f"[JSON] {out}")


if __name__ == "__main__":
    main()
