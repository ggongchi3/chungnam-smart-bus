"""Optional public municipal arrival lookup. Missing source time stays unknown."""
import asyncio
from datetime import timedelta
from math import isfinite
import httpx

from backend.integrations.providers import ArrivalObservation, ProviderState
from backend.models.schemas import ServiceChanges
from backend.services.time import quality

URL = 'https://its.cheonan.go.kr/bis/getArrivalScheduleList.do'


async def arrival_state(detail, now, *, client=None):
    observations = {}
    buses = [p for p in detail.segments if p.type == 'bus']
    async def collect_station(http, station):
        try:
            # A slow transfer-stop response must not consume another complete
            # request timeout after the first boarding-stop response.
            async with asyncio.timeout(3):
                response = await http.get(URL, params={'stopId': station.removeprefix('cheonan-stop-')})
                response.raise_for_status()
                rows = response.json()['resultList']
            if not isinstance(rows, list):
                return
            by_route = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                minutes = row.get('RTIME')
                if type(minutes) not in (int, float) or not isfinite(minutes) or not 0 <= minutes <= 180:
                    continue
                route_id = str(row.get('ROUTE_ID'))
                by_route[route_id] = min(minutes, by_route.get(route_id, minutes))
            for bus in (p for p in buses if p.boardStation.stationId == station):
                minutes = by_route.get(bus.routeId.removeprefix('cheonan-route-'))
                if minutes is not None:
                    # This is an observation at lookup time, never a promise
                    # that a later transfer connection can be caught.
                    observations[(bus.routeId, station)] = ArrivalObservation(now + timedelta(minutes=minutes),
                        operation_status='unknown', source_updated_at=None, fetched_at=now, source_id='cheonan-bis-arrival')
        except (httpx.HTTPError, ValueError, KeyError, TypeError, TimeoutError):
            return

    async def collect(http):
        await asyncio.gather(*(collect_station(http, station)
            for station in sorted({p.boardStation.stationId for p in buses})))
    if client is not None:
        await collect(client)
    else:
        async with httpx.AsyncClient(timeout=2, headers={'User-Agent': 'CheonanSmartBus/0.1 arrival-query'}) as http:
            await collect(http)
    return ProviderState(True, bool(observations), None, now,
        ServiceChanges(coverageStatus='unknown', items=[], dataQuality=quality(None, now, now, 'cheonan-bis-arrival')), observations)
