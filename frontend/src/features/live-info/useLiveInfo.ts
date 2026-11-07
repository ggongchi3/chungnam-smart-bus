import { useEffect, useRef, useState } from 'react'
import { isRouteIssue } from '../journey-guide/journeyApi'
import type { RouteDetail, RouteSelection } from '../journey-guide/journeyTypes'
import { loadLive } from './liveApi'
import { createPoller } from './polling'
import type { LiveData } from './liveTypes'

export type LiveState = { status: 'loading' | 'paused' }
  | { status: 'ready'; data: LiveData; generatedAt: string; refreshing: boolean }
  | { status: 'error'; error: unknown }

export function useLiveInfo(selection: RouteSelection, detail: RouteDetail, onRouteIssue: (error: unknown) => void) {
  const [state, setState] = useState<LiveState>({ status: 'loading' })
  const pollerRef = useRef<{ refresh: () => void } | null>(null)

  useEffect(() => {
    const poller = createPoller({
      load: (signal) => loadLive(selection, detail, signal),
      onStart: () => setState((previous) => previous.status === 'ready'
        ? { ...previous, refreshing: true } : { status: 'loading' }),
      onData: (result) => setState({ status: 'ready', data: result.data, generatedAt: result.generatedAt, refreshing: false }),
      onError: (error) => {
        setState({ status: 'error', error })
        if (isRouteIssue(error)) onRouteIssue(error)
      },
    })
    pollerRef.current = poller
    const visibility = () => {
      if (document.visibilityState === 'hidden') { poller.pause(); setState({ status: 'paused' }) }
      else poller.start()
    }
    document.addEventListener('visibilitychange', visibility)
    if (document.visibilityState !== 'hidden') poller.start()
    return () => { poller.dispose(); pollerRef.current = null; document.removeEventListener('visibilitychange', visibility) }
  }, [selection, detail, onRouteIssue])

  return { state, refresh: () => pollerRef.current?.refresh() }
}
