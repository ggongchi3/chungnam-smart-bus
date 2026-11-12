# AI 입출력 계약 v0.1

백엔드 `backend/integrations/ai.py`의 `AIAdapter`에 주입하는 두 동기 함수의 계약이다. 공통 API 계약([docs/api-contract.md](../../docs/api-contract.md) 8·9절)의 AI 내부 요청·응답을 구체화한 것이며, 서비스 전체 API의 대표 관리자는 백엔드다. JSON Schema는 [schemas.json](schemas.json)에 있다.

## 공통 원칙

- AI는 교통 사실의 출처가 아니다. 후보 ID와 templateId만 고르고 정류장·노선·정류장 수·시간·환승 연결을 만들거나 바꾸지 않는다.
- 동기 함수이며 JSON으로 직렬화 가능한 `dict`만 반환한다. 예외를 던지지 않고 실패는 `unavailable`로 반환한다.
- 결과 채택 예산은 백엔드 기준 1초다(출력 검증 포함). 기준선은 외부 모델·네트워크를 호출하지 않는다.
- 백엔드가 모든 출력을 다시 검증하고, 실패·시간초과·위반이면 일반 검색/고정 템플릿으로 대체한다. AI 실패만으로 경로 API를 실패 처리하지 않는다.

## 1. `interpret_destination(payload) -> dict`

입력(백엔드 → AI):

```json
{
  "text": "큰 병원에 가고 싶어요",
  "dataMode": "demo",
  "allowedDestinations": [
    {"destinationId": "demo-destination-001", "name": "시연 병원", "aliases": ["시연 큰 병원"]}
  ]
}
```

출력(AI → 백엔드):

```json
{"status": "matched", "candidateDestinationIds": ["demo-destination-001"], "reasonCode": "MATCHED"}
```

| status | candidateDestinationIds | reasonCode | 화면 동작(백엔드·A 처리) |
| --- | --- | --- | --- |
| `matched` | 정확히 1개 | `MATCHED` | 후보 확인 후 사용자가 선택 |
| `needs_confirmation` | 2개 이상, 또는 오타로 추정한 1개 이상 | `USER_CONFIRMATION_REQUIRED` | 후보 목록에서 사용자가 선택 |
| `no_match` | 빈 배열 | `NO_REGISTERED_MATCH` | 일반 검색·주요 장소 선택 |
| `unavailable` | 빈 배열 | `AI_UNAVAILABLE` | 일반 검색·주요 장소 선택 |

- 화면·음성 문구 검토안은 [fallback-copy.md](fallback-copy.md)에 있다.
- 공개 API도 위의 네 `reasonCode`를 사용한다. 백엔드는 AI의 `reasonCode` 문자열을 그대로 노출하지 않고, 검증된 `status`에 따라 해당 코드를 직접 정한다. `MATCHED`도 사용자 확인·선택을 생략한다는 뜻은 아니다.
- 후보 ID는 `allowedDestinations`의 부분집합이며 중복이 없고 입력 목록의 순서를 따른다.
- `text`가 문자열이 아니거나, 공백만 있거나, 200자를 넘거나, 후보 목록 형식이 잘못되면(ID 중복 포함) `unavailable`이다.

## 2. `choose_guidance(payload) -> dict`

입력:

```json
{
  "routeSnapshotVersion": "demo-v1",
  "dataMode": "demo",
  "verifiedSegments": [
    {"segmentId": "s1", "type": "bus", "allowedTemplateIds": ["bus.basic"]},
    {"segmentId": "s2", "type": "walk", "allowedTemplateIds": ["walk.basic"]}
  ]
}
```

출력:

```json
{
  "status": "ok",
  "routeSnapshotVersion": "demo-v1",
  "steps": [
    {"segmentId": "s1", "templateId": "bus.basic"},
    {"segmentId": "s2", "templateId": "walk.basic"}
  ]
}
```

- `ok`면 입력과 같은 버전, 같은 구간 수·순서·segmentId를 유지하고 구간마다 `allowedTemplateIds` 안의 active 템플릿 하나를 고른다.
- 버전이 비었거나, 구간이 없거나, 구간 유형을 알 수 없거나, segmentId가 중복이거나, 고를 수 있는 active 템플릿이 없으면 `{"status": "unavailable", "routeSnapshotVersion": <입력 버전 또는 "">, "steps": []}`를 반환한다.
- 문장의 슬롯 값(정류장명·노선명·정류장 수 등)은 백엔드가 채운다. 템플릿 목록은 [easy_guidance/templates.json](../easy_guidance/templates.json)이다.

## 3. 대화 기능 (제안 v0.2, 백엔드 미연결)

`RuleBasedAIAdapter`에 다섯 메서드를 더했다. 백엔드 `AIAdapter` Protocol에는 아직 없으므로 지금 동작에는 영향이 없다. 설명은 [conversation/README.md](../conversation/README.md), JSON Schema는 [schemas.json](schemas.json)의 `Understand*`·`Clarify*`·`ExplainRoute*`·`AnswerQuestion*`·`PrintHeadline*`이다.

| 메서드 | 입력 | 출력 |
| --- | --- | --- |
| `understand_request` | 1번과 같음 `{text, dataMode, allowedDestinations}` | `{destination: <1번 출력>, preference: {sort: "walking"\|"transfers"\|"fastest"\|null, matchedPhrase}}` |
| `clarify_destination` | `{candidates: [{destinationId, name}]}` | `{status, question, options: [{destinationId, label}]}` |
| `explain_route` | `{routeOption: RouteOption, sort}` | `{status, text, sentences}` |
| `answer_question` | `{question, routeDetail: RouteDetail, previousAnswer?}` | `{status, intent, text}` |
| `print_headline` | `{routeDetail: RouteDetail}` | `{status, text}` |

- 문장(`question`·`text`)은 모두 [conversation/phrases.json](../conversation/phrases.json)의 고정 문구 + 입력 값이다. 숫자·이름을 새로 만들지 않는다.
- 실패는 `status: "unavailable"`(understand는 `destination.status`)이며 예외를 던지지 않는다.

### 연결 제안 (백엔드·프론트 결정 필요)

- **백엔드**: 아래 중 편한 방식. AI 호출은 기존 `AIBoundary`(1초 예산)로 감싸고, 실패하면 각 기능을 건너뛴다.
  - `POST /destination-interpretations` 응답에 `preference.sort`와 `clarification`(question·options)을 더하거나, 새 `POST /conversation/understand`를 둔다.
  - `RouteOption`마다 `reasonText`(= `explain_route`)를 붙이거나 `GET .../options/{id}`에 넣는다.
  - `POST /conversation/answers` `{routeSearchId, routeOptionId, question, previousAnswer?}` → `{intent, text}`.
  - `PrintData.headline`(= `print_headline`). 인쇄표 맨 위에 한 줄, 기존 단계별 인쇄표는 아래에 그대로.
- **프론트 A**: `App.tsx`의 `searchText()`가 일반 검색이 비었을 때 해석 결과의 `preference.sort`로 `findRoutes(dest, sort)`를 부르면 "덜 걷고 싶어요"가 기존 `최소 도보` 정렬로 바로 이어진다. `needs_confirmation`이면 `question`을 제목으로, `options`를 큰 버튼으로.
- **프론트 B**: 묻고 듣기 답과 추천 이유는 기존 `speechPlayer`로 읽으면 된다. **음성 입력(STT)은 지금 프론트에 없다**(`speechSynthesis` 출력만). 말로 묻기를 실제로 하려면 STT 도입 여부를 정해야 하며, 그 전에는 화면 키보드·질문 버튼("몇 번 버스 타요?" 등)으로 같은 함수를 쓸 수 있다.

## 연결 결정과 후속 검토

1. **reasonCode 통일**: AI 계약과 공개 API 모두 위 표의 `MATCHED / USER_CONFIRMATION_REQUIRED / NO_REGISTERED_MATCH / AI_UNAVAILABLE`을 사용한다. 공개 코드는 백엔드가 검증한 상태로 산출한다.
2. **허용 템플릿이 유형별 1개**: 백엔드는 `<type>.basic`만 허용하고 문장도 고정으로 만든다. `templates.json`의 proposal(`bus.split`, `transfer.named`, `walk.short`, `bus.print`)을 쓰려면 백엔드의 허용 목록·슬롯 채우기 변경과 디자인 검토가 필요하다. `transfer.named`는 다음 노선명 슬롯도 필요하다.
3. **폴더 이름 전환 완료**: 이번 기본 앱 연결과 함께 `destination_interpretation`, `easy_guidance`로 바꾸고 `__init__.py`를 추가했다. `ai/adapter.py`는 파일 경로 로더 대신 표준 상대 import를 사용한다. 공개 어댑터 경로는 계속 `ai.adapter.RuleBasedAIAdapter`다.
4. **needs_confirmation 후보 1개 유지**: 오타 추정 결과는 후보가 1개여도 `needs_confirmation`으로 반환하며 백엔드가 그대로 전달한다. 화면은 후보 수만으로 자동 확정하지 않고 `status`에 따라 확인을 요청한다.
5. **Python 버전**: 백엔드는 3.13.2로 검증했다. AI 모듈은 표준 라이브러리만 사용하며 3.13 문법 범위로 작성했다.
6. **category 미전달**: 입력에 Destination의 `category`가 없어 분류 표현은 이름·별칭의 핵심어로 연결한다. category를 함께 받으면 분류 매칭을 더 명확히 할 수 있다(선택).
7. **도보 시간 단위**: `walk.basic`의 백엔드 문장은 60초 미만이면 초로 읽고, 60초 이상이면 화면·인쇄와 같이 분 단위로 올림한다. 89초는 약 2분이다. 응답의 `durationSeconds`는 초 단위를 유지한다.
8. **인쇄 안내표 슬롯(제안, 디자인 Print Guide 2026-11-05)**: 출력물(감열지 80mm, 인쇄 폭 68mm)에 **운행 방향(방면)**과 **하차 직전 정류장**이 들어간다. 둘 다 지금 백엔드 응답에 없으므로 `templates.json`에 proposal `bus.print`(슬롯 `direction`, `previousStation.name`)로 기록했다. 값은 백엔드가 실제 노선 순서로 채우고, AI는 값을 만들지 않는다.
9. **대화 기능 연결(제안)**: 위 3절. 백엔드 Protocol·엔드포인트·`PrintData.headline`, 프론트 STT 도입 여부가 정해지면 연결 테스트를 이어서 붙인다.
10. **같은 이름의 정류장(백엔드 확인 요청)**: 천안 정적 데이터에서 `종합터미널 → 천안고속버스터미널` 121번 직통 경로가 `종합터미널(685)`에서 타서 46개 정류장을 돌아 `종합터미널(2357)`에서 내린다(대기 제외 약 68분). 순환 노선을 거의 한 바퀴 도는 경로라 직통 후보로 보여 줄지 백엔드 확인이 필요하다. AI 문장은 이름이 같으면 정류장 번호를 붙여 가른다.
11. **장소 표현 보완**: 등록 이름 앞 지역명(천안·남산 등)을 뺀 말도 그 장소로 본다('중앙시장' → 천안중앙시장, '고속터미널' → 천안고속버스터미널, '시청' → 천안시청). 분류 이름 자체('병원'·'시장'·'터미널')는 계속 해당 분류 후보를 모두 고르고 확인을 요청한다.
