"""Stage 7: public error semantics across every selected-route consumer."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.integrations.providers import DemoProvider
from backend.main import create_app
from backend.services import catalog
from backend.tests.conftest import selection


def selected_responses(client, body, path):
    return [client.get(path), client.get(path + '/live'),
            client.post('/api/v1/easy-guidance', json=body),
            client.post('/api/v1/print-guides', json=body)]


@pytest.mark.parametrize('scenario', ['cancellation', 'detour', 'operation_not_running'])
def test_confirmed_unavailable_has_dedicated_contract_error(env, scenario):
    _, client, clock, provider = env
    body, path = selection(client, clock)
    provider.scenario = scenario
    for response in selected_responses(client, body, path):
        payload = response.json()
        assert response.status_code == 409, response.text
        assert payload['data'] is None
        assert payload['error']['code'] == 'ROUTE_UNAVAILABLE'
        assert payload['error']['retryable'] is True


def test_recheck_still_uses_version_error_and_expiry_keeps_precedence(env):
    _, client, clock, provider = env
    body, path = selection(client, clock)
    provider.scenario = 'timetable_change'
    for response in selected_responses(client, body, path):
        assert response.status_code == 409
        assert response.json()['error']['code'] == 'ROUTE_VERSION_CHANGED'
    provider.scenario = 'cancellation'
    clock.now += timedelta(seconds=600)
    for response in selected_responses(client, body, path):
        assert response.status_code == 410
        assert response.json()['error']['code'] == 'ROUTE_SEARCH_EXPIRED'


@pytest.mark.parametrize('source_age,code', [(90, 'ROUTE_UNAVAILABLE'),
                                           (91, 'ROUTE_VERSION_CHANGED')])
def test_confirmed_stop_becomes_recheck_when_source_turns_stale(env, source_age, code):
    _, client, clock, provider = env
    body, path = selection(client, clock)
    provider.scenario = 'operation_not_running'
    provider.read(clock.now)
    clock.now += timedelta(seconds=source_age)
    for response in selected_responses(client, body, path):
        assert response.status_code == 409
        assert response.json()['error']['code'] == code


@pytest.mark.parametrize('origin,allowed', [('http://localhost:5173', True),
                                         ('http://127.0.0.1:5173', True),
                                         ('https://untrusted.invalid', False)])
def test_cors_applies_to_sanitized_server_failure_and_recovery(monkeypatch, origin, allowed):
    app = create_app(Settings(database_url='sqlite:///:memory:'), provider=DemoProvider())
    with TestClient(app, raise_server_exceptions=False) as client:
        def check(response, status):
            assert response.status_code == status, response.text
            payload = response.json()
            assert response.headers['x-request-id'] == payload['meta']['requestId']
            assert response.headers['cache-control'] == 'no-store'
            if allowed:
                assert response.headers.get('access-control-allow-origin') == origin
                assert 'origin' in response.headers.get('vary', '').lower()
            else:
                assert 'access-control-allow-origin' not in response.headers
            return payload

        headers = {'Origin': origin}
        check(client.get('/api/v1/stations/demo-stop-001', headers=headers), 200)
        check(client.get('/api/v1/stations/not-registered', headers=headers), 404)
        check(client.post('/api/v1/route-searches', json={}, headers=headers), 400)

        def fail(*args):
            raise RuntimeError('private-test-failure')

        with monkeypatch.context() as patch:
            patch.setattr(catalog, 'station', fail)
            response = client.get('/api/v1/stations/demo-stop-001', headers=headers)
        payload = check(response, 500)
        assert payload['data'] is None and payload['error']['code'] == 'INTERNAL_ERROR'
        assert 'private-test-failure' not in response.text
        check(client.get('/api/v1/stations/demo-stop-001', headers=headers), 200)
