"""Idempotent insert-only seed: existing team edits are never overwritten."""
import json
from pathlib import Path

from backend.config import Settings
from backend.database import Database
from backend.models.tables import (Station, Destination, DestinationAlias, Route, RouteStop,
                                   DestinationAccess, TransferConnection)


def seed(database):
    source = json.loads((Path(__file__).parent / 'integrations/demo-data.json').read_text(encoding='utf-8'))
    groups = [('stations', Station), ('destinations', Destination), ('routes', Route),
              ('aliases', DestinationAlias), ('route_stops', RouteStop),
              ('access', DestinationAccess), ('transfers', TransferConnection)]
    with database.session() as session:
        for key, model in groups:
            keys = [column.name for column in model.__table__.primary_key]
            for values in source[key]:
                identity = tuple(values[k] for k in keys)
                if session.get(model, identity) is None:
                    session.add(model(**values))
            session.flush()


if __name__ == '__main__':
    settings = Settings.from_env()
    if settings.data_mode != 'demo':
        raise SystemExit('Synthetic seed requires BUS_DATA_MODE=demo')
    database = Database(settings.database_url)
    database.initialize()
    seed(database)
    print('Demo seed ready: 5 stations / 2 routes / 3 destinations / 6 stops / 1 transfer')
