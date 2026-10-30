"""AI 기준선 테스트. 프로젝트 루트에서 실행한다.

    python -m unittest discover -s ai/evaluation -t .
"""
import json
import time
import unittest

from ai.adapter import RuleBasedAIAdapter, interpreter, selector
from ai.evaluation.run_eval import interpretation_payload, load_cases, run

CASES = load_cases()
ADAPTER = RuleBasedAIAdapter()


class CaseTest(unittest.TestCase):
    def test_every_case_passes(self):
        for key, group, ok, expected, actual, _ in run(CASES):
            with self.subTest(case=key, group=group):
                self.assertTrue(ok, f'기대={expected} 실제={actual}')


class InterpretationContractTest(unittest.TestCase):
    def test_output_shape_and_allow_list(self):
        for case in CASES['interpretation']:
            payload = interpretation_payload(CASES, case)
            out = ADAPTER.interpret_destination(payload)
            allowed = [d['destinationId'] for d in payload['allowedDestinations']]
            with self.subTest(case=case['id']):
                self.assertEqual(set(out), {'status', 'candidateDestinationIds', 'reasonCode'})
                self.assertTrue(set(out['candidateDestinationIds']) <= set(allowed))
                self.assertEqual(len(out['candidateDestinationIds']), len(set(out['candidateDestinationIds'])))
                self.assertEqual(out['reasonCode'], interpreter.REASON_CODES[out['status']])
                # 백엔드 AIBoundary와 같이 JSON 직렬화 가능해야 한다.
                json.dumps(out, ensure_ascii=False, allow_nan=False)

    def test_does_not_mutate_payload(self):
        payload = interpretation_payload(CASES, CASES['interpretation'][0])
        before = json.dumps(payload, ensure_ascii=False)
        ADAPTER.interpret_destination(payload)
        self.assertEqual(before, json.dumps(payload, ensure_ascii=False))

    def test_never_raises(self):
        for payload in [None, [], 'text', {'text': None}, {'text': '병원', 'allowedDestinations': [None]},
                        {'text': '병원', 'allowedDestinations': [{'destinationId': 1, 'name': 'x'}]}]:
            with self.subTest(payload=payload):
                self.assertEqual(ADAPTER.interpret_destination(payload)['status'], 'unavailable')


class GuidanceContractTest(unittest.TestCase):
    def test_keeps_segment_order_and_version(self):
        for case in CASES['guidance']:
            out = ADAPTER.choose_guidance(case['payload'])
            if out['status'] != 'ok':
                continue
            payload = case['payload']
            with self.subTest(case=case['id']):
                self.assertEqual(out['routeSnapshotVersion'], payload['routeSnapshotVersion'])
                self.assertEqual([s['segmentId'] for s in out['steps']],
                                 [s['segmentId'] for s in payload['verifiedSegments']])
                for step, segment in zip(out['steps'], payload['verifiedSegments']):
                    self.assertIn(step['templateId'], segment['allowedTemplateIds'])

    def test_proposal_templates_are_never_active(self):
        catalog = json.loads(selector.CATALOG_PATH.read_text(encoding='utf-8'))
        proposals = {t['templateId'] for t in catalog['templates'] if t['status'] == 'proposal'}
        active = {t for ids in selector.ACTIVE.values() for t in ids}
        self.assertFalse(proposals & active)
        self.assertEqual(selector.ACTIVE, {'bus': ['bus.basic'], 'walk': ['walk.basic'],
                                           'transfer': ['transfer.basic']})


class BudgetTest(unittest.TestCase):
    def test_well_within_one_second_budget(self):
        payload = interpretation_payload(CASES, {'set': 'demo', 'textRepeat': ['병원 시장 ', 18]})
        started = time.perf_counter()
        for _ in range(100):
            ADAPTER.interpret_destination(payload)
            ADAPTER.choose_guidance(CASES['guidance'][1]['payload'])
        self.assertLess((time.perf_counter() - started) / 100, 0.05)


if __name__ == '__main__':
    unittest.main()
