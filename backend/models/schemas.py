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
    dataMode: Literal['demo', 'live', 'static']


T = TypeVar('T')


class Envelope(Model, Generic[T]):
    data: T | None
    error: Error | None = None
    meta: Meta


class Coordinates(Model):
    latitude: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
    longitude: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]


class Station(Model):
    stationId: Identifier
    name: str
    directionLabel: str
    region: str | None
    coordinates: Coordinates | None
    arsId: str | None = None


class StationData(Model):
    station: Station


class Destination(Model):
    destinationId: Identifier
    name: str
    category: Category
    aliases: list[str]
    address: str | None = None
    placeKind: str | None = None
    coordinates: Coordinates | None = None
    distanceMeters: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    distanceBasis: Literal['straight_line'] | None = None
    walkingDistanceMeters: Nonnegative | None = None
    sourceUrl: str | None = None
    coordinateSourceUrl: str | None = None


class DestinationData(Model):
    destinations: list[Destination]


class DestinationQuery(BaseModel):
    """GET filters; extra query parameters remain ignored for compatibility."""
    originStationId: Identifier
    query: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ''
    category: Category | None = None
    kind: Literal['hospital', 'office', 'market', 'shopping', 'terminal', 'station', 'education', 'culture'] | None = None
    sort: Literal['distance', 'name', 'walking'] = 'distance'


class Quality(Model):
    sourceId: str | None
    sourceUpdatedAt: AwareDatetime | None
    fetchedAt: AwareDatetime | None
    freshness: Literal['fresh', 'stale', 'unknown']


class StationRef(Model):
    stationId: Identifier
    name: str
    arsId: str | None = None


class RouteStop(StationRef):
    sequence: Annotated[int, Field(ge=1)]
    coordinates: Coordinates


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
    distanceMeters: Nonnegative | None = None
    directionLabel: str | None = None
    stops: list[RouteStop] = Field(default_factory=list)
    path: list[Coordinates] = Field(default_factory=list)


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
    directionLabels: list[str] = Field(default_factory=list)
    transferCount: Annotated[int, Field(ge=0, le=1)]
    totalDurationSeconds: Nonnegative | None
    walkingDurationSeconds: Nonnegative | None
    walkingDistanceMeters: Nonnegative | None = None
    totalDistanceMeters: Nonnegative | None = None
    estimatedTravelSeconds: Nonnegative | None = None
    waitingDurationSeconds: Nonnegative | None = None
    boardStation: StationRef | None = None
    alightStation: StationRef | None = None
    transferStations: list[StationRef] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    dataSource: str | None = None


class SearchRequest(Model):
    originStationId: Identifier
    destinationId: Identifier
    departAt: AwareDatetime
    sort: Literal['fastest', 'transfers', 'walking', 'distance'] = 'transfers'

    @field_validator('departAt', mode='before')
    @classmethod
    def iso_departure(cls, value):
        # Pydantic otherwise accepts numeric epochs, including numeric strings,
        # while our JSON/OpenAPI contract requires an ISO 8601 time string.
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise ValueError('departAt must be a timezone-aware ISO 8601 string')
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError('departAt must include a timezone')
        return value


class SearchData(Model):
    routeSearchId: Identifier
    originStationId: Identifier
    destinationId: Identifier
    expiresAt: AwareDatetime
    routeOptions: list[RouteOption] = Field(max_length=12)
    sortedBy: str | None = None
    routingNotice: str | None = None
    referenceRetrievedAt: AwareDatetime | None = None


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
    dataSource: str | None = None
    routingNotice: str | None = None
    estimatedTravelSeconds: Nonnegative | None = None
    totalDistanceMeters: Nonnegative | None = None
    walkingDistanceMeters: Nonnegative | None = None


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


class OptionArrivals(Model):
    routeSnapshotVersion: str
    arrivals: list[Arrival]


class SearchArrivals(Model):
    routeSearchId: Identifier
    options: dict[Identifier, OptionArrivals]


class LiveData(OptionArrivals):
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
    reasonCode: Literal['MATCHED', 'USER_CONFIRMATION_REQUIRED', 'NO_REGISTERED_MATCH', 'AI_UNAVAILABLE']


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
