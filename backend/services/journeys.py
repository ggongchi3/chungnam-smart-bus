from datetime import datetime, timedelta, timezone
from uuid import uuid4
from math import isclose, isfinite

from pydantic import ValidationError
from sqlalchemy import select

from backend.api.errors import ServiceError, changed, not_found, route_unavailable, unavailable
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


def confirmed_duration(segments):
    values = [p.durationSeconds for p in segments if p.type in ('bus', 'walk')]
    return sum(values) if values and all(value is not None for value in values) else None


def validated_expiry(search):
    times = (search.created_at, search.expires_at)
    if (any(type(value) not in (int, float) or not isfinite(value) for value in times)
            or search.data_mode not in ('demo', 'live', 'static')):
        unavailable()
    expiry = search.created_at + 600
    if search.expires_at <= search.created_at or not isclose(search.expires_at, expiry, rel_tol=0, abs_tol=1e-6):
        unavailable()
    return expiry


def create_search(session, request, state, now, data_mode, *, transport=None):
    require_core(state)
    if transport is not None and request.originStationId != transport.origin['stationId']:
        # Historical demo rows may remain in an existing SQLite file. They must
        # never fall through to synthetic routing under the real static mode.
        raise ServiceError(400, 'INVALID_REQUEST', '기준 정류장 종합터미널을 출발지로 선택해 주세요.')
    catalog.station(session, request.originStationId)
    destination = catalog.destination(session, request.destinationId)
    if transport is not None and request.originStationId == transport.origin['stationId']:
        return transport.search(session, request, destination, now, data_mode)
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
            totalDurationSeconds=confirmed_duration(segments),
            walkingDurationSeconds=confirmed_duration([p for p in segments if p.type == 'walk'])))
        if len(options) == 3:
            break
    session.add(RouteSearch(search_id=search_id, origin_station_id=request.originStationId,
        destination_id=request.destinationId, created_at=now.timestamp(), expires_at=expires.timestamp(),
        data_mode=data_mode, snapshot=saved))
    return s.SearchData(routeSearchId=search_id, originStationId=request.originStationId,
                       destinationId=request.destinationId, expiresAt=expires, routeOptions=options)


def checked_search(session, search_id, now):
    search = session.get(RouteSearch, search_id)
    if search is None:
        not_found()
    if now.timestamp() >= validated_expiry(search):
        raise ServiceError(410, 'ROUTE_SEARCH_EXPIRED', '검색 유효기간이 지났습니다. 다시 검색해 주세요.')
    if not isinstance(search.snapshot, dict):
        unavailable()
    return search


def checked_detail(session, search_id, option_id, state, now, data_mode, expected=None, *, transport=None):
    search = checked_search(session, search_id, now)
    if option_id not in search.snapshot:
        not_found()
    require_core(state)
    if search.data_mode != data_mode:
        changed()
    if transport is not None and search.origin_station_id == transport.origin['stationId']:
        return transport.checked_detail(search, option_id, now, expected)
    try:
        saved = SavedRouteOption.model_validate(search.snapshot[option_id])
    except (ValidationError, TypeError, ValueError):
        unavailable()
    detail = saved.detail
    if (detail.routeSearchId != search_id or detail.routeOptionId != option_id or
            detail.originStationId != search.origin_station_id or detail.destinationId != search.destination_id or
            detail.computedAt.timestamp() != search.created_at or
            detail.referenceDataQuality != quality(None, detail.computedAt, detail.computedAt) or
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
    if status == 'unavailable':
        route_unavailable()
    if status != 'ready':
        changed('선택 경로의 재확인이 필요합니다. 다시 검색해 주세요.')
    if version != detail.routeSnapshotVersion or (expected is not None and expected != version):
        changed()
    if segments != detail.segments:
        # A real reference-data change already returns 409 above. With the same
        # version, differing stored facts are an invalid snapshot, not new facts.
        unavailable()
    return detail


def arrival_values(detail, state, now, for_print=False):
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
    return arrivals


def live_info(detail, state, now, for_print=False, *, session=None):
    arrivals = arrival_values(detail, state, now, for_print=for_print)
    routes = {p.routeId for p in detail.segments if p.type == 'bus'}
    legs = [(p.routeId, p.boardSequence, p.alightSequence) for p in detail.segments if p.type == 'bus']
    stations = (routing.route_station_ids(session, legs) if session is not None else
        {ref.stationId for p in detail.segments if p.type == 'bus' for ref in (p.boardStation, p.alightStation)})
    changes = routing.scoped_changes(state, now, routes, stations)
    return s.LiveData(routeSnapshotVersion=detail.routeSnapshotVersion, arrivals=arrivals, serviceChanges=changes)


def print_notice(snapshot, data_mode):
    parts = [s.NOTICE] if data_mode == 'demo' else []
    parts.append('생성 시각과 교통정보 원천 갱신 시각을 구분해 주세요.')
    if any(a.arrivalStatus == 'unavailable' for a in snapshot.arrivals):
        parts.append('도착 예정 정보를 확인할 수 없습니다.')
    if any(a.dataQuality.freshness == 'stale' for a in snapshot.arrivals):
        parts.append('도착 정보가 오래되었습니다.')
    if any(a.dataQuality.freshness == 'unknown' for a in snapshot.arrivals):
        parts.append('도착 정보 원천 시각을 확인할 수 없습니다.')
    changes = snapshot.serviceChanges
    if changes.coverageStatus == 'unknown':
        parts.append('운행 변경 정보를 확인할 수 없습니다.')
    elif changes.dataQuality.freshness == 'stale' or any(c.dataQuality.freshness == 'stale' for c in changes.items):
        parts.append('운행 변경 정보가 오래되었습니다.')
    elif changes.dataQuality.freshness == 'unknown' or any(c.dataQuality.freshness == 'unknown' for c in changes.items):
        parts.append('운행 변경 정보 원천 시각을 확인할 수 없습니다.')
    return ' · '.join(parts)


def print_guide(detail, state, now, *, session=None, data_mode='demo'):
    snapshot = live_info(detail, state, now, for_print=True, session=session)
    return s.PrintData(printGuideId='demo-print-' + uuid4().hex, generatedAt=now, routeDetail=detail.model_copy(deep=True),
        liveInfoSnapshot=snapshot, guidance=fixed_guidance(detail, data_mode), notice=print_notice(snapshot, data_mode))
