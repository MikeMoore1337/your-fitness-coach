import { useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { profileGoals, type ProfileGoal } from '../../features/profile/goals';
import { api } from '../../shared/api/client';
import type { User } from '../../shared/api/types';
import { safeAuthNextPath } from '../../shared/auth/redirects';
import {
  productEventSurface,
  trackProductEvent,
  type ProductEvent,
} from '../../shared/analytics/productEvents';
import { useNavigation } from '../../shared/navigation/router';
import { AppThemeToggle } from '../../shared/ui/AppThemeToggle';
import { StepProgress } from '../../shared/ui/DataViz';
import { BrandLogo } from '../../shared/ui/BrandLogo';
import { Button, CheckIcon, ChevronIcon, ErrorState } from '../../shared/ui/common';
import '../../styles/react.css';
import '../../styles/design-v2.css';

const nextActions = [
  {
    key: 'nutrition',
    title: 'Настроить питание',
    description: 'Рассчитать стартовый ориентир калорий, белков, жиров и углеводов.',
    to: '/app?section=nutrition',
  },
  {
    key: 'programs',
    title: 'Подобрать программу',
    description: 'Выбрать план тренировок под свою цель и доступный график.',
    to: '/app?section=programs',
  },
  {
    key: 'today',
    title: 'Открыть «Сегодня»',
    description: 'Посмотреть ближайшую тренировку и текущие задачи.',
    to: '/app?section=today',
  },
] as const;

function trackNextAction(nextAction: ProductEvent & { name: 'onboarding_next_action_selected' }) {
  trackProductEvent(nextAction);
}

export default function OnboardingPage() {
  const { user, reloadUser } = useAuth();
  const { navigate } = useNavigation();
  const [goal, setGoal] = useState<ProfileGoal | null>(
    (user?.profile?.goal as ProfileGoal | null | undefined) ?? null,
  );
  const [saved, setSaved] = useState(user?.onboarding?.status === 'complete');
  const [validationError, setValidationError] = useState<string | null>(null);
  const completionHeading = useRef<HTMLHeadingElement>(null);
  const nextPath = safeAuthNextPath(new URLSearchParams(window.location.search).get('next'));
  const surface = productEventSurface();
  const complete = saved || user?.onboarding?.status === 'complete';

  useEffect(() => {
    if (complete) return;
    trackProductEvent({ name: 'onboarding_started', surface }, { dedupe: 'session' });
  }, [complete, surface]);

  useEffect(() => {
    if (complete) completionHeading.current?.focus();
  }, [complete]);

  const mutation = useMutation({
    mutationFn: (selectedGoal: ProfileGoal) =>
      api<User>('/api/v1/me/profile', {
        method: 'PATCH',
        body: { goal: selectedGoal },
      }),
    onSuccess: () => {
      setSaved(true);
      trackProductEvent({ name: 'onboarding_completed', surface });
      void reloadUser();
    },
  });

  const chooseNextAction = (
    nextAction: 'today' | 'nutrition' | 'programs' | 'continuation',
    to: string,
  ) => {
    trackNextAction({ name: 'onboarding_next_action_selected', surface, next_action: nextAction });
    navigate(to);
  };

  return (
    <main className="container narrow onboarding-page onboarding-page--design-v2" id="main-content">
      <header className="onboarding-header">
        <div className="onboarding-brand-lockup">
          <BrandLogo className="onboarding-brand" decorative variant="mark" />
          <span>Your Fitness Coach</span>
        </div>
        <AppThemeToggle />
      </header>

      <section className="onboarding-panel" aria-labelledby="onboarding-title">
        {!complete ? (
          <>
            <StepProgress current={1} labels={['Быстрый старт']} />
            <div className="onboarding-intro">
              <span className="eyebrow">Только необходимое</span>
              <h1 id="onboarding-title">Какая у вас главная цель?</h1>
              <p>
                Это поможет сразу показывать подходящие программы и настройки. Остальные данные
                спросим только там, где они действительно понадобятся.
              </p>
            </div>

            <form
              className="onboarding-form"
              onSubmit={(event) => {
                event.preventDefault();
                if (!goal) {
                  setValidationError('Выберите одну цель, чтобы продолжить.');
                  return;
                }
                setValidationError(null);
                mutation.mutate(goal);
              }}
            >
              <fieldset className="onboarding-goals" aria-describedby="onboarding-goal-hint">
                <legend className="sr-only">Главная цель</legend>
                {profileGoals.map((option) => (
                  <label
                    className={`onboarding-goal${goal === option.value ? ' is-selected' : ''}`}
                    key={option.value}
                  >
                    <input
                      type="radio"
                      name="goal"
                      value={option.value}
                      checked={goal === option.value}
                      onChange={() => {
                        setGoal(option.value);
                        setValidationError(null);
                      }}
                    />
                    <span className="onboarding-goal__control" aria-hidden="true" />
                    <span className="onboarding-goal__copy">
                      <strong>{option.label}</strong>
                      <span>{option.description}</span>
                    </span>
                  </label>
                ))}
              </fieldset>
              <p className="muted onboarding-form__hint" id="onboarding-goal-hint">
                Цель можно изменить позже в профиле.
              </p>
              {validationError && <ErrorState message={validationError} />}
              {mutation.isError && (
                <ErrorState
                  message={(mutation.error as Error).message || 'Не удалось сохранить цель'}
                />
              )}
              <Button type="submit" fullWidth disabled={mutation.isPending}>
                {mutation.isPending ? 'Сохраняем…' : 'Продолжить'}
              </Button>
            </form>
          </>
        ) : (
          <div className="onboarding-complete">
            <span className="onboarding-complete__mark" aria-hidden="true">
              <CheckIcon />
            </span>
            <div className="onboarding-intro">
              <span className="eyebrow">Основа готова</span>
              <h1 id="onboarding-title" ref={completionHeading} tabIndex={-1}>
                С чего хотите начать?
              </h1>
              <p>Выберите один полезный шаг. Остальные разделы останутся доступны в приложении.</p>
            </div>

            {nextPath !== '/app' ? (
              <button
                type="button"
                className="onboarding-next-action onboarding-next-action--primary"
                onClick={() => chooseNextAction('continuation', nextPath)}
              >
                <span>
                  <strong>Продолжить начатый сценарий</strong>
                  <small>Вернуться туда, куда вы направлялись после входа.</small>
                </span>
                <ChevronIcon />
              </button>
            ) : (
              <div className="onboarding-next-actions" aria-label="Следующий шаг">
                {nextActions.map((action) => (
                  <button
                    type="button"
                    className="onboarding-next-action"
                    key={action.key}
                    onClick={() => chooseNextAction(action.key, action.to)}
                  >
                    <span>
                      <strong>{action.title}</strong>
                      <small>{action.description}</small>
                    </span>
                    <ChevronIcon />
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
