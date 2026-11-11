# 종합터미널 685번 방향별 경로 검증

2026-11-11 [천안시 교통정보센터 정류장 조회](https://its.cheonan.go.kr/bis/busStop.do)와 [685번 정차 노선 조회](https://its.cheonan.go.kr/bis/getTransitRouteList.do?stopId=285000685)를 대조했다. 정류장 685번(`285000685`, 36.8187607, 127.1556582)과 686번(`285000686`, 36.8190148, 127.1565574)은 이름이 같고 ID와 좌표가 다르다. 공식 685번 정차 노선 31개의 방향별 ID 집합 및 정차 순서와, 아래 직통 7개의 지도 선형이 저장된 자료와 일치했다.

| 685번에서 바로 탈 수 있는 노선 | 단국대학교병원 하차 정류장 | 승차 후 이동 정류장 수 |
|---|---|---:|
| [13](https://its.cheonan.go.kr/bis/getBusStopOnRouteList.do?routeId=285000011), [20](https://its.cheonan.go.kr/bis/getBusStopOnRouteList.do?routeId=285000017), [192](https://its.cheonan.go.kr/bis/getBusStopOnRouteList.do?routeId=285000399) | 1715번 | 5 |
| [221](https://its.cheonan.go.kr/bis/getBusStopOnRouteList.do?routeId=285000108) | 639번 | 5 |
| [121](https://its.cheonan.go.kr/bis/getBusStopOnRouteList.do?routeId=285000081), [200](https://its.cheonan.go.kr/bis/getBusStopOnRouteList.do?routeId=285000104), [201](https://its.cheonan.go.kr/bis/getBusStopOnRouteList.do?routeId=285000106) | 639번 | 6 |

5정거장 경로는 종합터미널 685 → 나은필병원(대림한숲아파트) → 천안톨게이트 → 상명대학교 → 단국대치대병원 → 단국대학교병원 순이다. 6정거장 경로는 나은필병원 다음에 도솔광장에 정차한다. [반대 방향 13번](https://its.cheonan.go.kr/bis/getBusStopOnRouteList.do?routeId=285000010)은 병원에서 종합터미널 686번으로 운행한다.

첫 승차는 685번에서만 가능하다. 모든 버스 구간은 같은 방향별 노선 ID의 정차 순서를 따라가며, 환승은 두 노선이 같은 정류장 ID에 정차할 때 최대 한 번 허용한다. 둘 중 어느 한 버스를 685번에서 바로 타고 같은 곳에 내릴 수 있는 경우 불필요한 환승을 제외한다. 방향 표시는 실제 정차 순서의 종점(출발과 이름이 같으면 다음 정류장)에서 가져온다. 백엔드가 확정한 순서와 노선 선형을 상세와 지도에 사용하고, 음성·도착·인쇄는 같은 경로 버전을 검증한다.

거리는 BIS 선형 중 실제 승하차 구간과 Valhalla 보행망에서 계산한다. 버스 이동시간은 BIS의 노선 전체 평균시간을 해당 구간 거리 비율로 환산한다. 개별 구간 실측값이나 당일 운행 시간표가 아니며, 대기는 포함하지 않는다. 근거가 없는 이동시간이나 도착 예정값은 표시하지 않는다.

로컬 Vite → FastAPI에서 네 정렬 기준을 비교한 결과, 201번은 639번에 6정거장 후 도착하며 최종 도보를 포함해 약 11분, 192번은 1715번에 5정거장 후 도착하며 약 15분으로 계산됐다. 서북구청 검색에서는 442번 → 30번이 동일한 526번 정류장에서 환승했다. 686번 요청 거부 및 상세·도착·음성·인쇄 스냅샷 일치를 확인했고, 브라우저에서 정차 목록과 지도 화살표, 인쇄 안내표를 대조했다. 백엔드·AI 418개, 프론트 67개 테스트와 프로덕션 빌드를 통과했다.
