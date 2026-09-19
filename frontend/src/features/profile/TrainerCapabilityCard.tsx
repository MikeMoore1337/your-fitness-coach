import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { api } from '../../shared/api/client';
import type { TrainerCapability } from '../../shared/api/types';
import {
  productEventSurface,
  trackGrowthEvent,
  trackProductEvent,
} from '../../shared/analytics/productEvents';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Card, ErrorState, LoadingState } from '../../shared/ui/common';
import { AppLink } from '../../shared/navigation/router';
import { TrainerModeSwitch } from '../trainer/TrainerModeSwitch';

export function TrainerCapabilityCard() {
  const { user, reloadUser } = useAuth();
  const { toast, confirm } = useFeedback();
  const queryClient = useQueryClient();
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const capability = useQuery({
    queryKey: ['me', 'trainer-capability'],
    queryFn: () => api<TrainerCapability>('/api/v1/me/trainer-capability'),
    enabled: Boolean(user),
  });
  const refresh = async () => {
    await Promise.all([
      reloadUser(),
      queryClient.invalidateQueries({ queryKey: ['me', 'trainer-capability'] }),
    ]);
  };
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
        setShowOnboarding(true);
      }
      await refresh();
      toast('Режим тренера включён');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const deactivate = useMutation({
    mutationFn: () => api<TrainerCapability>('/api/v1/me/trainer-capability', { method: 'DELETE' }),
    onSuccess: async () => {
      await refresh();
      setAcceptedTerms(false);
      setShowOnboarding(false);
      toast('Режим тренера выключен');
    },
    onError: async (reason) => {
      await capability.refetch();
      toast((reason as Error).message, 'error');
    },
  });

  if (!user) return null;

  const requestDisable = async () => {
    const pendingInvites = capability.data?.pending_invite_count ?? 0;
    const accepted = await confirm({
      title: 'Выключить режим тренера?',
      message: pendingInvites
        ? `Активных клиентов нет. ${pendingInvites} ожидающих приглашений будут отозваны. История работы сохранится.`
        : 'Активных клиентов нет. История завершённых отношений, программ и комментариев сохранится.',
      confirmText: 'Выключить',
      danger: true,
    });
    if (accepted) deactivate.mutate();
  };

  return (
    <Card
      title="Режим тренера"
      description="Дополнительный рабочий режим внутри вашего обычного аккаунта."
      collapsible={false}
    >
      {capability.isLoading ? (
        <LoadingState label="Проверяем режим тренера…" />
      ) : capability.error ? (
        <ErrorState
          message={(capability.error as Error).message}
          retry={() => void capability.refetch()}
        />
      ) : capability.data?.is_active ? (
        <div className="trainer-capability top-gap">
          <div className="trainer-capability__status" role="status">
            <strong>Режим тренера включён</strong>
            <p>Личный профиль и собственные тренировки остаются доступны.</p>
          </div>
          <TrainerModeSwitch mode="personal" />
          {showOnboarding && (
            <section
              className="trainer-capability__onboarding"
              aria-labelledby="trainer-onboarding-title"
            >
              <div>
                <span className="eyebrow">Первый рабочий шаг</span>
                <h3 id="trainer-onboarding-title">Откройте Coach Today</h3>
                <p>
                  Настройка минимальна: пригласите первого клиента из рабочего пространства или
                  сразу пропустите этот шаг и посмотрите весь кабинет.
                </p>
              </div>
              <div className="trainer-capability__onboarding-actions">
                <AppLink
                  className="trainer-capability__onboarding-primary"
                  to="/coach"
                  onClick={() =>
                    trackProductEvent(
                      { name: 'trainer_onboarding_completed', surface: productEventSurface() },
                      { dedupe: 'session' },
                    )
                  }
                >
                  Пригласить первого клиента
                </AppLink>
                <AppLink
                  className="trainer-capability__onboarding-secondary"
                  to="/coach"
                  onClick={() =>
                    trackProductEvent(
                      { name: 'trainer_onboarding_completed', surface: productEventSurface() },
                      { dedupe: 'session' },
                    )
                  }
                >
                  Пропустить и открыть Coach Today
                </AppLink>
              </div>
            </section>
          )}
          <div className="trainer-capability__status">
            <strong>Следующий шаг</strong>
            <p>
              Откройте «Клиенты», создайте приглашение, затем назначьте программу и отслеживайте
              подтверждённый прогресс клиента.
            </p>
          </div>
          <div className="trainer-capability__disable">
            <strong>Отключение режима</strong>
            {capability.data.active_client_count > 0 ? (
              <>
                <p id="trainer-disable-guard" className="trainer-capability__guard" role="status">
                  Сначала завершите работу со всеми активными клиентами (
                  {capability.data.active_client_count}). Их история не удаляется автоматически.
                </p>
                <button
                  type="button"
                  className="btn-danger"
                  aria-describedby="trainer-disable-guard"
                  disabled
                >
                  Выключить режим тренера
                </button>
              </>
            ) : (
              <>
                <p>
                  Завершённые отношения и история сохранятся. Ожидающие приглашения будут отозваны.
                </p>
                <button
                  type="button"
                  className="btn-danger"
                  disabled={deactivate.isPending}
                  onClick={() => void requestDisable()}
                >
                  {deactivate.isPending ? 'Выключаем…' : 'Выключить режим тренера'}
                </button>
              </>
            )}
          </div>
        </div>
      ) : (
        <div className="trainer-capability top-gap">
          <ul className="trainer-capability__facts" aria-label="Возможности режима тренера">
            <li>Приглашать клиентов по персональной ссылке после их согласия.</li>
            <li>Создавать или переиспользовать программы и назначать их клиенту.</li>
            <li>Смотреть разрешённый прогресс и оставлять контекстные комментарии.</li>
          </ul>
          <ul className="trainer-capability__limits" aria-label="Ограничения режима тренера">
            <li>Режим не создаёт публичный профиль, платежи или маркетплейс.</li>
            <li>Сервис не проверяет образование, сертификацию или квалификацию тренера.</li>
            <li>Доступ к данным появляется только после подтверждения связи клиентом.</li>
          </ul>
          <label className="trainer-capability__terms">
            <input
              type="checkbox"
              checked={acceptedTerms}
              onChange={(event) => setAcceptedTerms(event.target.checked)}
            />
            <span>
              <strong>Принимаю условия использования режима тренера</strong>
              <small>
                Буду использовать доступ только для работы с подключёнными клиентами и не выдавать
                включение режима за проверку квалификации.
              </small>
            </span>
          </label>
          <button
            type="button"
            className="trainer-capability__activate"
            disabled={!acceptedTerms || activate.isPending}
            onClick={() => {
              trackGrowthEvent('trainer_application_started');
              activate.mutate();
            }}
          >
            {activate.isPending ? 'Включаем…' : 'Включить режим тренера'}
          </button>
        </div>
      )}
    </Card>
  );
}
