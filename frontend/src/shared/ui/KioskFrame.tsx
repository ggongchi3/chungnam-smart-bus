import { useEffect, useState, type PropsWithChildren } from 'react'
import chungnamLogo from '../../../../design/assets/logos/충남아이콘.svg'
import contrastIcon from '../../../../design/assets/icons/고대비아이콘.svg'
import highContrastIcon from '../../../../design/assets/icons contrast/고대비아이콘(고대비).svg'
import voiceIcon from '../../../../design/assets/icons/음성안내아이콘.svg'
import highContrastVoiceIcon from '../../../../design/assets/icons contrast/음성안내아이콘(고대비).svg'
import styles from './KioskFrame.module.css'

type KioskFrameProps = PropsWithChildren<{
  stationName: string | null
  stationNumber?: string | null
  onVoiceGuide?: () => void
}>

function formatClock(date: Date) {
  return new Intl.DateTimeFormat('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZone: 'Asia/Seoul',
  }).format(date)
}

export function KioskFrame({ stationName, stationNumber, onVoiceGuide, children }: KioskFrameProps) {
  const [now, setNow] = useState(() => new Date())
  const [highContrast, setHighContrast] = useState(false)

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 15_000)
    return () => window.clearInterval(timer)
  }, [])

  const stationLabel = stationName?.trim() || '정류장 정보를 확인하고 있습니다'

  return (
    <div className={styles.frame} data-contrast={highContrast ? 'high' : 'normal'} lang="ko">
      <header className={styles.header}>
        <div className={styles.station} role="group" aria-label="현재 정류장">
          <img className={styles.logo} src={chungnamLogo} alt="" aria-hidden="true" />
          <span className={styles.stationName}>
            {stationLabel}{stationNumber?.trim() ? ` ${stationNumber.trim()}` : ''}
          </span>
        </div>
        <time className={styles.clock} dateTime={now.toISOString()}>{formatClock(now)}</time>
      </header>

      <div className={styles.content}>{children}</div>

      <footer className={styles.footer} aria-label="공통 메뉴">
        <button
          className={styles.footerButton}
          type="button"
          aria-pressed={highContrast}
          onClick={() => setHighContrast((enabled) => !enabled)}
        >
          <img src={highContrast ? highContrastIcon : contrastIcon} alt="" aria-hidden="true" />
          <span>고대비</span>
        </button>
        <button
          className={styles.footerButton}
          type="button"
          onClick={onVoiceGuide}
          disabled={!onVoiceGuide}
        >
          <img src={highContrast ? highContrastVoiceIcon : voiceIcon} alt="" aria-hidden="true" />
          <span>음성안내</span>
        </button>
      </footer>
    </div>
  )
}
