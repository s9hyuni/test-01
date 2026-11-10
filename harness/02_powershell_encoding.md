# 하네스 규칙 02: 인코딩 및 명령어 실행 가드레일 (PowerShell & Encoding)

윈도우 PowerShell 환경에서 문자열 깨짐과 명령어 오동작을 원천 차단하기 위한 규칙입니다.

---

## 1. PowerShell UTF-8 인코딩 강제
- 파일 저장 시 PowerShell 리다이렉션(`>`)을 쓰지 않고 반드시 `Set-Content -Encoding utf8`을 사용합니다.
- 파이프(`|`) 또는 외부 프로그램 호출 시 콘솔 입출력 인코딩을 UTF-8로 선언합니다:
  ```powershell
  [Console]::InputEncoding = [System.Text.Encoding]::UTF8; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  ```

## 2. 멀티라인 Node.js 원라이너 가드레일
- 따옴표 이스케이프 유실로 인한 구문 오류(`TerminatorExpectedAtEndOfString`)를 방지하기 위해 임시 `.js` 파일을 작성해 실행하거나 Here-String을 사용합니다:
  ```powershell
  @'
  const fs = require('fs');
  // 코드 본문
  '@ | node -
  ```
