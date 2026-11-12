"""Directed alternatives over published Cheonan BIS stop sequences.

Bus edges are never inferred from proximity. Transfers use the exact same BIS
stop ID; the only walking edges are imported pedestrian-network results.
"""
from bisect import bisect_right
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
          '이동시간은 천안시가 공개한 노선 전체 평균시간을 구간 거리에 비례해 추정한 값에 도보시간을 더한 값입니다. '
          '거리는 공식 노선 선형과 OSM 보행 경로 기준의 근삿값입니다.')
SORTS = ('fastest', 'transfers', 'walking', 'distance')
MAX_OPTIONS = 12


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
    return list(reversed(matched)), offsets


def clip_path(geometry, offsets, start, end):
    """Keep the official geometry only between the two matched occurrences."""
    if start >= end:
        return []

    def point(offset):
        i = min(bisect_right(offsets, offset) - 1, len(offsets) - 2)
        span = offsets[i+1] - offsets[i]
        fraction = (offset - offsets[i]) / span if span else 0
        return [a + fraction * (b - a) for a, b in zip(geometry[i], geometry[i+1])]

    points = [point(start), *(geometry[i] for i in range(bisect_right(offsets, start), bisect_right(offsets, end))
                             if offsets[i] < end), point(end)]
    return [s.Coordinates(latitude=lat, longitude=lon) for lat, lon in points]


def ranking_key(metrics, mode, identity):
    """Use the same deterministic order before and after candidate pruning."""
    metric, walking, travel, distance = (metrics[k] for k in (mode, 'walking', 'fastest', 'distance'))
    time_key, distance_key = (travel is None, travel or 0), (distance is None, distance or 0)
    prefer_distance = mode == 'walking' or (mode == 'transfers' and metrics['transfers'] > 0)
    tie_break = (distance_key, time_key) if prefer_distance else (time_key, distance_key)
    return (metric is None, metric or 0, metrics['transfers'], *tie_break,
            walking is None, walking or 0, identity)


def option_metrics(option):
    return {'fastest': option.estimatedTravelSeconds, 'transfers': option.transferCount,
            'walking': option.walkingDistanceMeters, 'distance': option.totalDistanceMeters}


def sort_key(option, mode):
    return ranking_key(option_metrics(option), mode, option.routeOptionId)


class CheonanNetwork:
    def __init__(self, source=None, walks=None):
        self.data = source or json.loads((DATA / 'cheonan-transport.json').read_text(encoding='utf-8'))
        self.walks = walks if walks is not None else json.loads((DATA / 'cheonan-walks.json').read_text(encoding='utf-8'))
        self.origin = (json.loads((DATA / 'cheonan-origin.json').read_text(encoding='utf-8'))
                       if source is None else self.data['origin'])
        if self.origin != self.data['origin']:
            raise ValueError('Kiosk origin does not match the official transport snapshot')
        self.stations = self.data['stations']
        self.routes = {r['routeId']: r for r in self.data['routes']}
        origin_row = self.stations[self.origin['publicId']]
        if (self.origin['stationId'] != 'cheonan-stop-' + self.origin['publicId']
                or (self.origin['arsId'], self.origin['name']) != (origin_row['arsId'], origin_row['name'])
                or self.origin['coordinates'] != self.coordinates(self.origin['publicId'])):
            raise ValueError('Kiosk origin does not match the official stop ID and coordinates')
        self.occurrences = defaultdict(list)
        for route in self.routes.values():
            if any(sid not in self.stations for sid in route['stops']):
                raise ValueError('A published route references an unknown stop')
            for index, sid in enumerate(route['stops']):
                self.occurrences[sid].append((route['routeId'], index))
        self.revision = digest(['directed-stops-v4', self.data, self.walks])
        self.retrieved = datetime.fromisoformat(self.data['retrievedAt'])
        self._positions = {}

    def register_origin(self, database):
        with database.session() as session:
            station = session.get(Station, self.origin['stationId'])
            if station is None:
                station = Station(station_id=self.origin['stationId'])
                session.add(station)
            # A reused database must not leave the UI/distance origin at old or
            # manually edited coordinates while this graph uses the fixed stop.
            station.name = self.origin['name']
            station.direction_label = '정류장 ' + self.origin['arsId']
            station.region = '충청남도 천안시'
            station.coordinates = dict(self.origin['coordinates'])

    def coordinates(self, sid):
        row = self.stations[sid]
        return {'latitude': row['latitude'], 'longitude': row['longitude']}

    def ref(self, sid):
        row = self.stations[sid]
        return s.StationRef(stationId='cheonan-stop-' + sid, name=row['name'], arsId=row.get('arsId') or None)

    def station(self, station_id):
        sid = station_id.removeprefix('cheonan-stop-')
        if sid == station_id or sid not in self.stations:
            not_found()
        ref = self.ref(sid)
        return s.Station(**ref.model_dump(), directionLabel=f'정류장 {ref.arsId}' if ref.arsId else '방향 미확인',
            region='충청남도 천안시' if sid == self.origin['publicId'] else None, coordinates=self.coordinates(sid))

    def require_origin(self, station_id):
        if station_id != self.origin['stationId']:
            raise ServiceError(400, 'INVALID_REQUEST',
                f"이 키오스크는 {self.origin['name']} {self.origin['arsId']}번 정류장에서만 출발합니다.")

    def direct_walk(self, destination_id):
        if self.walks.get('originStationId') == self.origin['stationId']:
            return self.walks['destinations'].get(destination_id, {}).get('directWalk')
        return None

    @lru_cache(maxsize=32768)
    def bus(self, route_id, board, alight, identity):
        route = self.routes[route_id]
        if route_id not in self._positions:
            self._positions[route_id] = positions(route, self.stations)
        match = self._positions[route_id]
        distance = round(match[0][alight] - match[0][board]) if match else None
        if distance == 0:
            distance = None
        average = route.get('averageDurationMinutes')
        duration = round(average * 60 * distance / match[1][-1]) if (match and match[1][-1] > 0 and distance is not None
                    and type(average) in (int, float) and average > 0) else None
        return s.Bus(segmentId=identity, routeId='cheonan-route-' + route_id, routeName=route['name'],
            boardStation=self.ref(route['stops'][board]), alightStation=self.ref(route['stops'][alight]),
            boardSequence=board+1, alightSequence=alight+1, stopCount=alight-board,
            durationSeconds=duration, distanceMeters=distance)

    def detailed_bus(self, route_id, board, alight, identity):
        bus = self.bus(route_id, board, alight, identity)
        route = self.routes[route_id]
        stops = route['stops']
        # BIS free-form route descriptions can be stale (e.g. 192). Use the
        # actual terminus, or the next stop when the terminus name repeats here.
        terminal = self.stations[stops[-1]]['name']
        direction_stop = self.stations[stops[board+1]]['name'] if terminal == bus.boardStation.name else terminal
        direction = f'{direction_stop} 방면'
        refs = [s.RouteStop(**self.ref(sid).model_dump(), sequence=index, coordinates=self.coordinates(sid))
                for index, sid in enumerate(stops[board:alight+1], board+1)]
        match = self._positions[route_id]
        path = clip_path(route['geometry'], match[1], match[0][board], match[0][alight]) if bus.distanceMeters else []
        return bus.model_copy(update={'directionLabel': direction, 'stops': refs, 'path': path})

    @lru_cache(maxsize=256)
    def candidates(self, destination_id, destination_name):
        destination = self.walks['destinations'].get(destination_id, {})
        origin_sid = self.origin['publicId']
        direct_walk = self.direct_walk(destination_id)
        target = defaultdict(list)
        for access in destination.get('access', []):
            alight_sid = access['stationId']
            if alight_sid == origin_sid:
                continue
            if direct_walk and all(direct_walk[key] <= access[key] for key in ('distanceMeters', 'durationSeconds')):
                continue  # Riding cannot improve a trip whose final walk alone is longer.
            for route_id, alight in self.occurrences[alight_sid]:
                stops = self.routes[route_id]['stops']
                for board in range(alight):
                    target[stops[board]].append((route_id, board, alight, access))
        paths = []
        direct_access = set()
        for route_id, board, alight, access in target[origin_sid]:
            if origin_sid not in self.routes[route_id]['stops'][board+1:alight+1]:
                paths.append(([(route_id, board, alight)], access, None))
                direct_access.add((route_id, access['stationId']))
        for route_id, board in self.occurrences[origin_sid]:
            stops = self.routes[route_id]['stops']
            visited = {origin_sid}
            for transfer in range(board + 1, len(stops)):
                if stops[transfer] == origin_sid:
                    break
                visited.add(stops[transfer])
                for next_id, next_board, next_alight, access in target[stops[transfer]]:
                    if route_id == next_id:
                        continue
                    # If either line already connects the kiosk to this exact
                    # alighting stop, swapping between them adds no connection.
                    alight_sid = access['stationId']
                    if (route_id, alight_sid) in direct_access or (next_id, alight_sid) in direct_access:
                        continue
                    onward = self.routes[next_id]['stops'][next_board+1:next_alight+1]
                    if not visited.isdisjoint(onward):
                        continue
                    paths.append(([(route_id, board, transfer), (next_id, next_board, next_alight)], access, stops[transfer]))
        # Prune path families using all four metrics before constructing public
        # models. This bounds memory on a city graph with many shared stops.
        best = {mode: {} for mode in SORTS}
        direct_metrics = defaultdict(list)
        for path in paths:
            legs, access, _ = path
            family = tuple(rid for rid, _, _ in legs)
            stop_sequences = tuple(tuple(self.routes[rid]['stops'][board:alight+1]) for rid, board, alight in legs)
            buses = [self.bus(rid, board, alight, 'bus') for rid, board, alight in legs]
            walking = access['distanceMeters']
            walk_time = access['durationSeconds']
            distance = total([p.distanceMeters for p in buses] + [walking])
            duration = total([p.durationSeconds for p in buses] + [walk_time])
            identity = 'cheonan-option-' + digest([legs, access])
            metrics = {'fastest': duration, 'transfers': max(0, len(legs)-1), 'walking': walking, 'distance': distance}
            at_stop = direct_metrics[access['stationId']]
            if len(legs) == 1:
                at_stop.append((duration, distance))
            elif any(time is not None and length is not None
                     and (duration is None or time <= duration) and (distance is None or length <= distance)
                     for time, length in at_stop):
                continue  # A verified direct ride to this stop is as short or shorter.
            for mode in SORTS:
                key = ranking_key(metrics, mode, identity)
                if family not in best[mode] or key < best[mode][family][0]:
                    best[mode][family] = (key, path, stop_sequences)
        shortlist = {}
        for ranked in best.values():
            ordered = sorted(ranked.values(), key=lambda value: value[0])
            groups = {}
            for row in ordered:
                groups.setdefault(row[2], []).append(row)
            # An identical boarding-to-alighting sequence consumes one place
            # in the shortlist. Keep its bus variants for arrival comparison.
            for variants in list(groups.values())[:3]:
                for key, path, stop_sequences in variants:
                    shortlist[key[-1]] = (path, stop_sequences)
        # A direct line is a useful alternative when the user is waiting at the
        # kiosk, even if several other lines have similar movement estimates.
        direct = (value for family, value in best['transfers'].items() if len(family) == 1)
        for key, path, stop_sequences in sorted(direct, key=lambda value: value[0])[:MAX_OPTIONS]:
            shortlist[key[-1]] = (path, stop_sequences)
        candidates = []
        for option_id, ((legs, access, transfer), stop_sequences) in shortlist.items():
            segments = []
            for index, (rid, board, alight) in enumerate(legs):
                identity = f'bus-{index+1}'
                if index:
                    segments.append(s.Transfer(segmentId=f'transfer-{index}', fromSegmentId=f'bus-{index}',
                        toSegmentId=identity, atStation=self.ref(transfer)))
                segments.append(self.detailed_bus(rid, board, alight, identity))
            alight_ref = segments[-1].alightStation
            from_label = alight_ref.name + (f' ({alight_ref.arsId}번)' if alight_ref.arsId else '') + ' 정류장'
            segments.append(s.Walk(segmentId='destination-walk', fromLabel=from_label,
                toLabel=destination_name, distanceMeters=access['distanceMeters'], durationSeconds=access['durationSeconds']))
            buses = [p for p in segments if p.type == 'bus']
            walks = [p for p in segments if p.type == 'walk']
            option = s.RouteOption(routeOptionId=option_id, routeSnapshotVersion='cheonan-v-' + digest([self.revision, [p.model_dump(mode='json') for p in segments]]),
                pathGroupId='cheonan-path-' + digest(stop_sequences),
                journeyStatus='ready', routeNames=[p.routeName for p in buses], directionLabels=[p.directionLabel for p in buses],
                transferCount=max(0,len(legs)-1),
                totalDurationSeconds=None, walkingDurationSeconds=total([p.durationSeconds for p in walks]),
                walkingDistanceMeters=total([p.distanceMeters for p in walks]),
                totalDistanceMeters=total([p.distanceMeters for p in segments if p.type != 'transfer']),
                estimatedTravelSeconds=total([p.durationSeconds for p in segments if p.type != 'transfer']),
                boardStation=buses[0].boardStation, alightStation=buses[-1].alightStation,
                transferStations=[p.atStation for p in segments if p.type == 'transfer'], dataSource='cheonan-bis-static')
            # Same buses with a nearby alighting/transfer stop are a single
            # alternative family; choose its best member for each sort later.
            family = tuple(rid for rid, _, _ in legs)
            candidates.append((family, option, segments))
        return candidates

    def search(self, session, request, destination, now, data_mode):
        self.require_origin(request.originStationId)
        if abs((request.departAt - now).total_seconds()) > 120:
            raise ServiceError(400, 'INVALID_REQUEST', '현재 시각에서 120초 이내의 출발 시각을 입력해 주세요.')
        all_candidates = self.candidates(destination.destinationId, destination.name)
        minima = {mode: min((option_metrics(option)[mode] for _, option, _ in all_candidates
                    if option_metrics(option)[mode] is not None), default=None) for mode in SORTS}
        groups, families = set(), set()
        representatives, variants = [], []
        for family, option, segments in sorted(all_candidates, key=lambda row: sort_key(row[1], request.sort)):
            if family in families:
                continue
            families.add(family)
            if option.pathGroupId in groups:
                variants.append((option, segments))
            else:
                groups.add(option.pathGroupId)
                representatives.append((option, segments))
        # Give different paths space before adding equivalent bus variants.
        selected = (representatives + variants)[:MAX_OPTIONS]
        values = []
        for option, segments in sorted(selected, key=lambda row: sort_key(row[0], request.sort)):
            features = {'fastest': '최소 이동시간 · 대기 제외', 'transfers': '최소 환승', 'walking': '최소 도보', 'distance': '최단 이동거리'}
            metrics = option_metrics(option)
            option = option.model_copy(update={'features': [features[mode] for mode in SORTS
                if minima[mode] is not None and metrics[mode] == minima[mode]]})
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
