"""Provider boundary. No external transport service has been connected."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from typing import Protocol

from backend.config import ROOT
from backend.models import schemas as s
from backend.services.time import quality

SCENARIOS = ('normal', 'arrivals_missing', 'stale', 'source_missing', 'source_future',
             'changes_unknown', 'cancellation', 'detour', 'timetable_change', 'core_unavailable')


@dataclass(frozen=True)
class ProviderState:
    core_available: bool
    arrivals_available: bool
    source_updated_at: datetime | None
    fetched_at: datetime | None
    changes: s.ServiceChanges


class TransportProvider(Protocol):
    def read(self, now: datetime) -> ProviderState: ...


class DemoProvider:
    def __init__(self, scenario='normal', scenario_file=None):
        if scenario not in SCENARIOS:
            raise ValueError('Unknown demo scenario')
        self.scenario = scenario
        self.scenario_file = scenario_file
        self._loaded_scenario = None
        self._source = None
        self._fetched = None

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
        return ProviderState(
            core_available=scenario != 'core_unavailable', arrivals_available=scenario != 'arrivals_missing',
            source_updated_at=self._source, fetched_at=self._fetched,
            changes=s.ServiceChanges(coverageStatus=coverage, items=items,
                dataQuality=q if coverage == 'available' else quality(None, None, now, None)),
        )


class UnconnectedLiveProvider:
    def read(self, now):
        return ProviderState(False, False, None, None,
            s.ServiceChanges(coverageStatus='unknown', items=[], dataQuality=quality(None, None, now, None)))
