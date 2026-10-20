#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
web_app.py — เว็บเช็คตัว/ranger สไตล์ zippyranger.online แต่ยิง API จาก creds.json
             (ไม่ต้องลากไฟล์ .xml — ลดความเสี่ยง)

★ Local เท่านั้น: creds.json = cookie บัญชีจริง ห้ามเปิด public / bind 0.0.0.0
  โดยดีฟอลต์ผูกกับ 127.0.0.1 เท่านั้น (เครื่องนี้เข้าได้เครื่องเดียว)

ใช้:
  python web_app.py                 # เปิด http://127.0.0.1:8770
  python web_app.py --port 9000
  (ไม่มี dependency — ใช้ http.server ของ Python เอง ไม่ต้อง pip install)

API:
  GET /                     -> หน้าเว็บ (web/index.html)
  GET /api/accounts         -> รายชื่อบัญชีจาก creds.json (เร็ว ใช้ค่าที่แคชไว้) + targets
  GET /api/check?id=<key>   -> เช็คบัญชีเดียวสด ๆ ผ่าน API: heroes + hits + ruby/ticket/level
  GET /api/missions?id=<key>&claim=0 -> ภารกิจ daily/weekly/special (claim=0 = ดูเฉย ๆ)
"""
import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lgr_api import (
    LGRClient,
    parse_ruby,
    parse_coin,
    parse_tickets,
    gacha_pick_pay,
    load_creds as _api_load_creds,
    try_update_creds as _api_try_update_creds,
    CREDS_FILE,
)
from check_team import account_units_info, default_targets, match_targets

WEB_DIR = os.path.join(HERE, "web")
ROOT = os.path.dirname(HERE)
# โฟลเดอร์ที่เก็บ .xml ต้นฉบับ (เรียงตามลำดับความน่าเชื่อถือ)
XML_DIRS = [os.path.join(ROOT, d) for d in ("backup", "input-id", "login-success", "backup-id")]
_SAVE_LOCK = threading.Lock()
_XML_INDEX = None
_XML_LOCK = threading.Lock()


def load_creds():
    return _api_load_creds(CREDS_FILE, auto_merge=True)


def xml_index():
    """basename(ตัวเล็ก) -> path เต็มของไฟล์ .xml ต้นฉบับ (แคชไว้ครั้งเดียว)"""
    global _XML_INDEX
    with _XML_LOCK:
        if _XML_INDEX is None:
            import glob
            idx = {}
            for d in XML_DIRS:
                if not os.path.isdir(d):
                    continue
                for p in glob.glob(os.path.join(d, "*.xml")):
                    idx.setdefault(os.path.basename(p).lower(), p)
            _XML_INDEX = idx
        return _XML_INDEX


def xml_path_for(key):
    """หา path .xml ต้นฉบับของบัญชีจาก field 'file' ใน creds"""
    cred = load_creds().get(key) or {}
    f = cred.get("file")
    if not f:
        return None
    return xml_index().get(os.path.basename(f).lower())


AUTO_OUT = os.path.join(HERE, "output")


def auto_export(hits, misses, session=None):
    """แยกไฟล์ .xml หลัง Auto สุ่ม -> output/auto-<เวลา>/{เจอเป้า,norandom}/
    hits: [(key, ชื่อตัวที่ได้)] -> ตั้งชื่อ "<ชื่อตัว>+<ชื่อไฟล์เดิม>.xml" ; misses: [key] -> โฟลเดอร์ norandom ชื่อเดิม
    คืน (โฟลเดอร์, [(arcname, path)])"""
    import re
    import shutil
    # session = ชื่อโฟลเดอร์รอบนี้ (ส่งทีละไอดีเข้าโฟลเดอร์เดียวกัน) ; ไม่ใส่ = สร้างใหม่ตามเวลา
    name = re.sub(r"[^0-9A-Za-z_-]", "", session or "") or "auto-" + time.strftime("%Y%m%d-%H%M%S")
    out = os.path.join(AUTO_OUT, name)
    files = []
    for sub, rows in (("เจอเป้า", hits), ("norandom", [(k, "") for k in misses])):
        for key, name in rows:
            src = xml_path_for(key)
            if not (src and os.path.exists(src)):
                continue
            base = os.path.basename(src)
            if name:
                base = re.sub(r'[\/:*?"<>|]+', "_", name).strip() + "+" + base
            os.makedirs(os.path.join(out, sub), exist_ok=True)
            dst = os.path.join(out, sub, base)
            shutil.copy2(src, dst)
            files.append((sub + "/" + base, dst))
    return out, files


CATALOG_CACHE = os.path.join(WEB_DIR, "_catalog.json")
# ใช้ "วิธีเดียวกับเว็บ zippyranger" — ดึง catalog (ชื่อจริง+โค้ด, เรนเจอร์+เกียร์) จาก gateway ของมันเอง
CATALOG_SRC = "https://zippyranger.online/api/gateway?act=g"
IMG_BASE = "https://rangers.lerico.net/res"
CATALOG_TTL = 6 * 3600          # cache หมดอายุทุก 6 ชม. -> ดึงใหม่เอง (ตัวใหม่เข้ามาเรื่อยๆ)
_CATALOG = None
_CATALOG_LOCK = threading.Lock()


GAME_NDB = os.path.join(WEB_DIR, "_lang_unit.ndb")
GAME_NDB_REMOTE = "/sdcard/Android/data/com.linecorp.LGRGS/files/.res/lang_unit/lang_unit.ndb"


def _game_unit_names():
    """ชื่อเรนเจอร์จากไฟล์ภาษาของตัวเกมเอง (lang_unit.ndb = SQLite เปล่า) -> {code: name}
    ดึงจากอีมูที่ต่อ adb อยู่ (อัปเดตตามเกม -> มีตัวใหม่ก่อนเว็บนอก) ; ดึงไม่ได้ใช้ไฟล์เดิม"""
    import sqlite3
    import subprocess
    adb = os.path.join(os.path.dirname(HERE), "adb", "adb.exe")
    if os.path.exists(adb) and (not os.path.exists(GAME_NDB)
                                or time.time() - os.path.getmtime(GAME_NDB) > CATALOG_TTL):
        try:
            out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=10).stdout
            serials = [ln.split()[0] for ln in out.splitlines()[1:] if ln.strip().endswith("device")]
            for sr in serials:
                tmp = GAME_NDB + ".tmp"
                r = subprocess.run([adb, "-s", sr, "pull", GAME_NDB_REMOTE, tmp],
                                   capture_output=True, text=True, timeout=60)
                if r.returncode == 0 and os.path.exists(tmp):
                    os.replace(tmp, GAME_NDB)
                    break
        except Exception:
            pass
    if not os.path.exists(GAME_NDB):
        return {}
    names = {}
    try:
        con = sqlite3.connect(GAME_NDB)
        for code, msg in con.execute(
                "select dataCode, msg from lang_unit where language='en' and msgType='UNIT'"):
            if code.startswith("u") and code.endswith("_snm"):
                names[code[:-4]] = msg
        con.close()
    except Exception:
        return {}
    return names


def _merge_game_units(units):
    """เติมเรนเจอร์ที่ catalog ภายนอกยังไม่มี (ตัวใหม่) จากไฟล์ภาษาของเกม — เฉพาะร่าง e (ปกติ) และ u (UR)"""
    import re
    have = {u["code"].lower() for u in units}
    have_base = {_base_code(c) for c in have}
    # catalog ภายนอกมีแค่ตัว 6★ -> เติมเฉพาะเลขรหัสที่ใหม่กว่าตัวล่าสุดของมัน (= ตัวที่เพิ่งออก)
    newest = max((int(m.group(1)) for c in have for m in [re.match(r"^u(\d+)", c)] if m), default=0)
    extra = []
    for code, name in sorted(_game_unit_names().items(), reverse=True):
        m = re.match(r"^u(\d+)([eu])-", code)
        # >= 2000 = ตัวพิเศษ/tutorial/ทดสอบ ไม่ใช่ตัวกาชา
        if not m or not newest < int(m.group(1)) < 2000 or code in have or _base_code(code) in have_base:
            continue
        extra.append({"name": name + ("UR" if m.group(2) == "u" else ""), "code": code, "kind": "ranger",
                      "img": IMG_BASE + "/" + code + "/" + code + "-thum.png", "src": "game"})
    return extra + units


def build_catalog(force=False):
    """
    ดึงรายชื่อตัวละคร+เกียร์ทั้งหมด (พร้อมชื่อจริง) แบบเดียวกับเว็บ zippyranger -> cache ลงไฟล์
    โครงจากต้นทาง: [{name, unit, gear}]  (unit=โค้ดเรนเจอร์, gear=โค้ดเกียร์; อีกฝั่งจะว่าง)
    """
    global _CATALOG
    with _CATALOG_LOCK:
        fresh = (os.path.exists(CATALOG_CACHE)
                 and time.time() - os.path.getmtime(CATALOG_CACHE) < CATALOG_TTL)
        if _CATALOG is not None and _CATALOG.get("ok") and fresh and not force:
            return _CATALOG
        old = None
        if os.path.exists(CATALOG_CACHE):
            try:
                old = json.load(open(CATALOG_CACHE, encoding="utf-8"))
            except Exception:
                old = None
        if old and fresh and not force:
            _CATALOG = old
            return _CATALOG
        try:
            import requests
            r = requests.get(CATALOG_SRC, timeout=60, headers={
                "Referer": "https://zippyranger.online/",
                "Origin": "https://zippyranger.online",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
                "Accept": "*/*",
                "X-Requested-With": "XMLHttpRequest",
            })
            j = r.json()
            data = j.get("d") or []
        except Exception as e:
            # ดึงใหม่ไม่ได้ -> ใช้ของเก่าไปก่อน (ไม่ให้หน้าว่าง)
            data = []
            err = str(e)
        if not data:
            # ต้นทางล่ม -> ใช้ของเก่า + เติมตัวใหม่จากไฟล์เกม (ไม่ให้หน้าว่าง)
            if old:
                base = [u for u in old.get("units", []) if u.get("src") != "game"]
                old["units"] = _merge_game_units(base)
                old["count"] = len(old["units"])
                old["rangers"] = sum(1 for u in old["units"] if u["kind"] == "ranger")
                old["gears"] = old["count"] - old["rangers"]
                _CATALOG = old
            else:
                _CATALOG = {"ok": False, "err": locals().get("err", "empty"), "units": []}
            return _CATALOG
        units = []
        for x in data:
            name = x.get("name") or ""
            unit = x.get("unit") or ""
            gear = x.get("gear") or ""
            if gear:
                units.append({"name": name, "code": gear, "kind": "gear",
                              "img": IMG_BASE + "/gear_icon/" + gear + "_icon.png"})
            elif unit:
                units.append({"name": name, "code": unit, "kind": "ranger",
                              "img": IMG_BASE + "/" + unit + "/" + unit + "-thum.png"})
        units = _merge_game_units(units)
        nr = sum(1 for u in units if u["kind"] == "ranger")
        _CATALOG = {"ok": True, "updated": int(time.time()), "count": len(units), "rangers": nr,
                    "gears": len(units) - nr, "img_base": IMG_BASE, "units": units}
        try:
            json.dump(_CATALOG, open(CATALOG_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass
        return _CATALOG


def _base_code(code):
    """ตัด tier วิวัฒนาการออก: u1617e-ka / u1617u-ka -> u1617-ka (จับได้ทุกร่าง)"""
    import re
    return re.sub(r"^(u\d+)[a-z]+(-.+)$", r"\1\2", code or "")


def match_hits(owned_codes, targets):
    """
    คืนรายชื่อ target ที่บัญชีมี
    - target เป็นโค้ดเต็ม (จาก picker เช่น u1452e-ka=Kagura) -> จับ "ทุกร่าง" (เทียบ base code)
      เลือก Kagura หรือ KaguraUR ก็เจอบัญชีที่มีตัวนี้ร่างใดก็ได้
    - target เป็นข้อความอิสระ (เช่น '-ka', 'brown') -> จับแบบ substring
    """
    owned = set(c.lower() for c in owned_codes)
    owned_base = set(_base_code(c) for c in owned)
    hits = []
    for t in targets:
        tl = t.lower().strip()
        if not tl:
            continue
        if tl.startswith("u") and "-" in tl:            # โค้ดเต็ม -> จับทุกร่าง
            if tl in owned or _base_code(tl) in owned_base:
                hits.append(t)
        else:                                            # ข้อความอิสระ
            if any(tl in c for c in owned):
                hits.append(t)
    return hits


def account_summary(key, cred):
    """ค่าที่แคชไว้ใน creds.json (เร็ว ไม่ยิง API) — ใช้เรนเดอร์ตารางทันที"""
    def _int(v, d=0):
        try:
            return int(float(v))
        except Exception:
            return d
    return {
        "key": key,
        "rsn": cred.get("rsn", key),
        "file": cred.get("file", "-"),
        "ruby": _int(cred.get("ruby")),
        "coin": _int(cred.get("coin")),
        "ticket": _int(cred.get("ticket")),
        "level": _int(cred.get("level"), 1),
        "has_cred": bool(cred.get("udid") and cred.get("LF_AC")),
        "has_xml": bool(xml_path_for(key)),
    }


def check_account(key, targets):
    """เช็คบัญชีเดียวสด ๆ ผ่าน API -> heroes + hits + ค่าล่าสุด, เก็บ LF_AC ที่หมุนกลับ creds.json"""
    creds = load_creds()
    cred = creds.get(key)
    if not cred:
        return {"ok": False, "key": key, "err": "ไม่พบบัญชีนี้ใน creds.json"}
    udid, lf = cred.get("udid"), cred.get("LF_AC")
    if not (udid and lf):
        return {"ok": False, "key": key, "err": "ไม่มี udid/LF_AC"}

    cli = LGRClient(udid, lf)
    st, codes, team_slots, home = account_units_info(cli)
    # session หมดอายุ -> ขอใหม่ด้วย guestCookie
    if st != 200 and cred.get("guestCookie"):
        cli.login(cred["guestCookie"])
        st, codes, team_slots, home = account_units_info(cli)

    if st != 200 or not isinstance(home, dict):
        # เก็บ LF_AC ที่อาจหมุนไปแล้ว
        _persist(key, {"LF_AC": cli.lf_ac})
        err = ("IP โดนบล็อก (403) — เปลี่ยน WG แล้วก็ยังไม่ผ่าน" if st == 403
               else f"เช็คไม่ได้ (status {st})")
        return {"ok": False, "key": key, "status": st, "err": err}

    res = home.get("result", {}) or {}
    player = res.get("player") or {}
    ruby = parse_ruby(res, player) or 0
    coin = parse_coin(res, player) or 0
    ticket = cli.ticket_count().get("total", 0)
    level = player.get("level") or res.get("level") or 1
    hits = match_hits(codes, targets)

    save_err = _persist(key, {
        "LF_AC": cli.lf_ac, "ruby": ruby, "coin": coin,
        "ticket": ticket, "level": level,
    })

    return {
        "ok": True,
        **({"save_err": save_err} if save_err else {}),
        "key": key,
        "rsn": player.get("rsn") or res.get("rsn") or key,
        "userName": player.get("userName"),
        "level": level,
        "ruby": ruby,
        "coin": coin,
        "ticket": ticket,
        "heroes": codes,          # unit codes ทั้งหมดในบัญชี
        "team": team_slots,       # ตัวในทีม (มี Lv.)
        "hits": hits,             # ตัวเป้าที่เจอ
        "file": cred.get("file", "-"),
    }


def _persist(key, fields):
    """เขียนค่ากลับ creds.json แบบปลอดภัย (ไม่ทับบัญชีอื่น): update_creds ถือ lock ข้ามโปรเซส
    + merge เฉพาะ field ของบัญชีนี้ลงไฟล์ล่าสุด ; คืน error (str) หรือ None"""
    with _SAVE_LOCK:
        _, err = _api_try_update_creds({key: fields}, CREDS_FILE)
    return err


def gift_account(key, missions=True):
    """รับของ 1 บัญชี: กล่องของขวัญทั้งหมด (+ รางวัลภารกิจที่ทำครบแล้ว) แล้วคืน ruby/ตั๋วล่าสุด"""
    creds = load_creds()
    cred = creds.get(key)
    if not cred:
        return {"ok": False, "key": key, "err": "ไม่พบบัญชีนี้ใน creds.json"}
    c = LGRClient(cred["udid"], cred["LF_AC"])
    st, _ = c.home()
    if st != 200 and cred.get("guestCookie"):
        if c.login(cred["guestCookie"])[0] == 200:
            st, _ = c.home()
    if st != 200:
        _persist(key, {"LF_AC": c.lf_ac})
        err = "IP โดนบล็อก (403)" if st == 403 else f"เข้าเกมไม่ได้ (status {st})"
        return {"ok": False, "key": key, "status": st, "err": err}

    _, before = c.unclaimed_gifts()
    n_before = len(before or [])
    st_r = 200
    if n_before:
        st_r, _ = c.receive_all_gifts()
    _, after = c.unclaimed_gifts()
    gifts = max(0, n_before - len(after or []))
    # log ว่าได้อะไร: ของที่หายจากกล่อง = รับแล้ว
    left = {g.get("uid") for g in (after or [])}
    items = [{"src": "กล่องของขวัญ", "name": g.get("giftName") or g.get("dataCode") or g.get("giftType"),
              "count": g.get("giftCount", 1), "note": g.get("msg") or ""}
             for g in (before or []) if g.get("uid") not in left]

    n_mis = 0
    if missions:
        try:
            r = c.mission_receive_all()
            n_mis = int(r.get("claimed", 0) or 0)
            bad = {f["seq"] for f in r.get("failed", [])}
            for m in r.get("missions", []):
                if m["seq"] in bad:
                    continue
                for rw in (m.get("raw") or {}).get("missionRewards") or []:
                    items.append({"src": "ภารกิจ " + str(m.get("tab", "")).replace("MissionTab", ""),
                                  "name": rw.get("code") or rw.get("rewardType") or "?",
                                  "count": rw.get("amount", 1), "note": m.get("title", "")})
        except Exception:
            pass

    fields = {"LF_AC": c.lf_ac}
    stp, prof = c.home()
    if stp == 200 and isinstance(prof, dict):
        res = prof.get("result", {})
        fields["ruby"] = parse_ruby(res, res.get("player") or {})
    fields["ticket"] = c.ticket_count().get("total", 0)
    if c.guest_cookie_next:
        fields["guestCookie"] = c.guest_cookie_next
    save_err = _persist(key, fields)
    return {"ok": st_r == 200, "key": key, "gifts": gifts, "missions": n_mis, "items": items,
            **({"save_err": save_err} if save_err else {}),
            "ruby": fields.get("ruby"), "ticket": fields["ticket"],
            **({} if st_r == 200 else {"err": f"รับของไม่สำเร็จ (status {st_r})"})}


# ---------- WG proxy ในตัว (แทน wg-proxy.bat) ----------
# เปิด wireproxy เอง: WG conf -> SOCKS5 127.0.0.1:1080 (+ TCP tunnel 9443 ให้ capture_team)
# เลือก conf ที่ยัง "ไม่โดนบล็อก" (ยิง path มั่วต้องได้ 404 ไม่ใช่ 403) ; โดน 403 กลางทาง -> wg_rotate()
WG_DIR = os.path.join(os.path.dirname(HERE), "wg")
WG_EXE = os.path.join(HERE, "tools", "wireproxy.exe")
WG_CONF = os.path.join(HERE, "tools", "wireproxy.conf")
WG_LAST = os.path.join(WEB_DIR, "_wg_last.txt")
WG_PROBE_URL = "https://rangers-api.line-apps.com/v12.3/__probe"
_WG = {"proc": None, "conf": "", "bad": set()}
_WG_LOCK = threading.Lock()


def _port_open(port):
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def _wg_probe():
    """ยิงผ่าน proxy: 404 = ใช้ได้ , 403 = IP โดนบล็อก , 0 = ต่อไม่ติด"""
    import requests
    px = "socks5h://127.0.0.1:1080"
    try:
        return requests.get(WG_PROBE_URL, timeout=12, proxies={"https": px, "http": px}).status_code
    except Exception:
        return 0


def _wg_stop():
    p = _WG.get("proc")
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(5)
        except Exception:
            p.kill()
    _WG["proc"] = None


def _wg_start(conf_name):
    import subprocess
    body = open(os.path.join(WG_DIR, conf_name), encoding="utf-8").read()
    body += ("\n[Socks5]\nBindAddress = 127.0.0.1:1080\n"
             "\n[http]\nBindAddress = 127.0.0.1:1081\n"      # ให้ mitmdump (capture_newid --wg) ออกผ่าน WG
             "\n[TCPClientTunnel]\nBindAddress = 127.0.0.1:9443\nTarget = rangers-api.line-apps.com:443\n")
    with open(WG_CONF, "w", encoding="utf-8") as f:
        f.write(body)
    _WG["proc"] = subprocess.Popen([WG_EXE, "-s", "-c", WG_CONF],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(30):                     # รอ SOCKS ขึ้น
        if _port_open(1080):
            break
        time.sleep(0.2)
    time.sleep(2)                           # รอ handshake WG


def _wg_endpoint(conf_name):
    """host ของ Endpoint ในไฟล์ .conf (= IP ขาออก)"""
    try:
        with open(os.path.join(WG_DIR, conf_name), encoding="utf-8-sig") as f:
            for ln in f:
                if ln.strip().lower().startswith("endpoint"):
                    return ln.split("=", 1)[1].strip().rsplit(":", 1)[0]
    except Exception:
        pass
    return conf_name


def _wg_blocked_eps():
    try:
        with open(os.path.join(WG_DIR, ".blocked.json"), encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _wg_cfg():
    try:
        return json.load(open(os.path.join(os.path.dirname(HERE), "configmain.json"), encoding="utf-8-sig"))
    except Exception:
        return {}


def _wg_replace_blocked(conf_name):
    """เหมือน login.py: จด IP ที่โดนบล็อกลง wg/.blocked.json (ใช้ร่วมกับบอท/wg_gen ไม่สร้างซ้ำ),
    ลบไฟล์ที่ออก IP นั้น, แล้วสั่ง wg_gen สร้างเซิร์ฟเวอร์ใหม่มาแทนให้จำนวนไฟล์เท่าเดิม"""
    lock = os.path.join(WG_DIR, ".gen.lock")
    try:
        if os.path.exists(lock) and time.time() - os.path.getmtime(lock) > 300:
            os.remove(lock)
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except Exception:
        return False                         # บอท/จออื่นกำลังสร้างอยู่
    try:
        ep = _wg_endpoint(conf_name)
        bp = os.path.join(WG_DIR, ".blocked.json")
        try:
            d = json.load(open(bp, encoding="utf-8"))
        except Exception:
            d = {}
        d[ep] = time.time()
        with open(bp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        allc = [f for f in os.listdir(WG_DIR) if f.endswith(".conf")]
        want = len(allc)
        managed = os.path.exists(os.path.join(WG_DIR, ".managed"))
        cfg = _wg_cfg()
        if managed and not int(cfg.get("wg_regen_managed", 1) or 0):
            return False
        kp = os.path.join(WG_DIR, "keypair.txt")
        if managed and not os.path.exists(kp):
            with open(os.path.join(WG_DIR, conf_name), "rb") as a, open(kp, "wb") as b:
                b.write(a.read())
        gone = [f for f in allc if _wg_endpoint(f) == ep] or [conf_name]
        for f in gone:
            try:
                os.remove(os.path.join(WG_DIR, f))
            except OSError:
                pass
        print(f"[wg] ลบ {', '.join(gone)} (เกมบล็อก IP {ep}) -> สร้างเซิร์ฟเวอร์ใหม่มาแทน", flush=True)
        root = os.path.dirname(HERE)
        if root not in sys.path:
            sys.path.insert(0, root)
        import wg_gen
        if managed:
            wg_gen.generate(want, cfg.get("wg_gen_countries") or None, WG_DIR, 0, "", 0, managed_ok=True)
        else:
            wg_gen.generate(want, cfg.get("wg_gen_countries") or None, WG_DIR,
                            int(cfg.get("wg_machine", 0) or 0),
                            str(cfg.get("wg_account", "") or "").strip() or None,
                            int(cfg.get("wg_total_machines", 30) or 30))
        return True
    except Exception as e:
        print(f"[wg] สร้างไฟล์แทนไม่สำเร็จ: {e}", flush=True)
        return False
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def wg_ensure(rotate=False):
    """ให้มี proxy ที่ใช้ได้ -> คืนชื่อ conf ("" = ไม่มีตัวไหนใช้ได้/ไม่มี wireproxy -> ต่อตรง)"""
    import random
    import lgr_api as la
    with _WG_LOCK:
        if not rotate and _port_open(1080) and _wg_probe() == 404:
            la.LGR_PROXY = "socks5h://127.0.0.1:1080"
            return _WG.get("conf") or "(เปิดอยู่แล้ว)"
        if rotate and _WG.get("conf"):
            _WG["bad"].add(_WG["conf"])
            _wg_stop()
            _wg_replace_blocked(_WG["conf"])      # โดนบล็อก -> จด+ลบ+gen ใหม่
        if not (os.path.exists(WG_EXE) and os.path.isdir(WG_DIR)):
            return ""
        blocked = _wg_blocked_eps()
        confs = [f for f in os.listdir(WG_DIR) if f.endswith(".conf") and f not in _WG["bad"]
                 and _wg_endpoint(f) not in blocked]
        random.shuffle(confs)
        try:                                 # ลองตัวที่ใช้ได้ล่าสุดก่อน
            last = open(WG_LAST, encoding="utf-8").read().strip()
            if last in confs:
                confs.remove(last)
                confs.insert(0, last)
        except Exception:
            pass
        tries = 0
        while confs and tries < 12:          # confs อาจยาวขึ้นระหว่างทาง (ไฟล์ที่เพิ่ง gen)
            conf = confs.pop(0)
            tries += 1
            _wg_stop()
            if _port_open(1080):             # มี wireproxy ตัวอื่น (wg-proxy.bat) ค้างอยู่
                print("[wg] พอร์ต 1080 ถูกใช้อยู่ — ปิด wg-proxy.bat ตัวเก่าก่อน", flush=True)
                return ""
            _wg_start(conf)
            code = _wg_probe()
            print(f"[wg] {conf} -> {code}", flush=True)
            if code == 403:                  # เกมบล็อก IP นี้ -> จด+ลบ+gen ใหม่ (ไฟล์ใหม่ใช้รอบหน้า/ตัวถัดไป)
                _wg_stop()
                if _wg_replace_blocked(conf):
                    blocked = _wg_blocked_eps()
                    fresh = [f for f in os.listdir(WG_DIR) if f.endswith(".conf") and f not in confs
                             and f not in _WG["bad"] and _wg_endpoint(f) not in blocked]
                    confs.extend(fresh)       # ลองไฟล์ที่เพิ่ง gen ต่อในรอบนี้เลย
            if code == 404:
                _WG["conf"] = conf
                la.LGR_PROXY = "socks5h://127.0.0.1:1080"
                try:
                    with open(WG_LAST, "w", encoding="utf-8") as f:
                        f.write(conf)
                except Exception:
                    pass
                return conf
            _WG["bad"].add(conf)
        _wg_stop()
        return ""


_WG_ROT = {"t": 0.0}


def wg_rotate():
    """เปลี่ยน WG ; หลายเธรดเจอ 403 พร้อมกัน -> เปลี่ยนครั้งเดียว (ภายใน 30 วิ ถือว่าเปลี่ยนแล้ว)"""
    if time.time() - _WG_ROT["t"] < 30 and _WG.get("conf"):
        return _WG["conf"]
    with _WG_LOCK:
        pass                                   # รอเธรดที่กำลังเปลี่ยนอยู่ให้เสร็จก่อน
    if time.time() - _WG_ROT["t"] < 30 and _WG.get("conf"):
        return _WG["conf"]
    print("[wg] IP โดนบล็อก -> เปลี่ยน WG", flush=True)
    conf = wg_ensure(rotate=True)
    _WG_ROT["t"] = time.time()
    return conf


def with_wg_retry(fn, *a, **kw):
    """เรียก fn ; ได้ 403 (IP โดนบล็อก) -> เปลี่ยน WG แล้วลองใหม่ 1 ครั้ง (ใช้กับเช็ค/รับของ/กาชา)"""
    r = fn(*a, **kw)
    if isinstance(r, dict) and not r.get("ok") and (r.get("status") == 403 or "403" in str(r.get("err", ""))):
        if wg_rotate():
            r = fn(*a, **kw)
    return r


# ---------- เข้าเกมประจำวัน (เช็คอิน) อัตโนมัติ ----------
# ล็อกอิน/home = นับเป็นเข้าเกมวันนั้น -> ของเช็คอิน (ATTDNCEVNT) เข้ากล่องของขวัญเอง
# /attendance/cbu = ดูวันสะสม ; จากนั้นรับของในกล่อง + ภารกิจ (gift_account)
DAILY_FILE = os.path.join(WEB_DIR, "_daily.json")
DAILY_AT = os.environ.get("LGR_DAILY_AT", "06:00")      # เวลาเริ่มรอบประจำวัน (HH:MM เวลาเครื่อง)
_DAILY = {"running": False, "last_date": "", "done": 0, "total": 0, "results": []}
_DAILY_LOCK = threading.Lock()


def _daily_load():
    try:
        _DAILY.update(json.load(open(DAILY_FILE, encoding="utf-8")))
    except Exception:
        pass
    _DAILY["running"] = False


def _daily_save():
    try:
        json.dump({k: v for k, v in _DAILY.items() if k != "running"},
                  open(DAILY_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass


def daily_account(key):
    """เข้าเกม 1 บัญชี: เช็คอิน + รับของ -> สรุปสั้น"""
    r = gift_account(key)                    # home/login (= เช็คอิน) + กล่องของขวัญ + ภารกิจ
    out = {"key": key, "ok": r.get("ok"), "err": r.get("err"), "status": r.get("status"), "gifts": r.get("gifts", 0),
           "missions": r.get("missions", 0), "items": r.get("items", []),
           "ruby": r.get("ruby"), "ticket": r.get("ticket"), "time": time.strftime("%H:%M:%S")}
    if r.get("ok"):
        try:
            cred = load_creds().get(key) or {}
            c = LGRClient(cred["udid"], cred["LF_AC"])
            st, d = c.call("GET", "/attendance/cbu")
            _persist(key, {"LF_AC": c.lf_ac})
            if st == 200 and isinstance(d, dict):
                a = d.get("result") or {}
                out["attend_days"] = a.get("accumulateDays")
                out["attend_title"] = a.get("title")
        except Exception:
            pass
    return out


def daily_run(force=False):
    """รอบประจำวัน: ทุกบัญชีทีละตัว (backend จำกัดความถี่อยู่แล้ว) ; วันละครั้ง เว้นแต่ force"""
    today = time.strftime("%Y-%m-%d")
    with _DAILY_LOCK:
        if _DAILY["running"] or (_DAILY.get("last_date") == today and not force):
            return False
        _DAILY.update(running=True, done=0, results=[], started=time.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        keys = list(load_creds().keys())
        _DAILY["total"] = len(keys)
        print(f"[daily] เริ่มเข้าเกมประจำวัน {len(keys)} บัญชี", flush=True)
        for k in keys:
            try:
                res = daily_account(k)
            except Exception as e:
                res = {"key": k, "ok": False, "err": str(e), "time": time.strftime("%H:%M:%S")}
            _DAILY["results"].append(res)
            _DAILY["done"] += 1
            print(f"[daily] {k}: " + ("ok" if res.get("ok") else f"ไม่ได้ ({res.get('err')})")
                  + (f" · เช็คอินวันที่ {res.get('attend_days')}" if res.get("attend_days") else "")
                  + f" · ของ {res.get('gifts', 0)} · ภารกิจ {res.get('missions', 0)}", flush=True)
            if res.get("status") == 403 or "403" in str(res.get("err", "")):
                if not wg_rotate():
                    print("[daily] IP โดนบล็อก (403) และหา WG ใหม่ไม่ได้ -> หยุดรอบนี้", flush=True)
                    break
                _DAILY["results"][-1] = daily_account(k)      # ลองไอดีนี้ใหม่ด้วย IP ใหม่
        _DAILY["last_date"] = today
        _DAILY["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    finally:
        _DAILY["running"] = False
        _daily_save()
    return True


def _daily_scheduler():
    """เช็คทุกนาที: ถึงเวลา DAILY_AT และวันนี้ยังไม่ได้ทำ -> รันรอบประจำวัน"""
    while True:
        try:
            if time.strftime("%H:%M") >= DAILY_AT and _DAILY.get("last_date") != time.strftime("%Y-%m-%d"):
                daily_run()
        except Exception as e:
            print(f"[daily] error: {e}", flush=True)
        time.sleep(60)


def mission_account(key, claim=True):
    """เช็ค/รับ ภารกิจของบัญชีเดียว (ใช้กับ GET /api/missions)"""
    creds = load_creds()
    cred = creds.get(key)
    if not cred:
        return {"ok": False, "key": key, "err": "ไม่พบบัญชีนี้ใน creds.json"}

    c = LGRClient(cred["udid"], cred["LF_AC"])
    st, _ = c.home()
    if st != 200 and cred.get("guestCookie"):
        st_l, _ = c.login(cred["guestCookie"])
        if st_l == 200:
            st, _ = c.home()
    if st != 200:
        return {"ok": False, "key": key, "step": "home", "status": st}

    if not claim:
        st_l, pending = c.mission_pending()
        _persist(key, {"LF_AC": c.lf_ac})
        return {"ok": st_l == 200, "key": key, "status": st_l, "claimed": 0,
                "pending": len(pending),
                "missions": [{"seq": m["seq"], "title": m["title"]} for m in pending]}

    r = c.mission_receive_all()
    _persist(key, {"LF_AC": c.lf_ac})
    r["key"] = key
    r["missions"] = [{"seq": m["seq"], "title": m["title"]} for m in r.get("missions", [])]
    return r


def _catalog_names():
    """code(lower) -> ชื่อจริง จาก catalog (ไว้โชว์ผลกาชา)"""
    cat = build_catalog()
    return {u["code"].lower(): u["name"] for u in cat.get("units", []) if u.get("code")}


def _name_for(code):
    if not code:
        return code
    names = _catalog_names()
    c = code.lower()
    return names.get(c) or names.get(_base_code(c)) or code


def _client_ready(key):
    """สร้าง client ที่ล็อกอินแล้ว (คืน (client, cred) หรือ (None, err_dict))"""
    creds = load_creds()
    cred = creds.get(key)
    if not cred:
        return None, {"ok": False, "key": key, "err": "ไม่พบบัญชีนี้ใน creds.json"}
    c = LGRClient(cred["udid"], cred["LF_AC"])
    st, _ = c.home()
    if st != 200 and cred.get("guestCookie"):
        st_l, _ = c.login(cred["guestCookie"])
        if st_l == 200:
            st, _ = c.home()
    if st != 200:
        return None, {"ok": False, "key": key, "step": "home", "status": st}
    return c, cred


def gacha_info_account(key):
    """รายการตู้กาชาที่บัญชีนี้เปิดยิงได้ (groupId/gachaId/index + ราคา) พร้อมยอด ruby"""
    c, cred = _client_ready(key)
    if c is None:
        return cred
    st, d = c.gacha_info()
    _persist(key, {"LF_AC": c.lf_ac})
    if st != 200 or not isinstance(d, dict):
        return {"ok": False, "key": key, "step": "gacha/info", "status": st}
    groups = []
    for grp in d.get("result", {}).get("gachaGroupResponseList", []) or []:
        gg = grp.get("gachaGroup", {}) or {}
        title = ", ".join(_name_for(rc) for rc in gg.get("titleRewardCodes", []) or [])
        bg = gg.get("bgUrl") or {}
        lbg = gg.get("listBgUrl") or {}
        banner = {
            "name": gg.get("gachaName") or gg.get("groupId"),
            "bg": bg.get("th") or bg.get("en") or next(iter(bg.values()), ""),
            "listBg": lbg.get("th") or lbg.get("en") or next(iter(lbg.values()), ""),
            "start": gg.get("exposureStartDate"),
            "end": gg.get("exposureEndDate"),
            "sort": gg.get("sortOrder", 0),
        }
        for gi in gg.get("gachaGroupInfos", []) or []:
            groups.append({
                **banner,
                "title": title,
                "featured": gg.get("titleRewardCodes", []) or [],
                "display": gg.get("gachaDisplayType", ""),
                "badge": gg.get("gachaBadgeType", ""),
                "ticketCost": gi.get("ticketPayableCost") if gi.get("ticketPayableType") == "TICKET" else 0,
                "groupId": gi.get("groupId"),
                "gachaId": gi.get("gachaId"),
                "index": gi.get("gachaIndex", 1),
                "count": gi.get("gachaCount", 1),
                "bonus": gi.get("bonusCount", 0),
                "payType": gi.get("gachaPlayType") or gi.get("gachaType"),
                "needRuby": gi.get("needRuby", 0),
                "needFriendship": gi.get("needFriendship", 0),
                "needEventTicket": gi.get("needEventTicket", 0),
                "displayRuby": gi.get("displayRubyPrice", gi.get("needRuby", 0)),
            })
    tk = c.ticket_count()
    ruby = cred.get("ruby", 0)
    return {"ok": True, "key": key, "ruby": ruby,
            "tickets": tk, "groups": groups}


def gacha_pull_account(key, group_id, gacha_id, index=1, targets=None, max_pulls=1, pay="ruby"):
    """
    สุ่มกาชา: ยิง (reserve->confirm) ซ้ำได้ถึง max_pulls ครั้ง
    ถ้าใส่ targets (list โค้ดตัวที่อยากได้) จะหยุดทันทีที่สุ่มติดตัวใดตัวหนึ่ง (รีโรล)
    """
    c, cred = _client_ready(key)
    if c is None:
        return cred
    targets = [t.lower().strip() for t in (targets or []) if t.strip()]
    tbase = set(_base_code(t) for t in targets)
    pulls = []
    hit = None
    sel = None
    st_i, d_i = c.gacha_info()
    for grp in (d_i or {}).get("result", {}).get("gachaGroupResponseList", []) if st_i == 200 else []:
        for gi in (grp.get("gachaGroup") or {}).get("gachaGroupInfos", []) or []:
            if (gi.get("groupId"), gi.get("gachaId"), gi.get("gachaIndex", 1)) == (group_id, gacha_id, index):
                sel = gi
    _, prof = c.home()
    res = (prof or {}).get("result", {}) if isinstance(prof, dict) else {}
    ruby = parse_ruby(res, res.get("player") or {}) or 0
    tickets = c.ticket_count().get("premium", 0)
    n = int(max_pulls)
    for i in range(n if n > 0 else 10**6):          # max=0 -> สุ่มจนหมด
        use_t, cost = gacha_pick_pay(pay, sel, ruby, tickets)
        if use_t is None:
            if not pulls:
                pulls.append({"n": i + 1, "status": 0, "err": cost})
            break
        if i:
            time.sleep(1.2)   # กัน 429
        st, rewards, raw = c.gacha_pull(group_id, gacha_id, index, use_ticket=use_t)
        if st == 200:
            if use_t:
                tickets -= cost
            else:
                ruby -= cost
        if st != 200:
            pulls.append({"n": i + 1, "status": st, "err": str(raw)[:160]})
            break
        named = [{"code": rc, "name": _name_for(rc.split(":", 1)[-1])} for rc in rewards]
        pulls.append({"n": i + 1, "rewards": named})
        if targets:
            for rc in rewards:
                code = rc.split(":", 1)[-1].lower()
                if code in targets or _base_code(code) in tbase:
                    hit = {"code": code, "name": _name_for(code), "pull": i + 1}
                    break
            if hit:
                break
    # เก็บ LF_AC + ruby ล่าสุด
    fields = {"LF_AC": c.lf_ac}
    stp, prof = c.home()
    if stp == 200 and isinstance(prof, dict):
        res = prof.get("result", {})
        fields["ruby"] = parse_ruby(res, res.get("player") or {})
    save_err = _persist(key, fields)
    return {"ok": True, "key": key, "pulls": pulls, "hit": hit,
            **({"save_err": save_err} if save_err else {}),
            "count": len(pulls), "ruby": fields.get("ruby", cred.get("ruby", 0)), "tickets": tickets}


# ---------------------------------------------------------------- HTTP

def _json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # เงียบ

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        u = urlparse(self.path)
        path, qs = u.path, parse_qs(u.query)

        if path == "/" or path == "/index.html":
            f = os.path.join(WEB_DIR, "index.html")
            if os.path.exists(f):
                with open(f, "rb") as fh:
                    self._send(200, fh.read(), "text/html; charset=utf-8")
            else:
                self._send(404, b"index.html not found")
            return

        if path == "/api/accounts":
            creds = load_creds()
            accounts = [account_summary(k, v) for k, v in creds.items()]
            self._send(200, _json_bytes({
                "count": len(accounts),
                "accounts": accounts,
                "targets": default_targets(),
                "creds_file": CREDS_FILE,
            }))
            return

        if path == "/api/catalog":
            self._send(200, _json_bytes(build_catalog(force=(qs.get("force") == ["1"]))))
            return

        if path == "/api/check":
            key = (qs.get("id") or [""])[0]
            tstr = (qs.get("targets") or [""])[0]
            targets = [t.strip().lower() for t in tstr.split(",") if t.strip()] or default_targets()
            if not key:
                self._send(400, _json_bytes({"ok": False, "err": "ต้องระบุ id"}))
                return
            try:
                self._send(200, _json_bytes(with_wg_retry(check_account, key, targets)))
            except Exception as e:
                self._send(200, _json_bytes({"ok": False, "key": key, "err": str(e)}))
            return

        # รับของ: กล่องของขวัญ + รางวัลภารกิจ  ?id=<key>  (&missions=0 = เฉพาะกล่องของขวัญ)
        if path == "/api/gifts":
            key = (qs.get("id") or [""])[0]
            if not key:
                self._send(400, _json_bytes({"ok": False, "err": "ต้องระบุ id"}))
                return
            try:
                self._send(200, _json_bytes(with_wg_retry(gift_account, key, (qs.get("missions") or ["1"])[0] != "0")))
            except Exception as e:
                self._send(200, _json_bytes({"ok": False, "key": key, "err": str(e)}))
            return

        # ภารกิจ: ?id=<key>  (&claim=0 = ดูอย่างเดียว ไม่รับ)
        if path in ("/api/missions", "/api/sevendays"):   # ชื่อเดิมยังใช้ได้
            key = (qs.get("id") or [""])[0]
            claim = (qs.get("claim") or ["1"])[0] != "0"
            if not key:
                self._send(400, _json_bytes({"ok": False, "err": "ต้องระบุ id"}))
                return
            try:
                self._send(200, _json_bytes(mission_account(key, claim)))
            except Exception as e:
                self._send(200, _json_bytes({"ok": False, "key": key, "err": str(e)}))
            return

        # กาชา: รายการตู้ที่ยิงได้ + ruby/ตั๋ว
        if path == "/api/gacha/info":
            key = (qs.get("id") or [""])[0]
            if not key:
                self._send(400, _json_bytes({"ok": False, "err": "ต้องระบุ id"}))
                return
            try:
                self._send(200, _json_bytes(with_wg_retry(gacha_info_account, key)))
            except Exception as e:
                self._send(200, _json_bytes({"ok": False, "key": key, "err": str(e)}))
            return

        # กาชา: สุ่ม/รีโรล — group,gacha,index + targets(โค้ด, คั่นด้วย ,) + max
        if path == "/api/gacha/pull":
            key = (qs.get("id") or [""])[0]
            group = (qs.get("group") or [""])[0]
            gacha = (qs.get("gacha") or [""])[0]
            index = int((qs.get("index") or ["1"])[0] or 1)
            maxp = int((qs.get("max") or ["1"])[0] or 0)
            pay = (qs.get("pay") or ["ruby"])[0]
            tstr = (qs.get("targets") or [""])[0]
            targets = [t.strip() for t in tstr.split(",") if t.strip()]
            if not (key and group and gacha):
                self._send(400, _json_bytes({"ok": False, "err": "ต้องระบุ id, group, gacha"}))
                return
            try:
                self._send(200, _json_bytes(
                    gacha_pull_account(key, group, gacha, index, targets, maxp, pay)))
            except Exception as e:
                self._send(200, _json_bytes({"ok": False, "key": key, "err": str(e)}))
            return

        # ดาวน์โหลด .xml ต้นฉบับ 1 บัญชี
        if path == "/api/xml":
            key = (qs.get("id") or [""])[0]
            p = xml_path_for(key)
            if not p or not os.path.exists(p):
                self._send(404, _json_bytes({"ok": False, "err": "ไม่พบไฟล์ .xml ต้นฉบับของบัญชีนี้"}))
                return
            with open(p, "rb") as fh:
                data = fh.read()
            self._send(200, data, "application/xml; charset=utf-8",
                       extra={"Content-Disposition": f'attachment; filename="{os.path.basename(p)}"'})
            return

        # ดาวน์โหลด .xml หลายบัญชีเป็น .zip (id=a,b,c)
        # หลัง Auto สุ่ม: แยกไฟล์ .xml เจอเป้า/ไม่เจอ  ?hit=key:ชื่อ,key:ชื่อ&miss=key,key  (&zip=1 = ดาวน์โหลดด้วย)
        if path == "/api/auto_export":
            import io, zipfile
            hits = []
            for x in (qs.get("hit") or [""])[0].split(","):
                if ":" in x:
                    k, n = x.split(":", 1)
                    hits.append((k, n))
            misses = [x for x in (qs.get("miss") or [""])[0].split(",") if x]
            out, files = auto_export(hits, misses, (qs.get("dir") or [""])[0])
            if (qs.get("zip") or ["0"])[0] != "1":
                self._send(200, _json_bytes({"ok": True, "dir": out, "count": len(files),
                                             "hit": sum(1 for a, _ in files if a.startswith("เจอเป้า")),
                                             "miss": sum(1 for a, _ in files if a.startswith("norandom"))}))
                return
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for arc, pth in files:
                    zf.write(pth, arcname=arc)
            self._send(200, buf.getvalue(), "application/zip",
                       extra={"Content-Disposition": f'attachment; filename="{os.path.basename(out)}.zip"'})
            return

        # เข้าเกมประจำวัน: GET /api/daily = สถานะ ; /api/daily?run=1 = รันเดี๋ยวนี้ (force)
        # WG: GET /api/wg = สถานะ ; ?rotate=1 = เปลี่ยน IP (เมื่อโดน 403)
        if path == "/api/wg":
            import lgr_api as la
            conf = wg_rotate() if (qs.get("rotate") or ["0"])[0] == "1" else _WG.get("conf", "")
            self._send(200, _json_bytes({"ok": bool(conf), "conf": conf, "proxy": la.LGR_PROXY}))
            return

        if path == "/api/daily":
            if (qs.get("run") or ["0"])[0] == "1":
                threading.Thread(target=daily_run, kwargs={"force": True}, daemon=True).start()
                time.sleep(0.3)
            self._send(200, _json_bytes({"ok": True, "at": DAILY_AT, **_DAILY}))
            return

        if path == "/api/xml_zip":
            import io, zipfile
            ids = [x for x in (qs.get("id") or [""])[0].split(",") if x]
            if not ids:
                self._send(400, _json_bytes({"ok": False, "err": "ต้องระบุ id"}))
                return
            buf = io.BytesIO()
            n = 0
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for k in ids:
                    p = xml_path_for(k)
                    if p and os.path.exists(p):
                        zf.write(p, arcname=os.path.basename(p))
                        n += 1
            if n == 0:
                self._send(404, _json_bytes({"ok": False, "err": "ไม่พบไฟล์ .xml ของบัญชีที่เลือก"}))
                return
            self._send(200, buf.getvalue(), "application/zip",
                       extra={"Content-Disposition": f'attachment; filename="lgr_xml_{n}.zip"'})
            return

        self._send(404, _json_bytes({"err": "not found"}))


def main():
    ap = argparse.ArgumentParser(description="เว็บเช็ค ranger จาก creds.json (local)")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--host", default="127.0.0.1",
                    help="ดีฟอลต์ 127.0.0.1 (local เท่านั้น) — อย่าตั้ง 0.0.0.0 เว้นแต่รู้ว่าทำอะไรอยู่")
    ap.add_argument("--no-wg", action="store_true", help="ไม่เปิด WG proxy ในตัว (ต่อเน็ตตรง)")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    n = len(load_creds())
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"[!] คำเตือน: กำลัง bind {args.host} — creds.json เป็น cookie บัญชีจริง เปิดออกนอกเครื่องเสี่ยงมาก", flush=True)
    # เปิด WG proxy ในตัว (ไม่ต้องเปิด wg-proxy.bat แยก) ; --no-wg = ต่อตรง
    if not args.no_wg:
        import atexit
        atexit.register(_wg_stop)
        print("[*] กำลังเปิด WG proxy …", flush=True)
        print(f"[*] WG: {wg_ensure() or 'ใช้ไม่ได้ -> ต่อตรง'}", flush=True)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[*] เปิดเว็บแล้ว: http://{args.host}:{args.port}   (บัญชีใน creds.json: {n})", flush=True)
    import lgr_api as _la
    print(f"[*] ออกเน็ต API: {_la.LGR_PROXY or 'ตรง (ถ้าโดน 403 ให้เปิด wg-proxy.bat แล้วรันเว็บใหม่)'}", flush=True)
    print(f"[*] creds: {CREDS_FILE}", flush=True)
    _daily_load()
    threading.Thread(target=_daily_scheduler, daemon=True).start()
    print(f"[*] เข้าเกมประจำวันอัตโนมัติ: ทุกวันเวลา {DAILY_AT} (ตั้งด้วย LGR_DAILY_AT) "
          f"· ล่าสุด {_DAILY.get('last_date') or '-'}", flush=True)
    print("[*] Ctrl+C เพื่อปิด", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] ปิดเว็บแล้ว", flush=True)
        srv.shutdown()


if __name__ == "__main__":
    main()
