# 백엔드 구현·검증 상태

## 2026-10-28 · 백엔드 단독 전체 오류 점검

사용자 요청에 따라 지금까지의 백엔드를 단독 점검했다. 다른 팀원의 실제 프론트엔드/AI/디자인 연동은 검사하지 않았다. 시작 브랜치는 `codex/backend-implementation`, 커밋 `a0ff06c`, Git 변경 없음이다.

기존252개는 통과했지만 추가 재현에서 저장 시각/600초 수명·mode·품질 모순, 잘못된 제공자 모델의 검증 우회, 비정상 DB 좌표/순번, 일반500 헤더·405 Allow 누락, 시작 실패 엔진 정리, 확인된 도보 요약 누락을 확인해 수정했다. 관련64개 회귀를 추가했다.

최종 **316 passed**, 기존 경고1개, 96.41초. 실제 Uvicorn의 백엔드 HTTP28개와 API8개 흐름도 통과했다. pip check/compileall 정상이며 실행 DB 읽기 무결성은ok·외래키 위반0이다. 초기화/적재 실패와 일반 요청 실패의 롤백·자원 정리·후속 요청 복구도 검사했다.

상세 재현·변경 파일·명령·남은 제약은 `backend-audit-20261028.md`, 최종 결과는 `backend-audit-tests-20261028.xml`/`backend-audit-http-20261028.json`, 범위 비교는 `backend-audit-workspace-20261028.json`에 있다. 기존 단계별 실행 기록은 덮어쓰지 않았다. 경로 버전이 선택 노선 전체 자료를 포함하는 보수적인 정책과 동기 AI 강제 중단 미지원은 기존 제약으로 유지했다.

수정은 backend 내부뿐이며 실제 실행 DB·공용 scenario·다른 파트 파일을 보존했다. 다른 담당자 메시지·commit/tag/push/PR/원격 변경은 없다. 이번 점검을 전체 팀 서비스 연동 완료로 표시하지 않는다.

## 2026-10-28 · v2 계획서 6단계 실행 결과

요청 범위: **AI 중계와 인쇄 데이터 API**. v2 계획서 6단계 본문·추가 체크리스트11개를 공통 계약과 대조했다. 시작 상태는 `codex/backend-implementation`, 커밋 `3033f85`, Git 변경 없음이다. ai/contracts·destination-interpretation·easy-guidance에는 여전히 temp만 있어 실제 공개 Python 모듈은 없으며, 다른 파트 원본을 고치거나 AI 선택 알고리즘을 대신 구현하지 않았다.

| v2 6단계 항목 | 결과 |
| --- | --- |
| 실제 AI 공개 인터페이스·주입 어댑터 | 백엔드 완료, 실제 모듈 대기. 동기 interpret_destination/choose_guidance 계약 유지, ai 폴더 변경 없음 |
| 미연결 unavailable·수동 대체·테스트 가짜 구분 | 완료. 기본 서버/HTTP 도구는 실제 미연결, 가짜 성공·오류·지연은 pytest에만 주입 |
| text1~200·등록 후보·모호성 | 완료. 공백/길이·원래 허용 후보·현재 등록 목록을 모두 검사. matched도 사용자 확인 필요 |
| 안내 구간·순서·누락/중복·template·버전 | 완료. 허용 JSON 형태/정확한 구간 개수/유형별 표현 검증. 임의 추가 사실 거부 |
| 교통 사실의 서버 삽입 | 완료. 노선·정류장·개수·환승은 검증 상세만 사용. 거리/시간 확인 여부도 독립 보존 |
| AI 오류·1초·작업 누적 방지 | 완료. 준비/시작 실패 슬롯 복구·남은 예산·JSON 출력 복사/검증·공유1슬롯/대기열없음·완료 후 복구 확인 |
| 인쇄 만료·상태·기대 버전 재검사 | 완료. 기존 공통 검사 및 동일 버전의 detail/live/guidance 스냅샷 |
| 미수신 ready 인쇄·이용 불가 거부 | 완료. 미수신/변경unknown은 상태 표시 후200, 버전/불가409·만료410·핵심자료503 유지 |
| 생성시각·시연·동일 구간·카운트다운 제외 | 완료. etaSeconds=null, 절대 예정 시각/원천 시각 보존, 프린터 성공 필드 없음 |
| B용 안내·음성 텍스트·인쇄 JSON | 자료 준비 완료, 화면/음성/인쇄 공동 확인 대기. UI·CSS·window.print 구현 안 함 |
| 서비스 API8개·실제 연결 여부 구분 | 완료. 실제 HTTP28개 흐름, 실제 AI 미연결을 결과에 명시 |

이번에 보완한 실제 문제:

1. Thread.start 또는 준비 단계의 실패가 최초500과 잠긴 AI 슬롯을 남길 수 있었다. 실패를 대체하고 슬롯을 복구한다. 남은 채택 예산만 대기하고 시간초과 후 실제 작업 중단과 혼동하지 않는다.
2. AI가 dict가 아닌 값·비JSON·async 코루틴을 반환하는 경우를 경계에서 정리한다. NaN/set/모델 객체는 채택하지 않고 코루틴은 실행하지 않은 채 닫는다. 입력과 출력도 분리 복사한다.
3. 해석 대기 중 목적지 이름이 바뀌거나 등록이 삭제돼도 이전 후보가 응답될 수 있었다. 원래 허용 목록을 지킨 뒤 새 DB 세션에서 현재 등록 정보를 확인한다. 새 이름은 현재 값으로 반환하고 삭제된 ID는 unavailable로 대체한다. 이 재검증도 서비스 채택 예산 안에서 확인한다.
4. 거리만 미확인인 도보에도 확인된 시간까지 미확인으로 안내하던 문구를 수정했다. 확인된 거리·시간만 각각 넣고 나머지는 확인 불가로 안내한다.
5. 인쇄 notice를 실제 미수신·stale·unknown 상태로 만들고 서버 data_mode를 고정 안내/시연 표시에 전달한다. 인쇄는 AI를 다시 호출하지 않고 같은 검증 경로의 고정 텍스트를 사용한다.

변경 파일:

- `backend/integrations/ai.py`: 호출 슬롯·준비/worker 시작 실패 복구·남은 예산·동기 JSON 출력 경계·입출력 분리.
- `backend/services/ai.py`: 출력 형태/후보/템플릿 검증 보강, 현재 등록 정보 재검증, 확인된 도보 사실 보존.
- `backend/api/routes.py`: AI 해석 후 현재 후보를 새 세션에서 조회하는 콜백과 인쇄 data_mode 전달.
- `backend/services/journeys.py`: 실제 관측 상태를 담은 인쇄 notice, 같은 버전/모드의 고정 안내.
- `backend/tests/test_stage6.py`: 전용46개. 입력·허용 정보·오류/1초/공유 슬롯·재검증·복사·async/비JSON·인쇄 일관성 포함.
- `backend/tools/verify_stage6.py`: 실제 AI 미연결 상태로8개API와 인쇄 흐름을 검증하는 독립 HTTP 도구.
- `backend/docs/stage6-integration.md`, `stage6-http-examples.json`, `stage6-regression-results.xml`, `stage6-workspace-audit.json`: 연동·응답·회귀·범위 증거.
- `backend/README.md`, `backend/docs/coordination-notes.md`, 이 문서: 실제 명령·책임 경계·공동 검증 대기 기록.

최종 실제 실행:

```text
backend/.venv/Scripts/python -m pytest backend/tests/test_stage6.py -q -p no:cacheprovider
  → 46 passed, 1 warning, 12.57초
backend/.venv/Scripts/python -m pytest backend/tests -q --basetemp=backend/.test-tmp -p no:cacheprovider --junitxml=backend/docs/stage6-regression-results.xml
  → 252 passed, 1 warning, 55.92초
backend/.venv/Scripts/python -m backend.tools.verify_stage6
  → 실제 HTTP28개, 공개 API8개, 실제 AI 미연결/인쇄 스냅샷 검증 통과
```

HTTP 도구의 fixture 시각은 주입한 테스트 시각이다. 실제10분을 기다리거나 실행 DB를 삭제하지 않았다. 테스트용 제어 파일은 `.local/stage6-http-<ID>/`에만 생성하며 공용 scenario.json을 바꾸지 않는다. 실제 AI의 성공을 시연한 것이 아니다. 가짜 어댑터는 테스트 파일 안에서만 사용했다. 경고는 기존 Starlette/anyio BlockingPortal 폐기 예정 알림1개다. HTTP/TestClient는 기존 Windows 샌드박스의 로컬 소켓 제한을 피하기 위해 권한이 허용된 실행에서 수행했다.

남은 항목은 실제 AI 공개 모듈·같은 Python 환경의 연결, B/디자인 화면·브라우저 음성·인쇄 미리보기/취소·다른 PC 공동 검증이다. 어댑터1초는 결과 채택 예산이며 이미 실행 중인 동기 작업의 강제 중단을 보장하지 않는다. 멈춘 함수는 자체 취소 기능 또는 프로세스 재시작이 필요하다. 서버는 종이 출력 성공을 판정하지 않는다.

변경은 backend 내부에 한정했고 frontend/ai/design 및 루트 공통 원본을 보존했다. 실제 교통 API·외부 AI·비밀키를 추가하지 않았다. commit/tag/push/PR/배포·다른 담당자 메시지 전송은 없다. 최종 파일·DB·OpenAPI 비교는 `stage6-workspace-audit.json`에 기록한다.

## 2026-10-27 · v2 계획서 5단계 실행 결과

요청 범위: **도착·운행 변경·시간·버전 처리**. v2 계획서 5단계 본문과 추가 체크리스트 11개 항목을 공통 계약·실제 코드와 대조했다. 시작 상태는 `codex/backend-implementation`, 커밋 `62d4f2a`, Git 변경 없음이다. 일정일까지 기다리지 않고 백엔드 독립 작업을 수행했다.

| v2 5단계 항목 | 결과 |
| --- | --- |
| live API·합성 도착·운행 시나리오 | 완료. 기존10개에 명시 running/not_running/미수신+running 3개 추가. demo 및 기존 API 구조 유지 |
| sourceUpdatedAt/fetchedAt/generatedAt 분리 | 완료. 도착 관측·버스 구간·변경 피드/항목마다 자기 시각 보존, 응답 생성 시각으로 대체하지 않음 |
| 0~90초 fresh·초과 stale·없음/미래 unknown | 완료. 90.000001초·미래1마이크로초·다른 시간대도 테스트. 캐시된 변경 품질도 now에서 재계산 |
| 도착 미수신·운행 상태 독립 | 완료. 관측 없음/ETA 없음/지난 이벤트는 null·unavailable, 명시적 running은 별도 유지. 서비스의 임의 ETA 생성 제거 |
| 시간표·결행·우회·적용 범위 | 완료. 관련 노선/실제 승하차 사이 경유 정류장, 시작 포함/종료 제외 검사. 미확인 시작을 현재 결행으로 확정하지 않음 |
| 변경 조회 실패 unknown | 완료. 하위 변경 자료가 잘못돼도 core가 유효하면 200/unknown. 빈 목록을 정상 운행으로 해석하지 않음 |
| 경로 관련 변경/버전·ETA 갱신 | 완료. 경유·연결·적용 변경/운행 중단은 반영. ETA·변경 항목 순서·적용 ID 집합 순서/중복만의 차이는 버전 유지 |
| 상세/live/안내/인쇄의 공통 검사 | 완료. 기존 checked_detail를 모두 사용하며 버전·상태·만료 검사 회귀 확인 |
| now>=expiresAt 410·변경/불가409·우선순위 | 완료. 검색없음404 → 만료410 → 옵션없음404 → 핵심자료503 → 모드/경로/상태/버전409. provider 예외도 우선순위 보존 |
| 부분 실패200·핵심 자료503 구분 | 완료. 일부 잘못된 관측·하위 컨테이너는 unavailable/unknown, 전체 read 실패/핵심 자료 미확인은503. 내부 오류 문구 노출 없음 |
| B 연동 자료·30초/5초/재시도 | 자료 준비 완료, 브라우저 공동 확인 대기. 타이머·취소·재시도·UI는 구현하지 않음 |

확인하고 수정한 문제:

1. 도착 품질만 재계산하고 운행 변경의 저장 freshness를 신뢰해 같은 원천 나이에도 fresh/stale이 달랐다. 피드와 개별 항목 모두 원천 시각 기준으로 계산한다.
2. 노선 전체 정류장을 경로 영향 범위로 보면서 live에서는 승하차 끝점만 사용했다. 선택한 실제 경유 구간(중간 포함)으로 일원화해 무관 변경이 막거나 필요한 알림이 빠지는 문제를 보완했다.
3. 같은 변경 자료의 배열·적용 ID 순서만 바뀌어도 버전이 달랐다. 항목 정렬과 적용 대상 집합 정규화로 의미상 같은 자료는 같은 버전을 사용한다.
4. 제공자 read 예외가500으로 새어나가 만료/없는 대상 응답을 가렸다. 핵심 확인 불가 상태로 변환해 기존404/410/503 우선순위를 유지한다. 이미 확인된 core를 하위 관측 오류 때문에 버리지 않는다.
5. 서비스가 fetchedAt+300으로 ETA를 만들고 operationStatus를 항상 unknown으로 고정했다. 제공자 경계에 ArrivalObservation을 추가해 예상 절대 시각·운행 상태·각 출처/시각을 명시적으로 전달한다. 기본 normal의 unknown 상태는 유지하며, 새로운 합성 프로필로 명시 운행 증거를 시연한다.

변경 파일:

- `backend/integrations/providers.py`: 버스 노선/승차 정류장별 ArrivalObservation, 13개 시나리오, 품질/집합 정규화, 전체/부분 실패 경계.
- `backend/services/time.py`: aware 시각만 사용하고 원천 기준 freshness·품질 재계산.
- `backend/services/routing.py`: 선택 구간 범위·변경 적용기간·정렬·명시 운행 중단을 경로 상태/버전에 반영.
- `backend/services/journeys.py`: 제공받은 관측만 live에 사용하고 항목별 시각·상태·null을 보존. live/인쇄에 같은 경유 범위를 적용.
- `backend/api/routes.py`: 제공자 안전 경계를 사용하고 요청 DB 세션을 범위 조회에 전달.
- `backend/tests/test_stage5.py`: 전용45개. 최신성, 시각 분리, 부분 실패, 기간/범위, 집합 동일성, 공통 오류 우선순위, 관측/운행 독립성과 제공자 실패 포함.
- `backend/tools/verify_stage5.py`: 전용 제어 파일·주입 시각·메모리 DB의 자식 서버로 실제 HTTP 시간·상태 재현. 새 서비스/제어 API 없음.
- `backend/docs/stage5-integration.md`, `stage5-http-examples.json`, `stage5-regression-results.xml`, `stage5-workspace-audit.json`: B 연동/검증/범위 기록.
- `backend/README.md`, `backend/docs/coordination-notes.md`, 이 문서: 실행 안내·제약/공동 검증 대기.

최종 실제 실행:

```text
backend/.venv/Scripts/python -m pytest backend/tests/test_stage5.py -q -p no:cacheprovider
  → 45 passed, 1 warning, 17.43초
backend/.venv/Scripts/python -m pytest backend/tests -q --basetemp=backend/.test-tmp -p no:cacheprovider --junitxml=backend/docs/stage5-regression-results.xml
  → 206 passed, 1 warning, 54.17초
backend/.venv/Scripts/python -m backend.tools.verify_stage5
  → 최종 코드의 실제 HTTP36개 통과, 공개 API8개 유지
```

자동 검증은 10분을 실제로 기다리지 않고 clock/provider/관측을 주입했다. 실제 HTTP 도구도 테스트 전용 clock과 `.local/stage5-http-<ID>/control.json`을 사용하며 운영 앱·실행 DB·공용 scenario.json을 변경하지 않는다. 경고는 기존 Starlette/anyio BlockingPortal 폐기 예정 알림1개다. HTTP/TestClient는 기존 Windows 샌드박스 로컬 소켓 제한을 피하기 위해 권한이 허용된 실행에서 수행했다.

기존 DB의 검색2개에 저장된 정상 버전2개는 현재 정상 자료로 재계산해도 동일함을 확인했다(이미 만료된 검색을 유효하다고 표시한 것은 아님). 공개 필드·오류 코드·초기 원본 데이터는 변경하지 않았다. 실제 교통기관·키·지원 범위·실데이터 연결은 여전히 미확인이고 live 미연결은503이다. B 화면·30초 폴링/이탈 중지/5초 제한/GET 재시도·팀원 PC 검증은 대기다.

backend 밖 파일과 기존 실행 DB·상태를 보존했으며 commit/tag/push/PR/배포·외부 메시지 전송은 수행하지 않았다. 최종 범위·테스트·DB 보존 증거는 `stage5-workspace-audit.json`에 기록한다.

## 2026-10-27 · v2 계획서 4단계 실행 결과

요청 범위: **경로 검색과 상세 안내 API**. v2 계획서 4단계 본문·추가 체크리스트 10개 항목을 공통 계약과 대조했다. 시작 상태는 `codex/backend-implementation`, 커밋 `0ca2cd3`, Git 변경 없음이다. 11/1은 화면 연동 목표일이며 해당 날짜까지 기다리지 않고 백엔드 독립 작업을 진행했다.

| v2 4단계 항목 | 결과 |
| --- | --- |
| 출발·목적지·aware departAt, ±120초 | 완료. UTC 비교·±120 허용/±121 거부 및 120.000001초 경계 검증. 숫자 epoch/숫자 문자열·naive 입력은 400 |
| 순번에 따른 정방향 직통 | 완료. 역방향 생성 없음, 비연속 순번·동일 정류장 재방문도 실제 경유 행 수로 계산 |
| 명시 연결·최대 1회 환승 | 완료. 등록 연결만 사용, 서로 다른 정류장 사이 미등록 도보 연결 추정 없음, 두 번 환승하는 3개 버스 경로 제외 |
| 순서 있는 bus/walk/transfer·고유 ID·null | 완료. 구간 순서·고유 segmentId·환승의 앞뒤 버스 참조·미확인 시간/거리 null 확인 |
| 안정 정렬·중복 제거·최대3개 | 완료. 환승 수→버스 정류장 합계→경로 키 정렬. 이용 가능 상태 확인 후 최대3개로 제한하도록 수정 |
| 시장1·병원2·터미널 환승4 | 완료. 전용 테스트 및 실제 HTTP에서 확인 |
| 검색/옵션/버전/만료·스냅샷 저장 | 완료. 스냅샷 쓰기/읽기 검증 보강, 같은 검색의 상세·구간·computedAt 유지, 재시작 후 조회 확인 |
| 상세 조회·없는 검색/옵션·경로 없음 구분 | 완료. 정상200, 경로 없음200 빈 배열, 없는 대상404, 손상된 자료503, 실제 경로 변경409, 만료410 유지 |
| A→B 전달값6개 | 완료. 출발·목적지·검색·옵션·버전·dataMode를 검색 및 상세와 대조하고 사례3개 준비 |
| A/B 검색→선택→상세 공동 화면 | API 흐름 완료, 브라우저 공동 검증 대기. 다른 화면은 아직 자리 표시자뿐 |

발견하고 수정한 문제:

1. 후보를 가용 상태 확인 전에 3개로 자르면 앞 3개가 막히고 뒤 후보가 정상이어도 빈 결과가 됐다. 전체 정렬 후보 중 ready 경로를 고른 후 공개 응답만 최대3개로 제한한다.
2. 선택 후 더 짧은 후보가 추가돼 상위3개 밖으로 밀리면, 경로가 그대로여도 상세가409였다. 상세 존재 확인은 전체 후보를 사용해 해당 선택 경로 자체의 구조·버전만 검사한다.
3. 저장 JSON의 detail 타입만 검사해 잘못된 legs가 500이 되거나, stopCount를 바꾼 자료가200으로 반환될 수 있었다. 기존 JSON 배치와 호환되는 SavedRouteOption 내부 모델로 구조·구간 참조를 검증하고 현재 버전의 재계산 사실과 대조한다. 정상 형식에서 실제 경로가 바뀐 경우409를 우선 판단하고, 같은 버전에서 저장 사실이 다른 경우503으로 거부한다.
4. Pydantic이 numeric epoch를 aware datetime으로 자동 변환해 OpenAPI의 ISO 문자열 기준과 달랐다. 문자열 ISO 시각(또는 내부 Python aware datetime)만 받아 HTTP 숫자/숫자 문자열을400으로 거부한다.

변경 파일:

- `backend/services/routing.py`: 후보 생성과 공개 응답 제한을 분리한다. 방향·명시 환승·정렬 기준은 유지한다.
- `backend/services/journeys.py`: 가용 후보의 최대3개 선택, 저장 모델의 쓰기/읽기 검증, 검색/옵션/계산시각 연결 및 저장 사실 대조.
- `backend/models/snapshots.py`: 공개 응답과 별개인 내부 스냅샷 모델. legs·접근 정류장·순서/누락/중복·환승 참조를 검증한다. 기존 DB JSON 배열 형식은 유지한다.
- `backend/models/schemas.py`: SearchRequest.departAt의 ISO 문자열 검증.
- `backend/tests/test_stage4.py`: 전용39개. 정상 경로, 최대1회, 정렬/상한, 시간/ID, 저장/재시작, 위 결함 회귀와 스냅샷 손상12종을 포함한다.
- `backend/tools/verify_stage4.py`: 실제 HTTP 검색→상세 검증 및 동적 요청·A→B 선택 객체 기록. 기본 실행은 독립 메모리 DB를 사용한다.
- `backend/docs/stage4-integration.md`, `stage4-http-examples.json`, `stage4-regression-results.xml`, `stage4-workspace-audit.json`: 연동·실행·검증·범위 증거.
- `backend/README.md`, `backend/docs/coordination-notes.md`, 이 문서: 재현·담당자 확인 대기·상태 기록.

실행한 명령과 결과:

```text
backend/.venv/Scripts/python -m pytest backend/tests/test_stage4.py -q -p no:cacheprovider
  → 39 passed, 1 warning, 8.39초
backend/.venv/Scripts/python -m pytest backend/tests -q --basetemp=backend/.test-tmp -p no:cacheprovider --junitxml=backend/docs/stage4-regression-results.xml
  → 161 passed, 1 warning, 28.77초
backend/.venv/Scripts/python -m backend.tools.verify_stage4
  → 최종 보완 후 실제 HTTP21개 + POST/GET CORS/OpenAPI 통과
```

최종 HTTP 기록의 가장 긴 요청은 이번 환경에서 27.26ms이며 부하 성능 검증은 아니다. ±120초 경계는 주입 시각으로, 실제 HTTP의 범위 밖 오류는 ±180초로 확인해 네트워크 경과 시간 영향을 분리했다. 기존 실행 DB의 검색2개/옵션2개는 새 내부 모델과 형식 호환됨을 별도 확인했다. 테스트는 별도 DB와 주입 시각을 사용했으며 실행 DB·상태 파일을 삭제하지 않았다.

경고는 기존 Starlette/anyio BlockingPortal 폐기 예정 알림1개다. 실제 HTTP/TestClient는 앞서 확인한 Windows 샌드박스의 로컬 소켓 제한을 피하기 위해 권한이 허용된 실행에서 수행했다. 공통 필드·서비스 code·스키마의 공개 의미는 바꾸지 않았다. 초기 합성 원본과 다른 파트 파일을 보존했고 원격 변경·커밋·태그·push·PR·배포를 수행하지 않았다. API 흐름 검증을 A/B 브라우저 연동 완료로 표시하지 않는다.

## 2026-10-27 · v2 계획서 3단계 실행 결과

요청 범위: **정류장·목적지 조회 API**. v2 계획서의 3단계 본문과 추가 체크리스트 8개 항목을 현재 API 계약 및 실제 사용처와 대조했다. 시작 상태는 `codex/backend-implementation`, 커밋 `0bb90c2`, Git 변경 없음이다. 기존 1·2단계 및 경로/AI/인쇄 기능을 보존했다.

| v2 3단계 항목 | 결과 |
| --- | --- |
| 정류장 ID 조회 | 완료. 등록 5개 정류장의 이름·방향·문자열 ID·region/coordinates null을 검증 |
| 목적지 이름·별칭·분류·교집합 | 완료. 병원/시장/터미널의 이름/별칭/분류가 같은 ID를 반환하고 교집합·빈 결과를 확인 |
| 출발 정류장·분류·query 최대 100자 | 완료. DestinationQuery 모델로 정리; 공백 제거 후 100자 허용/101자 거부, 기존 미사용 query 인자 무시 동작 보존 |
| 200 빈 배열·400·404 구분 | 완료. FastAPI 입력 오류 포함 400 INVALID_REQUEST, 미등록 404 NOT_FOUND, 일치 없음 200 destinations=[] |
| lowerCamelCase·ID·null·응답 봉투 | 완료. Pydantic 응답 검증, UTF-8, requestId/헤더 일치·generatedAt의 시간대·dataMode 확인 |
| 주요 장소·별칭의 ID 일치 | 완료. 3개 목적지와 분류, 이름·별칭 검색, 동명 장소의 개별 ID 보존 확인 |
| 8000/5173·프록시·로컬 origin | 백엔드 완료, A 설정 확인 대기. 두 로컬 origin의 GET/OPTIONS·오류 응답 CORS를 검증하고 접두사 유지 프록시 안내 준비 |
| A 실제 화면 첫 조회 | 대기. frontend는 자리 표시자뿐이며 실제 브라우저 연동 완료로 표시하지 않음. 실행 가능한 검증 도구·정상/빈 결과/오류 자료 준비 |

변경 파일:

- `backend/models/schemas.py`: DestinationQuery 입력 모델 추가. 출발 ID·query 공백/길이·category를 한 모델로 검증한다.
- `backend/api/routes.py`: 목적지 조회 라우터에서 같은 모델을 사용한다. 서비스의 DB 조회·외부 응답·API 주소는 유지했다.
- `backend/tests/test_stage3.py`: 정류장 5개, 이름/별칭/분류, 교집합, 100/101자, 400/404/빈 결과, 실제 DB 변경 반영, 동명 ID 보존, CORS·OpenAPI 등 전용 테스트 44개.
- `backend/tools/verify_stage3.py`: 독립 메모리 SQLite DB의 Uvicorn 자식 서버 또는 지정한 demo 서버에 GET 요청을 보내 검증한다. 기본 실행은 기존 실행 DB·시나리오를 변경하지 않고 생성한 서버만 종료한다.
- `backend/docs/stage3-integration.md`, `stage3-http-examples.json`: A용 주소·입력/출력·프록시·오류 처리와 실제 HTTP 21개 기록.
- `backend/docs/stage3-test-results.xml`, `stage3-regression-results.xml`, `stage3-workspace-audit.json`: 전용/전체 테스트와 범위 증거.
- `backend/README.md`, `backend/docs/coordination-notes.md`, 이 문서: 실행 안내·담당자 확인 대기 기록.

실제로 실행한 명령:

```text
backend/.venv/Scripts/python -m pytest backend/tests/test_stage3.py -q --basetemp=backend/.test-tmp -p no:cacheprovider --junitxml=backend/docs/stage3-test-results.xml
  → 44 passed, 1 warning, 11.45초
backend/.venv/Scripts/python -m backend.tools.verify_stage3
  → Uvicorn 127.0.0.1:8000, 실제 HTTP 조회21개 + CORS/OpenAPI 통과
backend/.venv/Scripts/python -m pytest backend/tests -q --basetemp=backend/.test-tmp -p no:cacheprovider --junitxml=backend/docs/stage3-regression-results.xml
  → 122 passed, 1 warning, 30.06초
```

실제 HTTP 21개 중 가장 오래 걸린 요청은 이번 환경에서 15.42ms였다. 부하 환경 성능 보장은 아니다. 생성된 OpenAPI는 기존 파일과 내용이 동일하여 계약 필드·경로 변경이 없음을 확인했다. 경고는 기존 Starlette/anyio BlockingPortal 폐기 예정 알림 1개다. TestClient·실제 HTTP 실행은 앞서 확인한 Windows 샌드박스의 로컬 소켓 제한을 피하기 위해 권한이 허용된 실행에서 진행했다.

프론트엔드 화면·브라우저 프록시·화면 표시의 공동 검증은 미수행이다. 프론트 코드를 대신 작성하거나 다른 담당자에게 메시지를 보내지 않았다. 실제 교통 API 미연결 상태도 유지한다. 이번 변경은 backend 내부뿐이며 Git commit/tag/push/PR/배포는 수행하지 않았다. 상세 변경 범위는 `stage3-workspace-audit.json`을 참조한다.

## 2026-10-27 · v2 계획서 2단계 실행 결과

요청 범위: `backend-development-plan-v2(1).hwp`의 **DB와 시연 데이터 준비**. 첨부 파일을 직접 추출해 2단계 본문·DB 세부안·추가 체크리스트(2단계 9개 항목)를 확인했다. 과거 '계획서 작성만' 문구는 이번 실행 요청에 적용하지 않았다. 이번 시작 상태는 `codex/backend-implementation`, 커밋 `2a4b91e`, Git 변경 없음이다. 아래 2026-10-26 기록의 코드는 이미 저장소에 있었으므로 보존했다.

| v2 2단계 항목 | 결과 |
| --- | --- |
| PK/FK/nullable/고유 조건·ORM/API 분리 | 완료. 실제 테이블 검사 및 `database-schema.md` 작성. 기존 테이블·API 계약 변경 없음 |
| 연결마다 외래키·세션·커밋·롤백 | 완료. 새 물리 연결에서도 PRAGMA=1, 실제 seed 마지막 그룹 실패 및 commit 실패 롤백 확인 |
| 노선 ID+순번·복합 환승 참조 | 완료. 양쪽 노선 순번 참조 및 존재하지 않는 참조 거부 |
| 공통 ID·이름·별칭·분류·수량 적재 | 완료. 원본 JSON 변경 없이 실행 DB에 재적재; 정류장5/노선2/목적지3/경유6/환승1 유지 |
| 001노선 3번 → 002노선 1번·목적지 접근 | 완료. stop-003에서의 명시적 합성 환승1, 병원/시장/터미널 접근3 확인 |
| 반복 적재 중복 없음·실패 시 부분 반영 없음 | 완료. 전용 테스트 13개 통과. 기존 팀원 수정값 보존·재시도 가능 확인 |
| integrations 제공 인터페이스·시연 제공자 | 완료. 기존 TransportProvider/DemoProvider/ProviderState를 유지·대조; 실제 외부기관 URL 의존 없음 |
| DB·저널 제외·합성 원본/잠금/환경 예시 보존 | 완료. .local의 sqlite3/-journal/-wal/-shm 제외, 원본/lock/.env.example 추적 확인 |
| A/B 응답 예시·AI 후보/함수 입출력 | 자료 준비 완료, 담당자 공동 확인 대기. stage2-handoff-examples.json에 실제 API 200/빈 결과/400/404/환승 응답 및 AI 입력 계약 제공. 메시지 전송·다른 파트 수정 없음 |

이번 변경 파일:

- `backend/seed.py`: 선택 원본 주입으로 실패를 재현할 수 있게 하고, 신규 삽입 수·실제 전체 수량을 반환/출력한다. 전체 적재는 기존과 동일하게 단일 트랜잭션이며 기존 행을 보존한다.
- `backend/tests/test_stage2.py`: 적재 중/commit 시 실패 롤백, 빈/기존 DB, 외래키, 복합키 중복, 연결별 PRAGMA, 명시적 연결·nullable·모델 분리 테스트 13개.
- `backend/tools/verify_stage2.py`: 실행 DB에 반복 적재 후 수량·참조·기존 행·검색 스냅샷 보존·실제 DB 스키마를 검사하고 기록한다.
- `backend/.gitignore`: 전용 테스트의 JSON 원본 임시 폴더 `.test-tmp-stage2/` 제외.
- `backend/README.md`, `backend/docs/database-schema.md`: 재현 명령·실제 테이블 조건·제공 경계·합성 원본 설명.
- `backend/docs/stage2-verification-20261027.json`, `stage2-handoff-examples.json`, `stage2-test-results.xml`, `stage2-regression-results.xml`, `stage2-workspace-audit.json`: 이번 실행 증거.
- `backend/docs/coordination-notes.md`, 이 문서: 인수인계/공동 확인 대기·변경 범위 기록.

실제 실행 결과:

```text
backend/.venv/Scripts/python -m pip check
  → No broken requirements found
backend/.venv/Scripts/python -m backend.seed  (두 번)
  → inserted 모두 0, totals stations5/destinations3/aliases3/routes2/stops6/access3/transfers1
backend/.venv/Scripts/python -m backend.tools.verify_stage2
  → 외래키 활성, 위반0, 기존 행 보존, 재적재 전후 행 SHA-256 동일, 검색 스냅샷2 유지
backend/.venv/Scripts/python -m pytest backend/tests/test_stage2.py -q --basetemp=backend/.test-tmp-stage2 -p no:cacheprovider --junitxml=backend/docs/stage2-test-results.xml
  → 13 passed, 1 warning, 1.33초
backend/.venv/Scripts/python -m pytest backend/tests -q --basetemp=backend/.test-tmp -p no:cacheprovider --junitxml=backend/docs/stage2-regression-results.xml
  → 78 passed, 1 warning, 24.29초
```

API 인수인계 예시는 주입 DemoProvider와 격리 메모리 DB의 실제 TestClient 응답으로 생성했다. 전체 API 회귀 검증과 예시 생성은 이전에 확인된 Windows 로컬 socketpair 제한 때문에 권한이 허용된 실행에서 수행했다. 경고 1개는 기존 Starlette/anyio BlockingPortal 폐기 예정 알림이다. 실데이터 조회·AI 모듈 연결·A/B 브라우저·팀원 PC 공동 검증은 수행하지 않았다.

이번 작업은 backend 밖 파일을 변경하지 않았으며 기존 실행 DB를 삭제·초기화하지 않았다. 합성 원본 ID/값도 변경하지 않았다. Git commit/tag/push/PR/배포와 원격 변경은 수행하지 않았다. 최종 범위 비교는 `stage2-workspace-audit.json`에 기록한다.

## 2026-10-26 · 기존 전체 구현 기록

작업일: 2026-10-26, Asia/Seoul. 작업 루트: `C:/Users/LG/OneDrive/Desktop/chungnam-smart-bus`. 시작 상태: `main`, 추적/미추적 변경 없음. 로컬 작업 브랜치: `codex/backend-implementation`. 커밋·태그·push·PR·이슈·배포는 수행하지 않았다.

## 자료 확인

HWP 5 OLE의 FileHeader와 BodyText/Section0을 직접 읽어 압축 해제하고 전체 문단/표의 텍스트를 추출했다. 추출본은 `source-plan.txt`, 재현 도구는 `../tools/extract_hwp.py`다. 요약 미리보기(PrvText)에 의존하지 않았다. 루트 README·.gitignore·공통 docs 5개를 모두 읽었으며, `docs/development-plan.md`는 존재하지 않았다. 적용할 AGENTS.md는 발견되지 않았다. 전체 파일 검색으로 frontend/ai/design은 자리 표시자뿐임을 확인했다. 다른 파트의 실제 계약·타입·실행 코드·공통 데이터 파일은 없었다.

HWP의 과거 '계획서 작성만'이라는 문구와 발표/리허설 일정은 이번 구현 범위를 제한하거나 확장하지 않는다. 이번 명시적 사용자 요청을 우선 적용했다. 기존 문서의 미정 정책과 사용자 요청의 확정 경계는 충돌로 보지 않고 구체화했다. 기존 API와 병원 예시 ID를 보존했으며, 누락된 데이터 세부는 HWP의 수량·명시적 환승·기대 경로 결과에 맞췄다. 공통 문서 반영 제안은 `coordination-notes.md`에 남겼다.

## 단계별 결과

| 단계 | 백엔드 독립 작업 | 검증 결과 / 공동 작업 |
| --- | --- | --- |
| 1 환경·앱·공통 응답 | 완료. FastAPI 라우터, Pydantic 응답, 공통 예외, 설정, 5173 로컬 CORS | /docs·404 봉투·400 검증·OpenAPI 확인. 실제 브라우저 시각 점검 대기 |
| 2 DB·초기 데이터·제공자 | 완료. ORM/API 모델 분리, SQLite 외래키, 트랜잭션, insert-only 적재 | 두 번 적재 후 5/2/3/6/1, 잘못된 외래키·복합 참조 거부·롤백 확인 |
| 3 정류장·목적지 | 완료. 이름/별칭/분류 교집합 검색 | 실제 HTTP와 TestClient 정상·빈 결과·400·404 확인. A 화면 연결 대기 |
| 4 경로·스냅샷 | 완료. 정방향·명시 환승·정렬·최대 3개, DB 검색 스냅샷 | 시장 1, 병원 2, 터미널 환승 4; 역방향/미등록 환승 제외, 순번별 반복 방문·동점 키 확인 |
| 5 도착·운행 변경·시간 | 완료. 합성 제공자, 10개 시나리오, 만료·버전·부분 실패 | 0/90/91초와 미래/없음, 599/600초, 경로/운행 변경 409, 핵심 자료 503 확인 |
| 6 AI·안내·인쇄 | 완료. 주입 어댑터, 출력 검증, 1초 대체, 고정 인쇄 스냅샷 | AI 없음/오류/잘못된 출력/시간초과·작업 누적 방지·복구, 사실 삽입·버전/구간 일관성 확인. 실제 AI 모듈 연결 대기 |
| 7 테스트·연동 | 백엔드 완료, 공동 검증 대기 | 최종 **65 passed**, 경고 1개, 22.59초. 실제 Uvicorn 8개 API HTTP smoke 통과 |
| 8 수정·실행 문서·인수인계 | 백엔드 완료, 타 PC 검증 대기 | 버전 잠금 재설치·pip check·seed·시나리오 CLI·서버/테스트 안내, 범위 감사. 커밋/태그는 이번 요청 제외 |

최종 테스트 결과는 `test-results.xml`, 실제 런타임은 `runtime-versions.json`, 실제 HTTP 응답은 `examples.json`, 생성 명세는 `openapi.json`이다. 의존성 경고는 Starlette TestClient가 사용하는 anyio BlockingPortal 별칭의 폐기 예정 알림 1개이며 테스트 실패는 없다.

## 실제 변경 파일과 책임

| 파일 | 역할 |
| --- | --- |
| `backend/main.py`, `config.py`, `.env.example`, `__init__.py` | 앱 생성·lifespan·설정·주입 경계·기본 오류 및 OpenAPI |
| `backend/api/{routes,errors,__init__}.py` | API 8개, 요청/응답 변환, 공통 서비스 오류 |
| `backend/models/{tables,schemas,__init__}.py` | SQLAlchemy 저장 모델과 Pydantic 외부/AI 모델 분리 |
| `backend/database.py`, `seed.py` | SQLite 경로 제한·세션·외래키·원자적 초기 적재 |
| `backend/services/{catalog,routing,journeys,time,ai,__init__}.py` | 검색, 방향/환승 계산, 버전/만료, 최신성, AI 검증/사실 바인딩, 출력 준비 |
| `backend/integrations/{providers,ai,__init__}.py`, `demo-data.json` | 교통/AI 경계, 합성 시나리오·데이터. 실제 제공자/AI 구현 아님 |
| `backend/demo.py` | 로컬 시연 상태 CLI. 외부 관리 API 없음 |
| `backend/tests/conftest.py`, `test_backend.py` | 시각·DB·제공자·AI 주입과 65개 정상/실패/경계 테스트 |
| `backend/tools/{extract_hwp,request_examples,server_smoke,audit_workspace}.py` | HWP 추출, 동적 요청 예시, 실제 서버 검증, 변경 범위 감사 |
| `backend/{requirements.txt,requirements.lock,.gitignore,README.md}` | 직접/전체 의존성 고정, 로컬 산출물 제외, 설치·실행 안내 |
| `backend/docs/`의 md/txt/json/xml | 계획 추출·협업·구현 상태·버전·명세·응답·테스트·범위 증거 |
| `backend/{api,models,services,integrations}/temp` | 실제 코드를 추가한 네 폴더에서만 삭제 |

세부 전체 목록과 최종 추적/새 파일 수는 `workspace-audit.json`에 있다. backend 밖의 자리 표시자 20개는 보존했다.

## 설계 선택과 계약 적용

- SQLite 시간 저장은 UTC epoch 초이며 JSON API는 aware ISO 8601이다. DB 검색 JSON은 저장 전/읽은 후 Pydantic으로 검사한다. 스냅샷은 서버 재시작 후에도 동일 식별자로 조회할 수 있다.
- 직접 경로·환승 후보는 노선과 승하차 **순번**으로 계산한다. 같은 이름·좌표·정류장 ID만으로 환승을 만들지 않는다. 미확인 거리·소요시간·좌표·지역은 null이다. 순번이 비연속이어도 실제 경유 행 수로 stopCount를 계산한다.
- SHA-256 기반 경로 버전은 경유 구조·선택 구간·사용 환승 근거·현재 경로 관련 변경과 상태를 포함한다. ETA·단순 원천 갱신/수집 시각은 포함하지 않는다. 저장 경로가 달라지면 재검색하도록 기존 409 ROUTE_VERSION_CHANGED를 사용한다.
- 만료는 now >= expiresAt. 검색 없음 → 만료 → 옵션 없음 → 핵심 자료 → 경로/상태/기대 버전 순으로 오류를 고정했다. unavailable 전용 새 코드는 도입하지 않았다.
- 데모 원천 시각은 시나리오 발행 시 고정한다. polling/generatedAt으로 fresh를 만들지 않는다. 미수신 arrival은 unavailable/operationStatus unknown이며 변경 조회 실패는 coverageStatus unknown이다. live 기본 제공자는 핵심 자료를 제공하지 않아 503이며 demo를 섞지 않는다.
- AI에는 허용 목적지 또는 구간 ID·타입·허용 템플릿만 전달한다. ID 부분집합·중복·상태, 안내 버전·정확한 순서/개수/템플릿을 검사한다. AI의 자유 사실·이유 문구는 채택하지 않는다. 기본 고정 문구는 서비스의 사실 바인딩이며 AI 선택 모듈을 대리 구현한 것이 아니다.
- AI 결과는 출력 검증까지 포함해 1초 이내만 채택한다. 프로세스당 1개 동기 worker/대기열 없음이며 초과 요청은 바로 대체한다. 시간초과 이후 작업을 강제 중단한 것으로 표시하지 않는다. 작업이 끝나면 슬롯이 복구됨을 테스트했다.
- 인쇄는 상태/만료/버전을 다시 검사한 한 시점의 복사본이다. 모든 구간과 안내 버전이 같으며 ETA 카운트다운 값은 null이다. ready 경로는 도착 미수신이어도 notice와 함께 준비할 수 있다. 출력 성공은 판정하지 않는다.

## 실행한 명령·증거

프로젝트 루트에서 다음을 실제 수행했다. 설치의 첫 일반 실행은 DNS/ensurepip 제한으로 실패했으며 성공으로 기록하지 않는다. 권한이 허용된 실행에서 빈 venv에 고정 직접 의존성을 설치하고 pip를 복구했다. API TestClient도 기본 샌드박스의 asyncio socketpair가 멈추는 것을 traceback으로 확인한 뒤 권한이 허용된 실행에서 검증했다.

```text
git status --short / git branch --show-current / git rev-parse --show-toplevel
git switch -c codex/backend-implementation
python backend/tools/extract_hwp.py <사용자 Downloads의 HWP> backend/docs/source-plan.txt
python -m venv backend/.venv                          # ensurepip 단계 실패, 빈 venv 생성됨
python -m pip --python backend/.venv/Scripts/python.exe install --no-cache-dir --retries 0 fastapi==0.115.5 uvicorn==0.32.0 pydantic==2.9.2 SQLAlchemy==2.0.36 httpx==0.27.2 pytest==8.3.3
backend/.venv/Scripts/python -m ensurepip --upgrade    # TEMP/TMP를 backend/.local로 설정 후 성공
backend/.venv/Scripts/python -m pip freeze            # requirements.lock 기록
backend/.venv/Scripts/python -m pip install -r backend/requirements.lock
backend/.venv/Scripts/python -m pip check             # No broken requirements found
backend/.venv/Scripts/python -m backend.seed          # 두 번 실행, 수량 유지
backend/.venv/Scripts/python -m backend.demo scenario --name stale
backend/.venv/Scripts/python -m backend.demo scenario --name normal
backend/.venv/Scripts/python -m pytest backend/tests -q --basetemp=backend/.test-tmp -p no:cacheprovider --junitxml=backend/docs/test-results.xml
backend/.venv/Scripts/python -m backend.tools.server_smoke
backend/.venv/Scripts/python -m backend.tools.audit_workspace
git check-ignore <실행 DB/저널/테스트 DB/venv/환경 예시/잠금/합성 JSON>
git diff --check / git diff --name-status / git ls-files --others --exclude-standard
```

`server_smoke`가 실제 실행한 서버 명령은 `backend/.venv/Scripts/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`이다. 테스트 후 해당 서버·멈춘 자체 진단 프로세스는 종료했다. 실행 DB는 삭제하지 않았다.

## 남은 제약과 인수인계

| 항목 | 상태·후속 담당 |
| --- | --- |
| A/B 실제 검색→상세 화면 | 대기. 현재 frontend는 temp뿐. 6개 선택 필드·OpenAPI·동적 요청 도구 전달 |
| 실제 AI 함수·공통 Python | 대기. 현재 ai는 temp뿐. AI 담당의 함수 공개 후 AIAdapter 주입·공동 검증 필요 |
| 음성 재생·브라우저 인쇄·종이 결과 | 미수행. B/디자인 담당 범위. API 안내문·인쇄 JSON만 검증 |
| 다른 팀원 PC·macOS/Linux | 미수행. README 명령은 제공했으며 해당 OS 검증 완료로 표시하지 않음 |
| 실제 충남 교통 API | 미연결. 제공기관·키·지원 범위·이용 조건 계속 미확인 |
| 서로 다른 정류장 사이 도보 환승·다회 환승 | 초기 범위 제외. 명시 자료 없는 연결 생성 안 함 |
| 실행 데이터 교체·마이그레이션·운영 배포 | 초기 시연 범위 제외. 현재 seed는 기존 값 보존; 새 DB 파일로 독립 시연 가능 |
| 영구 중단된 AI 함수 | 단일 슬롯으로 작업 누적 방지. 함수 강제 종료는 불가; 자체 취소 기능 또는 프로세스 재시작 필요 |

부하/다중 worker/실제 외부 네트워크 장애 시험·브라우저 시각/접근성 검수는 수행하지 않았다. 전체 서비스 연동 완료가 아니라 **백엔드 독립 구현 및 검증 완료** 상태다.

## 변경 범위와 산출물

`workspace-baseline.json`에 backend 밖 27개 파일의 초기 SHA-256을 기록했고 `workspace-audit.json`으로 최종 비교한다. backend 밖 파일 생성·변경·삭제가 없어야 감사가 통과한다. 기존 다른 사람의 변경은 시작 시 없었으며 이후 외부 변경도 발견되지 않았다.

추적 파일 변경은 backend의 temp 4개 삭제뿐이며 소스·설정·문서·검증 기록은 새 파일이다. `.venv/`, `__pycache__/`, `.local/`의 실행 DB·테스트 DB·시나리오·서버 로그는 생성했으나 Git 제외다. 일반 캐시 규칙을 존중했으며 의존성 잠금·합성 초기 데이터·.env.example은 제외되지 않는다. Git 메타데이터의 로컬 브랜치 생성 외에 원격 변경은 없다.
