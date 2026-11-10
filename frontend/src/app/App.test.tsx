import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../shared/api/client';
import type { Destination, Envelope, GuidanceData, LiveData, PrintData, Quality, RouteDetail, SearchData } from '../shared/api/types';
import { App } from './App';

vi.mock('../shared/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../shared/api/client')>();
  return { ...actual, api: {
    station: vi.fn(), destinations: vi.fn(), search: vi.fn(), detail: vi.fn(),
    live: vi.fn(), interpret: vi.fn(), guidance: vi.fn(), printGuide: vi.fn(),
  } };
});
const voice = vi.hoisted(() => ({ supported: true, speaking: false, message: '', speak: vi.fn(), stop: vi.fn() }));
vi.mock('../features/voice-guide/useVoiceGuide', () => ({ useVoiceGuide: () => voice }));

const NOW = '2026-11-10T04:00:00Z';
const quality: Quality = { sourceId: 'demo-fixture', sourceUpdatedAt: null, fetchedAt: NOW, freshness: 'unknown' };
const destination: Destination = { destinationId: 'demo-destination-001', name: '시연 병원', category: 'hospital', aliases: [] };
const detail: RouteDetail = {
  routeSearchId: 'search-1', routeOptionId: 'option-1', routeSnapshotVersion: 'v1',
  originStationId: 'demo-stop-001', destinationId: destination.destinationId,
  computedAt: NOW, journeyStatus: 'ready', referenceDataQuality: quality,
  segments: [{ type: 'bus', segmentId: 'bus-1', routeId: 'route-1', routeName: '시연 1번',
    boardStation: { stationId: 'demo-stop-001', name: '시연 출발 정류장' },
    alightStation: { stationId: 'demo-stop-003', name: '시연 병원 앞 정류장' },
    boardSequence: 1, alightSequence: 3, stopCount: 2, durationSeconds: null }],
};
const live: LiveData = { routeSnapshotVersion: 'v1', arrivals: [], serviceChanges: { coverageStatus: 'unknown', items: [], dataQuality: quality } };
const guidance: GuidanceData = { routeSnapshotVersion: 'v1', mode: 'template_fallback', steps: [{ segmentId: 'bus-1', text: '시연 1번을 타고 시연 병원 앞 정류장에서 내리세요.' }] };
const printed: PrintData = { printGuideId: 'print-1', generatedAt: NOW, routeDetail: detail, liveInfoSnapshot: live, notice: '시연 데이터 · 실제 운행 정보 아님', guidance };
function envelope<T>(data: T): Envelope<T> { return { data, error: null, meta: { requestId: 'request-1', generatedAt: NOW, dataMode: 'demo' } }; }
function search(expiresAt = '2026-11-10T04:10:00Z'): SearchData {
  return { routeSearchId: 'search-1', originStationId: 'demo-stop-001', destinationId: destination.destinationId, expiresAt,
    routeOptions: [{ routeOptionId: 'option-1', routeSnapshotVersion: 'v1', journeyStatus: 'ready', routeNames: ['시연 1번'], transferCount: 0, totalDurationSeconds: null, walkingDurationSeconds: null }] };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

let root: Root;
let host: HTMLDivElement;
const originalScroll = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollTo');
const heading = () => host.querySelector('main h1')?.textContent;
function button(text: string): HTMLButtonElement {
  const result = Array.from(host.querySelectorAll('button')).find(item => item.textContent?.trim() === text);
  if (!result) throw new Error(`화면에 버튼이 없습니다: ${text}`);
  return result;
}
async function click(text: string) { await act(async () => { button(text).click(); }); }
async function mount() { await act(async () => { root.render(<App />); }); }
async function reachDetail() {
  await click('목적지 찾기');
  await click('병원');
  const destinationButton = Array.from(host.querySelectorAll('button')).find(item => item.querySelector('strong')?.textContent === destination.name)!;
  await act(async () => { destinationButton.click(); });
  const routeButton = Array.from(host.querySelectorAll('button')).find(item => item.querySelector('strong')?.textContent === '시연 1번')!;
  await act(async () => { routeButton.click(); });
  expect(heading()).toBe('이렇게 이동하세요');
}

beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(new Date(NOW)); vi.clearAllMocks();
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: vi.fn() });
  host = document.createElement('div'); document.body.append(host); root = createRoot(host);
  vi.mocked(api.station).mockResolvedValue(envelope({ station: { stationId: 'demo-stop-001', name: '시연 출발 정류장', directionLabel: '병원 방면', region: null, coordinates: null } }));
  vi.mocked(api.destinations).mockResolvedValue(envelope({ destinations: [destination] }));
  vi.mocked(api.search).mockResolvedValue(envelope(search()));
  vi.mocked(api.detail).mockResolvedValue(envelope(detail));
  vi.mocked(api.guidance).mockResolvedValue(envelope(guidance));
  vi.mocked(api.live).mockResolvedValue(envelope(live));
  vi.mocked(api.printGuide).mockResolvedValue(envelope(printed));
});
afterEach(async () => {
  await act(async () => { root.unmount(); }); host.remove();
  vi.useRealTimers(); vi.unstubAllGlobals();
  if (originalScroll) Object.defineProperty(HTMLElement.prototype, 'scrollTo', originalScroll);
  else Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo');
});

describe('연결된 키오스크 사용자 흐름', () => {
  it.each(['live 변경', '검색 만료'])('%s 이후 늦은 인쇄 응답으로 이전 경로가 복구되지 않는다', async reason => {
    if (reason === '검색 만료') vi.mocked(api.search).mockResolvedValue(envelope(search('2026-11-10T04:00:02Z')));
    await mount(); await reachDetail();
    const pendingPrint = deferred<Envelope<PrintData>>();
    // Deliberately allow a late response even after abort: the screen must reject it too.
    vi.mocked(api.printGuide).mockImplementationOnce(() => pendingPrint.promise);
    await click('안내표 인쇄하기');
    const signal = vi.mocked(api.printGuide).mock.calls[0][1]!;
    expect(signal.aborted).toBe(false);
    if (reason === 'live 변경') vi.mocked(api.live).mockRejectedValueOnce(new ApiError('ROUTE_VERSION_CHANGED', 409, '경로가 바뀌었어요.'));
    await act(async () => { await vi.advanceTimersByTimeAsync(reason === 'live 변경' ? 30_000 : 2_000); });
    expect(signal.aborted).toBe(true);
    expect(heading()).toBe('어떤 경로로 이동하시겠어요?');
    expect(host.querySelector('[role="alert"]')?.textContent).toContain('다시 검색');
    await act(async () => { pendingPrint.resolve(envelope(printed)); });
    expect(heading()).toBe('어떤 경로로 이동하시겠어요?');
    expect(host.querySelector('article[aria-label="인쇄용 이동 안내표"]')).toBeNull();
  });

  it('새 목적지 탐색에서 이전 인쇄표를 없애고 고대비 선택을 유지한다', async () => {
    vi.mocked(api.search).mockResolvedValue(envelope(search('2026-11-10T04:00:02Z')));
    await mount(); await click('고대비');
    expect(host.querySelector('[data-theme="contrast"]')).not.toBeNull();
    await reachDetail(); await click('안내표 인쇄하기');
    expect(host.querySelector('article[aria-label="인쇄용 이동 안내표"]')?.textContent).toContain('시연 병원');
    const browserPrint = vi.spyOn(window, 'print').mockImplementation(() => undefined);
    await click('인쇄하기');
    expect(browserPrint).toHaveBeenCalledOnce();
    // Browsers report afterprint on cancellation as well as actual printing.
    await act(async () => { window.dispatchEvent(new Event('afterprint')); });
    expect(heading()).toBe('안내표를 확인해 주세요');
    expect(host.querySelector('main')?.textContent).not.toContain('인쇄가 완료');
    await click('계속 이용하기');
    await click('이전'); await click('이전'); await click('이전');
    expect(heading()).toBe('어디로 가시나요?');
    expect(host.querySelector('article[aria-label="인쇄용 이동 안내표"]')).toBeNull();
    expect(host.querySelector('[data-theme="contrast"]')).not.toBeNull();
    // An old search expiry must not interrupt this new destination session.
    await act(async () => { await vi.advanceTimersByTimeAsync(3_000); });
    expect(host.querySelector('[role="alert"]')).toBeNull();
    expect(heading()).toBe('어디로 가시나요?');
  });

  it('일반 검색 결과가 없고 AI 해석도 실패하면 다시 검색 가능한 빈 결과를 보여준다', async () => {
    vi.mocked(api.destinations).mockResolvedValue(envelope({ destinations: [] }));
    vi.mocked(api.interpret).mockRejectedValue(new ApiError('AI_UNAVAILABLE', 503, '안내 연결 실패'));
    await mount(); await click('목적지 찾기'); await click('장소를 검색하세요');
    await click('1'); await click('검색하기');
    expect(api.interpret).toHaveBeenCalledWith('demo-stop-001', '1', expect.any(AbortSignal));
    expect(host.textContent).toContain('검색어와 일치하는 내용이 없어요');
    expect(host.querySelector('[role="alert"]')).toBeNull();
    await click('다시 검색하기');
    expect(host.querySelector('input[aria-label="목적지 검색"]')).not.toBeNull();
  });
});
