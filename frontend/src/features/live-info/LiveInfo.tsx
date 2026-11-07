import { formatDuration, formatTime } from '../journey-guide/format'
import type { DataQuality, RouteDetail } from '../journey-guide/journeyTypes'
import type { LiveData } from './liveTypes'
import type { LiveState } from './useLiveInfo'
import './LiveInfo.css'

export function QualityNote({ quality }: { quality: DataQuality }) {
  return <div className="bus-quality">
    <p>{quality.freshness === 'stale' ? '오래된 정보 · 이용 전 다시 확인해 주세요.'
      : quality.freshness === 'unknown' ? '정보의 갱신 상태 확인 불가' : '갱신 상태: 최신'}</p>
    <p>원천 갱신: {formatTime(quality.sourceUpdatedAt)}</p>
    <p>서버 수집: {formatTime(quality.fetchedAt)}</p>
  </div>
}

export function LiveInfoView({ data, detail, forPrint = false }: { data: LiveData; detail: RouteDetail; forPrint?: boolean }) {
  const changes = data.serviceChanges
  return <div className="bus-live-view">
    {detail.segments.filter((segment) => segment.type === 'bus').map((bus) => {
      const arrival = data.arrivals.find((item) => item.segmentId === bus.segmentId)
      return <section className="bus-arrival" key={bus.segmentId} aria-label={`${bus.routeName} 도착 정보`}>
        <h3>{bus.routeName}</h3>
        <p>{bus.boardStation.name} 승차</p>
        <p className="bus-arrival__estimate">{arrival?.arrivalStatus === 'available'
          ? forPrint ? `도착 예정 ${formatTime(arrival.expectedArrivalAt)}`
            : arrival.etaSeconds == null ? '도착까지 남은 시간 확인 불가' : `조회 시점 ${formatDuration(arrival.etaSeconds)} 후 도착 예정`
          : '도착 예정 정보 확인 불가'}</p>
        {!forPrint && arrival?.arrivalStatus === 'available' && <p>도착 예정 시각: {formatTime(arrival.expectedArrivalAt)}</p>}
        <p>운행 상태: {arrival?.operationStatus === 'running' ? '운행 중'
          : arrival?.operationStatus === 'not_running' ? '운행하지 않음' : '확인 불가'}</p>
        {arrival && <QualityNote quality={arrival.dataQuality} />}
      </section>
    })}

    <section className="bus-changes" aria-label="운행 변경 안내">
      <h3>운행 변경 안내</h3>
      {changes.coverageStatus === 'unknown' ? <p>운행 변경 정보를 확인할 수 없습니다.</p>
        : changes.items.length === 0 ? <p>{changes.dataQuality.freshness === 'fresh'
          ? '확인된 운행 변경 안내가 없습니다.' : '운행 변경의 최신 상태를 확인할 수 없습니다.'}</p> : null}
      {changes.items.map((item) => <div className="bus-change" key={item.changeId}>
        <h4>{item.title}</h4><p>{item.description}</p>
        <p>적용 시작: {formatTime(item.validFrom)}<br />적용 종료: {formatTime(item.validUntil)}</p>
        <QualityNote quality={item.dataQuality} />
      </div>)}
      <QualityNote quality={changes.dataQuality} />
    </section>
  </div>
}

export default function LiveInfo({ state, detail, onRefresh }: { state: LiveState; detail: RouteDetail; onRefresh: () => void }) {
  return <section className="bus-feature bus-live" aria-labelledby="bus-live-title">
    <div className="bus-feature__heading"><h2 id="bus-live-title">버스 도착·운행 정보</h2>
      <button type="button" onClick={onRefresh} disabled={state.status === 'loading' || state.status === 'paused'
        || (state.status === 'ready' && state.refreshing)}>새로고침</button></div>
    <p className="bus-feature__hint">이 화면을 보고 있는 동안 30초 간격으로 확인합니다.</p>
    {state.status === 'loading' && <p role="status">도착 정보를 불러오고 있습니다.</p>}
    {state.status === 'paused' && <p role="status">화면으로 돌아오면 도착 정보를 다시 확인합니다.</p>}
    {state.status === 'error' && <p role="alert">도착·운행 정보를 불러오지 못했습니다. 새로고침을 눌러 주세요.</p>}
    {state.status === 'ready' && <>
      <p className="bus-feature__hint">서버 응답 시각: {formatTime(state.generatedAt)}{state.refreshing ? ' · 갱신 중' : ''}</p>
      <LiveInfoView data={state.data} detail={detail} />
    </>}
  </section>
}
