# 5단계 도착·운행 변경·최신성 API 연동 안내

v2 계획서의 5단계를 위한 B 담당자 연동 자료다. **시연 데이터 · 실제 운행 정보 아님**. 실제 외부 교통 API·기관·제공 범위는 아직 연결하거나 확인하지 않았다. 프론트엔드 B 화면도 자리 표시자 상태이므로 HTTP 검증과 실제 브라우저 공동 확인을 구분한다.

## 선택 경로와 live 조회

먼저 정상 검색에서 선택한 routeSearchId/routeOptionId로 다음 API를 조회한다.

```text
GET /api/v1/route-searches/{routeSearchId}/options/{routeOptionId}/live
```

성공 data는 routeSnapshotVersion/arrivals/serviceChanges다. arrivals는 버스 구간별 segmentId, routeId, boardStationId를 포함한다. B는 상세의 구간 ID·경로 버전과 일치하는 값만 함께 표시한다. A가 전달한 오래된 선택 객체를 운행 사실의 원본으로 삼지 않는다.

| 값 | 의미 / 표시 |
| --- | --- |
| arrivalStatus=available | 도착 값이 있다는 뜻. 현재성은 dataQuality로 별도 확인 |
| arrivalStatus=unavailable | 도착 미수신/확인 불가. etaSeconds/expectedArrivalAt은 null이며 0분 도착이나 결행이 아님 |
| operationStatus=running/not_running/unknown | 별도 운행 증거. 도착 수신 여부만으로 추정하지 않음 |
| serviceChanges.coverageStatus=available | 해당 조회 범위의 변경 자료를 확인함. 전체 현실 운행을 보증하지 않음 |
| serviceChanges.coverageStatus=unknown | 운행 변경 조회 확인 불가. 빈 items를 변경 없음으로 표시하지 않음 |

도착 값이 없어도 별도의 명시적 운행 증거가 있으면 running일 수 있다. 반대로 현재 적용되는 fresh not_running 증거가 확인되면 선택 경로를 계속 안내하지 않고 409로 재선택을 요구한다. 합성 결행·우회·시간표 변경도 상세/live의 경로 재검사에 반영한다.

## 세 시각과 최신성

| 필드 | 의미 |
| --- | --- |
| sourceUpdatedAt | 정보 원천이 갱신한 시각. 없으면 null과 확인 불가 표시 |
| fetchedAt | 서버가 해당 자료를 수집/보관한 시각. 원천 시각을 대신하지 않음 |
| meta.generatedAt | 이번 API 응답을 만든 시각. 교통 최종 갱신 시각이 아님 |

서버는 UTC로 비교하고 시간대 포함 ISO 8601을 반환한다. UI는 Asia/Seoul로 표시한다. 원천 나이 0~90초는 fresh, 90초 초과는 stale, 원천 시각 없음/미래는 unknown이다. 새 응답을 받았다는 이유로 오래된 sourceUpdatedAt을 현재 시각으로 바꾸지 않는다. 항목마다 다른 출처·시각·품질을 하나의 '최종 갱신 시각'으로 덮지 않는다.

합성 도착은 발행 시각 +300초인 고정 이벤트다. 30초 후 같은 이벤트를 조회하면 ETA는 300→270초이며 경로 버전은 동일하다. 시간이 지난 ETA를 새 5분 도착으로 다시 생성하지 않는다. fresh/stale/unknown도 경로 자체의 버전과 구분한다. 경유·환승 연결·현재 경로 관련 운행 변경은 버전/상태에 반영된다.

시연 제공자가 명시적인 이벤트를 만들며 서비스는 fetchedAt/generatedAt에 임의로 300초를 더하지 않는다. `(routeId, boardStationId)`별 관측이 없거나 예상 시각을 받지 못했거나 이미 지난 이벤트라면 unavailable과 null을 유지한다. 각 버스 관측에는 자기 sourceUpdatedAt/fetchedAt/sourceId가 있어 한 구간의 시각을 다른 구간에 복사하지 않는다.

변경 범위는 선택한 버스의 승차~하차 사이 실제 경유 정류장(중간 정류장 포함)과 노선을 기준으로 확인한다. 관련 없는 정류장이나 다른 노선의 변경은 선택 경로를 막지 않는다. 적용이 미래이거나 종료된 알림은 경로 버전·상태를 바꾸지 않으며 관련 알림 자체는 validFrom/validUntil과 함께 live 목록에 남을 수 있다. validFrom이 미확인이거나 기간이 잘못된 변경을 현재 결행으로 확정하지 않고 재확인을 요구한다. 변경 항목과 적용 대상 ID 집합의 순서만 바뀌어도 버전이 바뀌지 않도록 정규화한다.

## 오류·부분 실패·재조회

| 상황 | HTTP / 처리 |
| --- | --- |
| 도착 미수신, 변경 조회 불가, stale/unknown | 200 + 항목별 상태·품질. 경로 핵심 사실이 유효하면 계속 표시하되 확인 불가/오래됨 안내 |
| 경로 변경·재확인·기대 버전 불일치 | 409 ROUTE_VERSION_CHANGED. 기존 상세와 섞지 않고 새 검색/선택으로 확인 |
| 확인된 결행·우회·운행 중단 | 409 ROUTE_UNAVAILABLE. 기존 안내 중단 후 재검색(2026-11-09 계약 오류 수정) |
| now >= expiresAt | 410 ROUTE_SEARCH_EXPIRED. 정확히 600초부터 새 검색 |
| 핵심 경로 검증 자료 확인 불가 | 503 TRANSPORT_DATA_UNAVAILABLE. 가능한 경로라고 확정하지 않음 |
| 없는 검색/옵션 | 404 NOT_FOUND. 식별자를 다시 선택 |

검색 없음 → 만료 → 옵션 없음 → 핵심 자료 → 모드/경로/상태/버전 검사 순서를 사용한다. 만료된 검색에서는 동시에 핵심 자료가 없어도 410이 우선한다. 상세·live와 후속 안내/인쇄의 공통 검사를 사용하며 경로 버전이 다른 값을 한 화면에 혼합하지 않는다.

제공자 전체 조회가 예외로 실패하면 핵심 자료 확인 불가로 처리하되 위 404/410 우선순위를 유지한다. 핵심 경로 자료가 유효하다고 확인된 상태에서 도착/변경 하위 자료만 잘못되거나 없으면 해당 관측을 unavailable, 변경 범위를 unknown으로 처리한다. 부분 자료 오류를 500으로 노출하거나 정상 도착·변경 없음으로 바꾸지 않는다.

B가 구현할 클라이언트 기준은 **활성 상세 화면에서 30초마다 조회, 화면 이탈 시 중지, 요청 제한 5초**다. GET의 일시적인 연결 실패/5xx만 1초 뒤 1회 재시도한다. 4xx나 POST는 자동 재시도하지 않는다. 타이머·재시도·화면 상태·음성/UI는 B의 책임이며 이번 백엔드 작업에서 대신 구현하지 않았다.

## 실제 HTTP 재현 도구

프로젝트 루트에서 실행한다.

```powershell
backend/.venv/Scripts/python -m backend.tools.verify_stage5
```

이 도구는 비어 있는 8000 포트에 독립 메모리 SQLite DB·DemoProvider·주입 시각을 쓰는 Uvicorn 자식 서버를 띄운다. 제어 파일은 매 실행 고유한 `backend/.local/stage5-http-<임의ID>/control.json`에만 생성한다. HTTP 요청 사이에 그 파일의 fixture 시각·시나리오를 바꾸어 0/30/90/91/599/600초를 재현하므로 실제로 10분을 기다리지 않는다. 실사용 main 앱·실행 DB·공용 scenario.json은 변경하지 않는다.

테스트 전용 HTTP 제어 API를 추가하지 않는다. 자식 앱도 공개 서비스 API는 기존 8개이며, 도구가 생성한 자식 서버만 종료한다. 포트가 사용 중이면 중단하고 기존 프로세스를 종료하지 않는다. 필요하면 `--port 8001`을 선택할 수 있지만 그 선택 명령 자체는 별도로 실행한 것으로 표시하지 않는다.

실제 실행 기록은 `stage5-http-examples.json`에 있다. 최종 실행에서 **36개 실제 HTTP 사례**를 통과했고 공개 서비스 API는 기존 8개임을 확인했다. 각 case의 fixture는 **주입 시각**이며 meta.generatedAt도 그 테스트 시각을 따른다. 파일의 verifiedAt은 도구 실행의 실제 UTC 시각이다. 따라서 주입 시각이 실제 시각보다 10분 이상 앞서도 현실의 교통 자료나 서버 시계라고 해석하지 않는다. 요청 예시의 departAt은 실제 사용할 때 현재 aware ISO 시각을 생성하고, 기록 속 검색 ID는 다른 실행에 재사용하지 않는다.

검증 범위는 정상 도착, ETA 30초 변화와 버전 유지, 90/91초 최신성, 원천 시각 없음/미래, 도착 미수신, 명시적 운행 상태와 도착 상태의 독립성, 변경 조회 unknown, 599/600초 만료, 결행/우회/시간표 변경 409, 무관 경로 유지, 핵심 자료 503 및 오류 우선순위다. 최종 사례 수·소요시간은 생성 JSON을 기준으로 확인한다.

기존 서버 대상 옵션은 제공하지 않는다. 전체 시간/시나리오 조작 검증은 주입 시각을 사용하는 전용 자식 앱에서만 수행해야 하기 때문이다. 일반 시연 상태 전환은 기존 backend.demo CLI와 README의 방법을 사용한다.

## 수행 여부와 B 공동 검증 대기

provider 개선 이후 새 operation_running/arrivals_missing_running/operation_not_running 시나리오까지 포함해 도구를 실제 실행하고 성공 기록을 생성했다. 명시적 running/not_running은 영향받는 route1에만 적용되며, 무관한 route2를 같은 상태로 복사하지 않는 것도 확인했다. 자동 테스트를 통과했다고 B의 30초 타이머·요청 취소·재시도·갱신 시각/unknown/stale 화면까지 동작한다고 보고하지 않는다. frontend 파일 수정·B에게 메시지 전송·실제 외부 교통 검증은 수행하지 않았다.
