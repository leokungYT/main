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
    want = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 30
    countries = [c.upper() for c in sys.argv[2:]] or None
    return generate(want, countries)


def generate(want, countries=None, wg_dir=None):
    """ให้มีไฟล์ใน wg/ อย่างน้อย want ไฟล์ - คืน 0 = สำเร็จ/ครบแล้ว, 1 = สร้างไม่ได้"""
    global WG_DIR
    if wg_dir:
        WG_DIR = wg_dir
    countries = countries or DEFAULT_COUNTRIES

    confs = sorted(f for f in os.listdir(WG_DIR) if f.lower().endswith(".conf")) if os.path.isdir(WG_DIR) else []
    if not confs:
        print(f"[WG-GEN] ไม่มีไฟล์ .conf ใน {WG_DIR}/ เลย - โหลดจากเว็บ Windscribe มา 1 ไฟล์ก่อน (ใช้เป็น Key Pair)")
        return 1
    have = [read_conf(os.path.join(WG_DIR, f)) for f in confs]
    tpl = have[0]
    for k in ("PrivateKey", "Address", "DNS", "PresharedKey"):
        if not tpl.get(k):
            print(f"[WG-GEN] ไฟล์ต้นแบบ {confs[0]} ไม่มี {k} - ใช้ไฟล์จากหน้า Config Generator ของ Windscribe")
            return 1
    print(f"[WG-GEN] ใช้ Key Pair จาก {confs[0]} | มีอยู่แล้ว {len(confs)} ไฟล์ ต้องการ {want}")
    if len(confs) >= want:
        print("[WG-GEN] ครบแล้ว ไม่ต้องสร้างเพิ่ม")
        return 0

    print("[WG-GEN] โหลดรายชื่อเซิร์ฟเวอร์ Windscribe...")
    req = urllib.request.Request(SERVERLIST_URL, headers={"User-Agent": "Mozilla/5.0"})
    data = json.load(urllib.request.urlopen(req, timeout=30))["data"]

    # เซิร์ฟเวอร์ที่ใช้อยู่แล้ว (กุญแจไหนก็ตาม) ไม่ซ้ำ จะได้ IP ไม่ซ้ำด้วย
    used = {kv.get("PublicKey") for kv in have}
    order = {c: i for i, c in enumerate(countries)}
    groups = []
    for loc in data:
        cc = loc.get("country_code", "")
        if cc not in order or not loc.get("status", 1):
            continue
        for g in loc.get("groups") or []:
            if not g.get("wg_pubkey") or not g.get("wg_endpoint") or g["wg_pubkey"] in used:
                continue
            if not g.get("nodes"):
                continue
            groups.append((order[cc], cc, g))
    groups.sort(key=lambda x: x[0])

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
