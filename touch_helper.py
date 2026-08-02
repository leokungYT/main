"""
Shared input + template-position helpers for the LGR bots
(login.py / ranger-gear.py / rangerplus.py).

Two independent features, both switchable from ranger-gear_config.json:

  "minitouch": 1
      Route tap()/swipe() through one persistent minitouch socket instead of
      spawning `adb shell input tap` for every click. Spawning adb on Windows
      costs ~80-200ms per tap; minitouch is a few hundred microseconds.
      Needs the minitouch binary in bin/minitouch/<abi>/ - see the README
      there. If anything is missing or fails, the bot silently falls back to
      plain ADB, so turning this on can never break a run.

  "pos_cache": 1
      Remember where each template last matched. On the next lookup only a
      small ROI around that spot is re-checked instead of scanning the whole
      screen (a ~40x40px window vs 1600x900 - roughly two orders of magnitude
      less work). If the ROI misses, the cached spot is dropped and a normal
      full-screen scan runs, so a moved/absent button is still found.
      "pos_cache_margin" controls how many px of slack the ROI allows.

Both features are per-device: each bot instance owns its own PositionMemory
and its own minitouch connection.
"""

import atexit
import os
import socket
import subprocess
import threading
import time

import cv2
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MINITOUCH_DIR = os.path.join(SCRIPT_DIR, "bin", "minitouch")
DEVICE_BIN_PATH = "/data/local/tmp/minitouch"

# abi -> other abis whose binary will also run on it
ABI_FALLBACKS = {
    "arm64-v8a": ["arm64-v8a", "armeabi-v7a", "armeabi"],
    "armeabi-v7a": ["armeabi-v7a", "armeabi"],
    "armeabi": ["armeabi"],
    "x86_64": ["x86_64", "x86"],
    "x86": ["x86"],
}

_NO_WINDOW = {}
if os.name == "nt":
    _NO_WINDOW["creationflags"] = subprocess.CREATE_NO_WINDOW


# =============================================================
# Position memory - "find the button once, remember where it was"
# =============================================================
class PositionMemory:
    """Caches the last match position of every template, per bot instance."""

    def __init__(self, enabled=True, margin=12, label=""):
        self.enabled = bool(enabled)
        self.margin = int(margin)
        self.label = label
        self._cache = {}   # template key -> (top_left_x, top_left_y)
        self.hits = 0      # matched from the remembered ROI
        self.misses = 0    # had to scan the whole screen

    def find(self, screen, tmpl, key, similarity):
        """Return (center_x, center_y) of the match, or None.

        Tries the remembered ROI first, then falls back to a full scan.
        """
        if screen is None or tmpl is None:
            return None
        th, tw = tmpl.shape[:2]
        sh, sw = screen.shape[:2]
        if th > sh or tw > sw:
            return None

        if self.enabled:
            spot = self._cache.get(key)
            if spot is not None:
                found = self._match_roi(screen, tmpl, spot, key, similarity, tw, th, sw, sh)
                if found is not None:
                    self.hits += 1
                    return found
                # Button moved or is gone - drop the stale spot and rescan.
                self._cache.pop(key, None)

        self.misses += 1
        return self._match_full(screen, tmpl, key, similarity, tw, th)

    def _match_roi(self, screen, tmpl, spot, key, similarity, tw, th, sw, sh):
        try:
            cx, cy = spot
            m = self.margin
            x0, y0 = max(0, cx - m), max(0, cy - m)
            x1, y1 = min(sw, cx + tw + m), min(sh, cy + th + m)
            roi = screen[y0:y1, x0:x1]
            if roi.shape[0] < th or roi.shape[1] < tw:
                return None
            result = cv2.matchTemplate(roi, tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val >= similarity:
                gx, gy = x0 + max_loc[0], y0 + max_loc[1]
                # Re-anchor so slow drift keeps being tracked by the ROI.
                self._cache[key] = (gx, gy)
                return (gx + tw // 2, gy + th // 2)
        except Exception:
            pass
        return None

    def _match_full(self, screen, tmpl, key, similarity, tw, th):
        try:
            result = cv2.matchTemplate(screen, tmpl, cv2.TM_CCOEFF_NORMED)
            loc = np.where(result >= similarity)
            if len(loc[0]) > 0:
                y, x = int(loc[0][0]), int(loc[1][0])
                if self.enabled:
                    self._cache[key] = (x, y)
                return (x + tw // 2, y + th // 2)
        except Exception:
            pass
        return None

    def forget(self, key=None):
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)

    def summary(self):
        total = self.hits + self.misses
        if total == 0:
            return "pos-cache: no lookups yet"
        pct = self.hits * 100.0 / total
        return f"pos-cache: {self.hits}/{total} hits ({pct:.1f}%), {len(self._cache)} remembered"


# =============================================================
# Minitouch
# =============================================================
class MinitouchController:
    """Persistent minitouch connection for one device.

    `ok` stays False whenever minitouch is unusable; callers should then use
    their normal ADB path. Every public method returns False on failure so a
    caller can retry over ADB.
    """

    def __init__(self, adb_cmd, device_id, log=print):
        self.adb_cmd = adb_cmd
        self.device_id = device_id
        self.log = log
        self.ok = False
        self.reason = "not started"
        self.sock = None
        self.proc = None
        self.port = None
        self.max_x = 0
        self.max_y = 0
        self.max_contacts = 2
        self.pressure = 50
        self.screen_w = 0
        self.screen_h = 0
        self._lock = threading.Lock()
        self._closed = False
        atexit.register(self.close)

    # ---------- setup ----------
    def _adb(self, args, timeout=15):
        return subprocess.run(
            [self.adb_cmd, "-s", self.device_id] + args,
            capture_output=True, timeout=timeout, **_NO_WINDOW
        )

    def _detect_abi(self):
        res = self._adb(["shell", "getprop", "ro.product.cpu.abi"])
        return res.stdout.decode("utf-8", "ignore").strip()

    def _local_binary(self, abi):
        for candidate_abi in ABI_FALLBACKS.get(abi, [abi]):
            path = os.path.join(MINITOUCH_DIR, candidate_abi, "minitouch")
            if os.path.exists(path):
                return path
            if os.path.exists(path + ".so"):
                return path + ".so"
        return None

    def _detect_screen_size(self):
        try:
            res = self._adb(["shell", "wm", "size"])
            text = res.stdout.decode("utf-8", "ignore")
            # "Physical size: 900x1600" (an Override line wins when present)
            size = None
            for line in text.splitlines():
                if "size:" in line and "x" in line:
                    size = line.split("size:")[-1].strip()
            if size:
                w, h = size.lower().split("x")
                return int(w), int(h)
        except Exception:
            pass
        return 0, 0

    @staticmethod
    def _free_port():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def start(self):
        """Bring minitouch up. Returns True when taps can be sent."""
        if self.ok:
            return True
        try:
            abi = self._detect_abi()
            if not abi:
                return self._fail("cannot read device ABI")

            local_bin = self._local_binary(abi)
            if not local_bin:
                return self._fail(
                    f"no binary for abi '{abi}' - put it at "
                    f"bin/minitouch/{abi}/minitouch (see bin/minitouch/README.md)"
                )

            push = self._adb(["push", local_bin, DEVICE_BIN_PATH], timeout=30)
            if push.returncode != 0:
                return self._fail("push failed: " +
                                  push.stderr.decode("utf-8", "ignore").strip())
            self._adb(["shell", "chmod", "755", DEVICE_BIN_PATH])

            sock_name = "minitouch_" + self.device_id.replace(":", "_").replace(".", "_")
            self.port = self._free_port()

            fwd = self._adb(["forward", f"tcp:{self.port}", f"localabstract:{sock_name}"])
            if fwd.returncode != 0:
                return self._fail("adb forward failed: " +
                                  fwd.stderr.decode("utf-8", "ignore").strip())

            self.proc = subprocess.Popen(
                [self.adb_cmd, "-s", self.device_id, "shell",
                 f"{DEVICE_BIN_PATH} -n {sock_name}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                **_NO_WINDOW
            )

            if not self._connect():
                return False

            self.screen_w, self.screen_h = self._detect_screen_size()
            self.ok = True
            self.reason = "ready"
            self.log(f"[{self.device_id}] minitouch ready "
                     f"(abi={abi}, max={self.max_x}x{self.max_y}, "
                     f"screen={self.screen_w}x{self.screen_h}, port={self.port})")
            return True
        except Exception as e:
            return self._fail(f"{type(e).__name__}: {e}")

    def _connect(self):
        """Connect to the forwarded port and parse the minitouch banner."""
        deadline = time.time() + 5
        last_err = "timeout"
        while time.time() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                err = self.proc.stderr.read().decode("utf-8", "ignore").strip()
                return self._fail("minitouch exited on device: " + (err or "no output"))
            try:
                sock = socket.create_connection(("127.0.0.1", self.port), timeout=2)
                sock.settimeout(2)
                banner = b""
                while banner.count(b"\n") < 3:
                    chunk = sock.recv(256)
                    if not chunk:
                        break
                    banner += chunk
                if self._parse_banner(banner.decode("utf-8", "ignore")):
                    sock.settimeout(3)
                    self.sock = sock
                    return True
                sock.close()
                last_err = "unexpected banner: " + banner.decode("utf-8", "ignore").strip()
            except OSError as e:
                last_err = str(e)
                time.sleep(0.15)
        return self._fail("connect failed: " + last_err)

    def _parse_banner(self, banner):
        # v <version> / ^ <max_contacts> <max_x> <max_y> <max_pressure> / $ <pid>
        for line in banner.splitlines():
            if line.startswith("^"):
                parts = line.split()
                if len(parts) >= 5:
                    self.max_contacts = int(parts[1])
                    self.max_x = int(parts[2])
                    self.max_y = int(parts[3])
                    self.pressure = min(50, int(parts[4])) or 50
                    return self.max_x > 0 and self.max_y > 0
        return False

    def _fail(self, reason):
        self.ok = False
        self.reason = reason
        self.log(f"[{self.device_id}] minitouch unavailable ({reason}) - using ADB taps")
        self._teardown()
        return False

    # ---------- geometry ----------
    def update_screen_size(self, width, height):
        """Bots call this with their screenshot size - that is the coordinate
        space every tap in the codebase is written in."""
        if width and height and (width, height) != (self.screen_w, self.screen_h):
            self.screen_w, self.screen_h = int(width), int(height)

    def _scale(self, x, y):
        """Screenshot pixel -> minitouch coordinate.

        Divide by the full width/height (not width-1) so that a touch panel
        reporting the same range as the display maps 1:1 - which is the case on
        most emulators. Same mapping STF/airtest use.
        """
        w = self.screen_w or self.max_x
        h = self.screen_h or self.max_y
        mx = int(round(x * self.max_x / float(max(1, w))))
        my = int(round(y * self.max_y / float(max(1, h))))
        return (max(0, min(self.max_x, mx)), max(0, min(self.max_y, my)))

    # ---------- input ----------
    def _send(self, payload):
        with self._lock:
            if not self.ok or self.sock is None:
                return False
            if self.proc is not None and self.proc.poll() is not None:
                self._fail("minitouch process died")
                return False
            try:
                self.sock.sendall(payload.encode("ascii"))
                return True
            except OSError as e:
                self._fail(f"send failed: {e}")
                return False

    def tap(self, x, y, hold_ms=40):
        if not self.ok:
            return False
        mx, my = self._scale(x, y)
        return self._send(
            f"d 0 {mx} {my} {self.pressure}\nc\nw {int(hold_ms)}\nu 0\nc\n"
        )

    def swipe(self, x1, y1, x2, y2, duration_ms=300, steps=16):
        if not self.ok:
            return False
        steps = max(2, int(steps))
        sx, sy = self._scale(x1, y1)
        parts = [f"d 0 {sx} {sy} {self.pressure}\nc\n"]
        step_ms = max(1, int(duration_ms / steps))
        for i in range(1, steps + 1):
            t = i / float(steps)
            mx, my = self._scale(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
            parts.append(f"m 0 {mx} {my} {self.pressure}\nc\nw {step_ms}\n")
        parts.append("u 0\nc\n")
        return self._send("".join(parts))

    # ---------- teardown ----------
    def _teardown(self):
        try:
            if self.sock is not None:
                self.sock.close()
        except Exception:
            pass
        self.sock = None
        try:
            if self.proc is not None and self.proc.poll() is None:
                self.proc.kill()
        except Exception:
            pass
        self.proc = None
        try:
            if self.port:
                self._adb(["forward", "--remove", f"tcp:{self.port}"], timeout=5)
        except Exception:
            pass
        self.port = None

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.ok = False
        self._teardown()


def make_minitouch(adb_cmd, device_id, log=print):
    """Build and start a controller; returns it only if taps actually work."""
    ctrl = MinitouchController(adb_cmd, device_id, log=log)
    if ctrl.start():
        return ctrl
    ctrl.close()
    return None
