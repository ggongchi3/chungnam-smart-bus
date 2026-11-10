"""Optional public municipal arrival lookup. Missing source time stays unknown."""
from datetime import timedelta
import httpx

from backend.integrations.providers import ArrivalObservation, ProviderState
from backend.models.schemas import ServiceChanges
from backend.services.time import quality

URL = 'https://its.cheonan.go.kr/bis/getArrivalScheduleList.do'


async def arrival_state(detail, now, *, client=None):
    observations = {}
    buses = [p for p in detail.segments if p.type == 'bus']
    async def collect(http):
        for station in sorted({p.boardStation.stationId for p in buses}):
            try:
                response = await http.get(URL, params={'stopId': station.removeprefix('cheonan-stop-')})
                response.raise_for_status()
                rows = response.json()['resultList']
                for bus in (p for p in buses if p.boardStation.stationId == station):
                    values = [row['RTIME'] for row in rows if str(row.get('ROUTE_ID')) == bus.routeId.removeprefix('cheonan-route-')
                              and type(row.get('RTIME')) in (int, float) and 0 <= row['RTIME'] <= 180]
                    if values:
                        # RTIME is the official response's minute estimate. Its
                        # source update timestamp is absent, never set to now.
                        observations[(bus.routeId, station)] = ArrivalObservation(now + timedelta(minutes=min(values)),
                            operation_status='unknown', source_updated_at=None, fetched_at=now, source_id='cheonan-bis-arrival')
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                continue
    if client is not None:
        await collect(client)
    else:
        async with httpx.AsyncClient(timeout=2, headers={'User-Agent': 'CheonanSmartBus/0.1 arrival-query'}) as http:
            await collect(http)
    return ProviderState(True, bool(observations), None, now,
        ServiceChanges(coverageStatus='unknown', items=[], dataQuality=quality(None, now, now, 'cheonan-bis-arrival')), observations)
