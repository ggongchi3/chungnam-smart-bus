import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiRequestError, getDestinations, interpretDestination } from '../../shared/api/client'
import type { Category, Destination, InterpretationData } from '../../shared/api/types'
import { ScreenHeader } from '../../shared/ui/ScreenHeader'
import styles from './DestinationSearch.module.css'

const categoryLabels: { value: Category; label: string }[] = [
  { value: 'hospital', label: '병원' },
  { value: 'market', label: '시장' },
  { value: 'terminal', label: '터미널' },
]

interface DestinationSearchProps {
  originStationId: string
  onBack: () => void
  onSelect: (destination: Destination) => void
}

export function DestinationSearch({ originStationId, onBack, onSelect }: DestinationSearchProps) {
  const [query, setQuery] = useState('')
  const [destinations, setDestinations] = useState<Destination[]>([])
  const [interpretation, setInterpretation] = useState<InterpretationData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const controllerRef = useRef<AbortController | null>(null)

  const runSearch = async (text: string, category?: Category) => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setLoading(true)
    setError('')
    setInterpretation(null)

    const cleanedText = text.trim()
    const normalSearch = getDestinations(originStationId, { query: cleanedText, category }, controller.signal)
      .then((result) => ({ ok: true as const, result }), (reason: unknown) => ({ ok: false as const, reason }))
    const aiSearch = cleanedText
      ? interpretDestination(originStationId, cleanedText, controller.signal)
          .then((result) => ({ ok: true as const, result }), (reason: unknown) => ({ ok: false as const, reason }))
      : Promise.resolve(null)
    const [normalResult, aiResult] = await Promise.all([normalSearch, aiSearch])
    if (controller.signal.aborted) return

    if (normalResult.ok) {
      setDestinations(normalResult.result.data.destinations)
    } else {
      setDestinations([])
      setError(normalResult.reason instanceof ApiRequestError
        ? normalResult.reason.message
        : '목적지를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.')
    }

    if (aiResult?.ok) {
      setInterpretation(aiResult.result.data)
    }
    setLoading(false)
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- A의 진입 검색 상태 초기화와 status 분기를 보존한다.
    void runSearch('')
    return () => controllerRef.current?.abort()
    // Load all registered options when entering the search step.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [originStationId])

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void runSearch(query)
  }

  const selectFirst = (candidates: Destination[]) => {
    if (candidates.length === 1) onSelect(candidates[0])
  }

  const clearInterpretation = () => setInterpretation(null)

  return (
    <main className={styles.page}>
      <ScreenHeader
        eyebrow="1단계 · 목적지 선택"
        title="어디로 가시나요?"
        description="가실 곳을 검색하거나 주요 장소를 선택해 주세요."
        action={<button className="button button-secondary" type="button" onClick={onBack}>처음으로</button>}
      />

      <form className={styles.searchForm} onSubmit={submit}>
        <label htmlFor="destination-query">목적지 이름이나 표현을 입력하세요</label>
        <div className={styles.searchRow}>
          <input
            id="destination-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            maxLength={100}
            autoComplete="off"
            placeholder="예: 병원, 전통시장"
          />
          <button className="button button-primary" type="submit" disabled={loading || !query.trim()}>
            검색
          </button>
        </div>
      </form>

      <section aria-labelledby="popular-destinations-title" className={styles.section}>
        <h2 id="popular-destinations-title">주요 장소</h2>
        <div className={styles.categoryList}>
          {categoryLabels.map((category) => (
            <button
              className="button button-secondary"
              key={category.value}
              type="button"
              disabled={loading}
              onClick={() => {
                setQuery('')
                void runSearch('', category.value)
              }}
            >
              {category.label}
            </button>
          ))}
        </div>
      </section>

      {loading && <p className="message" role="status">목적지를 찾고 있습니다.</p>}
      {error && <p className="message message-error" role="alert">{error}</p>}

      {interpretation && interpretation.status !== 'unavailable' && (
        <section className={styles.aiPanel} aria-live="polite" aria-labelledby="interpretation-title">
          {interpretation.status === 'matched' && interpretation.candidates.length > 0 && (
            <>
              <h2 id="interpretation-title">이곳이 맞나요?</h2>
              <p>{interpretation.candidates[0].name}</p>
              <div className={styles.actionList}>
                <button className="button button-primary" type="button" onClick={() => selectFirst(interpretation.candidates)}>
                  ✓ 네, 여기로 갈게요
                </button>
                <button className="button button-secondary" type="button" onClick={clearInterpretation}>
                  ✕ 다른 곳 찾기
                </button>
              </div>
            </>
          )}
          {interpretation.status === 'needs_confirmation' && interpretation.candidates.length === 1 && (
            <>
              <h2 id="interpretation-title">이곳을 찾으셨나요?</h2>
              <p>{interpretation.candidates[0].name}</p>
              <div className={styles.actionList}>
                <button className="button button-primary" type="button" onClick={() => selectFirst(interpretation.candidates)}>
                  ✓ 네, 여기로 갈게요
                </button>
                <button className="button button-secondary" type="button" onClick={clearInterpretation}>
                  ✕ 다른 곳 찾기
                </button>
              </div>
            </>
          )}
          {interpretation.status === 'needs_confirmation' && interpretation.candidates.length > 1 && (
            <>
              <h2 id="interpretation-title">어디로 가시나요?</h2>
              <p>아래에서 가실 곳을 골라 주세요.</p>
              <div className={styles.destinationList}>
                {interpretation.candidates.map((destination) => (
                  <button className="button button-secondary" key={destination.destinationId} type="button" onClick={() => onSelect(destination)}>
                    {destination.name}
                  </button>
                ))}
              </div>
              <button className="button button-secondary" type="button" onClick={clearInterpretation}>✕ 다른 곳 찾기</button>
            </>
          )}
          {interpretation.status === 'no_match' && (
            <>
              <h2 id="interpretation-title">찾는 곳이 목록에 없어요</h2>
              <p>아래 주요 장소에서 고르거나 다시 입력해 주세요.</p>
              <button className="button button-secondary" type="button" onClick={() => { clearInterpretation(); setQuery('') }}>
                다시 입력
              </button>
            </>
          )}
        </section>
      )}

      <section className={styles.section} aria-labelledby="destination-results-title">
        <h2 id="destination-results-title">검색 결과</h2>
        {!loading && !error && destinations.length === 0 && (
          <p className="message">등록된 목적지가 없습니다. 다시 검색하거나 주요 장소를 선택해 주세요.</p>
        )}
        <div className={styles.destinationList}>
          {destinations.map((destination) => (
            <button className="button button-secondary" key={destination.destinationId} type="button" onClick={() => onSelect(destination)}>
              {destination.name}
            </button>
          ))}
        </div>
      </section>
    </main>
  )
}
