import type { ReactNode } from 'react';
import { appUrlForHostname } from '../../shared/navigation/appUrl';
import { PublicShell } from '../../shared/ui/PublicShell';
import { LandingAudienceSwitch } from './LandingAudienceSwitch';
import type { LandingAudience } from './landingAudience';
import './landing-v10.css';

type LandingV10ShellProps = {
  audience: LandingAudience;
  children: ReactNode;
};

/** Staged composition shell; current public routes keep using their existing pages until cutover. */
export function LandingV10Shell({ audience, children }: LandingV10ShellProps) {
  return (
    <PublicShell
      className="landing-page landing-v10-page"
      headerBrandSurface="dark"
      homeHref="/"
      skipTarget="landing-v10-content"
      headerNavigation={<LandingAudienceSwitch audience={audience} />}
      headerAction={
        <a
          className="landing-button landing-button--compact"
          href={appUrlForHostname(window.location.hostname)}
        >
          Войти
        </a>
      }
    >
      <main id="landing-v10-content" tabIndex={-1} data-landing-audience={audience}>
        {children}
      </main>
    </PublicShell>
  );
}
