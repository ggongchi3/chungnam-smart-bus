"""cases.json으로 규칙 기준선을 평가한다. 표준 라이브러리만 사용한다.

    python ai/evaluation/run_eval.py          # 요약
    python ai/evaluation/run_eval.py -v       # 사례별 결과

수치는 이 합성 사례 묶음에서의 통과 수일 뿐이며 실제 사용자 표현의 정확도가 아니다.
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ai.adapter import RuleBasedAIAdapter  # noqa: E402

CASES_PATH = Path(__file__).with_name('cases.json')


def load_cases(path=CASES_PATH):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def case_text(case):
    if 'textRepeat' in case:
        piece, count = case['textRepeat']
        return piece * count
    return case['text']


def interpretation_payload(cases, case):
    return {'text': case_text(case), 'dataMode': 'demo',
            'allowedDestinations': cases['destinationSets'][case['set']]}


def run(cases=None):
    """(사례 ID, 묶음, 통과 여부, 기대, 실제) 목록을 반환한다."""
    cases = cases or load_cases()
    adapter = RuleBasedAIAdapter()
    rows = []
    for case in cases['interpretation']:
        out = adapter.interpret_destination(interpretation_payload(cases, case))
        expected = (case['status'], case['ids'])
        actual = (out['status'], out['candidateDestinationIds'])
        rows.append((case['id'], case['group'], expected == actual, expected, actual))
    for case in cases['malformedInterpretation']:
        out = adapter.interpret_destination(case['payload'])
        rows.append((case['id'], '입력 오류', out['status'] == 'unavailable', 'unavailable', out['status']))
    for case in cases['guidance']:
        out = adapter.choose_guidance(case['payload'])
        expected = (case['status'], case['templates'])
        actual = (out['status'], [s['templateId'] for s in out['steps']])
        rows.append((case['id'], case['group'], expected == actual, expected, actual))
    return rows


def main(argv):
    rows = run()
    total, passed = Counter(), Counter()
    for key, group, ok, expected, actual in rows:
        total[group] += 1
        passed[group] += ok
        if '-v' in argv or not ok:
            print(f"{'PASS' if ok else 'FAIL'} {key} [{group}] 기대={expected} 실제={actual}")
    for group in total:
        print(f'{group}: {passed[group]}/{total[group]}')
    print(f'전체: {sum(passed.values())}/{sum(total.values())}')
    return 0 if sum(passed.values()) == sum(total.values()) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
