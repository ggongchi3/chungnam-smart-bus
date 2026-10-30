"""백엔드 연결 확인. 백엔드 의존성(backend/requirements.lock)이 설치된 환경에서 실행한다.

    python -m unittest ai.evaluation.test_backend_integration

백엔드 코드를 바꾸지 않고 create_app(ai_adapter=...)에 어댑터를 주입해 공개 API로 확인한다.
의존성이 없으면 건너뛴다.
"""
import time
import unittest
from datetime import datetime, timedelta, timezone

try:
    from fastapi.testclient import TestClient

    from backend.config import Settings
    from backend.integrations.providers import DemoProvider
    from backend.main import create_app
except ImportError:  # pragma: no cover - 백엔드 환경이 없을 때
    create_app = None

from ai.adapter import RuleBasedAIAdapter


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 26, 5, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@unittest.skipIf(create_app is None, '백엔드 의존성 미설치')
class BackendCase(unittest.TestCase):
    adapter = None

    def setUp(self):
        self.clock = Clock()
        app = create_app(Settings(database_url='sqlite:///:memory:', data_mode='demo'), clock=self.clock,
                         provider=DemoProvider('normal'), ai_adapter=self.adapter)
        self.client = self.enterContext(TestClient(app))

    def interpret(self, text):
        response = self.client.post('/api/v1/destination-interpretations',
                                    json={'originStationId': 'demo-stop-001', 'text': text})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['data']

    def selection(self, destination='001'):
        response = self.client.post('/api/v1/route-searches', json={
            'originStationId': 'demo-stop-001', 'destinationId': 'demo-destination-' + destination,
            'departAt': self.clock.now.isoformat()})
        data = response.json()['data']
        option = data['routeOptions'][0]
        return {'routeSearchId': data['routeSearchId'], 'routeOptionId': option['routeOptionId'],
                'expectedRouteSnapshotVersion': option['routeSnapshotVersion']}

    def guidance(self, destination='001'):
        response = self.client.post('/api/v1/easy-guidance', json=self.selection(destination))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['data']


class RuleBasedAdapterTest(BackendCase):
    adapter = RuleBasedAIAdapter()

    def test_interpretation_statuses(self):
        cases = [('큰 병원에 가고 싶어요', 'matched', ['demo-destination-001']),
                 ('버스터미널', 'matched', ['demo-destination-003']),
                 ('병원이랑 시장', 'needs_confirmation', ['demo-destination-001', 'demo-destination-002']),
                 ('도서관', 'no_match', [])]
        for text, status, ids in cases:
            with self.subTest(text=text):
                data = self.interpret(text)
                self.assertEqual(data['status'], status)
                self.assertEqual([c['destinationId'] for c in data['candidates']], ids)

    def test_candidates_use_backend_facts(self):
        candidate = self.interpret('시장')['candidates'][0]
        self.assertEqual(candidate['name'], '시연 시장')
        self.assertEqual(candidate['category'], 'market')

    def test_guidance_is_ai_assisted_with_same_facts(self):
        for destination in ('001', '002', '003'):
            with self.subTest(destination=destination):
                data = self.guidance(destination)
                self.assertEqual(data['mode'], 'ai_assisted')
                self.assertTrue(data['steps'])

    def test_print_guide_uses_same_version(self):
        body = self.selection('003')
        printed = self.client.post('/api/v1/print-guides', json=body).json()['data']
        self.assertEqual(printed['guidance']['routeSnapshotVersion'], body['expectedRouteSnapshotVersion'])


class NoAdapterTest(BackendCase):
    adapter = None

    def test_fallback_without_ai(self):
        self.assertEqual(self.interpret('병원')['status'], 'unavailable')
        self.assertEqual(self.guidance()['mode'], 'template_fallback')


class SameTextTest(unittest.TestCase):
    @unittest.skipIf(create_app is None, '백엔드 의존성 미설치')
    def test_ai_does_not_change_guidance_text(self):
        texts = {}
        for name, adapter in (('none', None), ('rule', RuleBasedAIAdapter())):
            case = type('Case', (BackendCase,), {'adapter': adapter, 'runTest': lambda self: None})()
            case.setUp()
            try:
                texts[name] = [[s['text'] for s in case.guidance(d)['steps']] for d in ('001', '002', '003')]
            finally:
                case.doCleanups()
        self.assertEqual(texts['none'], texts['rule'])


class FakeAdapter(RuleBasedAIAdapter):
    """규칙 어댑터 결과를 일부러 망가뜨려 백엔드 검증을 확인한다."""

    def __init__(self, interpret=None, guide=None):
        self._interpret, self._guide = interpret, guide

    def interpret_destination(self, payload):
        out = super().interpret_destination(payload)
        return self._interpret(out) if self._interpret else out

    def choose_guidance(self, payload):
        out = super().choose_guidance(payload)
        return self._guide(out) if self._guide else out


def slow(out):
    time.sleep(1.2)
    return out


def boom(out):
    raise RuntimeError('adapter failure')


BAD_INTERPRETATIONS = {
    '목록 밖 ID': lambda o: {**o, 'candidateDestinationIds': ['demo-destination-999']},
    '중복 ID': lambda o: {**o, 'status': 'needs_confirmation',
                          'candidateDestinationIds': o['candidateDestinationIds'] * 2},
    'matched인데 후보 2개': lambda o: {**o, 'candidateDestinationIds': ['demo-destination-001',
                                                                         'demo-destination-002']},
    '시간초과': slow,
    '예외': boom,
    'NaN': lambda o: {**o, 'score': float('nan')},
}

BAD_GUIDANCE = {
    '버전 불일치': lambda o: {**o, 'routeSnapshotVersion': 'other-version'},
    '구간 순서 변경': lambda o: {**o, 'steps': o['steps'][::-1]},
    '구간 누락': lambda o: {**o, 'steps': o['steps'][:-1]},
    '구간 추가': lambda o: {**o, 'steps': o['steps'] + o['steps'][:1]},
    '틀린 템플릿': lambda o: {**o, 'steps': [{**s, 'templateId': 'bus.short'} for s in o['steps']]},
    '시간초과': slow,
    '예외': boom,
}


@unittest.skipIf(create_app is None, '백엔드 의존성 미설치')
class BackendRejectsBadOutputTest(unittest.TestCase):
    def run_case(self, adapter, call):
        case = type('Case', (BackendCase,), {'adapter': adapter, 'runTest': lambda self: None})()
        case.setUp()
        try:
            started = time.perf_counter()
            data = call(case)
            return data, time.perf_counter() - started
        finally:
            case.doCleanups()

    def test_bad_interpretation_falls_back(self):
        for name, broken in BAD_INTERPRETATIONS.items():
            with self.subTest(case=name):
                data, elapsed = self.run_case(FakeAdapter(interpret=broken), lambda c: c.interpret('병원'))
                self.assertEqual(data['status'], 'unavailable')
                self.assertEqual(data['candidates'], [])
                self.assertLess(elapsed, 1.5)

    def test_bad_guidance_falls_back(self):
        for name, broken in BAD_GUIDANCE.items():
            with self.subTest(case=name):
                data, elapsed = self.run_case(FakeAdapter(guide=broken), lambda c: c.guidance('003'))
                self.assertEqual(data['mode'], 'template_fallback')
                self.assertLess(elapsed, 1.5)


if __name__ == '__main__':
    unittest.main()
