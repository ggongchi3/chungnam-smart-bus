import { useState } from 'react';
import Hangul from 'hangul-js';
import styles from './Keyboard.module.css';

interface KeyboardProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  maxLength?: number;
  submitLabel?: string;
}

/** Recompose actual jamo: 받침 moves to the next syllable when a vowel follows. */
export function appendKey(value: string, key: string): string {
  return composeKey(value, key, 100);
}

function composeKey(value: string, key: string, maxLength: number): string {
  const result = Hangul.assemble([...(Hangul.disassemble(value) as string[]), ...Array.from(key)]);
  return result.length <= maxLength ? result : value;
}

/** Remove one jamo, including one half of a compound 받침, rather than a syllable. */
export function deleteCharacter(value: string): string {
  const jamo = Hangul.disassemble(value) as string[];
  jamo.pop();
  return Hangul.assemble(jamo);
}

const korean = [Array.from('ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔ'), Array.from('ㅁㄴㅇㄹㅎㅗㅓㅏㅣ-'), Array.from('ㅋㅌㅊㅍㅠㅜㅡ,.?')];
const english = [Array.from('qwertyuiop'), Array.from('asdfghjkl-'), Array.from('zxcvbnm,.?')];
const symbols = [Array.from('!@#$%^&*()'), Array.from('~_+=[]{}<>'), Array.from('/\\:;\'"`|·?')];
const shifted: Record<string, string> = { 'ㅂ': 'ㅃ', 'ㅈ': 'ㅉ', 'ㄷ': 'ㄸ', 'ㄱ': 'ㄲ', 'ㅅ': 'ㅆ', 'ㅐ': 'ㅒ', 'ㅔ': 'ㅖ' };

export default function Keyboard({ value, onChange, onSubmit, disabled = false, maxLength = 100, submitLabel = '검색하기' }: KeyboardProps) {
  const [language, setLanguage] = useState<'ko' | 'en'>('ko');
  const [symbolMode, setSymbolMode] = useState(false);
  const [shift, setShift] = useState(false);
  const rows = symbolMode ? symbols : language === 'ko' ? korean : english;
  const apply = (key: string) => {
    onChange(composeKey(value, key, maxLength));
    setShift(false);
  };
  const display = (key: string) => shift && !symbolMode
    ? language === 'ko' ? shifted[key] ?? key : key.toUpperCase()
    : key;

  return (
    <div className={styles.keyboard} aria-label="화면 키보드" onPointerDown={event => event.preventDefault()}>
      <div className={styles.keys}>
        <div className={styles.row}>
          {Array.from('1234567890').map(key => <button key={key} type="button" disabled={disabled} onClick={() => apply(key)}>{key}</button>)}
          <button className={`${styles.wide} ${styles.utility}`} type="button" disabled={disabled} aria-label="한 글자 지우기" onClick={() => onChange(deleteCharacter(value))}>
            <span className={styles.icon}><img src="/assets/cdc36.svg" alt="" /></span>
            <span>지우기</span>
          </button>
        </div>
        <div className={styles.row}>
          {rows[0].map(key => <button key={key} type="button" disabled={disabled} onClick={() => apply(display(key))}>{display(key)}</button>)}
          <button type="button" className={styles.utility} disabled={disabled} aria-pressed={symbolMode} onClick={() => setSymbolMode(!symbolMode)}>기호</button>
          <button type="button" className={styles.utility} disabled={disabled} aria-label={language === 'ko' ? '영문 키보드로 전환' : '한글 키보드로 전환'} onClick={() => { setLanguage(language === 'ko' ? 'en' : 'ko'); setSymbolMode(false); setShift(false); }}>한/영</button>
        </div>
        <div className={styles.row}>
          {rows[1].map(key => <button key={key} type="button" disabled={disabled} onClick={() => apply(display(key))}>{display(key)}</button>)}
          <button className={`${styles.wide} ${styles.utility}`} type="button" disabled={disabled} aria-label={language === 'ko' ? '쌍자음 전환' : '대문자 전환'} aria-pressed={shift} onClick={() => setShift(!shift)}>
            <span className={styles.icon}><img src="/assets/97449.svg" alt="" /></span>
            <span>{language === 'ko' ? '쌍자음' : '대문자'}</span>
          </button>
        </div>
        <div className={styles.row}>
          {rows[2].map(key => <button key={key} type="button" disabled={disabled} onClick={() => apply(display(key))}>{display(key)}</button>)}
          <button className={`${styles.wide} ${styles.utility}`} type="button" disabled={disabled} onClick={() => apply(' ')}>한칸 띄우기</button>
        </div>
      </div>
      <button type="button" className={styles.submit} disabled={disabled || !value.trim()} onClick={onSubmit}>{submitLabel}</button>
    </div>
  );
}
