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
    load_creds as _api_load_creds,
    save_creds as _api_save_creds,
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


CATALOG_CACHE = os.path.join(WEB_DIR, "_catalog.json")
# ใช้ "วิธีเดียวกับเว็บ zippyranger" — ดึง catalog (ชื่อจริง+โค้ด, เรนเจอร์+เกียร์) จาก gateway ของมันเอง
CATALOG_SRC = "https://zippyranger.online/api/gateway?act=g"
IMG_BASE = "https://rangers.lerico.net/res"
_CATALOG = None
_CATALOG_LOCK = threading.Lock()


def build_catalog(force=False):
    """
    ดึงรายชื่อตัวละคร+เกียร์ทั้งหมด (พร้อมชื่อจริง) แบบเดียวกับเว็บ zippyranger -> cache ลงไฟล์
    โครงจากต้นทาง: [{name, unit, gear}]  (unit=โค้ดเรนเจอร์, gear=โค้ดเกียร์; อีกฝั่งจะว่าง)
    """
    global _CATALOG
    with _CATALOG_LOCK:
        if _CATALOG is not None and not force:
            return _CATALOG
        if os.path.exists(CATALOG_CACHE) and not force:
            try:
                _CATALOG = json.load(open(CATALOG_CACHE, encoding="utf-8"))
                return _CATALOG
            except Exception:
                pass
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
            _CATALOG = {"ok": False, "err": str(e), "units": []}
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
        nr = sum(1 for u in units if u["kind"] == "ranger")
        _CATALOG = {"ok": True, "count": len(units), "rangers": nr,
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
        return {"ok": False, "key": key, "status": st, "err": f"เช็คไม่ได้ (status {st})"}

    res = home.get("result", {}) or {}
    player = res.get("player") or {}
    ruby = parse_ruby(res, player) or 0
    coin = parse_coin(res, player) or 0
    ticket = cli.ticket_count().get("total", 0)
    level = player.get("level") or res.get("level") or 1
    hits = match_hits(codes, targets)

    _persist(key, {
        "LF_AC": cli.lf_ac, "ruby": ruby, "coin": coin,
        "ticket": ticket, "level": level,
    })

    return {
        "ok": True,
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
    """เขียนค่ากลับ creds.json แบบปลอดภัย (ไม่ทับบัญชีอื่น)"""
    with _SAVE_LOCK:
        creds = load_creds()
        if key in creds:
            for k, v in fields.items():
                if v is not None:
                    creds[key][k] = v
            _api_save_creds(creds, CREDS_FILE)


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
        for gi in gg.get("gachaGroupInfos", []) or []:
            groups.append({
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


def gacha_pull_account(key, group_id, gacha_id, index=1, targets=None, max_pulls=1):
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
    for i in range(max(1, int(max_pulls))):
        st, rewards, raw = c.gacha_pull(group_id, gacha_id, index)
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
    _persist(key, fields)
    return {"ok": True, "key": key, "pulls": pulls, "hit": hit,
            "count": len(pulls), "ruby": fields.get("ruby", cred.get("ruby", 0))}


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
                self._send(200, _json_bytes(check_account(key, targets)))
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
                self._send(200, _json_bytes(gacha_info_account(key)))
            except Exception as e:
                self._send(200, _json_bytes({"ok": False, "key": key, "err": str(e)}))
            return

        # กาชา: สุ่ม/รีโรล — group,gacha,index + targets(โค้ด, คั่นด้วย ,) + max
        if path == "/api/gacha/pull":
            key = (qs.get("id") or [""])[0]
            group = (qs.get("group") or [""])[0]
            gacha = (qs.get("gacha") or [""])[0]
            index = int((qs.get("index") or ["1"])[0] or 1)
            maxp = int((qs.get("max") or ["1"])[0] or 1)
            tstr = (qs.get("targets") or [""])[0]
            targets = [t.strip() for t in tstr.split(",") if t.strip()]
            if not (key and group and gacha):
                self._send(400, _json_bytes({"ok": False, "err": "ต้องระบุ id, group, gacha"}))
                return
            try:
                self._send(200, _json_bytes(
                    gacha_pull_account(key, group, gacha, index, targets, maxp)))
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
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    n = len(load_creds())
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"[!] คำเตือน: กำลัง bind {args.host} — creds.json เป็น cookie บัญชีจริง เปิดออกนอกเครื่องเสี่ยงมาก", flush=True)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[*] เปิดเว็บแล้ว: http://{args.host}:{args.port}   (บัญชีใน creds.json: {n})", flush=True)
    print(f"[*] creds: {CREDS_FILE}", flush=True)
    print("[*] Ctrl+C เพื่อปิด", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] ปิดเว็บแล้ว", flush=True)
        srv.shutdown()


if __name__ == "__main__":
    main()
