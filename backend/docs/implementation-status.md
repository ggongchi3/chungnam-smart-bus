# 백엔드 구현·검증 상태

작업일: 2026-10-26, Asia/Seoul. 작업 루트: `C:/Users/LG/OneDrive/Desktop/chungnam-smart-bus`. 시작 상태: `main`, 추적/미추적 변경 없음. 로컬 작업 브랜치: `codex/backend-implementation`. 커밋·태그·push·PR·이슈·배포는 수행하지 않았다.

## 자료 확인

HWP 5 OLE의 FileHeader와 BodyText/Section0을 직접 읽어 압축 해제하고 전체 문단/표의 텍스트를 추출했다. 추출본은 `source-plan.txt`, 재현 도구는 `../tools/extract_hwp.py`다. 요약 미리보기(PrvText)에 의존하지 않았다. 루트 README·.gitignore·공통 docs 5개를 모두 읽었으며, `docs/development-plan.md`는 존재하지 않았다. 적용할 AGENTS.md는 발견되지 않았다. 전체 파일 검색으로 frontend/ai/design은 자리 표시자뿐임을 확인했다. 다른 파트의 실제 계약·타입·실행 코드·공통 데이터 파일은 없었다.

HWP의 과거 '계획서 작성만'이라는 문구와 발표/리허설 일정은 이번 구현 범위를 제한하거나 확장하지 않는다. 이번 명시적 사용자 요청을 우선 적용했다. 기존 문서의 미정 정책과 사용자 요청의 확정 경계는 충돌로 보지 않고 구체화했다. 기존 API와 병원 예시 ID를 보존했으며, 누락된 데이터 세부는 HWP의 수량·명시적 환승·기대 경로 결과에 맞췄다. 공통 문서 반영 제안은 `coordination-notes.md`에 남겼다.

## 단계별 결과

| 단계 | 백엔드 독립 작업 | 검증 결과 / 공동 작업 |
| --- | --- | --- |
| 1 환경·앱·공통 응답 | 완료. FastAPI 라우터, Pydantic 응답, 공통 예외, 설정, 5173 로컬 CORS | /docs·404 봉투·400 검증·OpenAPI 확인. 실제 브라우저 시각 점검 대기 |
| 2 DB·초기 데이터·제공자 | 완료. ORM/API 모델 분리, SQLite 외래키, 트랜잭션, insert-only 적재 | 두 번 적재 후 5/2/3/6/1, 잘못된 외래키·복합 참조 거부·롤백 확인 |
| 3 정류장·목적지 | 완료. 이름/별칭/분류 교집합 검색 | 실제 HTTP와 TestClient 정상·빈 결과·400·404 확인. A 화면 연결 대기 |
| 4 경로·스냅샷 | 완료. 정방향·명시 환승·정렬·최대 3개, DB 검색 스냅샷 | 시장 1, 병원 2, 터미널 환승 4; 역방향/미등록 환승 제외, 순번별 반복 방문·동점 키 확인 |
| 5 도착·운행 변경·시간 | 완료. 합성 제공자, 10개 시나리오, 만료·버전·부분 실패 | 0/90/91초와 미래/없음, 599/600초, 경로/운행 변경 409, 핵심 자료 503 확인 |
| 6 AI·안내·인쇄 | 완료. 주입 어댑터, 출력 검증, 1초 대체, 고정 인쇄 스냅샷 | AI 없음/오류/잘못된 출력/시간초과·작업 누적 방지·복구, 사실 삽입·버전/구간 일관성 확인. 실제 AI 모듈 연결 대기 |
| 7 테스트·연동 | 백엔드 완료, 공동 검증 대기 | 최종 **65 passed**, 경고 1개, 22.59초. 실제 Uvicorn 8개 API HTTP smoke 통과 |
| 8 수정·실행 문서·인수인계 | 백엔드 완료, 타 PC 검증 대기 | 버전 잠금 재설치·pip check·seed·시나리오 CLI·서버/테스트 안내, 범위 감사. 커밋/태그는 이번 요청 제외 |

최종 테스트 결과는 `test-results.xml`, 실제 런타임은 `runtime-versions.json`, 실제 HTTP 응답은 `examples.json`, 생성 명세는 `openapi.json`이다. 의존성 경고는 Starlette TestClient가 사용하는 anyio BlockingPortal 별칭의 폐기 예정 알림 1개이며 테스트 실패는 없다.

## 실제 변경 파일과 책임

| 파일 | 역할 |
| --- | --- |
| `backend/main.py`, `config.py`, `.env.example`, `__init__.py` | 앱 생성·lifespan·설정·주입 경계·기본 오류 및 OpenAPI |
| `backend/api/{routes,errors,__init__}.py` | API 8개, 요청/응답 변환, 공통 서비스 오류 |
| `backend/models/{tables,schemas,__init__}.py` | SQLAlchemy 저장 모델과 Pydantic 외부/AI 모델 분리 |
| `backend/database.py`, `seed.py` | SQLite 경로 제한·세션·외래키·원자적 초기 적재 |
| `backend/services/{catalog,routing,journeys,time,ai,__init__}.py` | 검색, 방향/환승 계산, 버전/만료, 최신성, AI 검증/사실 바인딩, 출력 준비 |
| `backend/integrations/{providers,ai,__init__}.py`, `demo-data.json` | 교통/AI 경계, 합성 시나리오·데이터. 실제 제공자/AI 구현 아님 |
| `backend/demo.py` | 로컬 시연 상태 CLI. 외부 관리 API 없음 |
| `backend/tests/conftest.py`, `test_backend.py` | 시각·DB·제공자·AI 주입과 65개 정상/실패/경계 테스트 |
| `backend/tools/{extract_hwp,request_examples,server_smoke,audit_workspace}.py` | HWP 추출, 동적 요청 예시, 실제 서버 검증, 변경 범위 감사 |
| `backend/{requirements.txt,requirements.lock,.gitignore,README.md}` | 직접/전체 의존성 고정, 로컬 산출물 제외, 설치·실행 안내 |
| `backend/docs/`의 md/txt/json/xml | 계획 추출·협업·구현 상태·버전·명세·응답·테스트·범위 증거 |
| `backend/{api,models,services,integrations}/temp` | 실제 코드를 추가한 네 폴더에서만 삭제 |

세부 전체 목록과 최종 추적/새 파일 수는 `workspace-audit.json`에 있다. backend 밖의 자리 표시자 20개는 보존했다.

## 설계 선택과 계약 적용

- SQLite 시간 저장은 UTC epoch 초이며 JSON API는 aware ISO 8601이다. DB 검색 JSON은 저장 전/읽은 후 Pydantic으로 검사한다. 스냅샷은 서버 재시작 후에도 동일 식별자로 조회할 수 있다.
- 직접 경로·환승 후보는 노선과 승하차 **순번**으로 계산한다. 같은 이름·좌표·정류장 ID만으로 환승을 만들지 않는다. 미확인 거리·소요시간·좌표·지역은 null이다. 순번이 비연속이어도 실제 경유 행 수로 stopCount를 계산한다.
- SHA-256 기반 경로 버전은 경유 구조·선택 구간·사용 환승 근거·현재 경로 관련 변경과 상태를 포함한다. ETA·단순 원천 갱신/수집 시각은 포함하지 않는다. 저장 경로가 달라지면 재검색하도록 기존 409 ROUTE_VERSION_CHANGED를 사용한다.
- 만료는 now >= expiresAt. 검색 없음 → 만료 → 옵션 없음 → 핵심 자료 → 경로/상태/기대 버전 순으로 오류를 고정했다. unavailable 전용 새 코드는 도입하지 않았다.
- 데모 원천 시각은 시나리오 발행 시 고정한다. polling/generatedAt으로 fresh를 만들지 않는다. 미수신 arrival은 unavailable/operationStatus unknown이며 변경 조회 실패는 coverageStatus unknown이다. live 기본 제공자는 핵심 자료를 제공하지 않아 503이며 demo를 섞지 않는다.
- AI에는 허용 목적지 또는 구간 ID·타입·허용 템플릿만 전달한다. ID 부분집합·중복·상태, 안내 버전·정확한 순서/개수/템플릿을 검사한다. AI의 자유 사실·이유 문구는 채택하지 않는다. 기본 고정 문구는 서비스의 사실 바인딩이며 AI 선택 모듈을 대리 구현한 것이 아니다.
- AI 결과는 출력 검증까지 포함해 1초 이내만 채택한다. 프로세스당 1개 동기 worker/대기열 없음이며 초과 요청은 바로 대체한다. 시간초과 이후 작업을 강제 중단한 것으로 표시하지 않는다. 작업이 끝나면 슬롯이 복구됨을 테스트했다.
- 인쇄는 상태/만료/버전을 다시 검사한 한 시점의 복사본이다. 모든 구간과 안내 버전이 같으며 ETA 카운트다운 값은 null이다. ready 경로는 도착 미수신이어도 notice와 함께 준비할 수 있다. 출력 성공은 판정하지 않는다.

## 실행한 명령·증거

프로젝트 루트에서 다음을 실제 수행했다. 설치의 첫 일반 실행은 DNS/ensurepip 제한으로 실패했으며 성공으로 기록하지 않는다. 권한이 허용된 실행에서 빈 venv에 고정 직접 의존성을 설치하고 pip를 복구했다. API TestClient도 기본 샌드박스의 asyncio socketpair가 멈추는 것을 traceback으로 확인한 뒤 권한이 허용된 실행에서 검증했다.

```text
git status --short / git branch --show-current / git rev-parse --show-toplevel
git switch -c codex/backend-implementation
python backend/tools/extract_hwp.py <사용자 Downloads의 HWP> backend/docs/source-plan.txt
python -m venv backend/.venv                          # ensurepip 단계 실패, 빈 venv 생성됨
python -m pip --python backend/.venv/Scripts/python.exe install --no-cache-dir --retries 0 fastapi==0.115.5 uvicorn==0.32.0 pydantic==2.9.2 SQLAlchemy==2.0.36 httpx==0.27.2 pytest==8.3.3
backend/.venv/Scripts/python -m ensurepip --upgrade    # TEMP/TMP를 backend/.local로 설정 후 성공
backend/.venv/Scripts/python -m pip freeze            # requirements.lock 기록
backend/.venv/Scripts/python -m pip install -r backend/requirements.lock
backend/.venv/Scripts/python -m pip check             # No broken requirements found
backend/.venv/Scripts/python -m backend.seed          # 두 번 실행, 수량 유지
backend/.venv/Scripts/python -m backend.demo scenario --name stale
backend/.venv/Scripts/python -m backend.demo scenario --name normal
backend/.venv/Scripts/python -m pytest backend/tests -q --basetemp=backend/.test-tmp -p no:cacheprovider --junitxml=backend/docs/test-results.xml
backend/.venv/Scripts/python -m backend.tools.server_smoke
backend/.venv/Scripts/python -m backend.tools.audit_workspace
git check-ignore <실행 DB/저널/테스트 DB/venv/환경 예시/잠금/합성 JSON>
git diff --check / git diff --name-status / git ls-files --others --exclude-standard
```

`server_smoke`가 실제 실행한 서버 명령은 `backend/.venv/Scripts/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`이다. 테스트 후 해당 서버·멈춘 자체 진단 프로세스는 종료했다. 실행 DB는 삭제하지 않았다.

## 남은 제약과 인수인계

| 항목 | 상태·후속 담당 |
| --- | --- |
| A/B 실제 검색→상세 화면 | 대기. 현재 frontend는 temp뿐. 6개 선택 필드·OpenAPI·동적 요청 도구 전달 |
| 실제 AI 함수·공통 Python | 대기. 현재 ai는 temp뿐. AI 담당의 함수 공개 후 AIAdapter 주입·공동 검증 필요 |
| 음성 재생·브라우저 인쇄·종이 결과 | 미수행. B/디자인 담당 범위. API 안내문·인쇄 JSON만 검증 |
| 다른 팀원 PC·macOS/Linux | 미수행. README 명령은 제공했으며 해당 OS 검증 완료로 표시하지 않음 |
| 실제 충남 교통 API | 미연결. 제공기관·키·지원 범위·이용 조건 계속 미확인 |
| 서로 다른 정류장 사이 도보 환승·다회 환승 | 초기 범위 제외. 명시 자료 없는 연결 생성 안 함 |
| 실행 데이터 교체·마이그레이션·운영 배포 | 초기 시연 범위 제외. 현재 seed는 기존 값 보존; 새 DB 파일로 독립 시연 가능 |
| 영구 중단된 AI 함수 | 단일 슬롯으로 작업 누적 방지. 함수 강제 종료는 불가; 자체 취소 기능 또는 프로세스 재시작 필요 |

부하/다중 worker/실제 외부 네트워크 장애 시험·브라우저 시각/접근성 검수는 수행하지 않았다. 전체 서비스 연동 완료가 아니라 **백엔드 독립 구현 및 검증 완료** 상태다.

## 변경 범위와 산출물

`workspace-baseline.json`에 backend 밖 27개 파일의 초기 SHA-256을 기록했고 `workspace-audit.json`으로 최종 비교한다. backend 밖 파일 생성·변경·삭제가 없어야 감사가 통과한다. 기존 다른 사람의 변경은 시작 시 없었으며 이후 외부 변경도 발견되지 않았다.

추적 파일 변경은 backend의 temp 4개 삭제뿐이며 소스·설정·문서·검증 기록은 새 파일이다. `.venv/`, `__pycache__/`, `.local/`의 실행 DB·테스트 DB·시나리오·서버 로그는 생성했으나 Git 제외다. 일반 캐시 규칙을 존중했으며 의존성 잠금·합성 초기 데이터·.env.example은 제외되지 않는다. Git 메타데이터의 로컬 브랜치 생성 외에 원격 변경은 없다.
