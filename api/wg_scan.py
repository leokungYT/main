#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
wg_scan.py — สแกนไฟล์ WG ทั้งหมดใน wg/ จาก PC ว่า IP ไหน "เกมบล็อก" แล้ว คัดออก + สร้างใหม่แทน

ทำไม: บอทในอีมูสุ่มไฟล์ทีละตัว ลองได้แค่ wg_probe_max (5) ตัว ถ้าไฟล์ส่วนใหญ่โดนบล็อก
      จะยอมแพ้แล้วเล่นแบบไม่มี VPN -> เข้าเกมไม่ได้ ; สแกนล่วงหน้าให้เหลือแต่ไฟล์ที่ใช้ได้

วิธีทดสอบ: wireproxy (tools/wireproxy.exe) ต่อทีละไฟล์ -> ยิง /v12.3/__probe
   404 = ใช้ได้ , 403 = เกมบล็อก IP , 0 = ต่อไม่ติด (ไม่ตัดสิน)
ผล: IP ที่บล็อก -> จดลง wg/.blocked.json (บอท/wg_gen ไม่ใช้/ไม่สร้างซ้ำ) + ลบไฟล์ -> wg_gen สร้างใหม่ให้ครบจำนวนเดิม
    แล้วสแกนไฟล์ใหม่ซ้ำ (สูงสุด --rounds รอบ)

ใช้:  python wg_scan.py            (สแกน + ลบ + สร้างใหม่)
      python wg_scan.py --dry      (สแกนอย่างเดียว ไม่แตะไฟล์)
หมายเหตุ: ใช้พอร์ต 1080 — ปิด web_app.py / wg-proxy.bat ก่อน
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import web_app as w   # ใช้ตัวเปิด/ปิด wireproxy + อ่าน endpoint เดียวกับเว็บ


def scan(confs):
    res = {}
    for i, c in enumerate(confs, 1):
        w._wg_stop()
        w._wg_start(c)
        code = w._wg_probe()
        if code == 0:                         # handshake ช้า ลองอีกครั้ง
            time.sleep(2)
            code = w._wg_probe()
        res[c] = code
        mark = {404: "✓ ใช้ได้", 403: "✗ บล็อก"}.get(code, "? ต่อไม่ติด")
        print(f"  [{i}/{len(confs)}] {c:48} {code}  {mark}", flush=True)
    w._wg_stop()
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="สแกนอย่างเดียว ไม่ลบ/ไม่สร้างใหม่")
    ap.add_argument("--rounds", type=int, default=3, help="สร้างใหม่แล้วสแกนซ้ำกี่รอบ")
    args = ap.parse_args()

    if w._port_open(1080):
        print("[X] พอร์ต 1080 ถูกใช้อยู่ — ปิด web_app.py / wg-proxy.bat ก่อน")
        return
    done = set()
    for rnd in range(1, args.rounds + 1):
        blocked_eps = w._wg_blocked_eps()
        confs = sorted(f for f in os.listdir(w.WG_DIR) if f.endswith(".conf") and f not in done)
        if not confs:
            break
        print(f"\n[รอบ {rnd}] สแกน {len(confs)} ไฟล์", flush=True)
        res = scan(confs)
        done.update(confs)
        bad = [c for c, code in res.items() if code == 403]
        ok = [c for c, code in res.items() if code == 404]
        print(f"[รอบ {rnd}] ใช้ได้ {len(ok)} · บล็อก {len(bad)} · ต่อไม่ติด {len(res) - len(ok) - len(bad)}", flush=True)
        if args.dry or not bad:
            break
        # จด IP ที่บล็อก + ลบไฟล์ทั้งหมดในครั้งเดียว แล้ว gen ใหม่ครั้งเดียว
        want = len([f for f in os.listdir(w.WG_DIR) if f.endswith(".conf")])
        bp = os.path.join(w.WG_DIR, ".blocked.json")
        try:
            d = json.load(open(bp, encoding="utf-8"))
        except Exception:
            d = {}
        eps = {w._wg_endpoint(c) for c in bad}
        for ep in eps:
            d[ep] = time.time()
        with open(bp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        for f in os.listdir(w.WG_DIR):
            if f.endswith(".conf") and w._wg_endpoint(f) in eps:
                os.remove(os.path.join(w.WG_DIR, f))
        print(f"[รอบ {rnd}] ลบไฟล์ที่บล็อกแล้ว -> สร้างใหม่ให้ครบ {want} ไฟล์", flush=True)
        root = os.path.dirname(HERE)
        sys.path.insert(0, root)
        import wg_gen
        cfg = w._wg_cfg()
        wg_gen.generate(want, cfg.get("wg_gen_countries") or None, w.WG_DIR,
                        int(cfg.get("wg_machine", 0) or 0),
                        str(cfg.get("wg_account", "") or "").strip() or None,
                        int(cfg.get("wg_total_machines", 30) or 30))
    left = [f for f in os.listdir(w.WG_DIR) if f.endswith(".conf")]
    print(f"\n[*] เสร็จ — ตอนนี้มี {len(left)} ไฟล์ใน wg/ ; IP ที่บล็อกจดใน wg/.blocked.json", flush=True)


if __name__ == "__main__":
    main()
