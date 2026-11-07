# 프론트엔드 B · 상세 이동 안내

B는 A가 선택한 경로를 받아 상세 이동 순서, 버스 도착·운행 정보, 80mm 인쇄 안내표, 음성 안내를 제공한다. 목적지 검색·확인과 경로 선택은 A의 영역이다.

## 화면과 인쇄 디자인

웹 화면은 feat/frontend-search의 공통 기준(흰 배경, 본문 24px, 최대 폭 760px, 버튼 높이 64px 이상, 모서리 8px, 파란 키보드 초점)에 맞췄다. 상단은 '3단계 · 이동 안내', 본문은 버스·환승·도보 순서와 실시간·인쇄·음성 기능이다. 개발용 경로 선택 버튼, API 연결 설명, 식별자·버전, 서버 응답 시각은 표시하지 않는다. 실시간 정보의 원천 갱신/서버 수집 시각은 '정보 확인 시각 보기'에 모았다. 오래됨·확인 불가는 접지 않고 표시한다.

PrintPaper는 웹 카드나 음성 원고를 재사용하지 않는다. design/guidelines/Print Guide 및 직통·환승 JPG에 맞춰 버스 길안내 로고 → 목적지 → 승차 위치 → 테두리의 버스 번호 → 이동 정류장 수 → 회색 하차 위치 → 출력 시각·주의 문구를 렌더링한다. 환승 시 연결 문구와 다음 버스/하차를 반복한다. 마지막 도보는 한 문단으로 남긴다. 중복된 음성 안내 원고와 상세 실시간 패널은 종이에서 제거했다.

용지 폭 80mm, 기본 길이 180mm, 좌우 6mm·상하 8mm 여백이며 긴 정류장명/환승/필수 주의 문구에 따라 길어진다. 인쇄 전용 글자 크기는 시안 기준 8/10/17/19/25pt다. Pretendard가 설치되어 있으면 사용하고 없으면 맑은 고딕으로 표시한다. 출력 시각에는 안내표 스냅샷 생성 시각을 쓰며 물리 출력 완료를 뜻하지 않는다. 경로 원천 갱신 시각은 별도로 표시한다. 일부 운행 정보의 확인 불가/오래됨과 실제 운행 변경이 있으면 짧은 하단 문구를 추가한다.

시연 표시는 화면에서 공통 셸이 한 번, 종이에서 별도로 한 번 표시한다. API에 없는 운행 방향·직전 정류장·맞은편 여부는 만들지 않는다. 서버가 제공한 정류장명·버스 번호를 시안의 가상 예시로 바꾸지 않는다.

## 기능과 API 검증

- 상세: 선택 식별자·버전·모드·구간을 검사한다. 거리/시간 null은 임의의 숫자로 채우지 않는다.
- 실시간: 도착 예정, 운행 상태, 운행 변경을 구분한다. 도착 정보 미수신을 결행으로, 변경 조회 실패를 변경 없음으로 표시하지 않는다.
- 조회: 상세 진입 후 30초 간격으로 조회하고 중복 요청을 막는다. 화면 숨김/이탈 시 취소·중단하고 복귀 시 즉시 갱신한다. 요청 제한은 5초, GET 연결 실패/5xx만 1초 뒤 한 번 재시도한다. POST/4xx는 자동 재시도하지 않는다.
- 인쇄: POST /print-guides의 같은 버전 스냅샷만 사용한다. 서버의 전체 스냅샷 검증은 유지하며 종이에 도착 카운트다운을 넣지 않는다. 인쇄 직전 상세를 재조회하여 만료·변경 시 중단한다. 별도 iframe 문서만 인쇄하고 물리 출력 성공을 판정하지 않는다.
- 음성: POST /easy-guidance의 같은 버전·구간 순서와 시연 표시를 검증한다. 한국어 재생·중지와 글 안내 대체를 제공한다. 숨김·경로 변경·인쇄 미리보기 진입·이탈 시 중지한다.

## A에서 연결하기

JourneyGuideScreen의 selection과 onReselect를 전달한다.

```tsx
<JourneyGuideScreen
  selection={state.routeSelection}
  onReselect={() => dispatch({ type: 'back-to-search' })}
/>
```

selection은 originStationId, destinationId, routeSearchId, routeOptionId, routeSnapshotVersion, dataMode 6개 필드다. A의 RouteSelection 타입과 구조가 일치한다. 컴포넌트는 main 영역과 '다른 경로 찾기' 버튼을 제공한다. 부모 앱은 폭 760px의 공통 셸과 dataMode에 맞는 시연 알림을 담당한다. A의 공통 CSS가 있는 환경에서도 동작하며 JourneyGuidePreview에 의존하지 않는다.

변경(409), 만료(410), 식별자 누락은 재선택하도록 안내한다. 핵심 자료 실패(503)는 안내·음성·인쇄를 중단하고 재시도한다. 일부 도착 데이터만 없는 200 응답은 경로를 유지한다. 선택 변경/화면 이탈 때 이전 응답이 새 화면을 덮지 않는다.

A의 소스·공통 폴더·백엔드는 수정하지 않았다. 공통 API 클라이언트 병합 및 package.json/lockfile 통일은 A와 최종 통합할 때 처리할 항목이다. 현재 B의 journeyApi.ts와 검증된 TypeScript ~6.0.2 설정을 유지한다.

## 단독 실행과 검증

현재 App의 JourneyGuidePreview는 B 단독 미리보기다. 기본적으로 실제 로컬 백엔드에 합성 환승 경로를 검색해 표시한다. 개발 메뉴는 화면에 없으며, 직통 확인은 http://localhost:5173/?journey=direct 에서 가능하다. 이 자동 검색은 실제 A → B 연결에서 사용하지 않는다.

프로젝트 루트에서 백엔드를 실행한다.

```powershell
backend/.venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

frontend 폴더에서:

```powershell
npm run dev
npm run build
npm run lint
$env:BUS_API_SMOKE='1'
node --test tests/journeyApi.test.mjs tests/b-features.test.mjs
```

브라우저 검사는 node tools/check-b-browser.mjs 이다. 기존 Playwright 설치가 필요하다. BUS_PLAYWRIGHT_PATH에 index.mjs, 필요하면 BUS_CHROME_PATH에 Chrome 경로를 지정한다. 개인 브라우저와 분리된 임시 프로필을 사용하며 결과·스크린샷·인쇄 HTML/PDF는 Git 제외 폴더 qa.local에 저장한다. PDF 검사는 pypdf가 있는 Python으로 python tools/check-print-pdf.py 를 실행한다.

자동 검사에서는 음성 엔진과 인쇄 대화상자를 모의한다. 실제 한국어 발음·음량과 80mm 감열 프린터의 출력·여백·긴 용지·커팅은 장비에서 확인해야 한다. 프린터는 80mm, 배율 100%, 브라우저 머리글/바닥글 끄기로 확인한다. 이 설정 설명은 사용자 화면의 개발 안내로 노출하지 않는다.