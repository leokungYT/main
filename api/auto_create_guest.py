#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_create_guest.py — orchestrator สร้าง "Guest ID ใหม่" ผ่านตัวเกมจริง (ADB) แล้วจับ credential
                        ที่ไคลเอนต์ยิงออกมา (udid+LF_AC+guestCookie) เก็บลง creds.json แบบ atomic

reuse โมดูลเดิม (ไม่ทำซ้ำ):
  - capture_newid : ฟังก์ชัน routing/CA/mitm/backup (subprocess ล้วน)  -> redirect 443 + bind CA
  - capture_credential : mitmproxy addon ที่ "เขียน creds.json" จากทราฟฟิก /login จริง
  - lgr_api       : load/save creds (atomic), MIN_COOKIE_LEN, LGRClient
  - account_workflow : verify บัญชีแบบ read-only (ยืนยันด้วย rsn/mid จากเซิร์ฟ)

เส้นแบ่งที่พิสูจน์แล้ว (LGR-API-NOTES §14): การ mint guest ต้องให้ "ตัวเกม" ทำ เพราะ
  auth/v3.8/authentication/GUEST ต้องลายเซ็น native (si=) + ยอมรับ ToS ; signup/guest ต้อง X-Guest-Signature
  และ "guestCookie" (credential ถาวร) ไหลผ่านตอน GET /login เท่านั้น (ไม่ใช่ตอน signup)
  -> orchestrator นี้จึง "ขับเกม + จับ" ไม่ปลอมลายเซ็น/ไม่ reuse session บัญชีอื่น/ไม่ข้าม ToS

ความปลอดภัย (บังคับ):
  - ระบุเครื่องเป้าหมายชัดเจน ; ไม่ pm clear / ไม่ลบบัญชี เว้นแต่ยืนยัน (--yes-clear) และสำรองแล้ว
  - ถ้าบัญชีบนเครื่อง "ยังไม่ถูก backup" (ไม่มีใน creds พร้อม guestCookie) -> หยุด ไม่ทำอะไรทั้งนั้น
  - --dry-run : ตรวจ/วางแผนอย่างเดียว ไม่แตะ mitm/clear/launch
  - --max N : เพดานจำนวนบัญชีต่อรอบ (กันสร้างรัว ๆ โดยอุบัติเหตุ) ; ไม่ retry สร้างไม่รู้จบ
  - ปิดเฉพาะโปรเซส/พอร์ตที่ตัวเองเปิด

ใช้ (ยังไม่สร้างจริงจนกว่าจะยืนยัน):
  python auto_create_guest.py --dry-run                    # ตรวจเครื่อง+แผน (ปลอดภัย)
  python auto_create_guest.py --serial 127.0.0.1:5563 --yes-clear --max 1
"""
import argparse
import logging
import os
import re
import subprocess
import sys
import time

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import capture_newid as cap                     # subprocess-only helpers (ปลอดภัยที่จะ import)
from lgr_api import load_creds, save_creds, MIN_COOKIE_LEN, CREDS_FILE
import account_workflow as wf

log = logging.getLogger("lgr.autocreate")
PKG = "com.linecorp.LGRGS"

# สถานะผลลัพธ์
CREATED = "CREATED"             # ได้บัญชีใหม่ครบ + เซฟแล้ว
DRY_RUN = "DRY_RUN"             # โหมดวางแผน
NEEDS_CONFIRM = "NEEDS_CONFIRM"  # ต้องยืนยัน --yes-clear (บัญชีบนเครื่องยังไม่ถูก backup)
NEEDS_MANUAL = "NEEDS_MANUAL"   # ต้องกดผ่าน UI/ToS เอง (ขับอัตโนมัติไม่ครบ) — ยังไม่ได้บัญชี
TIMEOUT = "TIMEOUT"             # จับ credential ใหม่ไม่ทันในเวลาที่กำหนด
DEVICE_ERROR = "DEVICE_ERROR"   # เครื่องกำกวม/หลุด/ไม่มีเกม


def mask(secret):
    if not secret:
        return "-"
    s = str(secret)
    return f"{s[:6]}..(len={len(s)})"


# --------------------------------------------------------------------- ADB (inject ได้ -> เทสต์ offline)
class Adb:
    """ครอบ adb เป็น object เดียว เพื่อให้เทสต์ fake ได้ (ไม่แตะ subprocess จริง)"""
    def __init__(self, binary=None):
        self.binary = binary or cap.ADB

    def raw(self, *args, timeout=20):
        return subprocess.run([self.binary, *args], capture_output=True, text=True, timeout=timeout)

    def connect(self, hostport):
        return self.raw("connect", hostport, timeout=5)

    def shell(self, serial, cmd, timeout=20):
        return self.raw("-s", serial, "shell", cmd, timeout=timeout)

    def su(self, serial, cmd, timeout=20):
        return self.shell(serial, "su -c '" + cmd.replace("'", "'\\''") + "'", timeout=timeout)

    def devices(self):
        out = self.raw("devices", timeout=10).stdout or ""
        return [l.split()[0] for l in out.splitlines()[1:] if l.strip().endswith("device")]

    def android_id(self, serial):
        return (self.shell(serial, "settings get secure android_id", timeout=10).stdout or "").strip()


COMMON_PORTS = [7555, 5555, 5557, 5563] + [16384 + 32 * i for i in range(8)]


def list_devices(adb):
    """คืน list ของ serial 'หนึ่งต่อหนึ่งเครื่องจริง' (ยุบ alias ที่ android_id ซ้ำ)"""
    devs = adb.devices()
    if not devs:
        for p in COMMON_PORTS:
            adb.connect(f"127.0.0.1:{p}")
        devs = adb.devices()
    seen, uniq = {}, []
    for d in devs:
        aid = adb.android_id(d)
        key = aid or d                         # ถ้าอ่าน android_id ไม่ได้ อย่ายุบรวมมั่ว
        if key not in seen:
            seen[key] = d
            uniq.append(d)
    return uniq


class AmbiguousDevice(Exception):
    pass


def select_device(adb, serial=None):
    """เลือกเครื่องเป้าหมายให้ชัด: ระบุ serial ตรง ๆ, หรือมีเครื่องเดียว; ไม่งั้น error (ไม่เดา)"""
    devs = list_devices(adb)
    if serial:
        if serial in devs:
            return serial
        # ผู้ใช้อาจระบุ host:port ที่ยังไม่ connect
        adb.connect(serial)
        if serial in adb.devices():
            return serial
        raise AmbiguousDevice(f"ไม่พบเครื่อง {serial} (เห็น: {devs})")
    if len(devs) == 1:
        return devs[0]
    raise AmbiguousDevice(f"เห็น {len(devs)} เครื่อง {devs} -> ระบุ --serial ให้ชัด")


# --------------------------------------------------------------------- preflight
def preflight(adb, serial):
    """ตรวจพร้อมใช้งาน: ออนไลน์ / ติดตั้งเกม / root"""
    online = serial in adb.devices()
    game = bool((adb.shell(serial, f"pm path {PKG}", timeout=10).stdout or "").strip().startswith("package:"))
    root = (adb.su(serial, "id", timeout=10).stdout or "").find("uid=0") >= 0
    return {"online": online, "game_installed": game, "root": root}


def current_udid(adb, serial):
    """อ่าน _DEVICE_UUID_KEY ของบัญชีที่โหลดอยู่ (ไม่ pull ไฟล์). คืน None ถ้าไม่มีบัญชี/อ่านไม่ได้"""
    pref = f"/data/data/{PKG}/shared_prefs/_LINE_COCOS_PREF_KEY.xml"
    for getter in (lambda: adb.su(serial, f"cat {pref}", timeout=10),
                   lambda: adb.shell(serial, f"cat {pref}", timeout=10)):
        m = re.search(r'_DEVICE_UUID_KEY">([^<]+)<', getter().stdout or "")
        if m:
            return m.group(1).strip()
    return None


# --------------------------------------------------------------------- credential validation
def validate_credential(entry):
    """ตรวจว่า credential ครบใช้งานได้จริงตามสคีมา creds.json. คืน (ok, reasons[])"""
    reasons = []
    if not isinstance(entry, dict):
        return False, ["ไม่ใช่ record"]
    if not entry.get("udid"):
        reasons.append("ไม่มี udid")
    if not (entry.get("LF_AC") and len(str(entry["LF_AC"])) >= MIN_COOKIE_LEN):
        reasons.append("LF_AC สั้น/หาย (ยังล็อกอินไม่เสร็จ)")
    if not (entry.get("guestCookie") and len(str(entry["guestCookie"])) >= MIN_COOKIE_LEN):
        reasons.append("ไม่มี guestCookie (เกมยังไม่ยิง /login หลัง signup)")
    return (not reasons), reasons


def is_backed_up(creds, udid):
    """บัญชี udid นี้ถูกเซฟใน creds พร้อม guestCookie แล้วหรือยัง (clear ได้อย่างปลอดภัย)"""
    if not udid:
        return False
    for v in creds.values():
        if isinstance(v, dict) and v.get("udid") == udid:
            ok, _ = validate_credential(v)
            if ok:
                return True
    return False


def account_udids(creds):
    return {v["udid"] for v in creds.values() if isinstance(v, dict) and v.get("udid")}


def find_new_accounts(before_udids, creds):
    """คืน list (key, entry) ของบัญชีที่ udid 'ใหม่' (ไม่อยู่ใน before) และ credential ครบ"""
    out = []
    for k, v in creds.items():
        if isinstance(v, dict) and v.get("udid") and v["udid"] not in before_udids:
            ok, _ = validate_credential(v)
            if ok:
                out.append((k, v))
    return out


def wait_for_new_credential(creds_file, before_udids, timeout=240, interval=3.0,
                            clock=time.time, sleep=time.sleep, loader=load_creds):
    """poll creds.json จนเจอบัญชีใหม่ครบ (capture_credential เป็นคนเขียนไฟล์). คืน (key, entry) หรือ None
    clock/sleep/loader inject ได้สำหรับเทสต์"""
    deadline = clock() + timeout
    while clock() < deadline:
        # อ่านอย่างเดียว: addon เขียนลง creds_file ตรง ๆ (ไม่ผ่าน part) -> ไม่ต้อง merge
        # (เดิม auto_merge=True จะไปรวม+ลบ creds.part*.json ของ capture_auto ที่อาจกำลังรันอยู่)
        found = find_new_accounts(before_udids, loader(creds_file))
        if found:
            return found[0]
        sleep(interval)
    return None


# --------------------------------------------------------------------- UI driver (หา ปุ่มจาก text, ไม่ hardcode พิกัด)
_BOUNDS = re.compile(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"')


def find_button(ui_xml, want_texts):
    """หา node แรกที่ text/resource-id/content-desc ตรงกับคำใด ๆ ใน want_texts (case-insensitive)
    คืน (cx, cy) จุดกึ่งกลาง หรือ None. รับ uiautomator dump XML"""
    if not ui_xml:
        return None
    wants = [w.lower() for w in want_texts]
    for node in re.findall(r'<node\b[^>]*/?>', ui_xml):
        hay = node.lower()
        if any(w in hay for w in wants):
            m = _BOUNDS.search(node)
            if m:
                x1, y1, x2, y2 = map(int, m.groups())
                return (x1 + x2) // 2, (y1 + y2) // 2
    return None


def dump_ui(adb, serial):
    """uiautomator dump -> ดึง XML (ใช้หา ปุ่ม Guest/Agree/Confirm โดยไม่พึ่งพิกัดตายตัว)"""
    adb.shell(serial, "uiautomator dump /sdcard/lgr_ui.xml", timeout=15)
    return (adb.shell(serial, "cat /sdcard/lgr_ui.xml", timeout=10).stdout or "")


# --------------------------------------------------------------------- config + orchestrator
class Config:
    def __init__(self, serial=None, dry_run=False, allow_clear=False, max_accounts=1,
                 timeout=300, do_verify=True, creds_file=None):
        self.serial = serial
        self.dry_run = dry_run
        self.allow_clear = allow_clear           # --yes-clear (ยืนยันลบบัญชีบนเครื่องเพื่อ mint ใหม่)
        self.max_accounts = max(1, int(max_accounts))
        self.timeout = int(timeout)
        self.do_verify = do_verify
        self.creds_file = creds_file or os.environ.get("LGR_CREDS_FILE") or CREDS_FILE


class Orchestrator:
    """คุมลำดับงานทั้งหมด. adb inject ได้ -> dry-run/needs-confirm เทสต์ได้โดยไม่แตะ subprocess จริง"""
    def __init__(self, adb, cfg, creds_loader=load_creds):
        self.adb = adb
        self.cfg = cfg
        self._load = creds_loader

    def _plan(self, serial, pf, cur_udid, backed):
        return {
            "serial": serial, "preflight": pf,
            "current_account_loaded": bool(cur_udid),
            "current_backed_up": backed,
            "will_clear": bool(cur_udid) and not backed,   # ต้อง clear เพื่อ mint ใหม่ (ถ้ามีบัญชีค้าง)
        }

    def run(self):
        res = {"status": DEVICE_ERROR, "created": [], "plan": None, "errors": []}
        try:
            serial = select_device(self.adb, self.cfg.serial)
        except AmbiguousDevice as e:
            res["errors"].append(str(e))
            log.error("%s", e)
            return res
        res["serial"] = serial

        pf = preflight(self.adb, serial)
        log.info("[%s] preflight online=%s game=%s root=%s",
                 serial, pf["online"], pf["game_installed"], pf["root"])
        if not pf["online"] or not pf["game_installed"]:
            res["errors"].append("เครื่องไม่ออนไลน์ หรือไม่ได้ติดตั้งเกม")
            return res

        creds = self._load(self.cfg.creds_file)
        before = account_udids(creds)
        cur = current_udid(self.adb, serial)
        backed = is_backed_up(creds, cur)
        plan = self._plan(serial, pf, cur, backed)
        res["plan"] = plan
        log.info("[%s] บัญชีบนเครื่อง=%s backed_up=%s | creds มี %d บัญชี",
                 serial, mask(cur) if cur else "ไม่มี", backed, len(creds))

        # ---- gate ความปลอดภัย: มีบัญชีค้างและยังไม่ backup -> ต้องยืนยันก่อนจะ clear ----
        if plan["will_clear"] and not self.cfg.allow_clear:
            res["status"] = NEEDS_CONFIRM
            res["errors"].append(
                f"บัญชีบนเครื่อง (udid {mask(cur)}) ยังไม่อยู่ใน creds.json พร้อม guestCookie — "
                "การ mint guest ใหม่ต้อง pm clear ซึ่งจะลบบัญชีนี้ถาวร. "
                "สำรองก่อน (เปิดเกมให้ยิง /login ผ่าน capture_credential) แล้วสั่งซ้ำด้วย --yes-clear")
            log.warning("[%s] หยุด: ต้องยืนยัน --yes-clear (บัญชียังไม่ถูก backup)", serial)
            return res

        if self.cfg.dry_run:
            res["status"] = DRY_RUN
            log.info("[%s] DRY-RUN: ไม่แตะ mitm/clear/launch. แผน=%s", serial, plan)
            return res

        # ---- โหมดจริง: start capture -> (clear) -> launch -> drive UI -> poll creds ----
        # หมายเหตุ: ส่วนนี้แตะ subprocess/อีมูเลเตอร์จริง จึงไม่ถูกเรียกในยูนิตเทสต์
        return self._run_live(serial, before, cur, backed, res)

    def _run_live(self, serial, before, cur, backed, res):
        wgp = mitm = None
        stamp = time.strftime("%Y%m%d_%H%M%S")
        env = dict(os.environ, LGR_CREDS_FILE=self.cfg.creds_file,
                   LGR_NEWID_LOG=os.path.join(cap.LOG_DIR, f"autocreate_{stamp}.jsonl"))
        try:
            os.makedirs(cap.LOG_DIR, exist_ok=True)
            # start mitmdump ด้วย addon 2 ตัว: capture_newid (dump) + capture_credential (เขียน creds)
            mitm = subprocess.Popen(
                [cap.find_mitmdump(), "--mode", "reverse:https://rangers-api.line-apps.com",
                 "--listen-port", str(cap.PORT), "--set", "connection_strategy=lazy",
                 "--set", "keep_host_header=true", "--ssl-insecure",
                 "-s", os.path.join(HERE, "capture_newid.py"),
                 "-s", os.path.join(HERE, "capture_credential.py"), "-q"],
                env=env)
            time.sleep(4)
            if not cap.setup(serial):              # เจอ routing ค้าง/ตั้งไม่ครบ -> หยุด (finally ถอนเฉพาะที่ตั้ง)
                res["status"] = DEVICE_ERROR
                res["errors"].append("ตั้ง routing ไม่ครบ หรือมี routing ของสคริปต์อื่นค้างอยู่ — ดู log [routing]")
                return res
            cap.install_ca(serial)

            if self.cfg.allow_clear and cur and not backed:
                log.warning("[%s] pm clear (ยืนยันแล้ว) -> สำรอง prefs ไป logs/prefs_backup_%s", serial, stamp)
                if not cap.backup_and_clear(serial, stamp, confirm=True):
                    res["status"] = DEVICE_ERROR
                    res["errors"].append("สำรอง prefs ไม่สำเร็จ -> ไม่ได้ pm clear")
                    return res

            self.adb.shell(serial, f"monkey -p {PKG} -c android.intent.category.LAUNCHER 1", timeout=20)
            log.info("[%s] เปิดเกมแล้ว — ขับ UI หา Guest/Agree + รอจับ credential (timeout %ds)",
                     serial, self.cfg.timeout)

            self._drive_ui(serial)                 # best-effort; ground-truth คือ poll creds ข้างล่าง
            found = wait_for_new_credential(self.cfg.creds_file, before, timeout=self.cfg.timeout,
                                            loader=self._load)
            if not found:
                res["status"] = NEEDS_MANUAL
                res["errors"].append("ยังไม่เจอบัญชีใหม่ครบ (udid+LF_AC+guestCookie) ในเวลาที่กำหนด — "
                                     "อาจต้องกด Guest/ToS/tutorial เอง หรือเปิด-ปิดเกมให้ยิง /login")
                log.warning("[%s] %s", serial, res["errors"][-1])
                return res

            key, entry = found
            ok, reasons = validate_credential(entry)
            rec = {"key": mask(key), "udid": mask(entry.get("udid")),
                   "LF_AC": mask(entry.get("LF_AC")), "guestCookie": mask(entry.get("guestCookie")),
                   "valid": ok}
            if self.cfg.do_verify and ok:
                rec["verified"] = self._verify(key, entry)
            res["created"].append(rec)
            res["status"] = CREATED if ok else NEEDS_MANUAL
            log.info("[%s] บัญชีใหม่ key=%s valid=%s verified=%s",
                     serial, mask(key), ok, rec.get("verified"))
            return res
        except Exception as e:
            res["status"] = DEVICE_ERROR
            res["errors"].append(f"{type(e).__name__}: {e}")
            log.exception("[%s] ล้มเหลวระหว่างรันจริง", serial)
            return res
        finally:
            try:
                left = cap.teardown(serial)
                if left:
                    res["errors"].append(f"routing ยังค้าง ต้องถอนเอง: {left}")
            except Exception as e:
                res["errors"].append(f"teardown error: {type(e).__name__}: {e}")
            if mitm:
                try:
                    mitm.terminate()
                except Exception:
                    pass
            if wgp:
                try:
                    wgp.terminate()
                except Exception:
                    pass

    def _drive_ui(self, serial, rounds=6):
        """กดปุ่มตามลำดับ onboarding โดยหาจาก text (Guest/Log in/Agree/Confirm/OK)
        ไม่ hardcode พิกัด; ถ้าหาไม่เจอก็ปล่อยให้ผู้ใช้กดเอง (poll creds เป็นตัวตัดสิน)"""
        wants = [["guest"], ["log in", "login", "ยืนยัน", "ตกลง"],
                 ["agree", "ยอมรับ", "accept"], ["confirm", "ok", "ถัดไป", "next"]]
        for _ in range(rounds):
            xml = dump_ui(self.adb, serial)
            tapped = False
            for group in wants:
                pt = find_button(xml, group)
                if pt:
                    self.adb.shell(serial, f"input tap {pt[0]} {pt[1]}", timeout=10)
                    tapped = True
                    time.sleep(2.5)
            if not tapped:
                time.sleep(3)

    def _verify(self, key, entry):
        """ยืนยันบัญชีใหม่แบบ read-only (GET /home) ด้วย account_workflow — คืน bool"""
        try:
            cfg = wf.Config(creds_file=self.cfg.creds_file, verify_only=True, dry_run=True, retry=1)
            r = wf.process_account(key, entry, cfg)
            return bool(r.get("verified"))
        except Exception as e:
            log.debug("verify error %s", e)
            return False


def build_report(res):
    """สรุปผลแบบปกปิดค่า (ไม่โชว์ token/cookie เต็ม)"""
    lines = [f"status = {res['status']}", f"device = {res.get('serial', '-')}"]
    if res.get("plan"):
        p = res["plan"]
        lines.append(f"plan   = online:{p['preflight']['online']} game:{p['preflight']['game_installed']} "
                     f"root:{p['preflight']['root']} will_clear:{p['will_clear']}")
    for c in res.get("created", []):
        lines.append(f"new    = key:{c['key']} udid:{c['udid']} LF_AC:{c['LF_AC']} "
                     f"guestCookie:{c['guestCookie']} valid:{c['valid']} verified:{c.get('verified')}")
    for e in res.get("errors", []):
        lines.append(f"note   = {e}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="สร้าง Guest ใหม่ผ่านเกมจริง + จับ credential (ปลอดภัย)")
    ap.add_argument("--serial", help="เครื่องเป้าหมาย เช่น 127.0.0.1:5563 (ไม่ใส่=ต้องมีเครื่องเดียว)")
    ap.add_argument("--dry-run", action="store_true", help="ตรวจ+วางแผนอย่างเดียว ไม่แตะอีมูฯ")
    ap.add_argument("--yes-clear", action="store_true",
                    help="ยืนยันให้ pm clear บัญชีบนเครื่องเพื่อ mint guest ใหม่ (ลบถาวร!)")
    ap.add_argument("--max", type=int, default=1, help="เพดานจำนวนบัญชีต่อรอบ (ดีฟอลต์ 1)")
    ap.add_argument("--timeout", type=int, default=300, help="วินาทีที่รอจับ credential ใหม่")
    ap.add_argument("--no-verify", action="store_true", help="ไม่ verify บัญชีใหม่ผ่าน API")
    ap.add_argument("--log-level", default="INFO")
    a = ap.parse_args(argv)

    wf.setup_logging(a.log_level)
    cfg = Config(serial=a.serial, dry_run=a.dry_run, allow_clear=a.yes_clear,
                 max_accounts=a.max, timeout=a.timeout, do_verify=not a.no_verify)
    res = Orchestrator(Adb(), cfg).run()
    print(build_report(res))
    return 0 if res["status"] in (CREATED, DRY_RUN) else 2


if __name__ == "__main__":
    sys.exit(main())
