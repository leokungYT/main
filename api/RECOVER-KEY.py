#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# api/RECOVER-KEY.py
#
# known-plaintext key recovery, multi-source:
#   (1) hash patterns of (seed, udid, variants)
#   (2) every 32-hex string found anywhere in the repo
#   (3) winreg HKCU\Environment (persisted env from `setx`)
#
# test = AES-CBC decrypt(iv=blob[:16], key=cand) ==(exact)== creds[guestCookie]
# byte-exact comparison -> zero false positives

import base64
import binascii
import hashlib
import json
import os
import re
import sys
import time

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA1, SHA256
from Crypto.Util.Padding import unpad

SEED = "linegamesupersecret"
SEED_B = SEED.encode()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDS_PATH = os.path.join(ROOT, "creds.json")

UDID_RX = re.compile(r'name="_DEVICE_UUID_KEY">([^<]+)</string>')
ENC_RX  = re.compile(r'name="_ENC_LF_AC_KEY">([^<]+)</string>', re.S)
HEX32_RX = re.compile(r'(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])')
HEX64_RX = re.compile(r'(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])')

SKIP_DIRS = (
    "node_modules", "Tesseract", ".git", "__pycache__",
    "prefs_backup", "lgr_prefs", "ad-player", "frida-server",
)


def _clean_b64(s):
    s = s.strip().strip('"').strip("'")
    # strip XML char entities (&#10; &#13; &amp; etc.)
    s = re.sub(r"&#\d+;", "", s)
    s = re.sub(r"&amp;", "&", s)
    # strip all whitespace incl. unicode
    s = re.sub(r"\s+", "", s)
    # keep only base64 alphabet + padding
    s = re.sub(r"[^A-Za-z0-9+/=_-]", "", s)
    s = s.replace("-", "+").replace("_", "/")
    s = s.rstrip("=")
    return s + ("=" * ((-len(s)) % 4))


def b64d(s):
    try:
        return base64.b64decode(_clean_b64(s), validate=False)
    except Exception:
        return b""


def find_pairs(creds, limit=50, verbose=True):
    u2c = {c["udid"]: (rsn, c["guestCookie"])
           for rsn, c in creds.items() if c.get("guestCookie")}
    hits = []
    matched_udid = 0
    bad_blob = 0
    for root, dirs, files in os.walk(ROOT):
        if any(s in root for s in SKIP_DIRS):
            continue
        for f in files:
            if not f.endswith(".xml"):
                continue
            p = os.path.join(root, f)
            try:
                t = open(p, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            mu = UDID_RX.search(t); me = ENC_RX.search(t)
            if not (mu and me):
                continue
            u = mu.group(1).strip()
            if u not in u2c:
                continue
            matched_udid += 1
            raw = b64d(me.group(1).strip())
            if len(raw) < 32 or (len(raw) - 16) % 16 != 0:
                bad_blob += 1
                if verbose and bad_blob <= 3:
                    print(f"    skip {os.path.relpath(p, ROOT)}  raw.len={len(raw)}")
                continue
            rsn, guest = u2c[u]
            hits.append({
                "xml": os.path.relpath(p, ROOT),
                "udid": u, "rsn": rsn, "guest": guest,
                "iv": raw[:16], "ct": raw[16:],
            })
            if len(hits) >= limit:
                break
        if len(hits) >= limit:
            break
    if verbose:
        print(f"    matched udid total={matched_udid}  bad_blob={bad_blob}  good={len(hits)}")
    return hits


def scan_hex_pool():
    """return set of 32/64-char hex strings from text files in repo + shell history"""
    pool = set()
    exts = (".py", ".js", ".bat", ".txt", ".md", ".json", ".ps1",
            ".sh", ".cfg", ".ini", ".env", ".yaml", ".yml",
            ".toml", ".lua", ".log")
    roots = [ROOT]
    # also check shell history - key might have been typed as `set LGR_AES_KEY=...`
    for h in (
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt"),
        os.path.expanduser("~/.bash_history"),
        os.path.expanduser("~/.zsh_history"),
    ):
        if os.path.isfile(h):
            try:
                txt = open(h, encoding="utf-8", errors="ignore").read()
                for m in HEX32_RX.findall(txt):
                    pool.add(m.lower())
                for m in HEX64_RX.findall(txt):
                    pool.add(m.lower())
                print(f"[*] scanned shell history: {h}")
            except Exception:
                pass
    for base in roots:
        for root, dirs, files in os.walk(base):
            if any(s in root for s in SKIP_DIRS):
                continue
            for f in files:
                if not f.endswith(exts):
                    continue
                p = os.path.join(root, f)
                try:
                    txt = open(p, encoding="utf-8", errors="ignore").read()
                except Exception:
                    continue
                for m in HEX32_RX.findall(txt):
                    pool.add(m.lower())
                for m in HEX64_RX.findall(txt):
                    pool.add(m.lower())
    return pool


def hkcu_env_hex():
    """pull any LGR/AES/KEY-shaped env from registry"""
    out = {}
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        i = 0
        while True:
            try:
                name, val, _ = winreg.EnumValue(k, i)
                i += 1
                if not isinstance(val, str):
                    continue
                if re.fullmatch(r"[0-9a-fA-F]{32,64}", val or ""):
                    out[name] = val.lower()
            except OSError:
                break
    except Exception:
        pass
    return out


def hash_patterns(udid):
    pats = []
    seen = set()

    def add(tag, k):
        if isinstance(k, str):
            k = k.encode()
        if len(k) not in (16, 24, 32) or k in seen:
            return
        seen.add(k)
        pats.append((tag, k))

    add("seed.pad16", SEED_B.ljust(16, b"\x00")[:16])
    add("md5(seed)",       hashlib.md5(SEED_B).digest())
    add("sha256(seed)16",  hashlib.sha256(SEED_B).digest()[:16])
    add("sha256(seed)32",  hashlib.sha256(SEED_B).digest())

    ub = udid.encode()
    try:
        raw = binascii.unhexlify(udid)
    except binascii.Error:
        raw = None

    if raw:
        add("udid.raw",         raw)
        add("md5(udid.raw)",    hashlib.md5(raw).digest())
        add("sha256(udid.raw)32", hashlib.sha256(raw).digest())
        add("sha256(seed+udid.raw)16", hashlib.sha256(SEED_B + raw).digest()[:16])
        add("sha256(seed+udid.raw)32", hashlib.sha256(SEED_B + raw).digest())
        add("sha256(udid.raw+seed)32", hashlib.sha256(raw + SEED_B).digest())

    for sep in (b"", b":", b"|", b"-"):
        add(f"md5(seed+udid sep={sep!r})",      hashlib.md5(SEED_B + sep + ub).digest())
        add(f"sha256(seed+udid sep={sep!r})16", hashlib.sha256(SEED_B + sep + ub).digest()[:16])
        add(f"sha256(seed+udid sep={sep!r})32", hashlib.sha256(SEED_B + sep + ub).digest())

    for cnt in (1, 1000, 10000, 100000):
        try:
            add(f"pbkdf2-sha1(seed,udid,{cnt})16",
                PBKDF2(SEED_B, ub, 16, count=cnt, hmac_hash_module=SHA1))
            add(f"pbkdf2-sha256(seed,udid,{cnt})32",
                PBKDF2(SEED_B, ub, 32, count=cnt, hmac_hash_module=SHA256))
        except Exception:
            pass

    return pats


def test_key(key, pair):
    """Try several IV strategies — return True if any yields exact pt match."""
    exp = pair["guest"].encode()
    iv_candidates = [
        ("blob[:16]", pair["iv"]),
        ("zeros",     b"\x00" * 16),
        ("seed[:16]", SEED_B[:16].ljust(16, b"\x00")),
        ("key[:16]",  key[:16]),
        ("udid.raw",  binascii.unhexlify(pair["udid"]) if len(pair["udid"]) == 32 else None),
    ]
    # ct strategies to match IV strategies
    for iv_tag, iv in iv_candidates:
        if iv is None:
            continue
        for ct_tag, ct in (
            ("ct=blob[16:]", pair["ct"]),
            ("ct=all",       pair["iv"] + pair["ct"]),   # no header
        ):
            try:
                pt = AES.new(key, AES.MODE_CBC, iv).decrypt(ct)
                try:
                    pt = unpad(pt, AES.block_size)
                except Exception:
                    continue
                if pt == exp:
                    pair["_hit_iv"] = iv_tag
                    pair["_hit_ct"] = ct_tag
                    return True
            except Exception:
                pass
    return False


def main():
    if not os.path.isfile(CREDS_PATH):
        sys.exit(f"[!] {CREDS_PATH} not found")
    creds = json.load(open(CREDS_PATH, encoding="utf-8"))
    print(f"[*] creds entries: {len(creds)}")

    print("[*] finding XML + creds pairs ...")
    pairs = find_pairs(creds, limit=20)
    print(f"[*] usable pairs: {len(pairs)}")
    for p in pairs[:5]:
        print(f"    - {p['xml']}  rsn={p['rsn']}  pt.len={len(p['guest'])}")
    if not pairs:
        sys.exit("[!] no usable pair")
    print()

    # source 1: HKCU env
    hkcu = hkcu_env_hex()
    if hkcu:
        print(f"[*] HKCU env hex-shaped vars: {list(hkcu.keys())}")
        for name, hx in hkcu.items():
            try:
                key = binascii.unhexlify(hx)
                for p in pairs:
                    if test_key(key, p):
                        print(f"\n*** HIT via HKCU env {name} ***")
                        print(f"    key = {hx}")
                        return save(hx, pairs)
            except Exception:
                pass

    # source 2: hash patterns per-pair
    print(f"[*] testing hash patterns (seed+udid family) ...")
    for p in pairs:
        pats = hash_patterns(p["udid"])
        for tag, key in pats:
            if test_key(key, p):
                print(f"\n*** HIT via hash pattern: {tag} (rsn={p['rsn']}) ***")
                return save(key.hex(), pairs)

    # source 3: every 32/64-hex string in repo
    print(f"[*] scanning repo for 32/64-hex strings ...")
    pool = scan_hex_pool()
    # remove things we know aren't keys: udids, rsns
    udid_set = {c["udid"].lower() for c in creds.values() if c.get("udid")}
    rsn_set  = {rsn.lower() for rsn in creds.keys()}
    pool -= udid_set
    pool -= rsn_set
    print(f"[*] candidate hex pool (after filter): {len(pool)}")

    t0 = time.time()
    # test every candidate against every pair - break on first match
    for hx in pool:
        try:
            key = binascii.unhexlify(hx)
        except Exception:
            continue
        for p in pairs[:3]:   # prune: 3 pairs enough to confirm
            if test_key(key, p):
                print(f"\n*** HIT via repo hex: key={hx} ***")
                print(f"    matched rsn={p['rsn']}")
                print(f"    search time: {time.time()-t0:.2f}s")
                return save(hx, pairs)

    print(f"\n[*] no match (scan took {time.time()-t0:.2f}s)")
    print("=" * 60)
    print(" key is NOT in HKCU env, NOT in hash patterns,")
    print(" NOT anywhere in repo text files.")
    print()
    print(" where creds.json came from previously:")
    print("   - the key was in a session env (not persisted)")
    print("   - OR the script that filled creds.json was deleted")
    print()
    print(" to recover:")
    print("   - find the shell window that ran xml_fire.py originally")
    print("   - OR check other machines / backups (.env, powershell history)")
    print("   - OR frida-dump again (need anti-tamper bypass for LGRGS)")
    print("=" * 60)
    sys.exit(1)


def save(hex_key, pairs):
    # cross-verify
    try:
        key = binascii.unhexlify(hex_key)
    except Exception:
        print(f"[!] bad hex: {hex_key}")
        sys.exit(1)
    n_ok = sum(1 for p in pairs if test_key(key, p))
    print(f"[*] cross-verify: {n_ok}/{len(pairs)} pairs decrypt cleanly with this key")
    if n_ok < 1:
        print("[!] false positive — key doesn't verify on any pair")
        sys.exit(1)
    print()
    print("=" * 60)
    print("  WINNING KEY")
    print("=" * 60)
    print(f"  hex ({len(key)} bytes) = {hex_key}")
    print()
    keytxt = os.path.join(ROOT, "key.txt")
    with open(keytxt, "w", encoding="ascii") as f:
        f.write(hex_key + "\n")
    print(f"  saved -> {keytxt}")
    print()
    print("  then:  double-click YIGHT.bat")


if __name__ == "__main__":
    main()
