from datetime import datetime, timezone
import unicodedata

from fastapi.testclient import TestClient
import pytest
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


def test_real_catalog_partial_address_unicode_shortcuts_and_ai_stay_distance_sorted():
    origin = 'cheonan-stop-285000686'
    app = create_app(Settings(database_url='sqlite:///:memory:'), ai_adapter=RuleBasedAIAdapter(),
                     place_catalog='cheonan', transport_catalog='cheonan')
    with TestClient(app) as client:
        base = {'originStationId': origin}
        for query, expected in [('망향로', {'cheonan-dankook-hospital'}),
                                (unicodedata.normalize('NFD', '단국대병원'), {'cheonan-dankook-hospital'}),
                                ('지하철', {'cheonan-station', 'cheonan-dujeong-station', 'cheonan-bongmyeong-station'})]:
            response = client.get('/api/v1/destinations', params={**base, 'query': query})
            assert response.status_code == 200, response.text
            rows = response.json()['data']['destinations']
            assert {row['destinationId'] for row in rows} == expected
            assert rows == sorted(rows, key=lambda row: (row['distanceMeters'], row['name'], row['destinationId']))
        rows = client.get('/api/v1/destinations', params={**base, 'kind': 'hospital'}).json()['data']['destinations']
        interpreted = client.post('/api/v1/destination-interpretations', json={**base, 'text': '병원으로 가고 싶어요'})
        assert interpreted.status_code == 200
        assert interpreted.json()['data']['candidates'] == rows
        # A fixed-origin pedestrian matrix must never be attached to another
        # origin, even if the request comes from an older bookmarked client.
        invalid = client.get('/api/v1/destinations', params={'originStationId': 'demo-stop-001', 'sort': 'walking'})
        assert invalid.status_code == 400
        assert invalid.json()['error']['code'] == 'INVALID_REQUEST'


@pytest.mark.anyio
async def test_ai_rebinds_current_catalog_distance_and_order_after_lookup():
    from backend.models.schemas import Destination
    from backend.services.ai import interpret

    def place(identity, distance):
        return Destination(destinationId=identity, name=identity, category='hospital', aliases=[],
                           distanceMeters=distance, distanceBasis='straight_line')

    class Boundary:
        budget = 1

        async def call(self, operation, payload):
            return {'status': 'needs_confirmation', 'candidateDestinationIds': ['first', 'second'], 'reasonCode': None}

    result = await interpret(Boundary(), '병원', [place('first', 10), place('second', 20)], 'static',
                             reload_destinations=lambda: [place('second', 5), place('first', 10)])
    assert [row.destinationId for row in result.candidates] == ['second', 'first']
    assert [row.distanceMeters for row in result.candidates] == [5, 10]


def test_origin_import_uses_official_row_and_fails_without_it():
    import json
    from pathlib import Path
    from backend.scripts.refresh_cheonan_transport import origin_from_stops

    snapshot = json.loads((Path(__file__).resolve().parents[2] / 'shared/data/cheonan-transport.json').read_text(encoding='utf-8'))
    row = snapshot['stations']['285000686']
    imported = origin_from_stops([{'STOP_ID': 285000686, 'STOP_NAME': row['name'], 'SERVICE_ID': row['arsId'],
                                  'LAT': str(row['latitude']), 'LNG': str(row['longitude'])}])
    assert imported == snapshot['origin']
    with pytest.raises(RuntimeError, match='missing'):
        origin_from_stops([])
    with pytest.raises(ValueError, match='invalid'):
        origin_from_stops([{'STOP_ID': 285000686, 'LAT': float('nan'), 'LNG': row['longitude']}])


def test_all_26_places_have_pedestrian_network_distance_and_sort_by_it():
    app = create_app(Settings(database_url='sqlite:///:memory:'),
                     place_catalog='cheonan', transport_catalog='cheonan')
    with TestClient(app) as client:
        response = client.get('/api/v1/destinations', params={
            'originStationId':'cheonan-stop-285000686', 'sort':'walking'})
        assert response.status_code == 200
        rows = response.json()['data']['destinations']
        assert len(rows) == 26
        assert all(row['walkingDistanceMeters'] is not None and row['walkingDistanceMeters'] >= 0 for row in rows)
        assert [row['walkingDistanceMeters'] for row in rows] == sorted(row['walkingDistanceMeters'] for row in rows)
        distances = {row['destinationId']:row['walkingDistanceMeters'] for row in rows}
        # Independently collected pedestrian-network results for remote places;
        # these are not the former straight-line proximity values.
        assert distances['cheonan-byeongcheon-market'] == 17749
        assert distances['cheonan-independence-hall'] == 10618
        assert app.state.transport.walks['costing'] == 'pedestrian'


@pytest.mark.parametrize('row', [{'distance':None,'time':20}, {'distance':-1,'time':20},
                                {'distance':float('nan'),'time':20}, {'distance':1,'time':True}])
def test_invalid_network_distance_is_never_approved_as_a_measured_path(row):
    from backend.scripts.refresh_cheonan_walks import link
    assert link(row) is None
