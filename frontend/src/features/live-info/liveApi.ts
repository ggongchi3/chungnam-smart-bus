import { assertSameVersion, JourneyApiError, requestJourneyApi } from '../journey-guide/journeyApi.ts'
import type { DataMode, RouteDetail, RouteSelection } from '../journey-guide/journeyTypes'
import type { LiveData } from './liveTypes'

export function validateLive(data: LiveData, detail: RouteDetail, mode: DataMode, selection: RouteSelection) {
  assertSameVersion(data?.routeSnapshotVersion, mode, selection)
  const buses = detail.segments.filter((segment) => segment.type === 'bus')
  if (!Array.isArray(data.arrivals) || data.arrivals.length !== buses.length
    || new Set(data.arrivals.map((arrival) => arrival.segmentId)).size !== buses.length
    || buses.some((bus) => !data.arrivals.some((arrival) => arrival.segmentId === bus.segmentId
      && arrival.routeId === bus.routeId && arrival.boardStationId === bus.boardStation.stationId))
    || !data.serviceChanges || !Array.isArray(data.serviceChanges.items)
    || !['available', 'unknown'].includes(data.serviceChanges.coverageStatus)) {
    throw new JourneyApiError('INVALID_RESPONSE', '실시간 정보의 경로를 확인할 수 없습니다.')
  }
}

export async function loadLive(selection: RouteSelection, detail: RouteDetail, signal?: AbortSignal) {
  const result = await requestJourneyApi<LiveData>(
    `/route-searches/${encodeURIComponent(selection.routeSearchId)}/options/${encodeURIComponent(selection.routeOptionId)}/live`,
    { signal },
  )
  validateLive(result.data, detail, result.dataMode, selection)
  return result
}
