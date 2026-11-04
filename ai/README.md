# AI — 추가 제안 모듈

자연어 목적지 표현을 등록 후보 ID에 연결하고, 검증된 경로 구간에 맞는 쉬운 안내 템플릿을 고른다. 첫 시연은 외부 모델 없이 **규칙 기반 기준선**으로 동작하며, 이를 학습 모델 추론으로 표현하지 않는다. AI는 교통 사실을 만들지 않고 백엔드가 모든 출력을 다시 검증한다.

| 폴더·파일 | 내용 |
| --- | --- |
| [adapter.py](adapter.py) | 백엔드 `AIAdapter`에 주입하는 `RuleBasedAIAdapter` |
| [contracts/](contracts/README.md) | 두 함수의 입출력 계약, JSON Schema, 연결 결정과 후속 검토, [결과별 화면·음성 문구안](contracts/fallback-copy.md) |
| [destination_interpretation/](destination_interpretation/README.md) | 목적지 표현 해석 규칙 |
| [easy_guidance/](easy_guidance/README.md) | 안내 템플릿 목록과 선택 규칙 |
| [evaluation/](evaluation/README.md) | 평가 사례, 평가 스크립트, 테스트, 백엔드 연결 확인, [LLM 비교 실험 설계](evaluation/llm-experiment.md) |

## 백엔드 연결

```python
from ai.adapter import RuleBasedAIAdapter
from backend.main import create_app

app = create_app(ai_adapter=RuleBasedAIAdapter())
```

`backend/main.py`의 기본 `app`은 위와 같이 어댑터를 연결한다. `create_app()`은 테스트·장애 대체 검증을 위해 어댑터를 주입하지 않는 방식도 유지하며, 이 경우 해석은 `unavailable`, 안내는 `template_fallback`이다. 연결 검증은 [evaluation/test_backend_integration.py](evaluation/test_backend_integration.py)에 있다.

AI 구현·계약·평가의 원본은 `origin/ai/baseline`의 `baf4a58`이며, 이번 연결에서 두 작업 폴더를 `destination_interpretation`, `easy_guidance` Python 패키지로 전환했다. 목적지 매칭과 안내 선택 규칙은 원본을 유지한다.
