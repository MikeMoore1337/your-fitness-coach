import { lazy, type ReactNode } from 'react';
import { AuthProvider, useAuth } from './AuthProvider';
import { AuthGate } from './AuthGate';
import { OnboardingGate } from './OnboardingGate';
import {
  PERSONAL_WORKSPACE_RETURN_STATE,
  Redirect,
  useNavigation,
} from '../shared/navigation/router';
import { hasExplicitAppDestination } from '../shared/auth/redirects';
import { isTrainerIntentLocation } from '../shared/auth/trainerIntent';

const TrainerIntentFlow = lazy(() =>
  import('../features/trainer/TrainerIntentFlow').then((module) => ({
    default: module.TrainerIntentFlow,
  })),
);

/** Auth internals stay outside the public landing/bootstrap dependency graph. */
export function AuthenticatedRoute({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <AuthGate>{children}</AuthGate>
    </AuthProvider>
  );
}

export function AuthenticatedAppRoute({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { search, path } = useNavigation();
  if (isTrainerIntentLocation(path, search, window.location.hash)) {
    return <TrainerIntentFlow />;
  }
  const isIntentionalPersonalReturn =
    window.history.state?.[PERSONAL_WORKSPACE_RETURN_STATE] === true;
  if (
    user?.is_coach &&
    !isIntentionalPersonalReturn &&
    !hasExplicitAppDestination(search, window.location.hash)
  ) {
    return <Redirect to="/coach" />;
  }
  return <OnboardingGate>{children}</OnboardingGate>;
}
