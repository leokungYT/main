# ท่า B shortcut — dump XXTEA/AES key ของ _ENC_LF_AC_KEY ใน 1 ชั่วโมง

## เป้าหมาย

หา key ที่เกมใช้ encrypt `_ENC_LF_AC_KEY` ใน SharedPreferences XML
→ ถอดเองใน Python → ยิง API ได้โดยไม่ต้องเปิด MuMu เลย

---

## ท่าลัด 3 ขั้น (ไม่ต้อง RE Ghidra)

### ขั้น 0 — ลอง default Cocos keys ก่อน (5 นาที, ฟรี, ไม่เสีย)

```bash
python api/decrypt_lfac.py input-id/some.xml --try-defaults
```

ถ้ามี `[HIT]` = จบ, ได้ key แล้ว ไม่ต้อง Frida
ถ้าไม่มี = ไปขั้น 1

---

### ขั้น 1 — เตรียม Frida (10 นาที, ครั้งเดียว)

**บน PC:**
```bash
pip install frida-tools
```

**บน MuMu (root):**
```bash
# โหลด frida-server-16.x-android-x86_64 จาก github.com/frida/frida/releases
adb push frida-server /data/local/tmp/
adb shell "su -c 'chmod +x /data/local/tmp/frida-server && /data/local/tmp/frida-server &'"
```

เช็ค frida เห็นเครื่อง:
```bash
frida-ps -U
```

---

### ขั้น 2 — hook + ดักกุญแจตอน login (15 นาที)

```bash
cd api
frida -U -f com.linecorp.LGRGS -l frida_dump_lfac_key.js --no-pause
```

**ดู output ที่น่าสนใจ:**

- `[SecretKeySpec AES] key hex=XXXXXX  ascii=YYYY` ← **key อยู่ตรงนี้ถ้าใช้ Java AES**
- `[Cipher.doFinal algo=AES/CBC/PKCS5Padding] input[:32] hex=... output str=XXXX` ← ciphertext + plain เทียบกับ xml
- `[hook] xxtea_decrypt ... arg3 (KEY?): aabbcc... | ....` ← **key ถ้าใช้ native XXTEA**

**ตรวจว่าใช่ key ของ `_ENC_LF_AC_KEY` ไหม:**

1. copy ciphertext hex จาก log (`input[:32]`)
2. เปิด xml → b64decode(`_ENC_LF_AC_KEY`) → hex 32 ตัวแรก
3. ถ้าตรง = ใช่ key นั้น ✓

---

### ขั้น 3 — เทส decrypt + batch (10 นาที)

```bash
# ลอง key ที่ dump ได้
python api/decrypt_lfac.py input-id/some.xml --key AABBCC...DD

# ได้ guestCookie → ยิง API
python -c "
from api.lgr_api import LGRClient
c = LGRClient(udid='<udid จาก xml>', lf_ac='')
code, data = c.login(guest_cookie='<guestCookie ที่ถอดได้>')
print(code, data)
"
```

ถ้า `code==200` + มี player data = **ท่า B สำเร็จ** → xml → API ตรงได้

---

## batch (ท่าเด็ด: ใช้ key เดียวถอดทุก xml ใน input-id/)

```python
import os, glob, xml.etree.ElementTree as ET
from decrypt_lfac import read_enc_lfac, decode_candidates, try_aes
from lgr_api import LGRClient

KEY_HEX = "<key ที่ Frida ดักได้>"
KEY = bytes.fromhex(KEY_HEX)

for xml in glob.glob("input-id/*.xml"):
    enc, _ = read_enc_lfac(xml)
    if not enc: continue
    cipher = next((c for _, c in decode_candidates(enc)), None)
    if not cipher: continue
    cookie, _ = try_aes(cipher, KEY, "cbc")
    if not cookie: continue
    # หา udid (อยู่คู่กันใน xml)
    tree = ET.parse(xml)
    udid = next((s.text for s in tree.iter("string") if s.attrib.get("name") == "udid"), None)
    if not udid: continue
    c = LGRClient(udid=udid, lf_ac="")
    code, data = c.login(guest_cookie=cookie.decode())
    ruby = data.get("result", {}).get("player", {}).get("ruby", "?") if isinstance(data, dict) else "?"
    print(f"{os.path.basename(xml):50s} code={code}  ruby={ruby}")
```

---

## ถ้า Frida ไม่เจอกุญแจเลย

เป็นไปได้ว่า:

1. **key อยู่ใน Lua script encrypted** → hook `xxtea_decrypt` จะเจอหลายครั้ง → filter เอาเฉพาะ call ที่ ciphertext ตรงกับใน xml
2. **key หมุนตาม device_id** → key = `HMAC(device_salt, android_id)` → ต้อง hook ก่อน SharedPreferences write ไม่ใช่ read
3. **native `.so` ใช้ JNI inline assembly** → Frida hook ไม่ติด → ขั้น C จริง (Ghidra, 2-3 สัปดาห์)

ถ้าถึงจุดนั้น → ส่ง log Frida มา จะดู call pattern ให้
