# 천안 정류장 기준 검색·다중 경로 구현 보고

2026-11-10. 기존 React/TypeScript/Vite, FastAPI, SQLite, 규칙 기반 AI, 천안 참조 데이터와 API 8개를 분석하고 재사용했다. 이 보고서가 이전 합성 데이터 설명·화면에서 자료 기준을 숨기던 기록보다 우선한다. 공개 배포는 수행하지 않았다.

| 항목 | 구현 결과 |
|---|---|
| 기준 버스정류장 | **종합터미널**, ARS **686**, BIS **285000686**. 충청남도 천안시 동남구 만남로, 천안종합버스터미널 앞. WGS84 **위도 36.8190148 / 경도 127.1565574**. 도로 위 정류장이므로 터미널 건물 주소와 구분한다. 주요 터미널·상업시설에 인접하고 경유 노선 61개를 확인해 선정했다. |
| 거리순 정렬 | 서버에서 WGS84 Haversine 직선거리 계산(평균 지구 반지름 6,371,008.8m), 거리→장소명→ID 오름차순. 기본 기준을 UI에 표시한다. 확보된 OSM 보행 경로 거리순도 지원하며 미확보 장소는 마지막이다. |
| 목적지 검색 | 검증된 26곳, 8개 시설 종류. 이름·별칭·주소 부분검색, 공백 제거, 분해형 한글 정규화, 시설 단축 버튼 지원. 천안 전역 임의 장소의 외부 검색은 미연동이다. |
| 다중 경로 | 공식 방향별 노선 333개 / 정류장 3,436개의 실제 경유 순서와 pedestrian 보행 연결을 사용한다. 직통·같은 정류장 ID에서 1회 환승을 탐색하고 노선 번호 조합 중복을 제거해 최대 12개를 반환한다. |
| 프론트엔드 | 고정 출발지, 거리 기준, 네 정렬, 경로 카드·승하차/환승 상세, 총시간·대기 미확인, 도보·전체거리, 정적 경로·도착 조회값 구분, 즉시 진한 선택 상태를 표시한다. 정렬 실패 시 이전 결과를 제거하고 같은 기준으로 재시도한다. |
| 백엔드 | 기존 DestinationLocation·RouteSearch 스냅샷 재사용. 고정 출발지 검증·DB 동기화, 정렬/동률 배지, 외부 도착 응답 검증, 경로 계산 중 다른 API 응답성을 개선했다. 스키마 변경·테이블 삭제는 없다. |
| AI | 기존 규칙 기반 목적지 해석·쉬운 안내 재사용. 최신 서버 카탈로그의 거리순을 유지하고 화면·음성·인쇄의 분 올림을 통일했다. AI가 노선·시간·좌표를 만들지 않는다. |
| 테스트 | 실제 Vite 프록시 HTTP **363건**, **26곳 × 4정렬 = 104검색**, **245개 경로 상세** 검증 통과. 최종 자동 테스트 집계는 아래에 기록한다. |

## 실제 자료 재검증

2026-11-10 천안시 BIS를 실제 조회했다.

- `GET https://its.cheonan.go.kr/bis/getBusStopList.do?searchKeyword=종합터미널`: HTTP 200. `STOP_ID=285000686`, `SERVICE_ID=686`, `STOP_NAME=종합터미널`, `LAT=36.8190148`, `LNG=127.1565574`가 저장값과 일치했다.
- `GET https://its.cheonan.go.kr/bis/getTransitRouteList.do?stopId=285000686`: HTTP 200. 경유 노선 **61개 ID 집합**이 로컬 스냅샷과 모두 일치했다.
- [천안시 정류장 조회](https://its.cheonan.go.kr/bis/busStop.do), [천안세관 공식 길안내](https://customs.go.kr/cheonan/lm/locationMapView.do?mi=5881)로 실존성을 교차 확인했다.

이는 기준 정류장 공개 목록 검증이며 333개 노선의 당일 운행·휴일·막차 검증을 뜻하지 않는다. 수집 시각과 원천 갱신 시각을 구분한다. 수집 도구는 출발지 좌표·명칭·ARS를 공식 응답에서 추출하며 필수값 누락/잘못된 좌표이면 기존 스냅샷을 유지한다.

시설 주소·좌표 원본 링크는 `shared/data/cheonan-places.json`, 범위·라이선스는 `shared/data/README.md`에 있다. 시설 대표점은 출입구와 다를 수 있다. 보행 자료는 [OpenStreetMap 기여자](https://www.openstreetmap.org/copyright), [ODbL](https://opendatacommons.org/licenses/odbl/1-0/)에 따른다.

## 검색 장소와 거리

- 병원 4: 단국대학교병원, 순천향대학교 부속 천안병원, 충청남도천안의료원, 천안충무병원.
- 관공서 6: 천안시청, 동남구청, 서북구청, 천안세무서, 국민연금공단 천안지사, 신안동 행정복지센터.
- 시장 3 / 쇼핑 1: 천안중앙시장, 성정시장, 병천시장, 신세계백화점 천안아산점.
- 터미널 2 / 역 3: 천안종합버스터미널, 천안고속버스터미널, 천안역, 두정역, 봉명역.
- 교육 4: 단국대학교·상명대학교·호서대학교 천안캠퍼스, 한국기술교육대학교.
- 문화·관광 3: 독립기념관, 천안박물관, 아라리오갤러리 천안.

명칭 일부와 주소, ‘의료시설’, ‘지하철역’, ‘철도역’, ‘관광지’ 등으로 검색할 수 있다. 카테고리와 AI 후보에도 서버 거리순을 적용한다. 직접 보행 경로가 확보된 21곳은 보행거리순으로 정렬하며 나머지는 `null`이다. 직선거리와 버스·도보를 합친 전체 이동거리는 구분한다. 화면 표시는 m 단위 정수 또는 km 소수 첫째 자리다.

## 경로 계산과 API

데이터 흐름은 목적지 검색 → 백엔드 장소 조회·거리 정렬 → 공식 노선/보행 연결 후보 탐색 → 지표 계산·중복 제거 → 프론트 경로 카드 → 선택 스냅샷의 상세·도착·AI 안내·인쇄 준비다.

- 네 기준은 최소 환승, 최소 도보, 최단 이동거리, **대기 제외 이동시간**이다. 각 기준 상위 후보군을 합쳐 최대 12개를 반환하고 같은 노선 번호 조합의 대표 하나를 표시한다. 각 지표 실제 최소값과 같은 후보 전체에 특징 배지를 붙인다.
- 버스 거리는 공식 노선 선형에 정류장 순서를 투영한 근삿값, 보행거리는 확보한 pedestrian 경로다. 버스 시간은 노선 전체 평균 소요시간의 구간 거리 비율로 추정한다.
- **대기·환승 대기를 포함한 최단시간은 미구현**이다. `totalDurationSeconds`와 `waitingDurationSeconds`는 `null`이며 확인되지 않음으로 표시한다. 순수 도보 카드는 대기 없음과 계산된 보행시간을 표시한다. 시간 정렬 이름도 ‘이동시간순 · 대기 제외’다.
- 도착값은 공식 응답의 노선 ID·승차 정류장 ID가 선택 구간과 일치할 때만 쓴다. 원천 갱신 시각이 없으므로 `fresh`로 승격하지 않는다. 최근 조회값은 90초 이내만 표시하고 실패·누락·만료 시 확인 불가다. 환승 정류장 값도 지금의 조회값이며 미래 환승을 보장하지 않는다.
- 잘못된 도착 응답 행은 건너뛰고 정상 행을 유지한다. 승차 정류장 요청을 병렬화하고 시간 제한을 둔다. CPU/SQLite 경로 계산은 FastAPI 작업 스레드에서 실행해 정류장·도착 API의 이벤트 루프를 막지 않는다.

| API | 최종 동작 |
|---|---|
| `GET /api/v1/stations/cheonan-stop-285000686` | 공식 정류장 이름·좌표. 재사용 DB의 출발지 값을 참조 자료로 동기화 |
| `GET /api/v1/destinations` | `originStationId`, `query`, `category`, `kind`, `sort=distance|walking|name`; 주소·좌표·직선거리/기준·보행거리·출처 |
| `POST /api/v1/route-searches` | `originStationId`, `destinationId`, `departAt`, `sort=transfers|walking|distance|fastest`; 최대 12개 후보·지표·자료 안내 |
| `GET /route-searches/{id}/options/{id}` | 실제 승하차·환승·보행 상세, 스냅샷 버전 검증·10분 만료 |
| 동일 경로의 `GET .../live` | 공식 도착조회. 미수신·원천 시각 미확인 보존 |
| `POST /destination-interpretations` | 등록 장소 ID와 최신 거리순 후보만 반환 |
| `POST /easy-guidance`, `POST /print-guides` | 검증된 구간 안내, 같은 버전 인쇄 스냅샷 |

천안 모드에서 고정 출발지 외 장소/경로 요청은 `400 INVALID_REQUEST`다. `demo-stop-*`를 보내 합성 경로가 `static`으로 노출되던 결함을 막았다. 기존 legacy 앱 팩토리와 합성 시나리오 테스트는 유지하며 기존 DB를 초기화하지 않았다.

## 검증 결과와 재현

최종 자동 테스트: 백엔드·AI **409 passed / 실패 0**(235.59초), 프론트 **7파일·59 passed / 실패 0**, TypeScript 검사·프로덕션 빌드 통과. `git diff --check` 통과. Starlette의 anyio BlockingPortal 별칭 폐기 예정 경고 1건이 있으며 기능 실패는 없다. 경로 계산 중 정류장 조회 응답성 회귀 테스트도 포함한다. 샌드박스의 소켓 접근 제한(WinError 10013)을 확인한 뒤 허용된 실행 환경에서 백엔드·실제 HTTP 검증을 수행했다.

실제 HTTP 결과는 [cheonan-verification-results.json](cheonan-verification-results.json)에 있다. Vite **5174 → FastAPI 8001 → 메모리 SQLite**에서 363건을 실행했다. 26곳 모두 중복 없는 6~12개 후보와 기준별 순서 변경을 확인했다. 245개 상세의 실제 노선 ID·정방향 승하차 순번·동일 ID 환승을 공식 원본 그래프와 대조했다. AI·live·인쇄 API도 확인했으며 실제 ETA 존재를 성공 조건으로 만들지 않았다.

브라우저에서 고정 정류장, 병원 직선/보행 거리순, 보행 미확보 표시, 시장·쇼핑 거리순, ‘중앙’ 부분검색→천안중앙시장, 최소 환승→시간순 변경, 532번 승차·6개 정류장·하차·207m 보행 상세, 기존 인쇄 준비 화면까지 확인했다. 화면·음성 안내 분 반올림 불일치를 발견해 양쪽 모두 4분으로 표시되는 것을 재확인했다. 스피커 청취와 실제 종이 출력은 미검증이다.

| 사용자 검증 항목 | 결과 |
|---|---|
| 1. 실제 정류장 | 공식 실조회 이름·좌표·ARS 및 경유 노선 61개 일치 |
| 2~3. 거리순·거리 계산 | 실제 26곳 오름차순, 알려진 적도 1도 거리·동일점/대칭 등 수치 검증. 이동거리는 선형·보행망 근삿값 |
| 4. 카테고리 | 8개 종류 HTTP 교집합·순서, 병원·시장 브라우저 확인 |
| 5. 복수 경로 | 26곳 모두 복수 후보, 노선 조합 중복 없음 |
| 6. 네 정렬 | 104검색 지표 오름차순·동률 배지 검증. 대기 포함 최단시간 미지원 |
| 7. 불가능한 경로 방지 | 실제 공식 방향·승하차·환승 검증. 당일 운행일·막차·결행은 자료 없어 확인 불가 |
| 8~9. 상세·통합 | 245개 상세 대조, Vite 프록시 HTTP 363건, 브라우저 선택→상세 확인 |
| 10. 기존 기능 | legacy·AI·만료·스냅샷·인쇄 준비·음성 UI 회귀. 현장 장비 미검증 |

전체 테스트는 프로젝트 루트에서 `backend/.venv/Scripts/python -m pytest backend/tests ai/evaluation -q -p no:cacheprovider`, 프론트는 `frontend`에서 `npm test`, `npm run build`로 재현한다.

격리 HTTP 검증은 별도 PowerShell 두 개에서 서버를 시작하고 세 번째에서 도구를 실행한다. 기존 8000/5173 서버는 중단하지 않는다.

```powershell
# 프로젝트 루트: 백엔드
$env:BUS_DATA_MODE='static'
$env:BUS_DATABASE_URL='sqlite:///:memory:'
backend/.venv/Scripts/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

```powershell
# frontend 폴더
$env:BUS_API_TARGET='http://127.0.0.1:8001'
npm run dev -- --port 5174
```

```powershell
# 프로젝트 루트
backend/.venv/Scripts/python -m backend.tools.verify_cheonan --base-url http://127.0.0.1:5174 --output docs/cheonan-verification-results.json
```

## 이번 작업의 수정 파일

| 파트 | 파일 |
|---|---|
| API·경로 | `backend/api/routes.py`, `backend/services/cheonan_routing.py`, `backend/services/journeys.py` |
| 목적지 | `backend/services/catalog.py`, `backend/services/places.py` |
| 공식 교통·수집 | `backend/integrations/cheonan_live.py`, `backend/scripts/refresh_cheonan_transport.py` |
| AI | `backend/services/ai.py` |
| 프론트 | `frontend/src/app/App.tsx`, `App.module.css`, `features/route-search/RouteCards.tsx`, `shared/api/types.ts`, `shared/api/format.ts` |
| 자동 테스트 | `backend/tests/test_cheonan_places.py`, `test_cheonan_routing.py`, `test_cheonan_live.py`(신규), `test_cheonan_responsiveness.py`(신규), `test_stage6.py`, `frontend/src/app/App.test.tsx` |
| HTTP 검증 | `backend/tools/verify_cheonan.py`(신규), `docs/cheonan-verification-results.json`(신규) |
| 문서 | `README.md`, `backend/README.md`, `frontend/README.md`, `docs/cheonan-routing-update.md` |

기존 `shared/data/cheonan-{origin,places,transport,walks}.json`, DB 모델·스키마, 프론트 API 클라이언트·키오스크 출발지 설정을 재사용했다. 이번 작업에서 참조 좌표/노선을 임의 생성하거나 DB 스키마를 바꾸지 않았다.

## 미구현 기능과 필요한 외부 자료

1. **대기 포함 최단시간·출발시각 기반 환승 보장**: 운행일 달력·정류장별 출발 시간표·신뢰 가능한 실시간 원천 시각과 지연 예측이 필요하다. 단순 도착값으로 미래 환승을 만들지 않았다.
2. **천안 전역 임의 신규 장소 검색**: 현재 검증된 26곳만 검색한다. 장소 API의 사용자 발급 키·이용 범위와 신규 시설의 보행 연결 자료가 필요하다. 키 없는 서비스를 무제한 자동완성 API로 사용하지 않았다.
3. **2회 이상 환승·전체 보행망**: 현재 직통/1회 환승·확보된 접근 정류장 후보로 제한한다. 광역 후보와 시간표 처리 확장이 필요하다.
4. **현재 운행·막차·결행/우회**: 정적 그래프만으로 판정할 수 없어 미확인을 명시한다. 원천 누락 노선은 데이터의 `failedRouteIds`에 기록돼 있다. 공개 BIS 웹 조회는 인증 OpenAPI 계약이나 가용성 보장이 아니며 실패·형식 변경은 확인 불가다. TAGO·ODsay 인증/유료 API를 연결했다고 표시하지 않는다.
5. **현장 접근성·장비**: 실제 출입구, 계단·휠체어 접근성, 스피커·프린터 현장 검증이 남아 있다. 보행시간은 4km/h 모델 추정치다.

현재 구현은 공식 자료에 존재하는 경로 구조를 비교한다. 당일 운행과 대기 포함 도착이 보장되는 여행계획 기능은 외부 자료 확보 후 추가해야 한다.
