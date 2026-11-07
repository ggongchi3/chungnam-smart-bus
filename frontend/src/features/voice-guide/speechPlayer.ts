export type SpeechState = 'idle' | 'playing' | 'error'

// 브라우저 음성 엔진을 주입해 중지·오류·이전 재생의 늦은 이벤트를 검증한다.
export function createSpeechPlayer({ engine, createUtterance, onState, startTimeout = 5_000 }: {
  engine: Pick<SpeechSynthesis, 'speak' | 'cancel'>
  createUtterance: (text: string) => SpeechSynthesisUtterance
  onState: (state: SpeechState) => void
  startTimeout?: number
}) {
  let generation = 0
  let speaking = false
  let utterance: SpeechSynthesisUtterance | null = null
  let timer: ReturnType<typeof setTimeout> | undefined

  function cancel() {
    generation += 1
    clearTimeout(timer)
    if (speaking) engine.cancel()
    speaking = false
    utterance = null
  }

  return {
    play(texts: string[], voice: SpeechSynthesisVoice) {
      cancel()
      if (!texts.length) { onState('error'); return }
      speaking = true
      const current = generation
      let index = 0
      onState('playing')
      function next() {
        if (current !== generation) return
        if (index >= texts.length) { speaking = false; utterance = null; onState('idle'); return }
        const item = createUtterance(texts[index++])
        utterance = item // 재생 중 GC되지 않도록 현재 발화를 유지한다.
        item.lang = 'ko-KR'
        item.voice = voice
        item.rate = 0.85
        item.onstart = () => { if (current === generation) clearTimeout(timer) }
        item.onend = () => { if (current === generation) { clearTimeout(timer); next() } }
        item.onerror = () => { if (current === generation) { cancel(); onState('error') } }
        timer = setTimeout(() => { if (current === generation) { cancel(); onState('error') } }, startTimeout)
        try { engine.speak(utterance) } catch { cancel(); onState('error') }
      }
      next()
    },
    stop() { cancel(); onState('idle') },
    dispose() { cancel() },
  }
}
