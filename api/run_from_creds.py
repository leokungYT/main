#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# api/run_from_creds.py
#
# อ่าน creds.json -> login HTTP ด้วย guestCookie เดิม -> refresh ค่า
# ไม่ต้องรู้ AES key ไม่ต้องใช้ XML ไม่ต้องเปิด MuMu
#
# usage:
#   python api\run_from_creds.py                 รันทั้งหมด, แค่ refresh
#   python api\run_from_creds.py --gift          เก็บ gift ทุก account
#   python api\run_from_creds.py --rsn a0aaa995  เฉพาะ rsn ที่ระบุ
#   python api\run_from_creds.py --limit 10      เฉพาะ 10 entry แรก
#   python api\run_from_creds.py --dry           ไม่ยิง server แค่โชว์ plan
#   python api\run_from_creds.py --stale 3600    ข้าม entry ที่ refresh ใน 1 ชม.

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xml_fire import fire, NATION_DEF  # type: ignore


CREDS_PATH_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creds.json")


def load_creds(path):
    if not os.path.isfile(path):
        sys.exit(f"[!] ไม่เจอ {path} - รัน collect_creds.py ก่อน")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_creds(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--creds", default=CREDS_PATH_DEFAULT)
    ap.add_argument("--rsn",   help="ยิงเฉพาะ rsn นี้")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--gift",  action="store_true")
    ap.add_argument("--dump",  action="store_true")
    ap.add_argument("--dry",   action="store_true")
    ap.add_argument("--stale", type=int, default=0,
                    help="ข้าม entry ที่มี last_login ใหม่กว่า N วินาที")
    ap.add_argument("--sleep", type=float, default=0.3)
    args = ap.parse_args()

    creds = load_creds(args.creds)
    now = int(time.time())

    # เลือก entries
    items = list(creds.items())
    if args.rsn:
        items = [(k, v) for k, v in items if k == args.rsn]
        if not items:
            sys.exit(f"[!] ไม่เจอ rsn={args.rsn} ใน {args.creds}")
    if args.stale > 0:
        items = [(k, v) for k, v in items
                 if now - int(v.get("last_login") or 0) >= args.stale]
    if args.limit > 0:
        items = items[:args.limit]
    if not items:
        sys.exit("[!] ไม่มี entry ให้ยิง (อาจโดน filter ตัดทิ้งหมด)")

    print(f"[*] creds entries total : {len(creds)}")
    print(f"[*] will fire           : {len(items)}")
    if args.dry:
        for rsn, c in items:
            age = now - int(c.get("last_login") or 0)
            print(f"  DRY  rsn={rsn}  udid={c['udid'][:12]}  "
                  f"lv={c.get('level')}  age={age}s")
        return

    ok = dead = 0
    for i, (rsn, c) in enumerate(items, 1):
        print(f"[{i}/{len(items)}] rsn={rsn}  udid={c['udid'][:12]}")
        guest = c.get("guestCookie")
        if not guest:
            dead += 1
            print("  DEAD no guestCookie in creds (ต้องรัน collect_creds ใหม่)\n")
            continue

        r = fire(c["udid"], guest, c.get("nation") or NATION_DEF,
                 args.gift, args.dump)
        if r.get("ok"):
            ok += 1
            c["level"]      = r.get("level",  c.get("level"))
            c["ruby"]       = r.get("ruby",   c.get("ruby"))
            c["coin"]       = r.get("coin",   c.get("coin"))
            c["name"]       = r.get("name",   c.get("name"))
            c["LF_AC"]      = r.get("LF_AC",  c.get("LF_AC"))
            c["last_login"] = now
            if args.gift:
                c["last_gift_count"]  = r.get("gift_count")
                c["last_gift_status"] = r.get("gift_status")
            creds[rsn] = c
            save_creds(args.creds, creds)
            line = f"  OK   lv={c['level']} ruby={c['ruby']} coin={c['coin']} name={c.get('name')!r}"
            if args.gift:
                line += f" gift={c.get('last_gift_count')}"
            print(line + "\n")
        else:
            dead += 1
            print(f"  DEAD stage={r['stage']} st={r['status']} body={r['body']}\n")

        time.sleep(args.sleep)

    print(f"=== ok={ok} dead={dead} total={len(items)} ===")


if __name__ == "__main__":
    main()
