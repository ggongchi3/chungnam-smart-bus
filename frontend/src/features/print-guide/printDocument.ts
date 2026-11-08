export function paperHeightMm(heightPixels: number) {
  // CSS의 물리 단위는 96px = 1in. 반올림 잘림을 막는 여유 2mm를 둔다.
  return Math.max(180, Math.ceil(heightPixels * 25.4 / 96) + 2)
}

export function printDocument(markup: string, css: string, heightPixels: number) {
  const height = paperHeightMm(heightPixels)
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>버스 길안내</title>
<style>${css}\n@page { size: 80mm ${height}mm; margin: 0; }
html, body { width: 80mm; margin: 0; padding: 0; background: white; color: black; color-scheme: light; }
.bus-paper { box-shadow: none !important; margin: 0 !important; }</style></head><body>${markup}</body></html>`
}

export function openPrintFrame(paper: HTMLElement, css: string, callbacks: {
  onOpened: () => void; onClosed: () => void; onError: () => void
}) {
  const frame = document.createElement('iframe')
  frame.title = '버스 길안내 인쇄 문서'
  frame.setAttribute('aria-hidden', 'true')
  frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:80mm;height:1px;border:0;'
  let disposed = false
  const dispose = () => { disposed = true; frame.remove() }
  frame.onload = async () => {
    try {
      await frame.contentDocument?.fonts.ready
      if (disposed) return
      const target = frame.contentWindow
      if (!target) throw new Error('Print window unavailable')
      target.addEventListener('afterprint', () => {
        callbacks.onClosed()
        // 대화상자 처리가 끝난 다음 프레임을 제거한다.
        setTimeout(dispose, 0)
      }, { once: true })
      callbacks.onOpened()
      target.focus()
      target.print()
    } catch { if (!disposed) callbacks.onError(); dispose() }
  }
  // React가 렌더링한 DOM을 복사하므로 서버 문장은 이미 HTML 이스케이프되어 있다.
  frame.srcdoc = printDocument(paper.outerHTML, css, paper.getBoundingClientRect().height)
  document.body.append(frame)
  return dispose
}
