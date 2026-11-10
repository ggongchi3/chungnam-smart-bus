import type { PrintData } from '../../shared/api/types';
import styles from './PrintDocument.module.css';

interface PrintDocumentProps {
  snapshot: PrintData;
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
  const detail = snapshot.routeDetail;
  const live = snapshot.liveInfoSnapshot;
  const guidanceMatches = snapshot.guidance.routeSnapshotVersion === detail.routeSnapshotVersion;
  return (
    <article className={styles.document} aria-label="인쇄용 이동 안내표">
      <header className={styles.header}>
        <p className={styles.notice}>{snapshot.notice}</p>
        <h1>나의 버스 이동 안내표</h1>
        <p className={styles.journey}>{originName} → {destinationName}</p>
        <p>안내표 생성 시각: {timestamp(snapshot.generatedAt)} (한국 시간)</p>
      </header>
      <ol className={styles.steps}>
        {detail.segments.map((segment) => (
          <li key={segment.segmentId}>
            {segment.type === 'bus' && <>
              <h2>{segment.routeName} 버스</h2>
              <p><strong>{segment.boardStation.name}</strong>에서 승차</p>
              <p><strong>{segment.stopCount}개 정류장</strong>을 지나 <strong>{segment.alightStation.name}</strong>에서 하차</p>
              <p className={styles.caption}>출발 정류장은 제외하고, 내리는 정류장은 포함한 수입니다.</p>
            </>}
            {segment.type === 'transfer' && <>
              <h2>버스 환승</h2>
              <p><strong>{segment.atStation.name}</strong>에서 다음 버스로 갈아타세요.</p>
            </>}
            {segment.type === 'walk' && <>
              <h2>도보 이동</h2>
              <p>{segment.fromLabel} → <strong>{segment.toLabel}</strong></p>
              <p>거리: {segment.distanceMeters === null ? '확인되지 않음' : `${segment.distanceMeters}m`} · 소요시간: {segment.durationSeconds === null ? '확인되지 않음' : `${Math.ceil(segment.durationSeconds / 60)}분`}</p>
            </>}
            {guidanceMatches && snapshot.guidance.steps.filter((step) => step.segmentId === segment.segmentId).map((step) => <p className={styles.caption} key={step.segmentId}>{step.text}</p>)}
          </li>
        ))}
      </ol>
      <section className={styles.quality}>
        <h2>생성 시점의 운행 정보</h2>
        <p>이 안내표는 생성 시점의 고정된 정보입니다. 이동 전 최신 운행 정보를 다시 확인해 주세요.</p>
        <p>경로 자료 원천 갱신 시각: {timestamp(detail.referenceDataQuality.sourceUpdatedAt)}</p>
        <p>경로 자료 서버 수집 시각: {timestamp(detail.referenceDataQuality.fetchedAt)}</p>
        {live.arrivals.map((arrival) => {
          const bus = detail.segments.find((segment) => segment.type === 'bus' && segment.segmentId === arrival.segmentId);
          return <div key={arrival.segmentId} className={styles.observation}>
            <h3>{bus?.type === 'bus' ? bus.routeName : '버스'} 운행 자료</h3>
            <p>운행 상태: {arrival.operationStatus === 'running' ? '운행 중으로 제공됨' : arrival.operationStatus === 'not_running' ? '운행하지 않음으로 제공됨' : '확인 불가'}</p>
            <p>자료 출처: {arrival.dataQuality.sourceId ?? '확인 불가'}</p>
            <p>원천 갱신 시각: {timestamp(arrival.dataQuality.sourceUpdatedAt)}</p>
            <p>서버 수집 시각: {timestamp(arrival.dataQuality.fetchedAt)}</p>
            <p>정보 상태: {arrival.dataQuality.freshness === 'fresh' ? '생성 시점의 최신 자료' : arrival.dataQuality.freshness === 'stale' ? '오래된 정보' : '최신성 확인 불가'}</p>
            {arrival.arrivalStatus === 'unavailable' && <p>도착 정보는 제공되지 않았습니다.</p>}
          </div>;
        })}
        <h3>운행 변경 정보</h3>
        {live.serviceChanges.coverageStatus === 'unknown' && <p>운행 변경 정보 확인 불가</p>}
        {live.serviceChanges.coverageStatus === 'available' && live.serviceChanges.items.length === 0 && <p>조회된 범위에서 운행 변경 정보가 없습니다.</p>}
        {live.serviceChanges.items.map((change) => <div key={change.changeId} className={styles.observation}>
          <strong>{change.title}</strong><p>{change.description}</p>
          <p>원천 갱신 시각: {timestamp(change.dataQuality.sourceUpdatedAt)}</p>
          <p>서버 수집 시각: {timestamp(change.dataQuality.fetchedAt)}</p>
        </div>)}
        <p>변경 자료 원천 갱신 시각: {timestamp(live.serviceChanges.dataQuality.sourceUpdatedAt)}</p>
        <p>변경 자료 서버 수집 시각: {timestamp(live.serviceChanges.dataQuality.fetchedAt)}</p>
      </section>
      <footer className={styles.footer}>
        <p>종이에는 변동하는 도착 카운트다운을 표시하지 않습니다.</p>
        <p>안내표 번호: {snapshot.printGuideId}</p>
        <p>경로 버전: {detail.routeSnapshotVersion}</p>
      </footer>
    </article>
  );
}
