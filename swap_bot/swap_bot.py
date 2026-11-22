import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import ctypes

LOG_FILE = Path("vpn_rotator.log")
FALLBACK_LOCATIONS = ["Brunei", "Cambodia", "Indonesia", "Laos", "Malaysia", "Myanmar", "Philippines", "Singapore", "Thailand", "Vietnam"]
SEARCH_DIRS = [
    r"C:\Program Files (x86)\ExpressVPN\services",
    r"C:\Program Files\ExpressVPN\services",
    r"C:\Program Files (x86)\ExpressVPN",
    r"C:\Program Files\ExpressVPN",
]

def is_admin():
    if os.name != "nt":
        return True
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def ensure_admin():
    if not is_admin():
        params = " ".join([f'"{a}"' for a in sys.argv])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        sys.exit(0)

class VPNRotatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ExpressVPN Rotator (ASEAN)")
        self.root.geometry("600x560")
        self.is_running = False
        self.cli = None
        self.locations = []
        self.protected_ips = []
        self.server_stats = {}  # location -> ping ms (ล่าสุด)
        self._cached_gw = None
        self._cached_if = None

        self.setup_ui()
        self.find_vpn_cli()

    def setup_ui(self):
        # Settings Frame
        frame_top = tk.Frame(self.root, pady=10)
        frame_top.pack(fill=tk.X, padx=10)

        tk.Label(frame_top, text="Interval (วินาที):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.interval_var = tk.IntVar(value=1800)
        tk.Entry(frame_top, textvariable=self.interval_var, width=10).grid(row=0, column=1, sticky=tk.W, pady=2)

        self.shuffle_var = tk.BooleanVar(value=True)
        tk.Checkbutton(frame_top, text="Shuffle (สุ่มเซิร์ฟเวอร์)", variable=self.shuffle_var).grid(row=1, column=0, columnspan=2, sticky=tk.W)

        self.disconnect_var = tk.BooleanVar(value=True)
        tk.Checkbutton(frame_top, text="Disconnect เมื่อกด Stop/ปิดโปรแกรม", variable=self.disconnect_var).grid(row=2, column=0, columnspan=2, sticky=tk.W)

        self.protect_rdp_var = tk.BooleanVar(value=True)
        tk.Checkbutton(frame_top, text="ป้องกัน RDP หลุด (bypass VPN สำหรับ Remote Desktop)", variable=self.protect_rdp_var).grid(row=3, column=0, columnspan=3, sticky=tk.W)

        self.bypass_lan_var = tk.BooleanVar(value=True)
        tk.Checkbutton(frame_top, text="Bypass LAN + Tailscale (ให้ Agent/UI 192.168.x + 100.x เข้าถึงได้)", variable=self.bypass_lan_var).grid(row=6, column=0, columnspan=3, sticky=tk.W)

        self.prefer_low_load_var = tk.BooleanVar(value=True)
        tk.Checkbutton(frame_top, text="เลือกเซิร์ฟเวอร์ที่คนน้อยก่อน (ping ต่ำ = โหลดเบา)", variable=self.prefer_low_load_var).grid(row=4, column=0, columnspan=3, sticky=tk.W)

        tk.Label(frame_top, text="IP เพิ่มเติมที่จะ bypass (คั่นด้วย , ):").grid(row=5, column=0, sticky=tk.W, pady=2)
        self.extra_ips_var = tk.StringVar(value="")
        tk.Entry(frame_top, textvariable=self.extra_ips_var, width=35).grid(row=5, column=1, columnspan=2, sticky=tk.W, pady=2)

        # Buttons Frame
        frame_btn = tk.Frame(self.root, pady=10)
        frame_btn.pack(fill=tk.X, padx=10)

        self.btn_start = tk.Button(frame_btn, text="Start Rotator", width=15, bg="green", fg="white", command=self.start_rotator)
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_stop = tk.Button(frame_btn, text="Stop Rotator", width=15, bg="red", fg="white", state=tk.DISABLED, command=self.stop_rotator)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        # Log Frame
        self.log_area = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, height=15)
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log_area.config(state=tk.DISABLED)

    def log(self, msg):
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{stamp}] {msg}\n"
        
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, line)
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)
        
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    def run_cli(self, args, timeout=60):
        try:
            r = subprocess.run([self.cli, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
            return r.returncode, (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired:
            return -1, "Timeout"
        except Exception as e:
            return -1, str(e)

    def looks_like_cli(self, path):
        if not path or not Path(path).is_file():
            return False
        try:
            r = subprocess.run([path, "-h"], capture_output=True, text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            return r.returncode == 0 and "connect" in r.stdout.lower()
        except:
            return False

    def find_vpn_cli(self):
        self.log("กำลังค้นหา expressvpnctl.exe...")
        for d in SEARCH_DIRS:
            p = Path(d) / "expressvpnctl.exe"
            if self.looks_like_cli(p):
                self.cli = str(p)
                break
        
        if not self.cli:
            p = shutil.which("expressvpnctl.exe")
            if self.looks_like_cli(p):
                self.cli = p
                
        if self.cli:
            self.log(f"พบ ExpressVPN CLI ที่: {self.cli}")
            self.fetch_locations()
            self.log("[AUTO] จะเริ่ม rotator อัตโนมัติใน 3 วินาที...")
            self.root.after(3000, self._auto_start_once)
        else:
            self.log("ไม่พบ expressvpnctl.exe กรุณาตรวจสอบว่าติดตั้ง ExpressVPN v12.69.0+ แล้ว")
            self.btn_start.config(state=tk.DISABLED)

    def _auto_start_once(self):
        if not self.is_running and self.locations:
            self.log("[AUTO] เริ่ม rotator อัตโนมัติ")
            self.start_rotator()

    def fetch_locations(self):
        self.log("กำลังดึงรายชื่อเซิร์ฟเวอร์...")
        rc, out = self.run_cli(["get", "regions"], timeout=60)
        locations = []
        for line in out.splitlines():
            s = line.strip().strip('"').strip()
            if not s or s.lower().startswith(("smart", "region", "----", "available", "to connect", "note")):
                continue
            if len(s) > 2 and s[0].isdigit() and s[1] in ".:":
                s = s[2:].strip().strip('"').strip()
            if s and len(s) > 1:
                locations.append(s)
                
        asean_keywords = ["brunei", "cambodia", "indonesia", "laos", "malaysia", "myanmar", "philippines", "singapore", "thailand", "vietnam"]
        self.locations = [loc for loc in set(locations) if any(kw in loc.lower() for kw in asean_keywords)]
        
        if not self.locations:
            self.locations = FALLBACK_LOCATIONS
            self.log("ดึงข้อมูลไม่สำเร็จ ใช้รายชื่อเซิร์ฟเวอร์สำรอง (Fallback)")
            
        self.log(f"พบ {len(self.locations)} เซิร์ฟเวอร์ใน ASEAN พร้อมทำงาน")

    def get_rdp_client_ips(self):
        """คืน IP ของเครื่องที่ remote เข้ามาที่ port 3389"""
        ips = set()
        try:
            r = subprocess.run(["netstat", "-n"], capture_output=True, text=True,
                               timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in r.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[0].upper() == "TCP" and parts[-1].upper() == "ESTABLISHED":
                    local, remote = parts[1], parts[2]
                    if local.endswith(":3389"):
                        ip = remote.rsplit(":", 1)[0].strip("[]")
                        if ip and ip not in ("0.0.0.0", "127.0.0.1", "::"):
                            ips.add(ip)
        except Exception as e:
            self.log(f"ตรวจหา RDP client ไม่สำเร็จ: {e}")
        return list(ips)

    def get_physical_gateway(self):
        """หา default gateway + interface index ของ NIC จริง (ไม่ใช่ VPN tunnel)"""
        ps = (
            "Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | "
            "Where-Object { $_.InterfaceAlias -notmatch 'ExpressVPN|TAP|Wintun|Lightway|VPN|Tunnel' } | "
            "Sort-Object RouteMetric | Select-Object -First 1 | "
            "ForEach-Object { \"$($_.NextHop)|$($_.InterfaceIndex)\" }"
        )
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            s = r.stdout.strip()
            if "|" in s:
                gw, ifidx = s.split("|", 1)
                gw, ifidx = gw.strip(), ifidx.strip()
                if gw and gw != "0.0.0.0" and ifidx.isdigit():
                    return gw, int(ifidx)
        except Exception as e:
            self.log(f"หา gateway ไม่สำเร็จ: {e}")
        return None, None

    def disable_network_lock(self):
        """ปิด Network Lock / Kill Switch ของ ExpressVPN - สาเหตุหลักที่ RDP หลุดตอนสลับ"""
        candidates = [
            ["preferences", "set", "network_lock", "off"],
            ["preferences", "set", "network-lock", "off"],
            ["preferences", "set", "network_lock", "none"],
            ["preferences", "set", "block_all_traffic", "false"],
            ["options", "set", "network_lock", "off"],
            ["set", "network_lock", "off"],
        ]
        for args in candidates:
            rc, out = self.run_cli(args, timeout=15)
            if rc == 0 and "error" not in out.lower() and "unknown" not in out.lower():
                self.log(f"ปิด Network Lock สำเร็จ: {' '.join(args)}")
                return True
        self.log("[!] ปิด Network Lock ผ่าน CLI ไม่สำเร็จ — กรุณาปิดเองในแอป ExpressVPN:")
        self.log("    Options > General > เอาติ๊กออก 'Block all internet traffic if VPN disconnects unexpectedly'")
        return False

    def add_firewall_allow(self, ip):
        """เพิ่ม Windows Firewall rule อนุญาต RDP จาก IP นี้ (defense in depth)"""
        rule_name = f"VPNRotator_Allow_{ip.replace(':', '_')}"
        try:
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name={rule_name}", "dir=in", "action=allow", "protocol=TCP",
                 "localport=3389", f"remoteip={ip}"],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception:
            pass

    def remove_firewall_allow(self, ip):
        rule_name = f"VPNRotator_Allow_{ip.replace(':', '_')}"
        try:
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception:
            pass

    def _route_exists(self, ip):
        try:
            r = subprocess.run(["route", "print", "-4", ip],
                               capture_output=True, text=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            return ip in r.stdout and "255.255.255.255" in r.stdout
        except Exception:
            return False

    def _add_single_route(self, ip, gw, ifidx):
        # ลบ route เดิมก่อน (ถ้ามี) แล้วค่อยเพิ่มใหม่ เพื่อให้แน่ใจว่า binding ถูก
        subprocess.run(["route", "delete", ip],
                       capture_output=True, text=True, timeout=10,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        cmd = ["route", "add", ip, "mask", "255.255.255.255", gw, "metric", "1"]
        if ifidx:
            cmd += ["IF", str(ifidx)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        out = (r.stdout + r.stderr).strip()
        return r.returncode == 0 and "fail" not in out.lower(), out

    def _add_subnet_route(self, net, mask, gw, ifidx):
        """เพิ่ม route /subnet (ไม่ใช่ /32) - สำหรับ LAN/Tailscale ทั้ง range
        ใช้ -p (persistent) + metric 1 - ExpressVPN ลบไม่ได้ + survive reboot
        ถ้า ExpressVPN พยายามลบ route จะล้มเหลวเพราะ persistent"""
        subprocess.run(["route", "delete", net, "mask", mask],
                       capture_output=True, text=True, timeout=10,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        cmd = ["route", "-p", "add", net, "mask", mask, gw, "metric", "1"]
        if ifidx:
            cmd += ["IF", str(ifidx)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        out = (r.stdout + r.stderr).strip()
        return r.returncode == 0 and "fail" not in out.lower(), out

    def _get_tailscale_iface(self):
        """หา Tailscale interface index + gateway (ตัวมันเอง เพราะ TS เป็น virtual)"""
        ps = (
            "Get-NetAdapter | Where-Object { $_.InterfaceDescription -match 'Tailscale' -and $_.Status -eq 'Up' } | "
            "Select-Object -First 1 | ForEach-Object { "
            "  $ip = (Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1).IPAddress; "
            "  \"$ip|$($_.ifIndex)\" }"
        )
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            s = r.stdout.strip()
            if "|" in s:
                ip, ifidx = s.split("|", 1)
                ip, ifidx = ip.strip(), ifidx.strip()
                if ip and ifidx.isdigit():
                    return ip, int(ifidx)
        except Exception as e:
            self.log(f"หา Tailscale iface ไม่ได้: {e}")
        return None, None

    def _find_agent_server_ips(self):
        """สแกน config.json ของ remote-file agent + hosts ที่ตั้งเอง
        คืน [(ip, hostname)] ที่ต้อง bypass - server ที่ agent เชื่อมอยู่ต้องถึงได้ตลอด
        ไม่งั้นพอ VPN สลับ IP -> agent socketio หลุด -> dashboard เห็น disconnected"""
        import json as _json
        import socket as _socket
        import re as _re
        out_ips = []
        seen = set()
        here = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
        # ที่อยู่ที่น่าจะเจอ agent config.json
        candidates = [
            os.path.join(here, "..", "..", "..", "remote", "remote-file", "config.json"),
            os.path.join(here, "..", "..", "remote", "remote-file", "config.json"),
            os.path.join(os.path.expanduser("~"), "Downloads", "remote", "remote-file", "config.json"),
            os.path.join(os.path.expanduser("~"), "Downloads", "remote-chan", "remote-file", "remote-file", "config.json"),
            os.path.join(os.path.expanduser("~"), "Desktop", "remote-file", "config.json"),
            # ที่ swap_bot จะอ่าน custom เพิ่ม
            os.path.join(here, "bypass_hosts.txt"),
            os.path.join(os.path.dirname(here), "bypass_hosts.txt"),
        ]
        urls = []
        for p in candidates:
            p = os.path.abspath(p)
            if not os.path.isfile(p):
                continue
            try:
                if p.endswith(".txt"):
                    for line in open(p, encoding="utf-8"):
                        s = line.strip()
                        if s and not s.startswith("#"):
                            urls.append(s)
                else:
                    cfg = _json.load(open(p, encoding="utf-8"))
                    for u in (cfg.get("server_urls") or []):
                        urls.append(u)
                    if cfg.get("server_url"):
                        urls.append(cfg["server_url"])
            except Exception as e:
                self.log(f"[AUTO-BYPASS] อ่าน {p} ไม่ได้: {e}")
        # extract host จาก URL แล้ว resolve เป็น IP
        for u in urls:
            host = _re.sub(r"^\w+://", "", u.strip()).split("/")[0].split(":")[0]
            if not host or host in ("localhost", "127.0.0.1", "0.0.0.0"):
                continue
            try:
                ip = _socket.gethostbyname(host)
                key = (ip, host)
                if key not in seen:
                    seen.add(key)
                    out_ips.append(key)
            except Exception:
                pass
        return out_ips

    def add_lan_tailscale_bypass(self):
        """bypass LAN subnets + Tailscale CGNAT + agent server URL - ไม่ให้ ExpressVPN ดูด
        เรียกตอน start + หลังสลับทุกครั้ง (VPN ชอบลบ route ทิ้ง)"""
        if not self._cached_gw:
            gw, ifidx = self.get_physical_gateway()
            if not gw:
                self.log("[LAN-BYPASS] หา gateway จริงไม่เจอ — ข้าม")
                return
            self._cached_gw, self._cached_if = gw, ifidx

        lan = [
            ("192.168.0.0", "255.255.0.0"),   # home LAN
            ("10.0.0.0",    "255.0.0.0"),     # corp/private
            ("172.16.0.0",  "255.240.0.0"),   # Docker/private
        ]
        for net, mask in lan:
            ok, out = self._add_subnet_route(net, mask, self._cached_gw, self._cached_if)
            if ok:
                self.log(f"[LAN-BYPASS] {net}/{mask} -> {self._cached_gw} IF={self._cached_if}")

        ts_ip, ts_if = self._get_tailscale_iface()
        if ts_ip and ts_if:
            ok, out = self._add_subnet_route("100.64.0.0", "255.192.0.0", ts_ip, ts_if)
            if ok:
                self.log(f"[TS-BYPASS] 100.64.0.0/10 -> Tailscale IF={ts_if} ({ts_ip})")
        else:
            self.log("[TS-BYPASS] ไม่พบ Tailscale adapter (ข้าม)")

        # ── bypass agent server URLs (กัน agent หลุดตอนสลับ IP) ──
        for ip, host in self._find_agent_server_ips():
            # LAN/Tailscale ครอบคลุมส่วนใหญ่แล้ว แต่ public IP ของ server ต้อง /32 เพิ่ม
            if ip.startswith(("192.168.", "10.", "100.", "172.1", "172.2", "172.3")):
                continue   # อยู่ใน subnet LAN/TS bypass แล้ว
            ok, out = self._add_single_route(ip, self._cached_gw, self._cached_if)
            if ok:
                self.log(f"[SERVER-BYPASS] {host} ({ip}) -> {self._cached_gw}")

    def remove_lan_tailscale_bypass(self):
        for net, mask in [("192.168.0.0", "255.255.0.0"),
                          ("10.0.0.0", "255.0.0.0"),
                          ("172.16.0.0", "255.240.0.0"),
                          ("100.64.0.0", "255.192.0.0")]:
            try:
                subprocess.run(["route", "delete", net, "mask", mask],
                               capture_output=True, text=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:
                pass

    def add_rdp_bypass_routes(self):
        """เพิ่ม host route /32 + firewall allow rule ให้ RDP client ไม่หลุด"""
        targets = set(self.get_rdp_client_ips())
        extra = (self.extra_ips_var.get() or "").replace(";", ",")
        for ip in extra.split(","):
            ip = ip.strip()
            if ip:
                targets.add(ip)

        if not targets:
            self.log("ไม่พบ RDP client ที่เชื่อมอยู่ (ถ้า remote ผ่าน jump host ให้กรอก IP เองในช่อง IP เพิ่มเติม)")
            return

        gw, ifidx = self.get_physical_gateway()
        if not gw:
            self.log("หา gateway จริงไม่เจอ — ข้ามการเพิ่ม bypass route (ควร disconnect VPN ก่อนเริ่ม)")
            return

        self._cached_gw = gw
        self._cached_if = ifidx
        self.log(f"Default gateway จริง: {gw} (IF={ifidx})")
        for ip in targets:
            ok, out = self._add_single_route(ip, gw, ifidx)
            if ok:
                self.protected_ips.append(ip)
                self.add_firewall_allow(ip)
                self.log(f"Bypass สำเร็จ: {ip} -> {gw} IF={ifidx} + firewall allow")
            else:
                self.log(f"เพิ่ม route {ip} ล้มเหลว: {out[:120]}")

    def ensure_bypass_routes(self):
        """เรียกหลังสลับ VPN ทุกครั้ง — ถ้า route หายให้ยัดกลับ"""
        if not self.protected_ips or not self._cached_gw:
            return
        for ip in self.protected_ips:
            if not self._route_exists(ip):
                ok, out = self._add_single_route(ip, self._cached_gw, self._cached_if)
                if ok:
                    self.log(f"[Re-add] bypass route: {ip} (VPN ลบทิ้ง — ใส่กลับแล้ว)")

    def remove_rdp_bypass_routes(self):
        for ip in list(self.protected_ips):
            try:
                subprocess.run(["route", "delete", ip],
                               capture_output=True, text=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                self.remove_firewall_allow(ip)
                self.log(f"ลบ bypass route: {ip}")
            except Exception:
                pass
        self.protected_ips = []

    def is_connected(self):
        rc, out = self.run_cli(["status"], timeout=30)
        low = out.lower()
        return rc == 0 and "connected" in low and "not connected" not in low

    def measure_latency(self, host="1.1.1.1", count=3):
        """วัด ping ผ่าน VPN เพื่อประมาณโหลดของเซิร์ฟเวอร์"""
        try:
            r = subprocess.run(
                ["ping", "-n", str(count), "-w", "1500", host],
                capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            out = r.stdout + r.stderr
            # Windows EN: "Average = 42ms" / TH: "เฉลี่ย = 42ms" — จับตัวเลข time= ทุกบรรทัดจะชัวร์กว่า
            times = re.findall(r"(?:time|เวลา)[=<]\s*(\d+)\s*ms", out, re.IGNORECASE)
            if times:
                vals = [int(t) for t in times]
                return sum(vals) // len(vals)
            m = re.search(r"(?:Average|เฉลี่ย)\s*=\s*(\d+)\s*ms", out, re.IGNORECASE)
            if m:
                return int(m.group(1))
        except Exception as e:
            self.log(f"วัด ping ไม่สำเร็จ: {e}")
        return None

    def pick_next_location(self, last):
        """เลือก location รอบต่อไป — ให้คะแนนจาก ping ล่าสุด"""
        candidates = [x for x in self.locations if x != last] or list(self.locations)

        if not self.prefer_low_load_var.get() or not self.shuffle_var.get():
            if self.shuffle_var.get():
                return random.choice(candidates)
            return None  # ให้ caller จัดการแบบ round-robin

        # ยังไม่เคยลอง — ให้ได้สำรวจก่อน
        untested = [x for x in candidates if x not in self.server_stats]
        if untested:
            return random.choice(untested)

        # มี stats แล้ว: เรียงตาม ping น้อย -> มาก, เลือกสุ่มจาก top 40%
        ranked = sorted(candidates, key=lambda x: self.server_stats.get(x, 99999))
        top_n = max(1, (len(ranked) * 2) // 5)
        # epsilon 15%: สุ่มจากทั้งหมดบ้าง กันติดในกลุ่มเดิม + เปิดโอกาสวัด ping ใหม่
        if random.random() < 0.15:
            return random.choice(candidates)
        return random.choice(ranked[:top_n])

    def connect_vpn(self, location, retries=2):
        for attempt in range(1, retries + 1):
            if not self.is_running: return False
            self.log(f"กำลังเชื่อมต่อ -> {location} (ครั้งที่ {attempt})")
            rc, out = self.run_cli(["connect", location], timeout=180)
            if rc == 0 and self.is_connected():
                self.log(f"เชื่อมต่อสำเร็จ: {location}")
                # รอ ExpressVPN ปรับ routing table เสร็จ (2s) แล้วค่อย re-add
                # กัน ExpressVPN ลบ LAN/TS bypass routes ทันทีหลังเราเพิ่ม
                time.sleep(2)
                return True
            self.log(f"เชื่อมต่อล้มเหลว: {out.strip()[:100]}...")
            time.sleep(3)
        return False

    def _verify_critical_routes(self):
        """verify Tailscale + LAN route ยังอยู่หลัง VPN connect
        ถ้าโดน ExpressVPN ลบ -> ยัดกลับทันที วนเช็ค 3 รอบ ห่าง 1 วิ
        กัน agent socket หลุดถาวร"""
        if not self.bypass_lan_var.get():
            return
        for i in range(3):
            re_add_needed = False
            # ตรวจ Tailscale route 100.64.0.0/10
            try:
                r = subprocess.run(["route", "print", "-4", "100.64.0.0"],
                                   capture_output=True, text=True, timeout=5,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                if "100.64.0.0" not in r.stdout or "255.192.0.0" not in r.stdout:
                    re_add_needed = True
            except Exception:
                re_add_needed = True
            # ตรวจ LAN route 192.168.0.0/16
            try:
                r = subprocess.run(["route", "print", "-4", "192.168.0.0"],
                                   capture_output=True, text=True, timeout=5,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                if "192.168.0.0" not in r.stdout or "255.255.0.0" not in r.stdout:
                    re_add_needed = True
            except Exception:
                re_add_needed = True

            if not re_add_needed:
                self.log(f"[VERIFY] routes OK (รอบ {i+1}/3)")
                return
            self.log(f"[VERIFY] routes หายไป! re-add (รอบ {i+1}/3)")
            self.add_lan_tailscale_bypass()
            time.sleep(1)

    def _find_trigger_file(self):
        """หา .host_wg_trigger ของ login.py (root ของโปรเจกต์ LGR)
        - exe รันจาก swap_bot/dist/  -> ../../.host_wg_trigger
        - .py รันจาก swap_bot/        -> ../.host_wg_trigger
        - fallback: cwd/.host_wg_trigger"""
        here = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
        for up in (os.path.join(here, "..", "..", ".host_wg_trigger"),
                   os.path.join(here, "..", ".host_wg_trigger"),
                   os.path.join(os.getcwd(), ".host_wg_trigger")):
            p = os.path.abspath(up)
            if os.path.exists(p):
                return p
        return None

    def rotation_loop(self):
        idx = 0
        last = None
        interval = self.interval_var.get()
        trigger_hits = 0

        self.log("="*40)
        self.log(f"เริ่มการทำงาน - สลับทุกๆ {interval} วินาที (+ fast-switch เมื่อเจอ .host_wg_trigger)")

        while self.is_running:
            if self.shuffle_var.get():
                loc = self.pick_next_location(last)
            else:
                loc = self.locations[idx % len(self.locations)]
                idx += 1

            if self.connect_vpn(loc):
                last = loc
                if self.protect_rdp_var.get():
                    self.ensure_bypass_routes()
                if self.bypass_lan_var.get():
                    self.add_lan_tailscale_bypass()
                    self._verify_critical_routes()
                if self.prefer_low_load_var.get():
                    ms = self.measure_latency()
                    if ms is not None:
                        self.server_stats[loc] = ms
                        ranked = sorted(self.server_stats.items(), key=lambda kv: kv[1])[:3]
                        best = ", ".join(f"{n}:{v}ms" for n, v in ranked)
                        self.log(f"Ping {loc} = {ms}ms | Top3 โหลดเบา: {best}")
            else:
                # จำว่า server นี้มีปัญหา โดยใส่ ping สูงไว้ให้เลี่ยง
                self.server_stats[loc] = max(self.server_stats.get(loc, 0), 9999)
                self.log("ข้ามไปเซิร์ฟเวอร์ถัดไป")

            # รอครบ interval หรือเจอ trigger file (จาก login.py: login-failed/fixnet/IP-blocked)
            # - trigger -> ลบไฟล์ -> rotate ทันที (cool-off 180 วิ กัน agent socket หลุดถี่)
            # เดิม 30s แต่ agents ต้องการเวลา reconnect ~60-90s หลัง VPN swap
            # ถ้า rotate ถี่กว่า reconnect window -> agents หลุดถาวร
            MIN_COOLOFF = 180
            waited = 0
            trigger_fired = False
            while waited < interval and self.is_running:
                tf = self._find_trigger_file()
                if tf and waited >= MIN_COOLOFF:
                    try:
                        reason = open(tf, encoding="utf-8").read().strip()[:80]
                    except Exception:
                        reason = "?"
                    try:
                        os.remove(tf)
                    except Exception:
                        pass
                    trigger_hits += 1
                    self.log(f"[TRIGGER #{trigger_hits}] login.py ขอสลับ IP: {reason} (รอไปแล้ว {waited}s/{interval}s) -> สลับทันที")
                    trigger_fired = True
                    break
                time.sleep(1)
                waited += 1
            if trigger_fired:
                continue   # ข้าม `for _ in range(interval)` ไปเริ่มรอบใหม่
                
        if self.disconnect_var.get():
            self.log("กำลังยกเลิกการเชื่อมต่อ VPN...")
            self.run_cli(["disconnect"])
        self.remove_rdp_bypass_routes()
        self.remove_lan_tailscale_bypass()
        self.log("หยุดการทำงานเรียบร้อย")
        
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

    def start_rotator(self):
        self.interval_var.get() # ตรวจสอบค่าตัวเลข
        self.is_running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)

        if self.protect_rdp_var.get():
            # ถ้า VPN เชื่อมต่ออยู่ ให้ disconnect ก่อน เพื่อให้หา gateway จริงได้ถูกต้อง
            if self.is_connected():
                self.log("VPN กำลังเชื่อมต่ออยู่ — disconnect ก่อนเพื่อหา gateway จริง")
                self.run_cli(["disconnect"], timeout=30)
                time.sleep(2)
            # ปิด Network Lock ก่อน (ถ้าเปิดไว้จะบล็อก RDP ตอนสลับ)
            self.disable_network_lock()
            self.add_rdp_bypass_routes()

        if self.bypass_lan_var.get():
            if not self._cached_gw:
                gw, ifidx = self.get_physical_gateway()
                self._cached_gw, self._cached_if = gw, ifidx
            self.add_lan_tailscale_bypass()

        threading.Thread(target=self.rotation_loop, daemon=True).start()

    def stop_rotator(self):
        self.is_running = False
        self.log("กำลังรอให้รอบปัจจุบันหยุดทำงาน...")
        self.btn_stop.config(state=tk.DISABLED)

def main():
    ensure_admin()
    root = tk.Tk()
    app = VPNRotatorApp(root)
    def on_close():
        app.is_running = False
        try:
            app.remove_rdp_bypass_routes()
        except Exception:
            pass
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

if __name__ == "__main__":
    main()