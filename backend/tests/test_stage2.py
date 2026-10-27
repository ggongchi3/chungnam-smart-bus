"""Stage 2 acceptance tests, separate from the runtime database."""
import json
from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import event, inspect, select, text
from sqlalchemy.exc import IntegrityError

from backend.config import ROOT
from backend.database import Database
from backend.models import schemas
from backend.models.tables import (Base, Destination, DestinationAccess, DestinationAlias,
                                   RouteStop, Station, TransferConnection)
from backend.seed import DEMO_SOURCE, catalog_counts, seed

COUNTS = {'stations': 5, 'destinations': 3, 'routes': 2, 'destination_aliases': 3,
          'route_stops': 6, 'destination_access': 3, 'transfer_connections': 1}


@pytest.fixture
def database():
    db = Database('sqlite:///:memory:')
    db.initialize()
    try:
        yield db
    finally:
        db.engine.dispose()


def write_source(tmp_path, source):
    path = tmp_path / 'seed-test.json'
    path.write_text(json.dumps(source, ensure_ascii=False), encoding='utf-8')
    return path


def test_seed_reports_actual_counts_and_keeps_full_catalog(database):
    first = seed(database)
    second = seed(database)
    assert first.inserted == first.totals == second.totals == COUNTS
    assert all(value == 0 for value in second.inserted.values())
    with database.session() as session:
        expected = json.loads(DEMO_SOURCE.read_text(encoding='utf-8'))
        assert session.scalars(select(DestinationAlias.alias).order_by(DestinationAlias.alias)).all() == sorted(
            item['alias'] for item in expected['aliases'])
        for item in expected['stations']:
            station = session.get(Station, item['station_id'])
            assert station.name == item['name'] and station.direction_label == item['direction_label']
            assert station.region is None and station.coordinates is None
        for item in expected['destinations']:
            destination = session.get(Destination, item['destination_id'])
            assert destination.name == item['name'] and destination.category == item['category']
        for item in expected['access']:
            access = session.get(DestinationAccess, (item['destination_id'], item['station_id']))
            assert access.distance_meters is None and access.duration_seconds is None
        transfer = session.get(TransferConnection, ('demo-route-001', 3, 'demo-route-002', 1))
        assert transfer is not None and transfer.evidence == expected['transfers'][0]['evidence']
        assert session.get(RouteStop, ('demo-route-001', 3)).station_id == 'demo-stop-003'
        assert session.get(RouteStop, ('demo-route-002', 1)).station_id == 'demo-stop-003'


@pytest.mark.parametrize('preexisting', [False, True])
def test_late_seed_failure_rolls_back_every_group(database, tmp_path, preexisting):
    if preexisting:
        seed(database)
        with database.session() as session:
            session.get(Station, 'demo-stop-001').name = '보존할 팀원 수정'
    with database.session() as session:
        before = catalog_counts(session)
    source = json.loads(DEMO_SOURCE.read_text(encoding='utf-8'))
    source['stations'].append({'station_id': 'test-partial-station', 'name': '합성 테스트',
                              'direction_label': '테스트', 'region': None, 'coordinates': None})
    # The final group fails only after all earlier groups have flushed.
    source['transfers'].append({'from_route_id': 'demo-route-001', 'from_sequence': 999,
                               'to_route_id': 'demo-route-002', 'to_sequence': 1, 'evidence': 'invalid test edge'})
    flushed = []
    with _flush_spy(database, flushed):
        with pytest.raises(IntegrityError):
            seed(database, source_path=write_source(tmp_path, source))
    assert 'test-partial-station' in flushed
    with database.session() as session:
        assert catalog_counts(session) == before
        assert session.get(Station, 'test-partial-station') is None
        if preexisting:
            assert session.get(Station, 'demo-stop-001').name == '보존할 팀원 수정'
    # A fresh session can commit normally after the failed seed.
    assert seed(database).totals == COUNTS


@contextmanager
def _flush_spy(database, flushed):
    def after_flush(session, context):
        flushed.extend(row.station_id for row in session.new if isinstance(row, Station))
    event.listen(database.sessions, 'after_flush', after_flush)
    try:
        yield
    finally:
        event.remove(database.sessions, 'after_flush', after_flush)


def test_seed_failure_after_last_flush_rolls_back_on_commit(database, tmp_path):
    path = write_source(tmp_path, json.loads(DEMO_SOURCE.read_text(encoding='utf-8')))
    def reject_commit(session):
        raise RuntimeError('simulated commit failure')
    event.listen(database.sessions, 'before_commit', reject_commit)
    try:
        with pytest.raises(RuntimeError, match='simulated commit failure'):
            seed(database, source_path=path)
    finally:
        event.remove(database.sessions, 'before_commit', reject_commit)
    with database.session() as session:
        assert all(value == 0 for value in catalog_counts(session).values())
    assert seed(database).totals == COUNTS


@pytest.mark.parametrize('row', [
    RouteStop(route_id='demo-route-001', sequence=4, station_id='missing-station'),
    DestinationAccess(destination_id='missing-destination', station_id='demo-stop-001'),
    DestinationAlias(destination_id='missing-destination', alias='합성 별칭'),
    TransferConnection(from_route_id='demo-route-001', from_sequence=3,
                       to_route_id='demo-route-002', to_sequence=999, evidence='invalid'),
])
def test_foreign_key_violations_are_rejected(database, row):
    seed(database)
    with pytest.raises(IntegrityError):
        with database.session() as session:
            session.add(row)
            session.flush()


@pytest.mark.parametrize('row', [
    DestinationAlias(destination_id='demo-destination-001', alias='시연 큰 병원'),
    RouteStop(route_id='demo-route-001', sequence=1, station_id='demo-stop-002'),
    DestinationAccess(destination_id='demo-destination-001', station_id='demo-stop-003'),
])
def test_composite_keys_reject_duplicates(database, row):
    seed(database)
    with pytest.raises(IntegrityError):
        with database.session() as session:
            session.add(row)
            session.flush()


def test_foreign_keys_enabled_on_every_new_connection():
    path = ROOT / '.local/tests' / ('stage2-' + uuid4().hex + '.sqlite3')
    db = Database('sqlite:///' + path.as_posix())
    try:
        db.initialize()
        for _ in range(2):
            with db.engine.connect() as connection:
                assert connection.scalar(text('PRAGMA foreign_keys')) == 1
            db.engine.dispose()  # Next connection must receive the hook too.
        assert path.parent.name == 'tests'
    finally:
        db.engine.dispose()


def test_schema_keys_nullable_and_models_remain_separate(database):
    schema = inspect(database.engine)
    assert schema.get_pk_constraint('route_stops')['constrained_columns'] == ['route_id', 'sequence']
    foreign_keys = schema.get_foreign_keys('transfer_connections')
    assert {tuple(fk['constrained_columns']) for fk in foreign_keys} == {
        ('from_route_id','from_sequence'), ('to_route_id','to_sequence')}
    assert all(fk['referred_table'] == 'route_stops' and fk['referred_columns'] == ['route_id','sequence']
               for fk in foreign_keys)
    station_columns = {column['name']: column for column in schema.get_columns('stations')}
    assert station_columns['region']['nullable'] and station_columns['coordinates']['nullable']
    assert not station_columns['name']['nullable']
    access_columns = {column['name']: column for column in schema.get_columns('destination_access')}
    assert access_columns['distance_meters']['nullable'] and access_columns['duration_seconds']['nullable']
    assert issubclass(Station, Base) and not issubclass(schemas.Station, Base)
