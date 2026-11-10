"""Municipal responses can be partly malformed without hiding valid arrivals."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend.integrations.cheonan_live import arrival_state
from backend.models import schemas as s


def detail():
    now = datetime.now(timezone.utc)
    buses = [s.Bus(segmentId=f'bus-{i}', routeId=f'cheonan-route-{rid}', routeName=str(i),
        boardStation=s.StationRef(stationId=f'cheonan-stop-{sid}', name='승차 정류장'),
        alightStation=s.StationRef(stationId='cheonan-stop-end', name='하차 정류장'),
        boardSequence=1, alightSequence=2, stopCount=1, durationSeconds=None)
        for i, (rid, sid) in enumerate((('285000007', '285000686'), ('285000008', '285000687')), 1)]
    return now, s.RouteDetail(routeSearchId='search', routeOptionId='option', routeSnapshotVersion='v',
        originStationId='cheonan-stop-285000686', destinationId='destination', computedAt=now,
        journeyStatus='ready', referenceDataQuality=s.Quality(sourceId=None, sourceUpdatedAt=None,
            fetchedAt=None, freshness='unknown'), segments=buses)


@pytest.mark.anyio
async def test_one_bad_row_or_station_does_not_hide_other_valid_observations():
    now, selected = detail()
    def handler(request):
        if request.url.params['stopId'] == '285000687':
            return httpx.Response(503)
        return httpx.Response(200, json={'resultList': [None, 'bad row', {},
            {'ROUTE_ID': 285000007, 'RTIME': True}, {'ROUTE_ID': 285000007, 'RTIME': '1'},
            {'ROUTE_ID': 285000007, 'RTIME': -1}, {'ROUTE_ID': 285000007, 'RTIME': 181},
            {'ROUTE_ID': 285000007, 'RTIME': 7}, {'ROUTE_ID': 285000007, 'RTIME': 3},
            {'ROUTE_ID': 999, 'RTIME': 0}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await arrival_state(selected, now, client=client)
    assert len(state.arrivals) == 1
    observed = state.arrivals[('cheonan-route-285000007', 'cheonan-stop-285000686')]
    assert observed.expected_arrival_at == now + timedelta(minutes=3)
    assert observed.source_updated_at is None
    assert observed.operation_status == 'unknown'


@pytest.mark.anyio
@pytest.mark.parametrize('payload', [None, [], {}, {'resultList': None}, {'resultList': {}}, {'resultList': []}])
async def test_missing_or_invalid_payload_remains_unavailable(payload):
    now, selected = detail()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))) as client:
        state = await arrival_state(selected, now, client=client)
    assert not state.arrivals_available
    assert state.arrivals == {}
