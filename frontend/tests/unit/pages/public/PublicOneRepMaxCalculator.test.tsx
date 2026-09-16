import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import PublicOneRepMaxCalculator from '../../../../src/pages/public/PublicOneRepMaxCalculator';
import {
  PRODUCT_EVENT_NAME,
  type ProductEventEnvelope,
} from '../../../../src/shared/analytics/productEvents';

describe('PublicOneRepMaxCalculator', () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
    window.history.replaceState({}, '', '/');
  });

  it('shows field-level validation and does not render a stale result', () => {
    render(<PublicOneRepMaxCalculator />);

    const form = screen.getByRole('form', { name: 'Рассчитать 1ПМ онлайн' });
    fireEvent.click(within(form).getByRole('button', { name: 'Рассчитать 1ПМ' }));

    expect(screen.getByRole('alert')).toHaveTextContent(/проверьте выделенные поля/i);
    expect(screen.getByLabelText('Вес в подходе, кг')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Повторения в подходе')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText(/вес от 0,5 до 500 кг/i)).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('calculates the estimate and emits only the existing privacy-safe growth events', async () => {
    const events: ProductEventEnvelope[] = [];
    const listener = (event: Event) =>
      events.push((event as CustomEvent<ProductEventEnvelope>).detail);
    window.addEventListener(PRODUCT_EVENT_NAME, listener);

    try {
      render(<PublicOneRepMaxCalculator />);
      const calculator = screen.getByRole('region', { name: 'Рассчитать 1ПМ онлайн' });
      const form = within(calculator).getByRole('form', { name: 'Рассчитать 1ПМ онлайн' });

      fireEvent.change(screen.getByLabelText('Вес в подходе, кг'), {
        target: { value: '100' },
      });
      fireEvent.change(screen.getByLabelText('Повторения в подходе'), {
        target: { value: '5' },
      });
      fireEvent.click(within(form).getByRole('button', { name: 'Рассчитать 1ПМ' }));

      await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('112,5 кг'));
      const result = screen.getByRole('status');
      expect(result).toHaveTextContent('Расчётный 1ПМ — ориентир, а не измеренный максимум.');
      expect(within(result).getByRole('table')).toBeInTheDocument();
      expect(within(result).getByRole('row', { name: '95% 107 кг' })).toBeInTheDocument();
      expect(within(result).getByRole('row', { name: '70% 79 кг' })).toBeInTheDocument();
      expect(window.location.search).toBe('');
      expect(localStorage.length).toBe(0);
      expect(events.map((event) => event.name)).toEqual([
        'calculator_started',
        'calculator_result',
      ]);
      expect(events.every((event) => Object.keys(event).length === 5)).toBe(true);
      expect(JSON.stringify(events)).not.toContain('100');
      expect(JSON.stringify(events)).not.toContain('112');

      fireEvent.click(within(form).getByRole('button', { name: 'Рассчитать 1ПМ' }));
      expect(events.map((event) => event.name)).toEqual([
        'calculator_started',
        'calculator_result',
      ]);
    } finally {
      window.removeEventListener(PRODUCT_EVENT_NAME, listener);
    }
  });

  it('accepts a decimal comma for weight and rejects high repetition counts', () => {
    render(<PublicOneRepMaxCalculator />);
    const form = screen.getByRole('form', { name: 'Рассчитать 1ПМ онлайн' });

    fireEvent.change(screen.getByLabelText('Вес в подходе, кг'), {
      target: { value: '80,5' },
    });
    fireEvent.change(screen.getByLabelText('Повторения в подходе'), {
      target: { value: '11' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'Рассчитать 1ПМ' }));

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByLabelText('Повторения в подходе')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText(/повторений от 1 до 10/i)).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
