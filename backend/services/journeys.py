from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select

from backend.api.errors import ServiceError, changed, not_found, unavailable
from backend.models import schemas as s
from backend.models.tables import DestinationAccess, RouteSearch
from backend.services import catalog, routing
from backend.services.ai import fixed_guidance
from backend.services.time import quality


def require_core(state):
    if not state.core_available:
        unavailable()


def create_search(session, request, state, now, data_mode):
    require_core(state)
    catalog.station(session, request.originStationId)
    destination = catalog.destination(session, request.destinationId)
    if abs((request.departAt.astimezone(timezone.utc) - now.astimezone(timezone.utc)).total_seconds()) > 120:
        raise ServiceError(400, 'INVALID_REQUEST', '현재 시각에서 120초 이내의 출발 시각을 입력해 주세요.')
    search_id = 'demo-search-' + uuid4().hex
    expires = now + timedelta(seconds=600)
    options, saved = [], {}
    for legs, access in routing.build_candidates(session, request.originStationId, request.destinationId):
        segments, version, status = routing.route_state(session, legs, access, destination.name, state, now)
        if status != 'ready':
            continue
        key = routing.digest([legs, access.station_id])
        option_id = 'demo-option-' + key
        detail = s.RouteDetail(routeSearchId=search_id, routeOptionId=option_id, routeSnapshotVersion=version,
            originStationId=request.originStationId, destinationId=request.destinationId, computedAt=now,
            journeyStatus=status, referenceDataQuality=quality(None, now, now), segments=segments)
        saved[option_id] = {'detail': detail.model_dump(mode='json'), 'legs': legs, 'accessStationId': access.station_id}
        options.append(s.RouteOption(routeOptionId=option_id, routeSnapshotVersion=version, journeyStatus=status,
            routeNames=[p.routeName for p in segments if p.type == 'bus'], transferCount=len(legs) - 1,
            totalDurationSeconds=None, walkingDurationSeconds=None))
    session.add(RouteSearch(search_id=search_id, origin_station_id=request.originStationId,
        destination_id=request.destinationId, created_at=now.timestamp(), expires_at=expires.timestamp(),
        data_mode=data_mode, snapshot=saved))
    return s.SearchData(routeSearchId=search_id, originStationId=request.originStationId,
                       destinationId=request.destinationId, expiresAt=expires, routeOptions=options)


def checked_detail(session, search_id, option_id, state, now, data_mode, expected=None):
    search = session.get(RouteSearch, search_id)
    if search is None:
        not_found()
    if now.timestamp() >= search.expires_at:
        raise ServiceError(410, 'ROUTE_SEARCH_EXPIRED', '검색 유효기간이 지났습니다. 다시 검색해 주세요.')
    saved = search.snapshot.get(option_id)
    if saved is None:
        not_found()
    require_core(state)
    if search.data_mode != data_mode:
        changed()
    try:
        detail = s.RouteDetail.model_validate(saved['detail'])
    except (ValidationError, KeyError, TypeError):
        unavailable()
    if (detail.routeSearchId != search_id or detail.routeOptionId != option_id or
            detail.originStationId != search.origin_station_id or detail.destinationId != search.destination_id):
        unavailable()
    legs = [tuple(p) for p in saved['legs']]
    candidates = routing.build_candidates(session, search.origin_station_id, search.destination_id)
    current = next((access for current_legs, access in candidates
                    if current_legs == legs and access.station_id == saved['accessStationId']), None)
    if current is None:
        changed('경유 순서 또는 연결이 바뀌었습니다. 다시 검색해 주세요.')
    destination = catalog.destination(session, search.destination_id)
    segments, version, status = routing.route_state(session, legs, current, destination.name, state, now)
    if status != 'ready':
        changed('선택 경로를 이용할 수 없거나 재확인이 필요합니다. 다시 검색해 주세요.')
    if version != detail.routeSnapshotVersion or (expected is not None and expected != version):
        changed()
    return detail


def live_info(detail, state, now, for_print=False):
    arrivals = []
    q = quality(state.source_updated_at, state.fetched_at, now)
    for segment in detail.segments:
        if segment.type != 'bus':
            continue
        # Fixed synthetic event, not a new 5-minute arrival on every poll.
        expected = state.fetched_at + timedelta(seconds=300) if state.arrivals_available and state.fetched_at else None
        available = expected is not None and now <= expected
        arrivals.append(s.Arrival(segmentId=segment.segmentId, routeId=segment.routeId,
            boardStationId=segment.boardStation.stationId, arrivalStatus='available' if available else 'unavailable',
            etaSeconds=max(0, int((expected - now).total_seconds())) if available and not for_print else None,
            expectedArrivalAt=expected if available else None, operationStatus='unknown', dataQuality=q))
    routes = {p.routeId for p in detail.segments if p.type == 'bus'}
    stations = {ref.stationId for p in detail.segments if p.type == 'bus' for ref in (p.boardStation, p.alightStation)}
    changes = state.changes.model_copy(update={'items': [c for c in state.changes.items
        if routes.intersection(c.affectedRouteIds) or stations.intersection(c.affectedStationIds)]}, deep=True)
    return s.LiveData(routeSnapshotVersion=detail.routeSnapshotVersion, arrivals=arrivals, serviceChanges=changes)


def print_guide(detail, state, now):
    snapshot = live_info(detail, state, now, for_print=True)
    return s.PrintData(printGuideId='demo-print-' + uuid4().hex, generatedAt=now, routeDetail=detail.model_copy(deep=True),
        liveInfoSnapshot=snapshot, guidance=fixed_guidance(detail), notice=s.NOTICE +
        ' · 생성 시각과 원천 갱신 시각을 구분해 주세요. 도착·운행 변경 정보는 확인 불가하거나 오래될 수 있습니다.')
