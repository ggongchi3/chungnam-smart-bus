# AI — 추가 제안 모듈

자연어 목적지 표현을 등록 후보 ID에 연결하고, 검증된 경로 구간에 맞는 쉬운 안내 템플릿을 고른다. 첫 시연은 외부 모델 없이 **규칙 기반 기준선**으로 동작하며, 이를 학습 모델 추론으로 표현하지 않는다. AI는 교통 사실을 만들지 않고 백엔드가 모든 출력을 다시 검증한다.

| 폴더·파일 | 내용 |
| --- | --- |
| [adapter.py](adapter.py) | 백엔드 `AIAdapter`에 주입하는 `RuleBasedAIAdapter` |
| [contracts/](contracts/README.md) | 두 함수의 입출력 계약, JSON Schema, 백엔드와 확인할 사항 |
| [destination-interpretation/](destination-interpretation/README.md) | 목적지 표현 해석 규칙 |
| [easy-guidance/](easy-guidance/README.md) | 안내 템플릿 목록과 선택 규칙 |
| [evaluation/](evaluation/README.md) | 평가 사례, 평가 스크립트, 테스트 |

## 백엔드 연결

```python
from ai.adapter import RuleBasedAIAdapter
from backend.main import create_app

app = create_app(ai_adapter=RuleBasedAIAdapter())
```

현재 `backend/main.py`의 기본 `app`에는 어댑터가 연결되어 있지 않다. 연결 확인은 [evaluation/test_backend_integration.py](evaluation/test_backend_integration.py)에서 했으며, 기본 앱에 연결하는 방식은 백엔드 담당과 정한다.
