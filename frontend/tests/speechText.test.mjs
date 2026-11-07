import assert from 'node:assert/strict'
import { test } from 'node:test'
import { pronounceRouteName, speechTexts } from '../src/features/voice-guide/speechText.ts'
import { createSpeechPlayer } from '../src/features/voice-guide/speechPlayer.ts'
import { detail, guidance } from './fixtures.mjs'

test('버스 번호는 횟수 대신 번호로 읽고 자릿값·지선 번호를 보존한다', () => {
  for (const [written, spoken] of [
    ['시연 1번', '시연 일번'], ['2번', '이번'], ['10번', '십번'],
    ['11번', '십일번'], ['100번', '백번'], ['101번', '백일번'],
    ['1001번', '천일번'], ['1-1번', '일 다시 일번'], ['100-2번', '백 다시 이번'],
    ['01번', '영일번'], ['0번', '영번'], ['급행 10000번', '급행 만번'],
    ['N1번', 'N일번'], ['마을버스', '마을버스'],
  ]) assert.equal(pronounceRouteName(written), spoken, written)
})

test('재생 문장의 해당 버스 번호만 바꾸고 정류장·개수·다른 구간·서버 원본을 유지한다', () => {
  const route = structuredClone(detail)
  const words = structuredClone(guidance)
  const bus = route.segments[0]
  bus.routeName = '1번'
  bus.boardStation.name = '1번 버스 정류장'
  bus.alightStation.name = '제1정류장'
  bus.stopCount = 1
  words.steps[0].text = '시연 데이터 · 실제 운행 정보 아님. 1번 버스 정류장에서 1번 버스를 타세요. 1개 정류장을 지나 제1정류장에서 내리세요.'
  const original = structuredClone(words)
  const spoken = speechTexts(words, route)
  assert.equal(spoken[0], '시연 데이터 · 실제 운행 정보 아님. 1번 버스 정류장에서 일번 버스를 타세요. 1개 정류장을 지나 제1정류장에서 내리세요.')
  assert.deepEqual(spoken.slice(1), words.steps.slice(1).map((step) => step.text))
  assert.deepEqual(words, original)
})

test('발음 규칙은 멱등적이며 알 수 없는 문장을 추측해 바꾸지 않는다', () => {
  const words = structuredClone(guidance)
  words.steps[0].text = '1번 승강장에서 다음 안내를 확인하세요.'
  assert.equal(speechTexts(words, detail)[0], words.steps[0].text)
  words.steps[0].text = '시연 출발 정류장에서 시연 1번 버스를 타세요.'
  const once = speechTexts(words, detail)
  words.steps = words.steps.map((step, index) => ({ ...step, text: once[index] }))
  assert.deepEqual(speechTexts(words, detail), once)
})

test('음성 엔진에 발음용 문장을 전달하고 한국어 음성을 유지한다', () => {
  const words = structuredClone(guidance)
  words.steps[0].text = '시연 출발 정류장에서 시연 1번 버스를 타세요. 2개 정류장을 지나세요.'
  const spoken = []
  const player = createSpeechPlayer({
    engine: { speak: (item) => spoken.push(item), cancel() {} },
    createUtterance: (text) => ({ text }), onState() {},
  })
  try {
    player.play(speechTexts(words, detail), { lang: 'ko-KR' })
    assert.equal(spoken[0].text, '시연 출발 정류장에서 시연 일번 버스를 타세요. 2개 정류장을 지나세요.')
    assert.equal(spoken[0].lang, 'ko-KR')
  } finally { player.dispose() }
})
