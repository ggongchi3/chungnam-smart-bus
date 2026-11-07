import type { DataMode, RouteDetail, RouteSelection } from './journeyTypes'

// B 기능의 임시 연결 지점. A의 공통 API 클라이언트가 준비되면 교체한다.
const baseUrl = (import.meta.env?.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

type ApiResponse<T> = {
  data: T | null
  error: { code: string; message: string; retryable: boolean } | null
  meta: { requestId: string; generatedAt: string; dataMode: DataMode }
}

export class JourneyApiError extends Error {
  code: string
  status: number

  constructor(code: string, message: string, status = 0) {
    super(message)
    this.name = 'JourneyApiError'
    this.code = code
    this.status = status
  }
}

async function requestOnce<T>(path: string, init: RequestInit) {
  const timeout = AbortSignal.timeout(5_000)
  const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout
  let response: Response

  try {
    response = await fetch(`${baseUrl}/api/v1${path}`, { ...init, signal, cache: 'no-store' })
  } catch (error) {
    if (init.signal?.aborted) throw error
    throw new JourneyApiError('CONNECTION_FAILED', timeout.aborted
      ? '응답을 기다리는 시간이 길어졌습니다. 잠시 후 다시 불러와 주세요.'
      : '서버에 연결하지 못했습니다. 백엔드 실행 상태를 확인해 주세요.')
  }

  let body: ApiResponse<T>
  try {
    body = await response.json()
  } catch (error) {
    if (init.signal?.aborted) throw error
    if (timeout.aborted) throw new JourneyApiError('CONNECTION_FAILED', '응답 시간이 초과되었습니다. 다시 불러와 주세요.')
    if (!response.ok) throw new JourneyApiError('REQUEST_FAILED', '안내 정보를 불러오지 못했습니다.', response.status)
    throw new JourneyApiError('INVALID_RESPONSE', '안내 정보를 읽을 수 없습니다. 다시 불러와 주세요.')
  }
  if (!response.ok || body?.error) {
    throw new JourneyApiError(body?.error?.code ?? 'REQUEST_FAILED',
      body?.error?.message ?? '안내 정보를 불러오지 못했습니다.', response.status)
  }
  if (body?.data == null || !['demo', 'live'].includes(body?.meta?.dataMode)) {
    throw new JourneyApiError('INVALID_RESPONSE', '안내 정보의 형식을 확인할 수 없습니다.')
  }
  return { data: body.data, dataMode: body.meta.dataMode, generatedAt: body.meta.generatedAt }
}

function waitBeforeRetry(signal?: AbortSignal | null) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) { reject(signal.reason); return }
    const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve() }, 1_000)
    function abort() { clearTimeout(timer); signal?.removeEventListener('abort', abort); reject(signal?.reason) }
    signal?.addEventListener('abort', abort, { once: true })
  })
}

export async function requestJourneyApi<T>(path: string, init: RequestInit = {}) {
  try {
    return await requestOnce<T>(path, init)
  } catch (error) {
    const transient = error instanceof JourneyApiError
      && (error.code === 'CONNECTION_FAILED' || error.status >= 500)
    // 문서 기준: GET 연결 실패/5xx에만 1초 뒤 1회 재시도. POST와 4xx는 재시도하지 않는다.
    if ((init.method ?? 'GET').toUpperCase() !== 'GET' || !transient || init.signal?.aborted) throw error
    await waitBeforeRetry(init.signal)
    return requestOnce<T>(path, init)
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
