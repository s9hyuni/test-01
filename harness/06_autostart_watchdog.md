# 하네스 규칙 06: 서버 무중단 자동 기동 및 와치독 가드레일 (Auto-Start & Watchdog)

윈도우 부팅 시 사용자 개입 없이 서버가 백그라운드에서 자동 구동되고, 예기치 못한 크래시 발생 시 5초 이내 자동 부활하기 위한 운영 규칙입니다.

---

## 1. 윈도우 시작프로그램 연동 구조

- **시작 파일 위치**:
  `C:\Users\song9\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\도스코_실시간_동기화서버_자동시작.vbs`
- **구동 메커니즘**:
  - `wscript.exe`를 통해 콘솔 검은 창을 100% 숨김(Silent Background, `0, False`).
  - 와치독 감시 스크립트(`dosko_server_watchdog.bat`)를 호출하여 파이썬 서버 기동.

## 2. 와치독(Watchdog) 무한 감시 루프

- **스크립트**: [dosko_server_watchdog.bat](../dosko_server_watchdog.bat)
- **가드레일**:
  - `python dosko_sync_server.py`가 네트워크 타임아웃, 메모리 부족, 예외 등으로 비정상 종료 시,
  - `dosko_watchdog.log`에 에러 타임스탬프를 기록한 뒤 **5초 후 프로세스를 자동으로 즉시 재시작**합니다.
  - 로그 파일(`dosko_sync_server.log`)에 표준 출력/에러를 누적 기록하여 사후 추적성을 보장합니다.

## 3. 포트 점검 및 프로세스 확인
```powershell
# 8089 포트 리스닝 확인
netstat -ano | findstr 8089

# 와치독 로그 실시간 확인
Get-Content -Tail 20 dosko_watchdog.log
```
