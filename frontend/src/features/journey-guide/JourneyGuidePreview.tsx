import { useEffect, useState } from 'react'
import JourneyGuideScreen, { JourneyLoadError } from './JourneyGuideScreen'
import { DEMO_NOTICE } from './format'
import { createDemoSelection } from './previewApi'
import type { RouteSelection } from './journeyTypes'
import './JourneyGuide.css'

type DemoState = { status: 'loading' } | { status: 'selected'; selection: RouteSelection } | { status: 'error'; error: unknown }

function DemoJourney({ onRestart }: { onRestart: () => void }) {
  const [state, setState] = useState<DemoState>({ status: 'loading' })
  useEffect(() => {
    const controller = new AbortController()
    // B 단독 실행의 시연 데이터 공급 지점. A에서 연결할 때는 이 검색을 사용하지 않는다.
    const destinationId = new URLSearchParams(window.location.search).get('journey') === 'direct'
      ? 'demo-destination-001' : 'demo-destination-003'
    createDemoSelection(destinationId, controller.signal).then(
      (selection) => { if (!controller.signal.aborted) setState({ status: 'selected', selection }) },
      (error: unknown) => { if (!controller.signal.aborted) setState({ status: 'error', error }) },
    )
    return () => controller.abort()
  }, [])
  if (state.status === 'loading') return <p className="journey-message" role="status">이동 안내를 준비하고 있습니다.</p>
  if (state.status === 'error') return <JourneyLoadError error={state.error} onRetry={onRestart} onReselect={onRestart} />
  return <JourneyGuideScreen selection={state.selection} onReselect={onRestart} showReselect={false} />
}

// A의 검색/경로 선택 UI를 복제하지 않고 B 화면만 실행하는 로컬 진입점.
export default function JourneyGuidePreview() {
  const [attempt, setAttempt] = useState(0)
  return <div className="journey-standalone" lang="ko">
    <p className="service-notice">{DEMO_NOTICE}</p>
    <DemoJourney key={attempt} onRestart={() => setAttempt((value) => value + 1)} />
  </div>
}