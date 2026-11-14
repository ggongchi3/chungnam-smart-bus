from fastapi.testclient import TestClient
import pytest

from backend.config import Settings
from backend.main import create_app


@pytest.fixture
def speech_app():
    return create_app(Settings(database_url='sqlite:///:memory:'), transport_catalog='cheonan')


def test_forwards_browser_recording_to_transcriber(speech_app, monkeypatch):
    def recognize(recording, audio_format):
        assert recording == b'webm recording'
        assert audio_format == 'matroska'
        return '중앙시장 가고 싶어요'

    monkeypatch.setattr(speech_app.state.speech, 'transcribe', recognize)
    with TestClient(speech_app) as client:
        result = client.post('/api/v1/speech/transcriptions', content=b'webm recording',
                             headers={'Content-Type': 'audio/webm;codecs=opus'})
    assert result.status_code == 200
    assert result.json()['data'] == {'text': '중앙시장 가고 싶어요'}


@pytest.mark.parametrize('content_type,recording,status,code', [
    ('text/plain', b'recording', 415, 'UNSUPPORTED_AUDIO'),
    ('audio/webm', b'', 400, 'INVALID_AUDIO'),
    ('audio/webm', b'x' * (2 * 1024 * 1024 + 1), 413, 'SPEECH_TOO_LONG'),
], ids=['unsupported-format', 'empty', 'oversize'])
def test_rejects_invalid_recordings(speech_app, content_type, recording, status, code):
    with TestClient(speech_app) as client:
        result = client.post('/api/v1/speech/transcriptions', content=recording,
                             headers={'Content-Type': content_type})
    assert result.status_code == status
    assert result.json()['error']['code'] == code
