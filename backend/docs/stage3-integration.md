# 3단계 정류장·목적지 API 연동 안내

2026-10-27에 v2 계획서의 3단계를 실행했다. API 두 개는 실제 SQLite 자료를 조회하며, 정적 응답을 라우터에 넣지 않는다. 기존 URL·필드·ID·오류 코드를 유지했다. 조회 조건 검증을 `models/schemas.py`의 DestinationQuery로 정리했다. 프론트엔드 A의 실제 화면은 아직 없어 공동 브라우저 확인은 대기다.

## 주소와 설정

백엔드는 `http://127.0.0.1:8000`, 프론트 개발 주소는 `http://localhost:5173` 또는 `http://127.0.0.1:5173`을 사용한다. 두 프론트 origin을 CORS로 허용했다. 프론트의 `/api` 개발 프록시는 **접두사를 유지**해 8000 서버로 전달해야 한다. 백엔드 경로 자체가 `/api/v1/...`이다. 이 설정을 반영할 대상은 `frontend/config/`와 A의 공통 API 클라이언트이며 이번에 직접 수정하지 않았다.

| API | 입력 | 성공 data |
| --- | --- | --- |
| GET /api/v1/stations/{stationId} | 등록 stationId 문자열 | `{station: {stationId,name,directionLabel,region,coordinates}}` |
| GET /api/v1/destinations | 필수 originStationId, 선택 query/category | `{destinations: [{destinationId,name,category,aliases}]}` |

정류장은 `demo-stop-001`부터 `005`까지이며 시작 정류장은 `demo-stop-001`이다. 목적지 목록은 다음과 같다. 현재 범위 안의 등록 목록을 반환하며 경로 이용 가능성 판단은 후속 경로 검색 API가 담당한다.

| 목적지 | ID | category | 등록 별칭 |
| --- | --- | --- | --- |
| 시연 병원 | demo-destination-001 | hospital | 시연 큰 병원 |
| 시연 시장 | demo-destination-002 | market | 시연 장터 |
| 시연 터미널 | demo-destination-003 | terminal | 시연 버스터미널 |

query는 앞뒤 공백을 제거한 뒤 최대 100자이며 이름·별칭의 부분 문자열로 찾는다. 영문은 대소문자를 구분하지 않는다. query 생략·빈 문자열·공백만 입력은 전체 등록 목록 조회다. category와 query가 함께 있으면 교집합이다. category는 hospital/market/terminal/station/other 중 하나이며, 분류를 선택하지 않았으면 **파라미터를 생략**한다. `category=`는 400이다. station/other는 유효한 분류지만 현재 등록 목적지가 없어 200 빈 배열이다.

`%`, `_` 등은 일반 검색 문자이며 전체 일치 와일드카드가 아니다. 같은 이름의 목적지가 여러 개면 ID별로 반환한다. 서버 결과의 이름을 ID로 바꾸거나 자동 확정하지 않는다.

## 성공·빈 결과·오류 처리

모든 응답은 `{data,error,meta}`를 사용한다. 성공은 error=null, 오류는 data=null이다. meta는 requestId/generatedAt/dataMode이며 ID는 문자열, generatedAt은 시간대 포함 ISO 8601이다. 정류장의 미확인 region·coordinates는 null을 유지한다.

| 상황 | HTTP / 처리 |
| --- | --- |
| 등록 정류장·목적지 조회 | 200, 실제 DB 값 표시 |
| 검색어/교집합에 일치 없음 | 200, destinations=[]; 결과 없음 화면 |
| originStationId 누락·빈 ID, 잘못된 category, 공백 제거 후 101자 이상 | 400 INVALID_REQUEST; 입력 수정 |
| 미등록 stationId 또는 originStationId | 404 NOT_FOUND; 출발 정류장 확인 |
| 핵심 교통 자료 확인 불가/live 미연결 | 503 TRANSPORT_DATA_UNAVAILABLE; 확인 불가 안내 |

원문 예외·SQL·내부 경로는 오류 메시지에 담지 않는다. requestId는 X-Request-ID 헤더와도 일치한다. 응답에 Cache-Control: no-store를 제공한다. `dataMode=demo`이면 화면에 **시연 데이터 · 실제 운행 정보 아님**을 표시한다. generatedAt을 교통 원천 갱신 시각으로 표시하지 않는다.

공통 클라이언트 요청 제한 5초, GET의 일시적 연결 실패/5xx만 1초 뒤 1회 재시도, 4xx 자동 재시도 없음은 기존 기준을 따른다. 서버는 프론트 타이머·재시도 코드를 구현하지 않는다.

## 실행 가능한 조회 예시

프로젝트 루트에서 서버를 실행한다.

```powershell
backend/.venv/Scripts/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

다른 PowerShell에서 다음처럼 조회한다. GET 두 개에는 departAt이 필요 없다.

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/stations/demo-stop-001'
$encodedQuery=[uri]::EscapeDataString('시연 장터')
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/destinations?originStationId=demo-stop-001&query=$encodedQuery&category=market"
```

위 PowerShell 예시는 연동 안내이며 해당 Invoke-RestMethod 명령 자체를 실행 검증한 것은 아니다. 실제 검증은 아래 Python HTTP 도구로 수행했다.

```powershell
backend/.venv/Scripts/python -m backend.tools.verify_stage3
backend/.venv/Scripts/python -m backend.tools.verify_stage3 --base-url http://127.0.0.1:8000
```

첫 번째 명령을 실제 실행했다. 빈 8000 포트에 **독립 메모리 SQLite DB**를 사용하는 Uvicorn 자식 서버를 띄워 21개 조회 사례·CORS·OpenAPI를 검증하고, 그 자식만 종료한다. 실행 DB·시연 상태 파일은 바꾸지 않는다. `--port 8001`처럼 비어 있는 다른 포트를 선택할 수도 있다. 두 번째 형식은 이미 실행 중인 정상 합성 서버를 점검할 때 사용하는 안내이며 이번에는 별도로 실행하지 않았다.

실제 요청·HTTP 상태·JSON·소요시간은 `stage3-http-examples.json`에 기록했다. 이는 당시 실행 응답이다. `verify_stage3`는 GET만 사용하므로 검색 시각·만료 ID의 재사용 문제가 없다. OpenAPI는 `openapi.json`, 자동 테스트 결과는 `stage3-test-results.xml`과 `stage3-regression-results.xml`이다.

## A와 공동 확인할 항목

시작 정류장 표시 → 주요 장소 선택/별칭 검색 → 빈 결과/입력 오류/미등록 정류장 안내를 실제 A 화면에서 확인해야 한다. 현재 frontend에는 자리 표시자만 있어 화면이 실제 API를 사용하는지, 프록시가 맞는지, 로딩·오류·시연 표시가 보이는지는 확인하지 못했다. 위 HTTP 성공을 A 브라우저 연동 완료로 표시하지 않는다. 다른 담당자에게 메시지는 전송하지 않았다.
