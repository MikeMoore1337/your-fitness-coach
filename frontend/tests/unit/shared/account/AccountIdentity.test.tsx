import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AccountAvatar } from '../../../../src/shared/account/AccountIdentity';

const { apiFile } = vi.hoisted(() => ({ apiFile: vi.fn() }));

vi.mock('../../../../src/shared/api/client', () => ({ apiFile }));

describe('AccountAvatar', () => {
  beforeEach(() => {
    apiFile.mockReset();
    vi.stubGlobal(
      'URL',
      class extends URL {
        static createObjectURL = vi.fn(() => `blob:${window.location.origin}/private-avatar`);
        static revokeObjectURL = vi.fn();
      },
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('uses deterministic emoji when no image source exists', () => {
    const view = render(<AccountAvatar name="Анна Петрова" />);
    const first = view.container.textContent;
    view.rerender(<AccountAvatar name="Анна Петрова" />);
    expect(view.container.textContent).toBe(first);
    expect(first).toMatch(/🏋️|💪|🏃|🚴|🥗|⚡|🎯|🔥/);
  });

  it('prefers private bytes and falls back through provider photo to emoji', async () => {
    apiFile.mockResolvedValue({
      blob: new Blob(['private'], { type: 'image/webp' }),
      filename: null,
    });
    const view = render(
      <AccountAvatar
        customAvatarVersion="2030-01-02T12:00:00"
        name="Анна Петрова"
        photoUrl="https://provider.example.test/avatar.jpg"
      />,
    );

    await waitFor(() =>
      expect(view.container.querySelector('img')).toHaveAttribute(
        'src',
        `blob:${window.location.origin}/private-avatar`,
      ),
    );
    fireEvent.error(view.container.querySelector('img')!);
    expect(view.container.querySelector('img')).toHaveAttribute(
      'src',
      'https://provider.example.test/avatar.jpg',
    );
    fireEvent.error(view.container.querySelector('img')!);
    expect(view.container.querySelector('img')).not.toBeInTheDocument();
    expect(view.container).toHaveTextContent(/🏋️|💪|🏃|🚴|🥗|⚡|🎯|🔥/);
  });

  it.each([
    'javascript:alert(1)',
    'JaVaScRiPt:alert(1)',
    'data:image/svg+xml,<svg onload="alert(1)"/>',
    'file:///private/avatar.png',
    'https://',
    `blob:${window.location.origin}/provider-avatar`,
  ])('does not use an unsafe provider source: %s', (photoUrl) => {
    const view = render(<AccountAvatar name="Анна Петрова" photoUrl={photoUrl} />);
    expect(view.container.querySelector('img')).not.toBeInTheDocument();
    expect(view.container.textContent).not.toBe('');
  });

  it.each(['https://provider.example.test/avatar.jpg', 'HTTPS://provider.example.test/avatar.jpg'])(
    'keeps valid provider photos after URL normalization: %s',
    (photoUrl) => {
      const view = render(<AccountAvatar name="Анна Петрова" photoUrl={photoUrl} />);
      expect(view.container.querySelector('img')).toHaveAttribute(
        'src',
        'https://provider.example.test/avatar.jpg',
      );
    },
  );

  it.each(['javascript:alert(1)', 'blob:https://other.example.test/preview'])(
    'falls back from an unsafe preview to the provider: %s',
    (previewUrl) => {
      const view = render(
        <AccountAvatar
          name="Анна Петрова"
          previewUrl={previewUrl}
          photoUrl="https://provider.example.test/avatar.jpg"
        />,
      );
      expect(view.container.querySelector('img')).toHaveAttribute(
        'src',
        'https://provider.example.test/avatar.jpg',
      );
    },
  );

  it('keeps a same-origin upload preview ahead of the provider and revokes private bytes', async () => {
    apiFile.mockResolvedValue({ blob: new Blob(['private'], { type: 'image/webp' }) });
    const previewUrl = `blob:${window.location.origin}/selected-avatar`;
    const view = render(
      <AccountAvatar
        customAvatarVersion="2030-01-02T12:00:00"
        name="Анна Петрова"
        photoUrl="https://provider.example.test/avatar.jpg"
        previewUrl={previewUrl}
      />,
    );
    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalledOnce());
    expect(view.container.querySelector('img')).toHaveAttribute('src', previewUrl);
    view.unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith(
      `blob:${window.location.origin}/private-avatar`,
    );
  });
});
