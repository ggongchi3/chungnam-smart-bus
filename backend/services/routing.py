"""Directed route occurrences, explicit transfer edges, at most two bus legs."""
import hashlib
import json

from sqlalchemy import select

from backend.models import schemas as s
from backend.models.tables import DestinationAccess, Route, RouteStop, Station, TransferConnection


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:24]


def build_candidates(session, origin, destination_id):
    stops = session.scalars(select(RouteStop).order_by(RouteStop.route_id, RouteStop.sequence)).all()
    transfers = session.scalars(select(TransferConnection)).all()
    accesses = session.scalars(select(DestinationAccess).where(DestinationAccess.destination_id == destination_id)).all()
    candidates = {}
    for access in accesses:
        for board in [p for p in stops if p.station_id == origin]:
            for alight in [p for p in stops if p.station_id == access.station_id]:
                if board.route_id == alight.route_id and board.sequence < alight.sequence:
                    legs = [(board.route_id, board.sequence, alight.sequence)]
                    candidates[(tuple(legs), access.station_id)] = (legs, access)
                for transfer in transfers:
                    if (board.route_id != transfer.from_route_id or alight.route_id != transfer.to_route_id or
                            board.route_id == alight.route_id or board.sequence >= transfer.from_sequence or
                            transfer.to_sequence >= alight.sequence):
                        continue
                    from_stop = session.get(RouteStop, (transfer.from_route_id, transfer.from_sequence))
                    to_stop = session.get(RouteStop, (transfer.to_route_id, transfer.to_sequence))
                    # Initial transfer model only approves the same station occurrence.
                    # Different station transfers require an explicit walking link, absent here.
                    if from_stop.station_id != to_stop.station_id:
                        continue
                    legs = [(board.route_id, board.sequence, transfer.from_sequence),
                            (alight.route_id, transfer.to_sequence, alight.sequence)]
                    candidates[(tuple(legs), access.station_id)] = (legs, access)
    def count(legs):
        return sum(sum(a < p.sequence <= b for p in stops if p.route_id == route) for route, a, b in legs)
    # Availability is checked by the search service before taking the public
    # top three. Detail checks also need every path, regardless of current rank.
    return sorted(candidates.values(), key=lambda item: (len(item[0]) - 1, count(item[0]), tuple(item[0]), item[1].station_id))


def station_ref(session, station_id):
    station = session.get(Station, station_id)
    return s.StationRef(stationId=station.station_id, name=station.name)


def segments_for(session, legs, access, destination_name):
    result = []
    for i, (route_id, board, alight) in enumerate(legs):
        route = session.get(Route, route_id)
        board_stop, alight_stop = (session.get(RouteStop, (route_id, seq)) for seq in (board, alight))
        bus_id = f'demo-leg-bus-{i + 1:03}'
        if i:
            result.append(s.Transfer(segmentId=f'demo-leg-transfer-{i:03}', fromSegmentId=result[-1].segmentId,
                toSegmentId=bus_id, atStation=station_ref(session, board_stop.station_id)))
        stop_count = len(session.scalars(select(RouteStop).where(RouteStop.route_id == route_id,
                                      RouteStop.sequence > board, RouteStop.sequence <= alight)).all())
        result.append(s.Bus(segmentId=bus_id, routeId=route_id, routeName=route.name,
            boardStation=station_ref(session, board_stop.station_id),
            alightStation=station_ref(session, alight_stop.station_id),
            boardSequence=board, alightSequence=alight, stopCount=stop_count, durationSeconds=None))
    result.append(s.Walk(segmentId='demo-leg-walk-001', fromLabel=session.get(Station, access.station_id).name,
                         toLabel=destination_name, distanceMeters=access.distance_meters, durationSeconds=access.duration_seconds))
    return result


def route_state(session, legs, access, destination_name, state, now):
    segments = segments_for(session, legs, access, destination_name)
    route_ids = {leg[0] for leg in legs}
    station_ids = {p.station_id for p in session.scalars(select(RouteStop).where(RouteStop.route_id.in_(route_ids))).all()}
    changes = [c for c in state.changes.items
               if (route_ids.intersection(c.affectedRouteIds) or station_ids.intersection(c.affectedStationIds))
               and (c.validFrom is None or c.validFrom <= now) and (c.validUntil is None or now < c.validUntil)]
    status = 'ready'
    if any(c.type in ('cancellation', 'detour') and c.dataQuality.freshness == 'fresh' for c in changes):
        status = 'unavailable'
    elif changes:
        status = 'recheck_required'
    structure = [[p.route_id, p.sequence, p.station_id] for p in session.scalars(
        select(RouteStop).where(RouteStop.route_id.in_(route_ids)).order_by(RouteStop.route_id, RouteStop.sequence))]
    links = [[t.from_route_id, t.from_sequence, t.to_route_id, t.to_sequence, t.evidence]
             for t in session.scalars(select(TransferConnection)).all()
             if len(legs) == 2 and (t.from_route_id, t.from_sequence, t.to_route_id, t.to_sequence) ==
                 (legs[0][0], legs[0][2], legs[1][0], legs[1][1])]
    version = 'demo-v-' + digest({'segments': [p.model_dump(mode='json') for p in segments],
        'structure': structure, 'links': links,
        'changes': [c.model_dump(mode='json', exclude={'dataQuality'}) for c in changes], 'status': status})
    return segments, version, status
