import { JourneyApiError, requestJourneyApi } from './journeyApi.ts'
import type { RouteSelection } from './journeyTypes'

// A의 검색·목적지 확인 화면과 별개인 개발용 진입점. 합성 시연 경로만 사용한다.
export async function createDemoSelection(destinationId: string, signal?: AbortSignal): Promise<RouteSelection> {
  const result = await requestJourneyApi<{
    routeSearchId: string
    originStationId: string
    destinationId: string
    routeOptions: { routeOptionId: string; routeSnapshotVersion: string; journeyStatus: string }[]
  }>('/route-searches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ originStationId: 'demo-stop-001', destinationId, departAt: new Date().toISOString() }),
    signal,
  })
  const option = result.data.routeOptions.find((item) => item.journeyStatus === 'ready')
  if (result.dataMode !== 'demo') {
    throw new JourneyApiError('INVALID_SELECTION', '이 개발 확인 화면은 시연 서버에서만 사용할 수 있습니다.')
  }
  if (!option) throw new JourneyApiError('NO_ROUTE', '이용 가능한 시연 경로가 없습니다. 다른 경로를 선택해 주세요.')
  return {
    originStationId: result.data.originStationId,
    destinationId: result.data.destinationId,
    routeSearchId: result.data.routeSearchId,
    routeOptionId: option.routeOptionId,
    routeSnapshotVersion: option.routeSnapshotVersion,
    dataMode: result.dataMode,
  }
}
