"""Stage 5 time, partial failure, service-change scope, and shared guards."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from backend.integrations import providers
from backend.models import schemas as s
from backend.models.tables import DestinationAccess, Route, RouteSearch
from backend.services import routing
from backend.services.time import quality
from backend.tests.conftest import selection


def assert_error(response,status,code):
    assert response.status_code == status,response.text
    payload = s.Envelope[None].model_validate(response.json())
    assert payload.data is None and payload.error.code == code


def parsed(value):
    return None if value is None else datetime.fromisoformat(value)


def freeze_provider(app,provider,clock,**changes):
    base = provider.read(clock.now)
    if changes.get('arrivals_available') is False and 'arrivals' not in changes:
        changes['arrivals'] = {key:replace(value,expected_arrival_at=None) for key,value in base.arrivals.items()}
    observation_fields = {name:changes[name] for name in ('source_updated_at','fetched_at') if name in changes}
    if observation_fields and 'arrivals' not in changes:
        changes['arrivals'] = {key:replace(value,**observation_fields) for key,value in base.arrivals.items()}
    fixed = replace(base,**changes)
    app.state.provider.read = lambda now: fixed
    return fixed


def change(clock,*,change_id='test-change',routes=None,stations=None,start=0,end=None,
           kind='cancellation',source_age=0):
    now = clock.now
    return s.Change(changeId=change_id,type=kind,
        affectedRouteIds=['demo-route-001'] if routes is None else routes,
        affectedStationIds=[] if stations is None else stations,
        title='합성 운행 변경 테스트',description='테스트 자료',
        validFrom=None if start is None else now+timedelta(seconds=start),
        validUntil=None if end is None else now+timedelta(seconds=end),
        dataQuality=quality(None if source_age is None else now-timedelta(seconds=source_age),now,now))


def publish_changes(app,provider,clock,items,coverage='available'):
    base = provider.read(clock.now)
    state = replace(base,changes=base.changes.model_copy(update={'coverageStatus':coverage,'items':items}))
    app.state.provider.read = lambda now: state
    return state


def all_selected_responses(client,body,path):
    return [client.get(path),client.get(path+'/live'),
            client.post('/api/v1/easy-guidance',json=body),
            client.post('/api/v1/print-guides',json=body)]


@pytest.mark.parametrize('age,freshness',[(0,'fresh'),(90,'fresh'),(90.000001,'stale'),
    (91,'stale'),(None,'unknown'),(-0.000001,'unknown')])
def test_live_freshness_uses_source_age_including_fractional_boundaries(env,age,freshness):
    app,client,clock,provider = env
    body,path = selection(client,clock)
    source = None if age is None else clock.now-timedelta(seconds=age)
    freeze_provider(app,provider,clock,source_updated_at=source,fetched_at=clock.now)
    response = client.get(path+'/live')
    assert response.status_code == 200
    arrival = s.Envelope[s.LiveData].model_validate(response.json()).data.arrivals[0]
    assert arrival.dataQuality.freshness == freshness
    assert arrival.dataQuality.sourceUpdatedAt == source
    assert arrival.dataQuality.fetchedAt == clock.now
    assert arrival.operationStatus == 'unknown'


def test_source_fetched_and_generated_times_remain_independent_per_feed(env):
    app,client,clock,provider = env
    body,path = selection(client,clock)
    arrival_source = clock.now-timedelta(seconds=55)
    arrival_fetched = clock.now-timedelta(seconds=12)
    changes_source = clock.now-timedelta(seconds=88)
    changes_fetched = clock.now-timedelta(seconds=9)
    base = provider.read(clock.now)
    changes = base.changes.model_copy(update={'dataQuality':quality(changes_source,changes_fetched,clock.now)})
    freeze_provider(app,provider,clock,source_updated_at=arrival_source,
                    fetched_at=arrival_fetched,changes=changes)
    clock.now += timedelta(seconds=7)
    response = client.get(path+'/live').json()
    aq = response['data']['arrivals'][0]['dataQuality']
    cq = response['data']['serviceChanges']['dataQuality']
    assert parsed(aq['sourceUpdatedAt']) == arrival_source
    assert parsed(aq['fetchedAt']) == arrival_fetched
    assert parsed(cq['sourceUpdatedAt']) == changes_source
    assert parsed(cq['fetchedAt']) == changes_fetched
    assert parsed(response['meta']['generatedAt']) == clock.now
    assert len({aq['sourceUpdatedAt'],aq['fetchedAt'],cq['sourceUpdatedAt'],cq['fetchedAt'],response['meta']['generatedAt']}) == 5
    assert aq['freshness'] == 'fresh'
    # The source is now 95 seconds old; a new response does not make it fresh.
    assert cq['freshness'] == 'stale'


def test_freshness_compares_aware_source_in_utc_not_display_offset(env):
    app,client,clock,provider = env
    body,path = selection(client,clock)
    seoul = timezone(timedelta(hours=9))
    source = (clock.now-timedelta(seconds=90)).astimezone(seoul)
    freeze_provider(app,provider,clock,source_updated_at=source,fetched_at=clock.now)
    data = client.get(path+'/live').json()['data']
    assert data['arrivals'][0]['dataQuality']['freshness'] == 'fresh'
    assert parsed(data['arrivals'][0]['dataQuality']['sourceUpdatedAt']) == clock.now-timedelta(seconds=90)


@pytest.mark.parametrize('arrivals,coverage',[(False,'available'),(True,'unknown'),(False,'unknown')])
def test_partial_feed_failures_keep_ready_route_without_fabricating_facts(env,arrivals,coverage):
    app,client,clock,provider = env
    body,path = selection(client,clock,'003')
    base = provider.read(clock.now)
    changes = base.changes.model_copy(update={'coverageStatus':coverage,'items':[],
        'dataQuality':quality(None,None,clock.now,None) if coverage=='unknown' else base.changes.dataQuality})
    freeze_provider(app,provider,clock,arrivals_available=arrivals,changes=changes)
    live = client.get(path+'/live')
    assert live.status_code == 200
    data = live.json()['data']
    assert data['routeSnapshotVersion'] == body['expectedRouteSnapshotVersion']
    assert len(data['arrivals']) == 2
    if not arrivals:
        assert all(a['arrivalStatus']=='unavailable' and a['etaSeconds'] is None and
                   a['expectedArrivalAt'] is None and a['operationStatus']=='unknown' for a in data['arrivals'])
    if coverage=='unknown':
        assert data['serviceChanges']['coverageStatus']=='unknown'
        assert data['serviceChanges']['items']==[]
        assert data['serviceChanges']['dataQuality']=={
            'sourceId':None,'sourceUpdatedAt':None,'fetchedAt':None,'freshness':'unknown'}
    for response in all_selected_responses(client,body,path):
        assert response.status_code == 200,response.text
    printed = client.post('/api/v1/print-guides',json=body).json()['data']
    assert all(a['etaSeconds'] is None for a in printed['liveInfoSnapshot']['arrivals'])
    assert s.NOTICE in printed['notice']


@pytest.mark.parametrize('start,end,blocked',[(1,None,False),(-1,0,False),(0,1,True),
    (-1,1,True),(-10,-1,False)])
def test_change_applicability_uses_inclusive_start_exclusive_end(env,start,end,blocked):
    app,client,clock,provider = env
    body,path = selection(client,clock)
    publish_changes(app,provider,clock,[change(clock,start=start,end=end)])
    responses = all_selected_responses(client,body,path)
    for response in responses:
        if blocked:
            assert_error(response,409,'ROUTE_UNAVAILABLE')
        else:
            assert response.status_code==200,response.text
    if not blocked:
        assert client.get(path).json()['data']['routeSnapshotVersion']==body['expectedRouteSnapshotVersion']


@pytest.mark.parametrize('routes,stations,destination,blocked',[
    (['demo-route-002'],[],'001',False),
    ([],['demo-stop-003'],'002',False),  # Same route, beyond the selected market stop.
    ([],['demo-stop-002'],'001',True),   # Intermediate stop lies inside the selected bus leg.
    ([],['demo-stop-001'],'001',True),
    ([],['not-registered'],'001',False),
])
def test_change_route_and_station_scope_matches_selected_occurrences(env,routes,stations,destination,blocked):
    app,client,clock,provider = env
    body,path = selection(client,clock,destination)
    publish_changes(app,provider,clock,[change(clock,routes=routes,stations=stations)])
    for response in all_selected_responses(client,body,path):
        if blocked:
            assert_error(response,409,'ROUTE_UNAVAILABLE')
        else:
            assert response.status_code==200,response.text


def test_reordering_equivalent_change_items_keeps_version(env):
    app,client,clock,provider = env
    base = provider.read(clock.now)
    first = change(clock,change_id='test-b',kind='other')
    second = change(clock,change_id='test-a',kind='timetable_change')
    a = replace(base,changes=base.changes.model_copy(update={'items':[first,second]}))
    b = replace(base,changes=base.changes.model_copy(update={'items':[second,first]}))
    with app.state.database.session() as session:
        access = session.get(DestinationAccess,('demo-destination-001','demo-stop-003'))
        value_a = routing.route_state(session,[('demo-route-001',1,3)],access,'시연 병원',a,clock.now)
        value_b = routing.route_state(session,[('demo-route-001',1,3)],access,'시연 병원',b,clock.now)
    assert value_a[1] == value_b[1]
    assert value_a[2] == value_b[2]


@pytest.mark.parametrize('case,status,code',[
    ('missing-search-and-core',404,'NOT_FOUND'),
    ('expired-missing-option-and-core',410,'ROUTE_SEARCH_EXPIRED'),
    ('missing-option-and-core',404,'NOT_FOUND'),
    ('core-and-expected-version',503,'TRANSPORT_DATA_UNAVAILABLE'),
    ('reference-version',409,'ROUTE_VERSION_CHANGED'),
    ('stored-data-mode',409,'ROUTE_VERSION_CHANGED'),
])
def test_shared_guard_priority_is_identical_for_detail_live_guidance_print(env,case,status,code):
    app,client,clock,provider = env
    body,path = selection(client,clock)
    if case=='missing-search-and-core':
        body['routeSearchId']='missing-search'
    elif case=='expired-missing-option-and-core':
        clock.now+=timedelta(seconds=600)
        body['routeOptionId']='missing-option'
    elif case=='missing-option-and-core':
        body['routeOptionId']='missing-option'
    elif case=='core-and-expected-version':
        body['expectedRouteSnapshotVersion']='old-version'
    elif case=='reference-version':
        with app.state.database.session() as session:
            session.get(Route,'demo-route-001').name='합성 노선명 변경'
    elif case=='stored-data-mode':
        with app.state.database.session() as session:
            session.get(RouteSearch,body['routeSearchId']).data_mode='live'
    if case in {'missing-search-and-core','expired-missing-option-and-core','missing-option-and-core','core-and-expected-version'}:
        freeze_provider(app,provider,clock,core_available=False)
    path=f"/api/v1/route-searches/{body['routeSearchId']}/options/{body['routeOptionId']}"
    for response in all_selected_responses(client,body,path):
        assert_error(response,status,code)


def test_all_selected_surfaces_transition_at_exact_expiry_without_waiting(env):
    _,client,clock,_ = env
    body,path=selection(client,clock)
    clock.now+=timedelta(seconds=599,microseconds=999999)
    for response in all_selected_responses(client,body,path):
        assert response.status_code==200,response.text
    clock.now+=timedelta(microseconds=1)
    for response in all_selected_responses(client,body,path):
        assert_error(response,410,'ROUTE_SEARCH_EXPIRED')


def test_explicit_arrival_update_changes_eta_without_changing_path_version(env):
    app,client,clock,provider=env
    body,path=selection(client,clock)
    before=client.get(path+'/live').json()['data']
    state=provider.read(clock.now)
    key=('demo-route-001','demo-stop-001')
    observation=replace(state.arrivals[key],expected_arrival_at=clock.now+timedelta(seconds=123),
                        source_updated_at=clock.now,fetched_at=clock.now)
    values={**state.arrivals,key:observation}
    freeze_provider(app,provider,clock,arrivals=values)
    after=client.get(path+'/live').json()['data']
    assert before['arrivals'][0]['etaSeconds']!=after['arrivals'][0]['etaSeconds']
    assert after['arrivals'][0]['etaSeconds']==123
    assert parsed(after['arrivals'][0]['expectedArrivalAt'])==clock.now+timedelta(seconds=123)
    assert before['routeSnapshotVersion']==after['routeSnapshotVersion']==body['expectedRouteSnapshotVersion']
    for response in all_selected_responses(client,body,path):
        assert response.status_code==200,response.text


@pytest.mark.parametrize('observation_kind',['missing-key','explicit-no-eta','past-event'])
def test_collection_time_is_never_used_to_invent_an_arrival(env,observation_kind):
    app,client,clock,provider=env
    body,path=selection(client,clock)
    state=provider.read(clock.now)
    key=('demo-route-001','demo-stop-001')
    values=dict(state.arrivals)
    if observation_kind=='missing-key':
        values.pop(key,None)
    else:
        values[key]=providers.ArrivalObservation(
            expected_arrival_at=clock.now-timedelta(seconds=1) if observation_kind=='past-event' else None,
            source_updated_at=clock.now,fetched_at=clock.now,operation_status='unknown',source_id='test-feed')
    freeze_provider(app,provider,clock,arrivals_available=True,arrivals=values)
    response=client.get(path+'/live')
    assert response.status_code==200
    item=response.json()['data']['arrivals'][0]
    assert item['arrivalStatus']=='unavailable'
    assert item['etaSeconds'] is None and item['expectedArrivalAt'] is None
    assert item['operationStatus']=='unknown'
    if observation_kind=='missing-key':
        assert item['dataQuality']=={'sourceId':None,'sourceUpdatedAt':None,'fetchedAt':None,'freshness':'unknown'}


def test_each_bus_observation_keeps_its_own_quality_and_nulls(env):
    app,client,clock,provider=env
    body,path=selection(client,clock,'003')
    state=provider.read(clock.now)
    first_source=clock.now-timedelta(seconds=91)
    first_fetched=clock.now-timedelta(seconds=8)
    arrivals={
        ('demo-route-001','demo-stop-001'):providers.ArrivalObservation(
            expected_arrival_at=clock.now+timedelta(seconds=77),operation_status='running',
            source_updated_at=first_source,fetched_at=first_fetched,source_id='test-route-001-feed'),
        ('demo-route-002','demo-stop-003'):providers.ArrivalObservation(expected_arrival_at=None),
    }
    freeze_provider(app,provider,clock,arrivals=arrivals)
    response=client.get(path+'/live')
    assert response.status_code==200
    first,second=response.json()['data']['arrivals']
    assert first['routeId']=='demo-route-001' and first['etaSeconds']==77
    assert first['operationStatus']=='running' and first['dataQuality']['freshness']=='stale'
    assert parsed(first['dataQuality']['sourceUpdatedAt'])==first_source
    assert parsed(first['dataQuality']['fetchedAt'])==first_fetched
    assert second['routeId']=='demo-route-002' and second['arrivalStatus']=='unavailable'
    assert second['operationStatus']=='unknown'
    assert second['dataQuality']=={'sourceId':None,'sourceUpdatedAt':None,'fetchedAt':None,'freshness':'unknown'}


@pytest.mark.parametrize('scenario,arrival,status',[
    ('operation_running','available','running'),
    ('arrivals_missing_running','unavailable','running'),
])
def test_explicit_operation_status_is_independent_of_arrival_receipt(env,scenario,arrival,status):
    _,client,clock,provider=env
    body,path=selection(client,clock)
    provider.scenario=scenario
    response=client.get(path+'/live')
    assert response.status_code==200
    data=response.json()['data']
    assert data['arrivals'][0]['arrivalStatus']==arrival
    assert data['arrivals'][0]['operationStatus']==status
    assert data['routeSnapshotVersion']==body['expectedRouteSnapshotVersion']


def test_fresh_explicit_not_running_blocks_selected_path_and_new_search(env):
    from backend.tests.conftest import search
    _,client,clock,provider=env
    body,path=selection(client,clock)
    provider.scenario='operation_not_running'
    for response in all_selected_responses(client,body,path):
        assert_error(response,409,'ROUTE_UNAVAILABLE')
    assert search(client,clock).json()['data']['routeOptions']==[]


@pytest.mark.parametrize('case,status,code',[
    ('missing',404,'NOT_FOUND'),('expired',410,'ROUTE_SEARCH_EXPIRED'),
    ('valid',503,'TRANSPORT_DATA_UNAVAILABLE'),
])
def test_provider_exception_maps_to_core_failure_after_search_existence_and_expiry(env,case,status,code):
    app,client,clock,provider=env
    body,path=selection(client,clock)
    if case=='missing':
        body['routeSearchId']='missing-search'
        path=f"/api/v1/route-searches/{body['routeSearchId']}/options/{body['routeOptionId']}"
    elif case=='expired':
        clock.now+=timedelta(seconds=600)
    def unavailable(now):
        raise RuntimeError('private transport provider details')
    app.state.provider.read=unavailable
    for response in all_selected_responses(client,body,path):
        assert_error(response,status,code)
        assert 'private' not in response.text


def test_unknown_change_start_cannot_confirm_current_cancellation(env):
    app,client,clock,provider=env
    state=publish_changes(app,provider,clock,[change(clock,start=None,end=None)])
    with app.state.database.session() as session:
        access=session.get(DestinationAccess,('demo-destination-001','demo-stop-003'))
        segments,version,status=routing.route_state(session,[('demo-route-001',1,3)],access,'시연 병원',state,clock.now)
    assert status=='recheck_required'


def test_equivalent_change_scope_sets_do_not_change_route_version(env):
    app,client,clock,provider=env
    base=provider.read(clock.now)
    first=change(clock,kind='other',routes=['demo-route-002','demo-route-001','demo-route-001'],
                 stations=['demo-stop-003','demo-stop-001','demo-stop-003'])
    equivalent=first.model_copy(update={'affectedRouteIds':['demo-route-001','demo-route-002'],
                                        'affectedStationIds':['demo-stop-001','demo-stop-003']})
    states=[replace(base,changes=base.changes.model_copy(update={'items':[item]}))
            for item in (first,equivalent)]
    with app.state.database.session() as session:
        access=session.get(DestinationAccess,('demo-destination-001','demo-stop-003'))
        original,current=[routing.route_state(session,[('demo-route-001',1,3)],access,'시연 병원',state,clock.now)
                          for state in states]
    assert original[1]==current[1]
    assert original[2]==current[2]=='recheck_required'


def test_invalid_arrival_source_id_is_isolated_as_partial_failure(env):
    app,client,clock,provider=env
    body,path=selection(client,clock,'003')
    state=provider.read(clock.now)
    key=('demo-route-001','demo-stop-001')
    broken=replace(state.arrivals[key],source_id=123)
    freeze_provider(app,provider,clock,arrivals={**state.arrivals,key:broken})
    response=client.get(path+'/live')
    assert response.status_code==200,response.text
    payload=s.Envelope[s.LiveData].model_validate(response.json())
    assert payload.error is None and payload.data.routeSnapshotVersion==body['expectedRouteSnapshotVersion']
    first,second=payload.data.arrivals
    assert first.arrivalStatus=='unavailable' and first.operationStatus=='unknown'
    assert first.etaSeconds is None and first.expectedArrivalAt is None
    assert first.dataQuality.model_dump()=={
        'sourceId':None,'sourceUpdatedAt':None,'fetchedAt':None,'freshness':'unknown'}
    assert second.routeId=='demo-route-002' and second.arrivalStatus=='available'
    assert second.dataQuality.sourceId=='demo-fixture'
    for result in all_selected_responses(client,body,path):
        assert result.status_code==200,result.text


@pytest.mark.parametrize('field',['changes','arrivals'])
def test_malformed_optional_feed_does_not_erase_confirmed_core_route(env,field):
    app,client,clock,provider=env
    body,path=selection(client,clock,'003')
    freeze_provider(app,provider,clock,**{field:None})
    response=client.get(path+'/live')
    assert response.status_code==200,response.text
    data=s.Envelope[s.LiveData].model_validate(response.json()).data
    assert data.routeSnapshotVersion==body['expectedRouteSnapshotVersion']
    if field=='changes':
        assert data.serviceChanges.coverageStatus=='unknown' and data.serviceChanges.items==[]
        assert data.serviceChanges.dataQuality.model_dump()=={
            'sourceId':None,'sourceUpdatedAt':None,'fetchedAt':None,'freshness':'unknown'}
        assert all(item.arrivalStatus=='available' for item in data.arrivals)
    else:
        assert all(item.arrivalStatus=='unavailable' and item.etaSeconds is None and
                   item.expectedArrivalAt is None and item.operationStatus=='unknown' for item in data.arrivals)
        assert data.serviceChanges.coverageStatus=='available'
    for result in all_selected_responses(client,body,path):
        assert result.status_code==200,result.text
