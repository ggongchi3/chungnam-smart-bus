import { useEffect, useState } from 'react'
import LiveInfo from '../live-info/LiveInfo'
import { useLiveInfo } from '../live-info/useLiveInfo'
import PrintGuide from '../print-guide/PrintGuide'
import VoiceGuide from '../voice-guide/VoiceGuide'
import { loadGuidance } from '../voice-guide/guidanceApi'
import type { GuidanceData } from '../voice-guide/guidanceTypes'
import { isRouteIssue } from './journeyApi'
import type { RouteDetail, RouteSelection } from './journeyTypes'

export default function JourneyFeatures({ selection, detail, onRouteIssue }: {
  selection: RouteSelection; detail: RouteDetail; onRouteIssue: (error: unknown) => void
}) {
  const live = useLiveInfo(selection, detail, onRouteIssue)
  const [guidance, setGuidance] = useState<GuidanceData | null>(null)
  const [guidanceError, setGuidanceError] = useState(false)
  const [guidanceLoading, setGuidanceLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)
  const [previewOpen, setPreviewOpen] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    loadGuidance(selection, detail, controller.signal).then(
      (data) => { if (!controller.signal.aborted) { setGuidance(data); setGuidanceLoading(false) } },
      (error: unknown) => {
        if (controller.signal.aborted) return
        setGuidanceError(true)
        setGuidanceLoading(false)
        if (isRouteIssue(error)) onRouteIssue(error)
      },
    )
    return () => controller.abort()
  }, [selection, detail, onRouteIssue, attempt])

  const enabled = live.state.status === 'ready'
  return <>
    <LiveInfo state={live.state} detail={detail} onRefresh={live.refresh} />
    <PrintGuide selection={selection} detail={detail} enabled={enabled}
      onRouteIssue={onRouteIssue} onPreviewChange={setPreviewOpen} />
    <VoiceGuide guidance={guidance} loading={guidanceLoading} error={guidanceError} enabled={enabled && !previewOpen}
      onRetry={() => { setGuidanceError(false); setGuidanceLoading(true); setAttempt((value) => value + 1) }} />
  </>
}
