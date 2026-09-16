#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gacha_reroll.py — สุ่มกาชาผ่าน API (เลือกตัวที่อยากได้ = รีโรลจนติด)
ยิงตรง ไม่เปิดเกม ใช้ session ในcreds.json (โครงเดียวกับ collect_all/seven_days)

ใช้:
  # ดูตู้กาชาที่บัญชีนี้ยิงได้ (groupId/gachaId/index + ราคา)
  python gacha_reroll.py <id> --list

  # สุ่มตู้ที่เลือก N ครั้ง (ไม่เจาะเป้า)
  python gacha_reroll.py <id> --group grp_gacha_1 --gacha gacha_grp_1 --index 1 --n 5

  # รีโรล: สุ่มจนติดตัวเป้า (โค้ดหรือชื่อบางส่วน) หรือหมด budget/ครบ max
  python gacha_reroll.py <id> --group grp_gacha_1 --gacha gacha_grp_1 \
        --target u2030e-jessica --target kappa --max 50

หมายเหตุ:
  - กาชาสุ่มจริง: "เลือกตัว" = รีโรลจนออก ไม่ใช่การันตี — เปลืองทรัพยากรของบัญชีนั้น
  - target เทียบแบบทุกร่าง (base code) + substring กับ unitCode ที่สุ่มได้
  - หยุดอัตโนมัติเมื่อ: ติดเป้า / ruby(หรือทรัพยากร)ไม่พอ / ครบ --max
"""
import argparse
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lgr_api import (
    LGRClient, load_creds, save_creds, parse_ruby, CREDS_FILE,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _base_code(code):
    """ตัด tier วิวัฒนาการ: u1617e-ka -> u1617-ka (จับทุกร่าง)"""
    return re.sub(r"^(u\d+)[a-z]+(-.+)$", r"\1\2", (code or "").lower())


def _client_ready(cred):
    c = LGRClient(cred["udid"], cred["LF_AC"])
    st, _ = c.home()
    if st != 200 and cred.get("guestCookie"):
        st_l, _ = c.login(cred["guestCookie"])
        if st_l == 200:
            st, _ = c.home()
    return c, st


def _cost_field(g):
    """คืน (ชื่อทรัพยากร, ราคาต่อครั้ง) ของตู้"""
    if g.get("needRuby"):
        return "ruby", g["needRuby"]
    if g.get("needFriendship"):
        return "friendship", g["needFriendship"]
    if g.get("needEventTicket"):
        return "eventTicket", g["needEventTicket"]
    return "free", 0


def list_gacha(c):
    st, d = c.gacha_info()
    if st != 200 or not isinstance(d, dict):
        print(f"[X] gacha/info status={st}")
        return []
    rows = []
    for grp in d.get("result", {}).get("gachaGroupResponseList", []) or []:
        gg = grp.get("gachaGroup", {}) or {}
        for gi in gg.get("gachaGroupInfos", []) or []:
            rows.append(gi)
    return rows


def match_target(rewards, targets, tbase):
    for rc in rewards:                       # rc = "unit:xxx" / "equip:yyy"
        code = rc.split(":", 1)[-1].lower()
        for t in targets:
            if t in code or code == t or _base_code(code) == _base_code(t) or t in _base_code(code):
                return code
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id", help="rsn/คีย์บัญชีใน creds.json")
    ap.add_argument("--list", action="store_true", help="โชว์ตู้กาชาที่ยิงได้แล้วออก")
    ap.add_argument("--group")
    ap.add_argument("--gacha")
    ap.add_argument("--index", type=int, default=1)
    ap.add_argument("--target", action="append", default=[], help="โค้ด/ชื่อบางส่วนของตัวที่อยากได้ (ใส่ซ้ำได้)")
    ap.add_argument("--n", type=int, default=1, help="จำนวนครั้งเมื่อไม่ได้ตั้ง target")
    ap.add_argument("--max", type=int, default=50, help="เพดานจำนวนครั้งตอนรีโรล")
    args = ap.parse_args()

    creds = load_creds(CREDS_FILE)
    cred = creds.get(args.id)
    if not cred:
        print(f"[X] ไม่พบ id '{args.id}' (มี {len(creds)} บัญชี)")
        return

    c, st = _client_ready(cred)
    if st != 200:
        print(f"[X] เข้าเกมไม่ได้ (home status={st})")
        return

    if args.list or not (args.group and args.gacha):
        rows = list_gacha(c)
        creds[args.id]["LF_AC"] = c.lf_ac
        save_creds(creds, CREDS_FILE)
        print(f"[*] ตู้กาชาที่ยิงได้ ({len(rows)}):")
        for gi in rows:
            cf, cost = _cost_field(gi)
            print(f"  {gi.get('groupId'):22} {gi.get('gachaId'):18} idx={gi.get('gachaIndex')} "
                  f"pull={gi.get('gachaCount')}(+{gi.get('bonusCount',0)}) cost={cost} {cf}")
        if not args.list:
            print("\n-> ระบุ --group/--gacha เพื่อสุ่ม (ดู index จากด้านบน)")
        return

    targets = [t.lower().strip() for t in args.target if t.strip()]
    tbase = set(_base_code(t) for t in targets)
    # ราคาต่อครั้งของตู้ที่เลือก (ไว้เช็ก budget)
    rows = {(g.get("groupId"), g.get("gachaId"), g.get("gachaIndex")): g for g in list_gacha(c)}
    sel = rows.get((args.group, args.gacha, args.index))
    cost_field, cost = _cost_field(sel) if sel else ("ruby", 0)

    limit = args.max if targets else args.n
    mode = f"รีโรลหาเป้า {targets}" if targets else f"สุ่ม {args.n} ครั้ง"
    print(f"[*] {args.id} | {args.group}/{args.gacha} idx={args.index} | {mode} | cost={cost} {cost_field}/ครั้ง\n", flush=True)

    hit = None
    done = 0
    for i in range(limit):
        st, rewards, raw = c.gacha_pull(args.group, args.gacha, args.index)
        if st != 200:
            msg = ""
            if isinstance(raw, dict):
                msg = raw.get("errorCode") or raw.get("message") or raw
            print(f"  [{i+1}] หยุด: status={st} {str(msg)[:100]}", flush=True)
            break
        done += 1
        names = ", ".join(rewards) or "-"
        print(f"  [{i+1}] {names}", flush=True)
        if targets:
            got = match_target(rewards, targets, tbase)
            if got:
                hit = {"code": got, "pull": i + 1}
                print(f"  ★ ติดเป้า: {got} (ครั้งที่ {i+1})", flush=True)
                break

    # เก็บ LF_AC + ruby ล่าสุด
    creds[args.id]["LF_AC"] = c.lf_ac
    if c.guest_cookie_next:
        creds[args.id]["guestCookie"] = c.guest_cookie_next
    stp, prof = c.home()
    if stp == 200 and isinstance(prof, dict):
        res = prof.get("result", {})
        creds[args.id]["ruby"] = parse_ruby(res, res.get("player") or {})
    save_creds(creds, CREDS_FILE)

    print("\n" + "=" * 55)
    print(f"สุ่มไป {done} ครั้ง | " + (f"★ ติดเป้า {hit['code']} ครั้งที่ {hit['pull']}" if hit
          else ("ไม่ติดเป้า" if targets else "ครบจำนวน")))
    print(f"ruby คงเหลือ: {creds[args.id].get('ruby','?')}")
    print("=" * 55)


if __name__ == "__main__":
    main()
