"""Manual, cached import of Cheonan's public BIS reference data (no API key).

Run from the repository root. Never invoked by an HTTP request or on app startup.
The reference snapshot has no vehicle observations or manufactured timetables.
"""
import json
from math import isfinite
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
BASE = 'https://its.cheonan.go.kr'
CACHE = ROOT / 'backend/.local/cheonan-import'
OUTPUT = ROOT / 'shared/data/cheonan-transport.json'


def origin_from_stops(stops):
    """Bind the fixed stop to the official response on every manual refresh."""
    public_id = '285000686'
    row = next((row for row in stops if str(row.get('STOP_ID')) == public_id), None)
    if row is None:
        raise RuntimeError('Official origin stop is missing; existing snapshot preserved')
    latitude, longitude = float(row['LAT']), float(row['LNG'])
    if not (isfinite(latitude) and isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError('Official origin coordinates are invalid; existing snapshot preserved')
    if not row.get('STOP_NAME') or not row.get('SERVICE_ID'):
        raise ValueError('Official origin name or ARS number is missing; existing snapshot preserved')
    return {'stationId': 'cheonan-stop-' + public_id, 'publicId': public_id,
            'name': row['STOP_NAME'], 'arsId': str(row['SERVICE_ID']),
            'address': '충청남도 천안시 동남구 만남로 (천안종합버스터미널 앞)',
            'addressNote': '도로 위 정류장으로 건물 도로명주소와 구분',
            'coordinates': {'latitude': latitude, 'longitude': longitude},
            'sourceUrl': BASE + '/bis/busStop.do'}


def fetch(client, endpoint, **params):
    key = endpoint + '-' + '-'.join(str(v) for v in params.values())
    path = CACHE / (key + '.json')
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    response = client.get('/bis/' + endpoint + '.do', params=params)
    response.raise_for_status()
    data = response.json()['resultList']
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    time.sleep(.3)
    return data


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=BASE, timeout=30, headers={'User-Agent': 'CheonanSmartBus/0.1 reference-data-import'}) as client:
        stops = fetch(client, 'getBusStopList', searchKeyword='')
        origin = origin_from_stops(stops)
        routes = fetch(client, 'getRouteList', searchKeyword='')
        # All directional municipal routes, including cross-boundary routes.
        result = []
        failures = []
        for index, route in enumerate(routes):
            identity = route['ROUTE_ID']
            try:
                sequence = fetch(client, 'getBusStopOnRouteList', routeId=identity)
                geometry = fetch(client, 'getRouteVrtxList', routeId=identity)
                if len(sequence) < 2 or any(not all(k in row for k in ('STOP_ID', 'STOP_NAME', 'LAT', 'LNG')) for row in sequence):
                    failures.append(identity)
                    continue
                result.append({
                    'routeId': str(identity), 'name': route['ROUTE_NAME'],
                    'direction': route.get('ROUTE_EXPLAIN', ''),
                    'firstDeparture': route.get('START_TIME'), 'lastDeparture': route.get('END_TIME'),
                    'averageDurationMinutes': route.get('AVG_TIME'),
                    'allocation': route.get('T_ALLOC_TIME', route.get('ALLOC_TIME')),
                    'stops': [str(row['STOP_ID']) for row in sequence],
                    'geometry': [[row['LAT'], row['LNG']] for row in geometry],
                })
            except (httpx.HTTPError, ValueError, KeyError):
                failures.append(identity)
            if (index + 1) % 30 == 0:
                print(f'{index + 1}/{len(routes)} routes read', flush=True)
        data = {
            'schemaVersion': 1, 'retrievedAt': datetime.now(timezone.utc).isoformat(),
            'sourceUrl': BASE + '/bis/route.do', 'sourceName': '천안시 교통정보센터',
            'sourceUpdatedAt': None,
            'coverage': '공식 공개 목록의 방향별 노선. 개별 운행일·구간 시간표는 미제공.',
            'failedRouteIds': failures,
            'origin': origin,
            'stations': {str(row['STOP_ID']): {'name': row['STOP_NAME'], 'arsId': str(row.get('SERVICE_ID', '')),
                         'latitude': row['LAT'], 'longitude': row['LNG']} for row in stops},
            'routes': result,
        }
        # Some cross-boundary stops occur only in the route response. Obtain their
        # actual coordinates from that response; never substitute a nearby stop.
        for route in routes:
            path = CACHE / f"getBusStopOnRouteList-{route['ROUTE_ID']}.json"
            if not path.exists():
                continue
            for row in json.loads(path.read_text(encoding='utf-8')):
                if not all(k in row for k in ('STOP_ID', 'STOP_NAME', 'LAT', 'LNG')):
                    continue
                data['stations'].setdefault(str(row['STOP_ID']), {'name': row['STOP_NAME'],
                    'arsId': str(row.get('SERVICE_ID', '')), 'latitude': row['LAT'], 'longitude': row['LNG']})
        if len(result) < 10:
            raise RuntimeError('Insufficient reference data; existing snapshot preserved')
        OUTPUT.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
        OUTPUT.with_name('cheonan-origin.json').write_text(json.dumps(data['origin'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'Saved {len(result)} routes, {len(data["stations"])} stations; {len(failures)} missing routes', flush=True)


if __name__ == '__main__':
    main()
