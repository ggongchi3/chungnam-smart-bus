import { describe, expect, it } from 'vitest';
import { arrivalLabel, effectiveFreshness, formatDateTime, formatDistance, formatDuration, formatTime } from './format';
import type { Arrival, Quality } from './types';

const now = Date.parse('2026-11-10T00:00:00Z');
const quality: Quality = { sourceId: 'fixture', sourceUpdatedAt: '2026-11-09T23:59:00Z', fetchedAt: '2026-11-10T00:00:00Z', freshness: 'fresh' };
const arrival: Arrival = {
  segmentId: 'bus', routeId: 'route', boardStationId: 'origin', arrivalStatus: 'available',
  etaSeconds: 300, expectedArrivalAt: '2026-11-10T00:05:00Z', operationStatus: 'unknown', dataQuality: quality,
};

describe('displaying verified transport facts', () => {
  it('keeps missing duration and distance distinct from actual zero', () => {
    expect(formatDuration(null)).toBe('확인되지 않음');
    expect(formatDistance(null)).toBe('확인되지 않음');
    expect(formatDuration(0)).toBe('0분');
    expect(formatDistance(0)).toBe('0m');
    expect(formatDuration(90)).toBe('2분');
  });

  it('renders time in Korea regardless of the device timezone', () => {
    expect(formatTime('2026-11-10T00:00:00Z')).toBe('09:00');
    expect(formatDateTime('2026-11-10T00:00:00Z')).toContain('2026');
    expect(formatTime(null)).toBe('확인 불가');
    expect(formatTime('invalid')).toBe('확인 불가');
  });

  it('ages source data at the 90-second boundary without promoting stale data', () => {
    expect(effectiveFreshness(quality, now + 30_000)).toBe('fresh');
    expect(effectiveFreshness(quality, now + 30_001)).toBe('stale');
    expect(effectiveFreshness({ ...quality, freshness: 'stale' }, now)).toBe('stale');
    expect(effectiveFreshness({ ...quality, sourceUpdatedAt: null }, now)).toBe('unknown');
    expect(effectiveFreshness(quality, now - 70_000)).toBe('unknown');
  });

  it('does not present unknown or old ETA as a current arrival prediction', () => {
    expect(arrivalLabel(arrival, now)).toBe('5분 후 도착 예정');
    expect(arrivalLabel(arrival, now + 31_000)).toBe('오래된 도착 정보');
    expect(arrivalLabel({ ...arrival, dataQuality: { ...quality, freshness: 'unknown' } }, now)).toBe('도착 정보 갱신 시각 확인 불가');
    expect(arrivalLabel({ ...arrival, etaSeconds: null }, now)).toBe('도착 정보 확인 불가');
  });
});
