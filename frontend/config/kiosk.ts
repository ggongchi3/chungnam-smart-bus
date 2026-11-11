import origin from '../../shared/data/cheonan-origin.json';

export const ORIGIN_STATION_ID = origin.stationId;
export const ORIGIN_NAME = origin.name;
export const ORIGIN_PUBLIC_CODE = origin.arsId;
export const LIVE_REFRESH_MS = 30_000;
export const IDLE_WARNING_MS = 120_000;
export const IDLE_COUNTDOWN_SECONDS = 30;
// Synthetic waits are opt-in for local demos. Cheonan service never uses them.
export const PROTOTYPE_TIMES_ENABLED = false;
