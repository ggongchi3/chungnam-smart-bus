import { ApiRequestError, requestApi } from '../../shared/api/http.ts'
import type { DataMode, RouteDetail, RouteSelection } from './journeyTypes'

// 통신은 A/B 공통 클라이언트를 사용하고 B의 식별자·버전 검사와 오류 타입은 유지한다.
export class JourneyApiError extends ApiRequestError {
  constructor(code: string, message: string, status = 0) {
    super(message, code, status)
    this.name = 'JourneyApiError'
  }
}

export async function requestJourneyApi<T>(path: string, init: RequestInit = {}) {
  try {
    const result = await requestApi<T>('/api/v1' + path, init)
    return { data: result.data, dataMode: result.meta.dataMode, generatedAt: result.meta.generatedAt }
  } catch (error) {
    if (error instanceof ApiRequestError) throw new JourneyApiError(error.code, error.message, error.status)
    throw error
  }
}
export function isRouteIssue(error: unknown) {
  return error instanceof JourneyApiError && ['INVALID_SELECTION', 'ROUTE_VERSION_CHANGED',
    'ROUTE_SEARCH_EXPIRED', 'NOT_FOUND', 'NO_ROUTE', 'TRANSPORT_DATA_UNAVAILABLE'].includes(error.code)
}

export function assertSameVersion(version: string, mode: DataMode, selection: RouteSelection) {
  if (version !== selection.routeSnapshotVersion || mode !== selection.dataMode) {
    throw new JourneyApiError('ROUTE_VERSION_CHANGED', '경로가 바뀌었습니다. 경로를 다시 선택해 주세요.')
  }
}

export function assertSameRoute(detail: RouteDetail, selection: RouteSelection, mode: DataMode) {
  assertSameVersion(detail?.routeSnapshotVersion, mode, selection)
  if (['originStationId', 'destinationId', 'routeSearchId', 'routeOptionId'].some(
    (key) => detail[key as keyof RouteDetail] !== selection[key as keyof RouteSelection],
  ) || detail.journeyStatus !== 'ready') {
    throw new JourneyApiError('ROUTE_VERSION_CHANGED', '선택한 경로를 다시 확인해 주세요.')
  }
}

export async function loadJourney(selection: RouteSelection, signal?: AbortSignal) {
  const { dataMode, ...identifiers } = selection
  if (!['demo', 'live'].includes(dataMode) || Object.values(identifiers).length !== 5
    || Object.values(identifiers).some((id) => typeof id !== 'string' || !id.trim())) {
    throw new JourneyApiError('INVALID_SELECTION', '선택한 경로가 없습니다. 경로를 다시 선택해 주세요.')
  }
  const result = await requestJourneyApi<RouteDetail>(
    `/route-searches/${encodeURIComponent(selection.routeSearchId)}/options/${encodeURIComponent(selection.routeOptionId)}`,
    { signal },
  )
  // 선택 당시와 버전·목적지·데이터 모드가 다르면 안내를 표시하지 않는다.
  if (result.dataMode !== dataMode || Object.entries(identifiers).some(
    ([key, value]) => result.data[key as keyof typeof identifiers] !== value,
  ) || result.data.journeyStatus !== 'ready') {
    throw new JourneyApiError('ROUTE_VERSION_CHANGED', '선택한 경로가 바뀌었습니다. 경로를 다시 선택해 주세요.')
  }
  if (!Array.isArray(result.data.segments) || result.data.segments.length === 0) {
    throw new JourneyApiError('INVALID_RESPONSE', '이동 구간을 확인할 수 없습니다. 다시 불러와 주세요.')
  }
  return result
}
