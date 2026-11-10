import { PROTOTYPE_TIMES_ENABLED } from '../../config/kiosk';
import type { DataMode, RouteOption } from './api/types';

export const prototypeEnabled = (mode: DataMode) => PROTOTYPE_TIMES_ENABLED && mode === 'static';

/** Stable per route and boarding leg: re-rendering or sorting never rolls new values. */
export function boardingWaitSeconds(optionId: string, leg = 0): number {
  let hash = 0;
  for (const letter of optionId) hash = (hash * 31 + letter.charCodeAt(0)) >>> 0;
  return (3 + (hash + leg * 2) % 5) * 60;
}

export function routeTiming(option: RouteOption, simulate = false) {
  const busCount = option.routeNames.length;
  const waits = Array.from({length:busCount}, (_, leg) => boardingWaitSeconds(option.routeOptionId, leg));
  const movement = option.estimatedTravelSeconds ?? (simulate
    ? busCount * 12 * 60 + (option.walkingDurationSeconds ?? (busCount ? 0 : 5 * 60)) : null);
  const waiting = simulate ? waits.reduce((sum, seconds) => sum + seconds, 0)
    : busCount ? option.waitingDurationSeconds ?? null : 0;
  const total = simulate && movement != null ? movement + waiting!
    : option.totalDurationSeconds ?? (!busCount ? movement : null);
  return {movement, waiting, total, waits, simulated:simulate && busCount > 0};
}
