import type { DataQuality } from '../journey-guide/journeyTypes'

export type Arrival = {
  segmentId: string
  routeId: string
  boardStationId: string
  arrivalStatus: 'available' | 'unavailable'
  etaSeconds: number | null
  expectedArrivalAt: string | null
  operationStatus: 'running' | 'not_running' | 'unknown'
  dataQuality: DataQuality
}

export type ServiceChange = {
  changeId: string
  type: 'timetable_change' | 'cancellation' | 'detour' | 'other'
  affectedRouteIds: string[]
  affectedStationIds: string[]
  title: string
  description: string
  validFrom: string | null
  validUntil: string | null
  dataQuality: DataQuality
}

export type LiveData = {
  routeSnapshotVersion: string
  arrivals: Arrival[]
  serviceChanges: {
    coverageStatus: 'available' | 'unknown'
    items: ServiceChange[]
    dataQuality: DataQuality
  }
}
