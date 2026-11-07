# 충청남도 스마트 버스정류장 프론트엔드

A와 B가 함께 사용하는 하나의 React/TypeScript 앱이다.

- A: 현재 정류장 → 목적지 검색/확인 → 경로 선택, 공통 앱 상태/UI/API.
- B: 선택한 경로 상세 → 도착·운행 정보 → 80mm 인쇄 안내표 → 한국어 음성 안내.

기본 화면은 A의 시작 화면이다. 경로를 선택하면 같은 식별자·버전·데이터 모드를 B에 전달한다. '다른 경로 찾기'는 검색 화면으로 돌아가며, 새로고침으로 선택이 사라지면 시작 화면부터 진행한다. needs_confirmation은 후보가 하나여도 확인을 거친다.

## 실행

Node 24와 npm을 사용한다. frontend 폴더에서:

```powershell
npm ci
npm run dev
```

기본 주소는 http://localhost:5173/ 이다. 백엔드는 프로젝트 루트에서 실행한다.

```powershell
backend/.venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

서버 주소는 VITE_API_BASE_URL로 변경할 수 있다. 기본값은 http://127.0.0.1:8000 이다. 현재 백엔드는 합성 시연 데이터이며 실제 버스 운행 정보가 아니다.

## 통합 기준

- A의 앱 셸·Context·검색/확인/경로 선택을 유지하고 마지막 임시 연결 화면을 JourneyGuideScreen으로 교체했다.
- 공통 전송 계층은 src/shared/api/http.ts 한 곳이다. A의 client.ts와 B의 journeyApi.ts가 사용하며, B는 경로 식별자·버전·구간 검사와 기존 오류 분기를 유지한다.
- 전달 객체 RouteSelection과 DataMode는 src/shared/api/types.ts를 공유한다. B 화면도 공통 ScreenHeader를 사용한다.
- TypeScript는 기존 B에서 검증한 ~6.0.2로 통일했다. A/B 소스를 함께 빌드하며 package-lock.json과 npm ci로 재현한다.
- 본문 24px·제목 32px·버튼 높이 64px·최대 화면 폭 760px·모서리 8px·파란 키보드 초점을 사용한다.

## 검증

```powershell
npm run build
npm run lint
npm test
# 백엔드가 실행 중이면 실제 API 검사도 포함한다.
$env:BUS_API_SMOKE='1'
npm test
```

브라우저 통합 검사는 node tools/check-b-browser.mjs 로 실행한다. Playwright 설치 경로를 BUS_PLAYWRIGHT_PATH로 지정할 수 있다. A의 실제 선택 흐름을 통해 B로 진입하고 목적지 재선택·상태 오류·30초 조회·음성·인쇄 스냅샷을 확인한다. 결과는 Git 제외 폴더 qa.local에 저장한다.

기능과 장비 확인 사항은 src/features/journey-guide/README.md를 따른다. 자동 검사에서는 음성 엔진과 인쇄 대화상자를 모의하며 실제 스피커·감열 프린터 출력은 별도로 확인한다.