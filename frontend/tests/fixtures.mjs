import { transferSegments } from '../src/features/journey-guide/previewSegments.ts'

export const selected = {
  originStationId: 'demo-stop-001', destinationId: 'demo-destination-003',
  routeSearchId: 'test-search', routeOptionId: 'test-option', routeSnapshotVersion: 'test-v1', dataMode: 'demo',
}
const { dataMode: _, ...ids } = selected
export const timestamp = '2026-11-07T05:00:00Z'
export const quality = { sourceId: 'fixture', sourceUpdatedAt: timestamp, fetchedAt: timestamp, freshness: 'fresh' }
export const detail = { ...ids, computedAt: timestamp, journeyStatus: 'ready', referenceDataQuality: quality, segments: transferSegments }
export const live = {
  routeSnapshotVersion: selected.routeSnapshotVersion,
  arrivals: transferSegments.filter((segment) => segment.type === 'bus').map((bus) => ({
    segmentId: bus.segmentId, routeId: bus.routeId, boardStationId: bus.boardStation.stationId,
    arrivalStatus: 'available', etaSeconds: 300, expectedArrivalAt: '2026-11-07T05:05:00Z',
    operationStatus: 'unknown', dataQuality: quality,
  })),
  serviceChanges: { coverageStatus: 'available', items: [], dataQuality: quality },
}
export const guidance = {
  routeSnapshotVersion: selected.routeSnapshotVersion, mode: 'template_fallback',
  steps: transferSegments.map((segment, index) => ({ segmentId: segment.segmentId,
    text: (index === 0 ? '시연 데이터 · 실제 운행 정보 아님. ' : '') + `검증용 ${segment.type} 안내 문장입니다.` })),
}
export function printed() {
  return structuredClone({ printGuideId: 'test-print', generatedAt: timestamp, routeDetail: detail,
    liveInfoSnapshot: { ...live, arrivals: live.arrivals.map((arrival) => ({ ...arrival, etaSeconds: null })) },
    guidance, notice: '시연 데이터 · 실제 운행 정보 아님. 생성 시점의 정보입니다.' })
}
export const envelope = (data, dataMode = 'demo') => ({ data, error: null, meta: { requestId: 'test-request', generatedAt: timestamp, dataMode } })
