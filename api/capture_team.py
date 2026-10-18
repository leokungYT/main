#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Show sanitized Rangers API calls and unit codes while inspecting My Team."""
import json
import argparse
import shutil
import subprocess
import sys
import os
from mitmproxy import http


def _unit_codes(value):
    codes = set()

    def visit(node):
        if isinstance(node, dict):
            for key, item in node.items():
                if key in {"unitCode", "dataCode"} and isinstance(item, str):
                    codes.add(item)
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(value)
    return sorted(codes)


def _amount(value):
    if isinstance(value, dict):
        value = value.get("total", value.get("free", 0))
    return int(value) if isinstance(value, (int, float)) else None


def _ruby_ticket_values(body):
    result = body.get("result", {}) if isinstance(body, dict) else {}
    if not isinstance(result, dict):
        return None, {}

    player = result.get("player", {}) or {}
    ruby = None
    for value in (result.get("ruby"), result.get("rubyBalance"),
                  player.get("ruby") if isinstance(player, dict) else None,
                  player.get("gem") if isinstance(player, dict) else None):
        ruby = _amount(value)
        if ruby is not None:
            break

    ticket_fields = {
        "premium": "premiumGachaTicketItems",
        "classic": "classicGachaTicketItems",
        "event": "eventGachaTicketItems",
    }
    tickets = {}
    for label, key in ticket_fields.items():
        if key in result:
            items = result.get(key) or []
            if isinstance(items, list):
                tickets[label] = sum(
                    int(item.get("amount") or item.get("freeAmount") or 0)
                    for item in items if isinstance(item, dict)
                )
    return ruby, tickets


# ส่งต่อขาออกผ่าน WG tunnel ของ wireproxy (IP เครื่องโดนบล็อก 403) — SNI/Host ยังเป็น rangers-api
WG_TUNNEL = os.environ.get("LGR_WG_TUNNEL", "").strip()     # เช่น 127.0.0.1:9443 (ว่าง = ต่อตรง)


def server_connect(data):
    if WG_TUNNEL:
        host, port = WG_TUNNEL.rsplit(":", 1)
        data.server.address = (host, int(port))


def response(flow: http.HTTPFlow):
    request, response = flow.request, flow.response
    # ผ่าน WG tunnel host จะกลายเป็น 127.0.0.1:9443 -> ดูจาก path /v12.x แทน
    if "rangers-api" not in request.pretty_host and not request.path.startswith("/v1"):
        return

    path = request.path.split("?", 1)[0]

    codes = []
    body = {}
    try:
        body = json.loads(response.get_text(strict=False) or "")
        codes = _unit_codes(body)
    except (ValueError, TypeError):
        pass

    print(f"[api] {request.method} {path} -> {response.status_code}"
          + (f"  ({len(codes)} unitCode)" if codes else ""), flush=True)
    ruby, tickets = _ruby_ticket_values(body)
    if ruby is not None or tickets:
        ticket_text = ", ".join(f"{kind}={count}" for kind, count in tickets.items())
        resource_text = f"ruby={ruby}" if ruby is not None else "ruby=n/a"
        if ticket_text:
            resource_text += f" tickets[{ticket_text}]"
        print(f"[ruby-ticket] {resource_text}", flush=True)
    if codes:
        shown = codes if len(codes) <= 12 else codes[:12] + [f"...(+{len(codes) - 12})"]
        print(f"[unit-codes] {', '.join(shown)}", flush=True)


def install_ca(serial):
    """ติด CA ของ mitmproxy เป็น system cert ชั่วคราว (bind-mount ทับ cacerts) ให้ client ที่ตรวจ cert ยอมผ่าน"""
    from capture_run import adb
    pem = os.path.join(os.path.expanduser("~"), ".mitmproxy", "mitmproxy-ca-cert.pem")
    if not os.path.exists(pem):
        print("[ca] ไม่พบ mitmproxy-ca-cert.pem (รัน mitmdump สักครั้งก่อน)")
        return
    name = "c8750f0d.0"   # subject_hash_old ของ CA mitmproxy ในเครื่องนี้
    adb(serial, "push", pem, "/data/local/tmp/" + name)
    # ต้องครอบทั้งก้อนด้วย '...' — adb ต่อ args เป็นสตริงเดียว ไม่งั้นหลัง ; จะไม่ได้รันเป็น su
    adb(serial, "shell",
        "su -c 'mkdir -p /data/local/tmp/cacerts && cp /system/etc/security/cacerts/* /data/local/tmp/cacerts/ && "
        f"cp /data/local/tmp/{name} /data/local/tmp/cacerts/ && chmod 644 /data/local/tmp/cacerts/* && "
        "mount --bind /data/local/tmp/cacerts /system/etc/security/cacerts'")
    print("[ca] ติด CA mitmproxy ในอีมูแล้ว (ชั่วคราว) — ปิด/เปิดเกมใหม่ให้มีผล")


def remove_ca(serial):
    from capture_run import adb
    # ถอดให้หมดทุกชั้น — CA ค้างในเครื่อง = LIAPP ของเกมปิดเกมทิ้ง (capture_auto/บอทเข้าเกมไม่ได้)
    adb(serial, "shell",
        "su -c 'while mount | grep -q \" /system/etc/security/cacerts \"; do "
        "umount /system/etc/security/cacerts || break; done'")
    print("[ca] ถอด CA คืนแล้ว")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture LINE Rangers Ruby and ticket API responses.")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=8443)
    parser.add_argument("--serial", default="127.0.0.1:7555", help="adb serial ของอีมูที่เปิดเกม")
    parser.add_argument("--wg", default="127.0.0.1:9443",
                        help="TCP tunnel ของ wireproxy (wg-proxy.bat) ; ใส่ '' = ต่อตรง")
    options = parser.parse_args()

    mitmdump = shutil.which("mitmdump")
    if not mitmdump:
        parser.error("mitmdump was not found on PATH; install mitmproxy or run this through its environment")

    command = [
        mitmdump,
        "--mode", "reverse:https://rangers-api.line-apps.com",
        "--listen-host", options.listen_host,
        "--listen-port", str(options.listen_port),
        "-s", os.path.abspath(__file__),
    ]
    # ตั้ง routing ในอีมู (hosts+iptables+adb reverse) ให้เกมวิ่งเข้า mitm แล้วถอดคืนตอนจบ
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from capture_run import setup, teardown
    env = dict(os.environ, LGR_WG_TUNNEL=options.wg)
    setup(options.serial)
    install_ca(options.serial)
    print(f"[*] เปิดเกม -> MY TEAM แล้วเลื่อนรายการตัวละคร ; Ctrl+C เพื่อจบ (ขาออกผ่าน {options.wg or 'ตรง'})", flush=True)
    try:
        code = subprocess.call(command, env=env)
    except KeyboardInterrupt:
        code = 0
    finally:
        teardown(options.serial)
        remove_ca(options.serial)
    raise SystemExit(code)