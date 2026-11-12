import type { GuidanceData, RouteDetail } from '../../shared/api/types'

const digits = ['영', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']
const smallUnits = ['', '십', '백', '천']
const largeUnits = ['', '만', '억', '조']

function readNumber(value: string): string {
  // 앞자리 0은 노선 식별의 일부다. 매우 긴 식별자도 숫자별로 읽어 손실을 막는다.
  if (/^0\d/.test(value) || value.length > 16) return [...value].map((digit) => digits[Number(digit)]).join('')
  if (Number(value) === 0) return digits[0]
  const groups: string[] = []
  for (let end = value.length, group = 0; end > 0; end -= 4, group++) {
    const part = value.slice(Math.max(0, end - 4), end)
    let spoken = ''
    for (let index = 0; index < part.length; index++) {
      const digit = Number(part[index])
      const position = part.length - index - 1
      if (digit !== 0) spoken += (digit === 1 && position > 0 ? '' : digits[digit]) + smallUnits[position]
    }
    if (spoken) groups.unshift((group === 1 && spoken === '일' ? '' : spoken) + largeUnits[group])
  }
  return groups.join('')
}

export function pronounceRouteName(routeName: string) {
  return routeName.replace(/\d+(?:-\d+)*/g, (number) => number.split('-').map(readNumber).join(' 다시 '))
}

export function speechTexts(guidance: GuidanceData, detail: RouteDetail) {
  return guidance.steps.map((step) => {
    const segment = detail.segments.find((item) => item.segmentId === step.segmentId)
    if (segment?.type !== 'bus') return step.text
    // 검증된 bus.basic 문장 안의 노선명만 발음용으로 바꾼다.
    // 정류장명·정류장 수·시연 문구와 화면/인쇄의 원본 문자열은 유지한다.
    return step.text.replace(`${segment.routeName} 버스를 타세요`, `${pronounceRouteName(segment.routeName)} 버스를 타세요`)
  })
}
