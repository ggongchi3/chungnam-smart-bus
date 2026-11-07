import assert from 'node:assert/strict'
import { test } from 'node:test'
import { JourneyApiError, loadJourney } from '../src/features/journey-guide/journeyApi.ts'
import { createDemoSelection } from '../src/features/journey-guide/previewApi.ts'

const selection = {
  originStationId: 'demo-stop-001', destinationId: 'demo-destination-001',
  routeSearchId: 'search-1', routeOptionId: 'option-1', routeSnapshotVersion: 'v1', dataMode: 'demo',
}
function envelope(overrides = {}, dataMode = 'demo') {
  const { dataMode: _, ...identifiers } = selection
  return {
    data: { ...identifiers, journeyStatus: 'ready', segments: [{ type: 'walk', segmentId: 'walk-1',
      fromLabel: '시연 병원 앞 정류장', toLabel: '시연 병원', distanceMeters: null, durationSeconds: null }], ...overrides },
    error: null, meta: { dataMode },
  }
}
const rejectsCode = (code) => (error) => error instanceof JourneyApiError && error.code === code

test('선택 식별자로 상세를 조회하고 null 거리·시간을 유지한다', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    assert.match(url, /\/api\/v1\/route-searches\/search-1\/options\/option-1$/)
    assert.equal(init.cache, 'no-store')
    return Response.json(envelope())
  })
  const result = await loadJourney(selection)
  assert.equal(result.data.segments[0].distanceMeters, null)
  assert.equal(result.data.segments[0].durationSeconds, null)
})

for (const overrides of [{ routeSnapshotVersion: 'v2' }, { destinationId: 'other' },
  { originStationId: 'other' }, { routeSearchId: 'other' }, { routeOptionId: 'other' }, { journeyStatus: 'recheck_required' }]) {
  test(`다른 경로 또는 재확인 상태는 차단: ${JSON.stringify(overrides)}`, async (t) => {
    t.mock.method(globalThis, 'fetch', async () => Response.json(envelope(overrides)))
    await assert.rejects(loadJourney(selection), rejectsCode('ROUTE_VERSION_CHANGED'))
  })
}

test('서버 데이터 모드가 선택과 다르면 차단한다', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json(envelope({}, 'live')))
  await assert.rejects(loadJourney(selection), rejectsCode('ROUTE_VERSION_CHANGED'))
})

test('필수 식별자가 빠진 선택은 요청 전에 차단한다', async (t) => {
  const fetchMock = t.mock.method(globalThis, 'fetch', async () => Response.json(envelope()))
  await assert.rejects(loadJourney({ ...selection, routeSearchId: '' }), rejectsCode('INVALID_SELECTION'))
  assert.equal(fetchMock.mock.calls.length, 0)
})

for (const [status, code] of [[409, 'ROUTE_VERSION_CHANGED'], [410, 'ROUTE_SEARCH_EXPIRED'], [503, 'TRANSPORT_DATA_UNAVAILABLE']]) {
  test(`HTTP ${status}의 오류 코드를 화면에 전달한다`, async (t) => {
    t.mock.method(globalThis, 'fetch', async () => Response.json({ data: null,
      error: { code, message: '다시 확인해 주세요.', retryable: status === 503 }, meta: { dataMode: 'demo' },
    }, { status }))
    await assert.rejects(loadJourney(selection), rejectsCode(code))
  })
}

test('연결 실패는 예시 경로로 바꾸지 않고 오류를 반환한다', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('Failed to fetch') })
  await assert.rejects(loadJourney(selection), rejectsCode('CONNECTION_FAILED'))
})

test('빈 이동 구간은 안내 가능한 경로로 표시하지 않는다', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json(envelope({ segments: [] })))
  await assert.rejects(loadJourney(selection), rejectsCode('INVALID_RESPONSE'))
})

test('취소된 요청의 신호가 fetch까지 전달된다', async (t) => {
  const controller = new AbortController()
  t.mock.method(globalThis, 'fetch', async (_url, init) => {
    controller.abort()
    assert.equal(init.signal.aborted, true)
    init.signal.throwIfAborted()
  })
  await assert.rejects(loadJourney(selection, controller.signal), { name: 'AbortError' })
})

test('실제 서버: 직통·환승 경로 검색 후 같은 선택 버전의 상세를 조회한다',
  { skip: process.env.BUS_API_SMOKE !== '1' }, async () => {
    for (const [destinationId, types, name] of [
      ['demo-destination-001', ['bus', 'walk'], '시연 병원'],
      ['demo-destination-003', ['bus', 'transfer', 'bus', 'walk'], '시연 터미널'],
    ]) {
      const selected = await createDemoSelection(destinationId)
      const result = await loadJourney(selected)
      assert.equal(result.dataMode, 'demo')
      assert.equal(result.data.routeSnapshotVersion, selected.routeSnapshotVersion)
      assert.deepEqual(result.data.segments.map((segment) => segment.type), types)
      assert.equal(result.data.segments.at(-1).toLabel, name)
      assert.equal(result.data.segments.at(-1).distanceMeters, null)
    }
  })
