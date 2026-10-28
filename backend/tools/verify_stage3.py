"""Run stage 3 GET examples against a real local server or --base-url."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep

import httpx

from backend.config import ROOT, Settings
from backend.integrations.providers import DemoProvider
from backend.models import schemas as s

BASE = {'originStationId': 'demo-stop-001'}


def exercise(base_url):
    records = []
    with httpx.Client(base_url=base_url, timeout=5, trust_env=False) as client:
        def check(name, path, params, expected_status, expected_ids=None, expected_code=None):
            started = monotonic()
            response = client.get(path,params=params,headers={'Origin':'http://localhost:5173'})
            elapsed = round((monotonic()-started)*1000,2)
            body = response.json()
            assert response.status_code == expected_status, (name,response.text)
            assert body['meta']['dataMode'] == 'demo'
            assert datetime.fromisoformat(body['meta']['generatedAt']).tzinfo is not None
            assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
            if expected_status != 200:
                s.Envelope[None].model_validate(body)
                assert body['data'] is None and body['error']['code'] == expected_code
            elif path.endswith('/destinations'):
                s.Envelope[s.DestinationData].model_validate(body)
                assert [d['destinationId'] for d in body['data']['destinations']] == expected_ids
            else:
                s.Envelope[s.StationData].model_validate(body)
                assert body['data']['station']['stationId'] == path.rsplit('/',1)[1]
                assert body['data']['station']['coordinates'] is None
                assert body['data']['station']['region'] is None
            records.append({'name':name,'request':{'method':'GET','path':path,'query':params},
                            'httpStatus':response.status_code,'elapsedMilliseconds':elapsed,'response':body})

        for number in range(1,6):
            check(f'station{number:03}',f'/api/v1/stations/demo-stop-{number:03}',{},200)
        all_ids = ['demo-destination-001','demo-destination-002','demo-destination-003']
        check('allDestinations','/api/v1/destinations',BASE,200,all_ids)
        for category,query,number in [('hospital','시연 큰 병원','001'),('market','시연 장터','002'),
                                      ('terminal','시연 버스터미널','003')]:
            check(category+'Alias','/api/v1/destinations',{**BASE,'query':' '+query+' '},200,['demo-destination-'+number])
            check(category+'Category','/api/v1/destinations',{**BASE,'category':category},200,['demo-destination-'+number])
        check('intersection','/api/v1/destinations',{**BASE,'query':'장터','category':'market'},200,['demo-destination-002'])
        check('emptyIntersection','/api/v1/destinations',{**BASE,'query':'장터','category':'hospital'},200,[])
        check('emptyResult','/api/v1/destinations',{**BASE,'query':'없는목적지'},200,[])
        check('trimmed100','/api/v1/destinations',{**BASE,'query':' '+'가'*100+' '},200,[])
        check('invalidLength','/api/v1/destinations',{**BASE,'query':'가'*101},400,expected_code='INVALID_REQUEST')
        check('invalidCategory','/api/v1/destinations',{**BASE,'category':'invalid'},400,expected_code='INVALID_REQUEST')
        check('missingOrigin','/api/v1/destinations',{},400,expected_code='INVALID_REQUEST')
        check('missingStation','/api/v1/stations/not-registered',{},404,expected_code='NOT_FOUND')
        check('unknownOrigin','/api/v1/destinations',{'originStationId':'not-registered'},404,expected_code='NOT_FOUND')
        schema = client.get('/openapi.json').json()
        parameters = {p['name']:p for p in schema['paths']['/api/v1/destinations']['get']['parameters']}
        assert parameters['originStationId']['required'] and parameters['query']['schema']['maxLength'] == 100
        assert '422' not in schema['paths']['/api/v1/destinations']['get']['responses']
        for origin in ('http://localhost:5173','http://127.0.0.1:5173'):
            result = client.options('/api/v1/destinations',headers={'Origin':origin,'Access-Control-Request-Method':'GET'})
            assert result.status_code == 200 and result.headers['access-control-allow-origin'] == origin
    output = ROOT / 'docs/stage3-http-examples.json'
    report = {'verifiedAt':datetime.now(timezone.utc).isoformat(),'baseUrl':base_url,'dataMode':'demo',
              'notice':s.NOTICE,'passedCases':len(records),'corsOrigins':['http://localhost:5173','http://127.0.0.1:5173'],
              'openapiChecked':True,'frontendABrowserChecked':False,'cases':records}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT / 'docs/openapi.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Stage 3: {len(records)} real HTTP GET cases + CORS/OpenAPI passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',help='Use an existing demo server; it must use the agreed fixture')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--serve',action='store_true',help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve:
        import uvicorn
        from backend.main import create_app
        app = create_app(Settings(database_url='sqlite:///:memory:'),provider=DemoProvider())
        uvicorn.run(app,host='127.0.0.1',port=args.port)
        return
    if args.base_url:
        exercise(args.base_url)
        return
    base_url = f'http://127.0.0.1:{args.port}'
    folder = ROOT / '.local'
    folder.mkdir(exist_ok=True)
    # Never inspect a preexisting server as if it were our child.
    import socket
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',args.port))
    with (folder/'stage3-server.log').open('w',encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable,'-m','backend.tools.verify_stage3','--serve','--port',str(args.port)],
            cwd=ROOT.parent,stdout=log,stderr=subprocess.STDOUT,
            env={**os.environ,'PYTHONIOENCODING':'utf-8'},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            deadline = monotonic()+15
            with httpx.Client(timeout=1,trust_env=False) as client:
                while True:
                    if process.poll() is not None:
                        raise RuntimeError('Server stopped; inspect backend/.local/stage3-server.log')
                    try:
                        if client.get(base_url+'/openapi.json').status_code == 200:
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
