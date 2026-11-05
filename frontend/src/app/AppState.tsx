import { createContext, useContext, useMemo, useReducer, type Dispatch, type PropsWithChildren } from 'react'
import { DEMO_ORIGIN_STATION_ID } from '../../config/demo'
import type { DataMode, Destination, RouteSelection, Station } from '../shared/api/types'

type Screen = 'start' | 'destination-search' | 'route-selection' | 'journey-guide'

interface AppState {
  screen: Screen
  originStationId: string
  station: Station | null
  destination: Destination | null
  routeSelection: RouteSelection | null
  dataMode: DataMode
}

type Action =
  | { type: 'station-loaded'; station: Station; dataMode: DataMode }
  | { type: 'open-search' }
  | { type: 'destination-selected'; destination: Destination }
  | { type: 'route-selected'; selection: RouteSelection }
  | { type: 'back-to-search' }
  | { type: 'restart' }

const initialState: AppState = {
  screen: 'start',
  originStationId: DEMO_ORIGIN_STATION_ID,
  station: null,
  destination: null,
  routeSelection: null,
  dataMode: 'demo',
}

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'station-loaded':
      return { ...state, station: action.station, dataMode: action.dataMode }
    case 'open-search':
      return { ...state, screen: 'destination-search', destination: null, routeSelection: null }
    case 'destination-selected':
      return { ...state, screen: 'route-selection', destination: action.destination, routeSelection: null }
    case 'route-selected':
      return { ...state, screen: 'journey-guide', routeSelection: action.selection, dataMode: action.selection.dataMode }
    case 'back-to-search':
      return { ...state, screen: 'destination-search', routeSelection: null }
    case 'restart':
      return { ...state, screen: 'start', destination: null, routeSelection: null }
  }
}

const AppStateContext = createContext<{ state: AppState; dispatch: Dispatch<Action> } | null>(null)

export function AppStateProvider({ children }: PropsWithChildren) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const value = useMemo(() => ({ state, dispatch }), [state])
  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>
}

export function useAppState() {
  const value = useContext(AppStateContext)
  if (!value) throw new Error('useAppState는 AppStateProvider 안에서 사용해야 합니다.')
  return value
}
