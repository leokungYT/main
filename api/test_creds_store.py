#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_creds_store.py — ยูนิตเทสต์การอ่าน/เขียน creds ใน lgr_api (lock, atomic, merge รายบัญชี, part files)
ทุกเทสต์ใช้โฟลเดอร์ชั่วคราวแยก ไม่แตะ creds.json จริง และไม่ยิงเน็ต
รัน:  python -m unittest test_creds_store -v
"""
import os
import sys
import json
import shutil
import tempfile
import unittest

os.environ["LGR_MIN_GAP"] = "0"
os.environ["LGR_PROXY"] = ""

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import requests
import lgr_api


def _write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class _TmpDir(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="lgr_store_test_")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.path = os.path.join(self.d, "creds.json")
        orig = lgr_api.CREDS_LOCK_TIMEOUT
        lgr_api.CREDS_LOCK_TIMEOUT = 0.2
        self.addCleanup(lambda: setattr(lgr_api, "CREDS_LOCK_TIMEOUT", orig))

    def listing(self):
        return sorted(os.listdir(self.d))


class LoadCreds(_TmpDir):
    def test_missing_file_returns_empty_and_creates_nothing(self):
        self.assertEqual(lgr_api.load_creds(self.path), {})
        self.assertEqual(self.listing(), [])

    def test_default_load_leaves_part_files_alone(self):
        _write(self.path, {"a": {"udid": "u1"}})
        _write(os.path.join(self.d, "creds.part1.json"), {"b": {"udid": "u2"}})
        self.assertEqual(lgr_api.load_creds(self.path), {"a": {"udid": "u1"}})
        self.assertEqual(self.listing(), ["creds.json", "creds.part1.json"])

    def test_corrupt_file_returns_empty_without_writing(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{broken")
        self.assertEqual(lgr_api.load_creds(self.path), {})
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{broken")


class MergeParts(_TmpDir):
    def test_no_parts_touches_nothing(self):
        merged, n = lgr_api.merge_part_creds(creds_path=self.path)
        self.assertEqual((merged, n), ({}, 0))
        self.assertEqual(self.listing(), [])

    def test_merge_keeps_existing_fields_and_removes_parts(self):
        _write(self.path, {"a": {"udid": "u1", "guestCookie": "G"}})
        _write(os.path.join(self.d, "creds.part1.json"),
               {"a": {"LF_AC": "L2", "guestCookie": None}, "b": {"udid": "u2"}})
        merged, n = lgr_api.merge_part_creds(creds_path=self.path)
        self.assertEqual(n, 1)
        saved = _read(self.path)
        self.assertEqual(saved["a"], {"udid": "u1", "guestCookie": "G", "LF_AC": "L2"})
        self.assertEqual(saved["b"], {"udid": "u2"})
        self.assertNotIn("creds.part1.json", self.listing())

    def test_lock_timeout_keeps_part_files(self):
        _write(self.path, {"a": {"udid": "u1"}})
        part = os.path.join(self.d, "creds.part1.json")
        _write(part, {"b": {"udid": "u2"}})
        open(self.path + ".lock", "w").close()
        with self.assertRaises(lgr_api.CredsLockError):
            lgr_api.merge_part_creds(creds_path=self.path)
        self.assertTrue(os.path.exists(part))
        self.assertEqual(_read(self.path), {"a": {"udid": "u1"}})


class SaveAndUpdate(_TmpDir):
    def test_save_is_atomic_with_bak(self):
        _write(self.path, {"a": {"udid": "u1"}})
        self.assertTrue(lgr_api.save_creds({"a": {"udid": "u1", "LF_AC": "x"}}, self.path))
        self.assertEqual(_read(self.path + ".bak"), {"a": {"udid": "u1"}})
        self.assertEqual(_read(self.path)["a"]["LF_AC"], "x")
        self.assertNotIn("creds.json.tmp", self.listing())
        self.assertNotIn("creds.json.lock", self.listing())   # ปล่อย lock แล้ว

    def test_save_refuses_without_lock(self):
        _write(self.path, {"a": {"udid": "u1"}})
        open(self.path + ".lock", "w").close()
        self.assertFalse(lgr_api.save_creds({"a": {"udid": "zzz"}}, self.path))
        self.assertEqual(_read(self.path), {"a": {"udid": "u1"}})

    def test_save_refuses_empty_over_data(self):
        _write(self.path, {"a": {"udid": "u1"}})
        self.assertFalse(lgr_api.save_creds({}, self.path))
        self.assertEqual(_read(self.path), {"a": {"udid": "u1"}})

    def test_update_merges_per_account_on_latest_file(self):
        _write(self.path, {"a": {"udid": "u1", "LF_AC": "old", "guestCookie": "G", "rsn": "a"},
                           "b": {"udid": "u2", "LF_AC": "bb"}})
        n = lgr_api.update_creds({"a": {"LF_AC": "new", "guestCookie": None, "udid": None},
                                  "ghost": {"LF_AC": "x"}}, self.path)
        self.assertEqual(n, 1)
        saved = _read(self.path)
        self.assertEqual(saved["a"], {"udid": "u1", "LF_AC": "new", "guestCookie": "G", "rsn": "a"})
        self.assertEqual(saved["b"], {"udid": "u2", "LF_AC": "bb"})
        self.assertNotIn("ghost", saved)                       # ไม่สร้างบัญชีใหม่

    def test_update_no_change_does_not_write(self):
        _write(self.path, {"a": {"LF_AC": "same"}})
        self.assertEqual(lgr_api.update_creds({"a": {"LF_AC": "same"}}, self.path), 0)
        self.assertEqual(self.listing(), ["creds.json"])       # ไม่มี .bak = ไม่ได้เขียน

    def test_update_lock_timeout_raises_and_does_not_write(self):
        _write(self.path, {"a": {"LF_AC": "old"}})
        open(self.path + ".lock", "w").close()
        with self.assertRaises(lgr_api.CredsLockError):
            lgr_api.update_creds({"a": {"LF_AC": "new"}}, self.path)
        self.assertEqual(_read(self.path), {"a": {"LF_AC": "old"}})

    def test_update_corrupt_file_raises_and_keeps_it(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{broken")
        with self.assertRaises(ValueError):
            lgr_api.update_creds({"a": {"LF_AC": "new"}}, self.path)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{broken")
        self.assertFalse(os.path.exists(self.path + ".lock"))  # ปล่อย lock แม้ error


class CaptureAddonLock(_TmpDir):
    """capture_credential ต้องใช้ lock เดียวกัน และไม่เขียนเมื่อได้ lock ไม่ทัน"""
    def setUp(self):
        super().setUp()
        try:
            import capture_credential as cc
        except ImportError as e:                               # ไม่มี mitmproxy ในเครื่องนี้
            self.skipTest(f"import capture_credential ไม่ได้: {e}")
        self.cc = cc
        orig = cc.CREDS
        cc.CREDS = self.path
        self.addCleanup(lambda: setattr(cc, "CREDS", orig))

    def test_store_preserves_guest_cookie_and_other_accounts(self):
        _write(self.path, {"a": {"udid": "u1", "LF_AC": "old", "guestCookie": "G" * 260},
                           "b": {"udid": "u2", "LF_AC": "bb"}})
        self.cc._store("a", "u1", "L" * 260, None, None, None, None, None)
        saved = _read(self.path)
        self.assertEqual(saved["a"]["LF_AC"], "L" * 260)
        self.assertEqual(saved["a"]["guestCookie"], "G" * 260)
        self.assertEqual(saved["b"], {"udid": "u2", "LF_AC": "bb"})

    def test_store_lock_timeout_raises_and_does_not_write(self):
        _write(self.path, {"a": {"udid": "u1", "LF_AC": "old"}})
        open(self.path + ".lock", "w").close()
        with self.assertRaises(lgr_api.CredsLockError):
            self.cc._store("a", "u1", "L" * 260, None, None, None, None, None)
        self.assertEqual(_read(self.path)["a"]["LF_AC"], "old")


# ---- Core API error paths (HTTP จำลอง) ---------------------------------------
class _Resp:
    def __init__(self, status, payload):
        self.status_code, self._p, self.cookies = status, payload, []

    def json(self):
        return self._p

    @property
    def text(self):
        return json.dumps(self._p)


class CallErrors(unittest.TestCase):
    def _patch(self, fn):
        orig = requests.Session.request
        requests.Session.request = fn
        self.addCleanup(lambda: setattr(requests.Session, "request", orig))
        orig_sleep = lgr_api.time.sleep
        lgr_api.time.sleep = lambda *_: None
        self.addCleanup(lambda: setattr(lgr_api.time, "sleep", orig_sleep))

    def test_caller_headers_not_mutated(self):
        self._patch(lambda s, m, u, headers=None, **kw: _Resp(200, {"result": {}}))
        h = {"X-Test": "1"}
        lgr_api.LGRClient("u", "l").call("GET", "/home", headers=h)
        self.assertEqual(h, {"X-Test": "1"})

    def test_connection_error_retried_then_raised(self):
        n = {"c": 0}

        def boom(s, m, u, headers=None, **kw):
            n["c"] += 1
            raise requests.exceptions.ConnectionError("unreachable")
        self._patch(boom)
        with self.assertRaises(requests.exceptions.ConnectionError):
            lgr_api.LGRClient("u", "l").home()
        self.assertEqual(n["c"], 3)

    def test_read_timeout_not_retried(self):
        n = {"c": 0}

        def slow(s, m, u, headers=None, **kw):
            n["c"] += 1
            raise requests.exceptions.ReadTimeout("read timed out")
        self._patch(slow)
        with self.assertRaises(requests.exceptions.Timeout):
            lgr_api.LGRClient("u", "l").receive_all_gifts()
        self.assertEqual(n["c"], 1)                            # POST อาจถึงเซิร์ฟแล้ว -> ไม่ยิงซ้ำ

    def test_unclaimed_gifts_failure_is_none_not_empty(self):
        self._patch(lambda s, m, u, headers=None, **kw: _Resp(500, {"errorCode": 500}))
        st, gifts = lgr_api.LGRClient("u", "l").unclaimed_gifts()
        self.assertEqual(st, 500)
        self.assertIsNone(gifts)

    def test_collect_account_reports_giftbox_failure(self):
        def route(s, m, u, headers=None, **kw):
            if u.endswith("/home"):
                return _Resp(200, {"result": {"player": {"rsn": "a"}}})
            return _Resp(500, {"errorCode": 500})
        self._patch(route)
        r = lgr_api.collect_account("u", "l")
        self.assertFalse(r["ok"])
        self.assertEqual(r["step"], "giftbox/list")


if __name__ == "__main__":
    unittest.main(verbosity=2)
