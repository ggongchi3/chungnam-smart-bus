# 6단계 AI 중계·쉬운 안내·인쇄 준비 연동 안내

v2 계획서의 6단계 연동 자료다. **시연 데이터 · 실제 운행 정보 아님**. 2026-11-02부터 기본 `backend.main:app`은 `RuleBasedAIAdapter`를 연결한다. 외부 모델·네트워크를 호출하지 않는 규칙 기반 선택이며, 백엔드는 등록 후보·검증된 구간·허용 표현만 교환한다. 프론트엔드 B 화면은 미구현이므로 API 검증과 실제 화면/음성/인쇄 공동 확인을 구분한다. 아래 `verify_stage6`의 기록은 기존 2026-10-28 미연결 대체 검증이다.

## 공개 API와 실패 대체

| API | 요청 | 정상·대체 data |
| --- | --- | --- |
| POST /api/v1/destination-interpretations | originStationId, text | status, candidates, reasonCode |
| POST /api/v1/easy-guidance | routeSearchId, routeOptionId, expectedRouteSnapshotVersion | routeSnapshotVersion, mode, steps |
| POST /api/v1/print-guides | 같은 선택 식별자·기대 버전 | printGuideId, generatedAt, routeDetail, liveInfoSnapshot, notice, guidance |

모든 응답은 기존 data/error/meta 봉투를 유지한다. text는 앞뒤 공백을 제거한 뒤 1~200자다. 빈 문자열·공백만 입력·201자 이상·숫자 등 잘못된 입력은 400 INVALID_REQUEST다.

실제 AI가 없으면 목적지 해석은 HTTP 200의 `status=unavailable`, `candidates=[]`, `reasonCode=AI_UNAVAILABLE`을 반환한다. UI는 일반 목적지 검색/주요 장소 선택으로 이어간다. AI 해석 성공으로 표시하거나 임의 목적지를 자동 확정하지 않는다. 쉬운 안내는 검증된 같은 경로의 `mode=template_fallback`으로 제공하므로 AI가 없어도 상세 안내가 계속 동작한다.

AI 동기 공개 인터페이스는 `interpret_destination(payload)`와 `choose_guidance(payload)`다. `ai/adapter.py`가 `destination_interpretation`, `easy_guidance` 패키지를 표준 import로 연결한다. 어댑터 주입 없는 `create_app()`은 기존 미연결 대체를 유지하므로 실패 경로를 독립적으로 검증할 수 있다.

공개 이유 코드는 `matched → MATCHED`, `needs_confirmation → USER_CONFIRMATION_REQUIRED`, `no_match → NO_REGISTERED_MATCH`, `unavailable → AI_UNAVAILABLE`로 [AI 계약](../../ai/contracts/README.md)과 일치한다. 서버가 검증한 상태로 이유 코드를 결정하며 AI의 원문 사유는 노출하지 않는다. 오타 추정은 후보가 1개여도 `needs_confirmation`으로 유지하고, `matched`도 사용자가 후보를 확인하고 선택한다.

- 목적지 입력은 text/dataMode/allowedDestinations이고, 각 허용 후보에는 등록 destinationId/name/aliases만 보낸다. 출력 status/candidateDestinationIds/reasonCode를 검사하고 ID가 허용 목록의 부분집합인지 확인한다. 공개 candidates는 서버 DB 값으로 다시 구성한다.
- AI 응답을 기다리는 동안 등록 정보가 바뀔 수 있어, 출력 직전에 원래 허용 목록과 현재 DB 목록을 모두 확인한다. 삭제된 ID는 unavailable로 대체하고 이름·별칭·분류는 현재 등록 값을 사용한다. matched도 사용자 확인을 생략한다는 뜻이 아니다.
- 안내 입력은 routeSnapshotVersion/dataMode/verifiedSegments다. 각 구간은 segmentId/type/allowedTemplateIds를 가진다. 기본 허용 표현은 bus.basic/walk.basic/transfer.basic이다. 출력 status/routeSnapshotVersion/steps의 segmentId·순서·누락·추가·중복·유형별 templateId를 검사한다.
- 실제 노선·정류장·승하차·정류장 수·환승 사실은 검증된 서버 경로에서 삽입한다. AI가 만든 새 장소·노선·도착 시각·자유 교통 사실을 채택하지 않는다. public steps는 segmentId/text이며 B는 일반 문자열로 사용한다.

AI 오류·잘못된 출력·결과 채택 예산 1초 초과는 수동 검색 또는 고정 안내로 대체한다. 시간초과는 결과를 기다리거나 채택하는 것을 중단한다는 뜻이며 동기 Python 함수를 강제로 종료했다는 뜻이 아니다. 실행 중인 작업이 끝나기 전 새 작업을 무제한 쌓지 않는 제한을 둔다.

어댑터는 동기 함수와 JSON으로 표현 가능한 dict 출력을 사용한다. 입력과 출력은 복사해 어댑터의 뒤늦은 변경이 서버 검증 자료를 바꾸지 않게 한다. NaN·set·모델 객체 등의 비JSON 출력과 미지원 async 함수는 실패 대체한다. 프로세스당 실행 슬롯은1개이고 대기열은 없다. worker 준비/시작이 실패해도 슬롯을 복구한다. 남은 채택 예산만 기다리며, 무기한 멈춘 실제 동기 함수는 어댑터 자체 취소 기능이나 서버 재시작이 필요하다.

## 상세·음성용 텍스트·인쇄의 일관성

B는 A가 전달한 originStationId/destinationId/routeSearchId/routeOptionId/routeSnapshotVersion/dataMode를 확인하고, 서버의 최신 상세를 다시 조회한다. easy-guidance와 print-guides에는 선택한 **expectedRouteSnapshotVersion**을 보낸다. 클라이언트가 별도 segments·교통 사실을 만들어 전달하지 않는다.

안내 steps는 상세 segments와 같은 segmentId·순서를 사용한다. 노선명·승하차 정류장·정류장 수는 구조화된 상세 사실을 기준으로 한다. 미확인 거리·시간은 null로 유지하고 고정 문구에서 확인 불가로 설명하거나 생략한다. demo 안내 첫 문장과 인쇄 notice에는 시연 표시를 포함한다. B는 이 텍스트를 화면과 음성 합성의 입력으로 사용할 수 있지만 브라우저 음성 엔진·재생/중지 UI는 B가 구현한다.

인쇄 요청은 만료·경로 상태·기대 버전을 다시 검사한다. 성공 데이터의 routeDetail/liveInfoSnapshot/guidance가 같은 routeSnapshotVersion을 참조하고, 상세 구간과 안내 step의 순서가 일치한다. 생성한 JSON 응답은 그 요청 시점의 고정 스냅샷이며 나중 도착 조회값과 섞지 않는다.

| 인쇄 필드 | 의미 |
| --- | --- |
| printGuideId | 인쇄 준비 데이터를 식별하는 문자열. 프린터 작업 ID가 아님 |
| generatedAt | 준비 데이터 생성 시각. 실제 종이 출력 완료 시각이 아님 |
| routeDetail | 검증된 같은 버전의 구간·정류장·정류장 수 |
| liveInfoSnapshot | 생성 시점의 도착·변경 상태와 각 원천/수집 시각 |
| arrivals[].etaSeconds | null. 종이 출력에 도착 카운트다운 수치를 넣지 않음 |
| expectedArrivalAt | 확인된 절대 도착 예정 시각이 있으면 고정 값으로 제공; 미수신이면 null |
| notice / guidance | 시연·미확인 상태 안내 및 같은 구간의 고정 텍스트 |

ready 경로는 도착 미수신이나 변경 조회 확인 불가를 명시하여 인쇄 준비할 수 있다. arrivalStatus=unavailable을 결행으로, coverageStatus=unknown의 빈 items를 변경 없음으로 바꾸지 않는다. 생성 시각을 sourceUpdatedAt으로 대신하지 않는다.

notice는 스냅샷의 실제 unavailable/stale/unknown 상태에 맞춰 생성한다. 확인된 도보 거리와 시간은 각각 독립적으로 안내하고, 거리만 미확인이라는 이유로 확인된 시간까지 미확인으로 바꾸지 않는다. 인쇄 준비는 AI를 다시 호출하지 않고 같은 검증 경로의 고정 문구를 사용한다. JSON 200이나 printGuideId는 프린터 작동 여부를 나타내지 않는다.

| 상황 | HTTP / 처리 |
| --- | --- |
| AI 미연결/실패 | 200 unavailable 또는 template_fallback. 수동 검색/고정 안내 유지 |
| text·요청 필드 오류 | 400 INVALID_REQUEST. 입력 수정 |
| 경로 버전 불일치·재확인 | 409 ROUTE_VERSION_CHANGED. 기존 안내/인쇄를 중단하고 재검색·확인 |
| 확인된 결행·우회·운행 중단 | 409 ROUTE_UNAVAILABLE. 기존 안내/인쇄 중단 후 재검색(2026-11-09 계약 오류 수정) |
| now >= expiresAt | 410 ROUTE_SEARCH_EXPIRED. 새 검색 |
| 핵심 검증 자료 확인 불가 | 503 TRANSPORT_DATA_UNAVAILABLE. 경로가 유효하다고 추정하지 않음 |

인쇄 HTML/CSS·용지 배치·window.print·전용 프린터 연결은 구현하지 않았다. 서버는 종이 출력 성공·실패·취소를 판정하지 않는다. 인쇄 준비 JSON 200을 물리적 출력 성공으로 표시하지 않는다.

## 실제 HTTP 재현과 범위

프로젝트 루트에서 다음 명령으로 검증한다.

```powershell
backend/.venv/Scripts/python -m backend.tools.verify_stage6
```

실제 실행해 `stage6-http-examples.json`을 생성했다. 정류장/목적지 → 경로 검색/상세/live → AI 미연결 해석/고정 안내 → 인쇄의 **공개 API 8개 흐름**을 호출했다. 실제 AI 어댑터나 가짜 성공 어댑터를 주입하지 않았다. AI 미연결 대체, text 오류, 인쇄 버전409·결행409·만료410·핵심503, 미수신/변경 조회 unknown/원천 시각 null 인쇄200, 동일 구간/버전/시연 표시와 null ETA를 확인한다. 최종 사례 수·소요시간은 최신 생성 JSON 및 구현 상태 문서를 기준으로 본다.

도구는 독립 메모리 SQLite DB·명시 DemoProvider·주입 시각의 Uvicorn 자식 서버를 사용한다. 전용 제어 파일은 매 실행 새 `backend/.local/stage6-http-<임의ID>/control.json`에만 만든다. 시각·상태를 파일로 주입하므로 별도 HTTP 제어 API를 추가하지 않으며 공개 API는 8개 그대로다. 599/600초 검증에서도 실제 10분을 기다리지 않는다. 실사용 main 앱·실행 DB·공용 scenario.json은 변경하지 않는다.

기본 8000 포트가 사용 중이면 중단하고 다른 프로세스를 종료하지 않는다. `--port 8001`처럼 다른 빈 포트를 선택할 수 있지만 해당 선택 명령은 이번에 별도로 실행한 것으로 표시하지 않는다. 도구가 만든 자식 서버만 종료한다. 전용 시각 제어가 필요한 도구라 기존 서버를 대상으로 상태를 바꾸는 옵션은 제공하지 않는다.

HTTP 기록의 fixture.now와 API generatedAt은 **주입된 테스트 시각**이다. verifiedAt은 도구 실행의 실제 UTC 시각이다. 기록 속 검색/버전 ID는 종료된 테스트 서버의 값이므로 실제 앱에 복사해 재사용하지 않는다. 새 요청은 그 서버의 현재 시각과 새 식별자를 사용한다.

## 별도 테스트와 공동 확인 대기

1초 예산·AI 오류/잘못된 출력/목록 밖 ID·구간 누락/중복·잘못된 템플릿·가짜 AI 성공은 별도 pytest의 주입 어댑터로 검증한다. 이 HTTP 도구는 미연결 대체를 검증한다. 실제 규칙 어댑터와 기본 ASGI 앱 연결은 `backend/tests/test_ai_integration.py`, `ai/evaluation/test_backend_integration.py`에서 별도로 검증한다.

B/디자인 담당자는 같은 버전의 상세·텍스트·인쇄 JSON으로 실제 화면·음성 재생/중지·인쇄 미리보기·취소·시연/미확인 표시를 확인해야 한다. 프론트 화면이 준비되지 않아 공동 브라우저·음성·인쇄·팀원 PC 검증은 대기다.
