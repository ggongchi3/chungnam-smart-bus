"""Backend-only audit checks for application failures, configuration and sessions."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

import backend.main as main_module
from backend.config import ROOT, Settings
from backend.database import Database
from backend.integrations.providers import DemoProvider
from backend.models import schemas as s
from backend.models.tables import RouteStop, Station
from backend.services import catalog


@pytest.fixture
def app_client():
    app = main_module.create_app(Settings(database_url='sqlite:///:memory:'), provider=DemoProvider())
    # Exercise the ASGI response for uncaught exceptions instead of re-raising them.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield app, client


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    value = s.Envelope[None].model_validate(response.json())
    assert value.data is None and value.error.code == code
    assert value.meta.requestId
    assert response.headers.get('x-request-id') == value.meta.requestId
    assert response.headers.get('cache-control') == 'no-store'
    return value


def test_unhandled_failure_is_sanitized_and_keeps_headers_and_rollback(app_client, monkeypatch):
    app, client = app_client
    sensitive = 'audit-private-sql-token-do-not-expose'

    def failing_station(session, station_id):
        session.add(Station(station_id='audit-failed-request', name='합성 실패 테스트', direction_label='감사'))
        session.flush()
        raise RuntimeError(sensitive)

    with monkeypatch.context() as patch:
        patch.setattr(catalog, 'station', failing_station)
        response = client.get('/api/v1/stations/demo-stop-001')
    assert_error(response, 500, 'INTERNAL_ERROR')
    assert sensitive not in response.text
    assert 'RuntimeError' not in response.text and 'Traceback' not in response.text
    with app.state.database.session() as session:
        assert session.get(Station, 'audit-failed-request') is None
    recovered = client.get('/api/v1/stations/demo-stop-001')
    assert recovered.status_code == 200
    assert recovered.headers['x-request-id'] != response.headers['x-request-id']


def test_method_not_allowed_preserves_allow_header(app_client):
    _, client = app_client
    response = client.put('/api/v1/stations/demo-stop-001')
    assert_error(response, 405, 'INVALID_REQUEST')
    assert 'GET' in response.headers.get('allow', '').replace(' ', '').split(',')


@pytest.mark.parametrize('failure_stage', ['initialize', 'seed'])
def test_startup_failure_disposes_database_engine(monkeypatch, failure_stage):
    app = main_module.create_app(Settings(database_url='sqlite:///:memory:'), provider=DemoProvider())
    engine = app.state.database.engine
    disposed = []

    def on_dispose(value):
        disposed.append(value)

    def fail(*args, **kwargs):
        raise RuntimeError('controlled-' + failure_stage + '-failure')

    event.listen(engine, 'engine_disposed', on_dispose)
    try:
        with monkeypatch.context() as patch:
            if failure_stage == 'initialize':
                patch.setattr(app.state.database, 'initialize', fail)
            else:
                patch.setattr(main_module, 'seed', fail)
            with pytest.raises(RuntimeError, match='controlled-' + failure_stage + '-failure'):
                with TestClient(app):
                    pytest.fail('Application must not start after initialization failure')
        assert disposed == [engine]
    finally:
        event.remove(engine, 'engine_disposed', on_dispose)
        if not disposed:
            engine.dispose()


@pytest.mark.parametrize('field,value', [
    ('latitude', 'not-a-number'), ('longitude', float('nan')),
    ('latitude', float('inf')), ('longitude', float('-inf')),
])
def test_invalid_runtime_coordinates_are_unavailable_not_server_details(app_client, field, value):
    app, client = app_client
    coordinates = {'latitude': 36.0, 'longitude': 127.0}
    coordinates[field] = value
    with app.state.database.session() as session:
        session.get(Station, 'demo-stop-001').coordinates = coordinates
    response = client.get('/api/v1/stations/demo-stop-001')
    assert_error(response, 503, 'TRANSPORT_DATA_UNAVAILABLE')
    assert 'not-a-number' not in response.text and 'ValidationError' not in response.text
    with app.state.database.session() as session:
        session.get(Station, 'demo-stop-001').coordinates = None
    recovered = client.get('/api/v1/stations/demo-stop-001')
    assert recovered.status_code == 200 and recovered.json()['data']['station']['coordinates'] is None


@pytest.mark.parametrize('content,content_type', [
    ('{', 'application/json'), (b'\xff', 'application/json'), ('{}', 'text/plain'),
])
def test_malformed_http_body_is_a_common_input_error(app_client, content, content_type):
    _, client = app_client
    response = client.post('/api/v1/route-searches', content=content, headers={'Content-Type': content_type})
    assert_error(response, 400, 'INVALID_REQUEST')
    assert_error(client.get('/api/v1/not-an-endpoint'), 404, 'NOT_FOUND')


def test_session_commit_and_constraint_failure_rollback_are_request_safe(app_client):
    app, client = app_client
    database = app.state.database
    with database.session() as session:
        session.add(Station(station_id='audit-committed', name='합성 커밋 정류장', direction_label='감사'))
    assert client.get('/api/v1/stations/audit-committed').status_code == 200
    with pytest.raises(IntegrityError):
        with database.session() as session:
            session.add(Station(station_id='audit-rolled-back', name='합성 롤백 정류장', direction_label='감사'))
            session.flush()
            session.add(RouteStop(route_id='audit-missing-route', sequence=1, station_id='audit-rolled-back'))
            session.flush()
    with database.session() as session:
        assert session.get(Station, 'audit-rolled-back') is None
        assert session.get(Station, 'audit-committed') is not None
    assert client.get('/api/v1/stations/audit-committed').status_code == 200


@pytest.mark.parametrize('location', ['outside', 'parent_escape', 'similar_prefix'])
def test_file_database_paths_cannot_escape_local(location):
    name = 'audit-' + uuid4().hex + '.sqlite3'
    targets = {'outside': ROOT.parent / name, 'parent_escape': ROOT / '.local' / '..' / name,
               'similar_prefix': ROOT / '.local-other' / name}
    with pytest.raises(ValueError, match='inside backend/.local'):
        Database('sqlite:///' + targets[location].as_posix())


def test_unsupported_database_driver_is_rejected_before_connecting():
    with pytest.raises(ValueError, match='SQLite only'):
        Database('postgresql://localhost/audit-not-used')


@pytest.mark.parametrize('mode', ['unsupported', 'DEMO', ''])
def test_invalid_data_mode_is_rejected_from_configuration(monkeypatch, mode):
    monkeypatch.setenv('BUS_DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('BUS_DATA_MODE', mode)
    with pytest.raises(ValueError, match='BUS_DATA_MODE must be demo, static or live'):
        main_module.create_app(Settings.from_env())
