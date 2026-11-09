"""Verify all 8 public APIs with unconnected AI and consistent print snapshots."""
import argparse
from datetime import datetime, timezone
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
from backend.tools.verify_stage5 import Control, ControlledClock

SEARCH_PATH = '/api/v1/route-searches'
INTERPRET_PATH = '/api/v1/destination-interpretations'
GUIDANCE_PATH = '/api/v1/easy-guidance'
PRINT_PATH = '/api/v1/print-guides'


def exercise(base_url, control, *, output=None):
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
                value = s.Envelope[None].model_validate(body)
                assert value.data is None and value.error.code == expected_code
            shown_request = {'method': method, 'path': path}
            if 'json' in kwargs:
                shown_request['json'] = dict(kwargs['json'])
                if 'departAt' in shown_request['json']:
                    shown_request['json']['departAt'] = '<current controlled fixture time; generate current aware ISO time in real requests>'
            records.append({'name': name, 'fixture': dict(control.value), 'request': shown_request,
                            'httpStatus': response.status_code, 'elapsedMilliseconds': elapsed, 'response': body})
            return body

        def select(name):
            body = request(name, 'POST', SEARCH_PATH, json={
                'originStationId': 'demo-stop-001', 'destinationId': 'demo-destination-003',
                'departAt': control.now().isoformat()})
            found = s.Envelope[s.SearchData].model_validate(body).data
            assert found.routeOptions and found.routeOptions[0].transferCount == 1
            option = found.routeOptions[0]
            selected = {'routeSearchId': found.routeSearchId, 'routeOptionId': option.routeOptionId,
                        'expectedRouteSnapshotVersion': option.routeSnapshotVersion}
            path = f'{SEARCH_PATH}/{found.routeSearchId}/options/{option.routeOptionId}'
            return selected, path

        def printed(name, selected):
            body = request(name, 'POST', PRINT_PATH, json=selected)
            data = s.Envelope[s.PrintData].model_validate(body).data
            version = selected['expectedRouteSnapshotVersion']
            assert data.routeDetail.routeSnapshotVersion == data.liveInfoSnapshot.routeSnapshotVersion == version
            assert data.guidance.routeSnapshotVersion == version
            assert data.routeDetail.journeyStatus == 'ready'
            assert data.routeDetail.routeSearchId == selected['routeSearchId']
            assert data.routeDetail.routeOptionId == selected['routeOptionId']
            assert [p.segmentId for p in data.routeDetail.segments] == [p.segmentId for p in data.guidance.steps]
            assert data.guidance.mode == 'template_fallback'
            assert all(p.etaSeconds is None for p in data.liveInfoSnapshot.arrivals)
            assert s.NOTICE in data.notice and s.NOTICE in data.guidance.steps[0].text
            assert data.generatedAt == control.now()
            return data

        station = request('station', 'GET', '/api/v1/stations/demo-stop-001')
        assert s.Envelope[s.StationData].model_validate(station).data.station.stationId == 'demo-stop-001'
        destinations = request('destinations', 'GET', '/api/v1/destinations', params={'originStationId': 'demo-stop-001'})
        assert len(s.Envelope[s.DestinationData].model_validate(destinations).data.destinations) == 3
        selected, path = select('terminalRouteSearch')
        detail_body = request('terminalRouteDetail', 'GET', path)
        detail = s.Envelope[s.RouteDetail].model_validate(detail_body).data
        assert sum(p.stopCount for p in detail.segments if p.type == 'bus') == 4
        live_body = request('normalLive', 'GET', path + '/live')
        live = s.Envelope[s.LiveData].model_validate(live_body).data
        assert live.routeSnapshotVersion == detail.routeSnapshotVersion

        interpretation = request('unconnectedAIInterpretation', 'POST', INTERPRET_PATH,
                                 json={'originStationId': 'demo-stop-001', 'text': '큰 병원에 가고 싶어요'})
        interpretation_data = s.Envelope[s.InterpretationData].model_validate(interpretation).data
        assert interpretation_data.status == 'unavailable' and interpretation_data.candidates == []
        assert interpretation_data.reasonCode == 'AI_UNAVAILABLE'
        guidance_body = request('unconnectedAIFixedGuidance', 'POST', GUIDANCE_PATH, json=selected)
        guidance = s.Envelope[s.GuidanceData].model_validate(guidance_body).data
        assert guidance.mode == 'template_fallback' and guidance.routeSnapshotVersion == detail.routeSnapshotVersion
        assert [p.segmentId for p in guidance.steps] == [p.segmentId for p in detail.segments]
        assert s.NOTICE in guidance.steps[0].text
        assert '시연 1번' in guidance.steps[0].text and '2개 정류장' in guidance.steps[0].text
        first_print = printed('normalPrintSnapshot', selected)
        assert first_print.routeDetail == detail
        assert first_print.guidance == guidance
        before_print = first_print.model_dump(mode='json')

        for name, text in [('emptyText', ''), ('whitespaceText', '   '), ('tooLongText', '가' * 201), ('numericText', 7)]:
            request(name, 'POST', INTERPRET_PATH, 400, 'INVALID_REQUEST',
                    json={'originStationId': 'demo-stop-001', 'text': text})
        for name, text in [('oneCharacterText', '병'), ('twoHundredCharacterText', '가' * 200)]:
            body = request(name, 'POST', INTERPRET_PATH, json={'originStationId': 'demo-stop-001', 'text': text})
            assert body['data']['status'] == 'unavailable' and body['data']['candidates'] == []
        request('printExpectedVersionMismatch', 'POST', PRINT_PATH, 409, 'ROUTE_VERSION_CHANGED',
                json={**selected, 'expectedRouteSnapshotVersion': 'not-the-selected-version'})
        request('guidanceExpectedVersionMismatch', 'POST', GUIDANCE_PATH, 409, 'ROUTE_VERSION_CHANGED',
                json={**selected, 'expectedRouteSnapshotVersion': 'not-the-selected-version'})

        control.set(30, 'arrivals_missing')
        missing = printed('missingArrivalStillPrintsReadyRoute', selected)
        assert all(a.arrivalStatus == 'unavailable' and a.expectedArrivalAt is None and a.etaSeconds is None
                   for a in missing.liveInfoSnapshot.arrivals)
        assert missing.printGuideId != first_print.printGuideId
        assert first_print.model_dump(mode='json') == before_print
        control.set(40, 'changes_unknown')
        changes_unknown = printed('unknownChangesRemainUnknownInPrint', selected)
        assert changes_unknown.liveInfoSnapshot.serviceChanges.coverageStatus == 'unknown'
        assert changes_unknown.liveInfoSnapshot.serviceChanges.items == []
        control.set(50, 'source_missing')
        source_missing = printed('unknownSourceTimestampRemainsNullInPrint', selected)
        assert all(a.dataQuality.sourceUpdatedAt is None and a.dataQuality.freshness == 'unknown'
                   for a in source_missing.liveInfoSnapshot.arrivals)

        control.set(60, 'cancellation')
        request('cancelledRouteCannotPrint', 'POST', PRINT_PATH, 409, 'ROUTE_UNAVAILABLE', json=selected)
        request('cancelledRouteCannotProduceGuidance', 'POST', GUIDANCE_PATH, 409, 'ROUTE_UNAVAILABLE', json=selected)
        control.set(599, 'normal')
        printed('age599PrintStillValid', selected)
        control.set(600)
        request('age600PrintExpired', 'POST', PRINT_PATH, 410, 'ROUTE_SEARCH_EXPIRED', json=selected)
        request('age600GuidanceExpired', 'POST', GUIDANCE_PATH, 410, 'ROUTE_SEARCH_EXPIRED', json=selected)
        control.set(610, 'normal')
        core_selected, _ = select('coreDataBaselineSearch')
        control.set(611, 'core_unavailable')
        request('coreUnavailableCannotPrint', 'POST', PRINT_PATH, 503, 'TRANSPORT_DATA_UNAVAILABLE', json=core_selected)
        request('coreUnavailableCannotProduceGuidance', 'POST', GUIDANCE_PATH, 503, 'TRANSPORT_DATA_UNAVAILABLE', json=core_selected)
        request('expiredPrintPriorityOverCoreFailure', 'POST', PRINT_PATH, 410, 'ROUTE_SEARCH_EXPIRED', json=selected)

        schema = client.get('/openapi.json').json()
        assert sum(len(operations) for operations in schema['paths'].values()) == 8
        for endpoint in (INTERPRET_PATH, GUIDANCE_PATH, PRINT_PATH):
            operation = schema['paths'][endpoint]['post']
            assert operation['requestBody']['required'] and '422' not in operation['responses']
        for origin in ('http://localhost:5173', 'http://127.0.0.1:5173'):
            for endpoint in (INTERPRET_PATH, GUIDANCE_PATH, PRINT_PATH):
                response = client.options(endpoint, headers={'Origin': origin, 'Access-Control-Request-Method': 'POST',
                                                             'Access-Control-Request-Headers': 'Content-Type'})
                assert response.status_code == 200 and response.headers['access-control-allow-origin'] == origin
    report = {'verifiedAt': datetime.now(timezone.utc).isoformat(), 'baseUrl': base_url, 'dataMode': 'demo',
              'notice': s.NOTICE, 'passedCases': len(records), 'publicServiceAPIs': 8,
              'actualAIConnected': False, 'fakeAIAdapterUsed': False, 'controlledFixtureClock': True,
              'realTenMinuteWaitPerformed': False, 'runtimeDatabaseChanged': False,
              'frontendBBrowserChecked': False, 'physicalPrintSuccessChecked': False, 'cases': records}
    target = (output or ROOT / 'docs/stage6-http-examples.json').resolve()
    if not target.is_relative_to(ROOT):
        raise ValueError('Verification output must stay inside backend/')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Stage 6: {len(records)} real HTTP cases passed; all 8 public APIs, AI unconnected and print snapshots verified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Save verification JSON inside backend/')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--control-file', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve:
        if args.control_file is None or not args.control_file.resolve().is_relative_to((ROOT / '.local').resolve()):
            raise SystemExit('Fixture control file must be inside backend/.local/')
        import uvicorn
        from backend.main import create_app
        # No AI adapter is injected: these HTTP responses exercise actual unconnected behavior.
        app = create_app(Settings(database_url='sqlite:///:memory:'), clock=ControlledClock(args.control_file),
                         provider=DemoProvider(scenario_file=args.control_file))
        uvicorn.run(app, host='127.0.0.1', port=args.port)
        return
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port))
    folder = ROOT / '.local' / ('stage6-http-' + uuid4().hex)
    folder.mkdir(parents=True)
    control = Control(folder / 'control.json')
    base_url = f'http://127.0.0.1:{args.port}'
    with (folder / 'server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'backend.tools.verify_stage6', '--serve',
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
            exercise(base_url, control, output=args.output)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    main()
