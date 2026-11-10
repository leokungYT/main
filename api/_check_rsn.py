#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ใช้คู่กับ xml_replay.ps1 — ตรวจสถานะบัญชีหลัง mitm จับ creds
# รัน: python _check_rsn.py <rsn>
import sys
from lgr_api import LGRClient, load_creds

if len(sys.argv) < 2:
    sys.exit("usage: python _check_rsn.py <rsn>")
rsn = sys.argv[1]
c = load_creds()
if rsn not in c:
    print(f"MISS {rsn} not in creds.json")
    sys.exit(0)
a = c[rsn]
if not (a.get("udid") and a.get("LF_AC") and a.get("guestCookie")):
    print(f"MISS {rsn} creds incomplete")
    sys.exit(0)
cli = LGRClient(a["udid"], a["LF_AC"])

# ลำดับที่เบาที่สุดต่อ server:
# 1) ยิง /home ด้วย LF_AC ล่าสุด (ไม่ consume guestCookie)
# 2) 401 ค่อย /login ด้วย guestCookie (consume 1 ครั้ง — เก็บ LF_AC ใหม่ลง creds)
st, resp = cli.home()
if st == 401:
    st, resp = cli.login(a["guestCookie"])

if st == 200 and isinstance(resp, dict) and "result" in resp:
    from lgr_api import parse_ruby, parse_coin
    r = resp["result"] or {}
    p = r.get("player", {}) or {}
    lv   = p.get("level") or r.get("level")
    ruby = parse_ruby(r, p)
    coin = parse_coin(r, p)
    name = p.get("userName") or rsn
    print(f"OK   {rsn} lv={lv} ruby={ruby} coin={coin:,} name={name!r}")
    # เขียน LF_AC/guestCookie ที่หมุนใหม่กลับ creds.json ให้รอบต่อไปใช้ได้
    from lgr_api import update_creds
    upd = {"LF_AC": cli.lf_ac}
    if cli.guest_cookie_next:
        upd["guestCookie"] = cli.guest_cookie_next
    update_creds({rsn: upd})
else:
    ec = resp.get("errorCode") if isinstance(resp, dict) else st
    em = resp.get("errorMessage") if isinstance(resp, dict) else None
    print(f"DEAD {rsn} st={st} ec={ec} em={em}")
