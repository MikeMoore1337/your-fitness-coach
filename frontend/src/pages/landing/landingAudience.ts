export type LandingAudience = 'athlete' | 'coach';

export const LANDING_AUDIENCE_ROUTES = {
  athlete: '/',
  athleteAlias: '/for-athletes',
  coach: '/for-trainers',
} as const;

export type LandingLocation = Pick<Location, 'search' | 'hash'>;

export function landingAudienceFromPath(path: string): LandingAudience | null {
  if (path === LANDING_AUDIENCE_ROUTES.coach) return 'coach';
  if (path === LANDING_AUDIENCE_ROUTES.athlete || path === LANDING_AUDIENCE_ROUTES.athleteAlias)
    return 'athlete';
  return null;
}

/** The root remains the canonical athlete landing; the alias is reserved for audience context. */
export function landingCanonicalPath(audience: LandingAudience): string {
  return audience === 'coach' ? LANDING_AUDIENCE_ROUTES.coach : LANDING_AUDIENCE_ROUTES.athlete;
}

/** Preserve campaign and in-page context while letting browser history handle the switch. */
export function landingAudienceHref(
  audience: LandingAudience,
  location: LandingLocation = window.location,
): string {
  const path =
    audience === 'coach' ? LANDING_AUDIENCE_ROUTES.coach : LANDING_AUDIENCE_ROUTES.athleteAlias;
  return `${path}${location.search}${location.hash}`;
}
