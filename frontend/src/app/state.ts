import type { Destination, GuidanceData, LiveData, PrintData, RouteDetail, SearchData, Station, DataMode } from '../shared/api/types';
import type { PlaceCategory } from '../shared/places';
export type Screen = 'home' | 'destinations' | 'keyboard' | 'results' | 'routes' | 'detail' | 'print' | 'done';
export interface State {
  screen: Screen; highContrast: boolean; station: Station | null; dataMode: DataMode;
  destination: Destination | null; results: Destination[]; resultTitle: string;
  search: SearchData | null; detail: RouteDetail | null; live: LiveData | null;
  liveChecked: boolean;
  guidance: GuidanceData | null; print: PrintData | null; busy: boolean; error: string;
  selectedCategory: PlaceCategory | null;
  selectedRouteOptionId: string | null;
}
export const initialState: State = { screen: 'home', highContrast: false, station: null, dataMode: 'demo', destination: null, results: [], resultTitle: '', search: null, detail: null, live: null, liveChecked:false, guidance: null, print: null, busy: false, error: '', selectedCategory:null, selectedRouteOptionId:null };
export type Action = { type: 'patch'; value: Partial<State> } | { type: 'reset' } | { type: 'invalidate'; message: string };
export function reducer(state: State, action: Action): State {
  if (action.type === 'reset') return { ...initialState, station: state.station, dataMode: state.dataMode, highContrast: state.highContrast };
  if (action.type === 'invalidate') return { ...state, screen: state.destination ? 'routes' : 'destinations', search: null, detail: null, live: null, guidance: null, print: null, busy: false, error: action.message };
  return { ...state, ...action.value };
}
