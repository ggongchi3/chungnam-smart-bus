import type { JourneySegment } from './journeyTypes'

export function journeyDestination(segments: JourneySegment[]) {
  const last = segments.at(-1)
  if (last?.type === 'walk') return last.toLabel
  if (last?.type === 'bus') return last.alightStation.name
  return '목적지'
}