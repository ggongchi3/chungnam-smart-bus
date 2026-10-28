# 백엔드 단독 전체 점검 · 2026-10-28

요청 범위는 지금까지 구현한 백엔드 전체다. 다른 팀원의 프론트엔드·실제 AI·디자인과의 연동은 검사하지 않았다. 테스트의 대체 제공자/가짜 어댑터는 backend 내부 경계 검증에만 사용했다. 실제 HTTP 도구도 AI 미연결·독립 메모리 SQLite DB를 사용한다.

시작 상태: `codex/backend-implementation`, 커밋 `a0ff06c`, Git 변경 없음. 기존 소스·실행 DB·공용 scenario.json을 보존하면서 읽기 점검과 격리 재현을 수행했다. 실제 재현된 문제만 수정했으며 다른 파트 파일·공통 원본은 수정하지 않았다.

## 최종 결과

| 검사 | 결과 |
| --- | --- |
| 변경 전 기존 테스트 | 252 passed, 실패0, 기존 경고1, 71.60초 |
| 새 데이터 정합성 회귀 | 37 passed |
| 새 앱/설정/오류/세션 회귀 | 19 passed |
| 새 제공자/AI 작업 수명 회귀 | 8 passed |
| 최종 전체 테스트 | **316 passed**, 실패0, 기존 경고1, 96.41초 |
| 실제 Uvicorn 백엔드 HTTP | **28개 사례**, 서비스 API8개 통과 |
| 의존성 정합성 | pip check: No broken requirements found |
| Python 컴파일 | compileall 성공 |
| 실행 DB 읽기 무결성 검사 | integrity_check=ok, foreign_key_check 위반0, foreign_keys=1 |
| 범위·원본 보존 | backend 밖/실행 DB/공용 상태의 최종 비교는 backend-audit-workspace-20261028.json |

기존 경고1개는 Starlette TestClient의 anyio BlockingPortal 폐기 예정 알림이다. 테스트 실패는 아니다. HTTP 기록은 `backend-audit-http-20261028.json`, 최종 테스트 XML은 `backend-audit-tests-20261028.xml`이다. 테스트/HTTP 실행은 기존 Windows 샌드박스의 로컬 소켓 제한을 피하도록 권한이 허용된 실행에서 수행했다.

## 재현한 오류와 수정

| 문제 | 재현·영향 | 수정 |
| --- | --- | --- |
| 일반500의 공통 헤더 누락 | 내부 예외가 call_next를 벗어나면 봉투에는 요청ID가 있지만 X-Request-ID/Cache-Control가 없음 | error_response에서도 헤더 직접 설정 |
| 405 Allow 헤더 유실 | 지원하지 않는 메서드의 HTTPException.headers가 사라짐 | 예외 헤더 보존, 서버 요청ID·캐시 정책 유지 |
| 시작 실패 때 DB 엔진 정리 누락 | initialize 또는 seed 실패 시 finally에 진입하지 않아 dispose가 안 됨 | 초기화/적재부터 try/finally로 감쌈 |
| 비정상 DB 핵심 자료가500으로 전파 | 잘못된 좌표 문자열·NaN/±Inf, 분수 경유 순번 등이 ValidationError/JSON 오류를 만듦 | 좌표 비유한 값 거부, 서버 자료 ValidationError는503. 사용자 입력 오류400은 유지 |
| 손상된 제공자 모델의 검증 우회 | model_copy/model_construct로 만든 잘못된 coverage/type/품질·문자열/naive 시각이 잘못된200 또는500을 만듦 | 원시 데이터로 되돌려 ServiceChanges 스키마 재검증. 잘못된 변경 feed는200+unknown·빈 items로 격리, 도착/경로 유지 |
| 검색 시각·수명 손상 허용 | 만료를3600초로 바꾸면601초에도 조회 가능, 문자열 만료는500 | 유한 숫자·정확한600초 수명 검사. 저장 오차1마이크로초만 허용하되 실제 만료는 created_at+600으로 판단. 손상503·정상만료410 |
| 저장 data_mode 손상 오분류 | invalid-mode가 정상 demo/live 변경처럼409로 처리됨 | 지원하지 않는 저장 mode는503, 정상 mode 불일치409는 유지 |
| 저장 기준 품질의 모순 허용 | sourceUpdatedAt=null인데 freshness=fresh인 스냅샷이 그대로 반환됨 | 현재 생성 규칙인 원천 미확인·검색 시점 수집 품질과 대조해 손상503 |
| 도보 요약과 상세 불일치 | 상세 walk.durationSeconds=120인데 walkingDurationSeconds=null | 확인된 도보 합계는120/0도 보존. 버스 시간이 미확인이면 전체 소요시간은 null 유지 |

위 항목은 실제 메모리 DB·독립 테스트 DB·백엔드 대체물로 재현했다. 손상 데이터를 실제 실행 DB에 넣거나 기존 실행 DB를 지우지 않았다. 오류 뒤 정상 요청/세션이 복구되고, 실패 요청 중 flush한 행은 롤백되는 것도 검사했다.

## 정상으로 확인한 범위

- 합성 데이터 반복 적재·외래키·복합키·트랜잭션·검색 저장/재시작.
- 정류장/목적지 검색, 입력 경계, 정상/빈 결과/400/404.
- 정방향·명시적1회환승·중복제거·정렬·최대3개, 시장1/병원2/터미널4.
- 시간대/출발±120초, 최신성0/90/91초와 미래/없음, 만료599/600초.
- 도착/변경의 부분 실패·명시 운행 상태·관련 범위·경로 버전과 공통409/410/503 우선순위.
- 백엔드 AI 경계의 검증·대체·1초 채택 예산·동시 실행 제한·취소/원래 이벤트 루프 종료 뒤 worker 복구. 실제 AI 모듈은 연결하지 않음.
- 인쇄 스냅샷의 구간/버전/시각/상태·null ETA·실제 출력 성공 필드 없음.
- 잘못된 JSON/비UTF-8/Content-Type, 일반500의 정보 비노출·헤더·롤백, 405, 시작 실패 자원 정리.
- DB 경로 제한·드라이버/dataMode 설정 거부·의존성·앱 실행·실제 HTTP8개 API.

## 변경 파일

| 파일 | 역할 |
| --- | --- |
| backend/main.py | 시작 실패 정리, 오류 헤더·405 헤더, 서버 자료 검증 실패503 |
| backend/models/schemas.py | 좌표의 NaN/Inf 거부 |
| backend/integrations/providers.py | 이미 생성된 모델도 원시 데이터로 재검증 |
| backend/services/journeys.py | 검색 메타데이터·품질 검증, 확인된 소요시간 합계 |
| backend/tools/verify_stage6.py | --output 옵션으로 이번 HTTP 기록을 별도 저장 |
| backend/tests/test_audit_app.py | 앱·HTTP·설정·세션19개 |
| backend/tests/test_audit_data.py | 저장 데이터·수명·품질·시간 요약37개 |
| backend/tests/test_audit_boundaries.py | 제공자 모델·AI 작업 수명8개 |
| backend/docs/backend-audit-* | 이번 보고서·실행 증거·범위 비교 |
| backend/README.md, backend/docs/implementation-status.md | 재현 명령·최신 점검 상태 |

## 실제 명령

모두 프로젝트 루트에서 실행했다.

```text
git status --short / git branch --show-current / git log -3 --oneline
backend/.venv/Scripts/python -m pip check
backend/.venv/Scripts/python -m compileall -q backend/api backend/models backend/services backend/integrations backend/tools backend/main.py backend/database.py backend/config.py backend/seed.py backend/demo.py
backend/.venv/Scripts/python -m pytest backend/tests -q --basetemp=backend/.test-tmp -p no:cacheprovider --junitxml=backend/.local/backend-audit-baseline-tests.xml
backend/.venv/Scripts/python -m pytest backend/tests/test_audit_data.py -q -p no:cacheprovider
backend/.venv/Scripts/python -m pytest backend/tests/test_audit_app.py -q -p no:cacheprovider
backend/.venv/Scripts/python -m pytest backend/tests/test_audit_boundaries.py -q -p no:cacheprovider
backend/.venv/Scripts/python -m pytest backend/tests -q --basetemp=backend/.test-tmp -p no:cacheprovider --junitxml=backend/docs/backend-audit-tests-20261028.xml
backend/.venv/Scripts/python -m backend.tools.verify_stage6 --output backend/docs/backend-audit-http-20261028.json
```

별도 읽기 명령으로 실행 DB의 PRAGMA integrity_check/foreign_key_check/foreign_keys를 검사했다. 데이터 테스트는 메모리 DB와 `.local/`의 별도 파일만 사용한다. HTTP 도구도 실행 DB·공용 scenario를 건드리지 않으며 실제10분 대기를 하지 않는다.

## 남은 제약·제외 범위

최종 검사 범위에서 미해결 테스트 실패는 없다. 모든 가능한 입력·부하·OS에서 오류가 없다는 보증은 아니다.

경로 버전은 현재 선택 노선의 전체 경유 자료를 포함한다. 따라서 선택 구간 밖의 같은 노선 자료가 바뀌어도409로 재확인을 요구할 수 있다. 현재의 보수적인 버전 정책을 유지했으며 이번 정합성 오류 수정과 구분한다.

이미 실행 중인 동기 AI 함수를 강제로 중단하지 않는 기존 제한도 유지한다. 백엔드 내부 가짜로 취소·복구를 검증했으며 실제 AI 구현자의 모듈 동작은 점검하지 않았다.

실제 프론트엔드/AI/디자인 연동, 화면·브라우저 음성·물리 인쇄, 팀원 PC, 운영 배포·부하 시험은 이번 범위에서 제외했다. Git commit/tag/push/PR/원격 변경도 수행하지 않았다.
