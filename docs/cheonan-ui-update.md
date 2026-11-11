> 이 문서는 이전 UI·시설 목록 단계의 기록이다. 이후 실제 위치·노선 자료가 연결되었다. 현재 기능과 검증은 [최신 경로 구현 보고](cheonan-routing-update.md)를 따른다.

# 천안 지역 장소·UI 개선 보고

작성일: 2026-11-10 (Asia/Seoul). 기존 Figma 배치와 React/CSS Modules 화면을 유지한 개선이다.

## 구현 검토와 변경 범위

- API 8개의 경로·요청·응답 형식, SQLite 테이블·제약, 경로 탐색·버전 검증·AI 규칙은 유지했다.
- `shared/data/cheonan-places.json`을 시설의 단일 원본으로 추가했다. 서버는 이름·ID·분류·별칭을 기존 테이블에 누락분만 등록하며, 프론트엔드는 같은 ID로 주소·위치 설명·출처를 보강한다.
- 기본 ASGI 앱은 천안 목록을 사용한다. 회귀 검증용 `create_app()` 기본 legacy 목록은 유지했고 `place_catalog="cheonan"`으로 같은 지역 목록을 명시할 수 있다. 관공서는 기존 API·DB의 `other`를 사용하므로 카테고리 마이그레이션이 없다.
- 기존 행을 삭제·덮어쓰기하지 않는다. 기존 실험용 정류장·노선·DestinationAccess·환승 연결을 실제 시설에 연결하지 않았다. 사용자 PC 기존 bus.sqlite3·공용 시나리오 대신 실행 중인 미리보기 서버는 메모리 DB를 사용한다.
- 화면의 반복 시연 표시를 제거하고 표시용 변환에서 접두어를 정리했다. 원본 API의 dataMode·notice·스냅샷·ID를 사실 데이터로 승격하거나 변경하지 않는다. 음성과 인쇄에도 같은 표시 정책을 적용한다.

## 등록 장소 17곳

| ID | 이름 | 분류 | 확인 주소 | 근거 |
| --- | --- | --- | --- | --- |
| cheonan-dankook-hospital | 단국대학교병원 | 병원 | 충청남도 천안시 동남구 망향로 201 | [천안의료원 협력병원 현황](https://camc.or.kr/refer/content/450) |
| cheonan-soonchunhyang-hospital | 순천향대학교 부속 천안병원 | 병원 | 충청남도 천안시 동남구 순천향6길 31 | [순천향대학교 부속 천안병원](https://www.schmc.ac.kr/cheonan/index.do) |
| cheonan-medical-center | 충청남도천안의료원 | 병원 | 충청남도 천안시 동남구 충절로 537 | [충청남도천안의료원](https://camc.or.kr/) |
| cheonan-chungmu-hospital | 천안충무병원 | 병원 | 충청남도 천안시 서북구 다가말3길 8 | [천안충무병원 오시는 길](https://www.cmhos.co.kr/cmhos/guide/map.asp) |
| cheonan-bus-terminal | 천안종합버스터미널 | 터미널 | 충청남도 천안시 동남구 만남로 43 | [천안종합터미널 운영사](https://www.cheonanterminal.co.kr/) |
| cheonan-express-terminal | 천안고속버스터미널 | 터미널 | 충청남도 천안시 동남구 만남로 43 | [천안종합터미널 운영사](https://www.cheonanterminal.co.kr/) |
| cheonan-station | 천안역 | 역 | 충청남도 천안시 동남구 대흥로 239 | [국가철도공단 천안역사 사업 안내](https://www.kr.or.kr/boardCnts/view.do?boardID=51&boardSeq=1111707&page=79) |
| cheonan-dujeong-station | 두정역 | 역 | 충청남도 천안시 서북구 두정로 289 | [네이버 지도 역정보](https://pts.map.naver.com/end-subway/ends/web/1407/home) |
| cheonan-bongmyeong-station | 봉명역 | 역 | 충청남도 천안시 동남구 차돌로 51 | [천안시 봉명역 입구 위치 안내](https://parking.cheonan.go.kr/vinf/vinf_cctv.jsp) |
| cheonan-city-hall | 천안시청 | 관공서 | 충청남도 천안시 서북구 번영로 156 | [공유누리 천안시청 위치](https://www.eshare.go.kr/UserPortal/Upv/UprResrcExpr/index.do?rsrc_no=BA10A0015155) |
| cheonan-dongnam-district-office | 천안시 동남구청 | 관공서 | 충청남도 천안시 동남구 옛시청길 39 | [천안시 청사·부서 안내](https://parking.cheonan.go.kr/pofl/pofl_info.jsp) |
| cheonan-seobuk-district-office | 천안시 서북구청 | 관공서 | 충청남도 천안시 서북구 성거읍 봉주로 75 | [천안시 청사·부서 안내](https://parking.cheonan.go.kr/pofl/pofl_info.jsp) |
| cheonan-tax-office | 천안세무서 | 관공서 | 충청남도 천안시 동남구 청수14로 80 | [국세청 천안세무서 찾아오시는 길](https://d.nts.go.kr/cheonan/ad/tsm/lcInfo.do?mi=4627) |
| cheonan-national-pension-office | 국민연금공단 천안지사 | 관공서 | 충청남도 천안시 동남구 청수6로 60 | [국민연금공단 천안지사 찾아오시는 길](https://www.nps.or.kr/pbcpgdnc/ognzprsn/getOHAG0016M0List.do?brofCd=5111) |
| cheonan-central-market | 천안중앙시장 | 시장 | 충청남도 천안시 동남구 사직로 7 | [충청남도 관광 천안중앙시장](https://tour.chungnam.go.kr/prog/trsrcn/kor/sub02_01_02/view.do?trsrcnNo=1377) |
| cheonan-seongjeong-market | 성정시장 | 시장 | 충청남도 천안시 서북구 양지21길 31 | [전국전통시장표준데이터](https://www.data.go.kr/data/15012894/standard.do) |
| cheonan-byeongcheon-market | 병천시장 | 시장 | 충청남도 천안시 동남구 병천면 아우내장터1길 46 | [전국전통시장표준데이터](https://www.data.go.kr/data/15012894/standard.do) |

종합터미널과 고속터미널은 같은 만남로 43 단지에 속한다. 같은 complexId로 묶고, 종합 단지/시외 시설 안내와 백화점 왼편 고속 전용 별도 건물 안내를 구분했다. 별도 시외터미널 중복 행은 만들지 않았다. 천안중앙시장과 남산중앙시장은 한 ID와 별칭으로 통합했다.

두정역은 지도 운영사의 역정보와 공공자료 기반 주소를 교차 확인했다. 봉명역은 천안시 공식 입구 위치, 천안역은 국가철도공단 역사 위치 자료를 확인했다. 단국대학교병원은 공식 브랜드명을 사용하고 등록명 단국대학교의과대학부속병원을 별칭으로 저장했다. 천안의료원은 공식 표기 충청남도천안의료원을 기본명으로 두고 띄어 쓴 이름도 검색된다.

좌표가 검증되지 않은 시설은 null이다. 성정시장·병천시장의 좌표는 전국전통시장표준데이터의 시설 대표점이며 승강장이나 출입구 좌표로 쓰지 않는다. 중앙시장은 관광 대표주소와 상인회 주소가 달라 대표주소에 상인회 좌표를 붙이지 않았다. 자세한 시장·공공기관 검증은 [조사 기록](research/cheonan-public-markets.md)을 참조한다.

## 검색과 선택 연결

1. 카테고리 버튼은 기존 GET /api/v1/destinations를 호출한다. 관공서만 기존 category=other를 사용한다.
2. 공백을 제외한 정식 명칭과 등록 별칭으로 검색할 수 있다. 자연어 해석도 같은 등록 ID만 반환한다.
3. 선택 즉시 활성 상태를 보존하고 기존 POST /api/v1/route-searches에 동일한 destinationId를 전달한다. 결과 화면에 선택 시설·주소·위치 설명·출처 링크를 표시한다.
4. 실제 버스 연결 근거가 없으므로 신규 시설은 routeOptions=[]를 반환한다. 화면은 경로 정보 연결 전 상태와 다시 검색 기능을 표시한다. 기존 합성 노선/정류장·ETA를 실제 장소의 운행 정보처럼 붙이지 않는다. 실제 노선·도착시간·이동시간 연결은 미완료이며 검증된 교통 자료가 필요하다.

## 버튼 상호작용

- 모든 button·button형 input·role=button·링크에 공통 누름 상태를 적용했다. 누름 즉시 filter:brightness(.84), 유지 중 어두운 상태, 해제 후 120ms 복귀다. 기본 모드·고대비 팔레트·크기·간격은 보존한다.
- 선택 aria-pressed와 순간 data-pressed를 분리한다. 카테고리·목적지·경로 선택은 활성 스타일을 유지하고 다른 항목을 선택하면 이전 선택이 해제된다.
- pointerup이 버튼 바깥에서 발생해도 해제되며 pointercancel·lostpointercapture·스크롤·창 비활성화·포커스 이동·언마운트에서 상태를 정리한다. 터치 이동을 클릭으로 붙잡기 위해 강제 pointer capture를 하지 않는다. Space/Enter와 focus-visible을 지원한다.
- 비활성 버튼은 옅게 표시하고 누름 효과·실행을 막는다. 현재 QR 버튼·QR API가 없어 QR 기능을 새로 만들지는 않았다.

## 검증 결과

- 프론트 자동 테스트: 최종 갱신 예정 (직전 45개 통과).
- 백엔드·AI: **380 passed**, 기존 의존성의 DeprecationWarning 1개. 기존 377개에 천안 실제 장소 통합·기존 자료 보존·중복 검증 3개를 추가했다. 기본 병원 4곳에 맞게 ASGI AI 검증을 구체명 matched/일반명 needs_confirmation으로 갱신했다.
- 기존 8개 API·응답 스키마·DB 테이블·경로 탐색 로직 유지. 신규 실제 장소 17개를 이름 검색/분류 조회하고, 각 선택 ID로 기존 경로 검색이 성공하며 가짜 경로가 생성되지 않는 것을 확인했다.
- 브라우저: 다섯 분류의 4/2/5/3/3개 목록과 주소, 시연 문구 없음, 별칭 단국대병원 검색, 선택 주소·출처·돌아가기 활성 유지, 일반·고대비 배치 확인. 누르는 도중 실제 computed filter=brightness(0.84), 해제 후 filter=none·transition=0.12s를 확인했다.
- 마우스·터치 pointer 이벤트, 다중 터치, 스크롤 취소, 키보드, 비활성 제어, 해제·언마운트는 자동 테스트로 검증했다. 실제 터치 패널 하드웨어의 점검으로 표현하지 않는다.
- 실제 교통 제공자·실물 인쇄·실제 스피커 청취는 이번 UI/장소 작업의 검증 범위가 아니다. 실제 시설의 버스 경로는 아직 연결되지 않았다.

## 변경 파일

- 데이터: shared/data/cheonan-places.json; 조사: docs/research/cheonan-public-markets.md.
- 서버: backend/main.py, backend/api/routes.py, backend/services/catalog.py, 신규 backend/services/places.py; tests/test_cheonan_places.py와 기본 ASGI AI 테스트.
- 화면: frontend/src/app/{App.tsx,App.module.css,state.ts}, shared/{places.ts,api/types.ts,ui/usePressFeedback.ts}, styles.css, config/kiosk.ts, features/print-guide/PrintDocument.tsx.
- 검증: App.test.tsx, PrintDocument.test.tsx, usePressFeedback.test.ts. 문서: 본 보고서와 README의 현재 상태 안내.
