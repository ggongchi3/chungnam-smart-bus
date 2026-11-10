import type { DataMode, PrintData } from '../../shared/api/types';
import { displayDetail, displayGuidance, displayText } from '../../shared/places';
import styles from './PrintDocument.module.css';

interface PrintDocumentProps {
  snapshot: PrintData;
  dataMode?: DataMode;
  originName: string;
  destinationName: string;
}

function timestamp(value: string | null): string {
  if (!value) return '확인 불가';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '확인 불가';
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(parsed);
}

export function PrintDocument({ snapshot, originName, destinationName }: PrintDocumentProps) {
  const detail = displayDetail(snapshot.routeDetail);
  const guidance = displayGuidance(snapshot.guidance);
  const guidanceMatches = guidance.routeSnapshotVersion === detail.routeSnapshotVersion;
  return (
    <article className={styles.document} aria-label="인쇄용 이동 안내표" data-route-version={detail.routeSnapshotVersion}>
      <header className={styles.header}>
        <h1>나의 버스 이동 안내표</h1>
        <p className={styles.journey}>{displayText(originName)} → {displayText(destinationName)}</p>
        <p>안내 일시: {timestamp(snapshot.generatedAt)}</p>
      </header>
      <ol className={styles.steps}>
        {detail.segments.map((segment) => (
          <li key={segment.segmentId}>
            {segment.type === 'bus' && <>
              <h2>{segment.routeName} 버스</h2>
              <p><strong>{segment.boardStation.name}</strong>에서 승차</p>
              <p><strong>{segment.stopCount}개 정류장</strong>을 지나 <strong>{segment.alightStation.name}</strong>에서 하차</p>
            </>}
            {segment.type === 'transfer' && <>
              <h2>버스 환승</h2>
              <p><strong>{segment.atStation.name}</strong>에서 다음 버스로 갈아타세요.</p>
            </>}
            {segment.type === 'walk' && <>
              <h2>도보 이동</h2>
              <p>{segment.fromLabel} → <strong>{segment.toLabel}</strong></p>
              {(segment.distanceMeters !== null || segment.durationSeconds !== null) && <p>{[
                segment.distanceMeters !== null ? `도보 ${segment.distanceMeters}m` : null,
                segment.durationSeconds !== null ? `약 ${Math.ceil(segment.durationSeconds / 60)}분` : null,
              ].filter(Boolean).join(' · ')}</p>}
            </>}
            {guidanceMatches && guidance.steps.filter((step) => step.segmentId === segment.segmentId).map((step) => <p className={styles.caption} key={step.segmentId}>{step.text}</p>)}
          </li>
        ))}
      </ol>
    </article>
  );
}
