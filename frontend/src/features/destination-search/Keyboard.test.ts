import { describe, expect, it } from 'vitest';
import { appendKey, deleteCharacter } from './Keyboard';

const type = (keys: string) => Array.from(keys).reduce(appendKey, '');

describe('Korean on-screen keyboard composition', () => {
  it('composes syllables and moves a final consonant to the next vowel', () => {
    expect(type('ㅂㅕㅇㅇㅝㄴ')).toBe('병원');
    expect(type('ㄱㅏㄴㅏ')).toBe('가나');
    expect(type('ㅅㅣㅈㅏㅇ')).toBe('시장');
  });

  it('supports double consonants and compound final consonants', () => {
    expect(type('ㄲㅏㅊㅣ')).toBe('까치');
    expect(type('ㄷㅏㄹㄱ')).toBe('닭');
    expect(type('ㄷㅏㄹㄱㅏ')).toBe('달가');
  });

  it('deletes a jamo at a time instead of deleting an entire syllable', () => {
    expect(deleteCharacter('닭')).toBe('달');
    expect(deleteCharacter('달')).toBe('다');
    expect(deleteCharacter('다')).toBe('ㄷ');
    expect(deleteCharacter('ㄷ')).toBe('');
    expect(deleteCharacter('')).toBe('');
  });

  it('keeps numeric, Latin, symbol and space input intact', () => {
    expect(appendKey('병원 ', 'A')).toBe('병원 A');
    expect(type('123-ABC ?')).toBe('123-ABC ?');
    expect(type('ㄱㅏ ㄴㅏ')).toBe('가 나');
  });

  it('respects the API search limit without blocking completion of the last syllable', () => {
    const prefix = '가'.repeat(99);
    expect(appendKey(prefix + 'ㄱ', 'ㅏ')).toBe(prefix + '가');
    expect(appendKey('가'.repeat(100), '1')).toBe('가'.repeat(100));
  });
});
