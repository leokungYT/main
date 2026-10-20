#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_capture_scripts.py — เทสต์ offline ของ capture_run / capture_newid / capture_auto / auto_create_guest
ไม่แตะ ADB / อีมูเลเตอร์ / เน็ตจริง: แทน adb ด้วย FakeDevice (จำลอง state ของ iptables / mount / ไฟล์ /
adb reverse / settings) แล้วตรวจว่า setup/teardown แตะเฉพาะของที่สคริปต์สร้าง
รัน:  python -m unittest test_capture_scripts -v
"""
import os
import sys
import json
import shlex
import shutil
import tempfile
import threading
import subprocess
import unittest

os.environ["LGR_MIN_GAP"] = "0"
os.environ["LGR_PROXY"] = ""

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lgr_api
import capture_run
import capture_newid


class _R:
    def __init__(self, rc=0, out=""):
        self.returncode, self.stdout, self.stderr = rc, out, ""


class FakeDevice:
    """จำลองอีมูฯ หนึ่งเครื่องพอให้ตรวจพฤติกรรม setup/teardown ได้
    รับเฉพาะรูปแบบคำสั่งที่สคริปต์ใช้ ; คำสั่ง su ถูก parse ด้วย shlex (POSIX) -> ตรวจ quoting ไปในตัว"""
    def __init__(self):
        self.rules = []            # iptables nat OUTPUT (สตริงกฎ)
        self.mounts = set()        # จุด mount (bind)
        self.files = set()         # path ที่มีอยู่
        self.reverses = set()
        self.settings = {"http_proxy": "null"}
        self.route_localnet = "0"
        self.log = []              # คำสั่งย่อยทั้งหมดที่รัน (หลังแตก su)
        self.fail = set()          # ชื่อ action ที่ให้ล้ม เช่น "iptables -A", "umount"

    # ---- adb argv ----
    def adb(self, serial, *args, **kw):
        args = list(args)
        if args[0] == "reverse":
            self.log.append("adb " + " ".join(args))
            if args[1] == "--list":
                return _R(0, "".join(f"host-1 {r} {r}\n" for r in sorted(self.reverses)))
            if args[1] == "--remove-all":
                self.reverses.clear()
            elif args[1] == "--remove":
                self.reverses.discard(args[2])
            elif "reverse" not in self.fail:
                self.reverses.add(args[1])
            return _R()
        if args[0] == "push":
            self.files.add(args[2])
            self.log.append("adb push " + args[2])
            return _R()
        if args[0] == "pull":
            self.log.append("adb pull " + args[1])
            return _R()
        if args[0] == "shell":
            rest = args[1:]
            if len(rest) == 1 and rest[0].startswith("su -c "):
                argv = shlex.split(rest[0])               # ตรวจว่า quote ถูก: ต้องได้ 3 ชิ้นพอดี
                assert argv[:2] == ["su", "-c"] and len(argv) == 3, argv
                return self.sh(argv[2])
            return self.sh(" ".join(rest))
        raise AssertionError(f"adb {args} ไม่รองรับใน fake")

    # ---- shell ฝั่งเครื่อง ----
    def sh(self, cmd):
        rc, out = 0, ""
        for part in self._split(cmd):
            r = self._one(part)
            rc, out = r.returncode, out + r.stdout
            if rc != 0 and part.endswith("&&"):
                break
        return _R(rc, out)

    @staticmethod
    def _split(cmd):
        out, buf, depth = [], "", 0
        toks = cmd.replace("&&", " && ").split(" ")
        for t in toks:
            if t in ("{",):
                depth += 1
            if t in ("}",):
                depth -= 1
            buf += t + " "
            if depth == 0 and (t.endswith(";") or t == "&&"):
                out.append(buf.strip())
                buf = ""
        if buf.strip():
            out.append(buf.strip())
        return out

    def _one(self, part):
        c = part.rstrip(";&").strip()
        if not c:
            return _R()
        self.log.append(c)
        a = shlex.split(c.split(" 2>")[0].split(" >/dev")[0])
        if a[:3] == ["iptables", "-t", "nat"]:
            op, rule = a[3], " ".join(a[4:])
            if op == "-C":
                return _R(0 if rule in self.rules else 1)
            if op == "-A":
                if "iptables -A" in self.fail:
                    return _R(1)
                self.rules.append(rule)
            elif op == "-D":
                if rule not in self.rules:
                    return _R(1)
                self.rules.remove(rule)
            elif op == "-F":
                self.rules.clear()
            elif op == "-S":
                return _R(0, "".join(f"-A {r}\n" for r in self.rules))
            return _R()
        if a[0] == "cat" and a[1] == "/proc/mounts":
            return _R(0, "".join(f"tmpfs {m} tmpfs rw 0 0\n" for m in sorted(self.mounts)))
        if a[0] == "cat" and a[1] == capture_newid.ROUTE_LOCALNET:
            return _R(0, self.route_localnet + "\n")
        if a[0] == "echo" and len(a) >= 3 and a[2] == ">":
            if a[3] == capture_newid.ROUTE_LOCALNET:
                self.route_localnet = a[1]
            return _R()
        if a[0] == "mount" and a[1] == "--bind":
            if "mount" in self.fail:
                return _R(1)
            self.mounts.add(a[3])
            return _R()
        if a[0] == "umount":
            if "umount" in self.fail or a[1] not in self.mounts:
                return _R(1)
            self.mounts.discard(a[1])
            return _R()
        if a[0] == "test":
            return _R(0 if a[2] in self.files else 1)
        if a[0] == "mkdir":
            self.files.add(a[-1])
            return _R()
        if a[0] == "cp":
            self.files.add(a[-1].rstrip("/"))
            return _R()
        if a[0] == "rm":
            for p in a[2:]:
                self.files.discard(p)
            return _R()
        if a[0] == "settings":
            if a[1] == "get":
                return _R(0, self.settings.get(a[3], "null") + "\n")
            self.settings[a[3]] = a[4]
            return _R()
        # grep/echo >>/chmod/chown/chcon/ls/mv/am/pm/monkey: บันทึกไว้ใน log ให้เทสต์ตรวจ
        return _R()


class _DevCase(unittest.TestCase):
    module = None

    def setUp(self):
        self.dev = FakeDevice()
        self.patch(self.module, "adb", self.dev.adb)
        self.patch(self.module, "_CREATED", {})
        # กันพลาดไปเรียก process จริง
        self.patch(subprocess, "run", self._no_proc)
        self.patch(subprocess, "Popen", self._no_proc)

    @staticmethod
    def _no_proc(*a, **kw):
        raise AssertionError("ห้ามเรียก subprocess จริงในเทสต์")

    def patch(self, obj, name, value):
        orig = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(lambda: setattr(obj, name, orig))

    def assert_no_broad_cleanup(self):
        joined = "\n".join(self.dev.log)
        self.assertNotIn("iptables -t nat -F", joined)
        self.assertNotIn("--remove-all", joined)
        self.assertNotIn("pm clear", joined)


# ================================================================ capture_run
class SuQuoting(unittest.TestCase):
    CASES = [
        "iptables -t nat -C OUTPUT -p tcp",
        "echo '127.0.0.1 rangers-api.line-apps.com' >> /data/local/tmp/x",
        "it's a 'quoted' word",
        "a  b\tc",
        "$HOME `id` $(id) \\n ; && || | > < * ? ! # ~ { } [ ] \"dq\"",
        "",
        "'",
        "''''",
    ]

    def test_round_trip_through_posix_sh_parsing(self):
        for cmd in self.CASES:
            with self.subTest(cmd=cmd):
                argv = shlex.split(capture_run.su_command(cmd))
                self.assertEqual(argv, ["su", "-c", cmd])
                self.assertEqual(shlex.split("x " + capture_run.sh_quote(cmd)), ["x", cmd])

    def test_old_escape_was_broken(self):
        # หลักฐานของบั๊กเดิม: "'\''" (ไม่ใช่ raw) = "'''" -> ข้อความมี ' ถูกแตกเป็นหลาย argument
        old = "su -c '" + "echo 'a b'".replace("'", "'\''") + "'"
        self.assertNotEqual(shlex.split(old), ["su", "-c", "echo 'a b'"])

    def test_matches_newid_quoting(self):
        for cmd in self.CASES:
            sent = []
            orig = capture_newid.adb
            capture_newid.adb = lambda serial, *a: sent.append(a) or _R()
            try:
                capture_newid.su("s", cmd)
            finally:
                capture_newid.adb = orig
            self.assertEqual(sent[0], ("shell", capture_run.su_command(cmd)))


class CaptureRunRouting(_DevCase):
    module = capture_run

    def test_setup_then_teardown_restores_only_own(self):
        foreign = "OUTPUT -p udp --dport 53 -j ACCEPT"
        self.dev.rules.append(foreign)
        self.dev.mounts.add("/system/etc/security/cacerts")
        self.dev.reverses.add("tcp:5000")
        self.dev.files.add("/system/etc/hosts")
        self.assertTrue(capture_run.setup("s"))
        self.assertIn(capture_run.RULE, self.dev.rules)
        self.assertIn(capture_run.HOSTS, self.dev.mounts)
        self.assertEqual(capture_run.teardown("s"), [])
        self.assertEqual(self.dev.rules, [foreign])
        self.assertEqual(self.dev.mounts, {"/system/etc/security/cacerts"})
        self.assertEqual(self.dev.reverses, {"tcp:5000"})
        self.assertNotIn(capture_run.HOSTS_COPY, self.dev.files)
        self.assert_no_broad_cleanup()

    def test_refuses_when_foreign_routing_present(self):
        self.dev.rules.append(capture_run.RULE)               # ของสคริปต์อื่นค้าง
        self.assertFalse(capture_run.setup("s"))
        self.assertEqual(capture_run.teardown("s"), [])
        self.assertEqual(self.dev.rules, [capture_run.RULE])  # ไม่ถูกลบ
        self.assertEqual(self.dev.reverses, set())

    def test_partial_setup_rolls_back_only_what_succeeded(self):
        self.dev.fail.add("iptables -A")
        self.assertFalse(capture_run.setup("s"))
        self.assertEqual(sorted(capture_run._CREATED["s"]), ["hosts", "hosts_copy", "reverse"])
        self.assertEqual(capture_run.teardown("s"), [])
        self.assertEqual((self.dev.rules, self.dev.mounts, self.dev.reverses), ([], set(), set()))
        self.assertFalse(any("iptables -t nat -D" in c for c in self.dev.log))  # ไม่ลบกฎที่ไม่ได้สร้าง

    def test_teardown_reports_leftovers(self):
        self.assertTrue(capture_run.setup("s"))
        self.dev.fail.add("umount")
        left = capture_run.teardown("s")
        self.assertEqual(left, [f"bind-mount {capture_run.HOSTS}"])
        self.assertIn(capture_run.HOSTS_COPY, self.dev.files)  # mount ยังอยู่ -> ไม่ลบไฟล์ใต้มัน

    def test_main_uses_find_mitmdump(self):
        with open(os.path.join(HERE, "capture_run.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("[find_mitmdump(), ", src)
        self.assertNotIn('["mitmdump"', src)


# ================================================================ capture_newid
class CaptureNewidRouting(_DevCase):
    module = capture_newid

    def setUp(self):
        super().setUp()
        self.patch(capture_newid, "LOG_DIR", tempfile.mkdtemp(prefix="lgr_newid_test_"))
        self.addCleanup(shutil.rmtree, capture_newid.LOG_DIR, True)

    def test_setup_teardown_keeps_foreign_rules_and_restores_real_values(self):
        foreign = ["OUTPUT -p udp --dport 53 -j ACCEPT",
                   "OUTPUT -p tcp --dport 80 -j DNAT --to-destination 127.0.0.1:9000"]
        self.dev.rules += foreign
        self.dev.settings["http_proxy"] = "10.0.0.5:3128"
        self.dev.route_localnet = "0"
        self.assertTrue(capture_newid.setup("s"))
        self.assertEqual(self.dev.route_localnet, "1")
        self.assertEqual(self.dev.settings["http_proxy"], ":0")
        self.assertEqual(capture_newid.teardown("s"), [])
        self.assertEqual(self.dev.rules, foreign)
        self.assertEqual(self.dev.route_localnet, "0")                 # คืนค่าที่อ่านได้จริง
        self.assertEqual(self.dev.settings["http_proxy"], "10.0.0.5:3128")
        self.assertEqual(self.dev.reverses, set())
        self.assert_no_broad_cleanup()

    def test_route_localnet_already_on_is_left_alone(self):
        self.dev.route_localnet = "1"
        self.assertTrue(capture_newid.setup("s"))
        capture_newid.teardown("s")
        self.assertEqual(self.dev.route_localnet, "1")
        self.assertFalse(any(c.startswith("echo 0 >") for c in self.dev.log))

    def test_refuses_foreign_hosts_mount_and_redirect(self):
        for prep in (lambda d: d.mounts.add(capture_newid.HOSTS),
                     lambda d: d.rules.append(capture_newid.OTHER_RULE),
                     lambda d: d.rules.append(capture_newid.RULE),
                     lambda d: d.reverses.add(f"tcp:{capture_newid.PORT}")):
            with self.subTest(prep=prep):
                self.dev = FakeDevice()
                capture_newid.adb = self.dev.adb
                prep(self.dev)
                before = (list(self.dev.rules), set(self.dev.mounts), set(self.dev.reverses))
                self.assertFalse(capture_newid.setup("s"))
                self.assertEqual(capture_newid.teardown("s"), [])
                self.assertEqual((self.dev.rules, self.dev.mounts, self.dev.reverses), before)
                self.assertFalse(any("umount" in c for c in self.dev.log))

    def test_partial_setup_rolls_back_only_what_succeeded(self):
        self.dev.fail.add("iptables -A")
        self.assertFalse(capture_newid.setup("s"))
        self.assertEqual(sorted(capture_newid._CREATED["s"]), ["reverse", "route_localnet"])
        self.assertEqual(capture_newid.teardown("s"), [])
        self.assertEqual((self.dev.rules, self.dev.reverses, self.dev.route_localnet), ([], set(), "0"))
        self.assertFalse(any("iptables -t nat -D" in c for c in self.dev.log))

    def _fake_pem(self):
        home = tempfile.mkdtemp(prefix="lgr_home_test_")
        self.addCleanup(shutil.rmtree, home, True)
        os.makedirs(os.path.join(home, ".mitmproxy"))
        pem = os.path.join(home, ".mitmproxy", "mitmproxy-ca-cert.pem")
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        import datetime
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-ca")])
        now = datetime.datetime(2026, 1, 1)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
                .sign(key, hashes.SHA256()))
        with open(pem, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        self.patch(os.path, "expanduser", lambda p: p.replace("~", home))

    def test_ca_skips_foreign_mount_and_dir(self):
        self._fake_pem()
        self.dev.mounts.add(capture_newid.CACERTS)              # มีคนอื่น mount ไว้
        self.assertFalse(capture_newid.install_ca("s"))
        capture_newid.teardown("s")
        self.assertIn(capture_newid.CACERTS, self.dev.mounts)
        self.assertFalse(any(c.startswith("umount") for c in self.dev.log))

        self.dev = FakeDevice()
        capture_newid.adb = self.dev.adb
        self.dev.files.add(capture_newid.CA_DIR)               # โฟลเดอร์ค้าง ไม่ใช่ของรอบนี้
        self.assertFalse(capture_newid.install_ca("s"))
        capture_newid.teardown("s")
        self.assertIn(capture_newid.CA_DIR, self.dev.files)

    def test_ca_installed_then_removed(self):
        self._fake_pem()
        self.assertTrue(capture_newid.install_ca("s"))
        self.assertIn(capture_newid.CACERTS, self.dev.mounts)
        self.assertEqual(capture_newid.teardown("s"), [])
        self.assertNotIn(capture_newid.CACERTS, self.dev.mounts)
        self.assertNotIn(capture_newid.CA_DIR, self.dev.files)

    def test_ca_umount_failure_reported_and_dir_kept(self):
        self._fake_pem()
        self.assertTrue(capture_newid.install_ca("s"))
        self.dev.fail.add("umount")
        left = capture_newid.teardown("s")
        self.assertEqual(left, [f"bind-mount {capture_newid.CACERTS}"])
        self.assertIn(capture_newid.CA_DIR, self.dev.files)

    def test_no_pm_clear_without_confirm(self):
        self.assertFalse(capture_newid.backup_and_clear("s", "t1"))
        self.assertEqual(self.dev.log, [])

    def test_no_pm_clear_when_backup_failed(self):
        # pull ไม่ได้ไฟล์ .xml (fake ไม่สร้างไฟล์ฝั่ง PC) -> ต้องไม่ clear แม้ยืนยัน
        self.assertFalse(capture_newid.backup_and_clear("s", "t2", confirm=True))
        self.assertFalse(any("pm clear" in c or "force-stop" in c for c in self.dev.log))

    def test_clear_only_after_backup_and_confirm(self):
        def pull(serial, *args, **kw):
            if args[0] == "pull":
                os.makedirs(os.path.join(args[2], "x"), exist_ok=True)
                open(os.path.join(args[2], "x", "_LINE_COCOS_PREF_KEY.xml"), "w").close()
                return _R()
            return self.dev.adb(serial, *args, **kw)
        capture_newid.adb = pull
        self.assertTrue(capture_newid.backup_and_clear("s", "t3", confirm=True))
        self.assertTrue(any("pm clear" in c for c in self.dev.log))

    def test_source_has_no_broad_cleanup(self):
        with open(os.path.join(HERE, "capture_newid.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("-F OUTPUT", src)
        self.assertNotIn('"--remove-all"', src)
        self.assertNotIn("sysctl -w", src)


# ================================================================ capture_auto
class CaptureAutoRouting(unittest.TestCase):
    """capture_auto.setup_routing/teardown_routing/sh กับ FakeDevice (adb ของ capture_auto รับ list args)"""
    def setUp(self):
        import capture_auto
        self.m = capture_auto
        self.dev = FakeDevice()
        self.dev.files.add(capture_auto.HOSTS)
        self._patch(capture_auto, "adb", lambda args, device=None, **kw: self.dev.adb(device, *args))
        self._patch(capture_auto, "_ROUTE_OWNED", {})
        self._patch(capture_auto, "_ROUTE_PORT", {})
        self._patch(capture_auto, "_ROOT_ADBD", False)        # บังคับผ่าน su -c -> ตรวจ quoting
        self._patch(subprocess, "run", _DevCase._no_proc)
        self._patch(subprocess, "Popen", _DevCase._no_proc)

    def _patch(self, obj, name, value):
        orig = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(lambda: setattr(obj, name, orig))

    def state(self):
        return (list(self.dev.rules), set(self.dev.mounts), set(self.dev.reverses), set(self.dev.files))

    def assert_no_broad(self):
        joined = "\n".join(self.dev.log)
        self.assertNotIn("iptables -t nat -F", joined)
        self.assertNotIn("--remove-all", joined)

    def test_sh_quotes_su_argument(self):
        for cmd in SuQuoting.CASES:
            with self.subTest(cmd=cmd):
                sent = []
                self._patch(self.m, "adb", lambda args, device=None, **kw: sent.append(args) or _R())
                self.m.sh(cmd, device="s")
                self.assertEqual(shlex.split(sent[-1][1]), ["su", "-c", cmd])

    def test_setup_then_teardown_keeps_foreign(self):
        foreign = "OUTPUT -p udp --dport 53 -j ACCEPT"
        self.dev.rules.append(foreign)
        self.dev.mounts.add("/system/etc/security/cacerts")
        self.dev.reverses.add("tcp:5000")
        before = self.state()
        self.assertTrue(self.m.setup_routing("s", 8450))
        self.assertIn(self.m._ROUTE_RULE, self.dev.rules)
        self.assertIn(self.m.HOSTS, self.dev.mounts)
        self.assertEqual(self.m.teardown_routing("s"), [])
        self.assertEqual(self.state(), before)
        self.assert_no_broad()

    def test_conflicts_stop_without_touching(self):
        preps = {
            "rule": lambda d: d.rules.append(self.m._ROUTE_RULE),
            "hosts": lambda d: d.mounts.add(self.m.HOSTS),
            "hosts_copy": lambda d: d.files.add(self.m.HOSTS_COPY),
            "reverse": lambda d: d.reverses.add(f"tcp:{self.m.DEV_PORT}"),
        }
        for name, prep in preps.items():
            with self.subTest(existing=name):
                self.dev = FakeDevice()
                self.dev.files.add(self.m.HOSTS)
                self.m._ROUTE_OWNED.clear()
                prep(self.dev)
                before = self.state()
                with self.assertRaises(self.m.RoutingConflict):
                    self.m.setup_routing("s")
                self.assertEqual(self.m.teardown_routing("s"), [])
                self.assertEqual(self.state(), before)            # ของเดิมยังอยู่ครบ ไม่มีอะไรเพิ่ม
                self.assertFalse(any(c.startswith(("umount", "rm ", "iptables -t nat -D", "mount"))
                                     for c in self.dev.log))
                self.assertFalse(any(c.startswith("adb reverse --remove") or c.startswith("adb reverse tcp")
                                     for c in self.dev.log))

    def test_resetup_after_reset_ip_recreates_own_only(self):
        self.assertTrue(self.m.setup_routing("s"))
        # Reset IP ล้างกฎ/reverse ของเราไป (mount ยังอยู่) -> setup ซ้ำต้องตั้งกลับได้ ไม่ถือว่าเป็นของคนอื่น
        self.dev.rules.remove(self.m._ROUTE_RULE)
        self.dev.reverses.clear()
        self.assertTrue(self.m.setup_routing("s"))
        self.assertEqual(self.dev.rules.count(self.m._ROUTE_RULE), 1)
        mounts_cmds = [c for c in self.dev.log if c.startswith("mount --bind")]
        self.assertEqual(len(mounts_cmds), 1)                       # ไม่ mount ซ้อน
        self.assertEqual(self.m.teardown_routing("s"), [])
        self.assertEqual((self.dev.rules, self.dev.mounts, self.dev.reverses), ([], set(), set()))

    def test_partial_setup_rolls_back_only_owned(self):
        self.dev.fail.add("iptables -A")
        self.assertFalse(self.m.setup_routing("s"))
        self.assertEqual(self.m._ROUTE_OWNED["s"], {"reverse", "hosts_copy", "hosts"})
        self.assertEqual(self.m.teardown_routing("s"), [])
        self.assertFalse(any(c.startswith("iptables -t nat -D") for c in self.dev.log))
        self.assertEqual((self.dev.mounts, self.dev.reverses), (set(), set()))
        self.assertNotIn(self.m.HOSTS_COPY, self.dev.files)

    def test_teardown_reports_leftover_and_keeps_copy_under_mount(self):
        self.assertTrue(self.m.setup_routing("s"))
        self.dev.fail.add("umount")
        left = self.m.teardown_routing("s")
        self.assertEqual(left, [f"bind-mount {self.m.HOSTS}"])
        self.assertIn(self.m.HOSTS_COPY, self.dev.files)

    def test_worker_conflict_starts_nothing(self):
        self.dev.rules.append(self.m._ROUTE_RULE)
        before = self.state()
        started = []
        self._patch(self.m, "enable_root", lambda d: False)
        self._patch(self.m, "start_mitm", lambda *a, **k: started.append(a))
        with self.assertRaises(self.m.RoutingConflict):
            self.m._process_xml_queue("s", [], None, False, 1, "move", 9998, None)
        self.assertEqual(started, [])
        self.assertEqual(self.state(), before)

    def test_source_has_no_broad_cleanup(self):
        with open(os.path.join(HERE, "capture_auto.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("-F OUTPUT", src)
        self.assertNotIn('"--remove-all"', src)
        self.assertNotIn("while grep -q", src)


# ================================================================ part files: lock + ownership
class PartFileProtocol(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="lgr_part_test_")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.creds = os.path.join(self.d, "creds.json")
        self.part = os.path.join(self.d, "creds.part8443.json")
        with open(self.creds, "w", encoding="utf-8") as f:
            json.dump({"old": {"udid": "u0"}}, f)

    def _read(self, p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def test_glob_merge_skips_part_in_use(self):
        with open(self.part, "w", encoding="utf-8") as f:
            json.dump({"r1": {"udid": "u1"}}, f)
        with lgr_api.part_owner(self.part):
            merged, n = lgr_api.merge_part_creds(creds_path=self.creds)      # สคริปต์อื่น (auto_merge)
            self.assertEqual(n, 0)
            self.assertTrue(os.path.exists(self.part))
            merged, n = lgr_api.merge_part_creds(creds_path=self.creds, part_files=[self.part])  # เจ้าของ
            self.assertEqual(n, 1)
        self.assertFalse(os.path.exists(self.part + lgr_api.PART_ACTIVE_SUFFIX))
        self.assertIn("r1", self._read(self.creds))

    def test_merge_waits_for_addon_write_then_includes_it(self):
        # addon ถือ lock ของ part ระหว่าง read-modify-write -> merge ต้องรอ แล้วได้ข้อมูลครบ (ไม่ลบก่อนเขียนเสร็จ)
        with open(self.part, "w", encoding="utf-8") as f:
            json.dump({"r1": {"udid": "u1"}}, f)
        in_lock, release = threading.Event(), threading.Event()

        def addon_write():
            with lgr_api.creds_lock(self.part):
                cur = lgr_api._read_json_file(self.part)
                in_lock.set()
                release.wait(2)
                cur["r1"]["LF_AC"] = "L" * 260
                cur["r1"]["guestCookie"] = "G" * 260
                lgr_api._write_creds_atomic(cur, self.part)
        t = threading.Thread(target=addon_write)
        t.start()
        in_lock.wait(2)
        result = {}

        def do_merge():
            result["r"] = lgr_api.merge_part_creds(creds_path=self.creds, part_files=[self.part])
        m = threading.Thread(target=do_merge)
        m.start()
        m.join(0.3)
        self.assertTrue(m.is_alive())                       # ยังรอ lock ของ part อยู่
        self.assertTrue(os.path.exists(self.part))
        release.set()
        t.join(2)
        m.join(5)
        self.assertEqual(result["r"][1], 1)
        saved = self._read(self.creds)["r1"]
        self.assertEqual(saved["guestCookie"], "G" * 260)    # ข้อมูลที่ addon เขียนระหว่างรอ ไม่หาย
        self.assertFalse(os.path.exists(self.part))

    def test_addon_write_after_merge_recreates_part_without_clobbering(self):
        # merge ลบ part ไปแล้ว -> addon เขียนต่อ (LF_AC หมุน) = part ใหม่ ; merge รอบถัดไปต้องไม่เอา None ทับ guestCookie
        with open(self.part, "w", encoding="utf-8") as f:
            json.dump({"r1": {"udid": "u1", "LF_AC": "A" * 260, "guestCookie": "G" * 260}}, f)
        lgr_api.merge_part_creds(creds_path=self.creds, part_files=[self.part])
        import capture_credential as cc
        orig = cc.CREDS
        cc.CREDS = self.part
        try:
            cc._store("r1", "u1", "B" * 260, None, None, None, None, None)
        finally:
            cc.CREDS = orig
        self.assertEqual(self._read(self.part)["r1"]["guestCookie"], None)
        lgr_api.merge_part_creds(creds_path=self.creds, part_files=[self.part])
        saved = self._read(self.creds)["r1"]
        self.assertEqual(saved["LF_AC"], "B" * 260)
        self.assertEqual(saved["guestCookie"], "G" * 260)

    def test_capture_auto_workers_own_their_part(self):
        import capture_auto
        orig_creds = capture_auto.CREDS
        capture_auto.CREDS = self.creds
        self.addCleanup(lambda: setattr(capture_auto, "CREDS", orig_creds))
        part = capture_auto.part_creds(9999)
        self.addCleanup(lambda: os.path.exists(part) and os.remove(part))
        seen = {}

        def fake_inner(*a, **kw):
            seen["active"] = lgr_api.part_in_use(part)
            return [], []
        orig = capture_auto._process_xml_queue
        capture_auto._process_xml_queue = fake_inner
        try:
            capture_auto.process_xml_queue("dev", [], None, False, 1, host_port=9999)
        finally:
            capture_auto._process_xml_queue = orig
        self.assertTrue(seen["active"])
        self.assertFalse(lgr_api.part_in_use(part))


# ================================================================ dry-run
class AutoCreateDryRun(unittest.TestCase):
    def test_dry_run_issues_only_read_commands_and_touches_no_files(self):
        import auto_create_guest as acg
        d = tempfile.mkdtemp(prefix="lgr_acg_test_")
        self.addCleanup(shutil.rmtree, d, True)
        creds = os.path.join(d, "creds.json")
        with open(creds, "w", encoding="utf-8") as f:
            json.dump({}, f)
        with open(os.path.join(d, "creds.part1.json"), "w", encoding="utf-8") as f:
            json.dump({"x": {"udid": "u"}}, f)
        def snapshot():
            out = {}
            for n in os.listdir(d):
                with open(os.path.join(d, n), "rb") as f:
                    out[n] = f.read()
            return out
        before = snapshot()

        class FakeAdb:
            def __init__(self):
                self.calls = []

            def devices(self):
                return ["emu-1"]

            def connect(self, hp):
                self.calls.append(("connect", hp))

            def android_id(self, s):
                return "aid"

            def shell(self, s, cmd, timeout=20):
                self.calls.append(("shell", cmd))
                return _R(0, "package:/data/app/x.apk" if cmd.startswith("pm path") else "")

            def su(self, s, cmd, timeout=20):
                self.calls.append(("su", cmd))
                return _R(0, "uid=0(root)" if cmd == "id" else "")

        fake = FakeAdb()
        orig_popen = subprocess.Popen
        subprocess.Popen = lambda *a, **k: (_ for _ in ()).throw(AssertionError("ห้ามเปิด process"))
        try:
            res = acg.Orchestrator(fake, acg.Config(dry_run=True, creds_file=creds)).run()
        finally:
            subprocess.Popen = orig_popen
        self.assertEqual(res["status"], acg.DRY_RUN)
        text = repr(fake.calls)
        for bad in ("pm clear", "iptables", "mount", "reverse", "monkey", "force-stop", "rm "):
            self.assertNotIn(bad, text)
        self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
