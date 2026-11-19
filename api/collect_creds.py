#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# api/collect_creds.py
#
# XML (_ENC_LF_AC blob) -> AES decrypt -> login HTTP -> เก็บ creds.json
# ไม่ใช้ MuMu, ไม่ใช้ Frida ตอนรัน
# AES key ต้องรู้ก่อน (env LGR_AES_KEY หรือ --key hex)
#
# usage:
#   set LGR_AES_KEY=<hex>
#   python api\collect_creds.py --xml C:\path\one.xml
#   python api\collect_creds.py --xml-dir C:\path\login-success --limit 50
#   python api\collect_creds.py --xml-dir ... --gift          เก็บ gift ด้วย
#   python api\collect_creds.py --xml-dir ... --force         เขียนทับของเก่า

import argparse
import glob
import json
import os
import sys
import time
from binascii import unhexlify
from pathlib import Path

# reuse ของเดิมใน xml_fire.py (ต้องวาง collect_creds.py ไว้ใน api/ เดียวกัน)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xml_fire import parse_xml, decrypt_blob, fire, NATION_DEF  # type: ignore


CREDS_PATH_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creds.json")


def load_creds(path):
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[!] creds.json corrupt: {e} - starting fresh")
        return {}


def save_creds(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def entry_from_result(r, udid, guest, nation):
    return {
        "udid":        udid,
        "guestCookie": guest,
        "nation":      nation or NATION_DEF,
        "rsn":         r.get("rsn"),
        "name":        r.get("name"),
        "level":       r.get("level"),
        "ruby":        r.get("ruby"),
        "coin":        r.get("coin"),
        "LF_AC":       r.get("LF_AC"),
        "last_login":  int(time.time()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml")
    ap.add_argument("--xml-dir")
    ap.add_argument("--creds", default=CREDS_PATH_DEFAULT,
                    help=f"ไฟล์เก็บผล (default: {CREDS_PATH_DEFAULT})")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--key",   help="AES hex (ไม่ใส่อ่าน env LGR_AES_KEY)")
    ap.add_argument("--gift",  action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="เขียนทับ entry เดิมใน creds.json")
    ap.add_argument("--sleep", type=float, default=0.3)
    ap.add_argument("--dump",  action="store_true")
    args = ap.parse_args()

    key_hex = args.key or os.environ.get("LGR_AES_KEY")
    if not key_hex or len(key_hex) not in (32, 64):
        sys.exit("ต้องให้ --key หรือ env LGR_AES_KEY (hex 32/64)")
    key = unhexlify(key_hex)

    xmls = (
        [args.xml] if args.xml
        else sorted(glob.glob(os.path.join(args.xml_dir, "*.xml"))) if args.xml_dir
        else []
    )
    if args.limit > 0:
        xmls = xmls[:args.limit]
    if not xmls:
        sys.exit("ไม่เจอ xml (ใส่ --xml หรือ --xml-dir)")

    creds = load_creds(args.creds)
    print(f"[*] creds loaded: {len(creds)} entries  -> {args.creds}")

    ok = dup = dead = miss = 0
    for i, x in enumerate(xmls, 1):
        f = parse_xml(x)
        rsn = f.get("rsn") or Path(x).stem
        udid = f.get("udid")
        print(f"[{i}/{len(xmls)}] {os.path.basename(x)}  rsn={rsn}  udid={(udid or '?')[:12]}")

        if not args.force and rsn in creds and creds[rsn].get("guestCookie"):
            dup += 1
            print("  SKIP already in creds (use --force to overwrite)\n")
            continue

        if not (udid and f.get("enc_blob")):
            miss += 1
            print("  MISS xml ขาดฟิลด์\n")
            continue

        try:
            guest = decrypt_blob(f["enc_blob"], key)
        except Exception as e:
            miss += 1
            print(f"  MISS decrypt: {e}\n")
            continue

        r = fire(udid, guest, f.get("nation"), args.gift, args.dump)
        if r.get("ok"):
            ok += 1
            creds[rsn] = entry_from_result(r, udid, guest, f.get("nation"))
            save_creds(args.creds, creds)
            line = f"  OK   lv={r['level']} ruby={r['ruby']} coin={r['coin']} name={r['name']!r}"
            if args.gift:
                line += f" gift={r.get('gift_count')}"
            print(line + "\n")
        else:
            dead += 1
            print(f"  DEAD stage={r['stage']} st={r['status']} body={r['body']}\n")

        time.sleep(args.sleep)

    print(f"=== ok={ok} dup={dup} dead={dead} miss={miss} total={len(xmls)} ===")
    print(f"=== creds now has {len(creds)} entries -> {args.creds} ===")


if __name__ == "__main__":
    main()
