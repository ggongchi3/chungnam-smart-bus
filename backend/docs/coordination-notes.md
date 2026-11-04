# 공통 영역 협업 및 인수인계

초기 백엔드 구현의 확인 기준은 사용자 구현 요청, HWP 전체 본문(`source-plan.txt`), 실제 저장소 공통 문서였다. HWP의 과거 '계획서 작성만' 범위·발표/커밋/PR 지시는 해당 구현 요청에 적용하지 않았다. 중요한 기존 API 필드·ID 충돌은 발견되지 않았다. 저장소에 없는 미정값은 당시 명시적 요청과 HWP의 구현 세부안으로 구체화했다. 아래 10월 기록은 당시 인수인계 이력이며, 현재 AI 연결과 계약 결정은 마지막 2026-11-02 절을 기준으로 한다.

| 대상 / 담당 | 관찰·변경 이유 | 제안 / 영향 |
| --- | --- | --- |
| `docs/development-plan.md` / 공통 관리자 | 현재 파일이 없으며 HWP가 참조한 확정 합성 원본도 저장소에 없음 | 생성 전 팀 확인 필요. 이번 요청의 5/2/3 수량, HWP의 6개 경유·003 환승, 기존 병원 ID/이름을 유지해 `backend/integrations/demo-data.json`으로 구체화함. 시장·터미널 ID/별칭과 미지정 정류장 이름은 이 파일을 A/B/AI와 공유할 것 |
| `README.md`, `docs/structure.md` / 공통 관리자 | 루트 README에는 초기 상태 설명이 남아 있음 | 2026-11-02 구조 문서는 현재 백엔드·AI 주요 소스와 실행 문서 링크를 반영했다. 루트 README의 전체 상태 정리는 후속 작업 |
| `.gitignore` / 공통 관리자 | HWP와 달리 루트 규칙에는 `.local/` 제외가 없음 | 백엔드 내부 `.gitignore`로 `.local/`, `.test-tmp/` 제외 완료. 공통 파일 변경 불필요 |
| `docs/api-contract.md` / 백엔드 + A/B/AI | 입력 길이·유효기간·최신성·AI 제한이 현재 미정 | 이번 요청의 100자/200자/120초/600초/90초/1초를 공통 문서에 반영 제안. `SearchData.expiresAt`, `PrintData.guidance`는 HWP/요청에 필요한 추가 응답 필드로 제공하며 기존 필드는 보존 |
| `docs/api-contract.md` / 백엔드 + B | unavailable 전용 서비스 code 미정, 기존 표에는 409 ROUTE_VERSION_CHANGED만 존재 | 별도 새 코드 도입 없이 현재 409 코드를 사용. 구체 사유는 재선택 메시지로 전달. 상세/live/안내/인쇄 동일 우선순위 적용 |
| `docs/api-contract.md` / B | print liveInfoSnapshot 구조에 ETA가 있으나 요청은 카운트다운 제외 | 구조는 유지하고 print의 etaSeconds를 null로 반환. absolute expectedArrivalAt·출처 시각 유지. `guidance`의 검증된 고정 문구도 같은 버전으로 사용 |
| `ai/contracts/`, `ai/destination_interpretation/`, `ai/easy_guidance/` / AI | 2026-11-02 규칙 기반 기준선과 계약을 통합 | `RuleBasedAIAdapter`의 동기 `interpret_destination(dict)`, `choose_guidance(dict)`를 기본 ASGI 앱에 연결했다. 상태별 이유 코드와 후보 하나의 오타 확인 규칙을 공통 계약에 명시하고 Python 폴더명은 언더바로 통일했다. 여러 안내 표현의 확대는 AI/디자인 검토 필요 |
| `frontend/config/`, `frontend/src/shared/api/` / A | 실제 프록시·클라이언트 미구현 | 5173 → 8000의 /api 프록시와 5초 제한, GET 일시 실패/5xx 1초 후 1회 재시도, POST/4xx 무재시도 구현 필요. 백엔드 CORS는 로컬 두 origin만 허용 |
| `frontend/src/features/` / A/B | 검색·상세·인쇄·음성 UI 없음 | 6개 선택 필드와 실제 JSON 예시 제공. 폴링 30초·이탈 중지, 409 재검색·410 재검색, unknown/stale 표시와 시연 문구 구현·공동 검증 대기 |
| `docs/data-sources.md` / 백엔드 | 실제 API·지원 범위·키·라이선스 계속 미확인 | 상태 갱신할 외부 증거 없음. live는 503, demo 값 혼입 없음 |
| `docs/verification.md` / 공통 관리자 | 최초 구조 검증 기록임 | 원문 유지. 이번 기능 검증은 backend/docs/implementation-status.md와 테스트 출력에 별도 기록 |

현재 계약상 부분 실패를 보존한다. 도착 unavailable을 not_running으로 바꾸지 않고, 변경 조회 실패는 coverageStatus=unknown이다. ready 경로의 미수신 인쇄는 경고를 붙여 허용한다. 초기 시연은 단방향·동일 정류장 명시 환승만 지원하며, 서로 다른 정류장 사이 환승을 지원하려면 별도 검증 도보 연결 자료와 계약 검토가 필요하다.

공동 검증 담당/우선순위: A/B 실제 화면 연결 및 재검색 처리 P1, AI 후보 확인 화면·팀원 PC의 동일 Python 환경 확인 P1, B·디자인 음성/인쇄 레이아웃 P1, 전원 다른 PC 재현 P1. 실제 교통 제공자 선정·현장 장비는 후속 범위다.

## 2026-10-27 · v2 계획서 2단계 인수인계

합성 원본의 ID·이름·별칭·분류·순번·연결은 이번 작업에서 변경하지 않았다. 테이블/외부 API 필드 변경도 없다. 내부 seed 명령 출력만 실제 수량 JSON(inserted/totals)으로 개선했다.

- A/B: `backend/docs/stage2-handoff-examples.json`에 정류장·목적지(이름·별칭·분류), 정상/빈 결과/400/404, 터미널 환승 경로의 실제 API 응답을 준비했다. `departAt`은 요청 시 현재 aware ISO 시각을 생성한다. 응답 기록의 검색 ID는 재사용하지 않는다.
- AI: 같은 파일의 aiInputContract에 등록 후보 목록과 interpret_destination(payload), choose_guidance(payload), 구간별 허용 templateId를 정리했다. 당시 ai 폴더는 자리 표시자뿐이었으므로 실제 함수·후보 계약의 공동 확인을 대기로 기록했다. 해당 단계의 결과는 AI 연결 검증이 아니다.
- 공통 관리자: `backend/docs/database-schema.md`에 PK/FK/nullable/복합키·합성 접근/환승 관계를 정리했다. 공통 docs/development-plan.md의 부재·초기 상태 설명 갱신 제안은 기존과 같다. 이번에는 공통 파일을 수정하지 않았다.

자료를 프로젝트 안에 준비했으며 다른 담당자에게 메시지 전송·리뷰 요청을 실행한 것은 아니다. 실제 교통 출처·키·지역/필드 지원 범위도 여전히 미확인이다.

## 2026-10-27 · v2 계획서 3단계 인수인계

정류장 조회·목적지 검색의 URL·공통 데이터·오류 코드·출력 필드는 변경하지 않았다. 목적지 조회 조건을 backend/models/schemas.py의 DestinationQuery로 정리했으며 생성 OpenAPI도 기존 명세와 동일하다.

- A: `backend/docs/stage3-integration.md`에 입력 규칙·상태별 처리·8000/5173·접두사를 유지하는 /api 프록시 기준을 정리했다. `stage3-http-examples.json`에는 실제 Uvicorn HTTP 21개 사례가 있다.
- 프론트 설정 대상은 `frontend/config/`와 `frontend/src/shared/api/`다. 로컬 두 origin의 CORS는 백엔드에서 검증했다. 프록시 구성·5초 클라이언트 제한·GET 재시도·로딩/빈 결과/400/404/시연 표시는 A의 구현·공동 확인이 필요하며 해당 파일을 직접 수정하지 않았다.
- `category` 선택이 없으면 파라미터를 생략한다. query만 공백 제거 후 최대 100자이며 `category=`는 입력 오류다. 검색 응답은 등록 목록이고 경로 이용 가능성은 후속 경로 검색 결과를 기준으로 한다.
- 실제 A 화면은 아직 없으므로 시작 정류장 표시 → 주요 장소/별칭 검색 → 오류 표시의 브라우저 검증은 대기다. HTTP 성공을 프론트 연동 완료로 표시하지 않는다.

타 담당자에게 메시지 전송이나 원격 리뷰 요청을 실행하지 않았다. 공통 문서·프론트 원본은 모두 보존했다.

## 2026-10-27 · v2 계획서 4단계 인수인계

- A/B: `backend/docs/stage4-integration.md`와 `stage4-http-examples.json`에 검색→선택→상세, 시장/병원/터미널의 A→B 6개 필드와 실제 응답을 준비했다. 기존 URL·ID·필드·응답 구조는 유지한다. 검색 ID와 옵션 ID를 함께 사용하고 departAt은 요청할 때 현재 aware ISO 시각으로 생성한다.
- A: 순위가 바뀌었다는 이유만으로 기존 선택을 버리지 않아도 된다. 해당 경로의 구조·버전이 같고 유효기간 안이면 상세가 유지된다. 실제 409/410 또는 선택 상태 소실이면 새 검색이 필요하다. 최대3개 제한은 이용 가능한 후보 선별 뒤 적용한다.
- B: 상세는 서버 스냅샷을 기준으로 구간 순서를 표시한다. 손상되거나 검증하지 못한 저장 자료는503이며 실제 경로 변경409와 구분한다. 이 보완이 라이브/안내/인쇄의 공통 선택 검사에도 적용되며 전체 회귀 테스트를 통과했다.
- 공통 관리자: 새로운 오류 코드나 외부 필드를 도입하지 않았다. 내부 JSON 저장 형식과 기존 정상 스냅샷은 호환된다. 공개 OpenAPI를 바꿀 필드는 없으며, 요청 스키마가 이미 명시한 문자열 departAt을 엄격히 적용한다.
- A/B 화면·라운팅·뒤로가기/새로고침·오류 표시는 여전히 미구현이므로 실제 브라우저 공동 확인은 대기다. 프론트 코드 변경·다른 담당자에 대한 메시지 전송은 하지 않았다.

## 2026-10-27 · v2 계획서 5단계 인수인계

- B: `backend/docs/stage5-integration.md`와 `stage5-http-examples.json`에 정상·미수신·stale/unknown·운행 상태·변경409·만료410·핵심불가503을 정리했다. sourceUpdatedAt은 원천, fetchedAt은 수집, generatedAt은 응답 시각이며 서로 대체하지 않는다. arrivalStatus와 operationStatus도 별도 의미로 표시한다.
- B: 30초 활성 화면 조회·이탈 시 중지·5초 요청 제한·GET 일시 연결 실패/5xx만1초 후1회 재시도·4xx/POST 무재시도는 기존 기준 그대로다. 구현 대상 `frontend/src/features/live-info/`, `frontend/src/shared/api/`를 직접 수정하지 않았다. 실제 UI/공동 브라우저 검증은 대기다.
- 공통 관리자: 공개 API8개·JSON 필드·오류 코드는 유지했다. 변경 범위는 실제 선택한 경유 구간으로 판단하고 미래/종료 알림은 현재 경로를 막지 않는다. 적용 시작 미확인/잘못된 기간은 현재 결행으로 확정하지 않고 재확인을 요구한다. 항목/적용 ID 집합의 순서는 버전 의미가 아니다.
- 백엔드 제공자 구현자: 내부 ProviderState.arrivals는 `(routeId,boardStationId)`별 ArrivalObservation(예상 시각·operation_status·source_updated_at·fetched_at·source_id)을 사용한다. 기존 기본 필드는 호환을 위해 유지한다. 관측 맵이 없으면 ETA를 만들지 않는다. 명시적 not_running 현재 증거가 fresh이면409, 단순 ETA/수집 갱신은 버전을 바꾸지 않는다. 실제 외부 제공자 연결 완료를 뜻하지 않는다.
- 공통 자료: data-sources.md의 외부기관/키/범위 미확인 상태는 유지했다. 합성 정류장·목적지·노선 원본은 바꾸지 않았다. 타 파트/공통 원본 수정과 담당자 메시지 전송은 없다.

## 2026-10-28 · v2 계획서 6단계 인수인계

- AI 담당자: 2026-10-28 당시 ai/는 temp뿐이었고, 동기 interpret_destination(payload)/choose_guidance(payload)를 준비하면 backend의 AIAdapter에 주입하는 경계를 제공했다. 백엔드는 후보·템플릿 선택 알고리즘을 대신 구현하지 않았다. 기존 논리 JSON 계약을 유지하며 NaN/set/모델 객체·async 반환은 실패 대체한다. 원래 허용 후보와 AI 반환 직전 현재 등록 목록을 함께 확인한다.
- AI 담당자: 1초는 출력 검증·후보 재확인을 포함한 결과 채택 예산이다. worker 준비/시작 실패는 복구하고 프로세스당1실행/대기열없음으로 제한한다. 시간초과가 실제 함수 강제 중단을 뜻하지 않는다. 실제 모듈의 취소/장시간 작업은 준비 후 공동 확인해야 한다.
- B/디자인: `backend/docs/stage6-integration.md`와 `stage6-http-examples.json`에 쉬운 텍스트·미수신/unknown 인쇄·409/410/503 사례를 준비했다. 같은 버전/구간의 구조화된 상세와 서버 텍스트를 사용한다. 도착 카운트다운 값은 null이고 준비200/printGuideId를 출력 성공으로 표시하지 않는다.
- B/디자인: notice는 실제 관측의 미수신·오래됨·원천 확인 불가를 담는다. 확인된 도보 거리와 시간은 각각 보존한다. 음성 UI·HTML/CSS·window.print·프린터 제어는 이번 백엔드 변경에 포함하지 않았고 실제 공동 브라우저 검증은 대기다.
- 공통 관리자: 공개 API8개·필드·ID·오류 코드는 유지했다. 내부 중계·검증/실패 대체와 인쇄 데이터만 보완했다. 원본 AI/프론트/디자인·공통 문서는 수정하지 않았고 담당자 메시지 전송·원격 작업도 없다.

## 2026-11-02 · 규칙 기반 AI 기본 연결과 계약 통일

AI 담당자의 전달사항에 따라 `origin/ai/baseline`의 AI 기준선을 통합하고, 백엔드 기본 앱과 공통 계약을 함께 맞췄다. 외부 모델 호출이나 학습 모델 추론이 아니라 등록 후보·허용 템플릿을 선택하는 규칙 기반 구현이다.

- 기본 실행 진입점 `backend.main:app`은 `create_app(ai_adapter=RuleBasedAIAdapter())`로 연결한다. `create_app()` 팩터리에 어댑터를 주입하지 않는 경우에는 기존 `unavailable`·`template_fallback` 대체 동작을 유지한다.
- 공개 `reasonCode`는 `matched → MATCHED`, `needs_confirmation → USER_CONFIRMATION_REQUIRED`, `no_match → NO_REGISTERED_MATCH`, `unavailable → AI_UNAVAILABLE`로 통일한다. 백엔드는 어댑터 이유 문구를 노출하지 않고 검증한 상태에서 코드를 결정한다. 이전 `NO_MATCH` 이유 코드에 의존하는 클라이언트는 `NO_REGISTERED_MATCH`로 맞춘다. `status`와 응답 필드는 그대로다.
- 후보가 하나여도 오타 추정 결과는 `needs_confirmation`을 유지한다. `matched`도 사용자가 화면에서 확인하고 선택하며, 두 상태 모두 목적지를 자동 확정하지 않는다. 이 기준을 공통 API 계약 8절과 역할 문서에 반영했다.
- AI 폴더는 이번 통합부터 `ai/destination_interpretation/`, `ai/easy_guidance/`를 사용한다. 파일 경로를 이용한 동적 로딩 대신 Python 표준 import를 사용하고, 공개 어댑터 경로는 `ai.adapter.RuleBasedAIAdapter`로 고정한다. 구조·역할·AI 문서도 같은 경로를 따른다.
- 등록 후보 재검증·서버 사실 바인딩·1초 채택 예산·실패 대체는 기존 경계를 유지한다. `bus.basic`, `walk.basic`, `transfer.basic` 외의 표현 확대는 후속 AI/디자인 검토 사항이다.

백엔드·AI 자동 검증 결과와 별개로 A/B 화면의 후보 확인·수동 검색 전환, 음성·인쇄, 팀원 PC 공동 검증은 해당 담당자의 후속 확인 범위다. 다른 담당자에게 메시지를 전송하지 않았다.
