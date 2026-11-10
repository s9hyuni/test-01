# AI 하네스 세션 회고록: 실수와 교훈 (Mistakes & Lessons Learned)

이 문서는 매 세션에서 발생한 시행착오, 버그, 환경적 함정, 그리고 이를 통해 정립한 재발 방지 가드레일을 누적 기록하는 하네스 엔지니어링 지식 베이스입니다.
사용자가 **`"마무리하자"`**라고 말하면 PreInvocation 훅([.agents/hooks.json](file:///c:/Users/song9/OneDrive/%EB%B0%94%ED%83%95%20%ED%99%94%EB%A9%B4/test-data/.agents/hooks.json))과 하네스 규칙에 의해 현재 세션의 실수와 교훈이 본 문서 및 글로벌 회고록([LESSONS_LEARNED.md](file:///C:/Users/song9/.gemini/config/LESSONS_LEARNED.md))에 자동으로 기록됩니다.

---

## [2026-11-09] 세션 기록 — `ai-study-profile` (SENIOR AI 2.0) 이슈 해결·검증·배포·브라우저 자동화

### 1. 주요 실수 (Mistakes)

1. **PowerShell 리다이렉션(`>`)의 UTF-16LE 인코딩 함정**
   - **현상**: `ego-browser skill > "$env:TEMP\ego-browser-skill.md"`로 출력물을 저장한 뒤 `read_file`로 읽으려 했으나, PowerShell 5.1의 `>` 연산자가 기본적으로 `UTF-16LE`로 파일을 생성해 바이너리 파일로 판정되어 읽기에 실패함.
   - **교훈**: PowerShell에서 텍스트 파일을 저장할 때는 반드시 `Set-Content -Encoding utf8` 또는 `Out-File -Encoding utf8`을 사용하거나 파이프로 직접 읽어야 함.

2. **PowerShell 인라인 스크립트 전달 시 따옴표 소실 및 한글 깨짐(Mojibake)**
   - **현상**:
     - `node -e '...'` 실행 시 PowerShell이 내부 큰따옴표(`"`)를 벗겨내어 Node.js 구문 에러(`SyntaxError`)가 발생함.
     - `.mjs` 스크립트를 `Get-Content -Raw ... | ego-browser nodejs`로 파이프 전달할 때 `[Console]::InputEncoding` / `[Console]::OutputEncoding`을 UTF-8로 지정하지 않아 한글 로케이터(`loc=css:button[aria-label="범용 선택 도구 열기"]`)가 `???`로 깨져서 매칭에 실패함.
   - **교훈**:
     - 멀티라인 Node 스크립트는 PowerShell Here-String(`@' ... '@ | node -`)을 사용해야 따옴표가 보존됨.
     - 파이프 입출력 전 반드시 `[Console]::InputEncoding = [System.Text.Encoding]::UTF8; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Content -Encoding UTF8 -Raw ...`를 선언하거나, 한글 텍스트 로케이터 대신 스냅샷의 `ref=<번호>` 로케이터를 우선 사용해야 함.

3. **`ego-browser` API 규격 오인 및 로케이터 문법 오류**
   - **현상**:
     - 스킬 문서를 먼저 확인하지 않고 `import { ego } from 'ego-browser/ego'` 또는 `ego-browser run`을 시도해 실패함 (실제 실행 방식은 `ego-browser nodejs`).
     - `task.newPage("p2")`처럼 인자를 넘겨 `TypeError: task.newPage does not accept arguments`가 발생함.
     - `loc=text:/sitemap.xml`처럼 잘못된 프리픽스를 써서 `Invalid locator` 오류가 발생함 (`text=/sitemap.xml` 또는 `ref=N` 사용이 맞음).
   - **교훈**: `ego-browser` 사용 시 반드시 `const task = await taskSpace("name")`, 기본 탭은 `task.page("p1")`, 추가 탭은 인자 없이 `await task.newPage()`로 생성하고, 클릭/입력 시 스냅샷에 나온 `ref=번호`를 최우선으로 사용하며 작업 후 `await task.finish({ keep: [] })`로 정리해야 함.

4. **원격 브랜치(`origin/main`) 병합 상태 미확인 및 병렬 작업 중 함수 유실 (`comments()`, `responseHeaders()`)**
   - **현상**:
     - 로컬에서 작업하는 사이 원격 `origin/main`에 다른 PR/커밋(`#5`~`#16`)이 병합되어 있었으나 `git fetch`를 먼저 하지 않아 non-fast-forward 충돌 및 루트/`public/` 이중 파일 혼선이 발생함.
     - 특히 이슈 `#10` 해결 커밋(`e30d171`)에서 한 줄로 압축된 `src/worker.js`의 `posts()`와 `createPost()`를 수정하면서, 그 사이에 있던 `comments(env, pid)` 함수와 `responseHeaders()` 헬퍼가 실수로 삭제되어 `GET /api/posts/:id/comments` 호출 시 500 `ReferenceError`가 발생하는 회귀 버그가 생김.
   - **교훈**:
     - 작업 시작 전과 푸시 직전 반드시 `git fetch --all --prune`으로 원격 상태를 먼저 동기화해야 함.
     - 압축된(minified/single-line) 파일을 수정할 때는 인접 함수가 지워지지 않았는지 `git diff`로 모든 삭제/변경 라인을 대조하고, 단위 테스트뿐 아니라 전체 API 엔드포인트(`GET /api/posts/:id/comments` 포함) 통합 테스트를 실행해야 함.

5. **Cloudflare Workers Static Assets 라우팅(`run_worker_first`)과 원격 배포(`wrangler deploy`) 누락**
   - **현상**:
     - `src/worker.js`에 `withSecurityHeaders()`를 추가하고 단위 테스트까지 통과시켰으나, `wrangler.jsonc`의 `run_worker_first`에 `/api/*`만 지정되어 있어 실제 정적 HTML(`/`)과 CSS(`/style.css`) 요청은 Worker를 거치지 않고 보안 헤더 없이 응답됨.
     - 또한 GitHub에 커밋만 푸시하고 `npx wrangler deploy`를 실행하지 않아 라이브 서버에는 구버전이 남아 있었음.
     - 원격 D1 CLI 쿼리가 계정 토큰 권한 제약(`code: 7403`)으로 막힐 수 있는 상황에서 Worker 내부에 자동 테이블/컬럼 보정(`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN`) 안전장치가 없으면 배포 즉시 500 에러가 발생할 수 있었음.
   - **교훈**:
     - **"커밋 완료 ≠ 배포 완료"**: 이슈를 닫기 전에 반드시 `npx wrangler deploy` 후 실제 프로덕션 URL(`https://...workers.dev`)을 대상으로 `fetch` 헤더 및 API E2E 검증을 수행해야 함.
     - 정적 자산에도 Worker 보안 헤더를 강제하려면 `wrangler.jsonc`의 `assets.run_worker_first: true`를 설정해야 함.
     - D1 스키마 변경이 수반될 때는 Worker 런타임에 idempotent 자동 마이그레이션 폴백(`ensureRevokedSessionsTable`, `ensureQuestionTitleColumn`)을 함께 넣어 무중단 배포를 보장해야 함.

---

### 2. 핵심 재발 방지 체크리스트 (Checklist for Future Sessions)

- [ ] **Git 작업 전**: `git fetch --all --prune` 및 `git status`로 원격/로컬 브랜치 차이 확인
- [ ] **코드 수정 후**: `git diff`로 의도치 않게 삭제된 함수(`comments` 등)나 하드코딩된 로컬 경로(`C:\Users\...`)가 없는지 전수 확인
- [ ] **정적 자산 수정 시**: `Cache-Control: immutable`이 걸린 CSS/JS를 수정했다면 HTML의 `?v=...` 캐시 버스터 쿼리스트링도 함께 갱신
- [ ] **배포 및 이슈 종료 전**: 로컬 단위 테스트(`node --test`) 통과 $\rightarrow$ `npx wrangler deploy` 실행 $\rightarrow$ 라이브 URL 대상 HTTP 응답 헤더 및 핵심 API E2E 호출 검증 완료 후 종료

---

## [2026-11-09 (2차)] 세션 기록 — `(주)도스코(DOSKO_ERP)` MSSQL v2.0 스키마 이관·사번 RBAC 보안·대시보드 개편·E2E 검증

### 1. 주요 실수 및 시행착오 (Mistakes & Root Causes)

1. **문자열 길이(`len(str)`)와 UTF-8 바이트 길이(`len(str.encode('utf-8'))`) 혼동**
   - **현상/원인**: 대용량 아카이브 보호 라인(`Protected Archive Lines`) 무결성 검증 시, 사전 메타데이터에 기록된 `170,300`이 Python 문자열 문자 수(`len(clean)`)였음에도 패치 스크립트(`patch_dashboards.py`)에서 UTF-8 인코딩 바이트 수(`173,245`)와 단순 비교하여 1차 실행 시 불일치 예외가 발생함.
   - **해결 방법**: `(len(clean), len(raw_bytes), sha256_hex[:8])` 3중 시그니처 튜플로 문자 길이·바이트 길이·SHA-256 해시를 동시에 대조하도록 보정함.
   - **교훈(가드레일)**: 한글 등 멀티바이트 문자가 포함된 라인/파일 무결성 검증 시 `char_len`(문자 수)과 `byte_len`(UTF-8 바이트 수)을 명확히 구분하여 둘 다 기록·검증해야 함.

2. **대용량 HTML 패치 시 들여쓰기·주석·변수명 추정 정규식 사용으로 인한 매칭 실패**
   - **현상/원인**: 15,000줄 규모의 대시보드 HTML을 패치할 때 실제 줄 내용을 먼저 대조하지 않고 주석 문구(`// [안전 부트스트랩]`), 컨테이너 클래스(`max-w-[1800px]`), 로컬스토리지 버전 변수명(`syncDbVersion` vs `DB_VERSION`), DOM ID(`diag-lines-grid` vs `diagnostic-lines-container`)를 기억에 의존해 정규식으로 작성하여 초기 패치 실행이 4차례 중단됨.
   - **해결 방법**: `read_file`로 정확한 타깃 라인 범위를 확인한 뒤 실제 DOM ID와 함수 시그니처에 맞춰 정규식을 교체함.
   - **교훈(가드레일)**: 대규모 단일 HTML/JS 파일 패치 스크립트를 작성할 때는 추측성 문자열 매칭을 금지하고, 반드시 사전에 수정 대상 블록의 정확한 앞뒤 5~10줄 컨텍스트를 확인한 뒤 정규식을 작성해야 함.

3. **단일 `<script>` 스코프 내 동일 변수명(`const tariff`) 중복 선언 (`SyntaxError`)**
   - **현상/원인**: `renderDiagnosticModal()` 내부의 `tariff is not defined` 런타임 버그를 고치면서, 파일 내 2곳(`renderCmtBoard`와 `renderDiagnosticModal`)에 동일한 주석 헤더(`// [신규] 수냉연마(L8) & 연마(L9)...`)가 존재한다는 점을 간과하고 정규식 치환을 수행하여, 이미 상단에 `const tariff`가 선언된 `renderCmtBoard` 스코프에 `const tariff`가 중복 주입되어 `node --check` 구문 검사에서 `SyntaxError: Identifier 'tariff' has already been declared`가 검출됨.
   - **해결 방법**: `function renderDiagnosticModal()` 함수 시작부 직후에만 `count=1`로 `const tariff`를 주입하도록 수정하고 `node --check`로 통과를 확인함.
   - **교훈(가드레일)**: 정규식 치환 시 `count=1`과 함수명 앵커(`function targetFn() {`)를 반드시 결합하여 타 함수 스코프 오염을 방지하고, 배포 전 모든 인라인 `<script>` 블록(`(?<!\\)</script>` 기준 분리)에 대해 `node --check` 정적 구문 검증을 필수로 수행해야 함.

4. **하드코딩된 DB 접속 문자열(`127.0.0.1,1433` + `Trusted_Connection=yes`) 사용 오류**
   - **현상/원인**: 정적 검증 스크립트(`verify_static.py`)에서 DB 사원명 목록을 불러올 때 프로젝트 공용 DB 모듈([dosko_db.py](file:///c:/Users/song9/OneDrive/%EB%B0%94%ED%83%95%20%ED%99%94%EB%A9%B4/test-data/dosko_db.py)의 `get_db_connection()`)을 쓰지 않고 임의로 `SERVER=127.0.0.1,1433;Trusted_Connection=yes;`를 하드코딩하여, 실제 동적 포트(`127.0.0.1:5539`) 및 앱 전용 SQL 계정(`dosko_app`) 환경에서 `pyodbc.InterfaceError (18456)` 로그인 실패가 발생함.
   - **해결 방법**: 즉시 `from dosko_db import get_db_connection`을 임포트하여 표준 커넥션 풀/폴백 래퍼를 사용하도록 통일함.
   - **교훈(가드레일)**: 검증/배치/마이그레이션 스크립트 작성 시 DB 접속 정보를 하드코딩하지 말고, 반드시 프로젝트의 단일 DB 추상화 모듈(`dosko_db.get_db_connection()`)을 재사용해야 함.

5. **E2E 검증 스크립트 작성 시 실제 DB 컬럼명·API 라우트/헤더 규격 사전 미대조**
   - **현상/원인**: `e2e_verify.py` 작성 초기에 실제 스키마/코드 확인 없이 테이블명(`os_inbound_receipts` $\rightarrow$ 실제 `proc_outsourcing_inbounds`), 컬럼명(`target_id` $\rightarrow$ `target_key`, `dept_path` 가상 필드, `failed_login_count` $\rightarrow$ `failed_attempts`), API 페이로드 필수키(`/api/admin/users/update`의 `emp_no`), 토큰 헤더(`X-Dosko-Token` $\rightarrow$ 실제 `X-API-Key`)를 추정으로 작성하여 3차례 수정 후 통과함.
   - **해결 방법**: [dosko_db.py](file:///c:/Users/song9/OneDrive/%EB%B0%94%ED%83%95%20%ED%99%94%EB%A9%B4/test-data/dosko_db.py), [dosko_auth.py](file:///c:/Users/song9/OneDrive/%EB%B0%94%ED%83%95%20%ED%99%94%EB%A9%B4/test-data/dosko_auth.py), [dosko_admin_api.py](file:///c:/Users/song9/OneDrive/%EB%B0%94%ED%83%95%20%ED%99%94%EB%A9%B4/test-data/dosko_admin_api.py), [dosko_sync_server.py](file:///c:/Users/song9/OneDrive/%EB%B0%94%ED%83%95%20%ED%99%94%EB%A9%B4/test-data/dosko_sync_server.py)의 실제 SQL 및 핸들러 규격을 확인하여 9개 E2E 시나리오 전 항목을 통과시킴.
   - **교훈(가드레일)**: E2E 테스트 스크립트를 작성하기 전에 반드시 백엔드 라우터(`do_GET`/`do_POST`)와 `INSERT`/`UPDATE` 대상 테이블의 실제 DDL 컬럼 목록을 먼저 대조해야 함.

---

### 2. 추가된 재발 방지 체크리스트 (Checklist Additions)

- [ ] **인라인 `<script>` 구문 검증**: HTML 내 템플릿 리터럴의 `<\/script>`에 잘리지 않도록 `<script(?![^>]*\bsrc=)[^>]*>(.*?)(?<!\\)</script>` 정규식으로 추출 후 `node --check` 전수 통과 확인
- [ ] **대용량 아카이브 라인 보호**: 수정 전후 `(char_len, byte_len, sha256[:8])` 3중 시그니처 일치 여부 자동 단언(`assert`)
- [ ] **DB 커넥션 일원화**: 모든 보조/검증 스크립트에서 `pyodbc.connect` 직접 호출 금지, 프로젝트 공용 `get_db_connection()` 사용
- [ ] **PII 및 임시 테스트 데이터 보호**: 코드/로그 내 실명(PII) 하드코딩 `0`건 검증 및 E2E 테스트 시 `try ... finally` 블록으로 `E2E_TMP_*` 데이터와 공유 상태 JSON(`dosko_shared_state.json`) 100% 원복
