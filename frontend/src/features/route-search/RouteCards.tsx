import type { OptionArrivals, RouteOption } from '../../shared/api/types';
import { currentArrival, formatBusLabel, formatDistance, formatDuration, formatStation } from '../../shared/api/format';
import { routeTiming, simulatedArrivalLabel } from '../../shared/prototypeTiming';
import styles from '../../app/App.module.css';

interface Props {
  options: RouteOption[];
  destination: string;
  selected: string | null;
  busy: boolean;
  simulate?: boolean;
  arrivals?: Record<string, OptionArrivals>;
  onChoose: (option: RouteOption) => void;
}

function RouteOverview({ destination, timing }: {
  destination: string; timing: ReturnType<typeof routeTiming>;
}) {
  const duration = timing.total ?? timing.movement;
  const durationLabel = timing.total != null ? (timing.simulated ? '총시간 시연' : '총 예상시간') : '이동 추정';
  return <span className={styles.routeOverview}>
    <span className={styles.routeDestination}><small>목적지</small><strong>{destination}</strong></span>
    <span className={styles.routeDuration}><small>{durationLabel}</small>{formatDuration(duration)}</span>
  </span>;
}

export function RouteCards({options, destination, selected, busy, simulate = false, arrivals, onChoose}: Props) {
  return <div className={styles.routeList} role="group" aria-label="이용 가능 경로">{options.map(option => {
    const timing = routeTiming(option, simulate);
    const snapshot = arrivals?.[option.routeOptionId];
    const boardings = snapshot?.routeSnapshotVersion === option.routeSnapshotVersion
      && snapshot.arrivals.length === option.routeNames.length ? snapshot.arrivals : [];
    return <button key={option.routeOptionId} className={styles.comparisonCard} aria-pressed={selected === option.routeOptionId}
      disabled={busy || option.journeyStatus !== 'ready'} onClick={() => onChoose(option)}>
      <RouteOverview destination={destination} timing={timing} />
      <span className={styles.routeBadges}>
        {option.features?.map(label => <span key={label}>{label}</span>)}
        {timing.simulated && <span>총시간·대기 시연</span>}
      </span>
      <span className={styles.routeStopsGroup}>
        {!option.routeNames.length ? <span className={styles.routeStops}>현재 정류장에서 목적지까지 도보 이동</span> : <>
          {option.boardStation && <span className={styles.routeStops}>타는 곳 <b>{formatStation(option.boardStation)}</b></span>}
          {!!option.transferStations?.length && <span className={styles.routeStops}>갈아타는 곳 <b>{option.transferStations.map(formatStation).join(' → ')}</b></span>}
          {option.alightStation && <span className={styles.routeStops}>내리는 곳 <b>{formatStation(option.alightStation)}</b></span>}
          {(!option.boardStation || !option.alightStation) && <span className={styles.routeStops}>정류장은 상세 안내에서 확인해 주세요.</span>}
        </>}
      </span>
      <span className={styles.routeMetrics}>
        {timing.total != null && <span>총 예상시간 <b>{formatDuration(timing.total)}</b></span>}
        <span>이동 추정 · 대기 제외 <b>{formatDuration(timing.movement)}</b></span>
        <span>예상 대기시간 <b>{!option.routeNames.length ? '없음' : formatDuration(timing.waiting)}</b></span>
        <span>환승 <b>{option.transferCount}회{option.transferCount === 0 && option.routeNames.length > 0 ? ' · 직통' : ''}</b></span>
        <span>도보 거리 <b>{formatDistance(option.walkingDistanceMeters)}</b></span>
        <span>전체 이동거리 <b>{formatDistance(option.totalDistanceMeters)}</b></span>
      </span>
      <span className={styles.routeFooter}>
        {option.routeNames.map((routeName, index) => {
          const station = index === 0 ? option.boardStation : option.transferStations?.[index - 1];
          const boarding = boardings[index];
          const observed = !station || boarding?.boardStationId === station.stationId ? currentArrival(boarding) : null;
          const fallback = simulate ? (arrivals ? simulatedArrivalLabel(option.routeOptionId, index) : '도착 정보 확인 중')
            : '도착 정보 확인 불가';
          return <span className={styles.routeStops} key={index}>
            <b>{formatBusLabel(routeName)}</b>{index > 0 ? ' (환승)' : ''}
            {option.directionLabels?.[index] && ` · ${option.directionLabels[index]}`} · {observed?.label ?? fallback}
          </span>;
        })}
        <span className={styles.cardAction}>상세 이동 안내 보기 →</span>
      </span>
    </button>;
  })}</div>;
}
