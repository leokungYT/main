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

CREDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creds.json")


def _load():
    try:
        return json.load(open(CREDS, encoding="utf-8"))
    except Exception:
        return {}


def _save(d):
    json.dump(d, open(CREDS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


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
    # rsn (เลขบัญชีในเกม = USER_GAME_ID) มาจาก response ของ /login
    rsn = None
    try:
        body = resp.get_text(strict=False) or ""
        m = re.search(r'"rsn"\s*:\s*"([^"]+)"', body)
        if m:
            rsn = m.group(1)
    except Exception:
        pass
    d = _load()
    key = rsn or udid
    d[key] = {"udid": udid, "LF_AC": lf, "rsn": rsn, "guestCookie": ck.get("guestCookie")}
    _save(d)
    print(f"[creds] saved acct={key} udid={udid[:8]}.. LF_AC={lf[:16]}..")
