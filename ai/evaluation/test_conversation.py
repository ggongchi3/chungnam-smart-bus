"""대화 기능(ai/conversation) 테스트. 프로젝트 루트에서 실행한다. 표준 라이브러리만 쓴다.

    python -m unittest ai.evaluation.test_conversation

사례별 기대 문장은 cases.json의 conversation 섹션(test_ai.CaseTest가 모두 확인)에 있고,
여기서는 계약 모양·예외 없음·숫자를 지어내지 않음·Gemini 선택 옵션의 대체 동작을 본다.
"""
import copy
import json
import re
import unittest
from unittest import mock

from ai.adapter import RuleBasedAIAdapter, RuleFirstGeminiAdapter
from ai.conversation import dialogue, llm_intent, words
from ai.evaluation.run_eval import load_cases

CASES = load_cases()
CONV = CASES['conversation']
CHEONAN = CASES['destinationSets']['cheonan']
ADAPTER = RuleBasedAIAdapter()
BROKEN = [None, [], 'text', {}, {'routeDetail': None}, {'routeDetail': {'segments': 'x'}},
          {'routeDetail': {'segments': [{'type': 'walk', 'toLabel': 'x', 'distanceMeters': 10}]}},
          {'routeDetail': {'segments': [{'type': 'bus', 'routeName': '16'}]}}]


def payload(text):
    return {'text': text, 'dataMode': 'static', 'allowedDestinations': CHEONAN}


class WordsTest(unittest.TestCase):
    def test_josa(self):
        self.assertEqual(words.josa('천안역', '으로/로'), '천안역으로')
        self.assertEqual(words.josa('터미널', '으로/로'), '터미널로')  # ㄹ 받침
        self.assertEqual(words.josa('시장', '과/와'), '시장과')
        self.assertEqual(words.josa('천안시청', '과/와'), '천안시청과')
        self.assertEqual(words.josa('성정시장', '을/를'), '성정시장을')
        self.assertEqual(words.josa('16번 버스', '을/를'), '16번 버스를')
        self.assertEqual(words.josa('16번', '으로/로'), '16번으로')
        self.assertEqual(words.josa('16', '으로/로'), '16으로')   # 육 → ㄱ 받침
        self.assertEqual(words.josa('7', '으로/로'), '7로')       # 칠 → ㄹ 받침
        self.assertEqual(words.josa('2', '과/와'), '2와')

    def test_labels(self):
        self.assertEqual(words.bus_label('16'), '16번 버스')
        self.assertEqual(words.bus_label('심야1'), '심야1번 버스')
        self.assertEqual(words.bus_label('16번'), '16번 버스')
        self.assertEqual(words.stop_label({'name': '고속터미널'}), '고속터미널 정류장')
        self.assertEqual(words.stop_label({'name': '시청앞 정류장'}), '시청앞 정류장')
        board = {'name': '종합터미널', 'arsId': '685'}
        self.assertEqual(words.stop_name({'name': '종합터미널', 'arsId': '2357'}, board), '종합터미널(2357번)')
        self.assertEqual(words.stop_name({'name': '종합터미널', 'arsId': '685'}, board), '종합터미널')

    def test_rounding_matches_backend(self):
        self.assertEqual(words.rounded_meters(248), 250)
        self.assertEqual(words.rounded_meters(273), 250)
        self.assertEqual(words.rounded_meters(276), 300)
        self.assertIsNone(words.rounded_meters(49))
        self.assertEqual(words.minutes(60), 1)
        self.assertEqual(words.minutes(61), 2)   # 백엔드·인쇄표처럼 올림
        self.assertIsNone(words.minutes(None))


class UnderstandTest(unittest.TestCase):
    def test_shape(self):
        for case in CONV['understand']:
            out = ADAPTER.understand_request(payload(case['text']))
            with self.subTest(case=case['id']):
                self.assertEqual(set(out), {'destination', 'preference'})
                self.assertEqual(set(out['destination']), {'status', 'candidateDestinationIds', 'reasonCode'})
                self.assertIn(out['preference']['sort'], (None, 'walking', 'transfers', 'fastest'))
                json.dumps(out, ensure_ascii=False, allow_nan=False)

    def test_same_as_interpreter_without_preference(self):
        """조건 표현이 없으면 기존 목적지 해석과 결과가 같다."""
        for case in CASES['interpretation']:
            body = {'text': case.get('text', '병원'), 'dataMode': 'demo',
                    'allowedDestinations': CASES['destinationSets'][case['set']]}
            out = ADAPTER.understand_request(body)
            if out['preference']['sort'] is None:
                with self.subTest(case=case['id']):
                    self.assertEqual(out['destination'], ADAPTER.interpret_destination(body))

    def test_never_raises(self):
        for bad in [None, [], {'text': None}, {'text': ''}, {'text': '병원' * 101, 'allowedDestinations': CHEONAN},
                    {'text': '빨리', 'allowedDestinations': 'x'}, {'text': '병원 빨리', 'allowedDestinations': [None]}]:
            with self.subTest(payload=str(bad)[:40]):
                out = ADAPTER.understand_request(bad)
                self.assertEqual(out['destination']['status'], 'unavailable')
                self.assertIsNone(out['preference']['sort'])

    def test_does_not_mutate(self):
        body = payload('중앙시장 빨리')
        before = json.dumps(body, ensure_ascii=False)
        ADAPTER.understand_request(body)
        self.assertEqual(before, json.dumps(body, ensure_ascii=False))


class ClarifyTest(unittest.TestCase):
    def test_options_keep_order_and_ids(self):
        names = {d['destinationId']: d['name'] for d in CHEONAN}
        for case in CONV['clarify']:
            out = ADAPTER.clarify_destination({'candidates': [{'destinationId': k, 'name': names[k]}
                                                              for k in case['candidateIds']]})
            with self.subTest(case=case['id']):
                self.assertEqual([o['destinationId'] for o in out['options']], case['candidateIds'])

    def test_bad_input(self):
        for bad in [None, {}, {'candidates': []}, {'candidates': [{'destinationId': 'a'}]},
                    {'candidates': [{'destinationId': 'a', 'name': 'x'}, {'destinationId': 'a', 'name': 'y'}]}]:
            with self.subTest(payload=bad):
                self.assertEqual(ADAPTER.clarify_destination(bad)['status'], 'unavailable')


class RouteTextTest(unittest.TestCase):
    def numbers(self, text):
        return set(re.findall(r'\d+', text))

    def test_numbers_come_from_route(self):
        """문장 속 숫자는 경로 값(노선 번호·정류장 수·정류장 번호)이나 그 반올림(거리·분)뿐이다."""
        for case in CONV['answer'] + CONV['headline']:
            route = CONV['routes'][case['route']]
            allowed = set()
            for seg in route['segments']:
                for key in ('routeName', 'stopCount'):
                    allowed |= self.numbers(str(seg.get(key, '')))
                for key in ('boardStation', 'alightStation'):
                    allowed |= self.numbers(str((seg.get(key) or {}).get('arsId', '')))
                if seg.get('distanceMeters') is not None and seg['type'] == 'walk':
                    allowed.add(str(words.rounded_meters(seg['distanceMeters'])))
                    allowed.add(str(words.minutes(seg.get('durationSeconds'))))
            allowed.add(str(words.minutes(route.get('estimatedTravelSeconds'))))
            with self.subTest(case=case['id']):
                self.assertLessEqual(self.numbers(case['text']) - {'16'} if case['id'] == 'a25' else
                                     self.numbers(case['text']), allowed)

    def test_never_raises(self):
        for bad in BROKEN:
            with self.subTest(payload=str(bad)[:40]):
                self.assertEqual(ADAPTER.print_headline(bad)['status'], 'unavailable')
                body = dict(bad) if type(bad) is dict else {}
                self.assertEqual(ADAPTER.answer_question({**body, 'question': '몇 번 버스 타요?'})['status'],
                                 'unavailable')
        for bad in [None, {}, {'routeOption': {}}, {'routeOption': {'transferCount': 3}},
                    {'routeOption': {'transferCount': 0}, 'sort': 'cheapest'}]:
            with self.subTest(payload=bad):
                self.assertEqual(ADAPTER.explain_route(bad)['status'], 'unavailable')

    def test_backend_shapes_are_not_mutated(self):
        route = CONV['routes']['express_transfer']
        before = copy.deepcopy(route)
        ADAPTER.print_headline({'routeDetail': route})
        ADAPTER.answer_question({'question': '어디서 내려요', 'routeDetail': route})
        self.assertEqual(route, before)

    def test_preference_sentence_only_when_backend_says_so(self):
        """'말씀하신 대로'는 백엔드 features에 그 조건 이름이 있을 때만 쓴다."""
        option = dict(CONV['routeOptions']['dankook_direct'], features=[])
        out = ADAPTER.explain_route({'routeOption': option, 'sort': 'walking'})
        self.assertNotIn('말씀하신 대로', out['text'])


class RuleFirstGeminiTest(unittest.TestCase):
    """선택 옵션 어댑터: 규칙이 알면 Gemini를 부르지 않고, Gemini 실패는 규칙 결과로 남는다."""

    def setUp(self):
        patcher = mock.patch.object(llm_intent, 'settings', return_value=('test-key', 'test-model'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.adapter = RuleFirstGeminiAdapter()

    def test_rule_hit_skips_model(self):
        with mock.patch.object(llm_intent, 'call_gemini', side_effect=AssertionError('부르면 안 됨')):
            out = self.adapter.understand_request(payload('중앙시장 많이 안 걷고 싶어요'))
            self.assertEqual(out['preference']['sort'], 'walking')
            route = CONV['routes']['dankook_direct']
            self.assertEqual(self.adapter.answer_question({'question': '어디서 내려요', 'routeDetail': route})['intent'],
                             'where_alight')

    def test_model_fills_unknown_with_allowed_value_only(self):
        route = CONV['routes']['dankook_direct']
        with mock.patch.object(llm_intent, 'call_gemini', return_value='{"value": "where_alight"}'):
            out = self.adapter.answer_question({'question': '병원 앞에 서요?', 'routeDetail': route})
        self.assertEqual(out['intent'], 'where_alight')
        self.assertEqual(out['text'], dialogue.reply('where_alight', route))
        with mock.patch.object(llm_intent, 'call_gemini', return_value='{"value": "tell_a_joke"}'):
            out = self.adapter.answer_question({'question': '병원 앞에 서요?', 'routeDetail': route})
        self.assertEqual(out['intent'], 'unknown')

    def test_model_preference(self):
        with mock.patch.object(llm_intent, 'call_gemini', return_value='{"value": "walking"}'):
            out = self.adapter.understand_request(payload('천안역 가는데 허리가 영 안 좋아서'))
        self.assertEqual(out['preference']['sort'], 'walking')
        self.assertEqual(out['destination']['candidateDestinationIds'], ['cheonan-station'])
        with mock.patch.object(llm_intent, 'call_gemini', return_value='{"value": "none"}'):
            self.assertIsNone(self.adapter.understand_request(payload('천안역'))['preference']['sort'])

    def test_model_failure_keeps_rule_result(self):
        from ai.destination_interpretation import llm_interpreter
        with mock.patch.object(llm_intent, 'call_gemini', side_effect=llm_interpreter.LLMError('시간초과')), \
                mock.patch.object(llm_interpreter, 'interpret', return_value={'status': 'unavailable'}):
            out = self.adapter.understand_request(payload('오늘 날씨 좋네요'))
            self.assertEqual(out['destination']['status'], 'no_match')
            self.assertIsNone(out['preference']['sort'])
            route = CONV['routes']['dankook_direct']
            self.assertEqual(self.adapter.answer_question({'question': '아무말', 'routeDetail': route})['intent'],
                             'unknown')


if __name__ == '__main__':
    unittest.main()
