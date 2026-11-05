import { useEffect, useState } from 'react'
import { ApiRequestError, searchRoutes } from '../../shared/api/client'
import type { DataMode, Destination, RouteOption, RouteSelection as RouteSelectionData } from '../../shared/api/types'
import { ScreenHeader } from '../../shared/ui/ScreenHeader'
import styles from './RouteSelection.module.css'

interface RouteSelectionProps {
  destination: Destination
  originStationId: string
  onBack: () => void
  onSelect: (selection: RouteSelectionData) => void
}

function routeStatus(status: RouteOption['journeyStatus']) {
  if (status === 'ready') return '이용 순서를 확인했습니다.'
  if (status === 'recheck_required') return '경로를 다시 확인해야 합니다.'
  return '현재 선택할 수 없는 경로입니다.'
}

export function RouteSelection({ destination, originStationId, onBack, onSelect }: RouteSelectionProps) {
  const [options, setOptions] = useState<RouteOption[]>([])
  const [routeSearchId, setRouteSearchId] = useState('')
  const [dataMode, setDataMode] = useState<DataMode>('demo')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    void searchRoutes(originStationId, destination.destinationId, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        setRouteSearchId(result.data.routeSearchId)
        setOptions(result.data.routeOptions)
        setDataMode(result.meta.dataMode)
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return
        setError(reason instanceof ApiRequestError ? reason.message : '경로를 불러오지 못했습니다. 다시 시도해 주세요.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [destination.destinationId, originStationId])

  const retry = () => {
    setError('')
    setLoading(true)
    void searchRoutes(originStationId, destination.destinationId)
      .then((result) => {
        setRouteSearchId(result.data.routeSearchId)
        setOptions(result.data.routeOptions)
        setDataMode(result.meta.dataMode)
      })
      .catch((reason: unknown) => setError(reason instanceof ApiRequestError ? reason.message : '경로를 불러오지 못했습니다. 다시 시도해 주세요.'))
      .finally(() => setLoading(false))
  }

  const chooseRoute = (option: RouteOption) => {
    if (option.journeyStatus !== 'ready' || !routeSearchId) return
    onSelect({
      originStationId,
      destinationId: destination.destinationId,
      routeSearchId,
      routeOptionId: option.routeOptionId,
      routeSnapshotVersion: option.routeSnapshotVersion,
      dataMode,
    })
  }

  return (
    <main className={styles.page}>
      <ScreenHeader
        eyebrow="2단계 · 경로 선택"
        title="이용할 경로를 골라 주세요"
        description={'목적지: ' + destination.name}
        action={<button className="button button-secondary" type="button" onClick={onBack}>목적지 다시 선택</button>}
      />
      {loading && <p className="message" role="status">이용 가능한 경로를 확인하고 있습니다.</p>}
      {error && <div className="message message-error" role="alert"><p>{error}</p><button className="button button-secondary" type="button" onClick={retry}>다시 불러오기</button></div>}
      {!loading && !error && options.length === 0 && (
        <p className="message">이 목적지로 갈 수 있는 경로를 찾지 못했습니다. 목적지를 다시 선택해 주세요.</p>
      )}
      <div className={styles.routeList}>
        {options.map((option, index) => (
          <article className={styles.routeCard} key={option.routeOptionId}>
            <h2>경로 {index + 1}</h2>
            <p className={styles.routeNames}>{option.routeNames.join(' → ')}</p>
            <p>환승 {option.transferCount}회</p>
            <p>{routeStatus(option.journeyStatus)}</p>
            <button
              className="button button-primary"
              type="button"
              disabled={option.journeyStatus !== 'ready' || loading || !routeSearchId}
              onClick={() => chooseRoute(option)}
            >
              이 경로 선택
            </button>
          </article>
        ))}
      </div>
    </main>
  )
}
