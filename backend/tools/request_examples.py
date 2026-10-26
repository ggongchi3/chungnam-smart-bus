"""Executable integration examples; departAt is always generated at request time."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import httpx


def exercise(base_url):
    results = {}
    with httpx.Client(base_url=base_url, timeout=5, trust_env=False) as client:
        def request(name, method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            results[name] = {'httpStatus': response.status_code, 'response': response.json()}
            return response
        station = request('station', 'GET', '/api/v1/stations/demo-stop-001')
        assert station.status_code == 200
        request('destinations', 'GET', '/api/v1/destinations', params={'originStationId':'demo-stop-001','query':'장터'})
        request('emptyResult', 'GET', '/api/v1/destinations', params={'originStationId':'demo-stop-001','query':'없는장소'})
        request('invalidInput', 'GET', '/api/v1/destinations', params={'originStationId':'demo-stop-001','category':'invalid'})
        request('notFound', 'GET', '/api/v1/stations/not-registered')
        data = request('routeSearch', 'POST', '/api/v1/route-searches', json={
            'originStationId':'demo-stop-001','destinationId':'demo-destination-003',
            'departAt':datetime.now(timezone.utc).isoformat()}).json()['data']
        option = data['routeOptions'][0]
        selection = {'routeSearchId':data['routeSearchId'],'routeOptionId':option['routeOptionId'],
                     'expectedRouteSnapshotVersion':option['routeSnapshotVersion']}
        path = f"/api/v1/route-searches/{selection['routeSearchId']}/options/{selection['routeOptionId']}"
        detail = request('routeDetail','GET',path).json()['data']
        assert sum(p['stopCount'] for p in detail['segments'] if p['type']=='bus') == 4
        request('live','GET',path+'/live')
        request('interpretation','POST','/api/v1/destination-interpretations',
                json={'originStationId':'demo-stop-001','text':'큰 병원에 가고 싶어요'})
        request('guidance','POST','/api/v1/easy-guidance',json=selection)
        printed = request('printGuide','POST','/api/v1/print-guides',json=selection).json()['data']
        assert printed['routeDetail']['routeSnapshotVersion'] == printed['liveInfoSnapshot']['routeSnapshotVersion']
        assert all(p['etaSeconds'] is None for p in printed['liveInfoSnapshot']['arrivals'])
        request('changedVersion','POST','/api/v1/print-guides',json={**selection,'expectedRouteSnapshotVersion':'old'})
        assert results['emptyResult']['response']['data']['destinations'] == []
        assert results['invalidInput']['httpStatus'] == 400 and results['notFound']['httpStatus'] == 404
        assert results['changedVersion']['httpStatus'] == 409
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = exercise(args.base_url)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        target = args.output.resolve()
        if not target.is_relative_to(Path(__file__).resolve().parents[1]):
            raise SystemExit('Output must stay inside backend/')
        target.write_text(encoded, encoding='utf-8')
    print('8 APIs + empty/400/404/409: HTTP verification passed')
