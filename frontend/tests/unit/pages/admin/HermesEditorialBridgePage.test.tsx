import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import HermesEditorialBridgePage from '../../../../src/pages/admin/HermesEditorialBridgePage';

const { apiMock, authState } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authState: { user: { id: 1, is_root: true } },
}));

vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/app/AuthProvider', () => ({
  useAuth: () => authState,
}));

const PROTOCOL = 'yfc-owner-editorial-bridge-v1';
const ORIGIN = 'https://hermes.mikemoore.top';
const NONCE = 'a'.repeat(64);
const ARTICLE = 'b'.repeat(32);
const HASH = 'c'.repeat(64);

function deliver(
  kind: string,
  overrides: Record<string, unknown> = {},
  origin = ORIGIN,
): void {
  act(() => {
    window.dispatchEvent(
      new MessageEvent('message', {
        origin,
        source: window,
        data: { protocol: PROTOCOL, kind, nonce: NONCE, ...overrides },
      }),
    );
  });
}

function handshake(): void {
  deliver('hello');
  fireEvent.click(screen.getByRole('button', { name: 'Разрешить просмотр черновиков' }));
}

describe('YFC Root editorial browser boundary', () => {
  beforeEach(() => {
    authState.user.is_root = true;
    apiMock.mockReset();
    Object.defineProperty(window, 'opener', { configurable: true, value: window });
    vi.spyOn(window, 'postMessage').mockImplementation(() => undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    Object.defineProperty(window, 'opener', { configurable: true, value: null });
  });

  it('rejects non-Root users independently of the Hermes window', () => {
    authState.user.is_root = false;
    render(<HermesEditorialBridgePage />);

    expect(screen.getByText('Доступ запрещён')).toBeInTheDocument();
    deliver('hello');
    deliver('request', { request_id: 'd'.repeat(32), action: 'list', payload: {} });
    expect(apiMock).not.toHaveBeenCalled();
  });

  it('requires the pinned opener, nonce and explicit consent before reading', async () => {
    apiMock.mockResolvedValue([]);
    render(<HermesEditorialBridgePage />);
    deliver('hello', {}, 'https://evil.example');
    expect(screen.queryByRole('button', { name: 'Разрешить просмотр черновиков' })).toBeNull();
    deliver('hello');

    deliver('request', { request_id: 'd'.repeat(32), action: 'list', payload: {} });
    expect(apiMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Разрешить просмотр черновиков' }));

    deliver(
      'request',
      { request_id: 'e'.repeat(32), action: 'list', payload: {} },
      'https://evil.example',
    );
    deliver('request', {
      request_id: 'f'.repeat(32),
      nonce: '0'.repeat(64),
      action: 'list',
      payload: {},
    });
    expect(apiMock).not.toHaveBeenCalled();
    deliver('request', { request_id: '1'.repeat(32), action: 'list', payload: {} });
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith('/api/v1/admin/articles/drafts?limit=25&offset=0', {
        timeoutMs: 10000,
        retryAuth: false,
      }),
    );
    expect(apiMock).toHaveBeenCalledTimes(1);
  });

  it('never publishes from a message alone and rejects replay of the publish request', async () => {
    apiMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/drafts/' + ARTICLE)) {
        return {
          article_id: ARTICLE,
          content_hash: HASH,
          content_version: 2,
          title: 'Проверяемая научная статья',
          review_blockers: [],
          claim_source_matrix: [{ review_status: 'pending', support_level: 'unclear' }],
        };
      }
      if (path.endsWith('/drafts/publish')) {
        return { article_id: ARTICLE, article_status: 'published', content_version: 2 };
      }
      throw Error('Unexpected request');
    });

    render(<HermesEditorialBridgePage />);
    handshake();
    const request = {
      request_id: '2'.repeat(32),
      action: 'publish',
      payload: {
        article_id: ARTICLE,
        content_hash: HASH,
        content_version: 2,
      },
    };
    deliver('request', request);
    await screen.findByRole('button', { name: 'Подтверждаю публикацию в YFC' });
    expect(apiMock).toHaveBeenCalledTimes(1);

    deliver('request', request);
    expect(apiMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Подтверждаю публикацию в YFC' }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    expect(apiMock).toHaveBeenLastCalledWith('/api/v1/admin/articles/drafts/publish', {
      method: 'POST',
      retryAuth: false,
      timeoutMs: 15000,
      body: {
        article_id: ARTICLE,
        expected_content_hash: HASH,
        expected_content_version: 2,
        acknowledge_unverified_evidence: true,
        confirm_exact_revision: true,
      },
    });
  });
});
