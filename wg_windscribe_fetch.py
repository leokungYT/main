"""wg_windscribe_fetch.py - auto-download fresh WireGuard .conf from Windscribe

Reverse-engineered client for Windscribe's web API. Logs in with username+password,
generates a NEW WG keypair on their server, picks a server from the public
server list, builds a valid .conf and writes it to wg/ip-chan/main-N/keyN.conf.

Run:
  python wg_windscribe_fetch.py                  (reads WINDSCRIBE_USER/PASS env or configmain.json)
  python wg_windscribe_fetch.py <user> <pass>

Outputs:
  wg/ip-chan/main-1/key1.conf
  wg/ip-chan/main-2/key2.conf
  wg/ip-chan/main-3/key3.conf

After success -> run host-wg-reset.bat then host-wg-rotate.bat.

WARNING: Unofficial API. Windscribe can change it / ban the account at any time.
         If a step fails -> fall back to manual at https://windscribe.com/getconfig/wireguard
"""
import json
import os
import sys
import subprocess
import urllib.parse
import urllib.request
import http.cookiejar

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "configmain.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
BASE = "https://windscribe.com"
API = "https://api.windscribe.com"


def _read_cred():
    """อ่าน user/pass จาก env หรือ configmain.json หรือ argv"""
    if len(sys.argv) >= 3:
        return sys.argv[1], sys.argv[2]
    u = os.environ.get("WINDSCRIBE_USER") or ""
    p = os.environ.get("WINDSCRIBE_PASS") or ""
    if not (u and p):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                c = json.load(f)
            u = u or c.get("windscribe_user") or ""
            p = p or c.get("windscribe_pass") or ""
        except Exception:
            pass
    if not (u and p):
        print("[WS] ไม่มี username/password - เซ็ต WINDSCRIBE_USER/PASS หรือตั้ง "
              "windscribe_user/windscribe_pass ใน configmain.json หรือรัน:")
        print("     python wg_windscribe_fetch.py <user> <pass>")
        sys.exit(2)
    return u, p


def _opener():
    cj = http.cookiejar.CookieJar()
    o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    o.addheaders = [("User-Agent", UA), ("Accept", "*/*"),
                    ("Accept-Language", "en-US,en;q=0.9"),
                    ("Origin", BASE), ("Referer", BASE + "/")]
    return o, cj


def _get_csrf(o):
    """GET /users/csrf_token -> {csrf_token, csrf_time}"""
    req = urllib.request.Request(BASE + "/users/csrf_token", method="POST")
    try:
        r = o.open(req, timeout=20)
        d = json.loads(r.read().decode("utf-8", "ignore"))
        if "csrf_token" in d and "csrf_time" in d:
            return d["csrf_token"], d["csrf_time"]
    except Exception as e:
        print(f"[WS] csrf fetch failed: {e}")
    raise RuntimeError("Cannot fetch csrf token (Windscribe may have changed their API)")


def _login(o, user, passwd):
    """POST /users/login"""
    csrf_t, csrf_s = _get_csrf(o)
    body = urllib.parse.urlencode({
        "login": "1",
        "username": user,
        "password": passwd,
        "code": "",   # 2FA ไม่รองรับ
        "csrf_token": csrf_t,
        "csrf_time": csrf_s,
    }).encode("utf-8")
    req = urllib.request.Request(BASE + "/users/login", data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    r = o.open(req, timeout=30)
    data = r.read().decode("utf-8", "ignore")
    try:
        d = json.loads(data)
    except Exception:
        raise RuntimeError(f"Login response not JSON: {data[:200]}")
    if d.get("success") == 1 or d.get("session_auth_hash"):
        print(f"[WS] login OK ({user})")
        return
    raise RuntimeError(f"Login failed: {d}")


def _gen_wg_key(o):
    """POST /users/wg_generate -> {wg_ip, wg_public_key, wg_preshared_key, server_public_key, ...}
    อาจต้องปรับ endpoint ตามเวอร์ชันของ Windscribe"""
    csrf_t, csrf_s = _get_csrf(o)
    body = urllib.parse.urlencode({
        "csrf_token": csrf_t,
        "csrf_time": csrf_s,
    }).encode("utf-8")
    for path in ("/users/wg_generate", "/getconfig/wg_generate", "/api/wgconfigs/newkey"):
        try:
            req = urllib.request.Request(BASE + path, data=body, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            r = o.open(req, timeout=30)
            txt = r.read().decode("utf-8", "ignore")
            d = json.loads(txt)
            if d.get("success") == 1 and (d.get("data") or d.get("wg_ip")):
                return d.get("data") or d
        except Exception as e:
            print(f"[WS] {path} -> {e}")
    raise RuntimeError("wg_generate endpoint not found - Windscribe may have changed API; fall back to manual download")


def _best_server(server_list_path=None):
    """ดึงรายชื่อเซิร์ฟเวอร์จาก assets.windscribe.com แล้วเลือก 3 ตัว (Hong Kong, Singapore, Tokyo)"""
    url = "https://assets.windscribe.com/serverlist/mob-v2/1/0"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = json.load(urllib.request.urlopen(req, timeout=30))["data"]
    picks = []
    want = ["HK", "SG", "JP"]   # ประเทศหลักที่เกม LGR ยอมรับ
    for cc in want:
        for loc in data:
            if loc.get("country_code") != cc:
                continue
            for g in loc.get("groups") or []:
                if g.get("wg_pubkey") and g.get("wg_endpoint"):
                    picks.append((cc, g))
                    break
            if picks and picks[-1][0] == cc:
                break
    return picks


def _write_conf(path, priv_key, address, dns, server_pubkey, preshared, endpoint):
    text = (
        "[Interface]\n"
        f"PrivateKey = {priv_key}\n"
        f"Address = {address}\n"
        f"DNS = {dns}\n"
        "\n[Peer]\n"
        f"PublicKey = {server_pubkey}\n"
        "AllowedIPs = 0.0.0.0/0, ::/0\n"
        f"Endpoint = {endpoint}\n"
        f"PresharedKey = {preshared}\n"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    u, p = _read_cred()
    o, cj = _opener()
    try:
        _login(o, u, p)
        key_info = _gen_wg_key(o)
    except Exception as e:
        print(f"\n[WS] ========== API พัง ==========")
        print(f"[WS] {e}")
        print(f"[WS] Windscribe น่าจะเปลี่ยน API - ลอง manual:")
        print(f"[WS]   1. เข้า https://windscribe.com/getconfig/wireguard")
        print(f"[WS]   2. Login + กด Generate + Download 3 ครั้ง (ประเทศต่างกัน)")
        print(f"[WS]   3. เปลี่ยนชื่อเป็น key1.conf, key2.conf, key3.conf")
        print(f"[WS]   4. วางใน wg/ip-chan/main-1/, main-2/, main-3/ ตามลำดับ")
        print(f"[WS] =============================\n")
        sys.exit(1)

    # key_info ควรมี: wg_ip (Interface Address), server public_key (per server from server list)
    priv = key_info.get("private_key") or key_info.get("wg_private_key")
    pub = key_info.get("public_key") or key_info.get("wg_public_key")
    addr = key_info.get("address") or key_info.get("wg_ip") or "10.14.0.2/32"
    preshared = key_info.get("preshared_key") or key_info.get("wg_preshared_key") or ""
    dns = key_info.get("dns") or "10.255.255.1, 10.255.255.2"
    if not priv:
        print(f"[WS] API ตอบมาแต่ไม่มี private key: {key_info}")
        sys.exit(1)

    servers = _best_server()
    if not servers:
        print(f"[WS] หาเซิร์ฟเวอร์ไม่เจอจาก server list")
        sys.exit(1)

    # ใช้ priv key เดียวกันทั้ง 3 ไฟล์ (Windscribe ยอมให้ 1 pubkey หลาย session) - ต่าง server เท่านั้น
    port = "443"
    for i, (cc, g) in enumerate(servers[:3], start=1):
        name = f"key{i}.conf"
        folder = os.path.join(SCRIPT_DIR, "wg", "ip-chan", f"main-{i}")
        path = os.path.join(folder, name)
        endpoint = f"{g['wg_endpoint']}:{port}"
        _write_conf(path, priv, addr, dns, g["wg_pubkey"], preshared, endpoint)
        print(f"[WS] + {path}  ({cc} {g['wg_endpoint']})")

    print(f"\n[WS] สร้าง keypair ใหม่สำเร็จ - รัน host-wg-reset.bat แล้วเปิด host-wg-rotate.bat ใหม่")


if __name__ == "__main__":
    main()
