# main_py/

ไฟล์ Python ที่ไม่ได้ถูก import โดยบอตหลัก (login.py / ranger-gear.py / rangerplus.py)
และไม่ได้ถูกเรียกโดย .bat ในรูท - เก็บไว้เผื่อใช้งาน dev/debug/legacy

## รายการ

### Debug / dev tools
- `backup.py` - สำรองไฟล์
- `capture_img.py` - จับภาพ debug
- `check-devices.py` - ตรวจอีมู ADB
- `check-match.py` - ทดสอบ OpenCV template match
- `check_proxy_rotation.py` - ทดสอบ proxy rotate
- `clear-app.py` - pm clear LGR app
- `fix-stuck-emu.py` - แก้อีมูค้าง
- `recapture_popup.py` - จับ popup ใหม่
- `test_auto_cap.py` - ทดสอบ auto-capture
- `test_ocr.py` - ทดสอบ EasyOCR

### Network / proxy (legacy)
- `free_proxy_scraper.py` - ดึง proxy list ฟรี
- `net_interface_rotator.py` - สลับ network interface
- `proxy_switcher.py` - สลับ Android http_proxy

### VPN (ไม่ได้ใช้ตั้งแต่ KILL_VPN_HARDCODED)
- `wg_key_server.py` - WG key sync server
- `wg_windscribe_fetch.py` - ดึง Windscribe keys
- `windscribe_cli_rotator.py` - Windscribe CLI rotate
- `windscribe_gui_rotator.py` - Windscribe GUI rotate

## รันจาก main_py/

```cmd
cd main_py
python <script>.py
```

หรือจากรูท:

```cmd
python main_py\<script>.py
```
