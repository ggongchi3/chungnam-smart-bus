"""Audit real Cheonan HTTP APIs, optionally through the frontend's /api proxy.

Run the API with an isolated memory DB, then pass --base-url. This never starts
or terminates existing servers, and never edits the published reference data.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

import httpx

DATA = Path(__file__).resolve().parents[2] / 'shared/data'
MODES = {'transfers': 'transferCount', 'walking': 'walkingDistanceMeters',
         'distance': 'totalDistanceMeters', 'fastest': 'estimatedTravelSeconds'}


def verify(base_url):
    source = json.loads((DATA / 'cheonan-transport.json').read_text(encoding='utf-8'))
    origin = source['origin']
    routes = {'cheonan-route-' + row['routeId']: row for row in source['routes']}
    checks = Counter()
    counts, changed_orders = {}, []
    with httpx.Client(base_url=base_url, timeout=60, trust_env=False) as client:
        def request(method, path, **kwargs):
            response = client.request(method, '/api/v1' + path, **kwargs)
            assert response.status_code == 200, (response.status_code, response.text)
            payload = response.json()
            assert payload['meta']['dataMode'] == 'static', payload['meta']
            checks['httpRequests'] += 1
            return payload['data']

        station = request('GET', '/stations/' + origin['stationId'])['station']
        assert station['name'] == origin['name'] and station['coordinates'] == origin['coordinates']
        params = {'originStationId': origin['stationId']}
        places = request('GET', '/destinations', params=params)['destinations']
        assert len(places) == 26
        assert places == sorted(places, key=lambda p: (p['distanceMeters'], p['name'], p['destinationId']))
        for kind in sorted({p['placeKind'] for p in places}):
            found = request('GET', '/destinations', params={**params, 'kind': kind})['destinations']
            assert found == [p for p in places if p['placeKind'] == kind]
            checks['categories'] += 1
        for place in places:
            orders = []
            for mode, metric in MODES.items():
                found = request('POST', '/route-searches', json={**params,
                    'destinationId': place['destinationId'], 'sort': mode,
                    'departAt': datetime.now(timezone.utc).isoformat()})
                options = found['routeOptions']
                assert options, place['name']
                metrics = [(p[metric] is None, p[metric] or 0) for p in options]
                assert metrics == sorted(metrics), (place['name'], mode)
                families = [tuple(p['routeNames']) for p in options]
                assert len(set(families)) == len(families)
                orders.append(tuple(families))
                checks['routeSearches'] += 1
                if mode != 'transfers':
                    continue
                counts[place['name']] = len(options)
                for option in options:
                    path = f"/route-searches/{found['routeSearchId']}/options/{option['routeOptionId']}"
                    detail = request('GET', path)
                    buses = [p for p in detail['segments'] if p['type'] == 'bus']
                    transfers = [p for p in detail['segments'] if p['type'] == 'transfer']
                    assert option['transferCount'] == max(0, len(buses)-1) == len(transfers)
                    for bus in buses:
                        stops = routes[bus['routeId']]['stops']
                        assert 1 <= bus['boardSequence'] < bus['alightSequence'] <= len(stops)
                        assert stops[bus['boardSequence']-1] == bus['boardStation']['stationId'].removeprefix('cheonan-stop-')
                        assert stops[bus['alightSequence']-1] == bus['alightStation']['stationId'].removeprefix('cheonan-stop-')
                    if transfers:
                        assert buses[0]['alightStation'] == transfers[0]['atStation'] == buses[1]['boardStation']
                    assert option['waitingDurationSeconds'] is None
                    assert option['totalDurationSeconds'] is None
                    checks['verifiedDetails'] += 1
            if len(set(orders)) > 1:
                changed_orders.append(place['name'])
        # Verify the same selection reaches AI guidance, arrival lookup and print.
        selection = {key: found[key] for key in ('routeSearchId',)}
        selection.update(routeOptionId=options[0]['routeOptionId'],
            expectedRouteSnapshotVersion=options[0]['routeSnapshotVersion'])
        request('POST', '/easy-guidance', json=selection)
        request('POST', '/print-guides', json=selection)
        request('GET', f"/route-searches/{selection['routeSearchId']}/options/{selection['routeOptionId']}/live")
        interpretation = request('POST', '/destination-interpretations', json={**params, 'text': '가까운 병원'})
        candidates = interpretation['candidates']
        assert [p['distanceMeters'] for p in candidates] == sorted(p['distanceMeters'] for p in candidates)
        assert changed_orders
    return {'verifiedAt': datetime.now(timezone.utc).isoformat(), 'baseUrl': base_url,
        'origin': origin, 'checks': dict(checks), 'placeCount': len(places),
        'routeOptionCounts': counts, 'destinationsWithDifferentSortOrders': changed_orders,
        'limitations': ['Static route structure only; operating calendar and wait-inclusive arrival time unverified.',
            'Places are limited to the 26 verified catalogue entries.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = verify(args.base_url)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
