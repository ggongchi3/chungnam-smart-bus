"""Station/destination API acceptance criteria from stage 3 of the v2 plan."""
import json
from datetime import datetime

import pytest
from pydantic import TypeAdapter

from backend.models import schemas as s
from backend.models.tables import Destination, DestinationAlias, Station
from backend.seed import DEMO_SOURCE

BASE = {'originStationId': 'demo-stop-001'}


def ids(response):
    assert response.status_code == 200, response.text
    data = TypeAdapter(s.Envelope[s.DestinationData]).validate_python(response.json()).data
    return [d.destinationId for d in data.destinations]


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = s.Envelope[None].model_validate(response.json())
    assert body.data is None and body.error.code == code
    assert response.headers['x-request-id'] == body.meta.requestId


@pytest.mark.parametrize('number', range(1, 6))
def test_registered_station_fields_and_unknown_values(env, number):
    _, client, *_ = env
    source = json.loads(DEMO_SOURCE.read_text(encoding='utf-8'))['stations'][number - 1]
    response = client.get('/api/v1/stations/' + source['station_id'])
    assert response.status_code == 200
    station = s.Envelope[s.StationData].model_validate(response.json()).data.station
    assert station.stationId == source['station_id'] and station.name == source['name']
    assert station.directionLabel == source['direction_label']
    assert station.region is None and station.coordinates is None
    assert station.name in response.content.decode('utf-8')
    assert set(response.json()['data']['station']) == {
        'stationId','name','directionLabel','region','coordinates'}


@pytest.mark.parametrize('query,category,expected', [
    ('시연 병원',None,'001'), ('시연 큰 병원',None,'001'), ('','hospital','001'),
    ('시연 시장',None,'002'), ('시연 장터',None,'002'), ('','market','002'),
    ('시연 터미널',None,'003'), ('시연 버스터미널',None,'003'), ('','terminal','003'),
])
def test_main_places_names_aliases_categories_share_ids(env, query, category, expected):
    _,client,*_ = env
    params = {**BASE,'query':query}
    if category is not None:
        params['category'] = category
    assert ids(client.get('/api/v1/destinations',params=params)) == ['demo-destination-'+expected]


@pytest.mark.parametrize('query,category,expected', [
    ('  장터  ','market',['demo-destination-002']),
    ('장터','hospital',[]), ('병원','terminal',[]),
    ('','station',[]), ('','other',[]),
])
def test_intersection_and_supported_empty_categories(env, query, category, expected):
    _,client,*_ = env
    assert ids(client.get('/api/v1/destinations',params={**BASE,'query':query,'category':category})) == expected


@pytest.mark.parametrize('query,valid', [
    ('가'*100,True), (' \t'+'가'*100+'\n ',True),
    ('가'*101,False), (' '+'x'*101+' ',False),
])
def test_query_length_checked_after_trimming(env, query, valid):
    _,client,*_ = env
    response = client.get('/api/v1/destinations',params={**BASE,'query':query})
    if valid:
        assert ids(response) == []
    else:
        assert_error(response,400,'INVALID_REQUEST')


@pytest.mark.parametrize('query', [None,'',' \t\n '])
def test_empty_query_returns_registered_catalog(env, query):
    _,client,*_ = env
    params = dict(BASE)
    if query is not None:
        params['query'] = query
    response = client.get('/api/v1/destinations',params=params)
    assert ids(response) == ['demo-destination-001','demo-destination-002','demo-destination-003']
    values = response.json()['data']['destinations']
    expected = json.loads(DEMO_SOURCE.read_text(encoding='utf-8'))
    assert [d['name'] for d in values] == [d['name'] for d in expected['destinations']]
    assert all(isinstance(d['destinationId'],str) and isinstance(d['aliases'],list) for d in values)


@pytest.mark.parametrize('params,status,code', [
    ({},400,'INVALID_REQUEST'), ({'originStationId':''},400,'INVALID_REQUEST'),
    ({'originStationId':'x'*201},400,'INVALID_REQUEST'),
    ({'originStationId':'not-registered'},404,'NOT_FOUND'),
    ({**BASE,'category':'bad'},400,'INVALID_REQUEST'),
    ({**BASE,'category':''},400,'INVALID_REQUEST'),
    ({**BASE,'category':'HOSPITAL'},400,'INVALID_REQUEST'),
])
def test_invalid_input_and_missing_targets_differ(env, params, status, code):
    _,client,*_ = env
    assert_error(client.get('/api/v1/destinations',params=params),status,code)
    assert_error(client.get('/api/v1/stations/not-registered'),404,'NOT_FOUND')


@pytest.mark.parametrize('query', ['%', '_', "' OR 1=1 --", '<script>alert(1)</script>'])
def test_search_treats_special_characters_as_literal_text(env, query):
    _,client,*_ = env
    assert ids(client.get('/api/v1/destinations',params={**BASE,'query':query})) == []


def test_responses_read_committed_database_values(env):
    app,client,*_ = env
    with app.state.database.session() as session:
        session.get(Station,'demo-stop-001').direction_label = '테스트 방향 변경'
        session.get(Destination,'demo-destination-002').name = '합성 변경 시장'
        session.add(DestinationAlias(destination_id='demo-destination-002',alias='NEW Demo Alias'))
    assert client.get('/api/v1/stations/demo-stop-001').json()['data']['station']['directionLabel'] == '테스트 방향 변경'
    assert ids(client.get('/api/v1/destinations',params={**BASE,'query':'합성 변경 시장'})) == ['demo-destination-002']
    assert ids(client.get('/api/v1/destinations',params={**BASE,'query':' new DEMO alias '})) == ['demo-destination-002']


def test_same_name_does_not_merge_different_destination_ids(env):
    app,client,*_ = env
    with app.state.database.session() as session:
        session.get(Destination,'demo-destination-002').name = '시연 병원'
    assert ids(client.get('/api/v1/destinations',params={**BASE,'query':'시연 병원'})) == [
        'demo-destination-001','demo-destination-002']


def test_metadata_is_consistent_for_success_empty_and_errors(env):
    _,client,clock,_ = env
    responses = [client.get('/api/v1/stations/demo-stop-001'),
        client.get('/api/v1/destinations',params={**BASE,'query':'없음'}),
        client.get('/api/v1/destinations',params={**BASE,'category':'bad'}),
        client.get('/api/v1/stations/not-registered')]
    request_ids = []
    for response in responses:
        body = response.json()
        assert set(body) == {'data','error','meta'}
        assert set(body['meta']) == {'requestId','generatedAt','dataMode'}
        assert body['meta']['dataMode'] == 'demo'
        assert datetime.fromisoformat(body['meta']['generatedAt']) == clock.now
        assert body['meta']['requestId'] == response.headers['x-request-id']
        assert response.headers['cache-control'] == 'no-store'
        request_ids.append(body['meta']['requestId'])
    assert len(set(request_ids)) == len(responses)


@pytest.mark.parametrize('origin',['http://localhost:5173','http://127.0.0.1:5173'])
def test_cors_for_both_gets_and_application_errors(env, origin):
    _,client,*_ = env
    for path in ['/api/v1/stations/demo-stop-001','/api/v1/destinations']:
        response = client.options(path,headers={'Origin':origin,'Access-Control-Request-Method':'GET'})
        assert response.status_code == 200
        assert response.headers['access-control-allow-origin'] == origin
    for path in ['/api/v1/stations/demo-stop-001','/api/v1/stations/not-registered','/api/v1/destinations']:
        response = client.get(path,headers={'Origin':origin})
        assert response.headers['access-control-allow-origin'] == origin


def test_extra_query_arguments_remain_ignored(env):
    _,client,*_ = env
    assert ids(client.get('/api/v1/destinations',params={**BASE,'unused':'compatible'})) == [
        'demo-destination-001','demo-destination-002','demo-destination-003']


def test_openapi_filters_match_actual_validation(env):
    _,client,*_ = env
    schema = client.get('/openapi.json').json()
    operation = schema['paths']['/api/v1/destinations']['get']
    parameters = {p['name']:p for p in operation['parameters']}
    assert set(parameters) == {'originStationId','query','category','kind','sort'}
    assert parameters['originStationId']['required'] is True
    assert parameters['query']['schema']['maxLength'] == 100
    assert parameters['query']['schema']['default'] == ''
    assert parameters['category']['required'] is False
    assert '400' in operation['responses'] and '422' not in operation['responses']
    assert parameters['category']['schema']['anyOf'][0]['enum'] == ['hospital','market','terminal','station','other']
