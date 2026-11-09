# 내부 API 계약 v0.1 — 구현 기준

이 문서는 프론트엔드·백엔드·AI의 **우리 서비스 내부 API 계약 v0.1**이다. 사용자의 요청에 따라 작성한 개발 기준안이며 실제 팀원의 합의 완료를 뜻하지 않는다. 기술과 시연 범위는 [development-plan.md](development-plan.md)를 따른다. 현재 합성 데이터 백엔드와 규칙 기반 AI가 구현되어 있으며 [생성 OpenAPI](../backend/docs/openapi.json) 및 [7단계 결과](stage7-integration-report.md)와 대조한다. 이 문서는 외부 제공기관의 API 명세가 아니다. 외부 교통 제공자·운영 배포 주소·운영 인증은 미정이고 실제 제공 필드·지역·갱신 주기·운행 변경 지원 여부는 확인 필요다.

모든 JSON의 `demo-` ID, 장소·노선 이름, 시간은 실제 운행과 무관한 합성 예시다. 예시 시각은 고정된 설명용 값이며 현재 시각이나 실제 데이터 갱신을 뜻하지 않는다. 코드 블록은 요청/응답 구조 예시이며 실행 프로그램이 아니다.

## 1. 연결과 공통 규칙

- 프론트엔드는 백엔드의 공개 서비스 API만 호출한다. 외부 데이터 키와 AI 접근 정보는 프론트엔드에 전달하지 않는다.
- 백엔드는 등록된 교통 데이터와 경로 계산 결과를 검증하고 외부 필드를 내부 모델로 변환한다. 시연은 등록된 합성 노선에서 직통·최대 1회 환승 후보를 열거하고 환승 수·버스 정류장 수·식별자 순으로 최대 3개를 반환한다. 실데이터의 연결 가능성은 별도로 검증한다.
- 백엔드는 등록된 목적지 후보 또는 검증 경로의 구간 ID·허용 표현만 AI에 전달한다. AI가 외부 교통 API나 프론트엔드와 직접 연결된다고 가정하지 않는다.
- ID는 불투명한 문자열이다. 표시 이름을 ID로 쓰지 않으며 제공기관 간 ID 매핑은 백엔드가 관리한다.
- 계약 필드명은 lowerCamelCase를 사용한다. 시간은 시간대 오프셋이 있는 ISO 8601 문자열을 사용하고 사용자 표시 시간대는 `Asia/Seoul`을 사용한다. 소요·남은 시간은 초 단위다. 서버는 시각을 UTC로 비교하고 직렬화 시 시간대 오프셋을 유지한다.
- 알 수 없는 값은 `null`과 상태 필드로 표현한다. `0분`, 빈 문자열, 현재 시각으로 대체하지 않는다. 없는 알림과 조회 실패를 구분한다.
- 공개 응답은 아래 봉투를 사용한다. 성공 시 `error=null`, 실패 시 `data=null`이다. `generatedAt`은 응답 생성 시각이며 교통정보의 최종 갱신 시각이 아니다.

```json
{
  "data": {},
  "error": null,
  "meta": {
    "requestId": "demo-request-001",
    "generatedAt": "2026-10-25T10:00:00+09:00",
    "dataMode": "demo"
  }
}
```

`dataMode`는 `demo | live`다. 서버가 정하며 클라이언트가 live로 승격하지 않는다. live 데이터 일부가 실패하면 시연 값으로 조용히 채우지 않고 해당 항목을 unavailable 또는 stale로 반환한다. 시연 모드 표시는 모든 화면·인쇄·음성 안내에 반영한다.

## 2. 공통 데이터 모델

| 모델 | 주요 필드와 의미 | 대표 관리자 |
| --- | --- | --- |
| Station | `stationId`, `name`, `directionLabel`, `region`, `coordinates`(확인 전 null). 같은 이름/반대편 정류장 구분 | 백엔드 |
| Destination | `destinationId`, `name`, `category`, `aliases`. 등록·확인된 장소 후보. 장소와 접근 정류장의 연결도 검증 대상 | 백엔드 |
| TransitRoute / RouteStop | `routeId`, `routeName`, `directionLabel`; `stationId`, `sequence`. 순환/반복 정차 시 ID와 순번으로 승하차 지점 구분 | 백엔드 |
| RouteOption | 검색 결과에서 고르는 하나의 이동 경로. 버스 노선 ID와 다르다. `routeOptionId`, `routeSnapshotVersion`, `journeyStatus`, 요약 필드 | 백엔드 |
| RouteDetail | `routeSearchId`, `routeOptionId`, `routeSnapshotVersion`, `originStationId`, `destinationId`, `computedAt`, `journeyStatus`, `segments`, `referenceDataQuality` | 백엔드 |
| DataQuality | `sourceId`, `sourceUpdatedAt`, `fetchedAt`, `freshness`. freshness는 `fresh | stale | unknown`이며 도착·운행 변경의 시연 임계값은 90초(12절 참고) | 백엔드 |
| RouteSelection | A→B의 선택 식별자·버전·데이터 모드. 상세 사실 데이터의 원본이 아니다 | 프론트엔드 A |
| GuideTemplateChoice | 검증된 구간 ID에 대응하는 허용 템플릿 ID. 사실 값을 새로 생성하지 않는다 | AI |

목적지 분류 초안은 `hospital | market | terminal | station | other`다. 장소와 버스 정류장을 의미하는 stationId는 별도 개념이다.

`journeyStatus`는 `ready | recheck_required | unavailable`이다. ready는 해당 데이터 모드와 확인된 경로 자료 안에서 이용 순서를 검증했다는 뜻이다. 현실의 운행을 보증하거나 모든 항목이 실시간임을 뜻하지 않는다. 도보·환승 연결 근거가 없으면 가능한 환승으로 확정하지 않는다.

`segments`는 순서가 있는 배열이며 모든 구간은 고유 `segmentId`를 가진다.

| 구간 type | 필수 구조 | 미확인 값 처리 |
| --- | --- | --- |
| `bus` | `routeId`, `routeName`, `boardStation`, `alightStation`, `boardSequence`, `alightSequence`, `stopCount`, `durationSeconds` | 순번·정류장 수는 확인된 경유 순서로 계산한다. 소요시간은 미확인 시 null |
| `walk` | `fromLabel`, `toLabel`, `distanceMeters`, `durationSeconds` | 검증한 도보 연결만 경로에 사용한다. 거리·시간 미제공 시 null; 임의 속도로 시간을 만들지 않는다 |
| `transfer` | `fromSegmentId`, `toSegmentId`, `atStation`, `instructionTemplateId` | 연결되는 버스 구간·환승 지점 확인이 필수다. 도보 이동이 있으면 별도 walk 구간으로 포함한다 |

`boardStation`, `alightStation`, `atStation`은 `{ "stationId": "...", "name": "..." }` 구조다. `stopCount`는 출발 정류장을 제외하고 하차 정류장을 포함해 앞으로 지나는 정류장 수로 정의한다. 실제 경유 순서에 따라 산정하며 이름만 비교하지 않는다. UI와 출력물은 이 정의를 함께 사용한다.

## 3. 프론트엔드 → 백엔드 API 목록

아래 경로의 `/api/v1`은 내부 접두사다. 구현할 목록이며 현재 호출 가능한 서버가 있다는 뜻은 아니다.

| 메서드·경로 | 요청 | 성공 시 data 구조·사용처 |
| --- | --- | --- |
| `GET /api/v1/stations/{stationId}` | 시연 설정 등으로 지정한 현재 정류장 ID | `{station: Station}`. A의 시작 화면 |
| `GET /api/v1/destinations` | 필수 `originStationId`; 선택 `query`, `category` | `{destinations: Destination[]}`. 텍스트 검색·주요 장소 선택. 두 선택 조건을 함께 주면 교집합 |
| `POST /api/v1/route-searches` | `originStationId`, `destinationId`, `departAt` | `{routeSearchId, originStationId, destinationId, expiresAt, routeOptions: RouteOption[]}`. A의 경로 선택 |
| `GET /api/v1/route-searches/{routeSearchId}/options/{routeOptionId}` | 경로 선택 식별자 | `RouteDetail`. B의 승차·하차·정류장 수·도보·환승 |
| `GET /api/v1/route-searches/{routeSearchId}/options/{routeOptionId}/live` | 선택 경로의 식별자 | `{routeSnapshotVersion, arrivals, serviceChanges}`. B의 도착·운행 현황·변경·갱신 시각 |
| `POST /api/v1/destination-interpretations` | `originStationId`, `text` | `{status, candidates: Destination[], reasonCode}`. 추가 제안인 자연어 검색; 백엔드가 후보 ID를 재검증 |
| `POST /api/v1/easy-guidance` | `routeSearchId`, `routeOptionId`, `expectedRouteSnapshotVersion` | `{routeSnapshotVersion, mode, steps}`. 검증 경로의 쉬운 안내; 추가 제안 |
| `POST /api/v1/print-guides` | `routeSearchId`, `routeOptionId`, `expectedRouteSnapshotVersion` | `{printGuideId, generatedAt, routeDetail, liveInfoSnapshot, notice}`. B가 인쇄용 스냅샷을 화면으로 렌더링 |

검색 결과 없음은 성공 응답의 빈 배열로 표현한다. departAt은 현재 출발 조회를 위한 필수 시각이며 서버 시각과 절댓값 120초 이내인 요청만 허용한다. 검색 query는 공백 제거 후 최대 100자, AI text는 1~200자다. 전체 시연 목적지는 3개여서 페이지 분할을 사용하지 않는다. 로컬 시연은 로그인 없이 사용하고 CORS는 로컬 프론트 주소로 제한한다. 운영 인증·배포 주소는 후속 결정이다.

## 4. 프론트엔드 A → B 공통 전달 데이터

대표 관리자는 A이며 백엔드 계약 변경 시 B와 함께 조정한다. 단일 앱의 React Context + useReducer에서 선택과 화면 상태를 관리한다. 새로고침으로 상태가 사라지면 시작 화면으로 이동한다.

```json
{
  "originStationId": "demo-stop-001",
  "destinationId": "demo-destination-001",
  "routeSearchId": "demo-search-001",
  "routeOptionId": "demo-option-001",
  "routeSnapshotVersion": "demo-v1",
  "dataMode": "demo"
}
```

| 필드 | 의미·검증 규칙 |
| --- | --- |
| `originStationId` | 현재 출발 정류장. 상세 응답의 출발 정류장과 일치해야 한다 |
| `destinationId` | 사용자가 확정한 등록 목적지 ID. 자연어 원문만 넘기지 않는다 |
| `routeSearchId` | 백엔드가 생성한 검색 결과 묶음. 검색 스냅샷을 저장하며 생성 후 10분 유효 |
| `routeOptionId` | 그 검색에서 선택한 이동 경로. 버스 노선 ID와 구분 |
| `routeSnapshotVersion` | A가 선택할 당시 경로의 버전. B의 조회/인쇄 준비에서 변경 감지 |
| `dataMode` | 선택 당시 모드 표시용. 상세 응답이 최종 기준이며 불일치 시 다시 조회/선택 |

B는 ID 누락·만료·새로고침 후 상태 소실 시 다시 선택하도록 안내한다. 상세 조회 버전이 달라졌거나 live 응답이 다른 경로 버전을 참조하면 기존 값과 섞지 않고 상세를 다시 조회한다. 변경된 경로를 사용자가 확인하기 전에는 이전 선택으로 인쇄를 진행하지 않는다.

## 5. 경로 요청·응답 예시

경로 검색 요청 예시:

```json
{
  "originStationId": "demo-stop-001",
  "destinationId": "demo-destination-001",
  "departAt": "2026-10-25T10:00:00+09:00"
}
```

성공 응답의 `data` 예시:

```json
{
  "routeSearchId": "demo-search-001",
  "originStationId": "demo-stop-001",
  "destinationId": "demo-destination-001",
  "expiresAt": "2026-10-25T10:10:00+09:00",
  "routeOptions": [
    {
      "routeOptionId": "demo-option-001",
      "routeSnapshotVersion": "demo-v1",
      "journeyStatus": "ready",
      "routeNames": ["시연 1번"],
      "transferCount": 0,
      "totalDurationSeconds": null,
      "walkingDurationSeconds": null
    }
  ]
}
```

동일한 경로의 상세 응답 `data` 예시:

```json
{
  "routeSearchId": "demo-search-001",
  "routeOptionId": "demo-option-001",
  "routeSnapshotVersion": "demo-v1",
  "originStationId": "demo-stop-001",
  "destinationId": "demo-destination-001",
  "computedAt": "2026-10-25T10:00:00+09:00",
  "journeyStatus": "ready",
  "referenceDataQuality": {
    "sourceId": "demo-fixture",
    "sourceUpdatedAt": null,
    "fetchedAt": "2026-10-25T10:00:00+09:00",
    "freshness": "unknown"
  },
  "segments": [
    {
      "segmentId": "demo-leg-bus-001",
      "type": "bus",
      "routeId": "demo-route-001",
      "routeName": "시연 1번",
      "boardStation": {"stationId": "demo-stop-001", "name": "시연 출발 정류장"},
      "alightStation": {"stationId": "demo-stop-003", "name": "시연 병원 앞 정류장"},
      "boardSequence": 1,
      "alightSequence": 3,
      "stopCount": 2,
      "durationSeconds": null
    },
    {
      "segmentId": "demo-leg-walk-001",
      "type": "walk",
      "fromLabel": "시연 병원 앞 정류장",
      "toLabel": "시연 병원",
      "distanceMeters": null,
      "durationSeconds": null
    }
  ]
}
```

위의 연결은 합성 시나리오 안에서 정의한 경로다. 실제 도보·환승 가능성이나 운행 검증을 뜻하지 않는다. 실제 데이터로 전환할 때는 정류장 순서, 방향, 연결 가능성과 출처를 별도로 검증한다.

## 6. 실시간 도착·운행 변경·시간 표시

성공 응답의 `data` 예시다. 300초는 시연 수치다.

```json
{
  "routeSnapshotVersion": "demo-v1",
  "arrivals": [
    {
      "segmentId": "demo-leg-bus-001",
      "routeId": "demo-route-001",
      "boardStationId": "demo-stop-001",
      "arrivalStatus": "available",
      "etaSeconds": 300,
      "expectedArrivalAt": "2026-10-25T10:05:00+09:00",
      "operationStatus": "unknown",
      "dataQuality": {
        "sourceId": "demo-fixture",
        "sourceUpdatedAt": null,
        "fetchedAt": "2026-10-25T10:00:00+09:00",
        "freshness": "unknown"
      }
    }
  ],
  "serviceChanges": {
    "coverageStatus": "unknown",
    "items": [],
    "dataQuality": {
      "sourceId": null,
      "sourceUpdatedAt": null,
      "fetchedAt": null,
      "freshness": "unknown"
    }
  }
}
```

- `arrivalStatus`: `available | unavailable`. available은 값이 있다는 뜻이다. 현재성은 dataQuality를 별도로 확인한다.
- `operationStatus`: `running | not_running | unknown`. 도착 데이터가 없다는 이유로 결행이라고 판단하지 않는다. 실제 제공 필드에 대응할 수 있을 때만 상태를 매핑한다.
- `serviceChanges.coverageStatus`: `available | unknown`. items가 비어 있고 coverageStatus가 unknown이면 `운행 변경 정보 확인 불가`로 표시한다. 정상 운행이나 변경 없음으로 단정하지 않는다. available이어도 해당 출처가 조회한 범위와 시각을 함께 표시한다.
- 변경 항목 초안: `{changeId, type, affectedRouteIds, affectedStationIds, title, description, validFrom, validUntil, dataQuality}`. type은 `timetable_change | cancellation | detour | other`다. 미확인 적용 시각은 null이며 출처에 없는 내용을 채우지 않는다.
- 항목마다 `sourceUpdatedAt`을 최종 원천 갱신 시각으로 표시한다. 제공되지 않으면 `원천 갱신 시각 확인 불가`, 별도로 `서버 수집 시각`을 표시한다. `meta.generatedAt`이나 화면을 새로 그린 시각으로 대체하지 않는다.
- 시연은 원천 갱신 후 0~90초면 fresh, 90초 초과면 stale, 원천 시각이 없거나 미래이면 unknown이다. 화면 조회 간격은 30초, 클라이언트 제한시간은 5초다. 실제 제공자 연동 시 호출·갱신 정책을 확인하여 별도 재검토한다. 오래된 값은 현재 도착 정보처럼 표시하지 않는다. 마지막 값을 참고로 유지할 경우 그 시각과 `오래된 정보` 표시를 붙인다.
- 모든 부분 데이터의 갱신 시각을 하나의 시각으로 덮지 않는다. live의 경로 버전이 상세와 다르면 먼저 상세를 재조회한다.

## 7. 안내표와 브라우저 인쇄

`POST /api/v1/print-guides`는 인쇄 준비용 내부 설계 제안이다. 서버가 선택 경로의 버전·이용 가능 상태를 다시 확인하고, 같은 경로 상세와 실시간 정보의 스냅샷을 반환한다. `routeDetail`은 5절의 구조, `liveInfoSnapshot`은 6절의 구조를 사용한다. `notice`에는 시연 여부·시각·확인 불가 상태를 나타내는 서버의 표시 문구를 담는다.

B는 같은 `routeSnapshotVersion`으로 승차 버스·승하차 정류장·정류장 수·도보·환승 순서·목적지를 렌더링하고 인쇄 UI를 제공한다. 화면용 버튼·내비게이션을 제외하는 인쇄 레이아웃과 브라우저 인쇄 미리보기를 계획한다. A4 세로·여백 15mm·본문 16pt를 시작 기준으로 삼고 긴 구간은 페이지를 나누어 브라우저에서 확인한다.

`generatedAt`은 안내표 생성 시각이다. 종이 출력 완료 시각이나 프린터 성공을 의미하지 않는다. 인쇄물에는 교통정보의 원천 갱신 시각/확인 불가 상태를 별도로 표시한다. 경로가 ready이면 실시간 정보 미수신을 명시하고 인쇄를 허용한다. 변동하는 도착 카운트다운은 종이에 넣지 않는다. 결행·경로 변경 등으로 이용 불가가 확인되거나 버전이 바뀌면 기존 확정 안내를 중단하고 재선택하도록 한다. 프린터 직접 제어·기기 탐지·출력 완료 판정은 확장 과제다.

## 8. AI 목적지 표현 해석 — 추가 제안

공개 요청 예시: `{originStationId, text}`. 백엔드는 텍스트 길이 등 입력을 검증하고 현재 정류장/시연 범위에 맞는 등록 후보만 구성한다. 현재 연결은 `ai.adapter.RuleBasedAIAdapter`의 동기 함수 `interpret_destination(payload)`를 호출한다. `backend.main:app`은 이 어댑터를 기본으로 연결하며 외부 모델·네트워크 없이 규칙 기반으로 동작한다. 테스트나 별도 앱에서 `create_app()`에 어댑터를 주입하지 않으면 기존 `unavailable` 대체 동작을 유지한다. 내부 HTTP 경로는 구현하지 않았다.

AI 내부 요청 예시:

```json
{
  "text": "큰 병원에 가고 싶어요",
  "dataMode": "demo",
  "allowedDestinations": [
    {"destinationId": "demo-destination-001", "name": "시연 병원", "aliases": ["시연 큰 병원"]}
  ]
}
```

AI 내부 응답 예시:

```json
{
  "status": "needs_confirmation",
  "candidateDestinationIds": ["demo-destination-001"],
  "reasonCode": "USER_CONFIRMATION_REQUIRED"
}
```

2026-11-02 기준 AI 내부 응답과 공개 응답의 상태별 이유 코드는 다음으로 통일한다.

| status | 후보 개수 | reasonCode | 화면 동작 |
| --- | --- | --- | --- |
| `matched` | 정확히 1개 | `MATCHED` | 목적지를 확인하고 사용자가 선택 |
| `needs_confirmation` | 1개 이상 | `USER_CONFIRMATION_REQUIRED` | 후보를 표시하고 사용자가 선택 |
| `no_match` | 0개 | `NO_REGISTERED_MATCH` | 일반 검색·주요 장소 선택 |
| `unavailable` | 0개 | `AI_UNAVAILABLE` | 일반 검색·주요 장소 선택 |

`matched`도 목적지 자동 확정을 의미하지 않는다. 동명 장소·모호한 표현은 후보를 표시하고 확인받는다. 오타로 추정한 결과는 후보가 1개여도 `needs_confirmation`을 유지한다. 백엔드는 후보 수가 하나라는 이유로 이를 `matched`로 바꾸지 않는다. 기준선의 구체적인 매칭·오타 추정 규칙은 [AI 계약](../ai/contracts/README.md)과 [목적지 해석 모듈](../ai/destination_interpretation/README.md)을 따른다.

백엔드는 후보 ID가 allowedDestinations의 부분집합인지 검증하고 직접 보관한 Destination 값으로 공개 응답 candidates를 구성한다. AI가 반환한 새로운 장소·좌표·노선은 사용하지 않는다. 공개 reasonCode는 백엔드가 검증된 status에서 위 표대로 결정하며, 어댑터가 반환한 이유 코드나 자유 문구를 그대로 노출하지 않는다. 기존 `NO_MATCH`는 공개 이유 코드로 사용하지 않는다. no_match이면 일반 검색/주요 장소 선택, unavailable 또는 시간초과이면 같은 수동 경로로 대체한다.

## 9. AI 쉬운 한국어 안내 — 추가 제안

검증된 경로를 쉽게 설명하되 AI가 숫자·이름·노선·환승·도착 시각을 새로 만들지 않도록, 초기 계약은 **허용된 안내 템플릿 선택 + 백엔드의 사실 값 삽입** 방식으로 제안한다. 자유 서술로 교통 사실을 생성하는 기능은 초기 계약에 포함하지 않는다.

공개 요청은 경로 식별자와 `expectedRouteSnapshotVersion`만 받는다. 클라이언트가 임의의 경로 사실을 만들어 AI에 직접 전달하지 않는다. 백엔드가 저장/검증한 RouteDetail을 읽어 내부 요청을 구성하고 같은 어댑터의 동기 함수 `choose_guidance(payload)`를 호출한다. 내부 HTTP 경로는 구현하지 않았다.

AI 내부 요청 예시:

```json
{
  "routeSnapshotVersion": "demo-v1",
  "dataMode": "demo",
  "verifiedSegments": [
    {"segmentId": "demo-leg-bus-001", "type": "bus", "allowedTemplateIds": ["bus.basic"]},
    {"segmentId": "demo-leg-walk-001", "type": "walk", "allowedTemplateIds": ["walk.basic"]}
  ]
}
```

AI 내부 응답 예시:

```json
{
  "status": "ok",
  "routeSnapshotVersion": "demo-v1",
  "steps": [
    {"segmentId": "demo-leg-bus-001", "templateId": "bus.basic"},
    {"segmentId": "demo-leg-walk-001", "templateId": "walk.basic"}
  ]
}
```

AI 내부 status는 `ok | unavailable`이다. 현재 규칙 기반 기준선은 구간 유형별 `bus.basic`, `walk.basic`, `transfer.basic`을 선택한다. 여러 허용 표현은 AI·디자인 담당이 함께 검토한다. `ai/contracts/`는 구체 스키마, `ai/easy_guidance/`는 템플릿과 선택 로직을 관리한다. Python 모듈 경로는 `ai.destination_interpretation`, `ai.easy_guidance`로 통일한다.

백엔드는 버전, 구간 ID, 구간 순서, 누락·추가·중복, 구간 유형별 허용 템플릿을 검사한다. 검증된 정류장명·노선명·정류장 수는 백엔드가 템플릿 슬롯에 넣는다. 미확인 시간·도착 수치는 생략하거나 확인 불가 표현을 사용하며 AI가 채우지 않는다.

공개 응답은 `{routeSnapshotVersion, mode, steps}`이며 mode는 `ai_assisted | template_fallback`이다. 공개 steps의 항목은 `{segmentId, text}`다. AI 실패·유효하지 않은 출력·시간초과 시 같은 검증 경로로 고정 템플릿을 적용하고 template_fallback으로 반환한다. 텍스트는 일반 문자열로 처리하며 임의 HTML을 실행하지 않는다. B는 이 안내를 음성·화면에서 사용하되 구조화된 교통 사실을 항상 기준으로 삼는다.

## 10. 오류·만료·실패 처리

오류 응답 예시:

```json
{
  "data": null,
  "error": {
    "code": "ROUTE_VERSION_CHANGED",
    "message": "경로 정보가 바뀌었습니다. 다시 확인해 주세요.",
    "retryable": true
  },
  "meta": {
    "requestId": "demo-request-002",
    "generatedAt": "2026-10-25T10:01:00+09:00",
    "dataMode": "demo"
  }
}
```

| HTTP 상태 | 서비스 code/상태 | 화면·서버 처리 |
| --- | --- | --- |
| 200 | 검색 결과 빈 배열 | 결과 없음. 사용자가 목적지를 다시 선택 |
| 400 | `INVALID_REQUEST` | ID·형식·지원하지 않는 출발 시각 등 입력 확인 |
| 404 | `NOT_FOUND` | 등록되지 않은 정류장/목적지/경로 확인 후 재선택 |
| 409 | `ROUTE_VERSION_CHANGED` | 기존 버전과 혼합 금지. 상세/경로 재조회 후 확인 |
| 409 | `ROUTE_UNAVAILABLE` | 확인된 결행·우회 등으로 기존 경로 이용 불가. 재검색 |
| 410 | `ROUTE_SEARCH_EXPIRED` | 생성 후 10분이 지난 검색. 다시 검색 |
| 503 | `TRANSPORT_DATA_UNAVAILABLE` | 핵심 경로 검증 자료가 없을 때 가능한 경로라고 확정하지 않음 |
| 200, 항목별 unavailable/unknown | 실시간 부분 실패 | 확인 불가·갱신 상태 표시. 정상/결행을 추정하지 않음 |
| 200, AI unavailable 또는 template_fallback | AI 실패 | 일반 검색 또는 고정 안내로 계속 진행 |

외부 제공자 오류·개인정보·키·내부 접근정보를 사용자 메시지나 로그 예시에 넣지 않는다. 시연의 재시도·제한시간·만료·입력 제한은 12절을 따른다. 실제 외부 제공자 요청 제한과 운영 보관 정책은 확인 필요다.

## 11. 평가와 변경 관리

- AI 평가에는 같은 이름의 목적지, 모호한 표현, 후보 없음, 목록 밖 ID, 경로 버전 불일치, 구간 누락/추가, 틀린 템플릿, 시간초과를 포함한다. 실제 사례·기준·목표치는 `ai/evaluation/`에 후속 작성한다.
- A/B/백엔드는 정의한 ID·버전·상태·시각·폴링 정책으로 구현하고 변경할 때 같은 PR에서 계약을 갱신한다.
- 백엔드/AI는 후보 제한, 스키마, 허용 템플릿, 검증 및 대체 동작을 합의한다. 백엔드가 최종 교통 사실을 소유한다.
- 디자인/A/B는 개발 기준안의 화면·접근성·음성·인쇄 기준을 실제 브라우저에서 확인한다. 특정 접근성 표준 준수 완료를 주장하지 않는다.
- 설치/실행 명령은 실제 코드로 검증한 뒤 추가한다. 실제 출처·커버리지·호출 제한·환승 검증과 운영 인증은 외부 데이터 연동 단계에서 확인하고 갱신한다.

## 12. v0.1 처리 정책

- 시연의 dataMode는 demo다. backend FastAPI가 SQLite/SQLAlchemy의 등록 자료를 조회하고 프론트엔드는 fetch 클라이언트를 사용한다. 실제 연결 검증 전 live를 활성화하지 않는다.
- 개발 포트는 프론트 5173·백엔드 8000이다. 프론트는 /api 상대 경로를 호출하고 Vite 개발 프록시가 백엔드로 전달한다. CORS 허용 대상은 로컬 프론트 주소만 설정한다. 배포 주소는 아직 없다.
- 검색 응답은 expiresAt을 포함하고 생성 후 10분 유효하다. 조회·안내문 생성·인쇄 준비에서 만료를 검사한다. 존재하지만 만료된 검색은 410, 존재하지 않는 ID는 404로 처리한다.
- routeSnapshotVersion은 경유 순서·연결·적용되는 운행 변경이 바뀔 때 갱신한다. 단순 ETA 갱신은 버전 변경 사유가 아니다. 상세/live/출력 스냅샷의 버전이 다르면 혼합하지 않는다.
- 상세 화면 진입 시 live를 조회하고 활성 상태에서 30초마다 반복한다. 화면 이탈이나 브라우저 문서 비활성화 시 반복 요청을 중지하고 복귀 시 다시 조회한다. 인쇄용 스냅샷에는 반복 갱신을 적용하지 않는다.
- 도착·운행 변경 자료의 sourceUpdatedAt이 서버 시각 기준 0~90초 전이면 fresh, 90초 초과면 stale, 없거나 미래이면 unknown이다. 정적 노선 자료는 별도 데이터 버전으로 관리한다. 이는 시연 정책이며 외부 제공자 연동 시 재검토한다.
- stale/unknown 도착 수치를 현재 예측처럼 표시하지 않는다. serviceChanges의 unknown을 변경 없음이나 정상 운행으로 바꾸지 않는다.
- 클라이언트 제한시간은 5초다. GET의 일시적 연결 실패/5xx만 1초 뒤 1회 재시도한다. 4xx·POST는 자동 재시도하지 않고 사용자가 다시 시도할 수 있게 한다.
- AI 결과 채택 예산은 1초다. 실패·시간초과·잘못된 ID/템플릿은 일반 검색 또는 template_fallback으로 대체한다. 고비용 모델을 시험할 때는 실행 격리를 검토하고 기한이 지난 결과는 채택하지 않는다.
- FastAPI의 기본 입력 검증 오류는 서비스 구현에서 400 INVALID_REQUEST와 공통 오류 봉투로 변환한다. 사용자 입력·템플릿·외부 값을 검증하며 기본 오류 응답을 그대로 섞지 않는다.
- 인쇄는 ready인 경로에 허용한다. 도착 정보 미수신은 문구로 표시하고 종이에 도착 카운트다운을 넣지 않는다. 확인된 경로 이용 불가면 409 ROUTE_UNAVAILABLE, 버전 불일치면 409 ROUTE_VERSION_CHANGED다. generatedAt은 종이 출력 완료 시각이 아니다.
- 위 정책은 구현 기준이다. API·규칙 기반 AI·인쇄용 JSON의 실행 결과와 미구현 UI·브라우저 인쇄를 [7단계 결과](stage7-integration-report.md)에서 구분한다.
