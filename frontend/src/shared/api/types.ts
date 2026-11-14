/** Public API v0.1: kept aligned with backend/models/schemas.py. */
export type DataMode = 'demo' | 'live' | 'static';
export type RouteSort = 'fastest' | 'transfers' | 'walking' | 'distance';
export type PlaceSort = 'distance' | 'name' | 'walking';
export type Category = 'hospital' | 'market' | 'terminal' | 'station' | 'other';
export type JourneyStatus = 'ready' | 'recheck_required' | 'unavailable';
export type Freshness = 'fresh' | 'stale' | 'unknown';

export interface Meta {
  requestId: string;
  generatedAt: string;
  dataMode: DataMode;
}

/** Only successful envelopes are returned. Failed envelopes become ApiError. */
export interface Envelope<T> { data: T; error: null; meta: Meta }
export interface ServiceError { code: string; message: string; retryable: boolean }
export interface ErrorEnvelope { data: null; error: ServiceError; meta: Meta }

export interface Coordinates { latitude: number; longitude: number }
export interface Station {
  stationId: string;
  name: string;
  directionLabel: string;
  region: string | null;
  coordinates: Coordinates | null;
  arsId?: string | null;
}
export interface StationData { station: Station }
export interface Destination {
  destinationId: string;
  name: string;
  category: Category;
  aliases: string[];
  /** Verified place/location fields are returned by the backend catalogue. */
  address?: string;
  placeKind?: 'hospital' | 'office' | 'terminal' | 'market' | 'station' | 'education' | 'culture' | 'shopping';
  coordinates?: Coordinates | null;
  distanceMeters?: number | null;
  distanceBasis?: 'straight_line' | null;
  walkingDistanceMeters?: number | null;
  /** Presentation annotation; estimates are explicitly authorized for this prototype. */
  walkingDistanceBasis?: 'pedestrian_network' | 'prototype_estimate';
  coordinateSourceUrl?: string | null;
  locationNote?: string;
  sourceUrl?: string;
  sourceName?: string;
}
export interface DestinationData { destinations: Destination[] }
export interface Quality {
  sourceId: string | null;
  sourceUpdatedAt: string | null;
  fetchedAt: string | null;
  freshness: Freshness;
}
export interface StationRef { stationId: string; name: string; arsId?: string | null }
export interface RouteStop extends StationRef { sequence: number; coordinates: Coordinates }
export interface Bus {
  segmentId: string;
  type: 'bus';
  routeId: string;
  routeName: string;
  boardStation: StationRef;
  alightStation: StationRef;
  boardSequence: number;
  alightSequence: number;
  stopCount: number;
  durationSeconds: number | null;
  directionLabel?: string | null;
  stops?: RouteStop[];
  path?: Coordinates[];
}
export interface Walk {
  segmentId: string;
  type: 'walk';
  fromLabel: string;
  toLabel: string;
  distanceMeters: number | null;
  durationSeconds: number | null;
}
export interface Transfer {
  segmentId: string;
  type: 'transfer';
  fromSegmentId: string;
  toSegmentId: string;
  atStation: StationRef;
  instructionTemplateId: 'transfer.basic';
}
export type Segment = Bus | Walk | Transfer;
export interface RouteOption {
  routeOptionId: string;
  routeSnapshotVersion: string;
  pathGroupId?: string | null;
  journeyStatus: JourneyStatus;
  routeNames: string[];
  directionLabels?: string[];
  transferCount: number;
  totalDurationSeconds: number | null;
  walkingDurationSeconds: number | null;
  walkingDistanceMeters?: number | null;
  totalDistanceMeters?: number | null;
  /** Estimated movement only. Excludes bus waiting and transfer waiting. */
  estimatedTravelSeconds?: number | null;
  waitingDurationSeconds?: number | null;
  boardStation?: StationRef | null;
  alightStation?: StationRef | null;
  transferStations?: StationRef[];
  features?: string[];
  dataSource?: string | null;
  reasonText?: string | null;
}
export interface SearchRequest { originStationId: string; destinationId: string; departAt: string }
export interface SearchData {
  routeSearchId: string;
  originStationId: string;
  destinationId: string;
  expiresAt: string;
  routeOptions: RouteOption[];
  sortedBy?: RouteSort;
  routingNotice?: string | null;
  referenceRetrievedAt?: string | null;
}
export interface RouteDetail {
  routeSearchId: string;
  routeOptionId: string;
  routeSnapshotVersion: string;
  originStationId: string;
  destinationId: string;
  computedAt: string;
  journeyStatus: JourneyStatus;
  referenceDataQuality: Quality;
  segments: Segment[];
  dataSource?: string | null;
  routingNotice?: string | null;
  estimatedTravelSeconds?: number | null;
  totalDistanceMeters?: number | null;
  walkingDistanceMeters?: number | null;
}
export interface Arrival {
  segmentId: string;
  routeId: string;
  boardStationId: string;
  arrivalStatus: 'available' | 'unavailable';
  etaSeconds: number | null;
  expectedArrivalAt: string | null;
  operationStatus: 'running' | 'not_running' | 'unknown';
  dataQuality: Quality;
}
export interface Change {
  changeId: string;
  type: 'timetable_change' | 'cancellation' | 'detour' | 'other';
  affectedRouteIds: string[];
  affectedStationIds: string[];
  title: string;
  description: string;
  validFrom: string | null;
  validUntil: string | null;
  dataQuality: Quality;
}
export interface ServiceChanges { coverageStatus: 'available' | 'unknown'; items: Change[]; dataQuality: Quality }
export interface OptionArrivals { routeSnapshotVersion: string; arrivals: Arrival[] }
export interface SearchArrivals { routeSearchId: string; options: Record<string, OptionArrivals> }
export interface LiveData extends OptionArrivals { serviceChanges: ServiceChanges }
export interface SelectionRequest { routeSearchId: string; routeOptionId: string; expectedRouteSnapshotVersion: string }
export interface RouteSelection {
  originStationId: string;
  destinationId: string;
  routeSearchId: string;
  routeOptionId: string;
  routeSnapshotVersion: string;
  dataMode: DataMode;
}
export interface InterpretationRequest { originStationId: string; text: string }
export interface InterpretationData {
  status: 'matched' | 'needs_confirmation' | 'no_match' | 'unavailable';
  candidates: Destination[];
  reasonCode: 'MATCHED' | 'USER_CONFIRMATION_REQUIRED' | 'NO_REGISTERED_MATCH' | 'AI_UNAVAILABLE';
}
export interface ConversationData extends InterpretationData {
  sort: Extract<RouteSort, 'walking' | 'transfers' | 'fastest'> | null;
  clarification: { question: string; options: { destinationId: string; label: string }[] } | null;
}
export type JourneyIntent = 'which_bus' | 'how_many' | 'where_board' | 'where_alight' | 'stop_count' | 'walk' | 'duration';
export interface AnswerData {
  status: 'ok' | 'unavailable';
  intent: JourneyIntent | 'repeat' | 'unknown' | null;
  text: string | null;
}
export interface Step { segmentId: string; text: string }
export interface GuidanceData {
  routeSnapshotVersion: string;
  mode: 'ai_assisted' | 'template_fallback';
  steps: Step[];
}
export interface PrintData {
  printGuideId: string;
  generatedAt: string;
  routeDetail: RouteDetail;
  liveInfoSnapshot: LiveData;
  notice: string;
  guidance: GuidanceData;
  headline?: string | null;
}

export const DEMO_NOTICE = '시연 데이터 · 실제 운행 정보 아님';
