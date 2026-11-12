"""말로 목적지와 조건 찾기.

'중앙시장 가는데 많이 안 걷고 싶어요' → 목적지(천안중앙시장)와 조건(최소 도보)을 따로 알아듣는다.
- 목적지는 기존 목적지 해석(interpreter.interpret)을 그대로 쓴다. 조건 표현이 들어 있는 낱말은
  빼고 해석해 '걷고'·'빨리' 같은 말이 장소로 잘못 잡히지 않게 한다.
- 조건은 백엔드 경로 검색의 sort 값(walking·transfers·fastest) 중 하나로만 돌려준다.
  여러 조건을 말하면 먼저 말한 것을 쓴다. 조건이 없으면 None → 백엔드 기본 정렬을 쓴다.
- 화면 키보드로 쓴 글도 같은 함수로 처리한다. 예외를 밖으로 던지지 않는다.
"""
import re

from ..destination_interpretation import interpreter

SORTS = ('walking', 'transfers', 'fastest')

# 조건 표현(공백을 뺀 글에서 찾는 정규식). 백엔드 sort 값 → 표현 목록.
PREFERENCE_PATTERNS = {
    'walking': (
        r'(많이|오래|멀리)?(안|덜|적게|조금만?|짧게|못)(걷|걸어|걸을|걸으)',
        r'걷(기|는것|는게|는거)(가|이)?(힘들|힘드|싫|어렵|불편|무리)',
        r'걷지(않|말|못)',
        r'다리(가|도)?(아프|아파|불편)', r'무릎(이|도)?(아프|아파|안좋)', r'허리(가|도)?(아프|아파)',
        r'도보(가|를)?(적|짧|조금|최소)', r'최소도보',
    ),
    'transfers': (
        r'(안|덜)갈아타', r'갈아타(기|는것|는게|는거)(가|이|는)?(싫|힘들|힘드|어렵|불편|귀찮)',
        r'갈아타지(않|말|못)', r'환승(없|안|싫|하기싫|적|최소)', r'최소환승',
        r'한번에(가|갈)', r'바로가는', r'(버스)?한번만타',
    ),
    'fastest': (
        r'빨리', r'빠른', r'급해', r'급하', r'서둘', r'얼른', r'바빠', r'바쁘', r'바쁜', r'시간(이)?없',
        r'(오래|많이)?안걸리', r'금방',
    ),
}

# 조건 표현 바로 뒤에 오면 그 조건을 원하지 않는다는 뜻('빨리 안 가도 돼요', '급하지 않아요').
NEGATED_AFTER = ('안가도', '안와도', '않아도', '안해도', '지않', '지는않', '진않', '않', '없어도', '아니')

_COMPILED = {sort: [re.compile(p) for p in patterns] for sort, patterns in PREFERENCE_PATTERNS.items()}


def _word_spans(text):
    """normalize한 낱말과 공백 뺀 글 안의 (시작, 끝) 위치."""
    words = [w for w in interpreter.normalize(text).split(' ') if w]
    spans, position = [], 0
    for word in words:
        spans.append((word, position, position + len(word)))
        position += len(word)
    return spans


def find_preferences(text):
    """[(시작, 끝, sort, 표현)] 말한 순서대로. 부정된 표현은 뺀다."""
    flat = interpreter.compact(text)
    found = []
    for sort, patterns in _COMPILED.items():
        for pattern in patterns:
            for m in pattern.finditer(flat):
                if flat[m.end():].startswith(NEGATED_AFTER):
                    continue
                found.append((m.start(), m.end(), sort, m.group()))
    found.sort()
    return found


def strip_preferences(text, found):
    """조건 표현과 겹치는 낱말을 뺀 글. 목적지 해석에만 쓴다."""
    kept = [word for word, start, end in _word_spans(text)
            if not any(start < e and s < end for s, e, _, _ in found)]
    return ' '.join(kept)


def preference(found):
    if not found:
        return {'sort': None, 'matchedPhrase': None}
    _, _, sort, phrase = found[0]
    return {'sort': sort, 'matchedPhrase': phrase}


def understand(payload, interpret=interpreter.interpret):
    """입력은 목적지 해석과 같다({text, dataMode, allowedDestinations}).

    출력: {destination: 목적지 해석 결과, preference: {sort, matchedPhrase}}.
    조건만 말했으면(예: '빨리 가고 싶어요') destination은 no_match다 — 화면은 이미 고른 목적지에
    조건만 바꿔 다시 검색하면 된다.
    """
    try:
        text = payload.get('text') if type(payload) is dict else None
        if (type(text) is not str or not text.strip() or len(text) > interpreter.MAX_TEXT_LENGTH
                or interpreter._valid_destinations(payload.get('allowedDestinations')) is None):
            return {'destination': interpreter.result('unavailable'), 'preference': preference([])}
        found = find_preferences(text)
        rest = strip_preferences(text, found) if found else text
        # 조건 말고 남는 말이 없으면 목적지는 말하지 않은 것(no_match).
        destination = interpret({**payload, 'text': rest}) if rest.strip() else interpreter.result('no_match')
        return {'destination': destination, 'preference': preference(found)}
    except Exception:
        return {'destination': interpreter.result('unavailable'), 'preference': preference([])}
