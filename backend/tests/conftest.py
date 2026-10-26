from contextlib import ExitStack
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.integrations.providers import DemoProvider
from backend.main import create_app


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 26, 5, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture
def make_app():
    with ExitStack() as stack:
        def make(adapter=None, scenario='normal', mode='demo', url='sqlite:///:memory:'):
            clock = Clock()
            provider = DemoProvider(scenario) if mode == 'demo' else None
            app = create_app(Settings(database_url=url, data_mode=mode), clock=clock,
                             provider=provider, ai_adapter=adapter)
            client = stack.enter_context(TestClient(app))
            return app, client, clock, provider
        yield make


@pytest.fixture
def env(make_app):
    return make_app()


def search(client, clock, destination='001', origin='001', offset=0):
    from datetime import timedelta
    return client.post('/api/v1/route-searches', json={
        'originStationId': 'demo-stop-' + origin, 'destinationId': 'demo-destination-' + destination,
        'departAt': (clock.now + timedelta(seconds=offset)).isoformat()})


def selection(client, clock, destination='001'):
    data = search(client, clock, destination).json()['data']
    option = data['routeOptions'][0]
    body = {'routeSearchId': data['routeSearchId'], 'routeOptionId': option['routeOptionId'],
            'expectedRouteSnapshotVersion': option['routeSnapshotVersion']}
    path = f"/api/v1/route-searches/{body['routeSearchId']}/options/{body['routeOptionId']}"
    return body, path
