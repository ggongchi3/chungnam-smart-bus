# 대화 기능 — 말로 묻고 경로 고르기 (규칙 기반)

어르신이 평소 말하듯 요청하면 뜻을 알아듣고 경로를 골라 주는 기능이다. 지금 있는 두 AI 기능(목적지 후보 찾기, 안내 양식 선택)을 넓힌 것으로, 팀원 제안 5가지를 담았다.

| 기능 | 사용 예시 | 함수(어댑터 메서드) | 쓰는 백엔드 값 |
| --- | --- | --- | --- |
| 말로 목적지와 조건 찾기 | "중앙시장 가는데 많이 안 걷고 싶어요" → 천안중앙시장 + `walking` | `understand` (`understand_request`) | `allowedDestinations` |
| 헷갈리는 목적지 다시 묻기 | "터미널 가고 싶어요" → "천안종합버스터미널과 천안고속버스터미널 중 어디로 가시나요?" | `clarify` (`clarify_destination`) | 해석 결과 `candidates` |
| 추천 이유 한 문장 | "이 버스는 갈아탈 필요가 없어요. 내린 뒤 250m 정도 걸으면 돼요." | `explain_route` | `RouteOption`의 `transferCount`·`transferStations`·`walkingDistanceMeters`·`features`·`estimatedTravelSeconds` |
| 한 단계씩 묻고 듣기 | "몇 번 버스 타요?" → "종합터미널 정류장에서 201번 버스를 타세요." | `answer` (`answer_question`) | `RouteDetail.segments` |
| 인쇄표 맨 위 핵심 한 줄 | "201번 버스 → 단국대학교병원에서 내리세요" | `print_headline` | `RouteDetail.segments` |

## 원칙

- **AI는 장소·노선·숫자를 만들지 않는다.** 모든 문장은 [phrases.json](phrases.json)의 고정 문구에 백엔드 값을 넣은 것이다. 거리는 50m 단위로 반올림하고, 분은 백엔드·인쇄표와 같은 올림(`(초+59)//60`)을 쓴다.
- **조건은 백엔드 정렬 값으로만 돌려준다.** `walking`(최소 도보)·`transfers`(최소 환승)·`fastest`(최소 이동시간)는 `POST /route-searches`의 `sort`와 같은 값이다. 경로를 고르고 정렬하는 일은 백엔드가 그대로 한다.
- **"말씀하신 대로 …" 문장은 백엔드가 그 경로에 해당 `features`(예: `최소 도보`)를 붙였을 때만** 쓴다. AI가 "가장 덜 걷는 길"이라고 스스로 판단하지 않는다.
- 예외를 밖으로 던지지 않는다. 필요한 값이 없으면 `status: "unavailable"`이고, 화면·음성·인쇄는 기존 안내만 쓰면 된다.
- 화면 키보드로 쓴 글도 같은 `understand`로 처리한다(말·글 구분 없음).

## 동작 요약

**understand** — 조건 표현을 먼저 찾고(`PREFERENCE_PATTERNS`), 그 낱말을 뺀 나머지를 기존 목적지 해석(`interpreter.interpret`)에 넘긴다. "빨리 안 가도 돼요"처럼 조건 뒤에 부정이 붙으면 조건으로 보지 않는다. 조건만 말하면("빨리 가야 돼요") 목적지는 `no_match`이므로, 화면은 이미 고른 목적지에 조건만 바꿔 다시 검색하면 된다.

**clarify** — 후보 1개: "천안역으로 가시나요?", 2개: "A와 B 중 어디로 가시나요?", 3~4개: "A, B, C 중 어디로 가시나요?", 5개 이상: "가시려는 곳을 아래에서 골라 주세요." `options`는 받은 후보 순서 그대로이며 큰 버튼으로 보여 주는 용도다. 조사(으로/로, 과/와)는 이름 끝 받침에 맞춘다.

**explain_route** — 사용자가 말한 조건과 관련된 문장을 앞에 둔다(덜 걷기 → 도보 먼저, 빨리 → 시간 먼저). 시간 문장은 `fastest`일 때만 넣는다.

**answer** — 질문 뜻(intent)을 규칙으로 고른다: `which_bus`, `how_many`, `where_board`, `where_alight`, `stop_count`, `walk`, `duration`, `repeat`, `unknown`. "몇 번 버스 타요?"(어느 버스)와 "몇 번 타요?"(몇 번 타는지), "걸어요"(도보)와 "걸려요"(시간)를 구분한다. `repeat`은 화면이 넘긴 `previousAnswer`를 다시 말한다. 모르는 말은 `unknown`과 다시 물어봐 달라는 고정 문장.

**print_headline** — 직통: "201번 버스 → 단국대학교병원에서 내리세요", 1회 환승: "72번 버스 → 신부동회차지에서 16번으로 갈아타기 → 고속터미널에서 내리세요". 탄 곳과 내리는 곳 이름이 같으면 정류장 번호로 가른다("종합터미널(2357번)").

## Gemini 선택 옵션

`ai.adapter.RuleFirstGeminiAdapter`는 **규칙이 모를 때만** Gemini를 부른다(기본 앱에는 연결하지 않음).

- 목적지 `no_match` → Gemini 목적지 해석(PR #8의 `llm_interpreter`, 허용 목록 재검증)
- 조건 없음 → Gemini가 `walking`·`transfers`·`fastest`·`none` 중 하나만 고름 ([llm_intent.py](llm_intent.py))
- 질문 `unknown` → Gemini가 정해진 intent 중 하나만 고름

Gemini는 값을 **고르기만** 하고 문장은 만들지 않는다. 키 없음·시간초과·목록 밖 값은 규칙 결과로 남는다. 조건을 말하지 않은 요청마다 Gemini를 한 번 더 부르게 되므로 무료 한도(분당 15회)와 1초 예산을 생각하면 시연 기본값은 규칙 기반이 맞다.

## 확인

```bash
python ai/evaluation/run_eval.py -v                 # 대화 사례 66개 포함
python -m unittest ai.evaluation.test_conversation  # 계약 모양·예외 없음·숫자 출처·Gemini 대체
python -m unittest ai.evaluation.test_backend_integration  # 실제 천안 데이터로 이어 보기(백엔드 의존성 필요)
```

평가 사례는 [cases.json](../evaluation/cases.json)의 `conversation` 섹션이다. 경로 예시는 2026-11-12 천안 정적 데이터에서 백엔드가 낸 실제 응답을 줄인 것이다.
