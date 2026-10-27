# 공통 영역 반영 제안 · 직접 수정 없음

확인 기준은 사용자 구현 요청, HWP 전체 본문(`source-plan.txt`), 실제 저장소 공통 문서다. HWP의 과거 '계획서 작성만' 범위·발표/커밋/PR 지시는 이번 구현 요청에 적용하지 않았다. 중요한 기존 API 필드·ID 충돌은 발견되지 않았다. 저장소에 없는 미정값은 이번 명시적 요청과 HWP의 구현 세부안으로 구체화했다.

| 대상 / 담당 | 관찰·변경 이유 | 제안 / 영향 |
| --- | --- | --- |
| `docs/development-plan.md` / 공통 관리자 | 현재 파일이 없으며 HWP가 참조한 확정 합성 원본도 저장소에 없음 | 생성 전 팀 확인 필요. 이번 요청의 5/2/3 수량, HWP의 6개 경유·003 환승, 기존 병원 ID/이름을 유지해 `backend/integrations/demo-data.json`으로 구체화함. 시장·터미널 ID/별칭과 미지정 정류장 이름은 이 파일을 A/B/AI와 공유할 것 |
| `README.md`, `docs/structure.md` / 공통 관리자 | 현재 '실행 코드·스택 미정'이라는 초기 상태 설명 | 백엔드 독립 구현 상태·파일 구조·실행 문서 링크를 반영 제안. 해당 원본은 수정하지 않음 |
| `.gitignore` / 공통 관리자 | HWP와 달리 루트 규칙에는 `.local/` 제외가 없음 | 백엔드 내부 `.gitignore`로 `.local/`, `.test-tmp/` 제외 완료. 공통 파일 변경 불필요 |
| `docs/api-contract.md` / 백엔드 + A/B/AI | 입력 길이·유효기간·최신성·AI 제한이 현재 미정 | 이번 요청의 100자/200자/120초/600초/90초/1초를 공통 문서에 반영 제안. `SearchData.expiresAt`, `PrintData.guidance`는 HWP/요청에 필요한 추가 응답 필드로 제공하며 기존 필드는 보존 |
| `docs/api-contract.md` / 백엔드 + B | unavailable 전용 서비스 code 미정, 기존 표에는 409 ROUTE_VERSION_CHANGED만 존재 | 별도 새 코드 도입 없이 현재 409 코드를 사용. 구체 사유는 재선택 메시지로 전달. 상세/live/안내/인쇄 동일 우선순위 적용 |
| `docs/api-contract.md` / B | print liveInfoSnapshot 구조에 ETA가 있으나 요청은 카운트다운 제외 | 구조는 유지하고 print의 etaSeconds를 null로 반환. absolute expectedArrivalAt·출처 시각 유지. `guidance`의 검증된 고정 문구도 같은 버전으로 사용 |
| `ai/contracts/`, `ai/destination-interpretation/`, `ai/easy-guidance/` / AI | 현재 temp만 있어 공개 Python 함수 없음 | backend AIAdapter에 interpret_destination(dict), choose_guidance(dict) 제공 필요. 공통 JSON 논리 계약을 그대로 사용. 하이픈 폴더 개명·AI 모듈 대리 구현 없음. transfer.basic 표현은 AI/디자인의 검토 필요 |
| `frontend/config/`, `frontend/src/shared/api/` / A | 실제 프록시·클라이언트 미구현 | 5173 → 8000의 /api 프록시와 5초 제한, GET 일시 실패/5xx 1초 후 1회 재시도, POST/4xx 무재시도 구현 필요. 백엔드 CORS는 로컬 두 origin만 허용 |
| `frontend/src/features/` / A/B | 검색·상세·인쇄·음성 UI 없음 | 6개 선택 필드와 실제 JSON 예시 제공. 폴링 30초·이탈 중지, 409 재검색·410 재검색, unknown/stale 표시와 시연 문구 구현·공동 검증 대기 |
| `docs/data-sources.md` / 백엔드 | 실제 API·지원 범위·키·라이선스 계속 미확인 | 상태 갱신할 외부 증거 없음. live는 503, demo 값 혼입 없음 |
| `docs/verification.md` / 공통 관리자 | 최초 구조 검증 기록임 | 원문 유지. 이번 기능 검증은 backend/docs/implementation-status.md와 테스트 출력에 별도 기록 |

현재 계약상 부분 실패를 보존한다. 도착 unavailable을 not_running으로 바꾸지 않고, 변경 조회 실패는 coverageStatus=unknown이다. ready 경로의 미수신 인쇄는 경고를 붙여 허용한다. 초기 시연은 단방향·동일 정류장 명시 환승만 지원하며, 서로 다른 정류장 사이 환승을 지원하려면 별도 검증 도보 연결 자료와 계약 검토가 필요하다.

공동 검증 담당/우선순위: A/B 실제 화면 연결 및 재검색 처리 P1, AI 공개 모듈/동일 Python 환경 P1, B·디자인 음성/인쇄 레이아웃 P1, 전원 다른 PC 재현 P1. 실제 교통 제공자 선정·현장 장비는 후속 범위다.

## 2026-10-27 · v2 계획서 2단계 인수인계

합성 원본의 ID·이름·별칭·분류·순번·연결은 이번 작업에서 변경하지 않았다. 테이블/외부 API 필드 변경도 없다. 내부 seed 명령 출력만 실제 수량 JSON(inserted/totals)으로 개선했다.

- A/B: `backend/docs/stage2-handoff-examples.json`에 정류장·목적지(이름·별칭·분류), 정상/빈 결과/400/404, 터미널 환승 경로의 실제 API 응답을 준비했다. `departAt`은 요청 시 현재 aware ISO 시각을 생성한다. 응답 기록의 검색 ID는 재사용하지 않는다.
- AI: 같은 파일의 aiInputContract에 등록 후보 목록과 interpret_destination(payload), choose_guidance(payload), 구간별 허용 templateId를 정리했다. ai 폴더는 여전히 자리 표시자뿐이므로 실제 함수·후보 계약의 공동 확인은 대기다. 실제 AI가 연결된 것으로 표시하지 않는다.
- 공통 관리자: `backend/docs/database-schema.md`에 PK/FK/nullable/복합키·합성 접근/환승 관계를 정리했다. 공통 docs/development-plan.md의 부재·초기 상태 설명 갱신 제안은 기존과 같다. 이번에는 공통 파일을 수정하지 않았다.

자료를 프로젝트 안에 준비했으며 다른 담당자에게 메시지 전송·리뷰 요청을 실행한 것은 아니다. 실제 교통 출처·키·지역/필드 지원 범위도 여전히 미확인이다.

## 2026-10-27 · v2 계획서 3단계 인수인계

정류장 조회·목적지 검색의 URL·공통 데이터·오류 코드·출력 필드는 변경하지 않았다. 목적지 조회 조건을 backend/models/schemas.py의 DestinationQuery로 정리했으며 생성 OpenAPI도 기존 명세와 동일하다.

- A: `backend/docs/stage3-integration.md`에 입력 규칙·상태별 처리·8000/5173·접두사를 유지하는 /api 프록시 기준을 정리했다. `stage3-http-examples.json`에는 실제 Uvicorn HTTP 21개 사례가 있다.
- 프론트 설정 대상은 `frontend/config/`와 `frontend/src/shared/api/`다. 로컬 두 origin의 CORS는 백엔드에서 검증했다. 프록시 구성·5초 클라이언트 제한·GET 재시도·로딩/빈 결과/400/404/시연 표시는 A의 구현·공동 확인이 필요하며 해당 파일을 직접 수정하지 않았다.
- `category` 선택이 없으면 파라미터를 생략한다. query만 공백 제거 후 최대 100자이며 `category=`는 입력 오류다. 검색 응답은 등록 목록이고 경로 이용 가능성은 후속 경로 검색 결과를 기준으로 한다.
- 실제 A 화면은 아직 없으므로 시작 정류장 표시 → 주요 장소/별칭 검색 → 오류 표시의 브라우저 검증은 대기다. HTTP 성공을 프론트 연동 완료로 표시하지 않는다.

타 담당자에게 메시지 전송이나 원격 리뷰 요청을 실행하지 않았다. 공통 문서·프론트 원본은 모두 보존했다.
