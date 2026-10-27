import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, expect, it } from 'vitest';
import { SegmentedControl } from '../../../../src/shared/ui/common';

afterEach(cleanup);

function TabsHarness() {
  const [value, setValue] = useState('a');
  return (
    <SegmentedControl
      ariaLabel="Проверка вкладок"
      onChange={setValue}
      options={[
        { label: 'Первый', value: 'a' },
        { label: 'Недоступен', value: 'b', disabled: true },
        { label: 'Третий', value: 'c' },
      ]}
      value={value}
    />
  );
}

it('preserves existing shadcn-style accessible tabs without adding a new dependency', () => {
  render(<TabsHarness />);
  const first = screen.getByRole('tab', { name: 'Первый' });
  const disabled = screen.getByRole('tab', { name: 'Недоступен' });
  const last = screen.getByRole('tab', { name: 'Третий' });

  expect(first).toHaveAttribute('aria-selected', 'true');
  expect(disabled).toBeDisabled();
  first.focus();
  fireEvent.keyDown(first, { key: 'ArrowRight' });
  expect(last).toHaveFocus();
  expect(last).toHaveAttribute('aria-selected', 'true');
  expect(disabled).toHaveAttribute('aria-selected', 'false');

  fireEvent.keyDown(last, { key: 'Home' });
  expect(first).toHaveFocus();
  expect(first).toHaveAttribute('aria-selected', 'true');

  fireEvent.keyDown(first, { key: 'End' });
  expect(last).toHaveFocus();
  expect(last).toHaveAttribute('aria-selected', 'true');
});

it('does not activate a disabled tab via mouse or keyboard', () => {
  render(<TabsHarness />);
  const first = screen.getByRole('tab', { name: 'Первый' });
  const disabled = screen.getByRole('tab', { name: 'Недоступен' });
  fireEvent.click(disabled);
  expect(first).toHaveAttribute('aria-selected', 'true');
  fireEvent.keyDown(first, { key: 'ArrowLeft' });
  const last = screen.getByRole('tab', { name: 'Третий' });
  expect(last).toHaveAttribute('aria-selected', 'true');
  expect(disabled).toHaveAttribute('aria-selected', 'false');
});
