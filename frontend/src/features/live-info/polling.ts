// React와 분리하여 조회 간격, 중복 방지, 취소와 늦은 응답 무시를 검증한다.
export function createPoller<T>({ load, onData, onError, onStart, interval = 30_000 }: {
  load: (signal: AbortSignal) => Promise<T>
  onData: (data: T) => void
  onError: (error: unknown) => void
  onStart?: () => void
  interval?: number
}) {
  let active = false
  let disposed = false
  let generation = 0
  let controller: AbortController | null = null
  let timer: ReturnType<typeof setTimeout> | undefined

  function cancel() {
    generation += 1
    clearTimeout(timer)
    controller?.abort()
    controller = null
  }

  async function run() {
    if (!active || disposed || controller) return
    const request = new AbortController()
    const current = ++generation
    controller = request
    onStart?.()
    try {
      const result = await load(request.signal)
      if (active && !disposed && current === generation) onData(result)
    } catch (error) {
      if (active && !disposed && current === generation && !request.signal.aborted) onError(error)
    } finally {
      if (current === generation) {
        controller = null
        if (active && !disposed) timer = setTimeout(run, interval)
      }
    }
  }

  return {
    start() { if (!active && !disposed) { active = true; void run() } },
    refresh() { if (active && !disposed && !controller) { clearTimeout(timer); void run() } },
    pause() { active = false; cancel() },
    dispose() { disposed = true; active = false; cancel() },
  }
}
