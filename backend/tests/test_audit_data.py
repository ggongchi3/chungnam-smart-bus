"""Data-integrity regressions for the independent backend audit.

All mutations target the per-test in-memory database. The runtime DB is untouched.
"""
from copy import deepcopy
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from backend.models import schemas as s
from backend.models.tables import DestinationAccess, RouteSearch, RouteStop, Station
from backend.tests.conftest import search, selection


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    payload = s.Envelope[None].model_validate(response.json())
    assert payload.data is None and payload.error.code == code
    assert response.headers['x-request-id'] == payload.meta.requestId


def selected_responses(client, body, path):
    return [client.get(path), client.get(path + '/live'),
            client.post('/api/v1/easy-guidance', json=body),
            client.post('/api/v1/print-guides', json=body)]


@pytest.mark.parametrize('column,value', [
    ('created_at', -1.0), ('created_at', 'NaN'),
    ('created_at', float('inf')), ('created_at', float('-inf')),
    ('created_at', 'broken'),
    ('expires_at', -1.0), ('expires_at', 'NaN'),
    ('expires_at', float('inf')), ('expires_at', float('-inf')),
    ('expires_at', 'broken'),
])
def test_corrupt_search_time_metadata_is_503_and_restorable(env, column, value):
    app, client, clock, _ = env
    body, path = selection(client, clock)
    with app.state.database.session() as session:
        row = session.get(RouteSearch, body['routeSearchId'])
        original = getattr(row, column)
        # SQLite REAL affinity still permits text corruption. A float NaN would
        # become SQL NULL and fail NOT NULL on insertion, so use stored NaN text.
        assert column in {'created_at', 'expires_at'}
        session.execute(text(f'UPDATE route_searches SET {column}=:value WHERE search_id=:sid'),
                        {'value': value, 'sid': body['routeSearchId']})
    for response in selected_responses(client, body, path):
        assert_error(response, 503, 'TRANSPORT_DATA_UNAVAILABLE')
    with app.state.database.session() as session:
        session.execute(text(f'UPDATE route_searches SET {column}=:value WHERE search_id=:sid'),
                        {'value': original, 'sid': body['routeSearchId']})
    assert client.get(path).status_code == 200
    assert search(client, clock).status_code == 200


@pytest.mark.parametrize('lifetime', [0, 599, 601, 3600])
def test_corrupt_search_lifetime_cannot_extend_or_shorten_contract(env, lifetime):
    app, client, clock, _ = env
    body, path = selection(client, clock)
    with app.state.database.session() as session:
        row = session.get(RouteSearch, body['routeSearchId'])
        row.expires_at = row.created_at + lifetime
    for response in selected_responses(client, body, path):
        assert_error(response, 503, 'TRANSPORT_DATA_UNAVAILABLE')


@pytest.mark.parametrize('age,status', [(599.999999, 200), (600, 410), (601, 410)])
def test_valid_search_keeps_exact_expiry_behavior(env, age, status):
    _, client, clock, _ = env
    body, path = selection(client, clock)
    clock.now += timedelta(seconds=age)
    for response in selected_responses(client, body, path):
        if status == 200:
            assert response.status_code == 200, response.text
        else:
            assert_error(response, 410, 'ROUTE_SEARCH_EXPIRED')


def test_storage_roundoff_never_extends_logical_six_hundred_second_expiry(env):
    app, client, clock, _ = env
    body, path = selection(client, clock)
    with app.state.database.session() as session:
        row = session.get(RouteSearch, body['routeSearchId'])
        row.expires_at += 0.0000005
    clock.now += timedelta(seconds=600)
    for response in selected_responses(client, body, path):
        assert_error(response, 410, 'ROUTE_SEARCH_EXPIRED')


@pytest.mark.parametrize('stored_mode,status,code', [
    ('invalid-mode', 503, 'TRANSPORT_DATA_UNAVAILABLE'),
    ('', 503, 'TRANSPORT_DATA_UNAVAILABLE'),
    ('demo', 200, None), ('live', 409, 'ROUTE_VERSION_CHANGED'),
])
def test_corrupt_mode_differs_from_valid_mode_change(env, stored_mode, status, code):
    app, client, clock, _ = env
    body, path = selection(client, clock)
    with app.state.database.session() as session:
        session.get(RouteSearch, body['routeSearchId']).data_mode = stored_mode
    for response in selected_responses(client, body, path):
        if status == 200:
            assert response.status_code == 200, response.text
        else:
            assert_error(response, status, code)


@pytest.mark.parametrize('fault', [
    'missing-source-marked-fresh', 'missing-source-marked-stale',
    'future-source-marked-fresh', 'altered-source-id',
    'missing-fetched-time', 'future-fetched-time', 'past-fetched-time',
])
def test_persisted_reference_quality_must_match_verified_snapshot_provenance(env, fault):
    app, client, clock, _ = env
    body, path = selection(client, clock)
    with app.state.database.session() as session:
        row = session.get(RouteSearch, body['routeSearchId'])
        snapshot = deepcopy(row.snapshot)
        quality = snapshot[body['routeOptionId']]['detail']['referenceDataQuality']
        if fault == 'missing-source-marked-fresh':
            quality['freshness'] = 'fresh'
        elif fault == 'missing-source-marked-stale':
            quality['freshness'] = 'stale'
        elif fault == 'future-source-marked-fresh':
            quality['sourceUpdatedAt'] = (clock.now + timedelta(seconds=30)).isoformat()
            quality['freshness'] = 'fresh'
        elif fault == 'altered-source-id':
            quality['sourceId'] = 'invented-source'
        elif fault == 'missing-fetched-time':
            quality['fetchedAt'] = None
        elif fault == 'future-fetched-time':
            quality['fetchedAt'] = (clock.now + timedelta(seconds=30)).isoformat()
        elif fault == 'past-fetched-time':
            quality['fetchedAt'] = (clock.now - timedelta(seconds=30)).isoformat()
        row.snapshot = snapshot
    for response in selected_responses(client, body, path):
        assert_error(response, 503, 'TRANSPORT_DATA_UNAVAILABLE')


@pytest.mark.parametrize('duration', [0, 120])
def test_known_walking_duration_is_preserved_in_summary_and_detail(env, duration):
    app, client, clock, _ = env
    with app.state.database.session() as session:
        access = session.get(DestinationAccess, ('demo-destination-001', 'demo-stop-003'))
        access.duration_seconds = duration
        assert access.distance_meters is None
    response = search(client, clock)
    assert response.status_code == 200, response.text
    data = s.Envelope[s.SearchData].model_validate(response.json()).data
    option = data.routeOptions[0]
    assert option.walkingDurationSeconds == duration
    assert option.totalDurationSeconds is None  # Bus duration remains unknown.
    path = f'/api/v1/route-searches/{data.routeSearchId}/options/{option.routeOptionId}'
    detail = s.Envelope[s.RouteDetail].model_validate(client.get(path).json()).data
    assert detail.segments[-1].durationSeconds == duration
    assert detail.segments[-1].distanceMeters is None
    assert all(p.durationSeconds is None for p in detail.segments if p.type == 'bus')


@pytest.mark.parametrize('coordinates', [
    {'latitude': 'broken', 'longitude': 127.0},
    {'latitude': 36.0, 'longitude': 'broken'},
    {'latitude': float('nan'), 'longitude': 127.0},
    {'latitude': float('inf'), 'longitude': 127.0},
    {'latitude': 36.0, 'longitude': float('-inf')},
])
def test_invalid_database_coordinates_are_503_and_sessions_recover(env, coordinates):
    app, client, clock, _ = env
    with app.state.database.session() as session:
        session.get(Station, 'demo-stop-001').coordinates = coordinates
        before = session.scalar(select(func.count()).select_from(RouteSearch))
    assert_error(client.get('/api/v1/stations/demo-stop-001'), 503, 'TRANSPORT_DATA_UNAVAILABLE')
    assert_error(search(client, clock), 503, 'TRANSPORT_DATA_UNAVAILABLE')
    with app.state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(RouteSearch)) == before
        session.get(Station, 'demo-stop-001').coordinates = None
    restored = client.get('/api/v1/stations/demo-stop-001')
    assert restored.status_code == 200 and restored.json()['data']['station']['coordinates'] is None
    assert search(client, clock).status_code == 200


def test_fractional_database_route_sequence_is_503_and_session_recovers(env):
    app, client, clock, _ = env
    with app.state.database.session() as session:
        session.get(RouteStop, ('demo-route-001', 1)).sequence = 1.5
        before = session.scalar(select(func.count()).select_from(RouteSearch))
    assert_error(search(client, clock), 503, 'TRANSPORT_DATA_UNAVAILABLE')
    with app.state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(RouteSearch)) == before
        row = session.get(RouteStop, ('demo-route-001', 1.5))
        assert row is not None
        row.sequence = 1
    assert search(client, clock).status_code == 200
