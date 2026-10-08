import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import { LandingAudienceSwitch } from '../../../../src/pages/landing/LandingAudienceSwitch';
import { LandingV10Shell } from '../../../../src/pages/landing/LandingV10Shell';
import {
  landingAudienceFromPath,
  landingAudienceHref,
  landingCanonicalPath,
} from '../../../../src/pages/landing/landingAudience';

function renderShell(audience: 'athlete' | 'coach') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <NavigationProvider>
        <LandingV10Shell audience={audience}>
          <p>Сценарий v10</p>
        </LandingV10Shell>
      </NavigationProvider>
    </QueryClientProvider>,
  );
}

describe('Landing v10 audience foundation', () => {
  afterEach(() => {
    cleanup();
    window.history.replaceState({}, '', '/');
    document.body.className = '';
  });

  it('maps only the staged landing paths to an audience', () => {
    expect(landingAudienceFromPath('/')).toBe('athlete');
    expect(landingAudienceFromPath('/for-athletes')).toBe('athlete');
    expect(landingAudienceFromPath('/for-trainers')).toBe('coach');
    expect(landingAudienceFromPath('/training')).toBeNull();
    expect(landingCanonicalPath('athlete')).toBe('/');
    expect(landingCanonicalPath('coach')).toBe('/for-trainers');
  });

  it('preserves campaign and in-page context in audience links', () => {
    const location = { search: '?utm_source=owner', hash: '#coach-work' };
    expect(landingAudienceHref('athlete', location)).toBe(
      '/for-athletes?utm_source=owner#coach-work',
    );
    expect(landingAudienceHref('coach', location)).toBe(
      '/for-trainers?utm_source=owner#coach-work',
    );
  });

  it('exposes an accessible switch with browser-native history links', () => {
    render(
      <LandingAudienceSwitch
        audience="coach"
        location={{ search: '?utm_campaign=v10', hash: '#coach-work' }}
      />,
    );

    expect(screen.getByRole('navigation', { name: 'Выбор аудитории' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Для себя' })).toHaveAttribute(
      'href',
      '/for-athletes?utm_campaign=v10#coach-work',
    );
    expect(screen.getByRole('link', { name: 'Для тренера' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('composes the staged shell from the shared PublicShell', () => {
    const { container } = renderShell('athlete');
    expect(container.querySelector('.public-shell.landing-v10-page')).toBeInTheDocument();
    expect(container.querySelector('#landing-v10-content')).toHaveAttribute(
      'data-landing-audience',
      'athlete',
    );
    expect(screen.getByRole('link', { name: 'Войти' })).toHaveAttribute('href', '/app');
  });
});
