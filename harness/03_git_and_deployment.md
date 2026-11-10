# 하네스 규칙 03: Git 협업 및 배포 실측 가드레일 (Git & Deployment)

저장소 무결성을 보장하고 프로덕션 배포 완료를 정밀 실측하기 위한 규칙입니다.

---

## 1. Git 푸시 전 원격 상태 사전 검증
- 작업 전과 푸시 전 반드시 원격 상태를 사전 검증합니다:
  ```powershell
  git fetch --all --prune
  ```
- 원격에 타 작업자나 다른 커밋이 있는 경우 force-push를 금지하고 안전하게 `git rebase` 또는 브랜치 분기 후 PR을 생성합니다.

## 2. 코드 수정 시 무결성 검증 (Regression 방지)
- 압축되었거나 거대한 소스 코드(`src/worker.js`, `dosko_sync_server.py` 등)를 수정할 때 인접 함수가 누락되지 않았는지 반드시 `git diff`로 대조 검증합니다.

## 3. 배포 완료 판정 기준
- Git 커밋 및 푸시만으로 작업을 완료 처리하지 않습니다.
- Cloudflare 배포의 경우 `npx wrangler deploy` 후 실제 프로덕션 URL(`https://...workers.dev`)을 대상으로 `curl` 응답 헤더 및 API E2E 호출을 직접 측정하여 확인합니다.
- 사내 관제 서버의 경우 `netstat -ano | findstr 8089`로 프로세스 리스닝 상태를 실측합니다.
