"""wg_gen_mullvad.py - gen WireGuard conf files สำหรับ Mullvad

วิธีใช้:
  python wg_gen_mullvad.py
  python wg_gen_mullvad.py --country jp --per-key 5 --out wg/ip-mullvad-1

Input: wg/ip-mullvad-1/keys.txt (1 private key ต่อ 1 บรรทัด)
Output: conf files ใน wg/ip-mullvad-1/

หมายเหตุ Address field: ต้องเป็น IP ที่ Mullvad assign ให้ pubkey นั้น
ถ้าไม่รู้ -> ใช้ placeholder, tunnel ขึ้นได้แต่ packet อาจตก (ต้องแก้ Address เอง)
"""
import argparse, base64, json, os, sys, time
from urllib.request import urlopen

# Windows: reconfigure stdout to utf-8 (Thai prints break cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization
except ImportError:
    print("ERROR: ต้อง pip install cryptography")
    sys.exit(1)

MULLVAD_API = "https://api.mullvad.net/public/relays/wireguard/v2/"


def derive_pubkey(priv_b64):
    priv_bytes = base64.b64decode(priv_b64)
    priv = X25519PrivateKey.from_private_bytes(priv_bytes)
    pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(pub).decode()


def fetch_relays(country_filter=None, retries=3):
    for i in range(retries):
        try:
            with urlopen(MULLVAD_API, timeout=15) as r:
                data = json.load(r)
            relays = []
            for relay in data.get("wireguard", {}).get("relays", []):
                if not relay.get("active", True):
                    continue
                loc = relay.get("location", "")
                if country_filter and not loc.startswith(f"{country_filter}-"):
                    continue
                relays.append(relay)
            return relays
        except Exception as e:
            print(f"[WG-MULLVAD] fetch relays fail ({e}) - retry {i+1}/{retries}")
            time.sleep(3)
    return []


def load_keys(keys_path):
    if not os.path.exists(keys_path):
        return []
    keys = []
    with open(keys_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            keys.append(line)
    return keys


def load_addresses(addrs_path):
    """อ่าน addresses.txt - format: <pubkey>=<address>  (ต่อบรรทัด)
    คืน dict {pubkey: address_cidr} (ว่าง = ไม่มีไฟล์/ไม่ตั้ง)"""
    if not os.path.exists(addrs_path):
        return {}
    out = {}
    with open(addrs_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # pubkey base64 มี "=" padding -> split แค่ "=" แรกหลัง address เป็น CIDR
            # ใช้ rsplit จากขวา: "pubkey==address" -> ["pubkey=", "address"]
            if "=" not in line:
                continue
            # หา index ของ "=" ที่ตามด้วย IP (ตัวเลขหรือ "fc")
            idx = -1
            for i in range(len(line) - 1):
                if line[i] == "=" and (line[i+1].isdigit() or line[i+1:i+3].lower() == "fc"):
                    idx = i
                    break
            if idx < 0:
                continue
            pub = line[:idx]  # pubkey (รวม "=" padding ของตัวเอง, ไม่รวม separator)
            addr = line[idx + 1:].strip()
            out[pub] = addr
    return out


def gen_confs(keys, relays, out_dir, per_key=5, base_address_octet=2, addresses=None):
    """gen conf: each key x (per_key) relays.
    ถ้ามี addresses[pubkey] -> ใช้ Address จริง; ไม่งั้นใช้ placeholder 10.64.0.{octet}"""
    os.makedirs(out_dir, exist_ok=True)
    addresses = addresses or {}
    made = 0
    for ki, priv in enumerate(keys):
        try:
            pub = derive_pubkey(priv)
        except Exception as e:
            print(f"[WG-MULLVAD] key #{ki+1} broken: {e}")
            continue
        real_addr = addresses.get(pub)
        addr = real_addr or f"10.64.0.{base_address_octet + ki}/32"
        if not real_addr:
            print(f"[WG-MULLVAD] warn: key #{ki+1} (pub={pub[:16]}...) ไม่มีใน addresses.txt - ใช้ placeholder {addr}")
        for ri, relay in enumerate(relays[:per_key]):
            conf = (
                "[Interface]\n"
                f"# Mullvad key #{ki+1} pub={pub}\n"
                f"PrivateKey = {priv}\n"
                f"Address = {addr}\n"
                "DNS = 10.64.0.1\n"
                "\n"
                "[Peer]\n"
                f"PublicKey = {relay['public_key']}\n"
                "AllowedIPs = 0.0.0.0/0\n"
                f"Endpoint = {relay['ipv4_addr_in']}:51820\n"
                f"# {relay['hostname']} ({relay.get('location','')})\n"
            )
            fname = f"Mullvad-key{ki+1}-{relay['hostname']}.conf"
            path = os.path.join(out_dir, fname)
            with open(path, "w", encoding="utf-8") as f:
                f.write(conf)
            made += 1
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="jp", help="country code (jp, sg, us, ...)")
    ap.add_argument("--per-key", type=int, default=5, help="จำนวน relay ต่อ key")
    ap.add_argument("--out", default="wg/ip-mullvad-1", help="โฟลเดอร์ปลายทาง")
    ap.add_argument("--keys", default=None, help="path ไฟล์ keys.txt (default: <out>/keys.txt)")
    ap.add_argument("--force", action="store_true", help="gen ทับไฟล์เดิม")
    args = ap.parse_args()

    keys_path = args.keys or os.path.join(args.out, "keys.txt")
    keys = load_keys(keys_path)
    if not keys:
        print(f"[WG-MULLVAD] ไม่พบ key ที่ {keys_path} - หยุด")
        print("ใส่ private key 1 ตัวต่อ 1 บรรทัดในไฟล์นี้")
        sys.exit(1)
    print(f"[WG-MULLVAD] โหลด {len(keys)} key จาก {keys_path}")

    # skip ถ้าโฟลเดอร์มี conf อยู่แล้ว (ไม่ --force)
    existing = [f for f in os.listdir(args.out) if f.endswith(".conf")] if os.path.isdir(args.out) else []
    if existing and not args.force:
        print(f"[WG-MULLVAD] มี {len(existing)} conf อยู่แล้วใน {args.out} - skip (ใช้ --force เพื่อ gen ทับ)")
        return

    relays = fetch_relays(country_filter=args.country)
    if not relays:
        print(f"[WG-MULLVAD] ไม่พบ relay ประเทศ {args.country} - หยุด")
        sys.exit(2)
    print(f"[WG-MULLVAD] โหลด {len(relays)} relay ประเทศ {args.country}")

    addrs_path = os.path.join(args.out, "addresses.txt")
    addrs = load_addresses(addrs_path)
    if addrs:
        print(f"[WG-MULLVAD] โหลด {len(addrs)} address จาก {addrs_path}")
    made = gen_confs(keys, relays, args.out, per_key=args.per_key, addresses=addrs)
    print(f"[WG-MULLVAD] gen {made} conf files ใน {args.out}")


if __name__ == "__main__":
    main()
