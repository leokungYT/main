import os
import sys
import re
import lzma
import shutil
import subprocess
import urllib.request
import time

FRIDA_VERSION = "16.7.19"
RELEASE_BASE = f"https://github.com/frida/frida/releases/download/{FRIDA_VERSION}"

ABI_TO_ARCH = {
    "arm64-v8a":   "arm64",
    "armeabi-v7a": "arm",
    "x86_64":      "x86_64",
    "x86":         "x86",
}


SERIAL = None  # set in main() after device pick


def adb(args, capture=True, check=False, timeout=None):
    cmd = ["adb"]
    if SERIAL:
        cmd += ["-s", SERIAL]
    cmd += args
    print(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout)
    if r.stdout:
        for line in r.stdout.rstrip().splitlines():
            print(f"    {line}")
    if r.stderr and r.returncode != 0:
        for line in r.stderr.rstrip().splitlines():
            print(f"    [err] {line}")
    if check and r.returncode != 0:
        print(f"[!] command failed (rc={r.returncode})")
        sys.exit(r.returncode)
    return r


def ensure_adb():
    r = subprocess.run(["adb", "version"], capture_output=True, text=True)
    if r.returncode != 0:
        print("[!] adb not in PATH")
        sys.exit(1)


def list_devices():
    r = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    devs = []
    for line in (r.stdout or "").splitlines()[1:]:
        line = line.strip()
        if not line or "offline" in line or "unauthorized" in line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devs.append(parts[0])
    return devs


def pick_serial():
    forced = os.environ.get("ADB_SERIAL", "").strip()
    devs = list_devices()
    if not devs:
        print("[!] no device connected")
        print("    try: adb connect 127.0.0.1:7555")
        sys.exit(1)
    if forced:
        if forced in devs:
            return forced
        print(f"[!] ADB_SERIAL={forced} not in connected devices: {devs}")
        sys.exit(1)
    if len(devs) == 1:
        return devs[0]
    # prefer MuMu 127.0.0.1:7555 / :16384, else first emulator-*
    for pref in ("127.0.0.1:7555", "127.0.0.1:16384", "127.0.0.1:5555"):
        if pref in devs:
            return pref
    for d in devs:
        if d.startswith("emulator-"):
            return d
    return devs[0]


def get_abi():
    r = adb(["shell", "getprop", "ro.product.cpu.abi"])
    abi = (r.stdout or "").strip()
    abi = re.sub(r"\s+", "", abi)
    if abi not in ABI_TO_ARCH:
        print(f"[!] unknown abi: {abi!r}")
        sys.exit(1)
    return abi, ABI_TO_ARCH[abi]


def shell_su(remote_cmd, capture=True, timeout=None, background=False):
    """
    Run a shell command as root on device.
    adb shell does not re-quote args, so we pass everything as ONE string.
    """
    wrapped = f"su -c '{remote_cmd}'"
    cmd = ["adb"]
    if SERIAL:
        cmd += ["-s", SERIAL]
    cmd += ["shell", wrapped]
    print(f"$ {' '.join(cmd)}")
    if background:
        return subprocess.Popen(cmd)
    return subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout)


def check_root():
    r = shell_su("id", timeout=10)
    out = (r.stdout or "") + (r.stderr or "")
    for line in (r.stdout or "").rstrip().splitlines():
        print(f"    {line}")
    return "uid=0" in out


def download(url, dst):
    print(f"[*] GET {url}")
    with urllib.request.urlopen(url) as resp, open(dst, "wb") as fo:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        chunk = 1 << 15
        while True:
            buf = resp.read(chunk)
            if not buf:
                break
            fo.write(buf)
            got += len(buf)
            if total:
                pct = got * 100 // total
                print(f"\r    {got}/{total}  {pct}%", end="")
        print()


def unxz(src, dst):
    print(f"[*] xz decompress {src} -> {dst}")
    with lzma.open(src, "rb") as fi, open(dst, "wb") as fo:
        shutil.copyfileobj(fi, fo)


def kill_existing():
    shell_su("pkill -f frida-server", timeout=10)


def push_and_start(local_fs):
    remote = "/data/local/tmp/fs"
    adb(["push", local_fs, remote], check=True)
    r = shell_su(f"chmod 755 {remote}", timeout=10)
    if r.returncode != 0:
        print(f"    [err] chmod rc={r.returncode}")
        if r.stderr:
            print(f"    [err] {r.stderr.strip()}")
        sys.exit(r.returncode)
    kill_existing()
    print("[*] starting frida-server (background)")
    shell_su(f"nohup {remote} >/dev/null 2>&1 &", background=True)
    time.sleep(3)


def verify():
    print("[*] frida-ps -U | head")
    cmd = ["frida-ps"]
    if SERIAL:
        cmd += ["-D", SERIAL]
    else:
        cmd += ["-U"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        print(f"    [err] frida-ps rc={r.returncode}")
        print(r.stderr)
        return False
    lines = r.stdout.splitlines()
    for ln in lines[:15]:
        print(f"    {ln}")
    print(f"    ... total {len(lines)} lines")
    return len(lines) > 5


def main():
    global SERIAL
    ensure_adb()
    SERIAL = pick_serial()
    print(f"[*] using device: {SERIAL}")

    print("[*] checking device abi ...")
    abi, arch = get_abi()
    print(f"    abi={abi}  arch={arch}")

    print("[*] checking root ...")
    rooted = check_root()
    print(f"    root = {'YES' if rooted else 'NO'}")
    if not rooted:
        print("[!] device not rooted — enable Root Permission in MuMu settings")
        print("    (Preference settings -> Other -> Root Permission -> restart)")
        sys.exit(1)

    here = os.path.dirname(os.path.abspath(__file__))
    xz_name = f"frida-server-{FRIDA_VERSION}-android-{arch}.xz"
    fs_name = f"frida-server-{FRIDA_VERSION}-android-{arch}"
    xz_path = os.path.join(here, xz_name)
    fs_path = os.path.join(here, fs_name)

    if not os.path.isfile(fs_path):
        if not os.path.isfile(xz_path):
            url = f"{RELEASE_BASE}/{xz_name}"
            try:
                download(url, xz_path)
            except Exception as e:
                print(f"[!] download failed: {e}")
                print(f"    grab manually: {url}")
                print(f"    place at: {xz_path}")
                sys.exit(1)
        unxz(xz_path, fs_path)

    push_and_start(fs_path)

    if verify():
        print()
        print("=" * 60)
        print("  frida-server is UP")
        print("  next: run RUN-FRIDA-CIPHER.bat")
        print("=" * 60)
    else:
        print()
        print("[!] frida-ps saw too few processes — server may not be up")
        print("    try manually:")
        print("      adb shell \"su -c '/data/local/tmp/fs &'\"")


if __name__ == "__main__":
    main()
