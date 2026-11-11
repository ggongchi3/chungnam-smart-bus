from sqlalchemy import select
import unicodedata

from backend.api.errors import not_found
from backend.models import schemas as s
from backend.models.tables import Station, Destination, DestinationAlias, DestinationLocation
from backend.services.geo import haversine_meters, destination_key


def station(session, station_id):
    row = session.get(Station, station_id)
    if row is None:
        not_found()
    return s.Station(stationId=row.station_id, name=row.name, directionLabel=row.direction_label,
                     region=row.region, coordinates=row.coordinates)


def destination(session, destination_id):
    row = session.get(Destination, destination_id)
    if row is None:
        not_found()
    aliases = session.scalars(select(DestinationAlias.alias).where(
        DestinationAlias.destination_id == destination_id).order_by(DestinationAlias.alias)).all()
    location = session.get(DestinationLocation, destination_id)
    facts = location.facts if location else {}
    return s.Destination(destinationId=row.destination_id, name=row.name, category=row.category, aliases=list(aliases),
        address=facts.get('address'), placeKind=facts.get('kind'), coordinates=facts.get('coordinates'),
        sourceUrl=facts.get('sourceUrl'), coordinateSourceUrl=facts.get('coordinateSourceUrl'))


def destinations(session, origin, query='', category=None, *, visible_ids=None, kind=None, sort='distance', transport=None):
    if transport:
        transport.require_origin(origin)
    source = transport.station(origin) if transport else station(session, origin)
    rows = session.scalars(select(Destination).order_by(Destination.destination_id)).all()
    result = [destination(session, row.destination_id) for row in rows
              if visible_ids is None or row.destination_id in visible_ids]
    def normalize(text):
        if visible_ids is not None:
            return ''.join(unicodedata.normalize('NFKC', text).casefold().split())
        return text.casefold()
    def searchable_values(item):
        values = [item.name, *item.aliases]
        if visible_ids is not None and item.address:
            values.append(item.address)
        return values
    result = [item for item in result if (not category or item.category == category) and (not kind or item.placeKind == kind) and
            (not query or any(normalize(query) in normalize(value) for value in searchable_values(item)))]
    if visible_ids is not None:
        for item in result:
            if source.coordinates and item.coordinates:
                item.distanceMeters = round(haversine_meters(source.coordinates.model_dump(), item.coordinates.model_dump()), 3)
                item.distanceBasis = 'straight_line'
            if transport:
                direct = transport.direct_walk(item.destinationId)
                item.walkingDistanceMeters = direct['distanceMeters'] if direct else None
        if sort == 'name':
            result.sort(key=lambda item: (item.name, item.destinationId))
        elif sort == 'walking':
            result.sort(key=lambda item: (item.walkingDistanceMeters is None, item.walkingDistanceMeters or 0, *destination_key(item)))
        else:
            result.sort(key=destination_key)
    return result
