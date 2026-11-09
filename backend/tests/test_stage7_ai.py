"""Stage 7 public AI contract checks using isolated databases and test adapters."""
import copy
import json

import pytest

from backend.tests.conftest import selection


@pytest.mark.parametrize('ids,accepted', [
    (['demo-destination-001', 'demo-destination-003'], True),
    (['demo-destination-002', 'demo-destination-003'], True),
    (['demo-destination-003', 'demo-destination-001'], False),
    (['demo-destination-003', 'demo-destination-002'], False),
])
def test_interpretation_requires_registered_candidate_order(make_app, ids, accepted):
    class Adapter:
        def interpret_destination(self, payload):
            assert [d['destinationId'] for d in payload['allowedDestinations']] == [
                'demo-destination-001', 'demo-destination-002', 'demo-destination-003']
            return {'status': 'needs_confirmation', 'candidateDestinationIds': ids,
                    'reasonCode': 'USER_CONFIRMATION_REQUIRED'}

    _, client, _, _ = make_app(adapter=Adapter())
    response = client.post('/api/v1/destination-interpretations', json={
        'originStationId': 'demo-stop-001', 'text': '병원 시장 터미널'})
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['status'] == ('needs_confirmation' if accepted else 'unavailable')
    assert [d['destinationId'] for d in data['candidates']] == (ids if accepted else [])
    assert data['reasonCode'] == ('USER_CONFIRMATION_REQUIRED' if accepted else 'AI_UNAVAILABLE')


@pytest.mark.parametrize('raw', [None, '', '{invalid JSON', 'null', [], {}, 0, True])
@pytest.mark.parametrize('endpoint', ['destination-interpretations', 'easy-guidance'])
def test_malformed_or_empty_adapter_outputs_have_public_fallbacks(make_app, raw, endpoint):
    class Adapter:
        def interpret_destination(self, payload):
            return copy.deepcopy(raw)

        def choose_guidance(self, payload):
            return copy.deepcopy(raw)

    _, client, clock, _ = make_app(adapter=Adapter())
    body, path = selection(client, clock, '003')
    detail = client.get(path).json()['data']
    if endpoint == 'destination-interpretations':
        request = {'originStationId': 'demo-stop-001', 'text': '병원'}
    else:
        request = body
    response = client.post('/api/v1/' + endpoint, json=request)
    assert response.status_code == 200, response.text
    data = response.json()['data']
    if endpoint == 'destination-interpretations':
        assert data == {'status': 'unavailable', 'candidates': [], 'reasonCode': 'AI_UNAVAILABLE'}
    else:
        assert data['mode'] == 'template_fallback'
        printed = client.post('/api/v1/print-guides', json=body)
        assert printed.status_code == 200, printed.text
        snapshot = printed.json()['data']
        assert snapshot['guidance'] == data
        assert snapshot['routeDetail']['segments'] == detail['segments']
        assert data['routeSnapshotVersion'] == detail['routeSnapshotVersion']


def test_json_text_from_adapter_is_not_treated_as_valid_parsed_output(make_app):
    class Adapter:
        def interpret_destination(self, payload):
            return json.dumps({'status': 'matched', 'candidateDestinationIds': ['demo-destination-001'],
                               'reasonCode': 'MATCHED'})

    _, client, _, _ = make_app(adapter=Adapter())
    response = client.post('/api/v1/destination-interpretations', json={
        'originStationId': 'demo-stop-001', 'text': '병원'})
    assert response.status_code == 200, response.text
    assert response.json()['data']['status'] == 'unavailable'
