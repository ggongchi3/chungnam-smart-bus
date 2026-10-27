# 4단계 경로 검색·상세 API 연동 안내

2026-10-27에 v2 계획서의 4단계 HTTP 검증을 실행했다. 합성 자료와 기존 서비스 API 계약을 사용한다. **시연 데이터 · 실제 운행 정보 아님**. 프론트엔드 A/B 화면은 아직 자리 표시자뿐이므로 검색 → 선택 → 상세의 실제 브라우저 공동 확인은 대기다.

## 검색에서 상세까지

| 순서 | API / 데이터 | 담당자가 사용할 값 |
| --- | --- | --- |
| 1 | POST /api/v1/route-searches | originStationId, destinationId, departAt |
| 2 | 검색 성공 data | routeSearchId, originStationId, destinationId, expiresAt, routeOptions |
| 3 | A가 후보를 선택해 B에 전달 | originStationId, destinationId, routeSearchId, routeOptionId, routeSnapshotVersion, dataMode |
| 4 | GET /api/v1/route-searches/{routeSearchId}/options/{routeOptionId} | B는 서버의 RouteDetail로 승차·하차·정류장 수·구간 순서를 표시 |

모든 ID는 불투명한 문자열이다. routeOptionId는 버스 노선 ID가 아니며 같은 경로를 다른 검색에서 조회했을 때 같은 값일 수 있다. 검색 ID와 옵션 ID를 항상 함께 사용한다. 이름이나 배열 인덱스를 식별자로 사용하지 않는다. dataMode는 검색 응답의 meta에서 가져오며 최종 상세 응답도 확인한다.

검색 예시는 다음과 같은 구조다. departAt은 요청을 보낼 때마다 `datetime.now(timezone.utc).isoformat()` 등으로 현재 시각을 생성한다. 아래 표현식 자리에 고정된 과거 시각을 복사하지 않는다.

```text
{
  "originStationId": "demo-stop-001",
  "destinationId": "demo-destination-001",
  "departAt": <요청 시 생성한 시간대 포함 현재 ISO 8601 문자열>
}
```

백엔드는 현재 시각과 절댓값 120초 이내인 departAt만 허용한다. naive 시각, 누락/잘못된 필드, 지원 범위를 벗어난 과거·미래 시각은 400 INVALID_REQUEST다. 정확한 ±120/±121초 경계는 주입 시각의 자동 테스트에서 검증하며, HTTP 도구는 네트워크 경과 시간의 영향을 피하려고 명확한 범위 밖인 ±180초를 사용한다.

## 합성 경로와 구간

| 출발·목적지 | 검색 결과 | 상세 구간 |
| --- | --- | --- |
| stop-001 → destination-002 시장 | 직통, 환승0, 버스 정류장 합계1 | bus → walk |
| stop-001 → destination-001 병원 | 직통, 환승0, 버스 정류장 합계2 | bus → walk |
| stop-001 → destination-003 터미널 | 환승1, 버스 정류장 합계4 | bus → transfer → bus → walk |
| stop-005 → destination-001 병원 | 역방향을 만들지 않아 routeOptions=[] | 상세 후보 없음 |

ID 표의 stop/destination에는 실제로 `demo-` 접두사를 사용한다. 노선1의 순번3 → 노선2의 순번1, 둘 다 `demo-stop-003`인 명시적 합성 연결만 환승으로 사용한다. 같은 이름·좌표가 있다는 이유로 환승하지 않는다. 최대 1회 환승이며 후보 정렬 기준은 환승 수 → 버스 정류장 수 합계 → 안정적인 노선/승하차 순번 키다. 중복 제거 후 최대 3개를 반환한다. 현재 기본 합성 자료에서는 각 위 목적지에 후보가 하나씩이다.

상세 segments는 배열 순서대로 사용한다. 모든 segmentId는 해당 경로 안에서 고유하다. bus는 승하차 stationId·이름·순번과 stopCount를 제공한다. stopCount는 출발을 제외하고 하차를 포함한 실제 경유 행 수다. transfer의 fromSegmentId/toSegmentId는 앞뒤 버스 구간을 가리킨다. 최종 walk는 등록된 목적지 접근 연결이다. 거리·구간/전체 소요시간이 미확인이면 null을 유지하며 0분이나 추정 거리로 채우지 않는다.

검색의 expiresAt과 상세 computedAt은 시간대 포함 ISO 8601이고 검색 수명은 600초다. 상세는 저장된 검색 스냅샷을 사용하므로 같은 검색·옵션의 반복 조회는 computedAt·구간·버전이 동일하다. meta.generatedAt과 requestId는 각 응답을 생성할 때의 별도 값이다. A가 전달한 요약을 상세의 교통 사실 원본으로 삼지 않는다.

## 정상·빈 결과·오류

공개 응답은 data/error/meta 봉투다. 검색 성공/빈 결과는 200이고, 실패는 data=null이다. A/B는 원문 내부 예외 대신 서비스 code와 message를 사용한다.

| 상황 | HTTP / code | 사용자 흐름 |
| --- | --- | --- |
| 경로 검색·저장 상세 조회 | 200, error=null | 후보 선택·검증된 구간 표시 |
| 역방향 등 경로 없음 | 200, routeOptions=[] | 다른 목적지/출발을 선택 |
| ID·시각 형식/필수 필드 오류 | 400 INVALID_REQUEST | 입력 확인, POST 자동 재시도 없음 |
| 등록되지 않은 출발·목적지·검색·옵션 | 404 NOT_FOUND | 기존 값을 섞지 않고 다시 선택 |
| 검색 만료 | 410 ROUTE_SEARCH_EXPIRED | 새 검색으로 시작 |
| 경로 자료·상태·버전 변경 | 409 ROUTE_VERSION_CHANGED | 기존 상세와 혼합하지 않고 재검색 |
| 핵심 자료를 확인할 수 없음 | 503 TRANSPORT_DATA_UNAVAILABLE | 확인 불가 표시 |

이 단계의 실제 HTTP 기록은 정상·빈 결과·400·404에 집중한다. 409/410/503은 공통 실패 규칙과 후속 단계의 상태/시간 검증 대상이다. 범위 밖 운행·AI·음성·인쇄 UI를 이 도구에서 구현하지 않았다.

## 재현 명령과 실제 수행 여부

프로젝트 루트에서 다음 명령을 실제 실행했다.

```powershell
backend/.venv/Scripts/python -m backend.tools.verify_stage4
```

독립 메모리 SQLite DB와 명시적 DemoProvider를 쓰는 Uvicorn 자식 서버를 `127.0.0.1:8000`에서 실행해 **21개 실제 HTTP 검색·상세 사례**와 두 로컬 origin의 POST/GET CORS, OpenAPI 요청·응답 명세를 검증했다. 생성한 자식만 종료하며 기존 실행 DB나 시연 상태 파일을 바꾸지 않는다. 8000 포트가 사용 중이면 중단하므로 기존 서버를 종료하지 않는다.

아래는 선택 실행 방법이며 이번에는 별도로 실행하지 않았다.

```powershell
backend/.venv/Scripts/python -m backend.tools.verify_stage4 --port 8001
backend/.venv/Scripts/python -m backend.tools.verify_stage4 --base-url http://127.0.0.1:8000
```

`--base-url`은 이미 실행 중인 정상 demo 서버를 대상으로 하며 POST 검색 스냅샷을 그 서버 DB에 추가한다. 합성 원본·기존 행을 덮어쓰거나 DB를 삭제하지 않는다. 테스트만 필요하면 기본 독립 메모리 DB 방식을 사용한다.

실제 요청·응답·HTTP 상태·소요시간은 `stage4-http-examples.json`의 cases에 있다. 요청 예시의 departAt은 재실행 시 현재 시각으로 만들도록 표시하고, 당시 응답 값은 그대로 기록했다. selections에는 시장/병원/터미널 각각의 **A→B 6개 필드**를 제공한다. 기록 속 search/option/version은 해당 검증 서버에서 만든 값이므로 다른 서버나 나중 실행에 복사해 재사용하지 않는다.

## A/B와 공동 확인할 항목

A는 5173 앱에서 8000 백엔드로 `/api` 접두사를 유지하는 개발 프록시를 설정하고, 검색 후 선택한 6개 필드를 B에 넘겨야 한다. B는 검색/옵션 식별자로 상세를 다시 조회하고 출발·목적지·버전을 대조해야 한다. HTTP 도구에서 이 객체와 상세의 값 일치는 확인했지만 실제 라우터·화면 상태 전달·새로고침/뒤로가기·오류 UI는 확인하지 못했다. frontend 파일을 수정하거나 A/B에게 메시지를 전송하지 않았다.
