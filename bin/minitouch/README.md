# minitouch binaries

วางไฟล์ `minitouch` (binary ของ Android) ตาม ABI ของอีมูเลเตอร์ที่ใช้:

```
bin/minitouch/x86_64/minitouch
bin/minitouch/x86/minitouch
bin/minitouch/arm64-v8a/minitouch
bin/minitouch/armeabi-v7a/minitouch
```

LDPlayer / Nox / MEmu ส่วนใหญ่เป็น **x86_64** หรือ **x86**
เช็ค ABI ของเครื่องได้ด้วย:

```
adb -s <device> shell getprop ro.product.cpu.abi
```

## เอา binary มาจากไหน

minitouch เป็นส่วนหนึ่งของโปรเจกต์ [openstf/minitouch](https://github.com/openstf/minitouch)
(ตัว prebuilt มักมาพร้อมกับ STF หรือ airtest — ในแพ็กเกจ airtest จะอยู่ที่
`airtest/core/android/static/stf_libs/<abi>/minitouch`)

## ถ้าไม่มีไฟล์

ไม่ต้องทำอะไร — บอทจะขึ้น log ว่า

```
[<device>] minitouch unavailable (no binary for abi 'x86_64' ...) - using ADB taps
```

แล้วกลับไปใช้ `adb shell input tap` แบบเดิมอัตโนมัติ ไม่พัง

## เปิด/ปิด

ตั้งใน `ranger-gear_config.json`:

```json
"minitouch": 1
```

หรือกดสวิตช์ **⚡ Minitouch (กดเร็ว)** ในหน้า Config ของโปรแกรม
