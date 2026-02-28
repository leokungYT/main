@echo off
:: โค้ดส่วนนี้จะทำให้หน้าต่างดำ (CMD) ซ่อนตัวไปเลย
if "%1" == "h" goto begin
mshta vbscript:createobject("wscript.shell").run("""%~nx0"" h",0)(window.close)&&exit
:begin

:: ย้ายไปที่โฟลเดอร์ปัจจุบัน
cd /d "%~dp0"

:: รันโปรแกรม login.py (หน้าต่างดำจะโดนซ่อน จะเห็นแค่หน้าต่าง GUI)
python login.py
