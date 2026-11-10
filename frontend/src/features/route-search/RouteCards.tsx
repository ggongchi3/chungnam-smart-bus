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
    <span className={styles.routeBadges}>{option.features?.map(label => <span key={label}>{label === '최소 이동시간 · 대기 제외' ? '빠른 이동' : label}</span>)}</span>
    <strong>{option.routeNames.join(' → ') || '도보 이동'}</strong>
    <span className={styles.routeEndpoints}>{origin} → {destination}</span>
    <span className={styles.routeStops}>{option.boardStation ? `${option.boardStation.name} 승차 → ${option.alightStation?.name} 하차` : '현재 정류장에서 출발'}</span>
    {!!option.transferStations?.length && <span className={styles.routeStops}>환승: {option.transferStations.map(stop => stop.name).join(' → ')}</span>}
    <span className={styles.routeMetrics}>
      {(option.estimatedTravelSeconds ?? option.totalDurationSeconds) != null && <span>이동 약 <b>{formatDuration(option.estimatedTravelSeconds ?? option.totalDurationSeconds)}</b></span>}
      <span>환승 <b>{option.transferCount}회</b>{option.walkingDistanceMeters != null && <small>도보 {formatDistance(option.walkingDistanceMeters)}</small>}</span>
      {option.totalDistanceMeters != null && <span>전체 <b>{formatDistance(option.totalDistanceMeters)}</b></span>}
    </span>
    <span className={styles.cardAction}>상세 이동 안내 보기 →</span>
  </button>)}</div>;
}
