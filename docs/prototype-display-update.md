# 프로토타입 시간·도착 및 보행거리 표시 변경

2026-11-10 사용자 후속 요청에 따라 적용했다. 기존 경로 자료 안내 상자는 제거한 상태를 유지한다.

- `frontend/config/kiosk.ts`의 `PROTOTYPE_TIMES_ENABLED=true`: `static` 모드에서 화면용 시간·도착 값을 사용한다. 실제 `live` 모드와 백엔드 API 사실 데이터는 바꾸지 않는다.
- 승차별 대기는 경로 ID·구간 순번으로 정한 3~7분이다. 재렌더링·정렬·재조회에도 같은 값이다. 총시간은 이동 추정시간과 모든 버스의 대기시간 합계다. 순수 도보에는 버스 대기가 없다.
- 카드의 첫 버스 도착값과 상세 도착 안내는 같은 값을 사용한다. 환승 버스는 환승 정류장 도착 후의 대기로 표현한다. 화면의 작은 시연 배지로 구분한다.
- 장소 화면의 기본 정렬과 표시를 지도상의 보행 경로 거리로 변경했다. 이름순으로 바꿔도 거리 표시는 보행거리다. API의 직선거리 필드는 내부 호환·근접 후보 검색용으로 유지하며 화면에는 표시하지 않는다.
- 기존 pedestrian 경로 21곳에 더해 천안의료원 5,865m, 서북구청 7,733m, 병천시장 17,749m, 한국기술교육대학교 16,801m, 독립기념관 10,618m를 Valhalla/FOSSGIS에 실제 조회했다. 26곳 모두 직접 보행 경로가 있다. 추가 조회 시각은 각 자료의 `directWalkRetrievedAt`이다.
- 사용자가 거리 계산 실패 시 임의값을 허용하여, 실제 보행거리가 없는 경우에만 화면에서 직선거리×1.3을 10m 단위로 반올림한 시연 추정치를 사용한다. 기준 거리마저 없으면 1,500m다. 이 경우 `walkingDistanceBasis=prototype_estimate`, ‘도보 약’으로 구분하고 추정치를 포함한 실제 표시 거리로 재정렬한다. 등록된 26곳에는 이 대체값이 현재 필요 없다.
- 추가 보행거리 수집 재현: `backend/.venv/Scripts/python backend/scripts/refresh_cheonan_walks.py --complete-direct`. 기존 버스 접근 연결은 유지한다. 누락·음수·NaN 등 잘못된 응답은 실제 측정값으로 승인하지 않는다.

수정 영역: `frontend/config/kiosk.ts`, `src/shared/prototypeTiming.ts`, `src/shared/places.ts`, `src/shared/api/types.ts`, `src/features/route-search/RouteCards.tsx`, `src/app/App.tsx`, `App.module.css`, 관련 프론트 테스트, `backend/scripts/refresh_cheonan_walks.py`, `backend/tests/test_cheonan_places.py`, `shared/data/cheonan-walks.json`.

백엔드 실제 장소·노선 회귀 28개, 프론트 8파일·63개 테스트 통과. 타입 검사·프로덕션 빌드·diff 검사 통과. 실제 사이트 `/api` 프록시에서 26곳의 보행거리와 정렬을 확인했다. 브라우저에서 천안의료원 도보 5.9km, 383번 경로 이동21분+대기6분=총27분, 카드와 상세의 6분 도착값 일치를 확인했다.

이 문서는 이전 보고서의 직선거리 기본 표시 및 시연 시간 미표시 설명을 대체한다. 시연값을 실제 교통 API에서 관측한 값으로 저장하거나 반환하지 않는다.
