import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LandingProgress } from '../../../../src/pages/landing/LandingProgress';
import { loadDemoSession } from '../../../../src/features/demo/demoApi';
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
describe('landing progress prepared preview', () => {
  it('renders a static preview without starting a demo session', async () => {
    mount();
    expect(await screen.findByText('6 220', { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/Показаны две сводные точки/)).toBeInTheDocument();
    expect(screen.getByRole('table')).toHaveTextContent('104,2');
    expect(screen.getByRole('link', { name: 'Открыть прогресс' })).toHaveAttribute(
      'href',
      '/demo?section=progress',
    );
    expect(loadDemoSession).not.toHaveBeenCalled();
  });
});
