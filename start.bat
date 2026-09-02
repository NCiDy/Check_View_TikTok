@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title TikTok Account Manager
color 0b

echo ================================================================
echo              TIKTOK ACCOUNT MANAGER - NOI BO
echo ================================================================
echo.

set "PY_CMD="

:: Chi dung Python Portable khi runtime thuc su doc duoc standard library.
if exist ".python\python.exe" (
    ".python\python.exe" -c "import encodings, sys; assert sys.version_info[:2] == (3, 11)" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=.python\python.exe"
)

:: Neu Portable bi thieu python311.zip, thu Python 3.11+ da cai tren may.
if not defined PY_CMD (
    python -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python"
)

:: Khong co runtime hop le: tai lai Python Embedded day du va ghi de phan bi thieu.
if not defined PY_CMD (
    echo [!] Python Portable hien tai bi thieu standard library ^(encodings/python311.zip^).
    echo [*] Dang tai lai Python 3.11 Embedded chinh thuc ^(khoang 11 MB^)...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip', 'python_embed_temp.zip')"
    if not exist "python_embed_temp.zip" (
        echo [X] Khong tai duoc Python. Kiem tra Internet roi chay lai start.bat.
        pause
        exit /b 1
    )

    if not exist ".python" mkdir ".python"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path 'python_embed_temp.zip' -DestinationPath '.python' -Force"
    del /f /q "python_embed_temp.zip" >nul 2>&1

    powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path '.python\python311._pth') { (Get-Content '.python\python311._pth') -replace '^#import site$', 'import site' | Set-Content '.python\python311._pth' -Encoding ASCII }"

    ".python\python.exe" -c "import encodings, sys; assert sys.version_info[:2] == (3, 11)" >nul 2>&1
    if errorlevel 1 (
        echo [X] Python Portable van bi loi sau khi tai lai.
        pause
        exit /b 1
    )
    set "PY_CMD=.python\python.exe"
)

:: Cai pip neu Python Embedded moi chua co pip.
"%PY_CMD%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [*] Dang cai PIP...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://bootstrap.pypa.io/get-pip.py', 'get-pip.py')"
    if not exist "get-pip.py" (
        echo [X] Khong tai duoc PIP. Kiem tra Internet roi chay lai.
        pause
        exit /b 1
    )
    "%PY_CMD%" get-pip.py --no-warn-script-location
    del /f /q "get-pip.py" >nul 2>&1
    if errorlevel 1 (
        echo [X] Cai PIP that bai.
        pause
        exit /b 1
    )
)

echo [1/3] Dang cai/cap nhat thu vien...
"%PY_CMD%" -m pip install -r requirements.txt --quiet --no-warn-script-location
if errorlevel 1 (
    echo [X] Cai thu vien that bai. Kiem tra log phia tren va ket noi Internet.
    pause
    exit /b 1
)

if not exist ".env" (
    echo.
    echo [2/3] Chua co .env. Bat dau setup Supabase va tai khoan BOSS...
    "%PY_CMD%" scripts\setup_local.py
    if errorlevel 1 (
        echo [X] Setup chua hoan tat.
        pause
        exit /b 1
    )
) else (
    echo [2/3] Da co file .env.
)

echo [3/3] Dang khoi dong server...
start "" http://127.0.0.1:8088
echo.
echo [OK] Mo website tai http://127.0.0.1:8088
echo [i] Khong tat cua so nay khi dang su dung.
echo ================================================================
echo.

"%PY_CMD%" server.py
pause
