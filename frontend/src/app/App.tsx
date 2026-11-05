import { useCallback, useEffect, useState } from 'react'
import { getStation, ApiRequestError } from '../shared/api/client'
import { ServiceNotice } from '../shared/ui/ServiceNotice'
import { DestinationSearch } from '../features/destination-search/DestinationSearch'
import { RouteSelection } from '../features/route-selection/RouteSelection'
import { useAppState } from './AppState'
import styles from './App.module.css'

export default function App() {
  const { state, dispatch } = useAppState()
  const [stationLoading, setStationLoading] = useState(true)
  const [stationError, setStationError] = useState('')

  const loadStation = useCallback(async (signal?: AbortSignal) => {
    setStationLoading(true)
    setStationError('')
    try {
      const result = await getStation(state.originStationId, signal)
      dispatch({ type: 'station-loaded', station: result.data.station, dataMode: result.meta.dataMode })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      setStationError(error instanceof ApiRequestError ? error.message : '정류장 정보를 불러오지 못했습니다.')
    } finally {
      if (!signal?.aborted) setStationLoading(false)
    }
  }, [dispatch, state.originStationId])

  useEffect(() => {
    const controller = new AbortController()
    void loadStation(controller.signal)
    return () => controller.abort()
  }, [loadStation])

  return (
    <div className={styles.appShell}>
      <ServiceNotice />
      {state.screen === 'start' && (
        <main className={styles.panel}>
          <p className="eyebrow">현재 정류장</p>
          <h1>어디로 가시나요?</h1>
          {stationLoading && <p role="status">정류장 정보를 확인하고 있습니다.</p>}
          {stationError && (
            <div className="message message-error" role="alert">
              <p>{stationError}</p>
              <button className="button button-secondary" type="button" onClick={() => void loadStation()}>
                다시 불러오기
              </button>
            </div>
          )}
          {state.station && (
            <p className={styles.stationName}>
              {state.station.name}{state.station.directionLabel ? ' · ' + state.station.directionLabel : ''}
            </p>
          )}
          <button
            className="button button-primary"
            type="button"
            disabled={!state.station || stationLoading}
            onClick={() => dispatch({ type: 'open-search' })}
          >
            목적지 찾기
          </button>
        </main>
      )}
      {state.screen === 'destination-search' && (
        <DestinationSearch
          originStationId={state.originStationId}
          onBack={() => dispatch({ type: 'restart' })}
          onSelect={(destination) => dispatch({ type: 'destination-selected', destination })}
        />
      )}
      {state.screen === 'route-selection' && state.destination && (
        <RouteSelection
          destination={state.destination}
          originStationId={state.originStationId}
          onBack={() => dispatch({ type: 'back-to-search' })}
          onSelect={(selection) => dispatch({ type: 'route-selected', selection })}
        />
      )}
      {state.screen === 'journey-guide' && state.routeSelection && (
        <main className={styles.panel}>
          <p className="eyebrow">경로 선택 완료</p>
          <h1>이동 안내로 이어집니다</h1>
          <p>선택한 경로 정보를 프론트엔드 B의 상세 안내 화면에 전달했습니다.</p>
          <dl className={styles.selectionSummary}>
            <div><dt>목적지 ID</dt><dd>{state.routeSelection.destinationId}</dd></div>
            <div><dt>경로 ID</dt><dd>{state.routeSelection.routeOptionId}</dd></div>
            <div><dt>경로 버전</dt><dd>{state.routeSelection.routeSnapshotVersion}</dd></div>
            <div><dt>정보 모드</dt><dd>{state.routeSelection.dataMode}</dd></div>
          </dl>
          <button className="button button-secondary" type="button" onClick={() => dispatch({ type: 'back-to-search' })}>
            다른 경로 찾기
          </button>
        </main>
      )}
    </div>
  )
}
