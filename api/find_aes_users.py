"""Find classes that reference AES/CBC/PKCS7Padding and look like crypto wrappers."""
import sys, io, os, logging
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
try:
    from loguru import logger; logger.remove()
except: pass
logging.disable(logging.CRITICAL)

from androguard.core.dex import DEX

TARGETS = [b'AES/CBC/PKCS7Padding', b'AES/CBC/PKCS5Padding',
           b'AES/ECB/PKCS7Padding', b'AES/ECB/PKCS5Padding']

for fn in sorted(os.listdir('api/libs_extracted')):
    if not fn.startswith('classes') or not fn.endswith('.dex'): continue
    p = 'api/libs_extracted/' + fn
    with open(p,'rb') as f: data = f.read()
    if not any(t in data for t in TARGETS): continue

    print(f'=== {fn} ===')
    dex = DEX(data)
    all_classes = list(dex.get_classes())
    print(f'  classes: {len(all_classes)}')
    found = 0
    for cls in all_classes:
        for m in cls.get_methods():
            code = m.get_code()
            if not code: continue
            try:
                raw = ' '.join(ins.get_output() for ins in code.get_bc().get_instructions())
            except Exception:
                continue
            for t in TARGETS:
                if t.decode() in raw:
                    cn = cls.get_name(); mn = m.get_name()
                    cn = cn.decode() if isinstance(cn,(bytes,bytearray)) else str(cn)
                    mn = mn.decode() if isinstance(mn,(bytes,bytearray)) else str(mn)
                    print(f'  HIT: {cn}->{mn} uses {t.decode()}')
                    found += 1
                    break
        if found >= 20: break
