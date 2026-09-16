#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
seven_days.py — รับรางวัล "ภารกิจ" (daily / weekly / special) ทุกบัญชีใน creds.json
ยิง API ตรง ไม่ต้องเปิดเกม (โครงเดียวกับ collect_all.py)

ใช้:  python seven_days.py              # ทุกบัญชี
      python seven_days.py 10a86152     # เฉพาะบัญชีเดียว
      python seven_days.py --list       # ดูอย่างเดียว ไม่รับ (ปลอดภัยสุด ใช้เช็คก่อน)
      python seven_days.py --dump 10a86152   # พ่น JSON ดิบของ /mission/list/new/

endpoint (ยืนยันสดกับเซิร์ฟจริง 2026-09-16):
  GET  /mission/list/new/              -> dailyMissionTab / weeklyMissionTab / specialMissionTab
  POST /mission/receive/reward/<missionNo>   -> รับรางวัล 1 ชิ้น (พิสูจน์แล้ว: 3688 -> 200)
  (`/mission/sevendays/list` มีจริงแต่คืน errorCode 120900 กับบัญชีทั่วไป = อีเวนต์เฉพาะช่วง
   เลยไม่ได้ใช้เป็นทางหลัก)
  ข้อจำกัด: daily/weekly รายชิ้นไม่มี missionNo -> รับทีละอันไม่ได้ สคริปต์จึงรับเฉพาะ
  ภารกิจที่มี missionNo (specialMissionTab เป็นหลัก)
"""
import json
import os
import random
import sys
import time
import concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lgr_api import (
    LGRClient,
    parse_missions,
    load_creds as _api_load_creds,
    save_creds as _api_save_creds,
    CREDS_FILE,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# เนียนเหมือน collect_all: ขนานน้อย + หน่วงสุ่มก่อนเริ่มแต่ละบัญชี
WORKERS = int(os.environ.get("LGR_WORKERS", "4"))
JITTER_MIN = float(os.environ.get("LGR_JITTER_MIN", "1.5"))
JITTER_MAX = float(os.environ.get("LGR_JITTER_MAX", "5.0"))


def _client_for(cred):
    """สร้าง client + ทำให้ session ใช้ได้จริง (ถ้า /home ไม่ผ่านและมี guestCookie ให้ล็อกอินใหม่)"""
    c = LGRClient(cred["udid"], cred["LF_AC"])
    st, home = c.home()
    if st != 200 and cred.get("guestCookie"):
        st_l, _ = c.login(cred["guestCookie"])
        if st_l == 200:
            st, home = c.home()
    return c, st, home


def _one(key, cred, claim=True):
    udid, lf = cred.get("udid"), cred.get("LF_AC")
    fname = cred.get("file", "-")
    if not (udid and lf):
        return key, {"ok": False, "file": fname, "err": "no udid/LF_AC"}
    try:
        time.sleep(random.uniform(JITTER_MIN, JITTER_MAX))
        c, st, home = _client_for(cred)
        if st != 200:
            detail = home.get("message") if isinstance(home, dict) else str(home)[:120]
            return key, {"ok": False, "file": fname, "step": "home", "status": st, "detail": detail}

        st_l, pending = c.mission_pending()
        if st_l != 200:
            return key, {"ok": False, "file": fname, "step": "mission/list", "status": st_l,
                         "lf_ac_next": c.lf_ac}

        if not claim:
            return key, {"ok": True, "file": fname, "pending": len(pending), "claimed": 0,
                         "missions": [f"{m['title']}#{m['seq']}" for m in pending],
                         "lf_ac_next": c.lf_ac}

        r = c.mission_receive_all(pending)
        r.update({"file": fname, "lf_ac_next": c.lf_ac, "gc_next": c.guest_cookie_next})
        r["missions"] = [f"{m['title']}#{m['seq']}" for m in r.get("missions", [])]
        return key, r
    except Exception as e:
        return key, {"ok": False, "file": fname, "err": str(e)}


def dump_one(key, creds):
    """พ่น JSON ดิบของ list ออกมา ใช้ตอนต้องการดูสคีมาจริงเพื่อปรับ parser"""
    cred = creds.get(key)
    if not cred:
        print(f"[X] ไม่พบ id '{key}'")
        return
    c, st, _ = _client_for(cred)
    if st != 200:
        print(f"[X] เข้าเกมไม่ได้ (home status={st})")
        return
    st_l, d = c.mission_list()
    print(f"GET /mission/list/new/ -> {st_l}")
    print(json.dumps(d, ensure_ascii=False, indent=2)[:20000])
    if st_l == 200 and isinstance(d, dict):
        pend = parse_missions(d.get("result", {}) or {})
        print(f"\n[parser เห็นว่ารับได้ {len(pend)} ชิ้น] " +
              ", ".join(str(m['title'] or m['seq']) for m in pend))


def main():
    args = [a for a in sys.argv[1:]]
    claim = "--list" not in args
    do_dump = "--dump" in args
    args = [a for a in args if not a.startswith("--")]

    creds = _api_load_creds(CREDS_FILE, auto_merge=True)
    if not creds:
        print(f"[!] ไม่พบบัญชีใน {CREDS_FILE} -> รัน capture_auto.py ก่อน")
        return

    if do_dump:
        dump_one(args[0] if args else next(iter(creds)), creds)
        return

    targets = [(k, creds[k]) for k in creds]
    if args:
        if args[0] not in creds:
            print(f"[X] ไม่พบ id '{args[0]}' (มี: {', '.join(creds) or '-'})")
            return
        targets = [(args[0], creds[args[0]])]

    mode = "เช็คอย่างเดียว (ไม่รับ)" if not claim else "รับรางวัล"
    print(f"[*] ภารกิจ — {mode} : {len(targets)} บัญชี\n", flush=True)

    results = {}
    with cf.ThreadPoolExecutor(max_workers=min(WORKERS, max(1, len(targets)))) as ex:
        for key, res in ex.map(lambda kv: _one(kv[0], kv[1], claim), targets):
            results[key] = res
            if res.get("ok") and res.get("lf_ac_next"):
                entry = creds.setdefault(key, {})
                entry["LF_AC"] = res.pop("lf_ac_next")
                if res.pop("gc_next", None):
                    entry["guestCookie"] = res["gc_next"]
            else:
                res.pop("lf_ac_next", None)
                res.pop("gc_next", None)

            if res.get("ok"):
                names = ", ".join(str(m) for m in res.get("missions", [])) or "-"
                print(f"[OK ] {key:<10} | file={res.get('file','-')} | "
                      f"ค้าง={res.get('pending',0)} | รับแล้ว={res.get('claimed',0)} | {names}", flush=True)
                if res.get("failed"):
                    print(f"       ↳ รับไม่ผ่าน {len(res['failed'])} ชิ้น: {res['failed'][:2]}", flush=True)
            else:
                print(f"[ERR] {key:<10} | file={res.get('file','-')}: {res}", flush=True)

    _api_save_creds(creds, CREDS_FILE)

    good = sum(1 for r in results.values() if r.get("ok"))
    tot_pend = sum(r.get("pending", 0) for r in results.values())
    tot_claim = sum(r.get("claimed", 0) for r in results.values())
    print("\n" + "=" * 55)
    print("สรุปภารกิจ:")
    print(f"  - สำเร็จ: {good}/{len(results)} บัญชี")
    print(f"  - ทำครบแต่ยังไม่รับ: {tot_pend} ชิ้น")
    print(f"  - รับไปได้: {tot_claim} ชิ้น")
    print("=" * 55)


if __name__ == "__main__":
    main()
