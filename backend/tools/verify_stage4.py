"""Exercise route searches and saved details through real HTTP in demo mode."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import socket
import subprocess
import sys
from time import monotonic, sleep

import httpx

from backend.config import ROOT, Settings
from backend.integrations.providers import DemoProvider
from backend.models import schemas as s

SEARCH_PATH = '/api/v1/route-searches'
ORIGINS = ('http://localhost:5173', 'http://127.0.0.1:5173')


def aware(value):
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    return parsed


def exercise(base_url):
    records, selections = [], []
    with httpx.Client(base_url=base_url, timeout=5, trust_env=False) as client:
        def request(name, method, path, expected_status=200, expected_code=None, **kwargs):
            started = monotonic()
            response = client.request(method, path, headers={'Origin': ORIGINS[0]}, **kwargs)
            elapsed = round((monotonic() - started) * 1000, 2)
            body = response.json()
            assert response.status_code == expected_status, (name, response.text)
            assert set(body) == {'data', 'error', 'meta'}
            assert body['meta']['dataMode'] == 'demo'
            aware(body['meta']['generatedAt'])
            assert response.headers['x-request-id'] == body['meta']['requestId']
            assert response.headers['access-control-allow-origin'] == ORIGINS[0]
            assert response.headers['cache-control'] == 'no-store'
            if expected_status == 200:
                assert body['error'] is None
            else:
                s.Envelope[None].model_validate(body)
                assert body['data'] is None and body['error']['code'] == expected_code
            recorded_request = {'method': method, 'path': path}
            if 'json' in kwargs:
                recorded_request['json'] = dict(kwargs['json'])
                if 'departAt' in recorded_request['json']:
                    # Keep recorded responses exact but make request examples safe to replay.
                    time_examples = {
                        'timezoneMissing': '<datetime.now().replace(tzinfo=None).isoformat()>',
                        'departureTooOld': '<(datetime.now(timezone.utc) - timedelta(seconds=180)).isoformat()>',
                        'departureTooFarFuture': '<(datetime.now(timezone.utc) + timedelta(seconds=180)).isoformat()>',
                    }
                    recorded_request['json']['departAt'] = time_examples.get(
                        name, '<datetime.now(timezone.utc).isoformat() at request time>')
            if 'content' in kwargs:
                recorded_request['body'] = kwargs['content']
            records.append({'name': name, 'request': recorded_request, 'httpStatus': response.status_code,
                            'elapsedMilliseconds': elapsed, 'response': body})
            return body

        def search(name, destination='001', origin='001', **kwargs):
            payload = {'originStationId': 'demo-stop-' + origin,
                       'destinationId': 'demo-destination-' + destination,
                       'departAt': datetime.now(timezone.utc).isoformat()}
            payload.update(kwargs.pop('payload_updates', {}))
            return request(name, 'POST', SEARCH_PATH, json=payload, **kwargs)

        paths, option_ids = {}, {}
        for label, destination, stop_count, transfers in (
                ('market', '002', 1, 0), ('hospital', '001', 2, 0), ('terminal', '003', 4, 1)):
            envelope = search(label + 'Search', destination)
            found = s.Envelope[s.SearchData].model_validate(envelope).data
            data = envelope['data']
            assert found.originStationId == 'demo-stop-001'
            assert found.destinationId == 'demo-destination-' + destination
            assert len(found.routeOptions) == 1
            option = found.routeOptions[0]
            assert option.transferCount == transfers and option.journeyStatus == 'ready'
            assert option.totalDurationSeconds is None and option.walkingDurationSeconds is None
            path = f'{SEARCH_PATH}/{found.routeSearchId}/options/{option.routeOptionId}'
            detail_body = request(label + 'Detail', 'GET', path)
            detail = s.Envelope[s.RouteDetail].model_validate(detail_body).data
            assert detail.routeSearchId == found.routeSearchId and detail.routeOptionId == option.routeOptionId
            assert detail.routeSnapshotVersion == option.routeSnapshotVersion
            assert detail.originStationId == found.originStationId and detail.destinationId == found.destinationId
            assert detail.journeyStatus == 'ready'
            assert aware(data['expiresAt']) - detail.computedAt == timedelta(seconds=600)
            bus = [p for p in detail.segments if p.type == 'bus']
            assert sum(p.stopCount for p in bus) == stop_count
            assert len(bus) == transfers + 1
            assert all(p.boardSequence < p.alightSequence and p.durationSeconds is None for p in bus)
            assert len({p.segmentId for p in detail.segments}) == len(detail.segments)
            walks = [p for p in detail.segments if p.type == 'walk']
            assert len(walks) == 1 and walks[0].distanceMeters is None and walks[0].durationSeconds is None
            if transfers:
                assert [p.type for p in detail.segments] == ['bus', 'transfer', 'bus', 'walk']
                transfer = detail.segments[1]
                assert transfer.fromSegmentId == bus[0].segmentId and transfer.toSegmentId == bus[1].segmentId
                assert transfer.atStation.stationId == 'demo-stop-003'
            else:
                assert [p.type for p in detail.segments] == ['bus', 'walk']
            again = request(label + 'RepeatedDetail', 'GET', path)
            assert again['data'] == detail_body['data']
            handoff = {'originStationId': found.originStationId, 'destinationId': found.destinationId,
                       'routeSearchId': found.routeSearchId, 'routeOptionId': option.routeOptionId,
                       'routeSnapshotVersion': option.routeSnapshotVersion,
                       'dataMode': envelope['meta']['dataMode']}
            assert set(handoff) == {'originStationId', 'destinationId', 'routeSearchId', 'routeOptionId',
                                    'routeSnapshotVersion', 'dataMode'}
            assert all(isinstance(v, str) and v for v in handoff.values())
            selections.append({'scenario': label, 'selection': handoff, 'expectedBusStopCount': stop_count})
            paths[label], option_ids[label] = path, option.routeOptionId

        repeated = search('hospitalRepeatedSearch')['data']
        hospital = selections[1]['selection']
        assert repeated['routeSearchId'] != hospital['routeSearchId']
        assert repeated['routeOptions'][0]['routeOptionId'] == hospital['routeOptionId']
        assert repeated['routeOptions'][0]['routeSnapshotVersion'] == hospital['routeSnapshotVersion']
        assert len(repeated['routeOptions']) <= 3
        assert len({p['routeOptionId'] for p in repeated['routeOptions']}) == len(repeated['routeOptions'])
        empty = search('reverseDirectionHasNoRoute', destination='001', origin='005')['data']
        assert empty['routeOptions'] == [] and isinstance(empty['routeSearchId'], str)
        search('unknownOrigin', origin='999', expected_status=404, expected_code='NOT_FOUND')
        search('unknownDestination', destination='999', expected_status=404, expected_code='NOT_FOUND')
        request('missingDepartureTime', 'POST', SEARCH_PATH, expected_status=400, expected_code='INVALID_REQUEST',
                json={'originStationId': 'demo-stop-001', 'destinationId': 'demo-destination-001'})
        search('timezoneMissing', payload_updates={'departAt': datetime.now().replace(tzinfo=None).isoformat()},
               expected_status=400, expected_code='INVALID_REQUEST')
        for label, delta in [('departureTooOld', -180), ('departureTooFarFuture', 180)]:
            search(label, payload_updates={'departAt': (datetime.now(timezone.utc) + timedelta(seconds=delta)).isoformat()},
                   expected_status=400, expected_code='INVALID_REQUEST')
        request('malformedJson', 'POST', SEARCH_PATH, expected_status=400, expected_code='INVALID_REQUEST',
                content='{')
        request('missingSearch', 'GET', SEARCH_PATH + '/not-registered/options/not-registered',
                expected_status=404, expected_code='NOT_FOUND')
        request('missingOption', 'GET', paths['hospital'].rsplit('/', 1)[0] + '/not-registered',
                expected_status=404, expected_code='NOT_FOUND')
        request('optionBelongsToDifferentPath', 'GET', paths['market'].rsplit('/', 1)[0] + '/' + option_ids['terminal'],
                expected_status=404, expected_code='NOT_FOUND')
        schema_response = client.get('/openapi.json')
        assert schema_response.status_code == 200
        schema = schema_response.json()
        search_operation = schema['paths'][SEARCH_PATH]['post']
        detail_operation = schema['paths'][SEARCH_PATH + '/{routeSearchId}/options/{routeOptionId}']['get']
        assert search_operation['requestBody']['required']
        assert schema['components']['schemas']['SearchRequest']['required'] == ['originStationId', 'destinationId', 'departAt']
        assert '400' in search_operation['responses'] and '422' not in search_operation['responses']
        assert [p['name'] for p in detail_operation['parameters']] == ['routeSearchId', 'routeOptionId']
        for origin in ORIGINS:
            for method, path in [('POST', SEARCH_PATH), ('GET', paths['hospital'])]:
                response = client.options(path, headers={'Origin': origin, 'Access-Control-Request-Method': method,
                                                         'Access-Control-Request-Headers': 'Content-Type'})
                assert response.status_code == 200 and response.headers['access-control-allow-origin'] == origin
    report = {'verifiedAt': datetime.now(timezone.utc).isoformat(), 'baseUrl': base_url, 'dataMode': 'demo',
              'notice': s.NOTICE, 'passedCases': len(records), 'openapiChecked': True, 'corsOrigins': list(ORIGINS),
              'frontendABBrowserChecked': False, 'selections': selections, 'cases': records}
    (ROOT / 'docs/stage4-http-examples.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Stage 4: {len(records)} real HTTP route search/detail cases + CORS/OpenAPI passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', help='Check an existing normal demo server using the agreed fixture')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve:
        import uvicorn
        from backend.main import create_app
        uvicorn.run(create_app(Settings(database_url='sqlite:///:memory:'), provider=DemoProvider()),
                    host='127.0.0.1', port=args.port)
        return
    if args.base_url:
        exercise(args.base_url)
        return
    base_url = f'http://127.0.0.1:{args.port}'
    folder = ROOT / '.local'
    folder.mkdir(exist_ok=True)
    # Refuse an occupied port instead of probing or stopping another server.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port))
    with (folder / 'stage4-server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'backend.tools.verify_stage4', '--serve', '--port', str(args.port)],
            cwd=ROOT.parent, stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            deadline = monotonic() + 15
            with httpx.Client(timeout=1, trust_env=False) as client:
                while True:
                    if process.poll() is not None:
                        raise RuntimeError('Server stopped; inspect backend/.local/stage4-server.log')
                    try:
                        if client.get(base_url + '/openapi.json').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if monotonic() >= deadline:
                        raise RuntimeError('Server startup timed out')
                    sleep(0.1)
            exercise(base_url)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    main()
