#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_creds_consumers.py — เทสต์ว่าสคริปต์ที่อ่าน/เขียน creds ใช้ตัวกลางของ lgr_api ถูกต้อง
(collect_all / seven_days / check_team / web_app / gacha_dump / capture_auto / auto_create_guest)
ทุกเทสต์ใช้โฟลเดอร์ชั่วคราวแยก ไม่แตะ creds.json จริง ; requests ถูกบล็อก (ยิงเน็ตจริง = เทสต์ล้ม)
รัน:  python -m unittest test_creds_consumers -v
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

LF = "L" * 260
GC = "G" * 260


def _write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class _Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="lgr_consumer_test_")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.path = os.path.join(self.d, "creds.json")
        orig = lgr_api.CREDS_LOCK_TIMEOUT
        lgr_api.CREDS_LOCK_TIMEOUT = 0.2
        self.addCleanup(lambda: setattr(lgr_api, "CREDS_LOCK_TIMEOUT", orig))

        def _no_net(*a, **kw):
            raise AssertionError("ห้ามยิงเน็ตจริงในเทสต์")
        orig_req = requests.Session.request
        requests.Session.request = _no_net
        self.addCleanup(lambda: setattr(requests.Session, "request", orig_req))

    def patch(self, obj, name, value):
        orig = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(lambda: setattr(obj, name, orig))

    def lock(self, path=None):
        open((path or self.path) + ".lock", "w").close()

    def snapshot(self):
        out = {}
        for n in sorted(os.listdir(self.d)):
            p = os.path.join(self.d, n)
            with open(p, "rb") as f:
                out[n] = (os.stat(p).st_mtime_ns, f.read())
        return out


# ---------------------------------------------------------------- lgr_api helpers ที่เพิ่มใน Part 3
class CentralHelpers(_Base):
    def test_update_create_adds_entry_without_touching_others(self):
        _write(self.path, {"a": {"udid": "u1", "guestCookie": GC}})
        n = lgr_api.update_creds({"b": {"udid": "u2", "LF_AC": LF, "guestCookie": None}}, self.path, create=True)
        self.assertEqual(n, 2)
        saved = _read(self.path)
        self.assertEqual(saved["a"], {"udid": "u1", "guestCookie": GC})
        self.assertEqual(saved["b"], {"udid": "u2", "LF_AC": LF})

    def test_try_update_reports_error(self):
        _write(self.path, {"a": {"LF_AC": "old"}})
        self.lock()
        n, err = lgr_api.try_update_creds({"a": {"LF_AC": "new"}}, self.path)
        self.assertEqual(n, 0)
        self.assertIn("CredsLockError", err)
        self.assertEqual(_read(self.path), {"a": {"LF_AC": "old"}})

    def test_changed_fields_ignores_none_and_unchanged(self):
        self.assertEqual(lgr_api.changed_fields({"a": 1, "b": 2, "g": GC}, {"a": 1, "b": 3, "g": None, "c": 4}),
                         {"b": 3, "c": 4})

    def test_merge_selected_part_only(self):
        _write(self.path, {"a": {"udid": "u1"}})
        p1, p2 = (os.path.join(self.d, f"creds.part{i}.json") for i in (1, 2))
        _write(p1, {"b": {"udid": "u2"}})
        _write(p2, {"c": {"udid": "u3"}})
        merged, n = lgr_api.merge_part_creds(creds_path=self.path, part_files=[p1])
        self.assertEqual(n, 1)
        self.assertEqual(sorted(_read(self.path)), ["a", "b"])
        self.assertFalse(os.path.exists(p1))
        self.assertTrue(os.path.exists(p2))                    # ไม่ได้สั่ง -> ไม่แตะ

    def test_merge_waits_for_part_lock(self):
        # addon กำลังเขียน part อยู่ (ถือ lock ของ part) -> merge ต้องไม่อ่าน/ลบ part นั้น
        _write(self.path, {"a": {"udid": "u1"}})
        part = os.path.join(self.d, "creds.part1.json")
        _write(part, {"b": {"udid": "u2"}})
        self.lock(part)
        with self.assertRaises(lgr_api.CredsLockError):
            lgr_api.merge_part_creds(creds_path=self.path)
        self.assertTrue(os.path.exists(part))
        self.assertEqual(_read(self.path), {"a": {"udid": "u1"}})
        self.assertFalse(os.path.exists(self.path + ".lock"))  # ปล่อย lock ที่ถือไปแล้วคืน

    def test_merge_write_failure_keeps_parts(self):
        _write(self.path, {"a": {"udid": "u1"}})
        part = os.path.join(self.d, "creds.part1.json")
        _write(part, {"b": {"udid": "u2"}})

        def boom(data, path):
            raise OSError("disk full")
        self.patch(lgr_api, "_write_creds_atomic", boom)
        with self.assertRaises(OSError):
            lgr_api.merge_part_creds(creds_path=self.path)
        self.assertTrue(os.path.exists(part))                  # ลบ part เฉพาะเมื่อเขียนสำเร็จ
        self.assertEqual(_read(self.path), {"a": {"udid": "u1"}})


# ---------------------------------------------------------------- collect_all / seven_days
class CollectAll(_Base):
    def setUp(self):
        super().setUp()
        import collect_all
        self.m = collect_all
        self.patch(collect_all, "CREDS", self.path)
        self.patch(sys, "argv", ["collect_all.py"])

    def test_per_account_save_keeps_other_accounts_and_guest_cookie(self):
        _write(self.path, {"a": {"udid": "u1", "LF_AC": "old", "guestCookie": GC, "file": "a.xml"},
                           "b": {"udid": "u2", "LF_AC": "bb"}})

        def fake_one(key, cred):
            if key == "a":
                # ระหว่างรัน มีโปรเซสอื่นเพิ่มบัญชีใหม่ลงไฟล์
                cur = _read(self.path)
                cur["new"] = {"udid": "u9", "LF_AC": "nn"}
                _write(self.path, cur)
                return key, {"ok": True, "ruby": 5, "ticket": 1, "coin": 9, "claimed": 0,
                             "lf_ac_next": LF + "A", "gc_next": None}
            return key, {"ok": False, "err": "x", "lf_ac_next": "SHOULD-NOT-SAVE"}
        self.patch(self.m, "_one", fake_one)
        self.m.main()
        saved = _read(self.path)
        self.assertIn("new", saved)
        self.assertEqual(saved["a"]["LF_AC"], LF + "A")
        self.assertEqual(saved["a"]["guestCookie"], GC)
        self.assertEqual(saved["a"]["file"], "a.xml")
        self.assertEqual((saved["a"]["ruby"], saved["a"]["ticket"], saved["a"]["coin"]), (5, 1, 9))
        self.assertEqual(saved["b"], {"udid": "u2", "LF_AC": "bb"})

    def test_rotated_guest_cookie_saved(self):
        # เดิม: res.pop("gc_next") แล้วอ่าน res["gc_next"] -> KeyError ทุกครั้งที่เซิร์ฟหมุน guestCookie
        _write(self.path, {"a": {"udid": "u1", "LF_AC": "old", "guestCookie": GC}})
        self.patch(self.m, "_one", lambda k, c: (k, {"ok": True, "lf_ac_next": LF, "gc_next": GC + "2"}))
        self.m.main()
        self.assertEqual(_read(self.path)["a"]["guestCookie"], GC + "2")

    def test_save_failure_is_reported(self):
        _write(self.path, {"a": {"udid": "u1", "LF_AC": "old"}})
        self.patch(self.m, "_one", lambda k, c: (k, {"ok": True, "lf_ac_next": LF}))
        self.lock()
        printed = []
        import builtins
        self.patch(builtins, "print", lambda *a, **k: printed.append(" ".join(map(str, a))))
        self.m.main()
        self.assertEqual(_read(self.path)["a"]["LF_AC"], "old")
        self.assertTrue(any("ไม่สำเร็จ" in p for p in printed), printed)


class SevenDays(_Base):
    def test_rotated_lf_and_gc_saved_per_account(self):
        import seven_days
        self.patch(seven_days, "CREDS_FILE", self.path)
        self.patch(sys, "argv", ["seven_days.py"])
        _write(self.path, {"a": {"udid": "u1", "LF_AC": "old", "guestCookie": GC},
                           "b": {"udid": "u2", "LF_AC": "bb"}})
        self.patch(seven_days, "_one", lambda k, c, claim: (k, {"ok": True, "lf_ac_next": LF, "gc_next": GC + "2"})
                   if k == "a" else (k, {"ok": False}))
        seven_days.main()
        saved = _read(self.path)
        self.assertEqual(saved["a"], {"udid": "u1", "LF_AC": LF, "guestCookie": GC + "2"})
        self.assertEqual(saved["b"], {"udid": "u2", "LF_AC": "bb"})


# ---------------------------------------------------------------- check_team / web_app / gacha_dump
class CheckTeam(_Base):
    def test_only_changed_fields_written(self):
        import check_team
        self.patch(check_team, "CREDS", self.path)
        _write(self.path, {"a": {"udid": "u1", "LF_AC": "old", "guestCookie": None, "ruby": 1},
                           "b": {"udid": "u2", "LF_AC": "bb"}})

        def fake_check(key, cred, targets, out_dir=None, device=None):
            if key == "a":
                # capture เพิ่ง /login ได้ guestCookie ให้บัญชีนี้ระหว่างตรวจ -> ต้องไม่ถูกค่าเก่า (None) ทับ
                cur = _read(self.path)
                cur["a"]["guestCookie"] = GC
                _write(self.path, cur)
                cred["LF_AC"], cred["ruby"] = LF, 7
            return {"key": key, "ok": True, "is_hit": False, "team": []}
        self.patch(check_team, "check_one_account", fake_check)
        check_team.run_batch(["x"], workers=1)
        saved = _read(self.path)
        self.assertEqual(saved["a"], {"udid": "u1", "LF_AC": LF, "guestCookie": GC, "ruby": 7})
        self.assertEqual(saved["b"], {"udid": "u2", "LF_AC": "bb"})


class WebApp(_Base):
    def test_persist_merges_and_reports_error(self):
        import web_app
        self.patch(web_app, "CREDS_FILE", self.path)
        _write(self.path, {"a": {"udid": "u1", "LF_AC": "old", "guestCookie": GC}, "b": {"udid": "u2"}})
        self.assertIsNone(web_app._persist("a", {"LF_AC": LF, "ruby": 3, "guestCookie": None}))
        saved = _read(self.path)
        self.assertEqual(saved["a"], {"udid": "u1", "LF_AC": LF, "guestCookie": GC, "ruby": 3})
        self.assertEqual(saved["b"], {"udid": "u2"})
        self.lock()
        self.assertIn("CredsLockError", web_app._persist("a", {"LF_AC": "zzz"}))
        self.assertEqual(_read(self.path)["a"]["LF_AC"], LF)


class GachaDump(_Base):
    def test_reads_without_merge_and_updates_one_account(self):
        import gacha_dump
        self.patch(gacha_dump, "CREDS_FILE", self.path)
        self.patch(sys, "argv", ["gacha_dump.py", "a"])
        _write(self.path, {"a": {"udid": "u1", "LF_AC": "old", "guestCookie": GC}, "b": {"udid": "u2"}})
        part = os.path.join(self.d, "creds.part1.json")
        _write(part, {"c": {"udid": "u3"}})

        class FakeClient:
            def __init__(self, udid, lf):
                self.lf_ac, self.guest_cookie_next = LF, None

            def gacha_info(self):
                return 500, None                                # จบก่อนเขียนไฟล์ gacha_data
        self.patch(gacha_dump, "LGRClient", FakeClient)
        gacha_dump.main()
        saved = _read(self.path)
        self.assertEqual(saved["a"], {"udid": "u1", "LF_AC": LF, "guestCookie": GC})
        self.assertEqual(saved["b"], {"udid": "u2"})
        self.assertNotIn("c", saved)                           # ไม่ merge part โดยไม่ตั้งใจ
        self.assertTrue(os.path.exists(part))


# ---------------------------------------------------------------- read-only paths
class ReadOnly(_Base):
    def test_auto_create_guest_poll_does_not_merge(self):
        import auto_create_guest as acg
        _write(self.path, {"a": {"udid": "u1", "LF_AC": LF, "guestCookie": GC}})
        _write(os.path.join(self.d, "creds.part1.json"), {"b": {"udid": "u2"}})
        before = self.snapshot()
        t = [0.0]
        got = acg.wait_for_new_credential(self.path, {"u1"}, timeout=1, interval=1,
                                          clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
        self.assertIsNone(got)
        self.assertEqual(self.snapshot(), before)

    def test_workflow_dry_run_touches_nothing(self):
        import account_workflow as wf
        _write(self.path, {"a": {"udid": "u1"}})              # ไม่มี LF_AC -> ไม่ยิงเน็ต
        _write(os.path.join(self.d, "creds.part1.json"), {"b": {"udid": "u2"}})
        before = self.snapshot()
        wf.run_workflow(wf.Config(creds_file=self.path, dry_run=True))
        self.assertEqual(self.snapshot(), before)


# ---------------------------------------------------------------- capture_auto
class CaptureAuto(_Base):
    def setUp(self):
        super().setUp()
        import capture_auto
        self.m = capture_auto
        self.patch(capture_auto, "CREDS", self.path)

    def test_no_private_writer_left(self):
        # ทุกเส้นทางเขียนต้องผ่านตัวกลาง: ไม่มี json.dump/os.replace ตรง ๆ ในไฟล์
        with open(os.path.join(HERE, "capture_auto.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("json.dump(", src)
        self.assertNotIn("os.replace(", src)

    def test_save_creds_uses_central_lock(self):
        _write(self.path, {"a": {"udid": "u1"}})
        self.lock()
        self.assertFalse(self.m.save_creds({"a": {"udid": "zzz"}}))
        self.assertEqual(_read(self.path), {"a": {"udid": "u1"}})

    def test_merge_parts_uses_central_lock(self):
        _write(self.path, {"a": {"udid": "u1"}})
        part = os.path.join(self.d, "creds.part8443.json")
        _write(part, {"b": {"udid": "u2"}})
        self.lock()
        self.assertEqual(self.m.merge_parts_into_creds([part]), 1)
        self.assertTrue(os.path.exists(part))
        os.remove(self.path + ".lock")
        self.assertEqual(self.m.merge_parts_into_creds([part]), 2)
        self.assertFalse(os.path.exists(part))
        self.assertEqual(sorted(_read(self.path)), ["a", "b"])

    def test_account_info_updates_fields_and_keeps_guest_cookie(self):
        _write(self.path, {"r1": {"udid": "u1", "LF_AC": "old", "guestCookie": GC, "rsn": "r1"},
                           "other": {"udid": "u2"}})
        cred = {"udid": "u1", "rsn": "r1", "LF_AC": LF, "guestCookie": None, "ruby": 4,
                "coin": 1, "ticket": 0, "level": 2, "file": "x.xml"}
        self.assertIsNone(self.m._save_account_info(cred, self.path))
        saved = _read(self.path)
        self.assertEqual(saved["r1"]["guestCookie"], GC)
        self.assertEqual(saved["r1"]["LF_AC"], LF)
        self.assertEqual((saved["r1"]["ruby"], saved["r1"]["level"], saved["r1"]["file"]), (4, 2, "x.xml"))
        self.assertEqual(saved["other"], {"udid": "u2"})

    def test_account_info_creates_missing_entry(self):
        _write(self.path, {"other": {"udid": "u2"}})
        cred = {"udid": "u1", "rsn": "r1", "LF_AC": LF, "guestCookie": None}
        self.assertIsNone(self.m._save_account_info(cred, self.path))
        self.assertEqual(_read(self.path)["r1"], {"udid": "u1", "rsn": "r1", "LF_AC": LF})

    def test_account_info_lock_timeout_and_corrupt_do_not_write(self):
        _write(self.path, {"r1": {"udid": "u1", "LF_AC": "old"}})
        self.lock()
        cred = {"udid": "u1", "rsn": "r1", "LF_AC": LF}
        self.assertIn("CredsLockError", self.m._save_account_info(cred, self.path))
        self.assertEqual(_read(self.path)["r1"]["LF_AC"], "old")
        os.remove(self.path + ".lock")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{broken")
        self.assertIsNotNone(self.m._save_account_info(cred, self.path))
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{broken")


if __name__ == "__main__":
    unittest.main(verbosity=2)
