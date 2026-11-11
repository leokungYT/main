#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# api/xml_fire.py
# xml -> decrypt enc_guestCookie -> ยิง HTTP ตรง -> พิมพ์ผล
# ไม่ใช้ mumu / mitm ตอนยิง / creds.json
#
# usage:
#   set LGR_AES_KEY=<hex จาก frida_dump_key.js>
#   python api\xml_fire.py --xml C:\path\one.xml --gift
#   python api\xml_fire.py --xml-dir C:\path\login-success --gift --limit 50
#   python api\xml_fire.py --xml one.xml --dump              # req/res ดิบ
#   python api\xml_fire.py --udid <u> --guest <g> --gift     # ข้าม xml ทั้งหมด

import argparse, base64, glob, json, os, re, sys, time
from binascii import unhexlify
from pathlib import Path
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# ============ แก้บล็อกนี้ให้ตรงกับที่ Charles ดักมาจากมือถือ ============
BASE       = "https://rangers-api.line-apps.com"
APP_VER    = "15.3.0"
CLIENT     = "LGRGS"
LANG       = "th"
NATION_DEF = "TH"
UA_ANDROID = "Dalvik/2.1.0 (Linux; U; Android 13; Pixel 6 Build/TQ3A.230805.001)"

HEAD = {
    "Accept":          "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Content-Type":    "application/json; charset=utf-8",
    "X-Lf-App":        CLIENT,
    "X-Lf-Ver":        APP_VER,
    "X-Lf-Lang":       LANG,
    "User-Agent":      UA_ANDROID,
}
# =======================================================================

RSN_RX   = re.compile(r'([0-9a-f]{8})_LINE_COCOS')
FIELD_RX = {
    "udid":      re.compile(r'name="_DEVICE_UUID_KEY">([^<]+)</string>'),
    "nation":    re.compile(r'name="USER_NATION_CODE">([^<]+)</string>'),
    "user_type": re.compile(r'name="_LF_UT_KEY">([^<]+)</string>'),
    "enc_blob":  re.compile(r'name="_ENC_LF_AC_KEY">([^<]+)</string>', re.S),
}


def parse_xml(path):
    txt = Path(path).read_text(encoding="utf-8", errors="ignore")
    out = {}
    for k, rx in FIELD_RX.items():
        m = rx.search(txt); out[k] = m.group(1).strip() if m else None
    m = RSN_RX.search(os.path.basename(path)); out["rsn"] = m.group(1) if m else None
    return out


def decrypt_blob(b64, key):
    raw = base64.b64decode(b64)
    iv, ct = raw[:16], raw[16:]
    return unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ct), AES.block_size).decode("utf-8", "ignore")


def fire(udid, guest_cookie, nation, do_gift, dump):
    s = requests.Session()
    s.headers.update(HEAD)
    s.headers["X-Lf-Nation"] = nation or NATION_DEF
    s.cookies.set("udid", udid, domain="rangers-api.linega.me")

    body = {
        "userType":    "GUEST",
        "guestCookie": guest_cookie,
        "udid":        udid,
        "nation":      nation or NATION_DEF,
        "appVersion":  APP_VER,
        "platform":    "android",
    }
    r1 = s.post(f"{BASE}/login", data=json.dumps(body), timeout=20)
    if dump:
        print("---- /login req ----"); print(json.dumps(body, ensure_ascii=False, indent=2))
        print("---- /login res ----"); print(r1.status_code); print(r1.text[:4096])
    if r1.status_code != 200:
        return {"ok": False, "stage": "login", "status": r1.status_code, "body": r1.text[:400]}

    try:    j1 = r1.json()
    except: j1 = {}
    lf_ac = s.cookies.get("LF_AC") \
            or (j1.get("result") or {}).get("sessionKey") \
            or (j1.get("result") or {}).get("LF_AC")
    if lf_ac:
        s.cookies.set("LF_AC", lf_ac, domain="rangers-api.linega.me")

    r2 = s.get(f"{BASE}/home", timeout=20)
    if dump:
        print("---- /home res ----"); print(r2.status_code); print(r2.text[:4096])
    if r2.status_code != 200:
        return {"ok": False, "stage": "home", "status": r2.status_code, "body": r2.text[:400]}

    try:    j2 = r2.json()
    except: j2 = {}
    res = (j2.get("result") or {}); p = res.get("player") or {}
    out = {
        "ok":    True,
        "rsn":   p.get("rsn") or res.get("rsn"),
        "level": p.get("level") or res.get("level"),
        "name":  p.get("userName"),
        "ruby":  p.get("ruby")  if "ruby"  in p else res.get("ruby"),
        "coin":  p.get("coin")  if "coin"  in p else res.get("coin"),
        "LF_AC": lf_ac,
    }
    if do_gift:
        r3 = s.post(f"{BASE}/gift/collectAll", data=json.dumps({}), timeout=20)
        if dump: print("---- /gift res ----"); print(r3.status_code); print(r3.text[:2048])
        out["gift_status"] = r3.status_code
        try:
            j3 = r3.json()
            out["gift_count"] = len((j3.get("result") or {}).get("received", []) or [])
        except Exception as e:
            out["gift_err"] = str(e)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml")
    ap.add_argument("--xml-dir")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--key",   help="AES hex (ไม่ใส่อ่าน env LGR_AES_KEY)")
    ap.add_argument("--udid",  help="ยิงตรง: udid")
    ap.add_argument("--guest", help="ยิงตรง: guestCookie plain (ข้าม xml)")
    ap.add_argument("--gift",  action="store_true")
    ap.add_argument("--dump",  action="store_true")
    ap.add_argument("--sleep", type=float, default=0.25)
    args = ap.parse_args()

    # เส้นลัด: ยิงตรงไม่ผ่าน xml/key
    if args.udid and args.guest:
        r = fire(args.udid, args.guest, "TH", args.gift, args.dump)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return

    key_hex = args.key or os.environ.get("LGR_AES_KEY")
    if not key_hex or len(key_hex) not in (32, 64):
        sys.exit("ต้องให้ --key หรือ env LGR_AES_KEY (hex 32/64)")
    key = unhexlify(key_hex)

    xmls = [args.xml] if args.xml else sorted(glob.glob(os.path.join(args.xml_dir, "*.xml"))) if args.xml_dir else []
    if args.limit > 0: xmls = xmls[:args.limit]
    if not xmls: sys.exit("ไม่เจอ xml (ใส่ --xml หรือ --xml-dir)")

    ok = dead = miss = 0
    for i, x in enumerate(xmls, 1):
        f = parse_xml(x)
        print(f"[{i}/{len(xmls)}] {os.path.basename(x)}  rsn={f['rsn']}  udid={(f['udid'] or '?')[:12]}")
        if not (f["udid"] and f["enc_blob"]):
            miss += 1; print("  MISS xml ขาดฟิลด์\n"); continue
        try:
            guest = decrypt_blob(f["enc_blob"], key)
        except Exception as e:
            miss += 1; print(f"  MISS decrypt: {e}\n"); continue

        r = fire(f["udid"], guest, f["nation"], args.gift, args.dump)
        if r["ok"]:
            ok += 1
            line = f"  OK   lv={r['level']} ruby={r['ruby']} coin={r['coin']} name={r['name']!r}"
            if args.gift: line += f" gift={r.get('gift_count')}"
            print(line + "\n")
        else:
            dead += 1
            print(f"  DEAD stage={r['stage']} st={r['status']} body={r['body']}\n")
        time.sleep(args.sleep)

    print(f"=== ok={ok} dead={dead} miss={miss} total={len(xmls)} ===")


if __name__ == "__main__":
    main()
