# 2026-11-02 AI 연결·계약 정리와 코드 리뷰

AI 담당자의 전달사항에 따라 기본 서버 연결, 이유 코드, 오타 확인 정책과 Python 패키지 이름을 정리했다. 현재 체크아웃에는 AI 자리 표시자만 있어 `origin/ai/baseline`의 `baf4a58`에서 `ai/` 구현·계약·평가를 가져왔다. 해당 브랜치의 다른 영역 변경은 가져오지 않았다.

## 반영한 결정

- `backend.main:app`은 `create_app(ai_adapter=RuleBasedAIAdapter())`로 시작한다. 외부 모델·네트워크를 호출하지 않는 규칙 기반 모듈이다.
- 어댑터를 주입하지 않은 `create_app()`은 `unavailable` / `template_fallback`을 유지해 실패 대체를 독립 검증할 수 있다.
- `destination-interpretation`, `easy-guidance`를 `destination_interpretation`, `easy_guidance`로 전환하고 표준 상대 import를 사용한다. 공개 import 경로는 `ai.adapter.RuleBasedAIAdapter`다.
- 목적지 해석·안내 선택 알고리즘과 템플릿 카탈로그는 AI 브랜치 원본을 유지했다.
- 공개 이유 코드는 백엔드가 검증한 상태에서 결정한다. AI의 임의 이유 문자열은 노출하지 않는다. 공개 응답 스키마와 OpenAPI도 네 코드로 제한한다.

| status | 공개 reasonCode |
| --- | --- |
| matched | MATCHED |
| needs_confirmation | USER_CONFIRMATION_REQUIRED |
| no_match | NO_REGISTERED_MATCH |
| unavailable | AI_UNAVAILABLE |

오타 추정은 후보가 하나여도 `needs_confirmation`을 유지한다. `matched`도 사용자가 목적지를 확인하고 선택한다. 이전 `NO_MATCH`에 의존하는 클라이언트는 `NO_REGISTERED_MATCH`로 맞춰야 하며, 화면 분기는 `status`를 기준으로 한다.

## 검증 결과

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests ai/evaluation -q -p no:cacheprovider --basetemp=backend/.test-tmp/ai-integration-20261102 --junitxml=backend/.local/ai-integration-tests-20261102.xml
```

**344 passed**, 기존 Starlette/anyio 폐기 예정 경고 1개, 144.07초. 기존 백엔드 316개, 새 연결 회귀 13개, 가져온 AI 테스트 15개를 포함한다. Windows 샌드박스의 asyncio 로컬 socketpair 생성 제한을 확인해 권한이 허용된 실행에서 검증했다.

- AI 단독 단위 테스트 7개와 합성 평가 **59/59**도 통과했다. 합성 사례 통과 수는 실제 사용자 표현의 정확도가 아니다.
- 기본 `backend.main:app`을 실제 Uvicorn 자식 서버로 실행했다. 독립 메모리 SQLite·임시 로컬 포트에서 공개 API 8개 흐름, 400/404/409, 오타 후보와 후보 없음을 확인했다. OpenAPI 조회를 포함해 15개 검증 요청이 통과했다. 실행 DB와 공용 시연 상태는 바꾸지 않았다.
- `pip check`, `compileall`, `git diff --check`를 통과했다.
- 로컬 상세 결과는 `backend/.local/ai-integration-tests-20261102.xml`, `backend/.local/ai-integration-http-20261102.json`에 있다. `.local`은 Git 제외 경로다.

## 구현 후 코드 리뷰

별도 리뷰에서 기본 앱·팩터리 분리, 이유 코드 생성과 스키마, 단일 오타 후보, 표준 패키지 import, 실제 어댑터 회귀 테스트를 확인했다. 수정이 필요한 구체적인 결함은 발견하지 못했다.

현재 원본 모듈은 `templates.json`을 import 시 읽으므로 배포 시 `ai/easy_guidance/templates.json`을 포함해야 한다. AI 규칙의 제한된 표현 범위는 원본을 유지했다. 프론트 화면·음성·인쇄 미리보기와 실제 교통 API는 이번 API 검증 범위에 포함되지 않는다.
