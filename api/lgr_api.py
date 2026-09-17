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

import json
import os
import sys
import glob
import shutil
import time
import requests

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except Exception:
        try:
            msg = " ".join(str(a) for a in args)
            enc = getattr(sys.stdout, "encoding", None) or "ascii"
            print(msg.encode(enc, errors="replace").decode(enc), **kwargs)
        except Exception:
            pass


BASE = "https://rangers-api.line-apps.com/v12.3"
# creds.json อยู่ที่เดียว = โฟลเดอร์ api/ (ทุกสคริปต์ + capture_auto ใช้ไฟล์นี้ร่วมกัน)
_API_DIR = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_API_DIR, "creds.json")

# LF_AC/guestCookie ของจริงยาว 280 ตัว ถ้าสั้นกว่านี้ = token ช่วงก่อนล็อกอินเสร็จ (ใช้ยิง API ไม่ได้ -> 401)
MIN_COOKIE_LEN = 200

# path รับรางวัลภารกิจ 7 วันที่ "ยิงผ่านแล้ว" (ค้นเจอครั้งแรกแล้วใช้ซ้ำทั้งโปรเซส)
_SD_ENDPOINT_CACHE = None


def merge_part_creds(base_dir=None):
    """
    รวมข้อมูลจากไฟล์ creds.part*.json ทุกไฟล์เข้า creds.json อัตโนมัติ (และลบ part files)
    ป้องกันปัญหาข้อมูลค้างใน creds.part*.json ทำให้ creds.json ว่างจนรันไม่ติด
    คืน (dict บัญชีทั้งหมด, จำนวนไฟล์ part ที่รวม)
    """
    if not base_dir:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    creds_path = os.path.join(base_dir, "creds.json")

    merged = {}
    if os.path.exists(creds_path):
        try:
            with open(creds_path, "r", encoding="utf-8") as f:
                c = f.read().strip()
                if c:
                    merged = json.loads(c)
        except Exception:
            merged = {}

    part_pattern = os.path.join(base_dir, "creds.part*.json")
    part_files = sorted(glob.glob(part_pattern))
    merged_count = 0

    for pf in part_files:
        try:
            with open(pf, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                data = json.loads(content)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
                            for field, val in v.items():
                                if val is not None or field not in merged[k]:
                                    merged[k][field] = val
                        else:
                            merged[k] = v
                    merged_count += 1
            try:
                os.remove(pf)
            except OSError:
                pass
        except Exception:
            pass

    if merged_count > 0 or not os.path.exists(creds_path):
        save_creds(merged, creds_path)
        if merged_count > 0:
            _safe_print(f"[*] ตรวจพบและรวมข้อมูลจาก {merged_count} ไฟล์ (creds.part*.json) เข้า creds.json สำเร็จ! (รวม {len(merged)} บัญชี)", flush=True)

    return merged, merged_count


def load_creds(path=None, auto_merge=True):
    """โหลด creds.json (พร้อม auto-merge creds.part*.json ถ้ามี)"""
    path = path or CREDS_FILE
    base_dir = os.path.dirname(os.path.abspath(path))
    if auto_merge:
        try:
            merge_part_creds(base_dir)
        except Exception:
            pass

    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            c = f.read().strip()
            return json.loads(c) if c else {}
    except Exception:
        return {}


def save_creds(data, path=None):
    """บันทึก creds.json แบบ atomic พร้อมสำรองไฟล์ .bak"""
    path = path or CREDS_FILE
    # กันเขียนทับด้วย dict ว่างเมื่อไฟล์เดิมมีข้อมูล (เคยทำบัญชีหายทั้งไฟล์ตอน process ชนกัน)
    if not data and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cur = f.read().strip()
            if cur and cur != "{}":
                _safe_print(f"[!] ปฏิเสธการเขียน creds ว่างทับ {path} (ของเดิมมีข้อมูล)", flush=True)
                return False
        except Exception:
            pass
    try:
        if os.path.exists(path):
            try:
                shutil.copy2(path, path + ".bak")
            except Exception:
                pass
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as e:
        _safe_print(f"[!] บันทึก {path} ไม่สำเร็จ: {e}", flush=True)
        return False



class LGRClient:
    def __init__(self, udid, lf_ac, app_version="12.3.1", nation="TH",
                 lang="en", model="SM-A528B", android="12"):
        self.udid = udid
        self.lf_ac = lf_ac                    # session cookie (จะถูกอัปเดตเมื่อเซิร์ฟหมุน)
        self.guest_cookie_next = None         # guestCookie ใหม่ ถ้าเซิร์ฟหมุนมาระหว่างทาง (ต้องเซฟทับของเดิม)
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
        # เก็บ LF_AC ที่หมุนใหม่ (และ guestCookie ถ้าเซิร์ฟหมุนมาด้วย — ของเก่าจะใช้ /login ไม่ได้อีก)
        for c in r.cookies:
            if c.name == "LF_AC" and c.value:
                self.lf_ac = c.value
            elif c.name == "guestCookie" and c.value and len(c.value) >= MIN_COOKIE_LEN:
                self.guest_cookie_next = c.value
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

    # ---------- ภารกิจ / mission (ยืนยันสดจากเซิร์ฟ 2026-09-16) ----------
    # หน้า "ภารกิจ" ของเกมจริงใช้ GET /mission/list/new/ -> daily / weekly / specialMissionTab
    # รับรางวัล: POST /mission/receive/reward/<missionNo>   (พิสูจน์แล้ว: missionNo 3688 -> 200)
    # หมายเหตุ: /mission/sevendays/list มีจริงแต่คืน errorCode 120900 กับบัญชีใหม่
    #           (เป็นอีเวนต์เฉพาะช่วง/เฉพาะกลุ่ม) -> อย่าใช้เป็นทางหลัก
    MISSION_LIST = "/mission/list/new/"
    MISSION_RECEIVE = "/mission/receive/reward/{no}"

    def mission_list(self):
        return self.call("GET", self.MISSION_LIST)

    def sevendays_list(self):
        """ภารกิจ 7 วันแบบอีเวนต์ (บัญชีทั่วไปมักได้ 400/120900) — เก็บไว้เผื่ออีเวนต์เปิด"""
        return self.call("GET", "/mission/sevendays/list")

    def mission_pending(self):
        """คืน (status, list ของภารกิจที่ 'ทำครบแล้วแต่ยังไม่รับ' จากทุก tab)"""
        st, d = self.mission_list()
        if st != 200 or not isinstance(d, dict):
            return st, []
        return st, parse_missions(d.get("result", {}) or {})

    def mission_receive(self, mission_no):
        """รับรางวัลภารกิจ 1 ชิ้นด้วย missionNo"""
        return self.call("POST", self.MISSION_RECEIVE.format(no=mission_no))

    def mission_receive_all(self, pending=None):
        """
        รับรางวัลภารกิจที่ค้างอยู่ทั้งหมด -> dict สรุป
        ส่ง pending ที่ดึงไว้แล้วเข้ามาได้ (สำคัญ: ยิง /mission/list/new/ ซ้ำติด ๆ กัน
        เซิร์ฟตอบ 400 -> อย่าเรียกซ้ำถ้ามีของอยู่แล้ว)
        """
        if pending is None:
            st, pending = self.mission_pending()
        else:
            st = 200
        if st != 200:
            return {"ok": False, "step": "mission/list", "status": st, "pending": 0, "claimed": 0}
        claimed, failed = 0, []
        for m in pending:
            st_r, resp = self.mission_receive(m["seq"])
            if st_r == 200 and isinstance(resp, dict) and "result" in resp:
                claimed += 1
            else:
                failed.append({"seq": m["seq"], "status": st_r, "resp": str(resp)[:120]})
        return {"ok": True, "pending": len(pending), "claimed": claimed,
                "failed": failed, "missions": pending}

    # ชื่อเดิม (ตอนยังไม่รู้ path จริง) — ให้ชี้มาที่ของจริง กันโค้ดเก่าพัง
    sevendays_pending = mission_pending
    sevendays_receive_all = mission_receive_all

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


# ---------- mission parsing (สคีมายืนยันสดจาก /mission/list/new/ 2026-09-16) ----------
# รูปแบบจริงต่อ 1 ภารกิจ:
#   {missionNo, missionType, missionCondition, currentCount, completionCount,
#    missionComplete: bool, receiveReward: bool, missionRewards:[{rewardType,code,amount}]}
# tab ของ daily/weekly ไม่มี missionNo ต่อชิ้น (รับรวมทั้ง tab) -> เก็บเฉพาะชิ้นที่มี missionNo
_MISSION_TABS = ("dailyMissionTab", "weeklyMissionTab", "specialMissionTab")


def _mission_rewards(m):
    out = []
    for r in m.get("missionRewards") or []:
        code = r.get("code") or r.get("rewardType") or "?"
        out.append(f"{code}x{r.get('amount', 1)}")
    return out


def parse_missions(result):
    """
    คืนภารกิจที่ 'ทำครบแล้วแต่ยังไม่รับ' จาก result ของ /mission/list/new/
    -> list ของ {seq(=missionNo), tab, title(=missionType), rewards, raw}
    """
    out = []
    for tab in _MISSION_TABS:
        v = (result or {}).get(tab)
        items = v if isinstance(v, list) else ((v or {}).get("detail") or [])
        for m in items:
            if not isinstance(m, dict):
                continue
            no = m.get("missionNo")
            if no is None:                       # daily/weekly รายชิ้นไม่มี missionNo -> รับไม่ได้ทีละอัน
                continue
            if m.get("missionComplete") and not m.get("receiveReward"):
                out.append({
                    "seq": no,
                    "tab": tab,
                    "title": m.get("missionType") or str(no),
                    "rewards": _mission_rewards(m),
                    "raw": m,
                })
    return out


# ชื่อเดิม กันโค้ดเก่าเรียกพัง
parse_sevendays = parse_missions


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
