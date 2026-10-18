#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
wg_reset.py — "Reset IP" ของ wg-push-file (push-file.py) แบบไม่มี GUI ให้สคริปต์อื่นเรียกใช้

ต่างจากระบบ WG ใน login.py:
  1) ล้าง MITM ที่ค้าง (hosts ซ้อนหลายชั้น / iptables / adb reverse) ก่อน
  2) VPN เฉพาะแอปเกม (IncludedApplications = com.linecorp.LGRGS) + PersistentKeepalive
  3) ทดสอบผ่าน tunnel จริง (ip rule ให้ root ออก tun0) : 401 = ใช้ได้ / 000,403,429 = บล็อก
  4) เลือกเซิร์ฟเวอร์ใกล้ไทยก่อน (ping ต่ำ ไม่ขึ้น Unstable network)

ใช้:  import wg_reset ; wg_reset.reset_ip(dev, log=print)  -> (ok, ข้อความ)
      python wg_reset.py 127.0.0.1:5563
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ADB = os.path.join(ROOT, "adb", "adb.exe")
PKG = "com.wireguard.android"
TUNNEL = "lgr"
NEARBY = ["sin", "kul", "hkg", "han", "sgn", "cgk", "mnl", "tpe", "hnd", "nrt", "kix", "icn"]
_KW = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
_PICK_LOCK = threading.Lock()


class WireGuardBlocked(Exception):
    pass


def _cfg():
    try:
        return json.load(open(os.path.join(ROOT, "configmain.json"), encoding="utf-8-sig"))
    except Exception:
        return {}


def _wg_dir(cfg):
    d = str(cfg.get("wg_dir", "wg") or "wg")
    return os.path.abspath(d if os.path.isabs(d) else os.path.join(ROOT, d))


def _endpoint(conf_path):
    try:
        with open(conf_path, encoding="utf-8-sig") as f:
            for ln in f:
                if ln.strip().lower().startswith("endpoint"):
                    return ln.split("=", 1)[1].strip().rsplit(":", 1)[0].lower()
    except OSError:
        pass
    return ""


def _adb(dev, args, timeout=30):
    return subprocess.run([ADB, "-s", dev, *args], capture_output=True, timeout=timeout, **_KW)


def _root(dev, cmd, timeout=30):
    return _adb(dev, ["shell", f"su -c '{cmd}'"], timeout=timeout)


def clean_mitm(dev):
    """ล้าง routing ของ capture_auto ที่ค้าง (hosts mount ซ้อนหลายชั้น / iptables / adb reverse)"""
    for _ in range(100):
        r = _root(dev, "grep -c rangers-api /system/etc/hosts", timeout=10)
        if r.stdout.strip() in (b"", b"0"):
            break
        if _root(dev, "umount /system/etc/hosts", timeout=10).returncode != 0:
            break
    _root(dev, "iptables -t nat -F OUTPUT 2>/dev/null", timeout=10)
    _adb(dev, ["reverse", "--remove-all"], timeout=10)


def _tuned_conf(conf_path, dev, cfg):
    lines = open(conf_path, encoding="utf-8-sig").read().replace("\r", "").split("\n")
    apps = str(cfg.get("wg_split_apps", "com.linecorp.LGRGS") or "").strip()
    keepalive = int(cfg.get("wg_keepalive", 25) or 0)
    low = [x.strip().lower() for x in lines]
    out, section = [], ""
    for ln in lines:
        s = ln.strip().lower()
        if s.startswith("[") and section == "[interface]" and apps and not any(x.startswith("includedapplications") for x in low):
            out.append(f"IncludedApplications = {apps}")
        if s.startswith("["):
            section = s
        out.append(ln)
    if keepalive and not any(x.startswith("persistentkeepalive") for x in low):
        while out and not out[-1].strip():
            out.pop()
        out.append(f"PersistentKeepalive = {keepalive}")
    p = os.path.join(tempfile.gettempdir(), f"wg_tuned_{dev.replace(':', '_')}.conf")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out).rstrip() + "\n")
    return p


def net_probe(dev):
    """ยิงเซิร์ฟเวอร์เกมผ่าน tunnel: คืน (ip, code) ; 401 = ใช้ได้ / 000,403,429 = บล็อก"""
    safe = dev.replace(":", "_").replace("/", "_")
    remote = f"/data/local/tmp/probe_{safe}.sh"
    local = os.path.join(tempfile.gettempdir(), f"probe_{safe}.sh")
    lines = [
        "command -v curl >/dev/null 2>&1 || { echo 'P NA NA'; rm -f " + remote + "; exit 0; }",
        "R=0",
        "if ip -o link | grep -q ' tun0'; then ip rule add pref 10500 uidrange 0-0 lookup tun0 2>/dev/null && R=1; fi",
        "IP=$(curl -s -m 8 https://api.ipify.org)",
        "C=$(curl -s -m 12 -o /dev/null -w '%{http_code}' https://rangers-api.line-apps.com/v12.3/home)",
        "[ $R = 1 ] && ip rule del pref 10500",
        "echo \"P ${IP:--} ${C:-000}\"",
        f"rm -f {remote}",
    ]
    with open(local, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    try:
        _adb(dev, ["push", local, remote], timeout=20)
        r = _adb(dev, ["shell", f"su -c 'sh {remote}'"], timeout=40)
    finally:
        try:
            os.remove(local)
        except OSError:
            pass
    for ln in r.stdout.decode("utf-8", "ignore").splitlines():
        if ln.startswith("P "):
            parts = ln.split()
            return parts[1], parts[2]
    return "-", "000"


def apply_conf(dev, conf_path, cfg):
    """ใส่ config เข้าแอป WireGuard ในอีมู + เปิด tunnel + ทดสอบ ; บล็อก -> WireGuardBlocked"""
    safe = dev.replace(":", "_").replace("/", "_")
    rconf, rpb, rsh = (f"/data/local/tmp/wg_{safe}.conf", f"/data/local/tmp/wg_{safe}.pb",
                       f"/data/local/tmp/wg_{safe}.sh")
    lpb = os.path.join(tempfile.gettempdir(), f"wg_{safe}.pb")
    lsh = os.path.join(tempfile.gettempdir(), f"wg_{safe}.sh")
    tuned = None
    try:
        rc = _root(dev, "id", timeout=10)
        if rc.returncode != 0 or b"uid=0" not in rc.stdout:
            raise RuntimeError("MuMu ต้องเปิด Root ก่อน")
        clean_mitm(dev)
        if b"YES" not in _root(dev, f"test -d /data/data/{PKG} && echo YES", timeout=15).stdout:
            apk = os.path.join(_wg_dir(cfg), "wireguard.apk")
            if not os.path.isfile(apk) or os.path.getsize(apk) < 1_000_000:
                urllib.request.urlretrieve(
                    "https://download.wireguard.com/android-client/com.wireguard.android-1.0.20260315.apk", apk)
            if _adb(dev, ["install", "-r", apk], timeout=180).returncode != 0:
                raise RuntimeError("ติดตั้งแอป WireGuard ไม่สำเร็จ")
        _root(dev, f"am broadcast -f 0x20 -p {PKG} -a {PKG}.action.SET_TUNNEL_DOWN --es tunnel {TUNNEL}", timeout=20)
        time.sleep(1)
        _adb(dev, ["shell", f"am force-stop {PKG}"], timeout=10)
        key = b"allow_remote_control_intents"
        entry = b"\x0a" + bytes([len(key)]) + key + b"\x12\x02\x08\x01"
        with open(lpb, "wb") as f:
            f.write(b"\x0a" + bytes([len(entry)]) + entry)
        data = f"/data/data/{PKG}"
        with open(lsh, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join([
                f"mkdir -p {data}/files/datastore",
                f"cp {rconf} {data}/files/{TUNNEL}.conf",
                f"cp {rpb} {data}/files/datastore/settings.preferences_pb",
                f"U=$(stat -c %u {data})",
                f"chown -R $U:$U {data}/files",
                f"chmod -R 700 {data}/files",
                f"restorecon -R {data}/files 2>/dev/null",
                f"rm -f {rconf} {rpb}",
                f"cmd appops set {PKG} ACTIVATE_VPN allow",
                f"cmd deviceidle whitelist +{PKG}",
                f"am broadcast -f 0x20 -p {PKG} -a {PKG}.action.SET_TUNNEL_UP --es tunnel {TUNNEL}",
                f"rm -f {rsh}",
            ]) + "\n")
        tuned = _tuned_conf(conf_path, dev, cfg)
        for lp, rp in ((tuned, rconf), (lpb, rpb), (lsh, rsh)):
            if _adb(dev, ["push", lp, rp], timeout=30).returncode != 0:
                raise RuntimeError("ส่งไฟล์ WireGuard เข้า MuMu ไม่สำเร็จ")
        if _root(dev, f"sh {rsh}", timeout=30).returncode != 0:
            raise RuntimeError("MuMu รันคำสั่งตั้งค่า WireGuard ไม่สำเร็จ")
        for _ in range(15):
            time.sleep(1)
            st = _adb(dev, ["shell", "ip -o link show"], timeout=10)
            if st.returncode == 0 and b"tun" in st.stdout:
                _adb(dev, ["shell", "am force-stop com.linecorp.LGRGS"], timeout=10)
                ip, code = net_probe(dev)
                if code in ("000", "403", "429"):
                    raise WireGuardBlocked(f"เซิร์ฟเวอร์เกมไม่รับ IP {ip} (code {code})")
                return f"{os.path.basename(conf_path)}, IP {ip}, code {code}"
        raise RuntimeError("ไม่พบ tunnel หลังสั่งเชื่อมต่อ")
    finally:
        for p in (lpb, lsh, tuned):
            if p:
                try:
                    os.remove(p)
                except OSError:
                    pass


def _active_endpoint(dev):
    r = _adb(dev, ["shell", f"su -c 'grep -i \"^Endpoint\" /data/data/{PKG}/files/{TUNNEL}.conf'"], timeout=12)
    ln = next((x for x in r.stdout.decode("utf-8", "ignore").splitlines() if "=" in x), "")
    return ln.split("=", 1)[1].strip().rsplit(":", 1)[0].lower() if ln else ""


def _mark_blocked(wg_dir, conf_path):
    bp = os.path.join(wg_dir, ".blocked.json")
    try:
        d = json.load(open(bp, encoding="utf-8"))
    except Exception:
        d = {}
    d[_endpoint(conf_path)] = time.time()
    with open(bp, "w", encoding="utf-8") as f:
        json.dump(d, f)


def reset_ip(dev, log=print, tries=5):
    """เปลี่ยน IP ของจอ dev (ใกล้ไทยก่อน, ไม่ซ้ำ IP เดิม/IP ที่บล็อก/ไฟล์ที่จออื่นจองอยู่) -> (ok, ข้อความ)"""
    cfg = _cfg()
    wg_dir = _wg_dir(cfg)
    claims = os.path.join(wg_dir, ".claims")
    os.makedirs(claims, exist_ok=True)
    try:
        blocked = set(json.load(open(os.path.join(wg_dir, ".blocked.json"), encoding="utf-8")))
    except Exception:
        blocked = set()
    current = _active_endpoint(dev)

    def owner(c):
        try:
            return open(os.path.join(claims, os.path.basename(c) + ".lock"), encoding="utf-8").read().strip()
        except OSError:
            return ""

    def rank(c):
        code = _endpoint(c).split("-", 1)[0]
        return NEARBY.index(code) if code in NEARBY else len(NEARBY)

    with _PICK_LOCK:
        confs = sorted(os.path.join(wg_dir, n) for n in os.listdir(wg_dir) if n.lower().endswith(".conf"))
        avail = [c for c in confs if _endpoint(c) not in blocked and _endpoint(c) != current
                 and owner(c) in ("", dev)]
        avail.sort(key=rank)
    if not avail:
        return False, "ไม่มีไฟล์ WG ว่างให้ใช้"
    last_err = ""
    for attempt in range(1, tries + 1):
        if not avail:
            break
        conf = avail.pop(0)
        claim = os.path.join(claims, os.path.basename(conf) + ".lock")
        try:
            fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(dev)
        except FileExistsError:
            continue
        try:
            msg = apply_conf(dev, conf, cfg)
            # คืนไฟล์อื่นที่จอนี้เคยจองไว้
            for fn in os.listdir(claims):
                p = os.path.join(claims, fn)
                if fn.endswith(".lock") and p != claim:
                    try:
                        if open(p, encoding="utf-8").read().strip() == dev:
                            os.remove(p)
                    except OSError:
                        pass
            log(f"[{dev}] [RESET-IP] สำเร็จ ({msg})")
            return True, msg
        except WireGuardBlocked as e:
            last_err = str(e)
            log(f"[{dev}] [RESET-IP] {os.path.basename(conf)}: {e} - สลับเซิร์ฟเวอร์ ({attempt}/{tries})")
            _mark_blocked(wg_dir, conf)
        except Exception as e:
            last_err = str(e)
            log(f"[{dev}] [RESET-IP] {os.path.basename(conf)}: {e} ({attempt}/{tries})")
        try:
            os.remove(claim)
        except OSError:
            pass
    return False, last_err or "เปลี่ยน IP ไม่สำเร็จ"


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print("usage: python wg_reset.py <adb serial>")
        sys.exit(1)
    ok, msg = reset_ip(sys.argv[1])
    print(("OK " if ok else "FAIL ") + msg)
