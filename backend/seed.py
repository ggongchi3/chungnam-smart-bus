"""Idempotent insert-only seed: existing team edits are never overwritten."""
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select

from backend.config import Settings
from backend.database import Database
from backend.models.tables import (Station, Destination, DestinationAlias, Route, RouteStop,
                                   DestinationAccess, TransferConnection)


DEMO_SOURCE = Path(__file__).parent / 'integrations/demo-data.json'
SEED_GROUPS = (
    ('stations', Station), ('destinations', Destination), ('routes', Route),
    ('aliases', DestinationAlias), ('route_stops', RouteStop),
    ('access', DestinationAccess), ('transfers', TransferConnection),
)


@dataclass(frozen=True)
class SeedResult:
    inserted: dict[str, int]
    totals: dict[str, int]


def catalog_counts(session):
    return {model.__tablename__: session.scalar(select(func.count()).select_from(model))
            for _, model in SEED_GROUPS}


def seed(database, *, source_path=None):
    """Insert a catalog in one transaction; optional source injection is for tests.

    Existing rows are preserved. On any load/flush/commit error the exception is
    propagated and the transaction rolls back, including previously flushed rows.
    """
    source = json.loads(Path(source_path or DEMO_SOURCE).read_text(encoding='utf-8'))
    inserted = {model.__tablename__: 0 for _, model in SEED_GROUPS}
    with database.session() as session:
        for key, model in SEED_GROUPS:
            keys = [column.name for column in model.__table__.primary_key]
            for values in source[key]:
                identity = tuple(values[k] for k in keys)
                if session.get(model, identity) is None:
                    session.add(model(**values))
                    inserted[model.__tablename__] += 1
            session.flush()
        totals = catalog_counts(session)
    return SeedResult(inserted=inserted, totals=totals)


if __name__ == '__main__':
    settings = Settings.from_env()
    if settings.data_mode != 'demo':
        raise SystemExit('Synthetic seed requires BUS_DATA_MODE=demo')
    database = Database(settings.database_url)
    database.initialize()
    try:
        result = seed(database)
        print(json.dumps({'dataMode': 'demo', 'inserted': result.inserted, 'totals': result.totals}))
    finally:
        database.engine.dispose()
