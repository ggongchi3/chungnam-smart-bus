import assert from 'node:assert/strict'
import { test } from 'node:test'
import { JourneyApiError, requestJourneyApi } from '../src/features/journey-guide/journeyApi.ts'
import { loadLive } from '../src/features/live-info/liveApi.ts'
import { createPoller } from '../src/features/live-info/polling.ts'
import { loadGuidance } from '../src/features/voice-guide/guidanceApi.ts'
import { createSpeechPlayer } from '../src/features/voice-guide/speechPlayer.ts'
import { preparePrint } from '../src/features/print-guide/printApi.ts'
import { paperHeightMm, printDocument } from '../src/features/print-guide/printDocument.ts'
import { selected, detail, live, guidance, printed, envelope } from './fixtures.mjs'

const flush = async () => { for (let index = 0; index < 10; index++) await Promise.resolve() }
const code = (expected) => (error) => error instanceof JourneyApiError && error.code === expected

test('GET 5xx는 1초 후 한 번만 재시도한다', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json(envelope(null), { status: 503 }))
  const promise = requestJourneyApi('/test')
  const result = assert.rejects(promise)
  await flush()
  assert.equal(mock.mock.calls.length, 1)
  t.mock.timers.tick(999)
  await flush()
  assert.equal(mock.mock.calls.length, 1)
  t.mock.timers.tick(1)
  await result
  assert.equal(mock.mock.calls.length, 2)
})

test('POST 실패와 GET 4xx는 자동 재시도하지 않는다', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json({ data: null,
    error: { code: 'ROUTE_SEARCH_EXPIRED', message: '만료', retryable: false } }, { status: 410 }))
  await assert.rejects(requestJourneyApi('/test'), code('ROUTE_SEARCH_EXPIRED'))
  assert.equal(mock.mock.calls.length, 1)
  mock.mock.mockImplementation(async () => { throw new TypeError('offline') })
  await assert.rejects(requestJourneyApi('/test', { method: 'POST' }), code('CONNECTION_FAILED'))
  assert.equal(mock.mock.calls.length, 2)
})

test('1초 재시도 대기 중 화면을 떠나면 다음 요청을 취소한다', async (t) => {
  const controller = new AbortController()
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json(envelope(null), { status: 503 }))
  const promise = requestJourneyApi('/test', { signal: controller.signal })
  const result = assert.rejects(promise, { name: 'AbortError' })
  await flush()
  controller.abort()
  await result
  assert.equal(mock.mock.calls.length, 1)
})

test('요청별 5초 제한 신호로 실패하면 시간 초과를 표시한다', async (t) => {
  const timeout = new AbortController()
  t.mock.method(AbortSignal, 'timeout', (milliseconds) => { assert.equal(milliseconds, 5000); return timeout.signal })
  t.mock.method(globalThis, 'fetch', async (_url, init) => new Promise((_resolve, reject) => {
    init.signal.addEventListener('abort', () => reject(init.signal.reason), { once: true })
  }))
  const promise = requestJourneyApi('/test', { method: 'POST' })
  const result = assert.rejects(promise, code('CONNECTION_FAILED'))
  timeout.abort(new DOMException('timeout', 'TimeoutError'))
  await result
})

test('도착 미수신·운행 중·변경 조회 불가를 각각 유지한다', async (t) => {
  const data = structuredClone(live)
  data.arrivals[0] = { ...data.arrivals[0], arrivalStatus: 'unavailable', etaSeconds: null, expectedArrivalAt: null, operationStatus: 'running' }
  data.serviceChanges.coverageStatus = 'unknown'
  data.serviceChanges.dataQuality.freshness = 'unknown'
  t.mock.method(globalThis, 'fetch', async () => Response.json(envelope(data)))
  const result = await loadLive(selected, detail)
  assert.equal(result.data.arrivals[0].operationStatus, 'running')
  assert.equal(result.data.arrivals[0].etaSeconds, null)
  assert.equal(result.data.serviceChanges.coverageStatus, 'unknown')
})

test('실시간 경로 버전 또는 승차 정류장 불일치를 차단한다', async (t) => {
  const data = structuredClone(live)
  t.mock.method(globalThis, 'fetch', async () => Response.json(envelope(data)))
  data.routeSnapshotVersion = 'other'
  await assert.rejects(loadLive(selected, detail), code('ROUTE_VERSION_CHANGED'))
  data.routeSnapshotVersion = selected.routeSnapshotVersion
  data.arrivals[0].boardStationId = 'other'
  await assert.rejects(loadLive(selected, detail), code('INVALID_RESPONSE'))
})

test('음성 문장은 같은 버전·구간 순서와 시연 표시를 확인한다', async (t) => {
  const data = structuredClone(guidance)
  const mock = t.mock.method(globalThis, 'fetch', async (_url, init) => {
    assert.deepEqual(JSON.parse(init.body), { routeSearchId: selected.routeSearchId, routeOptionId: selected.routeOptionId,
      expectedRouteSnapshotVersion: selected.routeSnapshotVersion })
    return Response.json(envelope(data))
  })
  assert.deepEqual(await loadGuidance(selected, detail), guidance)
  data.steps.reverse()
  await assert.rejects(loadGuidance(selected, detail), code('INVALID_RESPONSE'))
  assert.equal(mock.mock.calls.length, 2)
})

test('인쇄는 고정 도착 시각을 유지하고 카운트다운·다른 구간을 차단한다', async (t) => {
  const data = printed()
  t.mock.method(globalThis, 'fetch', async () => Response.json(envelope(data)))
  const snapshot = await preparePrint(selected, detail)
  assert.equal(snapshot.liveInfoSnapshot.arrivals[0].etaSeconds, null)
  assert.equal(snapshot.liveInfoSnapshot.arrivals[0].expectedArrivalAt, live.arrivals[0].expectedArrivalAt)
  data.liveInfoSnapshot.arrivals[0].etaSeconds = 300
  await assert.rejects(preparePrint(selected, detail), code('INVALID_RESPONSE'))
  data.liveInfoSnapshot.arrivals[0].etaSeconds = null
  data.routeDetail.segments[0].stopCount += 1
  await assert.rejects(preparePrint(selected, detail), code('INVALID_RESPONSE'))
})

test('인쇄 안내 문장 버전과 시연 표시가 다르면 차단한다', async (t) => {
  const data = printed()
  t.mock.method(globalThis, 'fetch', async () => Response.json(envelope(data)))
  data.guidance.routeSnapshotVersion = 'other'
  await assert.rejects(preparePrint(selected, detail), code('ROUTE_VERSION_CHANGED'))
  data.guidance.routeSnapshotVersion = selected.routeSnapshotVersion
  data.notice = ''
  await assert.rejects(preparePrint(selected, detail), code('INVALID_RESPONSE'))
})

test('80mm 용지의 최소 길이는 180mm이며 긴 내용은 길이를 늘린다', () => {
  assert.equal(paperHeightMm(200), 180)
  assert.ok(paperHeightMm(1000) > 180)
  const html = printDocument('<div>검증용 안내</div>', '.bus-paper{width:80mm}', 1000)
  assert.match(html, /@page \{ size: 80mm \d+mm; margin: 0; \}/)
  assert.match(html, /lang="ko"/)
})

test('폴링은 30초 간격이며 진행 중인 요청을 중복 실행하지 않는다', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let calls = 0
  const values = []
  const poller = createPoller({ load: async () => ++calls, onData: (value) => values.push(value), onError: assert.fail })
  poller.start()
  poller.refresh()
  await flush()
  assert.equal(calls, 1)
  t.mock.timers.tick(29_999)
  await flush()
  assert.equal(calls, 1)
  t.mock.timers.tick(1)
  await flush()
  assert.deepEqual(values, [1, 2])
  poller.dispose()
  t.mock.timers.tick(60_000)
  await flush()
  assert.equal(calls, 2)
})

test('화면 이탈로 요청을 취소하고 늦게 끝난 이전 응답을 무시한다', async () => {
  let finish
  let signal
  const values = []
  const poller = createPoller({ load: (requestSignal) => { signal = requestSignal; return new Promise((resolve) => { finish = resolve }) },
    onData: (value) => values.push(value), onError: assert.fail })
  poller.start()
  poller.pause()
  assert.equal(signal.aborted, true)
  finish('old')
  await flush()
  assert.deepEqual(values, [])
  poller.start()
  finish('new')
  await flush()
  assert.deepEqual(values, ['new'])
  poller.dispose()
})

function speechFixture(t) {
  const states = [], spoken = []
  const engine = { speak(item) { spoken.push(item) }, cancel: t.mock.fn() }
  const player = createSpeechPlayer({ engine, createUtterance: (text) => ({ text }), onState: (state) => states.push(state) })
  return { player, states, spoken, engine, voice: { lang: 'ko-KR' } }
}

test('음성은 문장 순서대로 읽고 한국어·느린 속도를 사용한다', (t) => {
  const { player, states, spoken, voice } = speechFixture(t)
  player.play(['첫 안내', '다음 안내'], voice)
  assert.equal(spoken[0].lang, 'ko-KR')
  assert.equal(spoken[0].rate, .85)
  spoken[0].onstart()
  spoken[0].onend()
  assert.equal(spoken[1].text, '다음 안내')
  spoken[1].onstart()
  spoken[1].onend()
  assert.deepEqual(states, ['playing', 'idle'])
  player.dispose()
})

test('중지한 재생의 늦은 종료 이벤트가 새 재생을 덮지 않는다', (t) => {
  const { player, states, spoken, engine, voice } = speechFixture(t)
  player.play(['이전'], voice)
  const old = spoken[0]
  player.stop()
  player.play(['새 안내'], voice)
  old.onend()
  assert.equal(states.at(-1), 'playing')
  assert.equal(spoken.length, 2)
  assert.equal(engine.cancel.mock.calls.length, 1)
  player.dispose()
})

test('음성 엔진 오류와 재생 시작 시간 초과는 글 안내 대체 상태로 끝낸다', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const { player, states, spoken, voice } = speechFixture(t)
  player.play(['안내'], voice)
  spoken[0].onerror()
  assert.equal(states.at(-1), 'error')
  player.play(['안내'], voice)
  t.mock.timers.tick(5000)
  assert.equal(states.at(-1), 'error')
  player.dispose()
})

test('실제 서버: 상세·실시간·음성·인쇄를 같은 버전으로 연결한다', { skip: process.env.BUS_API_SMOKE !== '1' }, async () => {
  const { createDemoSelection } = await import('../src/features/journey-guide/previewApi.ts')
  const { loadJourney } = await import('../src/features/journey-guide/journeyApi.ts')
  for (const id of ['demo-destination-001', 'demo-destination-003']) {
    const selection = await createDemoSelection(id)
    const { data } = await loadJourney(selection)
    const info = await loadLive(selection, data)
    const words = await loadGuidance(selection, data)
    const paper = await preparePrint(selection, data)
    assert.equal(info.data.routeSnapshotVersion, data.routeSnapshotVersion)
    assert.deepEqual(paper.guidance.steps, words.steps)
    assert.equal(paper.liveInfoSnapshot.routeSnapshotVersion, data.routeSnapshotVersion)
    assert.ok(paper.liveInfoSnapshot.arrivals.every((arrival) => arrival.etaSeconds === null))
  }
})
