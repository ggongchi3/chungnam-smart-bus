"""대화 기능이 함께 쓰는 문장 도우미: 조사 고르기, 버스·정류장 이름, 거리·시간 말하기.

모든 숫자·이름은 백엔드가 준 값을 그대로 쓴다. 여기서는 읽기 쉬운 모양으로만 바꾼다.
"""
import json
from pathlib import Path

PHRASES = json.loads(Path(__file__).with_name('phrases.json').read_text(encoding='utf-8'))
PHRASE_VERSION = PHRASES['version']


def phrase(key, **slots):
    """phrases.json의 고정 문구에 값을 넣는다."""
    return PHRASES['phrases'][key].format(**slots)


def _final(word):
    """마지막 글자의 받침 번호(0=받침 없음). 한글이 아니면 숫자 읽기로 판단한다."""
    word = word.rstrip()
    if not word:
        return 0
    last = word[-1]
    code = ord(last) - 0xAC00
    if 0 <= code < 11172:
        return code % 28
    # 숫자는 한국어로 읽었을 때의 받침: 0영 1일 3삼 6육 7칠 8팔 → 받침 있음, 1·7·8은 ㄹ.
    digit_finals = {'0': 21, '1': 8, '2': 0, '3': 16, '4': 0, '5': 0, '6': 1, '7': 8, '8': 8, '9': 0}
    return digit_finals.get(last, 0)


def josa(word, pair):
    """josa('시장', '과/와') → '시장과'. 앞이 받침 있음/없음 순서로 적는다.

    '으로/로'는 ㄹ 받침 뒤에서 '로'가 된다('천안역으로', '터미널로').
    """
    with_final, without_final = pair.split('/')
    final = _final(word)
    if pair == '으로/로':
        return word + ('로' if final in (0, 8) else '으로')
    return word + (with_final if final else without_final)


def bus_label(route_name):
    """'16' → '16번 버스'. 이미 '번'으로 끝나면 그대로 둔다."""
    name = str(route_name).strip()
    if name and name[-1].isdigit():
        name += '번'
    return name + ' 버스'


def route_label(route_name):
    """'16' → '16번' (버스라는 말 없이)."""
    name = str(route_name).strip()
    return name + '번' if name and name[-1].isdigit() else name


def stop_name(station, same_name_as=None):
    """인쇄표 한 줄처럼 짧게 쓸 때: 정류장 이름만.

    same_name_as(다른 StationRef)와 이름이 같고 정류장 번호가 다르면 번호를 붙여 가른다
    ('종합터미널'에서 타서 길 건너 '종합터미널(2357번)'에서 내리는 경우).
    """
    name = station.get('name', '').strip() if type(station) is dict else ''
    if not name:
        raise ValueError('정류장 이름 없음')
    other = same_name_as if type(same_name_as) is dict else {}
    ars = station.get('arsId')
    if other.get('name', '').strip() == name and ars and ars != other.get('arsId'):
        name = f'{name}({ars}번)'
    return name


def stop_label(station, same_name_as=None):
    """StationRef → '고속터미널 정류장'. 이름이 이미 '정류장'으로 끝나면 그대로."""
    name = stop_name(station, same_name_as)
    return name if name.endswith('정류장') else name + ' 정류장'


def rounded_meters(meters):
    """도보 거리를 50m 단위로. 50m 미만은 None(→ '조금만')."""
    if type(meters) not in (int, float) or meters < 0:
        return None
    if meters < 50:
        return None
    return int((meters + 25) // 50 * 50)


def minutes(seconds):
    """백엔드·인쇄표와 같은 올림 분((초+59)//60). 없으면 None."""
    if type(seconds) not in (int, float) or seconds < 0:
        return None
    return int((seconds + 59) // 60)


def bus_segments(detail):
    """RouteDetail에서 bus 구간만 순서대로."""
    segments = detail.get('segments') if type(detail) is dict else None
    if type(segments) is not list:
        raise ValueError('segments 없음')
    buses = [s for s in segments if type(s) is dict and s.get('type') == 'bus']
    if not buses:
        raise ValueError('bus 구간 없음')
    return buses


def walk_segments(detail):
    return [s for s in detail.get('segments', []) if type(s) is dict and s.get('type') == 'walk']
