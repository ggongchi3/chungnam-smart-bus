# 쉬운 한국어 안내 — 템플릿 선택 기준선

`selector.py`의 `choose(payload)`가 검증된 경로 구간마다 허용된 안내 템플릿 ID를 고른다. 입출력은 [contracts/README.md](../contracts/README.md) 2절을 따른다.

- 구간 순서·segmentId·버전을 그대로 유지하며 구간을 추가·삭제·재배열하지 않는다.
- [templates.json](templates.json)에서 `status: active`인 템플릿만 고르며, 같은 유형 안에서는 파일에 적힌 순서가 우선순위다.
- 문장의 슬롯은 백엔드가 검증한 값으로 채운다. 미확인 거리·시간은 생략하지 않고 `확인되지 않았습니다`로 표시한다(백엔드 구현).

## 템플릿 상태

| templateId | 상태 | 비고 |
| --- | --- | --- |
| `bus.basic`, `walk.basic`, `transfer.basic` | active | 현재 백엔드 고정 문장과 동일 |
| `bus.split` | proposal | 타기·내리기를 두 줄로 나눔(한 단계 한 행동). 백엔드의 두 줄 렌더링 필요 |
| `transfer.named` | proposal | 갈아탈 노선명 명시. 백엔드에 `nextRouteName` 슬롯 추가 필요 |
| `walk.short` | proposal | 음성 길이 단축. 미확인 문구 처리를 디자인·B와 결정 필요 |

각 템플릿의 `example`은 합성 시연 데이터로 채운 문장이며, active 3개는 백엔드 실제 응답과 같은지 확인했다(시연 표시 접두 문구 제외).

proposal을 active로 바꾸려면 디자인의 문구 검토, 백엔드의 허용 목록·슬롯 반영, 평가 사례 갱신이 모두 필요하다.
