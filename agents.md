# AI 하네스 마스터 가이드 (agents.md)

이 문서는 모든 AI 에이전트와 엔지니어가 시스템을 유지보수할 때 참조해야 하는 **기준 인덱스(Root Index) 문서**입니다. 세부 하네스 규칙과 아키텍처는 목적별 분할 파일로 관리되며, 본 문서의 링크를 통해 탐색합니다.

---

## 1. 하네스 모듈별 색인 (Index of Harness Modules)

각 파일은 독립된 단일 책임을 가지며, 시스템 변경 전 반드시 해당 규칙을 검토해야 합니다.

| 분할 모듈 | 주요 내용 | 링크 |
| :--- | :--- | :--- |
| **01. 세션 회고 규칙** | `'마무리하자'` 트리거 실행 절차 및 실수 복기 기준 | [harness/01_session_wrapup.md](harness/01_session_wrapup.md) |
| **02. 인코딩 및 명령어** | PowerShell UTF-8 강제 및 Node 원라이너 오류 방지 | [harness/02_powershell_encoding.md](harness/02_powershell_encoding.md) |
| **03. Git & 배포 실측** | 원격 사전 fetch, 회귀 검증, E2E 실측 배포 완료 기준 | [harness/03_git_and_deployment.md](harness/03_git_and_deployment.md) |
| **04. 망분리 듀얼 네트워크** | 사무실망/현장망 게이트웨이 분리 및 USB 허브 구성 | [harness/04_dual_network_setup.md](harness/04_dual_network_setup.md) |
| **05. 인증 및 사번 보안** | 생년월일 초기비번, 텐키패드, 4회 경고/6회 잠금 정책 | [harness/05_auth_and_security.md](harness/05_auth_and_security.md) |
| **06. 무중단 자동 시작·와치독** | 윈도우 부팅 시 Silent 자동 실행 및 크래시 시 5초 자동 재시작 | [harness/06_autostart_watchdog.md](harness/06_autostart_watchdog.md) |

---

## 2. 핵심 엔지니어링 명세 문서

시스템의 상세 비즈니스 로직과 데이터베이스 구조는 다음 기준 문서를 참조합니다.

- **[DOSKO_HARNESS_ENGINEERING.md](DOSKO_HARNESS_ENGINEERING.md)**: 1, 2, 3, 5, 6, 7호기 열처리 설비 사양, 5단계 생산 프로세스, 18개 클라이언트 타겟 동기화 체계
- **[도스코_이카운트_호환DB_및_공정별_설계계획서.md](도스코_이카운트_호환DB_및_공정별_설계계획서.md)**: MSSQL 2019 Standard 및 이카운트 ERP 호환 테이블 명세
- **[LESSONS_LEARNED.md](LESSONS_LEARNED.md)**: 엔지니어링 세션 누적 회고록 (실수와 재발 방지 가드레일)
- **[README.md](README.md)**: 사내 로컬(8089) 및 클라우드 서비스 접속 주소와 개발 가이드

---

## 3. 에이전트 행동 가이드라인

1. **기준 우선**: 모든 작업 전 본 `agents.md`와 해당 하네스 모듈을 먼저 읽고 가드레일을 준수합니다.
2. **단일 출처 유지**: 규칙이 변경될 경우 세부 파일(`harness/*.md`)을 먼저 수정하고 본 인덱스를 갱신합니다.
3. **작업 완료 기준**: 코드 커밋 후 반드시 실제 프로덕션 및 네트워크 상태를 직접 실측하여 완료를 보고합니다.
