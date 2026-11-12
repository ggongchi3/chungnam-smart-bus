# 7단계 기능 연결 조사와 검증 순서

조사일: 2026-11-09, Asia/Seoul. 기준은 [기존 7단계 원문](../backend/docs/source-plan.txt) 383~399행, [개발 기준안](development-plan.md), [API 계약](api-contract.md), [역할](roles.md), [데이터 출처](data-sources.md)다. 적용할 `AGENTS.md`는 저장소와 상위 경로에서 발견하지 못했다. 이 문서는 **실제 파일 조사 결과**이며 테스트 통과나 브라우저 검증 완료를 뜻하지 않는다. 이번 실행 결과와 수정·재검증은 별도 7단계 결과 보고서에서 판단한다.

## 조사 결론과 역할

백엔드 API·SQLite·합성 교통 제공자·규칙 기반 AI의 연결 코드는 존재한다. 프론트엔드는 `temp` 10개뿐이며 `package.json`, 잠금파일, Vite 설정, `index.html`, TypeScript/React 소스, API 클라이언트가 없다. A/B는 두 앱이 아니라 하나의 앱의 기능 담당이다([roles.md](roles.md) 3·10·11행).

디자인에는 자리 표시자 6개와 `kiosk-concept/`의 이미지 3개가 있다. `키오스크사이즈.png`, `키오스크사이즈2.png`, `키오스크렌더링.jpg`를 직접 열어 확인했다. 외형 치수·빈 화면·안내표 출력구의 콘셉트이며 화면별 정보 구성, 버튼, 색상, 인쇄물 시안이나 합의 기록은 아니다. 외형 치수를 CSS 목표 해상도나 브라우저 배율로 환산하지 않았다. `wireframes/`, `screens/`, `guidelines/`, `assets/`, `print-guide/`는 `temp`뿐이다. 따라서 합의된 화면과 실제 화면의 비교, 화면 크기·긴 문자열·접근성의 브라우저 검증은 차단이다.

공통 문서에는 본문 24px·제목 32px, 주요 터치 영역 64×64 CSS px, 요소 간격 16px, 텍스트 대비 4.5:1, A4 세로·여백 15mm·본문 16pt라는 **초기 목표**만 있다([development-plan.md](development-plan.md) 121~136행). 실제 디자이너의 승인이나 기준 충족을 확인한 상태로 해석하지 않는다.

## 기능 연결표

아래 표의 `코드 연결`은 존재하는 함수·라우터 간 호출을 뜻한다. 프론트엔드까지 연결되었다는 뜻은 아니다. 경로에 적힌 `:행`은 조사 시점의 근거 위치다. 공개 API의 모든 경로에는 `/api/v1`이 앞에 붙는다.

| 기능 | 화면·디자인 근거 | 프론트엔드 구현 | 백엔드 API·서비스 | DB·외부 제공자·AI | 연결 상태 | 확인 근거 |
|---|---|---|---|---|---|---|
| 시작·현재 정류장 | 개발 기준안 9·13행; 화면 시안 없음 | A `src/app/temp`, `config/temp` | `GET /stations/{stationId}` → `catalog.station` | `stations`; `require_core`와 교통 제공자 확인 | 백엔드 코드 연결; 시작 UI 차단 | `backend/api/routes.py:31`, `backend/services/catalog.py:8`, `backend/models/tables.py:9` |
| 목적지 텍스트 검색·별칭 | 개발 기준안 14행; 역할 A | A `destination-search/temp`; 입력 요소 없음 | `GET /destinations` → `catalog.destinations`; query/category 교집합 | `destinations`, `destination_aliases`; 등록 ID만 반환 | 백엔드 코드 연결; 입력·로딩·결과 표시 차단 | `backend/api/routes.py:38`, `backend/models/schemas.py:66`, `backend/services/catalog.py:25` |
| 병원·시장·터미널 주요 장소 버튼 | 개발 기준안 14·64~68행 | A 버튼 미구현 | 같은 목적지 API의 `category=hospital/market/terminal` | 등록된 합성 목적지 3개 | 서버 조회 경로 있음; 버튼 동작 차단 | `frontend/src/features/destination-search/temp:1`, `docs/api-contract.md:65` |
| 자연어 목적지·후보 확인 | API 계약 232~272행; 추가 제안 범위 | A 후보 확인 UI 없음 | `POST /destination-interpretations` → `ai.interpret`; 후보 ID 검증·현재 목록 재확인·이유 코드 바인딩 | `RuleBasedAIAdapter.interpret_destination` → 규칙 해석; 실패 시 unavailable 후 일반 검색 | 기본 ASGI 앱에 규칙 모듈 코드 연결; 화면 복구 차단 | `backend/main.py:107`, `backend/api/routes.py:66`, `backend/services/ai.py:7`, `ai/adapter.py:12` |
| 경로 검색·후보 정렬·선택 | 개발 기준안 15~16행; API 계약 75~99행 | A `route-selection/temp`; 선택 상태·A→B 전달 없음 | `POST /route-searches` → `create_search` → `build_candidates`; 환승 수→버스 정류장 수→안정적 키, 최대 3개 | 노선·경유·접근·환승 테이블, `route_searches` 스냅샷 | 백엔드 코드 연결; 후보 클릭·선택 UI 차단 | `backend/api/routes.py:46`, `backend/services/journeys.py:39`, `backend/services/routing.py:17`, `backend/models/tables.py:70` |
| 직통·최대 1회 환승·도보 상세 | 개발 기준안 15·70~72행; 역할 B | B `journey-guide/temp` | `GET /route-searches/{id}/options/{id}` → `checked_detail`; bus/walk/transfer 순서와 버전 재검사 | 명시적 `transfer_connections`, `destination_access`; 역방향 자동 생성 없음 | 서버 상세 코드 연결; 화면·긴 구간·뒤로 가기 차단 | `backend/api/routes.py:52`, `backend/services/journeys.py:71`, `backend/services/routing.py:54`, `backend/models/tables.py:47` |
| 도착·운행 현황·원천 갱신 시각 | 개발 기준안 17행·API 계약 179~222행 | B `live-info/temp`; 30초 폴링 없음 | `GET .../live` → `live_info`; available/unavailable, running/not_running/unknown, 항목별 품질 | `DemoProvider`의 합성 관측값; `freshness` 0~90초 fresh, 90초 초과 stale, 없음/미래 unknown | 합성 제공자 코드 연결; 실제 교통·UI·폴링 차단 | `backend/api/routes.py:59`, `backend/services/journeys.py:114`, `backend/services/time.py:10`, `backend/integrations/providers.py:84` |
| 시간표 변경·결행·우회·변경 조회 실패 | 개발 기준안 23행; API 계약 217~222행 | B 변경·재확인 표시 없음 | 상세/live에서 경로 관련 변경·기간·상태 검사, 버전 변경 시 409; coverageStatus unknown 구분 | 합성 시나리오; 실제 제공기관/지원 범위 미정 | 합성 상태 연결; 실제 알림·화면 복구 차단 | `backend/services/routing.py:86`, `backend/services/routing.py:104`, `backend/integrations/providers.py:12`, `docs/data-sources.md:26` |
| 쉬운 상세 안내·AI 실패 대체 | API 계약 274~307행 | B 화면 안내 없음 | `POST /easy-guidance` → `ai.guidance`; 버전·구간·순서·허용 템플릿 검증, 서버가 사실 값 삽입 | `RuleBasedAIAdapter.choose_guidance`; 실패 시 고정 안내; 외부 LLM 없음 | 규칙 모듈과 서버 코드 연결; 화면 반영 차단 | `backend/api/routes.py:90`, `backend/services/ai.py:44`, `backend/services/ai.py:72`, `ai/easy_guidance/selector.py:32` |
| 음성 재생·중지·화면 이동 취소 | 개발 기준안 20·129행; 역할 B | B `voice-guide/temp`; speechSynthesis/getVoices/cancel 없음 | 별도 음성 API는 계약에 없음. 검증한 `/easy-guidance`의 steps를 B가 읽도록 설계 | 한국어 브라우저/OS 음성은 기기 의존; 실제 소리 확인 안 함 | 안내 텍스트 서버 경로만 있음; 음성 전체 차단 | `frontend/src/features/voice-guide/temp:1`, `docs/roles.md:11`, `docs/development-plan.md:37` |
| 인쇄 스냅샷·안내표·인쇄 미리보기 | 개발 기준안 19·130~134행; 인쇄 시안 없음 | B `print-guide/temp`; print CSS·DOM·window.print 없음 | `POST /print-guides` → `print_guide`; 상세·live·고정 안내·notice 같은 시점 복사, etaSeconds null | 서버 버전/만료/이용 가능 확인 후 스냅샷 반환; 프린터 직접 제어 없음 | 서버 JSON 준비 코드 연결; 브라우저 미리보기·페이지 분할·종이 출력 차단 | `backend/api/routes.py:98`, `backend/services/journeys.py:158`, `backend/models/schemas.py:237`, `design/print-guide/temp:1` |
| 오류·만료·버전 변경·결과 없음 | API 계약 309~339행; 개발 기준안 89·109행 | 공통 `shared/api/temp`, `shared/ui/temp`; 복구 동작 없음 | 공통 봉투, 입력 400, 없음 404, 변경/이용 불가 409, 만료 410, 핵심 자료 503; 검색 빈 배열 200 | 주입 가능한 clock/provider/AI; 검색 DB 스냅샷 | 서버 처리 존재; 화면 상태·경쟁 요청·중복 클릭·새로고침 차단 | `backend/main.py:25`, `backend/main.py:62`, `backend/services/journeys.py:71`, `frontend/src/shared/api/temp:1` |
| 시연 표시·null·시각 일관성 | 개발 기준안 9·78~87행; API 계약 14·29행 | 모든 화면 표시 미구현 | 응답 meta.dataMode, null 필드·상태·품질, 안내 첫 문장과 인쇄 notice; API는 오프셋 포함 ISO 8601 | 합성 원본 `demo-data.json`; 비교 UTC, 표시 Asia/Seoul은 프론트 책임 | 서버 계약 경로 있음; 화면/음성/인쇄 렌더링 차단 | `backend/models/schemas.py:23`, `backend/services/ai.py:65`, `backend/services/journeys.py:139`, `backend/integrations/demo-data.json` |

QR 저장, 혼잡도, 비상 안내, 오류 신고는 현재 README·공통 docs·기존 계획 추출본에서 요구사항을 찾지 못했다. 이번에 API나 화면을 새로 추가할 근거로 삼지 않는다. 사용자가 예로 든 단축 버튼 중 병원·시장·터미널 주요 장소 버튼은 위 표처럼 실제 범위다. 음성 입력·다회 환승·실제 프린터 제어·현장 설치도 초기 범위 밖이다.

## 공개 API 8개 대조

계약 64~71행과 실제 `backend/api/routes.py`의 라우터 8개를 다음과 같이 대응했다. `/docs`, `/redoc`, `/openapi.json`은 FastAPI 문서 기능이며 서비스 API 8개에 넣지 않는다. 시연 CLI도 공개 API가 아니다.

| 번호 | 메서드 | 경로 | 실제 라우터 함수 |
|---|---|---|---|
| 1 | GET | `/api/v1/stations/{stationId}` | `station` |
| 2 | GET | `/api/v1/destinations` | `destinations` |
| 3 | POST | `/api/v1/route-searches` | `search` |
| 4 | GET | `/api/v1/route-searches/{routeSearchId}/options/{routeOptionId}` | `detail` |
| 5 | GET | `/api/v1/route-searches/{routeSearchId}/options/{routeOptionId}/live` | `live` |
| 6 | POST | `/api/v1/destination-interpretations` | `interpretation` |
| 7 | POST | `/api/v1/easy-guidance` | `guidance` |
| 8 | POST | `/api/v1/print-guides` | `print_guide` |

## 실행·재현 경계 조사

| 영역 | 실제 근거 | 판단·남은 확인 |
|---|---|---|
| 백엔드 런타임 | 현재 `backend/.venv/Scripts/python`으로 Python 3.13.2·SQLite 3.45.3·FastAPI 0.115.5·Uvicorn 0.32.0·Pydantic 2.9.2·SQLAlchemy 2.0.36·HTTPX 0.27.2·pytest 8.3.3 조회 | 기존 로컬 환경의 import/버전 조회다. 새 설치·다른 PC 재현 완료를 뜻하지 않음 |
| 패키지 | `backend/requirements.txt`, `requirements.lock` 존재; AI는 표준 라이브러리 | 잠금 설치·pip check 및 깨끗한 환경 실행은 별도 실행 기록 필요 |
| 프론트 런타임 | React/TypeScript/Vite는 계획 기술. package/lock 소스 없음 | Node/npm 버전·설치·실행 명령을 검증 완료로 적을 수 없음 |
| 설정 | `backend/config.py:8`, `.env.example` | 프로세스 환경변수만 읽고 `.env` 자동 로드 안 함. 기본 DB는 `__file__` 기준 생성 경로이므로 특정 사용자 PC 경로 하드코딩 아님 |
| DB | `backend/database.py:13`의 SQLite·외래키, `initialize()`의 create_all; `backend/seed.py:33` 적재 | 파일 DB는 `backend/.local/` 아래만 허용. 별도 마이그레이션 도구/변경 이력 없음. 기존 DB 삭제 대신 새 파일 사용 필요 |
| 포트·CORS·프록시 | 기본 허용 Origin `http://localhost:5173`, `http://127.0.0.1:5173`; 개발 백엔드 8000 | Vite 프록시 구현 없음. CORS 서버 응답을 확인해도 브라우저 프론트 연동 통과가 아님 |
| 외부 제공자 | `UnconnectedLiveProvider`가 core_available=False를 반환 | 실제 교통은 미연결. live 모드의 503을 합성 운행 정보로 대체하지 않아야 함 |
| AI 실행 순서 | `backend/main.py:107`에서 규칙 어댑터 주입, `ai/adapter.py` 상대 import | 백엔드와 같은 Python 환경; 별도 AI 서버 불필요. 외부 모델 추론/키/네트워크 연결 없음 |
| 음성·인쇄 조건 | 공통 개발 기준안·역할 문서만 존재 | 실제 Chrome 한국어 음성, 스피커 청취, 사용자 재생·중지, print 대화상자·취소·레이아웃은 B 구현 후 실제 기기에서 확인 |
| 제출 환경 | 공통 문서에 공개 배포 주소·인증 후속 결정; 기존 7단계 395행에 URL이 필수인 경우 점검 요구 | 확정 제출 URL·HTTPS·배포/프록시 프로세스 없음. 로컬 HTTP를 최종 제출 환경으로 간주하지 않음 |
| 다른 팀원 PC | 저장소 안에는 공동 PC 재현 증거 없음 | 현재 PC 검증과 구분하여 미실행. 팀원에게 실제 전달했다고 표시하지 않음 |

## 조사에서 발견한 문서 차이

아래는 초기 조사 시점의 차이다. 이번 작업에서 수정된 경우 최종 보고서가 최신 판단이다. 초기 기록·과거 실행 결과를 삭제하지 않고 작성일과 당시 범위를 유지해야 한다.

| 구분 | 차이와 근거 | 처리 방향 |
|---|---|---|
| 구현 상태 문서 | README 마지막 준비 상태는 서버·AI 실행을 후속 작업으로 설명하지만 상단과 `backend/main.py`에는 백엔드·규칙 AI 존재 | 현재 상태 안내를 갱신하고 과거 기록과 구분 |
| 구현 상태 문서 | API 계약 서문·3절의 서버 미구현 문구, 개발 기준안 5·45행의 코드/원본 미생성 문구, 데이터 출처 문서 마지막 합성 원본 미생성 문구 | 역사적 작성 범위는 유지하되 현재 코드 위치·최신 검증 안내를 추가 |
| 계약·오류 코드 | 공통 계약 335행/개발 기준안은 ROUTE_UNAVAILABLE를 정의. backend README 155행과 5단계 안내는 전용 코드가 없다며 ROUTE_VERSION_CHANGED로 합침 | 백엔드가 실제 409 분기와 회귀 테스트를 대조하여 공통 계약을 기준으로 정정 |
| AI 과거 기록 | backend README의 6단계 당시 설명은 AI 미연결. 현재 기본 앱에는 RuleBasedAIAdapter 연결 | 과거 검증 당시 상태임을 표시하고 11/02 이후 연결과 구분 |
| 디자인·구조 | 구조 문서의 트리에는 kiosk-concept 이미지 3개가 생략되고 README는 디자인을 자리 표시자로만 설명 | 외형 자료와 없는 화면/인쇄 시안을 구분해 기록 |
| 합성 별칭 | 개발 기준안은 초기 별칭 예시가 더 많고 원본 JSON은 병원·시장·터미널 각 1개 별칭 | 실제 등록값과 제안 예시를 혼동하지 않도록 표시. 제공자/AI가 별칭을 임의 생성하지 않음 |
| 합성 표시명 | 개발 기준안은 `demo-stop-004`를 `시연 마을 정류장`으로, 실제 합성 원본은 `시연 중간 정류장`으로 정의 | 같은 ID의 표시명 차이를 기록. UI는 검증한 서버 이름을 사용하고 초기 문구를 사실 값으로 하드코딩하지 않음 |

## 검증 순서

1. 시작 Git 상태·실행 DB와 공용 시나리오 파일을 보존하고 현재 코드를 기준으로 OpenAPI·8개 API·주입 경계·파일 목록을 기록한다. frontend와 디자인 미준비 범위를 먼저 분리한다.
2. 격리된 테스트 DB에서 pytest/FastAPI TestClient를 실행한다. DB 반복 적재·FK·롤백, 직통/환승/역방향/정렬/null, departAt ±120/121초, 만료 599/600초, 최신성 0/90/91초·없음·미래를 주입 시각으로 검사한다.
3. 입력 400·미등록 404·변경/이용 불가 409·만료 410·핵심 자료 503과 공통 봉투, OpenAPI 차이를 확인한다. 실제 파일·응답에 근거해 버그를 수정하고 직접 영향 범위를 재실행한다.
4. 실제 규칙 기반 AI와 테스트용 어댑터를 구분한다. 후보·버전·구간 순서/누락/중복/템플릿·자료형·파싱·빈 응답·예외·시간초과 후 대체와 사실 바인딩을 검증한다.
5. 격리 Uvicorn과 실제 HTTP로 검색→선택 ID→상세→live→쉬운 안내→인쇄 JSON을 연결하고 요청/응답/로그를 남긴다. 인쇄 응답의 버전·구간·상태와 원본 갱신 후 고정 스냅샷을 검사한다. 이 단계는 브라우저 음성·인쇄 미리보기 통과와 구분한다.
6. 가능하면 기존 PC의 새 가상환경/새 DB에서 잠금 설치·기동을 재현한다. 다른 팀원 PC·macOS/Linux·확정 제출 HTTPS 환경은 실제 수행 여부를 따로 기록한다.
7. A/B와 화면·인쇄 디자인이 준비되면 실제 브라우저의 정상 직통/환승, 빈 결과, 400/404, 만료, 버전 변경, 부분 실패/최신성, AI 대체, 연속 검색/중복 클릭/뒤로가기/새로고침, 인쇄 고정 후 원본 변경의 10개 시나리오를 네트워크·응답·서버 로그와 대조한다. 한국어 소리 청취와 정지/재생·이동 시 중복 방지, 인쇄 페이지 분할·잘림을 실제 확인한다. 현재는 모듈 부재로 차단이다.

조사에 사용한 명령은 `rg --files frontend design`, `rg -n`으로 요구사항·라우터·함수를 대응하는 검색, 각 문서 원문 읽기, 이미지 3개 직접 열기, 현재 Python으로 버전 조회다. 조사 담당은 서비스 테스트·실제 브라우저·다른 팀원 PC·배포 검증을 수행한 것으로 기록하지 않았다.
