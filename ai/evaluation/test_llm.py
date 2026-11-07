"""Gemini 어댑터의 검증·대체 동작 테스트. 네트워크·키 없이 모델 응답을 흉내 낸다.

    python -m unittest ai.evaluation.test_llm
"""
import json
import unittest
from unittest import mock

from ai.adapter import GeminiAIAdapter
from ai.destination_interpretation import llm_interpreter as llm
from ai.destination_interpretation.interpreter import REASON_CODES

DESTINATIONS = [
    {'destinationId': 'demo-destination-001', 'name': '시연 병원', 'aliases': ['병원']},
    {'destinationId': 'demo-destination-002', 'name': '시연 시장', 'aliases': ['시장']},
]
PAYLOAD = {'text': '큰 병원', 'dataMode': 'demo', 'allowedDestinations': DESTINATIONS}


def replying(obj):
    raw = obj if type(obj) is str else json.dumps(obj)
    return lambda body, key, model: raw


def failing(body, key, model):
    raise llm.LLMError('시간초과')


class GeminiInterpretTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(llm, 'settings', return_value=('test-key', 'test-model'))
        patcher.start()
        self.addCleanup(patcher.stop)

    def check(self, reply, status, ids=()):
        out = llm.interpret(PAYLOAD, call=reply)
        self.assertEqual(out['status'], status)
        self.assertEqual(out['candidateDestinationIds'], list(ids))
        self.assertEqual(out['reasonCode'], REASON_CODES[status])

    def test_valid_outputs(self):
        self.check(replying({'status': 'matched', 'candidateDestinationIds': ['demo-destination-001']}),
                   'matched', ['demo-destination-001'])
        self.check(replying({'status': 'needs_confirmation',
                             'candidateDestinationIds': ['demo-destination-002', 'demo-destination-001']}),
                   'needs_confirmation', ['demo-destination-001', 'demo-destination-002'])
        self.check(replying({'status': 'no_match', 'candidateDestinationIds': []}), 'no_match')

    def test_unsafe_outputs_become_unavailable(self):
        bad = [
            {'status': 'matched', 'candidateDestinationIds': ['demo-destination-999']},  # 목록 밖
            {'status': 'matched', 'candidateDestinationIds': ['demo-destination-001', 'demo-destination-002']},
            {'status': 'matched', 'candidateDestinationIds': []},
            {'status': 'no_match', 'candidateDestinationIds': ['demo-destination-001']},
            {'status': 'needs_confirmation', 'candidateDestinationIds': []},
            {'status': 'unavailable', 'candidateDestinationIds': []},
            {'status': 'matched', 'candidateDestinationIds': 'demo-destination-001'},
            ['demo-destination-001'],
            '이건 JSON이 아님',
        ]
        for reply in bad:
            with self.subTest(reply=reply):
                self.check(replying(reply), 'unavailable')

    def test_call_failure_becomes_unavailable(self):
        self.check(failing, 'unavailable')

    def test_bad_input_does_not_call_model(self):
        called = mock.Mock()
        for payload in (None, {'text': '', 'allowedDestinations': DESTINATIONS},
                        {'text': '가' * 201, 'allowedDestinations': DESTINATIONS},
                        {'text': '병원', 'allowedDestinations': 'x'}):
            with self.subTest(payload=payload):
                self.assertEqual(llm.interpret(payload, call=called)['status'], 'unavailable')
        called.assert_not_called()

    def test_request_sends_only_text_and_candidates(self):
        body = llm.build_request('큰 병원', DESTINATIONS)
        sent = json.loads(body['contents'][0]['parts'][0]['text'])
        self.assertEqual(set(sent), {'candidates', 'userText'})
        self.assertEqual(set(sent['candidates'][0]), {'destinationId', 'name', 'aliases'})


class GeminiSettingsTest(unittest.TestCase):
    def test_missing_key_is_unavailable_without_network(self):
        with mock.patch.object(llm, 'settings', return_value=('', 'm')), \
                mock.patch('urllib.request.urlopen') as urlopen:
            out = GeminiAIAdapter().interpret_destination(PAYLOAD)
        self.assertEqual(out['status'], 'unavailable')
        urlopen.assert_not_called()

    def test_env_file_parsing(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.env'
            path.write_text('# 주석\nGEMINI_API_KEY="abc"\nGEMINI_MODEL=\n', encoding='utf-8')
            self.assertEqual(llm.load_env(path), {'GEMINI_API_KEY': 'abc', 'GEMINI_MODEL': ''})

    def test_guidance_stays_rule_based(self):
        from ai.easy_guidance import selector
        payload = {'routeSnapshotVersion': 'v1', 'segments': []}
        self.assertEqual(GeminiAIAdapter().choose_guidance(payload), selector.choose(payload))


if __name__ == '__main__':
    unittest.main()
