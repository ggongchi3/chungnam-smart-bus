import type {
  ApiMeta,
  ApiResult,
  Category,
  Destination,
  InterpretationData,
  SearchData,
  Station,
} from './types'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')
const REQUEST_TIMEOUT_MS = 5000
const GET_RETRY_DELAY_MS = 1000

export class ApiRequestError extends Error {
  readonly code: string
  readonly status: number

  constructor(
    message: string,
    code: string,
    status: number,
  ) {
    super(message)
    this.name = 'ApiRequestError'
    this.code = code
    this.status = status
  }
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      window.clearTimeout(timeout)
      reject(new DOMException('요청이 취소되었습니다.', 'AbortError'))
    }, { once: true })
  })
}

async function request<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<ApiResult<T>> {
  const method = (init.method ?? 'GET').toUpperCase()
  const canRetry = method === 'GET'
  let attempt = 0

  while (true) {
    const timeoutController = new AbortController()
    const timeout = window.setTimeout(() => timeoutController.abort(), REQUEST_TIMEOUT_MS)
    const combinedSignal = signal ? AbortSignal.any([signal, timeoutController.signal]) : timeoutController.signal

    try {
      const response = await fetch(API_BASE_URL + path, {
        ...init,
        headers: {
          Accept: 'application/json',
          ...(init.body ? { 'Content-Type': 'application/json' } : {}),
          ...init.headers,
        },
        signal: combinedSignal,
      })
      const envelope = await response.json() as {
        data: T | null
        error: { code: string; message: string; retryable: boolean } | null
        meta: ApiMeta
      }

      if (!response.ok || envelope.error || envelope.data === null) {
        const error = envelope.error
        const apiError = new ApiRequestError(
          error?.message ?? '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.',
          error?.code ?? 'INVALID_RESPONSE',
          response.status,
        )
        if (canRetry && attempt === 0 && response.status >= 500) {
          attempt += 1
          await delay(GET_RETRY_DELAY_MS, signal)
          continue
        }
        throw apiError
      }

      return { data: envelope.data, meta: envelope.meta }
    } catch (error) {
      if (signal?.aborted) throw new DOMException('요청이 취소되었습니다.', 'AbortError')
      const isTimeout = timeoutController.signal.aborted
      const retryable = canRetry && attempt === 0 && (isTimeout || !(error instanceof ApiRequestError))
      if (retryable) {
        attempt += 1
        await delay(GET_RETRY_DELAY_MS, signal)
        continue
      }
      if (isTimeout) throw new ApiRequestError('요청 시간이 초과되었습니다. 다시 시도해 주세요.', 'REQUEST_TIMEOUT', 0)
      throw error
    } finally {
      window.clearTimeout(timeout)
    }
  }
}

export function getStation(stationId: string, signal?: AbortSignal) {
  return request<{ station: Station }>('/api/v1/stations/' + encodeURIComponent(stationId), {}, signal)
}

export function getDestinations(
  originStationId: string,
  filters: { query?: string; category?: Category } = {},
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ originStationId })
  if (filters.query) params.set('query', filters.query)
  if (filters.category) params.set('category', filters.category)
  return request<{ destinations: Destination[] }>('/api/v1/destinations?' + params.toString(), {}, signal)
}

export function interpretDestination(originStationId: string, text: string, signal?: AbortSignal) {
  return request<InterpretationData>('/api/v1/destination-interpretations', {
    method: 'POST',
    body: JSON.stringify({ originStationId, text }),
  }, signal)
}

export function searchRoutes(originStationId: string, destinationId: string, signal?: AbortSignal) {
  return request<SearchData>('/api/v1/route-searches', {
    method: 'POST',
    body: JSON.stringify({ originStationId, destinationId, departAt: new Date().toISOString() }),
  }, signal)
}
