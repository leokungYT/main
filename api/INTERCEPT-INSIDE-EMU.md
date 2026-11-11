# จับ LGR /login จากข้าง MuMu — 3 ทางเลือก (เรียงจากง่าย→ยาก)

เหตุผลที่ frida+MITM ภายนอกไม่เวิร์ก:
- MuMu = x86_64 host รัน arm64 .so ผ่าน native-bridge (libtzyxaxtyd.so)
- BoringSSL arm64 buffer เป็น mapped region ที่ frida x86_64 scan ไม่เจอ runtime body
- iptables REDIRECT ใน MuMu kernel ไม่มี xt_owner → scope UID ไม่ได้
- cocos ignore system HTTP proxy

วิธีที่ **เวิร์กแน่** คือ ติดตั้ง VPN-based interceptor **ใน MuMu เอง**

---

## ทางเลือก 1 — PCAPdroid (ฟรี, open source, no root)

1. ใน MuMu → Play Store → search **"PCAPdroid"** (by Emanuele Faranda)
2. Install
3. เปิด → Target App: select **LINE Rangers**
4. Settings → Decryption → **enable TLS decryption** (ติด mitm addon)
5. ปุ่ม Start → VPN prompt → Allow
6. เปิด LGR → เล่น 10 วิ
7. Stop → ดู flow → tap `POST /login` → see body

APK: https://play.google.com/store/apps/details?id=com.emanuelef.remote_capture

## ทางเลือก 2 — Reqable (ฟรี, modern UI)

1. ใน MuMu → Play Store → search **"Reqable"**
2. Install → เปิด
3. ติ๊ก: Capture HTTPS, Install certificate (system — needs MuMu root)
4. Start capture → เปิด LGR → request โผล่
5. tap /login → Request Body → copy json

APK: https://reqable.com/

## ทางเลือก 3 — HttpCanary (ลด support แล้ว, แต่เก่าๆ ก็ยังใช้ได้)

1. download APK: search `HttpCanary 3.3.6 apkmirror`
2. ลาก APK ลง MuMu window → auto install
3. หรือ: `adb -s 127.0.0.1:7555 install HttpCanary.apk`
4. เปิด → Target App: LINE Rangers → SSL install cert → ▶

---

## หลังได้ guestCookie:

```
python C:\Users\Administrator\Downloads\LGR\api\xml_fire.py ^
       --udid <UDID_from_request> ^
       --guest <GUEST_from_body> ^
       --gift
```

## ถ้ายังจับไม่ได้ (cocos pin cert):

ใช้ frida + `frida-boringssl-sslunpin.js` ต่ออีก layer:
- hook `SSL_CTX_set_verify` ใน libssl.so ของ cocos native stack
- override cert verify callback → return 1 (OK) เสมอ
- ขอ ถ้าถึงจุดนี้
