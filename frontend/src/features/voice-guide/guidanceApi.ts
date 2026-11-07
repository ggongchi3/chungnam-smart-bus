import { assertSameVersion, JourneyApiError, requestJourneyApi } from '../journey-guide/journeyApi.ts'
import { DEMO_NOTICE } from '../journey-guide/format.ts'
import type { DataMode, RouteDetail, RouteSelection } from '../journey-guide/journeyTypes'
import type { GuidanceData } from './guidanceTypes'

export function selectionRequest(selection: RouteSelection) {
  return { routeSearchId: selection.routeSearchId, routeOptionId: selection.routeOptionId,
    expectedRouteSnapshotVersion: selection.routeSnapshotVersion }
}

export function validateGuidance(data: GuidanceData, detail: RouteDetail, mode: DataMode, selection: RouteSelection) {
  assertSameVersion(data?.routeSnapshotVersion, mode, selection)
  if (!['ai_assisted', 'template_fallback'].includes(data.mode) || !Array.isArray(data.steps)
    || data.steps.length !== detail.segments.length
    || data.steps.some((step, index) => step.segmentId !== detail.segments[index].segmentId
      || typeof step.text !== 'string' || !step.text.trim())
    || (mode === 'demo' && !data.steps[0]?.text.includes(DEMO_NOTICE))) {
    throw new JourneyApiError('INVALID_RESPONSE', '현재 경로에 맞는 안내 문장을 확인할 수 없습니다.')
  }
}

export async function loadGuidance(selection: RouteSelection, detail: RouteDetail, signal?: AbortSignal) {
  const result = await requestJourneyApi<GuidanceData>('/easy-guidance', { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(selectionRequest(selection)), signal })
  validateGuidance(result.data, detail, result.dataMode, selection)
  return result.data
}
