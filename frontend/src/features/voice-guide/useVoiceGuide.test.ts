// @vitest-environment jsdom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useVoiceGuide, type VoiceGuide } from './useVoiceGuide';

class Utterance {
  text: string;
  voice: SpeechSynthesisVoice | null = null;
  lang = '';
  rate = 1;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(text: string) { this.text = text; }
}

const koreanVoice = { lang: 'ko-KR', name: '한국어', localService: true } as SpeechSynthesisVoice;
let voices: SpeechSynthesisVoice[];
let voiceChanged: (() => void) | undefined;
let controller: VoiceGuide;
let root: Root | undefined;
let host: HTMLDivElement;
const speak = vi.fn<(utterance: Utterance) => void>();
const cancel = vi.fn();

function Harness() { controller = useVoiceGuide(); return null; }
function mount() {
  host = document.createElement('div');
  document.body.append(host);
  root = createRoot(host);
  act(() => root?.render(createElement(Harness)));
}

beforeEach(() => {
  voices = [koreanVoice];
  voiceChanged = undefined;
  speak.mockReset(); cancel.mockReset();
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('SpeechSynthesisUtterance', Utterance);
  vi.stubGlobal('speechSynthesis', {
    getVoices: () => voices,
    speak,
    cancel,
    addEventListener: (_event: string, listener: () => void) => { voiceChanged = listener; },
    removeEventListener: () => { voiceChanged = undefined; },
  });
});

afterEach(() => {
  act(() => root?.unmount());
  root = undefined;
  host?.remove();
  vi.unstubAllGlobals();
});

describe('useVoiceGuide', () => {
  it('preserves screen guidance when speech APIs are absent', () => {
    vi.stubGlobal('speechSynthesis', undefined);
    vi.stubGlobal('SpeechSynthesisUtterance', undefined);
    mount();
    expect(controller.supported).toBe(false);
    expect(controller.message).toContain('화면 안내를 확인');
    act(() => controller.speak('화면 안내'));
    expect(speak).not.toHaveBeenCalled();
  });

  it('does not assume Korean speech support when only other languages are installed', () => {
    voices = [{ lang: 'en-US' } as SpeechSynthesisVoice];
    mount();
    expect(controller.supported).toBe(false);
    act(() => controller.speak('서버가 검증한 안내'));
    expect(speak).not.toHaveBeenCalled();
    expect(controller.message).toContain('한국어 음성을 사용할 수 없어요');
  });

  it('accepts asynchronously loaded Korean voices and reads the supplied text unchanged', () => {
    voices = [];
    mount();
    expect(controller.supported).toBe(false);
    voices = [koreanVoice];
    act(() => voiceChanged?.());
    expect(controller.supported).toBe(true);
    const text = '시연 데이터 · 실제 운행 정보 아님. 시연 1번 버스를 타세요.';
    act(() => controller.speak(text));
    const utterance = speak.mock.calls[0][0];
    expect(utterance.text).toBe(text);
    expect(utterance.voice).toBe(koreanVoice);
    expect(controller.speaking).toBe(true);
    act(() => utterance.onend?.());
    expect(controller.speaking).toBe(false);
    expect(controller.message).toContain('끝났어요');
  });

  it('cancels overlapping speech and ignores callbacks from replaced or stopped utterances', () => {
    mount();
    act(() => controller.speak('첫 안내'));
    const first = speak.mock.calls[0][0];
    act(() => controller.speak('다음 안내'));
    const second = speak.mock.calls[1][0];
    expect(cancel).toHaveBeenCalledTimes(2);
    act(() => first.onend?.());
    expect(controller.speaking).toBe(true);
    act(() => controller.stop());
    act(() => second.onerror?.());
    expect(controller.speaking).toBe(false);
    expect(controller.message).toContain('중지했어요');
  });

  it('keeps text guidance available after playback errors and does not speak empty text', () => {
    mount();
    act(() => controller.speak(''));
    expect(speak).not.toHaveBeenCalled();
    act(() => controller.speak('안내'));
    act(() => speak.mock.calls[0][0].onerror?.());
    expect(controller.speaking).toBe(false);
    expect(controller.message).toContain('화면 안내를 확인');
  });

  it('stops its active utterance and removes voice listeners on unmount', () => {
    mount();
    act(() => controller.speak('안내'));
    cancel.mockClear();
    act(() => root?.unmount());
    root = undefined;
    expect(cancel).toHaveBeenCalledOnce();
    expect(voiceChanged).toBeUndefined();
  });
});
