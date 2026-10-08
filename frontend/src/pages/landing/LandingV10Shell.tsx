import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import { demoCabinetUrlForHostname, loginUrlForHostname } from '../../shared/navigation/appUrl';
import { AppThemeToggle } from '../../shared/ui/AppThemeToggle';
import { Icon } from '../../shared/ui/Icon';
import { PublicShell } from '../../shared/ui/PublicShell';
import { LandingAudienceSwitch } from './LandingAudienceSwitch';
import type { LandingAudience } from './landingAudience';
import './landing-v10.css';

type LandingV10ShellProps = {
  audience: LandingAudience;
  children: ReactNode;
};

/** Shared public shell for the approved Product v10 audience compositions. */
export function LandingV10Shell({ audience, children }: LandingV10ShellProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const navigationRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const rawHash = window.location.hash.slice(1);
    if (!rawHash) return;
    const targetId = (() => {
      try {
        return decodeURIComponent(rawHash);
      } catch {
        return rawHash;
      }
    })();
    let attempts = 0;
    const timer = window.setInterval(() => {
      const target = document.getElementById(targetId);
      if (!target && attempts++ < 20) return;
      window.clearInterval(timer);
      target?.scrollIntoView({ block: 'start' });
    }, 50);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!mobileMenuOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setMobileMenuOpen(false);
      menuButtonRef.current?.focus();
    };
    const closeOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (navigationRef.current?.contains(target) || menuButtonRef.current?.contains(target))
        return;
      setMobileMenuOpen(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    window.addEventListener('pointerdown', closeOnOutsidePointer);
    return () => {
      window.removeEventListener('keydown', closeOnEscape);
      window.removeEventListener('pointerdown', closeOnOutsidePointer);
    };
  }, [mobileMenuOpen]);

  useEffect(() => {
    if (!mobileMenuOpen) return;
    navigationRef.current?.querySelector<HTMLElement>('a[href], button:not([disabled])')?.focus();
  }, [mobileMenuOpen]);

  const demoHref = demoCabinetUrlForHostname(
    window.location.hostname,
    audience === 'coach' ? 'trainer' : 'self_training',
    audience === 'coach' ? 'trainer' : 'today',
  );
  const closeMobileMenu = (restoreFocus = false) => {
    setMobileMenuOpen(false);
    if (restoreFocus) window.requestAnimationFrame(() => menuButtonRef.current?.focus());
  };

  const handleMenuKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Tab') return;
    const focusable = Array.from(
      navigationRef.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled])') ?? [],
    ).filter((element) => element.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0]!;
    const last = focusable[focusable.length - 1]!;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <PublicShell
      className={`landing-page landing-v10-page${mobileMenuOpen ? ' landing-v10-page--menu-open' : ''}`}
      headerBrandSurface="dark"
      homeHref="/"
      skipTarget="landing-v10-content"
      headerNavigation={
        <div
          ref={navigationRef}
          className={`landing-v10-header-navigation${mobileMenuOpen ? ' is-open' : ''}`}
          onKeyDown={handleMenuKeyDown}
        >
          <nav id="landing-navigation" className="landing-nav" aria-label="Навигация по странице">
            <a href="#product" onClick={() => closeMobileMenu(true)}>
              Продукт
            </a>
            <a href={demoHref} onClick={() => closeMobileMenu(true)}>
              Демо
            </a>
            <a href="#faq" onClick={() => closeMobileMenu(true)}>
              Вопросы
            </a>
          </nav>
          <div className="landing-v10-header-audience">
            <LandingAudienceSwitch audience={audience} />
          </div>
          <div className="landing-v10-mobile-menu-controls">
            <LandingAudienceSwitch
              audience={audience}
              showLabel={false}
              onNavigate={() => closeMobileMenu(true)}
            />
            <AppThemeToggle navigation />
          </div>
        </div>
      }
      headerAction={
        <>
          <a
            className="landing-button landing-button--compact"
            href={loginUrlForHostname(window.location.hostname)}
          >
            Войти
          </a>
          <button
            ref={menuButtonRef}
            type="button"
            className={`landing-menu-toggle${mobileMenuOpen ? ' is-open' : ''}`}
            aria-label={mobileMenuOpen ? 'Закрыть меню' : 'Открыть меню'}
            aria-expanded={mobileMenuOpen}
            aria-controls="landing-navigation"
            onClick={() => setMobileMenuOpen((open) => !open)}
          >
            <Icon name={mobileMenuOpen ? 'close' : 'menu'} />
          </button>
        </>
      }
    >
      <main id="landing-v10-content" tabIndex={-1} data-landing-audience={audience}>
        {children}
      </main>
    </PublicShell>
  );
}
