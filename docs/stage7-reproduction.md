# 11/10 재현 절차와 남은 제출 환경 확인

작성일: 2026-11-09, Asia/Seoul. 아래 명령은 저장소 루트에서 실행한다. 현재 실행 가능한 부분은 합성 데이터 백엔드·SQLite·규칙 기반 AI·인쇄용 JSON이다. A/B 화면·실제 음성·브라우저 인쇄는 코드가 없어 실행할 수 없다. 로컬 API 주소를 최종 제출 URL로 간주하지 않는다.

## 런타임과 설치

현재 PC는 Windows, Python 3.13.2, SQLite 3.45.3이다. FastAPI 0.115.5, Uvicorn 0.32.0, Pydantic 2.9.2, SQLAlchemy 2.0.36, HTTPX 0.27.2, pytest 8.3.3 및 간접 의존성 21개를 [requirements.lock](../backend/requirements.lock)에 고정했다. 실제 새 환경 결과는 [환경 기록](../backend/docs/stage7-clean-environment.json)에 둔다. 다른 PC·OS의 실행 완료를 뜻하지 않는다.

새로 받은 저장소에서 PowerShell로 실행한다. 이미 존재하는 가상환경이나 DB를 삭제하지 않는다.

```powershell
python --version
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.lock
backend/.venv/Scripts/python -m pip check
```

이번 PC에서는 기존 환경을 보존하고 `backend/.local/stage7-clean-20261109`를 새로 생성했다. 실제 설치는 아래 방식으로도 확인했다. 기존 `.venv`를 복사하거나 시스템 패키지를 상속하지 않았다.

```powershell
python -m venv --without-pip backend/.local/stage7-clean-20261109
backend/.venv/Scripts/python -m pip --python backend/.local/stage7-clean-20261109/Scripts/python.exe install --disable-pip-version-check --retries 0 --timeout 15 -r backend/requirements.lock
```

이 경로는 이번 검증 산출물이다. 다른 실행에서는 충돌하지 않는 새 환경 이름을 사용한다. Windows 기본 샌드박스에서는 asyncio의 로컬 socketpair가 멈추는 제한을 확인했다. 허용된 로컬 소켓 실행에서 TestClient와 HTTP를 검증했다. 이 환경 제한을 앱 통과/실패와 혼동하지 않는다. 패키지 설치에는 패키지 서버 연결이 필요하다.

## 환경변수·DB·시작 순서

비밀값 없는 예시는 [backend/.env.example](../backend/.env.example)이다. `.env` 자동 로딩은 없으므로 현재 셸의 환경변수로 지정한다. 기본 코드에는 특정 PC의 사용자 경로가 없고 `__file__`을 기준으로 `.local/bus.sqlite3` 위치를 계산한다.

| 변수 | 값·주의 |
|---|---|
| `BUS_DATA_MODE` | `demo`; 실제 제공자가 없는 `live`는 503이며 demo로 조용히 대체하지 않음 |
| `BUS_DATABASE_URL` | SQLite 파일은 `backend/.local/` 안만 허용. 새 독립 DB 이름을 사용 |
| `BUS_DEMO_SCENARIO` | `normal`; `.local/scenario.json`이 존재하면 파일 값이 우선 |
| `BUS_CORS_ORIGINS` | 기본 `http://localhost:5173,http://127.0.0.1:5173`; 주소별 쉼표 구분 |

팀원의 **새 체크아웃**에서 다음 순서로 실행한다. 새 DB 파일 이름인지 먼저 확인하고 기존 파일에 reset/delete를 하지 않는다.

```powershell
$env:BUS_DATA_MODE = 'demo'
$env:BUS_DATABASE_URL = 'sqlite:///backend/.local/team-demo-20261110.sqlite3'
backend/.venv/Scripts/python -m backend.seed
backend/.venv/Scripts/python -m backend.seed
backend/.venv/Scripts/python -m backend.demo scenario --name normal
backend/.venv/Scripts/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

첫 seed는 정류장5·목적지3·별칭3·노선2·경유6·접근3·환승1, 두 번째는 inserted 모두0이며 totals가 같아야 한다. seed는 기존 행을 덮어쓰지 않는다. DB 생성은 SQLAlchemy `create_all`이다. 별도 마이그레이션 시스템은 없고 이번 변경에 스키마 변경도 없다. 임의로 기존 DB를 새 스키마로 자동 변환했다고 보고하지 않는다.

`backend.demo scenario`는 공용 `.local/scenario.json`을 바꾸므로 같은 체크아웃에서 실행 중인 서버 모두에 영향을 준다. 이번 자동/HTTP 검증은 이 명령을 공용 상태에 실행하지 않고 전용 제어 파일을 사용했다. 합성 원천 시각은 발행 후 고정되어 91초부터 stale이다. 정상 fresh 시연이 필요하면 시연 담당자가 normal을 다시 발행한다. polling으로 시각을 갱신하거나 실제 교통정보라고 설명하지 않는다.

서버 시작 시 같은 seed를 수행한다. AI는 `ai.adapter.RuleBasedAIAdapter`를 같은 Python 프로세스에 연결하므로 별도 AI 서버·외부 모델 키가 필요 없다. 외부 교통 제공기관·키·실데이터는 준비되지 않았다.

## API·테스트 실행

두 번째 터미널에서 다음을 사용한다. `departAt`은 현재 시각으로 생성되므로 과거 JSON의 고정 시각이나 검색 ID를 복사하지 않는다.

```powershell
backend/.venv/Scripts/python -m backend.tools.request_examples --base-url http://127.0.0.1:8000
backend/.venv/Scripts/python -m pytest backend/tests ai/evaluation -q --basetemp=backend/.test-tmp/team-stage7-20261110 -p no:cacheprovider --junitxml=backend/.local/team-stage7-results.xml
backend/.venv/Scripts/python -m backend.tools.verify_stage7 --port 18007 --output backend/.local/team-stage7-http.json
```

pytest의 임시 폴더에는 매 실행마다 새 이름을 사용한다. 테스트는 메모리 DB와 `.local/tests/`의 독립 파일 DB를 사용한다. 실제 대기로 만료 경계를 만들지 않고 시계·교통 제공자·AI 어댑터를 주입한다. HTTP 도구는 비어 있는 루프백 포트에 자식 서버를 만들고 종료한다. 18007이 사용 중이면 다른 빈 포트를 지정하며 기존 프로세스를 종료하지 않는다. 도구의 정상 실행 기본 시나리오에는 실제 규칙 AI가 연결되며 교통은 합성 제공자다. 제어 파일·서버 로그는 `.local/stage7-http-<UUID>/`에 있다. Windows 파일 잠금 재시도는 최대1초이며 가짜 시계의 경계값에는 영향을 주지 않는다.

기본 서버의 [Swagger](http://127.0.0.1:8000/docs), [OpenAPI](http://127.0.0.1:8000/openapi.json)는 문서 기능이다. 서비스 API 8개 목록은 [기능 연결표](stage7-feature-matrix.md)를 따른다. OpenAPI는 저장본과 구조적으로 같아야 하고 422 대신 400 공통 오류를 사용해야 한다.

## 프론트엔드·브라우저·제출 환경

프론트 패키지와 앱이 없어 npm 설치·개발 서버 실행 명령을 아직 제공할 수 없다. A가 단일 React/TypeScript/Vite 앱·잠금파일·API 타입을 준비한 뒤 `/api`를 `http://127.0.0.1:8000`으로 프록시하고 개발 포트5173을 사용한다. 이 설정은 요구사항이며 현재 구현된 프록시가 아니다. 직접 백엔드에 요청할 때 기본 허용 Origin 두 개를 사용한다. 공개 배포에서는 확정된 주소를 기준으로 프록시·CORS를 다시 확인한다.

다른 팀원 PC에서 다음 증거를 직접 남긴 후 보고서의 차단 항목을 해제한다.

1. 같은 코드 버전·Python/패키지 버전, 새 DB의 seed 두 번, 전체 pytest와 HTTP JSON.
2. 디자인의 목표 CSS 화면 크기·배율·화면/인쇄 시안과 합의 기록.
3. 목적지→후보→선택→상세→음성→인쇄까지 브라우저 화면·Network·서버 로그·응답의 ID/버전 대조.
4. Chrome/OS의 한국어 음성 목록, 사용자 재생·중지, 화면 이동 취소와 중복 재생 방지. 실제 스피커 청취 없이는 소리 통과로 표시하지 않음.
5. A4 세로/15mm/16pt 시작 기준으로 긴 안내의 페이지 분할·잘림·취소 후 재시도. 인쇄 DOM은 서버 스냅샷 고정 후 polling으로 갱신하지 않음.
6. 오류400/404/409/410/5xx·네트워크 끊김·연속 검색·중복 클릭·뒤로/새로고침의 화면 복구. stale/unknown/null을 정상/0분으로 표시하지 않음.
7. URL 제출 필수 여부와 최종 주소 확정 후 HTTPS·인증/프록시·CORS·실행 프로세스·직접 새로고침 접근 검증.

다른 PC·컨테이너·macOS/Linux·실제 기기·제출 호스팅은 이번 로컬 새 가상환경과 구분하여 미실행으로 남긴다. 이 문서 작성만으로 팀원에게 전달되거나 공동 확인된 것은 아니다.
