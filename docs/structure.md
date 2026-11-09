# 전체 저장소 구조와 폴더 목적

초기의 영역 구분을 유지하며 백엔드와 AI Python 구현을 추가했다. 2026-11-02 기준 기본 백엔드 앱에는 규칙 기반 AI 어댑터가 연결된다. 백엔드 실행 방법은 [backend/README.md](../backend/README.md), AI 계약·평가는 [ai/README.md](../ai/README.md)를 따른다. 5개 파트는 5명의 역할이며, 루트의 5개 영역과 일대일로 대응하는 뜻은 아니다. 프론트엔드는 하나의 앱이다.

## 주요 파일 트리

아래는 주요 소스와 남아 있는 자리 표시자를 나타낸다. 백엔드의 나머지 구현·테스트·검증 기록과 로컬 생성물은 생략했다. `temp`는 확장자 없는 일반 자리 표시자 파일이다.

```text
chungnam-smart-bus/
├── .gitignore
├── README.md
├── backend/
│   ├── README.md
│   ├── main.py
│   ├── api/
│   │   └── routes.py
│   ├── integrations/
│   │   ├── ai.py
│   │   └── providers.py
│   ├── models/
│   │   └── schemas.py
│   ├── services/
│   │   └── ai.py
│   ├── tests/
│   ├── tools/
│   │   └── verify_stage7.py
│   └── docs/
├── frontend/
│   ├── config/
│   │   └── temp
│   └── src/
│       ├── app/
│       │   └── temp
│       ├── features/
│       │   ├── destination-search/
│       │   │   └── temp
│       │   ├── journey-guide/
│       │   │   └── temp
│       │   ├── live-info/
│       │   │   └── temp
│       │   ├── print-guide/
│       │   │   └── temp
│       │   ├── route-selection/
│       │   │   └── temp
│       │   └── voice-guide/
│       │       └── temp
│       └── shared/
│           ├── api/
│           │   └── temp
│           └── ui/
│               └── temp
├── ai/
│   ├── README.md
│   ├── __init__.py
│   ├── adapter.py
│   ├── contracts/
│   │   ├── README.md
│   │   ├── schemas.json
│   │   └── fallback-copy.md
│   ├── destination_interpretation/
│   │   ├── README.md
│   │   └── interpreter.py
│   ├── easy_guidance/
│   │   ├── README.md
│   │   ├── selector.py
│   │   └── templates.json
│   └── evaluation/
│       ├── README.md
│       ├── __init__.py
│       ├── cases.json
│       ├── run_eval.py
│       ├── test_ai.py
│       ├── test_backend_integration.py
│       └── llm-experiment.md
├── design/
│   ├── assets/
│   │   └── temp
│   ├── guidelines/
│   │   └── temp
│   ├── kiosk-concept/
│   │   ├── temp
│   │   ├── 키오스크사이즈.png
│   │   ├── 키오스크사이즈2.png
│   │   └── 키오스크렌더링.jpg
│   ├── print-guide/
│   │   └── temp
│   ├── screens/
│   │   └── temp
│   └── wireframes/
│       └── temp
└── docs/
    ├── api-contract.md
    ├── data-sources.md
    ├── development-plan.md
    ├── roles.md
    ├── stage7-feature-matrix.md
    ├── stage7-integration-report.md
    ├── stage7-reproduction.md
    ├── structure.md
    └── verification.md
```

## 각 폴더의 용도와 대표 관리자

| 폴더 | 대표 관리자 | 용도 |
| --- | --- | --- |
| `backend/` | 백엔드 | 교통 데이터와 서비스 API의 단일 백엔드 영역 |
| `backend/api/` | 백엔드 | 요청 검증, 응답 변환, 서비스 API 진입점 |
| `backend/services/` | 백엔드 | 목적지 조회, 경로 계산/검증, 운행 정보 조합, AI 중계와 인쇄 스냅샷 준비 |
| `backend/models/` | 백엔드 | 정류장·목적지·노선·경유 순서·이동 구간과 공통 데이터 모델 |
| `backend/integrations/` | 백엔드 | 외부 제공자 어댑터, 내부 필드 매핑, 출처별 시간/실패 처리; 제공자 미정 |
| `frontend/` | 프론트엔드 A | A와 B가 기능별로 개발하는 하나의 React + TypeScript + Vite 앱 |
| `frontend/config/` | 프론트엔드 A | 선정 기술의 앱 설정과 시연 정류장 설정; 실제 키 저장 금지 |
| `frontend/src/` | 프론트엔드 A | 단일 앱의 진입·기능·공통 코드 구분 |
| `frontend/src/app/` | 프론트엔드 A | 앱 진입, 시작 화면, 현재 정류장, 화면 전환과 공통 화면 틀 |
| `frontend/src/features/` | 프론트엔드 A | 기능별 경계; 아래 각 기능의 대표 관리자는 개별 지정 |
| `frontend/src/features/destination-search/` | 프론트엔드 A | 목적지 검색, 주요 장소 선택, 후보 확인과 결과 없음 |
| `frontend/src/features/route-selection/` | 프론트엔드 A | 경로 목록·선택, 상세로 넘기는 식별자와 버전 |
| `frontend/src/features/journey-guide/` | 프론트엔드 B | 승차·하차·정류장 수·도보·환승 순서와 쉬운 안내 |
| `frontend/src/features/live-info/` | 프론트엔드 B | 도착·운행 현황·변경·항목별 갱신 시각·미수신/오래됨 상태 |
| `frontend/src/features/print-guide/` | 프론트엔드 B | 이동 안내표, 인쇄 레이아웃, 브라우저 인쇄/미리보기 |
| `frontend/src/features/voice-guide/` | 프론트엔드 B | 음성 안내 재생·중지·실패 UI; Web Speech API, 실제 한국어 음성 가용성 확인 필요 |
| `frontend/src/shared/` | 프론트엔드 A | 중복을 피할 공통 코드의 관리 경계 |
| `frontend/src/shared/ui/` | 프론트엔드 A | 공통 버튼·카드·오류/로딩 표시 등; 디자인 기준과 접근성 적용 |
| `frontend/src/shared/api/` | 프론트엔드 A | 단일 API 클라이언트, 공통 응답/오류 처리와 데이터 계약 반영 |
| `ai/` | AI | 규칙 기반 어댑터와 추가 제안 기능; 교통 사실 계산과 분리 |
| `ai/destination_interpretation/` | AI | 자연어 표현을 등록된 목적지 후보 ID에 연결 |
| `ai/easy_guidance/` | AI | 검증 구간에 맞는 쉬운 한국어 안내 템플릿·표현 선택 |
| `ai/contracts/` | AI | 목적지 후보·구간·허용 템플릿의 입출력 형식과 실패 상태 |
| `ai/evaluation/` | AI | 모호한 표현, 미등록 ID, 사실 보존, 버전 불일치, 실패 대체 평가 자료 |
| `design/` | 디자인 | 화면·출력물과 시각 기준의 원본 자료 |
| `design/wireframes/` | 디자인 | 사용자 흐름과 기능별 와이어프레임 |
| `design/screens/` | 디자인 | 시작·검색·선택·상세·실시간·실패 화면 시안 |
| `design/assets/` | 디자인 | 아이콘·이미지 및 출처·이용권한 기록 |
| `design/guidelines/` | 디자인 | 색상·글꼴·간격·컴포넌트·쉬운 문구·접근성 기준 |
| `design/print-guide/` | 디자인 | 종이 이동 안내표 디자인과 인쇄용 가독성 기준 |
| `design/kiosk-concept/` | 디자인 | 선택 확장인 외형 콘셉트; 실제 하드웨어 구현과 구분 |
| `docs/` | 백엔드 | 공통 기획·계약·협업·데이터 출처·구조·초기 검증 문서 |

`features/`의 상위 구조 대표는 A이며, B의 각 기능 내부 작업은 B가 담당한다. 디자인의 공통 기준은 디자인 담당자가 관리한다. 공통 API 계약은 백엔드가 관리하며, AI의 세부 계약은 AI 담당자가 관리한다. 협업 경계는 [roles.md](roles.md)를 따른다.

## 기본 문서

| 파일 | 내용 |
| --- | --- |
| `README.md` | 소개·핵심 기능·역할·폴더·개발 순서·자리 표시자 관리 |
| `.gitignore` | 의존성·빌드·캐시·로컬 설정·비밀정보 제외 규칙 |
| `docs/roles.md` | 정확히 5명 역할·입출력·공통 항목 대표 관리자·접근성 |
| `docs/api-contract.md` | 공개/내부 API 초안·A→B 데이터·AI 경계·실패 처리 |
| `docs/data-sources.md` | 사진 확인 범위·필요 데이터·출처/키/제공 범위 미확인 사항 |
| `docs/structure.md` | 주요 파일 트리·폴더 목적·관리자 |
| `docs/verification.md` | 이번 초기 생성 결과의 구조·문서·Git 제외 규칙 점검 기록 |

AI 모듈은 Python 표준 import를 위해 하이픈 없는 `destination_interpretation`, `easy_guidance` 이름을 사용한다. 공개 어댑터는 `from ai.adapter import RuleBasedAIAdapter`로 가져온다.

`backend/tools/verify_stage7.py`는 메모리 DB·주입 시각·전용 제어 파일로 로컬 HTTP를 검증하는 도구다. 운영 앱으로 실행하거나 제어 파일을 외부에 공개하지 않는다. `backend/tests/test_stage7_ai.py`, `test_stage7_contract.py`는 이번 계약 회귀 테스트다. `design/kiosk-concept/temp`는 기존 파일을 보존했으며 이미지 3개는 화면 시안이 아닌 외형 자료다.

아직 구현하지 않은 최하위 폴더에 남아 있는 `temp`의 내용은 다음 한 줄로 통일한다.

```text
Placeholder file. Remove after adding actual project files.
```

실제 작업 파일을 추가하면 해당 최하위 폴더의 `temp`를 삭제한다. 실제 파일이 있는 `docs/`나 하위 폴더만 있는 상위 폴더에는 `temp`를 추가하지 않는다. 후속 구조 변경 시 대표 관리자가 이 문서도 갱신한다.
