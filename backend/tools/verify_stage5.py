"""Reproduce live-data time boundaries through an isolated, controlled HTTP server."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from time import monotonic, sleep
from uuid import uuid4

import httpx

from backend.config import ROOT, Settings
from backend.integrations.providers import DemoProvider
from backend.models import schemas as s

SEARCH_PATH = '/api/v1/route-searches'


class ControlledClock:
    """Test-fixture clock; not installed in the normal service application."""
    def __init__(self, path):
        self.path = path

    def __call__(self):
        value = datetime.fromisoformat(json.loads(self.path.read_text(encoding='utf-8'))['now'])
        if value.tzinfo is None:
            raise ValueError('Controlled time must include a timezone')
        return value.astimezone(timezone.utc)


class Control:
    def __init__(self, path):
        self.path = path
        self.anchor = datetime.now(timezone.utc).replace(microsecond=0)
        self.revision = 0
        self.value = {}
        self.set(0, 'normal')

    def set(self, offset, scenario=None):
        if scenario is not None:
            self.revision += 1
            self.value.update(scenario=scenario, revision=str(self.revision))
        self.value['now'] = (self.anchor + timedelta(seconds=offset)).isoformat()
        pending = self.path.with_suffix('.tmp')
        pending.write_text(json.dumps(self.value), encoding='utf-8')
        pending.replace(self.path)

    def now(self):
        return datetime.fromisoformat(self.value['now'])


def exercise(base_url, control):
    records = []
    with httpx.Client(base_url=base_url, timeout=5, trust_env=False) as client:
        def request(name, method, path, expected_status=200, expected_code=None, **kwargs):
            started = monotonic()
            response = client.request(method, path, headers={'Origin': 'http://localhost:5173'}, **kwargs)
            elapsed = round((monotonic() - started) * 1000, 2)
            body = response.json()
            assert response.status_code == expected_status, (name, response.text)
            assert set(body) == {'data', 'error', 'meta'}
            assert body['meta']['dataMode'] == 'demo'
            assert datetime.fromisoformat(body['meta']['generatedAt']) == control.now()
            assert response.headers['x-request-id'] == body['meta']['requestId']
            assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
            if expected_status == 200:
                assert body['error'] is None
            else:
                s.Envelope[None].model_validate(body)
                assert body['data'] is None and body['error']['code'] == expected_code
            recorded_request = {'method': method, 'path': path}
            if 'json' in kwargs:
                recorded_request['json'] = dict(kwargs['json'])
                if 'departAt' in recorded_request['json']:
                    recorded_request['json']['departAt'] = '<current controlled fixture time; use current aware ISO time in real requests>'
            records.append({'name': name, 'fixture': dict(control.value), 'request': recorded_request,
                            'httpStatus': response.status_code, 'elapsedMilliseconds': elapsed, 'response': body})
            return body

        def select(name, origin='001'):
            body = request(name, 'POST', SEARCH_PATH, json={
                'originStationId': 'demo-stop-' + origin, 'destinationId': 'demo-destination-003',
                'departAt': control.now().isoformat()})
            data = s.Envelope[s.SearchData].model_validate(body).data
            assert data.routeOptions
            selected = data.routeOptions[0]
            return (f'{SEARCH_PATH}/{data.routeSearchId}/options/{selected.routeOptionId}',
                    selected.routeSnapshotVersion)

        def live(name, path, expected_version):
            body = request(name, 'GET', path + '/live')
            data = s.Envelope[s.LiveData].model_validate(body).data
            assert data.routeSnapshotVersion == expected_version
            assert data.arrivals
            return data

        selected_path, version = select('initialSearch')
        first = live('freshAge0', selected_path, version)
        assert all(a.arrivalStatus == 'available' and a.etaSeconds == 300 and a.dataQuality.freshness == 'fresh'
                   for a in first.arrivals)
        assert first.serviceChanges.coverageStatus == 'available' and first.serviceChanges.items == []
        initial_source = first.arrivals[0].dataQuality.sourceUpdatedAt
        assert initial_source == control.anchor

        control.set(30)
        after30 = live('etaAfter30SecondsVersionUnchanged', selected_path, version)
        assert all(a.etaSeconds == 270 and a.dataQuality.sourceUpdatedAt == initial_source for a in after30.arrivals)
        for age, expected in ((90, 'fresh'), (91, 'stale')):
            control.set(age)
            result = live(f'freshnessAge{age}', selected_path, version)
            assert all(a.dataQuality.freshness == expected and a.dataQuality.sourceUpdatedAt == initial_source
                       for a in result.arrivals)

        control.set(100, 'arrivals_missing')
        missing = live('arrivalsMissingDoesNotMeanCancellation', selected_path, version)
        assert all(a.arrivalStatus == 'unavailable' and a.etaSeconds is None and a.expectedArrivalAt is None
                   and a.operationStatus == 'unknown' for a in missing.arrivals)
        for offset, scenario, expected in ((110, 'source_missing', 'unknown'),
                                           (120, 'source_future', 'unknown'), (130, 'stale', 'stale')):
            control.set(offset, scenario)
            result = live(scenario, selected_path, version)
            assert all(a.dataQuality.freshness == expected for a in result.arrivals)
            if scenario == 'source_missing':
                assert all(a.dataQuality.sourceUpdatedAt is None for a in result.arrivals)
            elif scenario == 'source_future':
                assert all(a.dataQuality.sourceUpdatedAt > control.now() for a in result.arrivals)
        control.set(140, 'changes_unknown')
        unknown = live('changesQueryFailureRemainsUnknown', selected_path, version)
        assert unknown.serviceChanges.coverageStatus == 'unknown' and unknown.serviceChanges.items == []
        assert unknown.serviceChanges.dataQuality.freshness == 'unknown'

        control.set(150, 'operation_running')
        running = live('explicitRunningStatusKeepsRouteVersion', selected_path, version)
        assert any(a.routeId == 'demo-route-001' for a in running.arrivals)
        assert all(a.arrivalStatus == 'available' and
                   a.operationStatus == ('running' if a.routeId == 'demo-route-001' else 'unknown')
                   for a in running.arrivals)
        control.set(160, 'arrivals_missing_running')
        missing_running = live('missingArrivalCanStillHaveExplicitRunningStatus', selected_path, version)
        assert all(a.arrivalStatus == 'unavailable' and a.etaSeconds is None and a.expectedArrivalAt is None
                   and a.operationStatus == ('running' if a.routeId == 'demo-route-001' else 'unknown')
                   for a in missing_running.arrivals)
        control.set(170, 'operation_not_running')
        request('explicitNotRunningBlocksLive', 'GET', selected_path + '/live', 409, 'ROUTE_VERSION_CHANGED')
        request('explicitNotRunningBlocksDetail', 'GET', selected_path, 409, 'ROUTE_VERSION_CHANGED')

        control.set(599, 'normal')
        live('searchAge599StillValid', selected_path, version)
        control.set(600)
        request('searchAge600ExpiredLive', 'GET', selected_path + '/live', 410, 'ROUTE_SEARCH_EXPIRED')
        request('searchAge600ExpiredDetail', 'GET', selected_path, 410, 'ROUTE_SEARCH_EXPIRED')

        for index, scenario in enumerate(('cancellation', 'detour', 'timetable_change')):
            offset = 610 + index * 20
            control.set(offset, 'normal')
            path, before_version = select(scenario + 'BaselineSearch')
            unaffected_path, unaffected_version = select(scenario + 'UnaffectedRouteSearch', origin='003')
            control.set(offset + 1, scenario)
            request(scenario + 'RequiresReselectionLive', 'GET', path + '/live', 409, 'ROUTE_VERSION_CHANGED')
            request(scenario + 'RequiresReselectionDetail', 'GET', path, 409, 'ROUTE_VERSION_CHANGED')
            unaffected = live(scenario + 'UnaffectedRouteRemainsUsable', unaffected_path, unaffected_version)
            assert all(a.routeId == 'demo-route-002' for a in unaffected.arrivals)

        control.set(680, 'normal')
        core_path, core_version = select('coreDataBaselineSearch')
        control.set(681, 'core_unavailable')
        request('coreDataUnavailableIs503', 'GET', core_path + '/live', 503, 'TRANSPORT_DATA_UNAVAILABLE')
        request('expiryTakesPriorityOverUnavailableCore', 'GET', selected_path + '/live', 410, 'ROUTE_SEARCH_EXPIRED')
        request('missingSearchIs404', 'GET', SEARCH_PATH + '/missing/options/missing/live', 404, 'NOT_FOUND')
        schema = client.get('/openapi.json').json()
        assert sum(len(operations) for operations in schema['paths'].values()) == 8
        operation = schema['paths'][SEARCH_PATH + '/{routeSearchId}/options/{routeOptionId}/live']['get']
        assert {'200', '404', '409', '410', '503'}.issubset(operation['responses'])
    report = {'verifiedAt': datetime.now(timezone.utc).isoformat(), 'baseUrl': base_url, 'dataMode': 'demo',
              'notice': s.NOTICE, 'passedCases': len(records), 'openapiServiceCount': 8,
              'controlledFixtureClock': True, 'realTenMinuteWaitPerformed': False,
              'runtimeDatabaseChanged': False, 'frontendBBrowserChecked': False, 'cases': records}
    (ROOT / 'docs/stage5-http-examples.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Stage 5: {len(records)} real HTTP time/scenario cases passed; 8 service APIs unchanged')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--control-file', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve:
        if args.control_file is None or not args.control_file.resolve().is_relative_to((ROOT / '.local').resolve()):
            raise SystemExit('Fixture control file must be inside backend/.local/')
        import uvicorn
        from backend.main import create_app
        app = create_app(Settings(database_url='sqlite:///:memory:'), clock=ControlledClock(args.control_file),
                         provider=DemoProvider(scenario_file=args.control_file))
        uvicorn.run(app, host='127.0.0.1', port=args.port)
        return
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port))
    folder = ROOT / '.local' / ('stage5-http-' + uuid4().hex)
    folder.mkdir(parents=True)
    control = Control(folder / 'control.json')
    base_url = f'http://127.0.0.1:{args.port}'
    with (folder / 'server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'backend.tools.verify_stage5', '--serve',
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
                        raise RuntimeError('Fixture server startup timed out')
                    sleep(0.1)
            exercise(base_url, control)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    main()
