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
                 ('병원 말고 시장', 'matched', ['demo-destination-002']),
                 ('벙원', 'needs_confirmation', ['demo-destination-001']),  # 후보 1개 확인 요청
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
    '틀린 템플릿': lambda o: {**o, 'steps': [{**s, 'templateId': 'bus.split'} for s in o['steps']]},
    '시간초과': slow,
    '예외': boom,
}


@unittest.skipIf(create_app is None, '백엔드 의존성 미설치')
class WalkDurationTextTest(unittest.TestCase):
    """도보 안내가 화면·인쇄와 같은 분 단위 올림을 적용하는지 확인한다."""

    def test_walk_duration_wording(self):
        from backend.models.schemas import Walk
        from backend.services.ai import template_text
        cases = [(45, '이동 시간은 45초입니다.'), (60, '이동 시간은 약 1분입니다.'),
                 (89, '이동 시간은 약 2분입니다.'), (90, '이동 시간은 약 2분입니다.'),
                 (420, '이동 시간은 약 7분입니다.')]
        for seconds, expected in cases:
            with self.subTest(seconds=seconds):
                walk = Walk(segmentId='seg-walk', fromLabel='시연 병원 앞 정류장', toLabel='시연 병원',
                            distanceMeters=350, durationSeconds=seconds)
                text = template_text(walk)
                self.assertTrue(text.endswith(expected), text)
                self.assertIn('거리는 350미터입니다.', text)
                self.assertEqual(walk.durationSeconds, seconds)  # 응답 필드는 초 그대로


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


class RecordingAdapter(RuleBasedAIAdapter):
    """백엔드가 AI에 넘긴 allowedDestinations를 기록한다."""
    seen = None

    def interpret_destination(self, payload):
        RecordingAdapter.seen = payload['allowedDestinations']
        return super().interpret_destination(payload)


@unittest.skipIf(create_app is None, '백엔드 의존성 미설치')
class CheonanConversationTest(unittest.TestCase):
    """실제 천안 정적 데이터로 대화 기능을 이어 본다: 말 → 목적지·조건 → 경로 검색 → 이유·답·한 줄.

    백엔드는 아직 대화 기능을 부르지 않는다. 여기서는 백엔드 응답을 그대로 어댑터에 넣어
    형식이 맞는지만 확인한다(제안: ai/contracts/README.md).
    """
    ORIGIN = 'cheonan-stop-285000685'

    def setUp(self):
        from ai.evaluation.run_eval import load_cases
        self.cases = load_cases()
        app = create_app(Settings(database_url='sqlite:///:memory:', data_mode='static'),
                         ai_adapter=RecordingAdapter(), place_catalog='cheonan', transport_catalog='cheonan')
        self.client = self.enterContext(TestClient(app))
        self.adapter = RuleBasedAIAdapter()

    def post(self, path, body):
        response = self.client.post('/api/v1' + path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['data']

    def test_cases_use_backend_allowed_destinations(self):
        """cases.json의 cheonan 목록이 백엔드가 AI에 넘기는 목록과 같아야 평가가 의미 있다."""
        self.post('/destination-interpretations', {'originStationId': self.ORIGIN, 'text': '시장'})
        def shape(items):  # 순서는 백엔드가 다시 맞추므로 내용만 비교
            return {d['destinationId']: (d['name'], sorted(d['aliases'])) for d in items}
        self.assertEqual(shape(RecordingAdapter.seen), shape(self.cases['destinationSets']['cheonan']))

    def test_end_to_end_sentences(self):
        allowed = self.cases['destinationSets']['cheonan']
        examples = [
            ('중앙시장 가는데 많이 안 걷고 싶어요', 'cheonan-central-market', True),
            ('갈아타기 싫어요 단국대병원', 'cheonan-dankook-hospital', True),
            ('성정시장 급해요', 'cheonan-seongjeong-market', False),
            ('고속터미널 가요', 'cheonan-express-terminal', False),
        ]
        for text, destination_id, has_route in examples:
            with self.subTest(text=text):
                understood = self.adapter.understand_request({'text': text, 'dataMode': 'static',
                                                              'allowedDestinations': allowed})
                self.assertEqual(understood['destination']['status'], 'matched')
                self.assertEqual(understood['destination']['candidateDestinationIds'], [destination_id])
                sort = understood['preference']['sort'] or 'transfers'
                search = self.post('/route-searches', {
                    'originStationId': self.ORIGIN, 'destinationId': destination_id,
                    'departAt': datetime.now(timezone.utc).isoformat(), 'sort': sort})
                self.assertEqual(search['sortedBy'], sort)
                if not has_route:
                    self.assertEqual(search['routeOptions'], [])
                    continue
                self.assertTrue(search['routeOptions'])
                option = search['routeOptions'][0]
                reason = self.adapter.explain_route({'routeOption': option, 'sort': understood['preference']['sort']})
                self.assertEqual(reason['status'], 'ok', option)
                detail = self.client.get(f"/api/v1/route-searches/{search['routeSearchId']}/options/"
                                         f"{option['routeOptionId']}").json()['data']
                headline = self.adapter.print_headline({'routeDetail': detail})
                self.assertEqual(headline['status'], 'ok')
                self.assertIn(option['routeNames'][0], headline['text'])
                for question in ['몇 번 버스 타요?', '어디서 내려요?', '얼마나 걸어요?', '얼마나 걸려요?']:
                    answer = self.adapter.answer_question({'question': question, 'routeDetail': detail})
                    self.assertEqual(answer['status'], 'ok', (question, answer))

    def test_clarify_uses_backend_candidates(self):
        data = self.post('/destination-interpretations', {'originStationId': self.ORIGIN, 'text': '터미널 가고 싶어요'})
        self.assertEqual(data['status'], 'needs_confirmation')
        out = self.adapter.clarify_destination({'candidates': data['candidates']})
        self.assertEqual(out['question'], '천안종합버스터미널과 천안고속버스터미널 중 어디로 가시나요?')
        self.assertEqual([o['destinationId'] for o in out['options']], [c['destinationId'] for c in data['candidates']])


if __name__ == '__main__':
    unittest.main()
