import { useCallback, useEffect, useState } from 'react'
import JourneyGuide from './JourneyGuide'
import JourneyFeatures from './JourneyFeatures'
import { JourneyApiError, loadJourney } from './journeyApi'
import type { DataMode, RouteDetail, RouteSelection } from './journeyTypes'

type Props = { selection: RouteSelection; onReselect: () => void; showReselect?: boolean }
type State = { status: 'loading' }
  | { status: 'ready'; detail: RouteDetail; dataMode: DataMode }
  | { status: 'error'; error: unknown }

export function JourneyLoadError({ error, onRetry, onReselect }: {
  error: unknown; onRetry: () => void; onReselect: () => void
}) {
  const code = error instanceof JourneyApiError ? error.code : ''
  const reselect = ['INVALID_SELECTION', 'ROUTE_VERSION_CHANGED', 'ROUTE_SEARCH_EXPIRED', 'NOT_FOUND', 'NO_ROUTE'].includes(code)
  return <section className="journey-message">
    <h2>경로를 확인해 주세요</h2>
    <p role="alert">{error instanceof JourneyApiError ? error.message : '안내 정보를 불러오지 못했습니다.'}</p>
    <button className="button button-secondary" type="button" onClick={reselect ? onReselect : onRetry}>
      {reselect ? '경로 다시 선택' : '다시 불러오기'}
    </button>
  </section>
}

function SelectedJourney({ selection, onReselect, showReselect = true }: Props) {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const onRouteIssue = useCallback((error: unknown) => setState({ status: 'error', error }), [])
  useEffect(() => {
    const controller = new AbortController()
    loadJourney(selection, controller.signal).then(
      (result) => { if (!controller.signal.aborted) setState({ status: 'ready', detail: result.data, dataMode: result.dataMode }) },
      (error: unknown) => { if (!controller.signal.aborted) setState({ status: 'error', error }) },
    )
    return () => controller.abort()
  }, [selection, attempt])

  return <main className="journey-screen" lang="ko">
    <header className="screen-header">
      <div><p className="eyebrow">3단계 · 이동 안내</p><h1>이동 안내</h1></div>
      {showReselect && <button className="button button-secondary" type="button" onClick={onReselect}>다른 경로 찾기</button>}
    </header>
    {state.status === 'loading' && <p className="journey-message" role="status">선택한 경로를 불러오고 있습니다.</p>}
    {state.status === 'error' && <JourneyLoadError error={state.error} onReselect={onReselect} onRetry={() => {
      setState({ status: 'loading' })
      setAttempt((value) => value + 1)
    }} />}
    {state.status === 'ready' && <>
      <JourneyGuide segments={state.detail.segments} referenceDataQuality={state.detail.referenceDataQuality} />
      <JourneyFeatures selection={selection} detail={state.detail} onRouteIssue={onRouteIssue} />
    </>}
  </main>
}

// A에서 선택 식별자 6개와 '다시 선택' 처리 함수를 전달한다. 시연 알림은 A의 공통 셸이 담당한다.
export default function JourneyGuideScreen(props: Props) {
  return <SelectedJourney key={JSON.stringify(props.selection)} {...props} />
}