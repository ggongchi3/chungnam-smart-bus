"""Exercise the real rule-based AI and all eight APIs over isolated loopback HTTP.

This is a test fixture, never an application entry point for deployment. It uses
an in-memory database, a private scenario file and an injected clock. No public
test-control API is added and the configured runtime database is never opened.
"""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from time import monotonic, sleep
from uuid import uuid4

import httpx

from ai.adapter import RuleBasedAIAdapter
from backend.config import ROOT, Settings
from backend.integrations.providers import ArrivalObservation, DemoProvider
from backend.main import create_app
from backend.models import schemas as s
from backend.tools.verify_stage5 import Control, ControlledClock

SEARCH = '/api/v1/route-searches'
SELECTION_APIS = ('/api/v1/easy-guidance', '/api/v1/print-guides')
EXPECTED_APIS = {
    ('get', '/api/v1/stations/{stationId}'), ('get', '/api/v1/destinations'),
    ('post', SEARCH), ('get', SEARCH + '/{routeSearchId}/options/{routeOptionId}'),
    ('get', SEARCH + '/{routeSearchId}/options/{routeOptionId}/live'),
    ('post', '/api/v1/destination-interpretations'),
    *(('post', path) for path in SELECTION_APIS),
}


class PartialFixtureProvider(DemoProvider):
    def read(self, now):
        state = super().read(now)
        if json.loads(self.scenario_file.read_text(encoding='utf-8')).get('partialMissing'):
            observations = dict(state.arrivals)
            observations[('demo-route-002', 'demo-stop-003')] = ArrivalObservation(None)
            return replace(state, arrivals=observations)
        return state


def runtime_fingerprints():
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
            for name in ('bus.sqlite3', 'scenario.json') for path in [ROOT / '.local' / name]}


def exercise(base_url, control):
    records = []
    with httpx.Client(base_url=base_url, timeout=5, trust_env=False) as client:
        def call(name, method, path, status=200, code=None, **kwargs):
            started = monotonic()
            response = client.request(method, path, headers={'Origin': 'http://localhost:5173'}, **kwargs)
            body = response.json()
            assert response.status_code == status, (name, response.text)
            assert set(body) == {'data', 'error', 'meta'}, name
            assert response.headers['x-request-id'] == body['meta']['requestId']
            assert response.headers['cache-control'] == 'no-store'
            assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
            assert body['meta']['dataMode'] == 'demo'
            assert datetime.fromisoformat(body['meta']['generatedAt']) == control.now()
            if status == 200:
                assert body['error'] is None, name
            else:
                assert body['data'] is None and body['error']['code'] == code, (name, body)
            records.append({'name': name, 'fixture': dict(control.value),
                            'request': {'method': method, 'path': path, **kwargs},
                            'httpStatus': status, 'response': body,
                            'elapsedMilliseconds': round((monotonic() - started) * 1000, 2)})
            return body['data']

        def search(name, destination='001', origin='001', depart=None):
            data = call(name, 'POST', SEARCH, json={
                'originStationId': 'demo-stop-' + origin,
                'destinationId': 'demo-destination-' + destination,
                'departAt': depart or control.now().isoformat()})
            if not data['routeOptions']:
                return data, None, None
            option = data['routeOptions'][0]
            selected = {'routeSearchId': data['routeSearchId'], 'routeOptionId': option['routeOptionId'],
                        'expectedRouteSnapshotVersion': option['routeSnapshotVersion']}
            path = f"{SEARCH}/{selected['routeSearchId']}/options/{selected['routeOptionId']}"
            return data, selected, path

        def print_snapshot(name, selected, detail):
            data = call(name, 'POST', '/api/v1/print-guides', json=selected)
            s.PrintData.model_validate(data)
            assert data['routeDetail'] == detail
            assert data['liveInfoSnapshot']['routeSnapshotVersion'] == data['guidance']['routeSnapshotVersion'] == detail['routeSnapshotVersion']
            assert [p['segmentId'] for p in detail['segments']] == [p['segmentId'] for p in data['guidance']['steps']]
            assert all(a['etaSeconds'] is None for a in data['liveInfoSnapshot']['arrivals'])
            assert s.NOTICE in data['notice'] and s.NOTICE in data['guidance']['steps'][0]['text']
            return data

        call('station', 'GET', '/api/v1/stations/demo-stop-001')
        assert len(call('destinations', 'GET', '/api/v1/destinations', params={'originStationId': 'demo-stop-001'})['destinations']) == 3
        assert call('emptyDestinationResults', 'GET', '/api/v1/destinations', params={'originStationId': 'demo-stop-001', 'query': '없는장소'})['destinations'] == []
        call('unknownStation', 'GET', '/api/v1/stations/absent', 404, 'NOT_FOUND')
        call('invalidCategory', 'GET', '/api/v1/destinations', 400, 'INVALID_REQUEST', params={'originStationId': 'demo-stop-001', 'category': 'invalid'})
        call('invalidSearchBody', 'POST', SEARCH, 400, 'INVALID_REQUEST', json={})
        call('malformedJSON', 'POST', SEARCH, 400, 'INVALID_REQUEST', content='{')
        from datetime import timedelta
        for offset in (-121, -120, -119, 119, 120, 121):
            body = {'originStationId': 'demo-stop-001', 'destinationId': 'demo-destination-001',
                    'departAt': (control.now() + timedelta(seconds=offset)).isoformat()}
            call(f'departAt{offset:+}', 'POST', SEARCH, 400 if abs(offset) > 120 else 200,
                 'INVALID_REQUEST' if abs(offset) > 120 else None, json=body)
        assert search('reverseRouteExcluded', origin='005')[0]['routeOptions'] == []

        for destination, expected_transfers in (('001', 0), ('003', 1)):
            data, selected, path = search('directSearch' if destination == '001' else 'transferSearch', destination)
            assert data['routeOptions'][0]['transferCount'] == expected_transfers
            assert data['routeOptions'][0]['totalDurationSeconds'] is None
            detail = call('detail' + destination, 'GET', path)
            s.RouteDetail.model_validate(detail)
            guidance = call('actualRuleGuidance' + destination, 'POST', '/api/v1/easy-guidance', json=selected)
            assert guidance['mode'] == 'ai_assisted'
            assert guidance['routeSnapshotVersion'] == detail['routeSnapshotVersion']
            assert [p['segmentId'] for p in guidance['steps']] == [p['segmentId'] for p in detail['segments']]
            printed = print_snapshot('print' + destination, selected, detail)
            assert printed['guidance']['steps'] == guidance['steps']

        for text, expected in (('큰 병원에 가고 싶어요', 'matched'), ('없는장소', 'no_match')):
            result = call('actualRuleInterpretation' + expected, 'POST', '/api/v1/destination-interpretations',
                          json={'originStationId': 'demo-stop-001', 'text': text})
            assert result['status'] == expected
        call('invalidAIInput', 'POST', '/api/v1/destination-interpretations', 400, 'INVALID_REQUEST',
             json={'originStationId': 'demo-stop-001', 'text': 7})
        call('missingSelection', 'GET', SEARCH + '/missing/options/missing', 404, 'NOT_FOUND')
        for endpoint in SELECTION_APIS:
            call('expectedVersionMismatch' + endpoint, 'POST', endpoint, 409, 'ROUTE_VERSION_CHANGED',
                 json={**selected, 'expectedRouteSnapshotVersion': 'old-version'})

        for age, freshness in ((0, 'fresh'), (89, 'fresh'), (90, 'fresh'), (91, 'stale')):
            control.set(age)
            live = call('freshness' + str(age), 'GET', path + '/live')
            assert all(a['dataQuality']['freshness'] == freshness for a in live['arrivals'])
        fixed_before = json.dumps(printed, sort_keys=True)
        control.value['partialMissing'] = True
        control.set(92)
        partial = call('partialArrivalFailure', 'GET', path + '/live')
        assert [a['arrivalStatus'] for a in partial['arrivals']] == ['available', 'unavailable']
        assert partial['arrivals'][1]['expectedArrivalAt'] is None and partial['arrivals'][1]['etaSeconds'] is None
        assert partial['arrivals'][1]['operationStatus'] == 'unknown'
        assert partial['arrivals'][1]['dataQuality']['sourceUpdatedAt'] is None
        partial_print = print_snapshot('partialFailurePrint', selected, detail)
        assert '확인할 수 없습니다' in partial_print['notice']
        assert json.dumps(printed, sort_keys=True) == fixed_before
        control.value['partialMissing'] = False
        for offset, scenario, freshness in ((100, 'source_missing', 'unknown'), (110, 'source_future', 'unknown')):
            control.set(offset, scenario)
            live = call(scenario, 'GET', path + '/live')
            assert all(a['dataQuality']['freshness'] == freshness for a in live['arrivals'])
        control.set(120, 'changes_unknown')
        assert call('changesUnknown', 'GET', path + '/live')['serviceChanges']['coverageStatus'] == 'unknown'
        control.set(130, 'cancellation')
        for suffix in ('', '/live'):
            call('unavailable' + suffix, 'GET', path + suffix, 409, 'ROUTE_UNAVAILABLE')
        for endpoint in SELECTION_APIS:
            call('unavailable' + endpoint, 'POST', endpoint, 409, 'ROUTE_UNAVAILABLE', json=selected)
        control.set(140, 'detour')
        call('detourUnavailable', 'GET', path, 409, 'ROUTE_UNAVAILABLE')
        control.set(150, 'timetable_change')
        call('routeVersionChanged', 'GET', path, 409, 'ROUTE_VERSION_CHANGED')
        control.set(599, 'normal')
        call('age599Valid', 'GET', path)
        for age in (600, 601):
            control.set(age)
            for suffix in ('', '/live'):
                call(f'age{age}' + suffix, 'GET', path + suffix, 410, 'ROUTE_SEARCH_EXPIRED')
            for endpoint in SELECTION_APIS:
                call(f'age{age}' + endpoint, 'POST', endpoint, 410, 'ROUTE_SEARCH_EXPIRED', json=selected)
        control.set(610, 'normal')
        _, core_selected, core_path = search('coreFailureBaseline')
        control.set(611, 'core_unavailable')
        call('coreFailure', 'GET', core_path, 503, 'TRANSPORT_DATA_UNAVAILABLE')
        call('expiryBeforeCoreFailure', 'GET', path, 410, 'ROUTE_SEARCH_EXPIRED')
        assert json.dumps(printed, sort_keys=True) == fixed_before

        schema = client.get('/openapi.json').json()
        actual_apis = {(method, endpoint) for endpoint, operations in schema['paths'].items()
                       for method in operations if method in ('get', 'post', 'put', 'patch', 'delete')}
        assert actual_apis == EXPECTED_APIS
        assert schema == json.loads((ROOT / 'docs/openapi.json').read_text(encoding='utf-8'))
        assert all('422' not in op['responses'] for ops in schema['paths'].values() for op in ops.values())
        for origin in ('http://localhost:5173', 'http://127.0.0.1:5173', 'https://example.invalid'):
            response = client.options('/api/v1/print-guides', headers={
                'Origin': origin, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'Content-Type'})
            assert response.status_code == (400 if origin.endswith('.invalid') else 200)
            assert response.headers.get('access-control-allow-origin') == (None if origin.endswith('.invalid') else origin)
    return {'verifiedAt': datetime.now(timezone.utc).isoformat(), 'passedCases': len(records),
            'publicServiceAPIs': [f'{m.upper()} {p}' for m, p in sorted(actual_apis)],
            'actualAI': 'ai.adapter.RuleBasedAIAdapter (rules; no external model)',
            'transportProvider': 'synthetic DemoProvider; one controlled partial failure',
            'testDatabase': 'sqlite:///:memory:', 'controlledFixtureClock': True,
            'browserChecked': False, 'audioHeard': False, 'printPreviewChecked': False,
            'otherComputerChecked': False, 'submissionURLChecked': False, 'cases': records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/stage7-http-results.json')
    parser.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--control-file', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve:
        if args.control_file is None or not args.control_file.resolve().is_relative_to((ROOT / '.local').resolve()):
            raise SystemExit('Fixture control must be inside backend/.local/')
        import uvicorn
        app = create_app(Settings(database_url='sqlite:///:memory:'), clock=ControlledClock(args.control_file),
                         provider=PartialFixtureProvider(scenario_file=args.control_file), ai_adapter=RuleBasedAIAdapter())
        uvicorn.run(app, host='127.0.0.1', port=args.port)
        return
    target = args.output.resolve()
    if not target.is_relative_to(ROOT):
        raise SystemExit('Output must stay inside backend/')
    before = runtime_fingerprints()
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port))  # Never terminate a pre-existing server.
    folder = ROOT / '.local' / ('stage7-http-' + uuid4().hex)
    folder.mkdir(parents=True)
    control = Control(folder / 'control.json')
    base_url = f'http://127.0.0.1:{args.port}'
    with (folder / 'server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'backend.tools.verify_stage7', '--serve',
                                    '--port', str(args.port), '--control-file', str(control.path)],
                                  cwd=ROOT.parent, stdout=log, stderr=subprocess.STDOUT,
                                  env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            deadline = monotonic() + 15
            with httpx.Client(timeout=1, trust_env=False) as client:
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(f'Server stopped; inspect {folder / "server.log"}')
                    try:
                        if client.get(base_url + '/openapi.json').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if monotonic() >= deadline:
                        raise RuntimeError('Fixture startup timed out')
                    sleep(0.1)  # Startup polling only; time boundaries use Control.
            report = exercise(base_url, control)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    after = runtime_fingerprints()
    assert before == after, 'Configured runtime files changed during verification'
    report.update(baseUrl=base_url, runtimeFilesUnchanged=True, runtimeFileHashes=after,
                  serverLog=str((folder / 'server.log').relative_to(ROOT.parent)))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Stage 7: {report['passedCases']} HTTP cases passed; eight APIs + actual rule AI; runtime files unchanged")


if __name__ == '__main__':
    main()
