// 개인 브라우저와 분리된 임시 프로필로 로컬 앱만 검사한다.
// npm에 Playwright가 없으면 BUS_PLAYWRIGHT_PATH로 기존 설치의 index.mjs를 지정한다.
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { createDemoSelection } from '../src/features/journey-guide/previewApi.ts'
import { loadJourney } from '../src/features/journey-guide/journeyApi.ts'
import { loadLive } from '../src/features/live-info/liveApi.ts'
import { loadGuidance } from '../src/features/voice-guide/guidanceApi.ts'
import { speechTexts } from '../src/features/voice-guide/speechText.ts'
import { preparePrint } from '../src/features/print-guide/printApi.ts'

const packagePath = process.env.BUS_PLAYWRIGHT_PATH
const { chromium } = await import(packagePath ? pathToFileURL(packagePath).href : 'playwright')
const executablePath = [process.env.BUS_CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  `${process.env.LOCALAPPDATA}/Google/Chrome/Application/chrome.exe`].find((path) => path && existsSync(path))
const output = resolve('qa.local')
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) })
const results = []
const errors = []
const contexts = []
const appUrl = process.env.BUS_APP_URL ?? 'http://127.0.0.1:5173/'
const mark = (name, detail = {}) => { results.push({ name, ...detail }); process.stdout.write(`PASS ${name}\n`) }

async function newContext(voices = 'korean') {
  const context = await browser.newContext({ viewport: { width: 1024, height: 900 } })
  contexts.push(context)
  await context.addInitScript(({ voices }) => {
    window.__speechTest = { spoken: [], cancelled: 0 }
    window.__printed = []
    window.print = () => {
      if (window.parent !== window) window.parent.__printed.push(document.documentElement.outerHTML)
      window.dispatchEvent(new Event('afterprint'))
    }
    if (voices === 'unsupported') {
      Object.defineProperty(window, 'speechSynthesis', { value: undefined, configurable: true })
      return
    }
    if (voices === 'native') return
    const events = new EventTarget()
    Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: {
      getVoices: () => voices === 'korean' ? [{ lang: 'ko-KR', name: 'Test Korean', localService: true }] : [],
      addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events),
      speak: (item) => { window.__speechTest.spoken.push(item.text); window.__speechLast = item;
        if (window.__speechTest.fail) throw new Error('Test speech failure'); queueMicrotask(() => item.onstart?.()) },
      cancel: () => { window.__speechTest.cancelled++ },
    } })
    Object.defineProperty(window, 'SpeechSynthesisUtterance', { configurable: true, value: class {
      constructor(text) { this.text = text }
    } })
  }, { voices })
  const page = await context.newPage()
  page.on('pageerror', (error) => errors.push(error.message))
  return { context, page }
}

async function selectJourney(page, destinationId = 'demo-destination-003') {
  await page.getByRole('button', { name: '목적지 찾기', exact: true }).click()
  await page.getByRole('button', { name: destinationId === 'demo-destination-001' ? '시연 병원' : '시연 터미널', exact: true }).click()
  await page.getByRole('button', { name: '이 경로 선택', exact: true }).first().click()
}

async function openJourney(page, destinationId) {
  await page.goto(appUrl)
  await selectJourney(page, destinationId)
}
async function ready(page) {
  await page.getByRole('heading', { name: '버스 도착·운행 정보' }).waitFor()
  await page.waitForFunction(() => Array.from(document.querySelectorAll('button')).some(
    (button) => button.textContent.includes('인쇄 안내표 준비') && !button.disabled))
}

async function captured(id) {
  const selection = await createDemoSelection(id)
  const { data: detail } = await loadJourney(selection)
  const { data: live } = await loadLive(selection, detail)
  return { selection, detail, live, guidance: await loadGuidance(selection, detail), print: await preparePrint(selection, detail) }
}

function mockApi(context, fixture, state) {
  const wrap = (data) => ({ data, error: null, meta: { dataMode: 'demo', requestId: 'browser-fixture', generatedAt: fixture.print.generatedAt } })
  return context.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!/\/(route-searches|easy-guidance|print-guides)(\/|$)/.test(path)) return route.continue()
    let data
    let status = 200
    if (path.endsWith('/route-searches')) data = { ...fixture.selection, expiresAt: fixture.print.generatedAt,
      routeOptions: [{ routeOptionId: fixture.selection.routeOptionId, routeSnapshotVersion: fixture.selection.routeSnapshotVersion, journeyStatus: 'ready',
        routeNames: fixture.detail.segments.filter((item) => item.type === 'bus').map((item) => item.routeName),
        transferCount: fixture.detail.segments.filter((item) => item.type === 'transfer').length,
        totalDurationSeconds: null, walkingDurationSeconds: null }] }
    else if (path.endsWith('/live')) {
      state.liveCalls++
      if (['changed', 'expired', 'core'].includes(state.mode)) {
        status = state.mode === 'changed' ? 409 : state.mode === 'expired' ? 410 : 503
        const code = state.mode === 'changed' ? 'ROUTE_VERSION_CHANGED' : state.mode === 'expired' ? 'ROUTE_SEARCH_EXPIRED' : 'TRANSPORT_DATA_UNAVAILABLE'
        await route.fulfill({ status, json: { ...wrap(null), error: { code, message: '검증용 경로 재확인 안내', retryable: false } } })
        return
      }
      data = structuredClone(fixture.live)
      if (state.mode === 'missing') {
        data.arrivals = data.arrivals.map((arrival, index) => ({ ...arrival, arrivalStatus: 'unavailable', etaSeconds: null,
          expectedArrivalAt: null, operationStatus: index === 0 ? 'running' : 'unknown' }))
        data.serviceChanges.coverageStatus = 'unknown'
        data.serviceChanges.items = []
      }
      if (state.mode === 'stale') {
        data.arrivals.forEach((arrival) => { arrival.dataQuality.freshness = 'stale' })
        data.serviceChanges.dataQuality.freshness = 'stale'
      }
    } else if (path.endsWith('/easy-guidance')) {
      data = structuredClone(fixture.guidance)
      if (state.mode === 'bad-guidance') data.routeSnapshotVersion = 'different'
    } else if (path.endsWith('/print-guides')) {
      state.printCalls++
      if (state.mode === 'print-failure') {
        await route.fulfill({ status: 500, json: { ...wrap(null), error: { code: 'INTERNAL_ERROR', message: '검증용 준비 실패', retryable: true } } })
        return
      }
      data = fixture.print
    } else {
      if (state.mode === 'detail-expired') {
        await route.fulfill({ status: 410, json: { ...wrap(null), error: {
          code: 'ROUTE_SEARCH_EXPIRED', message: '검증용 검색 만료', retryable: false } } })
        return
      }
      data = fixture.detail
    }
    await route.fulfill({ status, json: wrap(data) })
  })
}

try {
  // 실제 API 연결과 CORS는 목을 사용하지 않고 확인한다.
  const actual = await newContext('native')
  await openJourney(actual.page)
  await ready(actual.page)
  assert.equal(await actual.page.getByText(/개발 확인|API 연동 확인|합성 시연 경로/).count(), 0)
  assert.equal(await actual.page.locator('.service-notice').count(), 1)
  assert.equal(await actual.page.getByRole('heading', { level: 1, name: '이동 안내', exact: true }).count(), 1)
  const presentation = await actual.page.locator('.bus-live button').evaluate((button) => ({
    bodySize: getComputedStyle(document.body).fontSize,
    radius: getComputedStyle(button).borderRadius,
    height: button.getBoundingClientRect().height,
  }))
  assert.equal(presentation.bodySize, '24px')
  assert.equal(presentation.radius, '8px')
  assert.ok(presentation.height >= 64)
  assert.equal(await actual.page.getByText('원천 갱신:', { exact: false }).first().isVisible(), false)
  await actual.page.getByText('정보 확인 시각 보기', { exact: true }).click()
  assert.equal(await actual.page.getByText('원천 갱신:', { exact: false }).first().isVisible(), true)
  await actual.page.getByText('정보 확인 시각 보기', { exact: true }).click()
  mark('개발 메뉴 제거·A와 같은 화면 기준·확인 시각 펼치기')
  await actual.page.screenshot({ path: resolve(output, 'screen-transfer.png'), fullPage: true })
  mark('실제 API와 브라우저 화면 연결')
  await actual.page.getByRole('button', { name: '다른 경로 찾기', exact: true }).click()
  await actual.page.getByLabel('목적지 이름이나 표현을 입력하세요').fill('벙원')
  const interpretation = actual.page.waitForResponse((response) => response.url().endsWith('/destination-interpretations') && response.ok())
  await actual.page.getByRole('button', { name: '검색', exact: true }).click()
  const interpreted = (await (await interpretation).json()).data
  assert.equal(interpreted.status, 'needs_confirmation')
  assert.equal(interpreted.candidates.length, 1)
  await actual.page.getByRole('heading', { name: '이곳을 찾으셨나요?', exact: true }).waitFor()
  assert.equal(await actual.page.getByRole('heading', { name: '이동 안내', exact: true }).count(), 0)
  await actual.page.getByRole('button', { name: '✓ 네, 여기로 갈게요', exact: true }).click()
  await actual.page.getByRole('button', { name: '이 경로 선택', exact: true }).first().click()
  await ready(actual.page)
  assert.equal(await actual.page.locator('.journey-guide__summary h2').innerText(), '시연 병원')
  mark('A의 후보 1개 needs_confirmation 확인 → 경로 선택 → B 새 목적지')
  await actual.page.reload()
  await actual.page.getByRole('button', { name: '목적지 찾기', exact: true }).waitFor()
  assert.equal(await actual.page.getByRole('heading', { name: '이동 안내', exact: true }).count(), 0)
  mark('새로고침으로 선택 소실 시 A 시작 화면')
  await actual.context.close()

  const transfer = await captured('demo-destination-003')
  const direct = await captured('demo-destination-001')
  const test = await newContext()
  const state = { mode: 'normal', liveCalls: 0, printCalls: 0 }
  await mockApi(test.context, transfer, state)
  await openJourney(test.page)
  await ready(test.page)
  await test.page.getByRole('button', { name: '▶ 안내 듣기' }).click()
  await test.page.getByText('음성 안내를 재생하고 있습니다.').waitFor()
  assert.equal((await test.page.evaluate(() => window.__speechTest.spoken))[0], speechTexts(transfer.guidance, transfer.detail)[0])
  await test.page.getByRole('button', { name: '■ 중지' }).click()
  assert.ok((await test.page.evaluate(() => window.__speechTest.cancelled)) > 0)
  mark('음성 재생·중지와 노선 번호 발음 처리 (음성 엔진 모의)')
  await test.page.evaluate(() => { window.__speechTest.fail = true })
  await test.page.getByRole('button', { name: '▶ 안내 듣기' }).click()
  await test.page.getByText('음성을 재생하지 못했습니다. 다시 듣거나 글 안내를 이용해 주세요.').waitFor()
  await test.page.evaluate(() => { window.__speechTest.fail = false })
  mark('음성 재생 오류 후 글 안내 유지')

  for (const [fixture, name] of [[transfer, 'transfer'], [direct, 'direct']]) {
    if (name === 'direct') {
      await test.context.unrouteAll()
      await mockApi(test.context, direct, state)
      await test.page.reload()
      await selectJourney(test.page, 'demo-destination-001')
      await ready(test.page)
    }
    await test.page.getByRole('button', { name: '▤ 인쇄 안내표 준비' }).click()
    const dialog = test.page.getByRole('dialog')
    await dialog.waitFor()
    const dimensions = await dialog.locator('.bus-paper').evaluate((paper) => ({
      width: paper.getBoundingClientRect().width, height: paper.getBoundingClientRect().height,
      left: parseFloat(getComputedStyle(paper).paddingLeft), right: parseFloat(getComputedStyle(paper).paddingRight),
    }))
    assert.ok(Math.abs(dimensions.width - 80 * 96 / 25.4) < 1)
    assert.ok(Math.abs(dimensions.left - 6 * 96 / 25.4) < 1)
    assert.ok(dimensions.height >= 180 * 96 / 25.4)
    assert.equal(await dialog.getByText(/조회 시점 .*후 도착 예정/).count(), 0)
    assert.equal(await dialog.locator('.bus-paper').getByText(/이동 안내 문장|생성 시점의 운행 정보|서버 수집|안내표 생성 시각/).count(), 0)
    assert.equal(await dialog.locator('.bus-paper__bus').count(), fixture.detail.segments.filter((item) => item.type === 'bus').length)
    assert.equal(await dialog.locator('.bus-paper__alight').count(), fixture.detail.segments.filter((item) => item.type === 'bus').length)
    assert.ok((await dialog.locator('.bus-paper').innerText()).includes('출력 시각'))
    assert.equal(await dialog.locator('.bus-paper__alight').first().evaluate((box) => getComputedStyle(box).backgroundColor), 'rgb(237, 237, 237)')
    const paperOverflow = await dialog.locator('.bus-paper').evaluate((paper) => paper.scrollWidth > paper.clientWidth)
    assert.equal(paperOverflow, false)
    await dialog.locator('.bus-paper').screenshot({ path: resolve(output, `paper-${name}.png`) })
    await dialog.getByRole('button', { name: '인쇄 대화상자 열기' }).click()
    await test.page.waitForFunction(() => window.__printed.length > 0)
    const html = await test.page.evaluate(() => window.__printed.pop())
    await writeFile(resolve(output, `paper-${name}.html`), html, 'utf8')
    const pdf = await test.context.newPage()
    await pdf.setContent(html)
    await pdf.pdf({ path: resolve(output, `paper-${name}-80mm.pdf`), preferCSSPageSize: true, printBackground: false })
    await pdf.close()
    await dialog.getByRole('button', { name: '미리보기 닫기' }).click()
    assert.ok(fixture.print.notice.includes('시연 데이터'))
    mark(`80mm ${name} 미리보기·여백·카운트다운 제외·인쇄 HTML`, dimensions)
  }

  await test.page.setViewportSize({ width: 390, height: 844 })
  const overflow = await test.page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  assert.equal(overflow, false)
  await test.page.screenshot({ path: resolve(output, 'screen-mobile.png'), fullPage: true })
  mark('390px 화면 가로 넘침 없음')
  await test.context.close()

  const stalePrint = await newContext()
  const staleState = { mode: 'normal', liveCalls: 0, printCalls: 0 }
  await mockApi(stalePrint.context, transfer, staleState)
  await openJourney(stalePrint.page)
  await ready(stalePrint.page)
  await stalePrint.page.getByRole('button', { name: '▶ 안내 듣기' }).click()
  await stalePrint.page.getByRole('button', { name: '▤ 인쇄 안내표 준비' }).click()
  await stalePrint.page.getByRole('dialog').waitFor()
  assert.ok((await stalePrint.page.evaluate(() => window.__speechTest.cancelled)) > 0)
  staleState.mode = 'detail-expired'
  await stalePrint.page.getByRole('button', { name: '인쇄 대화상자 열기' }).click()
  await stalePrint.page.getByRole('heading', { name: '경로를 확인해 주세요' }).waitFor()
  assert.equal(await stalePrint.page.getByRole('dialog').count(), 0)
  assert.equal(await stalePrint.page.evaluate(() => window.__printed.length), 0)
  mark('인쇄 미리보기에서 음성 중지·최종 만료 시 인쇄 차단')
  await stalePrint.context.close()

  for (const mode of ['missing', 'stale', 'changed', 'expired', 'core', 'bad-guidance', 'print-failure']) {
    const { context, page } = await newContext()
    const state = { mode, liveCalls: 0, printCalls: 0 }
    await mockApi(context, transfer, state)
    await openJourney(page)
    if (['changed', 'expired', 'core', 'bad-guidance'].includes(mode)) {
      await page.getByRole('heading', { name: '경로를 확인해 주세요' }).waitFor()
      assert.equal(await page.getByRole('button', { name: '▤ 인쇄 안내표 준비' }).count(), 0)
    } else {
      await ready(page)
      if (mode === 'missing') {
        assert.equal(await page.getByText('도착 예정 정보 확인 불가', { exact: true }).count(), 2)
        await page.getByText('운행 변경 정보를 확인할 수 없습니다.', { exact: true }).waitFor()
        await page.getByText('운행 상태: 운행 중', { exact: true }).waitFor()
        await page.screenshot({ path: resolve(output, 'screen-missing.png'), fullPage: true })
      }
      if (mode === 'stale') assert.ok(await page.getByText('오래된 정보 · 이용 전 다시 확인해 주세요.', { exact: true }).count() >= 2)
      if (mode === 'print-failure') {
        await page.getByRole('button', { name: '▤ 인쇄 안내표 준비' }).click()
        await page.getByText('안내표를 준비하지 못했습니다. 다시 눌러 주세요.').waitFor()
        assert.equal(state.printCalls, 1)
      }
    }
    mark(`상태 화면: ${mode}`)
    await context.close()
  }

  for (const voices of ['none', 'unsupported']) {
    const { context, page } = await newContext(voices)
    await mockApi(context, transfer, { mode: 'normal', liveCalls: 0, printCalls: 0 })
    await openJourney(page)
    await ready(page)
    await page.getByText(voices === 'none'
      ? '한국어 음성을 사용할 수 없습니다. 기기의 한국어 음성 설정을 확인하거나 글 안내를 이용해 주세요.'
      : '이 브라우저는 음성 안내를 지원하지 않습니다. 글 안내를 이용해 주세요.').waitFor()
    assert.equal(await page.getByRole('button', { name: '▶ 안내 듣기' }).isDisabled(), true)
    mark(`음성 지원 상태: ${voices}`)
    await context.close()
  }

  const poll = await newContext()
  const pollState = { mode: 'normal', liveCalls: 0, printCalls: 0 }
  await mockApi(poll.context, transfer, pollState)
  await poll.page.clock.install()
  await openJourney(poll.page)
  await ready(poll.page)
  const initialCalls = pollState.liveCalls
  await poll.page.clock.fastForward(30_000)
  await poll.page.waitForFunction(() => document.querySelector('.bus-live .bus-arrival') !== null)
  assert.ok(pollState.liveCalls > initialCalls)
  await poll.page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await poll.page.getByText('화면으로 돌아오면 도착 정보를 다시 확인합니다.').waitFor()
  const hiddenCalls = pollState.liveCalls
  await poll.page.clock.fastForward(60_000)
  assert.equal(pollState.liveCalls, hiddenCalls)
  await poll.page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await ready(poll.page)
  assert.ok(pollState.liveCalls > hiddenCalls)
  mark('숨긴 화면 조회 중지·복귀 즉시 갱신')
  await poll.page.getByRole('button', { name: '다른 경로 찾기', exact: true }).click()
  await poll.page.getByRole('heading', { name: '어디로 가시나요?', exact: true }).waitFor()
  const lastCalls = pollState.liveCalls
  await poll.page.clock.fastForward(60_000)
  assert.equal(pollState.liveCalls, lastCalls)
  mark('브라우저 30초 갱신·화면 이탈 후 조회 중단')
  assert.deepEqual(errors, [])
  mark('브라우저 JavaScript 오류 없음')
} finally {
  await writeFile(resolve(output, 'browser-results.json'), JSON.stringify({ results, errors }, null, 2))
  await Promise.allSettled(contexts.map((context) => context.close()))
  await browser.close()
}
