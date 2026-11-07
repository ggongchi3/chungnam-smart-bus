import type { RouteDetail } from '../journey-guide/journeyTypes'
import type { LiveData } from '../live-info/liveTypes'
import type { GuidanceData } from '../voice-guide/guidanceTypes'

export type PrintData = {
  printGuideId: string
  generatedAt: string
  routeDetail: RouteDetail
  liveInfoSnapshot: LiveData
  notice: string
  guidance: GuidanceData
}
