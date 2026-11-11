import sys, os, base64, hashlib, re, binascii, hmac, time
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA1, SHA256

SEED = "linegamesupersecret"
SEED_B = SEED.encode()
BAR = "=" * 62
DASH = "-" * 62


def banner(t):
    print(BAR)
    print(f"  {t}")
    print(BAR)


def _clean_b64(s):
    s = s.strip().strip('"').strip("'")
    s = re.sub(r"\s+", "", s)
    s = s.replace("-", "+").replace("_", "/")
    return s + ("=" * ((-len(s)) % 4))


def _b64d(s):
    try:
        return base64.b64decode(_clean_b64(s), validate=False)
    except Exception:
        return b""


def load_blob():
    path = os.path.join(os.path.dirname(__file__), "_ENC_LF_AC.txt")
    if not os.path.isfile(path):
        print(f"[!] missing {path}")
        sys.exit(1)
    raw = open(path, "r", encoding="utf-8", errors="ignore").read()
    return _b64d(raw)


def pkcs7_strip(pt):
    if not pt:
        return pt, False
    p = pt[-1]
    if 1 <= p <= 16 and pt[-p:] == bytes([p]) * p:
        return pt[:-p], True
    return pt, False


def printable_ratio(b):
    if not b:
        return 0.0
    ok = sum(1 for x in b if 0x20 <= x < 0x7f or x in (0x09, 0x0a, 0x0d))
    return ok / len(b)


STRONG_MARKERS = (
    b"guestCookie", b"guest_cookie", b"cookie",
    b"LF_AC", b"LFAC",
    b"token", b"userId", b"user_id",
    b'{"', b'[{', b"accessToken", b"sessionId",
    b"linegame", b"linecorp",
)


def strong_marker(b):
    if not b:
        return None
    head = bytes(x & 0xff for x in b[:64])
    for sig in STRONG_MARKERS:
        if sig in head:
            return sig
    return None


def try_decrypt(key, blob, label):
    """
    Return list of (variant, pt_full, pt_strip, pkcs7_ok)
    Covers: ECB, CBC(iv=zero/seed/blob[:16]/blob[:12]+0000), CTR(nonce=zero/blob[:8]),
            GCM (if tag_len==16 at tail)
    """
    out = []
    if len(key) not in (16, 24, 32):
        return out

    # ECB
    if len(blob) % 16 == 0:
        try:
            pt = AES.new(key, AES.MODE_ECB).decrypt(blob)
            s, ok = pkcs7_strip(pt)
            out.append((f"{label}/ECB", pt, s if ok else pt, ok, False))
        except Exception:
            pass

    # CBC iv=zero
    if len(blob) % 16 == 0:
        try:
            pt = AES.new(key, AES.MODE_CBC, b"\x00" * 16).decrypt(blob)
            s, ok = pkcs7_strip(pt)
            out.append((f"{label}/CBC-zero", pt, s if ok else pt, ok, False))
        except Exception:
            pass

    # CBC iv=blob[:16], ct=blob[16:]
    if len(blob) >= 32 and (len(blob) - 16) % 16 == 0:
        try:
            pt = AES.new(key, AES.MODE_CBC, blob[:16]).decrypt(blob[16:])
            s, ok = pkcs7_strip(pt)
            out.append((f"{label}/CBC-ivhead", pt, s if ok else pt, ok, False))
        except Exception:
            pass

    # CBC iv=seed[:16]
    if len(blob) % 16 == 0:
        try:
            iv = SEED_B[:16].ljust(16, b"\x00")
            pt = AES.new(key, AES.MODE_CBC, iv).decrypt(blob)
            s, ok = pkcs7_strip(pt)
            out.append((f"{label}/CBC-ivseed", pt, s if ok else pt, ok, False))
        except Exception:
            pass

    # CBC iv=key[:16] (some SDKs do this)
    if len(blob) % 16 == 0:
        try:
            pt = AES.new(key, AES.MODE_CBC, key[:16]).decrypt(blob)
            s, ok = pkcs7_strip(pt)
            out.append((f"{label}/CBC-ivkey", pt, s if ok else pt, ok, False))
        except Exception:
            pass

    # CTR nonce=zero
    try:
        from Crypto.Util import Counter
        ctr = Counter.new(128, initial_value=0)
        pt = AES.new(key, AES.MODE_CTR, counter=ctr).decrypt(blob)
        out.append((f"{label}/CTR-zero", pt, pt, False, False))
    except Exception:
        pass

    # CTR nonce=blob[:16] as counter init
    try:
        from Crypto.Util import Counter
        if len(blob) >= 32:
            iv_int = int.from_bytes(blob[:16], "big")
            ctr = Counter.new(128, initial_value=iv_int)
            pt = AES.new(key, AES.MODE_CTR, counter=ctr).decrypt(blob[16:])
            out.append((f"{label}/CTR-ivhead", pt, pt, False, False))
    except Exception:
        pass

    # GCM: iv=12 at head, tag=16 at tail, ct=middle  (tag verified => crypto-proof WIN)
    if len(blob) >= 12 + 16 + 1:
        try:
            iv = blob[:12]
            tag = blob[-16:]
            ct = blob[12:-16]
            pt = AES.new(key, AES.MODE_GCM, nonce=iv).decrypt_and_verify(ct, tag)
            out.append((f"{label}/GCM-12-16", pt, pt, False, True))
        except Exception:
            pass

    # GCM alt: iv=16 at head
    if len(blob) >= 16 + 16 + 1:
        try:
            iv = blob[:16]
            tag = blob[-16:]
            ct = blob[16:-16]
            pt = AES.new(key, AES.MODE_GCM, nonce=iv).decrypt_and_verify(ct, tag)
            out.append((f"{label}/GCM-16-16", pt, pt, False, True))
        except Exception:
            pass

    return out


def gen_patterns(udids, blob):
    pats = []
    seen = set()

    def add(tag, k):
        if isinstance(k, str):
            k = k.encode()
        if len(k) not in (16, 24, 32) or k in seen:
            return
        seen.add(k)
        pats.append((tag, k))

    # seed-only
    add("seed.pad16", SEED_B.ljust(16, b"\x00")[:16])
    add("seed.pad32", SEED_B.ljust(32, b"\x00")[:32])
    add("md5(seed)", hashlib.md5(SEED_B).digest())
    add("sha256(seed)16", hashlib.sha256(SEED_B).digest()[:16])
    add("sha256(seed)32", hashlib.sha256(SEED_B).digest())
    add("sha1(seed)16", hashlib.sha1(SEED_B).digest()[:16])
    add("sha1(seed)20pad", hashlib.sha1(SEED_B).digest().ljust(24, b"\x00")[:24])

    # blob-derived (some SDKs stash key in header)
    if len(blob) >= 48:
        add("blob[:16]",       blob[:16])
        add("blob[:24]",       blob[:24])
        add("blob[:32]",       blob[:32])
        add("blob[16:32]",     blob[16:32])
        add("blob[-16:]",      blob[-16:])
        add("blob[-32:]",      blob[-32:])
        add("md5(blob[:16])",  hashlib.md5(blob[:16]).digest())
        add("sha256(blob[:16])32", hashlib.sha256(blob[:16]).digest())

    # per-udid
    for label, u in udids:
        if not u:
            continue
        ub = u.encode()
        ubl = u.lower().encode()
        ubu = u.upper().encode()

        # udid as raw bytes — THE KEY EVENT (32 hex = 16 raw bytes = perfect AES-128)
        try:
            raw = binascii.unhexlify(u)
            add(f"udid.raw[{label}]",              raw)
            add(f"udid.raw*2[{label}]",            raw + raw)
            add(f"udid.raw+seed16[{label}]",       raw + SEED_B[:16])
            add(f"seed16+udid.raw[{label}]",       SEED_B[:16] + raw)
            add(f"md5(udid.raw)[{label}]",         hashlib.md5(raw).digest())
            add(f"sha256(udid.raw)32[{label}]",    hashlib.sha256(raw).digest())
            add(f"sha256(udid.raw)16[{label}]",    hashlib.sha256(raw).digest()[:16])
            add(f"sha256(seed+udid.raw)16[{label}]", hashlib.sha256(SEED_B + raw).digest()[:16])
            add(f"sha256(seed+udid.raw)32[{label}]", hashlib.sha256(SEED_B + raw).digest())
            add(f"sha256(udid.raw+seed)32[{label}]", hashlib.sha256(raw + SEED_B).digest())
            add(f"md5(seed+udid.raw)[{label}]",    hashlib.md5(SEED_B + raw).digest())
            add(f"md5(udid.raw+seed)[{label}]",    hashlib.md5(raw + SEED_B).digest())
            # xor variants
            xor16 = bytes(a ^ b for a, b in zip(raw, SEED_B.ljust(16, b"\x00")[:16]))
            add(f"udid.raw^seed[{label}]", xor16)
            # interleave halves
            add(f"udid.raw[:8]+sha256(seed)[:8][{label}]", raw[:8] + hashlib.sha256(SEED_B).digest()[:8])
            add(f"sha256(seed)[:8]+udid.raw[:8][{label}]", hashlib.sha256(SEED_B).digest()[:8] + raw[:8])
        except binascii.Error:
            pass

        # hex-string concat
        for sep in (b"", b":", b"|", b"-", b"_", b".", b"/"):
            for mix in (SEED_B + sep + ub, ub + sep + SEED_B,
                        SEED_B + sep + ubl, SEED_B + sep + ubu):
                add(f"md5({mix[:12]!r}..)[{label}]",        hashlib.md5(mix).digest())
                add(f"sha256({mix[:12]!r}..)16[{label}]",   hashlib.sha256(mix).digest()[:16])
                add(f"sha256({mix[:12]!r}..)32[{label}]",   hashlib.sha256(mix).digest())
                add(f"sha1({mix[:12]!r}..)16[{label}]",     hashlib.sha1(mix).digest()[:16])
                # double hash
                add(f"sha256(sha256({mix[:12]!r}..))32[{label}]",
                    hashlib.sha256(hashlib.sha256(mix).digest()).digest())
                add(f"md5(md5({mix[:12]!r}..))[{label}]",
                    hashlib.md5(hashlib.md5(mix).digest()).digest())

        # udid-only
        add(f"md5(udid.hex)[{label}]",         hashlib.md5(ub).digest())
        add(f"sha256(udid.hex)16[{label}]",    hashlib.sha256(ub).digest()[:16])
        add(f"sha256(udid.hex)32[{label}]",    hashlib.sha256(ub).digest())
        add(f"sha256(udid.lo)32[{label}]",     hashlib.sha256(ubl).digest())
        add(f"sha256(udid.up)32[{label}]",     hashlib.sha256(ubu).digest())
        add(f"md5(udid.up)[{label}]",          hashlib.md5(ubu).digest())

        # HMAC (both directions)
        add(f"hmac-sha256(seed,udid)16[{label}]", hmac.new(SEED_B, ub, hashlib.sha256).digest()[:16])
        add(f"hmac-sha256(seed,udid)32[{label}]", hmac.new(SEED_B, ub, hashlib.sha256).digest())
        add(f"hmac-sha256(udid,seed)32[{label}]", hmac.new(ub, SEED_B, hashlib.sha256).digest())
        add(f"hmac-md5(seed,udid)[{label}]",      hmac.new(SEED_B, ub, hashlib.md5).digest())
        add(f"hmac-sha1(seed,udid)16[{label}]",   hmac.new(SEED_B, ub, hashlib.sha1).digest()[:16])

        # PBKDF2 — SHA1 + SHA256, several counts, both salt orders
        for cnt in (1, 100, 1000, 10000):
            try:
                add(f"pbkdf2-sha1(seed,udid,{cnt})16[{label}]",
                    PBKDF2(SEED_B, ub, 16, count=cnt, hmac_hash_module=SHA1))
                add(f"pbkdf2-sha1(seed,udid,{cnt})32[{label}]",
                    PBKDF2(SEED_B, ub, 32, count=cnt, hmac_hash_module=SHA1))
                add(f"pbkdf2-sha256(seed,udid,{cnt})16[{label}]",
                    PBKDF2(SEED_B, ub, 16, count=cnt, hmac_hash_module=SHA256))
                add(f"pbkdf2-sha256(seed,udid,{cnt})32[{label}]",
                    PBKDF2(SEED_B, ub, 32, count=cnt, hmac_hash_module=SHA256))
                add(f"pbkdf2-sha1(udid,seed,{cnt})16[{label}]",
                    PBKDF2(ub, SEED_B, 16, count=cnt, hmac_hash_module=SHA1))
            except Exception:
                pass

        # common LINE prefixes
        for prefix in (b"LGRGS", b"LGR", b"linegame", b"com.linecorp.LGRGS",
                       b"com.linecorp.lgrgs", b"LFAC", b"LF_AC"):
            add(f"sha256({prefix.decode()}+seed+udid)32[{label}]",
                hashlib.sha256(prefix + SEED_B + ub).digest())
            add(f"sha256(seed+{prefix.decode()}+udid)32[{label}]",
                hashlib.sha256(SEED_B + prefix + ub).digest())
            add(f"sha256(seed+udid+{prefix.decode()})32[{label}]",
                hashlib.sha256(SEED_B + ub + prefix).digest())
            add(f"md5({prefix.decode()}+seed+udid)[{label}]",
                hashlib.md5(prefix + SEED_B + ub).digest())

    # fixed-key long shots (hardcoded secrets occasionally reused across LINE SDKs)
    for guess in (
        b"0123456789abcdef",
        b"LineGameSuperSec",
        b"linegamesecret16",
        b"LGRGS_SECRET_KEY",
        b"LGRGS1234567890a",
    ):
        add(f"fixed:{guess!r}", guess)

    return pats


def pretty_header(udids, blob):
    banner("WHY THIS HAS A SHOT (v2)")
    print()
    print(f" 1) wider: udid raw bytes AS key (hex 32 = AES-128 fit)")
    print(f" 2) wider: blob[:16] / blob[:32] AS key (header stash)")
    print(f" 3) wider: GCM (12+ct+16 tag), CTR, CBC with iv=key[:16]")
    print(f" 4) wider: xor seed^udid, interleave halves")
    print(f" 5) wider: hmac-md5, double-hash, more prefixes/separators")
    print(f" blob len = {len(blob)} first16={blob[:16].hex()}")
    print()
    banner("inputs")
    print()
    for lbl, u in udids:
        print(f"  {lbl:<22} = {u}")
    print(f"  seed                   = {SEED}")
    print()


def win_block(hit):
    tag, mode, key, pt_full, pt_strip, pkcs, reason = hit
    banner(f"*** WIN  ({reason}) ***")
    print()
    print(f"  pattern    = {tag}")
    print(f"  mode       = {mode}")
    print(f"  key(hex)   = {key.hex()}")
    print(f"  key(len)   = {len(key)} bytes")
    try:
        txt = pt_strip.decode("utf-8")
    except UnicodeDecodeError:
        txt = pt_strip.decode("latin-1", errors="replace")
    print(f"  plaintext  = {txt!r}")
    print()
    banner("NEXT")
    print()
    print(f"  set LGR_AES_KEY={key.hex()}")
    print(f"  python api\\xml_fire.py --xml-dir <path> --gift")
    print()


def top_block(scored, n=10):
    banner(f"[X] no clean win - top{n} printable ratio")
    print()
    for i, (r, tag, mode, key, pt, pkcs) in enumerate(scored[:n], 1):
        mk = strong_marker(pt)
        hit_markers = f"  <-- marker:{mk!r}" if mk else ""
        print(f"  #{i}  ratio={r:.3f}  pkcs7={'Y' if pkcs else 'N'}{hit_markers}")
        print(f"      pattern = {tag}")
        print(f"      mode    = {mode}")
        print(f"      key     = {key.hex()}")
        print(f"      pt[:64] = {pt[:64]!r}")
        print(f"      {DASH}")
    print()
    banner("next moves")
    print()
    print("  - re-check android_id (adb was empty — maybe not connected)")
    print("  - try apk signature sha1 as another 'udid' slot")
    print("  - Frida hook: SETUP-FRIDA-SERVER.bat -> RUN-FRIDA-CIPHER.bat")
    print()


def main():
    argv = [a.strip() for a in sys.argv[1:]]
    while len(argv) < 2:
        argv.append("")
    udids = []
    if argv[0]:
        udids.append(("_DEVICE_UUID_KEY", argv[0]))
    if argv[1] and argv[1] != argv[0]:
        udids.append(("android_id", argv[1]))
    if not udids:
        print("[!] no udid provided")
        sys.exit(2)

    blob = load_blob()
    if len(blob) < 16:
        print(f"[!] blob too small: {len(blob)}")
        sys.exit(1)

    pretty_header(udids, blob)

    pats = gen_patterns(udids, blob)
    print(f"[*] running {len(pats)} key patterns against 9 cipher variants ...")
    print()

    t0 = time.time()
    scored = []
    wins = []
    for tag, key in pats:
        for mode, pt_full, pt_strip, pkcs, verified in try_decrypt(key, blob, tag):
            r = printable_ratio(pt_strip)
            scored.append((r, tag, mode, key, pt_strip, pkcs))
            mk = strong_marker(pt_strip)
            # WIN gates (ordered strongest → weakest):
            # 1) GCM tag verified → cryptographic proof, no false positive
            # 2) pkcs7 valid AND ratio ≥ 0.95 → printable content with valid padding
            # 3) strong multi-char marker found AND ratio ≥ 0.85 → recognizable text
            if verified:
                wins.append((tag, mode, key, pt_full, pt_strip, True, "GCM-TAG"))
            elif pkcs and r >= 0.95:
                wins.append((tag, mode, key, pt_full, pt_strip, pkcs, "PKCS7+ratio"))
            elif mk and r >= 0.85:
                wins.append((tag, mode, key, pt_full, pt_strip, pkcs, f"marker:{mk.decode(errors='replace')}"))

    print(f"[*] done in {time.time()-t0:.2f}s - {len(scored)} decrypts scored")
    print()

    if wins:
        # dedupe wins by key+mode
        seen_w = set()
        for w in wins:
            k = (w[2], w[1])
            if k in seen_w:
                continue
            seen_w.add(k)
            win_block(w)
    else:
        scored.sort(key=lambda x: (-int(x[5]), -x[0]))
        if scored:
            top_block(scored, n=10)
        else:
            banner("[X] no modes decrypted at all")


if __name__ == "__main__":
    main()
