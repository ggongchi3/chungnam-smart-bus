"""Stage 6 AI trust boundaries, bounded work, and fixed print snapshots.

All adapters in this file are test fakes; no real AI implementation is supplied.
"""
import asyncio
import copy
from dataclasses import replace
from datetime import datetime, timedelta
from threading import Event
import warnings

import pytest

from backend.integrations.ai import AIBoundary
from backend.models import schemas as s
from backend.models.tables import Destination, DestinationAccess, Route
from backend.tests.conftest import selection


class ValidAdapter:
    def __init__(self):
        self.interpret_calls=0
        self.guidance_calls=0
        self.interpret_payload=None
        self.guidance_payload=None

    def interpret_destination(self,payload):
        self.interpret_calls+=1
        self.interpret_payload=copy.deepcopy(payload)
        return {'status':'matched','candidateDestinationIds':['demo-destination-001'],'reasonCode':None}

    def choose_guidance(self,payload):
        self.guidance_calls+=1
        self.guidance_payload=copy.deepcopy(payload)
        return valid_choices(payload)


def valid_choices(payload):
    return {'status':'ok','routeSnapshotVersion':payload['routeSnapshotVersion'],
            'steps':[{'segmentId':p['segmentId'],'templateId':p['allowedTemplateIds'][0]}
                     for p in payload['verifiedSegments']]}


def assert_error(response,status,code):
    assert response.status_code==status,response.text
    value=s.Envelope[None].model_validate(response.json())
    assert value.data is None and value.error.code==code


@pytest.mark.parametrize('text,valid',[
    ('가',True),('가'*200,True),(' \t'+'가'*200+'\n ',True),
    ('가'*201,False),('',False),(' \n ',False),
])
def test_text_limits_are_checked_before_ai_and_payload_is_trimmed(make_app,text,valid):
    adapter=ValidAdapter()
    app,client,clock,_=make_app(adapter=adapter)
    response=client.post('/api/v1/destination-interpretations',json={'originStationId':'demo-stop-001','text':text})
    if valid:
        assert response.status_code==200
        assert adapter.interpret_calls==1
        assert adapter.interpret_payload['text']==text.strip()
    else:
        assert_error(response,400,'INVALID_REQUEST')
        assert adapter.interpret_calls==0


@pytest.mark.parametrize('result',[
    {'status':'matched','candidateDestinationIds':['demo-destination-001','demo-destination-002'],'reasonCode':None},
    {'status':'needs_confirmation','candidateDestinationIds':[],'reasonCode':None},
    {'status':'matched','candidateDestinationIds':[True],'reasonCode':None},
    {'status':'matched','candidateDestinationIds':['demo-destination-001'],'reasonCode':None,'coordinates':{'latitude':1}},
    {'status':'matched','candidateDestinationIds':['demo-destination-001'],'reasonCode':None,'routeId':'invented'},
])
def test_ambiguous_or_fact_adding_interpretations_do_not_get_adopted(make_app,result):
    class Adapter(ValidAdapter):
        def interpret_destination(self,payload):
            return copy.deepcopy(result)
    app,client,clock,_=make_app(adapter=Adapter())
    response=client.post('/api/v1/destination-interpretations',json={'originStationId':'demo-stop-001','text':'병원'})
    assert response.status_code==200
    assert response.json()['data']=={'status':'unavailable','candidates':[],'reasonCode':'AI_UNAVAILABLE'}


def test_confirmation_candidates_use_registered_facts_and_server_reason(make_app):
    class Adapter(ValidAdapter):
        def interpret_destination(self,payload):
            payload['allowedDestinations'][0]['name']='AI가 바꾼 이름'
            return {'status':'needs_confirmation','candidateDestinationIds':['demo-destination-001','demo-destination-002'],
                    'reasonCode':'<script>untrusted</script>'}
    app,client,clock,_=make_app(adapter=Adapter())
    response=client.post('/api/v1/destination-interpretations',json={'originStationId':'demo-stop-001','text':'큰 곳'})
    data=response.json()['data']
    assert data['status']=='needs_confirmation'
    assert [p['name'] for p in data['candidates']]==['시연 병원','시연 시장']
    assert data['reasonCode']=='USER_CONFIRMATION_REQUIRED'
    assert '<script>' not in response.text and 'AI가 바꾼 이름' not in response.text


def test_ai_receives_only_registered_choices_and_segment_template_choices(make_app):
    adapter=ValidAdapter()
    app,client,clock,_=make_app(adapter=adapter)
    response=client.post('/api/v1/destination-interpretations',json={'originStationId':'demo-stop-001','text':'병원'})
    assert response.status_code==200
    payload=adapter.interpret_payload
    assert set(payload)=={'text','dataMode','allowedDestinations'}
    assert payload['dataMode']=='demo'
    assert [p['destinationId'] for p in payload['allowedDestinations']]==[
        'demo-destination-001','demo-destination-002','demo-destination-003']
    assert all(set(p)=={'destinationId','name','aliases'} for p in payload['allowedDestinations'])
    body,path=selection(client,clock,'003')
    detail=client.get(path).json()['data']
    response=client.post('/api/v1/easy-guidance',json=body)
    assert response.json()['data']['mode']=='ai_assisted'
    payload=adapter.guidance_payload
    assert set(payload)=={'routeSnapshotVersion','dataMode','verifiedSegments'}
    assert payload['routeSnapshotVersion']==body['expectedRouteSnapshotVersion']
    assert [p['segmentId'] for p in payload['verifiedSegments']]==[p['segmentId'] for p in detail['segments']]
    for actual,segment in zip(payload['verifiedSegments'],detail['segments']):
        assert set(actual)=={'segmentId','type','allowedTemplateIds'}
        assert actual['allowedTemplateIds']==[segment['type']+'.basic']


@pytest.mark.parametrize('endpoint,extra',[
    ('destination-interpretations',{'candidateDestinationIds':['invented']}),
    ('easy-guidance',{'segments':[{'type':'bus','routeId':'invented'}]}),
    ('print-guides',{'etaSeconds':0}),
])
def test_public_ai_and_print_requests_do_not_accept_client_transport_facts(make_app,endpoint,extra):
    adapter=ValidAdapter()
    app,client,clock,_=make_app(adapter=adapter)
    body,path=selection(client,clock)
    if endpoint=='destination-interpretations':
        body={'originStationId':'demo-stop-001','text':'병원'}
    assert_error(client.post('/api/v1/'+endpoint,json={**body,**extra}),400,'INVALID_REQUEST')
    assert adapter.interpret_calls==adapter.guidance_calls==0


@pytest.mark.parametrize('fault',['top-fact','step-text','other-type-template','unavailable-status','steps-not-array'])
def test_guidance_rejects_extra_facts_and_type_valid_but_wrong_choices(make_app,fault):
    class Adapter(ValidAdapter):
        def choose_guidance(self,payload):
            result=valid_choices(payload)
            if fault=='top-fact': result['expectedArrivalAt']='2099-01-01T00:00:00Z'
            elif fault=='step-text': result['steps'][0]['text']='999번을 지금 타세요'
            elif fault=='other-type-template': result['steps'][0]['templateId']='walk.basic'
            elif fault=='unavailable-status': result['status']='unavailable'
            elif fault=='steps-not-array': result['steps']={'segmentId':'invented'}
            return result
    app,client,clock,_=make_app(adapter=Adapter())
    body,path=selection(client,clock,'003')
    detail=client.get(path).json()['data']
    response=client.post('/api/v1/easy-guidance',json=body)
    assert response.status_code==200
    data=response.json()['data']
    assert data['mode']=='template_fallback'
    assert [p['segmentId'] for p in data['steps']]==[p['segmentId'] for p in detail['segments']]
    assert '999번' not in response.text and '2099-' not in response.text
    assert '시연 1번' in data['steps'][0]['text'] and '2개 정류장' in data['steps'][0]['text']


@pytest.mark.parametrize('endpoint',['destination-interpretations','easy-guidance'])
@pytest.mark.parametrize('elapsed,accepted',[(1.0,True),(1.000001,False)])
def test_exact_one_second_adoption_boundary_includes_output_validation(make_app,monkeypatch,endpoint,elapsed,accepted):
    from backend.services import ai as service
    ticks=[0.0]
    class Adapter(ValidAdapter):
        def interpret_destination(self,payload):
            result=super().interpret_destination(payload)
            ticks[0]=elapsed
            return result
        def choose_guidance(self,payload):
            result=super().choose_guidance(payload)
            ticks[0]=elapsed
            return result
    monkeypatch.setattr(service,'monotonic',lambda:ticks[0])
    app,client,clock,_=make_app(adapter=Adapter())
    body,path=selection(client,clock)
    if endpoint=='destination-interpretations':
        body={'originStationId':'demo-stop-001','text':'병원'}
    response=client.post('/api/v1/'+endpoint,json=body)
    assert response.status_code==200
    data=response.json()['data']
    if endpoint=='destination-interpretations':
        assert data['status']==('matched' if accepted else 'unavailable')
    else:
        assert data['mode']==('ai_assisted' if accepted else 'template_fallback')


def test_worker_start_failure_falls_back_without_leaking_the_single_slot(monkeypatch):
    from backend.integrations import ai as integration
    class Adapter:
        def interpret_destination(self,payload): return {'completed':True}
    class BrokenThread:
        def __init__(self,*args,**kwargs): pass
        def start(self): raise RuntimeError('test thread admission failure')
    async def exercise():
        boundary=AIBoundary(Adapter(),budget=0.1)
        with monkeypatch.context() as context:
            context.setattr(integration,'Thread',BrokenThread)
            assert await boundary.call('interpret_destination',{'text':'병원'}) is None
        assert await boundary.call('interpret_destination',{'text':'병원'})=={'completed':True}
    asyncio.run(exercise())


def test_timeout_keeps_work_running_and_slot_shared_across_methods_until_completion():
    entered,release,completed=Event(),Event(),Event()
    class Adapter:
        interpret_calls=0
        guidance_calls=0
        def interpret_destination(self,payload):
            self.interpret_calls+=1
            entered.set()
            release.wait(3)
            completed.set()
            return {'which':'late-interpretation'}
        def choose_guidance(self,payload):
            self.guidance_calls+=1
            return {'which':'new-guidance'}
    async def exercise():
        adapter=Adapter()
        boundary=AIBoundary(adapter,budget=0.05)
        assert await boundary.call('interpret_destination',{}) is None
        assert entered.is_set() and not completed.is_set() and not release.is_set()
        for _ in range(3):
            assert await boundary.call('choose_guidance',{}) is None
        assert adapter.interpret_calls==1 and adapter.guidance_calls==0
        release.set()
        assert await asyncio.to_thread(completed.wait,1)
        for _ in range(20):
            result=await boundary.call('choose_guidance',{})
            if result is not None:
                assert result=={'which':'new-guidance'}
                assert adapter.guidance_calls==1
                return
            await asyncio.sleep(0.01)
        pytest.fail('The shared AI slot did not recover')
    try:
        asyncio.run(exercise())
    finally:
        release.set()


@pytest.mark.parametrize('mutation,status,code',[
    ('expiry',410,'ROUTE_SEARCH_EXPIRED'),('route-name',409,'ROUTE_VERSION_CHANGED'),
    ('cancellation',409,'ROUTE_UNAVAILABLE'),('core-unavailable',503,'TRANSPORT_DATA_UNAVAILABLE'),
])
def test_ai_success_cannot_bypass_post_call_path_revalidation(make_app,mutation,status,code):
    context={}
    class Adapter(ValidAdapter):
        def choose_guidance(self,payload):
            app,clock,provider=context['app'],context['clock'],context['provider']
            if mutation=='expiry': clock.now+=timedelta(seconds=600)
            elif mutation=='route-name':
                with app.state.database.session() as session:
                    session.get(Route,'demo-route-001').name='합성 경로 변경'
            elif mutation=='cancellation': provider.scenario='cancellation'
            elif mutation=='core-unavailable': provider.scenario='core_unavailable'
            return super().choose_guidance(payload)
    adapter=Adapter()
    app,client,clock,provider=make_app(adapter=adapter)
    context.update(app=app,clock=clock,provider=provider)
    body,path=selection(client,clock)
    assert_error(client.post('/api/v1/easy-guidance',json=body),status,code)
    assert adapter.guidance_calls==1


def test_print_uses_one_provider_observation_and_fixed_server_guidance(make_app):
    adapter=ValidAdapter()
    app,client,clock,provider=make_app(adapter=adapter)
    body,path=selection(client,clock,'003')
    original_time=clock.now
    state=provider.read(clock.now)
    class SingleRead:
        calls=0
        def read(self,now):
            self.calls+=1
            return state if self.calls==1 else replace(state,core_available=False)
    reader=SingleRead()
    app.state.provider=reader
    clock.now+=timedelta(seconds=30)
    response=client.post('/api/v1/print-guides',json=body)
    assert response.status_code==200,response.text
    result=s.Envelope[s.PrintData].model_validate(response.json()).data
    assert reader.calls==1
    assert adapter.interpret_calls==adapter.guidance_calls==0
    assert result.routeDetail.routeSnapshotVersion==result.liveInfoSnapshot.routeSnapshotVersion==result.guidance.routeSnapshotVersion==body['expectedRouteSnapshotVersion']
    assert result.routeDetail.journeyStatus=='ready'
    assert result.routeDetail.computedAt==original_time and result.generatedAt==clock.now
    assert [p.segmentId for p in result.routeDetail.segments]==[p.segmentId for p in result.guidance.steps]
    assert result.guidance.mode=='template_fallback'
    assert all(p.etaSeconds is None and p.dataQuality.fetchedAt==original_time for p in result.liveInfoSnapshot.arrivals)
    assert s.NOTICE in result.notice and s.NOTICE in result.guidance.steps[0].text
    assert not {'printSuccess','printerStatus','printedAt'}.intersection(response.json()['data'])


@pytest.mark.parametrize('guard,status,code',[
    ('expired',410,'ROUTE_SEARCH_EXPIRED'),('expected-version',409,'ROUTE_VERSION_CHANGED'),
    ('not-running',409,'ROUTE_UNAVAILABLE'),('core',503,'TRANSPORT_DATA_UNAVAILABLE'),
])
def test_print_and_guidance_guards_run_before_any_ai_work(make_app,guard,status,code):
    adapter=ValidAdapter()
    app,client,clock,provider=make_app(adapter=adapter)
    body,path=selection(client,clock)
    if guard=='expired': clock.now+=timedelta(seconds=600)
    elif guard=='expected-version': body['expectedRouteSnapshotVersion']='old-version'
    elif guard=='not-running': provider.scenario='operation_not_running'
    elif guard=='core': provider.scenario='core_unavailable'
    for endpoint in ('easy-guidance','print-guides'):
        assert_error(client.post('/api/v1/'+endpoint,json=body),status,code)
    assert adapter.interpret_calls==adapter.guidance_calls==0


def test_unknown_origin_is_rejected_before_ai_work(make_app):
    adapter=ValidAdapter()
    app,client,clock,_=make_app(adapter=adapter)
    response=client.post('/api/v1/destination-interpretations',json={'originStationId':'missing','text':'병원'})
    assert_error(response,404,'NOT_FOUND')
    assert adapter.interpret_calls==0


def test_interpretation_does_not_publish_destination_name_from_before_ai_wait(make_app):
    context={}
    class Adapter(ValidAdapter):
        def interpret_destination(self,payload):
            self.interpret_payload=copy.deepcopy(payload)
            with context['app'].state.database.session() as session:
                session.get(Destination,'demo-destination-001').name='합성 갱신 병원'
            return {'status':'matched','candidateDestinationIds':['demo-destination-001'],'reasonCode':None}
    adapter=Adapter()
    app,client,clock,_=make_app(adapter=adapter)
    context['app']=app
    response=client.post('/api/v1/destination-interpretations',json={'originStationId':'demo-stop-001','text':'병원'})
    assert response.status_code==200,response.text
    assert adapter.interpret_payload['allowedDestinations'][0]['name']=='시연 병원'
    data=response.json()['data']
    assert data['status']=='matched'
    assert data['candidates'][0]['name']=='합성 갱신 병원'


def test_destination_deleted_while_ai_waits_is_no_longer_an_allowed_candidate(make_app):
    context={}
    class Adapter(ValidAdapter):
        def interpret_destination(self,payload):
            assert any(p['destinationId']=='test-destination-unlinked' for p in payload['allowedDestinations'])
            with context['app'].state.database.session() as session:
                session.delete(session.get(Destination,'test-destination-unlinked'))
            return {'status':'matched','candidateDestinationIds':['test-destination-unlinked'],'reasonCode':None}
    app,client,clock,_=make_app(adapter=Adapter())
    context['app']=app
    with app.state.database.session() as session:
        session.add(Destination(destination_id='test-destination-unlinked',name='합성 독립 장소',category='other'))
    response=client.post('/api/v1/destination-interpretations',json={'originStationId':'demo-stop-001','text':'독립 장소'})
    assert response.status_code==200,response.text
    assert response.json()['data']=={'status':'unavailable','candidates':[],'reasonCode':'AI_UNAVAILABLE'}


@pytest.mark.parametrize('distance,duration,expected_time', [
    (100, None, '확인되지 않았습니다.'),
    (100, 59, '59초입니다.'),
    (None, 60, '약 1분입니다.'),
    (100, 90, '약 2분입니다.'),
    (100, 181, '약 4분입니다.'),
    (100, 420, '약 7분입니다.'),
])
def test_fixed_guidance_preserves_each_confirmed_walk_fact(env,distance,duration,expected_time):
    app,client,clock,_=env
    with app.state.database.session() as session:
        access=session.get(DestinationAccess,('demo-destination-001','demo-stop-003'))
        access.distance_meters=distance
        access.duration_seconds=duration
    body,path=selection(client,clock)
    guidance=client.post('/api/v1/easy-guidance',json=body)
    printed=client.post('/api/v1/print-guides',json=body)
    assert guidance.status_code==printed.status_code==200
    printed_data=s.Envelope[s.PrintData].model_validate(printed.json()).data
    assert printed_data.routeDetail.segments[-1].distanceMeters==distance
    assert printed_data.routeDetail.segments[-1].durationSeconds==duration
    for text in (guidance.json()['data']['steps'][-1]['text'],printed_data.guidance.steps[-1].text):
        assert f'이동 시간은 {expected_time}' in text
        if distance is not None:
            assert f'거리는 {distance}미터입니다.' in text
        else:
            assert '거리는 확인되지 않았습니다.' in text


@pytest.mark.parametrize('endpoint',['destination-interpretations','easy-guidance'])
def test_unsupported_async_adapter_falls_back_without_running_or_leaking_coroutine(make_app,endpoint):
    class Adapter:
        body_started=False
        async def interpret_destination(self,payload):
            self.body_started=True
            return {'status':'matched','candidateDestinationIds':['demo-destination-001'],'reasonCode':None}
        async def choose_guidance(self,payload):
            self.body_started=True
            return valid_choices(payload)
    adapter=Adapter()
    app,client,clock,_=make_app(adapter=adapter)
    body,path=selection(client,clock)
    if endpoint=='destination-interpretations':
        body={'originStationId':'demo-stop-001','text':'병원'}
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter('always')
        response=client.post('/api/v1/'+endpoint,json=body)
    assert response.status_code==200
    data=response.json()['data']
    if endpoint=='destination-interpretations': assert data['status']=='unavailable'
    else: assert data['mode']=='template_fallback'
    assert adapter.body_started is False
    assert not any(issubclass(item.category,RuntimeWarning) and 'coroutine' in str(item.message) for item in emitted)


def test_boundary_copies_input_and_output_instead_of_sharing_adapter_objects():
    class Adapter:
        reply={'choices':{'ids':['registered-id']}}
        def interpret_destination(self,payload):
            payload['choices']['ids'].append('adapter-mutation')
            return self.reply
    async def exercise():
        adapter=Adapter()
        boundary=AIBoundary(adapter)
        payload={'choices':{'ids':['registered-id']}}
        result=await boundary.call('interpret_destination',payload)
        assert payload=={'choices':{'ids':['registered-id']}}
        adapter.reply['choices']['ids'].append('late-mutation')
        assert result=={'choices':{'ids':['registered-id']}}
    asyncio.run(exercise())


@pytest.mark.parametrize('invalid',[{'value':float('nan')},{'value':{1,2}}])
def test_boundary_rejects_non_json_output_as_ai_failure(invalid):
    class Adapter:
        def interpret_destination(self,payload): return invalid
    async def exercise():
        assert await AIBoundary(Adapter()).call('interpret_destination',{}) is None
    asyncio.run(exercise())
