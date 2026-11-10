# AI 하네스 규칙 및 트리거 (GEMINI.md)

## 1. `'마무리하자'` 세션 회고 트리거 (Session Wrap-Up Trigger)

사용자가 대화 중 **`"마무리하자"`**라고 입력하면 즉시 다음 절차를 수행해야 합니다:

1. **현재 세션의 실수와 교훈 복기**:
   - 세션 중 발생한 명령어/인코딩 오류, 도구 호출 실수, 코드 회귀(regression), Git/배포 누락 등을 빠짐없이 정리합니다.
2. **하네스 회고록 누적 기록**:
   - 글로벌 회고록: [LESSONS_LEARNED.md](file:///C:/Users/song9/.gemini/config/LESSONS_LEARNED.md)
   - 워크스페이스 회고록: [LESSONS_LEARNED.md](file:///c:/Users/song9/OneDrive/%EB%B0%94%ED%83%95%20%ED%99%94%EB%A9%B4/test-data/LESSONS_LEARNED.md)
   - 위 두 파일에 날짜별(`## [YYYY-MM-DD] 세션 기록`) 섹션으로 **실수(현상/원인) $\rightarrow$ 교훈(재발 방지 가드레일)**을 기록합니다.
3. **요약 보고**:
   - 기록된 내용과 파일 링크를 사용자에게 간결하게 보고합니다.

---

## 2. 공통 재발 방지 가드레일 (Core Guardrails)

- **PowerShell UTF-8 인코딩 강제**:
  - 리다이렉션(`>`) 대신 `Set-Content -Encoding utf8`을 사용하고, 파이프 실행 시 `[Console]::InputEncoding = [System.Text.Encoding]::UTF8; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8`을 선언합니다.
  - 멀티라인 Node.js 원라이너는 따옴표 소실을 막기 위해 `@' ... '@ | node -` Here-String 방식을 사용합니다.
- **Git & 단일 라인 코드 수정 시 무결성 검증**:
  - 작업 전·푸시 전 반드시 `git fetch --all --prune`으로 원격 상태를 확인합니다.
  - 압축된 코드([src/worker.js](file:///C:/Users/song9/AppData/Local/Cline/web/src/worker.js) 등)를 수정할 때는 인접 함수(`comments()` 등)가 누락되지 않았는지 `git diff`로 반드시 대조합니다.
- **배포 완료 기준**:
  - Git 커밋/푸시만으로 완료 처리하지 않고, `npx wrangler deploy` 후 실제 프로덕션 URL(`https://...workers.dev`)을 대상으로 응답 헤더 및 API E2E 호출을 실측 검증합니다.
