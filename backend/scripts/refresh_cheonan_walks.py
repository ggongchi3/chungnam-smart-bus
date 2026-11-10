"""One-time OSM/Valhalla pedestrian matrix import; cached, one request/second.

Only road-routed links are approved. A straight-line proximity test is a bounded
candidate lookup, not evidence of pedestrian access. No automotive routes used.
"""
import json
from math import isfinite
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.services.geo import haversine_meters

URL = 'https://valhalla1.openstreetmap.de/sources_to_targets'
CACHE = ROOT / 'backend/.local/cheonan-walk-import'


def point(coordinates):
    return {'lat': coordinates['latitude'], 'lon': coordinates['longitude']}


def matrix(client, key, sources, targets):
    path = CACHE / (key + '.json')
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    response = client.get(URL, params={'json': json.dumps({'sources': sources, 'targets': targets,
        'costing': 'pedestrian', 'units': 'kilometers', 'costing_options': {'pedestrian': {'walking_speed': 4.0}}})})
    response.raise_for_status()
    data = response.json()
    path.write_text(json.dumps(data), encoding='utf-8')
    time.sleep(1.1)
    return data


def link(value):
    distance, duration = value.get('distance'), value.get('time')
    if any(type(v) not in (int, float) or not isfinite(v) or v < 0 for v in (distance, duration)):
        return None
    return {'distanceMeters': round(distance * 1000), 'durationSeconds': round(duration)}


def complete_direct_walks():
    """Fill missing origin-to-place paths without refreshing approved bus access."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = ROOT / 'shared/data/cheonan-walks.json'
    output = json.loads(path.read_text(encoding='utf-8'))
    transit = json.loads((ROOT / 'shared/data/cheonan-transport.json').read_text(encoding='utf-8'))
    places = json.loads((ROOT / 'shared/data/cheonan-places.json').read_text(encoding='utf-8'))['places']
    with httpx.Client(timeout=40, headers={'User-Agent': 'CheonanSmartBus/0.1 local-reference-import'}) as client:
        for place in places:
            entry = output['destinations'].get(place['destinationId'])
            if entry is None or entry.get('directWalk'):
                continue
            data = matrix(client, place['destinationId'] + '-direct-v1',
                [point(transit['origin']['coordinates'])], [point(place['coordinates'])])
            walk = link(data['sources_to_targets'][0][0])
            if not walk:
                raise ValueError('No pedestrian route for ' + place['destinationId'])
            entry['directWalk'] = walk
            entry['directWalkRetrievedAt'] = datetime.now(timezone.utc).isoformat()
            print(place['destinationId'], walk, flush=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    transit = json.loads((ROOT / 'shared/data/cheonan-transport.json').read_text(encoding='utf-8'))
    places = json.loads((ROOT / 'shared/data/cheonan-places.json').read_text(encoding='utf-8'))['places']
    origin = transit['origin']['coordinates']
    used = {sid for route in transit['routes'] for sid in route['stops']}
    stations = {sid: {'latitude': row['latitude'], 'longitude': row['longitude']} for sid, row in transit['stations'].items() if sid in used}
    output = {'schemaVersion': 1, 'sourceUrl': 'https://valhalla.openstreetmap.de/',
              'attribution': '© OpenStreetMap contributors (ODbL) · Valhalla / FOSSGIS',
              'costing': 'pedestrian', 'walkingSpeedKmh': 4.0,
              'retrievedAt': datetime.now(timezone.utc).isoformat(), 'originAccess': [], 'destinations': {}, 'failures': []}
    with httpx.Client(timeout=40, headers={'User-Agent': 'CheonanSmartBus/0.1 local-reference-import'}) as client:
        origin_stops = sorted((sid for sid, pos in stations.items() if haversine_meters(origin, pos) <= 350),
                              key=lambda sid: (haversine_meters(origin, stations[sid]), sid))[:8]
        values = matrix(client, 'origin', [point(origin)], [point(stations[sid]) for sid in origin_stops])
        for sid, value in zip(origin_stops, values['sources_to_targets'][0]):
            walk = link(value)
            if walk and walk['distanceMeters'] <= 600:
                output['originAccess'].append({'stationId': sid, **walk})
        for place in places:
            coordinates = place.get('coordinates')
            if not coordinates:
                output['failures'].append(place['destinationId'])
                continue
            nearby = sorted((sid for sid, pos in stations.items() if haversine_meters(coordinates, pos) <= 1500),
                            key=lambda sid: (haversine_meters(coordinates, stations[sid]), sid))[:4]
            sources = [point(stations[sid]) for sid in nearby]
            direct = True
            if direct:
                sources.append(point(origin))
            try:
                data = matrix(client, place['destinationId'] + '-all-direct-v2', sources, [point(coordinates)])
                walks = []
                for sid, row in zip(nearby, data['sources_to_targets']):
                    walk = link(row[0])
                    if walk and walk['distanceMeters'] <= 2500:
                        walks.append({'stationId': sid, **walk})
                output['destinations'][place['destinationId']] = {'access': walks,
                    'directWalk': link(data['sources_to_targets'][-1][0]) if direct else None}
                print(place['destinationId'], len(walks), flush=True)
            except (httpx.HTTPError, KeyError, ValueError):
                output['failures'].append(place['destinationId'])
        (ROOT / 'shared/data/cheonan-walks.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Walking reference saved; failures:', output['failures'], flush=True)


if __name__ == '__main__':
    complete_direct_walks() if '--complete-direct' in sys.argv else main()
