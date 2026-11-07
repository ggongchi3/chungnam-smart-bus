import { useEffect, useState } from 'react'
import JourneyGuide from './JourneyGuide'
import JourneyGuideScreen, { JourneyLoadError } from './JourneyGuideScreen'
import { createDemoSelection } from './previewApi'
import { directSegments, transferSegments } from './previewSegments'
import type { RouteSelection } from './journeyTypes'
import './JourneyGuide.css'

type Scenario = 'api-direct' | 'api-transfer' | 'direct' | 'transfer' | 'empty'
type DemoState = { status: 'loading' } | { status: 'selected'; selection: RouteSelection } | { status: 'error'; error: unknown }

function DemoJourney({ destinationId, onRestart }: { destinationId: string; onRestart: () => void }) {
  const [state, setState] = useState<DemoState>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    createDemoSelection(destinationId, controller.signal).then(
      (selection) => { if (!controller.signal.aborted) setState({ status: 'selected', selection }) },
      (error: unknown) => { if (!controller.signal.aborted) setState({ status: 'error', error }) },
    )
    return () => controller.abort()
  }, [destinationId])

  if (state.status === 'loading') return <p className="journey-message" role="status">시연 경로를 검색하고 있습니다.</p>
  if (state.status === 'error') return <JourneyLoadError error={state.error} onRetry={onRestart} onReselect={onRestart} />
  return <JourneyGuideScreen selection={state.selection} onReselect={onRestart} />
}

// A의 실제 검색·선택 화면이 연결될 때 이 개발용 진입점만 교체한다.
export default function JourneyGuidePreview() {
  const [scenario, setScenario] = useState<Scenario>('api-transfer')
  const [attempt, setAttempt] = useState(0)
  const apiMode = scenario === 'api-direct' || scenario === 'api-transfer'
  const segments = scenario === 'empty' ? [] : scenario === 'direct' ? directSegments : transferSegments
  const choices: { value: Scenario; label: string }[] = [
    { value: 'api-direct', label: 'API 직통 경로' },
    { value: 'api-transfer', label: 'API 환승 경로' },
    { value: 'direct', label: '화면 예시 · 직통' },
    { value: 'transfer', label: '화면 예시 · 환승' },
    { value: 'empty', label: '화면 예시 · 안내 없음' },
  ]

  return (
    <main className="journey-preview" lang="ko">
      <p className="journey-preview__source">
        {apiMode ? '백엔드 API 연동 확인 · 합성 시연 경로' : '화면 확인용 예시 · API를 사용하지 않는 화면'}
      </p>
      {apiMode ? <DemoJourney key={`${scenario}-${attempt}`}
        destinationId={scenario === 'api-direct' ? 'demo-destination-001' : 'demo-destination-003'}
        onRestart={() => setAttempt((value) => value + 1)} />
        : <JourneyGuide segments={segments} dataMode="demo" />}

      <details className="journey-devtools">
        <summary>개발 확인 · 경로와 화면 예시 바꾸기</summary>
        <p>API 버튼은 서버에서 새 경로를 검색한 뒤 상세를 다시 조회합니다. 실제 목적지 확인·경로 선택 화면은 A 담당 화면에서 연결합니다.</p>
        <div className="journey-devtools__buttons">
          {choices.map((choice) => <button key={choice.value} type="button" aria-pressed={scenario === choice.value}
            onClick={() => { setScenario(choice.value); setAttempt((value) => value + 1) }}>{choice.label}</button>)}
        </div>
      </details>
    </main>
  )
}
