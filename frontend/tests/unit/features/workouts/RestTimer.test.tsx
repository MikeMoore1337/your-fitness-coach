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
  it('preserves the warning when a backwards clock prevents a valid measurement', () => {
    beginMeasuredRest(7, 42, 201, 90, initialTime);
    mount();
    vi.setSystemTime(initialTime - 1000);
    fireEvent.click(screen.getByRole('button', { name: 'Стоп: завершить отдых' }));
    expect(
      screen.getByRole('complementary').querySelector('.active-workout-rest__complete-copy'),
    ).toHaveTextContent('Нет достоверного замера отдыха');
    expect(
      screen
        .getByRole('complementary')
        .querySelector('.active-workout-rest__complete-mark [data-icon="warning"]'),
    ).toBeInTheDocument();
    expect(loadRestJournal(7, 42)[0]).toMatchObject({ status: 'running' });
  });

  it('closes recovery when another context has already resolved the interval', () => {
    beginMeasuredRest(7, 42, 201, 90, initialTime);
    mount();
    fireEvent(window, new Event('pagehide'));
    vi.setSystemTime(initialTime + 17 * 60_000);
    fireEvent(window, new Event('pageshow'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(
      'Уточните длительность отдыха или не учитывайте замер',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Уточнить' }));
    expect(screen.getByRole('dialog', { name: 'Сколько отдыхали?' })).toBeVisible();
    act(() => {
      updateMeasuredRest(7, 42, 201, 'skip');
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(loadRestJournal(7, 42)[0]).toMatchObject({ status: 'skipped', measured_seconds: null });
    fireEvent.click(screen.getByRole('button', { name: 'Новый отдых' }));
    fireEvent(window, new Event('pagehide'));
    vi.setSystemTime(initialTime + 34 * 60_000);
    fireEvent(window, new Event('pageshow'));
    expect(screen.getByRole('button', { name: 'Уточнить' })).toBeVisible();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps four direct actions in the compact row without repeating the exercise', () => {
    beginMeasuredRest(7, 42, 201, 90, initialTime);
    mount();
    const panel = screen.getByRole('complementary');
    const actions = panel.querySelector('.active-workout-rest__actions')!;
    expect(
      Array.from(actions.querySelectorAll('button')).map(
        (button) => button.getAttribute('aria-label') ?? button.textContent?.trim(),
      ),
    ).toEqual(['+30 сек', '+60 сек', 'Стоп: завершить отдых', 'Пропустить']);
    expect(panel.querySelector('.active-workout-rest__stop')).toHaveClass('ui-button--primary');
    expect(panel).not.toHaveTextContent('Жим штанги лёжа');
    expect(screen.getByRole('timer', { name: 'Отдых' })).toHaveTextContent('1:30');
  });

  it('opens sync details outside the panel and restores focus without changing the interval', () => {
    beginMeasuredRest(7, 42, 201, 90, initialTime);
    mount();
    const previous = loadRestJournal(7, 42);
    const status = screen.getByRole('button', { name: /Состояние отдыха:/ });
    fireEvent.click(status, { detail: 2 });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(status, { detail: 1 });
    act(() => vi.advanceTimersToNextFrame());
    const dialog = screen.getByRole('dialog', { name: 'Сохранение отдыха' });
    expect(screen.getByRole('complementary')).not.toContainElement(dialog);
    expect(dialog).toHaveTextContent('Данные сохранены на устройстве');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(status).toHaveFocus();
    expect(loadRestJournal(7, 42)).toEqual(previous);
  });

  it('closes and reopens recovery without recording a guess and keeps validation in the dialog', () => {
    beginMeasuredRest(7, 42, 201, 90, initialTime);
    mount();
    screen.getByRole('textbox', { name: 'Вес' }).focus();
    fireEvent(window, new Event('pagehide'));
    vi.setSystemTime(initialTime + 17 * 60_000);
    fireEvent(window, new Event('pageshow'));
    fireEvent.click(screen.getByRole('button', { name: 'Уточнить' }));
    act(() => vi.advanceTimersToNextFrame());
    const previous = loadRestJournal(7, 42);
    expect(screen.getByRole('dialog', { name: 'Сколько отдыхали?' })).toBeVisible();
    expect(screen.getByRole('textbox', { name: 'Фактическое время, минуты' })).toHaveFocus();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.getByRole('button', { name: 'Уточнить' })).toHaveFocus();
    expect(loadRestJournal(7, 42)).toEqual(previous);
    const reopen = screen.getByRole('button', { name: 'Уточнить' });
    fireEvent.click(reopen);
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить время' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Введите время от 0 до 1440 минут');
    expect(loadRestJournal(7, 42)).toEqual(previous);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(reopen).toHaveFocus();
  });

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
    expect(screen.getByRole('button', { name: 'Стоп: завершить отдых' })).toBeVisible();
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

    expect(screen.getByRole('button', { name: 'Новый отдых' })).toBeVisible();
    expect(screen.queryByRole('timer')).not.toBeInTheDocument();
    expect(loadRestJournal(7, 42)).toHaveLength(1);
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
    expect(screen.getByRole('button', { name: 'Стоп: завершить отдых' })).toBeVisible();
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
      window.dispatchEvent(
        new CustomEvent('fit:rest', {
          detail: { workoutId: 42, setId: 201, seconds: 90 },
        }),
      );
    });
    const originalId = loadRestJournal(7, 42)[0]?.start_mutation_id;
    act(() => vi.advanceTimersByTime(12_000));
    fireEvent.click(screen.getByRole('button', { name: 'Свернуть таймер' }));

    expect(screen.getByRole('complementary')).toHaveClass('is-compact');
    expect(screen.getByText('Сохраняется…')).toBeVisible();
    expect(screen.getByText('ФАКТ 0:12')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Развернуть таймер' }));

    expect(screen.getByRole('timer', { name: 'Отдых' })).toHaveTextContent('1:18');
    expect(screen.getByText('ФАКТ')).toBeVisible();
    expect(loadRestJournal(7, 42)).toHaveLength(1);
    expect(loadRestJournal(7, 42)[0]?.start_mutation_id).toBe(originalId);
  });

  it('hides the terminal notice without removing the manual restart action', () => {
    mount();
    act(() => {
      window.dispatchEvent(
        new CustomEvent('fit:rest', {
          detail: { workoutId: 42, setId: 201, seconds: 90 },
        }),
      );
    });
    act(() => vi.advanceTimersByTime(12_000));
    fireEvent.click(screen.getByRole('button', { name: 'Стоп: завершить отдых' }));
    const previous = loadRestJournal(7, 42)[0]!;
    expect(
      screen.getByRole('complementary').querySelector('.active-workout-rest__complete-copy'),
    ).toHaveTextContent('Отдых завершён');
    expect(
      screen
        .getByRole('complementary')
        .querySelector('.active-workout-rest__complete-mark [data-icon="sync"]'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Скрыть' }));
    expect(
      screen.getByRole('complementary').querySelector('.active-workout-rest__complete-copy'),
    ).toBeNull();
    expect(screen.queryByRole('button', { name: 'Скрыть' })).not.toBeInTheDocument();
    expect(screen.queryByRole('timer')).not.toBeInTheDocument();
    expect(loadRestJournal(7, 42)).toEqual([previous]);

    const restart = screen.getByRole('button', { name: 'Новый отдых' });
    expect(restart).toBeVisible();
    act(() => {
      fireEvent.click(restart);
      fireEvent.click(restart);
    });
    expect(screen.getByRole('button', { name: 'Стоп: завершить отдых' })).toBeVisible();
    const records = loadRestJournal(7, 42);
    expect(records).toHaveLength(2);
    expect(records[0]).toEqual(previous);
    expect(records[1]).toMatchObject({
      status: 'running',
      restart_of_start_mutation_id: previous.start_mutation_id,
    });
  });

  it('dismisses an omitted rest without starting or changing it, then starts only one new interval', () => {
    mount();
    act(() => {
      window.dispatchEvent(
        new CustomEvent('fit:rest', {
          detail: { workoutId: 42, setId: 201, seconds: 90 },
        }),
      );
    });
    fireEvent(window, new Event('pagehide'));
    vi.setSystemTime(initialTime + 17 * 60_000);
    fireEvent(window, new Event('pageshow'));
    fireEvent.click(screen.getByRole('button', { name: 'Уточнить' }));
    fireEvent.click(screen.getByRole('button', { name: 'Не учитывать' }));
    const panel = screen.getByRole('complementary');
    expect(panel.querySelector('.active-workout-rest__complete-copy')).toHaveTextContent(
      'Отдых не учитывается',
    );
    const previous = loadRestJournal(7, 42)[0]!;
    expect(previous.status).toBe('skipped');
    expect(previous.measured_seconds).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Скрыть' }));
    expect(panel.querySelector('.active-workout-rest__complete-copy')).toBeNull();
    expect(screen.queryByRole('timer')).not.toBeInTheDocument();
    expect(loadRestJournal(7, 42)).toEqual([previous]);

    const restart = screen.getByRole('button', { name: 'Новый отдых' });
    act(() => {
      fireEvent.click(restart);
      fireEvent.click(restart);
    });
    const records = loadRestJournal(7, 42);
    expect(records).toHaveLength(2);
    expect(records[0]).toEqual(previous);
    expect(records[1]).toMatchObject({
      status: 'running',
      started_at: new Date(initialTime + 17 * 60_000).toISOString(),
      restart_of_start_mutation_id: previous.start_mutation_id,
    });
  });

  it('keeps the corrected fact when the user starts another interval', () => {
    mount();
    act(() => {
      window.dispatchEvent(
        new CustomEvent('fit:rest', {
          detail: { workoutId: 42, setId: 201, seconds: 90 },
        }),
      );
    });
    fireEvent(window, new Event('pagehide'));
    vi.setSystemTime(initialTime + 17 * 60_000);
    fireEvent(window, new Event('pageshow'));
    fireEvent.click(screen.getByRole('button', { name: 'Уточнить' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Фактическое время, минуты' }), {
      target: { value: '2,5' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить время' }));
    const previous = loadRestJournal(7, 42)[0]!;
    expect(previous).toMatchObject({
      status: 'completed',
      measured_seconds: 150,
      source: 'USER_CORRECTED',
    });
    expect(screen.getByRole('complementary')).toHaveTextContent('ФАКТ 2:30');
    fireEvent.click(screen.getByRole('button', { name: 'Новый отдых' }));
    expect(loadRestJournal(7, 42)[0]).toEqual(previous);
    expect(loadRestJournal(7, 42)).toHaveLength(2);
  });

  it('starts another interval only after stopping the previous one, without completing a set', () => {
    mount();
    act(() => {
      window.dispatchEvent(
        new CustomEvent('fit:rest', {
          detail: { workoutId: 42, setId: 201, seconds: 90 },
        }),
      );
    });
    act(() => vi.advanceTimersByTime(20_000));
    fireEvent.click(screen.getByRole('button', { name: 'Стоп: завершить отдых' }));
    const original = loadRestJournal(7, 42)[0]!;
    expect(original.status).toBe('completed');

    fireEvent.click(screen.getByRole('button', { name: 'Новый отдых' }));

    const sessions = loadRestJournal(7, 42);
    expect(sessions).toHaveLength(2);
    expect(sessions[0]).toMatchObject({
      status: 'completed',
      start_mutation_id: original.start_mutation_id,
    });
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
      window.dispatchEvent(
        new CustomEvent('fit:rest', {
          detail: { workoutId: 42, setId: 201, seconds: 90 },
        }),
      );
    });
    fireEvent.click(screen.getByRole('button', { name: 'Пропустить' }));
    expect(loadRestJournal(7, 42)[0]?.status).toBe('skipped');
    fireEvent.click(screen.getByRole('button', { name: 'Новый отдых' }));
    expect(loadRestJournal(7, 42)).toHaveLength(2);
    expect(loadRestJournal(7, 42)[0]?.status).toBe('skipped');
    expect(loadRestJournal(7, 42)[1]?.status).toBe('running');
  });

  it('restores the manual rest action rather than a phantom running timer after reload', () => {
    const first = beginMeasuredRest(7, 42, 201, 90, initialTime)!;
    updateMeasuredRest(7, 42, 201, 'complete', initialTime + 42_000);
    mount();
    expect(screen.queryByRole('timer', { name: 'Отдых' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Новый отдых' })).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'Новый отдых' }));
    expect(loadRestJournal(7, 42)[1]?.restart_of_start_mutation_id).toBe(first.start_mutation_id);
    expect(screen.getByRole('timer')).toHaveTextContent('1:30');
  });
});
