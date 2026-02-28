@echo off
chcp 65001 >nul
title Auto Update Checker
cd /d "%~dp0"

echo =========================================
echo       [ กำลังตรวจสอบเวอร์ชั่นล่าสุด ]
echo =========================================

:: เช็คว่าโฟลเดอร์นี้เป็น Git repository หรือเปล่า
if not exist ".git" (
    echo [ ❌ ไม่สามารถอัพเดทได้: โฟลเดอร์นี้ไม่ได้เชื่อมต่อกับ Git (อาจจะโหลดมาเป็น ZIP หรือก๊อปปี้มาไม่ครบ) ]
    echo [ ✅ ข้ามขั้นตอนอัพเดท... ]
    echo.
    goto start_program
)

:: ดึงสถานะล่าสุดจาก Github มาเทียบ แต่ยังไม่ได้โหลดไฟล์ทับ
git fetch origin main >nul 2>&1

:: เช็คว่ามีเวอร์ชั่นอัพเดทค้างอยู่กี่ commit
for /f "tokens=*" %%g in ('git rev-list HEAD...origin/main --count') do (set UPDATE_COUNT=%%g)
if "%UPDATE_COUNT%"=="" set UPDATE_COUNT=0

if %UPDATE_COUNT% GTR 0 (
    echo [! พบอัพเดทใหม่บน Github ]
    
    :: โชว์ Popup ให้เลือกว่าจะอัพเดทหรือไม่
    python -c "import tkinter as tk; from tkinter import messagebox; root=tk.Tk(); root.attributes('-topmost', 1); root.withdraw(); res=messagebox.askyesno('แจ้งเตือนอัพเดทใหม่!', 'พบโค้ดเวอร์ชั่นใหม่ล่าสุดอยู่บน Github\nคุณต้องการอัพเดทโปรแกรมในเครื่องนี้ให้เป็นอันใหม่เลยหรือไม่?\n\n[ Yes ] = บังคับอัพเดทดึงไฟล์ใหม่มาทับให้หมด\n[ No ] = ไม่สนใจการอัพเดท รันโปรแกรมด้วยเวอร์ชั่นเดิม'); import sys; sys.exit(0 if res else 1)"
    
    :: เช็คคำตอบจากผู้ใช้: ถ้ากด Yes (errorlevel 0) จะรันการอัพเดท
    if not errorlevel 1 (
        echo [ 🔄 กำลังดึงไฟล์เวอร์ชั่นใหม่มาทับของเดิมทั้งหมด... ]
        git reset --hard origin/main
        git pull origin main
        echo [ ✅ อัพเดทเสร็จสมบูรณ์! ]
    ) else (
        echo [ ❌ ยกเลิกการอัพเดท ขอใช้โค้ดดั้งเดิมต่อไป ]
    )
) else (
    echo [ ✅ โปรแกรมของคุณเป็นเวอร์ชั่นล่าสุดอยู่แล้ว ]
)

:start_program
echo.
echo =========================================
echo       [ กำลังเปิดโปรแกรม... ]
echo =========================================
echo.

:: รันโปรแกรมหลักในหน้าต่างดำเดิมนี้เลย จะได้เห็นข้อความ Echo ค้างไว้
python login.py
pause
