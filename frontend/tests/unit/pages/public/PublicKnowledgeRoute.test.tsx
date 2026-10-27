import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import PublicKnowledgeRoute from '../../../../src/pages/public/PublicKnowledgeRoute';

vi.mock('../../../../src/pages/public/KnowledgeHandoffPage', () => ({
  default: ({ articlePath }: { articlePath: string }) => (
    <div data-testid="knowledge-handoff">handoff:{articlePath}</div>
  ),
}));

vi.mock('../../../../src/pages/public/PublicContentPage', () => ({
  default: () => <div data-testid="public-content">public-content</div>,
}));

vi.mock('../../../../src/pages/NotFoundPage', () => ({
  default: () => <div data-testid="not-found">not-found</div>,
}));

describe('PublicKnowledgeRoute', () => {
  afterEach(() => {
    cleanup();
    delete window.Telegram;
    window.history.replaceState({}, '', '/');
  });

  it('hands a published knowledge path to the TMA handoff', () => {
    window.Telegram = { WebApp: { initData: 'signed' } };

    render(<PublicKnowledgeRoute articlePath="/knowledge/training/repetitions-in-reserve" />);

    expect(screen.getByTestId('knowledge-handoff')).toHaveTextContent(
      'handoff:/knowledge/training/repetitions-in-reserve',
    );
  });

  it('keeps published knowledge pages on the public web route outside TMA', () => {
    render(<PublicKnowledgeRoute articlePath="/knowledge" />);

    expect(screen.getByTestId('public-content')).toBeInTheDocument();
  });

  it('does not hand off an unknown legacy route', () => {
    render(<PublicKnowledgeRoute articlePath="/knowledge/unknown" legacyRoute />);

    expect(screen.getByTestId('not-found')).toBeInTheDocument();
  });

  it('hands a published legacy knowledge route to the web handoff outside TMA', () => {
    render(
      <PublicKnowledgeRoute articlePath="/knowledge/training/repetitions-in-reserve" legacyRoute />,
    );

    expect(screen.getByTestId('knowledge-handoff')).toHaveTextContent(
      'handoff:/knowledge/training/repetitions-in-reserve',
    );
  });
});
