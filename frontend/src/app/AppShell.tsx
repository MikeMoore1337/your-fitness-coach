import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { AppLink, useNavigation } from '../shared/navigation/router';
import { AppThemeToggle } from '../shared/ui/AppThemeToggle';
import { BrandLockup } from '../shared/ui/BrandLogo';
import { AppNavigationIcon, type AppNavigationIconName } from './AppNavigationIcon';
import { useOptionalAuth } from './AuthProvider';
import { useTelegramOverlayBackButton } from '../shared/telegram/useTelegramOverlayBackButton';
import { useDocumentScrollLock } from '../shared/ui/useModalA11y';
import { useMotionPresence } from '../shared/ui/useMotionPresence';
import {
  AccountAvatar,
  AccountIdentity,
  accountRoleLabel,
} from '../shared/account/AccountIdentity';
import { usePwa } from '../shared/pwa/PwaProvider';
import {
  DEFAULT_QUICK_ADD_ACTIONS,
  QuickAddTrigger,
  QuickAddSheet,
  type QuickAddAction,
} from './QuickAddSheet';

export type AppSection = 'today' | 'progress' | 'programs' | 'catalog' | 'nutrition' | 'profile';

const APP_DESTINATIONS: ReadonlyArray<{
  section: AppSection;
  label: string;
  icon: AppNavigationIconName;
}> = [
  { section: 'today', label: 'Сегодня', icon: 'today' },
  { section: 'programs', label: 'План', icon: 'plan' },
  { section: 'nutrition', label: 'Питание', icon: 'nutrition' },
  { section: 'progress', label: 'Прогресс', icon: 'progress' },
];

export interface DemoAppShellConfig {
  activeSection: string;
  brandTo: string;
  destinations: ReadonlyArray<{
    key: string;
    label: string;
    icon: AppNavigationIconName;
    to: string;
  }>;
  displayName: string;
  exitTo: string;
  accountTo?: string;
  accountLabel?: string;
  menuTitle?: string;
  moreLinks: ReadonlyArray<{ label: string; to: string }>;
  quickAddLinks?: ReadonlyArray<QuickAddAction>;
  onReset(): void;
  resetDisabled?: boolean;
}

function mobileNavigationMatches(): boolean {
  return window.matchMedia?.('(max-width: 899px)').matches ?? window.innerWidth < 900;
}

function useMobileNavigation(): boolean {
  const [mobile, setMobile] = useState(mobileNavigationMatches);

  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 899px)');
    const sync = () => setMobile(media?.matches ?? window.innerWidth < 900);
    media?.addEventListener?.('change', sync);
    window.addEventListener('resize', sync);
    sync();
    return () => {
      media?.removeEventListener?.('change', sync);
      window.removeEventListener('resize', sync);
    };
  }, []);

  return mobile;
}

function PwaInstallPrompt() {
  const pwa = usePwa();
  const { markInstallOptionShown, recordAppValue, shouldShowInstallPrompt } = pwa;
  const shownRef = useRef(false);

  useEffect(() => {
    recordAppValue();
  }, [recordAppValue]);

  useEffect(() => {
    if (shouldShowInstallPrompt && !shownRef.current) {
      shownRef.current = true;
      markInstallOptionShown();
    }
  }, [markInstallOptionShown, shouldShowInstallPrompt]);

  if (!shouldShowInstallPrompt) return null;

  return (
    <aside
      className="pwa-install-prompt"
      data-testid="pwa-install-prompt"
      aria-label="Установка приложения"
    >
      <div className="pwa-install-prompt__content">
        <strong>Быстрый возврат к тренировке</strong>
        {pwa.installPromptAvailable ? (
          <p>
            Установите YFC на устройство: приложение откроется отдельным окном и быстрее вернёт вас
            к «Сегодня».
          </p>
        ) : (
          <>
            <p>В Safari добавьте YFC на экран «Домой», чтобы открывать его отдельным окном.</p>
            <ol>
              <li>Нажмите «Поделиться».</li>
              <li>Выберите «На экран Домой».</li>
            </ol>
          </>
        )}
      </div>
      <div className="pwa-install-prompt__actions">
        {pwa.installPromptAvailable && (
          <button type="button" disabled={pwa.installPending} onClick={() => void pwa.install()}>
            {pwa.installPending ? 'Открываем…' : 'Установить'}
          </button>
        )}
        <button type="button" className="secondary" onClick={pwa.dismissInstall}>
          {pwa.installPromptAvailable ? 'Не сейчас' : 'Понятно'}
        </button>
      </div>
    </aside>
  );
}

export function AppShell({
  children,
  demo,
  narrow = false,
  section,
}: {
  children: React.ReactNode;
  demo?: DemoAppShellConfig;
  narrow?: boolean;
  section?: AppSection;
}) {
  const auth = useOptionalAuth();
  const user = auth?.user ?? null;
  const logout = auth?.logout;
  const { path } = useNavigation();
  const [moreOpen, setMoreOpen] = useState(false);
  const [quickAddOpen, setQuickAddOpen] = useState(false);
  const morePresence = useMotionPresence({
    closingAnimationName: 'app-more-backdrop-out',
    openingAnimationName: 'app-more-panel-in',
  });
  const hideMorePresence = morePresence.hide;
  const morePanelRef = useRef<HTMLDivElement>(null);
  const moreTriggerRef = useRef<HTMLElement | null>(null);
  const displayName =
    demo?.displayName ||
    user?.profile?.full_name ||
    user?.first_name ||
    user?.username ||
    'Пользователь';
  const accountRole = accountRoleLabel(Boolean(user?.is_root), Boolean(user?.is_coach));
  const secondaryActive = section === 'catalog' || section === 'profile';
  const isMiniApp = Boolean(window.Telegram?.WebApp?.initData);
  const mobileNavigation = useMobileNavigation();
  const shellDestinations = demo?.destinations ?? APP_DESTINATIONS;
  const quickAddLinks = demo?.quickAddLinks ?? DEFAULT_QUICK_ADD_ACTIONS;
  const brandTo = demo?.brandTo ?? '/app?section=today';
  const shellVisible = Boolean(user || demo);
  const quickAddVisible = shellVisible && (Boolean(demo) || section !== undefined);
  const morePresent = moreOpen || morePresence.present;
  const moreSurfacePresent = morePresent && (Boolean(demo) || mobileNavigation);
  const accountDestinations = [
    {
      key: 'catalog',
      label: 'Упражнения',
      to: '/app?section=catalog',
      icon: 'catalog' as const,
      desktopGroup: 'resources' as const,
      visible: true,
    },
    {
      key: 'profile',
      label: 'Профиль и настройки',
      to: '/app?section=profile',
      icon: 'profile' as const,
      desktopGroup: null,
      visible: true,
    },
    {
      key: 'coach',
      label: 'Кабинет тренера',
      desktopLabel: 'Тренер',
      to: '/coach',
      icon: 'coach' as const,
      desktopGroup: 'workspaces' as const,
      visible: Boolean(user?.is_coach),
    },
    {
      key: 'admin',
      label: 'Администрирование',
      desktopLabel: 'Админ-панель',
      to: '/admin',
      icon: 'admin' as const,
      desktopGroup: 'workspaces' as const,
      visible: Boolean(user?.is_root) && !isMiniApp,
    },
  ].filter((destination) => destination.visible);
  const morePhase = moreOpen && morePresence.phase === 'closed' ? 'open' : morePresence.phase;
  const showPwaInstallPrompt = Boolean(
    !demo && user && shellVisible && path === '/app' && section === 'today',
  );

  const closeMore = (restoreFocus = false) => {
    setMoreOpen(false);
    morePresence.hide();
    if (restoreFocus) moreTriggerRef.current?.focus();
  };
  const openMore = (trigger?: HTMLElement) => {
    if (trigger) moreTriggerRef.current = trigger;
    setMoreOpen(true);
    morePresence.show();
  };
  const openQuickAdd = () => {
    if (moreOpen) closeMore();
    setQuickAddOpen(true);
  };
  useTelegramOverlayBackButton(moreSurfacePresent, () => closeMore(true));

  useDocumentScrollLock(moreSurfacePresent);

  useEffect(() => {
    if (moreOpen) {
      morePanelRef.current?.querySelector<HTMLElement>('button, a')?.focus();
    }
  }, [moreOpen]);

  useEffect(() => {
    if (demo) return;
    const closeAtDesktopBreakpoint = () => {
      if (mobileNavigationMatches() || !moreOpen) return;
      setMoreOpen(false);
      hideMorePresence();
      window.requestAnimationFrame(() => {
        const accountLink = document.getElementById('appAccountProfileLink');
        const railBrand = document.querySelector<HTMLElement>(
          '#appBottomNav .app-bottom-nav__brand',
        );
        (accountLink ?? railBrand)?.focus();
      });
    };
    window.addEventListener('resize', closeAtDesktopBreakpoint);
    return () => window.removeEventListener('resize', closeAtDesktopBreakpoint);
  }, [demo, hideMorePresence, moreOpen]);

  if (!demo && !auth) {
    throw new Error('AppShell must be used inside AuthProvider unless demo config is provided');
  }

  const handleMoreKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeMore(true);
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>('a[href], button:not([disabled])'),
    ).filter((element) => element.offsetParent !== null);
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="app-shell app-shell--design-v2">
      {!demo && shellVisible && mobileNavigation && (
        <header className="app-mobile-header">
          <AppLink
            className="app-mobile-header__brand"
            to={brandTo}
            aria-label="Your Fitness Coach — сегодня"
          >
            <BrandLockup markClassName="app-mobile-header__brand-mark" />
          </AppLink>
          <button
            id="appProfileButton"
            type="button"
            className={`app-mobile-header__profile${moreOpen || secondaryActive ? ' is-active' : ''}`}
            aria-expanded={moreOpen}
            aria-controls="appMorePanel"
            aria-label="Открыть профиль и настройки"
            onClick={(event) => (moreOpen ? closeMore() : openMore(event.currentTarget))}
          >
            <AccountAvatar
              className="app-bottom-nav__avatar"
              customAvatarVersion={user?.custom_avatar?.updated_at}
              name={displayName}
              photoUrl={user?.photo_url}
            />
          </button>
        </header>
      )}
      {showPwaInstallPrompt && <PwaInstallPrompt />}
      {quickAddVisible && <QuickAddTrigger onOpen={openQuickAdd} />}
      {quickAddVisible && (
        <QuickAddSheet
          actions={quickAddLinks}
          onClose={() => setQuickAddOpen(false)}
          open={quickAddOpen}
        />
      )}
      <main id="appContent" className={`container app-shell__content${narrow ? ' narrow' : ''}`}>
        {children}
      </main>
      {shellVisible && (
        <>
          <nav
            id="appBottomNav"
            className={`app-bottom-nav${demo ? ' app-bottom-nav--demo' : ''}`}
            aria-label="Основная навигация"
          >
            <AppLink
              className="app-bottom-nav__brand"
              to={brandTo}
              aria-label={demo ? 'Your Fitness Coach — демо' : 'Your Fitness Coach — сегодня'}
            >
              <BrandLockup markClassName="app-bottom-nav__brand-mark" />
            </AppLink>

            {(!demo || demo.accountTo) && (
              <div className="app-bottom-nav__profile-slot">
                <AppLink
                  id="appAccountProfileLink"
                  to={demo?.accountTo ?? '/app?section=profile'}
                  className={`app-desktop-account-entry${
                    (
                      demo
                        ? demo.activeSection === 'profile'
                        : path === '/app' && section === 'profile'
                    )
                      ? ' is-active'
                      : ''
                  }`}
                  aria-current={
                    (
                      demo
                        ? demo.activeSection === 'profile'
                        : path === '/app' && section === 'profile'
                    )
                      ? 'page'
                      : undefined
                  }
                  aria-label={demo?.accountLabel ?? 'Профиль и настройки'}
                >
                  <AccountIdentity
                    avatarClassName="app-desktop-account-entry__avatar"
                    className="app-desktop-account-entry__identity"
                    customAvatarVersion={user?.custom_avatar?.updated_at}
                    name={displayName}
                    photoUrl={user?.photo_url}
                    role={accountRole}
                  />
                </AppLink>
              </div>
            )}

            <div className="app-bottom-nav__primary">
              {shellDestinations.map((destination) => {
                const destinationKey =
                  'section' in destination ? destination.section : destination.key;
                const active = demo
                  ? demo.activeSection === destinationKey
                  : path === '/app' && section === destinationKey;
                return (
                  <AppLink
                    key={destinationKey}
                    to={
                      'to' in destination ? destination.to : `/app?section=${destination.section}`
                    }
                    className={`app-bottom-nav__btn${active ? ' is-active' : ''}`}
                    aria-current={active ? 'page' : undefined}
                  >
                    <AppNavigationIcon name={destination.icon} />
                    <span className="app-bottom-nav__label">{destination.label}</span>
                  </AppLink>
                );
              })}
              {demo && (
                <button
                  id="appMoreButton"
                  type="button"
                  className={`app-bottom-nav__btn app-bottom-nav__more${moreOpen ? ' is-active' : ''}`}
                  aria-expanded={moreOpen}
                  aria-controls="appMorePanel"
                  onClick={(event) => (moreOpen ? closeMore() : openMore(event.currentTarget))}
                >
                  <AppNavigationIcon name="more" />
                  <span className="app-bottom-nav__label">Сценарии</span>
                </button>
              )}
            </div>

            {!demo && (
              <div
                className="app-bottom-nav__secondary"
                role="group"
                aria-label="Дополнительные разделы"
              >
                {(['resources', 'workspaces'] as const).map((group) => {
                  const destinations = accountDestinations.filter(
                    (destination) => destination.desktopGroup === group,
                  );
                  if (!destinations.length) return null;
                  return (
                    <div className="app-bottom-nav__secondary-group" key={group}>
                      <p className="app-bottom-nav__group-label">
                        {group === 'resources' ? 'Ресурсы' : 'Рабочие пространства'}
                      </p>
                      {destinations.map((destination) => {
                        const active =
                          destination.to === '/coach'
                            ? path === '/coach'
                            : destination.to === '/admin'
                              ? path === '/admin'
                              : path === '/app' && section === destination.key;
                        return (
                          <AppLink
                            key={destination.key}
                            to={destination.to}
                            className={`app-bottom-nav__btn${active ? ' is-active' : ''}`}
                            aria-current={active ? 'page' : undefined}
                          >
                            <AppNavigationIcon name={destination.icon} />
                            <span className="app-bottom-nav__label">
                              {'desktopLabel' in destination
                                ? destination.desktopLabel
                                : destination.label}
                            </span>
                          </AppLink>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            )}

            <div className="app-bottom-nav__utility">
              <AppThemeToggle navigation />
              {demo ? (
                <div className="app-bottom-nav__account">
                  <AccountAvatar
                    className="app-bottom-nav__avatar"
                    name={displayName}
                    photoUrl={user?.photo_url}
                  />
                  <>
                    <strong className="app-bottom-nav__account-name">{displayName}</strong>
                    <small className="app-bottom-nav__account-role">Отдельная сессия</small>
                  </>
                  <AppLink
                    className="app-bottom-nav__logout"
                    to={demo.exitTo}
                    aria-label="Выйти из демо"
                    title="Выйти из демо"
                  >
                    <AppNavigationIcon name="logout" />
                  </AppLink>
                </div>
              ) : (
                <button
                  type="button"
                  className="app-bottom-nav__btn app-bottom-nav__logout app-bottom-nav__utility-action"
                  onClick={() => void logout?.()}
                  aria-label="Выйти из аккаунта"
                  title="Выйти из аккаунта"
                >
                  <AppNavigationIcon name="logout" />
                  <span className="app-bottom-nav__label">Выйти</span>
                </button>
              )}
            </div>
          </nav>

          {moreSurfacePresent && (
            <div
              className="app-more-layer"
              data-motion-phase={morePhase}
              aria-hidden={morePhase === 'closing' || undefined}
              onAnimationEnd={morePresence.onAnimationEnd}
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) closeMore(true);
              }}
            >
              <div
                id="appMorePanel"
                className="app-more-panel"
                ref={morePanelRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="appMoreTitle"
                aria-hidden={morePhase === 'closing' || undefined}
                inert={morePhase === 'closing'}
                onKeyDown={handleMoreKeyDown}
              >
                <header className="app-more-panel__header">
                  <div className="app-more-panel__account">
                    <AccountIdentity
                      avatarClassName="app-bottom-nav__avatar"
                      className="app-more-panel__identity"
                      customAvatarVersion={user?.custom_avatar?.updated_at}
                      name={demo?.menuTitle ?? displayName}
                      photoUrl={user?.photo_url}
                      role={demo ? 'Отдельная сессия' : accountRole}
                    />
                    <span className="sr-only" id="appMoreTitle">
                      {demo?.menuTitle ?? (demo ? displayName : 'Профиль и настройки')}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="app-more-panel__close"
                    onClick={() => closeMore(true)}
                    aria-label="Закрыть меню"
                  >
                    <AppNavigationIcon name="close" />
                  </button>
                </header>

                <nav className="app-more-panel__nav" aria-label="Дополнительная навигация">
                  {demo && demo.accountTo && (
                    <AppLink
                      className="app-more-panel__item"
                      to={demo.accountTo}
                      aria-current={demo.activeSection === 'profile' ? 'page' : undefined}
                      onClick={() => closeMore()}
                    >
                      <AppNavigationIcon name="profile" />
                      <span>{demo.accountLabel ?? 'Профиль и настройки'}</span>
                    </AppLink>
                  )}
                  {demo &&
                    demo.moreLinks.map((item) => (
                      <AppLink
                        className="app-more-panel__item"
                        key={item.to}
                        onClick={() => closeMore()}
                        to={item.to}
                      >
                        <AppNavigationIcon name="plan" />
                        <span>{item.label}</span>
                      </AppLink>
                    ))}
                  {!demo &&
                    accountDestinations.map((destination) => {
                      const active =
                        destination.to === '/coach'
                          ? path === '/coach'
                          : destination.to === '/admin'
                            ? path === '/admin'
                            : path === '/app' && section === destination.key;
                      return (
                        <AppLink
                          key={destination.key}
                          to={destination.to}
                          className="app-more-panel__item"
                          aria-current={active ? 'page' : undefined}
                          onClick={() => closeMore()}
                        >
                          <AppNavigationIcon name={destination.icon} />
                          <span>{destination.label}</span>
                        </AppLink>
                      );
                    })}
                </nav>

                <div className="app-more-panel__actions">
                  <AppThemeToggle navigation />
                  {demo ? (
                    <>
                      <button
                        type="button"
                        className="app-more-panel__item"
                        disabled={demo.resetDisabled}
                        onClick={() => {
                          demo.onReset();
                          closeMore();
                        }}
                      >
                        <AppNavigationIcon name="progress" />
                        <span>Сбросить демо</span>
                      </button>
                      <AppLink
                        className="app-more-panel__item app-more-panel__logout"
                        onClick={() => closeMore()}
                        to={demo.exitTo}
                      >
                        <AppNavigationIcon name="logout" />
                        <span>Выйти из демо</span>
                      </AppLink>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="app-more-panel__item app-more-panel__logout"
                      onClick={() => void logout?.()}
                    >
                      <AppNavigationIcon name="logout" />
                      <span>Выйти из аккаунта</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
