import { createContext, useCallback, useContext, useEffect, useReducer, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { flushSync } from 'react-dom';
import { api, ApiError, isAbortError } from '../shared/api/client';
import type { Category, Destination, LiveData, OptionArrivals, RouteDetail, RouteOption, SearchArrivals, SelectionRequest, RouteSort, PlaceSort } from '../shared/api/types';
import { currentArrival, effectiveFreshness, formatBusLabel, formatDateTime, formatDuration, formatDistance, formatTime } from '../shared/api/format';
import { RouteCards } from '../features/route-search/RouteCards';
import { useVoiceGuide } from '../features/voice-guide/useVoiceGuide';
import { speechTexts } from '../features/voice-guide/speechText';
import { PrintDocument } from '../features/print-guide/PrintDocument';
import Keyboard from '../features/destination-search/Keyboard';
import { IDLE_COUNTDOWN_SECONDS, IDLE_WARNING_MS, LIVE_REFRESH_MS, ORIGIN_STATION_ID, ORIGIN_ADDRESS, ORIGIN_PUBLIC_CODE } from '../../config/kiosk';
import { initialState, reducer } from './state';
import type { State } from './state';
import { CATEGORY_LABELS, SERVICE_REGION, prepareDestinations, displayText, displayDetail, displayGuidance } from '../shared/places';
import { prototypeEnabled, simulatedArrivalLabel } from '../shared/prototypeTiming';
import type { PlaceCategory } from '../shared/places';
import { usePressFeedback } from '../shared/ui/usePressFeedback';
import s from './App.module.css';

const StateContext = createContext<State>(initialState);
function Asset({ file, className = '' }: { file: string; className?: string }) {
  return <span className={`${s.asset} ${className}`} aria-hidden="true"><img src={`/assets/${file}`} alt="" /></span>;
}
function Primary({ children, onClick, disabled = false, secondary = false }: { children: ReactNode; onClick: () => void; disabled?: boolean; secondary?: boolean }) {
  return <button className={`${s.primary} ${secondary ? s.secondary : ''}`} disabled={disabled} onClick={onClick}>{children}</button>;
}
function Progress({ step }: { step: number }) {
  return <div className={s.progress} aria-label={`${step + 1}단계: ${['목적지 선택', '이동 경로 선택', '상세 이동 안내', '안내표 출력'][step]}`}><span>{['목적지 선택', '이동 경로 선택', '상세 이동 안내', '안내표 출력'][step]}</span><div>{[0, 1, 2, 3].map(i => <i key={i} className={i === step ? s.activeDot : ''} />)}</div></div>;
}
function Heading({ title, subtitle }: { title: ReactNode; subtitle: ReactNode }) {
  return <div className={s.heading}><h1 tabIndex={-1}>{title}</h1><p>{subtitle}</p></div>;
}
function LiveInfo({ live, cached, retry, verified, detail }: {
  live: LiveData | null; cached?: OptionArrivals; retry: () => void; verified: boolean; detail: RouteDetail;
}) {
  const {dataMode, liveChecked} = useContext(StateContext);
  const simulate = prototypeEnabled(dataMode);
  if (!verified) return null;
  const buses = detail.segments.filter(segment => segment.type === 'bus');
  const matchingCache = cached?.routeSnapshotVersion === detail.routeSnapshotVersion ? cached : undefined;
  const arrivals = live?.arrivals ?? matchingCache?.arrivals ?? [];
  const rows = buses.map(bus => ({bus, arrival:currentArrival(arrivals.find(value =>
    value.segmentId === bus.segmentId && value.routeId === bus.routeId && value.boardStationId === bus.boardStation.stationId))}));
  const changes = live?.serviceChanges.items.filter(change => effectiveFreshness(change.dataQuality) === 'fresh') ?? [];
  if (!buses.length && !changes.length) return null;
  return <section className={s.live} aria-label="도착·운행 정보">
    <h2>버스 도착 안내</h2>
    {rows.map(({bus, arrival}, index) => <div key={bus.segmentId} className={s.arrival}>
      <p>{bus.routeName} · {bus.boardStation.name}</p>
      <strong>{arrival?.label ?? (!liveChecked && !matchingCache ? '도착 정보 확인 중'
        : simulate ? simulatedArrivalLabel(detail.routeOptionId, index) : '도착 정보 확인 불가')}</strong>
      {arrival?.queriedAt && <p>조회 {formatTime(arrival.queriedAt)}</p>}
    </div>)}
    {rows.slice(1).some(row => row.arrival) && <p>환승 버스의 도착 예정은 환승 정류장의 현재 조회 기준이에요.</p>}
    {changes.map(change => <div key={change.changeId}><strong>{change.title}</strong><p>{change.description}</p></div>)}
    <button onClick={retry}>새로고침</button>
  </section>;
}
function Summary() {
  const state = useContext(StateContext);
  return <div className={s.summary}><div><span>출발 정류장</span><strong>{state.station?.name ?? '현재 정류장'}</strong></div><Asset file="af0b3.svg" className={s.arrow} /><div><span>목적지</span><strong>{state.destination?.name}</strong></div></div>;
}
function JourneySteps({ detail, high }: { detail: RouteDetail; high: boolean }) {
  return <section className={s.journey}>
    <h2>이동 순서</h2>
    <ol className={s.journeyList} role="list">
      {detail.segments.map((segment, index) => (
        <li className={s.journeyStep} key={segment.segmentId}>
          <span className={s.stepIcon} aria-hidden="true">
            <Asset file={segment.type === 'bus' ? high ? '31cc0.svg' : '322d1.svg' : high ? 'bd9ef.svg' : 'e6b90.svg'} className={s.stepArt} />
            <span className={s.stepNumber}>{index + 1}</span>
          </span>
          <div>
            {segment.type === 'bus' && <>
              <h3>{formatBusLabel(segment.routeName)}</h3>
              <p>타는 곳 <strong>{segment.boardStation.name}</strong></p>
              <p>내리는 곳 <strong>{segment.alightStation.name}</strong></p>
              <p>{segment.stopCount}개 정류장 이동</p>
            </>}
            {segment.type === 'transfer' && <>
              <h3>버스를 갈아타세요</h3>
              <p><strong>{segment.atStation.name}</strong></p>
            </>}
            {segment.type === 'walk' && <>
              <h3>{segment.toLabel}까지 걸어가세요</h3>
              {(segment.distanceMeters !== null || segment.durationSeconds !== null) && <p>{[
                segment.distanceMeters !== null ? `도보 ${formatDistance(segment.distanceMeters)}` : null,
                segment.durationSeconds !== null ? `약 ${formatDuration(segment.durationSeconds)}` : null,
              ].filter(Boolean).join(' · ')}</p>}
            </>}
          </div>
        </li>
      ))}
    </ol>
  </section>;
}
function selection(detail: RouteDetail): SelectionRequest {
  return { routeSearchId: detail.routeSearchId, routeOptionId: detail.routeOptionId, expectedRouteSnapshotVersion: detail.routeSnapshotVersion };
}
const categoryNames: Record<Category, string> = { hospital: '병원', market: '시장', terminal: '터미널', station: '역', other: '기타' };

export function App() {
  usePressFeedback();
  const [state, dispatch] = useReducer(reducer, initialState);
  const [query, setQuery] = useState('');
  const [clock, setClock] = useState(Date.now());
  const [scale, setScale] = useState(1);
  const [idle, setIdle] = useState<number | null>(null);
  const [doneSeconds, setDoneSeconds] = useState(30);
  const [showVoice, setShowVoice] = useState(false);
  const [sort, setSort] = useState<RouteSort>('transfers');
  const [placeSort, setPlaceSort] = useState<PlaceSort>('walking');
  const [searchArrivals, setSearchArrivals] = useState<SearchArrivals | null>(null);
  const shell = useRef<HTMLDivElement>(null);
  const activity = useRef(Date.now());
  const request = useRef<AbortController | null>(null);
  const printListener = useRef<(() => void) | null>(null);
  const current = useRef(state); current.current = state;
  const voice = useVoiceGuide();
  const patch = useCallback((value: Partial<State>) => dispatch({ type: 'patch', value }), []);

  const clearPrintListener = useCallback(() => { if (printListener.current) window.removeEventListener('afterprint', printListener.current); printListener.current = null; }, []);
  const invalidate = useCallback((message: string) => { request.current?.abort(); clearPrintListener(); voice.stop(); dispatch({ type: 'invalidate', message }); }, [clearPrintListener, voice.stop]);
  const reset = useCallback(() => { request.current?.abort(); clearPrintListener(); voice.stop(); setQuery(''); setIdle(null); activity.current = Date.now(); dispatch({ type: 'reset' }); }, [clearPrintListener, voice.stop]);
  const run = useCallback(async (task: (signal: AbortSignal) => Promise<void>) => {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    patch({ busy: true, error: '' });
    try { await task(controller.signal); }
    catch (error) {
      if (!controller.signal.aborted && !isAbortError(error)) {
        const message = error instanceof Error ? error.message : '요청을 처리하지 못했어요. 다시 시도해 주세요.';
        if (error instanceof ApiError && [409, 410].includes(error.status)) invalidate(`${message} 경로를 다시 검색해 주세요.`);
        else patch({ error: message });
      }
    } finally { if (request.current === controller) patch({ busy: false }); }
  }, [patch, invalidate]);

  useEffect(() => {
    const controller = new AbortController();
    api.station(ORIGIN_STATION_ID, controller.signal).then(r => patch({ station: { ...r.data.station, name: r.data.station.stationId.startsWith('demo-') ? '현재 정류장' : displayText(r.data.station.name) }, dataMode: r.meta.dataMode })).catch(error => { if (!isAbortError(error)) patch({ error: error.message }); });
    const observer = new ResizeObserver(entries => setScale(entries[0].contentRect.width / 1080));
    if (shell.current) observer.observe(shell.current);
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => { controller.abort(); request.current?.abort(); clearPrintListener(); observer.disconnect(); clearInterval(timer); };
  }, [patch, clearPrintListener]);
  useEffect(() => { voice.stop(); setShowVoice(false); shell.current?.querySelector<HTMLElement>('h1')?.focus({ preventScroll: true }); shell.current?.querySelector(`.${s.content}`)?.scrollTo(0, 0); activity.current = Date.now(); }, [state.screen, voice.stop]);
  useEffect(() => { if (!showVoice || voice.speaking) return; const timer = setTimeout(() => setShowVoice(false), 6000); return () => clearTimeout(timer); }, [showVoice, voice.message, voice.speaking]);
  useEffect(() => {
    const touch = () => { if (idle === null) activity.current = Date.now(); };
    window.addEventListener('pointerdown', touch); window.addEventListener('keydown', touch); window.addEventListener('click', touch);
    const timer = setInterval(() => {
      if (current.current.screen === 'home' || current.current.screen === 'done' || document.hidden || current.current.busy) return;
      const elapsed = Date.now() - activity.current;
      if (elapsed >= IDLE_WARNING_MS) setIdle(Math.max(0, IDLE_COUNTDOWN_SECONDS - Math.floor((elapsed - IDLE_WARNING_MS) / 1000)));
    }, 1000);
    return () => { clearInterval(timer); window.removeEventListener('pointerdown', touch); window.removeEventListener('keydown', touch); window.removeEventListener('click', touch); };
  }, [idle]);
  useEffect(() => { if (idle === 0) reset(); }, [idle, reset]);
  useEffect(() => {
    if (state.screen !== 'done') return;
    setDoneSeconds(30); const timer = setInterval(() => setDoneSeconds(n => n - 1), 1000);
    return () => clearInterval(timer);
  }, [state.screen]);
  useEffect(() => { if (state.screen === 'done' && doneSeconds <= 0) reset(); }, [doneSeconds, state.screen, reset]);
  useEffect(() => {
    if (!state.search || state.screen === 'done' || state.screen === 'home') return;
    if (clock >= Date.parse(state.search.expiresAt)) invalidate('경로 검색의 유효 시간이 지났어요. 경로를 다시 검색해 주세요.');
  }, [clock, state.search, state.screen, invalidate]);

  const refreshLive = useCallback(async (signal?: AbortSignal) => {
    const detail = current.current.detail; if (!detail) return;
    try {
      const r = await api.live(detail.routeSearchId, detail.routeOptionId, signal);
      if (signal?.aborted || current.current.detail !== detail) return;
      if (r.data.routeSnapshotVersion !== detail.routeSnapshotVersion || r.meta.dataMode !== current.current.dataMode) { invalidate('경로 정보가 변경되었어요. 다시 검색해 주세요.'); return; }
      patch({ live: r.data, liveChecked: true });
    } catch (e) {
      if (isAbortError(e) || signal?.aborted || current.current.detail !== detail) return;
      if (e instanceof ApiError && [409, 410].includes(e.status)) invalidate(`${e.message} 다시 검색해 주세요.`);
      else patch({ live: null, liveChecked: true });
    }
  }, [patch, invalidate]);
  useEffect(() => {
    if (state.screen !== 'detail' || !state.detail) return;
    let controller = new AbortController();
    const update = () => { controller.abort(); controller = new AbortController(); if (!document.hidden) void refreshLive(controller.signal); };
    update(); const timer = setInterval(update, LIVE_REFRESH_MS); document.addEventListener('visibilitychange', update);
    return () => { controller.abort(); clearInterval(timer); document.removeEventListener('visibilitychange', update); };
  }, [state.screen, state.detail, refreshLive]);

  useEffect(() => {
    const search = state.search;
    if (state.screen !== 'routes' || state.dataMode !== 'static'
        || !search?.routeOptions.some(option => option.routeNames.length > 0)) return;
    let controller: AbortController | undefined;
    const update = async () => {
      controller?.abort();
      if (document.hidden) return;
      controller = new AbortController();
      const signal = controller.signal;
      const empty = {routeSearchId: search.routeSearchId, options:{}};
      try {
        const result = await api.searchArrivals(search.routeSearchId, signal);
        if (signal.aborted || current.current.search !== search) return;
        const matches = result.meta.dataMode === 'static' && result.data.routeSearchId === search.routeSearchId;
        setSearchArrivals(matches ? result.data : empty);
      } catch (error) {
        if (signal.aborted || current.current.search !== search) return;
        if (error instanceof ApiError && [409, 410].includes(error.status)) invalidate(`${error.message} 다시 검색해 주세요.`);
        else setSearchArrivals(previous => previous?.routeSearchId === search.routeSearchId ? previous : empty);
      }
    };
    void update();
    const timer = setInterval(update, LIVE_REFRESH_MS);
    document.addEventListener('visibilitychange', update);
    return () => {
      controller?.abort();
      clearInterval(timer);
      document.removeEventListener('visibilitychange', update);
    };
  }, [state.screen, state.search, state.dataMode, invalidate]);

  function go(screen: State['screen']) {
    request.current?.abort(); clearPrintListener();
    const clear = ['destinations', 'keyboard'].includes(screen) ? { search: null, detail: null, live: null, guidance: null, print: null, destination: null } : screen === 'results' ? { search:null, detail:null, live:null, guidance:null, print:null } : screen === 'routes' ? { detail: null, live: null, guidance: null, print: null } : {};
    patch({ screen, busy: false, error: '', ...clear });
  }
  function loadCategory(category: PlaceCategory, ordering: PlaceSort = 'walking') {
    patch({ selectedCategory: category, destination:null, results:[] });
    setPlaceSort(ordering);
    const apiCategory: Category = ['office','education','culture'].includes(category) ? 'other' : category === 'shopping' ? 'market' : category as Category;
    void run(async signal => { const r = await api.destinations(ORIGIN_STATION_ID, '', apiCategory, signal, {sort:ordering, ...(category !== 'market' ? {kind:category} : {})}); if (!signal.aborted) patch({ results: prepareDestinations(r.data.destinations, ordering, prototypeEnabled(r.meta.dataMode)), resultTitle: CATEGORY_LABELS[category], screen: 'results', dataMode: r.meta.dataMode }); });
  }
  function searchText(ordering: PlaceSort = 'walking') {
    patch({selectedCategory:null, destination:null});
    setPlaceSort(ordering);
    if (!query.trim()) { patch({ error: '검색할 장소를 입력해 주세요.' }); return; }
    patch({results:[]});
    void run(async signal => {
      const list = await api.destinations(ORIGIN_STATION_ID, query.trim(), undefined, signal, {sort:ordering});
      let results = list.data.destinations;
      if (!results.length) { try { const interpreted = await api.interpret(ORIGIN_STATION_ID, query.trim(), signal); results = interpreted.data.candidates; } catch (e) { if (signal.aborted || isAbortError(e)) throw e; } }
      if (!signal.aborted) patch({ results:prepareDestinations(results, ordering, prototypeEnabled(list.meta.dataMode)), resultTitle: `“${query.trim()}”`, screen: 'results', dataMode: list.meta.dataMode });
    });
  }
  function findRoutes(destination: Destination, ordering: RouteSort = 'transfers') {
    patch({destination, selectedRouteOptionId:null, search:null, detail:null, live:null, guidance:null, print:null});
    setSort(ordering);
    void run(async signal => { const r = await api.search(ORIGIN_STATION_ID, destination.destinationId, signal, ordering); if (!signal.aborted) { patch({ destination, search: r.data, detail: null, live: null, guidance: null, print: null, screen: 'routes', dataMode: r.meta.dataMode }); } });
  }
  function chooseRoute(option: RouteOption) {
    if (!state.search) return;
    const search = state.search;
    patch({ print: null, selectedRouteOptionId:option.routeOptionId });
    void run(async signal => {
      const r = await api.detail(search.routeSearchId, option.routeOptionId, signal);
      if (signal.aborted) return;
      if (r.data.routeSnapshotVersion !== option.routeSnapshotVersion || r.meta.dataMode !== state.dataMode) throw new ApiError('ROUTE_VERSION_CHANGED', 409, '선택한 경로가 변경되었어요.');
      patch({ detail: displayDetail(r.data), guidance: null, live: null, liveChecked: false, screen: 'detail' });
      const guidance = await api.guidance(selection(r.data), signal);
      if (!signal.aborted && guidance.data.routeSnapshotVersion === r.data.routeSnapshotVersion) patch({ guidance: displayGuidance(guidance.data) });
    });
  }
  function preparePrint() {
    if (!state.detail) return;
    void run(async signal => { const r = await api.printGuide(selection(state.detail!), signal); if (!signal.aborted) patch({ print: r.data, screen: 'print' }); });
  }
  function printNow() {
    if (!state.detail) return;
    void run(async signal => {
      const r = await api.printGuide(selection(state.detail!), signal); if (signal.aborted) return;
      flushSync(() => patch({ print: r.data, busy: false }));
      clearPrintListener();
      const after = () => { if (current.current.print?.printGuideId === r.data.printGuideId && current.current.screen === 'print') patch({ screen: 'done' }); clearPrintListener(); };
      printListener.current = after;
      window.addEventListener('afterprint', after, { once: true });
      window.print();
    });
  }
  const high = state.highContrast;
  const noResults = state.screen === 'results' && !state.results.length;
  const noRoutes = state.screen === 'routes' && !state.search?.routeOptions.length;
  const step = state.screen === 'routes' ? 1 : state.screen === 'detail' ? 2 : state.screen === 'print' ? 3 : 0;
  const screenSpeech: Record<State['screen'], string> = { home: '현재 정류장에서 목적지까지 가는 버스를 찾아드려요. 목적지 찾기 버튼을 눌러 주세요.', destinations: '어디로 가시나요? 검색하거나 목록에서 목적지를 선택해 주세요.', keyboard: '장소를 입력한 뒤 검색하기를 눌러 주세요.', results: `${state.resultTitle}. 검색 결과 ${state.results.length}건. 찾으시는 장소를 선택해 주세요.`, routes: `이용 가능한 경로 ${state.search?.routeOptions.length ?? 0}개. 이동할 경로를 선택해 주세요.`, detail: '타는 버스와 내리는 정류장을 확인해 주세요.', print: '종이 안내표를 출력해 드릴까요? 인쇄하기 버튼을 눌러 주세요.', done: '안내표를 확인해 주세요. 다시 인쇄하려면 계속 이용하기를 눌러 주세요.' };
  const spokenText = ['detail', 'print', 'done'].includes(state.screen) && state.detail && state.guidance
    ? speechTexts(state.guidance, state.detail).join(' ') : screenSpeech[state.screen];
  const sortedResults = state.results;
  const distanceNotice = placeSort === 'name' ? '장소명순 · 표시는 길을 따라 걷는 거리예요.' : '현재 정류장에서 길을 따라 걷는 거리순이에요.';
  const options = (state.search?.routeOptions ?? []).map(option => ({...option,routeNames:option.routeNames.map(displayText)}));
  const optionArrivals = searchArrivals?.routeSearchId === state.search?.routeSearchId ? searchArrivals?.options : undefined;
  return <StateContext.Provider value={state}>
    <div ref={shell} data-theme={high ? 'contrast' : 'default'} className={`${s.kiosk} ${high ? s.high : ''}`} style={{ '--design-scale': scale } as CSSProperties}>
      <header className={s.header}><span><Asset file="57066.svg" className={s.logo} />{SERVICE_REGION} 버스 길안내</span><time>{formatTime(new Date(clock).toISOString())}</time></header>
      <main className={`${s.content} ${state.screen === 'home' ? s.home : ''} ${state.screen === 'routes' ? s.routeScreen : ''}`} aria-busy={state.busy}>
        <div className={s.screenTop}>
          {state.screen !== 'home' && state.screen !== 'done' && <button className={s.back} onClick={() => go(state.screen === 'detail' ? 'routes' : state.screen === 'print' ? 'detail' : state.screen === 'routes' && state.results.length ? 'results' : 'destinations')}>이전</button>}
          <div className={s.originLabel} aria-label="현재 버스정류장"><strong>{state.station?.name ?? '정류장 확인 중'} · {ORIGIN_PUBLIC_CODE}</strong><span>{ORIGIN_ADDRESS}</span></div>
        </div>
        {state.screen !== 'home' && state.screen !== 'done' && <Progress step={step} />}
        {state.screen === 'home' && <><img className={s.startBus} src="/assets/b8667.png" alt="파란 버스" /><h1 tabIndex={-1}>현재 정류장에서 목적지까지<br />가는 버스를 찾아드려요</h1><p className={s.homeSubtitle}>목적지를 선택하면 버스를 안내해 드릴게요.</p><Primary disabled={!state.station || state.busy} onClick={() => go('destinations')}>목적지 찾기</Primary></>}
        {state.screen === 'destinations' && <><Heading title="어디로 가시나요?" subtitle="검색하거나 아래 목록에서 선택해 주세요." /><button className={s.searchField} onClick={() => go('keyboard')}><Asset file={high ? '70f47.svg' : 'b06fb.svg'} className={s.searchIcon} />장소를 검색하세요</button><div className={s.categories}>{(['hospital', 'office', 'terminal', 'market', 'station'] as const).map((cat, i) => <button key={cat} className={s.category} disabled={state.busy} aria-pressed={state.selectedCategory === cat} onClick={() => loadCategory(cat)}><span className={s.categoryIcon}>{cat === 'market' ? <><Asset file={high ? 'df386.svg' : '8d70f.svg'} className={s.marketTop} /><Asset file={high ? '76506.svg' : '9042c.svg'} className={s.marketBottom} /></> : <Asset file={(high ? ['3a98b', 'd780a', '3a4ca', '', '4a3cf'] : ['26a86', '3b151', '62785', '', 'd92b2'])[i] + '.svg'} className={s.categoryArt} />}</span><span>{['병원', '관공서', '터미널', '시장·쇼핑', '역'][i]}</span>{state.selectedCategory === cat && <small>선택됨</small>}</button>)}</div><div className={s.extraCategories}>{(['education', 'culture'] as const).map(cat => <button className={s.chip} key={cat} aria-pressed={state.selectedCategory === cat} disabled={state.busy} onClick={() => loadCategory(cat)}>{CATEGORY_LABELS[cat]}</button>)}</div></>}
        {state.screen === 'keyboard' && <><Heading title="어디로 가시나요?" subtitle="검색하거나 아래 목록에서 선택해 주세요." /><form onSubmit={e => { e.preventDefault(); searchText(); }}><label className={s.inputWrap}><Asset file="ec4c9.svg" className={s.searchIcon} /><input autoFocus aria-label="목적지 검색" placeholder="장소를 검색하세요" maxLength={100} value={query} onChange={e => setQuery(e.target.value)} /></label><div className={s.keyboard}><Keyboard value={query} onChange={setQuery} onSubmit={() => searchText()} disabled={state.busy} /></div></form></>}
        {state.screen === 'results' && <><Heading title={state.resultTitle} subtitle={noResults ? '검색어와 일치하는 내용이 없어요.' : state.resultTitle.startsWith('“') ? '찾으시는 장소를 선택해 주세요.' : '가고 싶은 장소를 선택해 주세요.'} />{noResults ? <div className={s.empty}><img src="/assets/a3ca0.png" alt="회색 버스" /><p>현재 검색어와 일치하는 내용이 없어요.<br />다시 검색해 주세요.</p><div className={s.actions}><Primary secondary onClick={() => go('destinations')}>이전</Primary><Primary onClick={() => go('keyboard')}>다시 검색하기</Primary></div></div> : <><div className={s.listHeading}><span>검색 결과 {state.results.length}건</span><span>{([['walking','가까운순'], ['name','이름순']] as const).map(([value,label]) => <button key={value} className={s.chip} disabled={state.busy} aria-pressed={placeSort === value} onClick={() => state.selectedCategory ? loadCategory(state.selectedCategory, value) : searchText(value)}>{label}</button>)}</span></div><p className={s.supportNote}>{distanceNotice}</p><div className={s.results}>{sortedResults.map(d => <button key={d.destinationId} className={s.destination} aria-pressed={state.destination?.destinationId === d.destinationId} disabled={state.busy} onClick={() => findRoutes(d)}><strong>{d.name}</strong><b className={s.placeDistance}>{`도보 ${d.walkingDistanceBasis === 'prototype_estimate' ? '약 ' : ''}${formatDistance(d.walkingDistanceMeters)}`}</b><span>{d.address ?? categoryNames[d.category]}</span>{d.locationNote && <small>{d.locationNote}</small>}</button>)}</div></>}</>}
        {state.screen === 'routes' && <><Heading title="어떤 경로로 이동하시겠어요?" subtitle="이용할 경로를 선택해 주세요." /><Summary />{state.destination && <PlaceDetails destination={state.destination} />}<div className={s.routeSort} aria-label="경로 정렬">{([['transfers','최소 환승'],['walking','최소 도보'],['distance','최단 거리'],['fastest','이동시간순 · 대기 제외']] as const).map(([value,label]) => <button key={value} className={s.chip} aria-pressed={sort === value} disabled={state.busy || noRoutes} onClick={() => state.destination && findRoutes(state.destination, value)}>{label}</button>)}</div>{noRoutes ? <div className={s.empty}><img src="/assets/a3ca0.png" alt="회색 버스" /><p>{state.search ? '이용할 수 있는 경로를 찾지 못했어요.' : '경로를 다시 검색해 주세요.'}</p><Primary disabled={!state.destination || state.busy} onClick={() => state.destination && findRoutes(state.destination, sort)}>경로 다시 검색</Primary></div> : <><RouteCards options={options} origin={state.station?.name ?? '현재 정류장'} destination={state.destination?.name ?? ''} selected={state.selectedRouteOptionId} busy={state.busy} simulate={prototypeEnabled(state.dataMode)} arrivals={optionArrivals} onChoose={chooseRoute} /></>}</>}
        {state.screen === 'detail' && state.detail && <><Heading title="이렇게 이동하세요" subtitle="타는 버스와 내리는 정류장을 확인해 주세요." /><div className={s.detailSummary}><strong>{state.detail.segments.filter(x => x.type === 'bus').map(x => x.routeName).join(' → ') || '도보 이동'}</strong><Asset file="ad3c1.svg" className={s.arrow} /><strong>{state.destination?.name}</strong></div><JourneySteps detail={state.detail} high={high} /><div className={s.actions}><Primary secondary onClick={() => { setShowVoice(true); if (voice.speaking) voice.stop(); else voice.speak(displayText(spokenText)); }}>{voice.speaking ? '안내 중지' : '음성으로 듣기'}</Primary><Primary disabled={state.busy || state.detail.journeyStatus !== 'ready'} onClick={preparePrint}>안내표 인쇄하기</Primary></div><LiveInfo detail={state.detail} live={state.live} cached={optionArrivals?.[state.detail.routeOptionId]} verified={state.dataMode === 'live' || state.dataMode === 'static'} retry={() => void refreshLive()} /></>}
        {state.screen === 'print' && state.print && <><Heading title="종이 안내표를 출력해 드릴까요?" subtitle={<>타는 버스와 내리는 정류장을<br />종이로 확인할 수 있어요.</>} /><div className={s.printerArt}><img src="/assets/7144f.png" alt="안내표를 출력하는 키오스크" /></div><div className={s.printSummary}><strong>{state.station?.name} → {state.destination?.name}</strong><p>인쇄 시각 {formatDateTime(state.print.generatedAt)}</p></div><div className={s.actions}><Primary secondary onClick={() => go('detail')}>인쇄 안 함</Primary><Primary disabled={state.busy} onClick={printNow}>인쇄하기</Primary></div></>}
        {state.screen === 'done' && <div className={s.done}><Heading title="안내표를 확인해 주세요" subtitle={<>필요하면 다시 인쇄할 수 있어요.</>} /><div className={`${s.printerArt} ${s.completionArt}`}><img src="/assets/7144f.png" alt="안내표를 가져가는 모습" /></div><p><em>{doneSeconds}</em>초 후 처음으로 돌아가요</p><Primary onClick={() => go('print')}>계속 이용하기</Primary><button className={s.textButton} onClick={reset}>이용 마치기</button></div>}
        {state.error && <div className={s.error} role="alert"><p>{state.error}</p><button onClick={() => state.screen === 'home' ? void run(async signal => { const r = await api.station(ORIGIN_STATION_ID, signal); if (!signal.aborted) patch({ station: { ...r.data.station, name: r.data.station.stationId.startsWith('demo-') ? '현재 정류장' : displayText(r.data.station.name) }, dataMode: r.meta.dataMode }); }) : patch({ error: '' })}>{state.screen === 'home' ? '정류장 다시 확인' : '확인'}</button></div>}
      </main>
      <nav className={s.navigation} aria-label="공통 메뉴"><button aria-pressed={high} onClick={() => patch({ highContrast: !high })}><Asset file={high ? '1e05d.svg' : '94617.svg'} className={s.navIcon} />고대비</button>{state.screen !== 'home' && <button onClick={reset}><Asset file={high ? 'c25a9.svg' : '5d43b.svg'} className={s.navIcon} />처음으로</button>}<button aria-pressed={voice.speaking} onClick={() => { setShowVoice(true); if (voice.speaking) voice.stop(); else voice.speak(displayText(spokenText)); }}><Asset file={high ? 'f17e5.svg' : '889d6.svg'} className={s.navIcon} />{voice.speaking ? '안내 중지' : '음성안내'}</button></nav>
      {showVoice && voice.message && <div className={s.toast} role="status">{voice.message}</div>}
      {state.busy && <div className={s.loading} role="status"><span />확인하고 있어요…</div>}
      {idle !== null && <IdleDialog count={idle} resume={() => { activity.current = Date.now(); setIdle(null); }} end={reset} />}
    </div>
    {state.print && <PrintDocument snapshot={state.print} originName={state.station?.name ?? ''} destinationName={state.destination?.name ?? ''} />}
  </StateContext.Provider>;
}
function IdleDialog({ count, resume, end }: { count: number; resume: () => void; end: () => void }) {
  const dialog = useRef<HTMLDivElement>(null);
  useEffect(() => { const previous = document.activeElement as HTMLElement; dialog.current?.querySelector('button')?.focus(); return () => previous?.focus(); }, []);
  return <div className={s.overlay}><div ref={dialog} className={s.dialog} role="dialog" aria-modal="true" aria-labelledby="idle-title" onKeyDown={e => { if (e.key === 'Escape') resume(); if (e.key === 'Tab') { const buttons = dialog.current?.querySelectorAll('button'); if (buttons && ((e.shiftKey && document.activeElement === buttons[0]) || (!e.shiftKey && document.activeElement === buttons[1]))) { e.preventDefault(); buttons[e.shiftKey ? 1 : 0].focus(); } } }}><h2 id="idle-title">곧 처음 화면으로 돌아가요</h2><p>움직임이 없어서 종료될 예정이에요.<br />계속 이용하시겠어요?</p><img src="/assets/b49ad.png" alt="시계" /><p><em>{count}</em>초 후 처음으로 돌아가요</p><Primary onClick={resume}>계속 이용하기</Primary><Primary secondary onClick={end}>종료하기</Primary></div></div>;
}

function PlaceDetails({destination}:{destination:Destination}) {
  return <section className={s.placeDetails} aria-label="선택한 장소"><p className={s.selectionLabel}>선택한 장소</p><h2>{destination.name}</h2>{destination.address && <p>{destination.address}</p>}{destination.locationNote && <p>{destination.locationNote}</p>}</section>;
}
