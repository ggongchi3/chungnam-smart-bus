import type { RouteOption } from '../../shared/api/types';
import { formatDistance, formatDuration } from '../../shared/api/format';
import styles from '../../app/App.module.css';

interface Props {
  options: RouteOption[];
  origin: string;
  destination: string;
  selected: string | null;
  busy: boolean;
  onChoose: (option: RouteOption) => void;
}

export function RouteCards({options, origin, destination, selected, busy, onChoose}: Props) {
  return <div className={styles.routeList}>{options.map(option => <button key={option.routeOptionId}
    className={styles.comparisonCard} aria-pressed={selected === option.routeOptionId}
    disabled={busy || option.journeyStatus !== 'ready'} onClick={() => onChoose(option)}>
    <span className={styles.routeBadges}>{option.features?.map(label => <span key={label}>{label}</span>)}</span>
    <strong>{option.routeNames.join(' → ') || '도보 이동'}</strong>
    <span className={styles.routeEndpoints}>{origin} → {destination}</span>
    <span className={styles.routeStops}>{!option.routeNames.length ? '현재 정류장에서 목적지까지 도보 이동' : option.boardStation ? `${option.boardStation.name} 승차 → ${option.alightStation?.name ?? '도착 정류장'} 하차` : '승하차 정류장은 상세 안내에서 확인해 주세요.'}</span>
    {!!option.transferStations?.length && <span className={styles.routeStops}>환승: {option.transferStations.map(stop => stop.name).join(' → ')}</span>}
    <span className={styles.routeMetrics}>
      <span>총 예상시간 <b>{formatDuration(option.totalDurationSeconds ?? (!option.routeNames.length ? option.estimatedTravelSeconds : null))}</b></span>
      <span>이동 추정 · 대기 제외 <b>{formatDuration(option.estimatedTravelSeconds)}</b></span>
      <span>예상 대기시간 <b>{!option.routeNames.length ? '없음' : formatDuration(option.waitingDurationSeconds)}</b></span>
      <span>환승 <b>{option.transferCount}회{option.transferCount === 0 && option.routeNames.length > 0 ? ' · 직통' : ''}</b></span>
      <span>도보 거리 <b>{formatDistance(option.walkingDistanceMeters)}</b></span>
      <span>전체 이동거리 <b>{formatDistance(option.totalDistanceMeters)}</b></span>
    </span>
    {!!option.routeNames.length && <span className={styles.routeStops}>버스 도착 예정은 상세 안내에서 조회해요.</span>}
    <span className={styles.cardAction}>상세 이동 안내 보기 →</span>
  </button>)}</div>;
}
