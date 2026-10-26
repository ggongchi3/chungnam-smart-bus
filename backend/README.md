# 백엔드 실행 안내

합성 데이터 전용 FastAPI 시제품이다. **시연 데이터 · 실제 운행 정보 아님**. 서비스 API 8개와 DB·경로·최신성·AI 출력 검증·인쇄 준비 데이터를 구현했다. 실제 교통 API, AI 선택 모듈, 프론트 화면, 음성 재생, 브라우저 인쇄는 연결되지 않았다.

명령은 프로젝트 루트에서 실행한다. 검증 환경은 Windows, Python **3.13.2**, FastAPI **0.115.5**, Uvicorn **0.32.0**, Pydantic **2.9.2**, SQLAlchemy **2.0.36**, HTTPX **0.27.2**, pytest **8.3.3**이다. SQLite는 Python 내장 라이브러리이며 실제 버전은 `docs/runtime-versions.json`에 기록한다. 전체 간접 의존성까지 `requirements.lock`에 고정했다. AI 담당자의 Python 버전 합의는 대기 중이다.

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

합성 도착 원천 시각은 시나리오를 처음 읽었을 때 고정된다. 30초 폴링이 원천 갱신 시각을 갱신하지 않는다. 91초부터 stale이며, 재발행하려면 `scenario --name normal`을 다시 실행한다. 도착 이벤트는 발행 시각 +300초이며 지난 이벤트로 새로운 도착을 만들어내지 않는다. 시나리오 재발행·단순 ETA 변경은 경로 버전을 바꾸지 않는다.

초기화는 `python -m backend.seed`이며, 재실행해도 기존 행은 덮어쓰지 않고 누락된 합성 행만 추가한다. 서버 시작도 같은 적재를 수행한다. 실행 DB를 지우는 reset 명령은 제공하지 않는다. 완전히 새로운 독립 실행 DB가 필요하면 `BUS_DATABASE_URL=sqlite:///backend/.local/new-demo.sqlite3`처럼 **기존에 없는 새 파일 경로**를 지정해 seed한다. 이 별도 명령은 안내이며 실검증은 `.local/tests/`의 새 DB 생성·재개방 테스트로 수행했다.

DB·저널·시나리오·로그·테스트 DB는 `.local/`, 가상환경은 `.venv/`에 있다. 모두 Git 제외를 확인했다. 합성 JSON·의존성 잠금·환경 설정 예시는 추적 가능하다.

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

AI는 `create_app(ai_adapter=...)`에 동기 함수 두 개를 가진 객체를 주입한다. `interpret_destination(payload)`, `choose_guidance(payload)`의 JSON 입출력은 공통 계약 8/9절을 따른다. 실제 모듈은 아직 없어 기본 응답은 `unavailable` / `template_fallback`이다. 별칭 해석이나 템플릿 선택 알고리즘을 백엔드에 대신 구현하지 않았다. 허용 템플릿은 `bus.basic`, `walk.basic`, `transfer.basic`이다. 후보 ID·구간·순서·버전을 검증하고 사실 값은 서버가 삽입한다. 모델이 만든 이유 문구는 사용하지 않고 서버 소유 reasonCode만 제공한다.

AI 채택 예산은 출력 검증 포함 1초다. 동시에 실행하는 AI 함수는 프로세스당 최대 1개이며 대기열이 없다. 시간초과는 **결과 채택 중단**으로 실제 함수를 강제 종료하지 않는다. 작업이 끝나기 전에는 추가 AI 호출도 대체 처리한다. 무기한 멈춘 어댑터는 프로세스를 재시작하거나 어댑터 자체 중단 기능이 필요하다. 다중 worker를 실행하면 이 제한은 프로세스별로 적용된다.

인쇄 응답은 같은 버전의 상세·운행 스냅샷·고정 안내·notice를 제공한다. 계약의 `etaSeconds` 필드는 **null**이며 카운트다운 값은 없다. 절대 도착 예정 시각과 원천 시각은 스냅샷으로 남는다. 도착 미수신/변경 조회 불가는 경고와 함께 출력 데이터를 제공하지만 경로 변경·이용 불가·만료는 거부한다. HTML·CSS·프린터 연결·출력 성공 판정은 제공하지 않는다.

## 테스트와 실행 가능한 예시

서버를 실행한 상태에서 두 번째 터미널로 요청 예시를 실행한다. `departAt`과 검색 식별자는 스크립트가 매번 현재 값으로 만든다.

```powershell
backend/.venv/Scripts/python -m backend.tools.request_examples
backend/.venv/Scripts/python -m pytest backend/tests -q --basetemp=backend/.test-tmp -p no:cacheprovider
backend/.venv/Scripts/python -m backend.tools.server_smoke
backend/.venv/Scripts/python -m backend.tools.audit_workspace
```

`server_smoke`는 8000 포트가 비어 있을 때 실행하며 자식 서버를 띄워 8개 API·정상/빈 결과/400/404/409와 `/docs`, `/openapi.json`을 검증한 뒤 그 서버를 종료한다. `docs/examples.json`은 **실제 실행 응답 기록**이며 재사용 요청의 고정 시각 예제가 아니다. `request_examples`가 현재 시각의 요청을 생성한다. `server_smoke`와 TestClient를 Windows에서 실행했다. Swagger HTML과 OpenAPI는 HTTP로 확인했으며 실제 브라우저 클릭·시각 검수는 수행하지 않았다.

테스트는 요청별 격리 메모리 DB와 `.local/tests/`의 파일 DB를 사용한다. 시각·제공자·AI 어댑터를 주입해 10분을 기다리거나 실행 DB를 삭제하지 않는다. 실행 결과와 제약은 `docs/implementation-status.md`, 타 담당자 변경 제안은 `docs/coordination-notes.md`에 있다.
