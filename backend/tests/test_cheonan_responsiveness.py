"""A cold route calculation must not block the kiosk's station lookup."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
from threading import Event

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app


def test_station_remains_responsive_during_graph_calculation(monkeypatch):
    app = create_app(Settings(database_url='sqlite:///:memory:'),
        place_catalog='cheonan', transport_catalog='cheonan')
    entered, release = Event(), Event()
    calculate = app.state.transport.search

    def cold_search(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return calculate(*args, **kwargs)

    monkeypatch.setattr(app.state.transport, 'search', cold_search)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as workers:
        search = workers.submit(client.post, '/api/v1/route-searches', json={
            'originStationId': 'cheonan-stop-285000685', 'destinationId': 'cheonan-city-hall',
            'departAt': datetime.now(timezone.utc).isoformat()})
        assert entered.wait(timeout=5)
        lookup = workers.submit(client.get, '/api/v1/stations/cheonan-stop-285000685')
        try:
            try:
                response = lookup.result(timeout=2)
            except TimeoutError:
                raise AssertionError('Route computation blocked the ASGI event loop') from None
            assert response.status_code == 200
            assert response.json()['data']['station']['name'] == '종합터미널'
        finally:
            release.set()
        assert search.result(timeout=30).status_code == 200
