# -*- coding: utf-8 -*-
"""net_interface_rotator.py - หมุน network interface บน PC + classify IP

ใช้:
  python net_interface_rotator.py                    # list interfaces + classify residential/datacenter
  python net_interface_rotator.py --assign           # แจก interface ให้แต่ละจอ (random)
  python net_interface_rotator.py --exit-ip <iface>  # แสดง exit IP ของ interface นั้น

หลักการ:
  - bot machine ของ olivia มี WiFi, Ethernet, USB tether, mobile hotspot
  - แต่ละ interface = IP คนละตัว = LGR เห็นเป็นคนละคน
  - residential interface (True/AIS/DTAC/3BB) = เกมรับ 401
  - datacenter interface (VPN, cloud) = เกมบล็อก 403

ข้อจำกัด:
  - ต้องมี interface residential อยู่จริงบน PC (WiFi บ้าน, USB tether, dongle 4G)
  - Windows: ใช้ netsh route เพื่อบังคับ app ต่อผ่าน interface ไหน (admin)
  - Linux: ip route via <iface>
"""
import subprocess
import json
import re
import sys
import urllib.request
import socket


RESIDENTIAL_ASN = {
    "AIS", "TRUE", "3BB", "DTAC", "TOT", "CAT",  # TH ISP
    "COMCAST", "VERIZON", "AT&T", "CHARTER", "COX",  # US ISP
    "NTT", "KDDI", "SOFTBANK",  # JP ISP
    "SK BROADBAND", "KT", "LG U+",  # KR ISP
}

DATACENTER_ASN = {
    "M247", "DATAPACKET", "MULLVAD", "WINDSCRIBE", "HOSTINGER",
    "DIGITALOCEAN", "AWS", "AMAZON", "GOOGLE CLOUD", "AZURE",
    "OVH", "HETZNER", "LINODE", "VULTR", "CLOUDFLARE",
    "WHISKERGALAXY",
}


def list_interfaces_windows():
    """คืน list ของ (name, ip, status) ของ interfaces บน Windows"""
    out = []
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-NetIPAddress -AddressFamily IPv4 | "
                            "Where-Object {$_.IPAddress -notmatch '^127\\.'} | "
                            "Select-Object InterfaceAlias,IPAddress | ConvertTo-Json"],
                           capture_output=True, text=True, timeout=15,
                           creationflags=0x08000000)
        data = json.loads(r.stdout or "[]")
        if isinstance(data, dict):
            data = [data]
        for row in data:
            name = row.get("InterfaceAlias", "")
            ip = row.get("IPAddress", "")
            if name and ip:
                out.append((name, ip))
    except Exception as e:
        print(f"[!] ดู interface ไม่ได้: {e}")
    return out


def get_exit_ip_via_interface(iface_ip):
    """ยิง HTTP จาก source IP ของ interface -> ดูว่า public IP ขาออกคืออะไร"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((iface_ip, 0))
        sock.settimeout(10)
        sock.connect(("api.ipify.org", 80))
        sock.send(b"GET / HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n")
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        sock.close()
        body = data.split(b"\r\n\r\n", 1)[-1].decode("utf-8", "ignore").strip()
        return body
    except Exception as e:
        return f"error: {e}"


def classify_ip(ip):
    """ยิง ip-api.com ดู ASN + classify residential/datacenter"""
    try:
        r = urllib.request.urlopen(f"http://ip-api.com/json/{ip}?fields=isp,org,as,country,city",
                                   timeout=10)
        data = json.loads(r.read().decode("utf-8", "ignore"))
        isp = (data.get("isp", "") or "").upper()
        org = (data.get("org", "") or "").upper()
        asn = (data.get("as", "") or "").upper()
        combined = f"{isp} {org} {asn}"
        country = data.get("country", "")
        city = data.get("city", "")

        kind = "unknown"
        for dc in DATACENTER_ASN:
            if dc in combined:
                kind = "DATACENTER"
                break
        if kind == "unknown":
            for res in RESIDENTIAL_ASN:
                if res in combined:
                    kind = "RESIDENTIAL"
                    break
        if kind == "unknown":
            # fallback guess: ASN contains "LLC" / "SA" / "GmbH" / "Ltd" = likely datacenter
            if any(x in combined for x in ["TELECOM", "MOBILE", "CELLULAR", "BROADBAND", "FIBER"]):
                kind = "RESIDENTIAL"
            elif any(x in combined for x in ["HOSTING", "DATACENTER", "SERVER", "CLOUD", "VPS"]):
                kind = "DATACENTER"

        return {
            "ip": ip,
            "kind": kind,
            "isp": data.get("isp", "-"),
            "org": data.get("org", "-"),
            "asn": data.get("as", "-"),
            "country": country,
            "city": city,
        }
    except Exception as e:
        return {"ip": ip, "kind": "error", "error": str(e)}


def main():
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        return

    print("=" * 70)
    print(" Network Interface Rotator - ดู interface + classify residential/DC")
    print("=" * 70)

    interfaces = list_interfaces_windows()
    if not interfaces:
        print("[!] ไม่พบ network interface เลย")
        return

    residential = []
    datacenter = []
    unknown = []

    for name, ip in interfaces:
        print(f"\n[iface] {name} (local IP: {ip})")
        print(f"        กำลังตรวจ exit IP + ASN...", flush=True)
        exit_ip = get_exit_ip_via_interface(ip)
        if exit_ip.startswith("error"):
            print(f"        exit IP: - ({exit_ip})")
            unknown.append((name, ip, "-", None))
            continue
        print(f"        exit IP: {exit_ip}")
        info = classify_ip(exit_ip)
        kind = info.get("kind", "unknown")
        tag = {"RESIDENTIAL": "✓ RESIDENTIAL", "DATACENTER": "✗ DATACENTER",
               "error": "? ERROR", "unknown": "? UNKNOWN"}.get(kind, kind)
        print(f"        ASN:     {info.get('asn', '-')}")
        print(f"        ISP:     {info.get('isp', '-')}")
        print(f"        country: {info.get('country', '-')} {info.get('city', '')}")
        print(f"        verdict: {tag}")
        row = (name, ip, exit_ip, info)
        if kind == "RESIDENTIAL":
            residential.append(row)
        elif kind == "DATACENTER":
            datacenter.append(row)
        else:
            unknown.append(row)

    print("\n" + "=" * 70)
    print(" สรุป")
    print("=" * 70)
    print(f"  Residential (เกมรับ 401): {len(residential)}")
    for name, lip, eip, _ in residential:
        print(f"    - {name}: {lip} -> {eip}")
    print(f"  Datacenter (เกมบล็อก 403): {len(datacenter)}")
    for name, lip, eip, _ in datacenter:
        print(f"    - {name}: {lip} -> {eip}")
    print(f"  Unknown: {len(unknown)}")

    if not residential:
        print("\n[!] ไม่มี residential interface เลย")
        print("    ทางออก:")
        print("    1. เสียบมือถือ USB เปิด Mobile Hotspot (4G) -> จะมี interface ใหม่")
        print("    2. ซื้อ 4G USB dongle + SIM AIS/True")
        print("    3. ถ้า bot runs บน remote server = ต้องเช่า server ไทย (บ้างตัว residential)")
    else:
        print(f"\n[OK] มี residential interface {len(residential)} ตัว - ใช้แจก emulator ได้")
        print("     ขั้นตอนถัดไป: บอก olivia จะเขียน patch login.py ให้แต่ละจอ bind")
        print("     ผ่าน interface ไหน (random rotation)")


if __name__ == "__main__":
    main()
