import { useCallback, useEffect, useRef, useState } from 'react';
import s from '../../app/App.module.css';
import { api, ApiError } from '../../shared/api/client';
import { MicrophoneIcon } from './MicrophoneIcon';
import { recordingType, recordSpeech } from './recordSpeech';

interface Recognition {
  lang: string;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  abort(): void;
}

const browser = window as Window & {
  SpeechRecognition?: new () => Recognition;
  webkitSpeechRecognition?: new () => Recognition;
};

const LISTENING_WINDOW_MS = 3000;
const RETRY_DELAY_MS = 150;
const NO_SPEECH_MESSAGE = '들은 내용이 없어요. 다시 말하거나 글로 입력해 주세요.';
const CONFIRM_MESSAGE = '입력된 말을 확인하고 버튼을 눌러 주세요.';

interface Capture {
  controller: AbortController;
  stop?: () => void;
}

interface Props {
  disabled: boolean;
  onListen: () => void;
  onText: (text: string) => void;
  variant?: 'destination' | 'question';
  onListeningChange?: (listening: boolean) => void;
}

export function SpeechInput({ disabled, onListen, onText, variant = 'question', onListeningChange }: Props) {
  const active = useRef<Recognition | null>(null);
  const capture = useRef<Capture | null>(null);
  const retry = useRef<number | null>(null);
  const [listening, setListening] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [message, setMessage] = useState('');
  const SpeechRecognition = browser.SpeechRecognition ?? browser.webkitSpeechRecognition;
  const mimeType = recordingType();
  const available = Boolean(mimeType || SpeechRecognition);
  const destination = variant === 'destination';

  useEffect(() => { onListeningChange?.(listening); }, [listening, onListeningChange]);

  const abort = useCallback(() => {
    if (retry.current !== null) {
      window.clearTimeout(retry.current);
      retry.current = null;
    }
    const recognition = active.current;
    const recording = capture.current;
    active.current = null;
    capture.current = null;
    recognition?.abort();
    recording?.controller.abort();
  }, []);

  const cancel = useCallback(() => {
    if (!active.current && !capture.current && retry.current === null) return;
    abort();
    setListening(false);
    setProcessing(false);
    setMessage('');
  }, [abort]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.hidden) cancel();
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      abort();
    };
  }, [abort, cancel]);

  useEffect(() => {
    if (disabled) cancel();
  }, [disabled, cancel]);

  async function startCapture(type: string) {
    const session: Capture = { controller: new AbortController() };
    const { signal } = session.controller;
    capture.current = session;
    let browserFallback = false;
    onListen();
    setListening(true);
    setMessage('마이크를 준비하고 있어요.');
    try {
      const audio = await recordSpeech(type, signal, stop => {
        session.stop = stop;
        setMessage('듣고 있어요. 말을 마치면 버튼을 다시 눌러 주세요.');
      });
      if (signal.aborted) return;
      if (!audio.size) {
        setMessage(NO_SPEECH_MESSAGE);
        return;
      }
      setProcessing(true);
      setMessage('말씀하신 내용을 확인하고 있어요.');
      const { data } = await api.transcribe(audio, signal);
      if (signal.aborted) return;
      const transcript = data.text.trim().slice(0, 200);
      setMessage(transcript ? CONFIRM_MESSAGE : NO_SPEECH_MESSAGE);
      if (transcript) onText(transcript);
    } catch (error) {
      if (signal.aborted) return;
      if (error instanceof ApiError) {
        browserFallback = Boolean(SpeechRecognition && (error.status === 404 || error.code === 'SPEECH_UNAVAILABLE'));
        setMessage(error.message);
      } else if (error instanceof DOMException && ['NotAllowedError', 'SecurityError'].includes(error.name)) {
        setMessage('마이크 사용을 허용하거나 글로 입력해 주세요.');
      } else {
        setMessage('마이크 연결을 확인하거나 글로 입력해 주세요.');
      }
    } finally {
      if (capture.current === session) {
        capture.current = null;
        setListening(false);
        setProcessing(false);
      }
    }
    if (browserFallback) startNative();
  }

  function toggle() {
    if (capture.current?.stop) { capture.current.stop(); return; }
    if (capture.current || active.current || retry.current !== null) { cancel(); return; }
    if (mimeType) void startCapture(mimeType);
    else startNative();
  }

  function startNative() {
    if (!SpeechRecognition) return;
    const Recognition = SpeechRecognition;
    const deadline = performance.now() + LISTENING_WINDOW_MS;
    function finish(message?: string) {
      abort();
      setListening(false);
      if (message) setMessage(message);
    }

    function startAttempt() {
      try {
        const recognition = new Recognition();
        recognition.lang = 'ko-KR';
        let received = false;
        let failureMessage = NO_SPEECH_MESSAGE;
        active.current = recognition;
        recognition.onresult = event => {
          if (active.current !== recognition) return;
          const transcript = event.results[0]?.[0]?.transcript.trim().slice(0, 200);
          if (!transcript) return;
          received = true;
          onText(transcript);
          setMessage(CONFIRM_MESSAGE);
        };
        recognition.onerror = ({ error }) => {
          if (active.current !== recognition) return;
          // Wait for onend before reopening a recognizer that stopped early.
          if (error === 'no-speech') return;
          if (error === 'network') {
            failureMessage = '음성 인식 서비스에 연결하지 못했어요. 다시 시도하거나 글로 입력해 주세요.';
            return;
          }
          if (error === 'not-allowed' || error === 'service-not-allowed') {
            finish('마이크 사용을 허용하거나 글로 입력해 주세요.');
          } else if (error === 'audio-capture') {
            finish('마이크 연결을 확인하거나 글로 입력해 주세요.');
          } else {
            finish('음성을 인식하지 못했어요. 다시 말하거나 글로 입력해 주세요.');
          }
        };
        recognition.onend = () => {
          if (active.current !== recognition) return;
          active.current = null;
          const remaining = deadline - performance.now();
          if (received || remaining <= 0) {
            finish(received ? undefined : failureMessage);
            return;
          }
          retry.current = window.setTimeout(() => {
            retry.current = null;
            if (performance.now() < deadline) startAttempt();
            else finish(failureMessage);
          }, Math.min(RETRY_DELAY_MS, remaining));
        };
        recognition.start();
      } catch {
        finish('마이크를 시작하지 못했어요. 글로 입력해 주세요.');
      }
    }

    onListen();
    setListening(true);
    setMessage('듣고 있어요. 천천히 말씀해 주세요.');
    startAttempt();
  }

  return <div className={destination ? s.destinationSpeech : s.speechInput}>
    {destination && <p role="status">{available ? message : '이 브라우저에서는 글로 입력해 주세요.'}</p>}
    {available && <button type="button" className={destination ? `${s.primary} ${s.destinationMic}` : `${s.helperButton} ${s.micButton}`} aria-pressed={listening}
      disabled={disabled || processing} onClick={toggle}>
      {destination && <MicrophoneIcon className={s.micIcon} />}
      {processing ? '인식 중' : destination ? (listening ? '듣고 있어요' : '말하기') : (listening ? '말하기 중지' : '마이크로 말하기')}
      {!destination && <MicrophoneIcon className={s.micIcon} />}
    </button>}
    {!destination && <p role="status">{available ? message : '이 브라우저에서는 글이나 화면 버튼으로 이용해 주세요.'}</p>}
  </div>;
}
