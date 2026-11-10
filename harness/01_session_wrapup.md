# 하네스 규칙 01: 세션 회고 및 복기 가드레일 (Session Wrap-up)

사용자가 대화 중 **`"마무리하자"`**라고 입력하거나 세션 종료를 요청할 때 즉시 수행하는 표준 절차입니다.

---

## 1. 세션 회고 3단계 절차

1. **실수 및 이상 현상 복기**:
   - 세션 중 발생한 모든 에러(명령어 구문, 인코딩 깨짐, 도구 호출 오류, Git 충돌, 배포 누락 등)의 원인을 가감 없이 분석합니다.
2. **누적 회고록 업데이트**:
   - 글로벌 회고록: [C:/Users/song9/.gemini/config/LESSONS_LEARNED.md](file:///C:/Users/song9/.gemini/config/LESSONS_LEARNED.md)
   - 워크스페이스 회고록: [LESSONS_LEARNED.md](../LESSONS_LEARNED.md)
   - 날짜별(`## [YYYY-MM-DD] 세션 기록`) 섹션으로 **실수(현상/원인) $\rightarrow$ 교훈(재발 방지 가드레일)**을 기록합니다.
3. **결과 요약 보고**:
   - 추가된 교훈과 가드레일 요약을 사용자에게 두괄식으로 간결하게 보고합니다.
