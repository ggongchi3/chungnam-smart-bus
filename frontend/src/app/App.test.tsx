import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../shared/api/client';
import type { Destination, Envelope, GuidanceData, LiveData, PrintData, Quality, RouteDetail, SearchData } from '../shared/api/types';
import { App } from './App';
import { displayText, places } from '../shared/places';

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
function envelope<T>(data: T, dataMode: Envelope<T>['meta']['dataMode'] = 'demo'): Envelope<T> { return { data, error: null, meta: { requestId: 'request-1', generatedAt: NOW, dataMode } }; }
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
  const destinationButton = Array.from(host.querySelectorAll('button')).find(item => item.querySelector('strong')?.textContent === displayText(destination.name))!;
  await act(async () => { destinationButton.click(); });
  const routeButton = Array.from(host.querySelectorAll('button')).find(item => item.querySelector('strong')?.textContent === '1번')!;
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
    expect(host.querySelector('article[aria-label="인쇄용 이동 안내표"]')?.textContent).toContain('병원');
    const browserPrint = vi.spyOn(window, 'print').mockImplementation(() => undefined);
    await click('인쇄하기');
    expect(browserPrint).toHaveBeenCalledOnce();
    // Browsers report afterprint on cancellation as well as actual printing.
    await act(async () => { window.dispatchEvent(new Event('afterprint')); });
    expect(heading()).toBe('안내표를 확인해 주세요');
    expect(host.querySelector('main')?.textContent).not.toContain('인쇄가 완료');
    await click('계속 이용하기');
    await click('이전'); await click('이전'); await click('이전'); await click('이전');
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
    expect(api.interpret).toHaveBeenCalledWith('cheonan-stop-285000686', '1', expect.any(AbortSignal));
    expect(host.textContent).toContain('검색어와 일치하는 내용이 없어요');
    expect(host.querySelector('[role="alert"]')).toBeNull();
    await click('다시 검색하기');
    expect(host.querySelector('input[aria-label="목적지 검색"]')).not.toBeNull();
  });
});


describe('천안 실제 장소 선택', () => {
  it('사용할 수 있는 도착 안내는 유지하고 오래된 조회값과 내부 메타데이터는 숨긴다', async () => {
    vi.mocked(api.search).mockResolvedValue(envelope(search(),'static'));
    vi.mocked(api.detail).mockResolvedValue(envelope(detail,'static'));
    vi.mocked(api.guidance).mockResolvedValue(envelope(guidance,'static'));
    const arrivals: LiveData = {...live,arrivals:[{segmentId:'bus-1',routeId:'route-1',boardStationId:'demo-stop-001',
      arrivalStatus:'available',etaSeconds:180,expectedArrivalAt:null,operationStatus:'unknown',
      dataQuality:{...quality,sourceId:'cheonan-bis-arrival'}}]};
    vi.mocked(api.live).mockResolvedValue(envelope(arrivals,'static'));
    await mount(); await reachDetail();
    expect(host.textContent).toContain('최근 조회 약 3분');
    expect(host.textContent).not.toMatch(/원천 갱신|서버 수집|미제공|공식 조회값/);
    await act(async () => {await vi.advanceTimersByTimeAsync(90_001);});
    expect(host.textContent).not.toContain('최근 조회 약 3분');
    expect(host.querySelector('[aria-label="도착·운행 정보"]')).toBeNull();
  });

  it('백엔드의 거리 정렬을 유지하고 도보 정렬 요청도 서버에 전달한다', async () => {
    const near: Destination = {...destination,destinationId:'near',name:'가까운 병원',distanceMeters:120};
    const far: Destination = {...destination,destinationId:'far',name:'가나다 병원',distanceMeters:450};
    vi.mocked(api.destinations).mockResolvedValue(envelope({destinations:[near,far]}));
    await mount(); await click('목적지 찾기'); await click('병원');
    const names = () => Array.from(host.querySelectorAll('button > strong')).map(e => e.textContent);
    expect(names()).toEqual(['가까운 병원','가나다 병원']);
    expect(host.textContent).toContain('직선 120m');
    await click('도보 거리순');
    expect(api.destinations).toHaveBeenLastCalledWith('cheonan-stop-285000686','', 'hospital', expect.any(AbortSignal),{sort:'walking',kind:'hospital'});
    expect(button('도보 거리순').getAttribute('aria-pressed')).toBe('true');
  });

  it('경로 정렬 변경 시 실제 API 순서를 표시하고 선택 상태를 유지한다', async () => {
    const first = search().routeOptions[0];
    const second = {...first,routeOptionId:'option-2',routeNames:['201번'],walkingDistanceMeters:100};
    vi.mocked(api.search).mockImplementation(async (_origin,_destination,_signal,sort) => envelope({...search(),routeOptions:sort==='walking' ? [second,first] : [first,second]}));
    await mount(); await click('목적지 찾기'); await click('병원');
    await act(async () => { Array.from(host.querySelectorAll('button')).find(b => b.querySelector('strong')?.textContent === displayText(destination.name))!.click(); });
    await click('최소 도보');
    expect(api.search).toHaveBeenLastCalledWith('cheonan-stop-285000686',destination.destinationId,expect.any(AbortSignal),'walking');
    expect(button('최소 도보').getAttribute('aria-pressed')).toBe('true');
    expect(Array.from(host.querySelectorAll('button > strong')).map(e => e.textContent)).toEqual(['201번','1번']);
    expect(host.textContent).not.toMatch(/대기시간 제외|후보 중|비교 경로|원천 갱신|서버 수집/);
  });

  it('관공서 분류와 장소 선택을 기존 API로 전달하고 주소·선택 상태를 유지한다', async () => {
    const office = places.find(p => p.destinationId === 'cheonan-city-hall')!;
    const second = places.find(p => p.destinationId === 'cheonan-tax-office')!;
    vi.mocked(api.destinations).mockResolvedValue(envelope({destinations:[{...office,category:'other'}, {...second,category:'other'}]}));
    vi.mocked(api.search).mockResolvedValue(envelope({...search(),routeOptions:[]}));
    await mount(); await click('목적지 찾기'); await click('관공서');
    expect(api.destinations).toHaveBeenCalledWith('cheonan-stop-285000686','', 'other', expect.any(AbortSignal), {kind:'office',sort:'distance'});
    expect(host.textContent).toContain(office.address);
    const choose = Array.from(host.querySelectorAll('button')).find(b => b.querySelector('strong')?.textContent === office.name)!;
    await act(async () => {choose.click();});
    expect(api.search).toHaveBeenCalledWith('cheonan-stop-285000686', office.destinationId, expect.any(AbortSignal), 'transfers');
    expect(host.querySelector('[aria-label="선택한 장소"]')?.textContent).toContain(office.address);
    expect(host.textContent).toContain('이용할 수 있는 경로를 찾지 못했어요');
    expect(host.textContent).not.toMatch(/시연|테스트용|가상 시설|더미 데이터/);
    expect(host.querySelector('article')).toBeNull();
    await click('이전');
    expect(Array.from(host.querySelectorAll('button[aria-pressed="true"]')).some(b => b.textContent?.includes(office.name))).toBe(true);
    const other = Array.from(host.querySelectorAll('button')).find(b => b.querySelector('strong')?.textContent === second.name)!;
    await act(async () => {other.click();});
    expect(host.querySelector('[aria-label="선택한 장소"]')?.textContent).toContain(second.name);
    await click('이전'); await click('이전');
    expect(Array.from(host.querySelectorAll('button[aria-pressed="true"]')).some(b => b.textContent?.includes('관공서'))).toBe(true);
    await click('시장·쇼핑'); await click('이전');
    expect(Array.from(host.querySelectorAll('button[aria-pressed="true"]')).some(b => b.textContent?.includes('관공서'))).toBe(false);
  });

  it('안내에 불필요한 기술 설명은 화면과 음성에서 생략하고 미검증 도착값을 표시하지 않는다', async () => {
    const technical = '공식 노선 구조 기준 · 평균 이동시간 추정 · 대기시간 제외 · OpenStreetMap contributors';
    vi.mocked(api.search).mockResolvedValue(envelope({...search(),routingNotice:technical,referenceRetrievedAt:NOW}));
    vi.mocked(api.detail).mockResolvedValue(envelope({...detail,routingNotice:technical}));
    await mount(); await reachDetail();
    expect(host.textContent).not.toMatch(/시연|테스트용|가상 시설|더미 데이터/);
    expect(host.textContent).not.toMatch(/실시간 운행 정보가 아직|공식 노선|원천 갱신|서버 수집|참조자료|OpenStreetMap|대기시간 제외/);
    expect(host.querySelector('[aria-label="도착·운행 정보"]')).toBeNull();
    await click('음성으로 듣기');
    expect(voice.speak).toHaveBeenCalledWith(expect.not.stringMatching(/시연|테스트용|가상 시설|더미 데이터/));
  });
});
