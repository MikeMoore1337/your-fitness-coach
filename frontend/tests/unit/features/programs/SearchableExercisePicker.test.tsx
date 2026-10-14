import { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SearchableExercisePicker } from '../../../../src/features/programs/SearchableExercisePicker';

const exercises = [
  { id: 11, title: 'Присед со штангой', primary_muscle: 'Квадрицепс', equipment: 'Штанга' },
  { id: 12, title: 'Велотренажёр', primary_muscle: 'Кардио', equipment: 'Велотренажёр' },
];

describe('SearchableExercisePicker mobile focus and selection', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: query === '(max-width: 680px)',
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('clears only the query, keeps focus and returns focus after a new selection', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    function Picker() {
      const [value, setValue] = useState<number | ''>(11);
      return (
        <SearchableExercisePicker
          mobileSheet
          exercises={exercises}
          value={value}
          onChange={(id) => {
            onChange(id);
            setValue(id);
          }}
        />
      );
    }
    render(<Picker />);
    const trigger = screen.getByRole('button', { name: 'Поиск упражнения' });
    await user.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Выбор упражнения' });
    const search = within(dialog).getByRole('searchbox');
    await waitFor(() => expect(search).toHaveFocus());
    await user.click(within(dialog).getByRole('button', { name: 'Очистить поиск' }));
    expect(search).toHaveValue('');
    expect(search).toHaveFocus();
    expect(onChange).not.toHaveBeenCalled();
    await user.type(search, 'велотренажёр');
    await user.click(within(dialog).getByRole('button', { name: /Велотренажёр/ }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith(12);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveTextContent('Велотренажёр');
    expect(trigger).toHaveFocus();
  });

  it('discards an unfinished query on close and Escape without changing the selection', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <SearchableExercisePicker mobileSheet exercises={exercises} value={11} onChange={onChange} />,
    );
    const trigger = screen.getByRole('button', { name: 'Поиск упражнения' });
    for (const closeWithEscape of [false, true]) {
      await user.click(trigger);
      const dialog = screen.getByRole('dialog', { name: 'Выбор упражнения' });
      const search = within(dialog).getByRole('searchbox');
      await waitFor(() => expect(search).toHaveFocus());
      expect(search).toHaveValue(exercises[0]!.title);
      await user.clear(search);
      await user.type(search, 'несуществующее упражнение');
      expect(within(dialog).getByRole('status')).toHaveTextContent('Ничего не найдено');
      if (closeWithEscape) await user.keyboard('{Escape}');
      else
        await user.click(within(dialog).getByRole('button', { name: 'Закрыть выбор упражнения' }));
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(trigger).toHaveFocus();
    }
    expect(onChange).not.toHaveBeenCalled();
  });

  it('updates the query when an editor row receives another selected exercise', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { rerender } = render(
      <SearchableExercisePicker mobileSheet exercises={exercises} value={11} onChange={onChange} />,
    );
    rerender(
      <SearchableExercisePicker mobileSheet exercises={exercises} value={12} onChange={onChange} />,
    );
    await user.click(screen.getByRole('button', { name: 'Поиск упражнения' }));
    const search = screen.getByRole('searchbox');
    await waitFor(() => expect(search).toHaveFocus());
    expect(search).toHaveValue(exercises[1]!.title);
    expect(screen.getByRole('button', { name: /Велотренажёр/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(onChange).not.toHaveBeenCalled();
  });

  it('keeps the edited desktop query when manual mapping clears the previous selection', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    function Picker() {
      const [value, setValue] = useState<number | ''>(11);
      return (
        <SearchableExercisePicker
          exercises={exercises}
          value={value}
          onChange={(id) => {
            onChange(id);
            setValue(id);
          }}
        />
      );
    }
    render(<Picker />);
    const search = screen.getByRole('combobox', { name: 'Поиск упражнения' });
    await user.click(search);
    fireEvent.change(search, { target: { value: 'вело' } });
    expect(search).toHaveValue('вело');
    expect(onChange).toHaveBeenCalledExactlyOnceWith('');
    expect(screen.getAllByRole('option')).toHaveLength(1);
    await user.keyboard('{ArrowDown}{Enter}');
    expect(search).toHaveValue('Велотренажёр');
    expect(onChange).toHaveBeenLastCalledWith(12);
  });
});
