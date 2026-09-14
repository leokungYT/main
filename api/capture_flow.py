#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capture_flow.py — mitmproxy addon: log ทราฟฟิก rangers-api "ทั้งหมด" ลงไฟล์
ใช้แกะ flow ที่ยังไม่รู้ (เช่น tutorial gacha: reserve/confirm/adPlay, ตัวที่ได้อยู่ field ไหน)

วิธีใช้ (แทน capture_credential.py ตอนอยากเห็น flow เต็ม):
  mitmdump --mode reverse:https://rangers-api.line-apps.com --listen-port 8443 -s capture_flow.py -q
  (routing เหมือนเดิม: adb reverse + hosts + iptables — หรือใช้ capture_auto.py ตั้งให้)

  แล้วเข้าเกมทำ tutorial + สุ่มกาชา 1 รอบ
  -> ได้ logs/flows-<ts>.jsonl : 1 บรรทัด = 1 request/response
     ฟิลด์: ts, method, path, status, req_body, resp_body (ตัด binary/ยาวเกินให้สั้น)

อ่านเฉพาะ gacha:  grep gacha logs/flows-*.jsonl
"""
import json
import os
import time
from mitmproxy import http

LOGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOGDIR, exist_ok=True)
LOGFILE = os.path.join(LOGDIR, f"flows-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")

# path ที่อยากเห็น body เต็ม (ไม่ตัด) — พวก gacha/tutorial/home/unit
FULL = ("gacha", "tutorial", "home", "unit", "stage", "reward", "login")
MAXLEN = 20000   # ตัด body ที่ยาวเกินนี้ (กันไฟล์บวม)


def _txt(msg):
    try:
        t = msg.get_text(strict=False) or ""
    except Exception:
        return "<binary>"
    return t


def _clip(path, body):
    if any(k in path for k in FULL):
        return body[:MAXLEN * 4]      # gacha ฯลฯ เก็บยาวหน่อย
    return body[:MAXLEN]


def response(flow: http.HTTPFlow):
    r, resp = flow.request, flow.response
    if "rangers-api" not in r.pretty_host:
        return
    path = r.path.split("?")[0]
    rec = {
        "ts": int(time.time() * 1000),
        "method": r.method,
        "path": path,
        "query": r.path.split("?", 1)[1] if "?" in r.path else "",
        "status": resp.status_code,
        "req_body": _clip(path, _txt(r)),
        "resp_body": _clip(path, _txt(resp)),
    }
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tag = " <-- GACHA" if "gacha" in path else ""
    print(f"[flow] {r.method:4} {path} -> {resp.status_code}{tag}", flush=True)
