import { requestApi as request } from './http.ts'
import type { Category, Destination, InterpretationData, SearchData, Station } from './types'

export { ApiRequestError } from './http.ts'
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
