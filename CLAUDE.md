# CLAUDE.md — บริบทโปรเจกต์ (Claude Code อ่านไฟล์นี้อัตโนมัติทุกเครื่องที่ clone)

บอตอัตโนมัติ **LINE Rangers** (`com.linecorp.LGRGS`) รันบนอีมูเลเตอร์ MuMu หลายจอ + มีไคลเอนต์ REST API ยิงตรง

## Deploy / โครงสร้างการรัน
- โค้ดนี้ = source (repo `github.com/leokungYT/main`). บอตจริงรันบนเครื่องรีโมทหลายเครื่อง ดึงจาก `origin/main` ผ่าน `autoupdate-lg.bat`
- **แก้แล้วยังไม่ live จนกว่าจะ commit + push + (เครื่องบอต) autoupdate/pull + restart**
- โค้ด popup/บอตใช้ร่วม 3 ไฟล์: `login.py` / `ranger-gear.py` / `rangerplus.py` — แก้เรื่อง popup/startup ต้องแก้ให้ครบทั้งสาม (ไฟล์ ranger เป็น CRLF)

## บอต (กดจอ)
- `login.py` = launcher หลัก (GUI): รอ MuMu บูต → เชื่อม adb → ปล่อยบอทต่อจอ
- ปัญหาคลาสสิก: เปิดหลายจอพร้อมกัน → แย่ง adb → `screencap` ค้าง → บอทเห็นเฟรมเก่า "ไม่กดอะไรเลย" + เน็ตดึง
  แก้แล้วด้วย: เริ่มบอตทีละจอหน่วง `start_stagger` (default 5s) + boot-wait ออกเร็วเมื่อจำนวนที่พร้อมหยุดเพิ่ม
- safety: ไม่กดอะไร 500s → clear+restart (login.py `RestartTimeoutError`)

## REST API แบบ headless (ยิงตรง ไม่ต้องเปิดเกม) — ★ ของใหม่
พิสูจน์แล้ว 2026-09-14: **ล็อกอิน + รับของ ผ่าน API ได้จริง** (ดูรายละเอียดเต็มใน `LGR-API-NOTES.md`)
- server `https://rangers-api.line-apps.com/v12.3/<path>` ; auth = **cookie เท่านั้น** `Cookie: udid=<uuid>; LF_AC=<session>` **ไม่มีลายเซ็น/HMAC**
- `LF_AC` = session ยิง `/home`, `/giftbox/list`, `POST /giftbox/gift/receive/all` ได้ตรง ๆ ; เซิร์ฟหมุนค่าใหม่ทาง Set-Cookie ทุก request (ต้องเก็บค่าใหม่)
- credential หมุน → **บัญชีที่ใช้ API อย่าเปิดเกมพร้อมกัน**
- เครื่องมือ: `capture_run.py` (จับ udid+LF_AC ต่อบัญชี → `creds.json`, ครั้งเดียว) , `collect_all.py` (รับของทุกบัญชี) , `lgr_api.py` (`LGRClient`) , `capture_credential.py` (mitmproxy addon)
- **`creds.json` มี cookie บัญชีจริง — อยู่ใน .gitignore ห้าม push**

## Reverse engineering ที่ทำไปแล้ว (อย่าเสียเวลาซ้ำ)
- frida ใช้ไม่ได้บน MuMu x86: libgame.so เป็น arm64 รันผ่าน native-bridge (frida x86 มองไม่เห็น) + LIAPP kill โปรเซสเมื่อเจอ frida
- MITM ผ่านได้โดย**ไม่ต้อง bypass pin** ด้วย reverse-proxy (เกมยอมรับ cert ของ mitmproxy) — วิธีตั้งอยู่ใน `capture_credential.py` / `capture_run.py`
- ตาราง `.db` ทรัพยากรเป็น SQLCipher (คีย์ยังไม่ได้), `.ndb` เป็น SQLite เปล่าอ่านได้ (เช่น `lang_unit.ndb` = ชื่อตัวละครทุกภาษา)

## หมายเหตุ
- ADB ของ repo อยู่ที่ `adb/adb.exe` ; อีมูฯ ตัวอย่าง `127.0.0.1:16512` (root ได้, SELinux permissive)
- เอกสารแกะระบบทั้งหมด: `LGR-API-NOTES.md`
