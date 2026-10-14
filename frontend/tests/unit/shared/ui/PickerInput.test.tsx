import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DateInput, TimeInput } from '../../../../src/shared/ui/PickerInput';

describe('DateInput', () => {
  it('одинаково оформляет поле даты и передаёт атрибуты нативному input', () => {
    render(
      <DateInput
        aria-label="Дата проверки"
        controlClassName="custom-date-control"
        min="2026-01-01"
        value="2026-08-11"
        readOnly
      />,
    );

    const input = screen.getByLabelText('Дата проверки');
    expect(input).toHaveAttribute('type', 'date');
    expect(input).toHaveAttribute('min', '2026-01-01');
    expect(input).toHaveValue('2026-08-11');
    expect(input.parentElement).toHaveClass('date-control', 'custom-date-control');
    expect(input.parentElement?.querySelector('svg')).toHaveAttribute('data-icon', 'calendar');
    expect(input.parentElement?.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('TimeInput', () => {
  it('одинаково оформляет поле времени и передаёт атрибуты нативному input', () => {
    render(
      <TimeInput
        aria-label="Время проверки"
        controlClassName="custom-time-control"
        step="3600"
        value="09:00"
        readOnly
      />,
    );

    const input = screen.getByLabelText('Время проверки');
    expect(input).toHaveAttribute('type', 'time');
    expect(input).toHaveAttribute('step', '3600');
    expect(input).toHaveValue('09:00');
    expect(input.parentElement).toHaveClass('time-control', 'custom-time-control');
    expect(input.parentElement?.querySelector('svg')).toHaveAttribute('data-icon', 'clock');
    expect(input.parentElement?.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });
});
