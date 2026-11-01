# -*- coding: utf-8 -*-
"""สร้างไฟล์ WireGuard (.conf) ของ Windscribe ให้ครบทุกจอ โดยไม่ต้องกดโหลดทีละเมือง

หลักการ: ไฟล์ .conf ของ Windscribe = Key Pair ของเรา ([Interface] + PresharedKey)
         + PublicKey/Endpoint ของเซิร์ฟเวอร์ (มีในรายชื่อเซิร์ฟเวอร์สาธารณะของ Windscribe)
ดังนั้นใช้ไฟล์ที่โหลดมาแล้ว 1 ไฟล์เป็นต้นแบบ (เอาแค่ Key Pair) แล้วสร้างไฟล์คนละเซิร์ฟเวอร์ได้หลายสิบไฟล์
แต่ละไฟล์คนละเซิร์ฟเวอร์ = ต่อพร้อมกันได้ ไม่ตีกัน (กุญแจเดียวกันห้ามต่อเซิร์ฟเวอร์เดียวกันซ้ำ)

ใช้:  python wg_gen.py 30            -> ให้มีไฟล์ใน wg/ ครบ 30 ไฟล์ (เพิ่มเฉพาะที่ขาด)
      python wg_gen.py 30 TH SG JP   -> เลือกประเทศเอง (รหัส 2 ตัว) ตามลำดับ
"""
import json
import os
import sys
import urllib.request

WG_DIR = "wg"
SERVERLIST_URL = "https://assets.windscribe.com/serverlist/mob-v2/1/0"
# ประเทศใกล้ไทยก่อน (ping ต่ำ เกมโหลดเร็ว) แล้วค่อยไกลออกไป
DEFAULT_COUNTRIES = ["TH", "SG", "HK", "MY", "VN", "JP", "KR", "TW", "ID", "PH", "KH",
                     "IN", "AU", "NZ", "AE", "TR", "US", "CA", "GB", "DE", "FR", "NL"]


def read_conf(path):
    kv = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            if "=" in line:
                k, v = line.split("=", 1)
                kv[k.strip()] = v.strip()
    return kv


def main():
    # python wg_gen.py 15 [--account account2] [--machine 3] [--total 30] [--dir wg/ip-chan/main-1] [TH SG ...]
    # ไม่ระบุ --dir -> อ่าน wg_profile จาก configmain.json: list -> วนทุกโฟลเดอร์ย่อย
    args = sys.argv[1:]
    opt = {}
    for k in ("--account", "--machine", "--total", "--dir"):
        if k in args:
            i = args.index(k)
            opt[k] = args[i + 1]
            del args[i:i + 2]
    save = "--save-config" in args
    if save:
        args.remove("--save-config")
    want = int(args[0]) if args and args[0].isdigit() else 30
    countries = [c.upper() for c in args[1:]] or None
    if save:
        save_config(opt.get("--account"), opt.get("--machine"))
    machine = int(opt.get("--machine", 0))
    acc = opt.get("--account")
    total = int(opt.get("--total", 0))
    if "--dir" in opt:
        return generate(want, countries, opt["--dir"], machine, acc, total)
    dirs = _wg_profile_dirs()
    if not dirs:
        return generate(want, countries, None, machine, acc, total)
    print(f"[WG-GEN] wg_profile มี {len(dirs)} โฟลเดอร์ - generate ทีละอัน ({', '.join(dirs)})")
    rc = 0
    for i, d in enumerate(dirs, 1):
        print(f"\n[WG-GEN] ===== [{i}/{len(dirs)}] โฟลเดอร์: {d} =====")
        r = generate(want, countries, d, machine, acc, total)
        rc = r or rc
    print(f"\n[WG-GEN] จบครบ {len(dirs)} โฟลเดอร์")
    return rc


def _wg_profile_dirs():
    """อ่าน configmain.json -> wg_profile -> คืน list ของ path โฟลเดอร์ที่มีจริง (relative จากโฟลเดอร์ repo)"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(script_dir, "configmain.json"), encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except Exception:
        return []
    prof = cfg.get("wg_profile", "")
    if isinstance(prof, (list, tuple)):
        profs = [str(p).strip() for p in prof if str(p).strip()]
    else:
        s = str(prof or "").strip()
        profs = [p.strip() for p in s.split(",") if p.strip()] if s else []
    out = []
    for p in profs:
        for cand in (os.path.join("wg", p), p):
            if os.path.isdir(os.path.join(script_dir, cand)):
                out.append(cand.replace("\\", "/"))
                break
        else:
            print(f"[WG-GEN] wg_profile='{p}' ไม่พบโฟลเดอร์ - ข้าม")
    return out


def save_config(account=None, machine=None, path="configmain.json"):
    """เขียน wg_enabled=1 / wg_account / wg_machine ลง configmain.json (แก้เฉพาะค่านั้น ไม่จัดรูปไฟล์ใหม่)"""
    import re
    raw = open(path, "rb").read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    t = raw.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in t else "\n"
    vals = {"wg_enabled": "1"}
    if account:
        vals["wg_account"] = json.dumps(account)
    if machine:
        vals["wg_machine"] = str(int(machine))
    for k, v in vals.items():
        pat = r'("' + k + r'"\s*:\s*)("[^"]*"|[^,\r\n}]+)'
        if re.search(pat, t):
            t = re.sub(pat, lambda m, v=v: m.group(1) + v, t, count=1)
        else:
            t = t.replace("{", "{" + nl + '    "' + k + '": ' + v + ",", 1)
    json.loads(t)                       # กันไฟล์พัง: JSON ไม่ถูกจะ error ก่อนเขียน
    open(path, "wb").write((b"\xef\xbb\xbf" if bom else b"") + t.encode("utf-8"))
    print("[WG-GEN] configmain.json: " + ", ".join(f"{k}={v}" for k, v in vals.items()))


def load_blocked(wg_dir):
    """{endpoint: เวลาที่โดนบล็อก} ที่ยังไม่หมดอายุ (wg_blocked_days วัน, default 7)"""
    try:
        with open(os.path.join(wg_dir, ".blocked.json"), encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return {}
    try:
        days = float(json.load(open(os.path.join(os.path.dirname(os.path.abspath(wg_dir)), "configmain.json"),
                                    encoding="utf-8-sig")).get("wg_blocked_days", 7))
    except Exception:
        days = 7.0
    import time as _t
    return {k: v for k, v in d.items() if _t.time() - v < days * 86400}


def generate(want, countries=None, wg_dir=None, machine=0, account=None, total=0, managed_ok=False):
    """ให้มีไฟล์ใน wg_dir อย่างน้อย want ไฟล์ - คืน 0 = สำเร็จ/ครบแล้ว, 1 = สร้างไม่ได้

    ใช้ keypair จากไฟล์ .conf แรกใน wg_dir ที่ส่งเข้ามา (ที่ user โยนมา) เท่านั้น
    ไม่ fallback ไปที่ keypair.txt / wg_accounts/ / _backup อีกต่อไป -
    ไม่งั้นกุญแจบัญชีเก่าจะถูกใช้ generate ลง pool ของบัญชีใหม่ = ต่อ VPN แต่ใช้ key ผิดบัญชี
    """
    global WG_DIR
    if wg_dir:
        WG_DIR = wg_dir
    countries = countries or DEFAULT_COUNTRIES
    machine = int(machine or 0)
    if not total:
        try:
            _cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(WG_DIR)), "configmain.json"),
                                  encoding="utf-8-sig"))
        except Exception:
            _cfg = {}
        total = int(_cfg.get("wg_total_machines", 30) or 30)
    if os.path.exists(os.path.join(WG_DIR, ".managed")) and not managed_ok:
        print("[WG-GEN] ไฟล์ VPN มาจาก server (RemoteFileManager) - ไม่สร้างเพิ่มเอง")
        return 0

    os.makedirs(WG_DIR, exist_ok=True)
    confs = sorted(f for f in os.listdir(WG_DIR) if f.lower().endswith(".conf"))
    if not confs:
        print(f"[WG-GEN] {WG_DIR}/ ไม่มีไฟล์ .conf ต้นแบบ - โยนไฟล์ 1 ไฟล์จากหน้า Config Generator ของ Windscribe ลงโฟลเดอร์นี้ก่อน")
        return 1
    tpl = read_conf(os.path.join(WG_DIR, confs[0]))
    tpl_name = confs[0]
    have = [read_conf(os.path.join(WG_DIR, f)) for f in confs]
    for k in ("PrivateKey", "Address", "DNS", "PresharedKey"):
        if not tpl.get(k):
            print(f"[WG-GEN] ไฟล์ต้นแบบ {tpl_name} ไม่มี {k} - โหลดใหม่จากหน้า Config Generator ของ Windscribe")
            return 1
    print(f"[WG-GEN] ใช้ Key Pair จาก {WG_DIR}/{tpl_name} | มีอยู่แล้ว {len(confs)} ไฟล์ ต้องการ {want}"
          + (f" | เครื่องที่ {machine}" if machine else ""))
    if len(confs) >= want:
        print("[WG-GEN] ครบแล้ว ไม่ต้องสร้างเพิ่ม")
        return 0

    print("[WG-GEN] โหลดรายชื่อเซิร์ฟเวอร์ Windscribe...")
    req = urllib.request.Request(SERVERLIST_URL, headers={"User-Agent": "Mozilla/5.0"})
    data = None
    for _try in range(3):
        try:
            data = json.load(urllib.request.urlopen(req, timeout=30))["data"]
            break
        except Exception as e:
            print(f"[WG-GEN] โหลดรายชื่อเซิร์ฟเวอร์ไม่ได้ ({e}) - ลองใหม่ ({_try + 1}/3)")
            import time as _t; _t.sleep(5)
    if data is None:
        print("[WG-GEN] เน็ต/DNS ของเครื่องใช้ไม่ได้ - ยังสร้าง IP ไม่ได้ (เช็คว่าเข้าเว็บได้ไหม ถ้าไม่ได้ให้รัน fix-dns.bat)")
        return 1

    # เซิร์ฟเวอร์ที่ใช้อยู่แล้ว (กุญแจไหนก็ตาม) ไม่ซ้ำ จะได้ IP ไม่ซ้ำด้วย
    used = {kv.get("PublicKey") for kv in have}
    # ประเทศที่เซิร์ฟเวอร์เกมบล็อก IP VPN (ทดสอบ 2026-10-06: Bangkok ออกเน็ตได้แต่ rangers-api ไม่ตอบ)
    try:
        _ex = json.load(open(os.path.join(os.path.dirname(os.path.abspath(WG_DIR)), "configmain.json"),
                             encoding="utf-8-sig")).get("wg_exclude_countries", ["TH"])
    except Exception:
        _ex = ["TH"]
    exclude = {str(c).upper() for c in (_ex or [])}
    blocked = load_blocked(WG_DIR)      # เซิร์ฟเวอร์ที่บอทเจอว่าเกมบล็อก IP (wg/.blocked.json) - ไม่สร้างซ้ำ
    order = {c: i for i, c in enumerate(countries)}
    groups = []
    for loc in data:
        cc = loc.get("country_code", "")
        if not loc.get("status", 1) or cc in exclude:
            continue
        for g in loc.get("groups") or []:
            if not g.get("wg_pubkey") or not g.get("wg_endpoint") or not g.get("nodes"):
                continue
            if g["wg_endpoint"] in blocked:
                continue
            groups.append((order.get(cc, len(order)), cc, g))
    # เรียงแบบตายตัว (ทุกเครื่องได้ลำดับเดียวกัน) -> แบ่งช่วงต่อเครื่องได้ไม่ชน
    groups.sort(key=lambda x: (x[0], x[1], int(x[2].get("id") or 0)))
    every = groups
    if machine:
        start = ((machine - 1) * want) % max(1, len(groups))
        groups = (groups[start:] + groups[:start])[:want]
        print(f"[WG-GEN] เครื่องที่ {machine}: ใช้เซิร์ฟเวอร์ลำดับ {start + 1}-{start + len(groups)} จาก {len(every)}")
    else:
        groups = [x for x in groups if x[1] in order]   # โหมดเครื่องเดียว: เอาเฉพาะประเทศที่เลือกก่อน
    groups = [x for x in groups if x[2]["wg_pubkey"] not in used]
    if len(confs) + len(groups) < want:
        # ช่วงของเครื่อง/ประเทศที่เลือกหมดแล้ว (โดนบล็อก/ใช้ไปแล้ว) -> สร้างต่อจากเซิร์ฟเวอร์ที่เหลือทั้งหมดเอง
        # ไม่ปล่อยให้จอค้าง "ไม่มีไฟล์ .conf" (เสี่ยงชนเครื่องอื่นกุญแจเดียวกันบ้าง ดีกว่าไม่มี IP)
        picked = {id(x[2]) for x in groups}
        extra = [x for x in every if id(x[2]) not in picked and x[2]["wg_pubkey"] not in used]
        if extra:
            print(f"[WG-GEN] เซิร์ฟเวอร์ในช่วงที่กำหนดไม่พอ - ขยายไปเซิร์ฟเวอร์อื่นอีก {len(extra)} ตัว")
        groups += extra

    made = 0
    port = tpl.get("Endpoint", ":443").rsplit(":", 1)[-1] or "443"
    for _, cc, g in groups:
        if len(confs) + made >= want:
            break
        city = (g.get("city") or cc).replace(" ", "-")
        nick = (g.get("nick") or str(g.get("id"))).replace(" ", "-")
        name = f"Windscribe-{city}-{nick}-WG.conf"
        path = os.path.join(WG_DIR, name)
        if os.path.exists(path):
            continue
        text = (
            "[Interface]\n"
            f"PrivateKey = {tpl['PrivateKey']}\n"
            f"Address = {tpl['Address']}\n"
            f"DNS = {tpl['DNS']}\n"
            "\n[Peer]\n"
            f"PublicKey = {g['wg_pubkey']}\n"
            f"AllowedIPs = {tpl.get('AllowedIPs', '0.0.0.0/0, ::/0')}\n"
            f"Endpoint = {g['wg_endpoint']}:{port}\n"
            f"PresharedKey = {tpl['PresharedKey']}\n"
        )
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        made += 1
        print(f"[WG-GEN] + {name}  ({cc} {g['wg_endpoint']})")

    total = len(confs) + made
    print(f"[WG-GEN] สร้างเพิ่ม {made} ไฟล์ - ตอนนี้มี {total} ไฟล์ใน {WG_DIR}/")
    if total < want:
        print(f"[WG-GEN] เซิร์ฟเวอร์ในประเทศที่เลือกไม่พอ ({total}/{want}) - เพิ่มรหัสประเทศ เช่น: python wg_gen.py {want} TH SG JP US DE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
