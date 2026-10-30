"""백엔드 AIAdapter(backend/integrations/ai.py)에 주입하는 규칙 기반 어댑터.

    from ai.adapter import RuleBasedAIAdapter
    create_app(ai_adapter=RuleBasedAIAdapter())

작업 폴더 이름에 하이픈이 있어 일반 import를 쓸 수 없으므로 파일 경로로 불러온다.
폴더를 destination_interpretation / easy_guidance로 바꾸면 이 로더를 import로 교체한다.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(f'ai.{name}', ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


interpreter = _load('interpreter', 'destination-interpretation/interpreter.py')
selector = _load('selector', 'easy-guidance/selector.py')


class RuleBasedAIAdapter:
    """동기 함수만 제공한다. 외부 모델·네트워크를 호출하지 않는다."""

    def interpret_destination(self, payload: dict) -> dict:
        return interpreter.interpret(payload)

    def choose_guidance(self, payload: dict) -> dict:
        return selector.choose(payload)
