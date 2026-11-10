# 천안 위치·교통 참조 데이터

- `cheonan-origin.json`: 고정 출발지. 종합터미널, BIS `285000686`, ARS `686`. 천안시 공식 정류장 응답의 위도 `36.8190148`, 경도 `127.1565574`. 소재 도로는 천안시 동남구 만남로, 천안종합버스터미널 앞이다. 도로 위 시설이므로 인접 터미널 건물 주소와 정류장 주소를 구분한다.
- `cheonan-places.json`: 기존 17개 시설과 추가 9개 시설. 시설 주소 근거와 좌표 원본 링크를 분리해 저장한다. 좌표는 시설 대표점이며 출입구와 다를 수 있다. 두 터미널은 같은 단지 안의 다른 시설이다.
- `cheonan-transport.json`: [천안시 교통정보센터](https://its.cheonan.go.kr/bis/route.do)의 공개 응답에서 수집한 333개 방향별 노선, 3,436개 정류장, 정류장 순서, 노선 선형. `retrievedAt`은 수집 시각이다. 원천 갱신 시각·개별 운행일 달력·구간별 시간표는 제공되지 않았다. 필수 정류장 정보가 누락된 3개 노선은 `failedRouteIds`로 기록하고 제외했다.
- `cheonan-walks.json`: [Valhalla/FOSSGIS](https://valhalla.openstreetmap.de/)의 **pedestrian** 경로 행렬로 계산한 연결. 26개 시설마다 가까운 정류장 후보 4곳의 실제 보행망 연결을 저장했다. 접근 후보 검색 반경 1.5km, 승인 보행거리 상한 2.5km. 출발지 주변 정류장은 반경 350m 안에서 최대 8곳, 승인 보행거리 600m 이하이다. 출발지에서 직선 5km 안의 21개 시설에는 직접 보행거리도 있다. 보행시간은 4km/h 설정에 따른 추정치이다. 자동차 경로나 직선거리를 보행거리로 사용하지 않는다.

시설 좌표·보행망: **© [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)**, [ODbL](https://opendatacommons.org/licenses/odbl/1-0/). 일부 시장 좌표: [전국전통시장표준데이터](https://www.data.go.kr/data/15012894/standard.do). OSM에 기반한 좌표·보행 데이터는 원본 객체 링크와 함께 제공한다.

공식 BIS 자료는 공개 웹 화면의 조회 엔드포인트를 사용한다. 인증키가 필요한 TAGO OpenAPI를 연결한 것으로 표시하지 않는다. 응답 형식이나 공개 범위가 변경될 수 있어 수집 스크립트는 자동 주기 실행하지 않는다. 정적 자료만으로 현재 운행·막차·휴일 운행을 보장하지 않는다.

수동 갱신은 프로젝트 루트에서 다음 순서로 실행한다. 외부 조회 원본은 `backend/.local`에 캐시된다. 재수집하려면 원하는 캐시를 먼저 검토하고 정리해야 한다. 기존 캐시가 있으면 이를 재사용하며, 새 수집 시각이 원천 자료 갱신을 뜻하지 않는다.

```powershell
backend/.venv/Scripts/python.exe backend/scripts/refresh_cheonan_transport.py
backend/.venv/Scripts/python.exe backend/scripts/update_place_coordinates.py
backend/.venv/Scripts/python.exe backend/scripts/refresh_cheonan_walks.py
```

시설 좌표 매핑 스크립트는 검토한 OSM 객체 원본 파일을 필요로 한다. 실행 시 새 좌표를 추정하거나 지오코딩하지 않는다. 해당 원본을 다시 확보하지 않은 환경에서는 기존 시설 JSON을 유지한다. 갱신 후 서버를 다시 실행하고 전체 장소 통합 테스트를 수행한다.
