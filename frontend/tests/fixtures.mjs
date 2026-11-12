const firstBus = {
  segmentId: 'preview-bus-1',
  type: 'bus',
  routeId: 'demo-route-001',
  routeName: '시연 1번',
  boardStation: { stationId: 'demo-stop-001', name: '시연 출발 정류장' },
  alightStation: { stationId: 'demo-stop-003', name: '시연 병원 앞 정류장' },
  boardSequence: 1,
  alightSequence: 3,
  stopCount: 2,
  durationSeconds: null,
}

const transferSegments = [
  firstBus,
  {
    segmentId: 'preview-transfer',
    type: 'transfer',
    fromSegmentId: 'preview-bus-1',
    toSegmentId: 'preview-bus-2',
    atStation: { stationId: 'demo-stop-003', name: '시연 병원 앞 정류장' },
    instructionTemplateId: 'transfer.basic',
  },
  {
    segmentId: 'preview-bus-2',
    type: 'bus',
    routeId: 'demo-route-002',
    routeName: '시연 2번',
    boardStation: { stationId: 'demo-stop-003', name: '시연 병원 앞 정류장' },
    alightStation: { stationId: 'demo-stop-005', name: '시연 터미널 앞 정류장' },
    boardSequence: 1,
    alightSequence: 3,
    stopCount: 2,
    durationSeconds: null,
  },
  {
    segmentId: 'preview-walk-terminal',
    type: 'walk',
    fromLabel: '시연 터미널 앞 정류장',
    toLabel: '시연 터미널',
    distanceMeters: null,
    durationSeconds: null,
  },
]

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
