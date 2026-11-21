"""Find all callers of SimpleCrypto.decrypt2 across all dex files."""
import sys, io, os, logging
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
try:
    from loguru import logger; logger.remove()
except: pass
logging.disable(logging.CRITICAL)
from androguard.core.dex import DEX

# target signature pattern
TARGET_SIG = 'Lorg/cocos2dx/lib/linecocos/utils/SimpleCrypto;->decrypt'

for fn in sorted(os.listdir('api/libs_extracted')):
    if not fn.startswith('classes') or not fn.endswith('.dex'): continue
    p = 'api/libs_extracted/' + fn
    with open(p,'rb') as f: data = f.read()
    if TARGET_SIG.encode() not in data and b'SimpleCrypto' not in data: continue
    print(f'=== {fn} ===')
    dex = DEX(data)
    for cls in dex.get_classes():
        cn = cls.get_name()
        cnb = cn.decode() if isinstance(cn,(bytes,bytearray)) else cn
        for m in cls.get_methods():
            code = m.get_code()
            if not code: continue
            try:
                insns = list(code.get_bc().get_instructions())
            except Exception:
                continue
            joined = ' | '.join(i.get_output() for i in insns)
            if TARGET_SIG not in joined: continue
            mn = m.get_name(); mn = mn.decode() if isinstance(mn,bytes) else mn
            desc = m.get_descriptor(); desc = desc.decode() if isinstance(desc,bytes) else desc
            print(f'  CALLER: {cnb}->{mn}{desc}')
            print(f'    --- bytecode ---')
            for i, ins in enumerate(insns):
                out = ins.get_output()
                print(f'    {i:4d} {ins.get_name():22s} {out}')
            print(f'    --- end ---')
            print()
