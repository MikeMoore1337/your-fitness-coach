import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LandingPractice } from '../../../../src/pages/landing/LandingPractice';
import { loadDemoSession } from '../../../../src/features/demo/demoApi';

vi.mock('../../../../src/features/demo/demoApi', () => ({
  loadDemoSession: vi.fn(),
  applyDemoAction: vi.fn(),
}));

describe('landing practice session boundary', () => {
  afterEach(cleanup);
  beforeEach(() => vi.clearAllMocks());

  it('starts no session before the visitor acts and prevents concurrent starts', async () => {
    let rejectRequest: (error: Error) => void = () => {
      throw new Error('Request not started');
    };
    vi.mocked(loadDemoSession).mockImplementation(
      () =>
        new Promise((_, reject) => {
          rejectRequest = reject;
        }),
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <LandingPractice />
      </QueryClientProvider>,
    );
    expect(loadDemoSession).not.toHaveBeenCalled();
    const start = screen.getByRole('button', { name: 'Попробовать тренировку' });
    fireEvent.click(start);
    fireEvent.click(start);
    expect(loadDemoSession).toHaveBeenCalledTimes(1);
    expect(start).toBeDisabled();
    await act(async () => rejectRequest(new Error('Network unavailable')));
    expect(start).toBeEnabled();
    expect(screen.getByRole('alert')).toHaveTextContent('Демо сейчас недоступно');
  });

  it('offers an explicit reload after failure without exposing backend details', async () => {
    vi.mocked(loadDemoSession).mockRejectedValue(new Error('private backend exception'));
    render(
      <QueryClientProvider client={new QueryClient()}>
        <LandingPractice />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Попробовать тренировку' }));
    await screen.findByRole('alert');
    expect(screen.queryByText('private backend exception')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Повторить/ }));
    await waitFor(() => expect(loadDemoSession).toHaveBeenCalledTimes(2));
    expect(loadDemoSession).toHaveBeenLastCalledWith('self_training');
  });
});
