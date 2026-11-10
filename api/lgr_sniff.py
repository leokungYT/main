# api/lgr_sniff.py
# mitmproxy addon — ดักเฉพาะ host ของ LGR
# เขียน creds + body ทุก request/response ลง ndjson + รวม creds.json อัตโนมัติ
#
# usage:
#   mitmweb --listen-port 8888 --web-port 8081 -s api\lgr_sniff.py
#
# แล้วชี้ proxy ของ MuMu ไปที่ <PC IP>:8888

import json, os, time
from mitmproxy import http

HERE = os.path.dirname(os.path.abspath(__file__))
DUMP  = os.path.join(HERE, "dump.ndjson")
CREDS = os.path.join(HERE, "creds.json")

HOSTS = ("axelth.com", "linega.me", "lrgame", "ranger", "linecorp.com")


def _is_lgr(flow):
    h = (flow.request.pretty_host or "").lower()
    return any(s in h for s in HOSTS)


def _save_creds(rsn_or_udid, payload):
    try:
        bank = json.load(open(CREDS, "r", encoding="utf-8"))
    except Exception:
        bank = {}
    cur = bank.get(rsn_or_udid, {})
    cur.update({k: v for k, v in payload.items() if v})
    cur["_ts"] = int(time.time())
    bank[rsn_or_udid] = cur
    json.dump(bank, open(CREDS, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def _pick_cookies(headers):
    udid = lfac = ""
    for part in (headers.get("cookie", "") or "").split(";"):
        p = part.strip()
        if p.lower().startswith("udid="): udid = p.split("=", 1)[1]
        if p.startswith("LF_AC="):        lfac = p.split("=", 1)[1]
    return udid, lfac


def request(flow: http.HTTPFlow):
    if not _is_lgr(flow): return
    udid, lfac = _pick_cookies(flow.request.headers)
    body = flow.request.get_text(strict=False) or ""
    guest = ""
    if "guestCookie" in body:
        try:
            j = json.loads(body)
            guest = j.get("guestCookie", "") or ""
        except Exception:
            pass
    if udid or lfac or guest:
        _save_creds(udid or "unknown", {
            "udid": udid, "LF_AC": lfac, "guestCookie": guest
        })


def response(flow: http.HTTPFlow):
    if not _is_lgr(flow): return
    rec = {
        "ts":     int(time.time()),
        "host":   flow.request.pretty_host,
        "path":   flow.request.path,
        "method": flow.request.method,
        "req_h":  dict(flow.request.headers),
        "req_b":  flow.request.get_text(strict=False)[:4096],
        "status": flow.response.status_code,
        "res_h":  dict(flow.response.headers),
        "res_b":  flow.response.get_text(strict=False)[:8192],
    }
    with open(DUMP, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    # ดัก LF_AC จาก set-cookie ของ server
    sc = flow.response.headers.get("set-cookie", "") or ""
    if "LF_AC=" in sc:
        lfac = sc.split("LF_AC=", 1)[1].split(";", 1)[0]
        udid, _ = _pick_cookies(flow.request.headers)
        if udid:
            _save_creds(udid, {"LF_AC": lfac})
