"""Host-level WireGuard rotator (Windows).

ใช้แทนที่ per-emulator WireGuard: ตั้ง VPN บน Windows เลย ทุกอีมูฯ ในเครื่องจะ
ออกเน็ตผ่าน IP ของ tunnel ปัจจุบัน แล้วสลับ tunnel ทุก N นาทีอัตโนมัติ
(เพื่อนเจ้าของบอทบอก: เน็ตประเทศนี้ใช้ได้ 10-20 นาที -> หมุนทุก 5-10 นาที)

การใช้งาน:
  1) ติดตั้ง WireGuard for Windows ก่อน (รัน install-host-wg.bat)
  2) ตั้ง config "use_host_vpn": 1 ใน configmain.json
  3) รัน `python host_wg_rotator.py` (หรือ host-wg-rotate.bat) ก่อนเปิดบอท
  4) ปล่อยไว้ทำงานเป็น background ตลอดเวลา - ปิดเมื่อเลิกบอท

หยุด tunnel ปัจจุบัน:
  python host_wg_rotator.py --stop

CLI:
  --once         รันหนึ่งรอบแล้วออก (debug)
  --stop         ถอน tunnel ปัจจุบันแล้วออก (ใช้เมื่อเลิกบอท)
  --dir <path>   โฟลเดอร์ .conf (default: wg)
  --min <n>      นาทีต่อรอบสลับ (default: 7)
"""
import argparse
import atexit
import glob
import hashlib
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time

WG_EXE_CANDIDATES = [
    r"C:\Program Files\WireGuard\wireguard.exe",
    r"C:\Program Files (x86)\WireGuard\wireguard.exe",
]
WG_CLI_CANDIDATES = [
    r"C:\Program Files\WireGuard\wg.exe",
    r"C:\Program Files (x86)\WireGuard\wg.exe",
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, "host_wg_state.json")
TUNNEL_DIR = os.path.join(SCRIPT_DIR, ".host_wg_tunnels")   # ชื่อ tunnel แบบสั้น (WG for Windows จำกัด 32 ตัว)
TRIGGER_FILE = os.path.join(SCRIPT_DIR, ".host_wg_trigger") # บอทเขียนไฟล์นี้ตอน login fail -> rotator สลับทันที

# domain ที่ควรวิ่งผ่าน VPN (split-tunnel) - override ด้วย config host_vpn_split_domains
# AnyDesk / browser / Windows Update ยังใช้เน็ตบ้าน ไม่โดนตัด
DEFAULT_SPLIT_DOMAINS = [
    "rangers-api.line-apps.com",   # API หลักของเกม LINE Rangers (home, gacha, event)
    "game-api.line.me",             # ★ LINE GUEST auth endpoint - ต้องผ่าน VPN ไม่งั้น "Authentication failed"
    "obs.line-apps.com",            # CDN รูปภาพ/asset เกม
    "obs.line-scdn.net",            # CDN LINE (asset/avatar)
    "access.line.me",               # LINE login (บางเคส)
    "api.line.me",                  # LINE core API (profile, friends)
    # เจอ domain เพิ่มตอนบอทเล่น (HTTP 000 / Authentication failed) -> เพิ่มใน configmain.json host_vpn_split_domains
]


def _safe_tunnel_name(conf_path):
    """ชื่อ tunnel สั้นๆ ไม่เกิน 32 ตัว, deterministic ต่อ path เดิม
    WG for Windows: ^[a-zA-Z0-9_=+.-]{1,32}$ - ชื่อยาวเกิน/มีช่องว่างจะ Error: Tunnel name is not valid"""
    h = hashlib.md5(conf_path.encode("utf-8")).hexdigest()[:8]
    return f"wg-{h}"   # 11 ตัว ปลอดภัยแน่


def _resolve_domains(domains):
    """resolve domain → list of IPs (IPv4 + IPv6) - รวบรวมทั้ง A และ AAAA records
    ถ้า resolve บาง domain พัง -> ข้ามเฉพาะตัวนั้น ไม่ถล่มทั้ง rotator"""
    import socket
    ips = set()
    for d in domains:
        d = d.strip()
        if not d:
            continue
        try:
            infos = socket.getaddrinfo(d, None)
            for info in infos:
                ip = info[4][0]
                # IPv4 → /32, IPv6 → /128
                if ":" in ip:
                    ips.add(f"{ip}/128")
                else:
                    ips.add(f"{ip}/32")
        except Exception as e:
            print(f"[HOST-WG] resolve {d} ล้มเหลว: {e}", flush=True)
    return sorted(ips)


def _tune_conf_split(src_conf, dst_conf, allowed_ips):
    """copy src_conf -> dst_conf และแทน AllowedIPs ใน [Peer] ด้วย allowed_ips (split-tunnel)
    - AllowedIPs = 0.0.0.0/0 จะทำให้ ทุก traffic ของ Windows ผ่าน VPN (AnyDesk/Chrome RD ตัด)
    - เปลี่ยนเป็น IP เฉพาะเกม = เน็ตอื่นวิ่งตรง ไม่โดนตัด"""
    with open(src_conf, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    out = []
    in_peer = False
    replaced = False
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            in_peer = (s.lower() == "[peer]")
            out.append(line)
            continue
        if in_peer and s.lower().startswith("allowedips"):
            if not replaced:
                out.append(f"AllowedIPs = {', '.join(allowed_ips)}\n")
                replaced = True
            # skip ทั้งบรรทัด AllowedIPs เดิม (ไม่ append)
            continue
        out.append(line)
    if not replaced:
        # ไม่เจอ AllowedIPs ใน [Peer] - เพิ่มท้ายไฟล์
        out.append(f"\nAllowedIPs = {', '.join(allowed_ips)}\n")
    with open(dst_conf, "w", encoding="utf-8") as f:
        f.writelines(out)


def _first_existing(paths):
    for p in paths:
        if os.path.isfile(p):
            return p
    return None


def _wg_exe():
    exe = _first_existing(WG_EXE_CANDIDATES)
    if not exe:
        print("[HOST-WG] ไม่พบ wireguard.exe - รัน install-host-wg.bat ก่อน", flush=True)
        sys.exit(2)
    return exe


def _wg_cli():
    return _first_existing(WG_CLI_CANDIDATES)   # อาจไม่มีก็ได้ - ใช้ /dumpinterfacelist แทน


def _load_cfg():
    path = os.path.join(SCRIPT_DIR, "configmain.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _list_confs(wg_dir):
    base = wg_dir if os.path.isabs(wg_dir) else os.path.join(SCRIPT_DIR, wg_dir)
    files = sorted(glob.glob(os.path.join(base, "**", "*.conf"), recursive=True))
    # กรองออก: path ที่มี substring ใน host_vpn_exclude_paths (default กัน Mullvad ที่ key หมดอายุบ่อย)
    cfg = _load_cfg()
    excludes = cfg.get("host_vpn_exclude_paths") or ["ip-mullvad", "mullvad", "Mullvad"]
    out = []
    for f in files:
        fa = os.path.abspath(f)
        norm = fa.replace("\\", "/").lower()
        if any(e.lower() in norm for e in excludes):
            continue
        out.append(fa)
    return out


def _current_tunnel():
    cli = _wg_cli()
    if cli:
        try:
            r = subprocess.run([cli, "show", "interfaces"], capture_output=True, text=True, timeout=10)
            name = (r.stdout or "").strip().splitlines()
            return name[0].strip() if name and name[0].strip() else None
        except Exception:
            pass
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return (json.load(f) or {}).get("tunnel") or None
    except Exception:
        return None


def _write_state(tunnel, conf, source=None, label=None):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "tunnel": tunnel,          # ชื่อ tunnel ที่ WG for Windows รู้จัก (wg-xxxxxxxx)
                "conf": conf,              # ไฟล์ .conf ที่ใช้ install (TUNNEL_DIR/wg-xxxxxxxx.conf)
                "source": source or conf,  # ไฟล์ .conf ต้นฉบับใน wg/ (ใช้ exclude ตอน rotate)
                "label": label,            # ชื่ออ่านง่าย (Windscribe-Singapore-...)
                "ts": int(time.time()),
            }, f)
    except Exception:
        pass


def _uninstall(name):
    if not name:
        return
    exe = _wg_exe()
    try:
        subprocess.run([exe, "/uninstalltunnelservice", name],
                       capture_output=True, timeout=30)
    except Exception as e:
        print(f"[HOST-WG] ถอด tunnel {name} พัง: {e}", flush=True)


def _install(conf_path):
    exe = _wg_exe()
    try:
        r = subprocess.run([exe, "/installtunnelservice", conf_path],
                           capture_output=True, text=True, timeout=45)
        if r.returncode != 0:
            print(f"[HOST-WG] ติดตั้ง tunnel พัง (rc={r.returncode}): {(r.stdout or '') + (r.stderr or '')}", flush=True)
            return False
        return True
    except Exception as e:
        print(f"[HOST-WG] ติดตั้ง tunnel พัง: {e}", flush=True)
        return False


def _show_ip():
    """print public IP (ของ api.ipify.org) - เป็นแค่ sanity check
    split-tunnel mode: ipify ไม่อยู่ใน AllowedIPs -> IP ที่เห็นยัง = IP บ้าน ไม่ใช่ IP VPN
                       แต่ traffic ไปเซิร์ฟเกม (rangers-api.line-apps.com) วิ่งผ่าน VPN จริง
    full-tunnel mode:  IP ที่เห็น = IP VPN"""
    try:
        import urllib.request
        with urllib.request.urlopen("https://api.ipify.org", timeout=6) as r:
            ip = r.read().decode("ascii", "ignore").strip()
            print(f"[HOST-WG] public IP (ipify) = {ip}", flush=True)
            print(f"[HOST-WG]   split-tunnel: IP นี้คือเน็ตบ้าน - เซิร์ฟเกมจะเห็น IP VPN ต่างหาก", flush=True)
            return ip
    except Exception:
        return None


def _tunnel_handshake_ok(name, wait_sec=20):
    """รอ handshake จริงของ tunnel (wg show <name> latest-handshakes != 0)
    install service สำเร็จ != tunnel ต่อสำเร็จ - WG for Windows ต้อง handshake กับ peer ก่อน"""
    cli = _wg_cli()
    if not cli:
        time.sleep(5)
        return None   # ไม่มี wg.exe - เช็คไม่ได้
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        try:
            r = subprocess.run([cli, "show", name, "latest-handshakes"],
                               capture_output=True, text=True, timeout=5)
            out = (r.stdout or "").strip()
            # format: "<pubkey>\t<unix ts>" - ts != 0 = handshake สำเร็จ
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[-1].isdigit() and int(parts[-1]) > 0:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


_BAD_CONFS = {}   # {conf_path: (last_fail_ts, fail_count)} - ไฟล์ที่ handshake ไม่ผ่าน เว้นสักพักค่อยลองใหม่


def _conf_is_bad(conf):
    """ไฟล์นี้เพิ่ง fail ภายใน cool-off ไหม (เริ่มที่ 5 นาที x fail_count, max 60 นาที)"""
    rec = _BAD_CONFS.get(conf)
    if not rec:
        return False
    last, n = rec
    cooloff = min(60 * 60, 5 * 60 * n)   # 5 นาที, 10, 15, ..., สูงสุด 60 นาที
    return (time.time() - last) < cooloff


def _mark_conf_bad(conf):
    last, n = _BAD_CONFS.get(conf, (0, 0))
    _BAD_CONFS[conf] = (time.time(), n + 1)


def _mark_conf_good(conf):
    _BAD_CONFS.pop(conf, None)


def rotate(wg_dir, exclude_current=True):
    """สลับไป tunnel ใหม่ (สุ่มจาก .conf ใน wg_dir ที่ไม่ใช่ตัวปัจจุบัน)
    copy .conf ไปเป็นชื่อสั้น (<32 ตัว) ก่อน install เพราะ WG for Windows จำกัดชื่อ tunnel
    ถ้า handshake ไม่ผ่าน -> ลองไฟล์อื่นต่อ (สูงสุด 5 ไฟล์) + blacklist ไฟล์เสียไว้ชั่วคราว"""
    cur = _current_tunnel()
    all_confs = _list_confs(wg_dir)
    if not all_confs:
        print(f"[HOST-WG] ไม่มีไฟล์ .conf ใน {wg_dir}/ - ข้าม", flush=True)
        return
    # filter: ตัดตัวปัจจุบัน + ตัดไฟล์ที่เพิ่ง handshake พัง (cool-off)
    cur_src = ""
    if cur and exclude_current:
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                cur_src = (json.load(f) or {}).get("source") or ""
        except Exception:
            pass
    good = [c for c in all_confs if c != cur_src and not _conf_is_bad(c)]
    if not good:
        # ไฟล์ดีหมด cool-off -> ลองไฟล์เสียเก่าสุด (อาจกลับมาใช้ได้แล้ว)
        good = [c for c in all_confs if c != cur_src] or all_confs
        if _BAD_CONFS:
            print(f"[HOST-WG] ไฟล์ดีหมด - ลองกลุ่มที่เคยเสีย ({len(_BAD_CONFS)} ไฟล์)", flush=True)

    # ลองไฟล์ 1-5 ไฟล์ จนกว่า handshake จะผ่าน (ถ้า install แรกพัง อย่าปล่อยให้ไม่มี tunnel)
    max_tries = min(5, len(good))
    pick = None
    for attempt in range(max_tries):
        pick = random.choice(good)
        good = [c for c in good if c != pick]   # กัน loop สุ่มซ้ำตัวเดิม
        if attempt > 0:
            print(f"[HOST-WG] ลองไฟล์ที่ {attempt + 1}/{max_tries}...", flush=True)
        if _rotate_once(pick, cur):
            _mark_conf_good(pick)
            return
        _mark_conf_bad(pick)
        print(f"[HOST-WG] ไฟล์นี้ handshake พัง -> blacklist ชั่วคราว", flush=True)
    print(f"[HOST-WG] ลอง {max_tries} ไฟล์ยังไม่ผ่าน - ไม่มี VPN รอรอบถัดไป", flush=True)


def _rotate_once(pick, cur):
    """ติด tunnel 1 ไฟล์ + รอ handshake. คืน True ถ้าผ่าน, False ถ้าพัง (rollback แล้ว)"""
    short_name = _safe_tunnel_name(pick)
    label = os.path.splitext(os.path.basename(pick))[0]
    os.makedirs(TUNNEL_DIR, exist_ok=True)
    short_conf = os.path.join(TUNNEL_DIR, f"{short_name}.conf")
    cfg = _load_cfg()
    domains = cfg.get("host_vpn_split_domains") or DEFAULT_SPLIT_DOMAINS
    full_tunnel = int(cfg.get("host_vpn_full_tunnel", 0) or 0)
    try:
        if full_tunnel:
            shutil.copyfile(pick, short_conf)
            print(f"[HOST-WG] full-tunnel mode (host_vpn_full_tunnel=1) - traffic ทั้งหมดผ่าน VPN", flush=True)
        else:
            allowed_ips = _resolve_domains(domains)
            if not allowed_ips:
                print(f"[HOST-WG] resolve domain ไม่ได้เลย -> fallback full-tunnel", flush=True)
                shutil.copyfile(pick, short_conf)
            else:
                _tune_conf_split(pick, short_conf, allowed_ips)
                print(f"[HOST-WG] split-tunnel: route {len(allowed_ips)} IP ของเกมผ่าน VPN "
                      f"(เน็ตอื่นวิ่งตรง - AnyDesk/Chrome RD ไม่ตัด)", flush=True)
    except Exception as e:
        print(f"[HOST-WG] เตรียมไฟล์ tunnel ล้มเหลว: {e}", flush=True)
        return False

    print(f"[HOST-WG] ติด tunnel ใหม่ก่อน (seamless): {label} -> {short_name}", flush=True)
    if not _install(short_conf):
        print(f"[HOST-WG] ติด tunnel ใหม่พัง - คง tunnel เก่า ({cur}) ไว้", flush=True)
        return False
    ok = _tunnel_handshake_ok(short_name, wait_sec=15)
    if ok is False:
        print(f"[HOST-WG] tunnel ใหม่ handshake ไม่ผ่านใน 15 วิ - rollback", flush=True)
        _uninstall(short_name)
        return False
    if cur and cur != short_name:
        print(f"[HOST-WG] handshake OK - ถอด tunnel เก่า: {cur}", flush=True)
        _uninstall(cur)
    _write_state(short_name, short_conf, source=pick, label=label)
    time.sleep(1)
    _show_ip()
    return True


def _list_all_wg_services():
    """list ชื่อ tunnel ของทุก WireGuard service ที่ติดอยู่ในเครื่อง (ไม่ใช่แค่ตัวที่เราติดตั้ง)"""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Service -Name 'WireGuardTunnel$*' -ErrorAction SilentlyContinue | "
             "ForEach-Object { $_.Name -replace '^WireGuardTunnel\\$','' }"],
            capture_output=True, text=True, timeout=10)
        return [n.strip() for n in (r.stdout or "").splitlines() if n.strip()]
    except Exception:
        return []


def stop_current():
    """ถอด tunnel ที่ต่ออยู่ - uninstall ทุก WireGuard service ไม่ใช่แค่ที่ rotator ติดตั้ง
    (ครอบคลุม tunnel ที่ user ติดจาก GUI เองด้วย - จะได้ปิดคราวเดียวจบ)"""
    all_svcs = _list_all_wg_services()
    if not all_svcs:
        cur = _current_tunnel()
        if cur:
            print(f"[HOST-WG] ถอด tunnel ปัจจุบัน: {cur}", flush=True)
            _uninstall(cur)
        else:
            print("[HOST-WG] ไม่มี tunnel ที่ต่ออยู่", flush=True)
    else:
        print(f"[HOST-WG] พบ {len(all_svcs)} tunnel - ถอดทั้งหมด", flush=True)
        for n in all_svcs:
            print(f"[HOST-WG] ถอด: {n}", flush=True)
            _uninstall(n)
            time.sleep(1)
    _write_state(None, None)


def main():
    cfg = _load_cfg()
    ap = argparse.ArgumentParser(description="Host WireGuard rotator")
    ap.add_argument("--dir", default=cfg.get("wg_dir", "wg"), help="โฟลเดอร์ .conf (default: wg จาก configmain.json)")
    ap.add_argument("--min", type=float, default=float(cfg.get("host_vpn_rotate_min", 7) or 7), help="นาทีต่อรอบสลับ (default: 7)")
    ap.add_argument("--once", action="store_true", help="สลับหนึ่งรอบแล้วออก")
    ap.add_argument("--stop", action="store_true", help="ถอด tunnel ปัจจุบันแล้วออก")
    args = ap.parse_args()

    if args.stop:
        stop_current()
        return

    interval = max(60.0, args.min * 60.0)   # ขั้นต่ำ 1 นาที กัน config ผิด
    cfg = _load_cfg()
    trigger_on = int(cfg.get("host_vpn_trigger_rotate", 1) or 0)
    trigger_gap = max(30.0, float(cfg.get("host_vpn_trigger_min_gap_sec", 120) or 120))
    print(f"[HOST-WG] เริ่ม rotator: wg_dir={args.dir} รอบละ {args.min} นาที "
          f"(trigger-rotate={'on' if trigger_on else 'off'}, min gap {trigger_gap:.0f}s)", flush=True)
    try:
        if os.path.exists(TRIGGER_FILE):
            os.remove(TRIGGER_FILE)
    except Exception:
        pass

    # cleanup: Ctrl+C / Ctrl+Break / ปิดจาก Task Manager -> ถอด tunnel ก่อนออก
    # เพราะ /installtunnelservice ติดตั้งเป็น Windows service persistent - ไม่ถอดเอง = ค้างจน restart
    _cleaning = {"done": False}
    def _cleanup(*_a):
        if _cleaning["done"]:
            return
        _cleaning["done"] = True
        print("\n[HOST-WG] กำลัง cleanup - ถอด tunnel ก่อนออก...", flush=True)
        try:
            stop_current()
        except Exception as e:
            print(f"[HOST-WG] cleanup พัง: {e}", flush=True)
    atexit.register(_cleanup)
    try:
        signal.signal(signal.SIGINT, lambda *a: (_cleanup(), sys.exit(0)))
        signal.signal(signal.SIGTERM, lambda *a: (_cleanup(), sys.exit(0)))
        if hasattr(signal, "SIGBREAK"):   # Windows เท่านั้น (Ctrl+Break / close window)
            signal.signal(signal.SIGBREAK, lambda *a: (_cleanup(), sys.exit(0)))
    except Exception:
        pass

    last_rotate = 0.0
    while True:
        try:
            rotate(args.dir)
            last_rotate = time.time()
        except Exception as e:
            print(f"[HOST-WG] rotate พัง: {e}", flush=True)
        if args.once:
            return
        # แทนที่จะ sleep ยาว - นอน 5 วิ x N ครั้ง เพื่อเช็ค trigger file ได้บ่อยๆ
        slept = 0.0
        while slept < interval:
            time.sleep(5)
            slept += 5
            if not trigger_on:
                continue
            try:
                if os.path.exists(TRIGGER_FILE):
                    gap = time.time() - last_rotate
                    if gap < trigger_gap:
                        print(f"[HOST-WG] trigger file พบ แต่เพิ่งสลับไป {gap:.0f}s (ต้องรอ {trigger_gap:.0f}s) - ข้าม", flush=True)
                        try: os.remove(TRIGGER_FILE)
                        except Exception: pass
                        continue
                    try:
                        with open(TRIGGER_FILE, "r", encoding="utf-8", errors="replace") as f:
                            reason = (f.read() or "").strip()[:200]
                    except Exception:
                        reason = ""
                    try: os.remove(TRIGGER_FILE)
                    except Exception: pass
                    print(f"[HOST-WG] ★ trigger-rotate: บอทขอสลับ IP ({reason or 'ไม่ระบุสาเหตุ'})", flush=True)
                    break   # ออกจาก inner sleep -> ไป rotate รอบใหม่
            except Exception:
                pass


if __name__ == "__main__":
    main()
