import assert from 'node:assert/strict'
import { test } from 'node:test'
import { getStation, getDestinations, interpretDestination, searchRoutes, ApiRequestError } from '../src/shared/api/client.ts'
import { JourneyApiError, requestJourneyApi } from '../src/features/journey-guide/journeyApi.ts'
import { envelope } from './fixtures.mjs'

test('A 조회도 B와 같은 캐시·타임아웃·JSON 헤더를 사용한다', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    assert.match(url, /\/api\/v1\/stations\/station%201$/)
    assert.equal(init.cache, 'no-store')
    assert.equal(init.headers.get('Accept'), 'application/json')
    assert.ok(init.signal instanceof AbortSignal)
    return Response.json(envelope({ station: { stationId: 'station 1' } }))
  })
  const result = await getStation('station 1')
  assert.equal(result.data.station.stationId, 'station 1')
  assert.equal(result.meta.dataMode, 'demo')
})

test('A 목적지 필터의 공백·기호를 안전하게 전달한다', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url) => {
    const params = new URL(url).searchParams
    assert.equal(params.get('originStationId'), 'station&1')
    assert.equal(params.get('query'), '병원 & 시장')
    assert.equal(params.get('category'), 'hospital')
    return Response.json(envelope({ destinations: [] }))
  })
  assert.deepEqual((await getDestinations('station&1', { query: '병원 & 시장', category: 'hospital' })).data.destinations, [])
})

test('공통화 후에도 후보 1개의 needs_confirmation을 그대로 유지한다', async (t) => {
  t.mock.method(globalThis, 'fetch', async (_url, init) => {
    assert.equal(init.method, 'POST')
    assert.equal(init.headers.get('Content-Type'), 'application/json')
    assert.deepEqual(JSON.parse(init.body), { originStationId: 'station', text: '병언' })
    return Response.json(envelope({ status: 'needs_confirmation', candidates: [{ destinationId: 'hospital' }] }))
  })
  const result = await interpretDestination('station', '병언')
  assert.equal(result.data.status, 'needs_confirmation')
  assert.equal(result.data.candidates.length, 1)
})

test('A 검색은 새 departAt을 보내고 POST 실패를 자동 재시도하지 않는다', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async (_url, init) => {
    const body = JSON.parse(init.body)
    assert.equal(body.originStationId, 'station')
    assert.equal(body.destinationId, 'hospital')
    assert.ok(Math.abs(Date.now() - Date.parse(body.departAt)) < 1000)
    return Response.json({ data: null, error: { code: 'INTERNAL_ERROR', message: '잠시 후 재시도', retryable: true } }, { status: 500 })
  })
  await assert.rejects(searchRoutes('station', 'hospital'), (error) => error instanceof ApiRequestError && error.code === 'INTERNAL_ERROR')
  assert.equal(mock.mock.calls.length, 1)
})

test('A와 B는 같은 오류 코드를 받으며 B의 기존 오류 분기도 유지한다', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ data: null,
    error: { code: 'ROUTE_SEARCH_EXPIRED', message: '경로 다시 선택', retryable: false } }, { status: 410 }))
  await assert.rejects(getStation('station'), (error) => error instanceof ApiRequestError && error.status === 410)
  await assert.rejects(requestJourneyApi('/route-searches/expired'), (error) => error instanceof JourneyApiError
    && error instanceof ApiRequestError && error.code === 'ROUTE_SEARCH_EXPIRED')
})
