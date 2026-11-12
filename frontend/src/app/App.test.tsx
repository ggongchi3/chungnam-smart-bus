import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ORIGIN_STATION_ID } from '../../config/kiosk';
import { api, ApiError } from '../shared/api/client';
import type { Destination, Envelope, GuidanceData, LiveData, PrintData, Quality, RouteDetail, SearchData } from '../shared/api/types';
import { App } from './App';
import { displayText, places } from '../shared/places';
import styles from './App.module.css';

vi.mock('../shared/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../shared/api/client')>();
  return { ...actual, api: {
    station: vi.fn(), destinations: vi.fn(), search: vi.fn(), detail: vi.fn(),
    live: vi.fn(), searchArrivals: vi.fn(), interpret: vi.fn(), guidance: vi.fn(), printGuide: vi.fn(),
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
const routeCards = () => Array.from(host.querySelectorAll<HTMLButtonElement>('[aria-label="이용 가능 경로"] button'));
const routeLines = () => routeCards().map(card => card.querySelector(`.${styles.routeLine}`)?.textContent);
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
  const routeButton = routeCards()[0];
  await act(async () => { routeButton.click(); });
  expect(heading()).toBe('선택한 경로를 확인해 주세요.');
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
  vi.mocked(api.searchArrivals).mockResolvedValue(envelope({routeSearchId:'search-1',options:{}}, 'static'));
  vi.mocked(api.printGuide).mockResolvedValue(envelope(printed));
});
afterEach(async () => {
  await act(async () => { root.unmount(); }); host.remove();
  vi.useRealTimers(); vi.unstubAllGlobals();
  if (originalScroll) Object.defineProperty(HTMLElement.prototype, 'scrollTo', originalScroll);
  else Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo');
});

describe('연결된 키오스크 사용자 흐름', () => {
  it('현재 정류장 번호를 헤더에 표시하고 이동 순서를 그 정류장에서의 승차로 시작한다', async () => {
    const station = { stationId: ORIGIN_STATION_ID, name: '종합터미널', arsId: '685', directionLabel: '정류장 685', region: null,
      coordinates: {latitude:36.8187607, longitude:127.1556582} };
    const hospital = { stationId:'cheonan-stop-285001715', name:'단국대학교병원', arsId:'1715',
      coordinates:{latitude:36.8412905, longitude:127.1743703} };
    const next = { stationId:'cheonan-stop-285000706', name:'나은필병원', arsId:'706',
      coordinates:{latitude:36.822, longitude:127.158} };
    const bus = detail.segments[0];
    if (bus.type !== 'bus') throw new Error('승차 구간이 필요합니다.');
    vi.mocked(api.station).mockResolvedValue(envelope({ station }));
    vi.mocked(api.detail).mockResolvedValue(envelope({ ...detail, originStationId: station.stationId, dataSource:'cheonan-bis-static',
      estimatedTravelSeconds: 660, segments: [
      { ...bus, routeName:'192', boardStation: station, alightStation:hospital, directionLabel:'단국대학교병원 방면',
        boardSequence:20, alightSequence:22, stopCount:2,
        stops:[{...station, sequence:20}, {...next, sequence:21}, {...hospital, sequence:22}],
        path:[station.coordinates, next.coordinates, hospital.coordinates] },
      { type: 'walk', segmentId: 'destination-walk', fromLabel: '병원 앞 정류장', toLabel: '병원', distanceMeters: 170, durationSeconds: 180 },
    ] }));

    await mount();
    expect(host.querySelector('header')?.textContent).toContain('종합터미널 685');
    await reachDetail();
    const steps = host.querySelectorAll('[aria-label="이동 단계"] > li');
    expect(steps[0].textContent).toContain('192번 종합터미널 승차');
    expect(steps[0].textContent).not.toContain('타는 곳');
    expect(host.querySelector('[aria-label="3단계: 상세 이동 안내"]')).not.toBeNull();
    expect(steps[0].textContent).toContain('단국대학교병원 방면');
    expect(steps[0].querySelector(`.${styles.rideCount}`)?.textContent).toBe('2개 정류장 이동');
    expect(steps[0].textContent).not.toContain('정차 순서 보기');
    expect(steps[0].querySelector('details')).toBeNull();
    expect(host.querySelector('[aria-label="버스 운행 경로"]')).toBeNull();
    expect(host.querySelector('[aria-label="선택한 경로"]')?.textContent).toContain('약 11분');
    expect(Array.from(host.querySelectorAll(`.${styles.stepNumber}`), badge => badge.textContent)).toEqual(['1','2','3']);
    expect(steps[1].textContent).toContain('도보 170m · 약 3분');
  });

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
    expect(host.querySelector('main')?.textContent).not.toContain('인쇄 시각');
    expect(host.querySelector('article[aria-label="인쇄용 이동 안내표"]')?.textContent).toContain('인쇄 시각');
    const browserPrint = vi.spyOn(window, 'print').mockImplementation(() => undefined);
    await click('출력하기');
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
    expect(api.interpret).toHaveBeenCalledWith('cheonan-stop-285000685', '1', expect.any(AbortSignal));
    expect(host.textContent).toContain('검색어와 일치하는 내용이 없어요');
    expect(host.querySelector('[role="alert"]')).toBeNull();
    await click('다시 검색하기');
    expect(host.querySelector('input[aria-label="목적지 검색"]')).not.toBeNull();
  });
});


describe('천안 실제 장소 선택', () => {
  it('최근 도착 조회값은 표시하고 오래되면 확인 불가와 재조회 버튼을 보여준다', async () => {
    vi.mocked(api.search).mockResolvedValue(envelope(search(),'live'));
    vi.mocked(api.detail).mockResolvedValue(envelope(detail,'live'));
    vi.mocked(api.guidance).mockResolvedValue(envelope(guidance,'live'));
    const arrivals: LiveData = {...live,arrivals:[{segmentId:'bus-1',routeId:'route-1',boardStationId:'demo-stop-001',
      arrivalStatus:'available',etaSeconds:180,expectedArrivalAt:null,operationStatus:'unknown',
      dataQuality:{...quality,sourceId:'cheonan-bis-arrival'}}]};
    vi.mocked(api.live).mockResolvedValue(envelope(arrivals,'live'));
    await mount(); await reachDetail();
    expect(host.textContent).toContain('최근 조회 약 3분');
    expect(host.textContent).not.toMatch(/원천 갱신|서버 수집|미제공|공식 조회값/);
    await act(async () => {await vi.advanceTimersByTimeAsync(90_001);});
    expect(host.textContent).not.toContain('최근 조회 약 3분');
    expect(host.querySelector('[aria-label="선택한 경로"]')?.textContent).toContain('도착 정보 확인 불가');
    expect(button('새로고침')).toBeTruthy();
  });

  it('직선거리가 아닌 실제 보행 경로 거리로 정렬하고 서버에도 같은 기준을 요청한다', async () => {
    const near: Destination = {...destination,destinationId:'near',name:'가까운 병원',distanceMeters:120,walkingDistanceMeters:600};
    const far: Destination = {...destination,destinationId:'far',name:'가나다 병원',distanceMeters:450,walkingDistanceMeters:500};
    vi.mocked(api.destinations).mockResolvedValue(envelope({destinations:[near,far]}));
    await mount(); await click('목적지 찾기'); await click('병원');
    const names = () => Array.from(host.querySelectorAll('button > strong')).map(e => e.textContent);
    expect(names()).toEqual(['가나다 병원','가까운 병원']);
    expect(host.textContent).toContain('도보 600m');
    expect(host.textContent).toContain('현재 정류장에서 길을 따라 걷는 거리순');
    await click('가까운순');
    expect(api.destinations).toHaveBeenLastCalledWith('cheonan-stop-285000685','', 'hospital', expect.any(AbortSignal),{sort:'walking',kind:'hospital'});
    expect(button('가까운순').getAttribute('aria-pressed')).toBe('true');
    expect(host.textContent).not.toContain('직선');
    expect(host.textContent).toContain('도보 500m');
  });

  it.each([
    ['transfers', '최소 환승'], ['distance', '최단 거리'],
  ] as const)('%s 정렬은 선택 즉시 반영하고 서버가 계산한 순서를 사용한다', async (sort, label) => {
    const first = search().routeOptions[0];
    const second = {...first,routeOptionId:'option-2',routeNames:['201번']};
    vi.mocked(api.search).mockResolvedValueOnce(envelope({...search(),routeOptions:[first,second]}, 'static'));
    await mount(); await click('목적지 찾기'); await click('병원');
    await act(async () => {Array.from(host.querySelectorAll('button')).find(b => b.querySelector('strong')?.textContent === displayText(destination.name))!.click();});
    const pending = deferred<Envelope<SearchData>>();
    vi.mocked(api.search).mockImplementationOnce(() => pending.promise);
    await click(label);
    expect(button(label).getAttribute('aria-pressed')).toBe('true');
    expect(button(label).disabled).toBe(true);
    expect(api.search).toHaveBeenLastCalledWith('cheonan-stop-285000685',destination.destinationId,expect.any(AbortSignal),sort);
    await act(async () => {pending.resolve(envelope({...search(),routeOptions:[second,first]}, 'static'));});
    expect(routeLines()).toEqual(['직행201번', '직행1번']);
  });

  it('대기 자료가 없는 경우 이동시간만 추정하고 선택을 유지한다', async () => {
    const option = {...search().routeOptions[0],estimatedTravelSeconds:900,walkingDistanceMeters:240,totalDistanceMeters:3400,
      boardStation:{stationId:'start',name:'종합터미널'},alightStation:{stationId:'end',name:'병원 앞'},
      features:['최소 이동시간 · 대기 제외']};
    vi.mocked(api.search).mockResolvedValue(envelope({...search(),routeOptions:[option]}, 'static'));
    await mount(); await click('목적지 찾기'); await click('병원');
    await act(async () => {Array.from(host.querySelectorAll('button')).find(b => b.querySelector('strong')?.textContent === displayText(destination.name))!.click();});
    const card = routeCards()[0];
    expect(card.textContent).toContain('종합터미널병원 앞');
    expect(card.textContent).toContain('직행1번');
    expect(card.textContent).toContain('도착 정보 확인 불가');
    expect(card.textContent).toContain('약 15분');
    expect(card.textContent).toContain('이 경로 선택하기');
    const pending = deferred<Envelope<RouteDetail>>();
    vi.mocked(api.detail).mockImplementationOnce(() => pending.promise);
    await act(async () => {card.click();});
    expect(card.getAttribute('aria-pressed')).toBe('true');
    expect(card.disabled).toBe(true);
    vi.mocked(api.guidance).mockResolvedValue(envelope(guidance, 'static'));
    vi.mocked(api.live).mockResolvedValue(envelope(live, 'static'));
    await act(async () => {pending.resolve(envelope(detail, 'static'));});
    expect(heading()).toBe('선택한 경로를 확인해 주세요.');
    expect(host.querySelector('[aria-label="선택한 경로"]')?.textContent).toContain('도착 정보 확인 불가');
    await act(async () => {await vi.advanceTimersByTimeAsync(30_000);});
    expect(host.querySelector('[aria-label="선택한 경로"]')?.textContent).toContain('도착 정보 확인 불가');
  });

  it('환승 카드와 상세에서 첫 버스의 실제 도착값을 표시한다', async () => {
    const first = detail.segments[0];
    if (first.type !== 'bus') throw new Error('버스 테스트 구간이 필요합니다');
    const second = {...first, segmentId:'bus-2', routeId:'route-2', routeName:'2번', boardStation:first.alightStation};
    const option = {...search().routeOptions[0], routeNames:['1번','2번'], transferCount:1,
      boardStation:first.boardStation, transferStations:[second.boardStation], alightStation:second.alightStation,
      directionLabels:['천안역 방면','병원 방면']};
    const observed: LiveData['arrivals'] = [{
      segmentId:first.segmentId, routeId:first.routeId, boardStationId:first.boardStation.stationId,
      arrivalStatus:'available', etaSeconds:120, expectedArrivalAt:'2026-11-10T04:02:00Z', operationStatus:'unknown',
      dataQuality:{...quality, sourceId:'cheonan-bis-arrival'},
    }, {
      segmentId:second.segmentId, routeId:second.routeId, boardStationId:second.boardStation.stationId,
      arrivalStatus:'unavailable', etaSeconds:null, expectedArrivalAt:null, operationStatus:'unknown', dataQuality:quality,
    }];
    vi.mocked(api.search).mockResolvedValue(envelope({...search(),routeOptions:[option]}, 'static'));
    vi.mocked(api.searchArrivals).mockResolvedValue(envelope({routeSearchId:'search-1',options:{
      'option-1':{routeSnapshotVersion:'v1',arrivals:observed},
    }}, 'static'));
    vi.mocked(api.detail).mockResolvedValue(envelope({...detail,segments:[first,second]}, 'static'));
    vi.mocked(api.live).mockResolvedValue(envelope({...live,arrivals:observed}, 'static'));
    await mount(); await click('목적지 찾기'); await click('병원');
    await act(async () => {Array.from(host.querySelectorAll('button')).find(b => b.querySelector('strong')?.textContent === displayText(destination.name))!.click();});
    const card = routeCards()[0];
    expect(api.searchArrivals).toHaveBeenCalledWith('search-1', expect.any(AbortSignal));
    expect(card.textContent).toContain('환승 1회1번2번');
    expect(card.textContent).toContain('천안역 방면');
    expect(card.textContent).toContain('환승 · 병원 방면');
    expect(card.textContent).toContain('최근 조회 약 2분 후 도착 예정');
    await act(async () => {card.click();});
    const panel = host.querySelector('[aria-label="선택한 경로"]');
    expect(panel?.textContent).toContain('최근 조회 약 2분 후 도착 예정');
    expect(panel?.textContent).toContain('새로고침');
    expect(panel?.textContent).not.toContain('시연');
    await act(async () => {await vi.advanceTimersByTimeAsync(90_001);});
    expect(panel?.textContent).not.toContain('최근 조회 약 2분 후 도착 예정');
    expect(panel?.textContent?.match(/도착 정보 확인 불가/g)).toHaveLength(1);
  });

  it('정렬 요청 실패 시 이전 경로를 새 순위로 표시하지 않고 같은 기준으로 재시도한다', async () => {
    await mount(); await click('목적지 찾기'); await click('병원');
    await act(async () => {Array.from(host.querySelectorAll('button')).find(b => b.querySelector('strong')?.textContent === displayText(destination.name))!.click();});
    vi.mocked(api.search).mockRejectedValueOnce(new ApiError('NETWORK_ERROR',0,'연결을 확인해 주세요.',true));
    await click('최단 거리');
    expect(host.querySelector('[role="alert"]')?.textContent).toContain('연결을 확인해 주세요');
    expect(routeCards()).toHaveLength(0);
    await click('경로 다시 검색');
    expect(api.search).toHaveBeenLastCalledWith('cheonan-stop-285000685',destination.destinationId,expect.any(AbortSignal),'distance');
  });

  it('도보만 있는 후보에는 이동시간을 표시하고 버스 도착 안내를 생략한다', async () => {
    const option = {...search().routeOptions[0],routeNames:[],estimatedTravelSeconds:240,walkingDistanceMeters:250,totalDistanceMeters:250};
    vi.mocked(api.search).mockResolvedValue(envelope({...search(),routeOptions:[option]}, 'static'));
    await mount(); await click('목적지 찾기'); await click('병원');
    await act(async () => {Array.from(host.querySelectorAll('button')).find(b => b.querySelector('strong')?.textContent === displayText(destination.name))!.click();});
    const card = routeCards()[0];
    expect(card.textContent).toContain('현재 정류장에서 목적지까지 도보 이동');
    expect(card.textContent).toContain('약 4분');
    expect(card.textContent).not.toContain('버스 도착 예정');
    expect(card.textContent).not.toContain('승하차 정류장');
  });

  it.each(['routeId','boardStationId'] as const)('선택 구간과 %s가 다른 도착값은 노출하지 않는다', async field => {
    vi.mocked(api.search).mockResolvedValue(envelope(search(),'live'));
    vi.mocked(api.detail).mockResolvedValue(envelope(detail,'live'));
    vi.mocked(api.guidance).mockResolvedValue(envelope(guidance,'live'));
    vi.mocked(api.live).mockResolvedValue(envelope({...live,arrivals:[{segmentId:'bus-1',routeId:'route-1',boardStationId:'demo-stop-001',
      arrivalStatus:'available',etaSeconds:180,expectedArrivalAt:null,operationStatus:'unknown',
      dataQuality:{...quality,sourceId:'cheonan-bis-arrival'},[field]:'other'}]},'live'));
    await mount(); await reachDetail();
    expect(host.textContent).not.toContain('최근 조회 약 3분');
    expect(host.querySelector('[aria-label="선택한 경로"]')?.textContent).toContain('도착 정보 확인 불가');
  });

  it('같은 경로는 한 카드로 표시하고 최소 대기에서 먼저 오는 버스를 선택할 수 있다', async () => {
    const first = {...search().routeOptions[0], pathGroupId:'path-1', routeNames:['72'],
      boardStation:{stationId:'demo-stop-001', name:'종합터미널'},
      alightStation:{stationId:'demo-stop-003', name:'병원 앞'}};
    const alternate = {...first, routeOptionId:'option-2', routeNames:['74']};
    const other = {...first, routeOptionId:'option-3', pathGroupId:'path-2', routeNames:['201']};
    const sameCard = {...first, routeOptionId:'option-4', pathGroupId:'path-3'};
    vi.mocked(api.search).mockResolvedValue(envelope({...search(),routeOptions:[first,alternate,other,sameCard]}, 'static'));
    const observed = (routeId: string, etaSeconds: number) => ({
      routeSnapshotVersion:'v1', arrivals:[{
        segmentId:'bus-1', routeId, boardStationId:'demo-stop-001', arrivalStatus:'available' as const,
        etaSeconds, expectedArrivalAt:null, operationStatus:'unknown' as const,
        dataQuality:{...quality,sourceId:'cheonan-bis-arrival'},
      }],
    });
    vi.mocked(api.searchArrivals).mockResolvedValue(envelope({routeSearchId:'search-1',options:{
      'option-1':observed('route-72', 300),
      'option-2':observed('route-74', 60),
      'option-3':observed('route-201', 120),
    }}, 'static'));
    await mount(); await click('목적지 찾기'); await click('병원');
    await act(async () => { Array.from(host.querySelectorAll('button')).find(b => b.querySelector('strong')?.textContent === displayText(destination.name))!.click(); });
    expect(routeLines()).toEqual(['직행72번', '직행201번']);
    await click('최소 대기');
    expect(api.search).toHaveBeenCalledOnce();
    expect(button('최소 대기').getAttribute('aria-pressed')).toBe('true');
    expect(routeLines()).toEqual(['직행74번', '직행201번']);
    vi.mocked(api.detail).mockResolvedValueOnce(envelope({...detail, routeOptionId:'option-2'}, 'static'));
    vi.mocked(api.live).mockResolvedValueOnce(envelope(live, 'static'));
    await act(async () => { routeCards()[0].click(); });
    expect(api.detail).toHaveBeenLastCalledWith('search-1', 'option-2', expect.any(AbortSignal));
    await click('이전');
    await act(async () => {await vi.advanceTimersByTimeAsync(90_001);});
    expect(routeLines()).toEqual(['직행72번', '직행201번']);
    expect(routeCards()[0].textContent).toContain('도착 정보 확인 불가');
  });

  it('관공서 분류와 장소 선택을 기존 API로 전달하고 주소·선택 상태를 유지한다', async () => {
    const office = places.find(p => p.destinationId === 'cheonan-city-hall')!;
    const second = places.find(p => p.destinationId === 'cheonan-tax-office')!;
    vi.mocked(api.destinations).mockResolvedValue(envelope({destinations:[{...office,category:'other'}, {...second,category:'other'}]}));
    vi.mocked(api.search).mockResolvedValue(envelope({...search(),routeOptions:[]}));
    await mount(); await click('목적지 찾기'); await click('관공서');
    expect(api.destinations).toHaveBeenCalledWith('cheonan-stop-285000685','', 'other', expect.any(AbortSignal), {kind:'office',sort:'walking'});
    expect(host.textContent).toContain(office.address);
    const choose = Array.from(host.querySelectorAll('button')).find(b => b.querySelector('strong')?.textContent === office.name)!;
    await act(async () => {choose.click();});
    expect(api.search).toHaveBeenCalledWith('cheonan-stop-285000685', office.destinationId, expect.any(AbortSignal), 'transfers');
    expect(host.querySelector('[aria-label="선택한 장소"]')?.textContent).toContain(office.name);
    expect(host.querySelector('main')?.textContent).not.toContain(office.address);
    expect(host.textContent).toContain('이용할 수 있는 경로를 찾지 못했어요');
    expect(host.textContent).not.toMatch(/시연|테스트용|가상 시설|더미 데이터/);
    expect(host.querySelector('article')).toBeNull();
    await click('이전');
    expect(Array.from(host.querySelectorAll('button[aria-pressed="true"]')).some(b => b.textContent?.includes(office.name))).toBe(true);
    const other = Array.from(host.querySelectorAll('button')).find(b => b.querySelector('strong')?.textContent === second.name)!;
    await act(async () => {other.click();});
    expect(api.search).toHaveBeenLastCalledWith(ORIGIN_STATION_ID, second.destinationId, expect.any(AbortSignal), 'transfers');
    expect(host.querySelector('[aria-label="선택한 장소"]')?.textContent).toContain(second.name);
    await click('이전'); await click('이전');
    expect(Array.from(host.querySelectorAll('button[aria-pressed="true"]')).some(b => b.textContent?.includes('관공서'))).toBe(true);
    await click('시장·쇼핑'); await click('이전');
    expect(Array.from(host.querySelectorAll('button[aria-pressed="true"]')).some(b => b.textContent?.includes('관공서'))).toBe(false);
  });

  it('경로 자료 안내 영역을 표시하지 않고 음성 안내는 이동 단계에 집중한다', async () => {
    const technical = '공식 노선 구조 기준 · 평균 이동시간 추정 · 대기시간 제외 · OpenStreetMap contributors';
    vi.mocked(api.search).mockResolvedValue(envelope({...search(),routingNotice:technical,referenceRetrievedAt:NOW}));
    vi.mocked(api.detail).mockResolvedValue(envelope({...detail,routingNotice:technical}));
    await mount(); await reachDetail();
    expect(host.textContent).not.toMatch(/시연|테스트용|가상 시설|더미 데이터/);
    expect(host.querySelector('[aria-label="경로 자료 안내"]')).toBeNull();
    expect(host.textContent).not.toContain('정적 노선 기반 경로예요');
    expect(host.textContent).not.toContain('경로 자료와 시간 기준');
    expect(host.querySelector('[aria-label="선택한 경로"]')?.textContent).not.toContain('도착 정보');
    await click('음성안내');
    expect(voice.speak).toHaveBeenCalledWith(expect.not.stringMatching(/시연|테스트용|가상 시설|더미 데이터/));
  });
});
