import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RestTimer } from '../../../../src/features/workouts/TodayWorkout';
import { activeWorkoutRestKey } from '../../../../src/features/workouts/activeWorkoutQueue';

vi.mock('../../../../src/shared/telegram/useTelegram', () => ({ haptic: vi.fn() }));

const key = activeWorkoutRestKey(7, 42);
const initialTime = new Date('2026-10-10T12:00:00Z').getTime();

function mount() {
  return render(
    <section className="active-workout">
      <RestTimer
        userId={7}
        workoutId={42}
        nextLabel="Жим штанги лёжа, подход 2"
        nextExercise="Жим штанги лёжа"
        nextPosition="Подход 2 из 3"
      />
      <div className="active-workout-exercises">
        <input aria-label="Вес" defaultValue="42.5" />
        <button type="button">Отдельное действие</button>
      </div>
    </section>,
  );
}

function pointer(target: Element, type: string, pointerId = 1) {
  fireEvent(target, Object.assign(new Event(type, { bubbles: true }), { pointerId }));
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(initialTime);
  localStorage.clear();
  localStorage.setItem(key, JSON.stringify(initialTime + 90_000));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('RestTimer', () => {
  it('extends the existing scoped deadline with native clicks and preserves field focus', () => {
    mount();
    const weight = screen.getByRole('textbox', { name: 'Вес' });
    weight.focus();
    const add30 = screen.getByRole('button', { name: '+30 сек' });
    expect(fireEvent.mouseDown(add30)).toBe(false);
    fireEvent.click(add30);
    fireEvent.click(screen.getByRole('button', { name: '+60 сек' }));
    fireEvent.click(add30);
    fireEvent.click(add30);
    expect(screen.getByRole('timer')).toHaveTextContent('4:00');
    expect(screen.getByRole('timer')).toHaveAttribute('aria-live', 'off');
    expect(JSON.parse(localStorage.getItem(key)!)).toBe(initialTime + 240_000);
    expect(weight).toHaveFocus();
    expect(weight).toHaveValue('42.5');
  });

  it('keeps the skip hit surface beyond 600 ms until a separate outside gesture completes', () => {
    mount();
    const skip = screen.getByRole('button', { name: 'Пропустить' });
    pointer(skip, 'pointerdown');
    pointer(skip, 'pointerup');
    fireEvent.click(skip);
    expect(localStorage.getItem(key)).toBeNull();
    act(() => vi.advanceTimersByTime(10_000));
    expect(skip).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(skip);
    fireEvent.click(screen.getByRole('button', { name: '+60 сек' }));
    expect(localStorage.getItem(key)).toBeNull();
    const weight = screen.getByRole('textbox', { name: 'Вес' });
    pointer(weight, 'pointerdown', 2);
    fireEvent.focusIn(weight);
    fireEvent.scroll(window);
    expect(skip).toBeVisible();
    pointer(weight, 'pointerup', 2);
    fireEvent.click(weight);
    expect(skip).not.toBeVisible();
    const hide = screen.getByRole('button', { name: 'Скрыть' });
    fireEvent.click(hide);
    act(() => vi.advanceTimersByTime(10_000));
    expect(hide).toHaveTextContent('Скрыто');
    fireEvent.click(hide);
    expect(screen.getByRole('complementary')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Отдельное действие' }));
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
  });

  it('retains the pressed control when the deadline expires and ignores its late click', () => {
    localStorage.setItem(key, JSON.stringify(initialTime + 1_000));
    mount();
    const add30 = screen.getByRole('button', { name: '+30 сек' });
    pointer(add30, 'pointerdown');
    act(() => vi.advanceTimersByTime(1_000));
    fireEvent.focusIn(screen.getByRole('textbox', { name: 'Вес' }));
    fireEvent.scroll(window);
    expect(add30).toBeVisible();
    pointer(add30, 'pointercancel');
    fireEvent.click(add30);
    expect(localStorage.getItem(key)).toBeNull();
    expect(screen.getByRole('status')).toHaveTextContent('Отдых завершён');
  });

  it('reconciles the stored deadline on resume and starts a new rest after skip', () => {
    mount();
    vi.setSystemTime(initialTime + 65_000);
    fireEvent(window, new Event('pageshow'));
    expect(screen.getByRole('timer')).toHaveTextContent('0:25');
    fireEvent.click(screen.getByRole('button', { name: 'Пропустить' }));
    act(() => {
      window.dispatchEvent(
        new CustomEvent('fit:rest', { detail: { workoutId: 99, seconds: 120 } }),
      );
    });
    expect(localStorage.getItem(key)).toBeNull();
    act(() => {
      window.dispatchEvent(
        new CustomEvent('fit:rest', { detail: { workoutId: 42, seconds: 120 } }),
      );
    });
    expect(screen.getByRole('timer')).toHaveTextContent('2:00');
    expect(screen.getByRole('button', { name: '+60 сек' })).toHaveAttribute(
      'aria-disabled',
      'false',
    );
    expect(JSON.parse(localStorage.getItem(key)!)).toBe(initialTime + 185_000);
  });

  it('releases interrupted pointers on pagehide without removing the skip hit surface', () => {
    mount();
    const skip = screen.getByRole('button', { name: 'Пропустить' });
    fireEvent.click(skip);
    pointer(skip, 'pointerdown', 8);
    fireEvent(window, new Event('pagehide'));
    fireEvent(window, new Event('pageshow'));
    expect(skip).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Отдельное действие' }));
    expect(skip).not.toBeVisible();
    expect(localStorage.getItem(key)).toBeNull();
  });
});
