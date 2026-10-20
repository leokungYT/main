#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
account_workflow.py — เวิร์กโฟลว์บัญชี "end-to-end" ที่ยิงผ่าน API ล้วน (headless)
โดยใช้ credential ที่ได้มาจาก flow สร้างบัญชีถูกต้อง (เกม/Trident mint guest -> MITM เก็บลง creds.json)

ขอบเขตที่พิสูจน์แล้ว (จากทราฟฟิกจริงใน logs/newid_*.jsonl):
  * สร้าง guest ID ใหม่ (mint)  -> ❗ ต้องใช้ตัวเกม: ลายเซ็น native ที่ยิงไม่ได้ด้วย Python
        POST game-api.line.me/auth/v3.8/authentication/GUEST  (X-Linegame-Authorization: si=<HMAC จาก libtrident>)
        GET  rangers-api .../v12.3/signup/guest               (X-Guest-Signature / X-Guest-Nonce)
    => ขั้นนี้ทำอัตโนมัติด้วย API ไม่ได้ ต้องให้เกม mint แล้ว capture_newid.py/capture_credential.py เก็บ
       udid+LF_AC(+guestCookie) ลง creds.json (ดู missing dependency ด้านล่าง)
  * ทุกอย่าง "หลังจากมี credential แล้ว" ยิงผ่าน rangers-api ได้ตรง ๆ ด้วย cookie เท่านั้น:
        GET  /login      (ใช้ guestCookie ขอ session ใหม่ เมื่อ LF_AC ตาย)      -> ยืนยัน 200 ในทราฟฟิก
        GET  /home       (ตรวจว่าบัญชีมีจริง + อ่าน rsn/level/ของ)               -> ยืนยัน 200
        POST /push/register                                                      -> ยืนยัน 200
        รับของขวัญ/ภารกิจ ฯลฯ (lgr_api.LGRClient)

ไฟล์นี้ทำ: โหลด creds.json -> ต่อบัญชี: verify (/home, ถ้า 401 ค่อย /login ด้วย guestCookie) ->
           push/register (best-effort) -> เก็บของ (ออปชัน) -> เขียน LF_AC/guestCookie ที่หมุนใหม่กลับ creds.json
           พร้อม logging แบบ structured, retry, แยก config ออกเป็น env, และยืนยันผลจากเซิร์ฟจริง (ไม่ใช่แค่ 200)

ใช้:
  python account_workflow.py                 # ทำทุกบัญชีใน creds.json (verify + activate)
  python account_workflow.py --id a113b3b1   # บัญชีเดียว
  python account_workflow.py --collect       # verify + รับของขวัญ/ภารกิจด้วย
  python account_workflow.py --json out.json # เขียนผลสรุปเป็น JSON
  python account_workflow.py --dry-run       # ไม่เขียน creds.json กลับ (ทดสอบ)

env (แยก config/credential ออกจากโค้ด):
  LGR_CREDS_FILE   ไฟล์ creds (ดีฟอลต์ api/creds.json)        LGR_PROXY      socks5h://... (เน็ตโดนบล็อก)
  LGR_WF_RETRY     จำนวน retry ต่อบัญชี (ดีฟอลต์ 2)            LGR_MIN_GAP    หน่วงต่อคำขอ (วินาที)
  LGR_LOG_LEVEL    DEBUG/INFO/WARNING (ดีฟอลต์ INFO)           LGR_LOG_FILE   เขียน log ลงไฟล์ด้วย
"""
import argparse
import json
import logging
import os
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

from lgr_api import (
    LGRClient,
    load_creds,
    merge_part_creds,
    update_creds,
    parse_ruby,
    parse_coin,
    CREDS_FILE,
    MIN_COOKIE_LEN,
)

log = logging.getLogger("lgr.workflow")


# --------------------------------------------------------------------- config
def _env_int(name, default):
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


class Config:
    """รวม config จาก env ไว้ที่เดียว (credential อยู่ใน creds.json ซึ่งอยู่ใน .gitignore)"""
    def __init__(self, creds_file=None, retry=None, collect=False, dry_run=False,
                 verify_only=False):
        self.creds_file = creds_file or os.environ.get("LGR_CREDS_FILE") or CREDS_FILE
        self.retry = retry if retry is not None else _env_int("LGR_WF_RETRY", 2)
        self.collect = collect
        self.dry_run = dry_run
        # verify_only = ยิงเฉพาะ GET (/home, /login) ไม่ทำ push/register หรือเก็บของ
        # (ทดสอบกับเซิร์ฟจริงแบบ "อ่านอย่างเดียว" ไม่เปลี่ยนสถานะบัญชี)
        self.verify_only = verify_only


def setup_logging(level=None, logfile=None):
    level = (level or os.environ.get("LGR_LOG_LEVEL") or "INFO").upper()
    logfile = logfile or os.environ.get("LGR_LOG_FILE")
    handlers = [logging.StreamHandler(sys.stdout)]
    if logfile:
        handlers.append(logging.FileHandler(logfile, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )


def _mask(secret):
    """อย่าให้ log รั่ว credential: โชว์แค่ 8 ตัวแรก + ความยาว"""
    if not secret:
        return "-"
    return f"{str(secret)[:8]}..(len={len(str(secret))})"


# --------------------------------------------------------------------- workflow
# สถานะผลลัพธ์ต่อบัญชี
OK = "OK"                      # ยืนยันตัวตนจากเซิร์ฟได้ (มี rsn/mid) — บัญชีใช้งานได้
NEEDS_CAPTURE = "NEEDS_CAPTURE"  # credential ตาย (401 + login ไม่ผ่าน) -> ต้องให้เกม login แล้ว re-capture
ERROR = "ERROR"               # ข้อผิดพลาดชั่วคราว/เน็ต (ลอง retry แล้วยังไม่ผ่าน)


def _valid_cookie(v):
    return bool(v) and len(str(v)) >= MIN_COOKIE_LEN


def _verify(client, entry):
    """ยืนยันบัญชี: /home ก่อน ถ้า 401 และมี guestCookie ที่ใช้ได้ -> /login แล้ว /home ใหม่
    คืน (status, home_dict, used_login: bool). ไม่กลืน exception (ให้ชั้นบน retry)"""
    st, home = client.home()
    used_login = False
    # guestCookie ที่เซิร์ฟหมุนมาในรอบก่อน (ถ้ามี) ใช้แทนของเดิมที่อาจถูกยกเลิกแล้ว
    gc = client.guest_cookie_next if _valid_cookie(client.guest_cookie_next) else entry.get("guestCookie")
    if st == 401 and _valid_cookie(gc):
        log.debug("home=401 -> /login ด้วย guestCookie %s", _mask(gc))
        ls, _ = client.login(gc)
        used_login = True
        if ls == 200:
            st, home = client.home()
    return st, home, used_login


def _server_confirmed(home):
    """เช็กว่า 'สำเร็จจริง' ไม่ใช่แค่ HTTP 200: ต้องมี identity จากเซิร์ฟ (rsn หรือ mid)"""
    if not isinstance(home, dict):
        return None
    result = home.get("result", {}) or {}
    player = result.get("player", {}) or {}
    rsn = player.get("rsn") or result.get("rsn")
    # /login คืน identity ที่ระดับ result (id/mid/rsn) ; /home คืนที่ result.player
    mid = player.get("mid") or result.get("mid") or result.get("id")
    if not rsn and not mid:
        return None
    return {
        "rsn": rsn,
        "mid": mid,
        "userName": player.get("userName"),
        "userType": player.get("userType") or result.get("userType"),
        "level": player.get("level") or result.get("level"),
        "ruby": parse_ruby(result, player),
        "coin": parse_coin(result, player),
    }


def _claim_gifts(client):
    """รับของทั้งกล่อง -> จำนวนที่รับได้ (int) หรือ "err:..." ถ้าขั้นใดล้มเหลว
    (ดึงรายการไม่ได้ != กล่องว่าง : ห้ามนับเป็น 0 เงียบ ๆ)"""
    st_b, before = client.unclaimed_gifts()
    if before is None:
        return f"err:giftbox/list HTTP {st_b}"
    if before:
        st_r, _ = client.receive_all_gifts()
        if st_r != 200:
            return f"err:receive/all HTTP {st_r}"
    st_a, after = client.unclaimed_gifts()
    if after is None:
        return f"err:giftbox/list(after) HTTP {st_a}"
    return max(0, len(before) - len(after))


def process_account(acct_id, entry, cfg):
    """ทำเวิร์กโฟลว์ 1 บัญชี -> dict ผลลัพธ์ (ไม่เขียนไฟล์ ให้ชั้นบนรวมแล้วเซฟทีเดียว)
    entry = {udid, LF_AC, guestCookie?, ...} จาก creds.json"""
    res = {"id": acct_id, "status": ERROR, "verified": False, "steps": {},
           "rsn": entry.get("rsn"), "lf_ac_next": entry.get("LF_AC"),
           "guest_cookie_next": entry.get("guestCookie")}

    udid, lf_ac = entry.get("udid"), entry.get("LF_AC")
    if not udid or not lf_ac:
        res["status"] = NEEDS_CAPTURE
        res["error"] = "ไม่มี udid/LF_AC ใน creds — ต้อง capture จากเกมก่อน"
        log.warning("[%s] ข้าม: %s", acct_id, res["error"])
        return res

    last_err = None
    # client ตัวเดียวทุกรอบ: LF_AC ที่เซิร์ฟหมุนให้ในรอบก่อน (client.lf_ac) ถูกใช้ต่อในรอบ retry
    # (เดิมสร้างใหม่จาก LF_AC ตั้งต้นทุกรอบ -> ส่งค่าที่เซิร์ฟยกเลิกไปแล้ว)
    client = LGRClient(udid, lf_ac)
    for attempt in range(cfg.retry + 1):
        try:
            st, home, used_login = _verify(client, entry)
        except Exception as e:                     # เน็ต/proxy สะดุด -> retry
            last_err = f"{type(e).__name__}: {e}"
            res["lf_ac_next"] = client.lf_ac       # อาจหมุนไปแล้วก่อน exception (เช่น /home ผ่าน แต่ /login หลุด)
            log.warning("[%s] พยายามครั้งที่ %d ล้มเหลว (%s)", acct_id, attempt + 1, last_err)
            time.sleep(1.0 * (attempt + 1))
            continue

        res["steps"]["login"] = used_login
        res["steps"]["home_status"] = st
        # เก็บค่าที่เซิร์ฟหมุนใหม่เสมอ (แม้ verify ไม่ผ่าน ก็อาจได้ LF_AC ใหม่)
        res["lf_ac_next"] = client.lf_ac
        if _valid_cookie(client.guest_cookie_next):
            res["guest_cookie_next"] = client.guest_cookie_next

        if st == 401:
            res["status"] = NEEDS_CAPTURE
            res["error"] = "LF_AC ตาย และ /login ด้วย guestCookie ไม่ผ่าน — ต้อง re-capture จากเกม"
            log.warning("[%s] credential ตาย -> ต้อง re-capture", acct_id)
            return res
        if st != 200:
            last_err = f"home HTTP {st}"
            log.warning("[%s] /home ตอบ %s (retry)", acct_id, st)
            time.sleep(1.0 * (attempt + 1))
            continue

        info = _server_confirmed(home)
        if not info:
            last_err = "200 แต่ไม่มี rsn/mid (ไม่ยืนยันตัวตน)"
            log.warning("[%s] %s", acct_id, last_err)
            time.sleep(1.0 * (attempt + 1))
            continue

        # ---- ยืนยันตัวตนสำเร็จจริง ----
        res["status"] = OK
        res["verified"] = True
        res.update({k: info[k] for k in ("rsn", "mid", "userName", "userType", "level", "ruby", "coin")})
        res["rsn"] = info["rsn"] or res["rsn"]
        log.info("[%s] OK rsn=%s type=%s lv=%s ruby=%s coin=%s",
                 acct_id, info["rsn"], info["userType"], info["level"], info["ruby"], info["coin"])

        # ---- verify-only: หยุดที่การยืนยันตัวตน ไม่ยิง POST ใด ๆ (read-only) ----
        if cfg.verify_only:
            res["steps"]["verify_only"] = True
            return res

        # ---- activate: push/register (best-effort, ไม่ gate) ----
        try:
            ps, pd = client.push_register(device_token=entry.get("deviceToken", ""))
            res["steps"]["push_register"] = ps
            ok_push = ps == 200 and isinstance(pd, dict) and pd.get("result") is True
            if not ok_push:
                log.debug("[%s] push/register ไม่ผ่าน (%s) — ข้ามได้", acct_id, ps)
        except Exception as e:
            res["steps"]["push_register"] = f"err:{type(e).__name__}"
            log.debug("[%s] push/register error %s — ข้ามได้", acct_id, e)

        # ---- collect (ออปชัน) ----
        if cfg.collect:
            try:
                res["steps"]["gifts_claimed"] = _claim_gifts(client)
            except Exception as e:
                res["steps"]["gifts_claimed"] = f"err:{type(e).__name__}"
            try:
                res["steps"]["missions"] = client.mission_receive_all()
            except Exception as e:
                res["steps"]["missions"] = f"err:{type(e).__name__}"

        res["lf_ac_next"] = client.lf_ac       # อัปเดตอีกรอบ (call ล่าสุดหมุนค่า)
        if _valid_cookie(client.guest_cookie_next):
            res["guest_cookie_next"] = client.guest_cookie_next
        return res

    res["error"] = last_err or "ล้มเหลวหลัง retry"
    log.error("[%s] ล้มเหลว: %s", acct_id, res["error"])
    return res


def _updates_for(results):
    """ผลลัพธ์ -> {acct_id: {field: value}} เฉพาะค่าที่ควรเขียน (None = ไม่แตะ field นั้น)
    ไม่แตะ udid ; rsn เขียนเฉพาะเมื่อเซิร์ฟยืนยัน ; guestCookie เขียนเฉพาะค่าใหม่ที่ใช้ได้ (ไม่งั้นคงของเดิม)"""
    updates = {}
    for r in results:
        if "lf_ac_next" not in r:                  # บัญชีที่ไม่มีใน creds
            continue
        gc = r.get("guest_cookie_next")
        updates[r["id"]] = {
            "LF_AC": r.get("lf_ac_next") or None,
            "guestCookie": gc if _valid_cookie(gc) else None,
            "rsn": (r.get("rsn") or None) if r.get("verified") else None,
            "level": r.get("level") if r.get("verified") else None,
        }
    return updates


def _persist(creds, results, cfg):
    """merge ค่าที่หมุนใหม่ลง creds.json "ฉบับล่าสุดบนดิสก์" เฉพาะบัญชีที่ทำ (update_creds ถือ lock)
    -> ไม่เขียน snapshot ตอนเริ่มทับบัญชีที่โปรเซสอื่น (capture) เพิ่ง เพิ่ม/แก้
    คืน (จำนวน field ที่เปลี่ยน, error|None)"""
    updates = _updates_for(results)
    pending = sum(1 for aid, f in updates.items() for k, v in f.items()
                  if v is not None and v != (creds.get(aid) or {}).get(k))
    if cfg.dry_run:
        log.info("[dry-run] ไม่เขียน creds.json (%d ค่าที่จะอัปเดต)", pending)
        return pending, None
    if not pending:
        return 0, None
    try:
        changed = update_creds(updates, cfg.creds_file)
    except Exception as e:                         # lock หมดเวลา/ไฟล์พัง -> ไม่เขียน รายงาน error
        log.error("ไม่ได้เขียน creds.json: %s: %s", type(e).__name__, e)
        return 0, f"{type(e).__name__}: {e}"
    log.info("เขียน creds.json กลับ (%d ค่าอัปเดต)", changed)
    return changed, None


def run_workflow(cfg, ids=None):
    """ทำเวิร์กโฟลว์ทุกบัญชี (หรือเฉพาะ ids) -> dict สรุป"""
    if not cfg.dry_run:
        # รวม creds.part*.json เป็นขั้นตอนเขียนที่ชัดเจน — เฉพาะโหมดเขียนจริง (dry-run ไม่แตะไฟล์ใด ๆ)
        try:
            merge_part_creds(creds_path=cfg.creds_file)
        except Exception as e:
            log.error("รวม creds.part*.json ไม่สำเร็จ: %s: %s", type(e).__name__, e)
    creds = load_creds(cfg.creds_file)             # อ่านอย่างเดียว
    if not creds:
        log.error("ไม่พบบัญชีใน %s", cfg.creds_file)
        return {"ok": False, "total": 0, "results": []}

    targets = ids or list(creds.keys())
    log.info("เริ่มเวิร์กโฟลว์ %d บัญชี (collect=%s dry_run=%s)", len(targets), cfg.collect, cfg.dry_run)

    results = []
    for aid in targets:
        entry = creds.get(aid)
        if not isinstance(entry, dict):
            log.warning("[%s] ไม่มีในไฟล์ creds — ข้าม", aid)
            results.append({"id": aid, "status": NEEDS_CAPTURE, "verified": False,
                            "error": "ไม่มีใน creds.json"})
            continue
        results.append(process_account(aid, entry, cfg))

    _, persist_err = _persist(creds, results, cfg)

    summary = {
        "ok": persist_err is None,
        "persist_error": persist_err,
        "total": len(results),
        "verified": sum(1 for r in results if r.get("verified")),
        "needs_capture": sum(1 for r in results if r.get("status") == NEEDS_CAPTURE),
        "error": sum(1 for r in results if r.get("status") == ERROR),
        "results": results,
    }
    log.info("สรุป: ยืนยัน %d/%d | ต้อง re-capture %d | error %d",
             summary["verified"], summary["total"], summary["needs_capture"], summary["error"])
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description="LGR account workflow (verify + activate, API ล้วน)")
    ap.add_argument("--id", action="append", dest="ids",
                    help="ทำเฉพาะบัญชีนี้ (ใส่ซ้ำได้); ไม่ใส่ = ทุกบัญชี")
    ap.add_argument("--collect", action="store_true", help="รับของขวัญ/ภารกิจด้วย")
    ap.add_argument("--verify-only", action="store_true",
                    help="ยิงเฉพาะ GET (/home,/login) ยืนยันตัวตนอย่างเดียว ไม่มี POST — ทดสอบ read-only")
    ap.add_argument("--retry", type=int, default=None, help="จำนวน retry ต่อบัญชี (ดีฟอลต์ env LGR_WF_RETRY/2)")
    ap.add_argument("--dry-run", action="store_true", help="ไม่เขียน creds.json กลับ")
    ap.add_argument("--creds", default=None, help="path ของ creds.json")
    ap.add_argument("--json", dest="json_out", default=None, help="เขียนผลสรุปเป็นไฟล์ JSON")
    ap.add_argument("--log-level", default=None, help="DEBUG/INFO/WARNING")
    a = ap.parse_args(argv)

    setup_logging(a.log_level)
    cfg = Config(creds_file=a.creds, retry=a.retry, collect=a.collect, dry_run=a.dry_run,
                 verify_only=a.verify_only)
    summary = run_workflow(cfg, ids=a.ids)

    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        log.info("เขียนผลสรุป -> %s", a.json_out)

    # exit code: 0 = มีบัญชียืนยันอย่างน้อย 1, 2 = ไม่มีเลย
    return 0 if summary.get("verified") else 2


if __name__ == "__main__":
    sys.exit(main())
