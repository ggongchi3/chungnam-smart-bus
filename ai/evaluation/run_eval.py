"""cases.json으로 AI 어댑터를 평가한다. 표준 라이브러리만 사용한다.

    python ai/evaluation/run_eval.py                       # 규칙 기준선 요약
    python ai/evaluation/run_eval.py -v                    # 사례별 결과
    python ai/evaluation/run_eval.py --adapter 모듈:클래스  # 다른 어댑터(예: LLM 실험)와 비교

수치는 이 합성 사례 묶음에서의 통과 수일 뿐이며 실제 사용자 표현의 정확도가 아니다.
"""
import argparse
import importlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ai.adapter import RuleBasedAIAdapter  # noqa: E402

CASES_PATH = Path(__file__).with_name('cases.json')
BUDGET_SECONDS = 1.0  # 백엔드 결과 채택 예산


def load_cases(path=CASES_PATH):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_adapter(spec):
    """'패키지.모듈:클래스' → 인스턴스."""
    module, _, name = spec.partition(':')
    return getattr(importlib.import_module(module), name)()


def case_text(case):
    if 'textRepeat' in case:
        piece, count = case['textRepeat']
        return piece * count
    return case['text']


def interpretation_payload(cases, case):
    return {'text': case_text(case), 'dataMode': 'demo',
            'allowedDestinations': cases['destinationSets'][case['set']]}


def timed(call, payload):
    started = time.perf_counter()
    try:
        out = call(payload)
    except Exception:  # 어댑터 예외는 백엔드처럼 실패로 본다.
        out = None
    return out, time.perf_counter() - started


def run(cases=None, adapter=None):
    """(사례 ID, 묶음, 통과 여부, 기대, 실제, 소요 초) 목록을 반환한다."""
    cases = cases or load_cases()
    adapter = adapter or RuleBasedAIAdapter()
    rows = []
    for case in cases['interpretation']:
        out, seconds = timed(adapter.interpret_destination, interpretation_payload(cases, case))
        expected = (case['status'], case['ids'])
        actual = (out['status'], out['candidateDestinationIds']) if type(out) is dict else out
        rows.append((case['id'], case['group'], expected == actual, expected, actual, seconds))
    for case in cases['malformedInterpretation']:
        out, seconds = timed(adapter.interpret_destination, case['payload'])
        actual = out.get('status') if type(out) is dict else out
        rows.append((case['id'], '입력 오류', actual == 'unavailable', 'unavailable', actual, seconds))
    for case in cases['guidance']:
        out, seconds = timed(adapter.choose_guidance, case['payload'])
        expected = (case['status'], case['templates'])
        actual = ((out['status'], [s['templateId'] for s in out['steps']])
                  if type(out) is dict and type(out.get('steps')) is list else out)
        rows.append((case['id'], case['group'], expected == actual, expected, actual, seconds))
    return rows


def percentile(values, ratio):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * ratio))]


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', action='store_true', help='사례별 결과 출력')
    parser.add_argument('--adapter', help="평가할 어댑터 '모듈:클래스' (기본: 규칙 기준선)")
    args = parser.parse_args(argv)
    rows = run(adapter=load_adapter(args.adapter) if args.adapter else None)
    total, passed = Counter(), Counter()
    for key, group, ok, expected, actual, seconds in rows:
        total[group] += 1
        passed[group] += ok
        if args.v or not ok:
            print(f"{'PASS' if ok else 'FAIL'} {key} [{group}] 기대={expected} 실제={actual} {seconds * 1000:.1f}ms")
    for group in total:
        print(f'{group}: {passed[group]}/{total[group]}')
    seconds = [row[-1] for row in rows]
    over = sum(s > BUDGET_SECONDS for s in seconds)
    print(f'전체: {sum(passed.values())}/{sum(total.values())}')
    print(f'응답 시간: 중앙값 {percentile(seconds, 0.5) * 1000:.1f}ms, '
          f'95% {percentile(seconds, 0.95) * 1000:.1f}ms, 1초 초과 {over}건')
    return 0 if sum(passed.values()) == sum(total.values()) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
