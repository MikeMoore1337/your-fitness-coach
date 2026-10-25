import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RestTimer } from '../../../../src/features/workouts/TodayWorkout';
import { activeWorkoutRestKey } from '../../../../src/features/workouts/activeWorkoutQueue';
import {
  beginMeasuredRest,
  loadRestJournal,
  updateMeasuredRest,
} from '../../../../src/features/workouts/restSessions';
import { legacyWorkoutRestStorageKey } from '../../../../src/shared/userScopedStorage';

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
        eligibleRestSourceSetIds={[201]}
      />
      <div className="active-workout-exercises">
        <input aria-label="Вес" defaultValue="42.5" />
        <button type="button">Отдельное действие</button>
      </div>
    </section>,
  );
}

function startUnmeasuredRest(deadline = initialTime + 90_000, seconds = 90) {
  act(() => {
    window.dispatchEvent(
      new CustomEvent('fit:rest', { detail: { workoutId: 42, seconds, deadline } }),
    );
  });
}

function pointer(target: Element, type: string, pointerId = 1) {
  fireEvent(target, Object.assign(new Event(type, { bubbles: true }), { pointerId }));
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(initialTime);
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('RestTimer', () => {
  it('does not resurrect a deadline-only legacy timer after resume', () => {
    localStorage.removeItem(key);
    localStorage.setItem(legacyWorkoutRestStorageKey(42), JSON.stringify(initialTime + 90_000));

    mount();

    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
    expect(localStorage.getItem(legacyWorkoutRestStorageKey(42))).toBeNull();
  });

  it('does not resurrect a deadline-only scoped timer after resume', () => {
    localStorage.setItem(key, JSON.stringify(initialTime + 90_000));

    mount();

    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
    expect(localStorage.getItem(key)).toBeNull();
  });

  it('restores the measured panel when resume follows a durable rest journal', () => {
    localStorage.removeItem(key);
    expect(beginMeasuredRest(7, 42, 201, 90, initialTime)).not.toBeNull();

    mount();

    expect(screen.getByRole('complementary')).toHaveTextContent('ФАКТ');
    expect(screen.getByRole('button', { name: 'Завершить отдых' })).toBeVisible();
  });

  it('ignores a replayed completion event after its measured rest is terminal', () => {
    localStorage.removeItem(key);
    expect(beginMeasuredRest(7, 42, 201, 90, initialTime)).not.toBeNull();
    expect(updateMeasuredRest(7, 42, 201, 'complete', initialTime + 30_000)).not.toBeNull();

    mount();
    act(() => {
      window.dispatchEvent(
        new CustomEvent('fit:rest', {
          detail: { workoutId: 42, setId: 201, seconds: 90 },
        }),
      );
    });

    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
  });

  it('uses an uppercase FACT label with a real, explicitly stoppable measured clock', () => {
    mount();
    act(() => {
      window.dispatchEvent(
        new CustomEvent('fit:rest', {
          detail: { workoutId: 42, setId: 201, seconds: 90 },
        }),
      );
    });
    const panel = screen.getByRole('complementary', { name: 'Отдых между подходами' });
    expect(panel.querySelector('.active-workout-rest__actual-value span')).toHaveTextContent(
      'ФАКТ',
    );
    expect(panel.querySelector('.active-workout-rest__actual-value strong')).toHaveTextContent(
      '0:00',
    );
    expect(screen.getByRole('timer', { name: 'Отдых' })).toHaveTextContent('1:30');
    expect(screen.getByRole('button', { name: 'Завершить отдых' })).toBeVisible();
  });

  it('clears an expired deadline-only timer on resume', () => {
    localStorage.setItem(key, JSON.stringify(initialTime - 1));

    mount();

    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
    expect(localStorage.getItem(key)).toBeNull();
  });

  it('shows the compact completion notice without an external event', () => {
    mount();
    startUnmeasuredRest(initialTime - 1);

    const panel = screen.getByRole('complementary');
    expect(panel).toHaveClass('is-compact');
    expect(screen.getByRole('button', { name: 'Скрыть' })).toBeVisible();
    expect(panel).toHaveTextContent('Отдых завершён · дальше: Жим штанги лёжа, подход 2');
  });

  it('removes the completion notice from the DOM on the first hide action', () => {
    mount();
    startUnmeasuredRest(initialTime - 1);

    fireEvent.click(screen.getByRole('button', { name: 'Скрыть' }));

    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
  });

  it('compacts after a real deadline without an external event', async () => {
    vi.useRealTimers();

    mount();
    startUnmeasuredRest(Date.now() + 25);

    await waitFor(() => expect(screen.getByRole('complementary')).toHaveClass('is-compact'));
    expect(screen.getByRole('status')).toHaveTextContent('Отдых завершён');
  });

  it('extends the existing scoped deadline with native clicks and preserves field focus', () => {
    mount();
    startUnmeasuredRest();
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

  it('shows a skipped-rest notice immediately and removes it on the first hide', () => {
    mount();
    startUnmeasuredRest();
    fireEvent.click(screen.getByRole('button', { name: 'Пропустить' }));

    expect(localStorage.getItem(key)).toBeNull();
    const panel = screen.getByRole('complementary');
    expect(panel).toHaveClass('is-compact');
    expect(panel).toHaveTextContent('Отдых пропущен · Подход 2 из 3');
    expect(screen.getByRole('button', { name: 'Скрыть' })).toBeVisible();

    const hide = screen.getByRole('button', { name: 'Скрыть' });
    fireEvent.click(hide);
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
  });

  it('retains the pressed control when the deadline expires and ignores its late click', () => {
    mount();
    startUnmeasuredRest(initialTime + 1_000);
    const add30 = screen.getByRole('button', { name: '+30 сек' });
    pointer(add30, 'pointerdown');
    act(() => vi.advanceTimersByTime(1_000));
    expect(add30).toBeVisible();
    pointer(add30, 'pointercancel');
    expect(screen.getByRole('complementary')).toHaveClass('is-compact');
    fireEvent.click(add30);
    expect(localStorage.getItem(key)).toBeNull();
    expect(screen.getByRole('status')).toHaveTextContent('Отдых завершён');
  });

  it('reconciles the stored deadline on resume and starts a new rest after skip', () => {
    mount();
    startUnmeasuredRest();
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

  it('keeps one deadline timer across resume events and clears it on unmount', () => {
    const view = mount();
    startUnmeasuredRest();
    const timersWithRest = vi.getTimerCount();

    expect(timersWithRest).toBeGreaterThan(0);
    fireEvent(window, new Event('pageshow'));
    fireEvent(document, new Event('visibilitychange'));
    expect(vi.getTimerCount()).toBe(timersWithRest);

    view.unmount();
    expect(vi.getTimerCount()).toBe(timersWithRest - 1);
  });

  it('releases interrupted pointers on pagehide before compacting an expired rest', () => {
    mount();
    startUnmeasuredRest(initialTime + 1_000);
    pointer(screen.getByRole('button', { name: '+30 сек' }), 'pointerdown', 8);
    act(() => vi.advanceTimersByTime(1_000));
    fireEvent(window, new Event('pagehide'));
    fireEvent(window, new Event('pageshow'));

    expect(screen.getByRole('complementary')).toHaveClass('is-compact');
    fireEvent.click(screen.getByRole('button', { name: 'Скрыть' }));
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
    expect(localStorage.getItem(key)).toBeNull();
  });
  it('hides and reopens an active rest without resetting its measured interval', () => {
    mount();
    act(() => {
      window.dispatchEvent(new CustomEvent('fit:rest', {
        detail: { workoutId: 42, setId: 201, seconds: 90 },
      }));
    });
    const originalId = loadRestJournal(7, 42)[0]?.start_mutation_id;
    act(() => vi.advanceTimersByTime(12_000));
    fireEvent.click(screen.getByRole('button', { name: 'Свернуть таймер' }));

    expect(screen.getByRole('complementary')).toHaveClass('is-compact');
    expect(screen.getByText('Отдых идёт')).toBeVisible();
    expect(screen.getByText('ФАКТ 0:12')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Показать таймер' }));

    expect(screen.getByRole('timer', { name: 'Отдых' })).toHaveTextContent('1:18');
    expect(screen.getByText('ФАКТ')).toBeVisible();
    expect(loadRestJournal(7, 42)).toHaveLength(1);
    expect(loadRestJournal(7, 42)[0]?.start_mutation_id).toBe(originalId);
  });

  it('starts another interval only after stopping the previous one, without completing a set', () => {
    mount();
    act(() => {
      window.dispatchEvent(new CustomEvent('fit:rest', {
        detail: { workoutId: 42, setId: 201, seconds: 90 },
      }));
    });
    act(() => vi.advanceTimersByTime(20_000));
    fireEvent.click(screen.getByRole('button', { name: 'Завершить отдых' }));
    const original = loadRestJournal(7, 42)[0]!;
    expect(original.status).toBe('completed');

    fireEvent.click(screen.getByRole('button', { name: 'Начать отдых' }));

    const sessions = loadRestJournal(7, 42);
    expect(sessions).toHaveLength(2);
    expect(sessions[0]).toMatchObject({ status: 'completed', start_mutation_id: original.start_mutation_id });
    expect(sessions[1]).toMatchObject({
      source_set_id: 201,
      status: 'running',
      restart_of_start_mutation_id: original.start_mutation_id,
    });
    expect(screen.getByRole('timer', { name: 'Отдых' })).toHaveTextContent('1:30');
    expect(screen.getByText('ФАКТ')).toBeVisible();
    expect(screen.getByRole('textbox', { name: 'Вес' })).toHaveValue('42.5');
  });

  it('retains a skipped interval when the user explicitly starts a new one', () => {
    mount();
    act(() => {
      window.dispatchEvent(new CustomEvent('fit:rest', {
        detail: { workoutId: 42, setId: 201, seconds: 90 },
      }));
    });
    fireEvent.click(screen.getByRole('button', { name: 'Пропустить' }));
    expect(loadRestJournal(7, 42)[0]?.status).toBe('skipped');
    fireEvent.click(screen.getByRole('button', { name: 'Начать отдых' }));
    expect(loadRestJournal(7, 42)).toHaveLength(2);
    expect(loadRestJournal(7, 42)[0]?.status).toBe('skipped');
    expect(loadRestJournal(7, 42)[1]?.status).toBe('running');
  });

});
