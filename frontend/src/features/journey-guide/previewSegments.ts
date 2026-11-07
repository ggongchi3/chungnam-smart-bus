import type { JourneySegment } from './JourneyGuide'

// 화면 확인용 합성 데이터. backend/integrations/demo-data.json의 경유 순서 기준.
// 실제 API 응답이나 A가 선택한 경로를 대신하지 않는다.
const firstBus: JourneySegment = {
  segmentId: 'preview-bus-1',
  type: 'bus',
  routeId: 'demo-route-001',
  routeName: '시연 1번',
  boardStation: { stationId: 'demo-stop-001', name: '시연 출발 정류장' },
  alightStation: { stationId: 'demo-stop-003', name: '시연 병원 앞 정류장' },
  boardSequence: 1,
  alightSequence: 3,
  stopCount: 2,
  durationSeconds: null,
}

export const directSegments: JourneySegment[] = [
  firstBus,
  {
    segmentId: 'preview-walk-hospital',
    type: 'walk',
    fromLabel: '시연 병원 앞 정류장',
    toLabel: '시연 병원',
    distanceMeters: null,
    durationSeconds: null,
  },
]

export const transferSegments: JourneySegment[] = [
  firstBus,
  {
    segmentId: 'preview-transfer',
    type: 'transfer',
    fromSegmentId: 'preview-bus-1',
    toSegmentId: 'preview-bus-2',
    atStation: { stationId: 'demo-stop-003', name: '시연 병원 앞 정류장' },
    instructionTemplateId: 'transfer.basic',
  },
  {
    segmentId: 'preview-bus-2',
    type: 'bus',
    routeId: 'demo-route-002',
    routeName: '시연 2번',
    boardStation: { stationId: 'demo-stop-003', name: '시연 병원 앞 정류장' },
    alightStation: { stationId: 'demo-stop-005', name: '시연 터미널 앞 정류장' },
    boardSequence: 1,
    alightSequence: 3,
    stopCount: 2,
    durationSeconds: null,
  },
  {
    segmentId: 'preview-walk-terminal',
    type: 'walk',
    fromLabel: '시연 터미널 앞 정류장',
    toLabel: '시연 터미널',
    distanceMeters: null,
    durationSeconds: null,
  },
]
