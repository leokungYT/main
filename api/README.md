# api/ — LINE Rangers REST API toolset

ยิง API ตรง (ไม่เปิดเกม) + จับ credential + reroll. แยกออกจากบอทกดจอ (login.py/ranger-gear.py ที่อยู่ root)

## ไฟล์
| ไฟล์ | หน้าที่ |
|---|---|
| `lgr_api.py` | REST client หลัก (`LGRClient`) — login/home/giftbox ฯลฯ |
| `test_login.py` | เทส login ทุกบัญชีใน creds.json |
| `collect_all.py` | login + รับของทั้งหมด (วน creds.json ขนาน) |
| `capture_auto.py` | **ตัวหลัก** — จับ credential auto (inject XML / reroll / ปัจจุบัน) |
| `capture_credential.py` | mitmproxy addon เก็บ udid+LF_AC+guestCookie -> creds.json |
| `capture_flow.py` | mitmproxy addon log ทราฟฟิกทั้งหมด (ไว้แกะ flow ใหม่ เช่น gacha) |
| `capture_run.py` | ตัวเก่า: MITM+routing 1 เครื่อง แบบ manual |
| `capture-auto.bat` | ดับเบิลคลิกรัน capture_auto.py |
| `creds.json` | credential ที่จับได้ (gitignore) |
| `LGR-API-NOTES.md` | โน้ตการแกะระบบทั้งหมด |

## ทรัพยากรร่วม (อยู่ที่ root โปรเจค `../`)
`adb/` `img/` `input-id/` `login-success/` `login.py` — capture_auto.py ชี้ไปที่ `../` อัตโนมัติ (ตัวแปร `ROOT`)

## ใช้งาน
```bash
cd api
python capture_auto.py                 # วนจับทุก .xml ใน ../input-id/ -> creds.json
python capture_auto.py --reroll 5      # สร้าง guest ใหม่ 5 รอบ -> creds.json + ../login-success/*.xml
python test_login.py                   # เทส login
python collect_all.py                  # รับของทุกบัญชี
```

## ต้องมี
- `pip install mitmproxy` (สำหรับ capture_*)
- emulator root (adb root / su)
