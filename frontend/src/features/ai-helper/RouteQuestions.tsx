import { useState } from 'react';
import type { AnswerData, JourneyIntent } from '../../shared/api/types';
import { displayText } from '../../shared/places';
import { SpeechInput } from './SpeechInput';
import s from '../../app/App.module.css';

const questions = ['몇 번 버스 타요?', '어디서 타요?', '어디서 내려요?', '몇 정거장 가요?', '얼마나 걸어요?', '다시 말해 주세요'];

interface Props {
  busy: boolean;
  allowSpeechInput: boolean;
  speaking: boolean;
  onAsk: (question: string, previousIntent: JourneyIntent | null, receive: (answer: AnswerData) => void) => void;
  onRead: (text: string) => void;
  onStop: () => void;
}

export function RouteQuestions({ busy, allowSpeechInput, speaking, onAsk, onRead, onStop }: Props) {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [lastIntent, setLastIntent] = useState<JourneyIntent | null>(null);

  function ask(value: string) {
    if (!value.trim() || busy) return;
    onStop();
    onAsk(value, lastIntent, result => {
      const text = result.text && displayText(result.text);
      setAnswer(text || '질문에 답하기 어려워요. 아래 경로 안내를 확인해 주세요.');
      if (text) {
        if (result.intent && result.intent !== 'repeat' && result.intent !== 'unknown') setLastIntent(result.intent);
        onRead(text);
      }
    });
  }

  return <section className={s.questionPanel} aria-labelledby="route-questions">
    <h2 id="route-questions">AI 도우미에게 물어보기</h2>
    <div className={s.questionButtons}>{questions.map(value =>
      <button type="button" key={value} className={s.helperButton} disabled={busy} onClick={() => ask(value)}>{value}</button>
    )}</div>
    <form onSubmit={event => { event.preventDefault(); ask(question); }}>
      <label className={s.inputWrap}>
        <input aria-label="경로 질문" placeholder="궁금한 내용을 입력해 주세요" value={question}
          maxLength={200} onChange={event => setQuestion(event.target.value)} />
      </label>
      <div className={s.questionActions}>
        {allowSpeechInput && <SpeechInput disabled={busy} onListen={onStop} onText={setQuestion} />}
        <button type="submit" className={s.primary} disabled={busy || !question.trim()}>질문하기</button>
      </div>
    </form>
    {answer && <div className={s.answer}>
      <p aria-live="polite">{answer}</p>
      <button type="button" className={s.helperButton} onClick={() => speaking ? onStop() : onRead(answer)}>
        {speaking ? '읽기 중지' : '답변 읽기'}
      </button>
    </div>}
  </section>;
}
