#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capture_auto.py — จับ credential แบบ AUTO ทั้งหมดในคำสั่งเดียว
(MITM + routing + ส่ง XML เข้าเกม + เปิดเกม/ล็อกอิน + เก็บ creds.json + ลบ XML จาก input-id + เก็บกวาด)

ความสามารถ:
  1) ตรวจจับไฟล์ .xml ใน input-id/ (หรือโฟลเดอร์ที่ระบุ)
  2) สลับบัญชีด้วยการ inject XML เข้า shared_prefs ของเกมทีละไฟล์
  3) ผ่านหน้า Login (Apple/Guest), Terms of Use, Select Language, Check resources อัตโนมัติ
  4) ดักจับ credential (udid, LF_AC, guestCookie, rsn) ผ่าน mitmproxy reverse-proxy
  5) เมื่อจับสำเร็จ: บันทึกลง creds.json, สั่งปิดเกมทันทีเพื่อตรึง session, แล้วลบไฟล์ .xml ออกจาก input-id/
  6) ถ้าไม่พบไฟล์ใน input-id/ จะ fallback ไปจับบัญชีปัจจุบันที่เปิดอยู่ในเครื่อง

ใช้:
  python capture_auto.py                     # วนจับทุกไฟล์ใน input-id/ (อัตโนมัติ)
  python capture_auto.py --single            # ทดสอบแค่ไฟล์แรก 1 ไฟล์
  python capture_auto.py --device 127.0.0.1:16512
  python capture_auto.py --input-dir backup  # ชี้โฟลเดอร์อื่น
  python capture_auto.py --no-delete         # ไม่ลบไฟล์ XML หลังจับสำเร็จ
  python capture_auto.py --use-login         # ให้ login.py ช่วยคลิกแทนการกดจอแบบ auto-tap

** ต้องมี: mitmdump (pip install mitmproxy) และเครื่อง root/su **
"""
import argparse
import glob
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import sysconfig
import threading
import time
import tkinter as tk
from tkinter import ttk
import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)   # โฟลเดอร์โปรเจคหลัก (มี adb/ img/ input-id/ login.py)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lgr_api import LGRClient, parse_ruby, parse_coin, parse_tickets
# ตัวกลางอ่าน/เขียน creds (lock ข้ามโปรเซส + atomic + .bak) — ทุกเส้นทางเขียนในไฟล์นี้ต้องผ่านชุดนี้
from lgr_api import (
    load_creds as _api_load_creds,
    save_creds as _api_save_creds,
    merge_part_creds as _api_merge_part_creds,
    part_owner as _api_part_owner,
    creds_lock as _api_creds_lock,
    _read_json_file as _api_read_json_file,
    _write_creds_atomic as _api_write_creds_atomic,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CREDS = os.path.join(HERE, "creds.json")   # ไฟล์เดียวใน api/ (ตรงกับ lgr_api.CREDS_FILE)
ADDON = os.path.join(HERE, "capture_credential.py")
PKG = "com.linecorp.LGRGS"
ACT = f"{PKG}/.LineRangersAdr"
API_HOST = "rangers-api.line-apps.com"
PORT = 8443
PREF_DIR = f"/data/data/{PKG}/shared_prefs"
PREF_FILE = f"{PREF_DIR}/_LINE_COCOS_PREF_KEY.xml"
OUTPUT_DIR = os.path.join(ROOT, "login-success")   # ที่เก็บ .xml ของบัญชีที่สำเร็จ (เหมือน login.py)
FAILED_DIR = os.path.join(ROOT, "login-failed")     # ที่เก็บ .xml ของบัญชีที่เข้าไม่ได้ (เหมือน login.py)

_INJECT_LOCK = threading.Lock()   # ล็อคคิวฉีดไฟล์ ให้ทำทีละจอ ป้องกันแย่ง ADB / disk I/O ชนกัน
_WG_CONTROLLERS = {}
_WG_CONTROLLERS_LOCK = threading.Lock()


# ---------- helpers ----------
def find_adb():
    for c in (os.path.join(ROOT, "adb", "adb.exe"),
              os.path.join(ROOT, "adb", "adb"), "adb"):
        if c in ("adb",) or os.path.exists(c):
            return c
    return "adb"


ADB = find_adb()


def find_mitmdump():
    """หา mitmdump — PATH ก่อน แล้วค่อยไล่โฟลเดอร์ Scripts ของ Python (user/global)"""
    p = shutil.which("mitmdump")
    if p:
        return p
    cand = []
    for base in {sysconfig.get_path("scripts"),
                 sysconfig.get_path("scripts", "nt_user"),
                 os.path.join(os.path.dirname(sys.executable), "Scripts")}:
        if base:
            cand += glob.glob(os.path.join(base, "mitmdump*"))
    try:
        import site
        for base in site.getsitepackages() + [site.getusersitepackages()]:
            cand += glob.glob(os.path.join(os.path.dirname(base), "Scripts", "mitmdump*"))
    except Exception:
        pass
    for c in cand:
        if os.path.exists(c):
            return c
    return None


def adb(args, device=None, **kw):
    cmd = [ADB]
    if device:
        cmd += ["-s", device]
    cmd += args
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def enable_root(dev):
    """ขอ root adbd (AVD/emulator ส่วนใหญ่ได้เลย) — คืน True ถ้า shell เป็น uid=0"""
    adb(["root"], device=dev, timeout=20)
    adb(["wait-for-device"], device=dev, timeout=20)
    time.sleep(1)
    who = adb(["shell", "id"], device=dev).stdout
    return "uid=0" in who


_ROOT_ADBD = False


def sh_quote(s):
    """single-quote สำหรับ POSIX sh: a'b -> 'a'\\''b'"""
    return "'" + s.replace("'", "'\\''") + "'"


def sh(cmd, device=None, timeout=30):
    """รันเป็น root: ถ้า adbd เป็น root แล้ว สั่งตรง; ไม่งั้น fallback ไป su -c '...'
    (เดิมห่อ '{cmd}' โดยไม่ escape -> คำสั่งที่มี ' เช่น echo '127.0.0.1 ...' ถูกตัดกลางทาง)"""
    if _ROOT_ADBD:
        return adb(["shell", cmd], device=device, timeout=timeout)
    if cmd.strip().startswith("su -c"):
        return adb(["shell", cmd], device=device, timeout=timeout)
    return adb(["shell", "su -c " + sh_quote(cmd)], device=device, timeout=timeout)


def list_devices():
    """คืน serial ของทุกเครื่องที่ต่ออยู่ (สถานะ device)"""
    out = adb(["devices"]).stdout.splitlines()
    devs = [l.split()[0] for l in out[1:] if l.strip() and l.strip().endswith("device")]
    if not devs:
        sys.exit("[X] ไม่พบเครื่อง adb — เปิด emulator แล้ว `adb connect` ก่อน")
    return devs


def dedupe_device_aliases(devices):
    """Keep one ADB serial per Android fingerprint so aliases cannot race as separate workers."""
    try:
        import login
    except Exception as exc:
        print(f"[!] ตรวจ alias ของ ADB ไม่ได้ ({exc}) - ใช้ serial ตามรายการเดิม", flush=True)
        return devices

    kept = []
    fingerprints = {}
    for dev in devices:
        snapshot = login._device_identity_snapshot(ADB, dev)
        signature = login._device_identity_signature(snapshot)
        if not signature:
            kept.append(dev)
            continue

        current = login._device_identity_map(signature)
        duplicate_of = None
        for previous, previous_fp in fingerprints.items():
            previous_map = login._device_identity_map(previous_fp)
            if signature == previous_fp or any(
                current.get(key) and current.get(key) == previous_map.get(key)
                for key in current
            ):
                duplicate_of = previous
                break

        if duplicate_of:
            print(f"[ADB] {dev} เป็น alias/fingerprint ซ้ำกับ {duplicate_of} - ใช้ worker เดียว", flush=True)
            continue
        kept.append(dev)
        fingerprints[dev] = signature

    return kept


def load_creds(path=None):
    """อ่านอย่างเดียว (ไฟล์ไม่มี/พัง = {}) — ใช้ตัวกลางของ lgr_api ไม่ merge part"""
    return _api_load_creds(path or CREDS)


def save_creds(data, path=None):
    """เขียนทั้งไฟล์ผ่านตัวกลาง (lock + atomic + .bak) ; คืน False ถ้าไม่ได้เขียน (แจ้งแล้ว)
    ถ้าแก้แค่บางบัญชีให้ใช้ _api_try_update_creds แทน"""
    return _api_save_creds(data, path or CREDS)


def part_creds(host_port):
    """ไฟล์ creds แยกต่อจอ (กันแย่ง .lock/เขียนชนกัน) -> merge เข้า creds.json ตอนจบ"""
    return os.path.join(HERE, f"creds.part{host_port}.json")


import threading as _threading
_MERGE_LOCK = _threading.Lock()


def merge_parts_into_creds(part_files=None):
    """รวม creds.partN.json เข้า creds.json ผ่าน lgr_api.merge_part_creds
    (lock ข้ามโปรเซสของ creds.json + ของ part แต่ละไฟล์ ; ลบ part เฉพาะหลังเขียนสำเร็จ)
    part_files=None = ทุก part ; lock หมดเวลา/ไฟล์พัง -> แจ้ง error, ไม่เขียน ไม่ลบ part"""
    with _MERGE_LOCK:
        try:
            merged, _ = _api_merge_part_creds(creds_path=CREDS, part_files=part_files)
        except Exception as e:
            print(f"[!] รวม creds.part*.json ไม่สำเร็จ (ไม่ได้เขียน/ไม่ได้ลบ part): {type(e).__name__}: {e}",
                  flush=True)
            return len(load_creds())
        return len(merged)


def fetch_account_info(cred, fname=None, creds_file=None):
    """เรียก GET API เพื่อดึง ruby, ticket, coin, level ทันทีหลังจับ credential ได้"""
    udid, lf = cred.get("udid"), cred.get("LF_AC")
    info = {
        "file": fname or cred.get("file", "-"),
        "ruby": cred.get("ruby", 0),
        "coin": cred.get("coin", 0),
        "ticket": cred.get("ticket", 0),
        "level": cred.get("level", 1),
    }
    if not (udid and lf):
        return info

    try:
        cli = LGRClient(udid, lf)
        st, home = cli.home()
        if st == 401 and cred.get("guestCookie"):
            cli.login(cred["guestCookie"])
            st, home = cli.home()

        if st == 200 and isinstance(home, dict):
            res = home.get("result", {}) or {}
            player = res.get("player", {}) or {}
            badge = res.get("badge", {}) or {}

            r_ruby = parse_ruby(res, player)
            r_coin = parse_coin(res, player)
            r_ticket = parse_tickets(res, player)
            r_level = player.get("level") or res.get("level")

            if r_ruby is not None:
                info["ruby"] = r_ruby
            if r_coin is not None:
                info["coin"] = r_coin
            if r_ticket is not None:
                info["ticket"] = r_ticket
            if r_level is not None:
                info["level"] = r_level
            info["gift_badge"] = badge.get("GIFT", 0)

            if cli.lf_ac:
                cred["LF_AC"] = cli.lf_ac
    except Exception as e:
        print(f"[!] เรียก API ดึงข้อมูลผู้เล่นไม่สำเร็จ: {e}", flush=True)

    if fname:
        cred["file"] = fname
    cred["ruby"] = info["ruby"]
    cred["coin"] = info["coin"]
    cred["ticket"] = info["ticket"]
    cred["level"] = info["level"]

    # บันทึกข้อมูลที่อัปเดต (รวม LF_AC ล่าสุด) ลงไฟล์ creds ของจอนี้ ภายใต้ lock เดียวกับ addon
    # (addon ของจอนี้เขียนไฟล์เดียวกันพร้อมกันได้) : มี entry อยู่แล้ว -> แก้เฉพาะ field ที่ฟังก์ชันนี้ตั้ง
    # ; ยังไม่มี -> สร้างจาก cred ; ค่า None ไม่ทับ (guestCookie เดิมคงอยู่)
    _save_account_info(cred, creds_file)

    return info


_INFO_FIELDS = ("LF_AC", "file", "ruby", "coin", "ticket", "level")


def _save_account_info(cred, creds_file=None):
    """หา key (rsn ก่อน แล้ว udid) + แก้ + เขียน ภายใต้ creds_lock ก้อนเดียว (addon อาจยุบ key udid->rsn ระหว่างทาง)
    lock หมดเวลา/ไฟล์ JSON พัง -> ไม่เขียน พิมพ์แจ้ง ; คืน error (str) หรือ None"""
    path = creds_file or CREDS
    rsn = cred.get("rsn") or cred.get("udid")
    if not rsn:
        return None
    try:
        with _api_creds_lock(path):
            cur = _api_read_json_file(path)
            key = next((k for k in (rsn, cred.get("udid")) if k and isinstance(cur.get(k), dict)), None)
            if key:
                fields = {k: cred.get(k) for k in _INFO_FIELDS}
            else:
                key, fields = rsn, dict(cred)
                cur[key] = {}
            entry = cur[key]
            changed = False
            for k, v in fields.items():
                if v is not None and entry.get(k) != v:   # None ไม่ทับ (guestCookie เดิมคงอยู่)
                    entry[k] = v
                    changed = True
            if changed:
                _api_write_creds_atomic(cur, path)
        return None
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"[!] บันทึกข้อมูลบัญชีลง {os.path.basename(path)} ไม่สำเร็จ: {err}", flush=True)
        return err


def extract_udid_from_xml(xml_path):
    """ดึง _DEVICE_UUID_KEY จากไฟล์ xml"""
    try:
        with open(xml_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        m = re.search(r'<string name="_DEVICE_UUID_KEY">([^<]+)</string>', content)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return None


# ---------- routing setup / teardown ----------
DEV_PORT = 8443   # port ฝั่งอีมูฯ (คงที่ทุกจอ) -> reverse ไป host port แยกต่อจอ


_ROUTE_PORT = {}   # dev -> host port ของ mitm (ไว้ตั้ง routing ใหม่หลัง Reset IP ล้างทิ้ง)


_ROUTE_RULE = f"OUTPUT -p tcp -d 127.0.0.1 --dport 443 -j REDIRECT --to-ports {DEV_PORT}"
HOSTS = "/system/etc/hosts"
# สำเนา hosts ชื่อเฉพาะของ capture_auto (เดิมใช้ /data/local/tmp/hosts ร่วมกับสคริปต์อื่น -> แยกเจ้าของไม่ได้)
HOSTS_COPY = "/data/local/tmp/lgr_capture_auto_hosts"
# dev -> set ของ resource ที่ setup_routing สร้างและยืนยันแล้ว ("reverse","hosts_copy","hosts","rule")
# teardown_routing ถอนเฉพาะในนี้ ; setup ซ้ำ (หลัง Reset IP) ใช้ตัวนี้แยกของตัวเองจากของคนอื่น
_ROUTE_OWNED = {}


class RoutingConflict(RuntimeError):
    """พบ routing/mount ที่ไม่ได้เป็นของรอบนี้ -> ไม่ลบ ไม่ตั้งทับ ให้ผู้ใช้ตรวจเอง"""


def _hosts_mounted(dev):
    return (" %s " % HOSTS) in (sh("cat /proc/mounts", device=dev).stdout or "")


def _route_rule_exists(dev):
    return sh(f"iptables -t nat -C {_ROUTE_RULE}", device=dev).returncode == 0


def _reverse_exists(dev):
    return f"tcp:{DEV_PORT}" in (adb(["reverse", "--list"], device=dev).stdout or "")


def _hosts_copy_exists(dev):
    return sh(f"test -e {HOSTS_COPY}", device=dev).returncode == 0


def setup_routing(dev, host_port=PORT):
    """ตั้ง reverse + hosts bind-mount + กฎ REDIRECT ; ไม่ถอด/ลบของที่มีอยู่ก่อน
    ตรวจก่อนสร้างอะไรทั้งนั้น: เจอ resource ที่ไม่ได้อยู่ใน _ROUTE_OWNED[dev] -> RoutingConflict
    (ของตัวเองที่ยังอยู่ = ใช้ต่อ ; ของตัวเองที่หายไป เช่นหลัง Reset IP = ตั้งใหม่)
    บันทึก ownership หลังยืนยันว่าแต่ละขั้นสำเร็จจริง ; คืน True เมื่อครบ"""
    owned = _ROUTE_OWNED.setdefault(dev, set())
    present = {
        "reverse": _reverse_exists(dev),
        "hosts_copy": _hosts_copy_exists(dev),
        "hosts": _hosts_mounted(dev),
        "rule": _route_rule_exists(dev),
    }
    foreign = sorted(k for k, v in present.items() if v and k not in owned)
    if foreign:
        raise RoutingConflict(
            f"[{dev}] พบ routing ที่ไม่ใช่ของรอบนี้ {foreign} -> ไม่ลบ/ไม่ตั้งทับ "
            f"(ตรวจ: adb reverse tcp:{DEV_PORT}, {HOSTS_COPY}, mount {HOSTS}, iptables {_ROUTE_RULE})")
    for k, v in present.items():                 # ของตัวเองที่หายไปแล้ว -> ไม่ถือว่าเป็นเจ้าของอีก
        if not v:
            owned.discard(k)

    _ROUTE_PORT[dev] = host_port
    print(f"[*] [{dev}] ตั้ง adb reverse (:{DEV_PORT}->host:{host_port}) + routing...", flush=True)
    adb(["reverse", f"tcp:{DEV_PORT}", f"tcp:{host_port}"], device=dev)
    if _reverse_exists(dev):
        owned.add("reverse")
    if "hosts_copy" not in owned:
        sh(f"cp {HOSTS} {HOSTS_COPY} && {{ grep -q {API_HOST} {HOSTS_COPY} || "
           f"echo '127.0.0.1 {API_HOST}' >> {HOSTS_COPY}; }}", device=dev)
        if _hosts_copy_exists(dev):
            owned.add("hosts_copy")
    if "hosts" not in owned and "hosts_copy" in owned:
        sh(f"mount --bind {HOSTS_COPY} {HOSTS}", device=dev)
        if _hosts_mounted(dev):
            owned.add("hosts")
    if "rule" not in owned and "hosts" in owned:
        sh(f"iptables -t nat -A {_ROUTE_RULE}", device=dev)
        if _route_rule_exists(dev):
            owned.add("rule")
    ok = {"reverse", "hosts", "rule"} <= owned
    if not ok:
        print(f"[!] [{dev}] routing ไม่สมบูรณ์ (ต้อง root?) ตั้งได้: {sorted(owned) or '-'}", flush=True)
    return ok


def teardown_routing(dev):
    """ถอนเฉพาะสิ่งที่ setup_routing บันทึก ownership ไว้ (ไม่ -F / ไม่ --remove-all / ไม่ umount ของคนอื่น)
    แล้วตรวจซ้ำ -> คืน list ของ resource ที่ยังค้าง (ว่าง = ถอนครบ) ; ค้าง = แจ้ง ไม่ลบแบบกว้าง"""
    owned = _ROUTE_OWNED.pop(dev, set())
    print(f"[*] [{dev}] ถอน routing/MITM คืนสภาพเดิม (เฉพาะของรอบนี้: {sorted(owned) or '-'})...", flush=True)
    left = []
    if "rule" in owned:
        sh(f"iptables -t nat -D {_ROUTE_RULE}", device=dev)
        if _route_rule_exists(dev):
            left.append(f"iptables -t nat {_ROUTE_RULE}")
    if "hosts" in owned:
        sh(f"umount {HOSTS}", device=dev)
        if _hosts_mounted(dev):
            left.append(f"bind-mount {HOSTS}")
    if "hosts_copy" in owned and f"bind-mount {HOSTS}" not in left:
        sh(f"rm -f {HOSTS_COPY}", device=dev)
        if _hosts_copy_exists(dev):
            left.append(HOSTS_COPY)
    if "reverse" in owned:
        adb(["reverse", "--remove", f"tcp:{DEV_PORT}"], device=dev)
        if _reverse_exists(dev):
            left.append(f"adb reverse tcp:{DEV_PORT}")
    if left:
        print(f"[!] [{dev}] routing ยังค้าง ต้องตรวจ/ถอนเอง: {left}", flush=True)
    return left


# ---------- game launch / inject ----------
def clear_session_files(dev):
    """ลบไฟล์ session เก่า (trident/cocos/cache) เพื่อไม่ให้ session บัญชีก่อนหน้าค้าง"""
    cmd = (
        f"rm -f {PREF_DIR}/trident.preferences.xml {PREF_DIR}/pcvmspf.xml "
        f"{PREF_DIR}/Cocos2dxPrefsFile.xml; "
        f"rm -rf /data/data/{PKG}/cache/*"
    )
    sh(cmd, device=dev, timeout=15)


def force_stop_game(dev):
    adb(["shell", "am", "force-stop", PKG], device=dev)
    time.sleep(0.5)
    sh(f"killall -9 {PKG} 2>/dev/null || true", device=dev)


def wipe_account(dev):
    """ล้างบัญชีทิ้งทั้งหมด -> ครั้งต่อไปที่เปิดเกม เกมจะสร้าง GUEST ใหม่เอง
    (ลบ _LINE_COCOS_PREF_KEY.xml = credential guest + session ต่าง ๆ + cache)"""
    force_stop_game(dev)
    cmd = (
        f"rm -f {PREF_FILE} "
        f"{PREF_DIR}/trident.preferences.xml {PREF_DIR}/pcvmspf.xml "
        f"{PREF_DIR}/Cocos2dxPrefsFile.xml; "
        f"rm -rf /data/data/{PKG}/cache/* /data/data/{PKG}/app_webview 2>/dev/null || true"
    )
    sh(cmd, device=dev, timeout=20)


def pull_account_xml(dev, name):
    """ดึง _LINE_COCOS_PREF_KEY.xml ของบัญชีที่เพิ่งสร้าง ออกมาเก็บใน out-dir
    วิธีชัวร์: cp -> /data/local/tmp -> chmod 644 -> adb pull. คืน path ไฟล์ หรือ None"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    tmp = f"/data/local/tmp/_out_pref_{dev.replace(':', '_')}.xml"
    sh(f"cp {PREF_FILE} {tmp} && chmod 644 {tmp}", device=dev, timeout=15)
    dst = os.path.join(OUTPUT_DIR, f"{name}_LINE_COCOS_PREF_KEY.xml")
    r = adb(["pull", tmp, dst], device=dev, timeout=30)
    sh(f"rm -f {tmp}", device=dev)
    if r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 100:
        return dst
    print(f"[!] pull .xml ไม่สำเร็จ: {r.stderr.strip() or r.stdout.strip()}", flush=True)
    return None


def pull_before_wipe(dev):
    """ก่อนล้างบัญชี: ถ้ามีบัญชีค้างอยู่ ให้ดึง .xml เก็บก่อน (save ก่อน delete ไม่ให้ตก)"""
    r = sh(f"cat {PREF_FILE} 2>/dev/null", device=dev, timeout=10)
    m = re.search(r'_DEVICE_UUID_KEY">([^<]+)<', r.stdout or "")
    if not m:
        return None
    udid = m.group(1).strip()
    dst = pull_account_xml(dev, f"pre_[{udid[:12]}]")
    if dst:
        print(f"[*] เซฟบัญชีค้างก่อน wipe: {os.path.basename(dst)}", flush=True)
    return dst


def launch_game(dev):
    print(f"[*] เปิดเกม (am start + monkey)...", flush=True)
    adb(["shell", "am", "start", "-S", "-n", ACT], device=dev)
    time.sleep(1)
    adb(["shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1"], device=dev)


def launch_login_py(dev):
    print("[*] เรียก login.py --cli ช่วยกดผ่านหน้า PLAY ...", flush=True)
    return subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "login.py"), "--device", dev, "--cli", "--no-reset-adb"],
        cwd=HERE,
    )


def handle_success_file(xml_path, dev=""):
    """ย้ายไฟล์สำเร็จไป login-success/ เหมือน login.py"""
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        base = os.path.basename(xml_path)
        dst = os.path.join(OUTPUT_DIR, base)
        if os.path.abspath(xml_path) != os.path.abspath(dst):
            if os.path.exists(dst):
                try:
                    os.remove(dst)
                except Exception:
                    pass
            shutil.move(xml_path, dst)
            print(f"[*] [{dev}] ส่งไฟล์สำเร็จไปที่ {OUTPUT_DIR}: {base}", flush=True)
        lock = xml_path + ".lock"
        if os.path.exists(lock):
            try:
                os.remove(lock)
            except Exception:
                pass
        return dst
    except Exception as e:
        print(f"[!] [{dev}] ย้ายไฟล์สำเร็จไม่สำเร็จ: {e}", flush=True)
        return xml_path


def handle_failure_file(xml_path, dev=""):
    """ย้ายไฟล์ล้มเหลวไป login-failed/ เหมือน login.py"""
    try:
        os.makedirs(FAILED_DIR, exist_ok=True)
        base = os.path.basename(xml_path)
        dst = os.path.join(FAILED_DIR, base)
        if os.path.abspath(xml_path) != os.path.abspath(dst):
            if os.path.exists(dst):
                try:
                    os.remove(dst)
                except Exception:
                    pass
            shutil.move(xml_path, dst)
            print(f"[*] [{dev}] ส่งไฟล์ล้มเหลวไปที่ {FAILED_DIR}: {base}", flush=True)
        lock = xml_path + ".lock"
        if os.path.exists(lock):
            try:
                os.remove(lock)
            except Exception:
                pass
        return dst
    except Exception as e:
        print(f"[!] [{dev}] ย้ายไฟล์ล้มเหลวไม่สำเร็จ: {e}", flush=True)
        return xml_path


def inject_xml(dev, xml_path):
    """ส่งไฟล์ _LINE_COCOS_PREF_KEY.xml ของบัญชีเข้าเกม (ใช้วิธีเดียวกับ login.py เป๊ะๆ)"""
    safe_name = os.path.basename(xml_path)
    print(f"[{dev}] กำลังส่งไฟล์เข้าเกม: {safe_name} (Robust Mode เหมือน login.py)...", flush=True)

    with _INJECT_LOCK:
        # 1. ปลดล็อก Read-only (ถ้ามี เหมือน login.py)
        try:
            adb(["shell", "su -c 'mount -o remount,rw / 2>/dev/null || mount -o remount,rw /data 2>/dev/null'"], device=dev, timeout=15)
        except Exception as e:
            print(f"[{dev}] [WARN] remount ข้ามไป (ไม่ critical): {e}", flush=True)

        try:
            adb(["shell", "am", "force-stop", "com.linecorp.LGRGS"], device=dev, timeout=15)
        except Exception as e:
            print(f"[{dev}] [WARN] force-stop ข้ามไป (ไม่ critical): {e}", flush=True)
        time.sleep(2)

        try:
            adb(["shell", "su -c 'killall -9 com.linecorp.LGRGS 2>/dev/null || true'"], device=dev, timeout=15)
        except Exception as e:
            print(f"[{dev}] [WARN] killall ข้ามไป (ไม่ critical): {e}", flush=True)
        time.sleep(1)

        src = os.path.abspath(xml_path)
        tmp = f"/data/local/tmp/temp_pref_{dev.replace(':', '_')}.xml"
        final_dir = "/data/data/com.linecorp.LGRGS/shared_prefs"
        final = f"{final_dir}/_LINE_COCOS_PREF_KEY.xml"

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                # Push to tmp (60 วิ: ตอนรันหลายจอพร้อมกัน ดิสก์หนัก 30 วิอาจไม่พอ)
                result = adb(["push", src, tmp], device=dev, timeout=60)
                if result.returncode != 0:
                    err = (result.stderr or result.stdout or 'Unknown Error').strip()
                    print(f"[{dev}] Push attempt {attempt} failed: {err}", flush=True)
                    time.sleep(2)
                    continue

                # Copy, set permissions and owner (เหมือน login.py เป๊ะๆ)
                shell_cmd = (
                    f"su -c '"
                    f"cp {tmp} {final} && "
                    f"chmod 666 {final} && "
                    f"chown $(stat -c %u:%g {final_dir} 2>/dev/null || stat -c %u:%g {final_dir}/.. 2>/dev/null || echo 1000:1000) {final} || true && "
                    f"rm -f {tmp}"
                    f"'"
                )
                adb(["shell", shell_cmd], device=dev, timeout=20)

                print(f"[{dev}] [OK] ส่งไฟล์เข้าเกมสำเร็จ! (Injection successful on attempt {attempt}: {safe_name})", flush=True)
                return True

            except Exception as e:
                print(f"[{dev}] Attempt {attempt} error: {e}", flush=True)
                time.sleep(2)

        print(f"[{dev}] [FAIL] ส่งไฟล์เข้าเกมไม่สำเร็จหลังลองครบ {max_retries} รอบ! (Injection FAILED: {safe_name})", flush=True)
        return False


# ---------- screen navigation helpers ----------
_TPL_CACHE = {}


def get_template(name):
    if name not in _TPL_CACHE:
        p = os.path.join(ROOT, "img", name)
        if os.path.exists(p):
            _TPL_CACHE[name] = cv2.imread(p)
        else:
            _TPL_CACHE[name] = None
    return _TPL_CACHE[name]


def grab_screen(dev):
    """จับภาพจอ -> img (BGR) หรือ None"""
    res = subprocess.run([ADB, "-s", dev, "exec-out", "screencap", "-p"], capture_output=True)
    if not res.stdout or len(res.stdout) < 1000:
        return None
    img = cv2.imdecode(np.frombuffer(res.stdout, np.uint8), cv2.IMREAD_COLOR)
    return img if (img is not None and img.shape[0] > 0) else None


def find_template(img, name, thr=0.8):
    """หา template ในภาพ -> (found, cx, cy, score)"""
    tpl = get_template(name)
    if tpl is None or img is None:
        return False, 0, 0, 0.0
    m = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, v, _, loc = cv2.minMaxLoc(m)
    return v >= thr, loc[0] + tpl.shape[1] // 2, loc[1] + tpl.shape[0] // 2, v


def _login_wg_controller(dev):
    import login

    with _WG_CONTROLLERS_LOCK:
        controller = _WG_CONTROLLERS.get(dev)
        if controller is None:
            controller = login.RangerGearBot(dev, start_popup_monitor=False)
            controller.adb_cmd = ADB
            _WG_CONTROLLERS[dev] = controller
    return login, controller


def open_game_like_login(dev):
    """Use login.py's network preparation and resilient app launch for this device."""
    try:
        login, controller = _login_wg_controller(dev)
    except Exception as exc:
        print(f"[!] [{dev}] โหลดตัวเปิดเกมจาก login.py ไม่สำเร็จ: {exc}", flush=True)
        return False

    # Reset IP แบบ wg-push-file (VPN เฉพาะเกม + ทดสอบผ่าน tunnel จริง + ใกล้ไทยก่อน)
    # แทนระบบ WG ของ login.py ; ปิดด้วย CAPTURE_RESET_IP=0
    if os.environ.get("CAPTURE_RESET_IP", "1") != "0":
        try:
            import wg_reset
            ok, msg = wg_reset.reset_ip(dev, log=lambda m: print(m, flush=True))
            if not ok:
                print(f"[!] [{dev}] Reset IP ไม่สำเร็จ ({msg}) - เปิดเกมต่อด้วย IP เดิม", flush=True)
        except Exception as exc:
            print(f"[!] [{dev}] Reset IP error: {exc}", flush=True)
        try:
            setup_routing(dev, _ROUTE_PORT.get(dev, PORT))   # Reset IP ล้าง routing ของ mitm -> ตั้งกลับ
        except RoutingConflict as exc:
            print(f"[X] {exc}", flush=True)
            return False
        login.config["wg_enabled"] = 0                   # ไม่ให้ login.py ไปยุ่ง WG ซ้ำ
    try:
        # login.py resets these per account in main_login(); this controller
        # persists across capture_auto's batch, so reset the same per-ID quota.
        controller._wg_net_hits = 0
        controller._wg_recover_n = 0
        opened = controller.open_app()
        if not opened:
            if getattr(controller, "device_identity_issue", False):
                print(f"[SKIP] [{dev}] device identity ซ้ำ - หยุด worker นี้และเก็บ XML ไว้", flush=True)
                return None
            print(f"[X] [{dev}] login.py ไม่สามารถเปิดเกมได้", flush=True)
        return bool(opened)
    except login.RestartTimeoutError as exc:
        print(f"[X] [{dev}] เตรียม WireGuard ก่อนเปิดเกมไม่สำเร็จ: {exc}", flush=True)
        return False
    except Exception as exc:
        print(f"[X] [{dev}] เปิดเกมผ่าน login.py ไม่สำเร็จ: {exc}", flush=True)
        return False


def recover_fixnet_ip(dev):
    """Reuse login.py's WireGuard recovery path when fixnet1 appears."""
    try:
        login, recovery = _login_wg_controller(dev)
    except Exception as exc:
        print(f"[!] [{dev}] โหลดระบบ WireGuard จาก login.py ไม่สำเร็จ: {exc}", flush=True)
        return False

    cfg = login.config
    if (not int(cfg.get("wg_enabled", 1) or 0)
            or not int(cfg.get("wg_fixnet1_switch", 1) or 0)):
        return False
    if int(cfg.get("wg_lock", 1) or 0):
        print(f"[WG] [{dev}] fixnet1 สั่งสลับ IP โดย override wg_lock เฉพาะเหตุการณ์นี้", flush=True)

    try:
        if not recovery._wg_is_up():
            return False
        recovery._wg_must_be_up()
        return recovery._wg_request_net_recover("fixnet1", switch_now=True, force_switch=True)
    except login.RestartTimeoutError as exc:
        print(f"[!] [{dev}] WireGuard recovery ต้อง restart: {exc}", flush=True)
        return False
    except Exception as exc:
        print(f"[!] [{dev}] เปลี่ยน IP จาก fixnet1 ไม่สำเร็จ: {exc}", flush=True)
        return False


def _tap(dev, x, y):
    adb(["shell", "input", "tap", str(int(x)), str(int(y))], device=dev)


def _wait_template(dev, name, timeout=30, thr=0.8):
    """รอจน template โผล่ (เจอก่อนค่อยทำต่อ) -> (found, cx, cy)"""
    end = time.time() + timeout
    while time.time() < end:
        img = grab_screen(dev)
        ok, cx, cy, _ = find_template(img, name, thr)
        if ok:
            return True, cx, cy
        time.sleep(1)
    return False, 0, 0


def checkline_sequence(dev):
    """พอร์ตจาก login.py: จับ checkline.png -> คลิก -> รอ check-l1 -> ติ๊ก 3 จุด
       -> รอ check-l4 คลิก -> รอ check-ok1 คลิก (ยืนยันด้วย template ทุกสเต็ป)"""
    print(f"[*] [{dev}] checkline.png -> รัน sequence (เจอก่อนค่อยติ๊ก)", flush=True)
    ok, cx, cy, _ = find_template(grab_screen(dev), "checkline.png", 0.8)
    if ok:
        _tap(dev, cx, cy)
    time.sleep(2)
    _wait_template(dev, "check-l1.png", timeout=40, thr=0.85)   # รอหน้าติ๊กโหลดก่อน
    for (x, y) in [(932, 133), (930, 253), (926, 327)]:          # ติ๊ก 3 ช่อง
        _tap(dev, x, y)
        time.sleep(2)
    found, cx, cy = _wait_template(dev, "check-l4.png", timeout=40, thr=0.8)
    if found:
        _tap(dev, cx, cy)
    found, cx, cy = _wait_template(dev, "check-ok1.png", timeout=40, thr=0.8)
    if found:
        _tap(dev, cx, cy)
        print(f"[*] [{dev}] checkline sequence เสร็จ", flush=True)


def handle_screen_flow(dev):
    """
    ตรวจจับและคลิกผ่านหน้าจออัตโนมัติ:
      1) Terms of Use: ติ๊กถูก 4 ช่อง + Agree
      2) Modal Dialogs (ตรวจก่อนปุ่มพื้นหลัง!):
         - ปุ่ม check.png (เช่น "Check internal resources")
         - ปุ่ม CHECK / OK สีเขียวตรงกลาง (เช่น "Check internal resources" หรือ "SELECT LANGUAGE")
         - ปุ่ม check-ok1..4, fixok
      3) หน้าต่าง Apple Sign In Webview: กด BACK 3 ครั้ง
      4) หน้าเลือกล็อกอิน:
         - ปุ่ม refresh.png (Guest Flow โดยตรง)
         - ปุ่ม apple.png (สำรอง)
      5) ทั่วไป: แตะตรงกลางหน้าจอ (480, 420) เป็นระยะ
    """
    try:
        res = subprocess.run([ADB, "-s", dev, "exec-out", "screencap", "-p"], capture_output=True)
        if not res.stdout or len(res.stdout) < 1000:
            return
        img = cv2.imdecode(np.frombuffer(res.stdout, np.uint8), cv2.IMREAD_COLOR)
        if img is None or img.shape[0] == 0:
            return

        fixnet1, fx, fy, score = find_template(img, "fixnet1.png", 0.8)
        if fixnet1:
            print(f"[*] [{dev}] พบ fixnet1 (score {score:.2f}) - ตรวจสอบการสลับ IP...", flush=True)
            if rotate_pc_wg(dev):                 # ขาออกจริงของเกม = mitm บน PC -> สลับ WG บน PC แล้วกดลองใหม่
                _tap(dev, fx, fy)
                time.sleep(2)
                return
            if recover_fixnet_ip(dev):
                return
            print(f"[*] [{dev}] ไม่ได้สลับ IP - กดปุ่ม fixnet1 ตามปกติ", flush=True)
            _tap(dev, fx, fy)
            time.sleep(0.6)
            return

        # 0. checkline.png (หน้าติ๊ก terms) - เจอก่อนค่อยรัน sequence แม่น ๆ (พอร์ตจาก login.py)
        ok_cl, _, _, _ = find_template(img, "checkline.png", 0.8)
        if ok_cl:
            checkline_sequence(dev)
            return

        # 1. เช็คหน้าจอ Terms of Use (มีแถบสีเขียว LINE GAME ด้านบน)
        if np.mean(img[:30, :, 1]) > 140 and np.mean(img[:30, :, 0]) < 60:
            # ตรวจว่ามี modal Close ค้างอยู่หรือไม่
            close_modal = img[200:360, 640:760]
            if np.sum((close_modal[:, :, 1] > 150) & (close_modal[:, :, 0] < 60)) > 50:
                adb(["shell", "input", "tap", "685", "289"], device=dev)
                time.sleep(0.3)
            # ติ๊กกล่องข้อตกลงทั้ง 4 ตำแหน่ง
            for pt in [(928, 142), (928, 260), (928, 340), (928, 405)]:
                adb(["shell", "input", "tap", str(pt[0]), str(pt[1])], device=dev)
                time.sleep(0.12)
            # หาปุ่ม Agree สีเขียวอัตโนมัติ (รองรับทั้งแบบ 3 กล่อง y~403 และแบบ 4 กล่อง y~484)
            agree_mask = (img[350:520, 350:580, 1] > 160) & (img[350:520, 350:580, 0] < 60) & (img[350:520, 350:580, 2] < 60)
            ys, xs = np.where(agree_mask)
            if len(ys) > 50:
                cx = 350 + int(np.mean(xs))
                cy = 350 + int(np.mean(ys))
                print(f"[*] [{dev}] Terms of Use -> กด Agree ({cx}, {cy})", flush=True)
                adb(["shell", "input", "tap", str(cx), str(cy)], device=dev)
            else:
                adb(["shell", "input", "tap", "437", "408"], device=dev)
            time.sleep(0.5)
            return

        # 2. เช็ค Modal / Popups ในกล่องกลางจอ (ต้องตรวจก่อนปุ่มเบื้องหลัง เช่น refresh.png)
        # 2.1 ตรวจ template check.png
        tpl_check = get_template("check.png")
        if tpl_check is not None:
            m = cv2.matchTemplate(img, tpl_check, cv2.TM_CCOEFF_NORMED)
            _, max_v, _, max_l = cv2.minMaxLoc(m)
            if max_v >= 0.80:
                cx = max_l[0] + tpl_check.shape[1] // 2
                cy = max_l[1] + tpl_check.shape[0] // 2
                print(f"[*] [{dev}] ตรวจพบปุ่ม check.png -> กด ({cx}, {cy})", flush=True)
                adb(["shell", "input", "tap", str(cx), str(cy)], device=dev)
                time.sleep(0.6)
                return

        # 2.2 ตรวจปุ่มสีเขียวตรงกลางหน้าจอ (Check internal resources / SELECT LANGUAGE)
        sub = img[350:460, 360:600]
        green_mask = (sub[:, :, 1] > 160) & (sub[:, :, 0] < 80) & (sub[:, :, 2] < 80)
        if np.sum(green_mask) > 300:
            ys, xs = np.where(green_mask)
            cx = 360 + int(np.mean(xs))
            cy = 350 + int(np.mean(ys))
            print(f"[*] [{dev}] ตรวจพบปุ่มสีเขียว modal -> กด ({cx}, {cy})", flush=True)
            adb(["shell", "input", "tap", str(cx), str(cy)], device=dev)
            time.sleep(0.6)
            return

        # 2.3 ตรวจ check-ok1..4
        for ok_name in ["check-ok1.png", "check-ok2.png", "check-ok3.png", "check-ok4.png", "fixok.png"]:
            tpl_ok = get_template(ok_name)
            if tpl_ok is not None:
                m = cv2.matchTemplate(img, tpl_ok, cv2.TM_CCOEFF_NORMED)
                _, max_v, _, max_l = cv2.minMaxLoc(m)
                if max_v >= 0.80:
                    cx = max_l[0] + tpl_ok.shape[1] // 2
                    cy = max_l[1] + tpl_ok.shape[0] // 2
                    print(f"[*] [{dev}] ตรวจพบ {ok_name} -> กด ({cx}, {cy})", flush=True)
                    adb(["shell", "input", "tap", str(cx), str(cy)], device=dev)
                    time.sleep(0.6)
                    return

        # 3. เช็คหน้าจอ Apple Sign In Webview
        is_white_top = np.mean(img[:50, 100:300]) > 240
        black_apple_pixels = np.sum((img[:100, :100, 0] < 60) & (img[:100, :100, 1] < 60) & (img[:100, :100, 2] < 60))
        if is_white_top and black_apple_pixels > 150:
            print(f"[*] [{dev}] ตรวจพบหน้าต่าง Apple Webview -> กด BACK 3 ครั้ง...", flush=True)
            for _ in range(3):
                adb(["shell", "input", "keyevent", "4"], device=dev)
                time.sleep(0.3)
            time.sleep(1)
            return

        # 4. ปุ่ม refresh.png (ไอคอนลูกศรหมุนวนมุมขวาล่างที่หน้าเลือกล็อกอิน เพื่อเข้า Guest Flow)
        tpl_refresh = get_template("refresh.png")
        if tpl_refresh is not None:
            m = cv2.matchTemplate(img, tpl_refresh, cv2.TM_CCOEFF_NORMED)
            _, max_v, _, max_l = cv2.minMaxLoc(m)
            if max_v >= 0.85:
                cx = max_l[0] + tpl_refresh.shape[1] // 2
                cy = max_l[1] + tpl_refresh.shape[0] // 2
                print(f"[*] [{dev}] กดปุ่ม Refresh ({cx}, {cy}) เพื่อเข้า Guest...", flush=True)
                adb(["shell", "input", "tap", str(cx), str(cy)], device=dev)
                time.sleep(0.8)
                return

        # 5. ปุ่ม Apple Sign In (apple.png)
        tpl_apple = get_template("apple.png")
        if tpl_apple is not None:
            m = cv2.matchTemplate(img, tpl_apple, cv2.TM_CCOEFF_NORMED)
            _, max_v, _, max_l = cv2.minMaxLoc(m)
            if max_v >= 0.85:
                cx = max_l[0] + tpl_apple.shape[1] // 2
                cy = max_l[1] + tpl_apple.shape[0] // 2
                print(f"[*] [{dev}] กดปุ่ม Apple Sign In ({cx}, {cy})...", flush=True)
                adb(["shell", "input", "tap", str(cx), str(cy)], device=dev)
                time.sleep(1)
                return

        # 6. ทั่วไป: แตะตรงกลางหน้าจอเป็นระยะเพื่อผ่านไตเติล
        adb(["shell", "input", "tap", "480", "420"], device=dev)
    except Exception as e:
        print(f"[!] handle_screen_flow error: {e}", flush=True)


# ---------- mitm + capture helpers ----------
_WG_TUNNEL_LOCK = threading.Lock()
_WG_ROT_T = [0.0]


def _port_open(port):
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def _ensure_wg_tunnel():
    """WG tunnel 127.0.0.1:9443 -> rangers-api (wireproxy) ให้ mitm ออกเน็ต ; web_app เปิดไว้แล้วก็ใช้ร่วม"""
    with _WG_TUNNEL_LOCK:
        if _port_open(9443):
            return "127.0.0.1:9443"
        try:
            import web_app
            conf = web_app.wg_ensure()
            if conf:
                print(f"[*] mitm ออกเน็ตผ่าน WG: {conf}", flush=True)
                return "127.0.0.1:9443"
        except Exception as e:
            print(f"[!] เปิด WG tunnel ไม่ได้ ({e})", flush=True)
        print("[!] ไม่มี WG tunnel - mitm ต่อตรงด้วย IP ของ PC", flush=True)
        return ""


def rotate_pc_wg(dev):
    """เกมขึ้น fixnet1 = IP ขาออกของ mitm (WG บน PC) โดนบล็อก -> สลับ WG บน PC (30 วิ ครั้งเดียว)"""
    if time.time() - _WG_ROT_T[0] < 30:
        return True
    _WG_ROT_T[0] = time.time()
    print(f"[WG] [{dev}] fixnet1 -> สลับ WG บน PC (ขาออกของ mitm)", flush=True)
    try:
        if _port_open(8770):                 # web_app เป็นเจ้าของ wireproxy -> สั่งผ่านเว็บ
            import urllib.request
            r = json.load(urllib.request.urlopen("http://127.0.0.1:8770/api/wg?rotate=1", timeout=300))
            conf = r.get("conf")
        else:
            import web_app
            conf = web_app.wg_rotate()
        print(f"[WG] [{dev}] ใช้ WG ใหม่: {conf or 'หาไม่ได้'}", flush=True)
        _WG_ROT_T[0] = time.time()
        return bool(conf)
    except Exception as e:
        print(f"[!] [{dev}] สลับ WG บน PC ไม่ได้: {e}", flush=True)
        return False


def start_mitm(mitmdump, host_port=PORT, creds_file=None):
    print(f"[*] เริ่ม mitmdump reverse-proxy host:{host_port} + addon ...", flush=True)
    env = dict(os.environ)
    if creds_file:
        env["LGR_CREDS_FILE"] = creds_file       # addon เขียน creds ไฟล์แยกต่อจอ (ไม่แย่ง .lock)
    tunnel = _ensure_wg_tunnel()
    if tunnel:
        env["LGR_WG_TUNNEL"] = tunnel            # mitm ออกเน็ตผ่าน WG บน PC
    p = subprocess.Popen(
        [mitmdump, "--mode", f"reverse:https://{API_HOST}",
         "--listen-port", str(host_port), "-s", ADDON, "-q"],
        cwd=HERE, env=env,
    )
    time.sleep(3)  # ให้ proxy ตั้งตัว
    return p


def stop_mitm(proc):
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def guest_login_flow(dev):
    """ขับปุ่มสร้าง guest ใหม่จริง (ลำดับยืนยันจาก screenshot 960x540):
       ⟳ refresh -> CHECK (resource) -> GUEST Login -> Log in (ยืนยัน) -> Terms
       เกมจะทำ Trident handshake สร้าง guest ใหม่ + ยิง /login เอง"""
    def tap(x, y, w=0.0):
        adb(["shell", "input", "tap", str(x), str(y)], device=dev)
        if w: time.sleep(w)
    print("[*] ขับ GUEST Login flow (สร้าง id ใหม่)...", flush=True)
    tap(895, 483, 3)     # ⟳ refresh -> โผล่ GUEST Login + resource modal
    tap(475, 410, 4)     # CHECK internal resources
    tap(480, 483, 3)     # GUEST Login
    tap(553, 408, 4)     # "Log in" ยืนยัน (Really login as guest?)
    # Terms of Use (ถ้าโผล่): ติ๊ก 4 ช่อง + Agree
    for pt in [(928, 142), (928, 260), (928, 340), (928, 405)]:
        tap(pt[0], pt[1], 0.15)
    tap(437, 484, 1)     # Agree (4-box)
    tap(437, 408, 1)     # Agree (3-box)


def capture_account(dev, xml_path, timeout, use_login, creds_file=None, to_lv3=False):
    """
    จับ credential ของ 1 บัญชี:
      1) inject XML (ถ้ามี) หรือ สร้าง guest ใหม่ (guest_login_flow)
      2) เปิดเกม
      3) วนตรวจหน้าจอ + รอจน creds.json มี udid/key นี้ และได้ LF_AC
      4) force-stop เกมทันทีเพื่อตรึง session
    คืนค่า (is_success, key, cred_dict)
    """
    target_udid = None
    if xml_path:
        target_udid = extract_udid_from_xml(xml_path)
        ok_inject = inject_xml(dev, xml_path)
        if not ok_inject:
            print(f"[X] [{dev}] ส่งไฟล์เข้าเกมไม่สำเร็จ! -> ข้ามไฟล์ {os.path.basename(xml_path)}", flush=True)
            return False, None, None
        print(f"[OK] [{dev}] ส่งไฟล์เข้าเกมสำเร็จเรียบร้อย -> กำลังเปิดเกม...", flush=True)

    before_creds = load_creds(creds_file)
    prev_entry = None
    if target_udid:
        for k, v in before_creds.items():
            if v.get("udid") == target_udid:
                prev_entry = v
                break

    login_proc = None
    if use_login:
        login_proc = launch_login_py(dev)
    elif not xml_path:
        # สร้าง guest ใหม่: เซฟบัญชีเดิมก่อน -> ลบ _LINE_COCOS_PREF_KEY.xml -> เปิดเกม -> GUEST Login
        pull_before_wipe(dev)                 # save ก่อน delete (กันตกบัญชีเดิม)
        wipe_account(dev)                     # ลบ _LINE_COCOS_PREF_KEY.xml + session -> เกมไม่มีบัญชีค้าง
        opened = open_game_like_login(dev)
        if opened is None:
            return None, None, None
        if not opened:
            return False, None, None
        time.sleep(22)
        guest_login_flow(dev)
    else:
        force_stop_game(dev)
        opened = open_game_like_login(dev)
        if opened is None:
            return None, None, None
        if not opened:
            return False, None, None

    print(f"[*] รอจับ credential (สูงสุด {timeout}s | udid={target_udid or 'auto'})...", flush=True)
    deadline = time.time() + timeout
    captured_key = None
    captured_data = None

    last_screen_handle = 0
    last_guest_drive = time.time()   # เพิ่ง drive guest flow ไปตอนเริ่ม
    while time.time() < deadline:
        creds = load_creds(creds_file)

        # ตรวจสอบว่า target_udid ได้รับ LF_AC ใหม่แล้วหรือยัง
        if target_udid:
            for k, v in creds.items():
                if v.get("udid") == target_udid and v.get("LF_AC"):
                    # สำคัญมาก: ต้องรอจนกว่าจะได้ guestCookie หรือ rsn (ผ่านหน้า /login จริง)
                    # ถ้าเพิ่งได้แค่ nation.nhn (ยังไม่มี guestCookie) อย่าเพิ่ง force-stop เพราะ session ยังไม่สมบูรณ์
                    has_login = bool(v.get("guestCookie") or (v.get("rsn") and len(k) < 32))
                    if has_login and ((not prev_entry) or (v.get("LF_AC") != prev_entry.get("LF_AC")) or (v.get("guestCookie") != prev_entry.get("guestCookie")) or (not prev_entry.get("guestCookie"))):
                        captured_key = k
                        captured_data = v
                        break
        else:
            diff = set(creds.keys()) - set(before_creds.keys())
            for k in diff:
                v = creds[k]
                has_login = bool(v.get("guestCookie") or (v.get("rsn") and len(k) < 32))
                if has_login:
                    captured_key = k
                    captured_data = v
                    break

        if captured_key:
            # จับได้แล้ว: รอ 2 วิ เก็บ Set-Cookie รอบสุดท้าย
            time.sleep(2)
            if to_lv3:
                # --to-lv3: อย่าเพิ่ง force-stop — ปล่อยเกมเล่น tutorial ต่อจนถึง Lv3
                # (ระหว่างเล่น เกมยิง /login เรื่อย ๆ -> capture_credential addon เขียน
                #  LF_AC/guestCookie ใหม่ลง creds.json ให้อัตโนมัติ = ได้ guestCookie + สถานะ Lv3)
                print("[*] จับ cred แรกได้ -> โหมด --to-lv3: เล่น tutorial ต่อ (ยังไม่ force-stop)", flush=True)
                play_until_stop(dev)
                time.sleep(2)
                print("[*] จบ tutorial -> force-stop ตรึง session (Lv3)", flush=True)
            else:
                print("[*] จับได้แล้ว! สั่ง force-stop เกมทันที เพื่อตรึง LF_AC ไม่ให้หมุนทิ้ง", flush=True)
            force_stop_game(dev)
            creds = load_creds(creds_file)
            captured_data = creds.get(captured_key, captured_data)
            break

        # ถ้าไม่ใช้ login.py: ตรวจจับและคลิกผ่านหน้าจออัตโนมัติทุก 2.5 วิ
        now = time.time()
        if not use_login and (now - last_screen_handle >= 2.5):
            handle_screen_flow(dev)
            last_screen_handle = now

        # โหมดสร้าง guest (ไม่มี xml): ถ้ายังไม่จับได้ ให้กดชุด GUEST Login ซ้ำทุก ~22s
        # (กันค้างวน refresh/check โดยไม่กดปุ่ม GUEST Login + ยืนยัน)
        if (not use_login) and (xml_path is None) and (now - last_guest_drive >= 22):
            guest_login_flow(dev)
            last_guest_drive = time.time()

        time.sleep(1.2)

    if login_proc and login_proc.poll() is None:
        login_proc.terminate()

    if captured_key:
        return True, captured_key, captured_data

    # หมดเวลา
    print(f"[X] หมดเวลา ({timeout}s) สำหรับบัญชีนี้", flush=True)
    force_stop_game(dev)
    return False, None, None


# ---------- queue batch processor ----------
def process_xml_queue(dev, xml_input, mitmdump, use_login, timeout, action_on_finish="move", host_port=PORT,
                      progress_events=None):
    # จอนี้เป็นเจ้าของ part ของตัวเองตลอดการจับ -> merge แบบ glob จากโปรเซสอื่นไม่ลบ part กลางคัน
    with _api_part_owner(part_creds(host_port)):
        return _process_xml_queue(dev, xml_input, mitmdump, use_login, timeout, action_on_finish,
                                  host_port, progress_events)


def _process_xml_queue(dev, xml_input, mitmdump, use_login, timeout, action_on_finish, host_port,
                       progress_events):
    global _ROOT_ADBD
    _ROOT_ADBD = enable_root(dev) or _ROOT_ADBD
    creds_file = part_creds(host_port)          # ไฟล์ creds แยกต่อจอ
    try:
        setup_routing(dev, host_port)           # RoutingConflict -> หยุดจอนี้ (ไม่แตะของคนอื่น)
    except Exception:
        teardown_routing(dev)                   # ล้มกลางทาง -> ถอนเฉพาะที่ตั้งได้แล้ว
        raise
    mitm = start_mitm(mitmdump, host_port, creds_file)

    success_list = []
    failed_list = []

    try:
        while True:
            if isinstance(xml_input, queue.Queue):
                try:
                    item = xml_input.get_nowait()
                except queue.Empty:
                    break
                i, total, xml_path = item
            elif isinstance(xml_input, list):
                if not xml_input:
                    break
                xml_path = xml_input.pop(0)
                i = len(success_list) + len(failed_list) + 1
                total = i + len(xml_input)
            else:
                break

            fname = os.path.basename(xml_path)
            print(f"\n===== [{dev}][{i}/{total}] {fname} =====", flush=True)
            if progress_events:
                progress_events.put(("start", fname, dev, i, total))
            ok, key, cred = capture_account(dev, xml_path, timeout, use_login, creds_file)

            if ok is None:
                print(f"[SKIP] [{dev}] ไม่จัดไฟล์เป็น login-failed; worker นี้หยุดเพราะ device identity ซ้ำ", flush=True)
                if progress_events:
                    progress_events.put(("skip", fname, dev, "device identity ซ้ำ"))
                if isinstance(xml_input, queue.Queue):
                    xml_input.put(item)
                elif isinstance(xml_input, list):
                    xml_input.insert(0, xml_path)
                if isinstance(xml_input, queue.Queue):
                    xml_input.task_done()
                break

            if ok:
                info = fetch_account_info(cred, fname, creds_file)
                success_list.append((fname, key, cred, info))
                print(f"[OK] [{dev}] id={key} | {fname} | ruby={info['ruby']} "
                      f"| ticket={info['ticket']} | Lv {info['level']}", flush=True)
                try:
                    merge_parts_into_creds([creds_file])
                except Exception:
                    pass
                if action_on_finish == "move":
                    handle_success_file(xml_path, dev)
                elif action_on_finish == "delete":
                    try:
                        os.remove(xml_path)
                    except Exception:
                        pass
                if progress_events:
                    progress_events.put(("finish", "success", fname, key, dev))
            else:
                failed_list.append(fname)
                if action_on_finish == "move":
                    handle_failure_file(xml_path, dev)
                elif action_on_finish == "delete":
                    try:
                        os.remove(xml_path)
                        print(f"[X] [{dev}] {fname} เข้าไม่ได้ -> ลบทิ้ง", flush=True)
                    except Exception:
                        print(f"[X] [{dev}] {fname} เข้าไม่ได้ (ลบไม่สำเร็จ)", flush=True)
                if progress_events:
                    progress_events.put(("finish", "failed", fname, "", dev))

            if isinstance(xml_input, queue.Queue):
                xml_input.task_done()

            time.sleep(1)

    finally:
        stop_mitm(mitm)
        teardown_routing(dev)

    return success_list, failed_list


def run_xml_batch(devices, xml_files, mitmdump, args, action_on_finish, progress_events=None):
    import concurrent.futures as cf

    device_count = len(devices)
    jobs = max(1, min(args.jobs, device_count))
    work_queue = queue.Queue()
    total_files = len(xml_files)
    for index, path in enumerate(xml_files, 1):
        work_queue.put((index, total_files, path))

    print(f"[*] พบ {total_files} ไฟล์ | {device_count} จอ | รันพร้อมกัน {jobs} จอ/รอบ (คิวแชร์อัตโนมัติเหมือน login.py)", flush=True)
    results = [([], []) for _ in range(device_count)]

    def worker(index):
        device = devices[index]
        if index > 0 and args.stagger > 0:
            delay = index * args.stagger
            print(f"[*] [{device}] หน่วงเวลาปล่อยจอ {delay}s เพื่อไม่ให้แย่งกันตอนเริ่ม (เหมือน login.py thread_delay)...", flush=True)
            time.sleep(delay)
        try:
            results[index] = process_xml_queue(
                device, work_queue, mitmdump, args.use_login, args.timeout,
                action_on_finish, PORT + index, progress_events,
            )
        except Exception as exc:
            print(f"[X] [{device}] worker error: {exc}", flush=True)
        try:
            merge_parts_into_creds([part_creds(PORT + index)])
        except Exception:
            pass

    with cf.ThreadPoolExecutor(max_workers=jobs) as executor:
        list(executor.map(worker, range(device_count)))
    try:
        merge_parts_into_creds()
    except Exception:
        pass

    successes = [item for result in results for item in result[0]]
    failures = [item for result in results for item in result[1]]
    print(f"\n[*] creds.json รวม {len(load_creds())} บัญชี", flush=True)
    success_action = "ย้ายไป " + OUTPUT_DIR if action_on_finish == "move" else ("ลบออกจาก input-id" if action_on_finish == "delete" else "คงไฟล์ไว้")
    fail_action = "ย้ายไป " + FAILED_DIR if action_on_finish == "move" else ("ลบออกจาก input-id" if action_on_finish == "delete" else "คงไฟล์ไว้")
    print("\n" + "=" * 55, flush=True)
    print("สรุปการทำงาน:", flush=True)
    print(f"  - สำเร็จ: {len(successes)} ไฟล์ ({success_action})", flush=True)
    print(f"  - ล้มเหลว: {len(failures)} ไฟล์ ({fail_action})", flush=True)
    print(f"  - ข้าม/ยังไม่ทำ: {work_queue.qsize()} ไฟล์", flush=True)
    for fname, key, cred, info in successes:
        print(f"    - {key:<10} | {fname} | ruby={info.get('ruby', 0)} | ticket={info.get('ticket', 0)}", flush=True)
    print("=" * 55, flush=True)
    return len(successes), len(failures)


class CaptureProgressWindow:
    def __init__(self, input_total, run_total, devices):
        self.root = tk.Tk()
        self.root.title("LINE Rangers Credential Capture")
        self.root.geometry("850x520")
        self.root.minsize(680, 420)
        self.events = queue.Queue()
        self.input_total = input_total
        self.run_total = run_total
        self.completed = 0
        self.successes = 0
        self.failures = 0
        self.current = "กำลังเตรียมงาน..."
        self.finished = False

        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Credential Capture", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(outer, text=f"พบ XML ใน input: {input_total}    รอบนี้: {run_total}    อุปกรณ์: {', '.join(devices)}").pack(anchor="w", pady=(6, 12))

        self.progress_text = tk.StringVar(value=f"ทำแล้ว 0 / {run_total} ID")
        ttk.Label(outer, textvariable=self.progress_text, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.progress = ttk.Progressbar(outer, maximum=max(1, run_total), mode="determinate")
        self.progress.pack(fill="x", pady=(6, 10))

        self.summary_text = tk.StringVar(value="สำเร็จ 0    ล้มเหลว 0    เหลือ 0")
        ttk.Label(outer, textvariable=self.summary_text).pack(anchor="w")
        self.current_text = tk.StringVar(value=self.current)
        ttk.Label(outer, textvariable=self.current_text, wraplength=800).pack(anchor="w", pady=(6, 10))

        columns = ("index", "file", "device", "result")
        self.rows = ttk.Treeview(outer, columns=columns, show="headings", height=14)
        self.rows.heading("index", text="#")
        self.rows.heading("file", text="XML / ID")
        self.rows.heading("device", text="อุปกรณ์")
        self.rows.heading("result", text="ผล")
        self.rows.column("index", width=48, anchor="center", stretch=False)
        self.rows.column("file", width=480)
        self.rows.column("device", width=140, stretch=False)
        self.rows.column("result", width=130, stretch=False)
        self.rows.pack(fill="both", expand=True)

        self.close_button = ttk.Button(outer, text="ปิด", command=self.root.destroy, state="disabled")
        self.close_button.pack(anchor="e", pady=(10, 0))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        if self.finished:
            self.root.destroy()

    def start(self, worker):
        def run():
            try:
                worker(self.events)
                self.events.put(("complete",))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=run, daemon=True).start()
        self.root.after(100, self._poll)
        self.root.mainloop()

    def _poll(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == "start":
                _, filename, device, index, total = event
                self.current = f"กำลังทำ {index}/{total}: {filename}  [{device}]"
                self.current_text.set(self.current)
            elif kind == "finish":
                _, result, filename, account_id, device = event
                self.completed += 1
                if result == "success":
                    self.successes += 1
                    status = f"สำเร็จ ({account_id})"
                else:
                    self.failures += 1
                    status = "ล้มเหลว"
                self.rows.insert("", "end", values=(self.completed, filename, device, status))
                self.progress.configure(value=min(self.completed, self.run_total))
                self.progress_text.set(f"ทำแล้ว {self.completed} / {self.run_total} ID")
                self.summary_text.set(f"สำเร็จ {self.successes}    ล้มเหลว {self.failures}    เหลือ {max(0, self.run_total - self.completed)}")
            elif kind == "skip":
                _, filename, device, reason = event
                self.rows.insert("", "end", values=("-", filename, device, f"ข้าม: {reason}"))
                self.current_text.set(f"หยุด worker [{device}]: {reason}; XML คงอยู่ในคิว")
            elif kind == "error":
                self.current_text.set(f"เกิดข้อผิดพลาด: {event[1]}")
            elif kind == "complete":
                self.finished = True
                self.current_text.set("เสร็จสิ้น")
                self.close_button.configure(state="normal")
                self.root.title("LINE Rangers Credential Capture - เสร็จสิ้น")
        if not self.finished:
            self.root.after(100, self._poll)


# ---------- เล่น tutorial ต่อจนถึง Lv3 (พอร์ตจาก main.py: norandom-reid) ----------
# เปิดด้วย --to-lv3 ; ปรับค่าได้ด้วย env (ไม่ต้องแก้โค้ด)
LV3_PLAY_TIMEOUT = int(os.environ.get("LV3_PLAY_TIMEOUT", "240"))   # เพดานเวลาเล่น/บัญชี (วิ)
LV3_STOPS = int(os.environ.get("LV3_STOPS", "1"))                   # เจอ clearstage4 (STOP) กี่ครั้ง = พอ (จบด่าน tutorial)
LV3_THR = float(os.environ.get("LV3_THR", "0.84"))                 # ค่า match template (0-1)

# template ด่าน (ก๊อปจาก norandom-reid มาไว้ img/tut_*.png) : เจอรูปไหนก่อน = ทำ action นั้น
# herodrag* = ลาก (swipe, coord ตายตัวจาก main.py) ; ที่เหลือ = แตะ (tap ตรงกลาง template)
_TUT_SWIPE = {
    "tut_herodrag.png":  ("484", "200", "503", "387"),
    "tut_herodrag1.png": ("142", "440", "474", "191"),
}
_TUT_TAP = [
    "tut_mainstage.png", "tut_start.png", "tut_stageok.png",
    "tut_nextstage1-1.png", "tut_nextstage1.png",
    "tut_clearstage1.png", "tut_clearstage2.png", "tut_clearstage3.png", "tut_clearstage5.png",
    "tut_heroo1.png", "tut_okwhite.png", "tut_okgust.png", "tut_ok.png",
    "tut_gacha.png", "tut_gachaok.png",
]


def play_until_stop(dev, max_seconds=None, target_stops=None, thr=None):
    """เล่น tutorial ด้วย template-tap/swipe จนเจอ clearstage4 (STOP) ครบ target_stops ครั้ง (~จบด่าน -> Lv3).
       ไม่ force-stop เกมให้ (ผู้เรียกจัดการต่อ). คืน True ถ้าถึง STOP ครบ, False ถ้าหมดเวลา.
       ** v1 พอร์ตจาก main.py (norandom-reid) — thr/จำนวน STOP/เวลา ปรับได้ด้วย env (LV3_THR/LV3_STOPS/LV3_PLAY_TIMEOUT) **"""
    max_seconds = LV3_PLAY_TIMEOUT if max_seconds is None else max_seconds
    target_stops = LV3_STOPS if target_stops is None else target_stops
    thr = LV3_THR if thr is None else thr
    print(f"[play] [{dev}] เริ่มเล่น tutorial -> รอ STOP x{target_stops} (เพดาน {max_seconds}s, thr={thr})", flush=True)
    stops = 0
    deadline = time.time() + max_seconds
    last_action = time.time()
    while time.time() < deadline:
        img = grab_screen(dev)
        if img is None:
            time.sleep(1.0)
            continue
        # STOP (จบด่าน) ตรวจก่อนเสมอ
        ok, _, _, sc = find_template(img, "tut_clearstage4.png", thr)
        if ok:
            stops += 1
            print(f"[play] [{dev}] STOP (clearstage4) #{stops} (score={sc:.2f})", flush=True)
            last_action = time.time()
            if stops >= target_stops:
                print(f"[play] [{dev}] ถึงเป้า STOP x{target_stops} -> จบการเล่น", flush=True)
                return True
            time.sleep(6)   # ปล่อยหน้าจบด่าน/รับของเล่นให้จบก่อนไปต่อ
            continue
        acted = False
        # หา swipe ก่อน (ลากฮีโร่ลงสนาม)
        for name, (x1, y1, x2, y2) in _TUT_SWIPE.items():
            found, _, _, _ = find_template(img, name, thr)
            if found:
                adb(["shell", "input", "swipe", x1, y1, x2, y2, "100"], device=dev)
                print(f"[play] [{dev}] swipe {name} ({x1},{y1})->({x2},{y2})", flush=True)
                acted = True
                last_action = time.time()
                time.sleep(1.2)
                break
        if acted:
            continue
        # แล้วค่อยหา tap (เจออันแรกในลิสต์ก่อน)
        for name in _TUT_TAP:
            found, cx, cy, _ = find_template(img, name, thr)
            if found:
                adb(["shell", "input", "tap", str(cx), str(cy)], device=dev)
                print(f"[play] [{dev}] tap {name} ({cx},{cy})", flush=True)
                acted = True
                last_action = time.time()
                time.sleep(1.5)
                break
        if not acted:
            if time.time() - last_action > 30:
                print(f"[play] [{dev}] ไม่พบปุ่ม tutorial > 30s (จอโหลด/ค้าง หรือ template ไม่ตรง) ...", flush=True)
                last_action = time.time()
            time.sleep(1.2)
    print(f"[play] [{dev}] หมดเวลา {max_seconds}s — เล่นไม่ถึง STOP x{target_stops} (stops={stops})", flush=True)
    return False


# ---------- reroll loop (สร้าง guest ใหม่เองวน ๆ) ----------
def reroll_loop(dev, count, mitmdump, use_login, timeout, to_lv3=False):
    """วนสร้างบัญชี guest ใหม่เอง count รอบ:
       ล้างบัญชี -> เปิดเกม (เกมสร้าง guest ใหม่) -> ผ่านจอ auto -> ดัก creds -> pull .xml
       คืน (success_list, failed)"""
    global _ROOT_ADBD
    _ROOT_ADBD = enable_root(dev)
    print(f"[*] root adbd = {'YES' if _ROOT_ADBD else 'no (จะลอง su แทน)'}", flush=True)
    if not _ROOT_ADBD:
        print("[!] ไม่ได้ root — ล้างบัญชี/สร้าง guest ใหม่อาจไม่ได้", flush=True)

    try:
        setup_routing(dev)
    except Exception as exc:
        print(f"[X] {exc}", flush=True)
        teardown_routing(dev)                   # ถอนเฉพาะที่ตั้งได้แล้ว (ถ้ามี)
        return [], count
    mitm = start_mitm(mitmdump)
    success, failed = [], 0
    try:
        for i in range(1, count + 1):
            print(f"\n===== [reroll {i}/{count}] สร้าง guest ใหม่ =====", flush=True)
            # capture_account (xml_path=None) จะ pull บัญชีเดิม -> wipe -> สร้างใหม่ ให้เอง
            ok, key, cred = capture_account(dev, None, timeout, use_login, to_lv3=to_lv3)
            if not ok:
                failed += 1
                print(f"[X] รอบ {i}: จับ credential ไม่สำเร็จ ข้าม", flush=True)
                continue
            # จับได้ -> เกม force-stop แล้ว pref ยังอยู่บนดิสก์ -> pull .xml ออกมา
            xml = pull_account_xml(dev, key)
            xml_fname = os.path.basename(xml) if xml else None
            info = fetch_account_info(cred, xml_fname)
            success.append((key, cred, xml, info))
            print(f"[OK] รอบ {i}: id={key} | file={xml_fname or '-'} | ruby={info['ruby']} | ticket={info['ticket']} "
                  f"| .xml={'saved' if xml else 'FAIL'}", flush=True)
    finally:
        stop_mitm(mitm)
        teardown_routing(dev)
    return success, failed


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description="Auto capture LGR credential from XML files into creds.json")
    ap.add_argument("--device", help="serial เช่น 127.0.0.1:16512 หรือ emulator-5556 (ไม่ใส่ = auto-detect)")
    ap.add_argument("--input-dir", default="input-id", help="โฟลเดอร์เก็บไฟล์ XML บัญชี (default: input-id)")
    ap.add_argument("--use-login", action="store_true", help="ใช้ login.py ช่วยกดผ่านหน้า PLAY อัตโนมัติ")
    ap.add_argument("--timeout", type=int, default=50, help="รอจับ credential กี่วินาทีต่อไฟล์ (default 50)")
    ap.add_argument("--jobs", type=int, default=4, help="จำนวนจอที่รันพร้อมกัน (default 4 กันเน็ต/CPU ดึงจนล็อกอินไม่ทัน)")
    ap.add_argument("--stagger", type=int, default=5,
                    help="หน่วงเวลาระหว่างเริ่มแต่ละจอกี่วินาที กันแย่ง ADB/ฉีดไฟล์ชนกัน (default: 5 เหมือน thread_delay ใน login.py)")
    ap.add_argument("--no-move", "--no-delete", dest="no_move", action="store_true",
                    help="คงไฟล์ไว้ที่เดิม ไม่ย้ายไฟล์ไป login-success/ หรือ login-failed/")
    ap.add_argument("--delete", action="store_true",
                    help="ลบไฟล์ XML ทิ้งแทนการย้ายไป login-success/login-failed")
    ap.add_argument("--single", action="store_true", help="ทำแค่ไฟล์แรกไฟล์เดียวแล้วหยุด (ใช้ทดสอบ)")
    ap.add_argument("--limit", type=int, default=0, help="จำกัดจำนวนไฟล์ที่จะทำ (0 = ทำทั้งหมด)")
    ap.add_argument("--reroll", type=int, default=0, metavar="N",
                    help="โหมดรีสร้าง: วนสร้าง guest ใหม่เอง N รอบ -> creds.json + .xml (login-success/)")
    ap.add_argument("--no-gui", action="store_true", help="รันใน console โดยไม่เปิดหน้าต่าง progress")
    ap.add_argument("--to-lv3", action="store_true",
                    help="(reroll) หลังจับ cred แรก เล่น tutorial ต่อจนถึง Lv3 ค่อย force-stop "
                         "(ปรับ env LV3_STOPS/LV3_THR/LV3_PLAY_TIMEOUT ได้)")
    args = ap.parse_args()

    mitmdump = find_mitmdump()
    if not mitmdump:
        sys.exit("[X] ไม่พบ mitmdump — ติดตั้งก่อน: pip install mitmproxy")
    print(f"[*] mitmdump = {mitmdump}", flush=True)
    if not os.path.exists(ADDON):
        sys.exit(f"[X] ไม่พบ addon: {ADDON}")

    if args.device:
        devices = [args.device]
    else:
        devices = dedupe_device_aliases(list_devices())
        if not devices:
            sys.exit("[X] ไม่พบ emulator ที่มี fingerprint ใช้งานได้")
    dev = devices[0]
    print(f"[*] เครื่องที่จะใช้งาน: {dev} (ทั้งหมดที่พบ: {devices})", flush=True)

    # รวม creds.part*.json ที่อาจค้างอยู่จากรอบก่อนเข้า creds.json ทันที
    try:
        import atexit
        atexit.register(lambda: merge_parts_into_creds())
        merge_parts_into_creds()
    except Exception:
        pass

    # ---- โหมดรีสร้าง guest ใหม่เอง (reroll) ----
    if args.reroll and args.reroll > 0:
        print(f"[*] โหมด REROLL: จะสร้าง guest ใหม่เอง {args.reroll} รอบ"
              + (" + เล่นถึง Lv3" if args.to_lv3 else ""), flush=True)
        success, failed = reroll_loop(dev, args.reroll, mitmdump, args.use_login, args.timeout, to_lv3=args.to_lv3)
        print("\n" + "=" * 55, flush=True)
        print(f"สรุป REROLL: สำเร็จ {len(success)} / ล้มเหลว {failed} (จาก {args.reroll} รอบ)", flush=True)
        for key, cred, xml, info in success:
            fname = os.path.basename(xml) if xml else '-'
            print(f"    - {key:<12} | {fname} | ruby={info.get('ruby', 0)} | ticket={info.get('ticket', 0)}", flush=True)
        print(f"\n.xml เก็บที่: {OUTPUT_DIR}", flush=True)
        print(f"creds เก็บที่: {CREDS}  -> ต่อด้วย: python collect_all.py", flush=True)
        print("=" * 55, flush=True)
        return

    # ค้นหาไฟล์ XML ใน input-dir (ค้นหาทั้ง ROOT, CWD และโฟลเดอร์ย่อย recursive)
    xml_files = []
    input_path = None
    candidates = [
        args.input_dir if os.path.isabs(args.input_dir) else os.path.join(ROOT, args.input_dir),
        os.path.join(os.getcwd(), args.input_dir),
        args.input_dir,
        os.path.join(ROOT, "input-id"),
        os.path.join(os.getcwd(), "input-id"),
        os.path.join(ROOT, "backup"),
        os.path.join(os.getcwd(), "backup"),
    ]
    seen_cand = set()
    for cand in candidates:
        cand_abs = os.path.abspath(cand)
        if cand_abs in seen_cand or not os.path.exists(cand_abs):
            continue
        seen_cand.add(cand_abs)
        found = []
        for r, _, fs in os.walk(cand_abs):
            for f in fs:
                if f.lower().endswith(".xml"):
                    found.append(os.path.join(r, f))
        if found:
            input_path = cand_abs
            xml_files = sorted(found)
            break

    if xml_files:
        print(f"[*] พบ {len(xml_files)} ไฟล์ .xml ใน '{input_path}'", flush=True)
    else:
        print(f"[*] ไม่พบไฟล์ .xml ใน '{args.input_dir}/' (ค้นหาที่: {os.path.abspath(os.path.join(ROOT, args.input_dir))})", flush=True)
    input_xml_total = len(xml_files)

    if args.single and xml_files:
        xml_files = xml_files[:1]
        print(f"[*] โหมด --single: จะประมวลผลแค่ 1 ไฟล์ ({os.path.basename(xml_files[0])})", flush=True)
    elif args.limit and args.limit > 0 and xml_files:
        xml_files = xml_files[:args.limit]
        print(f"[*] โหมด --limit {args.limit}: จะประมวลผล {len(xml_files)} ไฟล์", flush=True)

    if getattr(args, "delete", False):
        action_on_finish = "delete"
    elif getattr(args, "no_move", False):
        action_on_finish = "keep"
    else:
        action_on_finish = "move"   # ดีฟอลต์: ย้ายไฟล์ไป login-success / login-failed เหมือน login.py

    if xml_files:
        if not args.no_gui:
            try:
                progress = CaptureProgressWindow(input_xml_total, len(xml_files), devices)
                progress.start(lambda events: run_xml_batch(devices, xml_files, mitmdump, args, action_on_finish, events))
                return
            except tk.TclError as exc:
                print(f"[!] เปิด GUI ไม่ได้ ({exc}) - ทำงานต่อใน console", flush=True)

        import concurrent.futures as _cf
        n = len(devices)
        jobs = max(1, min(args.jobs, n))

        # ใส่คิวแชร์ร่วมกันทุกจอ ใครว่างก็หยิบไฟล์ถัดไปทำงานทันทีเหมือน login.py
        q = queue.Queue()
        total_files = len(xml_files)
        for i, f in enumerate(xml_files, 1):
            q.put((i, total_files, f))

        print(f"[*] พบ {total_files} ไฟล์ | {n} จอ | รันพร้อมกัน {jobs} จอ/รอบ (คิวแชร์อัตโนมัติเหมือน login.py)", flush=True)
        results = [([], []) for _ in range(n)]

        def _worker(idx):
            d = devices[idx]
            # หน่วงเวลาเริ่มแต่ละจอ (stagger delay เหมือน thread_delay ใน login.py)
            # ป้องกันแย่งกันตอนเริ่ม (ไม่แย่ง CPU / ADB / Network / port binding)
            if idx > 0 and getattr(args, "stagger", 5) > 0:
                stagger_sec = idx * args.stagger
                print(f"[*] [{d}] หน่วงเวลาปล่อยจอ {stagger_sec}s เพื่อไม่ให้แย่งกันตอนเริ่ม (เหมือน login.py thread_delay)...", flush=True)
                time.sleep(stagger_sec)

            try:
                results[idx] = process_xml_queue(d, q, mitmdump, args.use_login,
                                                 args.timeout, action_on_finish, PORT + idx)
            except Exception as e:
                print(f"[X] [{d}] worker error: {e}", flush=True)
            # merge ทันทีที่จอนี้เสร็จ (กันข้อมูลหายถ้าปิดกลางคัน)
            try:
                merge_parts_into_creds([part_creds(PORT + idx)])
            except Exception:
                pass

        with _cf.ThreadPoolExecutor(max_workers=jobs) as ex:
            list(ex.map(_worker, range(n)))
        try:
            merge_parts_into_creds()
        except Exception:
            pass
        success = [x for r in results for x in r[0]]
        failed = [x for r in results for x in r[1]]
        print(f"\n[*] creds.json รวม {len(load_creds())} บัญชี", flush=True)

        print("\n" + "=" * 55, flush=True)
        print(f"สรุปการทำงาน:", flush=True)
        suc_act = "ย้ายไป " + OUTPUT_DIR if action_on_finish == "move" else ("ลบออกจาก " + args.input_dir if action_on_finish == "delete" else "คงไว้ใน " + args.input_dir)
        fail_act = "ย้ายไป " + FAILED_DIR if action_on_finish == "move" else ("ลบออกจาก " + args.input_dir if action_on_finish == "delete" else "คงไว้ใน " + args.input_dir)
        print(f"  - สำเร็จ: {len(success)} ไฟล์ ({suc_act})", flush=True)
        print(f"  - ล้มเหลว/ข้าม: {len(failed)} ไฟล์ ({fail_act})", flush=True)
        if success:
            print(f"\nบัญชีที่จับได้ในรอบนี้:", flush=True)
            for fname, key, cred, info in success:
                print(f"    - {key:<10} | {fname} | ruby={info.get('ruby', 0)} | ticket={info.get('ticket', 0)}", flush=True)
        print(f"\nขั้นตอนถัดไป:", flush=True)
        print(f"  python test_login.py      # ตรวจสอบล็อกอินผ่าน API ทุกบัญชี", flush=True)
        print(f"  python collect_all.py     # ล็อกอิน + รับของทั้งหมดผ่าน API", flush=True)
        print("=" * 55, flush=True)

    else:
        # Fallback: ไม่มีไฟล์ใน input-dir -> สร้าง/จับ guest ปัจจุบันของ "ทุกจอ" ขนานกัน
        print(f"[*] ไม่พบไฟล์ .xml ใน '{args.input_dir}/' — จะจับ/สร้าง guest ของทุกจอ ({len(devices)} จอ) ขนานกัน", flush=True)
        import threading

        import concurrent.futures as _cf
        jobs = max(1, min(args.jobs, len(devices)))
        print(f"[*] รันพร้อมกัน {jobs} จอ/รอบ", flush=True)

        def _cap_one(idx):
            global _ROOT_ADBD
            d = devices[idx]
            if idx > 0 and rnd == 1 and getattr(args, "stagger", 5) > 0:
                stagger_sec = idx * args.stagger
                print(f"[*] [{d}] หน่วงเวลาเริ่ม {stagger_sec}s เพื่อไม่ให้แย่งกันตอนเริ่ม...", flush=True)
                time.sleep(stagger_sec)
            _ROOT_ADBD = enable_root(d) or _ROOT_ADBD
            hp = PORT + idx
            cf = part_creds(hp)
            with _api_part_owner(cf):        # เจ้าของ part ระหว่างจับ (ดู lgr_api.part_owner)
                _cap_one_owned(d, hp, cf)

        def _cap_one_owned(d, hp, cf):
            mitm = None
            try:
                setup_routing(d, hp)               # RoutingConflict -> หยุดจอนี้ (finally ถอนเฉพาะของที่ตั้ง)
                mitm = start_mitm(mitmdump, hp, cf)
                ok, key, cred = capture_account(d, None, args.timeout, args.use_login, cf)
                if ok:
                    info = fetch_account_info(cred, None, cf)
                    print(f"[OK] [{d}] id={key} | ruby={info['ruby']} | ticket={info['ticket']} | Lv {info['level']}", flush=True)
                    try:
                        merge_parts_into_creds([cf])
                    except Exception:
                        pass
                else:
                    print(f"[X] [{d}] จับไม่สำเร็จ", flush=True)
            except Exception as e:
                print(f"[X] [{d}] error: {e}", flush=True)
            finally:
                if mitm:
                    stop_mitm(mitm)
                teardown_routing(d)
                try:
                    merge_parts_into_creds([cf])   # merge ทันทีที่จอนี้เสร็จ
                except Exception:
                    pass

        # วนไม่หยุด: จบรอบแล้วเริ่มรอบใหม่ทันที (สร้าง guest เรื่อย ๆ) จนกด Ctrl+C
        rnd = 0
        try:
            while True:
                rnd += 1
                print(f"\n========== รอบที่ {rnd} (สร้าง guest ทุกจอ) ==========", flush=True)
                with _cf.ThreadPoolExecutor(max_workers=jobs) as ex:
                    list(ex.map(_cap_one, range(len(devices))))
                # รวมข้อมูลทุก part เข้า creds.json ตอนจบรอบ
                try:
                    merge_parts_into_creds()
                except Exception:
                    pass
                print(f"[*] รอบ {rnd} จบ | creds.json รวม {len(load_creds())} บัญชี (Ctrl+C เพื่อหยุด)", flush=True)
                time.sleep(2)
        except KeyboardInterrupt:
            try:
                merge_parts_into_creds()
            except Exception:
                pass
            print(f"\n[*] หยุดแล้ว (ทำไป {rnd} รอบ) | creds.json รวม {len(load_creds())} บัญชี -> python collect_all.py", flush=True)
        finally:
            try:
                merge_parts_into_creds()
            except Exception:
                pass


if __name__ == "__main__":
    main()
