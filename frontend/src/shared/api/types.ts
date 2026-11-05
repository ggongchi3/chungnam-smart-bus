export type DataMode = 'demo' | 'live'
export type Category = 'hospital' | 'market' | 'terminal' | 'station' | 'other'
export type JourneyStatus = 'ready' | 'recheck_required' | 'unavailable'

export interface ApiErrorBody {
  code: string
  message: string
  retryable: boolean
}

export interface ApiMeta {
  requestId: string
  generatedAt: string
  dataMode: DataMode
}

export interface Envelope<T> {
  data: T | null
  error: ApiErrorBody | null
  meta: ApiMeta
}

export interface ApiResult<T> {
  data: T
  meta: ApiMeta
}

export interface Station {
  stationId: string
  name: string
  directionLabel: string
  region: string | null
  coordinates: { latitude: number; longitude: number } | null
}

export interface Destination {
  destinationId: string
  name: string
  category: Category
  aliases: string[]
}

export interface RouteOption {
  routeOptionId: string
  routeSnapshotVersion: string
  journeyStatus: JourneyStatus
  routeNames: string[]
  transferCount: number
  totalDurationSeconds: number | null
  walkingDurationSeconds: number | null
}

export interface SearchData {
  routeSearchId: string
  originStationId: string
  destinationId: string
  expiresAt: string
  routeOptions: RouteOption[]
}

export interface InterpretationData {
  status: 'matched' | 'needs_confirmation' | 'no_match' | 'unavailable'
  candidates: Destination[]
  reasonCode: 'MATCHED' | 'USER_CONFIRMATION_REQUIRED' | 'NO_REGISTERED_MATCH' | 'AI_UNAVAILABLE'
}

export interface RouteSelection {
  originStationId: string
  destinationId: string
  routeSearchId: string
  routeOptionId: string
  routeSnapshotVersion: string
  dataMode: DataMode
}
