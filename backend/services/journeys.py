from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select

from backend.api.errors import ServiceError, changed, not_found, unavailable
from backend.models import schemas as s
from backend.models.snapshots import SavedRouteOption
from backend.models.tables import DestinationAccess, RouteSearch
from backend.integrations.providers import ArrivalObservation
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
        saved[option_id] = SavedRouteOption(detail=detail, legs=legs, accessStationId=access.station_id).model_dump(mode='json')
        options.append(s.RouteOption(routeOptionId=option_id, routeSnapshotVersion=version, journeyStatus=status,
            routeNames=[p.routeName for p in segments if p.type == 'bus'], transferCount=len(legs) - 1,
            totalDurationSeconds=None, walkingDurationSeconds=None))
        if len(options) == 3:
            break
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
    if not isinstance(search.snapshot, dict):
        unavailable()
    if option_id not in search.snapshot:
        not_found()
    require_core(state)
    if search.data_mode != data_mode:
        changed()
    try:
        saved = SavedRouteOption.model_validate(search.snapshot[option_id])
    except (ValidationError, TypeError, ValueError):
        unavailable()
    detail = saved.detail
    if (detail.routeSearchId != search_id or detail.routeOptionId != option_id or
            detail.originStationId != search.origin_station_id or detail.destinationId != search.destination_id or
            detail.computedAt.timestamp() != search.created_at or
            option_id != 'demo-option-' + routing.digest([saved.legs, saved.accessStationId])):
        unavailable()
    legs = saved.legs
    candidates = routing.build_candidates(session, search.origin_station_id, search.destination_id)
    current = next((access for current_legs, access in candidates
                    if current_legs == legs and access.station_id == saved.accessStationId), None)
    if current is None:
        changed('경유 순서 또는 연결이 바뀌었습니다. 다시 검색해 주세요.')
    destination = catalog.destination(session, search.destination_id)
    segments, version, status = routing.route_state(session, legs, current, destination.name, state, now)
    if status != 'ready':
        changed('선택 경로를 이용할 수 없거나 재확인이 필요합니다. 다시 검색해 주세요.')
    if version != detail.routeSnapshotVersion or (expected is not None and expected != version):
        changed()
    if segments != detail.segments:
        # A real reference-data change already returns 409 above. With the same
        # version, differing stored facts are an invalid snapshot, not new facts.
        unavailable()
    return detail


def live_info(detail, state, now, for_print=False, *, session=None):
    arrivals = []
    for segment in detail.segments:
        if segment.type != 'bus':
            continue
        observation = state.arrivals.get((segment.routeId, segment.boardStation.stationId))
        if not isinstance(observation, ArrivalObservation):
            observation = ArrivalObservation(None)
        q = quality(observation.source_updated_at, observation.fetched_at, now, observation.source_id)
        # Facts come from the provider. Collection/response times never create ETA.
        expected = observation.expected_arrival_at if state.arrivals_available else None
        available = expected is not None and now <= expected
        arrivals.append(s.Arrival(segmentId=segment.segmentId, routeId=segment.routeId,
            boardStationId=segment.boardStation.stationId, arrivalStatus='available' if available else 'unavailable',
            etaSeconds=max(0, int((expected - now).total_seconds())) if available and not for_print else None,
            expectedArrivalAt=expected if available else None,
            operationStatus=observation.operation_status, dataQuality=q))
    routes = {p.routeId for p in detail.segments if p.type == 'bus'}
    legs = [(p.routeId, p.boardSequence, p.alightSequence) for p in detail.segments if p.type == 'bus']
    stations = (routing.route_station_ids(session, legs) if session is not None else
        {ref.stationId for p in detail.segments if p.type == 'bus' for ref in (p.boardStation, p.alightStation)})
    changes = routing.scoped_changes(state, now, routes, stations)
    return s.LiveData(routeSnapshotVersion=detail.routeSnapshotVersion, arrivals=arrivals, serviceChanges=changes)


def print_guide(detail, state, now, *, session=None):
    snapshot = live_info(detail, state, now, for_print=True, session=session)
    return s.PrintData(printGuideId='demo-print-' + uuid4().hex, generatedAt=now, routeDetail=detail.model_copy(deep=True),
        liveInfoSnapshot=snapshot, guidance=fixed_guidance(detail), notice=s.NOTICE +
        ' · 생성 시각과 원천 갱신 시각을 구분해 주세요. 도착·운행 변경 정보는 확인 불가하거나 오래될 수 있습니다.')
