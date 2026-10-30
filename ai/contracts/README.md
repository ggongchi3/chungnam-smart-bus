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
- 문장의 슬롯 값(정류장명·노선명·정류장 수 등)은 백엔드가 채운다. 템플릿 목록은 [easy-guidance/templates.json](../easy-guidance/templates.json)이다.

## 백엔드와 확인할 사항

1. **reasonCode 불일치**: 공통 계약은 `MATCHED / USER_CONFIRMATION_REQUIRED / NO_REGISTERED_MATCH / AI_UNAVAILABLE`인데, 현재 `backend/services/ai.py`는 공개 응답에서 matched·needs_confirmation 모두 `USER_CONFIRMATION_REQUIRED`, no_match는 `NO_MATCH`로 덮어쓴다. AI 모듈은 계약 문서의 코드를 반환한다. 어느 쪽으로 맞출지 결정 필요.
2. **허용 템플릿이 유형별 1개**: 백엔드는 `<type>.basic`만 허용하고 문장도 고정으로 만든다. `templates.json`의 proposal(`bus.split`, `transfer.named`, `walk.short`)을 쓰려면 백엔드의 허용 목록·슬롯 채우기 변경과 디자인 검토가 필요하다. `transfer.named`는 다음 노선명 슬롯도 필요하다.
3. **폴더 이름**: `destination-interpretation`, `easy-guidance`는 하이픈 때문에 Python import가 불가하다. 지금은 `ai/adapter.py`가 파일 경로로 불러온다. 개발 기준안 2절대로 `destination_interpretation`, `easy_guidance`로 바꿀 시점을 정하면 `docs/structure.md` 등 공통 문서도 함께 갱신해야 한다.
4. **needs_confirmation 후보 1개**: 오타 추정 결과는 후보가 1개여도 `needs_confirmation`으로 반환한다. 현재 백엔드 검증(후보 존재 여부만 확인)은 이를 허용하며, 공통 계약 문서 8절과 A의 화면 분기에 반영이 필요하다.
5. **Python 버전**: 백엔드는 3.13.2로 검증했다. AI 모듈은 표준 라이브러리만 사용하며 3.13 문법 범위로 작성했다.
6. **category 미전달**: 입력에 Destination의 `category`가 없어 분류 표현은 이름·별칭의 핵심어로 연결한다. category를 함께 받으면 분류 매칭을 더 명확히 할 수 있다(선택).
