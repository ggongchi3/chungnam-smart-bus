"""Audit regressions using backend-only fakes and isolated in-memory DBs."""
import asyncio
from dataclasses import replace
from datetime import timedelta
from threading import Event

import pytest

from backend.integrations.ai import AIBoundary
from backend.models import schemas as s
from backend.services.time import quality
from backend.tests.conftest import selection


def changed_item(clock):
    return s.Change(changeId='audit-change',type='other',affectedRouteIds=['demo-route-001'],
        affectedStationIds=[],title='합성 감사 알림',description='백엔드 내부 테스트',
        validFrom=clock.now+timedelta(seconds=60),validUntil=None,
        dataQuality=quality(clock.now,clock.now,clock.now,'audit-source'))


def malformed_changes(state,clock,fault):
    if fault=='coverage-enum':
        return state.changes.model_copy(update={'coverageStatus':'bogus'})
    if fault=='feed-quality-enum':
        bad_quality=state.changes.dataQuality.model_copy(update={'freshness':'bogus'})
        return state.changes.model_copy(update={'dataQuality':bad_quality})
    item=changed_item(clock)
    if fault=='change-type-enum': item=item.model_copy(update={'type':'bogus'})
    elif fault=='start-string': item=item.model_copy(update={'validFrom':'not-a-time'})
    elif fault=='start-naive': item=item.model_copy(update={'validFrom':clock.now.replace(tzinfo=None)})
    elif fault=='item-quality-enum':
        item=item.model_copy(update={'dataQuality':item.dataQuality.model_copy(update={'freshness':'bogus'})})
    return state.changes.model_copy(update={'items':[item]})


@pytest.mark.parametrize('fault',[
    'coverage-enum','feed-quality-enum','change-type-enum','start-string','start-naive','item-quality-enum',
])
def test_malformed_provider_models_are_isolated_as_unknown_change_feed(env,fault):
    app,client,clock,provider=env
    body,path=selection(client,clock,'003')
    original=client.get(path).json()['data']
    base=provider.read(clock.now)
    bad=replace(base,changes=malformed_changes(base,clock,fault))
    provider.read=lambda now:bad
    response=client.get(path+'/live')
    assert response.status_code==200,response.text
    value=s.Envelope[s.LiveData].model_validate(response.json())
    assert value.error is None
    assert value.data.routeSnapshotVersion==body['expectedRouteSnapshotVersion']
    assert value.data.serviceChanges.coverageStatus=='unknown'
    assert value.data.serviceChanges.items==[]
    assert value.data.serviceChanges.dataQuality.model_dump()=={
        'sourceId':None,'sourceUpdatedAt':None,'fetchedAt':None,'freshness':'unknown'}
    assert len(value.data.arrivals)==2 and all(item.arrivalStatus=='available' for item in value.data.arrivals)
    assert client.get(path).json()['data']==original
    guide=client.post('/api/v1/easy-guidance',json=body)
    assert guide.status_code==200 and guide.json()['data']['routeSnapshotVersion']==body['expectedRouteSnapshotVersion']
    printed=client.post('/api/v1/print-guides',json=body)
    assert printed.status_code==200,printed.text
    snapshot=s.Envelope[s.PrintData].model_validate(printed.json()).data
    assert snapshot.routeDetail.journeyStatus=='ready'
    assert snapshot.liveInfoSnapshot.serviceChanges.coverageStatus=='unknown'
    assert snapshot.liveInfoSnapshot.serviceChanges.items==[]
    assert '운행 변경 정보를 확인할 수 없습니다' in snapshot.notice


def test_valid_provider_models_preserve_source_times_and_recalculate_feed_and_item_freshness(env):
    app,client,clock,provider=env
    body,path=selection(client,clock)
    origin=clock.now
    base=provider.read(clock.now)
    item=changed_item(clock)
    item_source=origin-timedelta(seconds=85)
    item_fetched=origin-timedelta(seconds=3)
    item=item.model_copy(update={'dataQuality':quality(item_source,item_fetched,clock.now,'audit-item')})
    feed_source=origin-timedelta(seconds=2)
    feed_fetched=origin-timedelta(seconds=1)
    feed_quality=quality(feed_source,feed_fetched,clock.now,'audit-feed').model_copy(update={'freshness':'stale'})
    good=replace(base,changes=base.changes.model_copy(update={'items':[item],'dataQuality':feed_quality}))
    provider.read=lambda now:good
    clock.now+=timedelta(seconds=10)
    response=client.get(path+'/live')
    assert response.status_code==200,response.text
    changes=s.Envelope[s.LiveData].model_validate(response.json()).data.serviceChanges
    assert changes.coverageStatus=='available' and len(changes.items)==1
    assert changes.dataQuality.sourceId=='audit-feed'
    assert changes.dataQuality.sourceUpdatedAt==feed_source and changes.dataQuality.fetchedAt==feed_fetched
    assert changes.dataQuality.freshness=='fresh'
    recorded=changes.items[0]
    assert recorded.changeId=='audit-change' and recorded.type=='other'
    assert recorded.validFrom==origin+timedelta(seconds=60)
    assert recorded.dataQuality.sourceUpdatedAt==item_source and recorded.dataQuality.fetchedAt==item_fetched
    assert recorded.dataQuality.freshness=='stale'
    assert client.get(path).status_code==200


def test_cancelled_ai_request_keeps_worker_bound_until_done_then_recovers_on_new_loop():
    entered,release,completed=Event(),Event(),Event()
    class Adapter:
        calls=0
        def interpret_destination(self,payload):
            self.calls+=1
            if self.calls==1:
                entered.set()
                release.wait(3)
                completed.set()
            return {'call':self.calls}
    adapter=Adapter()
    boundary=AIBoundary(adapter,budget=0.2)
    async def cancel_request():
        task=asyncio.create_task(boundary.call('interpret_destination',{}))
        assert await asyncio.to_thread(entered.wait,1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not completed.is_set()
        assert await boundary.call('interpret_destination',{}) is None
        assert adapter.calls==1
    async def recover_in_new_loop():
        for _ in range(30):
            result=await boundary.call('interpret_destination',{})
            if result is not None:
                assert result=={'call':2}
                return
            await asyncio.sleep(0.01)
        pytest.fail('Cancelled worker slot did not recover')
    try:
        asyncio.run(cancel_request())
        release.set()
        assert completed.wait(1)
        asyncio.run(recover_in_new_loop())
    finally:
        release.set()
