"""백엔드 AIAdapter(backend/integrations/ai.py)에 주입하는 규칙 기반 어댑터.

    from ai.adapter import RuleBasedAIAdapter
    create_app(ai_adapter=RuleBasedAIAdapter())

목적지 해석과 안내 선택은 표준 Python 패키지 import로 연결한다.
대화 기능 5개(understand_request 등)는 백엔드 AIAdapter Protocol에 아직 없는 추가 메서드다.
백엔드가 부르기 전까지는 기존 동작에 영향이 없다(제안: ai/contracts/README.md).
"""
from .conversation import dialogue, explain, understand
from .destination_interpretation import interpreter
from .easy_guidance import selector


class RuleBasedAIAdapter:
    """동기 함수만 제공한다. 외부 모델·네트워크를 호출하지 않는다."""

    def interpret_destination(self, payload: dict) -> dict:
        return interpreter.interpret(payload)

    def choose_guidance(self, payload: dict) -> dict:
        return selector.choose(payload)

    # ---- 대화 기능 (ai/conversation) ----
    def understand_request(self, payload: dict) -> dict:
        """말로 목적지와 조건 찾기. 입력은 interpret_destination과 같다."""
        return understand.understand(payload, interpret=self.interpret_destination)

    def clarify_destination(self, payload: dict) -> dict:
        """헷갈리는 목적지 다시 묻기. {candidates:[{destinationId, name}]}."""
        return explain.clarify(payload)

    def explain_route(self, payload: dict) -> dict:
        """추천 이유 한 문장. {routeOption, sort}."""
        return explain.explain_route(payload)

    def answer_question(self, payload: dict) -> dict:
        """한 단계씩 묻고 듣기. {question, routeDetail, previousAnswer?}."""
        return dialogue.answer(payload)

    def print_headline(self, payload: dict) -> dict:
        """인쇄표 맨 위 핵심 한 줄. {routeDetail}."""
        return explain.print_headline(payload)


class GeminiAIAdapter(RuleBasedAIAdapter):
    """비교 실험용. 기본 앱에 연결하지 않는다(ai/evaluation/llm-experiment.md).

    목적지 해석은 Gemini를 부르고, 안내 선택은 규칙 기준선을 그대로 쓴다.
        python ai/evaluation/run_eval.py --adapter ai.adapter:GeminiAIAdapter
    """

    def interpret_destination(self, payload: dict) -> dict:
        from .destination_interpretation import llm_interpreter
        return llm_interpreter.interpret(payload)


class RuleFirstGeminiAdapter(RuleBasedAIAdapter):
    """선택 옵션: 규칙을 먼저 쓰고, 규칙이 모를 때만 Gemini에 뜻을 묻는다. 기본 앱에 연결하지 않는다.

    - 목적지: 규칙이 no_match일 때만 Gemini 목적지 해석(허용 목록 재검증).
    - 조건: 규칙이 조건을 못 찾았을 때만 Gemini가 walking·transfers·fastest·none 중 하나를 고른다.
    - 질문: 규칙이 unknown일 때만 Gemini가 정해진 intent 중 하나를 고른다.
    답 문장은 언제나 고정 문구 + 백엔드 값이다. Gemini 실패는 규칙 결과로 남는다.
    """

    def interpret_destination(self, payload: dict) -> dict:
        rule = interpreter.interpret(payload)
        if rule['status'] != 'no_match':
            return rule
        from .destination_interpretation import llm_interpreter
        llm = llm_interpreter.interpret(payload)
        return llm if llm['status'] in ('matched', 'needs_confirmation') else rule

    def understand_request(self, payload: dict) -> dict:
        out = super().understand_request(payload)
        if out['preference']['sort'] is None and out['destination']['status'] != 'unavailable':
            from .conversation import llm_intent
            sort = llm_intent.classify_preference(payload['text'])
            if sort:
                out['preference'] = {'sort': sort, 'matchedPhrase': None}
        return out

    def answer_question(self, payload: dict) -> dict:
        def classify(question):
            intent = dialogue.classify(question)
            if intent != 'unknown':
                return intent
            from .conversation import llm_intent
            return llm_intent.classify_question(question)
        return dialogue.answer(payload, classify_intent=classify)
