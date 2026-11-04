"""규칙 기반 목적지 표현 해석 기준선.

입력된 자연어 표현을 백엔드가 준 allowedDestinations 안의 후보 ID에만 연결한다.
학습 모델이 아니며 장소·정류장·노선을 새로 만들지 않는다. 어떤 결과든 사용자가
후보를 확인하고 선택한다. 예외를 밖으로 던지지 않고 unavailable로 반환한다.
"""
import re
import unicodedata

MAX_TEXT_LENGTH = 200
MIN_TERM_LENGTH = 2
DEMO_PREFIX = '시연'

# 분류 표현 → 등록 이름의 핵심어. 표현이 나오면 핵심어를 이름·별칭에 포함한 후보를
# 모두 고른다. 특정 장소를 추정하지 않으며, 후보가 여럿이면 확인을 요청한다.
# '의원'·'보건소'처럼 다른 종류의 장소일 수 있는 표현은 넣지 않는다.
CATEGORY_TERMS = {
    '병원': ('병원', '종합병원', '대학병원'),
    '시장': ('시장', '전통시장', '재래시장', '장터', '장보러', '장보기', '장날'),
    '터미널': ('터미널', '버스터미널', '시외버스터미널', '고속버스터미널', '시외버스', '고속버스'),
}

# 표현 바로 뒤에 오면 그 장소를 빼라는 뜻으로 본다('병원 말고 시장').
PARTICLES = ('은', '는', '이', '가', '을', '를', '에', '으로', '로', '도')
NEGATIONS = ('말고', '말구', '빼고', '아니고', '아니구', '아니라', '아닌')

REASON_CODES = {
    'matched': 'MATCHED',
    'needs_confirmation': 'USER_CONFIRMATION_REQUIRED',
    'no_match': 'NO_REGISTERED_MATCH',
    'unavailable': 'AI_UNAVAILABLE',
}

_NON_WORD = re.compile(r'[^0-9a-z가-힣\s]')
_SPACES = re.compile(r'\s+')


def normalize(text):
    """NFKC·소문자·기호 제거·공백 정리."""
    text = unicodedata.normalize('NFKC', text).lower()
    return _SPACES.sub(' ', _NON_WORD.sub(' ', text)).strip()


def compact(text):
    return normalize(text).replace(' ', '')


def core(term):
    """'시연 병원' → '병원'. 합성 데이터 접두어는 사용자가 말하지 않는다."""
    words = normalize(term).split(' ')
    if words and words[0] == DEMO_PREFIX:
        words = words[1:]
    return ''.join(words)


def jamo(syllable):
    """한글 음절 → (초성, 중성, 종성) 번호. 한글이 아니면 글자 자체."""
    code = ord(syllable) - 0xAC00
    if 0 <= code < 11172:
        return code // 588, (code % 588) // 28, code % 28
    return syllable, None, None


def jamo_distance(left, right):
    """같은 길이의 두 문자열에서 서로 다른 초성·중성·종성 수('벙원'↔'병원' = 1)."""
    return sum(a != b for x, y in zip(left, right) for a, b in zip(jamo(x), jamo(y)))


def result(status, ids=()):
    return {'status': status, 'candidateDestinationIds': list(ids), 'reasonCode': REASON_CODES[status]}


def _valid_destinations(value):
    if type(value) is not list:
        return None
    seen = set()
    for item in value:
        if type(item) is not dict:
            return None
        key, name, aliases = item.get('destinationId'), item.get('name'), item.get('aliases', [])
        if type(key) is not str or not key or key in seen or type(name) is not str or not name.strip():
            return None
        if type(aliases) is not list or any(type(a) is not str for a in aliases):
            return None
        seen.add(key)
    return value


def _terms(destinations):
    """검색어 → 후보 ID 집합. 이름·별칭 전체, 접두어를 뺀 핵심어, 분류 표현."""
    terms = {}

    def add(term, key):
        if len(term) >= MIN_TERM_LENGTH and term != DEMO_PREFIX:
            terms.setdefault(term, set()).add(key)

    for item in destinations:
        for label in [item['name'], *item.get('aliases', [])]:
            add(compact(label), item['destinationId'])
            add(core(label), item['destinationId'])
    for head, expressions in CATEGORY_TERMS.items():
        owners = set()
        for item in destinations:
            labels = [core(label) for label in [item['name'], *item.get('aliases', [])]]
            if any(head in label for label in labels):
                owners.add(item['destinationId'])
        for expression in expressions:
            for key in owners:
                add(expression, key)
    return terms


def _hits(text, terms, fuzzy=False):
    """(시작, 끝, 후보 ID 집합) 목록. fuzzy면 자모 1개 차이까지 찾는다."""
    hits = []
    for term, keys in terms.items():
        if fuzzy:
            hits += [(i, i + len(term), keys) for i in range(len(text) - len(term) + 1)
                     if jamo_distance(text[i:i + len(term)], term) == 1]
            continue
        start = text.find(term)
        while start != -1:
            hits.append((start, start + len(term), keys))
            start = text.find(term, start + 1)
    # 더 긴 표현의 범위에 포함된 것은 버린다('큰 병원' 안의 '병원').
    return [(start, end, keys) for start, end, keys in hits
            if not any(s <= start and end <= e and (e - s) > (end - start) for s, e, _ in hits)]


def _negated(text, end):
    rest = text[end:]
    for particle in ('', *PARTICLES):
        if rest.startswith(particle) and rest[len(particle):].startswith(NEGATIONS):
            return True
    return False


def _match(text, terms):
    """(후보 ID 집합, 오타 추정 여부). 부정 표현이 붙은 장소는 뺀다."""
    fuzzy = False
    hits = _hits(text, terms)
    if not hits:
        hits, fuzzy = _hits(text, terms, fuzzy=True), True
    kept = set()
    for start, end, keys in hits:
        if not _negated(text, end):
            kept |= keys
    return kept, fuzzy


def interpret(payload):
    try:
        if type(payload) is not dict:
            return result('unavailable')
        text = payload.get('text')
        destinations = _valid_destinations(payload.get('allowedDestinations'))
        if type(text) is not str or not text.strip() or len(text) > MAX_TEXT_LENGTH or destinations is None:
            return result('unavailable')
        matched, fuzzy = _match(compact(text), _terms(destinations))
        # allowedDestinations 순서를 유지해 같은 입력에 같은 출력을 낸다.
        ids = [d['destinationId'] for d in destinations if d['destinationId'] in matched]
        if not ids:
            return result('no_match')
        # 오타로 추정한 후보는 1개여도 확인이 필요한 결과로 돌려준다.
        return result('matched' if len(ids) == 1 and not fuzzy else 'needs_confirmation', ids)
    except Exception:
        return result('unavailable')
