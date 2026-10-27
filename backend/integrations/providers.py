"""Provider boundary. No external transport service has been connected."""
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Literal, Protocol

from backend.config import ROOT
from backend.models import schemas as s
from backend.services.time import aware_time, quality, refresh_quality

SCENARIOS = ('normal', 'arrivals_missing', 'stale', 'source_missing', 'source_future',
             'changes_unknown', 'cancellation', 'detour', 'timetable_change', 'core_unavailable',
             'operation_running', 'operation_not_running', 'arrivals_missing_running')


@dataclass(frozen=True)
class ArrivalObservation:
    expected_arrival_at: datetime | None
    operation_status: Literal['running', 'not_running', 'unknown'] = 'unknown'
    source_updated_at: datetime | None = None
    fetched_at: datetime | None = None
    source_id: str | None = None


@dataclass(frozen=True)
class ProviderState:
    core_available: bool
    arrivals_available: bool
    source_updated_at: datetime | None
    fetched_at: datetime | None
    changes: s.ServiceChanges
    arrivals: dict[tuple[str, str], ArrivalObservation] = field(default_factory=dict)


class TransportProvider(Protocol):
    def read(self, now: datetime) -> ProviderState: ...


def normalize_changes(changes, now):
    return changes.model_copy(update={
        'dataQuality': refresh_quality(changes.dataQuality, now),
        'items': [c.model_copy(update={'dataQuality': refresh_quality(c.dataQuality, now),
                    'affectedRouteIds': sorted(set(c.affectedRouteIds)),
                    'affectedStationIds': sorted(set(c.affectedStationIds))}, deep=True)
                  for c in changes.items],
    }, deep=True)


def read_provider(provider, now):
    """A failed provider cannot obscure search existence/expiry precedence."""
    try:
        state = provider.read(now)
        if not isinstance(state, ProviderState) or not isinstance(state.core_available, bool):
            raise ValueError('Invalid provider result')
    except Exception:
        return ProviderState(False, False, None, None,
            s.ServiceChanges(coverageStatus='unknown', items=[], dataQuality=quality(None, None, now, None)))
    try:
        changes = normalize_changes(state.changes, now)
    except Exception:
        changes = s.ServiceChanges(coverageStatus='unknown', items=[], dataQuality=quality(None, None, now, None))
    arrivals = {}
    try:
        for key, observation in state.arrivals.items():
            if not (isinstance(key, tuple) and len(key) == 2 and all(isinstance(v, str) for v in key)
                    and isinstance(observation, ArrivalObservation)
                    and (observation.source_id is None or isinstance(observation.source_id, str))):
                continue
            arrivals[key] = replace(observation, expected_arrival_at=aware_time(observation.expected_arrival_at),
                operation_status=observation.operation_status if observation.operation_status in
                    ('running', 'not_running', 'unknown') else 'unknown',
                source_updated_at=aware_time(observation.source_updated_at), fetched_at=aware_time(observation.fetched_at))
    except Exception:
        arrivals = {}
    return replace(state, changes=changes, arrivals=arrivals,
                   arrivals_available=state.arrivals_available if isinstance(state.arrivals_available, bool) else False)


class DemoProvider:
    def __init__(self, scenario='normal', scenario_file=None):
        if scenario not in SCENARIOS:
            raise ValueError('Unknown demo scenario')
        self.scenario = scenario
        self.scenario_file = scenario_file
        self._loaded_scenario = None
        self._source = None
        self._fetched = None
        source = json.loads(Path(__file__).with_name('demo-data.json').read_text(encoding='utf-8'))
        self._boarding_points = {(row['route_id'], row['station_id']) for row in source['route_stops']}

    def read(self, now):
        scenario, revision = self.scenario, None
        if self.scenario_file and self.scenario_file.exists():
            config = json.loads(self.scenario_file.read_text(encoding='utf-8'))
            scenario, revision = config['scenario'], config.get('revision')
        if scenario not in SCENARIOS:
            raise ValueError('Unknown demo scenario')
        token = (scenario, revision)
        # Persist synthetic source timestamps; polling never makes old data fresh.
        if token != self._loaded_scenario:
            self._loaded_scenario = token
            self._fetched = now
            self._source = (None if scenario == 'source_missing' else
                            now + timedelta(seconds=30) if scenario == 'source_future' else
                            now - timedelta(seconds=91) if scenario == 'stale' else now)
        q = quality(self._source, self._fetched, now)
        coverage = 'unknown' if scenario == 'changes_unknown' else 'available'
        items = []
        if scenario in ('cancellation', 'detour', 'timetable_change'):
            items.append(s.Change(
                changeId='demo-change-' + scenario, type=scenario, affectedRouteIds=['demo-route-001'],
                affectedStationIds=[], title='시연 운행 변경', description='합성 운행 변경 시나리오',
                validFrom=self._fetched, validUntil=None, dataQuality=q,
            ))
        arrivals_available = scenario not in ('arrivals_missing', 'arrivals_missing_running')
        observations = {}
        for route_id, station_id in self._boarding_points:
            operation = 'unknown'
            if route_id == 'demo-route-001':
                if scenario in ('operation_running', 'arrivals_missing_running'):
                    operation = 'running'
                elif scenario == 'operation_not_running':
                    operation = 'not_running'
            observations[(route_id, station_id)] = ArrivalObservation(
                expected_arrival_at=self._fetched + timedelta(seconds=300)
                    if arrivals_available and operation != 'not_running' else None,
                operation_status=operation, source_updated_at=self._source, fetched_at=self._fetched,
                source_id='demo-fixture',
            )
        return ProviderState(
            core_available=scenario != 'core_unavailable', arrivals_available=arrivals_available,
            source_updated_at=self._source, fetched_at=self._fetched,
            changes=s.ServiceChanges(coverageStatus=coverage, items=items,
                dataQuality=q if coverage == 'available' else quality(None, None, now, None)),
            arrivals=observations,
        )


class UnconnectedLiveProvider:
    def read(self, now):
        return ProviderState(False, False, None, None,
            s.ServiceChanges(coverageStatus='unknown', items=[], dataQuality=quality(None, None, now, None)))
