import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type {
  BodyMeasurement,
  BodyMeasurementDefinition,
  BodyMeasurementSave,
} from '../../shared/api/types';
import { LIVE_DATA_REFETCH_INTERVAL_MS } from '../../shared/sync';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Button, Card, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';
import { useAuth } from '../../app/AuthProvider';
import { dateInputValue, detectedTimeZone, formatCalendarDate } from '../../shared/dateTime';
import { usePersistentState } from '../../shared/storage';
import { measurementDraftStorageKey } from '../../shared/userScopedStorage';
import { DateInput } from '../../shared/ui/PickerInput';
import { invalidateMeasurementMutation, queryKeys } from '../../shared/queryKeys';
import { productEventSurface, trackCoreProductEvent } from '../../shared/analytics/productEvents';

export function Diary({
  clientId,
  timeZone: clientTimeZone,
  onSaved,
  embedded = false,
  readOnly = false,
}: {
  clientId?: number;
  timeZone?: string | null;
  onSaved?: () => void | Promise<void>;
  embedded?: boolean;
  readOnly?: boolean;
}) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { toast, confirm } = useFeedback();
  const formRef = useRef<HTMLFormElement>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [editingDate, setEditingDate] = useState<string | null>(null);
  const timeZone = clientId
    ? clientTimeZone || detectedTimeZone()
    : user?.profile?.timezone || detectedTimeZone();
  const today = dateInputValue(new Date(), timeZone);
  const [form, setForm, clearDraft] = usePersistentState<BodyMeasurementSave>(
    measurementDraftStorageKey(clientId ? `client_${clientId}` : `user_${user?.id ?? 'me'}`),
    { measured_on: dateInputValue(new Date(), timeZone) },
  );
  const base = clientId
    ? `/api/v1/coach/clients/${clientId}/measurements`
    : '/api/v1/workouts/diary';
  const definitionsBase = clientId
    ? `/api/v1/coach/clients/${clientId}/measurements/custom-definitions?include_archived=true`
    : '/api/v1/workouts/diary/custom-definitions?include_archived=true';
  const rows = useQuery({
    queryKey: queryKeys.measurements.subject(clientId),
    queryFn: () => api<BodyMeasurement[]>(base),
    refetchInterval: LIVE_DATA_REFETCH_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });
  const definitions = useQuery({
    queryKey: queryKeys.measurements.definitions(clientId),
    queryFn: () => api<BodyMeasurementDefinition[]>(definitionsBase),
    refetchOnWindowFocus: true,
  });
  const [definitionLabel, setDefinitionLabel] = useState('');
  const [editingDefinitionId, setEditingDefinitionId] = useState<number | null>(null);
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body?: unknown }) =>
      api(path, { method, body }),
    onMutate: () => setSubmitError(null),
    onSuccess: async (_result, variables) => {
      if (variables.method === 'POST') {
        trackCoreProductEvent(
          { name: 'measurement_logged', surface: productEventSurface() },
          'measurement_logged',
        );
      }
      const activeElement = document.activeElement;
      if (activeElement instanceof HTMLElement && formRef.current?.contains(activeElement)) {
        activeElement.blur();
      }
      setEditingDate(null);
      clearDraft({ measured_on: today });
      await invalidateMeasurementMutation(queryClient, clientId);
      await onSaved?.();
      toast('Дневник обновлён');
    },
    onError: (reason) => {
      const message = (reason as Error).message;
      setSubmitError(message);
      toast(message, 'error');
    },
  });
  const definitionMutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body?: unknown }) =>
      api(path, { method, body }),
    onSuccess: async () => {
      setDefinitionLabel('');
      setEditingDefinitionId(null);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.measurements.definitions(clientId),
      });
      toast('Список показателей обновлён');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const numeric = [
    'weight_kg',
    'chest_cm',
    'waist_cm',
    'hips_cm',
    'biceps_cm',
    'thigh_cm',
  ] as const;
  const numericLimits: Record<(typeof numeric)[number], { min: number; max: number }> = {
    weight_kg: { min: 20, max: 350 },
    chest_cm: { min: 0.1, max: 300 },
    waist_cm: { min: 0.1, max: 300 },
    hips_cm: { min: 0.1, max: 300 },
    biceps_cm: { min: 0.1, max: 150 },
    thigh_cm: { min: 0.1, max: 200 },
  };
  const editingMeasurement = rows.data?.find((item) => item.measured_on === editingDate);
  const resetForm = () => {
    setSubmitError(null);
    setEditingDate(null);
    clearDraft({ measured_on: today });
  };
  const editMeasurement = (item: BodyMeasurement) => {
    setSubmitError(null);
    setEditingDate(item.measured_on);
    setForm({
      measured_on: item.measured_on,
      weight_kg: item.weight_kg,
      chest_cm: item.chest_cm,
      waist_cm: item.waist_cm,
      hips_cm: item.hips_cm,
      biceps_cm: item.biceps_cm,
      thigh_cm: item.thigh_cm,
      note: item.note,
      custom_values: (item.custom_values ?? []).map((value) => ({
        definition_id: value.definition_id,
        value: value.value,
      })),
    });
    requestAnimationFrame(() => {
      formRef.current?.scrollIntoView?.({ block: 'center' });
      formRef.current?.querySelector<HTMLInputElement>('input')?.focus();
    });
  };
  const activeDefinitions = (definitions.data ?? []).filter((definition) => !definition.archived);
  const setCustomValue = (definitionId: number, value: number | null) => {
    const customValues = (form.custom_values ?? []).filter(
      (item) => item.definition_id !== definitionId,
    );
    customValues.push({ definition_id: definitionId, value });
    setForm({ ...form, custom_values: customValues });
  };
  const saveDefinition = () => {
    const label = definitionLabel.trim();
    if (!label) return;
    if (editingDefinitionId === null) {
      definitionMutation.mutate({
        path: '/api/v1/workouts/diary/custom-definitions',
        method: 'POST',
        body: { label },
      });
    } else {
      definitionMutation.mutate({
        path: `/api/v1/workouts/diary/custom-definitions/${editingDefinitionId}`,
        method: 'PATCH',
        body: { label },
      });
    }
  };
  const content = (
    <>
      <header className="measurement-diary__header">
        <div>
          <span className="progress-section__eyebrow">Фактические данные</span>
          <h3>{editingMeasurement ? 'Изменить замер' : 'Новый замер'}</h3>
          <p>
            {editingMeasurement
              ? `Обновится запись за ${formatCalendarDate(editingMeasurement.measured_on, { day: 'numeric', month: 'long', year: 'numeric' })}.`
              : 'Достаточно одного показателя. Остальные поля можно заполнить позже.'}
          </p>
        </div>
        {editingMeasurement && (
          <Button type="button" variant="secondary" disabled={readOnly} onClick={resetForm}>
            Отменить изменение
          </Button>
        )}
      </header>
      {readOnly && (
        <p className="muted demo-capability-notice" role="status">
          Изменение замеров доступно после входа. Здесь показаны только подготовленные данные.
        </p>
      )}
      <fieldset className="demo-capability-fieldset" disabled={readOnly}>
        <form
          ref={formRef}
          className="stack measurement-diary__form"
          aria-busy={mutation.isPending}
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate({ path: base, method: 'POST', body: form });
          }}
        >
          <div className="form-grid diary-form-grid">
            <label className="field">
              <span>Дата</span>
              <DateInput
                controlClassName="diary-date-control"
                disabled={Boolean(editingMeasurement)}
                value={form.measured_on || ''}
                max={today}
                onChange={(e) => setForm({ ...form, measured_on: e.target.value })}
              />
            </label>
            {numeric.map((key) => (
              <label className="field" key={key}>
                <span>
                  {
                    {
                      weight_kg: 'Вес, кг',
                      chest_cm: 'Грудь, см',
                      waist_cm: 'Талия, см',
                      hips_cm: 'Бёдра, см',
                      biceps_cm: 'Плечо (окружность), см',
                      thigh_cm: 'Бедро (окружность), см',
                    }[key]
                  }
                </span>
                <input
                  type="number"
                  inputMode="decimal"
                  enterKeyHint={key === 'thigh_cm' ? 'done' : 'next'}
                  step="0.1"
                  min={numericLimits[key].min}
                  max={numericLimits[key].max}
                  value={form[key] ?? ''}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      [key]: e.target.value === '' ? null : Number(e.target.value),
                    })
                  }
                />
              </label>
            ))}
            {activeDefinitions.map((definition) => {
              const currentValue = form.custom_values?.find(
                (item) => item.definition_id === definition.id,
              )?.value;
              return (
                <label className="field" key={definition.id}>
                  <span>{definition.label}, см</span>
                  <input
                    aria-label={`${definition.label}, см`}
                    type="number"
                    inputMode="decimal"
                    step="0.1"
                    min={0.1}
                    max={300}
                    value={currentValue ?? ''}
                    onChange={(e) =>
                      setCustomValue(
                        definition.id,
                        e.target.value === '' ? null : Number(e.target.value),
                      )
                    }
                  />
                </label>
              );
            })}
          </div>
          <div className="auth-notice stack" aria-label="Как делать замеры">
            <strong>Как сравнивать замеры</strong>
            <span>
              Снимайте их в похожее время суток, в одинаковых условиях и накладывайте ленту в одном
              месте. Оценивайте несколько замеров, а не единичное колебание.
            </span>
            <small className="muted">
              Окружность плеча не показывает отдельно размер бицепса, а окружность бедра — размер
              квадрицепса. Эти значения описывают участок тела целиком.
            </small>
          </div>
          <label className="field">
            <span>Заметка</span>
            <textarea
              value={form.note || ''}
              maxLength={500}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
          </label>
          {submitError && (
            <p className="measurement-diary__error" role="alert">
              {submitError} Введённые значения сохранены — исправьте данные или повторите попытку.
            </p>
          )}
          <div className="measurement-diary__save-dock">
            <Button
              className="measurement-diary__save"
              disabled={mutation.isPending}
              fullWidth
              onMouseDown={(event) => {
                const activeElement = document.activeElement;
                if (
                  activeElement instanceof HTMLElement &&
                  formRef.current?.contains(activeElement)
                ) {
                  event.preventDefault();
                }
              }}
              onClick={(event) => {
                event.preventDefault();
                formRef.current?.requestSubmit();
              }}
              type="submit"
            >
              {mutation.isPending
                ? 'Сохраняем…'
                : editingMeasurement
                  ? 'Сохранить изменения'
                  : 'Сохранить замер'}
            </Button>
          </div>
        </form>
        {!clientId && !readOnly && (
          <section className="measurement-custom-fields" aria-labelledby="custom-measurement-title">
            <header className="measurement-custom-fields__header">
              <div>
                <span className="progress-section__eyebrow">Только для вас</span>
                <h3 id="custom-measurement-title">Свои показатели</h3>
                <p>
                  Добавляйте только те дополнительные замеры, которые хотите вести в сантиметрах.
                </p>
              </div>
            </header>
            <form
              className="measurement-custom-fields__form"
              onSubmit={(event) => {
                event.preventDefault();
                saveDefinition();
              }}
            >
              <label className="field">
                <span>{editingDefinitionId === null ? 'Новый показатель' : 'Новое название'}</span>
                <input
                  aria-label="Название пользовательского показателя"
                  autoComplete="off"
                  className="measurement-custom-fields__label-input"
                  enterKeyHint="done"
                  maxLength={64}
                  type="text"
                  value={definitionLabel}
                  onChange={(event) => setDefinitionLabel(event.target.value)}
                />
              </label>
              <Button
                disabled={definitionMutation.isPending || !definitionLabel.trim()}
                type="submit"
              >
                {editingDefinitionId === null ? 'Добавить показатель' : 'Сохранить название'}
              </Button>
              {editingDefinitionId !== null && (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    setEditingDefinitionId(null);
                    setDefinitionLabel('');
                  }}
                >
                  Отменить
                </Button>
              )}
            </form>
            {definitionMutation.error && (
              <p className="measurement-diary__error" role="alert">
                {(definitionMutation.error as Error).message}
              </p>
            )}
            {definitions.error ? (
              <p className="measurement-diary__error" role="alert">
                {(definitions.error as Error).message}
              </p>
            ) : (
              <ul className="measurement-custom-fields__list">
                {(definitions.data ?? []).map((definition) => (
                  <li key={definition.id}>
                    <span>
                      <strong>{definition.label}</strong> · см
                      {definition.archived && <small>Архивирован</small>}
                    </span>
                    <div>
                      {!definition.archived && (
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => {
                            setEditingDefinitionId(definition.id);
                            setDefinitionLabel(definition.label);
                          }}
                        >
                          Переименовать
                        </Button>
                      )}
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={async () => {
                          if (definition.archived) {
                            definitionMutation.mutate({
                              path: `/api/v1/workouts/diary/custom-definitions/${definition.id}/restore`,
                              method: 'POST',
                            });
                            return;
                          }
                          if (
                            await confirm({
                              title: 'Архивировать показатель?',
                              message: `${definition.label}. История сохранится, новые записи будут скрыты.`,
                              confirmText: 'Архивировать',
                            })
                          ) {
                            definitionMutation.mutate({
                              path: `/api/v1/workouts/diary/custom-definitions/${definition.id}`,
                              method: 'DELETE',
                            });
                          }
                        }}
                      >
                        {definition.archived ? 'Восстановить' : 'Архивировать'}
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
        {rows.isLoading ? (
          <LoadingState label="Загружаем историю замеров…" />
        ) : rows.error ? (
          <ErrorState message={(rows.error as Error).message} retry={() => void rows.refetch()} />
        ) : !rows.data?.length ? (
          <EmptyState
            title="Замеров пока нет"
            text="После первой записи здесь появится история с датами и единицами измерения."
          />
        ) : (
          <section className="measurement-history" aria-labelledby="measurement-history-title">
            <div className="measurement-history__heading">
              <h3 id="measurement-history-title">История замеров</h3>
              <span>{rows.data.length} записей</span>
            </div>
            {rows.data.map((item) => (
              <article className="measurement-history__row" key={item.id}>
                <div className="measurement-history__facts">
                  <time dateTime={item.measured_on}>
                    {formatCalendarDate(item.measured_on, {
                      day: 'numeric',
                      month: 'long',
                      year: 'numeric',
                    })}
                  </time>
                  <p>
                    {[
                      ...numeric
                        .filter((key) => item[key] != null)
                        .map(
                          (key) =>
                            `${{ weight_kg: 'Вес', chest_cm: 'Грудь', waist_cm: 'Талия', hips_cm: 'Бёдра', biceps_cm: 'Окружность плеча', thigh_cm: 'Окружность бедра' }[key]}: ${item[key]} ${key === 'weight_kg' ? 'кг' : 'см'}`,
                        ),
                      ...(item.custom_values ?? []).map(
                        (value) => `${value.label}: ${value.value} см`,
                      ),
                    ].join(' · ')}
                  </p>
                  {item.note && <p className="measurement-history__note">{item.note}</p>}
                </div>
                <div className="measurement-history__actions">
                  <Button type="button" variant="secondary" onClick={() => editMeasurement(item)}>
                    Изменить
                  </Button>
                  <Button
                    type="button"
                    variant="danger"
                    onClick={async () => {
                      if (
                        await confirm({
                          title: 'Удалить замер?',
                          message: formatCalendarDate(item.measured_on, {
                            day: 'numeric',
                            month: 'long',
                            year: 'numeric',
                          }),
                          confirmText: 'Удалить',
                        })
                      )
                        mutation.mutate({ path: `${base}/${item.id}`, method: 'DELETE' });
                    }}
                  >
                    Удалить
                  </Button>
                </div>
              </article>
            ))}
          </section>
        )}
      </fieldset>
    </>
  );
  if (embedded) {
    return (
      <section className="measurement-diary measurement-diary--embedded" id="measurement-diary">
        {content}
      </section>
    );
  }
  return (
    <Card
      className="diary-measurements-card measurement-diary"
      id="measurement-diary"
      title="Дневник замеров"
    >
      {content}
    </Card>
  );
}
