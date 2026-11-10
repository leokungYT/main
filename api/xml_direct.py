#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# xml_direct.py - อ่าน xml อย่างเดียว -> ยิง rangers-api ตรง
# ไม่มี MuMu, ไม่มี mitm, ไม่มี store กลาง
#
# ใช้:
#   python xml_direct.py --xml "C:\...\one.xml"
#   python xml_direct.py --xml-dir "C:\...\login-success" --limit 5
#
# สิ่งที่ดึงจาก xml ได้:
#   udid              (_DEVICE_UUID_KEY)       plaintext
#   nation            (USER_NATION_CODE)       plaintext
#   user_type         (_LF_UT_KEY)             plaintext (GUEST)
#   enc_guestCookie   (_ENC_LF_AC_KEY)         AES-encrypted, device-bound key
#
# ที่ server ต้องการเพื่อ auth:
#   Cookie: udid=<udid>; LF_AC=<session>
#   /login ต้องการ guestCookie=<credential> (ถอดจาก enc_guestCookie)
#
# ไม่มี key => ไม่มี guestCookie => server ตอบ 401/403 ทุก request

import argparse, glob, os, re, sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lgr_api import LGRClient, parse_ruby, parse_coin

RSN_RX  = re.compile(r'([0-9a-f]{8})_LINE_COCOS')
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
        m = rx.search(txt)
        out[k] = m.group(1).strip() if m else None
    m = RSN_RX.search(os.path.basename(path))
    out["rsn"] = m.group(1) if m else None
    return out


def probe(field):
    """ยิง api โดยใช้แค่สิ่งที่ xml ให้ (udid). ทำได้แค่ /home + /login (empty guestCookie)
    = คาดหวัง 401 แน่นอน; พิมพ์เป็นหลักฐานว่าเข้าไม่ได้"""
    cli = LGRClient(udid=field["udid"], lf_ac="",
                    nation=field.get("nation") or "TH")

    print(f"  -> GET /home       (udid only, no LF_AC)")
    st, r = cli.home()
    print(f"     status={st}  errCode={r.get('errorCode') if isinstance(r,dict) else '-'}  ", end="")
    if st == 200 and isinstance(r, dict) and "result" in r:
        rr = r["result"] or {}; pp = rr.get("player", {}) or {}
        print(f"OK lv={pp.get('level')} ruby={parse_ruby(rr,pp)} coin={parse_coin(rr,pp):,}")
        return "OK"
    print()

    print(f"  -> GET /login      (no guestCookie, xml encrypted blob not usable)")
    st, r = cli.login(guest_cookie="")
    print(f"     status={st}  errCode={r.get('errorCode') if isinstance(r,dict) else '-'}  "
          f"msg={r.get('errorMessage') if isinstance(r,dict) else '-'}")
    return f"BLOCKED (st={st})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml")
    ap.add_argument("--xml-dir")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--extract-only", action="store_true",
                    help="แค่ดึงค่าจาก xml ไม่ยิง api")
    args = ap.parse_args()

    xmls = [args.xml] if args.xml else sorted(glob.glob(os.path.join(args.xml_dir, "*.xml")))
    if args.limit > 0: xmls = xmls[:args.limit]
    if not xmls: sys.exit("ไม่เจอ xml")

    for i, x in enumerate(xmls, 1):
        f = parse_xml(x)
        name = os.path.basename(x)
        print(f"\n[{i}/{len(xmls)}] {name}")
        print(f"  rsn       = {f['rsn']}")
        print(f"  udid      = {f['udid']}")
        print(f"  nation    = {f['nation']}")
        print(f"  user_type = {f['user_type']}")
        print(f"  enc_blob  = {('len=' + str(len(f['enc_blob']))) if f['enc_blob'] else 'MISSING'} (encrypted; ต้องมี AES key จึงถอดได้)")

        if args.extract_only: continue
        if not f["udid"]:
            print("  SKIP no udid")
            continue
        probe(f)


if __name__ == "__main__":
    main()
