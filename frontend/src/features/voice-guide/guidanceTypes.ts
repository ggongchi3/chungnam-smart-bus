export type GuidanceData = {
  routeSnapshotVersion: string
  mode: 'ai_assisted' | 'template_fallback'
  steps: { segmentId: string; text: string }[]
}
