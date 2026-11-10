import { createContext, useCallback, useContext, useEffect, useReducer, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { flushSync } from 'react-dom';
import { api, ApiError, isAbortError } from '../shared/api/client';
import type { Category, Destination, LiveData, Quality, RouteDetail, RouteOption, SelectionRequest } from '../shared/api/types';
import { arrivalLabel, effectiveFreshness, formatDateTime, formatDuration, formatTime, freshnessLabel } from '../shared/api/format';
import { useVoiceGuide } from '../features/voice-guide/useVoiceGuide';
import { PrintDocument } from '../features/print-guide/PrintDocument';
import Keyboard from '../features/destination-search/Keyboard';
import { DEMO_NOTICE, IDLE_COUNTDOWN_SECONDS, IDLE_WARNING_MS, LIVE_REFRESH_MS, ORIGIN_STATION_ID } from '../../config/kiosk';
import { initialState, reducer } from './state';
import type { State } from './state';
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
function QualityInfo({ quality }: { quality: Quality }) {
  return <div className={s.quality}><span>{freshnessLabel(effectiveFreshness(quality))}</span><span>원천 갱신: {quality.sourceUpdatedAt ? formatDateTime(quality.sourceUpdatedAt) : '확인 불가'}</span><span>서버 수집: {quality.fetchedAt ? formatDateTime(quality.fetchedAt) : '확인 불가'}</span></div>;
}
function LiveInfo({ live, retry }: { live: LiveData | null; retry: () => void }) {
  if (!live) return <section className={s.live}><p>도착·운행 정보를 확인할 수 없어요.</p><button onClick={retry}>다시 확인</button></section>;
  return <section className={s.live} aria-label="도착·운행 정보"><h2>도착·운행 정보</h2>{live.arrivals.map(a => <div key={a.segmentId} className={s.arrival}><strong>{arrivalLabel(a)}</strong><p>운행 상태: {a.operationStatus === 'running' ? '운행 중' : a.operationStatus === 'not_running' ? '운행하지 않음' : '확인 불가'}</p><QualityInfo quality={a.dataQuality} /></div>)}<h3>운행 변경 안내</h3><p>{live.serviceChanges.coverageStatus === 'unknown' ? '운행 변경 정보 확인 불가' : live.serviceChanges.items.length ? '다음 변경 내용을 확인해 주세요.' : '조회 범위 안에서 등록된 변경 정보가 없어요.'}</p>{live.serviceChanges.items.map(c => <div key={c.changeId}><strong>{c.title}</strong><p>{c.description}</p></div>)}<QualityInfo quality={live.serviceChanges.dataQuality} /><button onClick={retry}>정보 새로고침</button></section>;
}
function Summary() {
  const state = useContext(StateContext);
  return <div className={s.summary}><div><span>출발 정류장</span><strong>{state.station?.name ?? '확인 중'}</strong></div><Asset file="af0b3.svg" className={s.arrow} /><div><span>목적지</span><strong>{state.destination?.name}</strong></div></div>;
}
function selection(detail: RouteDetail): SelectionRequest {
  return { routeSearchId: detail.routeSearchId, routeOptionId: detail.routeOptionId, expectedRouteSnapshotVersion: detail.routeSnapshotVersion };
}
const categoryNames: Record<Category, string> = { hospital: '병원', market: '시장', terminal: '터미널', station: '역', other: '기타' };

export function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [query, setQuery] = useState('');
  const [clock, setClock] = useState(Date.now());
  const [scale, setScale] = useState(1);
  const [idle, setIdle] = useState<number | null>(null);
  const [doneSeconds, setDoneSeconds] = useState(30);
  const [showVoice, setShowVoice] = useState(false);
  const [sort, setSort] = useState<'server' | 'transfer'>('server');
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
    api.station(ORIGIN_STATION_ID, controller.signal).then(r => patch({ station: r.data.station, dataMode: r.meta.dataMode })).catch(error => { if (!isAbortError(error)) patch({ error: error.message }); });
    const observer = new ResizeObserver(entries => setScale(entries[0].contentRect.width / 1080));
    if (shell.current) observer.observe(shell.current);
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => { controller.abort(); request.current?.abort(); clearPrintListener(); observer.disconnect(); clearInterval(timer); };
  }, [patch, clearPrintListener]);
  useEffect(() => { voice.stop(); setShowVoice(false); shell.current?.querySelector<HTMLElement>('h1')?.focus({ preventScroll: true }); shell.current?.querySelector(`.${s.content}`)?.scrollTo(0, 0); activity.current = Date.now(); }, [state.screen, voice.stop]);
  useEffect(() => { if (!showVoice || voice.speaking) return; const timer = setTimeout(() => setShowVoice(false), 6000); return () => clearTimeout(timer); }, [showVoice, voice.message, voice.speaking]);
  useEffect(() => {
    const touch = () => { if (idle === null) activity.current = Date.now(); };
    window.addEventListener('pointerdown', touch); window.addEventListener('keydown', touch);
    const timer = setInterval(() => {
      if (current.current.screen === 'home' || current.current.screen === 'done' || document.hidden || current.current.busy) return;
      const elapsed = Date.now() - activity.current;
      if (elapsed >= IDLE_WARNING_MS) setIdle(Math.max(0, IDLE_COUNTDOWN_SECONDS - Math.floor((elapsed - IDLE_WARNING_MS) / 1000)));
    }, 1000);
    return () => { clearInterval(timer); window.removeEventListener('pointerdown', touch); window.removeEventListener('keydown', touch); };
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
      patch({ live: r.data });
    } catch (e) {
      if (isAbortError(e) || signal?.aborted || current.current.detail !== detail) return;
      if (e instanceof ApiError && [409, 410].includes(e.status)) invalidate(`${e.message} 다시 검색해 주세요.`);
      else patch({ live: null });
    }
  }, [patch, invalidate]);
  useEffect(() => {
    if (state.screen !== 'detail' || !state.detail) return;
    let controller = new AbortController();
    const update = () => { controller.abort(); controller = new AbortController(); if (!document.hidden) void refreshLive(controller.signal); };
    update(); const timer = setInterval(update, LIVE_REFRESH_MS); document.addEventListener('visibilitychange', update);
    return () => { controller.abort(); clearInterval(timer); document.removeEventListener('visibilitychange', update); };
  }, [state.screen, state.detail, refreshLive]);

  function go(screen: State['screen']) {
    request.current?.abort(); clearPrintListener();
    const clear = ['destinations', 'keyboard', 'results'].includes(screen) ? { search: null, detail: null, live: null, guidance: null, print: null, destination: null } : screen === 'routes' ? { detail: null, live: null, guidance: null, print: null } : {};
    patch({ screen, busy: false, error: '', ...clear });
  }
  function loadCategory(category: Category) {
    void run(async signal => { const r = await api.destinations(ORIGIN_STATION_ID, '', category, signal); if (!signal.aborted) patch({ results: r.data.destinations, resultTitle: categoryNames[category], screen: 'results', dataMode: r.meta.dataMode }); });
  }
  function searchText() {
    if (!query.trim()) { patch({ error: '검색할 장소를 입력해 주세요.' }); return; }
    void run(async signal => {
      const list = await api.destinations(ORIGIN_STATION_ID, query.trim(), undefined, signal);
      let results = list.data.destinations;
      if (!results.length) { try { const interpreted = await api.interpret(ORIGIN_STATION_ID, query.trim(), signal); results = interpreted.data.candidates; } catch (e) { if (signal.aborted || isAbortError(e)) throw e; } }
      if (!signal.aborted) patch({ results, resultTitle: `“${query.trim()}”`, screen: 'results', dataMode: list.meta.dataMode });
    });
  }
  function findRoutes(destination: Destination) {
    void run(async signal => { const r = await api.search(ORIGIN_STATION_ID, destination.destinationId, signal); if (!signal.aborted) { setSort('server'); patch({ destination, search: r.data, detail: null, live: null, guidance: null, print: null, screen: 'routes', dataMode: r.meta.dataMode }); } });
  }
  function chooseRoute(option: RouteOption) {
    if (!state.search) return;
    const search = state.search;
    patch({ print: null });
    void run(async signal => {
      const r = await api.detail(search.routeSearchId, option.routeOptionId, signal);
      if (signal.aborted) return;
      if (r.data.routeSnapshotVersion !== option.routeSnapshotVersion || r.meta.dataMode !== state.dataMode) throw new ApiError('ROUTE_VERSION_CHANGED', 409, '선택한 경로가 변경되었어요.');
      patch({ detail: r.data, guidance: null, live: null, screen: 'detail' });
      const guidance = await api.guidance(selection(r.data), signal);
      if (!signal.aborted && guidance.data.routeSnapshotVersion === r.data.routeSnapshotVersion) patch({ guidance: guidance.data });
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
  const screenSpeech: Record<State['screen'], string> = { home: '현재 정류장에서 목적지까지 가는 버스를 찾아드려요. 목적지 찾기 버튼을 눌러 주세요.', destinations: '어디로 가시나요? 검색하거나 목록에서 목적지를 선택해 주세요.', keyboard: '장소를 입력한 뒤 검색하기를 눌러 주세요.', results: `${state.resultTitle}. 검색 결과 ${state.results.length}건. 찾으시는 장소를 선택해 주세요.`, routes: `이용 가능한 경로 ${state.search?.routeOptions.length ?? 0}개. 이동할 경로를 선택해 주세요.`, detail: '타는 버스와 내리는 정류장을 확인해 주세요.', print: '종이 안내표를 출력해 드릴까요? 인쇄하기를 누르면 브라우저 인쇄 창을 열어요.', done: '인쇄 창에서 출력 여부를 확인해 주세요. 다시 이용하려면 계속 이용하기를 눌러 주세요.' };
  const spokenText = ['detail', 'print', 'done'].includes(state.screen) && state.detail && state.guidance ? state.guidance.steps.map(x => x.text).join(' ') : screenSpeech[state.screen];
  const sortedResults = [...state.results].sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  const options = [...(state.search?.routeOptions ?? [])].sort((a, b) => sort === 'transfer' ? a.transferCount - b.transferCount : 0);
  return <StateContext.Provider value={state}>
    <div ref={shell} data-theme={high ? 'contrast' : 'default'} className={`${s.kiosk} ${high ? s.high : ''}`} style={{ '--design-scale': scale } as CSSProperties}>
      <header className={s.header}><span><Asset file="57066.svg" className={s.logo} />{state.station?.name ?? '정류장 확인 중'}</span><time>{formatTime(new Date(clock).toISOString())}</time></header>
      <main className={`${s.content} ${state.screen === 'home' ? s.home : ''}`} aria-busy={state.busy}>
        {state.screen !== 'home' && state.screen !== 'done' && <><button className={s.back} onClick={() => go(state.screen === 'detail' ? 'routes' : state.screen === 'print' ? 'detail' : 'destinations')}>이전</button><Progress step={step} /></>}
        {state.screen === 'home' && <><img className={s.startBus} src="/assets/b8667.png" alt="파란 버스" /><h1 tabIndex={-1}>현재 정류장에서 목적지까지<br />가는 버스를 찾아드려요</h1><p className={s.homeSubtitle}>목적지를 선택하면 버스를 안내해 드릴게요.</p><Primary disabled={!state.station || state.busy} onClick={() => go('destinations')}>목적지 찾기</Primary></>}
        {state.screen === 'destinations' && <><Heading title="어디로 가시나요?" subtitle="검색하거나 아래 목록에서 선택해 주세요." /><button className={s.searchField} onClick={() => go('keyboard')}><Asset file={high ? '70f47.svg' : 'b06fb.svg'} className={s.searchIcon} />장소를 검색하세요</button><div className={s.categories}>{(['hospital', 'office', 'terminal', 'market', 'station'] as const).map((cat, i) => <button key={cat} className={s.category} disabled={cat === 'office' || state.busy} title={cat === 'office' ? '현재 관공서 분류와 등록된 목적지가 제공되지 않습니다.' : undefined} onClick={() => loadCategory(cat as Category)}><span className={s.categoryIcon}>{cat === 'market' ? <><Asset file={high ? 'df386.svg' : '8d70f.svg'} className={s.marketTop} /><Asset file={high ? '76506.svg' : '9042c.svg'} className={s.marketBottom} /></> : <Asset file={(high ? ['3a98b', 'd780a', '3a4ca', '', '4a3cf'] : ['26a86', '3b151', '62785', '', 'd92b2'])[i] + '.svg'} className={s.categoryArt} />}</span><span>{['병원', '관공서', '터미널', '시장', '역'][i]}</span>{cat === 'office' && <small>준비되지 않음</small>}</button>)}</div></>}
        {state.screen === 'keyboard' && <><Heading title="어디로 가시나요?" subtitle="검색하거나 아래 목록에서 선택해 주세요." /><form onSubmit={e => { e.preventDefault(); searchText(); }}><label className={s.inputWrap}><Asset file="ec4c9.svg" className={s.searchIcon} /><input autoFocus aria-label="목적지 검색" placeholder="장소를 검색하세요" maxLength={100} value={query} onChange={e => setQuery(e.target.value)} /></label><div className={s.keyboard}><Keyboard value={query} onChange={setQuery} onSubmit={searchText} disabled={state.busy} /></div></form></>}
        {state.screen === 'results' && <><Heading title={state.resultTitle} subtitle={noResults ? '검색어와 일치하는 내용이 없어요.' : state.resultTitle.startsWith('“') ? '찾으시는 장소를 선택해 주세요.' : `가고 싶은 ${state.resultTitle}을 선택해 주세요.`} />{noResults ? <div className={s.empty}><img src="/assets/a3ca0.png" alt="회색 버스" /><p>현재 검색어와 일치하는 내용이 없어요.<br />다시 검색해 주세요.</p><div className={s.actions}><Primary secondary onClick={() => go('destinations')}>이전</Primary><Primary onClick={() => go('keyboard')}>다시 검색하기</Primary></div></div> : <><div className={s.listHeading}><span>검색 결과 {state.results.length}건</span><span><button className={s.chip} aria-pressed="true">이름순</button><button className={s.chip} disabled title="좌표·거리 정보가 제공되지 않습니다.">가까운순</button></span></div><div className={s.results}>{sortedResults.map(d => <button key={d.destinationId} className={s.destination} disabled={state.busy} onClick={() => findRoutes(d)}><strong>{d.name}</strong><span>{categoryNames[d.category]}</span></button>)}</div></>}</>}
        {state.screen === 'routes' && <><Heading title="어떤 경로로 이동하시겠어요?" subtitle="이용할 경로를 선택해 주세요." /><Summary /><div className={s.listHeading}><span>이용 가능 경로</span><span><button className={s.chip} disabled title="소요시간 자료가 제공되지 않습니다.">최단 시간</button><button className={s.chip} disabled title="경로별 대기시간 자료가 제공되지 않습니다.">최소 대기</button><button className={s.chip} aria-pressed={sort === 'transfer'} onClick={() => setSort('transfer')}>최소 환승</button></span></div>{noRoutes ? <div className={s.empty}><img src="/assets/a3ca0.png" alt="회색 버스" /><p>{state.search ? '이용 가능한 경로가 없어요.' : '경로를 다시 검색해 주세요.'}</p><Primary disabled={!state.destination || state.busy} onClick={() => state.destination && findRoutes(state.destination)}>경로 다시 검색</Primary></div> : <div className={s.routeList}>{options.map(o => <button key={o.routeOptionId} className={s.routeOption} disabled={state.busy || o.journeyStatus !== 'ready'} onClick={() => chooseRoute(o)}><strong>{o.routeNames.join(' → ')}</strong><div><span>출발 정류장</span>{state.station?.name}</div><Asset file={high ? '4a54e.svg' : 'd7267.svg'} className={s.arrow} /><div><span>목적지</span>{state.destination?.name}</div><Asset file={high ? 'af7e8.svg' : 'ba2a9.svg'} className={s.divider} /><div className={s.duration}>{formatDuration(o.totalDurationSeconds)}<small>환승 {o.transferCount}회</small></div></button>)}</div>}<p className={s.supportNote}>소요시간·대기시간은 제공되지 않아 표시할 수 없어요.</p></>}
        {state.screen === 'detail' && state.detail && <><Heading title="이렇게 이동하세요" subtitle="타는 버스와 내리는 정류장을 확인해 주세요." /><div className={s.detailSummary}><strong>{state.detail.segments.filter(x => x.type === 'bus').map(x => x.routeName).join(' → ')}</strong><Asset file="ad3c1.svg" className={s.arrow} /><strong>{state.destination?.name}</strong></div><section className={s.journey}><h2>경로 안내</h2>{state.detail.segments.map((segment, i) => <div className={s.journeyStep} key={segment.segmentId}><div className={s.stepIcon}><Asset file={segment.type === 'bus' ? high ? '31cc0.svg' : '322d1.svg' : high ? 'bd9ef.svg' : 'e6b90.svg'} className={s.stepArt} /></div><div>{segment.type === 'bus' ? <><strong>{segment.routeName}<br />{segment.boardStation.name} 승차</strong><p>{segment.stopCount}개 정류장 후 {segment.alightStation.name} 하차</p></> : segment.type === 'transfer' ? <strong>{segment.atStation.name}에서 환승</strong> : <><strong>{segment.toLabel}까지 도보 이동</strong><p>거리·소요시간: 확인되지 않음</p></>}{state.guidance?.steps.find(x => x.segmentId === segment.segmentId)?.text && <p className={s.easy}>{state.guidance.steps.find(x => x.segmentId === segment.segmentId)?.text}</p>}</div>{i < state.detail!.segments.length - 1 && <i className={s.connector} />}</div>)}</section><div className={s.actions}><Primary secondary onClick={() => { setShowVoice(true); if (voice.speaking) voice.stop(); else voice.speak(state.dataMode === 'demo' && !spokenText.startsWith(DEMO_NOTICE) ? DEMO_NOTICE + '. ' + spokenText : spokenText); }}>{voice.speaking ? '안내 중지' : '음성으로 듣기'}</Primary><Primary disabled={state.busy || state.detail.journeyStatus !== 'ready'} onClick={preparePrint}>안내표 인쇄하기</Primary></div><LiveInfo live={state.live} retry={() => void refreshLive()} /></>}
        {state.screen === 'print' && state.print && <><Heading title="종이 안내표를 출력해 드릴까요?" subtitle={<>타는 버스와 내리는 정류장을<br />종이로 확인할 수 있어요.</>} /><div className={s.printerArt}><img src="/assets/7144f.png" alt="안내표를 출력하는 키오스크" /></div><div className={s.printSummary}><strong>{state.station?.name} → {state.destination?.name}</strong><p>안내표 생성: {formatDateTime(state.print.generatedAt)}</p><p>브라우저 인쇄 창에서 출력하거나 PDF로 저장할 수 있어요.</p></div><div className={s.actions}><Primary secondary onClick={() => go('detail')}>인쇄 안 함</Primary><Primary disabled={state.busy} onClick={printNow}>인쇄하기</Primary></div></>}
        {state.screen === 'done' && <div className={s.done}><Heading title="안내표를 확인해 주세요" subtitle={<>인쇄 창에서 출력 여부를 확인해 주세요.<br />다시 인쇄할 수도 있어요.</>} /><div className={`${s.printerArt} ${s.completionArt}`}><img src="/assets/7144f.png" alt="안내표를 가져가는 모습" /></div><p><em>{doneSeconds}</em>초 후 처음으로 돌아가요</p><Primary onClick={() => go('print')}>계속 이용하기</Primary><button className={s.textButton} onClick={reset}>이용 마치기</button></div>}
        {state.error && <div className={s.error} role="alert"><p>{state.error}</p><button onClick={() => state.screen === 'home' ? void run(async signal => { const r = await api.station(ORIGIN_STATION_ID, signal); if (!signal.aborted) patch({ station: r.data.station, dataMode: r.meta.dataMode }); }) : patch({ error: '' })}>{state.screen === 'home' ? '정류장 다시 확인' : '확인'}</button></div>}
      </main>
      {state.dataMode === 'demo' && <p className={s.demo}>{DEMO_NOTICE}</p>}
      <nav className={s.navigation} aria-label="공통 메뉴"><button aria-pressed={high} onClick={() => patch({ highContrast: !high })}><Asset file={high ? '1e05d.svg' : '94617.svg'} className={s.navIcon} />고대비</button>{state.screen !== 'home' && <button onClick={reset}><Asset file={high ? 'c25a9.svg' : '5d43b.svg'} className={s.navIcon} />처음으로</button>}<button aria-pressed={voice.speaking} onClick={() => { setShowVoice(true); if (voice.speaking) voice.stop(); else voice.speak(state.dataMode === 'demo' && !spokenText.startsWith(DEMO_NOTICE) ? DEMO_NOTICE + '. ' + spokenText : spokenText); }}><Asset file={high ? 'f17e5.svg' : '889d6.svg'} className={s.navIcon} />{voice.speaking ? '안내 중지' : '음성안내'}</button></nav>
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
