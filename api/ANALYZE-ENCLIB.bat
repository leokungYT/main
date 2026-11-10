@echo off
setlocal

set "LIB=C:\Users\Administrator\Downloads\LGR\api\apk\arm64\lib\arm64-v8a\libline-sdk-encryption.so"
set "OUT=C:\Users\Administrator\Downloads\LGR\api\enc_analysis.txt"

echo ============================================================
echo   ANALYZE - libline-sdk-encryption.so (9688 bytes, เล็กมาก!)
echo ============================================================
echo.

if not exist "%LIB%" (
    echo [ERROR] ไม่เจอ %LIB%
    pause
    exit /b 1
)

> "%OUT%" echo === libline-sdk-encryption.so analysis ===
echo. >> "%OUT%"
echo === STRINGS (printable ASCII + UTF16) === >> "%OUT%"

echo [1] extract ASCII strings ...
powershell -Command "Get-Content -Encoding Byte '%LIB%' | ForEach-Object { if ($_ -ge 32 -and $_ -le 126) { [char]$_ } else { \"`n\" } } | Out-String" > "%TEMP%\strs.txt" 2>nul

REM แทนที่ด้วย python ซึ่งเร็วกว่า
python -c "import re; d=open(r'%LIB%','rb').read(); [print(s.decode()) for s in re.findall(rb'[\x20-\x7e]{6,}', d)]" >> "%OUT%" 2>&1

echo. >> "%OUT%"
echo === EXPORTED SYMBOLS (via python elftools) === >> "%OUT%"
python -c "from elftools.elf.elffile import ELFFile; f=open(r'%LIB%','rb'); elf=ELFFile(f); [print(s.name) for s in elf.get_section_by_name('.dynsym').iter_symbols() if s.name and s['st_info']['bind']=='STB_GLOBAL']" >> "%OUT%" 2>&1

if errorlevel 1 (
    echo elftools ไม่มี - pip install pyelftools
    echo. >> "%OUT%"
    echo === EXPORTED SYMBOLS fallback with regex === >> "%OUT%"
    python -c "import re; d=open(r'%LIB%','rb').read(); print('\n'.join(set(m.decode() for m in re.findall(rb'[A-Za-z_][A-Za-z0-9_]{3,100}', d) if b'ncrypt' in m or b'ecrypt' in m or b'Key' in m or b'Aes' in m or b'AES' in m)))" >> "%OUT%"
)

echo.
echo saved to: %OUT%
echo.
echo === TOP interesting strings ===
findstr /i /r "aes key cipher encrypt decrypt" "%OUT%" | more

pause
