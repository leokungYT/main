#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# check_pool_live.py — ไล่ยิง /login ทุกบัญชีใน creds.json ตรง ๆ
# ใช้:
#   python check_pool_live.py              # ทั้งไฟล์
#   python check_pool_live.py --limit 20   # แค่ 20 บัญชีแรก
#   python check_pool_live.py --id 408c53a3  # บัญชีเดียว
#   python check_pool_live.py --workers 4  # ขนานได้ (ระวัง rate limit)
#
# output:
#   alive.json  -> {acct_id: {udid, LF_AC(ใหม่), level, ruby, ticket}}
#   dead.json   -> {acct_id: {status, errCode, errMsg}}
#   live LF_AC ใหม่เขียนกลับ creds.json ทันที (update_creds)

import argparse, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from lgr_api import LGRClient, load_creds, update_creds


def check_one(aid: str, acct: dict):
    if not (acct.get("udid") and acct.get("LF_AC") and acct.get("guestCookie")):
        return aid, {"ok": False, "step": "creds-missing"}
    cli = LGRClient(acct["udid"], acct["LF_AC"])
    try:
        st, resp = cli.login(acct["guestCookie"])
    except Exception as e:
        return aid, {"ok": False, "step": "login-exc", "err": str(e)}

    if st != 200 or not isinstance(resp, dict) or "result" not in resp:
        rc = resp.get("errorCode") if isinstance(resp, dict) else st
        msg = resp.get("errorMessage") if isinstance(resp, dict) else None
        return aid, {"ok": False, "status": st, "errCode": rc, "errMsg": msg}

    r = resp.get("result", {}) or {}
    p = r.get("player", {}) or {}
    row = {
        "ok": True,
        "udid": acct["udid"],
        "LF_AC_new": cli.lf_ac,
        "level": p.get("level") or r.get("level"),
        "ruby": r.get("ruby") or p.get("ruby"),
        "name": p.get("userName"),
    }
    if cli.guest_cookie_next:
        row["guestCookie_new"] = cli.guest_cookie_next
    return aid, row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--id", help="เช็กบัญชีเดียว")
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()

    creds = load_creds()
    if not creds:
        sys.exit("creds.json ว่าง หรือเปิดไม่ได้")
    items = list(creds.items())
    if args.id:
        if args.id not in creds:
            sys.exit(f"ไม่มี id {args.id} ใน creds.json")
        items = [(args.id, creds[args.id])]
    if args.limit > 0:
        items = items[: args.limit]

    alive, dead = {}, {}
    t0 = time.time()
    if args.workers <= 1:
        results = (check_one(aid, acct) for aid, acct in items)
    else:
        pool = ThreadPoolExecutor(max_workers=args.workers)
        futs = [pool.submit(check_one, aid, acct) for aid, acct in items]
        results = (f.result() for f in as_completed(futs))

    updates = {}
    for i, (aid, row) in enumerate(results, 1):
        if row.get("ok"):
            alive[aid] = row
            upd = {"LF_AC": row["LF_AC_new"]}
            if row.get("guestCookie_new"):
                upd["guestCookie"] = row["guestCookie_new"]
            updates[aid] = upd
            print(f"[+] {aid}  lv={row.get('level')}  ruby={row.get('ruby')}  name={row.get('name')!r}")
        else:
            dead[aid] = row
            print(f"[-] {aid}  st={row.get('status')}  errCode={row.get('errCode')}  step={row.get('step','api')}")
        if i % 25 == 0:
            print(f"    ... {i}/{len(items)} ({len(alive)} alive)", flush=True)

    # เขียน LF_AC ใหม่กลับ creds.json ครั้งเดียวจบ
    if updates:
        n = update_creds(updates)
        print(f"[*] update_creds -> {n} fields written")

    json.dump(alive, open("alive.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(dead,  open("dead.json",  "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    dt = time.time() - t0
    print(f"\n=== tested={len(items)} alive={len(alive)} dead={len(dead)} in {dt:.1f}s ===")
    print("     alive.json / dead.json เขียนแล้ว")


if __name__ == "__main__":
    main()
