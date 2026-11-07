import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { isRouteIssue, loadJourney } from '../journey-guide/journeyApi'
import type { RouteDetail, RouteSelection } from '../journey-guide/journeyTypes'
import { preparePrint } from './printApi'
import { openPrintFrame } from './printDocument'
import PrintPaper from './PrintPaper'
import type { PrintData } from './printTypes'
import paperCss from './PrintGuide.css?inline'

function PrintPreview({ snapshot, selection, onClose, onRouteIssue, onPreviewChange }: {
  snapshot: PrintData; selection: RouteSelection; onClose: () => void
  onRouteIssue: (error: unknown) => void; onPreviewChange: (open: boolean) => void
}) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const paperRef = useRef<HTMLDivElement>(null)
  const disposeFrame = useRef<(() => void) | null>(null)
  const requestRef = useRef<AbortController | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog && !dialog.open) dialog.showModal()
    onPreviewChange(true)
    // StrictMode의 첫 cleanup에서 close()하면 지연된 close 이벤트가 새 미리보기를 닫는다.
    // 최종 이탈 시 dialog DOM 제거가 모달을 정리한다.
    return () => { requestRef.current?.abort(); disposeFrame.current?.(); onPreviewChange(false) }
  }, [onPreviewChange])

  async function print() {
    setBusy(true)
    setMessage('현재도 같은 경로를 이용할 수 있는지 확인하고 있습니다.')
    const controller = new AbortController()
    requestRef.current = controller
    try {
      await loadJourney(selection, controller.signal)
      if (controller.signal.aborted || !paperRef.current) return
      disposeFrame.current?.()
      const paper = paperRef.current.querySelector<HTMLElement>('.bus-paper')
      if (!paper) throw new Error('Paper unavailable')
      disposeFrame.current = openPrintFrame(paper, paperCss, {
        onOpened: () => { setBusy(false); setMessage('인쇄 대화상자를 열었습니다. 출력 여부는 선택한 프린터에서 확인해 주세요.') },
        onClosed: () => { setBusy(false); setMessage('인쇄 대화상자를 닫았습니다. 실제 출력 여부는 프린터에서 확인해 주세요.') },
        onError: () => { setBusy(false); setMessage('인쇄 대화상자를 열지 못했습니다. 다시 시도해 주세요.') },
      })
    } catch (error) {
      if (controller.signal.aborted) return
      setBusy(false)
      setMessage('경로를 다시 확인하지 못해 인쇄를 중단했습니다. 잠시 후 다시 시도해 주세요.')
      if (isRouteIssue(error)) onRouteIssue(error)
    }
  }

  return createPortal(<dialog ref={dialogRef} className="bus-print-root" aria-labelledby="bus-print-title"
    onClose={onClose}>
    <div className="bus-print-controls">
      <h2 id="bus-print-title">80mm 안내표 미리보기</h2>
      <div className="bus-feature__actions"><button className="button-primary" type="button" disabled={busy} onClick={print}>인쇄 대화상자 열기</button>
        <button type="button" onClick={() => dialogRef.current?.close()}>미리보기 닫기</button></div>
      {message && <p role="status">{message}</p>}
    </div>
    <div className="bus-print-scroll" ref={paperRef}><PrintPaper snapshot={snapshot} dataMode={selection.dataMode} /></div>
  </dialog>, document.body)
}

export default function PrintGuide({ selection, detail, enabled, onRouteIssue, onPreviewChange }: {
  selection: RouteSelection; detail: RouteDetail; enabled: boolean
  onRouteIssue: (error: unknown) => void; onPreviewChange: (open: boolean) => void
}) {
  const [snapshot, setSnapshot] = useState<PrintData | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const requestRef = useRef<AbortController | null>(null)
  useEffect(() => () => requestRef.current?.abort(), [])

  async function prepare() {
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller
    setBusy(true)
    setError(false)
    try {
      const data = await preparePrint(selection, detail, controller.signal)
      if (!controller.signal.aborted) { setSnapshot(data); setBusy(false) }
    } catch (failure) {
      if (controller.signal.aborted) return
      setError(true)
      setBusy(false)
      if (isRouteIssue(failure)) onRouteIssue(failure)
    }
  }

  return <section className="bus-feature bus-print" aria-labelledby="bus-print-panel-title">
    <h2 id="bus-print-panel-title">종이 안내표</h2>
    <p>승차·하차 순서를 흑백 안내표로 가져가세요.</p>
    <div className="bus-feature__actions"><button className="button-primary" type="button" disabled={!enabled || busy} onClick={prepare}>
      {busy ? '안내표 준비 중' : '▤ 인쇄 안내표 준비'}</button></div>
    {error && <p role="alert">안내표를 준비하지 못했습니다. 다시 눌러 주세요.</p>}
    {!enabled && <p className="bus-feature__hint">경로 정보를 확인한 뒤 안내표를 준비할 수 있습니다.</p>}
    {snapshot && <PrintPreview snapshot={snapshot} selection={selection} onClose={() => setSnapshot(null)}
      onRouteIssue={onRouteIssue} onPreviewChange={onPreviewChange} />}
  </section>
}
