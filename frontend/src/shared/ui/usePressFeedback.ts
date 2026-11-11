import { useEffect } from 'react';

const ACTIONABLE = 'button, input[type="button"], input[type="submit"], input[type="reset"], [role="button"], a[href]';
const TOUCH_SLOP = 12;

interface PointerPress {
  target: HTMLElement;
  startX: number;
  startY: number;
  pointerType: string;
  inside: boolean;
}

function control(target: EventTarget | null): HTMLElement | null {
  return target instanceof Element ? target.closest<HTMLElement>(ACTIONABLE) : null;
}

function disabled(target: HTMLElement): boolean {
  return target.matches(':disabled') || target.closest('[aria-disabled="true"], [inert]') !== null;
}

/** Visual feedback only: selection and the control's action remain with the caller. */
export function usePressFeedback(): void {
  useEffect(() => {
    const pointers = new Map<number, PointerPress>();
    const keys = new Map<string, HTMLElement>();
    const marked = new Set<HTMLElement>();

    function update(target: HTMLElement) {
      const down = !disabled(target) && (
        [...pointers.values()].some(press => press.target === target && press.inside) ||
        [...keys.values()].includes(target)
      );
      if (down) {
        target.setAttribute('data-pressed', 'true');
        marked.add(target);
      } else {
        target.removeAttribute('data-pressed');
        marked.delete(target);
      }
    }

    function releasePointer(id: number) {
      const press = pointers.get(id);
      if (!press) return;
      pointers.delete(id);
      update(press.target);
    }

    function clearPointers() {
      const targets = [...pointers.values()].map(press => press.target);
      pointers.clear();
      targets.forEach(update);
    }

    function clearAll() {
      pointers.clear();
      keys.clear();
      marked.forEach(target => target.removeAttribute('data-pressed'));
      marked.clear();
    }

    function pointerDown(event: PointerEvent) {
      if (event.button !== 0) return;
      const target = control(event.target);
      if (!target || disabled(target)) return;
      releasePointer(event.pointerId);
      pointers.set(event.pointerId, {
        target, startX: event.clientX, startY: event.clientY,
        pointerType: event.pointerType, inside: true,
      });
      update(target);
    }

    function pointerMove(event: PointerEvent) {
      const press = pointers.get(event.pointerId);
      if (!press) return;
      if (press.pointerType !== 'mouse' && Math.hypot(event.clientX - press.startX, event.clientY - press.startY) > TOUCH_SLOP) {
        releasePointer(event.pointerId);
        return;
      }
      const rect = press.target.getBoundingClientRect();
      press.inside = event.clientX >= rect.left && event.clientX <= rect.right &&
        event.clientY >= rect.top && event.clientY <= rect.bottom;
      update(press.target);
    }

    const pointerEnd = (event: PointerEvent) => releasePointer(event.pointerId);
    function keyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') { clearAll(); return; }
      if (![' ', 'Spacebar', 'Enter'].includes(event.key) || event.repeat) return;
      const target = control(event.target);
      if (!target || disabled(target) || (target.tagName === 'A' && event.key !== 'Enter')) return;
      keys.set(event.key, target);
      update(target);
    }

    function keyUp(event: KeyboardEvent) {
      const target = keys.get(event.key);
      if (!target) return;
      keys.delete(event.key);
      update(target);
    }

    function focusOut(event: FocusEvent) {
      const target = control(event.target);
      if (!target) return;
      keys.forEach((value, key) => { if (value === target) keys.delete(key); });
      update(target);
    }

    function click(event: MouseEvent) {
      const target = control(event.target);
      if (target && disabled(target)) {
        event.preventDefault();
        event.stopPropagation();
        update(target);
      }
    }
    const visibilityChange = () => { if (document.hidden) clearAll(); };

    // Capture sees keyboard keys even when a virtual keyboard prevents default focus.
    document.addEventListener('pointerdown', pointerDown, true);
    window.addEventListener('pointermove', pointerMove, true);
    window.addEventListener('pointerup', pointerEnd, true);
    window.addEventListener('pointercancel', pointerEnd, true);
    window.addEventListener('lostpointercapture', pointerEnd, true);
    document.addEventListener('keydown', keyDown, true);
    window.addEventListener('keyup', keyUp, true);
    document.addEventListener('focusout', focusOut, true);
    document.addEventListener('click', click, true);
    document.addEventListener('scroll', clearPointers, true);
    document.addEventListener('visibilitychange', visibilityChange);
    window.addEventListener('blur', clearAll);

    return () => {
      clearAll();
      document.removeEventListener('pointerdown', pointerDown, true);
      window.removeEventListener('pointermove', pointerMove, true);
      window.removeEventListener('pointerup', pointerEnd, true);
      window.removeEventListener('pointercancel', pointerEnd, true);
      window.removeEventListener('lostpointercapture', pointerEnd, true);
      document.removeEventListener('keydown', keyDown, true);
      window.removeEventListener('keyup', keyUp, true);
      document.removeEventListener('focusout', focusOut, true);
      document.removeEventListener('click', click, true);
      document.removeEventListener('scroll', clearPointers, true);
      document.removeEventListener('visibilitychange', visibilityChange);
      window.removeEventListener('blur', clearAll);
    };
  }, []);
}
