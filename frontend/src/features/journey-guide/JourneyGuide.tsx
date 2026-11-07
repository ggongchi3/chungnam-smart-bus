import type { DataMode, DataQuality, JourneySegment } from './journeyTypes'
import './JourneyGuide.css'
import { useId } from 'react'
import { formatDuration, formatTime } from './format'

export type { JourneySegment } from './journeyTypes'

type JourneyGuideProps = {
  segments: JourneySegment[]
  dataMode: DataMode
  computedAt?: string
  referenceDataQuality?: DataQuality
}

function BusIcon() {
  return (
    <svg viewBox="0 0 32 36" width="32" height="36" fill="none" aria-hidden="true">
      <rect x="4" y="2" width="24" height="28" rx="4" stroke="currentColor" strokeWidth="2.5" />
      <path d="M9 2v5h14V2M4 21h24M1 11v7m30-7v7M8 30v4m16-4v4" stroke="currentColor" strokeWidth="2.5" />
      <path d="M8 10h16v8H8z" fill="currentColor" />
      <circle cx="10" cy="25" r="2" fill="currentColor" /><circle cx="22" cy="25" r="2" fill="currentColor" />
    </svg>
  )
}

export default function JourneyGuide({ segments, dataMode, computedAt, referenceDataQuality }: JourneyGuideProps) {
  const titleId = useId()
  const lastSegment = segments.at(-1)
  const destination = lastSegment?.type === 'walk' ? lastSegment.toLabel : '목적지'
  const transferCount = segments.filter((segment) => segment.type === 'transfer').length

  return (
    <article className="journey-guide" aria-labelledby={titleId}>
      <header className="journey-guide__header">
        <p className="journey-guide__brand"><BusIcon /> 버스 길안내</p>
        {dataMode === 'demo' && <p className="journey-guide__notice">시연 데이터 · 실제 운행 정보 아님</p>}
        <div className="journey-guide__destination">
          <p>목적지{transferCount > 0 ? ` / 환승 ${transferCount}회` : ''}</p>
          <h1 id={titleId}>{destination}</h1>
        </div>
      </header>

      {segments.length === 0 && <p className="journey-guide__empty">이동 안내가 없습니다. 경로를 다시 선택해 주세요.</p>}

      <ol className="journey-guide__segments" aria-label="이동 순서">
        {segments.map((segment, index) => {
          const step = 1 + segments.slice(0, index).reduce((count, item) => count + (item.type === 'bus' ? 3 : 1), 0)
          return (
            <li key={segment.segmentId} className={`journey-guide__segment journey-guide__segment--${segment.type}`}>
              {segment.type === 'bus' && <>
                <div className="journey-guide__board">
                  <h2>{step}. 여기서 타세요</h2>
                  <p className="journey-guide__station">{segment.boardStation.name}</p>
                </div>
                <div className="journey-guide__bus">
                  <h2>{step + 1}. 이 버스를 타세요</h2>
                  <p className="journey-guide__route">{segment.routeName}</p>
                </div>
                <p className="journey-guide__travel"><span aria-hidden="true">↓</span>{segment.stopCount}개 정류장 이동</p>
                <div className="journey-guide__alight">
                  <h2>{step + 2}. 여기서 내리세요</h2>
                  <p className="journey-guide__station">{segment.alightStation.name}</p>
                </div>
              </>}
              {segment.type === 'transfer' && <div className="journey-guide__connection">
                <span aria-hidden="true">↓</span>
                <h2>{step}. 버스를 갈아타세요</h2>
                <p><strong>{segment.atStation.name}</strong>에서 환승하세요.</p>
              </div>}
              {segment.type === 'walk' && <div className="journey-guide__walk">
                <h2>{step}. {index === segments.length - 1 ? '걸어서 목적지로 가세요' : '걸어가세요'}</h2>
                <p>{segment.fromLabel}에서 <strong>{segment.toLabel}</strong>까지 걸어가세요.</p>
                <p className="journey-guide__walk-meta">
                  거리 {segment.distanceMeters === null ? '확인 불가' : `${segment.distanceMeters}미터`}
                  {' · '}
                  시간 {segment.durationSeconds === null ? '확인 불가' : formatDuration(segment.durationSeconds)}
                </p>
              </div>}
            </li>
          )
        })}
      </ol>

      <footer className="journey-guide__footer">
        {computedAt && <p>경로 계산 시각 <time dateTime={computedAt}>{formatTime(computedAt)}</time></p>}
        {referenceDataQuality?.freshness === 'stale' && <p role="status">경로 기준 정보가 오래되었습니다. 이용 전 다시 확인해 주세요.</p>}
        {referenceDataQuality?.freshness === 'unknown' && <p role="status">경로 기준 정보의 갱신 상태를 확인할 수 없습니다.</p>}
        <p>버스 번호와 방향을 확인하고 탑승하세요.<br />운행 정보는 변경될 수 있습니다.</p>
      </footer>
    </article>
  )
}
