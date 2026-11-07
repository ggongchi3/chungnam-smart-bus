import { useId } from 'react'
import { formatDuration } from './format'
import { journeyDestination } from './journeyPresentation'
import type { DataQuality, JourneySegment } from './journeyTypes'
import './JourneyGuide.css'

export type { JourneySegment } from './journeyTypes'
type JourneyGuideProps = { segments: JourneySegment[]; referenceDataQuality?: DataQuality }

export default function JourneyGuide({ segments, referenceDataQuality }: JourneyGuideProps) {
  const titleId = useId()
  const busCount = segments.filter((segment) => segment.type === 'bus').length
  const transferCount = segments.filter((segment) => segment.type === 'transfer').length
  return <section className="journey-guide" aria-labelledby={titleId}>
    <header className="journey-guide__summary">
      <p className="journey-guide__label">목적지</p>
      <h2 id={titleId}>{journeyDestination(segments)}</h2>
      <p>버스 {busCount}회 · {transferCount > 0 ? `환승 ${transferCount}회` : '환승 없음'}</p>
    </header>
    {segments.length === 0 && <p>이동 안내가 없습니다. 경로를 다시 선택해 주세요.</p>}
    <ol className="journey-guide__segments" aria-label="이동 순서">
      {segments.map((segment, index) => <li key={segment.segmentId}
        className={`journey-guide__segment journey-guide__segment--${segment.type}`}>
        <span className="journey-guide__step" aria-hidden="true">{index + 1}</span>
        <div className="journey-guide__content">
          {segment.type === 'bus' && <>
            <h3>{segment.routeName} 버스</h3>
            <p className="journey-guide__station"><span>승차</span><strong>{segment.boardStation.name}</strong></p>
            <p className="journey-guide__travel">↓ {segment.stopCount}개 정류장 이동
              {segment.durationSeconds !== null ? ` · ${formatDuration(segment.durationSeconds)}` : ''}</p>
            <p className="journey-guide__station"><span>하차</span><strong>{segment.alightStation.name}</strong></p>
          </>}
          {segment.type === 'transfer' && <>
            <h3>버스 갈아타기</h3>
            <p><strong>{segment.atStation.name}</strong>에서 다음 버스로 갈아타세요.</p>
          </>}
          {segment.type === 'walk' && <>
            <h3>{index === segments.length - 1 ? '목적지까지 걷기' : '걸어서 이동'}</h3>
            <p>{segment.fromLabel}에서 <strong>{segment.toLabel}</strong>까지 걸어가세요.</p>
            <p className="journey-guide__travel">
              {segment.distanceMeters === null ? '거리 확인 불가' : `${segment.distanceMeters}미터`}
              {' · '}{segment.durationSeconds === null ? '시간 확인 불가' : formatDuration(segment.durationSeconds)}
            </p>
          </>}
        </div>
      </li>)}
    </ol>
    {referenceDataQuality?.freshness === 'stale' && <p className="journey-guide__warning" role="status">경로 기준 정보가 오래되었습니다. 이용 전 다시 확인해 주세요.</p>}
    {referenceDataQuality?.freshness === 'unknown' && <p className="journey-guide__warning" role="status">경로 기준 정보의 갱신 상태를 확인할 수 없습니다.</p>}
  </section>
}