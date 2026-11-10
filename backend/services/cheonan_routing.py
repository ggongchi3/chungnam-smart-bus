"""Directed alternatives over published Cheonan BIS stop sequences.

Bus edges are never inferred from proximity. Transfers use the exact same BIS
stop ID; the only walking edges are imported pedestrian-network results.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
import json
from math import cos, radians
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from backend.api.errors import ServiceError, changed, not_found, unavailable
from backend.models import schemas as s
from backend.models.tables import RouteSearch, Station
from backend.services.geo import haversine_meters
from backend.services.routing import digest
from backend.services.time import quality

DATA = Path(__file__).resolve().parents[2] / 'shared/data'
NOTICE = ('공식 노선 구조 기준 · 현재 운행 여부와 대기·환승 대기시간은 확인되지 않았습니다. '
          '이동시간은 노선 전체 평균 운행시간의 거리 비율과 보행 경로로 추정하며 대기시간을 제외합니다. '
          '거리는 공식 노선 선형과 OSM 보행 경로 기준의 근삿값입니다.')
SORTS = ('fastest', 'transfers', 'walking', 'distance')


def total(values):
    return sum(values) if values and all(v is not None for v in values) else None


def positions(route, stations):
    """Monotone map matching retains repeated stops and directed loops."""
    geometry = route['geometry']
    if len(geometry) < 2:
        return None
    reference_lat = radians(geometry[0][0])
    points = [(radians(lon) * 6371008.8 * cos(reference_lat), radians(lat) * 6371008.8) for lat, lon in geometry]
    offsets = [0.0]
    for a, b in zip(geometry, geometry[1:]):
        offsets.append(offsets[-1] + haversine_meters({'latitude':a[0], 'longitude':a[1]}, {'latitude':b[0], 'longitude':b[1]}))
    previous, parents, candidates = None, [], []
    for sid in route['stops']:
        stop = stations[sid]
        px, py = radians(stop['longitude']) * 6371008.8 * cos(reference_lat), radians(stop['latitude']) * 6371008.8
        choices = []
        for index, ((ax, ay), (bx, by)) in enumerate(zip(points, points[1:])):
            dx, dy = bx - ax, by - ay
            fraction = min(1, max(0, ((px-ax)*dx + (py-ay)*dy) / (dx*dx+dy*dy))) if dx or dy else 0
            error = (px-ax-fraction*dx)**2 + (py-ay-fraction*dy)**2
            choices.append((offsets[index] + fraction * (offsets[index+1]-offsets[index]), error))
        current, links = [], []
        best, best_index, cursor = float('inf'), -1, 0
        for j, (along, error) in enumerate(choices):
            if previous is None:
                current.append(error)
                links.append(-1)
                continue
            while cursor < len(previous) and candidates[-1][cursor][0] <= along + .001:
                if previous[cursor] < best:
                    best, best_index = previous[cursor], cursor
                cursor += 1
            current.append(best + error)
            links.append(best_index)
        previous = current
        parents.append(links)
        candidates.append(choices)
    end = min(range(len(previous)), key=previous.__getitem__)
    matched = []
    for i in range(len(candidates)-1, -1, -1):
        if end < 0 or candidates[i][end][1] > 150**2:
            return None
        matched.append(candidates[i][end][0])
        end = parents[i][end]
    return list(reversed(matched)), offsets[-1]


def sort_key(option, mode):
    metric = {'fastest': option.estimatedTravelSeconds, 'transfers': option.transferCount,
              'walking': option.walkingDistanceMeters, 'distance': option.totalDistanceMeters}[mode]
    return (metric is None, metric or 0, option.transferCount,
            option.walkingDistanceMeters is None, option.walkingDistanceMeters or 0, option.routeOptionId)


class CheonanNetwork:
    def __init__(self, source=None, walks=None):
        self.data = source or json.loads((DATA / 'cheonan-transport.json').read_text(encoding='utf-8'))
        self.walks = walks if walks is not None else json.loads((DATA / 'cheonan-walks.json').read_text(encoding='utf-8'))
        self.origin = self.data['origin']
        self.stations = self.data['stations']
        self.routes = {r['routeId']: r for r in self.data['routes']}
        self.occurrences = defaultdict(list)
        for route in self.routes.values():
            if any(sid not in self.stations for sid in route['stops']):
                raise ValueError('A published route references an unknown stop')
            for index, sid in enumerate(route['stops']):
                self.occurrences[sid].append((route['routeId'], index))
        self.revision = digest([self.data, self.walks])
        self.retrieved = datetime.fromisoformat(self.data['retrievedAt'])
        self._positions = {}

    def register_origin(self, database):
        with database.session() as session:
            if session.get(Station, self.origin['stationId']) is None:
                session.add(Station(station_id=self.origin['stationId'], name=self.origin['name'],
                    direction_label='정류장 ' + self.origin['arsId'], region='충청남도 천안시', coordinates=self.origin['coordinates']))

    def ref(self, sid):
        return s.StationRef(stationId='cheonan-stop-' + sid, name=self.stations[sid]['name'])

    @lru_cache(maxsize=32768)
    def bus(self, route_id, board, alight, identity):
        route = self.routes[route_id]
        if route_id not in self._positions:
            self._positions[route_id] = positions(route, self.stations)
        match = self._positions[route_id]
        distance = round(match[0][alight] - match[0][board]) if match else None
        average = route.get('averageDurationMinutes')
        duration = round(average * 60 * distance / match[1]) if (match and match[1] > 0 and distance is not None
                    and type(average) in (int, float) and average > 0) else None
        return s.Bus(segmentId=identity, routeId='cheonan-route-' + route_id, routeName=route['name'],
            boardStation=self.ref(route['stops'][board]), alightStation=self.ref(route['stops'][alight]),
            boardSequence=board+1, alightSequence=alight+1, stopCount=alight-board,
            durationSeconds=duration, distanceMeters=distance)

    @lru_cache(maxsize=256)
    def candidates(self, destination_id, destination_name):
        destination = self.walks['destinations'].get(destination_id, {})
        target = defaultdict(list)
        for access in destination.get('access', []):
            for route_id, alight in self.occurrences[access['stationId']]:
                for board in range(alight):
                    target[self.routes[route_id]['stops'][board]].append((route_id, board, alight, access))
        paths = []
        origin_area = {walk['stationId'] for walk in self.walks['originAccess']}
        direct = destination.get('directWalk')
        if direct and direct['distanceMeters'] <= 1200:
            paths.append(([], None, direct, None))
        for start in self.walks['originAccess']:
            sid = start['stationId']
            for route_id, board, alight, access in target[sid]:
                paths.append(([(route_id, board, alight)], start, access, None))
            for route_id, board in self.occurrences[sid]:
                stops = self.routes[route_id]['stops']
                for transfer in range(board + 1, len(stops)):
                    # Exclude bus loops returning to another platform at the
                    # origin complex merely to avoid a short initial walk.
                    if stops[transfer] in origin_area:
                        continue
                    for next_id, next_board, next_alight, access in target[stops[transfer]]:
                        if route_id == next_id or self.routes[route_id]['name'] == self.routes[next_id]['name']:
                            continue
                        # A passenger must make forward progress, not return to
                        # a stop already passed on the first leg.
                        if self.routes[next_id]['stops'][next_alight] in stops[board:transfer+1]:
                            continue
                        paths.append(([(route_id, board, transfer), (next_id, next_board, next_alight)], start, access, stops[transfer]))
        # Prune path families using all four metrics before constructing public
        # models. This bounds memory on a city graph with many shared stops.
        best = {mode: {} for mode in SORTS}
        for path in paths:
            legs, start, access, _ = path
            family = tuple(self.routes[rid]['name'] for rid, _, _ in legs)
            buses = [self.bus(rid, board, alight, 'bus') for rid, board, alight in legs]
            walking = access['distanceMeters'] + (start['distanceMeters'] if start else 0)
            walk_time = access['durationSeconds'] + (start['durationSeconds'] if start else 0)
            distance = total([p.distanceMeters for p in buses] + [walking])
            duration = total([p.durationSeconds for p in buses] + [walk_time])
            stable = (tuple(legs), start['stationId'] if start else '', access.get('stationId', ''))
            metrics = {'fastest': duration, 'transfers': max(0, len(legs)-1), 'walking': walking, 'distance': distance}
            for mode, metric in metrics.items():
                key = (metric is None, metric or 0, len(legs), duration is None, duration or 0, walking, stable)
                if family not in best[mode] or key < best[mode][family][0]:
                    best[mode][family] = (key, path)
        shortlist = {}
        for ranked in best.values():
            for _, path in sorted(ranked.values(), key=lambda value: value[0])[:3]:
                legs, start, access, _ = path
                shortlist[digest([legs, start, access])] = path
        candidates = []
        for legs, start, access, transfer in shortlist.values():
            segments = []
            if start and start['distanceMeters'] > 0:
                segments.append(s.Walk(segmentId='origin-walk', fromLabel=self.origin['name'] + ' 정류장',
                    toLabel=self.stations[start['stationId']]['name'] + ' 정류장', distanceMeters=start['distanceMeters'], durationSeconds=start['durationSeconds']))
            for index, (rid, board, alight) in enumerate(legs):
                identity = f'bus-{index+1}'
                if index:
                    segments.append(s.Transfer(segmentId=f'transfer-{index}', fromSegmentId=f'bus-{index}',
                        toSegmentId=identity, atStation=self.ref(transfer)))
                segments.append(self.bus(rid, board, alight, identity))
            segments.append(s.Walk(segmentId='destination-walk', fromLabel=(self.stations[access['stationId']]['name'] if legs else self.origin['name']) + ' 정류장',
                toLabel=destination_name, distanceMeters=access['distanceMeters'], durationSeconds=access['durationSeconds']))
            buses = [p for p in segments if p.type == 'bus']
            walks = [p for p in segments if p.type == 'walk']
            identity = 'cheonan-option-' + digest([legs, start, access])
            option = s.RouteOption(routeOptionId=identity, routeSnapshotVersion='cheonan-v-' + digest([self.revision, [p.model_dump(mode='json') for p in segments]]),
                journeyStatus='ready', routeNames=[p.routeName for p in buses], transferCount=max(0,len(legs)-1),
                totalDurationSeconds=None, walkingDurationSeconds=total([p.durationSeconds for p in walks]),
                walkingDistanceMeters=total([p.distanceMeters for p in walks]),
                totalDistanceMeters=total([p.distanceMeters for p in segments if p.type != 'transfer']),
                estimatedTravelSeconds=total([p.durationSeconds for p in segments if p.type != 'transfer']),
                boardStation=buses[0].boardStation if buses else None, alightStation=buses[-1].alightStation if buses else None,
                transferStations=[p.atStation for p in segments if p.type == 'transfer'], dataSource='cheonan-bis-static')
            # Same buses with a nearby alighting/transfer stop are a single
            # alternative family; choose its best member for each sort later.
            family = tuple(self.routes[rid]['name'] for rid, _, _ in legs)
            candidates.append((family, option, segments))
        return candidates

    def search(self, session, request, destination, now, data_mode):
        if abs((request.departAt - now).total_seconds()) > 120:
            raise ServiceError(400, 'INVALID_REQUEST', '현재 시각에서 120초 이내의 출발 시각을 입력해 주세요.')
        all_candidates = self.candidates(destination.destinationId, destination.name)
        # Keep the best distinct families for every supported criterion before
        # applying the requested order; never truncate to an old top-three first.
        selected = {}
        winners = {}
        for mode in SORTS:
            families = set()
            for family, option, segments in sorted(all_candidates, key=lambda row: sort_key(row[1], mode)):
                if family in families:
                    continue
                families.add(family)
                selected[option.routeOptionId] = (family, option, segments)
                if len(families) == 1:
                    winners[mode] = option.routeOptionId
                if len(families) == 3:
                    break
        # Display one option per family in this order, capped at twelve.
        values, families = [], set()
        for family, option, segments in sorted(selected.values(), key=lambda row: sort_key(row[1], request.sort)):
            if family in families:
                continue
            families.add(family)
            features = {'fastest': '최소 이동시간 · 대기 제외', 'transfers': '최소 환승', 'walking': '최소 도보', 'distance': '최단 이동거리'}
            option = option.model_copy(update={'features': [features[k] for k, oid in winners.items() if oid == option.routeOptionId
                and (k != 'fastest' or option.estimatedTravelSeconds is not None) and (k != 'distance' or option.totalDistanceMeters is not None)]})
            values.append((option, segments))
        search_id = 'cheonan-search-' + uuid4().hex
        saved = {}
        for option, segments in values:
            detail = s.RouteDetail(routeSearchId=search_id, routeOptionId=option.routeOptionId, routeSnapshotVersion=option.routeSnapshotVersion,
                originStationId=request.originStationId, destinationId=request.destinationId, computedAt=now,
                journeyStatus='ready', referenceDataQuality=quality(None, self.retrieved, now, 'cheonan-bis-static'), segments=segments,
                dataSource='cheonan-bis-static', routingNotice=NOTICE, estimatedTravelSeconds=option.estimatedTravelSeconds,
                totalDistanceMeters=option.totalDistanceMeters, walkingDistanceMeters=option.walkingDistanceMeters)
            raw = detail.model_dump(mode='json')
            saved[option.routeOptionId] = {'kind': 'cheonan-reference', 'revision': self.revision, 'detail': raw, 'checksum': digest(raw)}
        session.add(RouteSearch(search_id=search_id, origin_station_id=request.originStationId, destination_id=request.destinationId,
            created_at=now.timestamp(), expires_at=(now+timedelta(minutes=10)).timestamp(), data_mode=data_mode, snapshot=saved))
        return s.SearchData(routeSearchId=search_id, originStationId=request.originStationId, destinationId=request.destinationId,
            expiresAt=now+timedelta(minutes=10), routeOptions=[o for o,_ in values], sortedBy=request.sort,
            routingNotice=NOTICE, referenceRetrievedAt=self.retrieved)

    def checked_detail(self, search, option_id, now, expected=None):
        saved = search.snapshot.get(option_id)
        if saved is None:
            not_found()
        try:
            if saved['kind'] != 'cheonan-reference' or saved['checksum'] != digest(saved['detail']):
                unavailable()
            detail = s.RouteDetail.model_validate(saved['detail'])
        except (KeyError, TypeError, ValidationError):
            unavailable()
        if saved['revision'] != self.revision or (expected and expected != detail.routeSnapshotVersion):
            changed()
        if (detail.routeSearchId != search.search_id or detail.routeOptionId != option_id or
                detail.originStationId != search.origin_station_id or detail.destinationId != search.destination_id or
                detail.computedAt.timestamp() != search.created_at):
            unavailable()
        # Rebuild from the current source, rather than trust a saved checksum as
        # proof that a bus/boarding occurrence really exists.
        options = self.candidates(search.destination_id, detail.segments[-1].toLabel)
        if not any(option.routeOptionId == option_id and option.routeSnapshotVersion == detail.routeSnapshotVersion
                   and segments == detail.segments for _, option, segments in options):
            changed()
        return detail
