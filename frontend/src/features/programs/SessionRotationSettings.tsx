import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, getUserFacingErrorMessage } from '../../shared/api/client';
import type { ApiSchemas } from '../../shared/api/types';
import { Button, Field, SegmentedControl, Select } from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { useOnlineStatus } from '../../shared/ui/OnlineStatus';
import './SessionRotation.css';

type Settings = ApiSchemas['SessionRotationSettingsResponse'];
type SettingsRequest = ApiSchemas['SessionRotationSettingsRequest'];

export function SessionRotationSettings({
  programId,
  readOnly = false,
}: {
  programId: number;
  readOnly?: boolean;
}) {
  const queryClient = useQueryClient();
  const online = useOnlineStatus();
  const { toast } = useFeedback();
  const [draftMode, setDraftMode] = useState<'calendar' | 'rotation' | null>(null);
  const [firstDay, setFirstDay] = useState('');
  const [calendarChoice, setCalendarChoice] = useState('');
  const [preview, setPreview] = useState<{ result: Settings; request: SettingsRequest } | null>(
    null,
  );
  const [error, setError] = useState('');
  const path = `/api/v1/programs/assigned/${programId}/session-rotation`;
  const settings = useQuery({
    queryKey: ['assigned-program', programId, 'session-rotation'],
    queryFn: () => api<Settings>(path, { cache: 'no-store' }),
  });
  const onError = async (reason: unknown) => {
    if (reason instanceof ApiError && reason.status === 409) {
      setPreview(null);
      await settings.refetch();
      setError('Программа изменилась. Проверьте порядок тренировок ещё раз.');
      return;
    }
    setError(getUserFacingErrorMessage(reason));
  };
  const previewMutation = useMutation({
    mutationFn: (request: SettingsRequest) =>
      api<Settings>(`${path}/preview`, { method: 'POST', body: request }),
    onSuccess: (result, request) => {
      setPreview({ result, request });
      setError('');
    },
    onError,
  });
  const applyMutation = useMutation({
    mutationFn: ({ result, request }: { result: Settings; request: SettingsRequest }) =>
      api<Settings>(`${path}/apply`, {
        method: 'POST',
        body: { ...request, preview_token: result.preview_token },
      }),
    onSuccess: async () => {
      setPreview(null);
      setDraftMode(null);
      setFirstDay('');
      setCalendarChoice('');
      setError('');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['assigned-program', programId] }),
        queryClient.invalidateQueries({ queryKey: ['workout'] }),
        queryClient.invalidateQueries({ queryKey: ['templates'] }),
        queryClient.invalidateQueries({ queryKey: ['coach', 'programs'] }),
      ]);
      toast('Порядок тренировок сохранён');
    },
    onError,
  });
  if (settings.isPending) return <p role="status">Загружаем порядок тренировок…</p>;
  if (settings.isError || !settings.data) {
    return (
      <div className="session-rotation-settings" role="alert">
        <p>Не удалось загрузить порядок тренировок.</p>
        <Button type="button" variant="secondary" onClick={() => void settings.refetch()}>
          Повторить
        </Button>
      </div>
    );
  }
  const mode = draftMode ?? settings.data.mode;
  const busy = previewMutation.isPending || applyMutation.isPending;
  return (
    <section
      className="session-rotation-settings"
      aria-labelledby={`rotation-settings-${programId}`}
    >
      <h3 id={`rotation-settings-${programId}`}>Порядок тренировок</h3>
      <p>Выберите, как определять следующую тренировку.</p>
      <SegmentedControl
        ariaLabel="Порядок тренировок"
        value={mode}
        onChange={(value) => {
          setDraftMode(
            value === 'calendar' && settings.data.mode === 'calendar'
              ? null
              : (value as 'calendar' | 'rotation'),
          );
          setFirstDay('');
          setCalendarChoice('');
          setPreview(null);
          setError('');
        }}
        options={[
          { label: 'По расписанию', value: 'calendar', disabled: readOnly },
          { label: 'По очереди', value: 'rotation', disabled: readOnly },
        ]}
      />
      <p>
        {mode === 'rotation'
          ? 'Следующая тренировка определяется порядком дней, а не датой. Отдых не сдвигает очередь.'
          : 'Тренировки показываются по дням календарного расписания.'}
      </p>
      {mode === 'rotation' && draftMode !== null && (
        <Field label="С какой тренировки начать?" labelFor={`rotation-first-${programId}`}>
          <Select
            id={`rotation-first-${programId}`}
            value={firstDay}
            onChange={(event) => {
              setFirstDay(event.target.value);
              setPreview(null);
            }}
          >
            <option value="">Выберите тренировку</option>
            {settings.data.days.map((day) => (
              <option key={day.day_number} value={day.day_number}>
                {day.title}
                {day.from_template ? ' · из шаблона' : ''}
              </option>
            ))}
          </Select>
        </Field>
      )}
      {mode === 'calendar' && settings.data.mode === 'rotation' && draftMode !== null && (
        <Field label="С какой тренировки продолжить?" labelFor={`rotation-calendar-${programId}`}>
          <Select
            id={`rotation-calendar-${programId}`}
            value={calendarChoice}
            onChange={(event) => {
              setCalendarChoice(event.target.value);
              setPreview(null);
            }}
          >
            <option value="">Выберите тренировку</option>
            {settings.data.calendar_options?.map((option) => (
              <option
                key={`${option.week_number}:${option.day_number}`}
                value={`${option.week_number}:${option.day_number}`}
              >
                {option.scheduled_date} · {option.title}
              </option>
            ))}
          </Select>
          {!settings.data.calendar_options?.length && (
            <p>В ближайшем расписании нет тренировок. Продлите программу или измените план.</p>
          )}
        </Field>
      )}
      {readOnly && <p>Изменения программы согласуйте с тренером.</p>}
      {!online && (
        <p role="status">Нет соединения. Изменения можно подтвердить после подключения.</p>
      )}
      {error && <p role="alert">{error}</p>}
      {preview ? (
        <div className="session-rotation-settings__preview">
          <strong>Проверьте изменения</strong>
          <p>
            {mode === 'rotation'
              ? `Первой будет: ${preview.result.days.find((day) => day.day_number === Number(firstDay))?.title ?? ''}.`
              : `Календарное расписание продолжится с «${preview.result.calendar_resume?.title ?? ''}» ${preview.result.calendar_resume?.scheduled_date ?? ''}.`}
          </p>
          {preview.result.future_reminders > 0 && (
            <>
              <p>Напоминания о тренировках будут отменены: {preview.result.future_reminders}.</p>
              <ul>
                {preview.result.reminders?.map((reminder) => (
                  <li key={reminder.workout_id}>
                    {reminder.title} · {reminder.scheduled_date}
                    {reminder.status === 'processing' ? ' · уже отправляется' : ''}
                  </li>
                ))}
              </ul>
            </>
          )}
          {Boolean(preview.result.template_plans?.length) && (
            <>
              <strong>Дни, которых нет в назначенном расписании</strong>
              <p>
                Эти тренировки добавятся в очередь по текущему шаблону. Сохранится показанный план
                первой недели.
              </p>
              {preview.result.template_plans?.map((plan) => (
                <div key={plan.day_number}>
                  <strong>
                    {plan.title} · неделя {plan.week_number}
                  </strong>
                  <ul>
                    {plan.exercises.map((exercise, index) => (
                      <li key={`${exercise.title}-${index}`}>
                        {exercise.title}
                        {exercise.prescribed_sets ? ` · подходов: ${exercise.prescribed_sets}` : ''}
                        {exercise.prescribed_reps ? ` × ${exercise.prescribed_reps}` : ''}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </>
          )}
          <p>Выполненные тренировки и подходы сохранятся.</p>
          <Button
            disabled={!online || busy}
            type="button"
            onClick={() => applyMutation.mutate(preview)}
          >
            Подтвердить изменения
          </Button>
          <Button type="button" variant="ghost" onClick={() => setPreview(null)}>
            Вернуться
          </Button>
        </div>
      ) : (
        draftMode !== null &&
        !readOnly && (
          <Button
            type="button"
            disabled={
              !online ||
              busy ||
              (mode === 'rotation' && !firstDay) ||
              (mode === 'calendar' && settings.data.mode === 'rotation' && !calendarChoice)
            }
            onClick={() =>
              previewMutation.mutate({
                mode,
                first_day_number: mode === 'rotation' ? Number(firstDay) : null,
                resume_calendar_week:
                  mode === 'calendar' && calendarChoice
                    ? Number(calendarChoice.split(':')[0])
                    : null,
                resume_calendar_day:
                  mode === 'calendar' && calendarChoice
                    ? Number(calendarChoice.split(':')[1])
                    : null,
                expected_revision_number: settings.data.revision_number,
              })
            }
          >
            Проверить изменения
          </Button>
        )
      )}
    </section>
  );
}
