#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gacha_dump.py — โหลดข้อมูลตู้กาชาทั้งหมด + รูปแบนเนอร์ มาเก็บในเครื่อง

ใช้:
  python gacha_dump.py <id> [--lang th]

ได้:
  gacha_data/gacha_info.json   ก้อนดิบจาก /gacha/info (ทุกตู้ ทุก field)
  gacha_data/banners.json      สรุปต่อตู้: ชื่อตัวเด่น / ประเภท / ราคา / ตั๋ว / รูป
  gacha_data/bg/*.png          รูปแบนเนอร์ (game.line-scdn.net เป็น CDN สาธารณะ ไม่ต้องใช้ cookie)
"""
import argparse
import json
import os
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lgr_api import LGRClient, load_creds, try_update_creds, CREDS_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT = os.path.join(HERE, "gacha_data")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id", help="rsn/คีย์บัญชีใน creds.json")
    ap.add_argument("--lang", default="th", help="ภาษารูปแบนเนอร์ (th/en/ja/ko/zh-Hant)")
    args = ap.parse_args()

    creds = load_creds(CREDS_FILE)               # อ่านอย่างเดียว (บัญชีเดียวที่ระบุ ไม่ต้อง merge part)
    cred = creds.get(args.id)
    if not cred:
        print(f"[X] ไม่พบ id '{args.id}'")
        return
    c = LGRClient(cred["udid"], cred["LF_AC"])
    st, d = c.gacha_info()
    # เก็บ LF_AC ที่หมุนใหม่ เฉพาะบัญชีนี้ลงไฟล์ล่าสุด (error ถูกพิมพ์แจ้งใน try_update_creds)
    try_update_creds({args.id: {"LF_AC": c.lf_ac, "guestCookie": c.guest_cookie_next}}, CREDS_FILE)
    if st != 200 or not isinstance(d, dict):
        print(f"[X] gacha/info status={st} {str(d)[:200]}")
        return

    os.makedirs(os.path.join(OUT, "bg"), exist_ok=True)
    with open(os.path.join(OUT, "gacha_info.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)

    banners = []
    for grp in d.get("result", {}).get("gachaGroupResponseList", []) or []:
        gg = grp.get("gachaGroup", {}) or {}
        urls = gg.get("bgUrl") or {}
        url = urls.get(args.lang) or urls.get("en") or next(iter(urls.values()), "")
        local = ""
        if url:
            local = os.path.join("bg", url.rsplit("/", 1)[-1])
            path = os.path.join(OUT, local)
            if not os.path.exists(path):
                r = requests.get(url, timeout=30)
                if r.status_code == 200:
                    with open(path, "wb") as f:
                        f.write(r.content)
                else:
                    local = ""
        banners.append({
            "groupId": gg.get("groupId"),
            "display": gg.get("gachaDisplayType"),
            "badge": gg.get("gachaBadgeType"),
            "featured": gg.get("titleRewardCodes", []),
            "bgUrl": url,
            "bgFile": local,
            "pulls": [{
                "gachaId": gi.get("gachaId"),
                "index": gi.get("gachaIndex"),
                "count": gi.get("gachaCount"),
                "bonus": gi.get("bonusCount", 0),
                "ruby": gi.get("displayRubyPrice", 0),
                "friendship": gi.get("displayFriendshipPrice", 0),
                "ticket": gi.get("ticketPayableCost") if gi.get("ticketPayableType") == "TICKET" else 0,
            } for gi in gg.get("gachaGroupInfos", []) or []],
            # field อื่นของกลุ่ม (วันหมดเขต/เรท ฯลฯ ถ้ามี) เก็บไว้ดู
            "extra": {k: v for k, v in gg.items()
                      if k not in ("gachaGroupInfos", "bgUrl", "titleRewardCodes")},
        })
        print(f"  {gg.get('groupId'):18} {gg.get('gachaDisplayType',''):14} "
              f"{', '.join(gg.get('titleRewardCodes', []))}  {'✓ รูป' if local else '- ไม่มีรูป'}")

    with open(os.path.join(OUT, "banners.json"), "w", encoding="utf-8") as f:
        json.dump(banners, f, ensure_ascii=False, indent=1)
    print(f"\n[*] {len(banners)} ตู้ -> {OUT}")


if __name__ == "__main__":
    main()
