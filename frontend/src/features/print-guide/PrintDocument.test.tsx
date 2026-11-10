import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { PrintData, Quality } from '../../shared/api/types';
import { PrintDocument } from './PrintDocument';

const generatedAt = '2026-11-10T04:00:00Z';
const unknown: Quality = { sourceId: null, sourceUpdatedAt: null, fetchedAt: null, freshness: 'unknown' };

function snapshot(): PrintData {
  return {
    printGuideId: 'print-test', generatedAt,
    notice: '시연 데이터 · 실제 운행 정보 아님',
    routeDetail: {
      routeSearchId: 'search-test', routeOptionId: 'option-test', routeSnapshotVersion: 'v1',
      originStationId: 'start', destinationId: 'destination', computedAt: generatedAt,
      journeyStatus: 'ready', referenceDataQuality: unknown,
      segments: [
        { type: 'bus', segmentId: 'bus-1', routeId: 'route-1', routeName: '시연 1번',
          boardStation: { stationId: 'start', name: '시연 출발 정류장' },
          alightStation: { stationId: 'transfer', name: '시연 환승 정류장' },
          boardSequence: 1, alightSequence: 3, stopCount: 2, durationSeconds: null },
        { type: 'transfer', segmentId: 'transfer-1', fromSegmentId: 'bus-1', toSegmentId: 'bus-2',
          atStation: { stationId: 'transfer', name: '시연 환승 정류장' }, instructionTemplateId: 'transfer.basic' },
        { type: 'bus', segmentId: 'bus-2', routeId: 'route-2', routeName: '시연 2번',
          boardStation: { stationId: 'transfer', name: '시연 환승 정류장' },
          alightStation: { stationId: 'end', name: '시연 도착 정류장' },
          boardSequence: 1, alightSequence: 2, stopCount: 1, durationSeconds: null },
        { type: 'walk', segmentId: 'walk-1', fromLabel: '시연 도착 정류장', toLabel: '시연 터미널',
          distanceMeters: null, durationSeconds: null },
      ],
    },
    liveInfoSnapshot: {
      routeSnapshotVersion: 'v1',
      arrivals: [{ segmentId: 'bus-1', routeId: 'route-1', boardStationId: 'start',
        arrivalStatus: 'available', etaSeconds: 987655, expectedArrivalAt: '2026-11-10T17:42:00Z',
        operationStatus: 'unknown', dataQuality: unknown }],
      serviceChanges: { coverageStatus: 'unknown', items: [], dataQuality: unknown },
    },
    guidance: { routeSnapshotVersion: 'v1', mode: 'template_fallback', steps: [] },
  };
}

function render(data: PrintData): HTMLElement {
  const host = document.createElement('div');
  host.innerHTML = renderToStaticMarkup(<PrintDocument snapshot={data} originName="시연 출발 정류장" destinationName="시연 터미널" />);
  return host;
}

describe('고정 인쇄 안내표', () => {
  it('버스·환승·도보 순서와 미확인 정보를 유지하고 변동하는 도착 예측은 출력하지 않는다', () => {
    const doc = render(snapshot());
    const steps = Array.from(doc.querySelectorAll('ol > li'));
    expect(steps.map(step => step.querySelector('h2')?.textContent)).toEqual(['시연 1번 버스', '버스 환승', '시연 2번 버스', '도보 이동']);
    expect(steps[0].textContent).toContain('2개 정류장');
    expect(steps[1].textContent).toContain('시연 환승 정류장');
    expect(steps[3].textContent).toContain('거리: 확인되지 않음 · 소요시간: 확인되지 않음');
    expect(doc.textContent).toContain('시연 데이터 · 실제 운행 정보 아님');
    expect(doc.textContent).toContain('운행 상태: 확인 불가');
    expect(doc.textContent).toContain('운행 변경 정보 확인 불가');
    expect(doc.textContent).not.toContain('987655');
    expect(doc.textContent).not.toContain('02:42');
    expect(doc.textContent).not.toContain('0분');
    expect(doc.querySelectorAll('h1')).toHaveLength(1);
  });

  it.each([
    { version: 'old-version', segmentId: 'bus-1' },
    { version: 'v1', segmentId: 'unrelated-segment' },
  ])('현재 경로와 연결되지 않은 안내 문장을 인쇄하지 않는다 (%s)', ({ version, segmentId }) => {
    const data = snapshot();
    data.guidance = { routeSnapshotVersion: version, mode: 'ai_assisted', steps: [{ segmentId, text: '다른 경로에서 남은 오래된 안내 문장' }] };
    const doc = render(data);
    expect(doc.textContent).not.toContain('다른 경로에서 남은 오래된 안내 문장');
    expect(doc.querySelectorAll('ol > li')).toHaveLength(4);
    expect(doc.textContent).toContain('경로 버전: v1');
  });
});
