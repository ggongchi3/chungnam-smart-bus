"""되묻기·추천 이유·인쇄표 핵심 한 줄. 모두 고정 문구(phrases.json) + 백엔드 값이다.

예외를 밖으로 던지지 않는다. 필요한 값이 없으면 status=unavailable을 돌려주고, 화면·인쇄표는
기존 안내만 보여 주면 된다.
"""
from .words import bus_label, bus_segments, josa, minutes, phrase, rounded_meters, route_label, stop_name

MAX_CHOICES = 4  # 큰 버튼으로 보여 줄 수 있는 후보 수. 넘으면 목록에서 고르게 한다.

# 사용자가 말한 조건 → 백엔드 RouteOption.features에 붙는 이름(backend/services/cheonan_routing.py).
# 백엔드가 이 경로에 그 이름을 붙였을 때만 '말씀하신 대로' 문장을 쓴다.
FEATURE_FOR_SORT = {
    'walking': '최소 도보',
    'transfers': '최소 환승',
    'fastest': '최소 이동시간 · 대기 제외',
}


def unavailable():
    return {'status': 'unavailable', 'text': None}


# ---------------------------------------------------------------- 되묻기

def clarify(payload):
    """입력 {candidates: [{destinationId, name}]} (백엔드 InterpretationData.candidates 그대로 가능).

    출력 {status, question, options: [{destinationId, label}]}. 후보 순서는 받은 그대로.
    """
    try:
        candidates = payload.get('candidates') if type(payload) is dict else None
        if type(candidates) is not list or not candidates:
            return {'status': 'unavailable', 'question': None, 'options': []}
        options, seen = [], set()
        for item in candidates:
            key, name = item.get('destinationId'), item.get('name')
            if type(key) is not str or not key or key in seen or type(name) is not str or not name.strip():
                return {'status': 'unavailable', 'question': None, 'options': []}
            seen.add(key)
            options.append({'destinationId': key, 'label': name.strip()})
        names = [o['label'] for o in options]
        if len(names) == 1:
            question = phrase('clarify.one', place=josa(names[0], '으로/로'))
        elif len(names) == 2:
            question = phrase('clarify.two', first=josa(names[0], '과/와'), second=names[1])
        elif len(names) <= MAX_CHOICES:
            question = phrase('clarify.few', names=', '.join(names))
        else:
            question = phrase('clarify.many')
        return {'status': 'ok', 'question': question, 'options': options}
    except Exception:
        return {'status': 'unavailable', 'question': None, 'options': []}


# ---------------------------------------------------------------- 추천 이유

def explain_route(payload):
    """입력 {routeOption: 백엔드 RouteOption, sort: walking|transfers|fastest|None}.

    출력 {status, text, sentences}. 쓰는 값: transferCount, transferStations, walkingDistanceMeters,
    estimatedTravelSeconds, features. 사용자가 말한 조건과 관련된 문장을 앞에 둔다.
    """
    try:
        option = payload.get('routeOption') if type(payload) is dict else None
        sort = payload.get('sort') if type(payload) is dict else None
        if type(option) is not dict or sort not in (None, *FEATURE_FOR_SORT):
            return {**unavailable(), 'sentences': []}
        transfers = option.get('transferCount')
        if transfers not in (0, 1):
            return {**unavailable(), 'sentences': []}

        if transfers == 0:
            transfer = phrase('explain.direct')
        else:
            stations = option.get('transferStations') or []
            name = stations[0].get('name') if stations and type(stations[0]) is dict else None
            transfer = phrase('explain.transfer.at', station=name) if name else phrase('explain.transfer')

        walk = None
        if option.get('walkingDistanceMeters') is not None:
            meters = rounded_meters(option['walkingDistanceMeters'])
            if transfers == 0:
                walk = phrase('explain.walk.after', meters=meters) if meters else phrase('explain.walk.after.short')
            else:
                walk = phrase('explain.walk.total', meters=meters) if meters else phrase('explain.walk.total.short')

        # 시간은 '빨리'를 말했을 때만 말한다(대기시간이 빠진 값이라 다른 때는 헷갈릴 수 있다).
        travel = minutes(option.get('estimatedTravelSeconds')) if sort == 'fastest' else None
        time = phrase('explain.time', minutes=travel) if travel else None

        order = {'walking': (walk, transfer), 'fastest': (time, transfer, walk)}.get(sort, (transfer, walk))
        sentences = [s for s in order if s]
        features = option.get('features') or []
        if sort and FEATURE_FOR_SORT[sort] in features:
            sentences.insert(0, phrase('explain.preference.' + sort))
        return {'status': 'ok', 'text': ' '.join(sentences), 'sentences': sentences}
    except Exception:
        return {**unavailable(), 'sentences': []}


# ---------------------------------------------------------------- 인쇄표 핵심 한 줄

def print_headline(payload):
    """입력 {routeDetail: 백엔드 RouteDetail}. 출력 {status, text}.

    '16번 버스 → 순천향대병원 건너에서 내리세요'. 환승이 있으면 갈아타는 곳과 다음 버스를 넣는다.
    기존 단계별 인쇄표는 이 줄 아래에 그대로 이어진다.
    """
    try:
        detail = payload.get('routeDetail') if type(payload) is dict else None
        buses = bus_segments(detail)
        last = buses[-1]
        alight = stop_name(last['alightStation'], same_name_as=buses[0]['boardStation'])
        if len(buses) == 1:
            text = phrase('headline.one', bus=bus_label(last['routeName']), alight=alight)
        elif len(buses) == 2:
            text = phrase('headline.two', first=bus_label(buses[0]['routeName']),
                          transfer=stop_name(buses[0]['alightStation']),
                          second=josa(route_label(last['routeName']), '으로/로'), alight=alight)
        else:
            return unavailable()
        return {'status': 'ok', 'text': text}
    except Exception:
        return unavailable()
