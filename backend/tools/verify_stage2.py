"""Verify stage 2 in the configured demo DB without deleting or replacing data."""
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import inspect, select, text

from backend.config import ROOT, Settings
from backend.database import Database
from backend.models.tables import Base
from backend.seed import DEMO_SOURCE, catalog_counts, seed

EXPECTED = {'stations': 5, 'destinations': 3, 'routes': 2, 'destination_aliases': 3,
            'route_stops': 6, 'destination_access': 3, 'transfer_connections': 1}


def snapshot(database):
    with database.session() as session:
        return {table.name: [dict(row) for row in session.execute(
            select(table).order_by(*table.primary_key.columns)).mappings()]
            for table in Base.metadata.sorted_tables}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def verify():
    settings = Settings.from_env()
    if settings.data_mode != 'demo':
        raise SystemExit('Stage 2 demo verification requires BUS_DATA_MODE=demo')
    database = Database(settings.database_url)
    try:
        database.initialize()
        before = snapshot(database)
        first = seed(database)
        second = seed(database)
        after = snapshot(database)
        if first.totals != EXPECTED or second.totals != EXPECTED:
            raise RuntimeError('Catalog counts differ from the agreed fixture; existing rows were preserved')
        assert not any(second.inserted.values())
        inspector = inspect(database.engine)
        schema = {}
        for table in Base.metadata.sorted_tables:
            schema[table.name] = {
                'primaryKey': inspector.get_pk_constraint(table.name)['constrained_columns'],
                'columns': [{'name': c['name'], 'type': str(c['type']), 'nullable': c['nullable']}
                            for c in inspector.get_columns(table.name)],
                'foreignKeys': inspector.get_foreign_keys(table.name),
                'checkConstraints': inspector.get_check_constraints(table.name),
            }
        with database.engine.connect() as connection:
            foreign_keys = connection.scalar(text('PRAGMA foreign_keys'))
            violations = connection.execute(text('PRAGMA foreign_key_check')).all()
        assert foreign_keys == 1 and not violations
        # Existing rows (including unrelated search snapshots) must survive intact.
        for table_name, rows in before.items():
            assert all(row in after[table_name] for row in rows)
        transfer = after['transfer_connections']
        assert len(transfer) == 1
        edge = transfer[0]
        assert (edge['from_route_id'], edge['from_sequence'], edge['to_route_id'], edge['to_sequence']) == (
            'demo-route-001', 3, 'demo-route-002', 1)
        route_stops = {(r['route_id'], r['sequence']): r['station_id'] for r in after['route_stops']}
        assert route_stops[('demo-route-001',3)] == route_stops[('demo-route-002',1)] == 'demo-stop-003'
        report = {
            'verifiedAt': datetime.now(timezone.utc).isoformat(), 'dataMode': 'demo',
            'notice': '시연 데이터 · 실제 운행 정보 아님',
            'sourceSha256': hashlib.sha256(DEMO_SOURCE.read_bytes()).hexdigest(),
            'databasePath': str(database.engine.url.database),
            'firstLoad': {'inserted':first.inserted,'totals':first.totals},
            'secondLoad': {'inserted':second.inserted,'totals':second.totals},
            'foreignKeysEnabled': bool(foreign_keys), 'foreignKeyViolations': [],
            'existingRowsPreserved': True, 'beforeSha256': fingerprint(before), 'afterSha256': fingerprint(after),
            'catalog': {k: v for k,v in after.items() if k != 'route_searches'},
            'preservedSearchCount': len(after['route_searches']), 'databaseSchema': schema,
        }
        output = ROOT / 'docs/stage2-verification-20261027.json'
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'totals': second.totals, 'secondLoadInserted':second.inserted,
                          'foreignKeyViolations':[], 'existingRowsPreserved':True}))
        return report
    finally:
        database.engine.dispose()


if __name__ == '__main__':
    verify()
