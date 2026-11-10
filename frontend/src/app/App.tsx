import JourneyGuideScreen from '../features/journey-guide/JourneyGuideScreen'
import { useCallback, useEffect, useState } from 'react'
import startBusImage from '../../../design/assets/images/첫화면버스.png'
import { getStation, ApiRequestError } from '../shared/api/client'
import { ServiceNotice } from '../shared/ui/ServiceNotice'
import { KioskFrame } from '../shared/ui/KioskFrame'
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
    // eslint-disable-next-line react-hooks/set-state-in-effect -- A의 화면 진입 로딩/재시도 초기화 동작을 유지한다.
    void loadStation(controller.signal)
    return () => controller.abort()
  }, [loadStation])

  return (
    <KioskFrame stationName={state.station?.name ?? null} stationNumber={state.station?.displayNumber}>
      {state.screen !== 'start' && <ServiceNotice />}
      {state.screen === 'start' && (
        <main className={styles.startScreen}>
          <img className={styles.startBus} src={startBusImage} alt="" aria-hidden="true" />
          <h1>현재 정류장에서 목적지까지 가는 버스를 찾아드려요</h1>
          <p className={styles.startDescription}>목적지를 선택하면 버스를 안내해 드릴게요.</p>
          {stationLoading && <p role="status">정류장 정보를 확인하고 있습니다.</p>}
          {stationError && (
            <div className="message message-error" role="alert">
              <p>{stationError}</p>
              <button className="button button-secondary" type="button" onClick={() => void loadStation()}>
                다시 불러오기
              </button>
            </div>
          )}
          <button
            type="button"
            disabled={!state.station || stationLoading}
            onClick={() => dispatch({ type: 'open-search' })}
            className={`button button-primary ${styles.startButton}`}
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
        <JourneyGuideScreen selection={state.routeSelection} onReselect={() => dispatch({ type: 'back-to-search' })} />
      )}
    </KioskFrame>
  )
}
