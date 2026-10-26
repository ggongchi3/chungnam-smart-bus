import asyncio
from datetime import timedelta
import json
from pathlib import Path
from threading import Event
from time import monotonic
from uuid import uuid4

import pytest
from pydantic import TypeAdapter
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from backend.api.errors import ServiceError
from backend.config import ROOT, Settings
from backend.database import Database
from backend.integrations.ai import AIBoundary
from backend.integrations.providers import DemoProvider
from backend.models import schemas as s
from backend.models.tables import (Destination, DestinationAccess, Route, RouteSearch, RouteStop,
                                   Station, TransferConnection)
from backend.seed import seed
from backend.services import routing
from backend.services.time import freshness
from backend.tests.conftest import search, selection


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert body['data'] is None and body['error']['code'] == code
    assert set(body) == {'data', 'error', 'meta'}
    s.Envelope[None].model_validate(body)
    assert response.headers['x-request-id'] == body['meta']['requestId']


def test_idempotent_seed_foreign_keys_and_rollback(env):
    app, client, clock, provider = env
    db = app.state.database
    seed(db)
    seed(db)
    with db.session() as session:
        assert [session.scalar(select(func.count()).select_from(t)) for t in
                [Station, Route, Destination, RouteStop, TransferConnection]] == [5, 2, 3, 6, 1]
    with pytest.raises(IntegrityError):
        with db.session() as session:
            session.add(Station(station_id='rollback-station', name='rollback', direction_label='demo'))
            session.flush()
            session.add(RouteStop(route_id='missing-route', sequence=1, station_id='rollback-station'))
            session.flush()
    with db.session() as session:
        assert session.get(Station, 'rollback-station') is None
    with pytest.raises(IntegrityError):
        with db.session() as session:
            session.add(TransferConnection(from_route_id='demo-route-001', from_sequence=999,
                to_route_id='demo-route-002', to_sequence=1, evidence='invalid'))
            session.flush()


def test_seed_does_not_overwrite_existing_changes(env):
    app, *_ = env
    with app.state.database.session() as session:
        session.get(Station, 'demo-stop-001').name = '팀원 변경'
    seed(app.state.database)
    with app.state.database.session() as session:
        assert session.get(Station, 'demo-stop-001').name == '팀원 변경'


def test_station_and_catalog(env):
    _, client, _, _ = env
    body = client.get('/api/v1/stations/demo-stop-001').json()
    assert body['data']['station']['name'] == '시연 출발 정류장'
    assert body['data']['station']['coordinates'] is None
    assert body['data']['station']['region'] is None
    TypeAdapter(s.Envelope[s.StationData]).validate_python(body)
    base = {'originStationId': 'demo-stop-001'}
    assert len(client.get('/api/v1/destinations', params=base).json()['data']['destinations']) == 3
    result = client.get('/api/v1/destinations', params={**base, 'query': '  장터  ', 'category': 'market'})
    assert result.json()['data']['destinations'][0]['destinationId'] == 'demo-destination-002'
    for fields in [{'query': '없음'}, {'query': '장터', 'category': 'hospital'}, {'query': '%'}]:
        assert client.get('/api/v1/destinations', params={**base, **fields}).json()['data']['destinations'] == []
    assert_error(client.get('/api/v1/stations/missing'), 404, 'NOT_FOUND')
    assert_error(client.get('/api/v1/destinations', params={'originStationId': 'missing'}), 404, 'NOT_FOUND')
    assert_error(client.get('/api/v1/destinations'), 400, 'INVALID_REQUEST')
    assert_error(client.get('/api/v1/destinations', params={**base, 'category': 'bad'}), 400, 'INVALID_REQUEST')
    assert_error(client.get('/api/v1/destinations', params={**base, 'query': 'x' * 101}), 400, 'INVALID_REQUEST')
    assert client.get('/api/v1/destinations', params={**base, 'query': ' ' + 'x' * 100 + ' '}).status_code == 200


@pytest.mark.parametrize('destination,total,transfers', [('002',1,0), ('001',2,0), ('003',4,1)])
def test_direct_and_transfer_routes(env, destination, total, transfers):
    _, client, clock, _ = env
    data = search(client, clock, destination).json()['data']
    assert len(data['routeOptions']) == 1
    option = data['routeOptions'][0]
    assert option['transferCount'] == transfers
    assert option['totalDurationSeconds'] is None and option['walkingDurationSeconds'] is None
    path = f"/api/v1/route-searches/{data['routeSearchId']}/options/{option['routeOptionId']}"
    detail = client.get(path).json()['data']
    s.RouteDetail.model_validate(detail)
    assert sum(p['stopCount'] for p in detail['segments'] if p['type'] == 'bus') == total
    assert len({p['segmentId'] for p in detail['segments']}) == len(detail['segments'])
    assert all(p.get('durationSeconds') is None for p in detail['segments'])
    assert detail['segments'][-1]['distanceMeters'] is None
    assert detail['routeSnapshotVersion'] == option['routeSnapshotVersion']
    if transfers:
        a,b,c,d = detail['segments']
        assert [p['type'] for p in (a,b,c,d)] == ['bus','transfer','bus','walk']
        assert b['fromSegmentId'] == a['segmentId'] and b['toSegmentId'] == c['segmentId']
        assert b['atStation']['stationId'] == 'demo-stop-003'


def test_reverse_unregistered_transfer_and_no_inference(env):
    app, client, clock, _ = env
    assert search(client, clock, '001', '005').json()['data']['routeOptions'] == []
    with app.state.database.session() as session:
        session.execute(delete(TransferConnection))
    # The same station ID/name alone is insufficient evidence for transfer.
    assert search(client, clock, '003').json()['data']['routeOptions'] == []


def test_candidates_deduplicate_and_sort(env):
    app, client, clock, _ = env
    with app.state.database.session() as session:
        for station_id in ['demo-stop-002', 'demo-stop-003', 'demo-stop-004']:
            session.add(DestinationAccess(destination_id='demo-destination-003', station_id=station_id))
    first = search(client, clock, '003').json()['data']['routeOptions']
    second = search(client, clock, '003').json()['data']['routeOptions']
    assert len(first) == 3
    assert [p['transferCount'] for p in first] == [0,0,1]
    assert [p['routeOptionId'] for p in first] == [p['routeOptionId'] for p in second]
    assert len({p['routeOptionId'] for p in first}) == 3
    data = search(client, clock, '003').json()['data']
    counts = []
    for option in data['routeOptions']:
        path = f"/api/v1/route-searches/{data['routeSearchId']}/options/{option['routeOptionId']}"
        detail = client.get(path).json()['data']
        counts.append(sum(p['stopCount'] for p in detail['segments'] if p['type'] == 'bus'))
    assert counts == [1,2,3]


@pytest.mark.parametrize('offset,ok', [(-121,False),(-120,True),(120,True),(121,False)])
def test_departure_boundary(env, offset, ok):
    _, client, clock, _ = env
    response = search(client, clock, offset=offset)
    if ok:
        assert response.status_code == 200
    else:
        assert_error(response, 400, 'INVALID_REQUEST')


@pytest.mark.parametrize('depart', ['2026-10-26T05:00:00', 'bad', None])
def test_departure_requires_aware_time(env, depart):
    _, client, *_ = env
    assert_error(client.post('/api/v1/route-searches', json={
        'originStationId':'demo-stop-001','destinationId':'demo-destination-001','departAt':depart}), 400, 'INVALID_REQUEST')


def test_missing_ids_extra_fields_malformed_json(env):
    _, client, clock, _ = env
    assert_error(search(client, clock, '999'), 404, 'NOT_FOUND')
    assert_error(search(client, clock, origin='999'), 404, 'NOT_FOUND')
    assert_error(client.post('/api/v1/route-searches', content='{', headers={'Content-Type':'application/json'}), 400, 'INVALID_REQUEST')
    assert_error(client.post('/api/v1/route-searches', json={'origin_station_id':1}), 400, 'INVALID_REQUEST')
    body, path = selection(client, clock)
    assert_error(client.get('/api/v1/route-searches/missing/options/missing'), 404, 'NOT_FOUND')
    assert_error(client.get(path + '-missing'), 404, 'NOT_FOUND')


@pytest.mark.parametrize('seconds,status', [(599,200),(600,410)])
def test_expiry_applies_to_all_selected_apis(env, seconds, status):
    _, client, clock, _ = env
    body,path = selection(client, clock)
    clock.now += timedelta(seconds=seconds)
    responses = [client.get(path), client.get(path+'/live'), client.post('/api/v1/easy-guidance',json=body),
                 client.post('/api/v1/print-guides',json=body)]
    for response in responses:
        if status == 200:
            assert response.status_code == 200, response.text
        else:
            assert_error(response,410,'ROUTE_SEARCH_EXPIRED')


@pytest.mark.parametrize('age,expected', [(0,'fresh'),(90,'fresh'),(91,'stale'),(None,'unknown'),(-1,'unknown')])
def test_freshness(env, age, expected):
    _, client, clock, _ = env
    source = None if age is None else clock.now - timedelta(seconds=age)
    assert freshness(source, clock.now) == expected


@pytest.mark.parametrize('scenario,arrival,coverage,fresh', [
    ('normal','available','available','fresh'),('arrivals_missing','unavailable','available','fresh'),
    ('stale','available','available','stale'),('source_missing','available','available','unknown'),
    ('source_future','available','available','unknown'),('changes_unknown','available','unknown','fresh')])
def test_live_partial_failures(make_app, scenario, arrival, coverage, fresh):
    app, client, clock, _ = make_app(scenario=scenario)
    body, path = selection(client, clock)
    live = client.get(path+'/live').json()['data']
    assert live['arrivals'][0]['arrivalStatus'] == arrival
    assert live['arrivals'][0]['operationStatus'] == 'unknown'
    assert live['arrivals'][0]['dataQuality']['freshness'] == fresh
    assert live['serviceChanges']['coverageStatus'] == coverage
    if arrival == 'unavailable':
        assert live['arrivals'][0]['etaSeconds'] is None and live['arrivals'][0]['expectedArrivalAt'] is None
    assert client.post('/api/v1/print-guides',json=body).status_code == 200


def test_polling_does_not_rejuvenate_source_or_change_version(env):
    _, client, clock, _ = env
    body,path = selection(client, clock)
    first = client.get(path+'/live').json()['data']
    clock.now += timedelta(seconds=91)
    second = client.get(path+'/live').json()['data']
    assert first['routeSnapshotVersion'] == second['routeSnapshotVersion']
    assert second['arrivals'][0]['dataQuality']['freshness'] == 'stale'
    assert second['arrivals'][0]['dataQuality']['sourceUpdatedAt'] == first['arrivals'][0]['dataQuality']['sourceUpdatedAt']
    assert second['arrivals'][0]['etaSeconds'] == 209


@pytest.mark.parametrize('scenario',['cancellation','detour','timetable_change'])
def test_service_change_invalidates_all_selected_apis(env, scenario):
    _, client, clock, provider = env
    body,path = selection(client, clock)
    provider.scenario = scenario
    for response in [client.get(path),client.get(path+'/live'),client.post('/api/v1/easy-guidance',json=body),
                     client.post('/api/v1/print-guides',json=body)]:
        assert_error(response,409,'ROUTE_VERSION_CHANGED')
    assert search(client, clock).json()['data']['routeOptions'] == []


def test_structure_and_transfer_version(env):
    app, client, clock, provider = env
    body,path = selection(client, clock)
    with app.state.database.session() as session:
        session.get(RouteStop,('demo-route-001',2)).station_id = 'demo-stop-004'
    assert_error(client.get(path),409,'ROUTE_VERSION_CHANGED')
    body,path = selection(client, clock,'003')
    with app.state.database.session() as session:
        session.execute(delete(TransferConnection))
    assert_error(client.get(path),409,'ROUTE_VERSION_CHANGED')


def test_expected_version_and_expiry_priority(env):
    _, client, clock, provider = env
    body,path = selection(client, clock)
    body['expectedRouteSnapshotVersion'] = 'old'
    assert_error(client.post('/api/v1/print-guides',json=body),409,'ROUTE_VERSION_CHANGED')
    assert_error(client.post('/api/v1/easy-guidance',json=body),409,'ROUTE_VERSION_CHANGED')
    provider.scenario = 'core_unavailable'
    assert_error(client.get(path),503,'TRANSPORT_DATA_UNAVAILABLE')
    clock.now += timedelta(seconds=600)
    assert_error(client.get(path),410,'ROUTE_SEARCH_EXPIRED')


def test_live_mode_never_uses_demo(make_app):
    _,client,clock,_ = make_app(mode='live')
    for response in [client.get('/api/v1/stations/demo-stop-001'),search(client,clock)]:
        assert_error(response,503,'TRANSPORT_DATA_UNAVAILABLE')
        assert response.json()['meta']['dataMode'] == 'live'


class GoodAI:
    def interpret_destination(self,payload):
        assert payload['allowedDestinations'][0]['destinationId'] == 'demo-destination-001'
        return {'status':'matched','candidateDestinationIds':['demo-destination-001'],'reasonCode':'USER_CONFIRMATION_REQUIRED'}

    def choose_guidance(self,payload):
        return {'status':'ok','routeSnapshotVersion':payload['routeSnapshotVersion'],
                'steps':[{'segmentId':p['segmentId'],'templateId':p['allowedTemplateIds'][0]} for p in payload['verifiedSegments']]}


def test_good_ai_and_fact_binding(make_app):
    app,client,clock,_ = make_app(adapter=GoodAI())
    response = client.post('/api/v1/destination-interpretations',json={'originStationId':'demo-stop-001','text':'병원'})
    assert response.json()['data']['status'] == 'matched'
    body,path = selection(client,clock,'003')
    guide = client.post('/api/v1/easy-guidance',json=body).json()['data']
    assert guide['mode'] == 'ai_assisted'
    assert '2개 정류장' in guide['steps'][0]['text']
    assert '시연 1번' in guide['steps'][0]['text']
    assert s.NOTICE in guide['steps'][0]['text']


@pytest.mark.parametrize('fault',['missing','extra','duplicate','reverse','template','version','exception','none'])
def test_ai_invalid_guidance_falls_back(make_app, fault):
    class Bad(GoodAI):
        def choose_guidance(self,payload):
            result = super().choose_guidance(payload)
            if fault == 'missing': result['steps'].pop()
            elif fault == 'extra': result['steps'].append({'segmentId':'invented','templateId':'walk.basic'})
            elif fault == 'duplicate': result['steps'][1] = result['steps'][0]
            elif fault == 'reverse': result['steps'].reverse()
            elif fault == 'template': result['steps'][0]['templateId'] = 'bus.invented'
            elif fault == 'version': result['routeSnapshotVersion'] = 'invented'
            elif fault == 'exception': raise RuntimeError('private data must never leak')
            elif fault == 'none': return None
            return result
    app,client,clock,_ = make_app(adapter=Bad())
    body,path = selection(client,clock,'003')
    response = client.post('/api/v1/easy-guidance',json=body)
    assert response.status_code == 200
    assert response.json()['data']['mode'] == 'template_fallback'
    assert len(response.json()['data']['steps']) == 4


@pytest.mark.parametrize('output', [None,
    {'status':'matched','candidateDestinationIds':['unknown'],'reasonCode':None},
    {'status':'no_match','candidateDestinationIds':['demo-destination-001'],'reasonCode':None},
    {'status':'matched','candidateDestinationIds':[],'reasonCode':None},
    {'status':'needs_confirmation','candidateDestinationIds':['demo-destination-001']*2,'reasonCode':None}])
def test_ai_unregistered_or_invalid_candidates(make_app, output):
    class Bad(GoodAI):
        def interpret_destination(self,payload): return output
    app,client,clock,_ = make_app(adapter=Bad())
    response = client.post('/api/v1/destination-interpretations',json={'originStationId':'demo-stop-001','text':'병원'})
    assert response.json()['data'] == {'status':'unavailable','candidates':[],'reasonCode':'AI_UNAVAILABLE'}


def test_ai_unconnected_and_text_validation(env):
    _,client,clock,_ = env
    base = {'originStationId':'demo-stop-001'}
    assert client.post('/api/v1/destination-interpretations',json={**base,'text':'병원'}).json()['data']['status'] == 'unavailable'
    for text in ['', '  ', 'x'*201, 12]:
        assert_error(client.post('/api/v1/destination-interpretations',json={**base,'text':text}),400,'INVALID_REQUEST')
    assert client.post('/api/v1/destination-interpretations',json={**base,'text':'x'*200}).status_code == 200
    body,path = selection(client,clock)
    assert client.post('/api/v1/easy-guidance',json=body).json()['data']['mode'] == 'template_fallback'


def test_ai_timeout_no_unbounded_workers_and_recovery(make_app):
    release,started = Event(),Event()
    class Slow(GoodAI):
        calls = 0
        def choose_guidance(self,payload):
            self.calls += 1
            started.set()
            release.wait(4)
            return super().choose_guidance(payload)
    adapter = Slow()
    app,client,clock,_ = make_app(adapter=adapter)
    body,path = selection(client,clock)
    start = monotonic()
    try:
        assert client.post('/api/v1/easy-guidance',json=body).json()['data']['mode'] == 'template_fallback'
        elapsed = monotonic() - start
        assert 0.9 <= elapsed < 2.5
        for _ in range(4):
            assert client.post('/api/v1/easy-guidance',json=body).json()['data']['mode'] == 'template_fallback'
        assert adapter.calls == 1
    finally:
        release.set()


def test_ai_interpret_exception_and_timeout(make_app):
    release = Event()
    class Slow(GoodAI):
        def interpret_destination(self,payload):
            release.wait(3)
            raise RuntimeError('private')
    app,client,clock,_ = make_app(adapter=Slow())
    try:
        assert client.post('/api/v1/destination-interpretations',json={'originStationId':'demo-stop-001','text':'병원'}).json()['data']['status'] == 'unavailable'
    finally:
        release.set()


def test_ai_immediate_interpret_exception(make_app):
    class Broken(GoodAI):
        def interpret_destination(self,payload):
            raise ValueError('private provider details')
    app,client,clock,_ = make_app(adapter=Broken())
    response = client.post('/api/v1/destination-interpretations',json={'originStationId':'demo-stop-001','text':'병원'})
    assert response.json()['data']['status'] == 'unavailable'
    assert 'private' not in response.text


@pytest.mark.parametrize('status,ids', [('no_match',[]), ('needs_confirmation',['demo-destination-001','demo-destination-002'])])
def test_ai_valid_non_matched_status(make_app,status,ids):
    class Adapter(GoodAI):
        def interpret_destination(self,payload):
            return {'status':status,'candidateDestinationIds':ids,'reasonCode':'untrusted text'}
    app,client,clock,_ = make_app(adapter=Adapter())
    data = client.post('/api/v1/destination-interpretations',json={'originStationId':'demo-stop-001','text':'병원'}).json()['data']
    assert data['status'] == status and [p['destinationId'] for p in data['candidates']] == ids
    assert data['reasonCode'] != 'untrusted text'


def test_guidance_rechecks_expiry_after_adapter(make_app):
    class Advance(GoodAI):
        def choose_guidance(self,payload):
            clock.now += timedelta(seconds=600)
            return super().choose_guidance(payload)
    app,client,clock,_ = make_app(adapter=Advance())
    body,path = selection(client,clock)
    assert_error(client.post('/api/v1/easy-guidance',json=body),410,'ROUTE_SEARCH_EXPIRED')


def test_ai_late_validation_not_adopted(make_app,monkeypatch):
    from backend.services import ai as service
    tick = iter([0.0,1.01])
    monkeypatch.setattr(service,'monotonic',lambda:next(tick))
    app,client,clock,_ = make_app(adapter=GoodAI())
    body,path = selection(client,clock)
    assert client.post('/api/v1/easy-guidance',json=body).json()['data']['mode'] == 'template_fallback'


def test_ai_slot_reopens_after_timed_out_worker_finishes():
    started,release,done = Event(),Event(),Event()
    class Adapter:
        calls = 0
        def choose_guidance(self,payload):
            self.calls += 1
            if self.calls == 1:
                started.set()
                release.wait(2)
                done.set()
            return {'ok':True}
    async def exercise():
        adapter = Adapter()
        boundary = AIBoundary(adapter,budget=0.05)
        assert await boundary.call('choose_guidance',{}) is None
        assert await boundary.call('choose_guidance',{}) is None
        assert adapter.calls == 1
        release.set()
        assert await asyncio.to_thread(done.wait,1)
        # Worker releases its lock immediately after setting the future result.
        for _ in range(20):
            result = await boundary.call('choose_guidance',{})
            if result is not None:
                assert result == {'ok':True}
                return
            await asyncio.sleep(0.01)
        pytest.fail('AI slot did not recover')
    try:
        asyncio.run(exercise())
    finally:
        release.set()


def test_stable_tie_key_and_repeat_stop_occurrences(env):
    app,client,clock,_ = env
    with app.state.database.session() as session:
        session.add(Route(route_id='demo-route-000',name='시연 우선 키',direction_label='합성'))
        session.flush()
        for seq,station in [(1,'demo-stop-001'),(2,'demo-stop-002'),(3,'demo-stop-001')]:
            session.add(RouteStop(route_id='demo-route-000',sequence=seq,station_id=station))
    data = search(client,clock,'002').json()['data']
    assert data['routeOptions'][0]['routeNames'] == ['시연 우선 키']
    assert len(data['routeOptions']) == 2
    # Later repeated origin occurrence cannot board backwards to sequence 2.
    with app.state.database.session() as session:
        candidates = routing.build_candidates(session,'demo-stop-001','demo-destination-002')
        assert all(a < b for legs,access in candidates for route,a,b in legs)


def test_print_fixed_consistent_and_no_countdown(env):
    app,client,clock,provider = env
    body,path = selection(client,clock,'003')
    first = client.post('/api/v1/print-guides',json=body).json()['data']
    s.PrintData.model_validate(first)
    assert first['routeDetail']['routeSnapshotVersion'] == first['liveInfoSnapshot']['routeSnapshotVersion'] == body['expectedRouteSnapshotVersion']
    assert first['guidance']['routeSnapshotVersion'] == body['expectedRouteSnapshotVersion']
    assert [p['segmentId'] for p in first['routeDetail']['segments']] == [p['segmentId'] for p in first['guidance']['steps']]
    assert all(p['etaSeconds'] is None for p in first['liveInfoSnapshot']['arrivals'])
    assert s.NOTICE in first['notice']
    saved = json.dumps(first,sort_keys=True)
    clock.now += timedelta(seconds=30)
    assert client.post('/api/v1/print-guides',json=body).json()['data']['printGuideId'] != first['printGuideId']
    assert json.dumps(first,sort_keys=True) == saved


def test_file_database_persistence_isolated_from_runtime(make_app):
    path = ROOT / '.local/tests' / (uuid4().hex + '.sqlite3')
    url = 'sqlite:///' + path.as_posix()
    app,client,clock,_ = make_app(url=url)
    body,endpoint = selection(client,clock)
    second,client2,clock2,_ = make_app(url=url)
    assert client2.get(endpoint).status_code == 200
    assert path != ROOT / '.local/bus.sqlite3'


def test_database_path_must_remain_local():
    with pytest.raises(ValueError): Database('sqlite:///outside.sqlite3')


def test_openapi_and_actual_json(env):
    app,client,clock,_ = env
    assert client.get('/docs').status_code == 200
    schema = client.get('/openapi.json').json()
    operations = [v for p in schema['paths'].values() for v in p.values()]
    assert len(operations) == 8
    assert all('422' not in v['responses'] and '400' in v['responses'] for v in operations)
    assert schema['components']['schemas']['SearchRequest']['required'] == ['originStationId','destinationId','departAt']
    assert schema['components']['schemas']['Bus']['properties']['type']['const'] == 'bus'
    body,path = selection(client,clock)
    for endpoint,model in [(path,s.RouteDetail),(path+'/live',s.LiveData)]:
        TypeAdapter(s.Envelope[model]).validate_python(client.get(endpoint).json())
    assert_error(client.post('/api/v1/easy-guidance',json={}),400,'INVALID_REQUEST')


def test_local_cors_and_request_metadata(env):
    _,client,clock,_ = env
    path = '/api/v1/stations/demo-stop-001'
    allowed = client.options(path,headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'GET'})
    assert allowed.headers['access-control-allow-origin'] == 'http://localhost:5173'
    denied = client.options(path,headers={'Origin':'https://untrusted.example','Access-Control-Request-Method':'GET'})
    assert 'access-control-allow-origin' not in denied.headers
    response = client.get(path)
    assert response.headers['cache-control'] == 'no-store'
    meta = response.json()['meta']
    assert meta['dataMode'] == 'demo'
    assert meta['generatedAt'] == clock.now.isoformat().replace('+00:00','Z')
