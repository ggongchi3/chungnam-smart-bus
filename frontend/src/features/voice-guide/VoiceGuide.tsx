import { useEffect, useRef, useState } from 'react'
import GuidanceText from './GuidanceText'
import { createSpeechPlayer } from './speechPlayer'
import { speechTexts } from './speechText'
import type { SpeechState } from './speechPlayer'
import type { GuidanceData } from './guidanceTypes'
import type { RouteDetail } from '../journey-guide/journeyTypes'

export default function VoiceGuide({ guidance, detail, loading, error, enabled, onRetry }: {
  guidance: GuidanceData | null; detail: RouteDetail; loading: boolean; error: boolean; enabled: boolean; onRetry: () => void
}) {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])
  const [status, setStatus] = useState<SpeechState>('idle')
  const supported = typeof window !== 'undefined' && typeof window.speechSynthesis?.speak === 'function'
    && typeof window.SpeechSynthesisUtterance === 'function'
  const playerRef = useRef<ReturnType<typeof createSpeechPlayer> | null>(null)
  const koreanVoice = voices.find((voice) => voice.localService) ?? voices[0]

  useEffect(() => {
    if (!supported) return
    const updateVoices = () => setVoices(window.speechSynthesis.getVoices().filter((voice) => /^ko(?:-|$)/i.test(voice.lang.replace('_', '-'))))
    updateVoices()
    window.speechSynthesis.addEventListener('voiceschanged', updateVoices)
    return () => window.speechSynthesis.removeEventListener('voiceschanged', updateVoices)
  }, [supported])

  useEffect(() => {
    if (!supported) return
    const player = createSpeechPlayer({ engine: window.speechSynthesis,
      createUtterance: (text) => new SpeechSynthesisUtterance(text), onState: setStatus })
    playerRef.current = player
    const visibility = () => { if (document.visibilityState === 'hidden') player.stop() }
    document.addEventListener('visibilitychange', visibility)
    return () => { player.dispose(); playerRef.current = null; document.removeEventListener('visibilitychange', visibility) }
  }, [supported, guidance])

  useEffect(() => { if (!enabled) playerRef.current?.stop() }, [enabled])

  return <section className="bus-feature bus-voice" aria-labelledby="bus-voice-title">
    <h2 id="bus-voice-title">음성 안내</h2>
    <p>화면의 이동 안내를 한국어로 읽어 드립니다.</p>
    <div className="bus-feature__actions">
      <button className="button-primary" type="button" disabled={!enabled || !guidance || !koreanVoice || !supported || status === 'playing'}
        onClick={() => { if (guidance && koreanVoice) playerRef.current?.play(speechTexts(guidance, detail), koreanVoice) }}>▶ 안내 듣기</button>
      <button type="button" disabled={status !== 'playing'} onClick={() => { playerRef.current?.stop(); setStatus('idle') }}>■ 중지</button>
      {error && <button type="button" onClick={onRetry}>안내 문장 다시 불러오기</button>}
    </div>
    <p role="status">{!supported ? '이 브라우저는 음성 안내를 지원하지 않습니다. 글 안내를 이용해 주세요.'
      : !koreanVoice ? '한국어 음성을 사용할 수 없습니다. 기기의 한국어 음성 설정을 확인하거나 글 안내를 이용해 주세요.'
        : !enabled ? '경로 정보를 확인한 뒤 안내 듣기를 눌러 주세요.'
          : status === 'playing' ? '음성 안내를 재생하고 있습니다.'
            : status === 'error' ? '음성을 재생하지 못했습니다. 다시 듣거나 글 안내를 이용해 주세요.'
              : loading ? '안내 문장을 불러오고 있습니다.'
                : error ? '안내 문장을 불러오지 못했습니다. 위의 이동 순서를 확인해 주세요.' : '안내 듣기를 누르면 재생합니다.'}</p>
    {guidance && <details className="bus-transcript"><summary>음성 안내 문장 보기</summary><GuidanceText guidance={guidance} /></details>}
  </section>
}
