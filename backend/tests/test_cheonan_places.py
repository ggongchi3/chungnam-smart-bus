from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from ai.adapter import RuleBasedAIAdapter
from backend.config import Settings
from backend.main import create_app
from backend.models.tables import Destination, DestinationAccess, Route, RouteStop, TransferConnection
from backend.services.places import load_places, register_places


def test_every_real_place_searches_in_its_category_and_reaches_existing_route_search():
    now = datetime.now(timezone.utc)
    app = create_app(Settings(database_url='sqlite:///:memory:'), clock=lambda: now,
                     ai_adapter=RuleBasedAIAdapter(), place_catalog='cheonan')
    with TestClient(app) as client:
        base = {'originStationId': 'demo-stop-001'}
        rows = client.get('/api/v1/destinations', params=base).json()['data']['destinations']
        places = load_places()
        assert {p['destinationId'] for p in places} == {r['destinationId'] for r in rows}
        assert len(rows) == 26
        for place in places:
            found = client.get('/api/v1/destinations', params={**base, 'query': place['name'].replace(' ', ''), 'category': place['category']})
            assert place['destinationId'] in [p['destinationId'] for p in found.json()['data']['destinations']]
            response = client.post('/api/v1/route-searches', json={**base,
                'destinationId': place['destinationId'], 'departAt': now.isoformat()})
            assert response.status_code == 200, response.text
            assert response.json()['data']['destinationId'] == place['destinationId']
            # An actual facility is not evidence for synthetic bus access.
            assert response.json()['data']['routeOptions'] == []
        offices = client.get('/api/v1/destinations', params={**base, 'category': 'other'}).json()['data']['destinations']
        assert len(offices) == 13
        assert len(client.get('/api/v1/destinations', params={**base, 'query': '관공서'}).json()['data']['destinations']) == 6
        interpreted = client.post('/api/v1/destination-interpretations', json={**base, 'text': '천안시청에 가고 싶어요'})
        assert interpreted.json()['data']['candidates'][0]['destinationId'] == 'cheonan-city-hall'


def test_additive_registration_preserves_existing_catalog_and_never_adds_transit_links():
    app = create_app(Settings(database_url='sqlite:///:memory:'))
    with TestClient(app):
        db = app.state.database
        models = [Route, RouteStop, DestinationAccess, TransferConnection]
        with db.session() as session:
            before = [session.scalar(select(func.count()).select_from(model)) for model in models]
            session.get(Destination, 'demo-destination-001').name = '기존 담당자 수정값'
        register_places(db, load_places())
        register_places(db, load_places())
        with db.session() as session:
            assert [session.scalar(select(func.count()).select_from(model)) for model in models] == before
            assert session.get(Destination, 'demo-destination-001').name == '기존 담당자 수정값'
            assert session.scalar(select(func.count()).select_from(Destination)) == 29


def test_terminal_complex_and_central_market_are_not_silent_duplicates():
    places = load_places()
    terminals = [p for p in places if p['kind'] == 'terminal']
    assert len({p['destinationId'] for p in terminals}) == 2
    assert len({p['complexId'] for p in terminals}) == 1
    assert all(p['locationNote'] for p in terminals)
    assert sum('남산중앙시장' in p['aliases'] for p in places) == 1
    assert all(not any(k in p for k in ['etaSeconds', 'routeId', 'durationSeconds', 'stationId']) for p in places)
