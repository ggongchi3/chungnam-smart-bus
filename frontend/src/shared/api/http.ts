import type { ApiResult, Envelope } from './types'

const baseUrl = (import.meta.env?.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

export class ApiRequestError extends Error {
  readonly code: string
  readonly status: number
  constructor(message: string, code: string, status = 0) {
    super(message)
    this.name = 'ApiRequestError'
    this.code = code
    this.status = status
  }
}

async function requestOnce<T>(path: string, init: RequestInit): Promise<ApiResult<T>> {
  const timeout = AbortSignal.timeout(5_000)
  const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout
  const headers = new Headers(init.headers)
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  let response: Response
  try {
    response = await fetch(baseUrl + path, { ...init, headers, signal, cache: 'no-store' })
  } catch (error) {
    if (init.signal?.aborted) throw error
    throw new ApiRequestError(timeout.aborted
      ? '응답을 기다리는 시간이 길어졌습니다. 잠시 후 다시 불러와 주세요.'
      : '안내 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.', 'CONNECTION_FAILED')
  }

  let body: Envelope<T>
  try {
    body = await response.json()
  } catch (error) {
    if (init.signal?.aborted) throw error
    if (timeout.aborted) throw new ApiRequestError('응답 시간이 초과되었습니다. 다시 불러와 주세요.', 'CONNECTION_FAILED')
    if (!response.ok) throw new ApiRequestError('안내 정보를 불러오지 못했습니다.', 'REQUEST_FAILED', response.status)
    throw new ApiRequestError('안내 정보를 읽을 수 없습니다. 다시 불러와 주세요.', 'INVALID_RESPONSE')
  }
  if (!response.ok || body?.error) {
    throw new ApiRequestError(body?.error?.message ?? '안내 정보를 불러오지 못했습니다.',
      body?.error?.code ?? 'REQUEST_FAILED', response.status)
  }
  if (body?.data == null || !['demo', 'live'].includes(body?.meta?.dataMode)) {
    throw new ApiRequestError('안내 정보의 형식을 확인할 수 없습니다.', 'INVALID_RESPONSE')
  }
  return { data: body.data, meta: body.meta }
}

function waitBeforeRetry(signal?: AbortSignal | null) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) { reject(signal.reason); return }
    const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve() }, 1_000)
    function abort() { clearTimeout(timer); signal?.removeEventListener('abort', abort); reject(signal?.reason) }
    signal?.addEventListener('abort', abort, { once: true })
  })
}

// A/B 공통: 요청별 5초 제한, GET 연결 실패/5xx만 1초 뒤 한 번 재시도한다.
export async function requestApi<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<ApiResult<T>> {
  const request = { ...init, signal: signal ?? init.signal }
  try {
    return await requestOnce<T>(path, request)
  } catch (error) {
    const transient = error instanceof ApiRequestError && (error.code === 'CONNECTION_FAILED' || error.status >= 500)
    if ((request.method ?? 'GET').toUpperCase() !== 'GET' || !transient || request.signal?.aborted) throw error
    await waitBeforeRetry(request.signal)
    return requestOnce<T>(path, request)
  }
}