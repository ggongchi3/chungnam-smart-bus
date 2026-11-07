import { assertSameRoute, JourneyApiError, requestJourneyApi } from '../journey-guide/journeyApi.ts'
import { DEMO_NOTICE } from '../journey-guide/format.ts'
import type { RouteDetail, RouteSelection } from '../journey-guide/journeyTypes'
import { validateLive } from '../live-info/liveApi.ts'
import { selectionRequest, validateGuidance } from '../voice-guide/guidanceApi.ts'
import type { PrintData } from './printTypes'

function facts(detail: RouteDetail) {
  return JSON.stringify(detail.segments.map((segment) => {
    if (segment.type === 'bus') return [segment.segmentId, segment.type, segment.routeId, segment.routeName,
      segment.boardStation.stationId, segment.boardStation.name, segment.alightStation.stationId,
      segment.alightStation.name, segment.boardSequence, segment.alightSequence, segment.stopCount, segment.durationSeconds]
    if (segment.type === 'transfer') return [segment.segmentId, segment.type, segment.fromSegmentId,
      segment.toSegmentId, segment.atStation.stationId, segment.atStation.name, segment.instructionTemplateId]
    return [segment.segmentId, segment.type, segment.fromLabel, segment.toLabel, segment.distanceMeters, segment.durationSeconds]
  }))
}

export async function preparePrint(selection: RouteSelection, detail: RouteDetail, signal?: AbortSignal) {
  const result = await requestJourneyApi<PrintData>('/print-guides', { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(selectionRequest(selection)), signal })
  const data = result.data
  assertSameRoute(data.routeDetail, selection, result.dataMode)
  validateLive(data.liveInfoSnapshot, detail, result.dataMode, selection)
  validateGuidance(data.guidance, detail, result.dataMode, selection)
  if (facts(data.routeDetail) !== facts(detail) || data.liveInfoSnapshot.arrivals.some((arrival) => arrival.etaSeconds !== null)
    || !data.printGuideId || !Number.isFinite(Date.parse(data.generatedAt))
    || typeof data.notice !== 'string' || (result.dataMode === 'demo' && !data.notice.includes(DEMO_NOTICE))) {
    throw new JourneyApiError('INVALID_RESPONSE', '화면과 같은 경로의 인쇄 안내표를 준비하지 못했습니다.')
  }
  return data
}
