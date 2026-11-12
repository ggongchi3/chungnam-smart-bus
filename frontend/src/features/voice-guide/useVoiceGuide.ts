import { useCallback, useEffect, useRef, useState } from 'react';

export interface VoiceGuide {
  supported: boolean;
  speaking: boolean;
  message: string;
  speak: (text: string) => void;
  stop: () => void;
}

/** Reads only the text the caller supplies; it never generates journey facts. */
export function useVoiceGuide(): VoiceGuide {
  const [supported, setSupported] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [message, setMessage] = useState('한국어 음성을 확인하고 있어요.');
  const synthesis = useRef<SpeechSynthesis | null>(null);
  const voice = useRef<SpeechSynthesisVoice | null>(null);
  const current = useRef<SpeechSynthesisUtterance | null>(null);

  const stop = useCallback(() => {
    // Clear first: cancel() may synchronously report an interrupted utterance.
    current.current = null;
    synthesis.current?.cancel();
    setSpeaking(false);
    setMessage('음성 안내를 중지했어요.');
  }, []);

  useEffect(() => {
    if (!window.speechSynthesis || typeof window.SpeechSynthesisUtterance !== 'function') {
      setMessage('이 기기에서는 음성 안내를 사용할 수 없어요. 화면 안내를 확인해 주세요.');
      return;
    }
    const synth = window.speechSynthesis;
    synthesis.current = synth;
    const updateVoices = () => {
      const korean = synth.getVoices().filter((item) => /^ko(?:[-_]|$)/i.test(item.lang));
      voice.current = korean.find((item) => item.localService) ?? korean[0] ?? null;
      setSupported(voice.current !== null);
      if (!current.current) {
        setMessage(voice.current
          ? '음성 안내를 누르면 화면의 안내를 읽어드려요.'
          : '한국어 음성을 사용할 수 없어요. 화면 안내를 확인해 주세요.');
      }
    };
    updateVoices();
    synth.addEventListener('voiceschanged', updateVoices);
    const pauseWhenHidden = () => { if (document.hidden) stop(); };
    document.addEventListener('visibilitychange', pauseWhenHidden);
    return () => {
      synth.removeEventListener('voiceschanged', updateVoices);
      document.removeEventListener('visibilitychange', pauseWhenHidden);
      const hadCurrent = current.current !== null;
      current.current = null;
      if (hadCurrent) synth.cancel();
      synthesis.current = null;
      voice.current = null;
    };
  }, [stop]);

  const speak = useCallback((text: string) => {
    const synth = synthesis.current;
    current.current = null;
    synth?.cancel();
    setSpeaking(false);
    if (!synth || !voice.current) {
      setMessage('한국어 음성을 사용할 수 없어요. 화면 안내를 확인해 주세요.');
      return;
    }
    if (!text.trim()) {
      setMessage('읽어드릴 안내가 없어요. 화면 안내를 확인해 주세요.');
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.voice = voice.current;
    utterance.lang = voice.current.lang;
    utterance.rate = 0.9;
    current.current = utterance;
    utterance.onend = () => {
      if (current.current !== utterance) return;
      current.current = null;
      setSpeaking(false);
      setMessage('음성 안내가 끝났어요.');
    };
    utterance.onerror = () => {
      if (current.current !== utterance) return;
      current.current = null;
      setSpeaking(false);
      setMessage('음성 안내를 재생하지 못했어요. 화면 안내를 확인해 주세요.');
    };
    try {
      setSpeaking(true);
      setMessage('음성으로 안내하고 있어요. 다시 누르면 중지해요.');
      synth.speak(utterance);
    } catch {
      current.current = null;
      setSpeaking(false);
      setMessage('음성 안내를 재생하지 못했어요. 화면 안내를 확인해 주세요.');
    }
  }, []);

  return { supported, speaking, message, speak, stop };
}
