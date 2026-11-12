"""One-time reviewed mapping of OSM facility objects to the existing catalogue."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    path = ROOT / 'shared/data/cheonan-places.json'
    catalog = json.loads(path.read_text(encoding='utf-8'))
    elements = json.loads((ROOT / 'backend/.local/research-osm-places.json').read_text(encoding='utf-8'))['elements']
    station_path = ROOT / 'backend/.local/research-osm-stations.json'
    if station_path.exists():
        elements += json.loads(station_path.read_text(encoding='utf-8'))['elements']
    by_id = {(x['type'], x['id']): x for x in elements}
    mapping = {
        'cheonan-dankook-hospital': ('way', 368095491),
        'cheonan-soonchunhyang-hospital': ('way', 1412690010),
        'cheonan-medical-center': ('way', 815583919),
        'cheonan-chungmu-hospital': ('way', 469716617),
        'cheonan-bus-terminal': ('node', 368736352),
        'cheonan-express-terminal': ('way', 174920754),
        'cheonan-station': ('node', 368636171),
        'cheonan-bongmyeong-station': ('node', 1973709782),
        'cheonan-dujeong-station': ('way', 479508674),
        'cheonan-city-hall': ('relation', 18451371),
        'cheonan-dongnam-district-office': ('way', 788723684),
        'cheonan-seobuk-district-office': ('way', 203708290),
        'cheonan-tax-office': ('way', 479990340),
        'cheonan-national-pension-office': ('way', 816471053),
        'cheonan-central-market': ('node', 5282288410),
    }
    additions = [
        ('sinan-office', '신안동 행정복지센터', 'other', 'office', '동남구 신부3길 16-6', ['신안동 주민센터'], ('way', 795652308)),
        ('dankook-university', '단국대학교 천안캠퍼스', 'other', 'education', '동남구 단대로 119', ['단국대', '단국대학교', '대학교', '대학'], ('way', 171904156)),
        ('sangmyung-university', '상명대학교 천안캠퍼스', 'other', 'education', '동남구 상명대길 31', ['상명대', '상명대학교', '대학교', '대학'], ('way', 231288273)),
        ('hoseo-university', '호서대학교 천안캠퍼스', 'other', 'education', '동남구 호서대길 12', ['호서대', '호서대학교', '대학교', '대학'], ('relation', 5470604)),
        ('koreatech', '한국기술교육대학교', 'other', 'education', '동남구 병천면 충절로 1600', ['한기대', '코리아텍', '대학교', '대학'], ('way', 223661475)),
        ('independence-hall', '독립기념관', 'other', 'culture', '동남구 목천읍 독립기념관로 1', ['기념관', '관광', '문화시설'], ('node', 368635603)),
        ('museum', '천안박물관', 'other', 'culture', '동남구 천안대로 429-13', ['박물관', '문화시설'], ('way', 481319581)),
        ('arario-gallery', '아라리오갤러리 천안', 'other', 'culture', '동남구 만남로 43', ['아라리오', '갤러리', '미술관', '문화시설'], ('way', 480562867)),
        ('shinsegae', '신세계백화점 천안아산점', 'market', 'shopping', '동남구 만남로 43', ['신세계', '백화점', '쇼핑'], ('way', 84331571)),
    ]
    for slug, name, category, kind, address, aliases, obj in additions:
        identity = 'cheonan-' + slug
        mapping[identity] = obj
        if not any(p['destinationId'] == identity for p in catalog['places']):
            catalog['places'].append({'destinationId': identity, 'name': name, 'category': category, 'kind': kind,
                'address': '충청남도 천안시 ' + address, 'aliases': aliases,
                'sourceUrl': f'https://www.openstreetmap.org/{obj[0]}/{obj[1]}', 'sourceName': 'OpenStreetMap 시설 정보'})
    for place in catalog['places']:
        if place['destinationId'] not in mapping:
            continue
        obj = mapping[place['destinationId']]
        source = by_id[obj]
        point = source.get('center', source)
        place['coordinates'] = {'latitude': point['lat'], 'longitude': point['lon']}
        place['coordinateSourceUrl'] = f'https://www.openstreetmap.org/{obj[0]}/{obj[1]}'
        place['coordinateNote'] = '시설 대표점. 출입구 위치와 차이가 있을 수 있음.'
    catalog['coordinateAttribution'] = '© OpenStreetMap contributors (ODbL); 일부 시장 좌표: 공공데이터포털'
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
