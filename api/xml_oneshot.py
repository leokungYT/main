#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# xml_oneshot.py - xml เข้า -> ใช้ MuMu+mitm decrypt -> ยิง api -> พิมพ์ผลจอ
# ไม่แตะ creds.json หลัก. captured creds ไว้ใน dict ของโปรเซส, ทิ้งเมื่อจบ.
#
# usage:
#   python xml_oneshot.py --xml-dir "C:\...\login-success"
#   python xml_oneshot.py --xml  "C:\...\one.xml"
#   python xml_oneshot.py --xml-dir "..." --limit 5 --out fresh.jsonl
#
# precondition: WG + mitm + emu routing + emu serial — เหมือน run-replay-all.ps1

import argparse, glob, json, os, re, subprocess, sys, time, tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lgr_api import LGRClient, parse_ruby, parse_coin


RSN_RX = re.compile(r'([0-9a-f]{8})_LINE_COCOS')
UDID_RX = re.compile(r'name="_DEVICE_UUID_KEY">([^<]+)</string>')
PKG   = "com.linecorp.LGRGS"
ACTV  = f"{PKG}/{PKG}.LineRangersAdr"
PREF  = f"/data/data/{PKG}/shared_prefs/_LINE_COCOS_PREF_KEY.xml"


def adb(serial, *args, check=True, capture=False):
    cmd = ["adb", "-s", serial, *args]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if check and r.returncode != 0:
        raise RuntimeError(f"adb failed: {' '.join(cmd)}\n{r.stderr}")
    return r.stdout if capture else None


def rsn_from(name):
    m = RSN_RX.search(name)
    return m.group(1) if m else None


def udid_from_xml(path):
    txt = Path(path).read_text(encoding="utf-8", errors="ignore")
    m = UDID_RX.search(txt)
    return m.group(1).strip() if m else None


def push_and_launch(serial, xml_path):
    adb(serial, "push", xml_path, "/sdcard/_lgr_prefs.xml")
    uid = adb(serial, "shell", f"su -c 'stat -c %u /data/data/{PKG}'", capture=True).strip()
    adb(serial, "shell",
        f"su -c 'cp /sdcard/_lgr_prefs.xml {PREF} && chown {uid}:{uid} {PREF} && chmod 660 {PREF}'")
    adb(serial, "shell", f"am force-stop {PKG}")
    time.sleep(0.4)
    adb(serial, "shell", f"am start -n {ACTV}")


def wait_capture(captured_file, rsn, timeout=25):
    """เฝ้าไฟล์ที่ mitm addon เขียน; รอจนเจอ rsn หรือ timeout. คืน dict ของบัญชีนั้น หรือ None"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data = json.loads(Path(captured_file).read_text(encoding="utf-8"))
            if rsn in data and data[rsn].get("LF_AC") and data[rsn].get("guestCookie"):
                return data[rsn]
        except Exception:
            pass
        time.sleep(1)
    return None


def check_live(acct):
    cli = LGRClient(acct["udid"], acct["LF_AC"])
    st, resp = cli.home()
    if st == 401:
        st, resp = cli.login(acct["guestCookie"])
    if st != 200 or not isinstance(resp, dict) or "result" not in resp:
        return {"ok": False, "status": st,
                "err": resp.get("errorCode") if isinstance(resp, dict) else None}
    r = resp["result"] or {}
    p = r.get("player", {}) or {}
    return {
        "ok": True,
        "rsn":   p.get("rsn") or r.get("rsn"),
        "level": p.get("level") or r.get("level"),
        "ruby":  parse_ruby(r, p),
        "coin":  parse_coin(r, p),
        "name":  p.get("userName"),
        "udid":  acct["udid"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml")
    ap.add_argument("--xml-dir")
    ap.add_argument("--serial", default="127.0.0.1:7555")
    ap.add_argument("--wait", type=int, default=25)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", help="เขียนบัญชี OK ลง jsonl (ไม่ใส่ = พิมพ์จอเท่านั้น)")
    ap.add_argument("--captured",
                    default=os.environ.get("LGR_CREDS_FILE") or os.path.join(tempfile.gettempdir(), "lgr_captured.json"),
                    help="ไฟล์ที่ mitm addon เขียน (ตั้ง env LGR_CREDS_FILE ตอนเปิด mitm ให้ตรงกัน)")
    args = ap.parse_args()

    # เคลียร์ไฟล์ captured ก่อนเริ่ม = รอบนี้จะมีเฉพาะที่เพิ่งเกิด
    Path(args.captured).write_text("{}", encoding="utf-8")
    print(f"[CFG] captured_file={args.captured}")
    print(f"[CFG] serial={args.serial} wait={args.wait}s")

    xmls = [args.xml] if args.xml else sorted(glob.glob(os.path.join(args.xml_dir, "*.xml")))
    if args.limit > 0: xmls = xmls[:args.limit]
    if not xmls: sys.exit("ไม่เจอ xml")

    out_fp = open(args.out, "a", encoding="utf-8") if args.out else None
    ok = dead = miss = 0
    for i, x in enumerate(xmls, 1):
        rsn = rsn_from(os.path.basename(x))
        udid = udid_from_xml(x)
        print(f"\n[{i}/{len(xmls)}] {os.path.basename(x)} rsn={rsn} udid={udid[:12] if udid else '?'}")
        if not rsn or not udid:
            miss += 1; print("  MISS no rsn/udid"); continue

        push_and_launch(args.serial, x)
        acct = wait_capture(args.captured, rsn, timeout=args.wait)
        adb(args.serial, "shell", f"am force-stop {PKG}", check=False)   # หยุดก่อน check
        time.sleep(1)

        if not acct:
            miss += 1; print("  MISS no capture within timeout"); continue

        r = check_live(acct)
        if r["ok"]:
            ok += 1
            print(f"  OK   lv={r['level']} ruby={r['ruby']} coin={r['coin']:,} name={r['name']!r}")
            if out_fp:
                out_fp.write(json.dumps({"rsn": rsn, **r, **{"guestCookie": acct["guestCookie"]}}, ensure_ascii=False) + "\n")
                out_fp.flush()
        else:
            dead += 1
            print(f"  DEAD st={r['status']} err={r.get('err')}")

    if out_fp: out_fp.close()
    print(f"\n=== ok={ok} dead={dead} miss={miss} total={len(xmls)} ===")
    if args.out: print(f"    alive -> {args.out}")


if __name__ == "__main__":
    main()
