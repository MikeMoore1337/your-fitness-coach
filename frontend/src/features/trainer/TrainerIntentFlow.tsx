import { useEffect, useRef } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { api } from '../../shared/api/client';
import type { TrainerCapability } from '../../shared/api/types';
import {
  productEventSurface,
  trackGrowthEvent,
  trackProductEvent,
} from '../../shared/analytics/productEvents';
import { useNavigation } from '../../shared/navigation/router';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Card, ErrorState, LoadingState } from '../../shared/ui/common';
import { TrainerCapabilityConsent } from './TrainerCapabilityConsent';
import './trainer-capability.css';

export function TrainerIntentFlow() {
  const { reloadUser } = useAuth();
  const { navigate } = useNavigation();
  const { toast } = useFeedback();
  const startedRef = useRef(false);
  const capability = useQuery({
    queryKey: ['me', 'trainer-capability'],
    queryFn: () => api<TrainerCapability>('/api/v1/me/trainer-capability'),
  });
  const activate = useMutation({
    mutationFn: () =>
      api<TrainerCapability>('/api/v1/me/trainer-capability', {
        method: 'POST',
        body: { accepted_terms: true },
      }),
    onSuccess: async (result) => {
      if (result.activated_now) {
        trackGrowthEvent('trainer_application_completed');
        trackProductEvent({ name: 'trainer_mode_activated', surface: productEventSurface() });
        trackProductEvent(
          { name: 'trainer_onboarding_started', surface: productEventSurface() },
          { dedupe: 'session' },
        );
      }
      await reloadUser();
      navigate('/coach', true);
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  useEffect(() => {
    if (capability.data?.is_active) navigate('/coach', true);
  }, [capability.data?.is_active, navigate]);

  if (capability.isLoading || capability.data?.is_active) {
    return (
      <main className="container">
        <LoadingState label="Проверяем режим тренера…" />
      </main>
    );
  }
  if (capability.error) {
    return (
      <main className="container">
        <ErrorState
          message={(capability.error as Error).message}
          retry={() => void capability.refetch()}
        />
      </main>
    );
  }

  return (
    <main className="container" aria-labelledby="trainer-intent-title">
      <Card
        title={<span id="trainer-intent-title">Режим тренера</span>}
        description="Дополнительный рабочий режим внутри вашего обычного аккаунта."
        collapsible={false}
      >
        <TrainerCapabilityConsent
          pending={activate.isPending}
          onCancel={() => navigate('/app?section=today', true)}
          onConfirm={() => {
            if (!startedRef.current) {
              startedRef.current = true;
              trackGrowthEvent('trainer_application_started');
            }
            activate.mutate();
          }}
        />
      </Card>
    </main>
  );
}
