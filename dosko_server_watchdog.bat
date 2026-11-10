@echo off
chcp 65001 > nul
set "WORK_DIR=c:\Users\song9\OneDrive\바탕 화면\test-data"
set "PYTHON_EXE=C:\Python315\python.exe"

cd /d "%WORK_DIR%"

:loop
echo [%date% %time%] (주)도스코 열처리 관제 동기화 서버 시작 중... >> dosko_watchdog.log
"%PYTHON_EXE%" dosko_sync_server.py >> dosko_sync_server.log 2>&1
echo [%date% %time%] 서버 프로세스가 비정상 종료되었습니다. 5초 후 자동 재시작합니다. >> dosko_watchdog.log
timeout /t 5 /nobreak > nul
goto loop
