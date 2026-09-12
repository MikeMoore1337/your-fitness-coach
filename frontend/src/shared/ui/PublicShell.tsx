import { useEffect, type ReactNode } from 'react';
import { AppLink } from '../navigation/router';
import { useWebTheme } from '../useWebTheme';
import { AppThemeToggle } from './AppThemeToggle';
import { BrandLockup } from './BrandLogo';
import { glassProps } from './Glass';
import './public-shell.css';
import '../../styles/react.css';
import '../../styles/design-v2.css';

type PublicShellProps = {
  children: ReactNode;
  className?: string;
  headerAction?: ReactNode;
  headerNavigation?: ReactNode;
  homeHref?: string;
  skipTarget: string;
};

export function PublicShell({
  children,
  className = '',
  headerAction,
  headerNavigation,
  homeHref = '/',
  skipTarget,
}: PublicShellProps) {
  const { colorScheme } = useWebTheme();

  useEffect(() => {
    document.body.classList.add('public-shell-mode');
    document.body.classList.toggle('public-shell-dark-mode', colorScheme === 'dark');
    return () => {
      document.body.classList.remove('public-shell-mode', 'public-shell-dark-mode');
    };
  }, [colorScheme]);

  const brand = (
    <BrandLockup
      className="public-shell__lockup"
      markClassName="public-shell__logo landing-brand__mark"
    />
  );

  return (
    <div
      className={`public-shell public-shell--design-v2 public-shell--${colorScheme} ${className}`.trim()}
    >
      <a
        className="public-shell__skip-link landing-skip-link"
        href={`#${skipTarget}`}
        onClick={() => document.querySelector<HTMLElement>(`#${skipTarget}`)?.focus()}
      >
        К содержимому
      </a>
      <header
        {...(skipTarget === 'landing-content' ? {} : glassProps('tinted'))}
        className={`public-shell__header landing-header${
          headerNavigation ? '' : ' public-shell__header--simple'
        }`}
      >
        {homeHref.startsWith('#') ? (
          <a
            className="public-shell__brand landing-brand"
            href={homeHref}
            aria-label="Your Fitness Coach — на главную"
          >
            {brand}
          </a>
        ) : (
          <AppLink
            className="public-shell__brand landing-brand"
            to={homeHref}
            aria-label="Your Fitness Coach — на главную"
          >
            {brand}
          </AppLink>
        )}
        {headerNavigation}
        <div className="public-shell__header-actions landing-header__actions">
          <AppThemeToggle landing />
          {headerAction}
        </div>
      </header>
      {children}
    </div>
  );
}
