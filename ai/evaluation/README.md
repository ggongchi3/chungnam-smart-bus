# AI 기준선 평가

[cases.json](cases.json)의 합성 사례로 규칙 기준선을 검사한다. 통과 수는 이 사례 묶음에 대한 결과일 뿐이며 실제 사용자 표현의 정확도를 뜻하지 않는다.

프로젝트 루트에서 실행한다. 표준 라이브러리만 쓰므로 별도 설치가 필요 없다.

```
python ai/evaluation/run_eval.py -v
python ai/evaluation/run_eval.py --adapter 모듈:클래스   # 다른 어댑터 비교
python -m unittest discover -s ai/evaluation -t .
```

대화 기능 사례의 경로 예시(`conversation.routes`)는 2026-11-12 천안 정적 데이터에서 백엔드가 낸 실제 응답을 줄인 것이다. 문장은 고정 문구라 글자 그대로 비교한다. [test_conversation.py](test_conversation.py)는 계약 모양·예외 없음·문장 속 숫자가 경로 값에서만 나오는지·Gemini 선택 옵션의 대체 동작을 본다.

## 사례 묶음

| 묶음 | 내용 |
| --- | --- |
| 표현 변형 | 공백·기호·조사, 별칭, 분류 표현 |
| 모호한 표현 | 여러 장소를 함께 말함 |
| 부정 표현 | `말고·빼고·아니라` 등으로 장소를 뺌 |
| 구어체·사투리 | `장 보러`, `고속버스 타러`, `갈라고 하는디유` |
| 오타 | 자모 1개 차이(`벙원`), 비슷하지만 다른 단어(`시청`, `시정`) |
| 동명·유사 후보 | 평가 전용 목록(`시연 병원`, `시연 큰 병원`)에서 구체적 표현 우선 |
| 후보 없음 | 등록되지 않은 장소, 접두어만 입력, 연결하지 않는 분류(`의원`) |
| 허용 목록 밖 | 시장이 빠진 목록에서 시장 요청 |
| 입력 오류 | 빈 값, 200자 초과, 잘못된 형식, 중복 ID |
| 안내 선택 | 직통·환승, proposal만 허용, 알 수 없는 유형, 중복 구간, 빈 버전 |
| 대화: 목적지와 조건 (20) | 실제 천안 장소 목록(`cheonan`)에서 "중앙시장 가는데 많이 안 걷고 싶어요" → 천안중앙시장 + `walking`, 부정("빨리 안 가도"), 조건만 말함, 목적지 아님 |
| 대화: 다시 묻기 (6) | 후보 1·2·3~4·5개 이상 문구, 조사(으로/로, 과/와) |
| 대화: 추천 이유 (8) | 직통·환승, 말한 조건별 문장 순서, 백엔드 `features`가 있을 때만 "말씀하신 대로" |
| 대화: 묻고 듣기 (28) | 몇 번 버스/몇 번 타요/어디서 타요·내려요/몇 정거장/얼마나 걸어요·걸려요/다시/모르는 말, 이름이 같은 정류장 |
| 대화: 인쇄표 한 줄 (4) | 직통·1회 환승·같은 이름 정류장 |

외부 LLM 비교 실험 계획은 [llm-experiment.md](llm-experiment.md)에 있다.

## 백엔드 연결 확인

[test_backend_integration.py](test_backend_integration.py)는 백엔드 코드를 바꾸지 않고 `create_app(ai_adapter=...)`에 어댑터를 주입해 공개 API로 확인한다. `backend/requirements.lock`이 설치된 Python 3.13 환경에서 실행하며, 의존성이 없으면 건너뛴다.

```
python -m unittest ai.evaluation.test_backend_integration -v
```

| 확인 내용 | 결과 기준 |
| --- | --- |
| 규칙 어댑터 연결 | 목적지 해석 matched / needs_confirmation / no_match, 안내 `ai_assisted`, 인쇄 안내의 버전 일치 |
| 사실 값 보존 | 후보의 이름·분류는 백엔드 값, AI 유무와 관계없이 안내 문장 동일 |
| AI 없음 | 해석 `unavailable`, 안내 `template_fallback` |
| 잘못된 AI 출력(`backendSideCases`) | 목록 밖·중복 ID, 상태와 후보 수 불일치, NaN, 예외, 1초 초과 → 해석 `unavailable` / 버전 불일치, 구간 순서 변경·누락·추가, 허용 밖 템플릿, 예외, 1초 초과 → 안내 `template_fallback`. 모두 1.5초 안에 응답 |

공개 `reasonCode`(상태별 네 값, 백엔드가 산출)와 기본 앱 연결의 회귀 검증은 백엔드의 [backend/tests/test_ai_integration.py](../../backend/tests/test_ai_integration.py)에 있다.

| 날짜 | 환경 | 결과 |
| --- | --- | --- |
| 2026-10-30 | macOS, Python 3.13.15, 잠금 파일 의존성 | 이 파일 8개 통과, 백엔드 기존 테스트 316개 통과 |
| 2026-11-02 | Windows 11, Python 3.13.2 (백엔드 담당 실행) | 백엔드·AI 전체 344개 통과, 합성 평가 59/59. 상세는 [AI 연결 결과](../../backend/docs/ai-integration-20261102.md) |
| 2026-11-04 | macOS 26.6.2 (arm64), Python 3.13.18, 잠금 파일 의존성 | 백엔드·AI 전체 344개 통과(`pytest backend/tests ai/evaluation`), 합성 평가 59/59, 이 파일 8개 통과 |
| 2026-11-05 | Windows 11, Python 3.12.10, 잠금 파일 의존성 (main `cf78085` 기준) | 백엔드·AI 전체 348개 통과(`pytest backend/tests ai/evaluation`, 도보 분 단위 확인 1개 추가), 합성 평가 59/59, 이 파일 9개 통과 |
| 2026-11-06 | macOS 26.6.2 (arm64), Python 3.13.18, 잠금 파일 의존성 (main `71f47ef` 기준) | 백엔드·AI 전체 348개 통과, 합성 평가 59/59. 실제 Uvicorn 서버에 프론트엔드(PR #6 `client.ts`)와 같은 요청 형식으로 `POST /api/v1/destination-interpretations` 확인: `큰 병원` matched, `벙원` needs_confirmation(후보 1개), `시장 병원` needs_confirmation(후보 2개), `우체국` no_match — 화면 분기(`DestinationSearch.tsx`)가 쓰는 status·reasonCode와 일치. `frontend` `npm run build` 통과. 브라우저 화면 확인은 하지 않음 |
| 2026-11-06 | 같은 환경, 정답 변경 후 | i32(`장에 가요` → 시장 확인 필요)·i43(`병원이랑 시잔` → 병원·시장 확인 필요) 정답 변경과 규칙 수정, 오탐 방지 사례 i44~i50 추가. 합성 평가 66/66, 백엔드·AI 전체 356개 통과 |
| 2026-11-12 | macOS 26.6.2 (arm64), Python 3.13, 잠금 파일 의존성 (`ai/conversation`, main `5f62345` + PR #8 기준) | 대화 기능 추가. 합성 평가 132/132(기존 66 + 대화 66), 백엔드·AI 전체 446개 통과(`pytest`), 이 파일 12개 통과(천안 실제 데이터로 말 → 조건 정렬 검색 → 이유·답·인쇄 한 줄 이어 보기 포함). 대화 입출력 66건 `schemas.json` 검증(jsonschema, 일회성). 장소 표현 보완 후 기존 66/66 유지 |
