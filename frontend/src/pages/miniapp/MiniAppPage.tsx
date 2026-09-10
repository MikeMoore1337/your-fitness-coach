import { lazy, Suspense, useEffect, useState } from 'react';
import { AppShell, type AppSection } from '../../app/AppShell';
import '../../styles/react.css';
import '../../styles/design-v2.css';
import { useAuth } from '../../app/AuthProvider';
import {
  authRecoveryMessage,
  providerLabel,
  safeOAuthProvider,
} from '../../shared/auth/oauthRecovery';
import { TelegramLinkPrompt } from '../../features/account/TelegramLinkPrompt';
import { TodayDashboard } from '../../features/dashboard/TodayDashboard';
import type { WorkoutNavigationTarget } from '../../features/workouts/WorkoutHistory';
import { AppLink, focusedContextReturn, useNavigation } from '../../shared/navigation/router';
import { Badge, Card } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { AiCoachSettingsCard, useAiCoachStatus } from '../../features/ai/AiCoachExperience';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { useSemanticMotion } from '../../shared/ui/useSemanticMotion';
import { programProfileReadiness } from '../../features/profile/programReadiness';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import '../../styles/pulse-concepts.css';
import '../../styles/semantic-cards.css';

const NotificationsPanel = lazy(() =>
  import('../../features/account/NotificationsPanel').then((module) => ({
    default: module.NotificationsPanel,
  })),
);
const AccountPrivacy = lazy(() =>
  import('../../features/account/AccountPrivacy').then((module) => ({
    default: module.AccountPrivacy,
  })),
);
const Diary = lazy(() =>
  import('../../features/diary/Diary').then((module) => ({ default: module.Diary })),
);
const ExerciseCatalog = lazy(() =>
  import('../../features/exercises/ExerciseCatalog').then((module) => ({
    default: module.ExerciseCatalog,
  })),
);
const NutritionPage = lazy(() =>
  import('../../features/nutrition/NutritionPage').then((module) => ({
    default: module.NutritionPage,
  })),
);
const CoachInvites = lazy(() =>
  import('../../features/profile/CoachInvites').then((module) => ({
    default: module.CoachInvites,
  })),
);
const TrainerCapabilityCard = lazy(() =>
  import('../../features/profile/TrainerCapabilityCard').then((module) => ({
    default: module.TrainerCapabilityCard,
  })),
);
const ProfileForm = lazy(() =>
  import('../../features/profile/ProfileForm').then((module) => ({
    default: module.ProfileForm,
  })),
);
const ProgramBuilder = lazy(() =>
  import('../../features/programs/ProgramBuilder').then((module) => ({
    default: module.ProgramBuilder,
  })),
);
const HistoricalProgramWorkout = lazy(() =>
  import('../../features/programs/HistoricalProgramWorkout').then((module) => ({
    default: module.HistoricalProgramWorkout,
  })),
);
const TemplatesList = lazy(() =>
  import('../../features/programs/TemplatesList').then((module) => ({
    default: module.TemplatesList,
  })),
);
const ProgressSchedule = lazy(() =>
  import('../../features/workouts/ProgressSchedule').then((module) => ({
    default: module.ProgressSchedule,
  })),
);
const WorkoutHistory = lazy(() =>
  import('../../features/workouts/WorkoutHistory').then((module) => ({
    default: module.WorkoutHistory,
  })),
);

const sections: ReadonlyArray<AppSection> = [
  'today',
  'progress',
  'programs',
  'catalog',
  'nutrition',
  'profile',
];

function requestedSection(search: string): AppSection | null {
  const params = new URLSearchParams(search);
  const section = params.get('section');
  if (section && sections.includes(section as AppSection)) return section as AppSection;
  return requestedWorkoutFeedback(search) ? 'progress' : null;
}

function requestedNutritionDate(search: string): string | undefined {
  const value = new URLSearchParams(search).get('date');
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : undefined;
}

type NutritionMealType = 'breakfast' | 'lunch' | 'dinner' | 'snacks';

function requestedNutritionMeal(search: string): NutritionMealType | undefined {
  const value = new URLSearchParams(search).get('meal');
  return value === 'breakfast' || value === 'lunch' || value === 'dinner' || value === 'snacks'
    ? value
    : undefined;
}

function requestedHydrationQuick(search: string): boolean {
  return new URLSearchParams(search).get('hydration') === 'quick';
}

function requestedWellbeingDate(search: string): string | undefined {
  const value = new URLSearchParams(search).get('wellbeing_date');
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : undefined;
}

function requestedProgramStart(search: string): 'create' | 'templates' | null {
  const value = new URLSearchParams(search).get('start');
  return value === 'create' || value === 'templates' ? value : null;
}

function requestedProgressReturn(search: string): string | undefined {
  const value = new URLSearchParams(search).get('return_to');
  if (!value) return undefined;
  try {
    const parsed = new URL(value, window.location.origin);
    return parsed.origin === window.location.origin &&
      parsed.pathname === '/app' &&
      parsed.searchParams.get('section') === 'progress'
      ? `${parsed.pathname}${parsed.search}${parsed.hash}`
      : undefined;
  } catch {
    return undefined;
  }
}

function positiveId(value: string | null): number | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function requestedWorkoutFeedback(search: string): {
  workoutId: number;
  commentId: number | null;
  workoutExerciseId: number | null;
} | null {
  const params = new URLSearchParams(search);
  const workoutId = positiveId(params.get('workout_id'));
  if (!workoutId) return null;
  return {
    workoutId,
    commentId: positiveId(params.get('comment_id')),
    workoutExerciseId: positiveId(params.get('workout_exercise_id')),
  };
}

function requestedHistoricalProgramWorkout(search: string): {
  programId: number;
  revisionNumber: number;
  workoutId: number;
} | null {
  const params = new URLSearchParams(search);
  const workoutId = positiveId(params.get('workout_id'));
  const programId = positiveId(params.get('program_history'));
  const revisionNumber = positiveId(params.get('program_revision'));
  return workoutId && programId && revisionNumber ? { workoutId, programId, revisionNumber } : null;
}

function launchInviteToken(): string | null {
  const params = new URLSearchParams(window.location.search);
  const startParam =
    window.Telegram?.WebApp?.initDataUnsafe?.start_param ||
    params.get('tgWebAppStartParam') ||
    params.get('startapp');
  return startParam?.startsWith('trainer_') ? startParam.slice('trainer_'.length) : null;
}

export default function MiniAppPage() {
  const { user, reloadUser } = useAuth();
  const { navigate, search } = useNavigation();
  const { toast } = useFeedback();
  const [initialInviteToken] = useState(launchInviteToken);
  const [fallbackSection] = useState<AppSection>(() => {
    const requested = requestedSection(window.location.search);
    if (requested) return requested;
    const params = new URLSearchParams(window.location.search);
    return initialInviteToken || params.has('auth_linked') || params.has('auth_error')
      ? 'profile'
      : 'today';
  });
  const section = requestedSection(search) ?? fallbackSection;
  const aiCoachStatus = useAiCoachStatus(section === 'profile');
  const nutritionDate = requestedNutritionDate(search);
  const nutritionMeal = requestedNutritionMeal(search);
  const nutritionHydrationOpen = requestedHydrationQuick(search);
  const reportHandoffId =
    section === 'progress'
      ? positiveId(new URLSearchParams(search).get('report_handoff_id'))
      : null;
  const sectionMotion = useSemanticMotion<HTMLDivElement>(section, {
    animateInitial: section === 'progress',
  });
  const analyticsSurface = productEventSurface();
  const requestedFeedback = requestedWorkoutFeedback(search);
  const historicalProgramWorkout = requestedHistoricalProgramWorkout(search);
  const workoutReturnPath = requestedFeedback ? focusedContextReturn(search) : null;
  const focusWeeklyReview = new URLSearchParams(search).get('weekly_review') === '1';
  const focusDailyWellbeing = new URLSearchParams(search).get('wellbeing') === '1';
  const dailyWellbeingDate = requestedWellbeingDate(search);
  const [focusedWorkout, setFocusedWorkout] = useState<{
    id: number;
    target: WorkoutNavigationTarget;
  } | null>(null);
  const [inviteToken, setInviteToken] = useState<string | null>(initialInviteToken);
  const scheduleFocusId =
    requestedFeedback?.workoutId ??
    (focusedWorkout?.target === 'schedule' ? focusedWorkout.id : null);
  const historyFocusId =
    requestedFeedback?.workoutId ??
    (focusedWorkout?.target === 'history' ? focusedWorkout.id : null);

  useEffect(() => {
    if (reportHandoffId === null) return;
    const params = new URLSearchParams({ handoff_id: String(reportHandoffId) });
    if (
      new URLSearchParams(search).get('return_to') === '/app?section=profile#profile-notifications'
    ) {
      params.set('return_to', '/app?section=profile#profile-notifications');
    }
    navigate(`/app/report?${params}`, true);
  }, [navigate, reportHandoffId, search]);

  useEffect(() => {
    if (analyticsSurface === 'tma') {
      trackProductEvent({ name: 'tma_launched', surface: 'tma' }, { dedupe: 'session' });
    }
  }, [analyticsSurface]);

  useEffect(() => {
    if (section === 'today') {
      trackProductEvent({ name: 'today_viewed', surface: analyticsSurface }, { dedupe: 'session' });
    }
  }, [analyticsSurface, section]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const rawLinkedProvider = params.get('auth_linked');
    const linkedProvider = safeOAuthProvider(rawLinkedProvider);
    const authError = params.get('auth_error');
    const oauthProvider = safeOAuthProvider(params.get('oauth_provider'));
    if (!rawLinkedProvider && !authError) return;

    if (linkedProvider) {
      toast(`${providerLabel(linkedProvider)} привязан к аккаунту`);
    } else {
      const linkError = authError === 'conflict' ? 'oauth_link_conflict' : authError;
      toast(
        authRecoveryMessage(linkError, oauthProvider) ??
          'Не удалось связаться с сервисом авторизации',
        'error',
      );
    }

    params.delete('auth_linked');
    params.delete('auth_error');
    params.delete('oauth_provider');
    params.delete('next');
    const query = params.toString();
    window.history.replaceState(
      null,
      '',
      `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`,
    );
  }, [toast]);
  const programStart = section === 'programs' ? requestedProgramStart(search) : null;
  const profileReadiness = programProfileReadiness(user?.profile);
  const profileFormKey = JSON.stringify([
    user?.profile?.full_name,
    user?.profile?.birth_date,
    user?.profile?.goal,
    user?.profile?.level,
    user?.profile?.height_cm,
    user?.profile?.weight_kg,
    user?.profile?.workouts_per_week,
    user?.profile?.cardio_trainings_per_week,
    user?.profile?.timezone,
  ]);
  const revealDetails = (details: HTMLDetailsElement | null) => {
    if (!details || details.open) return;
    const summary = details.querySelector('summary');
    if (summary instanceof HTMLElement) summary.click();
  };
  const openProfileSection = (detailsId: string, targetId = detailsId) => {
    const details = document.getElementById(detailsId);
    revealDetails(details instanceof HTMLDetailsElement ? details : null);
    window.requestAnimationFrame(() =>
      document.getElementById(targetId)?.scrollIntoView({ block: 'start' }),
    );
  };

  useEffect(() => {
    if (section !== 'profile') return;
    const targetId = window.location.hash.slice(1);
    if (!targetId.startsWith('profile-')) return;
    const revealHashTarget = () => {
      const target = document.getElementById(targetId);
      if (!target) return false;
      const details =
        target instanceof HTMLDetailsElement ? target : target?.closest('details.card-disclosure');
      revealDetails(details instanceof HTMLDetailsElement ? details : null);
      target?.scrollIntoView({ block: 'start' });
      return true;
    };

    if (revealHashTarget()) return;

    const observer = new MutationObserver(() => {
      if (revealHashTarget()) observer.disconnect();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [section, search]);

  return (
    <AppShell section={section}>
      <div
        className={`page-stack app-section app-section--${section} app-section--design-v2`}
        id={sectionMotion.elementId}
        data-motion-phase={section === 'progress' ? sectionMotion.motionPhase : 'idle'}
        data-motion-revision={sectionMotion.motionRevision}
        data-motion-surface={section === 'progress' ? 'progress' : undefined}
        onAnimationEnd={sectionMotion.onMotionAnimationEnd}
      >
        {section !== 'today' && section !== 'progress' && section !== 'nutrition' && (
          <header className="card hero-card">
            <div>
              <span className="eyebrow">Your Fitness Coach</span>
              <h1>
                {section === 'profile'
                  ? 'Профиль и настройки'
                  : section === 'programs'
                    ? 'Программа тренировок'
                    : user?.profile?.full_name || user?.first_name || 'Мой фитнес'}
              </h1>
              <p className="muted">
                {section === 'profile'
                  ? 'Личные данные, связи, уведомления и безопасность аккаунта.'
                  : section === 'programs'
                    ? 'Текущая программа, тренировочные дни и создание своего плана.'
                    : 'Тренировки, питание и прогресс в одном месте.'}
              </p>
            </div>
          </header>
        )}
        {(section === 'programs' || section === 'catalog') && <TelegramLinkPrompt />}
        <section className="page-stack">
          <Suspense
            fallback={
              <p className="muted" role="status">
                Загружаем раздел…
              </p>
            }
          >
            {section === 'today' && (
              <TodayDashboard
                initialWellbeingDate={dailyWellbeingDate}
                initialWellbeingOpen={focusDailyWellbeing}
              />
            )}
            {section === 'progress' && (
              <>
                {workoutReturnPath?.includes('section=programs') && (
                  <AppLink className="program-history-return" to={workoutReturnPath}>
                    К истории программы
                  </AppLink>
                )}
                {historicalProgramWorkout && (
                  <HistoricalProgramWorkout {...historicalProgramWorkout} />
                )}
                <div className="stack progress-workout-stack">
                  <ProgressSchedule
                    userId={user?.id}
                    timeZone={user?.profile?.timezone}
                    focusedWorkoutId={historicalProgramWorkout ? null : scheduleFocusId}
                    focusedCommentId={requestedFeedback?.commentId}
                    focusedExerciseId={requestedFeedback?.workoutExerciseId}
                    focusWeeklyReview={focusWeeklyReview}
                    measurementDiary={
                      <Diary embedded onSaved={async () => void (await reloadUser())} />
                    }
                  />
                  <WorkoutHistory
                    timeZone={user?.profile?.timezone}
                    focusedWorkoutId={historicalProgramWorkout ? null : historyFocusId}
                    focusedCommentId={requestedFeedback?.commentId}
                    focusedExerciseId={requestedFeedback?.workoutExerciseId}
                    onWorkoutSelect={(id, target) => setFocusedWorkout({ id, target })}
                  />
                </div>
              </>
            )}
            {section === 'programs' && (
              <>
                <TemplatesList
                  key={programStart === 'templates' ? 'templates-start' : 'templates-default'}
                  defaultLibraryOpen={programStart === 'templates'}
                >
                  <ProgramBuilder
                    key={programStart === 'create' ? 'create-start' : 'create-default'}
                    defaultOpen={programStart === 'create'}
                  />
                </TemplatesList>
              </>
            )}
            {section === 'catalog' && <ExerciseCatalog canCreate={Boolean(user?.is_coach)} />}
            {section === 'nutrition' && (
              <NutritionPage
                key={JSON.stringify([
                  user?.profile?.kbju ?? null,
                  nutritionDate,
                  nutritionMeal,
                  nutritionHydrationOpen,
                ])}
                initial={user?.profile?.kbju}
                initialDate={nutritionDate}
                initialMealType={nutritionMeal}
                initialHydrationOpen={nutritionHydrationOpen}
                returnPath={requestedProgressReturn(search)}
                timeZone={user?.profile?.timezone}
                onSaved={async () => void (await reloadUser())}
              />
            )}
            {section === 'profile' && (
              <div className="profile-settings">
                {!profileReadiness.isComplete && (
                  <section className="profile-status-shell" aria-labelledby="profile-status-title">
                    <div className="profile-status-shell__copy">
                      <span className="eyebrow">Основа рекомендаций</span>
                      <h2 id="profile-status-title">Профиль стоит дополнить</h2>
                      <p>
                        Цель, уровень и число силовых тренировок в неделю помогают предложить
                        подходящую программу.
                      </p>
                    </div>
                    <div className="profile-status-shell__value">
                      <span>Заполнено</span>
                      <strong>
                        {profileReadiness.completed} из {profileReadiness.total}
                      </strong>
                      <Badge tone="warning">Нужны данные</Badge>
                    </div>
                  </section>
                )}

                <nav
                  className={`profile-settings-nav${
                    aiCoachStatus.data?.ui_enabled ? ' profile-settings-nav--ai-enabled' : ''
                  }`}
                  aria-label="Разделы профиля"
                >
                  <a
                    href="#profile-personal"
                    onClick={() => openProfileSection('profile-personal')}
                  >
                    <Icon name="nav-profile" size={16} /> Личные данные
                  </a>
                  <a
                    href="#profile-fitness"
                    onClick={() => openProfileSection('profile-personal', 'profile-fitness')}
                  >
                    <Icon name="nav-plan" size={16} /> Цели и параметры
                  </a>
                  <a href="#profile-trainer" onClick={() => openProfileSection('profile-trainer')}>
                    <Icon name="nav-coach" size={16} /> Тренер и приглашения
                  </a>
                  <a
                    href="#profile-notifications"
                    onClick={() => openProfileSection('profile-notifications')}
                  >
                    <Icon name="nav-today" size={16} /> Уведомления
                  </a>
                  <a
                    href="#profile-security"
                    onClick={() => openProfileSection('profile-security')}
                  >
                    <Icon name="permission-denied" size={16} /> Доступ и безопасность
                  </a>
                  {aiCoachStatus.data?.ui_enabled && (
                    <a
                      href="#profile-ai-coach"
                      onClick={() => openProfileSection('profile-ai-coach')}
                    >
                      <Icon name="star" size={16} /> AI Coach beta
                    </a>
                  )}
                </nav>

                <ProfileForm key={profileFormKey} />
                <Card
                  className="profile-settings-group"
                  defaultOpen={Boolean(inviteToken)}
                  family="neutral"
                  id="profile-trainer"
                  title={
                    <>
                      <Icon name="nav-coach" size={20} /> Тренер и приглашения
                    </>
                  }
                  description="Управляйте текущим тренером или включите собственный режим тренера."
                >
                  <CoachInvites
                    initialToken={inviteToken}
                    onInitialTokenHandled={() => setInviteToken(null)}
                  />
                  <TrainerCapabilityCard />
                </Card>
                {aiCoachStatus.data?.ui_enabled && (
                  <AiCoachSettingsCard
                    defaultOpen={window.location.hash === '#profile-ai-coach'}
                    status={aiCoachStatus.data}
                  />
                )}
                <Card
                  className="profile-settings-group"
                  family="neutral"
                  id="profile-notifications"
                  defaultOpen={window.location.hash === '#profile-notifications'}
                  title={
                    <>
                      <Icon name="nav-today" size={20} /> Уведомления
                    </>
                  }
                  description="Выберите полезные напоминания и время их отправки."
                >
                  <NotificationsPanel
                    onNavigate={(destination) => {
                      setFocusedWorkout(null);
                      navigate(destination);
                    }}
                  />
                </Card>
                <Card
                  className="profile-settings-group profile-settings-group--security"
                  family="neutral"
                  id="profile-security"
                  title={
                    <>
                      <Icon name="permission-denied" size={20} /> Доступ и безопасность
                    </>
                  }
                  description="Способы входа, копия ваших данных и действия с аккаунтом."
                >
                  <AccountPrivacy />
                </Card>
              </div>
            )}
          </Suspense>
        </section>
      </div>
    </AppShell>
  );
}
