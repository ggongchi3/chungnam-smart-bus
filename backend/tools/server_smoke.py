"""Start a real Uvicorn child process, exercise HTTP, and stop only that child."""
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep

import httpx

from backend.config import ROOT
from backend.tools.request_examples import exercise


def main():
    folder = ROOT / '.local'
    folder.mkdir(exist_ok=True)
    log_path = folder / 'server-smoke.log'
    env = {**os.environ, 'BUS_DATA_MODE':'demo', 'BUS_DEMO_SCENARIO':'normal', 'PYTHONIOENCODING':'utf-8'}
    # An explicit scenario file, if present, takes priority. Do not overwrite it.
    scenario = folder / 'scenario.json'
    if scenario.exists() and json.loads(scenario.read_text(encoding='utf-8'))['scenario'] != 'normal':
        raise SystemExit('Select the normal scenario before running smoke tests')
    with log_path.open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000'],
            cwd=ROOT.parent, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            with httpx.Client(base_url='http://127.0.0.1:8000', timeout=1, trust_env=False) as client:
                deadline = monotonic() + 15
                while True:
                    if process.poll() is not None:
                        raise RuntimeError('Uvicorn exited; inspect backend/.local/server-smoke.log')
                    try:
                        response = client.get('/openapi.json')
                        if response.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if monotonic() >= deadline:
                        raise RuntimeError('Uvicorn startup timed out')
                    sleep(0.1)
                assert client.get('/docs').status_code == 200
                (ROOT / 'docs/openapi.json').write_text(json.dumps(response.json(),ensure_ascii=False,indent=2),encoding='utf-8')
            results = exercise('http://127.0.0.1:8000')
            (ROOT / 'docs/examples.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            print('Real Uvicorn 127.0.0.1:8000: /docs, OpenAPI, 8 APIs and error cases passed')
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    main()
