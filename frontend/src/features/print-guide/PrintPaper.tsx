import JourneyGuide from '../journey-guide/JourneyGuide'
import { formatTime } from '../journey-guide/format'
import type { DataMode } from '../journey-guide/journeyTypes'
import { LiveInfoView } from '../live-info/LiveInfo'
import GuidanceText from '../voice-guide/GuidanceText'
import type { PrintData } from './printTypes'
import './PrintGuide.css'

export default function PrintPaper({ snapshot, dataMode }: { snapshot: PrintData; dataMode: DataMode }) {
  return <div className="bus-paper" lang="ko">
    <JourneyGuide segments={snapshot.routeDetail.segments} dataMode={dataMode} />
    <section className="bus-paper__wording" aria-label="이동 안내 문장">
      <h2>이동 안내 문장</h2><GuidanceText guidance={snapshot.guidance} />
    </section>
    <section className="bus-paper__live" aria-label="생성 시점의 운행 정보">
      <h2>생성 시점의 운행 정보</h2>
      <LiveInfoView data={snapshot.liveInfoSnapshot} detail={snapshot.routeDetail} forPrint />
    </section>
    <footer className="bus-paper__footer">
      <p>안내표 생성 시각: {formatTime(snapshot.generatedAt)}</p>
      <p>{snapshot.notice}</p>
      <p>이 종이는 생성 시점의 정보입니다.<br />이용 전 버스 번호와 방향을 확인하세요.</p>
    </footer>
  </div>
}
