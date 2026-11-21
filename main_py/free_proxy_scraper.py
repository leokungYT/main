# -*- coding: utf-8 -*-
"""free_proxy_scraper.py - หา free proxy ที่ LGR ยอมรับ (residential ASN + ตอบ 401)

หลักการ:
  1) ดึง free proxy lists จาก source สาธารณะ (ProxyScrape, FreeProxy, SpysOne)
  2) ยิง rangers-api.line-apps.com ผ่านแต่ละ proxy (timeout 10s)
  3) code 401 = ใช้ได้ -> เก็บ, classify ASN (residential/datacenter)
  4) output free_proxies_working.txt + wg_outer_proxy.conf ตัวอย่าง

ใช้:
  python free_proxy_scraper.py             # ยิงทุก source หา proxy
  python free_proxy_scraper.py --quick     # แค่ 100 proxy แรก (เร็ว)
  python free_proxy_scraper.py --country TH  # เฉพาะ proxy ประเทศไทย

ไฟล์ output:
  free_proxies_working.txt     - list proxy ที่ LGR ยอมรับ
  free_proxies_residential.txt - subset ที่เป็น residential ASN

คำเตือน:
  - free proxy 99% dead/slow - คาดหวัง hit rate 1-5%
  - ไม่ secure (traffic อาจโดน MITM) ใช้แค่ bot ไม่ใช่ login บัญชีจริง
  - รัน 5-10 นาทีต่อรอบ

Public sources (ไม่ต้อง API key):
  - geonode.com/free-proxy-list
  - proxyscrape.com/free-proxy-list
  - free-proxy-list.net
  - spys.one
"""
import json
import socket
import ssl
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


SOURCES = {
    "geonode": "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc",
    "proxyscrape_http": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all",
    "proxyscrape_socks5": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=5000&country=all",
    "proxylist_download_http": "https://www.proxy-list.download/api/v1/get?type=http",
    "proxylist_download_socks5": "https://www.proxy-list.download/api/v1/get?type=socks5",
}

LGR_API = "https://rangers-api.line-apps.com/v12.3/home"
TEST_TIMEOUT = 10
MAX_CONCURRENT = 50


def fetch_url(url, timeout=15):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")
    except Exception as e:
        return None


def parse_source(name, text):
    """คืน list ของ (ip, port, protocol) จาก response ของแต่ละ source"""
    if not text:
        return []
    out = []
    if name == "geonode":
        try:
            data = json.loads(text)
            for p in data.get("data", []):
                ip = p.get("ip")
                port = p.get("port")
                protos = p.get("protocols", [])
                for proto in protos:
                    if proto in ("http", "socks5"):
                        out.append((ip, int(port), proto))
        except Exception:
            pass
    else:
        # plain text: ip:port per line
        proto = "socks5" if "socks5" in name else "http"
        for line in text.splitlines():
            line = line.strip()
            if ":" not in line:
                continue
            try:
                ip, port = line.split(":", 1)
                out.append((ip.strip(), int(port.strip()), proto))
            except Exception:
                continue
    return out


def test_proxy_http(ip, port, proto):
    """ยิง LGR_API ผ่าน proxy - คืน (ok, code, exit_ip)"""
    try:
        if proto == "http":
            proxy_url = f"http://{ip}:{port}"
            handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        else:
            # socks5: ต้องใช้ pysocks (ลงด้วย pip install pysocks)
            try:
                import socks
                socks.set_default_proxy(socks.SOCKS5, ip, port)
                socket.socket = socks.socksocket
                handler = urllib.request.HTTPHandler()
            except ImportError:
                return False, "no-pysocks", None
        opener = urllib.request.build_opener(handler)
        opener.addheaders = [("User-Agent", "Mozilla/5.0")]
        try:
            r = opener.open(LGR_API, timeout=TEST_TIMEOUT)
            return True, r.getcode(), ip
        except urllib.error.HTTPError as e:
            # 401 = ใช้ได้ (แค่ไม่ login)
            return True, e.code, ip
    except Exception as e:
        return False, str(e)[:40], None


def classify_asn(ip):
    """ยิง ip-api.com ดู ASN + verdict"""
    try:
        r = urllib.request.urlopen(f"http://ip-api.com/json/{ip}?fields=isp,org,as,country",
                                   timeout=8)
        d = json.loads(r.read())
        combined = f"{d.get('isp', '')} {d.get('org', '')} {d.get('as', '')}".upper()
        datacenter = any(dc in combined for dc in [
            "M247", "DATAPACKET", "MULLVAD", "WINDSCRIBE", "DIGITALOCEAN",
            "AWS", "AMAZON", "GOOGLE CLOUD", "AZURE", "OVH", "HETZNER",
            "LINODE", "VULTR", "CLOUDFLARE", "HOSTING", "DATACENTER", "VPS"
        ])
        residential = any(res in combined for res in [
            "COMCAST", "VERIZON", "NTT", "AIS", "TRUE", "3BB", "DTAC",
            "KT", "SK BROADBAND", "LG U+", "SOFTBANK", "KDDI",
            "BROADBAND", "FIBER", "TELECOM", "MOBILE"
        ])
        if datacenter and not residential:
            kind = "DATACENTER"
        elif residential and not datacenter:
            kind = "RESIDENTIAL"
        else:
            kind = "UNKNOWN"
        return {
            "kind": kind,
            "isp": d.get("isp", "-")[:40],
            "country": d.get("country", "-"),
        }
    except Exception:
        return {"kind": "error", "isp": "-", "country": "-"}


def main():
    args = sys.argv[1:]
    quick = "--quick" in args
    country_filter = None
    if "--country" in args:
        country_filter = args[args.index("--country") + 1].upper()

    print("=" * 70)
    print(" Free Proxy Scraper - หา proxy ที่ LGR รับ (residential)")
    print("=" * 70)

    # 1. Fetch sources
    all_proxies = []
    for name, url in SOURCES.items():
        print(f"[fetch] {name}...", end=" ", flush=True)
        text = fetch_url(url, timeout=20)
        proxies = parse_source(name, text) if text else []
        all_proxies.extend(proxies)
        print(f"{len(proxies)} proxies")

    # dedupe
    seen = set()
    unique = []
    for p in all_proxies:
        k = (p[0], p[1])
        if k not in seen:
            seen.add(k)
            unique.append(p)
    print(f"\n[total] {len(unique)} unique proxies")

    if quick:
        unique = unique[:100]
        print(f"[quick] limit to {len(unique)}")

    # 2. Test against LGR_API in parallel
    print(f"\n[test] ยิง LGR_API ผ่าน proxy (timeout {TEST_TIMEOUT}s, {MAX_CONCURRENT} parallel)...")
    print(f"[test] คาดเสร็จใน {len(unique) * TEST_TIMEOUT // MAX_CONCURRENT}s")

    working = []
    done = 0
    lock = threading.Lock()

    def one(proxy):
        nonlocal done
        ip, port, proto = proxy
        ok, code, exit_ip = test_proxy_http(ip, port, proto)
        with lock:
            done += 1
            if done % 20 == 0:
                print(f"  {done}/{len(unique)} ตรวจแล้ว, working={len(working)}", flush=True)
        if ok and code in (401, 200, 204):
            return (ip, port, proto, code, exit_ip)
        return None

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as ex:
        for result in as_completed([ex.submit(one, p) for p in unique]):
            r = result.result()
            if r:
                working.append(r)

    print(f"\n[result] working proxies (LGR รับ): {len(working)}")

    # 3. Classify by ASN - อัพเดท working ให้มี info dict
    residential = []
    datacenter = []
    unknown = []
    classified = []   # (ip, port, proto, code, info_dict)

    if working:
        print("\n[classify] เช็ค ASN แต่ละ proxy...")
        for i, (ip, port, proto, code, exit_ip) in enumerate(working, 1):
            info = classify_asn(exit_ip or ip)
            # country filter: ข้ามจากการนับ residential/datacenter แต่ยังเก็บใน classified
            matches_country = (not country_filter) or info.get("country", "").upper() == country_filter.upper()
            row = (ip, port, proto, code, info)
            classified.append(row)
            kind = info.get("kind", "unknown")
            tag = {"RESIDENTIAL": "✓ RES", "DATACENTER": "✗ DC", "UNKNOWN": "? UNK",
                   "error": "? ERR"}.get(kind, kind)
            print(f"  [{i}/{len(working)}] {proto}://{ip}:{port} ({info.get('country', '-')}) {tag} - {info.get('isp', '-')}")
            if matches_country:
                if kind == "RESIDENTIAL":
                    residential.append(row)
                elif kind == "DATACENTER":
                    datacenter.append(row)
                else:
                    unknown.append(row)

    # 4. Output files - ใช้ classified ที่มี info dict ครบ
    with open("free_proxies_working.txt", "w", encoding="utf-8") as f:
        f.write(f"# Found {len(classified)} working proxies (LGR api accepts, code 401/200/204)\n")
        f.write(f"# Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for ip, port, proto, code, info in classified:
            isp = info.get("isp", "-") if isinstance(info, dict) else "-"
            country = info.get("country", "-") if isinstance(info, dict) else "-"
            kind = info.get("kind", "-") if isinstance(info, dict) else "-"
            f.write(f"{proto}://{ip}:{port}  # code={code} isp={isp} country={country} kind={kind}\n")

    with open("free_proxies_residential.txt", "w", encoding="utf-8") as f:
        f.write(f"# Residential + non-datacenter proxies ({len(residential) + len(unknown)} proxies)\n")
        f.write(f"# Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        # รวม residential + unknown (ไม่ใช่ datacenter) = usable pool
        for ip, port, proto, code, info in residential + unknown:
            isp = info.get("isp", "-") if isinstance(info, dict) else "-"
            country = info.get("country", "-") if isinstance(info, dict) else "-"
            kind = info.get("kind", "-") if isinstance(info, dict) else "-"
            f.write(f"{proto}://{ip}:{port}  # isp={isp} country={country} kind={kind}\n")

    print("\n" + "=" * 70)
    print(" สรุป")
    print("=" * 70)
    print(f"  Scanned: {len(unique)} proxies")
    print(f"  Working (LGR รับ): {len(working)}")
    print(f"    - Residential: {len(residential)}")
    print(f"    - Datacenter:  {len(datacenter)}")
    print(f"    - Unknown:     {len(unknown)}")
    print(f"\n  Files:")
    print(f"    - free_proxies_working.txt       ({len(working)} lines)")
    print(f"    - free_proxies_residential.txt   ({len(residential)} lines)")

    usable = len(residential) + len(unknown)
    if usable > 0:
        print(f"\n[OK] เจอ proxy ใช้ได้ (ไม่ใช่ datacenter) {usable} ตัว:")
        print(f"     - Residential ชัดเจน: {len(residential)}")
        print(f"     - Unknown ASN (น่าจะไม่โดนบล็อก): {len(unknown)}")
        print(f"     ลองเอา proxy จาก free_proxies_residential.txt ไปใช้ดู")
    else:
        print(f"\n[!] ไม่เจอ residential/unknown proxy เลย")
        print(f"    ทางเลือก: 1) รันอีกครั้ง (รายการเปลี่ยน), 2) ซื้อ IPRoyal 1GB $1.56, 3) SIM 4G")


if __name__ == "__main__":
    main()
