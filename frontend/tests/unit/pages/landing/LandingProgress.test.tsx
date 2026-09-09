import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LandingProgress } from '../../../../src/pages/landing/LandingProgress';
import { loadDemoSession } from '../../../../src/features/demo/demoApi';
import { demoFixture } from '../../../e2e/fixtures/demo-session';
vi.mock('../../../../src/features/demo/demoApi', () => ({ loadDemoSession: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
function mount() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <LandingProgress href="/demo?section=progress" />
    </QueryClientProvider>,
  );
}
describe('landing progress from prepared session', () => {
  it('renders server aggregates and identifies the two-point index honestly', async () => {
    vi.mocked(loadDemoSession).mockResolvedValue(demoFixture('self_training'));
    mount();
    expect(await screen.findByText('6 220', { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/Показаны две сводные точки/)).toBeInTheDocument();
    expect(screen.getByRole('table')).toHaveTextContent('104,2');
    expect(screen.getByRole('link', { name: 'Открыть прогресс' })).toHaveAttribute(
      'href',
      '/demo?section=progress',
    );
  });
  it('offers retry after failure without inventing data', async () => {
    vi.mocked(loadDemoSession)
      .mockRejectedValueOnce(new Error('private'))
      .mockResolvedValueOnce(demoFixture('self_training'));
    mount();
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось загрузить');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Повторить/ }));
    expect(await screen.findByRole('table')).toHaveTextContent('104,2');
  });
});
