"""Real AI adapter integration and the public interpretation contract."""
import runpy

import pytest
from fastapi.testclient import TestClient

from ai.adapter import RuleBasedAIAdapter
from backend import main
from backend.integrations.providers import DemoProvider
from backend.tests.conftest import Clock, selection


INTERPRET_PATH = '/api/v1/destination-interpretations'


@pytest.mark.parametrize('text,status,ids,reason', [
    ('큰 병원에 가고 싶어요', 'matched', ['demo-destination-001'], 'MATCHED'),
    ('병원이랑 시장', 'needs_confirmation',
     ['demo-destination-001', 'demo-destination-002'], 'USER_CONFIRMATION_REQUIRED'),
    ('벙원', 'needs_confirmation', ['demo-destination-001'], 'USER_CONFIRMATION_REQUIRED'),
    ('도서관', 'no_match', [], 'NO_REGISTERED_MATCH'),
])
def test_real_adapter_preserves_status_candidates_and_public_reason(make_app, text, status, ids, reason):
    app, client, _, _ = make_app(adapter=RuleBasedAIAdapter())
    response = client.post(INTERPRET_PATH, json={'originStationId': 'demo-stop-001', 'text': text})
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['status'] == status
    assert data['reasonCode'] == reason
    assert [candidate['destinationId'] for candidate in data['candidates']] == ids
    registered = client.get('/api/v1/destinations', params={'originStationId': 'demo-stop-001'}).json()['data']
    facts = {candidate['destinationId']: candidate for candidate in registered['destinations']}
    assert data['candidates'] == [facts[key] for key in ids]


@pytest.mark.parametrize('status,ids,reason', [
    ('matched', ['demo-destination-001'], 'MATCHED'),
    ('needs_confirmation', ['demo-destination-001'], 'USER_CONFIRMATION_REQUIRED'),
    ('no_match', [], 'NO_REGISTERED_MATCH'),
    ('unavailable', [], 'AI_UNAVAILABLE'),
])
def test_public_reason_is_owned_by_backend_even_when_adapter_reason_is_wrong(make_app, status, ids, reason):
    class Adapter:
        def interpret_destination(self, payload):
            return {'status': status, 'candidateDestinationIds': ids, 'reasonCode': '<untrusted explanation>'}

    _, client, _, _ = make_app(adapter=Adapter())
    response = client.post(INTERPRET_PATH, json={'originStationId': 'demo-stop-001', 'text': '병원'})
    assert response.status_code == 200, response.text
    assert response.json()['data']['status'] == status
    assert response.json()['data']['reasonCode'] == reason
    assert 'untrusted' not in response.text


@pytest.mark.parametrize('destination', ['001', '003'])
def test_real_guidance_preserves_route_facts_and_fixed_text(make_app, destination):
    results = {}
    for name, adapter in [('rule', RuleBasedAIAdapter()), ('none', None)]:
        _, client, clock, _ = make_app(adapter=adapter)
        body, path = selection(client, clock, destination)
        detail = client.get(path).json()['data']
        response = client.post('/api/v1/easy-guidance', json=body)
        assert response.status_code == 200, response.text
        guidance = response.json()['data']
        assert guidance['routeSnapshotVersion'] == detail['routeSnapshotVersion']
        assert [step['segmentId'] for step in guidance['steps']] == [
            segment['segmentId'] for segment in detail['segments']]
        assert client.get(path).json()['data'] == detail
        results[name] = guidance
    assert results['rule']['mode'] == 'ai_assisted'
    assert results['none']['mode'] == 'template_fallback'
    assert results['rule']['steps'] == results['none']['steps']


def test_factory_without_adapter_retains_manual_fallback(make_app):
    _, client, _, _ = make_app()
    response = client.post(INTERPRET_PATH, json={'originStationId': 'demo-stop-001', 'text': '병원'})
    assert response.status_code == 200, response.text
    assert response.json()['data'] == {
        'status': 'unavailable', 'candidates': [], 'reasonCode': 'AI_UNAVAILABLE'}


def test_default_asgi_entrypoint_connects_real_adapter(monkeypatch):
    # Execute the actual entrypoint with an isolated in-memory database. This
    # checks its module-level app without replacing the app other tests imported.
    monkeypatch.setenv('BUS_DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('BUS_DATA_MODE', 'demo')
    monkeypatch.setenv('BUS_DEMO_SCENARIO', 'normal')
    app = runpy.run_path(main.__file__)['app']
    assert isinstance(app.state.ai.adapter, RuleBasedAIAdapter)
    app.state.clock = Clock()
    app.state.provider = DemoProvider('normal')
    with TestClient(app) as client:
        response = client.post(INTERPRET_PATH, json={'originStationId': 'cheonan-stop-285000685', 'text': '단국대병원'})
        assert response.status_code == 200, response.text
        assert response.json()['data']['status'] == 'matched'
        assert response.json()['data']['reasonCode'] == 'MATCHED'
        assert response.json()['data']['candidates'][0]['destinationId'] == 'cheonan-dankook-hospital'
        # The production catalogue now has four hospitals, so the generic word
        # must ask the user to choose rather than retaining the old single match.
        multiple = client.post(INTERPRET_PATH, json={'originStationId': 'cheonan-stop-285000685', 'text': '병원'})
        assert multiple.json()['data']['status'] == 'needs_confirmation'
        assert len(multiple.json()['data']['candidates']) == 4
        found = client.post('/api/v1/route-searches', json={'originStationId':'cheonan-stop-285000685', 'destinationId':'cheonan-dankook-hospital', 'departAt':app.state.clock().isoformat()}).json()['data']
        option = found['routeOptions'][0]
        body = {'routeSearchId':found['routeSearchId'], 'routeOptionId':option['routeOptionId'], 'expectedRouteSnapshotVersion':option['routeSnapshotVersion']}
        guidance = client.post('/api/v1/easy-guidance', json=body)
        assert guidance.status_code == 200, guidance.text
        assert guidance.json()['data']['mode'] == 'ai_assisted'


def test_openapi_exposes_agreed_public_reason_codes(env):
    app, _, _, _ = env
    reason = app.openapi()['components']['schemas']['InterpretationData']['properties']['reasonCode']
    assert set(reason['enum']) == {
        'MATCHED', 'USER_CONFIRMATION_REQUIRED', 'NO_REGISTERED_MATCH', 'AI_UNAVAILABLE'}
