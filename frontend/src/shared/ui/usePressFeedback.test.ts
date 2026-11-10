import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { usePressFeedback } from './usePressFeedback';

let root: Root | undefined;
let host: HTMLDivElement;
let controls: HTMLDivElement;
let first: HTMLButtonElement;
let second: HTMLButtonElement;
let icon: HTMLElement;

function Harness() { usePressFeedback(); return null; }
function pointer(target: EventTarget, type: string, id = 1, pointerType = 'mouse', x = 20, y = 20) {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, clientX: x, clientY: y });
  Object.defineProperties(event, { pointerId: { value: id }, pointerType: { value: pointerType } });
  target.dispatchEvent(event);
}
function keyboard(target: EventTarget, type: 'keydown' | 'keyup', key: string) {
  target.dispatchEvent(new KeyboardEvent(type, { bubbles: true, cancelable: true, key }));
}

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  host = document.createElement('div');
  controls = document.createElement('div');
  controls.innerHTML = '<button aria-pressed="false"><span>검색</span></button><button>처음으로</button>';
  document.body.append(host, controls);
  [first, second] = Array.from(controls.querySelectorAll('button'));
  icon = first.querySelector('span')!;
  [first, second].forEach(button => vi.spyOn(button, 'getBoundingClientRect').mockReturnValue({ left: 0, right: 100, top: 0, bottom: 100, width: 100, height: 100, x: 0, y: 0, toJSON: () => ({}) }));
  root = createRoot(host);
  act(() => root!.render(createElement(Harness)));
});
afterEach(() => {
  act(() => root?.unmount());
  root = undefined;
  host.remove(); controls.remove();
  vi.unstubAllGlobals();
});

describe('held press feedback', () => {
  it('marks the button behind an icon and releases outside without changing its selection', () => {
    pointer(icon, 'pointerdown');
    expect(first.getAttribute('data-pressed')).toBe('true');
    expect(first.getAttribute('aria-pressed')).toBe('false');
    pointer(document.body, 'pointerup');
    expect(first.hasAttribute('data-pressed')).toBe(false);
    pointer(first, 'pointerdown');
    pointer(window, 'pointermove', 1, 'mouse', 140, 20);
    expect(first.hasAttribute('data-pressed')).toBe(false);
    pointer(window, 'pointermove', 1, 'mouse', 50, 20);
    expect(first.getAttribute('data-pressed')).toBe('true');
    pointer(window, 'pointerup');
    expect(first.hasAttribute('data-pressed')).toBe(false);
  });

  it('handles simultaneous touches and cancels only the released pointer', () => {
    pointer(first, 'pointerdown', 10, 'touch');
    pointer(second, 'pointerdown', 11, 'touch');
    expect(first.hasAttribute('data-pressed')).toBe(true);
    expect(second.hasAttribute('data-pressed')).toBe(true);
    pointer(window, 'pointercancel', 10, 'touch');
    expect(first.hasAttribute('data-pressed')).toBe(false);
    expect(second.hasAttribute('data-pressed')).toBe(true);
    pointer(window, 'lostpointercapture', 11, 'touch');
    expect(second.hasAttribute('data-pressed')).toBe(false);
  });

  it('cancels a scrolling touch without grabbing pointer capture or restoring a cancelled drag', () => {
    const capture = vi.fn();
    first.setPointerCapture = capture;
    pointer(first, 'pointerdown', 1, 'touch');
    pointer(window, 'pointermove', 1, 'touch', 20, 50);
    expect(first.hasAttribute('data-pressed')).toBe(false);
    pointer(window, 'pointermove', 1, 'touch', 20, 20);
    expect(first.hasAttribute('data-pressed')).toBe(false);
    pointer(first, 'pointerdown', 2, 'touch');
    controls.dispatchEvent(new Event('scroll'));
    expect(first.hasAttribute('data-pressed')).toBe(false);
    expect(capture).not.toHaveBeenCalled();
  });

  it('keeps keyboard feedback until keyup and clears it when focus moves', () => {
    keyboard(first, 'keydown', ' ');
    expect(first.hasAttribute('data-pressed')).toBe(true);
    keyboard(window, 'keyup', ' ');
    expect(first.hasAttribute('data-pressed')).toBe(false);
    keyboard(second, 'keydown', 'Enter');
    expect(second.hasAttribute('data-pressed')).toBe(true);
    second.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
    expect(second.hasAttribute('data-pressed')).toBe(false);
  });

  it('does not activate native or aria disabled actions', () => {
    first.disabled = true;
    second.setAttribute('aria-disabled', 'true');
    const action = vi.fn(); second.addEventListener('click', action);
    pointer(first, 'pointerdown'); keyboard(first, 'keydown', 'Enter');
    pointer(second, 'pointerdown', 2); keyboard(second, 'keydown', ' ');
    second.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    expect(first.hasAttribute('data-pressed')).toBe(false);
    expect(second.hasAttribute('data-pressed')).toBe(false);
    expect(action).not.toHaveBeenCalled();
  });

  it('clears held feedback on blur and unmount, then removes global listeners', () => {
    pointer(first, 'pointerdown'); keyboard(second, 'keydown', 'Enter');
    window.dispatchEvent(new Event('blur'));
    expect(first.hasAttribute('data-pressed')).toBe(false);
    expect(second.hasAttribute('data-pressed')).toBe(false);
    pointer(first, 'pointerdown');
    act(() => root!.unmount()); root = undefined;
    expect(first.hasAttribute('data-pressed')).toBe(false);
    pointer(second, 'pointerdown', 2);
    expect(second.hasAttribute('data-pressed')).toBe(false);
  });
});
