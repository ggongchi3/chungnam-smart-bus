# 2단계 DB·합성 원본 계약

2026-10-27, `backend-development-plan-v2(1).hwp`의 2단계와 5절 기준. 기존 DB를 삭제하거나 새 스키마로 교체하지 않았다. 실제 테이블 정의는 `backend/models/tables.py`, API/AI 입출력은 별도 `backend/models/schemas.py`다. 저장 필드는 snake_case이고 외부 API는 lowerCamelCase다.

| 테이블 | 기본키·고유 조건 | 외래키 | NULL 허용 | 나머지 조건 |
| --- | --- | --- | --- | --- |
| stations | station_id | 없음 | region, coordinates | name, direction_label 필수 |
| destinations | destination_id | 없음 | 없음 | category는 hospital/market/terminal/station/other |
| destination_aliases | (destination_id, alias) | destination_id → destinations | 없음 | 같은 목적지·별칭 조합 중복 거부 |
| routes | route_id | 없음 | 없음 | name, direction_label 필수 |
| route_stops | (route_id, sequence) | route_id → routes, station_id → stations | 없음 | sequence > 0; 같은 정류장 재방문은 다른 순번으로 식별 |
| destination_access | (destination_id, station_id) | 각각 destinations, stations | distance_meters, duration_seconds | 확인된 값은 0 이상, 미확인은 null |
| transfer_connections | (from_route_id, from_sequence, to_route_id, to_sequence) | 두 (route_id, sequence) 조합 → route_stops | 없음 | evidence 필수; 존재하지 않는 순번 거부 |
| route_searches | search_id | origin_station_id → stations, destination_id → destinations | 없음 | created_at/expires_at은 UTC epoch 초; data_mode와 JSON snapshot 저장 |

복합 기본키가 고유 제약 역할도 수행한다. 역방향 노선과 미등록 환승을 자동 추가하지 않는다. 외래키는 `database.py`의 connect 이벤트에서 연결마다 `PRAGMA foreign_keys=ON`으로 활성화한다. 요청 의존성은 `Database.session()`을 사용하며 세션 종료·성공 커밋·실패 롤백을 처리한다. 외래키와 컬럼 정의는 새 DB 및 기존 실행 DB에서 검사했다. 실제 SQLite 인스펙션은 `stage2-verification-20261027.json`의 databaseSchema에 있다.

합성 원본은 `backend/integrations/demo-data.json` 한 곳이다. 정류장 5개, 목적지 3개, 별칭 3개, 단방향 노선 2개, 경유 6개, 목적지 접근 3개, 명시적 환승 1개를 적재한다. ID·이름·별칭·분류는 기존 파일을 변경하지 않고 사용했다.

- demo-route-001: 001 → 002 → 003, 경유 순번 1/2/3.
- demo-route-002: 003 → 004 → 005, 경유 순번 1/2/3.
- 환승: demo-route-001의 3번 → demo-route-002의 1번. 둘 다 demo-stop-003이며 **명시 등록 근거가 있는 합성 연결**이다.
- 목적지: 병원 demo-destination-001 → stop-003, 시장 002 → stop-002, 터미널 003 → stop-005.
- 지역·좌표·도보 거리·소요시간은 미확인으로 null이다.

초기 적재는 하나의 트랜잭션으로 처리한다. 중간 flush는 커밋이 아니므로 마지막 환승 그룹이나 commit 단계에서 오류가 나도 앞선 삽입까지 롤백된다. 기존 행은 덮어쓰지 않으며 새 행만 넣는다. `seed()` 결과는 테이블별 신규 삽입 수와 실제 전체 수량을 반환하고 CLI도 그 값을 JSON으로 출력한다. 수량이 예상과 다를 때 기존 자료를 지우거나 바꾸어 맞추지 않는다. `verify_stage2`는 차이를 실패로 보고한다.

`seed(database, source_path=...)`는 격리 테스트에서 잘못된 원본을 주입하기 위한 선택 인자다. 서버와 CLI는 기본 합성 원본만 사용한다. 실제 운영 DB에는 실패 데이터를 넣지 않았다.

교통 제공 경계는 `backend/integrations/providers.py`의 TransportProvider / DemoProvider이며 시간·운행 상태를 내부 ProviderState로 변환한다. 합성 등록 자료는 seed를 통해 동일 SQLite 모델로 공급된다. 서비스가 특정 외부기관의 URL이나 필드에 의존하지 않는다. 실제 기관·키·지원 범위는 계속 미확인이다.

재현 명령(프로젝트 루트, Windows):

```powershell
backend/.venv/Scripts/python -m backend.seed
backend/.venv/Scripts/python -m backend.seed
backend/.venv/Scripts/python -m backend.tools.verify_stage2
backend/.venv/Scripts/python -m pytest backend/tests/test_stage2.py -q --basetemp=backend/.test-tmp-stage2 -p no:cacheprovider
```

실행 DB와 모든 저널은 `backend/.local/` 아래이며 Git 제외를 확인했다. 테스트는 메모리 DB 및 `.local/tests/`의 독립 DB를 사용한다. 잘못된 적재 원본·실패 주입은 테스트에서만 사용한다. 합성 원본·의존성 잠금·비밀값 없는 `.env.example`은 Git 추적 대상이다.
