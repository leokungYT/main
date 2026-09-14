#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lgr_api.py — LINE Rangers (com.linecorp.LGRGS) REST client
ยิง API ตรง ๆ ไม่ต้องเปิดเกม/อีมูเลเตอร์ — ใช้ ล็อกอิน + รับของ ได้เลย

หลักการ (แกะจาก MITM จริง 2026-09-14):
  - server  : https://rangers-api.line-apps.com/v12.3/<path>
  - auth    : ส่งผ่าน Cookie เท่านั้น -> "udid=<device_uuid>; LF_AC=<session>"
              ไม่มีลายเซ็น/HMAC ต่อ request (X-LINEGAME-TIMESTAMP เป็นแค่ค่าเวลา)
  - LF_AC   : session cookie ใช้เรียก endpoint ที่ต้อง auth ได้ตรง ๆ
              เซิร์ฟหมุนค่าใหม่กลับมาทาง Set-Cookie ทุก request -> ต้องเก็บค่าใหม่ไว้ใช้ต่อ
  - guestCookie : credential ถาวรของ guest (ถอดจาก _ENC_LF_AC_KEY) ใช้กับ /login
                  เพื่อขอ session ใหม่ (ถ้า LF_AC หมดอายุ)

วิธีได้ credential (udid + LF_AC) ต่อ 1 บัญชี — ทำครั้งเดียว:
  ใช้ capture_credential.py (MITM) จับตอนเกมล็อกอิน 1 ครั้ง แล้วเก็บ udid+LF_AC
  จากนั้นบัญชีนั้นใช้ API ตัวนี้อย่างเดียว (อย่าเปิดเกมบัญชีเดิมพร้อมกัน เดี๋ยว credential หมุนชนกัน)
"""

import time
import requests

BASE = "https://rangers-api.line-apps.com/v12.3"


class LGRClient:
    def __init__(self, udid, lf_ac, app_version="12.3.1", nation="TH",
                 lang="en", model="SM-A528B", android="12"):
        self.udid = udid
        self.lf_ac = lf_ac                    # session cookie (จะถูกอัปเดตเมื่อเซิร์ฟหมุน)
        self.app_version = app_version
        self.s = requests.Session()
        self.s.headers.update({
            "App-Version": f"LGRGS/{app_version};android/{android}",
            "Nation-Code": nation,
            "Accept-Language": lang,
            "User-Agent": f"LGRGS/{app_version} (Linux; U; Android {android}; {lang}-US; {model} Build/V417IR)",
            "useLGC": "true",
            "X-LINEGAME-MCC": "000",
            "X-LINEGAME-MNC": "00",
            "Accept-Encoding": "identity",
        })

    def _cookie(self, guest_cookie=None):
        ck = f"udid={self.udid}; LF_AC={self.lf_ac}"
        if guest_cookie:
            ck += f"; guestCookie={guest_cookie}"
        return ck

    def call(self, method, path, guest_cookie=None, **kw):
        """เรียก endpoint หนึ่ง คืน (status_code, json|text). อัปเดต LF_AC อัตโนมัติเมื่อเซิร์ฟหมุน"""
        headers = kw.pop("headers", {})
        headers["X-LINEGAME-TIMESTAMP"] = str(int(time.time() * 1000))
        headers["Cookie"] = self._cookie(guest_cookie)
        if method.upper() == "POST" and "data" not in kw and "json" not in kw:
            headers.setdefault("Content-Type", "application/json")
            kw["data"] = "{}"
        r = self.s.request(method, BASE + path, headers=headers, timeout=25, **kw)
        # เก็บ LF_AC ที่หมุนใหม่
        for c in r.cookies:
            if c.name == "LF_AC" and c.value:
                self.lf_ac = c.value
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text

    # ---------- ตัวช่วยที่ใช้บ่อย ----------
    def login(self, guest_cookie):
        """ขอ session ใหม่ด้วย guestCookie (credential ถาวร). คืน player dict"""
        return self.call("GET", "/login", guest_cookie=guest_cookie)

    def home(self):
        """สถานะบ้าน: badge (GIFT/COLLECT/...), player, ฯลฯ — ใช้เช็ก 'เข้าเกมได้ไหม' + จำนวนของ"""
        return self.call("GET", "/home")

    def giftbox_list(self):
        return self.call("GET", "/giftbox/list")

    def receive_all_gifts(self):
        """รับของขวัญทั้งกล่อง gift — คืน player ที่อัปเดตแล้ว"""
        return self.call("POST", "/giftbox/gift/receive/all")

    def unclaimed_gifts(self):
        st, d = self.giftbox_list()
        if st != 200 or not isinstance(d, dict):
            return st, None
        gifts = (d.get("result", {}).get("giftBox", {}) or {}).get("gift", {}).get("playerGifts", [])
        return st, [g for g in gifts if not g.get("receive")]

    # ---------- กาชา (แกะจากทราฟฟิกจริง 2026-09-14) ----------
    def gacha_info(self):
        """รายการกาชาทั้งหมด: result.gachaGroupResponseList[].gachaGroup.gachaGroupInfos[]"""
        return self.call("GET", "/gacha/info")

    def gacha_reserve(self, group_id, gacha_id, gacha_index=1):
        """จอง 1 การสุ่ม -> result มี reserveSeq (ต้องเอาไปใส่ confirm)"""
        return self.call("POST", "/gacha/group/reserve",
                         json={"groupId": group_id, "gachaId": gacha_id, "gachaIndex": gacha_index})

    def gacha_confirm(self, reserve_result):
        """ยืนยันการสุ่ม -> ต้องส่ง 'ทั้งก้อน result ของ reserve' กลับไป. คืน gachaResults"""
        return self.call("POST", "/gacha/group/confirm", json=reserve_result)

    def gacha_pull(self, group_id, gacha_id, gacha_index=1):
        """สุ่มครบ flow: reserve -> confirm. คืน (status, list ของรหัสตัว/ไอเทมที่ได้, raw)"""
        st, d = self.gacha_reserve(group_id, gacha_id, gacha_index)
        if st != 200 or not isinstance(d, dict):
            return st, [], d
        st2, d2 = self.gacha_confirm(d.get("result", {}))
        return st2, parse_gacha_rewards(d2), d2

    def stage_last(self):
        return self.call("GET", "/stage/last")

    def stage_main(self):
        return self.call("GET", "/stage/main")


def parse_gacha_rewards(confirm_resp):
    """ดึงรหัสของที่ได้จาก response ของ /gacha/group/confirm
       คืน list เช่น ['unit:u421e-daniel', 'equip:eq_wpn_0011']"""
    out = []
    if not isinstance(confirm_resp, dict):
        return out
    for gr in confirm_resp.get("result", {}).get("gachaResults", []) or []:
        for rw in gr.get("rewards", []) or []:
            unit = rw.get("rewardUnit") or rw.get("unit")
            if unit:
                code = unit.get("unitCode") or unit.get("dataCode") or unit.get("code")
                out.append(f"unit:{code}")
            item = rw.get("rewardGameItem")
            if item:
                out.append(f"equip:{item.get('itemCode') or item.get('equipItemCode')}")
    return out


def collect_account(udid, lf_ac):
    """ตัวอย่างงานจริง: เช็กว่าเข้าเกมได้ + รับของทั้งหมด (1 บัญชี)"""
    c = LGRClient(udid, lf_ac)
    st, home = c.home()
    if st != 200:
        return {"ok": False, "step": "home", "status": st, "detail": home}
    badge = home.get("result", {}).get("badge", {})
    gift_badge = badge.get("GIFT", 0)
    st, before = c.unclaimed_gifts()
    n_before = len(before or [])
    st_r, resp = (200, None)
    if n_before > 0:
        st_r, resp = c.receive_all_gifts()
    st, after = c.unclaimed_gifts()
    n_after = len(after or [])
    return {
        "ok": True,
        "rsn": home.get("result", {}).get("player", {}).get("rsn")
              or home.get("result", {}).get("rsn"),
        "gift_badge": gift_badge,
        "unclaimed_before": n_before,
        "unclaimed_after": n_after,
        "claimed": max(0, n_before - n_after),
        "receive_status": st_r,
        "lf_ac_next": c.lf_ac,   # เก็บไว้ใช้รอบหน้า (เซิร์ฟหมุนค่าแล้ว)
    }


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 3:
        print("usage: python lgr_api.py <udid> <LF_AC>")
        sys.exit(1)
    print(json.dumps(collect_account(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=2))
