import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '../../../src/app/AppShell';

const logout = vi.fn();
function stubViewport(initialWidth: number, reducedMotion = false) {
  let width = initialWidth;
  Object.defineProperty(window, 'innerWidth', { configurable: true, get: () => width });
  vi.stubGlobal('matchMedia', (query: string) => ({
    get matches() {
      if (query === '(max-width: 899px)') return width < 900;
      if (query === '(prefers-reduced-motion: reduce)') return reducedMotion;
      return false;
    },
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  return (nextWidth: number) => {
    width = nextWidth;
    window.dispatchEvent(new Event('resize'));
  };
}

function finishAnimation(element: Element, animationName: string) {
  const event = new Event('animationend', { bubbles: true });
  Object.defineProperty(event, 'animationName', { value: animationName });
  fireEvent(element, event);
}
const { authState, avatarFile, navigation, pwa, user } = vi.hoisted(() => ({
  authState: { missing: false },
  avatarFile: vi.fn(),
  navigation: { path: '/coach', search: '' },
  pwa: {
    enabled: true,
    isStandalone: false,
    isIosInstallSurface: false,
    shouldShowInstallPrompt: false,
    installPromptAvailable: false,
    installPending: false,
    recordAppValue: vi.fn(),
    markInstallOptionShown: vi.fn(),
    install: vi.fn(async () => undefined),
    dismissInstall: vi.fn(),
    updateAvailable: false,
    updateBlockedByWorkout: false,
    applyUpdate: vi.fn(),
  },
  user: {
    id: 1,
    username: 'mikhail',
    first_name: 'Михаил',
    is_coach: true,
    is_root: false,
    photo_url: null as string | null,
    custom_avatar: null as null | {
      content_type: 'image/webp';
      byte_size: number;
      width: 512;
      height: 512;
      updated_at: string;
    },
  },
}));

vi.mock('../../../src/shared/api/client', () => ({ apiFile: avatarFile }));

vi.mock('../../../src/app/AuthProvider', () => ({
  useOptionalAuth: () => (authState.missing ? null : { user, logout }),
}));

vi.mock('../../../src/shared/pwa/PwaProvider', () => ({
  usePwa: () => pwa,
}));

vi.mock('../../../src/shared/navigation/router', () => ({
  useNavigation: () => navigation,
  AppLink: ({ to, className, children, ...props }: React.ComponentProps<'a'> & { to: string }) => (
    <a href={to} className={className} {...props}>
      {children}
    </a>
  ),
}));

describe('AppShell', () => {
  beforeEach(() => {
    cleanup();
    authState.missing = false;
    user.photo_url = null;
    user.custom_avatar = null;
    user.is_root = false;
    navigation.path = '/coach';
    navigation.search = '';
    logout.mockClear();
    avatarFile.mockReset();
    vi.unstubAllGlobals();
    stubViewport(1280);
    delete window.Telegram;
  });

  it('показывает основные направления и отделяет рабочее пространство тренера', () => {
    render(<AppShell>Содержимое</AppShell>);

    expect(screen.getByRole('navigation', { name: 'Основная навигация' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Сегодня' })).toHaveAttribute(
      'href',
      '/app?section=today',
    );
    expect(screen.getByRole('link', { name: 'План' })).toHaveAttribute(
      'href',
      '/app?section=programs',
    );
    expect(
      Array.from(document.querySelectorAll('.app-bottom-nav__primary > a')).map(
        (link) => link.textContent,
      ),
    ).toEqual(['Сегодня', 'План', 'Питание', 'Прогресс']);
    expect(screen.queryByRole('button', { name: 'Ещё' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Тренер' })).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByRole('link', { name: 'Админ-панель' })).not.toBeInTheDocument();
    expect(screen.getByText('Ресурсы')).toBeInTheDocument();
    expect(screen.getByText('Михаил')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Быстро добавить' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Выйти из аккаунта' }));
    expect(logout).toHaveBeenCalledOnce();
  });

  it('сохраняет active state для каждого прямого core route', () => {
    navigation.path = '/app';
    for (const [section, label] of [
      ['today', 'Сегодня'],
      ['programs', 'План'],
      ['nutrition', 'Питание'],
      ['progress', 'Прогресс'],
    ] as const) {
      const view = render(<AppShell section={section}>Содержимое</AppShell>);
      expect(screen.getByRole('link', { name: label })).toHaveAttribute('aria-current', 'page');
      view.unmount();
    }
  });

  it('открывает единую панель быстрых действий и закрывает её Escape', () => {
    navigation.path = '/app';
    render(<AppShell section="today">Содержимое</AppShell>);

    fireEvent.click(screen.getByRole('button', { name: 'Быстро добавить' }));

    const dialog = screen.getByRole('dialog', { name: 'Что добавить?' });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByRole('link', { name: /Добавить еду/ })).toHaveAttribute(
      'href',
      '/app?section=nutrition&quick_add=food',
    );
    expect(within(dialog).getByRole('link', { name: /Открыть AI Coach/ })).toHaveAttribute(
      'href',
      '/app?section=profile#profile-ai-coach',
    );

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Что добавить?' })).not.toBeInTheDocument();
  });

  it('открывает доступное mobile-меню с secondary navigation и завершает exit после возврата фокуса', async () => {
    stubViewport(390);
    navigation.path = '/app';
    render(<AppShell section="profile">Содержимое</AppShell>);

    const more = screen.getByRole('button', { name: 'Открыть профиль и настройки' });
    expect(more).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(more);

    expect(more).toHaveAttribute('aria-expanded', 'true');
    const dialog = screen.getByRole('dialog', { name: 'Профиль и настройки' });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByRole('link', { name: 'Профиль и настройки' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(dialog).queryByRole('link', { name: 'База знаний' })).not.toBeInTheDocument();

    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(more).toHaveFocus();
    const closingLayer = document.querySelector<HTMLElement>(
      '.app-more-layer[data-motion-phase="closing"]',
    );
    expect(closingLayer).toBeInTheDocument();
    finishAnimation(closingLayer!, 'app-more-backdrop-out');
    await waitFor(() => expect(document.querySelector('.app-more-layer')).not.toBeInTheDocument());
  });

  it('показывает admin entry только аккаунту с соответствующей capability', () => {
    user.is_root = true;
    navigation.path = '/admin';
    render(<AppShell>Содержимое</AppShell>);

    expect(screen.getByRole('link', { name: 'Админ-панель' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('открывает и закрывает mobile-меню сразу при reduced motion', () => {
    stubViewport(390, true);
    navigation.path = '/app';
    render(<AppShell section="today">Содержимое</AppShell>);

    const more = screen.getByRole('button', { name: 'Открыть профиль и настройки' });
    fireEvent.click(more);
    const dialog = screen.getByRole('dialog', { name: 'Профиль и настройки' });
    expect(dialog).toBeInTheDocument();

    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(document.querySelector('.app-more-layer')).not.toBeInTheDocument();
    expect(more).toHaveFocus();
  });

  it('сохраняет обязательный AuthProvider для обычного production shell', () => {
    authState.missing = true;

    expect(() => render(<AppShell>Содержимое</AppShell>)).toThrow(
      'AppShell must be used inside AuthProvider unless demo config is provided',
    );
  });

  it('использует короткое описание отдельной demo-сессии в rail и mobile menu', () => {
    authState.missing = true;
    render(
      <AppShell
        demo={{
          activeSection: 'today',
          brandTo: '/demo?cabinet=1',
          destinations: [{ key: 'today', label: 'Сегодня', icon: 'today', to: '/demo?cabinet=1' }],
          displayName: 'Демо-кабинет',
          exitTo: '/demo',
          moreLinks: [],
          onReset: vi.fn(),
        }}
      >
        Демо-содержимое
      </AppShell>,
    );

    expect(screen.getByText('Отдельная сессия')).toBeInTheDocument();
    expect(screen.queryByText('Изолированная сессия')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Сценарии' }));
    const dialog = screen.getByRole('dialog', { name: 'Демо-кабинет' });
    expect(within(dialog).getByText('Отдельная сессия')).toBeInTheDocument();
  });

  it('не показывает библиотеку знаний в Web или Telegram Mini App navigation', () => {
    stubViewport(390);
    navigation.path = '/app';
    const web = render(<AppShell section="today">Содержимое</AppShell>);

    expect(screen.queryByRole('link', { name: 'База знаний' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть профиль и настройки' }));
    expect(
      within(screen.getByRole('dialog')).queryByRole('link', { name: 'База знаний' }),
    ).not.toBeInTheDocument();

    web.unmount();
    window.Telegram = { WebApp: { initData: 'signed-init-data' } };
    render(<AppShell section="today">Содержимое</AppShell>);
    expect(screen.queryByRole('link', { name: 'База знаний' })).not.toBeInTheDocument();
  });

  it('показывает тематическую заглушку, если аватар отсутствует или не загрузился', () => {
    const { container, rerender } = render(<AppShell>Содержимое</AppShell>);
    const avatar = container.querySelector('.app-desktop-account-entry__avatar');

    expect(avatar).toHaveTextContent(/🏋️|💪|🏃|🚴|🥗|⚡|🎯|🔥/);

    user.photo_url = 'https://t.me/i/userpic/broken.jpg';
    rerender(<AppShell>Содержимое</AppShell>);
    const image = avatar?.querySelector('img');
    expect(image).toHaveAttribute('src', user.photo_url);

    fireEvent.error(image!);
    expect(avatar?.querySelector('img')).not.toBeInTheDocument();
    expect(avatar).toHaveTextContent(/🏋️|💪|🏃|🚴|🥗|⚡|🎯|🔥/);
  });

  it('показывает private avatar раньше provider photo и возвращается к provider при ошибке', async () => {
    avatarFile.mockResolvedValue({
      blob: new Blob(['private-avatar'], { type: 'image/webp' }),
      filename: null,
    });
    user.custom_avatar = {
      content_type: 'image/webp',
      byte_size: 4096,
      width: 512,
      height: 512,
      updated_at: '2030-01-02T12:00:00',
    };
    user.photo_url = 'https://provider.example.test/avatar.jpg';
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn(() => 'blob:private-avatar'),
      revokeObjectURL: vi.fn(),
    });

    const { container } = render(<AppShell>Содержимое</AppShell>);
    const avatar = container.querySelector('.app-desktop-account-entry__avatar');
    await waitFor(() =>
      expect(avatar?.querySelector('img')).toHaveAttribute('src', 'blob:private-avatar'),
    );
    const privateImage = avatar?.querySelector('img');
    expect(privateImage).not.toBeNull();
    fireEvent.error(privateImage!);
    expect(avatar?.querySelector('img')).toHaveAttribute('src', user.photo_url);
  });

  it('использует account row под брендом как единственный desktop-вход в профиль без dialog', () => {
    navigation.path = '/app';
    render(<AppShell section="profile">Содержимое</AppShell>);

    const profileLink = screen.getByRole('link', { name: 'Профиль и настройки' });
    expect(profileLink).toHaveAttribute('href', '/app?section=profile');
    expect(profileLink).toHaveAttribute('aria-current', 'page');
    expect(profileLink.closest('.app-bottom-nav__profile-slot')).toBeInTheDocument();
    expect(profileLink.closest('nav')).toHaveAccessibleName('Основная навигация');
    expect(screen.queryByRole('link', { name: /^Профиль$/ })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Открыть профиль и настройки' }),
    ).not.toBeInTheDocument();
    expect(document.getElementById('appMorePanel')).not.toBeInTheDocument();
  });

  it('закрывает mobile sheet и переносит focus в desktop account row на breakpoint 900px', async () => {
    const resize = stubViewport(899, true);
    navigation.path = '/app';
    render(<AppShell section="today">Содержимое</AppShell>);

    fireEvent.click(screen.getByRole('button', { name: 'Открыть профиль и настройки' }));
    expect(screen.getByRole('dialog', { name: 'Профиль и настройки' })).toBeInTheDocument();
    expect(document.body.style.position).toBe('fixed');

    resize(900);

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(document.body.style.position).toBe('');
    await waitFor(() =>
      expect(screen.getByRole('link', { name: 'Профиль и настройки' })).toHaveFocus(),
    );

    resize(899);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Открыть профиль и настройки' })).toHaveAttribute(
        'aria-expanded',
        'false',
      ),
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('не перехватывает focus при обычном desktop resize без открытого sheet', async () => {
    const resize = stubViewport(900);
    render(
      <AppShell section="today">
        <button type="button">Контроль focus</button>
      </AppShell>,
    );

    const control = screen.getByRole('button', { name: 'Контроль focus' });
    control.focus();
    resize(1100);

    await waitFor(() => expect(control).toHaveFocus());
  });
});
