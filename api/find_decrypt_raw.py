"""
find_decrypt_raw.py — raw byte scan of all classesN.dex for crypto algorithm strings
near _ENC_LF_AC_KEY references. Much faster than androguard.
"""
import sys, io, os, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

MARKER = b'_ENC_LF_AC_KEY'
CRYPTO_PATTERNS = [
    rb'AES/CBC/[A-Za-z0-9]+',
    rb'AES/ECB/[A-Za-z0-9]+',
    rb'AES/GCM/[A-Za-z0-9]+',
    rb'AES/CTR/[A-Za-z0-9]+',
    rb'DES/CBC/[A-Za-z0-9]+',
    rb'PBKDF2WithHmacSHA[0-9]+',
    rb'HmacSHA\d+',
    rb'SHA-\d+',
    rb'XXTEA',
    rb'XOR',
]
# class-name-like strings near marker
CLS_PATTERN = re.compile(rb'L[a-zA-Z_][a-zA-Z0-9_/$]{5,100};')

for fn in sorted(os.listdir('api/libs_extracted')):
    if not fn.startswith('classes') or not fn.endswith('.dex'): continue
    p = 'api/libs_extracted/' + fn
    with open(p,'rb') as f: d = f.read()
    marker_pos = []
    for m in re.finditer(MARKER, d):
        marker_pos.append(m.start())
    if not marker_pos: continue

    print(f'=== {fn} ({len(d):,} B) marker@{marker_pos} ===')

    # crypto algo strings anywhere in this dex
    algos_found = {}
    for pat in CRYPTO_PATTERNS:
        for m in re.finditer(pat, d):
            s = m.group()
            algos_found.setdefault(s, []).append(m.start())
    for s, positions in sorted(algos_found.items()):
        print(f'  ALGO: {s!r:40s} @ {positions[:5]}  (count={len(positions)})')

    # class names near marker (+/- 4KB)
    for mp in marker_pos:
        print(f'  --- classes near marker @ {mp:#x} ---')
        window = d[max(0,mp-4096):mp+4096]
        classes = set()
        for m in CLS_PATTERN.finditer(window):
            classes.add(m.group())
        for c in sorted(classes):
            cs = c.decode('ascii','ignore')
            # filter out androidx/junit noise
            if any(k in cs for k in ('androidx/', 'kotlin/', 'okhttp3/', 'kotlinx/',
                                      'com/google/', 'androidx.', 'spongycastle', 'bouncycastle')):
                continue
            print(f'    {cs}')
    print()
