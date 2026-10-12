import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { api } from '../../shared/api/client';
import type {
  NotificationItem,
  NotificationSetting,
  ReminderTemplate,
  ReminderTemplateUpdate,
} from '../../shared/api/types';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { addCalendarDays, dateInputValue, detectedTimeZone } from '../../shared/dateTime';
import { usePersistentState } from '../../shared/storage';
import { notificationDraftStorageKey } from '../../shared/userScopedStorage';
import { DisclosureIcon, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { DateInput, TimeInput } from '../../shared/ui/PickerInput';
import { WebPushSettings } from './WebPushSettings';

interface NotificationOpenResponse {
  destination: string;
  stale: boolean;
  message?: string | null;
}

const categoryLabels: Record<string, string> = {
  workout_reminder: 'Тренировка',
  trainer_comment: 'Комментарий тренера',
  trainer_program_update: 'Программа',
  weekly_check_in_reminder: 'Итоги недели',
  measurement_reminder: 'Замеры',
  relationship_event: 'Связь с тренером',
  nutrition_update: 'Питание',
  workout_change: 'Расписание',
  report_handoff: 'Отчёт тренеру',
  custom_reminder: 'Личное напоминание',
  meal_logging_reminder: 'Приём пищи',
  hydration_reminder: 'Гидратация',
  movement_break_reminder: 'Перерыв на движение',
};

const navigableCategories = new Set([
  'workout_reminder',
  'trainer_comment',
  'trainer_program_update',
  'weekly_check_in_reminder',
  'measurement_reminder',
  'relationship_event',
  'nutrition_update',
  'workout_change',
  'report_handoff',
  'meal_logging_reminder',
  'hydration_reminder',
  'movement_break_reminder',
]);

const weekdayLabels = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

type ReminderTemplateKey = ReminderTemplate['template_key'];

function formatTemplateWeekdays(weekdays: number[]): string {
  const sorted = [...weekdays].sort((left, right) => left - right);
  if (sorted.length === weekdayLabels.length) return 'Пн–Вс';
  return sorted.map((weekday) => weekdayLabels[weekday] ?? `День ${weekday + 1}`).join(', ');
}

function templateScheduleSummary(template: ReminderTemplate): string {
  const days = formatTemplateWeekdays(template.weekdays);
  if (template.schedule_kind === 'times') {
    return `${days} · ${template.times.map((value) => timeValue(value, '00:00')).join(', ')}`;
  }
  return `${days} · ${timeValue(template.window_start, '09:00')}–${timeValue(
    template.window_end,
    '21:00',
  )} · каждые ${template.interval_minutes ?? 120} мин`;
}

function templateUpdatePayload(template: ReminderTemplate): ReminderTemplateUpdate {
  return {
    enabled: template.enabled,
    weekdays: template.weekdays,
    times: template.schedule_kind === 'times' ? template.times : [],
    window_start:
      template.schedule_kind === 'interval' ? timeValue(template.window_start, '09:00') : null,
    window_end:
      template.schedule_kind === 'interval' ? timeValue(template.window_end, '21:00') : null,
    interval_minutes: template.schedule_kind === 'interval' ? template.interval_minutes : null,
    max_per_day: template.schedule_kind === 'times' ? template.times.length : template.max_per_day,
    minimum_spacing_minutes: template.minimum_spacing_minutes,
  };
}

interface ReminderTemplateCardProps {
  template: ReminderTemplate;
  serverTemplate: ReminderTemplate;
  isSaving: boolean;
  onChange: (template: ReminderTemplate) => void;
  onSave: (template: ReminderTemplate) => void;
}

function ReminderTemplateCard({
  template,
  serverTemplate,
  isSaving,
  onChange,
  onSave,
}: ReminderTemplateCardProps) {
  const isDirty = JSON.stringify(template) !== JSON.stringify(serverTemplate);
  const update = (patch: Partial<ReminderTemplate>) => onChange({ ...template, ...patch });
  const updateTime = (index: number, value: string) => {
    const times = [...template.times];
    if (value) times[index] = `${value}:00`;
    update({ times });
  };
  const addTime = () => update({ times: [...template.times, '12:00:00'] });
  const removeTime = (index: number) =>
    update({ times: template.times.filter((_value, timeIndex) => timeIndex !== index) });

  return (
    <article className={`notification-template-card ${template.enabled ? 'is-enabled' : ''}`}>
      <header className="notification-template-card__head">
        <div>
          <span className="notification-template-card__eyebrow">Готовый сценарий</span>
          <h4>{template.label}</h4>
          <p>{template.purpose}</p>
        </div>
        <label className="switch-row notification-template-toggle">
          <input
            type="checkbox"
            aria-label={`Включить: ${template.label}`}
            checked={template.enabled}
            onChange={(event) => update({ enabled: event.target.checked })}
          />
          <span>
            <strong>{template.enabled ? 'Включён' : 'Выключен'}</strong>
            <small>По умолчанию выключен</small>
          </span>
        </label>
      </header>

      <div className="notification-template-card__summary">
        <div>
          <span>Когда</span>
          <strong>{templateScheduleSummary(template)}</strong>
        </div>
        <div>
          <span>Почему может быть пропущено</span>
          <p>{template.suppression}</p>
        </div>
        <div>
          <span>Канал</span>
          <p>{template.channel_note}</p>
          <small>Внешний текст: «{template.neutral_copy}»</small>
        </div>
      </div>

      {template.enabled && (
        <div className="notification-template-card__editor">
          <fieldset className="notification-template-weekdays">
            <legend>Дни недели</legend>
            <div className="notification-template-weekdays__options">
              {weekdayLabels.map((label, weekday) => {
                const checked = template.weekdays.includes(weekday);
                return (
                  <label className="notification-template-day" key={label}>
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={checked && template.weekdays.length === 1}
                      onChange={(event) =>
                        update({
                          weekdays: event.target.checked
                            ? [...template.weekdays, weekday].sort((left, right) => left - right)
                            : template.weekdays.filter((value) => value !== weekday),
                        })
                      }
                    />
                    <span>{label}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          {template.schedule_kind === 'times' ? (
            <div className="notification-template-fields">
              <div className="notification-template-times">
                <div className="notification-template-fields__label">
                  <span>Времена</span>
                  <small>Каждое выбранное время — отдельный мягкий повод записать еду.</small>
                </div>
                <div className="notification-template-times__list">
                  {template.times.map((value, index) => (
                    <div className="notification-template-time" key={`time-${index}`}>
                      <label className="field">
                        <span>Окно {index + 1}</span>
                        <TimeInput
                          value={timeValue(value, '08:00')}
                          onChange={(event) => updateTime(index, event.target.value)}
                        />
                      </label>
                      {template.times.length > 1 && (
                        <button
                          type="button"
                          className="text-button notification-template-time__remove"
                          onClick={() => removeTime(index)}
                        >
                          Убрать
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                {template.times.length < 3 && (
                  <button type="button" className="secondary" onClick={addTime}>
                    Добавить время
                  </button>
                )}
              </div>
              <label className="field">
                <span>Минимальный интервал, минут</span>
                <input
                  type="number"
                  min={15}
                  max={720}
                  step={15}
                  value={template.minimum_spacing_minutes}
                  onChange={(event) =>
                    update({ minimum_spacing_minutes: Number(event.target.value) })
                  }
                />
                <small className="field-hint">Окна не будут стоять ближе этого значения.</small>
              </label>
            </div>
          ) : (
            <div className="notification-template-fields notification-template-fields--interval">
              <label className="field">
                <span>Начало окна</span>
                <TimeInput
                  value={timeValue(template.window_start, '09:00')}
                  onChange={(event) =>
                    update({ window_start: event.target.value ? `${event.target.value}:00` : null })
                  }
                />
              </label>
              <label className="field">
                <span>Конец окна</span>
                <TimeInput
                  value={timeValue(template.window_end, '21:00')}
                  onChange={(event) =>
                    update({ window_end: event.target.value ? `${event.target.value}:00` : null })
                  }
                />
              </label>
              <label className="field">
                <span>Повтор, минут</span>
                <input
                  type="number"
                  min={30}
                  max={360}
                  step={30}
                  value={template.interval_minutes ?? 120}
                  onChange={(event) => update({ interval_minutes: Number(event.target.value) })}
                />
              </label>
              <label className="field">
                <span>Максимум в день</span>
                <input
                  type="number"
                  min={1}
                  max={8}
                  step={1}
                  value={template.max_per_day}
                  onChange={(event) => update({ max_per_day: Number(event.target.value) })}
                />
              </label>
              <label className="field">
                <span>Минимальный интервал, минут</span>
                <input
                  type="number"
                  min={15}
                  max={720}
                  step={15}
                  value={template.minimum_spacing_minutes}
                  onChange={(event) =>
                    update({ minimum_spacing_minutes: Number(event.target.value) })
                  }
                />
              </label>
            </div>
          )}

          <div className="notification-template-card__notes">
            <p>
              <strong>Тихие часы:</strong> {template.quiet_hours_behavior}
            </p>
            <p>
              <strong>Откроется:</strong> {template.deep_link}
            </p>
          </div>
        </div>
      )}

      <footer className="notification-template-card__actions">
        <small>
          {template.enabled
            ? 'Изменения применятся после сохранения и будут работать в часовом поясе профиля.'
            : 'Включите шаблон, чтобы настроить расписание и сохранить его.'}
        </small>
        <button
          type="button"
          aria-label={`Сохранить шаблон «${template.label}»`}
          disabled={!isDirty || isSaving}
          onClick={() => onSave(template)}
        >
          {isSaving ? 'Сохраняем…' : 'Сохранить шаблон'}
        </button>
      </footer>
    </article>
  );
}

function timeValue(value: string | null | undefined, fallback: string): string {
  return value ? value.slice(0, 5) : fallback;
}

function formatWallTime(value: string): string {
  const normalized = value.length === 16 ? `${value}:00` : value;
  const parsed = new Date(`${normalized}Z`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'UTC',
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
}

export function NotificationsPanel({ onNavigate }: { onNavigate?: (path: string) => void }) {
  const queryClient = useQueryClient();
  const { toast, confirm } = useFeedback();
  const { user } = useAuth();
  const timeZone = user?.profile?.timezone || detectedTimeZone();
  const settings = useQuery({
    queryKey: ['notifications', 'settings'],
    queryFn: () => api<NotificationSetting>('/api/v1/notifications/settings'),
  });
  const notifications = useQuery({
    queryKey: ['notifications', 'list'],
    queryFn: () => api<NotificationItem[]>('/api/v1/notifications'),
  });
  const templates = useQuery({
    queryKey: ['notifications', 'templates'],
    queryFn: () => api<ReminderTemplate[]>('/api/v1/notifications/templates'),
  });
  const defaultNotification = () => ({
    title: 'Личное напоминание',
    body: 'Откройте приложение и проверьте запланированное действие',
    scheduledDate: addCalendarDays(dateInputValue(new Date(), timeZone), 1),
  });
  const [notificationDraft, setNotificationDraft, clearNotificationDraft] = usePersistentState(
    notificationDraftStorageKey(user?.id ?? 'anonymous'),
    defaultNotification,
  );
  const [settingsDraft, setSettingsDraft] = useState<NotificationSetting | null>(null);
  const [templateDrafts, setTemplateDrafts] = useState<
    Partial<Record<ReminderTemplateKey, ReminderTemplate>>
  >({});
  const [savingTemplateKey, setSavingTemplateKey] = useState<ReminderTemplateKey | null>(null);
  const visibleSettings = settingsDraft ?? settings.data ?? null;
  const settingsDirty = Boolean(
    settings.data &&
    settingsDraft &&
    JSON.stringify(settings.data) !== JSON.stringify(settingsDraft),
  );
  const unreadCount = useMemo(
    () => notifications.data?.filter((item) => !item.read_at).length ?? 0,
    [notifications.data],
  );

  const settingsMutation = useMutation({
    mutationFn: (payload: NotificationSetting) =>
      api<NotificationSetting>('/api/v1/notifications/settings', {
        method: 'PATCH',
        body: {
          workout_reminders_enabled: payload.workout_reminders_enabled,
          weekly_check_in_reminders_enabled: payload.weekly_check_in_reminders_enabled,
          measurement_reminders_enabled: payload.measurement_reminders_enabled,
          telegram_enabled: payload.telegram_enabled,
          reminder_hour: payload.reminder_hour,
          quiet_hours_start: payload.quiet_hours_start,
          quiet_hours_end: payload.quiet_hours_end,
        },
      }),
    onSuccess: (saved) => {
      trackProductEvent({
        name: 'notification_preferences_changed',
        surface: productEventSurface(),
      });
      queryClient.setQueryData(['notifications', 'settings'], saved);
      setSettingsDraft(null);
      toast('Настройки уведомлений сохранены');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const templateMutation = useMutation({
    mutationFn: (template: ReminderTemplate) =>
      api<ReminderTemplate>(`/api/v1/notifications/templates/${template.template_key}`, {
        method: 'PATCH',
        body: templateUpdatePayload(template),
      }),
    onSuccess: (saved) => {
      queryClient.setQueryData<ReminderTemplate[]>(['notifications', 'templates'], (current) =>
        current?.map((template) =>
          template.template_key === saved.template_key ? saved : template,
        ),
      );
      setTemplateDrafts((current) =>
        current ? { ...current, [saved.template_key]: saved } : current,
      );
      setSavingTemplateKey(null);
      toast(`Шаблон «${saved.label}» сохранён`);
    },
    onError: (reason) => {
      setSavingTemplateKey(null);
      toast((reason as Error).message, 'error');
    },
  });
  const listMutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body?: unknown }) =>
      api(path, { method, body }),
    onSuccess: async (_data, variables) => {
      await queryClient.invalidateQueries({ queryKey: ['notifications'] });
      if (variables.method === 'POST') {
        clearNotificationDraft(defaultNotification());
        toast('Личное напоминание создано');
      } else {
        toast('Уведомление удалено');
      }
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const openMutation = useMutation({
    mutationFn: (notificationId: number) =>
      api<NotificationOpenResponse>(`/api/v1/notifications/${notificationId}/open`, {
        method: 'POST',
      }),
    onSuccess: (result) => {
      if (result.message) toast(result.message, result.stale ? 'error' : 'success');
      onNavigate?.(result.destination);
      void queryClient.invalidateQueries({ queryKey: ['notifications', 'list'] });
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const readAllMutation = useMutation({
    mutationFn: () => api('/api/v1/notifications/read-all', { method: 'PATCH' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['notifications', 'list'] });
      toast('Все уведомления отмечены прочитанными');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  return (
    <div className="notification-preferences stack">
      <section className="notification-settings" aria-labelledby="notification-channels-title">
        {settings.isLoading ? (
          <LoadingState />
        ) : settings.error ? (
          <ErrorState message={(settings.error as Error).message} />
        ) : (
          visibleSettings && (
            <form
              className="stack"
              onSubmit={(event) => {
                event.preventDefault();
                settingsMutation.mutate(visibleSettings);
              }}
            >
              <div className="notification-settings__group">
                <div className="notification-settings__heading">
                  <h3 id="notification-channels-title">Каналы</h3>
                  <p>
                    Подробности всегда остаются в приложении; Telegram показывает нейтральный текст.
                  </p>
                </div>
                <div className="notification-channel-row">
                  <span>
                    <strong>В приложении</strong>
                    <small>Всегда доступно в центре уведомлений</small>
                  </span>
                  <span className="notification-channel-state">Включено</span>
                </div>
                <label
                  className={`switch-row ${!visibleSettings.telegram_linked ? 'is-disabled' : ''}`}
                >
                  <input
                    type="checkbox"
                    checked={visibleSettings.telegram_enabled && visibleSettings.telegram_linked}
                    disabled={!visibleSettings.telegram_linked}
                    onChange={(event) =>
                      setSettingsDraft({
                        ...visibleSettings,
                        telegram_enabled: event.target.checked,
                      })
                    }
                  />
                  <span>
                    <strong>Telegram</strong>
                    <small>
                      {visibleSettings.telegram_linked
                        ? 'Получать внешние уведомления в связанном аккаунте'
                        : 'Недоступно: сначала свяжите Telegram в разделе доступа'}
                    </small>
                  </span>
                </label>
              </div>

              <div className="notification-settings__group">
                <div className="notification-settings__heading">
                  <h3>Полезные напоминания</h3>
                  <p>
                    Системные сообщения тренера и изменения программы остаются отдельными событиями.
                  </p>
                </div>
                <label className="switch-row">
                  <input
                    type="checkbox"
                    checked={visibleSettings.workout_reminders_enabled}
                    onChange={(event) =>
                      setSettingsDraft({
                        ...visibleSettings,
                        workout_reminders_enabled: event.target.checked,
                      })
                    }
                  />
                  <span>
                    <strong>Предстоящая тренировка</strong>
                    <small>За 2 часа до точного времени или в выбранный час дня</small>
                  </span>
                </label>
                <label className="switch-row">
                  <input
                    type="checkbox"
                    checked={visibleSettings.weekly_check_in_reminders_enabled}
                    onChange={(event) =>
                      setSettingsDraft({
                        ...visibleSettings,
                        weekly_check_in_reminders_enabled: event.target.checked,
                      })
                    }
                  />
                  <span>
                    <strong>Итоги недели</strong>
                    <small>Одно напоминание в воскресенье, если итоги ещё не заполнены</small>
                  </span>
                </label>
                <label className="switch-row">
                  <input
                    type="checkbox"
                    checked={visibleSettings.measurement_reminders_enabled}
                    onChange={(event) =>
                      setSettingsDraft({
                        ...visibleSettings,
                        measurement_reminders_enabled: event.target.checked,
                      })
                    }
                  />
                  <span>
                    <strong>Замеры</strong>
                    <small>Не чаще раза в неделю и только если замеров не было 14 дней</small>
                  </span>
                </label>
              </div>

              <div className="notification-settings__group notification-schedule-grid">
                <label className="field">
                  <span>Час для напоминаний без точного времени</span>
                  <TimeInput
                    controlClassName="reminder-time-control"
                    step="3600"
                    value={`${String(visibleSettings.reminder_hour).padStart(2, '0')}:00`}
                    onChange={(event) =>
                      setSettingsDraft({
                        ...visibleSettings,
                        reminder_hour: Number(event.target.value.split(':')[0]),
                      })
                    }
                  />
                </label>
                <label className="switch-row notification-quiet-toggle">
                  <input
                    type="checkbox"
                    checked={Boolean(visibleSettings.quiet_hours_start)}
                    onChange={(event) =>
                      setSettingsDraft({
                        ...visibleSettings,
                        quiet_hours_start: event.target.checked ? '22:00:00' : null,
                        quiet_hours_end: event.target.checked ? '08:00:00' : null,
                      })
                    }
                  />
                  <span>
                    <strong>Тихие часы</strong>
                    <small>Доставка подождёт до окончания выбранного периода</small>
                  </span>
                </label>
                {visibleSettings.quiet_hours_start && visibleSettings.quiet_hours_end && (
                  <div className="notification-quiet-hours">
                    <label className="field">
                      <span>С</span>
                      <TimeInput
                        value={timeValue(visibleSettings.quiet_hours_start, '22:00')}
                        onChange={(event) =>
                          setSettingsDraft({
                            ...visibleSettings,
                            quiet_hours_start: `${event.target.value}:00`,
                          })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>До</span>
                      <TimeInput
                        value={timeValue(visibleSettings.quiet_hours_end, '08:00')}
                        onChange={(event) =>
                          setSettingsDraft({
                            ...visibleSettings,
                            quiet_hours_end: `${event.target.value}:00`,
                          })
                        }
                      />
                    </label>
                  </div>
                )}
              </div>
              <div className="notification-settings__save">
                <button type="submit" disabled={!settingsDirty || settingsMutation.isPending}>
                  {settingsMutation.isPending ? 'Сохраняем…' : 'Сохранить настройки'}
                </button>
              </div>
            </form>
          )
        )}
      </section>

      <WebPushSettings />

      <details className="notification-templates profile-disclosure">
        <summary>
          <span>
            <strong>Готовые шаблоны</strong>
            <small>
              Мягкие подсказки для питания, воды и коротких перерывов · выключены по умолчанию
            </small>
          </span>
          <DisclosureIcon />
        </summary>
        <div className="profile-disclosure__body">
          {templates.isLoading ? (
            <LoadingState />
          ) : templates.error ? (
            <ErrorState
              message={(templates.error as Error).message}
              retry={() => void templates.refetch()}
            />
          ) : (
            <div className="notification-template-list">
              {templates.data?.map((serverTemplate) => {
                const template = templateDrafts?.[serverTemplate.template_key] ?? serverTemplate;
                return (
                  <ReminderTemplateCard
                    key={serverTemplate.template_key}
                    template={template}
                    serverTemplate={serverTemplate}
                    isSaving={savingTemplateKey === serverTemplate.template_key}
                    onChange={(next) =>
                      setTemplateDrafts((current) => ({
                        ...(current ?? {}),
                        [next.template_key]: next,
                      }))
                    }
                    onSave={(next) => {
                      setSavingTemplateKey(next.template_key);
                      templateMutation.mutate(next);
                    }}
                  />
                );
              })}
            </div>
          )}
        </div>
      </details>

      <details className="notification-center profile-disclosure">
        <summary>
          <span>
            <strong>Центр уведомлений</strong>
            <small>
              {notifications.isLoading
                ? 'Загружаем события…'
                : notifications.error
                  ? 'Не удалось загрузить · можно повторить после раскрытия'
                  : unreadCount
                    ? `Непрочитанные · ${unreadCount}`
                    : notifications.data?.length
                      ? 'Всё прочитано'
                      : 'Уведомлений пока нет'}
            </small>
          </span>
          <DisclosureIcon />
        </summary>
        <div className="profile-disclosure__body">
          <header className="notification-center__head">
            <h3 id="notification-center-title">
              {unreadCount ? `Непрочитанные · ${unreadCount}` : 'Последние события'}
            </h3>
            {unreadCount > 0 && (
              <button
                type="button"
                className="secondary"
                disabled={readAllMutation.isPending}
                onClick={() => readAllMutation.mutate()}
              >
                Отметить всё
              </button>
            )}
          </header>
          {notifications.isLoading ? (
            <LoadingState />
          ) : notifications.error ? (
            <ErrorState
              message={(notifications.error as Error).message}
              retry={() => void notifications.refetch()}
            />
          ) : !notifications.data?.length ? (
            <EmptyState
              title="Уведомлений пока нет"
              text="Здесь появятся напоминания и важные изменения от тренера."
            />
          ) : (
            <div className="notification-list">
              {notifications.data.map((item) => {
                const canOpen = navigableCategories.has(item.category);
                const copy = (
                  <>
                    <span className="notification-row__meta">
                      {categoryLabels[item.category] ?? 'Событие'}
                      {!item.read_at && <span>Новое</span>}
                    </span>
                    <strong>{item.title}</strong>
                    <span>{item.body}</span>
                    <span className="muted">
                      {item.event_kind === 'reminder' ? 'Запланировано' : 'Создано'}:{' '}
                      {formatWallTime(item.scheduled_for)}
                    </span>
                  </>
                );
                return (
                  <article
                    className={`notification-row ${item.read_at ? '' : 'notification-row--unread'}`}
                    key={item.id}
                  >
                    {canOpen && onNavigate ? (
                      <button
                        type="button"
                        className="notification-row__main text-button notification-action"
                        aria-label={`Открыть: ${item.title}`}
                        disabled={openMutation.isPending}
                        onClick={() => openMutation.mutate(item.id)}
                      >
                        {copy}
                      </button>
                    ) : (
                      <div className="notification-row__main">{copy}</div>
                    )}
                    <button
                      type="button"
                      className="notification-row__delete"
                      onClick={async () => {
                        if (
                          await confirm({
                            title: 'Удалить уведомление?',
                            message: item.title,
                            confirmText: 'Удалить',
                          })
                        ) {
                          listMutation.mutate({
                            path: `/api/v1/notifications/${item.id}`,
                            method: 'DELETE',
                          });
                        }
                      }}
                    >
                      Удалить
                    </button>
                  </article>
                );
              })}
            </div>
          )}
        </div>
      </details>

      <details className="notification-personal profile-disclosure">
        <summary>
          <span>
            <strong>Личное напоминание</strong>
            <small>Свободный текст остаётся внутри приложения</small>
          </span>
          <DisclosureIcon />
        </summary>
        <div className="profile-disclosure__body">
          <p className="muted">
            В Telegram придёт только нейтральная фраза без текста напоминания.
          </p>
          <form
            className="stack"
            onSubmit={(event) => {
              event.preventDefault();
              listMutation.mutate({
                path: '/api/v1/notifications',
                method: 'POST',
                body: {
                  title: notificationDraft.title,
                  body: notificationDraft.body,
                  scheduled_for: `${notificationDraft.scheduledDate}T${String(
                    settings.data?.reminder_hour ?? 9,
                  ).padStart(2, '0')}:00:00`,
                },
              });
            }}
          >
            <div className="form-grid">
              <label className="field">
                <span>Заголовок</span>
                <input
                  value={notificationDraft.title}
                  maxLength={128}
                  onChange={(event) =>
                    setNotificationDraft({ ...notificationDraft, title: event.target.value })
                  }
                  required
                />
              </label>
              <label className="field">
                <span>Дата</span>
                <DateInput
                  controlClassName="notification-date-control"
                  min={dateInputValue(new Date(), timeZone)}
                  value={notificationDraft.scheduledDate}
                  onChange={(event) =>
                    setNotificationDraft({
                      ...notificationDraft,
                      scheduledDate: event.target.value,
                    })
                  }
                  required
                />
                <small className="field-hint">
                  Отправка в {String(settings.data?.reminder_hour ?? 9).padStart(2, '0')}:00
                </small>
              </label>
            </div>
            <label className="field">
              <span>Текст внутри приложения</span>
              <textarea
                value={notificationDraft.body}
                maxLength={2000}
                onChange={(event) =>
                  setNotificationDraft({ ...notificationDraft, body: event.target.value })
                }
                required
              />
            </label>
            <button className="secondary" disabled={listMutation.isPending}>
              {listMutation.isPending ? 'Создаём…' : 'Создать напоминание'}
            </button>
          </form>
        </div>
      </details>
    </div>
  );
}
