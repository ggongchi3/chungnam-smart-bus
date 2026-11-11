"""검증된 경로 구간에 맞는 안내 템플릿 선택 기준선.

백엔드가 준 구간 순서를 그대로 유지하고 구간마다 allowedTemplateIds 안의 active
템플릿 하나만 고른다. 구간·정류장·노선·시간을 추가하거나 바꾸지 않는다.
입력이 계약과 다르면 unavailable을 반환하고 백엔드가 고정 템플릿으로 대체한다.
"""
import json
from pathlib import Path

CATALOG_PATH = Path(__file__).with_name('templates.json')
SEGMENT_TYPES = ('bus', 'walk', 'transfer')
DATA_MODES = ('demo', 'live', 'static')


def load_active(path=CATALOG_PATH):
    """구간 유형별 active 템플릿 ID 목록(카탈로그 순서가 우선순위)."""
    catalog = json.loads(Path(path).read_text(encoding='utf-8'))
    active = {kind: [] for kind in SEGMENT_TYPES}
    for item in catalog['templates']:
        if item.get('status') == 'active' and item.get('segmentType') in active:
            active[item['segmentType']].append(item['templateId'])
    return active


ACTIVE = load_active()


def unavailable(version):
    return {'status': 'unavailable', 'routeSnapshotVersion': version if type(version) is str else '', 'steps': []}


def choose(payload, active=None):
    active = ACTIVE if active is None else active
    version = payload.get('routeSnapshotVersion') if type(payload) is dict else None
    try:
        segments = payload.get('verifiedSegments')
        if (type(version) is not str or not version or payload.get('dataMode') not in DATA_MODES or
                type(segments) is not list or not segments):
            return unavailable(version)
        steps, seen = [], set()
        for segment in segments:
            if type(segment) is not dict:
                return unavailable(version)
            key, kind, allowed = segment.get('segmentId'), segment.get('type'), segment.get('allowedTemplateIds')
            if type(key) is not str or not key or key in seen or kind not in SEGMENT_TYPES:
                return unavailable(version)
            if type(allowed) is not list or any(type(t) is not str for t in allowed):
                return unavailable(version)
            choice = next((t for t in active[kind] if t in allowed), None)
            if choice is None:
                return unavailable(version)
            seen.add(key)
            steps.append({'segmentId': key, 'templateId': choice})
        return {'status': 'ok', 'routeSnapshotVersion': version, 'steps': steps}
    except Exception:
        return unavailable(version)
