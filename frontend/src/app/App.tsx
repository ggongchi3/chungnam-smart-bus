import JourneyGuideScreen from '../features/journey-guide/JourneyGuideScreen'
import { useCallback, useEffect } from 'react'
import startBusImage from '../../../design/assets/images/첫화면버스.png'
import { getStation } from '../shared/api/client'
import { ServiceNotice } from '../shared/ui/ServiceNotice'
import { KioskFrame } from '../shared/ui/KioskFrame'
import { DestinationSearch } from '../features/destination-search/DestinationSearch'
import { RouteSelection } from '../features/route-selection/RouteSelection'
import { useAppState } from './AppState'
import styles from './App.module.css'

export default function App() {
  const { state, dispatch } = useAppState()

  const loadStation = useCallback(async (signal?: AbortSignal) => {
    try {
      const result = await getStation(state.originStationId, signal)
      dispatch({ type: 'station-loaded', station: result.data.station, dataMode: result.meta.dataMode })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
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
          <h1>현재 정류장에서 목적지까지<br />가는 버스를 찾아드려요</h1>
          <p className={styles.startDescription}>목적지를 선택하면 버스를 안내해 드릴게요.</p>
          <button
            type="button"
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
