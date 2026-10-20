#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_account_workflow.py — ยูนิตเทสต์ account_workflow (ไม่แตะเน็ตจริง)
จำลองเซิร์ฟ rangers-api ด้วยการ monkeypatch requests.Session.request
รัน:  python -m unittest test_account_workflow -v
      (หรือ python test_account_workflow.py)

หมายเหตุ: response ที่ mock อิงรูปแบบจริงจาก logs/newid_*.jsonl (/login, /home)
          ไม่ได้แต่ง endpoint/ลายเซ็น/ผลสำเร็จขึ้นเอง — แค่เลียน schema ที่จับได้จริง
"""
import os
import sys
import json
import shutil
import tempfile
import unittest

# ต้องตั้งก่อน import lgr_api: ปิด rate-limit + proxy auto-detect ให้เทสต์เร็ว/นิ่ง
os.environ["LGR_MIN_GAP"] = "0"
os.environ["LGR_PROXY"] = ""

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import requests
import lgr_api
import account_workflow as wf


# ---- fake HTTP layer -------------------------------------------------------
class _Cookie:
    def __init__(self, name, value):
        self.name, self.value = name, value


class FakeResp:
    def __init__(self, status, payload=None, set_cookies=None):
        self.status_code = status
        self._payload = payload
        self.cookies = [_Cookie(n, v) for n, v in (set_cookies or {}).items()]

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    @property
    def text(self):
        return json.dumps(self._payload) if self._payload is not None else ""


def install_router(testcase, handler):
    """patch requests.Session.request -> handler(method, path, headers, kw) -> FakeResp
    path = ส่วนหลัง BASE (เช่น '/home'). เก็บ log การเรียกไว้ที่ testcase.calls"""
    testcase.calls = []

    def _fake(self, method, url, headers=None, **kw):
        path = url.replace(lgr_api.BASE, "")
        testcase.calls.append((method, path, dict(headers or {})))
        return handler(method, path, headers or {}, kw)

    orig = requests.Session.request
    requests.Session.request = _fake
    testcase.addCleanup(lambda: setattr(requests.Session, "request", orig))


LF_LONG = "L" * 260          # ยาวพอผ่าน MIN_COOKIE_LEN
GC_LONG = "G" * 260
HOME_OK = {"result": {"player": {"rsn": "a113b3b1", "mid": "T0FF001OSFXC",
                                 "userName": "tester", "userType": "GUEST",
                                 "level": 3, "ruby": {"total": 121}, "coin": {"total": 5000}}}}


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _tmp_creds(testcase, data):
    # โฟลเดอร์ชั่วคราวแยกต่อเทสต์: workflow (โหมดเขียน) รวม creds.part*.json ในโฟลเดอร์เดียวกับไฟล์ creds
    # -> ห้ามวางไว้ใน %TEMP% ตรง ๆ (จะไปแตะไฟล์อื่นในนั้น)
    d = tempfile.mkdtemp(prefix="lgr_creds_test_")
    testcase.addCleanup(shutil.rmtree, d, True)
    path = os.path.join(d, "creds.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def _no_sleep(testcase):
    orig_sleep = wf.time.sleep
    wf.time.sleep = lambda *_: None
    testcase.addCleanup(lambda: setattr(wf.time, "sleep", orig_sleep))


def _cookie_lf(headers):
    """ดึงค่า LF_AC จาก Cookie header ที่ส่งออกไป (ใช้เทียบในเทสต์เท่านั้น)"""
    for part in headers.get("Cookie", "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == "LF_AC":
            return v
    return None


# ---- tests -----------------------------------------------------------------
class ServerConfirmed(unittest.TestCase):
    def test_rsn_present_is_confirmed(self):
        info = wf._server_confirmed(HOME_OK)
        self.assertIsNotNone(info)
        self.assertEqual(info["rsn"], "a113b3b1")
        self.assertEqual(info["ruby"], 121)

    def test_http200_without_identity_is_not_confirmed(self):
        # 200 แต่ไม่มี rsn/mid -> ต้องไม่ถือว่าสำเร็จ (กันนับ "ส่งได้" = "สำเร็จ")
        self.assertIsNone(wf._server_confirmed({"result": {"player": {}}}))
        self.assertIsNone(wf._server_confirmed({"result": {}}))


class VerifyPaths(unittest.TestCase):
    def test_home_ok_marks_verified(self):
        install_router(self, lambda m, p, h, kw: FakeResp(200, HOME_OK,
                       {"LF_AC": LF_LONG + "NEW"}) if p == "/home" else FakeResp(404))
        creds = {"a113b3b1": {"udid": "u1", "LF_AC": LF_LONG, "guestCookie": GC_LONG}}
        path = _tmp_creds(self, creds)
        cfg = wf.Config(creds_file=path)
        s = wf.run_workflow(cfg)
        self.assertEqual(s["verified"], 1)
        r = s["results"][0]
        self.assertEqual(r["status"], wf.OK)
        self.assertEqual(r["rsn"], "a113b3b1")
        # LF_AC ที่เซิร์ฟหมุนใหม่ ต้องถูกเขียนกลับ creds.json
        saved = _read_json(path)
        self.assertEqual(saved["a113b3b1"]["LF_AC"], LF_LONG + "NEW")

    def test_401_then_login_then_home(self):
        state = {"logged_in": False}

        def handler(m, p, h, kw):
            if p == "/home":
                return FakeResp(200, HOME_OK) if state["logged_in"] else FakeResp(401, {"errorCode": 401})
            if p == "/login":
                state["logged_in"] = True
                return FakeResp(200, {"result": {"rsn": "a113b3b1", "mid": "T0FF001OSFXC"}})
            return FakeResp(200, {"result": True})

        install_router(self, handler)
        creds = {"a113b3b1": {"udid": "u1", "LF_AC": LF_LONG, "guestCookie": GC_LONG}}
        cfg = wf.Config(creds_file=_tmp_creds(self, creds))
        s = wf.run_workflow(cfg)
        self.assertEqual(s["verified"], 1)
        self.assertTrue(s["results"][0]["steps"]["login"])

    def test_401_no_guestcookie_needs_capture(self):
        install_router(self, lambda m, p, h, kw: FakeResp(401, {"errorCode": 401}))
        creds = {"dead1": {"udid": "u1", "LF_AC": LF_LONG, "guestCookie": None}}
        cfg = wf.Config(creds_file=_tmp_creds(self, creds))
        s = wf.run_workflow(cfg)
        self.assertEqual(s["needs_capture"], 1)
        self.assertEqual(s["results"][0]["status"], wf.NEEDS_CAPTURE)

    def test_missing_udid_needs_capture(self):
        install_router(self, lambda m, p, h, kw: FakeResp(200, HOME_OK))
        creds = {"x": {"LF_AC": LF_LONG}}         # ไม่มี udid
        cfg = wf.Config(creds_file=_tmp_creds(self, creds))
        s = wf.run_workflow(cfg)
        self.assertEqual(s["results"][0]["status"], wf.NEEDS_CAPTURE)

    def test_malformed_200_is_not_success(self):
        # เซิร์ฟตอบ 200 แต่ไม่ใช่ JSON dict (เช่นหน้า error/HTML) -> ต้องไม่นับว่าสำเร็จ
        orig_sleep = wf.time.sleep
        wf.time.sleep = lambda *_: None
        self.addCleanup(lambda: setattr(wf.time, "sleep", orig_sleep))
        install_router(self, lambda m, p, h, kw: FakeResp(200, "not-a-dict"))
        creds = {"a113b3b1": {"udid": "u1", "LF_AC": LF_LONG, "guestCookie": GC_LONG}}
        cfg = wf.Config(creds_file=_tmp_creds(self, creds), retry=1)
        s = wf.run_workflow(cfg)
        self.assertEqual(s["verified"], 0)
        self.assertEqual(s["results"][0]["status"], wf.ERROR)

    def test_timeout_is_retried_then_recovers(self):
        orig_sleep = wf.time.sleep
        wf.time.sleep = lambda *_: None          # อย่าหน่วงจริงตอนเทสต์ retry
        self.addCleanup(lambda: setattr(wf.time, "sleep", orig_sleep))
        state = {"n": 0}

        def handler(m, p, h, kw):
            if p == "/home":
                state["n"] += 1
                if state["n"] == 1:
                    raise requests.exceptions.Timeout("read timed out")   # ครั้งแรก timeout
                return FakeResp(200, HOME_OK)
            return FakeResp(200, {"result": True})

        install_router(self, handler)
        creds = {"a113b3b1": {"udid": "u1", "LF_AC": LF_LONG, "guestCookie": GC_LONG}}
        cfg = wf.Config(creds_file=_tmp_creds(self, creds), retry=2)
        s = wf.run_workflow(cfg)
        self.assertEqual(s["verified"], 1)       # retry แล้วผ่าน
        self.assertGreaterEqual(state["n"], 2)

    def test_dry_run_does_not_write(self):
        install_router(self, lambda m, p, h, kw: FakeResp(200, HOME_OK, {"LF_AC": LF_LONG + "NEW"})
                       if p == "/home" else FakeResp(200, {"result": True}))
        creds = {"a113b3b1": {"udid": "u1", "LF_AC": LF_LONG, "guestCookie": GC_LONG}}
        path = _tmp_creds(self, creds)
        wf.run_workflow(wf.Config(creds_file=path, dry_run=True))
        saved = _read_json(path)
        self.assertEqual(saved["a113b3b1"]["LF_AC"], LF_LONG)   # ไม่ถูกเขียนทับ


class VerifyOnly(unittest.TestCase):
    def test_verify_only_issues_no_post(self):
        install_router(self, lambda m, p, h, kw: FakeResp(200, HOME_OK)
                       if p == "/home" else FakeResp(200, {"result": True}))
        creds = {"a113b3b1": {"udid": "u1", "LF_AC": LF_LONG, "guestCookie": GC_LONG}}
        cfg = wf.Config(creds_file=_tmp_creds(self, creds), verify_only=True)
        s = wf.run_workflow(cfg)
        self.assertEqual(s["verified"], 1)
        # ต้องไม่มี POST ใด ๆ ออกไป (ไม่ push/register ไม่เก็บของ)
        methods = {m for m, _p, _h in self.calls}
        self.assertNotIn("POST", methods)
        self.assertTrue(s["results"][0]["steps"].get("verify_only"))


class CollectStep(unittest.TestCase):
    def test_collect_claims_gifts(self):
        gifts = {"n": 2}

        def handler(m, p, h, kw):
            if p == "/home":
                return FakeResp(200, HOME_OK)
            if p.startswith("/giftbox/list"):
                box = [{"receive": False}] * gifts["n"]
                return FakeResp(200, {"result": {"giftBox": {"gift": {"playerGifts": box}}}})
            if "receive/all" in p:
                gifts["n"] = 0
                return FakeResp(200, {"result": {}})
            if "mission" in p:
                return FakeResp(200, {"result": {}})
            return FakeResp(200, {"result": True})

        install_router(self, handler)
        creds = {"a113b3b1": {"udid": "u1", "LF_AC": LF_LONG, "guestCookie": GC_LONG}}
        cfg = wf.Config(creds_file=_tmp_creds(self, creds), collect=True)
        s = wf.run_workflow(cfg)
        self.assertEqual(s["results"][0]["steps"]["gifts_claimed"], 2)

    def _run_collect(self, handler):
        install_router(self, handler)
        creds = {"a113b3b1": {"udid": "u1", "LF_AC": LF_LONG, "guestCookie": GC_LONG}}
        cfg = wf.Config(creds_file=_tmp_creds(self, creds), collect=True)
        return wf.run_workflow(cfg)["results"][0]["steps"]["gifts_claimed"]

    def test_giftbox_list_failure_is_error_not_zero(self):
        def handler(m, p, h, kw):
            if p == "/home":
                return FakeResp(200, HOME_OK)
            if p.startswith("/giftbox/list"):
                return FakeResp(500, {"errorCode": 500})
            return FakeResp(200, {"result": {}})
        got = self._run_collect(handler)
        self.assertIsInstance(got, str)
        self.assertTrue(got.startswith("err:giftbox/list"))

    def test_receive_all_failure_is_error(self):
        def handler(m, p, h, kw):
            if p == "/home":
                return FakeResp(200, HOME_OK)
            if p.startswith("/giftbox/list"):
                return FakeResp(200, {"result": {"giftBox": {"gift": {"playerGifts": [{"receive": False}]}}}})
            if "receive/all" in p:
                return FakeResp(403, {"errorCode": 403})
            return FakeResp(200, {"result": {}})
        self.assertEqual(self._run_collect(handler), "err:receive/all HTTP 403")


class RetryRotation(unittest.TestCase):
    def test_retry_uses_rotated_lf_ac(self):
        # รอบแรก: /home ตอบ 503 แต่หมุน LF_AC ใหม่มา -> รอบ retry ต้องส่งค่าใหม่ ไม่ใช่ค่าตั้งต้น
        _no_sleep(self)
        rotated = LF_LONG + "R1"
        state = {"n": 0}

        def handler(m, p, h, kw):
            if p == "/home":
                state["n"] += 1
                if state["n"] == 1:
                    return FakeResp(503, {"errorCode": 503}, {"LF_AC": rotated})
                return FakeResp(200, HOME_OK)
            return FakeResp(200, {"result": True})

        install_router(self, handler)
        creds = {"a113b3b1": {"udid": "u1", "LF_AC": LF_LONG, "guestCookie": GC_LONG}}
        path = _tmp_creds(self, creds)
        s = wf.run_workflow(wf.Config(creds_file=path, retry=2, verify_only=True))
        self.assertEqual(s["verified"], 1)
        homes = [_cookie_lf(h) for m, p, h in self.calls if p == "/home"]
        self.assertEqual(homes, [LF_LONG, rotated])
        self.assertEqual(_read_json(path)["a113b3b1"]["LF_AC"], rotated)

    def test_401_after_rotation_logs_in_with_latest_lf_ac(self):
        # /home 401 (หมุน LF_AC มาด้วย) -> /login ต้องส่ง LF_AC ล่าสุด + guestCookie ; ล้มเหลว -> NEEDS_CAPTURE
        rotated = LF_LONG + "R2"

        def handler(m, p, h, kw):
            if p == "/home":
                return FakeResp(401, {"errorCode": 401}, {"LF_AC": rotated})
            if p == "/login":
                return FakeResp(401, {"errorCode": 401})
            return FakeResp(404)

        install_router(self, handler)
        creds = {"a113b3b1": {"udid": "u1", "LF_AC": LF_LONG, "guestCookie": GC_LONG, "rsn": "a113b3b1"}}
        path = _tmp_creds(self, creds)
        s = wf.run_workflow(wf.Config(creds_file=path, retry=2))
        r = s["results"][0]
        self.assertEqual(r["status"], wf.NEEDS_CAPTURE)
        login = [h for m, p, h in self.calls if p == "/login"]
        self.assertEqual(len(login), 1)                       # 401 ไม่ retry
        self.assertEqual(_cookie_lf(login[0]), rotated)
        self.assertIn("guestCookie=" + GC_LONG, login[0]["Cookie"])
        saved = _read_json(path)["a113b3b1"]
        self.assertEqual(saved["LF_AC"], rotated)
        self.assertEqual(saved["guestCookie"], GC_LONG)        # guestCookie เดิมคงอยู่
        self.assertEqual(saved["udid"], "u1")


class PersistMerge(unittest.TestCase):
    def test_persist_merges_into_latest_file(self):
        # ระหว่างรัน มีโปรเซสอื่น (capture) เพิ่มบัญชีใหม่ลงไฟล์ -> ต้องไม่ถูก snapshot เก่าเขียนทับ
        creds = {"a113b3b1": {"udid": "u1", "LF_AC": LF_LONG, "guestCookie": GC_LONG},
                 "other": {"udid": "u2", "LF_AC": "O" * 260, "guestCookie": None}}
        path = _tmp_creds(self, creds)

        def handler(m, p, h, kw):
            if p == "/home":
                cur = _read_json(path)
                cur["newacct"] = {"udid": "u9", "LF_AC": "N" * 260, "guestCookie": None}
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cur, f)
                return FakeResp(200, HOME_OK, {"LF_AC": LF_LONG + "NEW"})
            return FakeResp(200, {"result": True})

        install_router(self, handler)
        wf.run_workflow(wf.Config(creds_file=path, verify_only=True), ids=["a113b3b1"])
        saved = _read_json(path)
        self.assertIn("newacct", saved)
        self.assertEqual(saved["other"], creds["other"])
        self.assertEqual(saved["a113b3b1"]["LF_AC"], LF_LONG + "NEW")
        self.assertEqual(saved["a113b3b1"]["guestCookie"], GC_LONG)

    def test_lock_timeout_reports_error_and_does_not_write(self):
        install_router(self, lambda m, p, h, kw: FakeResp(200, HOME_OK, {"LF_AC": LF_LONG + "NEW"}))
        creds = {"a113b3b1": {"udid": "u1", "LF_AC": LF_LONG, "guestCookie": GC_LONG}}
        path = _tmp_creds(self, creds)
        open(path + ".lock", "w").close()                   # โปรเซสอื่นถือ lock อยู่
        orig = lgr_api.CREDS_LOCK_TIMEOUT
        lgr_api.CREDS_LOCK_TIMEOUT = 0.2
        self.addCleanup(lambda: setattr(lgr_api, "CREDS_LOCK_TIMEOUT", orig))
        s = wf.run_workflow(wf.Config(creds_file=path, verify_only=True))
        self.assertFalse(s["ok"])
        self.assertIn("CredsLockError", s["persist_error"])
        self.assertEqual(_read_json(path)["a113b3b1"]["LF_AC"], LF_LONG)
        self.assertFalse(os.path.exists(path + ".tmp"))


class DryRunNoFiles(unittest.TestCase):
    def test_dry_run_touches_no_files(self):
        # dry-run: ไม่สร้าง/แก้/ลบ/ย้ายไฟล์ใด ๆ ในโฟลเดอร์ (รวมถึง part files และ .bak/.lock)
        install_router(self, lambda m, p, h, kw: FakeResp(200, HOME_OK, {"LF_AC": LF_LONG + "NEW"})
                       if p == "/home" else FakeResp(200, {"result": True}))
        creds = {"a113b3b1": {"udid": "u1", "LF_AC": LF_LONG, "guestCookie": GC_LONG}}
        path = _tmp_creds(self, creds)
        d = os.path.dirname(path)
        with open(os.path.join(d, "creds.part8443.json"), "w", encoding="utf-8") as f:
            json.dump({"p1": {"udid": "u3", "LF_AC": "P" * 260}}, f)

        def snapshot():
            out = {}
            for n in sorted(os.listdir(d)):
                st = os.stat(os.path.join(d, n))
                with open(os.path.join(d, n), "rb") as f:
                    out[n] = (st.st_mtime_ns, f.read())
            return out

        before = snapshot()
        wf.run_workflow(wf.Config(creds_file=path, dry_run=True, collect=True))
        self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
