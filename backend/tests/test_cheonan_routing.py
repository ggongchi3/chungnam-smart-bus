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
from backend.services.cheonan_routing import CheonanNetwork, sort_key
from backend.services.geo import haversine_meters
from backend.services.places import load_places

ORIGIN = 'cheonan-stop-285000685'
OPPOSITE = 'cheonan-stop-285000686'
ORIGIN_COORDINATES = {'latitude': 36.8187607, 'longitude': 127.1556582}


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
    assert origin['arsId'] == '685'
    assert origin['coordinates'] == ORIGIN_COORDINATES
    opposite = client.get('/api/v1/stations/' + OPPOSITE).json()['data']['station']
    assert opposite['name'] == origin['name']
    assert opposite['stationId'] != origin['stationId'] and opposite['arsId'] == '686'
    assert opposite['coordinates'] == {'latitude': 36.8190148, 'longitude': 127.1565574}
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
    assert station['coordinates'] == ORIGIN_COORDINATES
    with app.state.database.session() as db:
        assert db.get(Station, ORIGIN).coordinates == ORIGIN_COORDINATES


@pytest.mark.parametrize('wrong_origin', ['demo-stop-001', OPPOSITE])
def test_real_catalog_rejects_every_other_origin_even_for_ai(real_service, wrong_origin):
    app, client, clock = real_service
    # Simulate a persistent DB created by the previous demo application. Before
    # the fixed-origin guard this request returned real-looking synthetic buses.
    seed(app.state.database)
    base = {'originStationId': wrong_origin}
    for response in (
        client.post('/api/v1/route-searches', json={**base, 'destinationId': 'cheonan-dankook-hospital',
                                                   'departAt': clock[0].isoformat()}),
        client.get('/api/v1/destinations', params=base),
        client.post('/api/v1/destination-interpretations', json={**base, 'text': '단국대병원'}),
    ):
        assert response.status_code == 400
        assert response.json()['error']['code'] == 'INVALID_REQUEST'
        assert '685번' in response.json()['error']['message']


@pytest.mark.parametrize('kind', [None,'hospital','office','market','shopping','terminal','station','education','culture'])
def test_partial_search_and_every_category_sort_by_distance(real_service, kind):
    _, client, _ = real_service
    params = {'originStationId':ORIGIN, **({'kind':kind} if kind else {})}
    rows = client.get('/api/v1/destinations', params=params).json()['data']['destinations']
    assert rows
    assert rows == sorted(rows, key=lambda r:(r['distanceMeters'],r['name'],r['destinationId']))
    for row in rows:
        assert row['coordinates'] and row['distanceBasis'] == 'straight_line'
        assert row['distanceMeters'] == pytest.approx(haversine_meters(ORIGIN_COORDINATES, row['coordinates']), abs=.001)
    found = client.get('/api/v1/destinations', params={'originStationId':ORIGIN,'query':'기술교육'}).json()['data']['destinations']
    assert found[0]['destinationId'] == 'cheonan-koreatech'


def test_all_places_have_real_directed_paths_and_no_synthetic_edges(real_service):
    app, client, clock = real_service
    network = app.state.transport
    counts = {}
    has_transfer = False
    for place in load_places():
        found = search(client, clock, place['destinationId'])
        assert found['originStationId'] == ORIGIN
        counts[place['destinationId']] = len(found['routeOptions'])
        families = set()
        for option in found['routeOptions']:
            assert option['totalDurationSeconds'] is None and option['waitingDurationSeconds'] is None
            assert option['routeNames'] and option['boardStation']['stationId'] == ORIGIN
            path = f"/api/v1/route-searches/{found['routeSearchId']}/options/{option['routeOptionId']}"
            response = client.get(path)
            assert response.status_code == 200, response.text
            detail = response.json()['data']
            assert detail['segments'][0]['type'] == 'bus'
            assert detail['segments'][0]['boardStation']['stationId'] == ORIGIN
            assert [p['segmentId'] for p in detail['segments'] if p['type'] == 'walk'] == ['destination-walk']
            buses = [p for p in detail['segments'] if p['type']=='bus']
            family = tuple(bus['routeId'] for bus in buses)
            assert family not in families
            families.add(family)
            for bus in buses:
                route = network.routes[bus['routeId'].removeprefix('cheonan-route-')]
                start, end = bus['boardSequence'], bus['alightSequence']
                assert end - start == bus['stopCount'] > 0
                assert [stop['stationId'] for stop in bus['stops']] == [
                    'cheonan-stop-' + sid for sid in route['stops'][start-1:end]]
                assert OPPOSITE not in {stop['stationId'] for stop in bus['stops']}
                assert [stop['sequence'] for stop in bus['stops']] == list(range(start, end + 1))
                assert bus['directionLabel']
                for actual, key in [(bus['stops'][0], 'boardStation'), (bus['stops'][-1], 'alightStation')]:
                    assert bus[key] == {k: actual[k] for k in ('stationId','name','arsId')}
                if bus['path']:
                    assert haversine_meters(bus['path'][0], bus['stops'][0]['coordinates']) < 151
                    assert haversine_meters(bus['path'][-1], bus['stops'][-1]['coordinates']) < 151
            if len(buses)==2:
                has_transfer = True
                transfer = next(p for p in detail['segments'] if p['type'] == 'transfer')
                assert buses[0]['alightStation'] == transfer['atStation'] == buses[1]['boardStation']
                assert transfer['fromSegmentId'] == buses[0]['segmentId']
                assert transfer['toSegmentId'] == buses[1]['segmentId']
    assert has_transfer and counts['cheonan-dankook-hospital'] and counts['cheonan-city-hall']


def test_hospital_uses_the_seven_verified_directions_and_real_distance(real_service):
    app, client, clock = real_service
    found = search(client, clock, 'cheonan-dankook-hospital', 'fastest')
    # Published directional route IDs and their stop order at 685 (not just
    # the public bus number). E.g. the other 13 passes hospital before 686.
    expected = {'13': ('285000011', '1715', 5), '20': ('285000017', '1715', 5),
                '192': ('285000399', '1715', 5), '121': ('285000081', '639', 6),
                '200': ('285000104', '639', 6), '201': ('285000106', '639', 6),
                '221': ('285000108', '639', 5)}
    assert {tuple(o['routeNames']) for o in found['routeOptions']} == {(bus,) for bus in expected}
    reverse = app.state.transport.routes['285000010']['stops']
    assert reverse.index('285000640') < reverse.index('285000686') and '285000685' not in reverse
    for option in found['routeOptions']:
        path = f"/api/v1/route-searches/{found['routeSearchId']}/options/{option['routeOptionId']}"
        detail = client.get(path).json()['data']
        bus, walk = detail['segments']
        route_id, alight, count = expected[bus['routeName']]
        assert bus['routeId'] == 'cheonan-route-' + route_id
        assert bus['boardStation']['arsId'] == '685' and bus['alightStation']['arsId'] == alight
        if bus['routeName'] in {'13', '20', '192'}:
            assert bus['directionLabel'] == '단국대학교병원 방면'
        assert all(stop['stationId'] != OPPOSITE for stop in bus['stops'])
        assert bus['stopCount'] == count and bus['path']
        assert bus['stops'][1]['stationId'] == 'cheonan-stop-285000706'
        assert bus['stops'][-2]['stationId'] == 'cheonan-stop-285001595'
        def length(line):
            return sum(haversine_meters(a, b) for a, b in zip(line, line[1:]))
        assert bus['distanceMeters'] == round(length(bus['path']))
        route = app.state.transport.routes[route_id]
        full_length = length([{'latitude':lat, 'longitude':lon} for lat, lon in route['geometry']])
        assert bus['durationSeconds'] == round(route['averageDurationMinutes'] * 60 * bus['distanceMeters'] / full_length)
        assert detail['estimatedTravelSeconds'] == option['estimatedTravelSeconds'] == bus['durationSeconds'] + walk['durationSeconds']


@pytest.mark.parametrize(('mode', 'field'), [('transfers', 'transferCount'), ('distance', 'totalDistanceMeters')])
def test_medical_center_forward_trips_share_one_path_group(real_service, mode, field):
    _, client, clock = real_service
    found = search(client, clock, 'cheonan-medical-center', mode)
    options = found['routeOptions']
    values = [option[field] for option in options]
    assert values == sorted(values, key=lambda value: (value is None, value))
    assert len({option['routeOptionId'] for option in options}) == len(options)
    shared = [option for option in options if option['routeNames'] in (['982', '500'], ['982', '512'])
              and option['alightStation']['arsId'] == '743'
              and [stop['arsId'] for stop in option['transferStations']] == ['649']]
    assert {tuple(option['routeNames']) for option in shared} == {('982', '500'), ('982', '512')}
    assert len({option['pathGroupId'] for option in shared}) == 1
    assert len({option['pathGroupId'] for option in options}) > 1
    for option in shared:
        path = f"/api/v1/route-searches/{found['routeSearchId']}/options/{option['routeOptionId']}"
        response = client.get(path)
        assert response.status_code == 200, response.text
        detail = response.json()['data']
        assert detail['routeSnapshotVersion'] == option['routeSnapshotVersion']
        assert [leg['routeName'] for leg in detail['segments'] if leg['type'] == 'bus'] == option['routeNames']


def test_removes_terminal_loop_and_medical_center_reverse_transfer_in_every_sort(real_service):
    _, client, clock = real_service
    for mode in ('transfers', 'distance', 'fastest', 'walking'):
        # The 72 → 72 round trip in the screenshot leaves 685 and returns to 686.
        assert not search(client, clock, 'cheonan-bus-terminal', mode)['routeOptions']
        # The 24 → 24 detour returns through 686 before continuing to the hospital.
        medical = search(client, clock, 'cheonan-medical-center', mode)['routeOptions']
        assert ['24', '24'] not in [o['routeNames'] for o in medical]
        assert any(o['routeNames'] == ['982', '500'] and o['transferStations'][0]['arsId'] == '649' for o in medical)
        # These routes do not need the opposite terminal stop to be a detour.
        chungmu = search(client, clock, 'cheonan-chungmu-hospital', mode)['routeOptions']
        assert any(o['routeNames'] == ['982', '10'] for o in chungmu)
        assert not any(o['routeNames'][0] in {'72', '121'} for o in chungmu)


def test_direct_ride_wins_over_transfer_with_negligible_distance_gain(real_service):
    _, client, clock = real_service
    options = search(client, clock, 'cheonan-station', 'distance')['routeOptions']
    assert options
    assert all(o['transferCount'] == 0 for o in options)
    assert options[0]['routeNames'] == ['982']
    campus = search(client, clock, 'cheonan-dankook-university')['routeOptions']
    assert campus[0]['transferCount'] == 0
    assert any(o['transferCount'] == 1 and o['walkingDistanceMeters'] < campus[0]['walkingDistanceMeters'] for o in campus)


def test_opposite_side_of_traveled_corridor_is_a_reverse_transfer():
    # Test only the geographic check. The two sides of the road have
    # different IDs, and a small turn near the interchange remains valid.
    positions = {
        'start': (36.82, 127.150),
        'earlier': (36.82, 127.156),
        'earlier-opposite': (36.8203, 127.156),
        'transfer': (36.82, 127.164),
        'short-turn': (36.821, 127.163),
        'end': (36.855, 127.162),
    }
    stations = {sid: {'name': sid, 'arsId': sid, 'latitude': lat, 'longitude': lon}
                for sid, (lat, lon) in positions.items()}
    start = {key: stations['start'][key] for key in ('latitude', 'longitude')}
    source = {
        'origin': {'publicId': 'start', 'stationId': 'cheonan-stop-start', 'name': 'start',
                   'arsId': 'start', 'coordinates': start},
        'stations': stations, 'routes': [], 'retrievedAt': datetime.now(timezone.utc).isoformat(),
    }
    network = CheonanNetwork(source=source, walks={})
    first = ('start', 'earlier', 'transfer')

    def remaining(sid):
        return haversine_meters(stations[sid], stations['end'])

    assert network.makes_forward_progress((first, ('transfer', 'short-turn', 'end')), remaining, 800)
    assert not network.makes_forward_progress((first, ('transfer', 'earlier-opposite', 'end')), remaining, 800)


def test_swapping_direction_uses_the_return_side_and_return_route(real_service):
    app, _, _ = real_service
    network = app.state.transport
    hospital_return, terminal_return = '285000640', '285000686'
    # Use actual stop-to-stop endpoints so the reverse direction does not
    # invent a facility access link or change the production kiosk origin.
    source = {**network.data, 'origin': {
        'publicId': hospital_return, 'stationId': 'cheonan-stop-' + hospital_return,
        'name': '단국대학교병원', 'arsId': '640', 'coordinates': network.coordinates(hospital_return),
    }}
    walks = {'destinations': {'return-terminal': {'access': [
        {'stationId': terminal_return, 'distanceMeters': 0, 'durationSeconds': 0},
    ]}}}
    return_network = CheonanNetwork(source=source, walks=walks)
    terminal = s.Destination(destinationId='return-terminal', name='종합터미널', category='terminal',
                             aliases=[], coordinates=network.coordinates(terminal_return))
    rows = return_network.destination_candidates(terminal)
    legs = [segments[0] for _, option, segments in rows if option.routeNames == ['13']]
    assert len(legs) == 1
    bus = legs[0]
    assert bus.routeId == 'cheonan-route-285000010'
    assert bus.boardStation.arsId == '640' and bus.alightStation.arsId == '686'
    assert bus.boardSequence < bus.alightSequence


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
        printed_segments = printed.json()['data']['routeDetail']['segments']
        path = f"/api/v1/route-searches/{found['routeSearchId']}/options/{first.routeOptionId}"
        shown = client.get(path).json()['data']
        assert printed.json()['data']['routeDetail'] == shown
        voice = guidance.json()['data']['steps'][0]['text']
        assert '종합터미널 685번' in voice
        assert shown['segments'][0]['directionLabel'] in voice
        assert f"약 {(first.estimatedTravelSeconds + 59) // 60}분" in voice
        assert printed_segments[0]['type'] == 'bus' and printed_segments[0]['boardStation']['stationId'] == ORIGIN
        assert [p['segmentId'] for p in printed_segments if p['type'] == 'walk'] == ['destination-walk']
        assert printed.json()['data']['liveInfoSnapshot']['arrivals'] == [] or all(a['etaSeconds'] is None for a in printed.json()['data']['liveInfoSnapshot']['arrivals'])
    assert len({tuple(order) for order in orders}) >= 2


def test_ranked_metrics_and_tied_features_are_independently_consistent(real_service):
    _, client, clock = real_service
    fields = {'fastest': 'estimatedTravelSeconds', 'transfers': 'transferCount',
              'walking': 'walkingDistanceMeters', 'distance': 'totalDistanceMeters'}
    for mode, field in fields.items():
        options = search(client, clock, 'cheonan-dankook-hospital', mode)['routeOptions']
        values = [option[field] for option in options]
        assert values == sorted(values, key=lambda value: (value is None, value or 0))
        # The minimum can be one when the fixed stop has no direct bus.
        minimum_transfers = min(option['transferCount'] for option in options)
        for option in options:
            assert ('최소 환승' in option['features']) == (option['transferCount'] == minimum_transfers)


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
    found = search(client, clock, 'cheonan-seobuk-district-office')
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
        assert request.url.params['stopId']=='285000685'
        return httpx.Response(200,json={'resultList':[{'ROUTE_ID':285000007,'RTIME':3}, {'ROUTE_ID':285000007,'RTIME':-1}, {'ROUTE_ID':1,'RTIME':1}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await arrival_state(detail,now,client=client)
    value = state.arrivals[(bus.routeId,ORIGIN)]
    assert value.expected_arrival_at == now+timedelta(minutes=3)
    assert value.source_updated_at is None and value.fetched_at == now
