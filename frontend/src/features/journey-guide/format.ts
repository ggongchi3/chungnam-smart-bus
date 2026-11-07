export const DEMO_NOTICE = '시연 데이터 · 실제 운행 정보 아님'

export function formatTime(value: string | null | undefined) {
  if (!value || !Number.isFinite(Date.parse(value))) return '확인 불가'
  return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: 'long', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(value))
}

export function formatDuration(seconds: number) {
  return seconds < 60 ? `${seconds}초` : `약 ${Math.round(seconds / 60)}분`
}
