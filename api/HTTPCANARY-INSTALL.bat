@echo off
setlocal

echo ============================================================
echo   HTTPCANARY install - VPN-based HTTPS interceptor ใน MuMu
echo   จับ LGR POST /login + guestCookie plaintext ได้โดยไม่ต้อง frida
echo ============================================================
echo.

set "SER=127.0.0.1:7555"
set "APK=C:\Users\Administrator\Downloads\LGR\api\HttpCanary.apk"

echo [1] check APK ที่ต้อง download ก่อน:
echo.
echo    วิธี download HttpCanary:
echo      1) Chrome → https://httpcanary.com/
echo      2) หรือ APKMirror: search "HttpCanary 3.3.6"
echo      3) save เป็น: %APK%
echo.
echo    (หรือใช้ตัวอื่น: PCAPdroid, Reqable, Charles Proxy Android)
echo.
if not exist "%APK%" (
    echo [X] ยังไม่มี APK → download ก่อน แล้วรัน script นี้อีกครั้ง
    echo.
    echo    ทางเลือก: ติดตั้งจาก Google Play Store ใน MuMu ตรง ๆ
    echo       1) ใน MuMu → Play Store → search "HttpCanary"
    echo       2) install → เปิด → ข้าม
    echo       ข้าม step [2]-[3] ไปเลย
    pause
    exit /b 1
)

echo [2] install HttpCanary ใน MuMu ...
adb -s %SER% install -r "%APK%"

echo.
echo [3] grant permissions ...
adb -s %SER% shell "pm grant com.guoshi.httpcanary android.permission.WRITE_EXTERNAL_STORAGE" 2>nul
adb -s %SER% shell "pm grant com.guoshi.httpcanary android.permission.READ_EXTERNAL_STORAGE" 2>nul

echo.
echo ============================================================
echo   NEXT STEPS (ใน MuMu)
echo ============================================================
echo.
echo   1) เปิด HttpCanary (icon ใหม่ใน home)
echo.
echo   2) หน้าแรก → More ^(icon ขวาบน^) → Target Apps
echo        เลือก "LINE Rangers" เป็น target เดียว
echo        (ไม่อย่างนั้นจะจับ app อื่นปนเข้ามา)
echo.
echo   3) Settings → SSL Proxying → ติ๊ก Enable
echo        → Install Root Certificate → Install to system
echo          (needs root → MuMu รองรับอยู่แล้ว)
echo.
echo   4) กดปุ่ม ▶ (play) หน้าแรก → เริ่มจับ
echo        VPN prompt ขึ้น → Allow
echo.
echo   5) เปิด LGR → เล่นอะไรก็ได้ 10 วิ
echo.
echo   6) กดปุ่ม ■ (stop) → กลับไปหน้า Sessions
echo        จะเห็น list requests
echo        filter: Host = rangers-api.line-apps.com
echo.
echo   7) tap /login → tab Request → tab Body
echo        เห็น JSON: udid + guestCookie plaintext
echo.
echo   8) copy udid + guestCookie → ยิง:
echo        python api\xml_fire.py --udid U --guest G --gift
echo.
echo ============================================================
pause
