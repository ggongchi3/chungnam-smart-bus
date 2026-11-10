"""Verified facility catalogue. Facilities do not imply a verified bus connection."""
import json
from pathlib import Path
from urllib.parse import urlparse

from backend.models.schemas import Coordinates
from backend.models.tables import Destination, DestinationAlias, DestinationLocation

SOURCE = Path(__file__).resolve().parents[2] / 'shared/data/cheonan-places.json'


def load_places():
    data = json.loads(SOURCE.read_text(encoding='utf-8'))
    places = data['places']
    ids = set()
    for place in places:
        identity = place['destinationId']
        if identity in ids or not identity.startswith('cheonan-'):
            raise ValueError('Facility IDs must be unique and scoped to Cheonan')
        ids.add(identity)
        if not place['address'].startswith('충청남도 천안시 ') or not place['name']:
            raise ValueError('Every facility must have a verified Cheonan address')
        if urlparse(place['sourceUrl']).scheme != 'https':
            raise ValueError('Every facility needs a source URL')
        if place['category'] not in ('hospital', 'terminal', 'station', 'market', 'other'):
            raise ValueError('Use the existing destination categories')
        if place['kind'] not in ('office', 'hospital', 'market', 'terminal', 'station', 'education', 'culture', 'shopping'):
            raise ValueError('Every facility must have a supported place kind')
        Coordinates.model_validate(place['coordinates'])
    return places


def register_places(database, places):
    """Add catalogue rows only; never add stops, routes, access or transfer links."""
    with database.session() as session:
        for place in places:
            identity = place['destinationId']
            if session.get(Destination, identity) is None:
                session.add(Destination(destination_id=identity, name=place['name'], category=place['category']))
        session.flush()
        for place in places:
            if session.get(DestinationLocation, place['destinationId']) is None:
                session.add(DestinationLocation(destination_id=place['destinationId'], facts=place))
            kind_terms = {'office': ['관공서', '공공기관'], 'hospital': ['병원', '의료시설'],
                          'market': ['시장'], 'terminal': ['터미널'], 'station': ['기차역', '철도역', '전철역', '지하철역'],
                          'education': ['대학교', '교육시설'], 'culture': ['관광', '관광지', '문화시설'], 'shopping': ['쇼핑', '백화점']}
            for alias in dict.fromkeys([*place['aliases'], *kind_terms[place['kind']]]):
                identity = (place['destinationId'], alias)
                if session.get(DestinationAlias, identity) is None:
                    session.add(DestinationAlias(destination_id=identity[0], alias=alias))
