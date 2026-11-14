import { createContext, useCallback, useContext, useEffect, useReducer, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { flushSync } from 'react-dom';
import { api, ApiError, isAbortError } from '../shared/api/client';
import type { Category, ConversationData, Destination, LiveData, OptionArrivals, RouteDetail, RouteOption, SearchArrivals, SelectionRequest, RouteSort, PlaceSort } from '../shared/api/types';
import { currentArrival, effectiveFreshness, formatBusLabel, formatDuration, formatDistance, formatStation, formatTime } from '../shared/api/format';
import { RouteCardHeader, RouteCards } from '../features/route-search/RouteCards';
import { useVoiceGuide } from '../features/voice-guide/useVoiceGuide';
import { routeSpeech, speechTexts } from '../features/voice-guide/speechText';
import { PrintDocument } from '../features/print-guide/PrintDocument';
import Keyboard from '../features/destination-search/Keyboard';
import { SpeechInput } from '../features/ai-helper/SpeechInput';
import { MicrophoneIcon } from '../features/ai-helper/MicrophoneIcon';
import { IDLE_COUNTDOWN_SECONDS, IDLE_WARNING_MS, LIVE_REFRESH_MS, ORIGIN_STATION_ID, ORIGIN_NAME, ORIGIN_PUBLIC_CODE } from '../../config/kiosk';
import { initialState, reducer } from './state';
import type { State } from './state';
import { CATEGORY_LABELS, prepareDestinations, displayText, displayDetail, displayGuidance } from '../shared/places';
import { prototypeEnabled, simulatedArrivalLabel } from '../shared/prototypeTiming';
import type { PlaceCategory } from '../shared/places';
import { usePressFeedback } from '../shared/ui/usePressFeedback';
import s from './App.module.css';

const StateContext = createContext<State>(initialState);
function Asset({ file, className = '' }: { file: string; className?: string }) {
  return <span className={`${s.asset} ${className}`} aria-hidden="true"><img src={`/assets/${file}`} alt="" /></span>;
}
function Primary({ children, onClick, disabled = false, secondary = false }: { children: ReactNode; onClick: () => void; disabled?: boolean; secondary?: boolean }) {
  return <button type="button" className={`${s.primary} ${secondary ? s.secondary : ''}`} disabled={disabled} onClick={onClick}>{children}</button>;
}
function Progress({ step }: { step: number }) {
  return <div className={s.progress} aria-label={`${step + 1}단계: ${['목적지 선택', '이동 경로 선택', '상세 이동 안내', '안내표 출력'][step]}`}><span>{['목적지 선택', '이동 경로 선택', '상세 이동 안내', '안내표 출력'][step]}</span><div>{[0, 1, 2, 3].map(i => <i key={i} className={i === step ? s.activeDot : ''} />)}</div></div>;
}
function Heading({ title, subtitle }: { title: ReactNode; subtitle: ReactNode }) {
  return <div className={s.heading}><h1 tabIndex={-1}>{title}</h1><p>{subtitle}</p></div>;
}
function SelectedRoute({ live, cached, retry, verified, detail }: {
  live: LiveData | null; cached?: OptionArrivals; retry: () => void; verified: boolean; detail: RouteDetail;
}) {
  const {dataMode, liveChecked} = useContext(StateContext);
  const simulate = prototypeEnabled(dataMode);
  const buses = detail.segments.filter(segment => segment.type === 'bus');
  const matchingCache = cached?.routeSnapshotVersion === detail.routeSnapshotVersion ? cached : undefined;
  const arrivals = live?.arrivals ?? matchingCache?.arrivals ?? [];
  const first = buses[0];
  const arrival = first && verified ? currentArrival(arrivals.find(value =>
    value.segmentId === first.segmentId && value.routeId === first.routeId && value.boardStationId === first.boardStation.stationId)) : null;
  const arrivalText = !first || !verified ? undefined : arrival?.label ?? (!liveChecked && !matchingCache ? '도착 정보 확인 중'
    : simulate ? simulatedArrivalLabel(detail.routeOptionId, 0) : '도착 정보 확인 불가');
  const changes = live?.serviceChanges.items.filter(change => effectiveFreshness(change.dataQuality) === 'fresh') ?? [];
  const duration = detail.estimatedTravelSeconds ?? null;
  return <section className={s.selectedRoute} aria-label="선택한 경로">
    <RouteCardHeader names={buses.map(bus => bus.routeName)} transferCount={Math.max(0, buses.length - 1)}
      duration={duration} arrival={arrivalText} action={verified && first && <button className={s.refreshRoute} onClick={retry}>
        <Asset file="fcc0c.svg" className={s.refreshIcon} />새로고침
      </button>} />
    {changes.map(change => <div key={change.changeId} className={s.serviceChange}><strong>{change.title}</strong><p>{change.description}</p></div>)}
  </section>;
}
function Summary() {
  const state = useContext(StateContext);
  return <div className={s.summary}>
    <div className={s.summaryRoute}>
      <div>
        <span>출발 정류장</span>
        <strong>{state.station?.name ?? '현재 정류장'}{state.station?.stationId === ORIGIN_STATION_ID && <><br />{ORIGIN_PUBLIC_CODE}</>}</strong>
      </div>
      <Asset file={state.highContrast ? '4a54e.svg' : 'af0b3.svg'} className={s.arrow} />
      <div>
        <span>목적지</span>
        <strong>{state.destination?.name}</strong>
      </div>
    </div>
  </div>;
}
function JourneySteps({ detail, high }: { detail: RouteDetail; high: boolean }) {
  const busIcon = high ? '31cc0.svg' : '322d1.svg';
  const pinIcon = high ? 'bd9ef.svg' : 'e6b90.svg';
  const transfers = detail.segments.filter(segment => segment.type === 'transfer');
  let step = 0;
  return <section className={s.journey}>
    <h2>경로 안내</h2>
    <ol className={s.journeyList} role="list" aria-label="이동 단계">
      {detail.segments.filter(segment => segment.type !== 'transfer').map(segment => {
        const boardStep = ++step;
        const alightStep = segment.type === 'bus' ? ++step : undefined;
        const transfer = transfers.some(item => item.toSegmentId === segment.segmentId);
        return (
          <li className={s.journeyStep} key={segment.segmentId}>
            <div className={s.journeyEvent}>
              <span className={s.stepIcon} aria-hidden="true">
                <Asset file={segment.type === 'bus' ? busIcon : pinIcon} className={s.stepArt} />
                <span className={s.stepNumber}>{boardStep}</span>
              </span>
              <div>
                {segment.type === 'bus' && <>
                  <h3>{formatBusLabel(segment.routeName).replace(/ 버스$/, '')} {transfer ? formatStation(segment.boardStation) : segment.boardStation.name} 승차</h3>
                  {segment.directionLabel && <p className={s.direction}>운행 방향 <strong>{segment.directionLabel}</strong></p>}
                </>}
                {segment.type === 'walk' && <>
                  <h3>{segment.toLabel}까지 걸어가세요</h3>
                  {(segment.distanceMeters !== null || segment.durationSeconds !== null) && <p>{[
                    segment.distanceMeters !== null ? `도보 ${formatDistance(segment.distanceMeters)}` : null,
                    segment.durationSeconds !== null ? `약 ${formatDuration(segment.durationSeconds)}` : null,
                  ].filter(Boolean).join(' · ')}</p>}
                </>}
              </div>
            </div>
            {segment.type === 'bus' && <>
              <p className={s.rideCount}>{segment.stopCount}개 정류장 이동</p>
              <div className={s.journeyEvent}>
                <span className={s.stepIcon} aria-hidden="true"><Asset file={pinIcon} className={s.stepArt} /><span className={s.stepNumber}>{alightStep}</span></span>
                <div><h3>{formatStation(segment.alightStation)} 하차</h3><p>내리는 곳</p></div>
              </div>
            </>}
          </li>
        );
      })}
    </ol>
  </section>;
}
function selection(detail: RouteDetail): SelectionRequest {
  return { routeSearchId: detail.routeSearchId, routeOptionId: detail.routeOptionId, expectedRouteSnapshotVersion: detail.routeSnapshotVersion };
}
const categoryNames: Record<Category, string> = { hospital: '병원', market: '시장', terminal: '터미널', station: '역', other: '기타' };
type RouteOrder = RouteSort | 'waiting';
const standardSorts = [['transfers', '최소 환승'], ['waiting', '최소 대기'], ['distance', '최단 거리']] as const;
const assistantSorts = [['walking', '최소 도보'], ['transfers', '최소 환승'], ['fastest', '최소 이동시간']] as const;
const assistantExamples = [
  '단국대학교 천안캠퍼스 가는데 많이 안 걷고 싶어요',
  '중앙시장 가고싶어요',
];

export function App() {
  usePressFeedback();
  const [state, dispatch] = useReducer(reducer, initialState);
  const [query, setQuery] = useState('');
  const [assistantText, setAssistantText] = useState('');
  const [conversation, setConversation] = useState<ConversationData | null>(null);
  const routePreference = state.assistant ? conversation?.sort : null;
  const [listening, setListening] = useState(false);
  const [showAssistantKeyboard, setShowAssistantKeyboard] = useState(false);
  const [showOtherRoutes, setShowOtherRoutes] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const [scale, setScale] = useState(1);
  const [idle, setIdle] = useState<number | null>(null);
  const [doneSeconds, setDoneSeconds] = useState(30);
  const [showVoice, setShowVoice] = useState(false);
  const [sort, setSort] = useState<RouteOrder>('transfers');
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
  const reset = useCallback(() => {
    request.current?.abort(); clearPrintListener(); voice.stop();
    setQuery(''); setAssistantText(''); setConversation(null); setListening(false);
    setShowAssistantKeyboard(false); setShowOtherRoutes(false); setIdle(null);
    activity.current = Date.now(); dispatch({ type: 'reset' });
  }, [clearPrintListener, voice.stop]);
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
  useEffect(() => {
    if (state.screen !== 'assistant' && state.screen !== 'routes') return;
    shell.current?.querySelector<HTMLElement>('h1')?.focus({ preventScroll: true });
    shell.current?.querySelector(`.${s.content}`)?.scrollTo(0, 0);
  }, [state.screen, conversation, showOtherRoutes]);
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
    const clear = ['destinations', 'keyboard', 'assistant'].includes(screen) ? { search: null, detail: null, live: null, guidance: null, print: null, destination: null } : screen === 'results' ? { search:null, detail:null, live:null, guidance:null, print:null } : screen === 'routes' ? { detail: null, live: null, guidance: null, print: null } : {};
    patch({ screen, busy: false, error: '', ...clear });
  }
  function editAssistant(text: string) {
    setAssistantText(text);
    setConversation(null);
  }
  function searchAssistant(text: string) {
    if (!text.trim() || state.busy) return;
    voice.stop();
    editAssistant(text);
    void run(async signal => {
      const result = await api.understand(ORIGIN_STATION_ID, text, signal);
      if (signal.aborted) return;
      setListening(false);
      setConversation(result.data);
      setShowAssistantKeyboard(false);
      patch({ dataMode: result.meta.dataMode });
    });
  }
  function restartAssistant() {
    editAssistant('');
    setListening(false);
    setShowAssistantKeyboard(false);
  }
  function confirmDestination(destination: Destination) {
    setShowOtherRoutes(false);
    findRoutes(destination, routePreference ?? 'transfers');
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
  function findRoutes(destination: Destination, ordering: RouteOrder = 'transfers') {
    patch({destination, selectedRouteOptionId:null, search:null, detail:null, live:null, guidance:null, print:null});
    setSort(ordering);
    void run(async signal => {
      const backendSort = ordering === 'waiting' ? 'transfers' : ordering;
      const args = [ORIGIN_STATION_ID, destination.destinationId, signal, backendSort] as const;
      const r = routePreference ? await api.search(...args, true) : await api.search(...args);
      if (!signal.aborted) patch({ destination, search: r.data, detail: null, live: null, guidance: null, print: null, screen: 'routes', dataMode: r.meta.dataMode });
    });
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
  const noRoutes = state.screen === 'routes' && !state.busy && !state.search?.routeOptions.length;
  const recommended = Boolean(routePreference) && !showOtherRoutes && !noRoutes;
  const preferenceSort = assistantSorts.find(([value]) => value === routePreference && value !== 'transfers');
  const confirmationSubtitle = routePreference ? 'AI가 경로를 추천해 드려요.' : '목적지를 확인하면 이용할 수 있는 경로를 보여 드려요.';
  const confirmedCandidate = conversation?.candidates.length === 1 ? conversation.candidates[0] : undefined;
  const walkingDistance = state.assistant ? state.destination?.walkingDistanceMeters : null;
  const printPending = state.screen === 'print' && state.busy;
  const step = state.screen === 'routes' ? 1 : state.screen === 'detail' ? 2 : state.screen === 'print' ? 3 : 0;
  const routeBack = state.assistant ? 'assistant' : state.results.length ? 'results' : 'destinations';
  const topBack = state.screen === 'assistant' || state.screen === 'keyboard' || (state.screen === 'print' && !printPending)
    || (state.screen === 'results' && !noResults && state.selectedCategory !== null)
    || (state.screen === 'routes' && !noRoutes);
  const screenClass = {
    home: s.home, destinations: '', keyboard: s.keyboardScreen, assistant: s.assistantScreen,
    results: noResults ? s.emptyResults : state.selectedCategory ? '' : s.searchResults,
    routes: recommended ? s.recommendationScreen : '', detail: s.detailScreen, print: s.printScreen, done: s.done,
  }[state.screen];
  const screenSpeech: Record<State['screen'], string> = { home: '현재 정류장에서 목적지까지 가는 버스를 찾아드려요. 화면으로 찾기나 말로 찾기를 눌러 주세요.', assistant: conversation?.clarification?.question ?? (confirmedCandidate ? `${confirmedCandidate.name}이 맞나요?` : '가고 싶은 곳과 원하는 이동 방법을 말씀하거나 입력해 주세요.'), destinations: '어디로 가시나요? 검색하거나 목록에서 목적지를 선택해 주세요.', keyboard: '장소를 입력한 뒤 검색하기를 눌러 주세요.', results: `${state.resultTitle}. 검색 결과 ${state.results.length}건. 찾으시는 장소를 선택해 주세요.`, routes: noRoutes ? `이용할 수 있는 버스 경로를 찾지 못했어요. ${walkingDistance == null ? '' : `목적지까지 도보 ${formatDistance(walkingDistance)}예요.`}` : `이용 가능한 경로 ${state.search?.routeOptions.length ?? 0}개. 이동할 경로를 선택해 주세요.`, detail: '선택한 경로를 확인해 주세요. 아래 경로로 이동하시겠어요?', print: '종이 안내표를 출력해 드릴까요? 출력하기 버튼을 눌러 주세요.', done: '안내표를 확인해 주세요. 다시 인쇄하려면 계속 이용하기를 눌러 주세요.' };
  let spokenText = screenSpeech[state.screen];
  if (state.screen === 'detail' && state.detail?.journeyStatus === 'ready') {
    spokenText = routeSpeech(state.detail) || spokenText;
  } else if ((state.screen === 'print' || state.screen === 'done') && state.detail && state.guidance) {
    spokenText = speechTexts(state.guidance, state.detail).join(' ');
  }
  const sortedResults = state.results;
  const distanceNotice = placeSort === 'name' ? '장소명순 · 표시는 길을 따라 걷는 거리예요.' : '현재 정류장에서 길을 따라 걷는 거리순이에요.';
  const options = (state.search?.routeOptions ?? []).map(option => ({...option,routeNames:option.routeNames.map(displayText)}));
  const optionArrivals = searchArrivals?.routeSearchId === state.search?.routeSearchId ? searchArrivals?.options : undefined;
  const originName = state.station?.name ?? ORIGIN_NAME;
  const originCode = !state.station || state.station.stationId === ORIGIN_STATION_ID ? ORIGIN_PUBLIC_CODE : null;

  function toggleVoice() {
    setShowVoice(true);
    if (voice.speaking) voice.stop();
    else voice.speak(displayText(spokenText));
  }

  return <StateContext.Provider value={state}>
    <div ref={shell} data-theme={high ? 'contrast' : 'default'} className={`${s.kiosk} ${high ? s.high : ''}`} style={{ '--design-scale': scale } as CSSProperties}>
      <header className={s.header}>
        <span><Asset file="57066.svg" className={s.logo} />{originName}{originCode && ` ${originCode}`}</span>
        <time>{formatTime(new Date(clock).toISOString())}</time>
      </header>
      <main className={`${s.content} ${screenClass}`} aria-busy={state.busy}>
        {state.screen !== 'home' && state.screen !== 'done' && <div className={s.screenTop}>
          {topBack && <button className={s.back} onClick={() => state.screen === 'assistant' ? (conversation ? restartAssistant() : reset())
            : state.screen === 'routes' && routePreference && showOtherRoutes ? setShowOtherRoutes(false)
            : go(state.screen === 'print' ? 'detail' : state.screen === 'routes' ? routeBack : 'destinations')}>이전</button>}
          {printPending ? <div className={s.progressPlaceholder} /> : <Progress step={step} />}
        </div>}
        {state.screen === 'home' && <><img className={s.startBus} src="/assets/b8667.png" alt="파란 버스" /><h1 tabIndex={-1}>현재 정류장에서 목적지까지<br />가는 버스를 찾아드려요</h1><p className={s.homeSubtitle}>편한 방법을 선택해 주세요.</p>
          <div className={s.homeActions}>
            <button className={s.primary} aria-label="화면으로 찾기" disabled={!state.station || state.busy} onClick={() => go('destinations')}>
              <img src="/assets/ec4c9.svg" alt="" /><strong>화면으로 찾기</strong><span>목적지를 직접 선택해요</span>
            </button>
            <button className={s.primary} aria-label="말로 찾기" disabled={!state.station || state.busy}
              onClick={() => { patch({ assistant: true }); go('assistant'); }}>
              <MicrophoneIcon /><strong>말로 찾기</strong><span>가고 싶은 곳을 말해요</span>
            </button>
          </div>
        </>}
        {state.screen === 'assistant' && (conversation ? <>
          <Heading title={confirmedCandidate ? '이 장소가 맞나요?' : conversation.candidates.length ? '어디로 가시나요?' : '목적지를 확인해 주세요.'}
            subtitle={conversation.candidates.length ? confirmationSubtitle : '장소 이름을 바꿔 다시 찾아보세요.'} />
          <section className={s.voiceConfirmation} aria-label="목적지 확인">
            <img src="/assets/voice-location-pin.png" alt="" className={s.confirmationPin} />
            {confirmedCandidate ? <>
              <p><strong>{displayText(confirmedCandidate.name)}</strong><br />“{assistantText}”</p>
              <div className={s.actions}>
                <Primary secondary disabled={state.busy} onClick={restartAssistant}>아니에요</Primary>
                <Primary disabled={state.busy} onClick={() => confirmDestination(confirmedCandidate)}>맞아요</Primary>
              </div>
            </> : <>
              <p>{conversation.clarification?.question ?? (conversation.status === 'unavailable'
                ? 'AI 도우미를 이용할 수 없어요.' : '일치하는 목적지를 찾지 못했어요.')}</p>
              <div className={s.assistantResults}>
                {conversation.candidates.map(destination => <Primary key={destination.destinationId} disabled={state.busy}
                  onClick={() => confirmDestination(destination)}>{displayText(destination.name)}</Primary>)}
                <Primary secondary disabled={state.busy} onClick={restartAssistant}>다시 입력하기</Primary>
              </div>
            </>}
          </section>
        </> : <>
          <Heading title="말로 목적지 찾기" subtitle={<>가고 싶은 곳을 말씀해 주세요.<br />원하는 조건도 함께 말씀하실 수 있어요.</>} />
          <div className={s.voiceControls}>
            <img src="/assets/voice-microphone.png" alt="" className={s.voiceArt} />
            <SpeechInput disabled={state.busy || idle !== null} onListen={voice.stop}
              onListeningChange={setListening} onText={searchAssistant}>
              <div className={s.voiceExamples} aria-label="예시로 검색">
                <p>아래 버튼을 누른 후 이렇게 말씀해 보세요.</p>
                {assistantExamples.map(text => <button key={text} type="button" disabled={state.busy}
                  onClick={() => searchAssistant(text)}>“{text}”</button>)}
              </div>
            </SpeechInput>
            {!listening && <button type="button" className={s.helperButton} disabled={state.busy}
              aria-expanded={showAssistantKeyboard} onClick={() => setShowAssistantKeyboard(open => !open)}>글로 입력하기</button>}
          </div>
          {showAssistantKeyboard && !listening && <form onSubmit={event => { event.preventDefault(); searchAssistant(assistantText); }}>
            <label className={s.inputWrap}>
              <input aria-label="목적지와 이동 조건" placeholder="예: 중앙시장에 가고 싶어요" value={assistantText}
                maxLength={200} disabled={state.busy} onChange={event => editAssistant(event.target.value)} />
            </label>
            <div className={s.keyboard}><Keyboard value={assistantText} onChange={editAssistant} maxLength={200}
              onSubmit={() => searchAssistant(assistantText)} disabled={state.busy} /></div>
          </form>}
        </>)}
        {state.screen === 'destinations' && <><Heading title="어디로 가시나요?" subtitle="검색하거나 아래 목록에서 선택해 주세요." /><button className={s.searchField} onClick={() => go('keyboard')}><Asset file={high ? '70f47.svg' : 'b06fb.svg'} className={s.searchIcon} />장소를 검색하세요</button><div className={s.categories}>{(['hospital', 'office', 'terminal', 'market', 'station'] as const).map((cat, i) => <button key={cat} className={s.category} disabled={state.busy} aria-pressed={state.selectedCategory === cat} onClick={() => loadCategory(cat)}><span className={s.categoryIcon}>{cat === 'market' ? <><Asset file={high ? 'df386.svg' : '8d70f.svg'} className={s.marketTop} /><Asset file={high ? '76506.svg' : '9042c.svg'} className={s.marketBottom} /></> : <Asset file={(high ? ['3a98b', 'd780a', '3a4ca', '', '4a3cf'] : ['26a86', '3b151', '62785', '', 'd92b2'])[i] + '.svg'} className={s.categoryArt} />}</span><span>{['병원', '관공서', '터미널', '시장·쇼핑', '역'][i]}</span>{state.selectedCategory === cat && <small>선택됨</small>}</button>)}</div><div className={s.extraCategories}>{(['education', 'culture'] as const).map(cat => <button className={s.chip} key={cat} aria-pressed={state.selectedCategory === cat} disabled={state.busy} onClick={() => loadCategory(cat)}>{CATEGORY_LABELS[cat]}</button>)}</div></>}
        {state.screen === 'keyboard' && <>
          <Heading title="어디로 가시나요?" subtitle="검색하거나 아래 목록에서 선택해 주세요." />
          <form onSubmit={e => { e.preventDefault(); searchText(); }}>
            <label className={s.inputWrap}>
              <Asset file="ec4c9.svg" className={s.searchIcon} />
              <input autoFocus aria-label="목적지 검색" placeholder="장소를 검색하세요" maxLength={100} value={query} onChange={e => setQuery(e.target.value)} />
            </label>
            <div className={s.keyboard}><Keyboard value={query} onChange={setQuery} onSubmit={() => searchText()} disabled={state.busy} /></div>
          </form>
        </>}
        {state.screen === 'results' && <>
          <Heading title={state.resultTitle} subtitle={noResults ? '검색어와 일치하는 내용이 없어요.' : state.selectedCategory ? '가고 싶은 장소를 선택해 주세요.' : '찾으시는 장소를 선택해 주세요.'} />
          {noResults ? <div className={s.empty}>
            <img src="/assets/a3ca0.png" alt="회색 버스" />
            <p>현재 검색어와 일치하는 내용이 없어요.<br />다시 검색해 주세요.</p>
            <div className={s.actions}>
              <Primary secondary onClick={() => go('destinations')}>이전</Primary>
              <Primary onClick={() => go('keyboard')}>다시 검색하기</Primary>
            </div>
          </div> : <>
            <div className={s.listHeading}>
              <span>{state.selectedCategory ? '목록' : `검색 결과 ${state.results.length}건`}</span>
              <span>
                {([['name', '이름순'], ['walking', '가까운순']] as const).map(([value, label]) =>
                  <button key={value} className={s.chip} disabled={state.busy} aria-pressed={placeSort === value}
                    onClick={() => state.selectedCategory ? loadCategory(state.selectedCategory, value) : searchText(value)}>{label}</button>)}
              </span>
            </div>
            <div className={s.resultItems}>
              <div className={s.results}>{sortedResults.map(d =>
                <button key={d.destinationId} className={s.destination} aria-pressed={state.destination?.destinationId === d.destinationId}
                  disabled={state.busy} onClick={() => findRoutes(d)}>
                  <strong>{d.name}</strong>
                  <span className={s.destinationDetails}>
                    <span>{d.address ?? categoryNames[d.category]}</span>
                    <b className={s.placeDistance}>{`도보 ${d.walkingDistanceBasis === 'prototype_estimate' ? '약 ' : ''}${formatDistance(d.walkingDistanceMeters)}`}</b>
                  </span>
                  {d.locationNote && <small>{d.locationNote}</small>}
                </button>)}
              </div>
              <p className={s.supportNote}>{distanceNotice}</p>
            </div>
            {!state.selectedCategory && <div className={s.returnActions}><Primary onClick={() => go('keyboard')}>이전</Primary></div>}
          </>}
        </>}
        {state.screen === 'routes' && (noRoutes ? <>
          <Heading title="어떤 경로로 이동하시겠어요?" subtitle={state.search ? '이곳까지 가는 버스 경로를 찾지 못했어요.' : '경로를 다시 확인해 주세요.'} />
          <div className={s.empty}>
            <img src="/assets/a3ca0.png" alt="회색 버스" />
            <p>{state.search ? '이용할 수 있는 경로를 찾지 못했어요.' : '경로를 다시 검색해 주세요.'}</p>
            {state.destination && <p aria-label="선택한 장소">{state.destination.name}</p>}
            {walkingDistance != null && <p>목적지까지 도보 {formatDistance(walkingDistance)}</p>}
            <div className={s.actions}>
              <Primary secondary onClick={() => go(routeBack)}>이전</Primary>
              <Primary disabled={!state.destination || state.busy} onClick={() => state.destination && findRoutes(state.destination, sort)}>경로 다시 검색</Primary>
            </div>
          </div>
        </> : <>
          <Heading title={recommended ? '조건에 맞는 경로를 찾았어요'
            : state.assistant ? '다른 경로도 확인해 보세요' : '어떤 경로로 이동하시겠어요?'}
            subtitle={recommended && sort === 'walking' ? '적게 걷고 싶은 조건을 고려해 추천했어요.'
              : sort === 'fastest' ? '예상 이동시간이 짧은 순서예요. 버스 대기시간은 제외돼요.'
              : recommended ? '이동할 경로를 확인해 주세요.'
              : state.assistant ? '원하는 기준으로 경로를 다시 찾아볼 수 있어요.' : '이용할 경로를 선택해 주세요.'} />
          <Summary />
          {!recommended && <div className={s.listHeading}>
            <span>이용 가능 경로</span>
            <span className={s.routeSort} aria-label="경로 정렬">
              {(preferenceSort ? [...standardSorts, preferenceSort] : standardSorts).map(([value, label]) =>
                <button key={value} className={s.chip} aria-pressed={sort === value} disabled={state.busy}
                  title={value === 'waiting' ? '첫 버스 도착 예정 순' : value === 'fastest' ? '대기시간 제외' : undefined}
                  onClick={() => value === 'waiting' ? setSort(value) : state.destination && findRoutes(state.destination, value)}>{label}</button>)}
            </span>
          </div>}
          <RouteCards options={options} recommended={recommended} selected={state.selectedRouteOptionId} busy={state.busy}
            simulate={prototypeEnabled(state.dataMode)} sortByWait={sort === 'waiting'} now={Date.now()}
            checkingArrivals={state.dataMode === 'static' && !optionArrivals} arrivals={optionArrivals} onChoose={chooseRoute} />
          {recommended && options.length > 0 && <button type="button" className={`${s.helperButton} ${s.otherRoutes}`}
            disabled={state.busy} onClick={() => setShowOtherRoutes(true)}>다른 경로도 보기</button>}
        </>)}
        {state.screen === 'detail' && state.detail && <>
          <Heading title="선택한 경로를 확인해 주세요." subtitle="아래 경로로 이동하시겠어요?" />
          <div className={s.detailBody} tabIndex={0} role="region" aria-label="경로 안내">
            <SelectedRoute detail={state.detail} live={state.live} cached={optionArrivals?.[state.detail.routeOptionId]}
              verified={state.dataMode === 'live' || state.dataMode === 'static'} retry={() => void refreshLive()} />
            <JourneySteps detail={state.detail} high={high} />
          </div>
          <div className={s.actions}>
            <Primary secondary onClick={() => go('routes')}>이전</Primary>
            <Primary disabled={state.busy || state.detail.journeyStatus !== 'ready'} onClick={preparePrint}>안내표 인쇄하기</Primary>
          </div>
        </>}
        {printPending && <>
          <Heading title="안내표를 준비하고 있어요" subtitle="잠시만 기다려 주세요." />
          <div className={s.printSpinner} role="status" aria-label="인쇄 안내표 준비 중" />
        </>}
        {state.screen === 'print' && state.print && !printPending && <>
          <Heading title="종이 안내표를 출력해 드릴까요?" subtitle={<>타는 버스와 내리는 정류장을<br />종이로 확인할 수 있어요.</>} />
          <div className={s.printerArt}><img src="/assets/7144f.png" alt="안내표를 출력하는 키오스크" /></div>
          <div className={s.printSummary}>
            <span>{originName}</span><Asset file="4c4ca.svg" className={s.printDash} /><span>{state.destination?.name}</span>
          </div>
          <div className={s.actions}>
            <Primary secondary onClick={() => go('detail')}>괜찮아요</Primary>
            <Primary disabled={state.busy} onClick={printNow}>출력하기</Primary>
          </div>
        </>}
        {state.screen === 'done' && <>
          <Heading title="안내표를 확인해 주세요" subtitle="필요하면 다시 인쇄할 수 있어요." />
          <div className={`${s.printerArt} ${s.completionArt}`}><img src="/assets/7144f.png" alt="안내표를 가져가는 모습" /></div>
          <p><em>{doneSeconds}</em>초 후 처음으로 돌아가요</p>
          <Primary onClick={() => go('print')}>계속 이용하기</Primary>
        </>}
        {state.error && <div className={s.error} role="alert"><p>{state.error}</p><button onClick={() => state.screen === 'home' ? void run(async signal => { const r = await api.station(ORIGIN_STATION_ID, signal); if (!signal.aborted) patch({ station: { ...r.data.station, name: r.data.station.stationId.startsWith('demo-') ? '현재 정류장' : displayText(r.data.station.name) }, dataMode: r.meta.dataMode }); }) : patch({ error: '' })}>{state.screen === 'home' ? '정류장 다시 확인' : '확인'}</button></div>}
      </main>
      <nav className={s.navigation} aria-label="공통 메뉴"><button aria-pressed={high} onClick={() => patch({ highContrast: !high })}><Asset file={high ? '1e05d.svg' : '94617.svg'} className={s.navIcon} />고대비</button>{state.screen !== 'home' && <button onClick={reset}><Asset file={high ? 'c25a9.svg' : '5d43b.svg'} className={s.navIcon} />처음으로</button>}<button aria-pressed={voice.speaking} onClick={toggleVoice}><Asset file={high ? 'f17e5.svg' : '889d6.svg'} className={s.navIcon} />{voice.speaking ? '안내 중지' : '음성안내'}</button></nav>
      {showVoice && voice.message && <div className={s.toast} role="status">{voice.message}</div>}
      {state.busy && !printPending && <div className={s.loading} role="status"><span />확인하고 있어요…</div>}
      {idle !== null && <IdleDialog count={idle} resume={() => { activity.current = Date.now(); setIdle(null); }} end={reset} />}
    </div>
    {state.print && <PrintDocument snapshot={state.print} originName={originName} destinationName={state.destination?.name ?? ''} />}
  </StateContext.Provider>;
}
function IdleDialog({ count, resume, end }: { count: number; resume: () => void; end: () => void }) {
  const dialog = useRef<HTMLDivElement>(null);
  useEffect(() => { const previous = document.activeElement as HTMLElement; dialog.current?.querySelector('button')?.focus(); return () => previous?.focus(); }, []);
  return <div className={s.overlay}><div ref={dialog} className={s.dialog} role="dialog" aria-modal="true" aria-labelledby="idle-title" onKeyDown={e => { if (e.key === 'Escape') resume(); if (e.key === 'Tab') { const buttons = dialog.current?.querySelectorAll('button'); if (buttons && ((e.shiftKey && document.activeElement === buttons[0]) || (!e.shiftKey && document.activeElement === buttons[1]))) { e.preventDefault(); buttons[e.shiftKey ? 1 : 0].focus(); } } }}><h2 id="idle-title">곧 처음 화면으로 돌아가요</h2><p>움직임이 없어서 종료될 예정이에요.<br />계속 이용하시겠어요?</p><img src="/assets/b49ad.png" alt="시계" /><p><em>{count}</em>초 후 처음으로 돌아가요</p><Primary onClick={resume}>계속 이용하기</Primary><Primary secondary onClick={end}>종료하기</Primary></div></div>;
}
