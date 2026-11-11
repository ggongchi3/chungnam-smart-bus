import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, isAbortError } from './client';

const meta = { requestId: 'test-request', generatedAt: '2026-11-10T03:00:00Z', dataMode: 'demo' };
const station = {
  stationId: 'demo-stop-001', name: '시연 출발 정류장', directionLabel: '시연 방향',
  region: null, coordinates: null,
};
const success = (data: unknown) => new Response(JSON.stringify({ data, error: null, meta }), { status: 200 });
const failure = (status: number, code = 'NOT_FOUND') => new Response(JSON.stringify({
  data: null, error: { code, message: '서버 오류 안내', retryable: status >= 500 }, meta,
}), { status });

describe('public API client', () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    vi.useFakeTimers();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it('keeps the backend envelope, null facts and encoded station ID', async () => {
    fetchMock.mockResolvedValue(success({ station }));
    const response = await api.station('test/한글');
    expect(response).toEqual({ data: { station }, error: null, meta });
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/stations/test%2F%ED%95%9C%EA%B8%80');
    expect(fetchMock.mock.calls[0][1].cache).toBe('no-store');
  });

  it('passes text and category as an intersection without inventing destinations', async () => {
    fetchMock.mockResolvedValue(success({ destinations: [] }));
    expect((await api.destinations('origin', ' 병원 ', 'hospital')).data.destinations).toEqual([]);
    const url = new URL(fetchMock.mock.calls[0][0], 'http://localhost');
    expect(url.searchParams.get('originStationId')).toBe('origin');
    expect(url.searchParams.get('query')).toBe('병원');
    expect(url.searchParams.get('category')).toBe('hospital');
  });

  it('retries a GET 5xx once after one second and retains the eventual server data', async () => {
    fetchMock.mockResolvedValueOnce(failure(503, 'TRANSPORT_DATA_UNAVAILABLE')).mockResolvedValueOnce(success({ station }));
    const result = api.station('origin');
    await vi.advanceTimersByTimeAsync(999);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect((await result).data.station.name).toBe(station.name);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('retries network failure once and then exposes a recoverable error', async () => {
    fetchMock.mockRejectedValue(new TypeError('offline'));
    const result = api.station('origin');
    const rejection = expect(result).rejects.toMatchObject({ code: 'NETWORK_ERROR', status: 0, retryable: true });
    await vi.advanceTimersByTimeAsync(1_000);
    await rejection;
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it.each([400, 404, 409, 410])('does not retry GET status %i and preserves server error metadata', async status => {
    fetchMock.mockResolvedValue(failure(status, 'ROUTE_VERSION_CHANGED'));
    await expect(api.detail('search', 'option')).rejects.toMatchObject({
      code: 'ROUTE_VERSION_CHANGED', status, meta, message: '서버 오류 안내',
    });
    await vi.advanceTimersByTimeAsync(10_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('does not automatically retry a route-search POST after a 503', async () => {
    fetchMock.mockResolvedValue(failure(503));
    await expect(api.search('origin', 'destination')).rejects.toBeInstanceOf(ApiError);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const request = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(request.originStationId).toBe('origin');
    expect(request.destinationId).toBe('destination');
    expect(new Date(request.departAt).toISOString()).toBe(request.departAt);
  });

  it('cancels an already aborted call before sending it', async () => {
    const controller = new AbortController();
    controller.abort();
    const error = await api.station('origin', controller.signal).catch(error => error);
    expect(isAbortError(error)).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('cancels during retry delay and never sends the second request', async () => {
    fetchMock.mockRejectedValue(new TypeError('offline'));
    const controller = new AbortController();
    const result = api.station('origin', controller.signal);
    const rejection = expect(result).rejects.toMatchObject({ name: 'AbortError' });
    await vi.advanceTimersByTimeAsync(100);
    controller.abort();
    await rejection;
    await vi.advanceTimersByTimeAsync(1_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('aborts a slow POST at five seconds without retrying', async () => {
    fetchMock.mockImplementation((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    }));
    const result = api.interpret('origin', '병원');
    const rejection = expect(result).rejects.toMatchObject({ code: 'TIMEOUT', status: 0 });
    await vi.advanceTimersByTimeAsync(5_000);
    await rejection;
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true);
  });

  it('rejects invalid success envelopes rather than making up usable data', async () => {
    fetchMock.mockResolvedValue(success(null));
    await expect(api.station('origin')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('uses the selected version unchanged for guidance and print preparation', async () => {
    const selected = { routeSearchId: 'search', routeOptionId: 'option', expectedRouteSnapshotVersion: 'version-1' };
    fetchMock.mockImplementation(() => Promise.resolve(success({})));
    await api.guidance(selected);
    await api.printGuide(selected);
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual(['/api/v1/easy-guidance', '/api/v1/print-guides']);
    expect(fetchMock.mock.calls.map(call => JSON.parse(call[1].body))).toEqual([selected, selected]);
  });
});
