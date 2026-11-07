// backend/models/schemas.py와 docs/api-contract.md의 공개 필드에 대응한다.
// A의 공통 타입이 준비되면 이 기능 안의 타입을 공통 타입 import로 교체한다.
export type DataMode = 'demo' | 'live'

export type StationRef = { stationId: string; name: string }

export type BusSegment = {
  segmentId: string
  type: 'bus'
  routeId: string
  routeName: string
  boardStation: StationRef
  alightStation: StationRef
  boardSequence: number
  alightSequence: number
  stopCount: number
  durationSeconds: number | null
}

export type WalkSegment = {
  segmentId: string
  type: 'walk'
  fromLabel: string
  toLabel: string
  distanceMeters: number | null
  durationSeconds: number | null
}

export type TransferSegment = {
  segmentId: string
  type: 'transfer'
  fromSegmentId: string
  toSegmentId: string
  atStation: StationRef
  instructionTemplateId: 'transfer.basic'
}

export type JourneySegment = BusSegment | WalkSegment | TransferSegment

export type RouteSelection = {
  originStationId: string
  destinationId: string
  routeSearchId: string
  routeOptionId: string
  routeSnapshotVersion: string
  dataMode: DataMode
}

export type DataQuality = {
  sourceId: string | null
  sourceUpdatedAt: string | null
  fetchedAt: string | null
  freshness: 'fresh' | 'stale' | 'unknown'
}

export type RouteDetail = Omit<RouteSelection, 'dataMode'> & {
  computedAt: string
  journeyStatus: 'ready' | 'recheck_required' | 'unavailable'
  referenceDataQuality: DataQuality
  segments: JourneySegment[]
}
