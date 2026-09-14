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

    # inventory ที่มีจำนวนตั๋วกาชา (แสดงหน้า gacha ข้าง ๆ ruby) - ตั๋วไม่อยู่ใน /home
    ITEM_PATH = ("/player/item?pGacha=true&clsGacha=true&etGacha=true"
                 "&battleAuto=false&battleManual=false&evolve=false")

    def player_items(self):
        return self.call("GET", self.ITEM_PATH)

    def ticket_count(self):
        """คืน dict {premium, classic, event, total} ของตั๋วกาชาที่ถืออยู่จริง"""
        st, d = self.player_items()
        if st != 200 or not isinstance(d, dict):
            return {"premium": 0, "classic": 0, "event": 0, "total": 0, "_status": st}
        return sum_tickets(d.get("result", {}) or {})

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

    def get_profile(self, guest_cookie=None):
        """ดึงข้อมูลสถานะผู้เล่น: level, ruby, coin, ticket, gift_badge (ลอง /home ก่อน ถ้า 401 ค่อย /login)"""
        st, home = self.home()
        if st == 401 and guest_cookie:
            self.login(guest_cookie)
            st, home = self.home()
        if st != 200 or not isinstance(home, dict):
            return {"ok": False, "status": st, "data": home, "lf_ac_next": self.lf_ac}

        result = home.get("result", {}) or {}
        player = result.get("player", {}) or {}
        badge = result.get("badge", {}) or {}
        return {
            "ok": True,
            "rsn": player.get("rsn") or result.get("rsn"),
            "userName": player.get("userName"),
            "level": player.get("level") or result.get("level"),
            "ruby": parse_ruby(result, player),
            "coin": parse_coin(result, player),
            "ticket": self.ticket_count().get("total", 0),   # ตั๋วกาชาจาก /player/item (ไม่อยู่ใน /home)
            "gift_badge": badge.get("GIFT", 0),
            "lf_ac_next": self.lf_ac,
        }


# ---------- resource parsing helpers ----------
def _amount(v):
    """currency ในเกมเป็น object {innerFree,...,total} หรือเลขตรง ๆ -> คืนยอดรวม"""
    if isinstance(v, dict):
        return v.get("total", v.get("free", 0))
    if isinstance(v, (int, float)):
        return int(v)
    return 0


def parse_ruby(result, player=None):
    """ดึงจำนวน Ruby / เพชร จาก response ของ /home หรือ /login"""
    result = result or {}
    player = player or {}
    for src in (result.get("ruby"), result.get("rubyBalance"), player.get("ruby"), player.get("gem")):
        if src not in (None, 0):
            return _amount(src)
    return 0


def parse_coin(result, player=None):
    """ดึงจำนวนเหรียญทอง จาก response ของ /home หรือ /login"""
    result = result or {}
    player = player or {}
    for src in (result.get("coin"), result.get("gold"), player.get("coin"), player.get("gold")):
        if src not in (None, 0):
            return _amount(src)
    return 0


IGNORE_TICKET_KEYS = {
    "ticketpayablecost", "needticket", "needclassicticket", "needeventticket",
    "displayticketprice", "displayoriginalticketprice", "displayeventticketprice",
    "displayoriginaleventticketprice", "displayclassicticketprice", "displayoriginalclassicticketprice",
    "eventticketyn", "classicticketyn", "ticketpayabletype",
}


def parse_tickets(result, player=None):
    """สแกนหา key ที่มีคำว่า ticket (นับตั๋วกาชาทุกชนิด) โดยกรองตัดคีย์ราคาของตู้กาชาออก -> int รวม หรือ dict"""
    found = {}

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                kl = k.lower()
                if "ticket" in kl:
                    if kl in IGNORE_TICKET_KEYS or "price" in kl or "cost" in kl or "need" in kl:
                        continue
                    if isinstance(v, (int, float)) and v:
                        found[k] = found.get(k, 0) + int(v)
                walk(v)
        elif isinstance(o, list):
            for it in o:
                walk(it)

    if isinstance(result, dict):
        walk(result)
    if isinstance(player, dict):
        walk(player)

    if not found:
        return 0
    total = sum(found.values())
    return total if len(found) <= 1 else found


def sum_tickets(item_result):
    """รวมจำนวนตั๋วกาชาจาก /player/item -> {premium, classic, event, total}
       (แต่ละลิสต์เป็น item ที่มี field 'amount' = จำนวนที่ถือ)"""
    r = item_result or {}

    def _sum(lst):
        return sum(int(x.get("amount") or x.get("freeAmount") or 0)
                   for x in (r.get(lst) or []) if isinstance(x, dict))

    prem = _sum("premiumGachaTicketItems")
    cls = _sum("classicGachaTicketItems")
    evt = _sum("eventGachaTicketItems")
    return {"premium": prem, "classic": cls, "event": evt, "total": prem + cls + evt}


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
