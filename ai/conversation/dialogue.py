"""한 단계씩 묻고 듣기.

경로를 고른 뒤 '몇 번 버스 타요?', '어디서 내려요?', '다시 말해 주세요'처럼 물으면, 고른 경로
(백엔드 RouteDetail)에서 그 질문에 필요한 값만 꺼내 한 문장으로 답한다. 질문 뜻은 규칙으로
알아듣고, 모르면 intent=unknown과 다시 물어봐 달라는 문장을 돌려준다. 예외를 던지지 않는다.
"""
import re

from ..destination_interpretation.interpreter import MAX_TEXT_LENGTH, compact
from .words import (bus_label, bus_segments, josa, minutes, phrase, rounded_meters, route_label, stop_label,
                    walk_segments)

# 위에서부터 차례로 본다. '몇 번 버스'(어느 버스)와 '몇 번 타요'(몇 번 타는지)를 가르려고
# which_bus를 how_many보다 먼저 둔다. '걸어요'(도보)와 '걸려요'(시간)도 다른 뜻이다.
INTENT_PATTERNS = (
    ('repeat', (r'다시', r'뭐라고', r'못들', r'안들', r'한번더', r'또말해', r'잘모르겠')),
    ('stop_count', (r'몇(개|정거장|정류장)', r'정거장', r'몇코스')),
    ('which_bus', (r'몇번버스', r'무슨버스', r'어떤버스', r'어느버스', r'버스(번호|몇번)', r'몇번(이|을|이에요|인가)',
                   r'뭐타', r'뭘타', r'무엇을타')),
    ('how_many', (r'몇번(타|갈아)', r'몇대', r'갈아타', r'환승', r'한번(에|만)', r'바로가')),
    ('where_alight', (r'내려', r'내리', r'하차')),
    ('where_board', (r'어디(서|에서)?타', r'타는곳', r'타는데', r'승차', r'어디(서|에서)기다')),
    ('walk', (r'걸어', r'걷', r'도보', r'얼마나멀')),
    ('duration', (r'걸려', r'걸리', r'몇분', r'시간', r'오래', r'언제도착', r'얼마나가')),
)
INTENTS = tuple(name for name, _ in INTENT_PATTERNS) + ('unknown',)
_COMPILED = [(name, [re.compile(p) for p in patterns]) for name, patterns in INTENT_PATTERNS]


def classify(question):
    """질문 → intent. 규칙에 없으면 'unknown'."""
    flat = compact(question)
    for name, patterns in _COMPILED:
        if any(p.search(flat) for p in patterns):
            return name
    return 'unknown'


def _bus_text(bus):
    return bus_label(bus['routeName'])


def reply(intent, detail):
    """intent와 RouteDetail → 답 문장. 값이 모자라면 ValueError."""
    buses = bus_segments(detail)
    first, last = buses[0], buses[-1]
    if len(buses) > 2:
        raise ValueError('버스 3대 이상은 안내하지 않음')
    two = len(buses) == 2
    transfer = stop_label(first['alightStation']) if two else None
    board = first['boardStation']
    alight = stop_label(last['alightStation'], same_name_as=board)  # 탄 곳과 이름이 같으면 번호로 가른다

    if intent == 'which_bus':
        if two:
            return phrase('answer.which_bus.two', board=stop_label(first['boardStation']),
                          first=josa(_bus_text(first), '을/를'), transfer=transfer,
                          second=josa(route_label(last['routeName']), '으로/로'))
        return phrase('answer.which_bus.one', board=stop_label(first['boardStation']),
                      bus=josa(_bus_text(first), '을/를'))
    if intent == 'how_many':
        return phrase('answer.how_many.two', transfer=transfer) if two else phrase('answer.how_many.one')
    if intent == 'where_board':
        return phrase('answer.where_board', board=stop_label(first['boardStation']),
                      bus=josa(_bus_text(first), '을/를'))
    if intent == 'where_alight':
        if two:
            return phrase('answer.where_alight.two', transfer=transfer,
                          second=josa(route_label(last['routeName']), '으로/로'),
                          alight=alight)
        return phrase('answer.where_alight.one', alight=alight)
    if intent == 'stop_count':
        if two:
            return phrase('answer.stop_count.two', first=first['stopCount'], second=last['stopCount'])
        return phrase('answer.stop_count.one', stops=first['stopCount'], alight=alight)
    if intent == 'walk':
        walks = [w for w in walk_segments(detail) if w.get('distanceMeters') is not None]
        if not walks:
            return phrase('answer.walk.none')
        walk = walks[-1]  # 마지막 도보 = 내린 뒤 목적지까지
        to, meters, mins = walk['toLabel'], rounded_meters(walk['distanceMeters']), minutes(walk.get('durationSeconds'))
        if meters is None:
            return phrase('answer.walk.short', to=to)
        if mins is None:
            return phrase('answer.walk.no_time', to=to, meters=meters)
        return phrase('answer.walk', to=to, meters=meters, minutes=mins)
    if intent == 'duration':
        mins = minutes(detail.get('estimatedTravelSeconds'))
        return phrase('answer.duration', minutes=mins) if mins else phrase('answer.duration.none')
    raise ValueError('모르는 intent')


def answer(payload, classify_intent=classify):
    """입력 {question, routeDetail, previousAnswer?}. 출력 {status, intent, text}.

    - repeat: previousAnswer를 그대로 다시 말한다. 없으면 '몇 번 버스' 답을 말한다.
    - unknown: status=ok, 다시 물어봐 달라는 고정 문장.
    - routeDetail이 안내할 수 없는 모양이면 status=unavailable.
    """
    try:
        question = payload.get('question') if type(payload) is dict else None
        detail = payload.get('routeDetail') if type(payload) is dict else None
        if type(question) is not str or not question.strip() or len(question) > MAX_TEXT_LENGTH:
            return {'status': 'unavailable', 'intent': None, 'text': None}
        bus_segments(detail)  # 경로 모양 먼저 확인
        intent = classify_intent(question)
        if intent not in INTENTS:
            intent = 'unknown'
        if intent == 'unknown':
            return {'status': 'ok', 'intent': intent, 'text': phrase('answer.unknown')}
        if intent == 'repeat':
            previous = payload.get('previousAnswer')
            text = previous if type(previous) is str and previous.strip() else reply('which_bus', detail)
            return {'status': 'ok', 'intent': intent, 'text': text}
        return {'status': 'ok', 'intent': intent, 'text': reply(intent, detail)}
    except Exception:
        return {'status': 'unavailable', 'intent': None, 'text': None}
