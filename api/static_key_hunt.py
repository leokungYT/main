"""
static_key_hunt.py — find AES key for _ENC_LF_AC_KEY without frida/MuMu.

Workflow:
    (1) extract native libs from APK (unzip)
    (2) scan every library byte-by-byte for 16/24/32-byte candidates
    (3) also extract printable C-string constants as candidate keys
    (4) try each candidate as AES key against ciphertext from one XML
    (5) print any "hit" where decrypt yields printable text / JSON-looking / known markers

Usage:
    # one-shot: extract + hunt
    py static_key_hunt.py --apk linerangers.apk --xml input-id/some.xml

    # if you already extracted libs
    py static_key_hunt.py --so lib/arm64-v8a/libLGRGS.so lib/arm64-v8a/libcocos2djs.so --xml input-id/some.xml

    # dump candidates only (no decrypt attempt) — useful for inspection
    py static_key_hunt.py --so libLGRGS.so --dump-candidates candidates.txt

Requirements:  pip install pycryptodome
"""

import argparse
import io
import os
import re
import sys
import zipfile
from typing import Iterator

# force utf-8 so Thai paths don't crash the console
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

try:
    from Crypto.Cipher import AES
except ImportError:
    print("ERROR: pip install pycryptodome")
    sys.exit(1)

STRONG_MARKERS = (b"userToken", b"refreshUserToken", b"userKey",
                  b"guestCookie", b"LF_AC", b'{"', b'"user')


# ------------------------- step 1: extract from APK -------------------------

def extract_libs(apk_path: str, out_dir: str) -> list[str]:
    """Return list of extracted .so paths."""
    os.makedirs(out_dir, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(apk_path, "r") as z:
        for info in z.infolist():
            name = info.filename
            # we want native libs and anything that could hold crypto consts
            if not name.endswith(".so"):
                continue
            # prefer arm64-v8a (modern emulators + phones), keep others too
            dst = os.path.join(out_dir, os.path.basename(name))
            # if same basename appears in multiple ABIs, prefix with abi
            abi = name.split("/")[1] if name.startswith("lib/") else "noabi"
            dst = os.path.join(out_dir, f"{abi}__{os.path.basename(name)}")
            with z.open(info) as src, open(dst, "wb") as fh:
                fh.write(src.read())
            extracted.append(dst)
    return extracted


# ------------------------- step 2: candidate generator -------------------------

def sliding_bytes(data: bytes, size: int, step: int = 1) -> Iterator[bytes]:
    """Every size-byte window with given step."""
    for i in range(0, len(data) - size + 1, step):
        yield data[i:i + size]


def aligned_bytes(data: bytes, size: int, align: int = 4) -> Iterator[bytes]:
    """Every size-byte window at `align`-aligned offset."""
    for i in range(0, len(data) - size + 1, align):
        yield data[i:i + size]


def printable_strings(data: bytes, min_len: int = 8, max_len: int = 64) -> Iterator[bytes]:
    """Every ASCII-printable null-terminated C string within the lib."""
    cur = bytearray()
    for b in data:
        if 32 <= b < 127:
            cur.append(b)
        else:
            if min_len <= len(cur) <= max_len:
                yield bytes(cur)
            cur = bytearray()
    if min_len <= len(cur) <= max_len:
        yield bytes(cur)


def key_candidates(so_bytes: bytes) -> Iterator[tuple[str, bytes]]:
    """Yield (source_label, key_bytes) for every candidate we want to try."""
    seen = set()

    # aligned 4-byte windows of size 16/24/32 — fastest, catches most hardcoded keys
    for size, label in [(16, "aligned4-16"), (24, "aligned4-24"), (32, "aligned4-32")]:
        for kb in aligned_bytes(so_bytes, size, align=4):
            if kb in seen:
                continue
            # skip all-zero or trivially-repeating junk
            if len(set(kb)) < 4:
                continue
            seen.add(kb)
            yield (label, kb)

    # aligned 16 windows of size 16/32 — a .rodata block aligned to 16 is likely intentional
    for size, label in [(16, "aligned16-16"), (32, "aligned16-32")]:
        for kb in aligned_bytes(so_bytes, size, align=16):
            if kb in seen:
                continue
            if len(set(kb)) < 4:
                continue
            seen.add(kb)
            yield (label, kb)

    # printable C-strings padded/truncated to 16/24/32
    for s in printable_strings(so_bytes, 8, 64):
        for size, label in [(16, "cstr-16"), (24, "cstr-24"), (32, "cstr-32")]:
            kb = (s + b"\x00" * size)[:size]
            if kb in seen:
                continue
            seen.add(kb)
            yield (label, kb)
        # also hex-decoded form if the string is pure hex of the right length
        if len(s) in (32, 48, 64) and all(c in b"0123456789abcdefABCDEF" for c in s):
            try:
                kb = bytes.fromhex(s.decode())
                if kb not in seen:
                    seen.add(kb)
                    yield (f"cstr-hex-{len(kb)}", kb)
            except ValueError:
                pass


# ------------------------- step 3: decrypt attempts -------------------------

def pkcs7_strip(pt: bytes) -> tuple[bytes, bool]:
    if not pt:
        return pt, False
    p = pt[-1]
    if 1 <= p <= 16 and pt[-p:] == bytes([p]) * p:
        return pt[:-p], True
    return pt, False


def printable_ratio(b: bytes) -> float:
    if not b:
        return 0.0
    ok = sum(1 for x in b if 0x20 <= x < 0x7f or x in (9, 10, 13))
    return ok / len(b)


def strong_marker(b: bytes) -> bytes | None:
    head = b[:256]
    for sig in STRONG_MARKERS:
        if sig in head:
            return sig
    return None


def try_decrypt_all_modes(key: bytes, blob: bytes) -> Iterator[tuple[str, bytes, bool]]:
    """Yield (mode_name, plaintext, pkcs7_ok) for each AES mode."""
    if len(key) not in (16, 24, 32):
        return
    # ECB
    if len(blob) % 16 == 0:
        try:
            pt = AES.new(key, AES.MODE_ECB).decrypt(blob)
            s, ok = pkcs7_strip(pt)
            yield ("ECB", s if ok else pt, ok)
        except Exception:
            pass
    # CBC iv=0
    if len(blob) % 16 == 0:
        try:
            pt = AES.new(key, AES.MODE_CBC, b"\x00" * 16).decrypt(blob)
            s, ok = pkcs7_strip(pt)
            yield ("CBC-iv0", s if ok else pt, ok)
        except Exception:
            pass
    # CBC iv=blob[:16]
    if len(blob) >= 32 and (len(blob) - 16) % 16 == 0:
        try:
            pt = AES.new(key, AES.MODE_CBC, blob[:16]).decrypt(blob[16:])
            s, ok = pkcs7_strip(pt)
            yield ("CBC-ivhead", s if ok else pt, ok)
        except Exception:
            pass
    # CBC iv=key[:16]
    if len(blob) % 16 == 0:
        try:
            pt = AES.new(key, AES.MODE_CBC, key[:16]).decrypt(blob)
            s, ok = pkcs7_strip(pt)
            yield ("CBC-ivkey", s if ok else pt, ok)
        except Exception:
            pass


def score_result(pt: bytes, pkcs7_ok: bool) -> tuple[int, float, bytes | None]:
    """Return (tier, printable_ratio, marker). Higher tier = stronger evidence."""
    mk = strong_marker(pt)
    r = printable_ratio(pt)
    if mk and r >= 0.90:
        return (3, r, mk)   # marker in mostly-printable plaintext = near-certain
    if pkcs7_ok and r >= 0.95:
        return (2, r, mk)   # valid padding + printable
    if mk:
        return (1, r, mk)   # marker in binary-looking blob
    return (0, r, None)


# ------------------------- step 4: read XML -------------------------

def read_ciphertext(xml_path: str) -> bytes:
    import base64
    with open(xml_path, "r", encoding="utf-8", errors="replace") as f:
        txt = f.read()
    m = re.search(r'_ENC_LF_AC_KEY">(.*?)</string>', txt, re.S)
    if not m:
        raise SystemExit(f"[!] _ENC_LF_AC_KEY not found in {xml_path}")
    enc = m.group(1).replace("&#10;", "").replace("\n", "").replace("\r", "").strip()
    # pad for b64
    return base64.b64decode(enc + "===")


# ------------------------- main -------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Static AES key hunt in native libs")
    ap.add_argument("--apk", help="LINE Rangers APK (or .xapk/.apks); if given, extracts .so files first")
    ap.add_argument("--extract-dir", default="api/libs_extracted", help="where to extract .so files")
    ap.add_argument("--so", nargs="+", default=[], help="path(s) to .so file(s) to scan")
    ap.add_argument("--xml", help="XML file to pull _ENC_LF_AC_KEY from (needed for decrypt tests)")
    ap.add_argument("--dump-candidates", help="write all candidates to this file, skip decrypt")
    ap.add_argument("--max-candidates", type=int, default=0, help="stop after N candidates (0 = all)")
    args = ap.parse_args()

    so_paths: list[str] = list(args.so)
    if args.apk:
        print(f"[1] extracting .so from {args.apk} -> {args.extract_dir}/")
        if not os.path.isfile(args.apk):
            print(f"[!] apk not found: {args.apk}")
            return 2
        extracted = extract_libs(args.apk, args.extract_dir)
        print(f"    found {len(extracted)} .so files")
        for p in extracted:
            print(f"      {p}  ({os.path.getsize(p):,} bytes)")
        so_paths.extend(extracted)

    if not so_paths:
        print("[!] no .so files; pass --apk or --so")
        return 2

    # keep only arm64-v8a if both abis extracted (same code, different arch — try arm64 first)
    arm64 = [p for p in so_paths if "arm64" in p.lower()]
    if arm64:
        so_paths = arm64
        print(f"[*] using {len(so_paths)} arm64-v8a .so file(s)")

    # read all libs into memory
    print(f"[2] reading {len(so_paths)} native lib(s)")
    all_bytes = b""
    for p in so_paths:
        with open(p, "rb") as f:
            data = f.read()
        print(f"    {os.path.basename(p)}: {len(data):,} bytes")
        all_bytes += data

    # dump-candidates mode
    if args.dump_candidates:
        print(f"[3] dumping candidates -> {args.dump_candidates}")
        with open(args.dump_candidates, "w", encoding="utf-8") as f:
            n = 0
            for label, kb in key_candidates(all_bytes):
                f.write(f"{label}\t{kb.hex()}\n")
                n += 1
                if args.max_candidates and n >= args.max_candidates:
                    break
        print(f"    wrote {n} candidates")
        return 0

    if not args.xml:
        print("[!] --xml required unless --dump-candidates")
        return 2

    ct = read_ciphertext(args.xml)
    print(f"[3] ciphertext from {args.xml}: {len(ct)} bytes (first 16: {ct[:16].hex()})")

    # dedupe candidates as we go
    print(f"[4] trying candidates...")
    tier3, tier2, tier1 = [], [], []
    n = 0
    for label, kb in key_candidates(all_bytes):
        n += 1
        if n % 50000 == 0:
            print(f"    ... {n:,} candidates tried, tiers so far: "
                  f"tier3={len(tier3)} tier2={len(tier2)} tier1={len(tier1)}")
        if args.max_candidates and n > args.max_candidates:
            break
        for mode, pt, pkcs7_ok in try_decrypt_all_modes(kb, ct):
            tier, r, mk = score_result(pt, pkcs7_ok)
            if tier == 0:
                continue
            hit = (label, mode, kb, pt, r, mk)
            [tier1, tier2, tier3][tier - 1].append(hit)
            if tier == 3:
                # near-certain win — print immediately
                print()
                print("=" * 70)
                print(f"*** TIER-3 WIN *** ({mk!r} in printable plaintext, ratio={r:.3f})")
                print(f"  source    : {label}")
                print(f"  mode      : {mode}")
                print(f"  key(hex)  : {kb.hex()}")
                print(f"  key(len)  : {len(kb)} bytes")
                print(f"  plaintext : {pt[:200]!r}")
                print("=" * 70)

    print()
    print(f"[done] tested {n:,} candidates")
    print(f"       tier3 (marker + printable) : {len(tier3)}")
    print(f"       tier2 (valid pkcs7 + text) : {len(tier2)}")
    print(f"       tier1 (marker in binary)   : {len(tier1)}")

    def dump(name, items, limit=5):
        if not items:
            return
        print()
        print(f"--- {name} (showing up to {limit}) ---")
        for label, mode, kb, pt, r, mk in items[:limit]:
            print(f"  [{label} / {mode}] key={kb.hex()}")
            print(f"    ratio={r:.3f} marker={mk!r}")
            print(f"    pt[:120]={pt[:120]!r}")

    dump("TIER-3 wins", tier3, limit=10)
    dump("TIER-2 candidates", tier2, limit=5)
    dump("TIER-1 candidates", tier1, limit=3)

    return 0 if (tier3 or tier2) else 1


if __name__ == "__main__":
    sys.exit(main())
