from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

Category = Literal['hospital', 'market', 'terminal', 'station', 'other']
JourneyStatus = Literal['ready', 'recheck_required', 'unavailable']
Identifier = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)]
Nonnegative = Annotated[int, Field(ge=0)]
NOTICE = '시연 데이터 · 실제 운행 정보 아님'


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Error(Model):
    code: str
    message: str
    retryable: bool


class Meta(Model):
    requestId: str
    generatedAt: AwareDatetime
    dataMode: Literal['demo', 'live']


T = TypeVar('T')


class Envelope(Model, Generic[T]):
    data: T | None
    error: Error | None = None
    meta: Meta


class Coordinates(Model):
    latitude: float
    longitude: float


class Station(Model):
    stationId: Identifier
    name: str
    directionLabel: str
    region: str | None
    coordinates: Coordinates | None


class StationData(Model):
    station: Station


class Destination(Model):
    destinationId: Identifier
    name: str
    category: Category
    aliases: list[str]


class DestinationData(Model):
    destinations: list[Destination]


class DestinationQuery(BaseModel):
    """GET filters; extra query parameters remain ignored for compatibility."""
    originStationId: Identifier
    query: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ''
    category: Category | None = None


class Quality(Model):
    sourceId: str | None
    sourceUpdatedAt: AwareDatetime | None
    fetchedAt: AwareDatetime | None
    freshness: Literal['fresh', 'stale', 'unknown']


class StationRef(Model):
    stationId: Identifier
    name: str


class Bus(Model):
    segmentId: Identifier
    type: Literal['bus'] = 'bus'
    routeId: Identifier
    routeName: str
    boardStation: StationRef
    alightStation: StationRef
    boardSequence: Annotated[int, Field(ge=1)]
    alightSequence: Annotated[int, Field(ge=1)]
    stopCount: Annotated[int, Field(ge=1)]
    durationSeconds: Nonnegative | None


class Walk(Model):
    segmentId: Identifier
    type: Literal['walk'] = 'walk'
    fromLabel: str
    toLabel: str
    distanceMeters: Nonnegative | None
    durationSeconds: Nonnegative | None


class Transfer(Model):
    segmentId: Identifier
    type: Literal['transfer'] = 'transfer'
    fromSegmentId: Identifier
    toSegmentId: Identifier
    atStation: StationRef
    instructionTemplateId: Literal['transfer.basic'] = 'transfer.basic'


Segment = Annotated[Bus | Walk | Transfer, Field(discriminator='type')]


class RouteOption(Model):
    routeOptionId: Identifier
    routeSnapshotVersion: str
    journeyStatus: JourneyStatus
    routeNames: list[str]
    transferCount: Annotated[int, Field(ge=0, le=1)]
    totalDurationSeconds: Nonnegative | None
    walkingDurationSeconds: Nonnegative | None


class SearchRequest(Model):
    originStationId: Identifier
    destinationId: Identifier
    departAt: AwareDatetime


class SearchData(Model):
    routeSearchId: Identifier
    originStationId: Identifier
    destinationId: Identifier
    expiresAt: AwareDatetime
    routeOptions: list[RouteOption] = Field(max_length=3)


class RouteDetail(Model):
    routeSearchId: Identifier
    routeOptionId: Identifier
    routeSnapshotVersion: str
    originStationId: Identifier
    destinationId: Identifier
    computedAt: AwareDatetime
    journeyStatus: JourneyStatus
    referenceDataQuality: Quality
    segments: list[Segment]


class Arrival(Model):
    segmentId: Identifier
    routeId: Identifier
    boardStationId: Identifier
    arrivalStatus: Literal['available', 'unavailable']
    etaSeconds: Nonnegative | None
    expectedArrivalAt: AwareDatetime | None
    operationStatus: Literal['running', 'not_running', 'unknown']
    dataQuality: Quality


class Change(Model):
    changeId: str
    type: Literal['timetable_change', 'cancellation', 'detour', 'other']
    affectedRouteIds: list[str]
    affectedStationIds: list[str]
    title: str
    description: str
    validFrom: AwareDatetime | None
    validUntil: AwareDatetime | None
    dataQuality: Quality


class ServiceChanges(Model):
    coverageStatus: Literal['available', 'unknown']
    items: list[Change]
    dataQuality: Quality


class LiveData(Model):
    routeSnapshotVersion: str
    arrivals: list[Arrival]
    serviceChanges: ServiceChanges


class SelectionRequest(Model):
    routeSearchId: Identifier
    routeOptionId: Identifier
    expectedRouteSnapshotVersion: Identifier


class InterpretationRequest(Model):
    originStationId: Identifier
    text: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)]

    @field_validator('text', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class InterpretationData(Model):
    status: Literal['matched', 'needs_confirmation', 'no_match', 'unavailable']
    candidates: list[Destination]
    reasonCode: str | None


class Step(Model):
    segmentId: Identifier
    text: str


class GuidanceData(Model):
    routeSnapshotVersion: str
    mode: Literal['ai_assisted', 'template_fallback']
    steps: list[Step]


class PrintData(Model):
    printGuideId: Identifier
    generatedAt: AwareDatetime
    routeDetail: RouteDetail
    liveInfoSnapshot: LiveData
    notice: str
    guidance: GuidanceData


class AIInterpretation(Model):
    status: Literal['matched', 'needs_confirmation', 'no_match', 'unavailable']
    candidateDestinationIds: list[Identifier]
    reasonCode: str | None


class AIChoice(Model):
    segmentId: Identifier
    templateId: str


class AIGuidance(Model):
    status: Literal['ok', 'unavailable']
    routeSnapshotVersion: str
    steps: list[AIChoice]
