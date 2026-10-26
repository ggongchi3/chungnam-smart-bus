from sqlalchemy import select

from backend.api.errors import not_found
from backend.models import schemas as s
from backend.models.tables import Station, Destination, DestinationAlias


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
    return s.Destination(destinationId=row.destination_id, name=row.name, category=row.category, aliases=list(aliases))


def destinations(session, origin, query='', category=None):
    station(session, origin)
    rows = session.scalars(select(Destination).order_by(Destination.destination_id)).all()
    result = [destination(session, row.destination_id) for row in rows]
    return [item for item in result if (not category or item.category == category) and
            (not query or any(query.casefold() in value.casefold() for value in [item.name, *item.aliases]))]
