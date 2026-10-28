"""Stage 4 route-search and stored-detail acceptance tests."""
import copy
from dataclasses import replace
from datetime import timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, func, select

from backend.config import ROOT, Settings
from backend.integrations.providers import DemoProvider
from backend.main import create_app
from backend.models import schemas as s
from backend.models.tables import DestinationAccess, Route, RouteSearch, RouteStop, Station, TransferConnection
from backend.tests.conftest import Clock, search


def details(client, data):
    assert data['routeOptions']
    result = []
    for option in data['routeOptions']:
        path = f"/api/v1/route-searches/{data['routeSearchId']}/options/{option['routeOptionId']}"
        response = client.get(path)
        assert response.status_code == 200, response.text
        result.append(s.Envelope[s.RouteDetail].model_validate(response.json()).data.model_dump(mode='json'))
    return result


def selected(client, clock, destination='001'):
    response = search(client,clock,destination)
    assert response.status_code == 200,response.text
    data = response.json()['data']
    option = data['routeOptions'][0]
    path = f"/api/v1/route-searches/{data['routeSearchId']}/options/{option['routeOptionId']}"
    return data,option,path


def assert_error(response,status,code):
    assert response.status_code == status,response.text
    payload = s.Envelope[None].model_validate(response.json())
    assert payload.data is None and payload.error.code == code


def add_route(session,route_id,station_ids,sequences=None):
    session.add(Route(route_id=route_id,name=route_id,direction_label='합성 테스트 방향'))
    session.flush()
    for sequence,station_id in zip(sequences or range(1,len(station_ids)+1),station_ids):
        session.add(RouteStop(route_id=route_id,sequence=sequence,station_id=station_id))
    session.flush()


@pytest.mark.parametrize('destination,stops,transfers,types',[
    ('002',1,0,['bus','walk']),('001',2,0,['bus','walk']),
    ('003',4,1,['bus','transfer','bus','walk']),
])
def test_known_routes_handoff_and_snapshot_fact_consistency(env,destination,stops,transfers,types):
    app,client,clock,_ = env
    response = search(client,clock,destination)
    payload = s.Envelope[s.SearchData].model_validate(response.json())
    assert response.status_code == 200 and len(payload.data.routeOptions) == 1
    data = payload.data.model_dump(mode='json')
    option = data['routeOptions'][0]
    detail = details(client,data)[0]
    handoff = {k:data[k] for k in ('originStationId','destinationId','routeSearchId')}
    handoff.update({k:option[k] for k in ('routeOptionId','routeSnapshotVersion')})
    handoff['dataMode'] = payload.meta.dataMode
    assert len(handoff) == 6 and all(isinstance(value,str) for value in handoff.values())
    assert all(detail[key] == value for key,value in handoff.items() if key != 'dataMode')
    assert option['journeyStatus'] == detail['journeyStatus'] == 'ready'
    assert option['transferCount'] == transfers
    assert [p['type'] for p in detail['segments']] == types
    buses = [p for p in detail['segments'] if p['type']=='bus']
    assert sum(p['stopCount'] for p in buses) == stops
    assert option['routeNames'] == [p['routeName'] for p in buses]
    assert option['totalDurationSeconds'] is None and option['walkingDurationSeconds'] is None
    assert all(p['durationSeconds'] is None for p in buses)
    assert detail['segments'][-1]['distanceMeters'] is None
    assert detail['segments'][-1]['durationSeconds'] is None
    assert len({p['segmentId'] for p in detail['segments']}) == len(detail['segments'])
    assert payload.data.expiresAt == clock.now + timedelta(seconds=600)
    with app.state.database.session() as session:
        saved = session.get(RouteSearch,data['routeSearchId'])
        assert saved.snapshot[option['routeOptionId']]['detail'] == detail
        assert saved.expires_at == (clock.now+timedelta(seconds=600)).timestamp()
    if transfers:
        a,transfer,b,walk = detail['segments']
        assert transfer['fromSegmentId'] == a['segmentId'] and transfer['toSegmentId'] == b['segmentId']
        assert a['alightStation'] == transfer['atStation'] == b['boardStation']


def test_nonconsecutive_and_repeated_station_occurrences_use_rows_not_sequence_difference(env):
    app,client,clock,_ = env
    with app.state.database.session() as session:
        add_route(session,'test-repeat',['demo-stop-001','demo-stop-002','demo-stop-001','demo-stop-003'],[10,20,30,90])
    data = search(client,clock).json()['data']
    result = details(client,data)
    assert len(result) == 3
    buses = [next(p for p in detail['segments'] if p['type']=='bus') for detail in result]
    assert [p['stopCount'] for p in buses] == [1,2,3]
    assert buses[0]['boardSequence'] == 30 and buses[0]['alightSequence'] == 90
    assert buses[2]['boardSequence'] == 10 and buses[2]['alightSequence'] == 90
    assert len({p['routeOptionId'] for p in data['routeOptions']}) == 3


def test_transfer_count_precedes_total_bus_stops(env):
    app,client,clock,_ = env
    with app.state.database.session() as session:
        add_route(session,'test-long-direct',['demo-stop-001','demo-stop-002','demo-stop-004',
                                             'demo-stop-002','demo-stop-003','demo-stop-005'])
    data = search(client,clock,'003').json()['data']
    result = details(client,data)
    assert [option['transferCount'] for option in data['routeOptions']] == [0,1]
    assert [sum(p['stopCount'] for p in detail['segments'] if p['type']=='bus') for detail in result] == [5,4]


def test_tied_routes_sort_by_stable_key_and_public_results_are_capped(env):
    app,client,clock,_ = env
    with app.state.database.session() as session:
        for suffix in ['d','c','b','a']:
            add_route(session,'test-route-'+suffix,['demo-stop-001','demo-stop-003'])
    first = search(client,clock).json()['data']
    second = search(client,clock).json()['data']
    assert len(first['routeOptions']) == 3
    assert [option['routeNames'] for option in first['routeOptions']] == [
        ['test-route-a'],['test-route-b'],['test-route-c']]
    assert first['routeSearchId'] != second['routeSearchId']
    assert first['routeOptions'] == second['routeOptions']


def test_unavailable_top_candidates_do_not_hide_later_ready_route(env):
    app,client,clock,provider = env
    blocked = []
    with app.state.database.session() as session:
        for suffix in ['a','b','c','d']:
            add_route(session,'test-route-'+suffix,['demo-stop-001','demo-stop-003'])
            if suffix != 'd':
                blocked.append('test-route-'+suffix)
    base = provider.read(clock.now)
    change = s.Change(changeId='test-cancelled',type='cancellation',affectedRouteIds=blocked,
        affectedStationIds=[],title='합성 결행 테스트',description='테스트',validFrom=clock.now,
        validUntil=None,dataQuality=base.changes.dataQuality)
    provider.read = lambda now: replace(base,changes=base.changes.model_copy(update={'items':[change]}))
    data = search(client,clock).json()['data']
    assert [option['routeNames'] for option in data['routeOptions']] == [['test-route-d'],['시연 1번']]


def test_new_shorter_options_do_not_invalidate_unchanged_selected_snapshot(env):
    app,client,clock,_ = env
    data,option,path = selected(client,clock)
    original = client.get(path).json()['data']
    with app.state.database.session() as session:
        for suffix in ['a','b','c','d']:
            add_route(session,'test-new-'+suffix,['demo-stop-001','demo-stop-003'])
    new = search(client,clock).json()['data']
    assert all(o['routeOptionId'] != option['routeOptionId'] for o in new['routeOptions'])
    assert client.get(path).status_code == 200
    assert client.get(path).json()['data'] == original


def test_explicit_edge_is_required_and_cross_station_transfer_is_not_invented(env):
    app,client,clock,_ = env
    with app.state.database.session() as session:
        transfer = session.get(TransferConnection,('demo-route-001',3,'demo-route-002',1))
        transfer.to_sequence = 2  # A different station needs a separate verified walking link.
    assert search(client,clock,'003').json()['data']['routeOptions'] == []
    with app.state.database.session() as session:
        session.execute(delete(TransferConnection))
    assert search(client,clock,'003').json()['data']['routeOptions'] == []
    assert search(client,clock,'001','005').json()['data']['routeOptions'] == []


def test_two_registered_transfers_still_do_not_create_three_bus_route(env):
    app,client,clock,_ = env
    with app.state.database.session() as session:
        session.add(Station(station_id='test-stop-006',name='합성 후속 정류장',direction_label='테스트'))
        session.flush()
        add_route(session,'test-route-third',['demo-stop-005','test-stop-006'])
        session.add(TransferConnection(from_route_id='demo-route-002',from_sequence=3,
            to_route_id='test-route-third',to_sequence=1,evidence='합성 테스트 연결'))
        session.execute(delete(DestinationAccess).where(DestinationAccess.destination_id=='demo-destination-003'))
        session.add(DestinationAccess(destination_id='demo-destination-003',station_id='test-stop-006'))
    assert search(client,clock,'003').json()['data']['routeOptions'] == []


@pytest.mark.parametrize('offset,status',[(-121,400),(-120,200),(120,200),(121,400),
                                         (-120.000001,400),(120.000001,400)])
def test_departure_exact_boundaries_and_search_expiry_are_server_based(env,offset,status):
    _,client,clock,_ = env
    response = search(client,clock,offset=offset)
    if status == 200:
        data = s.Envelope[s.SearchData].model_validate(response.json()).data
        assert data.expiresAt == clock.now + timedelta(seconds=600)
    else:
        assert_error(response,400,'INVALID_REQUEST')


@pytest.mark.parametrize('representation',['seoul','numeric','numeric-string','naive'])
def test_departure_requires_iso_timezone_string_and_compares_utc(env,representation):
    _,client,clock,_ = env
    value = {
        'seoul':clock.now.astimezone(timezone(timedelta(hours=9))).isoformat(),
        'numeric':clock.now.timestamp(),'numeric-string':str(int(clock.now.timestamp())),
        'naive':clock.now.replace(tzinfo=None).isoformat(),
    }[representation]
    response = client.post('/api/v1/route-searches',json={'originStationId':'demo-stop-001',
        'destinationId':'demo-destination-001','departAt':value})
    if representation == 'seoul':
        assert response.status_code == 200
        assert details(client,response.json()['data'])[0]['computedAt'] == clock.now.isoformat().replace('+00:00','Z')
    else:
        assert_error(response,400,'INVALID_REQUEST')


def test_no_route_is_saved_empty_result_while_missing_search_or_option_is_404(env):
    app,client,clock,_ = env
    response = search(client,clock,'001','005')
    assert response.status_code == 200
    data = response.json()['data']
    assert data['routeOptions'] == []
    with app.state.database.session() as session:
        assert session.get(RouteSearch,data['routeSearchId']).snapshot == {}
    assert_error(client.get(f"/api/v1/route-searches/{data['routeSearchId']}/options/missing"),404,'NOT_FOUND')
    assert_error(client.get('/api/v1/route-searches/missing/options/missing'),404,'NOT_FOUND')


def test_option_must_belong_to_the_requested_search(env):
    _,client,clock,_ = env
    hospital,hospital_option,_ = selected(client,clock,'001')
    terminal,terminal_option,_ = selected(client,clock,'003')
    assert hospital_option['routeOptionId'] != terminal_option['routeOptionId']
    path = f"/api/v1/route-searches/{hospital['routeSearchId']}/options/{terminal_option['routeOptionId']}"
    assert_error(client.get(path),404,'NOT_FOUND')


def test_failed_search_does_not_leave_partial_search_row(env):
    app,client,clock,_ = env
    with app.state.database.session() as session:
        before = session.scalar(select(func.count()).select_from(RouteSearch))
    assert_error(search(client,clock,offset=121),400,'INVALID_REQUEST')
    assert_error(search(client,clock,destination='999'),404,'NOT_FOUND')
    assert_error(search(client,clock,origin='999'),404,'NOT_FOUND')
    with app.state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(RouteSearch)) == before


def test_later_search_does_not_rewrite_selected_detail(env):
    _,client,clock,_ = env
    data,option,path = selected(client,clock,'003')
    first = client.get(path).json()['data']
    clock.now += timedelta(seconds=30)
    newer,new_option,new_path = selected(client,clock,'003')
    assert newer['routeSearchId'] != data['routeSearchId']
    assert client.get(path).json()['data'] == first
    assert client.get(new_path).json()['data']['computedAt'] != first['computedAt']


@pytest.mark.parametrize('age,status',[(599.999,200),(600,410)])
def test_detail_obeys_half_open_search_lifetime(env,age,status):
    _,client,clock,_ = env
    data,option,path = selected(client,clock)
    clock.now += timedelta(seconds=age)
    if status == 200:
        assert client.get(path).status_code == 200
    else:
        assert_error(client.get(path),410,'ROUTE_SEARCH_EXPIRED')


def test_stored_search_can_be_read_after_app_restart():
    path = ROOT / '.local/tests' / ('stage4-'+uuid4().hex+'.sqlite3')
    settings = Settings(database_url='sqlite:///'+path.as_posix())
    clock = Clock()
    with TestClient(create_app(settings,clock=clock,provider=DemoProvider())) as client:
        data,option,endpoint = selected(client,clock,'003')
        original = client.get(endpoint).json()['data']
    with TestClient(create_app(settings,clock=clock,provider=DemoProvider())) as client:
        response = client.get(endpoint)
        assert response.status_code == 200
        assert response.json()['data'] == original


@pytest.mark.parametrize('fault',[
    'root-null','root-list','option-null','missing-legs','empty-legs','wrong-access-type',
    'stop-count','board-station','segment-duplicate','segment-order','segment-missing','transfer-reference',
])
def test_corrupt_snapshot_is_rejected_as_unverifiable_transport_data(env,fault):
    app,client,clock,_ = env
    data,option,path = selected(client,clock,'003')
    with app.state.database.session() as session:
        row = session.get(RouteSearch,data['routeSearchId'])
        snapshot = copy.deepcopy(row.snapshot)
        stored = snapshot[option['routeOptionId']]
        if fault == 'root-null': snapshot = None
        elif fault == 'root-list': snapshot = []
        elif fault == 'option-null': snapshot[option['routeOptionId']] = None
        elif fault == 'missing-legs': stored.pop('legs')
        elif fault == 'empty-legs': stored['legs'] = []
        elif fault == 'wrong-access-type': stored['accessStationId'] = 123
        elif fault == 'stop-count': stored['detail']['segments'][0]['stopCount'] = 999
        elif fault == 'board-station': stored['detail']['segments'][0]['boardStation']['stationId'] = 'invented'
        elif fault == 'segment-duplicate': stored['detail']['segments'][2]['segmentId'] = stored['detail']['segments'][0]['segmentId']
        elif fault == 'segment-order': stored['detail']['segments'].reverse()
        elif fault == 'segment-missing': stored['detail']['segments'].pop()
        elif fault == 'transfer-reference': stored['detail']['segments'][1]['toSegmentId'] = 'invented'
        row.snapshot = snapshot
    assert_error(client.get(path),503,'TRANSPORT_DATA_UNAVAILABLE')
