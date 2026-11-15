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
import glob
import hashlib
import json
import os
import random
import shutil
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


def _safe_tunnel_name(conf_path):
    """ชื่อ tunnel สั้นๆ ไม่เกิน 32 ตัว, deterministic ต่อ path เดิม
    WG for Windows: ^[a-zA-Z0-9_=+.-]{1,32}$ - ชื่อยาวเกิน/มีช่องว่างจะ Error: Tunnel name is not valid"""
    h = hashlib.md5(conf_path.encode("utf-8")).hexdigest()[:8]
    return f"wg-{h}"   # 11 ตัว ปลอดภัยแน่


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
    return [os.path.abspath(f) for f in files]


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
    """print public IP ปัจจุบัน - ยืนยันว่า VPN ต่อแล้ว (best-effort)"""
    try:
        import urllib.request
        with urllib.request.urlopen("https://api.ipify.org", timeout=6) as r:
            ip = r.read().decode("ascii", "ignore").strip()
            print(f"[HOST-WG] public IP = {ip}", flush=True)
    except Exception:
        pass


def rotate(wg_dir, exclude_current=True):
    """สลับไป tunnel ใหม่ (สุ่มจาก .conf ใน wg_dir ที่ไม่ใช่ตัวปัจจุบัน)
    copy .conf ไปเป็นชื่อสั้น (<32 ตัว) ก่อน install เพราะ WG for Windows จำกัดชื่อ tunnel"""
    cur = _current_tunnel()
    confs = _list_confs(wg_dir)
    if not confs:
        print(f"[HOST-WG] ไม่มีไฟล์ .conf ใน {wg_dir}/ - ข้าม", flush=True)
        return
    choices = confs
    if cur and exclude_current:
        # cur คือชื่อสั้น (wg-xxxxxxxx) - map กลับไปหา source conf ของตัวที่กำลังใช้
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                cur_src = (json.load(f) or {}).get("source") or ""
        except Exception:
            cur_src = ""
        choices = [c for c in confs if c != cur_src] or confs
    pick = random.choice(choices)
    short_name = _safe_tunnel_name(pick)
    label = os.path.splitext(os.path.basename(pick))[0]

    os.makedirs(TUNNEL_DIR, exist_ok=True)
    short_conf = os.path.join(TUNNEL_DIR, f"{short_name}.conf")
    try:
        shutil.copyfile(pick, short_conf)
    except Exception as e:
        print(f"[HOST-WG] copy .conf ล้มเหลว: {e}", flush=True)
        return

    if cur:
        print(f"[HOST-WG] ถอด tunnel เก่า: {cur}", flush=True)
        _uninstall(cur)
        time.sleep(2)
    print(f"[HOST-WG] ต่อ tunnel ใหม่: {label} -> {short_name} ({pick})", flush=True)
    if _install(short_conf):
        _write_state(short_name, short_conf, source=pick, label=label)
        time.sleep(3)
        _show_ip()
    else:
        _write_state(None, None)


def stop_current():
    cur = _current_tunnel()
    if cur:
        print(f"[HOST-WG] ถอด tunnel ปัจจุบัน: {cur}", flush=True)
        _uninstall(cur)
        _write_state(None, None)
    else:
        print("[HOST-WG] ไม่มี tunnel ที่ต่ออยู่", flush=True)


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
    print(f"[HOST-WG] เริ่ม rotator: wg_dir={args.dir} รอบละ {args.min} นาที", flush=True)
    while True:
        try:
            rotate(args.dir)
        except Exception as e:
            print(f"[HOST-WG] rotate พัง: {e}", flush=True)
        if args.once:
            return
        time.sleep(interval)


if __name__ == "__main__":
    main()
