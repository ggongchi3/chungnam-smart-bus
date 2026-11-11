import { formatBusLabel, formatDateTime, formatDistance, formatDuration } from '../../shared/api/format';
import type { PrintData } from '../../shared/api/types';
import { displayDetail, displayText } from '../../shared/places';
import { ORIGIN_PUBLIC_CODE, ORIGIN_STATION_ID } from '../../../config/kiosk';
import styles from './PrintDocument.module.css';

interface PrintDocumentProps {
  snapshot: PrintData;
  originName: string;
  destinationName: string;
}

export function PrintDocument({ snapshot, originName, destinationName }: PrintDocumentProps) {
  const detail = displayDetail(snapshot.routeDetail);
  const originCode = detail.originStationId === ORIGIN_STATION_ID ? ORIGIN_PUBLIC_CODE : null;
  return (
    <article className={styles.document} aria-label="인쇄용 이동 안내표" data-route-version={detail.routeSnapshotVersion}>
      <header className={styles.header}>
        <h1>나의 버스 이동 안내표</h1>
        <dl className={styles.journey}>
          <dt>출발 정류장</dt><dd>{displayText(originName)}{originCode && ` ${originCode}`}</dd>
          <dt>목적지</dt><dd className={styles.destination}>{displayText(destinationName)}</dd>
        </dl>
        <p className={styles.timestamp}>인쇄 시각 {formatDateTime(snapshot.generatedAt)}</p>
      </header>
      <ol className={styles.steps}>
        {detail.segments.map((segment) => (
          <li key={segment.segmentId}>
            {segment.type === 'bus' && <>
              <h2 className={styles.bus}>{formatBusLabel(segment.routeName)}</h2>
              <dl className={styles.instructions}>
                <dt>타는 곳</dt><dd className={styles.board}>{segment.boardStation.name}</dd>
                <dt>내리는 곳</dt><dd className={styles.alight}>{segment.alightStation.name}</dd>
              </dl>
              <p>{segment.stopCount}개 정류장 이동</p>
            </>}
            {segment.type === 'transfer' && <>
              <h2>버스를 갈아타세요</h2>
              <dl className={styles.instructions}>
                <dt>갈아타는 곳</dt><dd>{segment.atStation.name}</dd>
              </dl>
            </>}
            {segment.type === 'walk' && <>
              <h2>걸어가세요</h2>
              <dl className={styles.instructions}>
                <dt>출발하는 곳</dt><dd>{segment.fromLabel}</dd>
                <dt>도착하는 곳</dt><dd>{segment.toLabel}</dd>
              </dl>
              {(segment.distanceMeters !== null || segment.durationSeconds !== null) && <p>{[
                segment.distanceMeters !== null ? `도보 ${formatDistance(segment.distanceMeters)}` : null,
                segment.durationSeconds !== null ? `약 ${formatDuration(segment.durationSeconds)}` : null,
              ].filter(Boolean).join(' · ')}</p>}
            </>}
          </li>
        ))}
      </ol>
    </article>
  );
}
