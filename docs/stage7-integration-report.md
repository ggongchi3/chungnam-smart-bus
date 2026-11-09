# 7단계 통합과 핵심 테스트 결과

검증일: 2026-11-09, Asia/Seoul. 기준: [기존 7단계](../backend/docs/source-plan.txt) 383~399행, [공통 API 계약](api-contract.md), [개발 기준안](development-plan.md), 사용자 제공 통합 QA 요청. 시작 브랜치는 `codex/backend-implementation`, Git 작업 트리는 변경 없이 시작했다. 적용할 AGENTS.md는 발견되지 않았다.

**백엔드 8개 API → SQLite → 합성 교통 제공자 → 실제 규칙 기반 AI → 안내/인쇄용 JSON 연결은 재검증했다. 전체 자동 테스트는 377 통과·실패0·건너뜀0이다. 실제 HTTP 55건, 별도 새 가상환경의 같은 HTTP 55건, AI 규칙 평가59건도 통과했다. 사용자 화면까지의 통합은 완료되지 않았다.** frontend는 temp 10개뿐이고 화면·인쇄 디자인은 없으며 외형 이미지 3개만 있다. 실제 브라우저·음성 청취·인쇄 미리보기는 차단, 외부 교통·다른 팀원 PC·제출 환경은 미연결/미실행이다.

코드 오류 3건(이용 불가 오류 코드, AI 후보 순서 검증, 500 CORS)을 실제로 재현·수정·재검증했다. 실행 DB·공용 시연 상태를 삭제하거나 바꾸지 않았다. 새로운 화면·서비스 API·실제 교통 사실은 추가하지 않았다. 역할/요구사항/실제 파일을 대응한 전체 표와 **정확한 API 8개 목록**은 [기능 연결표](stage7-feature-matrix.md), 팀원 실행 절차는 [11/10 재현 안내](stage7-reproduction.md)에 있다.

## A. 기능별 검증 결과

아래 통과는 각 행에 명시한 계층의 결과다. 서버 통과를 화면·실제 운행·음성·종이 출력 통과로 확장하지 않는다. `실제 API·모듈 연결`은 루프백 Uvicorn HTTP와 저장소의 RuleBasedAIAdapter이며 교통 자료는 합성이다.

| 기능 | 연결 상태 | 검증 방식 | 결과 | 근거 | 남은 작업 |
|---|---|---|---|---|---|
| 현재 정류장·목적지 검색·별칭/분류·빈 결과 | 서버/SQLite 연결 | 자동 테스트, 실제 API·모듈 연결 | 통과 | test_stage3; HTTP station/destinations/emptyDestinationResults | A의 입력·주요 장소 버튼·결과 UI |
| 직통 경로·선택 식별자·null | 서버/저장 스냅샷 연결 | 자동 테스트, 실제 API·모듈 연결 | 통과 | test_stage4, HTTP directSearch/detail001; 이동시간 null | A→B 객체와 선택 UI |
| 1회 환승·도보·구간 순서 | 명시된 합성 연결 사용 | 자동 테스트, 실제 API·모듈 연결 | 통과 | HTTP transferSearch/detail003; 버스 정류장 합계4 | 상세 UI·긴 이름/구간 렌더링 |
| 역방향 제외·후보 정렬·최대3개 | 경로 엔진/DB 연결 | 자동 테스트, 실제 API·모듈 연결 | 통과 | test_stage4의 순번·정렬·역방향; HTTP reverseRouteExcluded | 브라우저 후보 표시 순서 |
| departAt 현재 시각 검증 | 서버 시계 주입 가능 | 자동 테스트, 실제 API·모듈 연결 | 통과 | ±119/120 허용·±121 거부; 기존 소수초 경계 포함 | 클라이언트 현재 aware ISO 시각 생성 |
| 검색 만료·404/409/410/503 공통 계약 | 모든 선택 소비자 공통 검사 | 자동 테스트, 실제 API·모듈 연결 | 통과 | 599/600/601초 HTTP, test_stage5의 599.999999→600; stage7 계약9개 | UI 재검색/복구 |
| 최신성·원천 시각 없음/미래 | 관측 시각과 생성 시각 분리 | 자동 테스트, 실제 API·모듈 연결 | 통과 | HTTP 0/89/90/91초·source_missing/future; 소수초/UTC 테스트 | stale/unknown을 수치만으로 정상 표시하지 않는 B UI |
| 도착 정보 일부 실패 | 환승 첫 항목 available/둘째 unavailable | 자동 테스트, 실제 API·모듈 연결 | 통과 | HTTP partialArrivalFailure; 둘째 ETA/예정/원천=null, 운행 unknown | 실제 제공자·항목별 표시 |
| 결행·우회·운행 중단·재확인 | 합성 상태/버전 검사 | 자동 테스트, 실제 API·모듈 연결 | 통과 | 신선한 이용 불가 ROUTE_UNAVAILABLE, 재확인 ROUTE_VERSION_CHANGED; 90/91초 상태 전환 | UI 기존 안내 중단/재검색 |
| DB 반복 적재·FK·롤백·재시작 | 테스트/실행 DB 분리 | 자동 테스트, 수동 확인 | 통과 | test_stage2/4 및 clean environment의 seed2회·FK 실제 거부 | 타 PC 재현, 스키마 변경 시 별도 마이그레이션 설계 |
| API 8개·OpenAPI·입력400 | 계약/라우터/저장 OpenAPI 대조 | 자동 테스트, 실제 API·모듈 연결 | 통과 | HTTP 집합 비교·OpenAPI 구조 일치·422 미노출 | A TypeScript 타입 구현 |
| 500 공통 오류·CORS·복구 | 허용 Origin에서 오류 봉투 접근 가능 | 자동 테스트, 테스트용 어댑터 | 통과 | test_stage7_contract의 허용2/비허용1 Origin, 200/400/404/500/회복; audit rollback | 실제 브라우저 네트워크 오류 UI |
| 규칙 AI 목적지·안내 성공 | 기본 ASGI 앱/실제 RuleBasedAIAdapter 연결 | 자동 테스트, 실제 API·모듈 연결 | 통과 | HTTP matched/no_match·ai_assisted; 규칙평가59/59 | 사용자 후보 확인 UI. 외부 모델은 도입하지 않음 |
| AI 미등록/역순 후보·구간/버전/템플릿 검증 | 백엔드에서 거부 후 대체 | 자동 테스트, 테스트용 어댑터 | 통과 | test_stage6, test_stage7_ai 21개, 기존 잘못된 구간/중복/누락 테스트 | 화면/음성의 fallback 표현 확인 |
| AI 빈 응답·타입/파싱 실패·예외·시간초과 | unavailable/template_fallback, 단일 worker 예산 | 자동 테스트, 테스트용 어댑터 | 통과 | AI 영향98개; 기존 timeout/slot 회복/정확1초 검증 | 외부 모델 미도입. 영구 정지 함수의 강제 종료는 제공 안 함 |
| 안내와 인쇄 스냅샷의 사실·버전·상태 | 같은 상세/구간, 고정 템플릿과 null ETA | 자동 테스트, 실제 API·모듈 연결 | 통과 | HTTP print001/003/partialFailurePrint; test_stage6 한 번 관측; 기존 deep copy 불변성 | B의 고정 인쇄 DOM·페이지 분할 |
| 새 로컬 환경의 설치·DB·서버/AI | 같은 PC의 새 venv/독립 파일 DB | 수동 확인, 실제 API·모듈 연결 | 통과 | clean environment: 21개 잠금 버전·pip check·seed2회·HTTP55 | 다른 PC/컨테이너/다른 OS는 별도 미실행 |
| A/B 전체 화면·입력/로딩/결과·오류 복구 | 프론트 패키지/코드 없음 | 실제 브라우저 | 차단 | frontend temp 10개, package.json/index.html/TSX 없음 | A/B 구현 후 아래 10시나리오 실행 |
| 디자인 일치·큰 버튼/글자·긴 이름·키보드/초점/대비 | 화면/인쇄 시안과 앱 없음 | 실제 브라우저, 수동 확인 | 차단 | design 화면·guidelines·print-guide는 temp; 외형 이미지는 화면 시안 아님 | 디자인 목표 크기/배율과 시안, A/B 접근성 구현 |
| 음성 재생/중지·화면 이동 취소·실제 청취 | speechSynthesis 구현 없음 | 실제 브라우저, 수동 확인 | 차단 | voice-guide/temp; 한국어 음성/스피커 소리 미확인 | B 및 실제 기기 확인 |
| 인쇄 미리보기·페이지 분할·취소·종이 출력 | 인쇄 CSS/DOM/window.print 없음 | 실제 브라우저, 수동 확인 | 차단 | print-guide/temp; 서버 JSON만 검증 | B/디자인 구현 후 실제 미리보기. 출력 성공 판정 안 함 |
| 실제 충남 교통 정보 | 제공기관·키·범위 미확정 | 실제 API·모듈 연결 | 차단 | UnconnectedLiveProvider; live에서는503·demo 미혼합 테스트 | 백엔드 출처/필드/권리·갱신 검증 |
| 다른 팀원 PC·컨테이너·macOS/Linux | 접근/실행 증거 없음 | 수동 확인 | 미실행 | 새 로컬 venv 결과와 구분 | 재현 안내 실행·근거 회신 |
| 최종 제출 URL·HTTPS·프록시·새로고침 | 환경과 URL 제출 의무 미확정 | 실제 브라우저, 수동 확인 | 미실행 | 로컬 HTTP는 검증용. 배포·공개 주소 생성 안 함 | 제출 담당 환경 확정 후 점검 |

QR 저장·혼잡도·비상 안내·오류 신고는 실제 공통 요구사항에서 찾지 못하여 기능을 추가하지 않았다. 주요 장소 단축 버튼은 범위에 있으나 서버 분류 조회만 있고 A 버튼은 없다.

## B. 오류 및 담당 목록

이름이 확인된 담당자는 없으므로 역할만 적었다. 미준비 모듈은 코드 결함과 구분하여 통합 차단 항목으로 기록한다. 전달 문서는 준비했으며 다른 팀원에게 메시지를 발송하거나 합의했다고 주장하지 않는다.

| ID | 기능 | 재현 절차 | 기대값 | 실제값 | 원인·근거 | 담당 | 우선순위 | 수정·재검증 상태 |
|---|---|---|---|---|---|---|---|---|
| S7-01 | 경로 이용 불가 오류 | 정상 검색 후 cancellation/detour/not_running으로 변경→상세/live/안내/인쇄 | 409 ROUTE_UNAVAILABLE | 수정 전 ROUTE_VERSION_CHANGED | checked_detail가 모든 비ready를 changed로 처리 | 백엔드 | P1 | 상태 분기 수정. 신규6개 및 영향 테스트/HTTP 재통과 |
| S7-02 | AI 후보 순서 | 테스트 어댑터가 등록001,002,003 중003,001 역순 반환→해석 요청 | 검증 실패 unavailable·빈 후보 | 수정 전 역순 그대로 채택 | ID 집합만 검증하고 내부 계약 순서 미검사 | 백엔드/AI | P1 | 부분수열 순서 검증 추가. 사전2실패/19통과→영향98통과 |
| S7-03 | 서버 오류 CORS | 허용 Origin으로 GET, catalog 함수에서 RuntimeError 주입 | 공통500+허용 Origin CORS, 다음 정상 요청 회복 | 수정 전 ACAO 헤더 없음 | Starlette 바깥500 응답이 CORS를 우회 | 백엔드/A API 클라이언트 | P2 | CORS 내부 오류 경계 추가. 허용2/비허용1 Origin 회귀 통과 |
| S7-04 | 검증 제어 파일 | Windows/OneDrive에서 제어 파일 원자 교체 | 고정 시계 제어 파일 교체 | 최종 HTTP 첫 재실행 중 WinError5 | 짧은 파일 잠금. 앱 기능 오류가 아닌 검증 도구 문제 | 백엔드 검증 도구 | P2 | PermissionError 최대1초 제한 재시도. 최종 HTTP55 재통과; 10분 경계 대기 없음 |
| S7-05 | A/B 핵심 UI | frontend 실행/검색→선택→상세 시도 | 단일 앱과6개 인계 필드/버전/오류 상태 | temp10개, 실행 패키지 없음 | 실제 파일 목록 | 프론트 A/B | P0 | 차단. 없는 화면을 임의 생성하지 않음 |
| S7-06 | 화면/인쇄 디자인 | design 화면·가이드·출력물 비교 | 목표 크기/배율·시안·상태/긴 문자열 기준 | 외형 이미지3개와temp만 존재 | 외형 이미지는 버튼/화면 합의 근거가 아님 | 디자인/A/B | P1 | 차단. 시안·합의 기록 필요 |
| S7-07 | 음성·브라우저 인쇄 | B 기능에서 재생/정지/미리보기 | 검증 안내와 실제 청취/미리보기 일치 | 구현 없음, 실제 소리/인쇄창 미확인 | voice/print temp | 프론트 B/디자인 | P1 | 차단. JSON 통과와 구분 |
| S7-08 | 문서 현재 상태 | 루트/계약/계획/출처와 실제 코드 비교 | 현재 구현과 역사 기록 구분 | 서버·AI·합성 원본 미생성 문구와 실제 코드 혼재 | 초기 문서 미갱신, 구409 설명 | 백엔드/공통 문서 | P2 | 현재 상태·오류 가이드·재현 절차 갱신. 과거 결과 보존 |
| S7-09 | 합성 명칭·별칭 | 개발 기준안 표와 demo-data.json 비교 | 합의된 같은 ID 이름/등록 별칭 | 004 마을↔중간; 초기 예시 별칭과 실제 각1개 차이 | 초기 제안과 등록 원본 차이 | 백엔드/디자인/A | P2 | 차이 기록, 데이터 보존. UI는 검증한 서버명 사용; 최종 명칭 합의 대기 |
| S7-10 | 실제 교통 제공자 | live 모드 조회 | 승인 제공자의 검증된 자료 | 제공자 없음·503 | 출처/키/지역/약관 미확정 | 백엔드/제공자 확인 필요 | P2 | 시연은demo 유지. 실제 운행 시연은 차단 |
| S7-11 | 타 PC·제출 환경 | 새 PC 설치 및 최종 URL 접속/새로고침 | 실제 실행/HTTPS/프록시/CORS 근거 | 대상 PC·최종 환경 증거 없음 | 제출 조건 미확정 | 전원/제출 담당 확인 필요 | P1 | 미실행. 재현 문서 준비, 환경 확정 후 실행 |

현재 재현된 수정 대상 코드 오류가 미해결로 남아 있지는 않다. S7-05~07/09~11의 미준비·미확인 사항이 남아 있어 전체 7단계를 완료로 표시하지 않는다.

## C. 변경 내용과 실행 근거

### 변경한 파일과 이유

| 파일 | 변경 이유 |
|---|---|
| backend/api/errors.py, services/journeys.py | 확인된 unavailable과 재확인/버전 오류 구분. 기존 오류 우선순위·null 의미 유지 |
| backend/services/ai.py | 현재 등록 후보 순서를 벗어나는 AI 응답 거부 |
| backend/main.py | 공통500을 CORS 내부에서 반환하고 기존 request ID/캐시 금지/오류 봉투 유지 |
| backend/tests/test_stage7_contract.py, test_stage7_ai.py | 신규30개: 상태/신선도와409 의미, Origin별500/회복, 후보 순서와 malformed/빈 응답·인쇄 대체 일치 |
| backend/tests/test_backend.py, test_stage5.py, test_stage6.py | 기존 비ready 사례 중 확인된 unavailable만 공통 계약 기대값으로 교정. 검증 완화 없음 |
| backend/tools/verify_stage5.py, verify_stage6.py | 같은 오류 계약과 HTTP 기대값 정정; Windows 제어 파일 교체의 제한 재시도 |
| backend/tools/verify_stage7.py | 격리 메모리 DB/시각/전용 제어 파일과 실제 규칙 AI로 HTTP55건·정확8 API·OpenAPI·CORS·실행 파일 보존 검증 |
| README, backend/README, docs/api-contract·development-plan·data-sources·structure | 실제 구현 상태·원본과의 차이·실행/범위 안내 정정. 스키마/요구사항 정책 추가 없음 |
| backend/docs/stage5-integration.md, stage6-integration.md | A/B 연동용409 이용 불가/버전 구분 안내 정정 |
| docs/stage7-*.md, docs/verification.md | 기능표·결과·오류·역할별 전달 내용·11/10 재현 절차/검증 범위 |
| backend/docs/stage7-*.json/xml | 실제 테스트/HTTP/규칙 평가/새 환경/최종 감사 근거 |

DB 모델·합성 원본·AI 규칙 자체·프론트/디자인 파일은 변경하지 않았다. OpenAPI 저장본은 실제 생성본과 구조가 같아 불필요하게 다시 쓰지 않았다. 스키마·공개 API 개수는 그대로다.

### 실행한 명령과 실제 결과

모든 명령은 저장소 루트 기준이다. 아래 부분집합 테스트 수를 전체377에 더하여 중복 집계하지 않는다.

| 명령/실행 | 실제 결과·근거 |
|---|---|
| `backend/.venv/Scripts/python -m pip check` | No broken requirements found |
| `...python -m pytest backend/tests ai/evaluation -q --basetemp=backend/.test-tmp/stage7-final-20261109 -p no:cacheprovider --junitxml=backend/docs/stage7-test-results.xml` | **377 passed, 실패0, 오류0, skip0, 경고1, 154.49초**. [전체 XML](../backend/docs/stage7-test-results.xml) |
| `...python -m pytest backend/tests/test_stage7_contract.py backend/tests/test_audit_app.py backend/tests/test_backend.py -q -p no:cacheprovider --junitxml=backend/docs/stage7-contract-results.xml` | 최종 영향 **93 passed**, 경고1,24.74초. 첫 unavailable 수정 영향165개도 재통과 |
| `...python -m pytest backend/tests/test_stage7_ai.py backend/tests/test_ai_integration.py backend/tests/test_stage6.py ai/evaluation -q -p no:cacheprovider --junitxml=backend/docs/stage7-ai-results.xml` | **98 passed**, 경고1,35.61초. 사전 버그 [2 failed/19 passed](../backend/docs/stage7-ai-before-fix.xml) |
| `...python -m ai.evaluation.run_eval` (결과 JSON 저장) | 실제 규칙 어댑터 **59/59**, 1초 초과0. [평가 JSON](../backend/docs/stage7-ai-evaluation.json). 외부 모델 정확도/현장 품질 지표 아님 |
| `...python -m backend.tools.verify_stage7 --port 18007` | 최종 **HTTP55건 통과**, 실제 규칙 AI·합성 제공자·API8/OpenAPI/CORS/실행 파일 보존. [요청/응답](../backend/docs/stage7-http-results.json) |
| `...python -m backend.tools.verify_stage6 --port 18006 --output backend/docs/stage7-legacy-http-results.json` | 최종 **HTTP28건 통과**, 어댑터 미연결 대체 경로만 검증. [별도 근거](../backend/docs/stage7-legacy-http-results.json) |
| `python -m venv --without-pip backend/.local/stage7-clean-20261109` 및 별도 Python 대상 lock 설치 | 새 환경 생성/패키지 설치 exit0, 기존 환경 복사/상속 없음 |
| clean Python `ensurepip`·`pip check`·버전 대조·UUID DB seed2회·FK/rollback | 성공. 두 번째 신규0, 21개 잠금 버전 일치. [환경/명령/결과 JSON](../backend/docs/stage7-clean-environment.json) |
| clean Python `-m backend.tools.verify_stage7 --port 18017 --output backend/docs/stage7-clean-http-results.json` | 새 환경에서도 **HTTP55건 통과**. [요청/응답](../backend/docs/stage7-clean-http-results.json) |

경고1개는 설치된 Starlette TestClient의 anyio BlockingPortal 폐기 예정 별칭이다. 현재 테스트 실패는 아니다. 시간 경계는 주입 시각으로 검증했다. AI worker의 실제 시간초과/취소/회복 테스트에는 제한된 worker 동기화가 있으며, 600초 만료나90초 최신성을 실제 대기한 것은 아니다.

기본 샌드박스에서 시작한 전체 baseline은 TestClient의 asyncio `_fallback_socketpair → accept`에서 대기해 중단했으며 성공으로 기록하지 않는다. `faulthandler_timeout=8`로 같은 제한을 확인한 뒤 허용된 실행에서 위 전체 suite를 완료했다. 새 HTTP 도구의 첫 개발 실행은 detour 기대값을 잘못 지정해 assertion 실패했으나 계약의 신선한 이용 불가로 교정했다. 이후 일시 파일 잠금 실패도 수정하여 **최종 실행**이 통과한 결과만 위에 적었다. 이 과정에서 검증 조건을 낮추거나 실제 대기 경계를 바꾸지 않았다.

### 브라우저 최소10시나리오와 확인 한계

**실제 브라우저로 완료한 사용자 시나리오는 0개다.** 앱이 없으므로 화면/Network/음성/인쇄창을 실행했다고 주장하지 않는다. 아래 서버 대응 검증은 브라우저 통과를 대신하지 않는다.

| 번호 | 요구 시나리오 | 서버에서 실행한 대응 검증 | 실제 브라우저 결과 |
|---|---|---|---|
| 1 | 직통 전체 이용 | HTTP directSearch→detail001→actualRuleGuidance001→print001 | 차단 |
| 2 | 환승 전체 이용 | HTTP transferSearch→detail003→actualRuleGuidance003→print003 | 차단 |
| 3 | 검색 결과 없음 | 목적지 빈 배열, 역방향 경로 빈 배열200 | 차단 |
| 4 | 잘못된 입력·없는 대상 | 입력/JSON400·미등록404 공통 봉투 | 차단 |
| 5 | 만료 후 선택/상세 | 599유효,600/601 상세/live/안내/인쇄410 | 차단 |
| 6 | 경로 버전 변경 | 기대 버전409, timetable 재확인, 구조/연결 변경 자동 테스트 | 차단 |
| 7 | 도착 일부 실패·최신성 | 환승 항목별 실패·0/89/90/91·없음/미래 | 차단 |
| 8 | AI 검증 실패/예외/시간초과 | 테스트용 어댑터와 실제 규칙 모듈을 구분해 대체 검증 | 차단 |
| 9 | 연속검색/중복/뒤로/새로고침 | 새 검색이 이전 저장 상세를 덮지 않는 서버 테스트만 통과; 클라이언트 race/화면 초기화는 미실행 | 차단 |
| 10 | 인쇄 고정 후 원본 변경 | 서버 deep copy·상태 변경 후 이전 응답 고정·새 요청 재검증 | 차단: 인쇄 DOM/미리보기 없음 |

Uvicorn 접근 로그와 HTTP JSON의 경로·상태를 대조했고 응답의 X-Request-ID/봉투 requestId도 검사했다. 최종 로그 위치는 각 HTTP JSON의 `serverLog`에 기록한다(로그는 `.local/`로 Git 제외). 요청 ID는 서버 오류 봉투 추적용이며 Uvicorn 기본 로그가 request ID를 출력하도록 변경한 것은 아니다. 비밀키·개인정보를 로그/보고서에 넣지 않았다.

최종 [검증 요약 JSON](../backend/docs/stage7-verification-summary.json)에서 JUnit377/0/0/0, API8개·OpenAPI 일치, 현재/새 환경의 요청55건 각각과 서버 로그 대조, 문서12개의 로컬 링크 검사, 실행DB/시나리오 SHA-256 전후 일치를 재확인했다. `git diff --check`는 exit0이며 프론트·디자인·AI 규칙 소스의 Git 변경은 없다. 새 가상환경·테스트DB·시나리오·로그가 Git 제외됨도 확인했다.

인쇄 JSON은 영구 보관/재조회 API가 아니라 한 번 반환된 복사본이다. 자동 테스트는 원본 모델/관측 변경 후 반환 스냅샷이 유지되는 것을 검사하고 HTTP는 이전 수신 JSON과 새 응답/오류를 비교했다. 이후 DOM을 고정하는 책임, 실제 미리보기의 잘림/페이지 분할, 프린터 성공 여부는 확인하지 않았다.

## D. 팀원 전달 사항과 시연 판단

| 담당 영역 | 구체적으로 필요한 작업·사용할 계약 |
|---|---|
| 디자인 | 화면/상태/출력물 시안, CSS 목표 해상도·배율·긴 문자열·대비/초점·버튼 기준. 외형 치수를 CSS 해상도로 추정하지 않음 |
| 프론트 A | 단일 앱/package-lock·공통 API 클라이언트/타입·시작/검색/주요 장소/후보/선택.6개 인계 필드 보존, AbortController/요청 순서 보호, 조건 변경 시 이전 선택/상세/음성/인쇄 초기화.5초 제한·GET 일시실패만1회 재시도 |
| 프론트 B | 상세/live에서 버전 대조, 항목별 null/stale/unknown 표시, 활성 중30초 조회/이탈 중지,409/410 시 이전 안내 중단.검증된 steps로 음성 재생/취소, 서버 인쇄 JSON으로 고정 DOM·CSS/취소/긴 안내 확인 |
| 백엔드 | ROUTE_UNAVAILABLE와 ROUTE_VERSION_CHANGED를 구분하는 최신 가이드 전달.004 이름·별칭을 디자인/A와 확정.실제 제공자 필요시 출처·키·지원 범위·시간대/초 단위·호출 제한 검증 후 연결.운영 DB 삭제 금지 |
| AI | 후보는 등록 순서의 부분수열, 안내는 같은 버전·정확한 구간 순서·유형별 허용 템플릿만 반환.딕셔너리 JSON 출력이며 JSON 문자열/빈값/예외는 대체됨.현재 외부 모델 없음; 임의 노선/시각 생성 금지 |
| 전원/제출 담당 | [재현 절차](stage7-reproduction.md)로 다른 PC 실행 근거 확보.실제 브라우저10시나리오·음성 청취·인쇄 미리보기 완료.제출 URL 필수 여부·환경 확정 후 HTTPS/프록시/CORS/프로세스/새로고침 검증 |

현재 가능한 시연은 **백엔드 API/Swagger·합성 직통/환승·규칙 목적지 해석/쉬운 안내·상태 오류·고정 인쇄 JSON**이다. HTTP fixture는 테스트 전용이며 제출 서비스로 배포하지 않는다. 사용자용 키오스크 시연은 A/B 코드와 디자인, 음성·인쇄 기능 부재로 막혀 있다. 실제 교통 운행이나 외부 AI 모델이 연결됐다고 설명할 수 없다.

제출 전에는 A/B 앱·시안·실제 브라우저10시나리오, 실제 음성/인쇄, 다른 PC 재현, 제출 조건/URL을 반드시 확인해야 한다. 동일 PC의 새 venv 검증과 타 PC/컨테이너 확인을 구분한다. 이번 작업은 코드·문서·검증 산출물까지이며 커밋/push/PR/배포나 외부 담당자에게의 메시지 전송은 수행하지 않았다.
