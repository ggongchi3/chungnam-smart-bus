import { DEMO_NOTICE, formatClock, formatDuration } from '../journey-guide/format'
import { journeyDestination } from '../journey-guide/journeyPresentation'
import type { DataMode } from '../journey-guide/journeyTypes'
import type { PrintData } from './printTypes'
import './PrintGuide.css'

function BusIcon() {
  return <svg viewBox="0 0 32 36" width="16" height="18" fill="none" aria-hidden="true">
    <rect x="4" y="2" width="24" height="28" rx="4" stroke="currentColor" strokeWidth="2.5" />
    <path d="M9 2v5h14V2M4 21h24M1 11v7m30-7v7M8 30v4m16-4v4" stroke="currentColor" strokeWidth="2.5" />
    <path d="M8 10h16v8H8z" fill="currentColor" />
    <circle cx="10" cy="25" r="2" fill="currentColor" /><circle cx="22" cy="25" r="2" fill="currentColor" />
  </svg>
}

// 웹 카드·음성 원고와 분리해 디자인 시안의 종이 안내표만 그린다.
// 이용에 필요한 오래됨/확인 불가 안내는 짧은 하단 문구로 남긴다.
export default function PrintPaper({ snapshot, dataMode }: { snapshot: PrintData; dataMode: DataMode }) {
  const { segments, referenceDataQuality } = snapshot.routeDetail
  const transfers = segments.filter((segment) => segment.type === 'transfer').length
  const buses = segments.filter((segment) => segment.type === 'bus')
  const { arrivals, serviceChanges } = snapshot.liveInfoSnapshot
  const unavailable = arrivals.some((item) => item.arrivalStatus === 'unavailable' || item.dataQuality.freshness === 'unknown')
    || serviceChanges.coverageStatus === 'unknown' || serviceChanges.dataQuality.freshness === 'unknown'
  const stale = arrivals.some((item) => item.dataQuality.freshness === 'stale')
    || serviceChanges.dataQuality.freshness === 'stale'

  return <article className="bus-paper" lang="ko" aria-label="버스 길안내 인쇄 안내표">
    <header className="bus-paper__header">
      <p className="bus-paper__brand"><BusIcon />버스 길안내</p>
      {dataMode === 'demo' && <p className="bus-paper__demo">{DEMO_NOTICE}</p>}
      <div className="bus-paper__destination">
        <p>목적지{transfers > 0 ? ` / 환승 ${transfers}회` : ''}</p>
        <h2>{journeyDestination(segments)}</h2>
      </div>
    </header>

    <ol className="bus-paper__segments" aria-label="이동 순서">
      {segments.map((segment) => {
        if (segment.type === 'bus') {
          const busIndex = buses.findIndex((bus) => bus.segmentId === segment.segmentId)
          const previousBus = buses[busIndex - 1]
          return <li key={segment.segmentId} className="bus-paper__leg">
            {busIndex === 0 && <div className="bus-paper__board">
              <h3>1. 여기서 타세요</h3>
              <p>{segment.boardStation.name}</p>
            </div>}
            <div className="bus-paper__bus">
              <h3>{2 + busIndex * 2}. {busIndex === 0 ? '이 버스를 타세요' : '다음 버스를 타세요'}</h3>
              <p className="bus-paper__route">{segment.routeName}</p>
              {previousBus && previousBus.alightStation.stationId !== segment.boardStation.stationId
                && <p className="bus-paper__next-board">{segment.boardStation.name}에서 승차</p>}
            </div>
            <p className="bus-paper__travel"><span aria-hidden="true">↓</span>{segment.stopCount}개 정류장 이동</p>
            <div className="bus-paper__alight">
              <h3>{3 + busIndex * 2}. 여기서 내리세요</h3>
              <p>{segment.alightStation.name}</p>
            </div>
          </li>
        }
        if (segment.type === 'transfer') return <li key={segment.segmentId} className="bus-paper__transfer">
          <span aria-hidden="true">↓</span>
          <p>{segment.atStation.name}에서 버스를 갈아타세요.</p>
        </li>
        return <li key={segment.segmentId} className="bus-paper__walk">
          <p>{segment.fromLabel}에서 {segment.toLabel}까지 걸어가세요.</p>
          {(segment.distanceMeters !== null || segment.durationSeconds !== null) && <p>
            {[segment.distanceMeters !== null ? `${segment.distanceMeters}미터` : '',
              segment.durationSeconds !== null ? formatDuration(segment.durationSeconds) : ''].filter(Boolean).join(' · ')}
          </p>}
        </li>
      })}
    </ol>

    <footer className="bus-paper__footer">
      <p>출력 시각 <time dateTime={snapshot.generatedAt}>{formatClock(snapshot.generatedAt)}</time></p>
      <p>경로 원천 갱신 {formatClock(referenceDataQuality.sourceUpdatedAt)}
        {referenceDataQuality.freshness === 'stale' ? ' · 오래됨'
          : referenceDataQuality.freshness === 'unknown' && referenceDataQuality.sourceUpdatedAt ? ' · 상태 확인 불가' : ''}</p>
      {unavailable ? <p>일부 운행 정보 확인 불가 · 탑승 전 확인하세요.</p>
        : stale ? <p>운행 정보 오래됨 · 탑승 전 확인하세요.</p> : null}
      {serviceChanges.items.map((item) => <p key={item.changeId}>{item.title} · {item.description}</p>)}
      <p className="bus-paper__caution">버스 번호와 방향을 확인하고 탑승하세요.<br />운행 정보는 변경될 수 있습니다.</p>
    </footer>
  </article>
}
