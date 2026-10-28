# C:\Users\Administrator\Downloads\LGR\api\lgr_mitm.py
# python 3.10+, pip install mitmproxy
# ใช้: mitmdump -s api/lgr_mitm.py --listen-port 8888
# emulator: adb shell settings put global http_proxy 10.0.2.2:8888
#
# BLIND MODE: เขียนทับทุก response จาก lineranger/lgrgs/line-apps.com host
# ให้ client เห็น "success" เสมอ ไม่ว่าเซิร์ฟจะปฏิเสธกี่ครั้ง

from mitmproxy import http
import json, time, re

LGR_HOSTS = (
    "lineranger.line-apps.com",
    "lgrgs.line-apps.com",
    "lgc.line-apps.com",
    "line-apps.com",
)

# status code ทุกตัวที่ไม่ใช่ 200 -> rewrite เป็น 200 ว่าง
BLOCK_CODES = {400, 401, 403, 404, 429, 500, 502, 503, 1052, 1055, 1060, 2001}

# key ใน response body ที่ตีความว่า block/ban -> ล้างเป็น false/0
KILL_BOOL_KEYS = ("blocked", "ipBlocked", "deviceBlocked", "banned", "restricted",
                  "needCheck", "needVerify", "forceLogout", "kicked",
                  "authFailed", "loginFailed", "sessionInvalid")
KILL_INT_KEYS = ("loginCount", "loginLimit", "dailyLoginCount",
                 "banRemaining", "cooldownSec", "retryAfter")

# error message patterns ที่ถือว่าโดน block
BLOCK_MSGS = re.compile(
    r"(ip|device|login|session|authentication|network)"
    r".{0,30}"
    r"(limit|block|exceed|ban|fail|invalid|unstable|refused)",
    re.I
)


def _is_lgr(flow: http.HTTPFlow) -> bool:
    return any(h in flow.request.pretty_host for h in LGR_HOSTS)


def request(flow: http.HTTPFlow):
    if not _is_lgr(flow):
        return
    # ซิงก์ timestamp กับเวลาปัจจุบันเสมอ - กัน skew
    flow.request.headers["X-LINEGAME-TIMESTAMP"] = str(int(time.time() * 1000))
    # strip header fingerprint ที่เซิร์ฟใช้ track
    for h in ("X-Device-Boot-Id", "X-Install-Id", "X-Session-Nonce", "X-Fingerprint"):
        flow.request.headers.pop(h, None)


def _fake_success(path: str) -> dict:
    """response ว่าง ๆ ที่แอป parse ได้ไม่ crash - รูปร่างตาม path"""
    base = {"result": True, "error": None, "version": int(time.time())}
    if "/home" in path:
        base["result"] = {
            "player": {"rank": 1, "exp": 0, "ruby": 0},
            "giftBoxCount": 0, "mailCount": 0,
            "blocked": False, "ipBlocked": False, "deviceBlocked": False,
            "loginCount": 0, "loginLimit": 0,
        }
    elif "/giftbox" in path:
        base["result"] = {"giftList": [], "giftBoxCount": 0}
    elif "/login" in path:
        base["result"] = {
            "player": {"id": 0, "rank": 1},
            "sessionId": "0" * 32, "lfAc": "0" * 280,
        }
    elif "/player/item" in path:
        base["result"] = {"items": [], "tickets": {"premium": 0, "classic": 0}}
    return base


def response(flow: http.HTTPFlow):
    if not _is_lgr(flow):
        return
    path = flow.request.path

    # status code บล็อก -> rewrite เป็น 200 + fake body
    if flow.response.status_code in BLOCK_CODES:
        flow.response.status_code = 200
        flow.response.content = json.dumps(_fake_success(path)).encode()
        flow.response.headers["Content-Type"] = "application/json"
        return

    # body carry error
    try:
        body = flow.response.get_text()
        if not body:
            return
        d = json.loads(body)
    except Exception:
        return

    if not isinstance(d, dict):
        return

    # error object with any blocking signal
    err = d.get("error")
    if isinstance(err, dict):
        code = err.get("code") or err.get("errorCode")
        msg = str(err.get("message", ""))
        if (code in BLOCK_CODES) or (msg and BLOCK_MSGS.search(msg)):
            d["error"] = None
            d["result"] = d.get("result") or True
            if not isinstance(d.get("result"), dict):
                d["result"] = _fake_success(path)["result"]

    # result.flag ที่ขึ้นหน้า "เครื่องนี้เข้าเกมไม่ได้"
    r = d.get("result")
    if isinstance(r, dict):
        for k in KILL_BOOL_KEYS:
            if r.get(k):
                r[k] = False
        for k in KILL_INT_KEYS:
            if k in r and r[k]:
                r[k] = 0
        # กันหน้า "update required" ที่หลายเกมใช้ไล่ user ที่โดนแบน
        for k in ("needUpdate", "forceUpdate", "maintenance"):
            if r.get(k):
                r[k] = False

    try:
        flow.response.text = json.dumps(d, ensure_ascii=False)
    except Exception:
        pass
