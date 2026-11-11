"""Actual imported graph integration plus independent distance invariants."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from ai.adapter import RuleBasedAIAdapter
from backend.config import Settings
from backend.integrations.cheonan_live import arrival_state, arrival_state_many
from backend.main import create_app
from backend.models import schemas as s
from backend.models.tables import RouteSearch, Station
from backend.seed import seed
from backend.services.cheonan_routing import sort_key
from backend.services.geo import haversine_meters
from backend.services.places import load_places

ORIGIN = 'cheonan-stop-285000686'


@pytest.fixture(scope='module')
def real_service():
    clock = [datetime.now(timezone.utc)]
    app = create_app(Settings(database_url='sqlite:///:memory:'), clock=lambda: clock[0],
        ai_adapter=RuleBasedAIAdapter(), place_catalog='cheonan', transport_catalog='cheonan')
    with TestClient(app) as client:
        yield app, client, clock


def search(client, clock, destination, mode='transfers'):
    response = client.post('/api/v1/route-searches', json={'originStationId':ORIGIN,
        'destinationId':destination, 'departAt':clock[0].isoformat(), 'sort':mode})
    assert response.status_code == 200, response.text
    return response.json()['data']


def test_origin_and_distance_are_actual_reference_data(real_service):
    app, client, _ = real_service
    response = client.get('/api/v1/stations/' + ORIGIN)
    assert response.json()['meta']['dataMode'] == 'static'
    origin = response.json()['data']['station']
    assert origin['name'] == '종합터미널'
    assert origin['coordinates'] == {'latitude':36.8190148, 'longitude':127.1565574}
    assert app.state.transport.stations['285000686']['name'] == '종합터미널'
    assert len(app.state.transport.routes) == 333
    assert haversine_meters({'latitude':0,'longitude':0}, {'latitude':0,'longitude':1}) == pytest.approx(111195.080, abs=.01)
    assert haversine_meters(origin['coordinates'], origin['coordinates']) == 0


def test_reused_database_origin_is_refreshed_to_verified_reference(real_service):
    app, client, _ = real_service
    with app.state.database.session() as db:
        stored = db.get(Station, ORIGIN)
        stored.name = '이전 설정'
        stored.coordinates = {'latitude': 0, 'longitude': 0}
    app.state.transport.register_origin(app.state.database)
    station = client.get('/api/v1/stations/' + ORIGIN).json()['data']['station']
    assert station['name'] == '종합터미널'
    assert station['coordinates'] == {'latitude': 36.8190148, 'longitude': 127.1565574}


def test_real_catalog_rejects_legacy_demo_origins_instead_of_synthetic_fallback(real_service):
    app, client, clock = real_service
    # Simulate a persistent DB created by the previous demo application. Before
    # the fixed-origin guard this request returned real-looking synthetic buses.
    seed(app.state.database)
    response = client.post('/api/v1/route-searches', json={'originStationId': 'demo-stop-001',
        'destinationId': 'demo-destination-001', 'departAt': clock[0].isoformat()})
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'INVALID_REQUEST'
    assert response.json()['meta']['dataMode'] == 'static'


@pytest.mark.parametrize('kind', [None,'hospital','office','market','shopping','terminal','station','education','culture'])
def test_partial_search_and_every_category_sort_by_distance(real_service, kind):
    _, client, _ = real_service
    params = {'originStationId':ORIGIN, **({'kind':kind} if kind else {})}
    rows = client.get('/api/v1/destinations', params=params).json()['data']['destinations']
    assert rows
    assert rows == sorted(rows, key=lambda r:(r['distanceMeters'],r['name'],r['destinationId']))
    for row in rows:
        assert row['coordinates'] and row['distanceBasis'] == 'straight_line'
        assert row['distanceMeters'] == pytest.approx(haversine_meters({'latitude':36.8190148,'longitude':127.1565574}, row['coordinates']), abs=.001)
    found = client.get('/api/v1/destinations', params={'originStationId':ORIGIN,'query':'기술교육'}).json()['data']['destinations']
    assert found[0]['destinationId'] == 'cheonan-koreatech'


def test_all_places_have_real_directed_paths_and_no_synthetic_edges(real_service):
    app, client, clock = real_service
    network = app.state.transport
    counts = {}
    for place in load_places():
        found = search(client, clock, place['destinationId'])
        counts[place['destinationId']] = len(found['routeOptions'])
        assert found['routeOptions'], place['name']
        assert len({tuple(o['routeNames']) for o in found['routeOptions']}) == len(found['routeOptions'])
        for option in found['routeOptions']:
            assert option['totalDurationSeconds'] is None and option['waitingDurationSeconds'] is None
            path = f"/api/v1/route-searches/{found['routeSearchId']}/options/{option['routeOptionId']}"
            response = client.get(path)
            assert response.status_code == 200, response.text
            detail = response.json()['data']
            buses = [p for p in detail['segments'] if p['type']=='bus']
            for bus in buses:
                route = network.routes[bus['routeId'].removeprefix('cheonan-route-')]
                assert bus['boardSequence'] < bus['alightSequence']
                assert bus['boardStation']['stationId'] == 'cheonan-stop-' + route['stops'][bus['boardSequence']-1]
                assert bus['alightStation']['stationId'] == 'cheonan-stop-' + route['stops'][bus['alightSequence']-1]
            if len(buses)==2:
                assert buses[0]['alightStation'] == buses[1]['boardStation']
    assert all(count >= 2 for count in counts.values()), counts


def test_four_real_metrics_change_order_and_preserve_detail_ai_and_print(real_service):
    _, client, clock = real_service
    orders = []
    for mode in ['fastest','transfers','walking','distance']:
        found = search(client, clock, 'cheonan-dankook-hospital', mode)
        options = [s.RouteOption.model_validate(o) for o in found['routeOptions']]
        assert options == sorted(options, key=lambda o:sort_key(o,mode))
        orders.append([o.routeOptionId for o in options])
        first = options[0]
        selected = {'routeSearchId':found['routeSearchId'],'routeOptionId':first.routeOptionId,
                    'expectedRouteSnapshotVersion':first.routeSnapshotVersion}
        guidance = client.post('/api/v1/easy-guidance',json=selected)
        printed = client.post('/api/v1/print-guides',json=selected)
        assert guidance.status_code == printed.status_code == 200
        assert guidance.json()['data']['mode'] == 'ai_assisted'
        assert printed.json()['data']['routeDetail']['routeSnapshotVersion'] == first.routeSnapshotVersion
        assert printed.json()['data']['liveInfoSnapshot']['arrivals'] == [] or all(a['etaSeconds'] is None for a in printed.json()['data']['liveInfoSnapshot']['arrivals'])
    assert len({tuple(order) for order in orders}) >= 3


def test_ranked_metrics_and_tied_features_are_independently_consistent(real_service):
    _, client, clock = real_service
    fields = {'fastest': 'estimatedTravelSeconds', 'transfers': 'transferCount',
              'walking': 'walkingDistanceMeters', 'distance': 'totalDistanceMeters'}
    for mode, field in fields.items():
        options = search(client, clock, 'cheonan-dankook-hospital', mode)['routeOptions']
        values = [option[field] for option in options]
        assert values == sorted(values, key=lambda value: (value is None, value or 0))
        # Every zero-transfer candidate has the same optimal transfer metric;
        # a badge must not depend on which equal option happened to sort first.
        assert any(option['transferCount'] == 0 for option in options)
        for option in options:
            assert ('최소 환승' in option['features']) == (option['transferCount'] == 0)


def test_expiry_and_changed_snapshot_still_block_guidance(real_service):
    app, client, clock = real_service
    found = search(client, clock, 'cheonan-city-hall')
    option = found['routeOptions'][0]
    path = f"/api/v1/route-searches/{found['routeSearchId']}/options/{option['routeOptionId']}"
    with app.state.database.session() as db:
        saved = db.get(RouteSearch,found['routeSearchId'])
        snapshot = dict(saved.snapshot)
        snapshot[option['routeOptionId']] = {**snapshot[option['routeOptionId']], 'revision':'changed'}
        saved.snapshot = snapshot
    assert client.get(path).status_code == 409
    before = clock[0]
    clock[0] += timedelta(minutes=10)
    assert client.get(path).status_code == 410
    clock[0] = before


def test_card_arrivals_cover_every_bus_and_share_stop_queries(real_service, monkeypatch):
    _, client, clock = real_service
    found = search(client, clock, 'cheonan-dankook-hospital')
    base = f"/api/v1/route-searches/{found['routeSearchId']}"
    buses_by_option = {}
    for option in found['routeOptions']:
        option_id = option['routeOptionId']
        detail = client.get(f'{base}/options/{option_id}').json()['data']
        buses_by_option[option_id] = [p for p in detail['segments'] if p['type'] == 'bus']
    assert any(len(buses) > 1 for buses in buses_by_option.values())
    buses = [bus for legs in buses_by_option.values() for bus in legs]
    target = buses[0]
    target_stop = target['boardStation']['stationId'].removeprefix('cheonan-stop-')
    target_route = target['routeId'].removeprefix('cheonan-route-')
    all_stops = {bus['boardStation']['stationId'].removeprefix('cheonan-stop-') for bus in buses}
    assert len(all_stops) < len(buses)
    queried = []

    def official(request):
        stop = request.url.params['stopId']
        queried.append(stop)
        if stop != target_stop:
            return httpx.Response(503)
        return httpx.Response(200, json={'resultList':[{'ROUTE_ID':int(target_route), 'RTIME':4}]})

    async def lookup(details, now):
        async with httpx.AsyncClient(transport=httpx.MockTransport(official)) as provider:
            return await arrival_state_many(details, now, client=provider)

    monkeypatch.setattr('backend.api.routes.arrival_state_many', lookup)
    response = client.get(base + '/arrivals')
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['routeSearchId'] == found['routeSearchId']
    assert set(data['options']) == set(buses_by_option)
    assert sorted(queried) == sorted(all_stops)
    for option in found['routeOptions']:
        option_id = option['routeOptionId']
        result = data['options'][option_id]
        assert result['routeSnapshotVersion'] == option['routeSnapshotVersion']
        assert len(result['arrivals']) == len(buses_by_option[option_id])
        for bus, arrival in zip(buses_by_option[option_id], result['arrivals']):
            assert arrival['segmentId'] == bus['segmentId']
            assert arrival['routeId'] == bus['routeId']
            assert arrival['boardStationId'] == bus['boardStation']['stationId']
            matches = bus['routeId'] == target['routeId'] and bus['boardStation'] == target['boardStation']
            assert arrival['etaSeconds'] == (240 if matches else None)
            assert arrival['arrivalStatus'] == ('available' if matches else 'unavailable')


@pytest.mark.anyio
async def test_arrivals_use_only_official_matching_route_and_do_not_forge_source_timestamp():
    bus = s.Bus(segmentId='bus-1', routeId='cheonan-route-285000007',routeName='11',
        boardStation=s.StationRef(stationId=ORIGIN,name='종합터미널'),
        alightStation=s.StationRef(stationId='cheonan-stop-285000693',name='정류장'),
        boardSequence=1,alightSequence=2,stopCount=1,durationSeconds=None)
    now = datetime.now(timezone.utc)
    detail = s.RouteDetail(routeSearchId='search',routeOptionId='option',routeSnapshotVersion='v',
        originStationId=ORIGIN,destinationId='destination',computedAt=now,journeyStatus='ready',
        referenceDataQuality=s.Quality(sourceId=None,sourceUpdatedAt=None,fetchedAt=None,freshness='unknown'),segments=[bus])
    def handler(request):
        assert request.url.params['stopId']=='285000686'
        return httpx.Response(200,json={'resultList':[{'ROUTE_ID':285000007,'RTIME':3}, {'ROUTE_ID':285000007,'RTIME':-1}, {'ROUTE_ID':1,'RTIME':1}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await arrival_state(detail,now,client=client)
    value = state.arrivals[(bus.routeId,ORIGIN)]
    assert value.expected_arrival_at == now+timedelta(minutes=3)
    assert value.source_updated_at is None and value.fetched_at == now
