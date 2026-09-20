import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AppShell, type DemoAppShellConfig } from '../../app/AppShell';
import '../../styles/react.css';
import '../../styles/design-v2.css';
import '../../features/coach/coach-os.css';
import { useAuth } from '../../app/AuthProvider';
import { Diary } from '../../features/diary/Diary';
import { ClientAnalytics } from '../../features/coach/ClientAnalytics';
import { CoachToday } from '../../features/coach/CoachToday';
import {
  CoachClientOperationsCard,
  CoachOperationsPanel,
} from '../../features/coach/CoachOperationsPanel';
import { CoachClientTimeline } from '../../features/coach/CoachClientTimeline';
import { CoachReportHandoffEntry } from '../../features/coach/CoachReportHandoffEntry';
import { TrainerModeSwitch } from '../../features/trainer/TrainerModeSwitch';
import { ExerciseCatalog } from '../../features/exercises/ExerciseCatalog';
import { NutritionForm } from '../../features/nutrition/NutritionForm';
import { NutritionPeriodReport } from '../../features/workouts/NutritionReport';
import { ProgramBuilder } from '../../features/programs/ProgramBuilder';
import { AssignedProgramDetails } from '../../features/programs/AssignedProgramDetails';
import { api } from '../../shared/api/client';
import type {
  ApiSchemas,
  Client,
  CoachAssignedProgram,
  InviteLink,
  TrainerClientProgressList,
  TrainerClientProgressSummary,
} from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { Icon } from '../../shared/ui/Icon';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import {
  Badge,
  Card,
  DisclosureIcon,
  EmptyState,
  ErrorState,
  LoadingState,
} from '../../shared/ui/common';
import { Redirect } from '../../shared/navigation/router';
import { LIVE_DATA_REFETCH_INTERVAL_MS } from '../../shared/sync';
import { coachClientProfileDraftStorageKey } from '../../shared/userScopedStorage';
import { handleTabKeyDown } from '../../shared/ui/tabs';
import { DateInput } from '../../shared/ui/PickerInput';
import {
  productEventSurface,
  trackGrowthEvent,
  trackProductEvent,
  type CoachQuickActionKind,
} from '../../shared/analytics/productEvents';
import { useTelegramOverlayBackButton } from '../../shared/telegram/useTelegramOverlayBackButton';
import { useRuntime, useRuntimeCapabilities } from '../../shared/runtime/runtime';
import {
  BodyPriorityPicker,
  isBodyPriorityComplete,
} from '../../features/profile/BodyPriorityPicker';
import {
  TrainingPreferencesFields,
  trainingPreferencesDraft,
  trainingPreferencesValidationError,
  useRevisionedDraft,
  type TrainingPreferencesDraft,
} from '../../features/profile/TrainingPreferencesForm';
import {
  activityLabel,
  clientDisplayName,
  filterCoachClients,
  needsCoachAttention,
  type CoachClientFilter,
} from '../../features/coach/coachWorkspace';

type CoachTab = 'today' | 'clients' | 'programs' | 'tools';

async function loadCoachClientSummaries(): Promise<TrainerClientProgressList> {
  const limit = 100;
  const firstPage = await api<TrainerClientProgressList>(
    `/api/v1/coach/client-summaries?period_days=30&limit=${limit}&offset=0`,
  );
  const items = [...firstPage.items];
  while (items.length < firstPage.total) {
    const page = await api<TrainerClientProgressList>(
      `/api/v1/coach/client-summaries?period_days=30&limit=${limit}&offset=${items.length}`,
    );
    if (!page.items.length) break;
    items.push(...page.items);
  }
  return { ...firstPage, items };
}

type ClientProfileDraft = Pick<
  Client,
  | 'full_name'
  | 'birth_date'
  | 'goal'
  | 'level'
  | 'height_cm'
  | 'weight_kg'
  | 'workouts_per_week'
  | 'cardio_trainings_per_week'
  | 'resting_heart_rate'
  | 'body_priority'
> & { training_preferences: TrainingPreferencesDraft };

function clientProfileDraft(client: Client): ClientProfileDraft {
  return {
    full_name: client.full_name,
    birth_date: client.birth_date,
    goal: client.goal,
    level: client.level,
    height_cm: client.height_cm,
    weight_kg: client.weight_kg,
    workouts_per_week: client.workouts_per_week,
    cardio_trainings_per_week: client.cardio_trainings_per_week,
    resting_heart_rate: client.resting_heart_rate,
    body_priority: client.body_priority,
    training_preferences: trainingPreferencesDraft(client.training_preferences),
  };
}

function clientProfileKey(client: Client): string {
  return JSON.stringify([
    client.id,
    client.full_name,
    client.birth_date,
    client.goal,
    client.level,
    client.height_cm,
    client.weight_kg,
    client.workouts_per_week,
    client.cardio_trainings_per_week,
    client.resting_heart_rate,
    client.body_priority,
    client.training_preferences,
  ]);
}

function ClientDataSection({
  id,
  title,
  description,
  children,
  open = false,
}: {
  id?: string;
  title: string;
  description: string;
  children: ReactNode;
  open?: boolean;
}) {
  const [expanded, setExpanded] = useState(open);
  return (
    <details
      className="coach-data-disclosure"
      id={id}
      open={expanded}
      onToggle={(event) => setExpanded(event.currentTarget.open)}
    >
      <summary>
        <span>
          <strong>{title}</strong>
          <small>{description}</small>
        </span>
        <DisclosureIcon />
      </summary>
      {expanded && <div className="coach-data-disclosure__body">{children}</div>}
    </details>
  );
}

function ClientProfileEditor({ client, readOnly = false }: { client: Client; readOnly?: boolean }) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const serverDraft = useMemo(() => clientProfileDraft(client), [client]);
  const [form, setForm, clearDraft] = useRevisionedDraft<ClientProfileDraft>(
    coachClientProfileDraftStorageKey(client.id),
    client.training_preferences?.updated_at ?? null,
    serverDraft,
  );
  const validBirthDate = /^\d{4}-\d{2}-\d{2}$/.test(form.birth_date ?? '');
  const validRestingHeartRate =
    form.resting_heart_rate == null ||
    (form.resting_heart_rate >= 30 && form.resting_heart_rate <= 120);
  const heartRatePreview = useQuery({
    queryKey: [
      'heart-rate-preview',
      form.birth_date,
      form.resting_heart_rate,
      form.goal,
      'coach-client',
      client.id,
    ],
    queryFn: () =>
      api<ApiSchemas['HeartRatePreviewResponse']>('/api/v1/me/profile/heart-rates/preview', {
        method: 'POST',
        body: {
          birth_date: form.birth_date,
          resting_heart_rate: form.resting_heart_rate,
          goal: form.goal || null,
        },
      }),
    enabled: !readOnly && validBirthDate && validRestingHeartRate,
    retry: false,
  });
  const heartRate = heartRatePreview.data;
  const mutation = useMutation({
    mutationFn: () =>
      api<Client>(`/api/v1/coach/clients/${client.id}/profile`, {
        method: 'PATCH',
        body: {
          full_name: form.full_name,
          birth_date: form.birth_date ?? null,
          goal: form.goal || null,
          level: form.level || null,
          height_cm: form.height_cm ?? null,
          weight_kg: form.weight_kg ?? null,
          workouts_per_week: form.workouts_per_week ?? null,
          cardio_trainings_per_week: form.cardio_trainings_per_week ?? null,
          resting_heart_rate: form.resting_heart_rate ?? null,
          body_priority: form.body_priority ?? null,
          training_preferences: form.training_preferences,
        },
      }),
    onSuccess: async (updatedClient) => {
      clearDraft(clientProfileDraft(updatedClient));
      queryClient.setQueryData<Client[]>(queryKeys.trainer.clients, (clients) =>
        clients?.map((item) => (item.id === updatedClient.id ? updatedClient : item)),
      );
      await queryClient.invalidateQueries({ queryKey: queryKeys.trainer.clients });
      toast('Профиль клиента сохранён');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const numberValue = (value: string) => (value === '' ? null : Number(value));
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        if (!isBodyPriorityComplete(form.body_priority)) {
          toast('Выберите хотя бы одну приоритетную мышечную группу', 'error');
          return;
        }
        const trainingError = trainingPreferencesValidationError(form.training_preferences);
        if (trainingError) {
          toast(trainingError, 'error');
          return;
        }
        mutation.mutate();
      }}
    >
      {readOnly && (
        <p className="muted demo-capability-notice" role="status">
          Изменение профиля клиента доступно после входа в рабочий кабинет.
        </p>
      )}
      <fieldset className="demo-capability-fieldset" disabled={readOnly}>
        <div className="form-grid profile-form-grid">
          <label className="field">
            <span>Имя у тренера</span>
            <input
              value={form.full_name || ''}
              maxLength={128}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
            <small className="field-hint">Это имя видите только вы.</small>
          </label>
          <label className="field">
            <span>Дата рождения</span>
            <DateInput
              controlClassName="coach-client-birth-date-control"
              value={form.birth_date ?? ''}
              onChange={(event) => setForm({ ...form, birth_date: event.target.value || null })}
            />
          </label>
          <label className="field">
            <span>Цель</span>
            <select
              value={form.goal || ''}
              required
              onChange={(e) => setForm({ ...form, goal: e.target.value })}
            >
              <option value="" disabled>
                Выберите цель
              </option>
              <option value="fat_loss">Похудение</option>
              <option value="muscle_gain">Набор мышц</option>
              <option value="maintenance">Поддержание</option>
              <option value="recomposition">Рекомпозиция</option>
            </select>
          </label>
          <label className="field">
            <span>Уровень</span>
            <select
              value={form.level || ''}
              required
              onChange={(e) => setForm({ ...form, level: e.target.value })}
            >
              <option value="" disabled>
                Выберите уровень
              </option>
              <option value="beginner">Начальный</option>
              <option value="intermediate">Средний</option>
              <option value="advanced">Продвинутый</option>
            </select>
          </label>
          <label className="field">
            <span>Рост, см</span>
            <input
              type="number"
              min="100"
              max="250"
              value={form.height_cm ?? ''}
              onChange={(e) => setForm({ ...form, height_cm: numberValue(e.target.value) })}
            />
          </label>
          <label className="field">
            <span>Вес, кг</span>
            <input
              type="number"
              min="20"
              max="350"
              step="0.1"
              value={form.weight_kg ?? ''}
              onChange={(e) => setForm({ ...form, weight_kg: numberValue(e.target.value) })}
            />
          </label>
          <label className="field">
            <span>Силовых в неделю</span>
            <input
              type="number"
              min="0"
              max="14"
              value={form.workouts_per_week ?? ''}
              onChange={(e) => setForm({ ...form, workouts_per_week: numberValue(e.target.value) })}
            />
          </label>
          <label className="field">
            <span>Кардио в неделю</span>
            <input
              type="number"
              min="0"
              max="14"
              value={form.cardio_trainings_per_week ?? ''}
              onChange={(e) =>
                setForm({ ...form, cardio_trainings_per_week: numberValue(e.target.value) })
              }
            />
          </label>
          <label className="field">
            <span>Средний пульс в покое, уд/мин</span>
            <input
              type="number"
              min="30"
              max="120"
              step="1"
              value={form.resting_heart_rate ?? ''}
              onChange={(e) =>
                setForm({ ...form, resting_heart_rate: numberValue(e.target.value) })
              }
            />
          </label>
        </div>
        <BodyPriorityPicker
          value={form.body_priority}
          onChange={(body_priority) => setForm({ ...form, body_priority })}
        />
        <ClientDataSection
          title="Тренировочные предпочтения"
          description="Длительность, расписание, места, инвентарь и упражнения"
        >
          <TrainingPreferencesFields
            value={form.training_preferences}
            ownerUserId={client.id}
            onChange={(training_preferences) => setForm({ ...form, training_preferences })}
          />
        </ClientDataSection>
        {heartRate && (
          <div className="auth-notice stack">
            <strong>Пульсовые зоны · максимум {heartRate.estimated_max_heart_rate} уд/мин</strong>
            {heartRate.recommended_cardio_range && (
              <span>
                Рекомендация для кардио: {heartRate.recommended_cardio_range.min_bpm}–
                {heartRate.recommended_cardio_range.max_bpm} уд/мин
              </span>
            )}
            <div className="toolbar wrap">
              {heartRate.heart_rate_zones.map((zone) => (
                <Badge key={zone.zone}>
                  Z{zone.zone}: {zone.min_bpm}–{zone.max_bpm}
                </Badge>
              ))}
            </div>
          </div>
        )}
        <button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? 'Сохраняем…' : 'Сохранить профиль'}
        </button>
      </fieldset>
    </form>
  );
}

function formatCoachDate(value: string | null | undefined): string {
  if (!value) return 'Нет данных';
  return new Date(`${value}T12:00:00`).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
  });
}

function coachGoalLabel(goal: string | null | undefined): string {
  return (
    {
      fat_loss: 'Похудение',
      muscle_gain: 'Набор мышц',
      maintenance: 'Поддержание формы',
      recomposition: 'Рекомпозиция',
    }[goal ?? ''] ?? 'Цель пока не указана'
  );
}

function operationalStatusLabel(status: Client['operational_status']): string {
  return { active: 'В работе', paused: 'Пауза', archived: 'Архив' }[status];
}

function adherenceText(summary?: TrainerClientProgressSummary): string {
  const workouts = summary?.adherence.workouts;
  if (!workouts || workouts.status !== 'available' || workouts.percent == null) {
    return 'Пока мало данных о выполнении плана';
  }
  return `Выполнено ${workouts.achieved} из ${workouts.evaluated} по плану — ${Math.round(workouts.percent)}%`;
}

function CoachZeroState({
  inviteCreating,
  inviteDisabled,
  pendingCount,
  onInvite,
}: {
  inviteCreating: boolean;
  inviteDisabled?: boolean;
  pendingCount: number;
  onInvite: () => void;
}) {
  return (
    <section className="coach-zero-state" aria-labelledby="coach-zero-title">
      <div className="coach-zero-state__copy">
        <span className="eyebrow">Первый рабочий цикл</span>
        <h2 id="coach-zero-title">Добавьте первого клиента</h2>
        <p>
          После подключения здесь появятся программа, ближайшие тренировки, прогресс и разрешённые
          данные питания.
        </p>
        <button disabled={inviteCreating || inviteDisabled} onClick={onInvite} type="button">
          {inviteDisabled
            ? 'Приглашения недоступны в демо'
            : inviteCreating
              ? 'Создаём приглашение…'
              : 'Пригласить первого клиента'}
        </button>
      </div>
      <ol className="coach-onboarding-steps">
        <li className={pendingCount ? 'is-complete' : ''}>
          <span>01</span>
          <div>
            <strong>Отправьте приглашение</strong>
            <small>
              {pendingCount
                ? 'Приглашение ожидает подтверждения'
                : 'Ссылка работает в Web и Telegram'}
            </small>
          </div>
        </li>
        <li>
          <span>02</span>
          <div>
            <strong>Клиент подтвердит связь</strong>
            <small>Доступ появится только после его согласия</small>
          </div>
        </li>
        <li>
          <span>03</span>
          <div>
            <strong>Назначьте программу</strong>
            <small>Используйте общий конструктор программ YFC</small>
          </div>
        </li>
        <li>
          <span>04</span>
          <div>
            <strong>Следите за фактами</strong>
            <small>Тренировки, результаты, замеры и соблюдение плана</small>
          </div>
        </li>
      </ol>
    </section>
  );
}

function CoachInviteCard({
  inviteLink,
  inviteCreating,
  inviteDisabled,
  onCreate,
  onCopy,
}: {
  inviteLink: InviteLink | null;
  inviteCreating: boolean;
  inviteDisabled: boolean;
  onCreate: () => void;
  onCopy: (value: string) => Promise<void>;
}) {
  return (
    <Card
      className={`coach-invite-panel${inviteLink ? ' is-visible' : ''}`}
      collapsible={false}
      title="Пригласить клиента"
      description="Клиент сначала увидит ваше имя и сам подтвердит подключение."
      actions={
        <button disabled={inviteCreating || inviteDisabled} onClick={onCreate} type="button">
          {inviteCreating ? 'Создаём…' : 'Создать приглашение'}
        </button>
      }
    >
      {inviteLink ? (
        <div className="auth-notice stack top-gap">
          {inviteLink.web_url && (
            <label className="field">
              <span>Ссылка для браузера и Telegram</span>
              <input
                readOnly
                value={inviteLink.web_url}
                onFocus={(event) => event.currentTarget.select()}
              />
            </label>
          )}
          {inviteLink.telegram_url && (
            <label className="field">
              <span>Открыть внутри Telegram</span>
              <input
                readOnly
                value={inviteLink.telegram_url}
                onFocus={(event) => event.currentTarget.select()}
              />
            </label>
          )}
          {inviteLink.code && (
            <label className="field">
              <span>Код приглашения</span>
              <input
                readOnly
                value={inviteLink.code}
                onFocus={(event) => event.currentTarget.select()}
              />
            </label>
          )}
          <p className="muted">
            Действует до {new Date(inviteLink.expires_at).toLocaleString('ru-RU')}.
          </p>
          <div className="toolbar wrap">
            <button
              type="button"
              onClick={() =>
                void onCopy(
                  inviteLink.web_url || inviteLink.url || inviteLink.code || inviteLink.start_param,
                )
              }
            >
              Копировать
            </button>
            {inviteLink.web_url && typeof navigator.share === 'function' && (
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  void navigator
                    .share({
                      title: 'Приглашение тренера',
                      text: 'Откройте Your Fitness Coach и подтвердите подключение к тренеру.',
                      url: inviteLink.web_url!,
                    })
                    .catch(() => undefined)
                }
              >
                Поделиться
              </button>
            )}
          </div>
        </div>
      ) : (
        <p className="muted">
          Новая персональная ссылка появится здесь. До подтверждения клиента доступ к данным не
          открывается.
        </p>
      )}
    </Card>
  );
}

function ClientSummaryFacts({ summary }: { summary?: TrainerClientProgressSummary }) {
  if (!summary) {
    return <p className="muted">Сводка ещё загружается или данных за период пока нет.</p>;
  }
  const workoutAdherence = summary.adherence.workouts;
  const latestMeasurement = summary.body.latest_measurement;
  const customMeasurement = latestMeasurement?.custom_measurements?.find(
    (measurement) => !measurement.archived,
  );
  return (
    <div className="coach-client-facts">
      <div>
        <span>Последняя тренировка</span>
        <strong>{formatCoachDate(summary.training.last_completed_workout_on)}</strong>
        <small>{activityLabel(summary.training.last_completed_workout_on)}</small>
      </div>
      <div>
        <span>Выполнение плана</span>
        <strong>
          {workoutAdherence.status === 'available' && workoutAdherence.percent != null
            ? `${Math.round(workoutAdherence.percent)}%`
            : 'Недостаточно данных'}
        </strong>
        <small>
          {workoutAdherence.status === 'available'
            ? `${workoutAdherence.achieved} из ${workoutAdherence.evaluated} тренировок`
            : 'Появится после выполненных тренировок'}
        </small>
      </div>
      <div>
        <span>Новые результаты</span>
        <strong>{summary.training.new_personal_records}</strong>
        <small>личных рекордов за 30 дней</small>
      </div>
      <div>
        <span>Последний замер</span>
        <strong>{formatCoachDate(latestMeasurement?.measured_on)}</strong>
        <small>
          {latestMeasurement?.weight_kg != null
            ? `${latestMeasurement.weight_kg} кг`
            : 'Вес не указан'}
          {customMeasurement
            ? ` · ${customMeasurement.label}: ${customMeasurement.value} ${customMeasurement.unit}`
            : ''}
        </small>
      </div>
    </div>
  );
}

function ProgramAssignmentDisclosure({ client }: { client: Client }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <details
      className="coach-program-assignment"
      open={expanded}
      onToggle={(event) => setExpanded(event.currentTarget.open)}
    >
      <summary>
        <span>
          <strong>Назначить новую программу</strong>
          <small>Открыть общий конструктор программ для этого клиента</small>
        </span>
        <DisclosureIcon />
      </summary>
      {expanded && (
        <div className="coach-program-assignment__body">
          <ProgramBuilder
            targetTelegramId={client.telegram_user_id}
            targetName={client.full_name || client.username}
          />
        </div>
      )}
    </details>
  );
}

function CoachClientDetail({
  client,
  focusedAttention,
  focusedProgramId,
  focusedWorkoutId,
  onBack,
  onOpenCatalog,
  onFocusWorkout,
  onFocusCheckIn,
  onQuickAction,
  programs,
  summary,
}: {
  client: Client;
  focusedAttention: 'weekly_check_in' | null;
  focusedProgramId: number | null;
  focusedWorkoutId: number | null;
  onBack: () => void;
  onOpenCatalog: () => void;
  onFocusWorkout: (workoutId: number) => void;
  onFocusCheckIn: () => void;
  onQuickAction: (kind: CoachQuickActionKind) => void;
  programs: CoachAssignedProgram[];
  summary?: TrainerClientProgressSummary;
}) {
  const capabilities = useRuntimeCapabilities();
  const [timelineRequest, setTimelineRequest] = useState<number | null>(null);
  const [programRequest, setProgramRequest] = useState<number | null>(null);
  const [progressRequest, setProgressRequest] = useState<number | null>(null);
  const [reportRequest, setReportRequest] = useState<number | null>(null);
  if (client.id == null) return null;
  const activeProgram = programs.find((program) => program.is_active);
  return (
    <article className="coach-client-detail" aria-labelledby="coach-client-detail-title">
      <header className="coach-client-detail__header">
        <button className="coach-client-detail__back secondary" onClick={onBack} type="button">
          К списку клиентов
        </button>
        <div className="coach-client-detail__identity">
          <span className="eyebrow">Сейчас открыт клиент</span>
          <h2 id="coach-client-detail-title">{clientDisplayName(client)}</h2>
          <p>
            {client.username ? `@${client.username} · ` : ''}
            Цель: {coachGoalLabel(client.goal)} · Операционный статус:{' '}
            <strong>{operationalStatusLabel(client.operational_status)}</strong>
          </p>
        </div>
        <nav className="coach-client-quick-actions" aria-label="Данные клиента">
          <a
            href="#coach-client-timeline"
            onClick={() => {
              onQuickAction('review_workout');
              setTimelineRequest(Date.now());
            }}
          >
            Последние события
          </a>
          <a
            href="#coach-client-program"
            onClick={() => {
              onQuickAction('assign_program');
              setProgramRequest(Date.now());
            }}
          >
            Программа
          </a>
          <a
            href="#coach-client-progress"
            onClick={() => {
              onQuickAction('progress');
              setProgressRequest(Date.now());
            }}
          >
            Прогресс
          </a>
          <a
            href="#coach-client-nutrition"
            onClick={() => {
              onQuickAction('nutrition');
            }}
          >
            Питание
          </a>
          <a
            href="#coach-client-profile"
            onClick={() => {
              onQuickAction('profile');
            }}
          >
            Профиль
          </a>
          <a
            href="#coach-client-report"
            onClick={() => {
              onQuickAction('report');
              setReportRequest(Date.now());
            }}
          >
            Отчёт
          </a>
        </nav>
      </header>

      <ClientSummaryFacts summary={summary} />

      <section className="coach-client-overview" aria-label="Контекст клиента">
        <div>
          <span className="eyebrow">Текущий контекст</span>
          <strong>{activeProgram?.title ?? 'Активной программы нет'}</strong>
          <small>
            {summary?.training.next_workout
              ? `Следующая тренировка · ${formatCoachDate(summary.training.next_workout.scheduled_date)} · ${summary.training.next_workout.title}`
              : 'Следующая тренировка не запланирована'}
          </small>
        </div>
        <div>
          <span className="eyebrow">Состояние</span>
          <strong>
            {needsCoachAttention(summary) ? 'Нужна проверка' : 'Недавняя активность есть'}
          </strong>
          <small>{activityLabel(summary?.training.last_completed_workout_on)}</small>
        </div>
      </section>

      <CoachClientOperationsCard
        clientId={client.id}
        operationalStatus={client.operational_status}
      />

      <ClientDataSection
        id="coach-client-timeline"
        key={`timeline-${client.id}-${timelineRequest ?? 'closed'}`}
        title="Лента активности"
        description="Тренировки, недельные итоги и замеры в одной хронологии"
        open={timelineRequest != null}
      >
        <CoachClientTimeline
          clientId={client.id}
          enabled
          onOpenWorkout={onFocusWorkout}
          onOpenCheckIn={onFocusCheckIn}
          onOpenProgress={() => {
            onQuickAction('progress');
            setProgressRequest(Date.now());
          }}
        />
      </ClientDataSection>

      <ClientDataSection
        id="coach-client-program"
        key={`program-${client.id}-${focusedProgramId ?? 'none'}-${programRequest ?? 'closed'}`}
        title="Программа тренировок"
        description="Текущий план, ближайшая тренировка и новое назначение"
        open={Boolean(focusedProgramId || programRequest)}
      >
        <div className="coach-client-programs">
          <div className="coach-client-programs__head">
            <div>
              <strong>{activeProgram ? 'Активная программа' : 'Программа не назначена'}</strong>
              <span>
                {summary?.training.next_workout
                  ? `Следующая тренировка ${formatCoachDate(summary.training.next_workout.scheduled_date)} — ${summary.training.next_workout.title}`
                  : 'Ближайшая тренировка пока не запланирована'}
              </span>
            </div>
            {activeProgram && (
              <button
                type="button"
                className="secondary"
                disabled={!capabilities.canMutatePrograms}
                onClick={onOpenCatalog}
              >
                Добавить упражнение
              </button>
            )}
          </div>
          {!programs.length ? (
            <EmptyState
              title="У клиента ещё нет назначенной программы"
              text="Создайте и назначьте её в общем конструкторе ниже."
            />
          ) : (
            programs.map((program) => (
              <article
                className={`coach-client-program${program.id === focusedProgramId ? ' is-focused' : ''}`}
                key={program.id}
              >
                <div>
                  <span className="eyebrow">
                    {program.is_active ? 'Текущая программа клиента' : 'Архив клиента'}
                  </span>
                  <strong>{program.title}</strong>
                  <small>
                    Выполнено {program.workouts_completed} из {program.workouts_total} тренировок
                  </small>
                </div>
                <Badge tone={program.is_active ? 'success' : 'neutral'}>
                  {program.is_active ? 'Активна' : 'Архив'}
                </Badge>
                {program.is_active && (
                  <>
                    {!capabilities.canMutatePrograms && (
                      <p className="muted demo-capability-notice" role="status">
                        Изменение этапов программы доступно после входа в рабочий кабинет.
                      </p>
                    )}
                    <fieldset
                      className="demo-capability-fieldset"
                      disabled={!capabilities.canMutatePrograms}
                    >
                      <AssignedProgramDetails
                        programId={program.id}
                        currentRevisionNumber={program.current_revision_number}
                        startDate={program.start_date}
                        durationWeeks={program.duration_weeks}
                      />
                    </fieldset>
                  </>
                )}
              </article>
            ))
          )}
        </div>
        {capabilities.canMutatePrograms ? (
          <ProgramAssignmentDisclosure key={`program-${client.id}`} client={client} />
        ) : (
          <p className="muted">Изменение программ доступно в рабочем кабинете.</p>
        )}
      </ClientDataSection>

      <ClientDataSection
        id="coach-client-progress"
        key={`progress-${client.id}-${focusedAttention ?? 'none'}-${focusedWorkoutId ?? 'none'}-${progressRequest ?? 'closed'}`}
        title="Тренировки, прогресс и замеры"
        description={adherenceText(summary)}
        open={Boolean(focusedAttention || focusedProgramId || focusedWorkoutId || progressRequest)}
      >
        <ClientAnalytics
          clientId={client.id}
          clientName={clientDisplayName(client)}
          canComment={client.status === 'active'}
          canSchedule={capabilities.canManageCoach}
          focusedCheckIn={focusedAttention === 'weekly_check_in'}
          focusedWorkoutId={focusedWorkoutId}
        />
        <Diary
          key={`diary-${client.id}`}
          clientId={client.id}
          readOnly={!capabilities.canMutateProgress}
          timeZone={client.timezone}
        />
      </ClientDataSection>

      <ClientDataSection
        id="coach-client-report"
        key={`report-${client.id}-${reportRequest ?? 'closed'}`}
        title="Расширенный отчёт"
        description="Канонический report и комментарий клиента"
        open={reportRequest != null}
      >
        <CoachReportHandoffEntry clientId={client.id} enabled />
      </ClientDataSection>

      <ClientDataSection
        id="coach-client-nutrition"
        title="Питание"
        description={
          summary?.nutrition.visible
            ? `${summary.nutrition.logged_days} учтённых дней питания за период`
            : 'Агрегаты питания не доступны'
        }
      >
        {summary && !summary.nutrition.visible ? (
          <EmptyState
            title="Нет доступа к сводке питания"
            text="Раздел не показывает дневник или состав приёмов пищи без разрешённого доступа."
          />
        ) : (
          <>
            {client.status === 'active' && (
              <NutritionPeriodReport
                canExport={capabilities.canExport}
                key={`nutrition-report-${client.id}`}
                clientId={client.id}
              />
            )}
            <NutritionForm
              key={JSON.stringify([client.id, client.kbju])}
              clientId={client.id}
              targetTelegramId={client.telegram_user_id}
              initial={client.kbju}
              timeZone={client.timezone}
              readOnly={!capabilities.canMutateProfile}
            />
          </>
        )}
      </ClientDataSection>

      <ClientDataSection
        id="coach-client-profile"
        title="Профиль клиента"
        description="Анкета, цель и параметры"
      >
        <ClientProfileEditor
          key={clientProfileKey(client)}
          client={client}
          readOnly={!capabilities.canMutateProfile}
        />
      </ClientDataSection>
    </article>
  );
}

export default function CoachPage({
  demo,
  renderShell = true,
}: {
  demo?: DemoAppShellConfig;
  renderShell?: boolean;
} = {}) {
  const { user } = useAuth();
  const runtime = useRuntime();
  const capabilities = useRuntimeCapabilities();
  const { toast, confirm } = useFeedback();
  const queryClient = useQueryClient();
  const initialClientId = (() => {
    const value = new URLSearchParams(window.location.search).get('client_id');
    if (!value || !/^\d+$/.test(value)) return null;
    const clientId = Number(value);
    return Number.isSafeInteger(clientId) && clientId > 0 ? clientId : null;
  })();
  const [tab, setTab] = useState<CoachTab>(initialClientId ? 'clients' : 'today');
  const initialWorkoutId = (() => {
    const value = new URLSearchParams(window.location.search).get('workout_id');
    if (!value || !/^\d+$/.test(value)) return null;
    const workoutId = Number(value);
    return Number.isSafeInteger(workoutId) && workoutId > 0 ? workoutId : null;
  })();
  const initialAttentionFocus =
    new URLSearchParams(window.location.search).get('focus') === 'weekly_check_in'
      ? ('weekly_check_in' as const)
      : null;
  const [selectedId, setSelectedId] = useState<number | null>(initialClientId);
  const [clientDetailOpen, setClientDetailOpen] = useState(Boolean(initialClientId));
  const usefulActionStartedAt = useRef<number | null>(null);
  const usefulActionTracked = useRef(false);
  useTelegramOverlayBackButton(clientDetailOpen, () => setClientDetailOpen(false));

  const markDemoStep = useCallback(
    (step: 'attention' | 'client' | 'workout' | 'progress' | 'task' | 'return') => {
      if (runtime.kind !== 'demo') return;
      runtime.onNavigate?.(`/coach?demo_step=${step}`);
    },
    [runtime],
  );

  useEffect(() => {
    usefulActionStartedAt.current = performance.now();
  }, []);

  useEffect(() => {
    if (user?.is_coach) {
      trackProductEvent(
        { name: 'trainer_workspace_viewed', surface: productEventSurface() },
        { dedupe: 'session' },
      );
      trackProductEvent(
        { name: 'coach_home_viewed', surface: productEventSurface() },
        { dedupe: 'session' },
      );
    }
  }, [user?.is_coach]);
  const [clientSearch, setClientSearch] = useState('');
  const [clientFilter, setClientFilter] = useState<CoachClientFilter>('all');
  const [programSearch, setProgramSearch] = useState('');
  const [focusedProgramId, setFocusedProgramId] = useState<number | null>(null);
  const [focusedWorkoutId, setFocusedWorkoutId] = useState<number | null>(initialWorkoutId);
  const [focusedAttention, setFocusedAttention] = useState<'weekly_check_in' | null>(
    initialAttentionFocus,
  );
  const [inviteLink, setInviteLink] = useState<InviteLink | null>(null);
  const [inviteCreating, setInviteCreating] = useState(false);

  const trackCoachUsefulAction = () => {
    if (usefulActionTracked.current) return;
    usefulActionTracked.current = true;
    const elapsed = performance.now() - (usefulActionStartedAt.current ?? performance.now());
    const latency_bucket =
      elapsed < 10_000
        ? ('under_10s' as const)
        : elapsed < 30_000
          ? ('10_30s' as const)
          : elapsed < 60_000
            ? ('30_60s' as const)
            : ('over_60s' as const);
    trackProductEvent({
      name: 'coach_time_to_first_useful_action',
      surface: productEventSurface(),
      latency_bucket,
    });
  };

  const trackCoachQuickAction = (kind: CoachQuickActionKind) => {
    trackCoachUsefulAction();
    if (kind === 'review_workout') markDemoStep('workout');
    if (kind === 'progress') markDemoStep('progress');
    trackProductEvent({
      name: 'coach_quick_action_used',
      surface: productEventSurface(),
      kind,
    });
  };
  const clients = useQuery({
    queryKey: queryKeys.trainer.clients,
    queryFn: () => api<Client[]>('/api/v1/coach/clients'),
    refetchInterval: LIVE_DATA_REFETCH_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
  const programs = useQuery({
    queryKey: ['coach', 'programs'],
    queryFn: () => api<CoachAssignedProgram[]>('/api/v1/coach/assigned-programs'),
    enabled: true,
    refetchInterval: tab === 'programs' ? LIVE_DATA_REFETCH_INTERVAL_MS : false,
    refetchOnWindowFocus: true,
  });
  const clientSummaries = useQuery({
    queryKey: queryKeys.trainer.clientSummaries,
    queryFn: loadCoachClientSummaries,
    enabled: Boolean(clients.data?.some((client) => client.status === 'active')),
    refetchInterval: tab === 'clients' ? LIVE_DATA_REFETCH_INTERVAL_MS : false,
    refetchOnWindowFocus: true,
  });
  const summaryMap = useMemo(
    () =>
      new Map(
        (clientSummaries.data?.items ?? []).map((summary) => [summary.user_id, summary] as const),
      ),
    [clientSummaries.data?.items],
  );
  const selected =
    (selectedId == null ? null : clients.data?.find((item) => item.id === selectedId)) ??
    clients.data?.find((item) => item.status === 'active') ??
    null;
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body?: unknown }) =>
      api(path, { method, body }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['coach'] });
      setSelectedId(null);
      setClientDetailOpen(false);
      toast('Данные тренера обновлены');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const filteredPrograms = useMemo(() => {
    const q = programSearch.toLowerCase();
    return (programs.data ?? []).filter(
      (item) =>
        !q ||
        `${item.title} ${item.client_full_name} ${item.client_username}`.toLowerCase().includes(q),
    );
  }, [programs.data, programSearch]);
  const selectedPrograms = useMemo(
    () => (programs.data ?? []).filter((item) => item.client_id === selected?.id),
    [programs.data, selected?.id],
  );
  const activeClients = useMemo(
    () => (clients.data ?? []).filter((client) => client.status === 'active'),
    [clients.data],
  );
  useEffect(() => {
    if (runtime.kind === 'demo' || !user?.is_coach || activeClients.length === 0) return;
    trackProductEvent(
      { name: 'trainer_first_client_connected', surface: productEventSurface() },
      { dedupe: 'session' },
    );
  }, [activeClients.length, runtime.kind, user?.is_coach]);
  const pendingCount = (clients.data ?? []).filter((client) => client.status === 'pending').length;
  const filteredClients = useMemo(
    () =>
      filterCoachClients({
        clients: clients.data ?? [],
        filter: clientFilter,
        programs: programs.data ?? [],
        search: clientSearch,
        summaries: summaryMap,
      }),
    [clientFilter, clientSearch, clients.data, programs.data, summaryMap],
  );
  const selectedSummary = selected?.id ? summaryMap.get(selected.id) : undefined;
  if (!user?.is_coach) return <Redirect to="/app" />;
  const copyInvite = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast('Приглашение скопировано');
    } catch {
      toast('Не удалось скопировать автоматически — выделите значение вручную.', 'error');
    }
  };
  const createInvite = async () => {
    if (!capabilities.canManageCoach) {
      toast('Приглашения доступны только в рабочем кабинете.', 'error');
      return;
    }
    const firstInvite = (clients.data ?? []).length === 0;
    setInviteCreating(true);
    try {
      const result = await api<InviteLink>('/api/v1/coach/invite-links', {
        method: 'POST',
      });
      setInviteLink(result);
      trackGrowthEvent('client_invited');
      if (firstInvite) {
        trackProductEvent(
          { name: 'trainer_first_invite_created', surface: productEventSurface() },
          { dedupe: 'session' },
        );
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.trainer.clients });
      if (result.web_url || result.url) await copyInvite(result.web_url || result.url || '');
      else toast('Приглашение создано');
    } catch (reason) {
      toast((reason as Error).message, 'error');
    } finally {
      setInviteCreating(false);
    }
  };

  const navigateCoach = (destination: CoachTab, filter?: CoachClientFilter) => {
    if (
      destination === 'today' ||
      destination === 'clients' ||
      destination === 'programs' ||
      destination === 'tools'
    ) {
      trackProductEvent({
        name: 'coach_navigation_selected',
        surface: productEventSurface(),
        destination,
      });
    }
    if (destination === 'today') markDemoStep('return');
    if (filter) setClientFilter(filter);
    setTab(destination);
    if (destination !== 'clients') setClientDetailOpen(false);
  };

  const openClient = (clientId: number) => {
    trackCoachUsefulAction();
    markDemoStep('client');
    trackProductEvent({
      name: 'trainer_client_opened',
      surface: productEventSurface(),
    });
    trackProductEvent({
      name: 'coach_client_opened',
      surface: productEventSurface(),
    });
    setSelectedId(clientId);
    setFocusedProgramId(null);
    setFocusedWorkoutId(null);
    setFocusedAttention(null);
    setClientDetailOpen(true);
    setTab('clients');
  };

  const content = (
    <div
      className={`page-stack app-section app-section--programs app-section--design-v2 coach-workspace--design-v2 coach-os${clientDetailOpen ? ' is-client-detail-open' : ''}`}
    >
      <TrainerModeSwitch
        mode="clients"
        clientName={clientDetailOpen && selected ? clientDisplayName(selected) : undefined}
      />
      <header className="coach-os-header">
        <div>
          <span className="eyebrow">Тренер · рабочее пространство</span>
          <h1>{tab === 'today' ? 'Сегодня' : 'Кабинет тренера'}</h1>
          <p>Сначала действие, затем детали клиента — без потери глубины YFC.</p>
        </div>
        <div className="coach-os-header__actions">
          <button
            disabled={inviteCreating || !capabilities.canManageCoach}
            onClick={() => void createInvite()}
            type="button"
          >
            {inviteCreating ? 'Создаём…' : 'Пригласить клиента'}
          </button>
        </div>
      </header>
      <nav className="coach-os-nav" aria-label="Разделы тренера">
        {(
          [
            ['today', 'Сегодня'],
            ['clients', 'Клиенты'],
            ['programs', 'Программы'],
            ['tools', 'Ещё · инструменты'],
          ] as const
        ).map(([key, label]) => (
          <button
            type="button"
            aria-current={tab === key ? 'page' : undefined}
            className={tab === key ? 'is-active' : 'secondary'}
            aria-label={key === 'tools' ? label : undefined}
            onClick={() => navigateCoach(key)}
            onKeyDown={handleTabKeyDown}
            key={key}
          >
            <span className="coach-os-nav__label coach-os-nav__label--desktop">{label}</span>
            <span
              className="coach-os-nav__label coach-os-nav__label--mobile"
              aria-hidden={key === 'tools' ? true : undefined}
            >
              {key === 'tools' ? 'Ещё' : label}
            </span>
          </button>
        ))}
      </nav>
      <section
        className="page-stack"
        aria-label={
          tab === 'today'
            ? 'Сегодня'
            : tab === 'clients'
              ? 'Клиенты'
              : tab === 'programs'
                ? 'Программы'
                : 'Инструменты'
        }
      >
        {tab === 'today' && (
          <>
            <CoachOperationsPanel
              clients={activeClients}
              onDemoStep={markDemoStep}
              onOpenClient={openClient}
              timezone={user.profile?.timezone}
            />
            <CoachToday
              clients={clients.data ?? []}
              programs={programs.data ?? []}
              summaries={clientSummaries.data?.items ?? []}
              clientsLoading={clients.isLoading}
              programsLoading={programs.isPending}
              summariesLoading={clientSummaries.isPending}
              pendingCount={pendingCount}
              inviteCreating={inviteCreating}
              inviteDisabled={!capabilities.canManageCoach}
              onNavigate={(destination, filter) => navigateCoach(destination, filter)}
              onOpenClient={openClient}
              onInvite={() => void createInvite()}
              onAttentionAction={() => markDemoStep('attention')}
            />
          </>
        )}
        {tab === 'clients' && (
          <>
            {clientSummaries.error && activeClients.length > 0 && (
              <div className="coach-summary-warning" role="status">
                Краткие показатели временно недоступны. Список клиентов и подробные разделы
                продолжают работать.
                <button className="secondary" onClick={() => void clientSummaries.refetch()}>
                  Повторить
                </button>
              </div>
            )}
            {!clients.isLoading && activeClients.length === 0 && (
              <CoachZeroState
                inviteCreating={inviteCreating}
                inviteDisabled={!capabilities.canManageCoach}
                pendingCount={pendingCount}
                onInvite={() => void createInvite()}
              />
            )}
            <div className={`coach-client-workspace${clientDetailOpen ? ' is-client-open' : ''}`}>
              <Card className="coach-client-roster" title="Клиенты" collapsible={false}>
                <div className="coach-client-tools">
                  <label className="field">
                    <span>Найти клиента</span>
                    <input
                      type="search"
                      placeholder="Имя или username"
                      value={clientSearch}
                      onChange={(event) => setClientSearch(event.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>Показать</span>
                    <select
                      value={clientFilter}
                      onChange={(event) => setClientFilter(event.target.value as CoachClientFilter)}
                    >
                      <option value="all">Все</option>
                      <option value="attention">Нет тренировок 7+ дней</option>
                      <option value="recent">Тренировались за 7 дней</option>
                      <option value="without_program">Без активной программы</option>
                      <option value="pending">Ожидают подключения</option>
                    </select>
                  </label>
                </div>
                {clients.isLoading ? (
                  <LoadingState />
                ) : clients.error ? (
                  <ErrorState message={(clients.error as Error).message} />
                ) : !clients.data?.length ? (
                  <EmptyState
                    title="Клиентов пока нет"
                    text="Создайте приглашение, чтобы начать работу."
                  />
                ) : !filteredClients.length ? (
                  <EmptyState
                    title="Клиенты не найдены"
                    text="Измените запрос или выберите другой фильтр."
                  />
                ) : (
                  <div className="coach-client-list">
                    {filteredClients.map((client) => {
                      const summary = client.id ? summaryMap.get(client.id) : undefined;
                      const activeProgram = (programs.data ?? []).find(
                        (program) => program.client_id === client.id && program.is_active,
                      );
                      return (
                        <article
                          className={`coach-client-row${selected?.id === client.id ? ' selected' : ''}`}
                          key={client.id || `invite-${client.invite_id}`}
                        >
                          <button
                            className="coach-client-row__main text-button"
                            disabled={!client.id}
                            onClick={() => {
                              if (!client.id) return;
                              openClient(client.id);
                            }}
                          >
                            <span className="coach-client-row__identity">
                              <strong>{clientDisplayName(client)}</strong>
                              <small>
                                {client.status === 'pending'
                                  ? 'Ожидает подтверждения'
                                  : activeProgram?.title || 'Нет активной программы'}
                              </small>
                            </span>
                            {client.status === 'active' ? (
                              <span className="coach-client-row__signals">
                                <span
                                  className={needsCoachAttention(summary) ? 'is-attention' : ''}
                                >
                                  {activityLabel(summary?.training.last_completed_workout_on)}
                                </span>
                                <small>{adherenceText(summary)}</small>
                              </span>
                            ) : (
                              <Badge tone="warning">Ожидает</Badge>
                            )}
                          </button>
                          <details className="coach-client-row__menu">
                            <summary aria-label={`Действия: ${clientDisplayName(client)}`}>
                              <Icon name="more-horizontal" size={20} />
                            </summary>
                            <button
                              className="btn-danger"
                              disabled={!capabilities.canManageCoach}
                              onClick={async () => {
                                if (
                                  await confirm({
                                    title:
                                      client.status === 'pending'
                                        ? 'Отозвать приглашение?'
                                        : 'Завершить работу с клиентом?',
                                    message: clientDisplayName(client),
                                    confirmText:
                                      client.status === 'pending' ? 'Отозвать' : 'Завершить',
                                  })
                                )
                                  mutation.mutate({
                                    path: client.id
                                      ? `/api/v1/coach/clients/${client.id}`
                                      : `/api/v1/coach/client-invites/id/${client.invite_id}`,
                                    method: 'DELETE',
                                  });
                              }}
                            >
                              {client.status === 'pending'
                                ? 'Отозвать приглашение'
                                : 'Завершить работу'}
                            </button>
                          </details>
                        </article>
                      );
                    })}
                  </div>
                )}
              </Card>
              {selected?.id && selected.status === 'active' && (
                <CoachClientDetail
                  key={selected.id}
                  client={selected}
                  focusedAttention={focusedAttention}
                  focusedProgramId={focusedProgramId}
                  focusedWorkoutId={focusedWorkoutId}
                  onBack={() => setClientDetailOpen(false)}
                  onOpenCatalog={() => navigateCoach('tools')}
                  onFocusWorkout={(workoutId) => {
                    trackCoachQuickAction('review_workout');
                    setFocusedWorkoutId(workoutId);
                    setFocusedAttention(null);
                  }}
                  onFocusCheckIn={() => {
                    trackCoachQuickAction('review_check_in');
                    setFocusedAttention('weekly_check_in');
                    setFocusedWorkoutId(null);
                  }}
                  onQuickAction={trackCoachQuickAction}
                  programs={selectedPrograms}
                  summary={selectedSummary}
                />
              )}
            </div>
          </>
        )}
        {tab === 'programs' && (
          <Card className="coach-programs-card" title="Программы клиентов">
            <label className="coach-programs-search">
              <span className="sr-only">Поиск по клиенту или программе</span>
              <Icon className="coach-programs-search__icon" name="search" size={20} />
              <input
                aria-label="Поиск по клиенту или программе"
                placeholder="Поиск по клиенту или программе"
                type="search"
                value={programSearch}
                onChange={(e) => setProgramSearch(e.target.value)}
              />
            </label>
            {programs.isLoading ? (
              <LoadingState />
            ) : programs.error ? (
              <ErrorState message={(programs.error as Error).message} />
            ) : !filteredPrograms.length ? (
              <EmptyState title="Назначений не найдено" />
            ) : (
              <div className="list-grid">
                {filteredPrograms.map((item) => (
                  <article className="coach-program-row" key={item.id}>
                    <div className="coach-program-row__main">
                      <span className="eyebrow">Программа клиента</span>
                      <strong>{item.title}</strong>
                      <p>{item.client_full_name || item.client_username || 'Клиент'}</p>
                      <small>
                        Назначена {new Date(item.assigned_at).toLocaleDateString('ru-RU')}
                        {item.next_workout_date
                          ? ` · следующая ${new Date(`${item.next_workout_date}T12:00:00`).toLocaleDateString('ru-RU')}`
                          : ''}
                      </small>
                    </div>
                    <div className="coach-program-row__progress">
                      <Badge tone={item.is_active ? 'success' : 'neutral'}>
                        {item.is_active ? 'Активна' : 'Архив'}
                      </Badge>
                      <strong>
                        {item.workouts_completed} / {item.workouts_total}
                      </strong>
                      <span>тренировок выполнено</span>
                    </div>
                    <div className="coach-program-row__actions">
                      <button
                        type="button"
                        onClick={() => {
                          openClient(item.client_id);
                          setFocusedProgramId(item.id);
                        }}
                      >
                        Открыть клиента
                      </button>
                      {item.is_active && (
                        <button
                          type="button"
                          className="secondary"
                          disabled={!capabilities.canMutatePrograms || !capabilities.canManageCoach}
                          onClick={() => {
                            setSelectedId(item.client_id);
                            setFocusedWorkoutId(null);
                            setFocusedAttention(null);
                            setClientDetailOpen(true);
                            navigateCoach('tools');
                          }}
                        >
                          Добавить упражнение
                        </button>
                      )}
                    </div>
                    {item.is_active && (
                      <>
                        {!capabilities.canMutatePrograms && (
                          <p className="muted demo-capability-notice" role="status">
                            Изменение этапов программы доступно после входа в рабочий кабинет.
                          </p>
                        )}
                        <fieldset
                          className="demo-capability-fieldset"
                          disabled={!capabilities.canMutatePrograms}
                        >
                          <AssignedProgramDetails
                            programId={item.id}
                            currentRevisionNumber={item.current_revision_number}
                            startDate={item.start_date}
                            durationWeeks={item.duration_weeks}
                          />
                        </fieldset>
                      </>
                    )}
                  </article>
                ))}
              </div>
            )}
          </Card>
        )}
        {tab === 'tools' && (
          <>
            <CoachInviteCard
              inviteLink={inviteLink}
              inviteCreating={inviteCreating}
              inviteDisabled={!capabilities.canManageCoach}
              onCreate={() => void createInvite()}
              onCopy={copyInvite}
            />
            <ExerciseCatalog
              canCreate={capabilities.canCreateCatalog}
              canAssign={capabilities.canMutatePrograms && capabilities.canManageCoach}
              targetTelegramId={selected?.telegram_user_id}
            />
          </>
        )}
      </section>
    </div>
  );
  return renderShell ? <AppShell demo={demo}>{content}</AppShell> : content;
}
