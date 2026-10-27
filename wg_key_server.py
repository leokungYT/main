# รันบนเครื่องหลัก (ที่มี wg_accounts/<บัญชี>/key.conf) - แจกกุญแจ Windscribe ให้เครื่องบอตผ่าน Tailscale
# ตอบเฉพาะ IP วง Tailscale (100.64.0.0/10) เท่านั้น ; เครื่องบอตดึงอัตโนมัติตอนเริ่ม (login.py _fetch_wg_key)
# ใช้: python wg_key_server.py [บัญชี] [พอร์ต]
import http.server
import ipaddress
import os
import sys

ACCOUNT = sys.argv[1] if len(sys.argv) > 1 else "account1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
KEY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wg_accounts", ACCOUNT, "key.conf")
TAILNET = ipaddress.ip_network("100.64.0.0/10")


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if ipaddress.ip_address(self.client_address[0]) not in TAILNET or self.path != "/key.conf":
            self.send_error(403)
            return
        with open(KEY, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        print(f"[WG-KEY] ส่งกุญแจให้ {self.client_address[0]}")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    if not os.path.exists(KEY):
        sys.exit(f"ไม่มี {KEY}")
    print(f"[WG-KEY] แจกกุญแจ {KEY} ที่พอร์ต {PORT} (เฉพาะวง Tailscale)")
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
