"""
find_decrypt.py v2 — brute-force scan of every method's instructions in all classesN.dex.
"""
import sys, io, os, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from loguru import logger
    logger.remove()
except Exception:
    pass
import logging
logging.disable(logging.CRITICAL)

from androguard.core.dex import DEX

MARKERS = ['_ENC_LF_AC_KEY', '_LF_AC_KEY']

# extract all classes*.dex from APK if not done yet
APK = 'api/lgr_base.apk'
OUT = 'api/libs_extracted'
os.makedirs(OUT, exist_ok=True)
with zipfile.ZipFile(APK,'r') as z:
    for n in z.namelist():
        if n.startswith('classes') and n.endswith('.dex'):
            dst = os.path.join(OUT, os.path.basename(n))
            if not os.path.exists(dst):
                with z.open(n) as src, open(dst,'wb') as f: f.write(src.read())
                print(f'[+] extracted {dst} ({os.path.getsize(dst):,} B)')

dex_files = sorted([f for f in os.listdir(OUT) if f.startswith('classes') and f.endswith('.dex')])
print(f'[*] scanning {len(dex_files)} dex files')

for dex_name in dex_files:
    dex_path = os.path.join(OUT, dex_name)
    with open(dex_path,'rb') as f:
        data = f.read()
    # quick check if marker string is anywhere in this dex
    found_any = False
    for m in MARKERS:
        if m.encode() in data:
            found_any = True
            break
    if not found_any:
        continue
    print(f'=== {dex_name} ({len(data):,} B) ===')
    dex = DEX(data)
    count = 0
    for cls in dex.get_classes():
        for m in cls.get_methods():
            code = m.get_code()
            if not code: continue
            try:
                insns = list(code.get_bc().get_instructions())
            except Exception:
                continue
            joined_text = ' | '.join(ins.get_output() for ins in insns)
            matched = None
            for marker in MARKERS:
                if marker in joined_text:
                    matched = marker; break
            if not matched: continue
            cls_name = cls.get_name()
            mname = m.get_name()
            desc = m.get_descriptor()
            print(f'  HIT [{matched}]: {cls_name}->{mname}{desc}')
            count += 1
            # print instructions
            for i, ins in enumerate(insns):
                print(f'    {i:4d} {ins.get_name():22s} {ins.get_output()}')
            print('    --- end ---')
            print()
            if count >= 10: break
        if count >= 10: break
