"""백엔드 AIAdapter(backend/integrations/ai.py)에 주입하는 규칙 기반 어댑터.

    from ai.adapter import RuleBasedAIAdapter
    create_app(ai_adapter=RuleBasedAIAdapter())

목적지 해석과 안내 선택은 표준 Python 패키지 import로 연결한다.
"""
from .destination_interpretation import interpreter
from .easy_guidance import selector


class RuleBasedAIAdapter:
    """동기 함수만 제공한다. 외부 모델·네트워크를 호출하지 않는다."""

    def interpret_destination(self, payload: dict) -> dict:
        return interpreter.interpret(payload)

    def choose_guidance(self, payload: dict) -> dict:
        return selector.choose(payload)


class GeminiAIAdapter:
    """비교 실험용. 기본 앱에 연결하지 않는다(ai/evaluation/llm-experiment.md).

    목적지 해석만 Gemini를 부르고, 안내 선택은 규칙 기준선을 그대로 쓴다.
        python ai/evaluation/run_eval.py --adapter ai.adapter:GeminiAIAdapter
    """

    def interpret_destination(self, payload: dict) -> dict:
        from .destination_interpretation import llm_interpreter
        return llm_interpreter.interpret(payload)

    def choose_guidance(self, payload: dict) -> dict:
        return selector.choose(payload)
