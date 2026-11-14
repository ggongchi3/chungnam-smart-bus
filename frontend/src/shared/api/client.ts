import type {
  AnswerData, Category, ConversationData, DestinationData, Envelope, GuidanceData, InterpretationData, JourneyIntent, LiveData,
  Meta, PrintData, RouteDetail, SearchArrivals, SearchData, SelectionRequest, StationData, RouteSort, PlaceSort,
} from './types';

const BASE = '/api/v1';
const TIMEOUT_MS = 5_000;
const RETRY_DELAY_MS = 1_000;

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
    message: string,
    public readonly retryable = false,
    public readonly meta?: Meta,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export function isAbortError(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'name' in error && error.name === 'AbortError';
}

const cancelled = () => new DOMException('요청이 취소되었습니다.', 'AbortError');

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(cancelled()); return; }
    const onAbort = () => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
      reject(cancelled());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object';
}

function readMeta(value: unknown): Meta | undefined {
  if (!isRecord(value) || typeof value.requestId !== 'string' ||
      typeof value.generatedAt !== 'string' ||
      !['demo', 'live', 'static'].includes(String(value.dataMode))) return undefined;
  return value as unknown as Meta;
}

async function attempt<T>(path: string, method: 'GET' | 'POST', body: unknown, signal?: AbortSignal): Promise<Envelope<T>> {
  if (signal?.aborted) throw cancelled();
  const controller = new AbortController();
  let timedOut = false;
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort, { once: true });
  const recording = body instanceof Blob ? body : null;
  const timeout = recording ? 45_000 : path === '/route-searches' ? 30_000 : TIMEOUT_MS;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeout);
  try {
    const response = await fetch(BASE + path, {
      method,
      signal: controller.signal,
      cache: 'no-store',
      ...(method === 'POST' ? {
        headers: { 'Content-Type': recording?.type || 'application/json' },
        body: recording ?? JSON.stringify(body),
      } : {}),
    });
    const payload: unknown = await response.json().catch(() => null);
    // Abort can happen while consuming the response body as well as during fetch.
    if (controller.signal.aborted) {
      if (signal?.aborted) throw cancelled();
      throw new ApiError('TIMEOUT', 0, '응답 시간이 초과되었습니다. 다시 시도해 주세요.', true);
    }
    const meta = isRecord(payload) ? readMeta(payload.meta) : undefined;
    const error = isRecord(payload) && isRecord(payload.error) ? payload.error : undefined;
    if (!response.ok || error) {
      throw new ApiError(
        typeof error?.code === 'string' ? error.code : 'HTTP_ERROR',
        response.status,
        typeof error?.message === 'string' ? error.message : '서버에 연결하지 못했습니다. 다시 시도해 주세요.',
        typeof error?.retryable === 'boolean' ? error.retryable : response.status >= 500,
        meta,
      );
    }
    if (!isRecord(payload) || payload.data == null || payload.error !== null || !meta) {
      throw new ApiError('INVALID_RESPONSE', response.status, '서버 응답을 확인할 수 없습니다. 다시 시도해 주세요.');
    }
    return payload as unknown as Envelope<T>;
  } catch (error) {
    if (signal?.aborted) throw cancelled();
    if (timedOut) throw new ApiError('TIMEOUT', 0, '응답 시간이 초과되었습니다. 다시 시도해 주세요.', true);
    if (error instanceof ApiError) throw error;
    throw new ApiError('NETWORK_ERROR', 0, '네트워크 연결을 확인한 뒤 다시 시도해 주세요.', true);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  }
}

async function request<T>(path: string, method: 'GET' | 'POST' = 'GET', body?: unknown, signal?: AbortSignal): Promise<Envelope<T>> {
  try {
    return await attempt<T>(path, method, body, signal);
  } catch (error) {
    const retry = method === 'GET' && error instanceof ApiError &&
      (error.status >= 500 || error.code === 'NETWORK_ERROR' || error.code === 'TIMEOUT');
    if (!retry) throw error;
    await delay(RETRY_DELAY_MS, signal);
    return attempt<T>(path, method, body, signal);
  }
}

const encode = encodeURIComponent;
const optionPath = (searchId: string, optionId: string) => `/route-searches/${encode(searchId)}/options/${encode(optionId)}`;

export const api = {
  station: (id: string, signal?: AbortSignal) => request<StationData>(`/stations/${encode(id)}`, 'GET', undefined, signal),
  destinations: (origin: string, query = '', category?: Category, signal?: AbortSignal, options?: { sort?: PlaceSort; kind?: string }) => {
    const params = new URLSearchParams({ originStationId: origin, query: query.trim() });
    if (category) params.set('category', category);
    if (options?.sort) params.set('sort', options.sort);
    if (options?.kind) params.set('kind', options.kind);
    return request<DestinationData>(`/destinations?${params}`, 'GET', undefined, signal);
  },
  search: (origin: string, destination: string, signal?: AbortSignal, sort?: RouteSort, explain = false) => request<SearchData>('/route-searches', 'POST', {
    originStationId: origin, destinationId: destination, departAt: new Date().toISOString(),
    ...(sort ? {sort} : {}),
    ...(explain ? {explain} : {}),
  }, signal),
  detail: (searchId: string, optionId: string, signal?: AbortSignal) => request<RouteDetail>(optionPath(searchId, optionId), 'GET', undefined, signal),
  searchArrivals: (searchId: string, signal?: AbortSignal) => request<SearchArrivals>(`/route-searches/${encode(searchId)}/arrivals`, 'GET', undefined, signal),
  live: (searchId: string, optionId: string, signal?: AbortSignal) => request<LiveData>(`${optionPath(searchId, optionId)}/live`, 'GET', undefined, signal),
  interpret: (origin: string, text: string, signal?: AbortSignal) => request<InterpretationData>('/destination-interpretations', 'POST', { originStationId: origin, text: text.trim() }, signal),
  understand: (origin: string, text: string, signal?: AbortSignal) => request<ConversationData>('/conversation/understand', 'POST', { originStationId: origin, text: text.trim() }, signal),
  transcribe: (audio: Blob, signal: AbortSignal) =>
    request<{ text: string }>('/speech/transcriptions', 'POST', audio, signal),
  answer: (selection: SelectionRequest, question: string, previousIntent: JourneyIntent | null, signal?: AbortSignal) =>
    request<AnswerData>('/conversation/answers', 'POST', { ...selection, question: question.trim(), previousIntent }, signal),
  guidance: (selection: SelectionRequest, signal?: AbortSignal) => request<GuidanceData>('/easy-guidance', 'POST', selection, signal),
  printGuide: (selection: SelectionRequest, signal?: AbortSignal) => request<PrintData>('/print-guides', 'POST', selection, signal),
};
