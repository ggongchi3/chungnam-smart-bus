import type { RouteSelection } from '../../shared/api/types'
export type { DataMode, RouteSelection } from '../../shared/api/types'

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
