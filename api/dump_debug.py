#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dump_debug.py — ดึง response จริงของ /home, /giftbox/list, /player/item, /login
มาเก็บเป็นไฟล์ JSON ใน logs/ เพื่อเอาไปแก้ field ที่ถูกต้อง (ticket / gift receive)

ใช้:  python dump_debug.py            # ใช้บัญชีแรกใน creds.json
      python dump_debug.py 107f4fcc  # เจาะจง id
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lgr_api import LGRClient, load_creds, CREDS_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

LOGDIR = os.path.join(HERE, "logs")
os.makedirs(LOGDIR, exist_ok=True)


def save(name, status, data):
    path = os.path.join(LOGDIR, f"debug_{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"status": status, "data": data}, f, ensure_ascii=False, indent=2)
    print(f"[saved] {path}  (status={status})")


def main():
    creds = load_creds(CREDS_FILE)
    if not creds:
        print("[X] ไม่มีบัญชีใน creds.json")
        return
    key = sys.argv[1] if len(sys.argv) > 1 else next(iter(creds))
    if key not in creds:
        print(f"[X] ไม่พบ id {key} (มี: {', '.join(list(creds)[:10])} ...)")
        return
    c = creds[key]
    print(f"[*] ใช้บัญชี: {key}")
    cli = LGRClient(c["udid"], c["LF_AC"])

    st, home = cli.home()
    if st != 200 and c.get("guestCookie"):
        cli.login(c["guestCookie"])
        st, home = cli.home()
    save("home", st, home)

    # ดึงทั้งหมดที่เกี่ยวกับ reroll/เช็คบัญชี
    for name, fn in [
        ("giftbox", cli.giftbox_list),
        ("player_item", cli.player_items),
        ("gacha_info", cli.gacha_info),
        ("mission_list", cli.mission_list),
        ("stage_last", cli.stage_last),
    ]:
        try:
            s, d = fn()
            save(name, s, d)
        except Exception as e:
            print(f"[!] {name} error: {e}")

    # สรุปแบบเดียวกับบอท (lv / ruby / coin / ticket / gift)
    res = home.get("result", {}) if isinstance(home, dict) else {}
    player = res.get("player", {}) or {}
    from lgr_api import parse_ruby, parse_coin
    tk = cli.ticket_count()
    lv = player.get("level") or res.get("level")
    print("\n" + "=" * 50)
    print(f"[SUMMARY] id={key}")
    print(f"  level  = {lv}")
    print(f"  ruby   = {parse_ruby(res, player)}")
    print(f"  coin   = {parse_coin(res, player)}")
    print(f"  ticket = {tk}   (premium/classic/event/total)")
    print(f"  gift   = {res.get('badge', {}).get('GIFT', 0)}")
    ver = home.get("version") if isinstance(home, dict) else None
    print(f"  server version = {ver}")
    print("=" * 50)
    print("[*] เสร็จ — ส่งไฟล์ logs/debug_*.json ให้ผมอ่าน (home/giftbox/player_item/gacha_info/mission_list/stage_last)")


if __name__ == "__main__":
    main()
