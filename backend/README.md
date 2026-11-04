# 백엔드 실행 안내

합성 데이터 전용 FastAPI 시제품이다. **시연 데이터 · 실제 운행 정보 아님**. 서비스 API 8개와 DB·경로·최신성·AI 출력 검증·인쇄 준비 데이터를 구현했다. 기본 서버에는 외부 모델·네트워크를 호출하지 않는 규칙 기반 AI 어댑터가 연결되어 있다. 실제 교통 API, 프론트 화면, 음성 재생, 브라우저 인쇄는 연결되지 않았다.

명령은 프로젝트 루트에서 실행한다. 검증 환경은 Windows, Python **3.13.2**, FastAPI **0.115.5**, Uvicorn **0.32.0**, Pydantic **2.9.2**, SQLAlchemy **2.0.36**, HTTPX **0.27.2**, pytest **8.3.3**이다. SQLite는 Python 내장 라이브러리이며 실제 버전은 `docs/runtime-versions.json`에 기록한다. 전체 간접 의존성까지 `requirements.lock`에 고정했다. 규칙 기반 AI 모듈은 표준 라이브러리만 사용한다.

## Windows PowerShell

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.lock
backend/.venv/Scripts/python -m pip check
backend/.venv/Scripts/python -m backend.seed
backend/.venv/Scripts/python -m backend.demo scenario --name normal
backend/.venv/Scripts/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

이 환경에서는 기본 샌드박스의 ensurepip와 로컬 소켓에 제한이 있었다. 빈 가상환경 생성 후 시스템 pip의 `--python backend/.venv/Scripts/python.exe install ...`로 의존성을 설치했으며, 권한이 허용된 실행에서 다음 복구 명령과 잠금 파일 설치를 확인했다. 일반 PC에서는 위 표준 명령을 사용한다.

```powershell
$env:TEMP=(Resolve-Path backend/.local).Path
$env:TMP=$env:TEMP
backend/.venv/Scripts/python -m ensurepip --upgrade
backend/.venv/Scripts/python -m pip install -r backend/requirements.lock
```

`TEMP`/`TMP` 변경은 해당 PowerShell 프로세스에만 적용한다. 패키지 설치에는 패키지 서버 연결이 필요하다. 개발 서버는 로컬 주소에만 바인딩한다. [`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs)에서 OpenAPI UI를 제공한다.

## macOS / Linux

아래는 경로 차이를 반영한 안내이며 이 OS들에서는 실행하지 않았다. Python 3.13 환경을 별도로 준비한다.

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.lock
backend/.venv/bin/python -m backend.seed
backend/.venv/bin/python -m backend.demo scenario --name normal
backend/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

## 설정과 데이터

설정 예시는 `.env.example`이다. **.env 자동 로딩은 하지 않는다.** PowerShell의 `$env:BUS_DEMO_SCENARIO='stale'`, 셸의 `export BUS_DEMO_SCENARIO=stale` 등으로 프로세스 환경변수를 지정한다.

| 설정 | 기본값 / 의미 |
| --- | --- |
| `BUS_DATA_MODE` | `demo`. `live`는 미연결 제공자로 503을 반환하며 합성 자료를 사용하지 않음 |
| `BUS_DATABASE_URL` | 절대 경로의 `backend/.local/bus.sqlite3`. 파일 DB는 `.local/` 안만 허용 |
| `BUS_DEMO_SCENARIO` | `normal`. 아래 시나리오 파일이 있으면 파일이 우선 |
| `BUS_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |

`backend/.local/scenario.json`은 시연 CLI가 원자적으로 교체한다. 서버 재시작 없이 다음 요청에 반영된다. CLI와 환경변수 이름은 백엔드 내부 도구이며 공개 API를 늘리지 않는다.

```powershell
backend/.venv/Scripts/python -m backend.demo scenario --name stale
backend/.venv/Scripts/python -m backend.demo scenario --name normal
```

두 명령을 실제 실행했다. 같은 방식으로 `arrivals_missing`, `source_missing`, `source_future`, `changes_unknown`, `cancellation`, `detour`, `timetable_change`, `core_unavailable`을 선택한다. 모든 시나리오의 API 동작은 주입 제공자로 자동 테스트했다. 실제 HTTP smoke는 normal 시나리오로 실행했다.

5단계에서 `operation_running`, `operation_not_running`, `arrivals_missing_running`을 추가해 총 13개 합성 시나리오를 제공한다. 명시적 운행 상태는 시연 1번 노선에만 적용한다. 새 시나리오의 API 동작은 주입 제공자 자동 테스트 및 5단계 HTTP 도구로 검증했으며 공용 scenario.json은 바꾸지 않았다.

합성 도착 원천 시각은 시나리오를 처음 읽었을 때 고정된다. 30초 폴링이 원천 갱신 시각을 갱신하지 않는다. 91초부터 stale이며, 재발행하려면 `scenario --name normal`을 다시 실행한다. 도착 이벤트는 발행 시각 +300초이며 지난 이벤트로 새로운 도착을 만들어내지 않는다. 시나리오 재발행·단순 ETA 변경은 경로 버전을 바꾸지 않는다.

초기화는 `python -m backend.seed`이며, 재실행해도 기존 행은 덮어쓰지 않고 누락된 합성 행만 추가한다. 서버 시작도 같은 적재를 수행한다. 실행 DB를 지우는 reset 명령은 제공하지 않는다. 완전히 새로운 독립 실행 DB가 필요하면 `BUS_DATABASE_URL=sqlite:///backend/.local/new-demo.sqlite3`처럼 **기존에 없는 새 파일 경로**를 지정해 seed한다. 이 별도 명령은 안내이며 실검증은 `.local/tests/`의 새 DB 생성·재개방 테스트로 수행했다.

DB·저널·시나리오·로그·테스트 DB는 `.local/`, 가상환경은 `.venv/`에 있다. 모두 Git 제외를 확인했다. 합성 JSON·의존성 잠금·환경 설정 예시는 추적 가능하다.

### 2단계 DB·시연 데이터 검증 (2026-10-27)

v2 계획서의 2단계를 다시 대조하여 기존 구현을 보존하고 적재 결과 집계·실제 적재 실패 롤백 검증을 보강했다. `seed` 명령은 고정 문구 대신 테이블별 `inserted`(이번 신규 수)와 `totals`(실제 DB 전체 수)를 JSON으로 출력한다. 이미 준비된 DB에서는 재실행 시 inserted가 모두 0이며, totals는 정류장 5·목적지 3·별칭 3·노선 2·경유 6·접근 연결 3·환승 1이다.

```powershell
backend/.venv/Scripts/python -m backend.tools.verify_stage2
backend/.venv/Scripts/python -m pytest backend/tests/test_stage2.py -q --basetemp=backend/.test-tmp-stage2 -p no:cacheprovider
```

두 명령을 실제 실행했다. 전용 테스트 **13개**, 기존 기능을 포함한 전체 테스트 **78개**를 통과했다. 실행 DB의 전체 행 해시가 재적재 전후 동일하고 기존 검색 스냅샷 2개도 보존됐다. 검증 도구는 DB를 삭제하거나 기존 행을 덮어쓰지 않는다.

테이블별 PK·FK·nullable·고유 조건은 [DB 명세](docs/database-schema.md), 실제 DB 검증 기록은 [2단계 결과](docs/stage2-verification-20261027.json), A/B용 정상·빈 결과·오류 및 AI 입출력 예시는 [2단계 인수인계 JSON](docs/stage2-handoff-examples.json)에 있다. 응답 기록의 시각·검색 ID는 당시 실행값이다. 새 요청은 기존 `backend.tools.request_examples`처럼 현재 시각을 생성한다. 실제 A/B·AI 담당자와의 공동 확인은 대기 중이다.

### 3단계 정류장·목적지 조회 검증 (2026-10-27)

`GET /api/v1/stations/{stationId}`와 `GET /api/v1/destinations`는 SQLite 자료를 조회한다. 조회 조건은 DestinationQuery 모델에서 검증하고 기존 파라미터·응답·ID는 유지했다. 병원/시장/터미널 이름·별칭·분류, 교집합, 공백 제거 후 100자 경계와 오류를 검증했다.

```powershell
backend/.venv/Scripts/python -m backend.tools.verify_stage3
backend/.venv/Scripts/python -m pytest backend/tests/test_stage3.py -q --basetemp=backend/.test-tmp -p no:cacheprovider
```

두 명령을 실제 실행했다. 전용 테스트 **44개**, 전체 테스트 **122개**를 통과했으며, 실제 Uvicorn 서버의 **21개 HTTP GET 사례**와 로컬 CORS/OpenAPI도 통과했다. 검증 도구는 비어 있는 8000 포트에 독립 메모리 DB를 사용하는 자식 서버를 띄웠다가 종료한다. 기존 서버가 있다면 종료하지 않고 실행이 중단된다. 실행 DB·시연 상태는 변경하지 않는다.

A 담당자가 사용할 요청·응답·8000/5173 프록시 기준은 [3단계 연동 안내](docs/stage3-integration.md), 실제 HTTP 기록은 [조회 응답 예시](docs/stage3-http-examples.json)에 있다. 프론트엔드 A 화면은 아직 없어 실제 브라우저 공동 검증은 대기다.

### 4단계 경로 검색·상세 검증 (2026-10-27)

직통·명시적 1회 환승, 검색 스냅샷과 상세 조회를 보완했다. 전체 후보를 정렬하고 이용 가능한 후보를 고른 뒤 최대 3개로 제한한다. 새 후보가 추가돼 순위만 바뀌어도 기존 선택 경로의 사실·버전이 같으면 상세를 유지한다. 저장 스냅샷은 쓰기/읽기에서 내부 모델로 검증하고 같은 버전의 재계산 구간과 대조한다. 손상된 자료는 503이며 실제 경로 변경은 기존 409다. 숫자 epoch 대신 시간대 포함 ISO 8601 departAt을 요구한다.

```powershell
backend/.venv/Scripts/python -m backend.tools.verify_stage4
backend/.venv/Scripts/python -m pytest backend/tests/test_stage4.py -q -p no:cacheprovider
```

두 명령을 실제 실행했다. 전용 테스트 **39개**, 전체 테스트 **161개**, 실제 Uvicorn **21개 검색·상세 HTTP 사례**와 CORS/OpenAPI가 통과했다. 시장1·병원2·터미널 환승 합계4, 후보 정렬·제한·명시 환승·출발 시각 경계·스냅샷 저장/재시작·손상 거부를 확인했다. HTTP 도구는 독립 메모리 DB의 자식 서버를 사용해 실행 DB·시연 상태를 보존한다.

요청·응답과 A→B 6개 필드는 [4단계 연동 안내](docs/stage4-integration.md)와 [실제 HTTP 기록](docs/stage4-http-examples.json)에 있다. 응답 기록의 검색 ID는 그 검증 실행에서만 유효하므로 새로운 검색 결과를 사용한다. 실제 A/B 화면의 선택→상세 연결은 대기다.

### 5단계 도착·운행 변경·시간·버전 검증 (2026-10-27)

도착과 운행 변경의 원천/수집/응답 시각을 분리하고 서버 현재 시각으로 각 항목 최신성을 다시 계산한다. 도착 예정 시각·운행 상태는 `(routeId, boardStationId)`별 명시적 제공 관측값을 사용한다. 서비스가 수집 시각에 임의로 300초를 더하지 않으며 미수신을 결행으로 해석하지 않는다.

변경 범위에는 선택한 버스 구간의 실제 중간 정류장을 포함한다. 경로 밖 변경이나 적용이 미래/종료된 변경은 현재 경로를 막지 않는다. 변경 항목·적용 대상 ID 집합의 순서만 바뀌거나 ETA만 갱신돼도 버전은 유지한다. 시작 시각이 미확인인 변경은 현재 결행으로 확정하지 않고 재확인을 요구한다. 제공자 전체 실패는 핵심 자료 503, 하위 도착/변경만 실패하면 항목별 unavailable/unknown의 200이다. 없는 검색/옵션·만료 우선순위도 보존한다.

```powershell
backend/.venv/Scripts/python -m backend.tools.verify_stage5
backend/.venv/Scripts/python -m pytest backend/tests/test_stage5.py -q -p no:cacheprovider
```

두 명령을 실제 실행했다. 전용 테스트 **45개**, 전체 **206개**, 실제 Uvicorn **36개 HTTP 사례**를 통과했다. 주입 시각으로 0/90/91/599/600초를 재현했으며 실제로 10분을 기다리지 않았다. HTTP 도구의 제어 파일은 `.local/`의 매 실행 전용 폴더에만 생성하고 메모리 DB를 사용한다. 정상 앱의 공개 API는 8개 그대로이고 실행 DB·공용 시연 상태는 보존했다.

B 담당자의 30초 조회·5초 제한·GET 재시도·오류/최신성 표시는 [5단계 연동 안내](docs/stage5-integration.md), 상태별 실제 JSON은 [HTTP 사례](docs/stage5-http-examples.json)를 참조한다. 실제 B 화면의 타이머·요청 취소·표시 검증은 대기다.

### 6단계 AI 중계·인쇄 준비 검증 (2026-10-28)

실제 ai 모듈은 아직 없으며 백엔드의 주입 어댑터·출력 검증·실패 대체만 구현한다. worker 준비/시작 실패에도 슬롯을 복구하고 남은 채택 예산만 기다린다. 미지원 async/비JSON 출력은 대체 처리하고 입력·출력을 복사한다. 프로세스당 실행1개·대기열없음과 1초 채택 기준은 유지한다. 실제 동기 함수를 강제 중단하는 기능은 아니다.

AI 해석 후 현재 등록 목록을 다시 확인해 변경된 이름을 사용하고 삭제된 ID는 대체한다. 쉬운 안내는 검증된 구간/허용 템플릿만 사용하며 확인된 도보 거리와 시간도 각각 보존한다. 인쇄는 같은 경로·구간·버전의 고정 문구와 실제 unavailable/stale/unknown 상태 안내를 제공하고 ETA 카운트다운은 null이다.

```powershell
backend/.venv/Scripts/python -m backend.tools.verify_stage6
backend/.venv/Scripts/python -m pytest backend/tests/test_stage6.py -q -p no:cacheprovider
```

두 명령을 실제 실행했다. 전용 테스트 **46개**, 전체 **252개**, 실제 HTTP **28개 사례**를 통과했다. HTTP 도구는 AI 어댑터를 주입하지 않고 독립 메모리 DB·주입 시각으로 공개 API8개를 검증한다. 가짜 AI의 성공/오류/지연은 pytest에만 있다. 실제 AI가 연결된 것으로 표시하지 않는다. 실행 DB·공용 시연 상태를 바꾸거나 실제10분을 기다리지 않았다.

[6단계 연동 안내](docs/stage6-integration.md)와 [실제 HTTP 기록](docs/stage6-http-examples.json)에 B/AI 담당자가 사용할 계약·응답을 정리했다. 실제 AI 모듈·B 화면·브라우저 음성/인쇄·팀원 PC 공동 검증은 대기다. HTML/CSS·window.print·프린터 제어·종이 출력 성공 판정은 포함하지 않는다.

## API와 연동

`api/routes.py`의 8개 경로와 `models/schemas.py`가 실제 요청·응답 스키마다. 생성된 명세는 `docs/openapi.json`이다. 성공/오류 모두 `data/error/meta`를 사용한다. FastAPI 입력 검증 오류는 422 대신 **400 INVALID_REQUEST**다. 기본 요청 ID는 서버가 생성하며 `X-Request-ID`에도 반환한다. 응답은 `Cache-Control: no-store`다.

| 합성 ID | 의미 |
| --- | --- |
| `demo-stop-001` ~ `demo-stop-005` | 출발 → 시장 → 병원 → 중간 → 터미널 |
| `demo-route-001` | 001 → 002 → 003, 순번 1/2/3 |
| `demo-route-002` | 003 → 004 → 005, 순번 1/2/3 |
| `demo-destination-001` | 병원, 별칭 `시연 큰 병원`, 접근 정류장 003 |
| `demo-destination-002` | 시장, 별칭 `시연 장터`, 접근 정류장 002 |
| `demo-destination-003` | 터미널, 별칭 `시연 버스터미널`, 접근 정류장 005 |

명시적 환승은 route-001 순번 3 → route-002 순번 1 하나다. 합성 자료 안에서만 승인한 연결이다. 역방향 자동 생성은 없다. 후보는 환승 수 → 버스 정류장 합계 → 노선·승하차 순번 키 순으로 정렬하며 중복 제거 후 최대 3개다. 거리·시간·좌표·지역은 미확인 시 null이다.

`departAt`은 현재 시각에서 절댓값 120초까지 허용한다. `query`는 공백 제거 후 100자, `text`는 공백 제거 후 1~200자다. 검색 유효기간은 600초이고 `now >= expiresAt`부터 410이다. 시간 비교는 UTC, 응답은 시간대 포함 ISO 8601이다. 클라이언트가 Asia/Seoul로 표시한다.

기존 계약에 완료된 unavailable 전용 오류 코드가 없으므로, 경로 이용 불가·재확인·변경은 기존 **409 ROUTE_VERSION_CHANGED**와 재선택 메시지를 사용한다. 오류 우선순위는 검색 없음 404 → 만료 410 → 옵션 없음 404 → 핵심 자료 없음 503 → 모드/경로/상태/기대 버전 불일치 409다. 상세/live도 저장된 버전이 바뀌면 재검색이 필요하다.

A는 `originStationId`, `destinationId`, `routeSearchId`, `routeOptionId`, `routeSnapshotVersion`, `dataMode`를 B에 넘긴다. B는 상세/live 버전을 대조하고 안내·인쇄 POST에는 `expectedRouteSnapshotVersion`을 사용한다. `meta.dataMode=demo`면 모든 화면에 **시연 데이터 · 실제 운행 정보 아님**을 표시한다. 안내 첫 문장과 인쇄 notice에도 같은 표시를 제공한다. 30초 폴링·5초 클라이언트 제한·GET 한 번 재시도 정책과 호환된다. 프론트 타이머·재시도 구현은 포함하지 않았다.

기본 ASGI 앱 `backend.main:app`은 `create_app(ai_adapter=RuleBasedAIAdapter())`로 AI 담당자의 규칙 기반 어댑터를 연결한다. `ai/destination_interpretation/`, `ai/easy_guidance/`는 표준 Python import를 사용한다. 별도 서버를 만들 때는 `create_app(ai_adapter=...)`로 교체할 수 있고, `create_app()` 또는 `create_app(ai_adapter=None)`은 미연결 실패 대체를 유지한다. `interpret_destination(payload)`, `choose_guidance(payload)`의 JSON 입출력은 [AI 계약](../ai/contracts/README.md)과 공통 계약 8/9절을 따른다. 허용 템플릿은 `bus.basic`, `walk.basic`, `transfer.basic`이다. 후보 ID·구간·순서·버전을 검증하고 사실 값은 서버가 삽입한다.

공개 `reasonCode`는 검증한 `status`에서 서버가 결정한다: `matched → MATCHED`, `needs_confirmation → USER_CONFIRMATION_REQUIRED`, `no_match → NO_REGISTERED_MATCH`, `unavailable → AI_UNAVAILABLE`. 어댑터가 보낸 이유 문구를 그대로 노출하지 않는다. 오타 추정은 후보가 1개여도 `needs_confirmation`이며 `matched`도 사용자가 후보를 확인하고 선택한다. 미연결·오류·시간초과 시에는 `unavailable` / `template_fallback`으로 대체한다.

AI 채택 예산은 출력 검증 포함 1초다. 동시에 실행하는 AI 함수는 프로세스당 최대 1개이며 대기열이 없다. 시간초과는 **결과 채택 중단**으로 실제 함수를 강제 종료하지 않는다. 작업이 끝나기 전에는 추가 AI 호출도 대체 처리한다. 무기한 멈춘 어댑터는 프로세스를 재시작하거나 어댑터 자체 중단 기능이 필요하다. 다중 worker를 실행하면 이 제한은 프로세스별로 적용된다.

인쇄 응답은 같은 버전의 상세·운행 스냅샷·고정 안내·notice를 제공한다. 계약의 `etaSeconds` 필드는 **null**이며 카운트다운 값은 없다. 절대 도착 예정 시각과 원천 시각은 스냅샷으로 남는다. 도착 미수신/변경 조회 불가는 경고와 함께 출력 데이터를 제공하지만 경로 변경·이용 불가·만료는 거부한다. HTML·CSS·프린터 연결·출력 성공 판정은 제공하지 않는다.

## 테스트와 실행 가능한 예시

2026-10-28 백엔드 단독 전체 점검에서 추가 회귀64개를 포함해 **316개 테스트**와 **백엔드 HTTP28개 사례**가 통과했다. 손상된 저장 메타데이터/제공자 모델·서버 자료 검증·오류 헤더·시작 실패 정리·확인된 도보 요약을 보완했다. 실제 다른 팀원 모듈이나 화면의 연동 검사는 하지 않았다. [전체 점검 보고서](docs/backend-audit-20261028.md)에 재현·수정·제약을 기록했다.

```powershell
backend/.venv/Scripts/python -m pytest backend/tests -q --basetemp=backend/.test-tmp -p no:cacheprovider --junitxml=backend/docs/backend-audit-tests-20261028.xml
backend/.venv/Scripts/python -m backend.tools.verify_stage6 --output backend/docs/backend-audit-http-20261028.json
```

위 두 명령을 실제 실행했다. `--output`은 backend 내부에 별도 HTTP 기록을 저장하며 기존 단계별 기록은 그대로 유지한다. 백엔드 밖 파일·실행 DB·공용 시연 상태 보존을 최종 비교한다.

서버를 실행한 상태에서 두 번째 터미널로 요청 예시를 실행한다. `departAt`과 검색 식별자는 스크립트가 매번 현재 값으로 만든다.

```powershell
backend/.venv/Scripts/python -m backend.tools.request_examples
backend/.venv/Scripts/python -m pytest backend/tests -q --basetemp=backend/.test-tmp -p no:cacheprovider
backend/.venv/Scripts/python -m backend.tools.server_smoke
backend/.venv/Scripts/python -m backend.tools.audit_workspace
```

`server_smoke`는 8000 포트가 비어 있을 때 실행하며 자식 서버를 띄워 8개 API·정상/빈 결과/400/404/409와 `/docs`, `/openapi.json`을 검증한 뒤 그 서버를 종료한다. `docs/examples.json`은 **실제 실행 응답 기록**이며 재사용 요청의 고정 시각 예제가 아니다. `request_examples`가 현재 시각의 요청을 생성한다. `server_smoke`와 TestClient를 Windows에서 실행했다. Swagger HTML과 OpenAPI는 HTTP로 확인했으며 실제 브라우저 클릭·시각 검수는 수행하지 않았다.

테스트는 요청별 격리 메모리 DB와 `.local/tests/`의 파일 DB를 사용한다. 시각·제공자·AI 어댑터를 주입해 10분을 기다리거나 실행 DB를 삭제하지 않는다. 실행 결과와 제약은 `docs/implementation-status.md`, 타 담당자 변경 제안은 `docs/coordination-notes.md`에 있다.
