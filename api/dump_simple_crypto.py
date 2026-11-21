"""Dump SimpleCrypto class bytecode to find the hardcoded key."""
import sys, io, os, logging
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
try:
    from loguru import logger; logger.remove()
except: pass
logging.disable(logging.CRITICAL)
from androguard.core.dex import DEX

TARGET_CLASS = b'Lorg/cocos2dx/lib/linecocos/utils/SimpleCrypto;'

with open('api/libs_extracted/classes5.dex','rb') as f: data = f.read()
dex = DEX(data)
for cls in dex.get_classes():
    cn = cls.get_name()
    cnb = cn if isinstance(cn,(bytes,bytearray)) else cn.encode()
    if cnb != TARGET_CLASS: continue
    print(f'=== {cnb.decode()} ===')
    # list fields (hardcoded constants may be stored as static final fields)
    try:
        for fld in cls.get_fields():
            fn = fld.get_name()
            fn = fn.decode() if isinstance(fn,(bytes,bytearray)) else fn
            print(f'  FIELD: {fn}  access={fld.get_access_flags_string()}')
    except Exception as e: print(f'  (fields err: {e})')

    for m in cls.get_methods():
        mn = m.get_name()
        mn = mn.decode() if isinstance(mn,(bytes,bytearray)) else mn
        desc = m.get_descriptor()
        desc = desc.decode() if isinstance(desc,(bytes,bytearray)) else desc
        print(f'\n--- METHOD: {mn}{desc} ---')
        code = m.get_code()
        if not code:
            print('  (no code)')
            continue
        try:
            insns = list(code.get_bc().get_instructions())
        except Exception as e:
            print(f'  (insns err: {e})')
            continue
        for i, ins in enumerate(insns):
            print(f'    {i:4d} {ins.get_name():22s} {ins.get_output()}')
    break
