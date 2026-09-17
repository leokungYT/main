#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capture_credential.py — mitmproxy addon จับ credential (udid + LF_AC) ของแต่ละบัญชี
จากทราฟฟิกเกมจริง แล้วเก็บลง creds.json  (ใช้ครั้งเดียวต่อบัญชี แล้วสลับไปใช้ lgr_api.py)

ทำไมต้อง MITM: guestCookie ถูกเก็บแบบเข้ารหัส (_ENC_LF_AC_KEY) ในเครื่อง
ถอดตรง ๆ ไม่ได้ (LINE SDK encryption ผูกเครื่อง) แต่ตอนเกมยิง /login มันส่ง cookie
แบบถอดรหัสแล้ว -> ดักตรงนั้นทีเดียวได้ทั้ง udid + LF_AC + guestCookie + rsn(บัญชี)

--- วิธีตั้ง routing (rooted emulator, ทำครั้งเดียว) ---
  HOST=10.0.2.2   # หรือ IP host ที่ emulator มองเห็น (ตัวนี้ใช้ adb reverse ก็ได้)
  # 1) รัน mitmdump reverse-proxy ชี้ rangers-api พร้อม addon นี้:
  #    mitmdump --mode reverse:https://rangers-api.line-apps.com --listen-port 8443 -s capture_credential.py -q
  # 2) ต่อ tunnel + เปลี่ยนเส้นให้ traffic rangers-api วิ่งเข้า mitm:
  #    adb -s <serial> reverse tcp:8443 tcp:8443
  #    adb -s <serial> shell "su -c 'cp /system/etc/hosts /data/local/tmp/hosts; \
  #        echo 127.0.0.1 rangers-api.line-apps.com >> /data/local/tmp/hosts; \
  #        mount --bind /data/local/tmp/hosts /system/etc/hosts; \
  #        iptables -t nat -A OUTPUT -p tcp -d 127.0.0.1 --dport 443 -j REDIRECT --to-ports 8443'"
  # 3) เปิดเกม กด PLAY ให้ล็อกอิน 1 ครั้ง -> creds.json จะมี entry ของบัญชีนั้น
  # 4) เลิก MITM: adb ... reverse --remove-all ; su -c 'umount /system/etc/hosts; iptables -t nat -F OUTPUT'
  # หมายเหตุ: เกมยอมรับ cert ของ mitmproxy (ไม่ต้อง bypass pin) — ทดสอบแล้วผ่าน

หลังได้ creds.json:  python lgr_api.py <udid> <LF_AC>   (หรือ import LGRClient)
"""

import json
import os
import re
from mitmproxy import http

# แต่ละจอตั้ง env LGR_CREDS_FILE ให้เขียนไฟล์แยกกัน (ไม่แย่ง .lock เดียวกัน) แล้ว capture_auto merge ตอนจบ
CREDS = os.environ.get("LGR_CREDS_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "creds.json")   # api/creds.json

# LF_AC ของจริงยาว 280 ตัว; ค่าสั้น ๆ (~40) คือ token ช่วงยังล็อกอินไม่เสร็จ -> เก็บไปก็ 401
MIN_COOKIE_LEN = 200
_UDID2RSN = {}   # จำ udid -> rsn ภายในรอบจับ (กัน entry ซ้ำ)


def _load():
    try:
        return json.load(open(CREDS, encoding="utf-8"))
    except Exception:
        return {}


import time as _time
import contextlib

_LOCK = CREDS + ".lock"


@contextlib.contextmanager
def _flock():
    """cross-process lock (หลาย mitmdump เขียน creds.json พร้อมกันตอนรันหลายจอ)"""
    fd = None
    for _ in range(200):                       # รอสูงสุด ~10s
        try:
            fd = os.open(_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            _time.sleep(0.05)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
            try:
                os.remove(_LOCK)
            except OSError:
                pass


def _save(d):
    tmp = CREDS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CREDS)                      # atomic (กันไฟล์พังตอนเขียนพร้อมกัน)


def _cookie_parts(raw):
    out = {}
    for part in re.split(r"[;,]", raw or ""):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            out[k.strip()] = v.strip()
    return out


def response(flow: http.HTTPFlow):
    r, resp = flow.request, flow.response
    if "rangers-api" not in r.pretty_host:
        return
    # ข้าม pre-check เช่น /exapi/ (เช่น /exapi/nation.nhn) เพราะยังไม่ได้ล็อกอิน (ยังไม่มี guestCookie / rsn)
    if "/exapi/" in r.path:
        return
    ck = _cookie_parts(r.headers.get("cookie", ""))
    udid = ck.get("udid")
    # LF_AC ล่าสุด = Set-Cookie ของ response (เซิร์ฟหมุนค่าใหม่) ถ้าไม่มีค่อยใช้ของ request
    lf = None
    for sc in resp.headers.get_all("set-cookie"):
        m = re.search(r"LF_AC=([^;]+)", sc)
        if m:
            lf = m.group(1)
    lf = lf or ck.get("LF_AC")
    if not (udid and lf):
        return
    if len(lf) < MIN_COOKIE_LEN:               # ยังล็อกอินไม่เสร็จ -> รอ request ถัดไป อย่าเพิ่งเขียนทับของดี
        return
    # rsn (เลขบัญชีในเกม = USER_GAME_ID) มาจาก response ของ /login
    rsn = None
    ruby = None
    coin = None
    level = None
    try:
        body = resp.get_text(strict=False) or ""
        if "/login" in r.path:
            import json as _json
            data = _json.loads(body)
            res_obj = data.get("result", {})
            rsn = res_obj.get("rsn")
            level = res_obj.get("level")
            ruby_obj = res_obj.get("ruby", {})
            if isinstance(ruby_obj, dict):
                ruby = ruby_obj.get("total", ruby_obj.get("free", 0))
            elif isinstance(ruby_obj, (int, float)):
                ruby = int(ruby_obj)
            coin_obj = res_obj.get("coin", {})
            if isinstance(coin_obj, dict):
                coin = coin_obj.get("total", coin_obj.get("free", 0))
            elif isinstance(coin_obj, (int, float)):
                coin = int(coin_obj)
        else:
            m = re.search(r'"rsn"\s*:\s*"?([a-zA-Z0-9_-]+)"?', body)
            if m:
                rsn = m.group(1)
    except Exception:
        pass
    if rsn:
        _UDID2RSN[udid] = rsn
    key = rsn or _UDID2RSN.get(udid) or udid
    with _flock():                            # ล็อก: reload สด -> แก้ -> เขียน (กันจออื่นเขียนทับ)
        d = _load()
        # ยุบ entry เก่าที่เคยคีย์ด้วย udid ให้มารวมกับคีย์ rsn (ครั้งแรกที่รู้ rsn)
        old_udid_entry = d.get(udid, {}) if key != udid else {}
        entry = d.get(key, {}) or old_udid_entry
        entry["udid"] = udid
        entry["LF_AC"] = lf                       # อัปเดตเป็นค่าล่าสุดเสมอ (เซิร์ฟหมุน)
        if key != udid:
            entry["rsn"] = key
        if ruby is not None:
            entry["ruby"] = ruby
        if coin is not None:
            entry["coin"] = coin
        if level is not None:
            entry["level"] = level
        gc = ck.get("guestCookie")
        if gc and len(gc) < MIN_COOKIE_LEN:       # gc สั้น = ยังไม่ใช่ credential ถาวร
            gc = None
        if gc:                                    # อย่าเขียนทับด้วย None (มีแค่ตอน /login)
            entry["guestCookie"] = gc
        elif not entry.get("guestCookie") and old_udid_entry.get("guestCookie"):
            entry["guestCookie"] = old_udid_entry["guestCookie"]
        entry.setdefault("guestCookie", None)
        d[key] = entry
        if key != udid and udid in d:             # ลบ entry ซ้ำที่คีย์ด้วย udid
            d.pop(udid, None)
        _save(d)
    ruby_str = f" ruby={entry['ruby']}" if "ruby" in entry else ""
    coin_str = f" coin={entry['coin']}" if "coin" in entry else ""
    print(f"[creds] saved acct={key} udid={udid[:8]}.. LF_AC={lf[:16]}.. gc={'Y' if entry.get('guestCookie') else '-'}{ruby_str}{coin_str}", flush=True)
