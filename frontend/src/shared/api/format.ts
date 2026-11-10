import type { Arrival, Freshness, Quality } from './types';

export const UNKNOWN = '확인되지 않음';

function parsed(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatTime(value: string | null | undefined): string {
  const date = parsed(value);
  return date ? new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).format(date) : '확인 불가';
}

export function formatDateTime(value: string | null | undefined): string {
  const date = parsed(value);
  return date ? new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).format(date) : '확인 불가';
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return UNKNOWN;
  return `${Math.ceil(seconds / 60)}분`;
}

export function formatDistance(meters: number | null | undefined): string {
  if (meters == null || !Number.isFinite(meters) || meters < 0) return UNKNOWN;
  return meters < 1000 ? `${meters.toLocaleString('ko-KR')}m` : `${(meters / 1000).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}km`;
}

export function freshnessLabel(freshness: Freshness): string {
  return { fresh: '최근 정보', stale: '오래된 정보', unknown: '갱신 상태 확인 불가' }[freshness];
}

/** Source timestamps do not become fresh just because this browser fetched again. */
export function effectiveFreshness(quality: Quality, now = Date.now()): Freshness {
  if (quality.freshness !== 'fresh') return quality.freshness;
  const source = parsed(quality.sourceUpdatedAt);
  if (!source || source.getTime() > now) return 'unknown';
  return now - source.getTime() > 90_000 ? 'stale' : 'fresh';
}

export function arrivalLabel(arrival: Arrival, now = Date.now()): string {
  if (arrival.arrivalStatus !== 'available' || arrival.etaSeconds == null) return '도착 정보 확인 불가';
  const freshness = effectiveFreshness(arrival.dataQuality, now);
  if (freshness === 'stale') return '오래된 도착 정보';
  if (freshness === 'unknown') return '도착 정보 갱신 시각 확인 불가';
  return `${formatDuration(arrival.etaSeconds)} 후 도착 예정`;
}
