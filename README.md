# LINE Rangers Bot + Headless API

บอตอัตโนมัติ LINE Rangers (`com.linecorp.LGRGS`) บนอีมูเลเตอร์ MuMu หลายจอ
พร้อม **ไคลเอนต์ REST API ยิงตรง** — ล็อกอิน + รับของ โดยไม่ต้องเปิดเกม

> 📌 **เอกสารแกะระบบ/API ทั้งหมด → [`LGR-API-NOTES.md`](LGR-API-NOTES.md)**
> 📌 **บริบทสำหรับ Claude Code → [`CLAUDE.md`](CLAUDE.md)** (อ่านอัตโนมัติทุกเครื่องที่ clone)

## ส่วนบอตกดจอ (GUI)
| ไฟล์ | หน้าที่ |
|---|---|
| `login.py` | launcher หลัก — เชื่อม adb, ปล่อยบอทต่อจอ (เริ่มทีละจอหน่วง 5s กันเน็ตดึง) |
| `ranger-gear.py` / `rangerplus.py` | โหมดหาตัว/เกียร์ (ใช้โค้ด popup ร่วมกับ login.py) |
| `autoupdate-lg.bat` | เครื่องบอตดึงอัปเดตจาก GitHub |

## ส่วน Headless REST API (ใหม่ — ไม่ต้องเปิดเกม)
| ไฟล์ | หน้าที่ |
|---|---|
| `lgr_api.py` | `LGRClient(udid, lf_ac)` — `.home()`, `.giftbox_list()`, `.receive_all_gifts()` |
| `capture_run.py` | จับ credential ของ 1 เครื่องอัตโนมัติ (ตั้ง MITM+routing ให้เอง) → `creds.json` |
| `capture_credential.py` | mitmproxy addon (ตัวเก็บ udid+LF_AC) |
| `collect_all.py` | รับของทุกบัญชีใน `creds.json` รวดเดียว (ขนาน) |

### ใช้งาน
```bash
# 1) จับ credential (ครั้งเดียว/บัญชี) — เปิดเกมกด PLAY ให้ล็อกอิน 1 ครั้ง แล้ว Ctrl+C
python capture_run.py 127.0.0.1:16512

# 2) รับของทุกบัญชี (ทำซ้ำได้เรื่อย ๆ ไม่ต้องเปิดเกม)
python collect_all.py
```
ต้องมี: `pip install mitmproxy requests` ; อีมูฯ root ได้

⚠️ **`creds.json` มี cookie บัญชีจริง — .gitignore ไว้แล้ว ห้าม push**
⚠️ บัญชีที่ใช้ API อย่าเปิดเกมพร้อมกัน (credential หมุนจะชนกัน)
