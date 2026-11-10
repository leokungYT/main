#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# api/lgr_requests.py
# ยิง LGR API ตรงด้วย requests อย่างเดียว — ไม่มี wrapper, ไม่มี dependency พิเศษ
# host จาก Charles: lrg.axelth.com
#
# usage (CLI):
#   python api\lgr_requests.py --udid <udid> --guest <guestCookie>
#   python api\lgr_requests.py --udid <u> --guest <g> --gift --dump
#
# usage (import):
#   from lgr_requests import LGR
#   lgr = LGR(udid="...", guest_cookie="...")
#   lgr.login()
#   home = lgr.home()
#   gifts = lgr.collect_gifts()

import argparse, json, sys, time
import requests

# ═══════════════════ แก้ค่าตรงนี้ให้ตรงกับ Charles ═══════════════════
BASE        = "https://lrg.axelth.com"
APP_VERSION = "15.3.0"
PLATFORM    = "android"
LANG        = "th"
NATION      = "TH"
USER_AGENT  = "Dalvik/2.1.0 (Linux; U; Android 13; MuMu Build/TQ3A.230805.001)"
# ═══════════════════════════════════════════════════════════════════════

ENDPOINTS = {
    "login":    "/login",
    "home":     "/home",
    "gift_all": "/gift/collectAll",
    "gift_one": "/gift/collect",
}


class LGR:
    def __init__(self, udid, guest_cookie=None, lf_ac=None,
                 nation=NATION, timeout=20, dump=False):
        self.udid         = udid
        self.guest_cookie = guest_cookie
        self.lf_ac        = lf_ac
        self.nation       = nation
        self.timeout      = timeout
        self.dump         = dump

        self.s = requests.Session()
        self.s.headers.update({
            "Accept":          "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Content-Type":    "application/json; charset=utf-8",
            "User-Agent":      USER_AGENT,
            "X-Lf-App":        "LGRGS",
            "X-Lf-Ver":        APP_VERSION,
            "X-Lf-Lang":       LANG,
            "X-Lf-Nation":     nation,
        })
        self.s.cookies.set("udid", udid, domain=self._host())
        if lf_ac:
            self.s.cookies.set("LF_AC", lf_ac, domain=self._host())

    def _host(self):
        return BASE.replace("https://", "").replace("http://", "").split("/")[0]

    def _req(self, method, path, **kw):
        url = BASE + path
        r = self.s.request(method, url, timeout=self.timeout, **kw)
        if self.dump:
            print(f"---- {method} {path} ----")
            if kw.get("data"): print("req:", kw["data"][:2048])
            print("status:", r.status_code)
            print("set-cookie:", r.headers.get("set-cookie"))
            print("body:", r.text[:2048])
            print()
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text

    def _post(self, path, body):
        return self._req("POST", path, data=json.dumps(body))

    def _get(self, path, params=None):
        return self._req("GET", path, params=params)

    def login(self):
        body = {
            "userType":    "GUEST",
            "guestCookie": self.guest_cookie or "",
            "udid":        self.udid,
            "nation":      self.nation,
            "appVersion":  APP_VERSION,
            "platform":    PLATFORM,
        }
        st, r = self._post(ENDPOINTS["login"], body)
        if st == 200 and isinstance(r, dict):
            lf = (self.s.cookies.get("LF_AC")
                  or (r.get("result") or {}).get("sessionKey")
                  or (r.get("result") or {}).get("LF_AC"))
            if lf:
                self.lf_ac = lf
                self.s.cookies.set("LF_AC", lf, domain=self._host())
        return st, r

    def home(self):
        st, r = self._get(ENDPOINTS["home"])
        if st == 401 and self.guest_cookie:
            self.login()
            st, r = self._get(ENDPOINTS["home"])
        return st, r

    def collect_gifts(self):
        return self._post(ENDPOINTS["gift_all"], {})

    def collect_gift(self, gift_id):
        return self._post(ENDPOINTS["gift_one"], {"giftId": gift_id})

    @staticmethod
    def summary(home_resp):
        if not isinstance(home_resp, dict): return {}
        res = home_resp.get("result") or {}
        p   = res.get("player") or {}
        return {
            "rsn":   p.get("rsn")   or res.get("rsn"),
            "name":  p.get("userName"),
            "level": p.get("level") or res.get("level"),
            "ruby":  p.get("ruby")  or res.get("ruby"),
            "coin":  p.get("coin")  or res.get("coin"),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--udid",   required=True)
    ap.add_argument("--guest",  required=True, help="guestCookie plain text (ดูจาก Charles)")
    ap.add_argument("--nation", default="TH")
    ap.add_argument("--gift",   action="store_true")
    ap.add_argument("--dump",   action="store_true")
    args = ap.parse_args()

    lgr = LGR(udid=args.udid, guest_cookie=args.guest,
              nation=args.nation, dump=args.dump)

    st, r = lgr.login()
    if st != 200:
        print(f"LOGIN FAIL  status={st}  body={r}")
        sys.exit(1)
    print(f"LOGIN OK  LF_AC={lgr.lf_ac[:16] if lgr.lf_ac else '(none)'}...")

    st, h = lgr.home()
    if st != 200:
        print(f"HOME FAIL  status={st}  body={h}")
        sys.exit(1)

    s = LGR.summary(h)
    print(f"HOME OK  rsn={s['rsn']}  lv={s['level']}  name={s['name']!r}  ruby={s['ruby']}  coin={s['coin']}")

    if args.gift:
        gs, gr = lgr.collect_gifts()
        got = len((gr.get("result") or {}).get("received", [])) if isinstance(gr, dict) else 0
        print(f"GIFT  status={gs}  received={got}")


if __name__ == "__main__":
    main()
