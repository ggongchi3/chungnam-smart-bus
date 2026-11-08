import type { GuidanceData } from './guidanceTypes'

export default function GuidanceText({ guidance }: { guidance: GuidanceData }) {
  return <ol className="bus-guidance-text">
    {guidance.steps.map((step) => <li key={step.segmentId}>{step.text}</li>)}
  </ol>
}
