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
import re
import shutil
import subprocess
import sys
import sysconfig
import time
import cv2
import numpy as np

from lgr_api import LGRClient, parse_ruby, parse_coin, parse_tickets

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)   # โฟลเดอร์โปรเจคหลัก (มี adb/ img/ input-id/ login.py)
CREDS = os.path.join(HERE, "creds.json")
ADDON = os.path.join(HERE, "capture_credential.py")
PKG = "com.linecorp.LGRGS"
ACT = f"{PKG}/.LineRangersAdr"
API_HOST = "rangers-api.line-apps.com"
PORT = 8443
PREF_DIR = f"/data/data/{PKG}/shared_prefs"
PREF_FILE = f"{PREF_DIR}/_LINE_COCOS_PREF_KEY.xml"
OUTPUT_DIR = os.path.join(ROOT, "login-success")   # ที่เก็บ .xml ของบัญชี guest ที่สร้างใหม่


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


def sh(cmd, device=None, timeout=30):
    """รันเป็น root: ถ้า adbd เป็น root แล้ว สั่งตรง; ไม่งั้น fallback ไป su -c"""
    if _ROOT_ADBD:
        return adb(["shell", cmd], device=device, timeout=timeout)
    return adb(["shell", "su", "-c", cmd], device=device, timeout=timeout)


def list_devices():
    """คืน serial ของทุกเครื่องที่ต่ออยู่ (สถานะ device)"""
    out = adb(["devices"]).stdout.splitlines()
    devs = [l.split()[0] for l in out[1:] if l.strip() and l.strip().endswith("device")]
    if not devs:
        sys.exit("[X] ไม่พบเครื่อง adb — เปิด emulator แล้ว `adb connect` ก่อน")
    return devs


def load_creds():
    try:
        content = open(CREDS, encoding="utf-8").read().strip()
        return json.loads(content) if content else {}
    except Exception:
        return {}


def save_creds(data):
    try:
        with open(CREDS, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] บันทึก {CREDS} ไม่สำเร็จ: {e}", flush=True)


def fetch_account_info(cred, fname=None):
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

    # บันทึกข้อมูลที่อัปเดต (รวม LF_AC ล่าสุด) ลง creds.json
    try:
        all_c = load_creds()
        rsn = cred.get("rsn") or cred.get("udid")
        target_keys = [k for k in (rsn, cred.get("udid")) if k]
        for k in target_keys:
            if k in all_c:
                all_c[k].update(cred)
                save_creds(all_c)
                break
        else:
            if rsn:
                all_c[rsn] = cred
                save_creds(all_c)
    except Exception:
        pass

    return info


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


def setup_routing(dev, host_port=PORT):
    print(f"[*] [{dev}] ตั้ง adb reverse (:{DEV_PORT}->host:{host_port}) + routing...", flush=True)
    adb(["reverse", f"tcp:{DEV_PORT}", f"tcp:{host_port}"], device=dev)
    cmd = (
        "cp /system/etc/hosts /data/local/tmp/hosts 2>/dev/null; "
        f"grep -q {API_HOST} /data/local/tmp/hosts || echo '127.0.0.1 {API_HOST}' >> /data/local/tmp/hosts; "
        "mount --bind /data/local/tmp/hosts /system/etc/hosts; "
        f"iptables -t nat -A OUTPUT -p tcp -d 127.0.0.1 --dport 443 -j REDIRECT --to-ports {DEV_PORT}"
    )
    r = sh(cmd, device=dev)
    if r.returncode != 0:
        print(f"[!] routing อาจไม่สมบูรณ์ (ต้อง root): {r.stderr.strip() or r.stdout.strip()}", flush=True)


def teardown_routing(dev):
    print(f"[*] [{dev}] ถอน routing/MITM คืนสภาพเดิม...", flush=True)
    sh("umount /system/etc/hosts 2>/dev/null; iptables -t nat -F OUTPUT 2>/dev/null", device=dev)
    adb(["reverse", "--remove-all"], device=dev)


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


def inject_xml(dev, xml_path):
    """ส่งไฟล์ _LINE_COCOS_PREF_KEY.xml ของบัญชีเข้าเกม (สลับบัญชี) — คืน True ถ้าสำเร็จ"""
    src = os.path.abspath(xml_path)
    safe_name = os.path.basename(xml_path)
    tmp = f"/data/local/tmp/_cap_pref_{dev.replace(':', '_')}.xml"
    print(f"[*] inject เข้าเกม: {safe_name}", flush=True)
    force_stop_game(dev)
    clear_session_files(dev)

    r = adb(["push", src, tmp], device=dev, timeout=60)
    if r.returncode != 0:
        print(f"[X] push ล้มเหลว: {r.stderr.strip() or r.stdout.strip()}", flush=True)
        return False

    cmd = (
        f"cp {tmp} {PREF_FILE} && chmod 666 {PREF_FILE} && "
        f"chown $(stat -c %u:%g {PREF_DIR} 2>/dev/null || echo 1000:1000) {PREF_FILE}; "
        f"rm -f {tmp}"
    )
    sh(cmd, device=dev, timeout=25)
    return True


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
def start_mitm(mitmdump, host_port=PORT):
    print(f"[*] เริ่ม mitmdump reverse-proxy host:{host_port} + addon ...", flush=True)
    p = subprocess.Popen(
        [mitmdump, "--mode", f"reverse:https://{API_HOST}",
         "--listen-port", str(host_port), "-s", ADDON, "-q"],
        cwd=HERE,
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


def capture_account(dev, xml_path, timeout, use_login):
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
        if not inject_xml(dev, xml_path):
            return False, None, None

    before_creds = load_creds()
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
        launch_game(dev)
        time.sleep(22)
        guest_login_flow(dev)
    else:
        force_stop_game(dev)
        launch_game(dev)

    print(f"[*] รอจับ credential (สูงสุด {timeout}s | udid={target_udid or 'auto'})...", flush=True)
    deadline = time.time() + timeout
    captured_key = None
    captured_data = None

    last_screen_handle = 0
    while time.time() < deadline:
        creds = load_creds()

        # ตรวจสอบว่า target_udid ได้รับ LF_AC ใหม่แล้วหรือยัง
        if target_udid:
            for k, v in creds.items():
                if v.get("udid") == target_udid and v.get("LF_AC"):
                    if (not prev_entry) or (v.get("LF_AC") != prev_entry.get("LF_AC")) or (v.get("guestCookie") != prev_entry.get("guestCookie")):
                        captured_key = k
                        captured_data = v
                        break
        else:
            diff = set(creds.keys()) - set(before_creds.keys())
            if diff:
                captured_key = list(diff)[0]
                captured_data = creds[captured_key]
                break

        if captured_key:
            # จับได้แล้ว: รอ 2 วิ เก็บ Set-Cookie รอบสุดท้าย แล้วปิดเกมทันที
            time.sleep(2)
            print("[*] จับได้แล้ว! สั่ง force-stop เกมทันที เพื่อตรึง LF_AC ไม่ให้หมุนทิ้ง", flush=True)
            force_stop_game(dev)
            creds = load_creds()
            captured_data = creds.get(captured_key, captured_data)
            break

        # ถ้าไม่ใช้ login.py: ตรวจจับและคลิกผ่านหน้าจออัตโนมัติทุก 2.5 วิ
        now = time.time()
        if not use_login and (now - last_screen_handle >= 2.5):
            handle_screen_flow(dev)
            last_screen_handle = now

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
def process_xml_queue(dev, xml_files, mitmdump, use_login, timeout, delete_on_success, host_port=PORT):
    global _ROOT_ADBD
    _ROOT_ADBD = enable_root(dev) or _ROOT_ADBD
    setup_routing(dev, host_port)
    mitm = start_mitm(mitmdump, host_port)

    success_list = []
    failed_list = []

    try:
        total = len(xml_files)
        for i, xml_path in enumerate(xml_files, 1):
            fname = os.path.basename(xml_path)
            print(f"\n===== [{i}/{total}] ประมวลผล: {fname} =====", flush=True)
            ok, key, cred = capture_account(dev, xml_path, timeout, use_login)

            if ok:
                info = fetch_account_info(cred, fname)
                success_list.append((fname, key, cred, info))
                print(f"[OK] จับสำเร็จ: id={key} | file={fname} | ruby={info['ruby']} "
                      f"| ticket={info['ticket']} | coin={info['coin']} | Lv {info['level']}", flush=True)

                if delete_on_success:
                    try:
                        os.remove(xml_path)
                        print(f"[OK] ลบไฟล์ {fname} ออกจากโฟลเดอร์เรียบร้อยแล้ว", flush=True)
                    except Exception as e:
                        print(f"[!] ลบไฟล์ {fname} ไม่สำเร็จ: {e}", flush=True)
                else:
                    print(f"[*] คงไฟล์ {fname} ไว้ (โหมด --no-delete)", flush=True)
            else:
                failed_list.append(fname)
                print(f"[X] จับไม่สำเร็จ: {fname} (ไม่ลบไฟล์ เพื่อความปลอดภัย)", flush=True)

            time.sleep(1)

    finally:
        stop_mitm(mitm)
        teardown_routing(dev)

    return success_list, failed_list


# ---------- reroll loop (สร้าง guest ใหม่เองวน ๆ) ----------
def reroll_loop(dev, count, mitmdump, use_login, timeout):
    """วนสร้างบัญชี guest ใหม่เอง count รอบ:
       ล้างบัญชี -> เปิดเกม (เกมสร้าง guest ใหม่) -> ผ่านจอ auto -> ดัก creds -> pull .xml
       คืน (success_list, failed)"""
    global _ROOT_ADBD
    _ROOT_ADBD = enable_root(dev)
    print(f"[*] root adbd = {'YES' if _ROOT_ADBD else 'no (จะลอง su แทน)'}", flush=True)
    if not _ROOT_ADBD:
        print("[!] ไม่ได้ root — ล้างบัญชี/สร้าง guest ใหม่อาจไม่ได้", flush=True)

    setup_routing(dev)
    mitm = start_mitm(mitmdump)
    success, failed = [], 0
    try:
        for i in range(1, count + 1):
            print(f"\n===== [reroll {i}/{count}] สร้าง guest ใหม่ =====", flush=True)
            # capture_account (xml_path=None) จะ pull บัญชีเดิม -> wipe -> สร้างใหม่ ให้เอง
            ok, key, cred = capture_account(dev, None, timeout, use_login)
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
    ap.add_argument("--no-delete", action="store_true", help="ไม่ลบไฟล์ XML หลังจับสำเร็จ (default: ลบออกตามคำขอ)")
    ap.add_argument("--single", action="store_true", help="ทำแค่ไฟล์แรกไฟล์เดียวแล้วหยุด (ใช้ทดสอบ)")
    ap.add_argument("--limit", type=int, default=0, help="จำกัดจำนวนไฟล์ที่จะทำ (0 = ทำทั้งหมด)")
    ap.add_argument("--reroll", type=int, default=0, metavar="N",
                    help="โหมดรีสร้าง: วนสร้าง guest ใหม่เอง N รอบ -> creds.json + .xml (login-success/)")
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
        devices = list_devices()
    dev = devices[0]
    print(f"[*] เครื่องที่จะใช้งาน: {dev} (ทั้งหมดที่พบ: {devices})", flush=True)

    # ---- โหมดรีสร้าง guest ใหม่เอง (reroll) ----
    if args.reroll and args.reroll > 0:
        print(f"[*] โหมด REROLL: จะสร้าง guest ใหม่เอง {args.reroll} รอบ", flush=True)
        success, failed = reroll_loop(dev, args.reroll, mitmdump, args.use_login, args.timeout)
        print("\n" + "=" * 55, flush=True)
        print(f"สรุป REROLL: สำเร็จ {len(success)} / ล้มเหลว {failed} (จาก {args.reroll} รอบ)", flush=True)
        for key, cred, xml, info in success:
            fname = os.path.basename(xml) if xml else '-'
            print(f"    - {key:<12} | {fname} | ruby={info.get('ruby', 0)} | ticket={info.get('ticket', 0)}", flush=True)
        print(f"\n.xml เก็บที่: {OUTPUT_DIR}", flush=True)
        print(f"creds เก็บที่: {CREDS}  -> ต่อด้วย: python collect_all.py", flush=True)
        print("=" * 55, flush=True)
        return

    # ค้นหาไฟล์ XML ใน input-dir
    input_path = os.path.join(ROOT, args.input_dir) if not os.path.isabs(args.input_dir) else args.input_dir
    xml_files = []
    if os.path.exists(input_path):
        xml_files = sorted(glob.glob(os.path.join(input_path, "*.xml")))

    if args.single and xml_files:
        xml_files = xml_files[:1]
        print(f"[*] โหมด --single: จะประมวลผลแค่ 1 ไฟล์ ({os.path.basename(xml_files[0])})", flush=True)
    elif args.limit and args.limit > 0 and xml_files:
        xml_files = xml_files[:args.limit]
        print(f"[*] โหมด --limit {args.limit}: จะประมวลผล {len(xml_files)} ไฟล์", flush=True)

    delete_on_success = not args.no_delete

    if xml_files:
        # กระจายไฟล์ให้ทุกจอทำขนานกัน (แต่ละจอ = mitmdump host-port แยก, creds.json ล็อกกันเขียนชน)
        n = len(devices)
        print(f"[*] พบ {len(xml_files)} ไฟล์ | ใช้ {n} จอขนานกัน: {devices}", flush=True)
        chunks = [xml_files[i::n] for i in range(n)]   # แบ่งแบบ round-robin
        results = [None] * n
        import threading

        def _worker(idx, d, files):
            if not files:
                results[idx] = ([], []); return
            try:
                results[idx] = process_xml_queue(d, files, mitmdump, args.use_login,
                                                 args.timeout, delete_on_success, PORT + idx)
            except Exception as e:
                print(f"[X] [{d}] worker error: {e}", flush=True)
                results[idx] = ([], [os.path.basename(f) for f in files])

        threads = [threading.Thread(target=_worker, args=(i, devices[i], chunks[i]), daemon=True)
                   for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        success = [x for r in results if r for x in r[0]]
        failed = [x for r in results if r for x in r[1]]

        print("\n" + "=" * 55, flush=True)
        print(f"สรุปการทำงาน:", flush=True)
        print(f"  - สำเร็จ: {len(success)} ไฟล์ (บันทึกลง creds.json {'และลบจาก ' + args.input_dir if delete_on_success else ''})", flush=True)
        print(f"  - ล้มเหลว/ข้าม: {len(failed)} ไฟล์", flush=True)
        if success:
            print(f"\nบัญชีที่จับได้ในรอบนี้:", flush=True)
            for fname, key, cred, info in success:
                print(f"    - {key:<10} | {fname} | ruby={info.get('ruby', 0)} | ticket={info.get('ticket', 0)}", flush=True)
        print(f"\nขั้นตอนถัดไป:", flush=True)
        print(f"  python test_login.py      # ตรวจสอบล็อกอินผ่าน API ทุกบัญชี", flush=True)
        print(f"  python collect_all.py     # ล็อกอิน + รับของทั้งหมดผ่าน API", flush=True)
        print("=" * 55, flush=True)

    else:
        # Fallback: ถ้าไม่มีไฟล์ใน input-dir จับบัญชีที่เปิดอยู่ในเครื่องปัจจุบัน
        print(f"[*] ไม่พบไฟล์ .xml ใน '{args.input_dir}/' — จะจับ credential ของบัญชีปัจจุบันในเครื่อง {dev}", flush=True)
        global _ROOT_ADBD
        _ROOT_ADBD = enable_root(dev)
        setup_routing(dev)
        mitm = start_mitm(mitmdump)
        try:
            ok, key, cred = capture_account(dev, None, args.timeout, args.use_login)
            if ok:
                info = fetch_account_info(cred)
                print(f"\n[OK] จับสำเร็จ: id={key} | file={info.get('file', '-')} | ruby={info['ruby']} "
                      f"| ticket={info['ticket']} | coin={info['coin']} | Lv {info['level']}", flush=True)
            else:
                print(f"\n[X] จับไม่สำเร็จสำหรับเครื่อง {dev}", flush=True)
        finally:
            stop_mitm(mitm)
            teardown_routing(dev)


if __name__ == "__main__":
    main()
