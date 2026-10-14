import { TimeInput } from '../../shared/ui/PickerInput';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../app/AuthProvider';
import { api } from '../../shared/api/client';
import type { ApiSchemas, User } from '../../shared/api/types';
import { readStorage, removeStorage, writeStorage } from '../../shared/storage';
import { trainingPreferencesDraftStorageKey } from '../../shared/userScopedStorage';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Card, DisclosureIcon } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';

export type TrainingPreferencesDraft = ApiSchemas['TrainingPreferencesUpdate'];
type Exercise = ApiSchemas['ExerciseCatalogItem'];
type AvoidedExercise = ApiSchemas['AvoidedExercisePreference'];
type LocationProfile = ApiSchemas['TrainingLocationPreference'];

const weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const locations = [
  { value: 'gym', label: 'Тренажёрный зал' },
  { value: 'home', label: 'Дома' },
  { value: 'other', label: 'Другое место' },
] as const;
const equipment = [
  { value: 'bodyweight', label: 'Собственный вес' },
  { value: 'dumbbell', label: 'Гантели' },
  { value: 'barbell', label: 'Штанга' },
  { value: 'bench', label: 'Скамья' },
  { value: 'cable', label: 'Тросовый блок' },
  { value: 'machine', label: 'Тренажёр' },
  { value: 'kettlebell', label: 'Гиря' },
  { value: 'cardio', label: 'Кардиооборудование' },
  { value: 'other', label: 'Другое' },
] as const;
const avoidReasons = [
  { value: '', label: 'Без причины' },
  { value: 'not_enjoyable', label: 'Не нравится' },
  { value: 'uncomfortable', label: 'Некомфортно выполнять' },
  { value: 'not_confident', label: 'Не уверен(а) в технике' },
  { value: 'other', label: 'Другая причина' },
] as const;

export const emptyTrainingPreferences: TrainingPreferencesDraft = {
  preferred_duration_min: null,
  preferred_duration_max: null,
  preferred_weekdays: [],
  preferred_time: null,
  location_profiles: [],
  preferred_exercise_ids: [],
  avoided_exercises: [],
  note: null,
};

interface RevisionedDraft<T> {
  revision: string | null;
  value: T;
}

function readRevisionedDraft<T>(key: string, revision: string | null, serverValue: T): T {
  const stored = readStorage<RevisionedDraft<T> | null>(key, null);
  if (stored?.revision === revision && stored.value !== undefined) return stored.value;
  if (stored !== null) removeStorage(key);
  return serverValue;
}

export function useRevisionedDraft<T>(
  key: string,
  revision: string | null,
  serverValue: T,
): [T, (next: T) => void, (next: T) => void] {
  const [value, setValue] = useState<T>(() => readRevisionedDraft(key, revision, serverValue));
  const sourceRef = useRef({ key, revision });

  useEffect(() => {
    if (sourceRef.current.key === key && sourceRef.current.revision === revision) return;
    sourceRef.current = { key, revision };
    setValue(readRevisionedDraft(key, revision, serverValue));
  }, [key, revision, serverValue]);

  const update = (next: T) => {
    setValue(next);
    writeStorage(key, { revision, value: next } satisfies RevisionedDraft<T>);
  };
  const clear = (next: T) => {
    removeStorage(key);
    setValue(next);
  };
  return [value, update, clear];
}

export function trainingPreferencesDraft(
  value: ApiSchemas['TrainingPreferencesResponse'] | null | undefined,
): TrainingPreferencesDraft {
  return {
    preferred_duration_min: value?.preferred_duration_min ?? null,
    preferred_duration_max: value?.preferred_duration_max ?? null,
    preferred_weekdays: [...(value?.preferred_weekdays ?? [])],
    preferred_time: value?.preferred_time ?? null,
    location_profiles: (value?.location_profiles ?? []).map((profile) => ({
      location: profile.location,
      equipment_ids: [...(profile.equipment_ids ?? [])],
    })),
    preferred_exercise_ids: [...(value?.preferred_exercise_ids ?? [])],
    avoided_exercises: (value?.avoided_exercises ?? []).map((item) => ({ ...item })),
    note: value?.note ?? null,
  };
}

export function trainingPreferencesValidationError(value: TrainingPreferencesDraft): string | null {
  const minimum = value.preferred_duration_min;
  const maximum = value.preferred_duration_max;
  if (minimum != null && maximum != null && minimum > maximum) {
    return 'Минимальная длительность не может быть больше максимальной.';
  }
  return null;
}

function hasRestrictions(value: TrainingPreferencesDraft): boolean {
  return Boolean(
    value.preferred_duration_min != null ||
    value.preferred_duration_max != null ||
    value.preferred_weekdays?.length ||
    value.preferred_time ||
    value.location_profiles?.length ||
    value.preferred_exercise_ids?.length ||
    value.avoided_exercises?.length ||
    value.note?.trim(),
  );
}

function ExercisePicker({
  title,
  description,
  exercises,
  selectedIds,
  onToggle,
}: {
  title: string;
  description: string;
  exercises: Exercise[];
  selectedIds: Set<number>;
  onToggle: (exerciseId: number, checked: boolean) => void;
}) {
  const [search, setSearch] = useState('');
  const rows = useMemo(() => {
    const query = search.trim().toLocaleLowerCase('ru-RU');
    return exercises
      .filter(
        (item) =>
          selectedIds.has(item.id) ||
          !query ||
          item.title.toLocaleLowerCase('ru-RU').includes(query),
      )
      .sort((left, right) => Number(selectedIds.has(right.id)) - Number(selectedIds.has(left.id)))
      .slice(0, 24);
  }, [exercises, search, selectedIds]);
  return (
    <details className="training-preferences-disclosure">
      <summary className="yfc-disclosure-summary">
        <span>
          <strong>{title}</strong>
          <small>{description}</small>
        </span>
        <DisclosureIcon />
      </summary>
      <div className="training-preferences-disclosure__body stack">
        <label className="field">
          <span>Найти упражнение</span>
          <input
            type="search"
            enterKeyHint="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <div className="training-preferences-exercise-list">
          {rows.map((exercise) => (
            <label className="training-preferences-choice" key={exercise.id}>
              <input
                type="checkbox"
                checked={selectedIds.has(exercise.id)}
                onChange={(event) => onToggle(exercise.id, event.target.checked)}
              />
              <span>
                <strong>{exercise.title}</strong>
                <small>
                  {exercise.is_custom
                    ? 'Личное упражнение'
                    : exercise.equipment || 'Без оборудования'}
                </small>
              </span>
            </label>
          ))}
          {!rows.length && <p className="muted">По этому запросу упражнений не найдено.</p>}
        </div>
      </div>
    </details>
  );
}

export function TrainingPreferencesFields({
  value,
  onChange,
  ownerUserId,
}: {
  value: TrainingPreferencesDraft;
  onChange: (next: TrainingPreferencesDraft) => void;
  ownerUserId: number | null | undefined;
}) {
  const catalog = useQuery({
    queryKey: ['exercises'],
    queryFn: () => api<Exercise[]>('/api/v1/programs/exercises'),
  });
  const visibleExercises = useMemo(
    () =>
      (catalog.data ?? []).filter(
        (item) => item.created_by_user_id == null || item.created_by_user_id === ownerUserId,
      ),
    [catalog.data, ownerUserId],
  );
  const preferredIds = new Set(value.preferred_exercise_ids ?? []);
  const avoidedById = new Map(
    (value.avoided_exercises ?? []).map((item) => [item.exercise_id, item]),
  );
  const avoidedIds = new Set(avoidedById.keys());
  const locationById = new Map(
    (value.location_profiles ?? []).map((profile) => [profile.location, profile]),
  );
  const updateLocation = (next: LocationProfile) => {
    const profiles = (value.location_profiles ?? []).filter(
      (profile) => profile.location !== next.location,
    );
    onChange({ ...value, location_profiles: [...profiles, next] });
  };
  return (
    <div className="training-preferences-fields stack">
      <div className="training-preferences-status">
        <strong>{hasRestrictions(value) ? 'Предпочтения настроены' : 'Без ограничений'}</strong>
        <span>
          {hasRestrictions(value)
            ? 'Подбор и совместимые замены учтут сохранённый контекст.'
            : 'Подбор использует только основные параметры фитнес-профиля.'}
        </span>
        {hasRestrictions(value) && (
          <button
            type="button"
            className="secondary"
            onClick={() => onChange(emptyTrainingPreferences)}
          >
            Сбросить ограничения
          </button>
        )}
      </div>

      <details className="training-preferences-disclosure">
        <summary className="yfc-disclosure-summary">
          <span>
            <strong>Расписание</strong>
            <small>Дни и длительность · необязательно</small>
          </span>
          <DisclosureIcon />
        </summary>
        <div className="training-preferences-disclosure__body stack">
          <div className="training-preferences-duration">
            <label className="field">
              <span>От, минут</span>
              <input
                type="number"
                inputMode="numeric"
                enterKeyHint="next"
                min="10"
                max="240"
                value={value.preferred_duration_min ?? ''}
                onChange={(event) =>
                  onChange({
                    ...value,
                    preferred_duration_min:
                      event.target.value === '' ? null : Number(event.target.value),
                  })
                }
              />
            </label>
            <label className="field">
              <span>До, минут</span>
              <input
                type="number"
                inputMode="numeric"
                enterKeyHint="next"
                min="10"
                max="240"
                value={value.preferred_duration_max ?? ''}
                onChange={(event) =>
                  onChange({
                    ...value,
                    preferred_duration_max:
                      event.target.value === '' ? null : Number(event.target.value),
                  })
                }
              />
            </label>
            <label className="field">
              <span>Обычное время</span>
              <TimeInput
                value={value.preferred_time?.slice(0, 5) ?? ''}
                onChange={(event) =>
                  onChange({ ...value, preferred_time: event.target.value || null })
                }
              />
            </label>
          </div>
          <fieldset className="training-preferences-weekdays">
            <legend>Удобные дни</legend>
            <div>
              {weekdays.map((label, day) => (
                <label key={label}>
                  <input
                    type="checkbox"
                    checked={value.preferred_weekdays?.includes(day) ?? false}
                    onChange={(event) =>
                      onChange({
                        ...value,
                        preferred_weekdays: event.target.checked
                          ? [...(value.preferred_weekdays ?? []), day].sort()
                          : (value.preferred_weekdays ?? []).filter((item) => item !== day),
                      })
                    }
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </fieldset>
        </div>
      </details>

      <details className="training-preferences-disclosure">
        <summary className="yfc-disclosure-summary">
          <span>
            <strong>Места и оборудование</strong>
            <small>Можно сохранить зал, дом и другое место отдельно</small>
          </span>
          <DisclosureIcon />
        </summary>
        <div className="training-preferences-disclosure__body training-preferences-locations">
          {locations.map((location) => {
            const profile = locationById.get(location.value);
            return (
              <fieldset key={location.value}>
                <legend>
                  <label>
                    <input
                      type="checkbox"
                      checked={Boolean(profile)}
                      onChange={(event) =>
                        onChange({
                          ...value,
                          location_profiles: event.target.checked
                            ? [
                                ...(value.location_profiles ?? []),
                                { location: location.value, equipment_ids: ['bodyweight'] },
                              ]
                            : (value.location_profiles ?? []).filter(
                                (item) => item.location !== location.value,
                              ),
                        })
                      }
                    />
                    <span>{location.label}</span>
                  </label>
                </legend>
                {profile && (
                  <div className="training-preferences-equipment">
                    {equipment.map((item) => (
                      <label key={item.value}>
                        <input
                          type="checkbox"
                          checked={(profile.equipment_ids ?? []).includes(item.value)}
                          onChange={(event) =>
                            updateLocation({
                              ...profile,
                              equipment_ids: event.target.checked
                                ? [...(profile.equipment_ids ?? []), item.value]
                                : (profile.equipment_ids ?? []).filter((id) => id !== item.value),
                            })
                          }
                        />
                        <span>{item.label}</span>
                      </label>
                    ))}
                  </div>
                )}
              </fieldset>
            );
          })}
        </div>
      </details>

      <ExercisePicker
        title="Предпочитаемые упражнения"
        description="Необязательно · повышают приоритет совместимого шаблона"
        exercises={visibleExercises.filter((item) => !avoidedIds.has(item.id))}
        selectedIds={preferredIds}
        onToggle={(exerciseId, checked) =>
          onChange({
            ...value,
            preferred_exercise_ids: checked
              ? [...(value.preferred_exercise_ids ?? []), exerciseId]
              : (value.preferred_exercise_ids ?? []).filter((id) => id !== exerciseId),
          })
        }
      />
      <ExercisePicker
        title="Упражнения и движения, которых хотите избегать"
        description="Необязательно · исключаются из подбора и совместимых замен"
        exercises={visibleExercises.filter((item) => !preferredIds.has(item.id))}
        selectedIds={avoidedIds}
        onToggle={(exerciseId, checked) =>
          onChange({
            ...value,
            avoided_exercises: checked
              ? [...(value.avoided_exercises ?? []), { exercise_id: exerciseId }]
              : (value.avoided_exercises ?? []).filter((item) => item.exercise_id !== exerciseId),
          })
        }
      />
      {avoidedIds.size > 0 && (
        <div className="training-preferences-reasons">
          {[...avoidedIds].map((exerciseId) => {
            const selected = avoidedById.get(exerciseId);
            const exercise = visibleExercises.find((item) => item.id === exerciseId);
            return (
              <label className="field" key={exerciseId}>
                <span>Причина · {exercise?.title ?? `упражнение ${exerciseId}`}</span>
                <select
                  value={selected?.reason ?? ''}
                  onChange={(event) =>
                    onChange({
                      ...value,
                      avoided_exercises: (value.avoided_exercises ?? []).map((item) =>
                        item.exercise_id === exerciseId
                          ? {
                              ...item,
                              reason: (event.target.value || null) as AvoidedExercise['reason'],
                            }
                          : item,
                      ),
                    })
                  }
                >
                  {avoidReasons.map((reason) => (
                    <option value={reason.value} key={reason.value || 'none'}>
                      {reason.label}
                    </option>
                  ))}
                </select>
              </label>
            );
          })}
        </div>
      )}
      <p className="training-preferences-safety-copy">
        Укажите движения, которых хотите избегать. Это не медицинская оценка. При боли или травме
        обратитесь к специалисту.
      </p>
      <label className="field">
        <span>Дополнительная заметка</span>
        <textarea
          aria-label="Дополнительная заметка"
          rows={3}
          maxLength={500}
          value={value.note ?? ''}
          onChange={(event) => onChange({ ...value, note: event.target.value || null })}
        />
        <small className="field-hint">До 500 символов · не указывайте диагнозы.</small>
      </label>
    </div>
  );
}

export function TrainingPreferencesForm() {
  const { user, reloadUser } = useAuth();
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const response = user?.profile?.training_preferences;
  const serverDraft = useMemo(() => trainingPreferencesDraft(response), [response]);
  const [form, setForm, clearDraft] = useRevisionedDraft<TrainingPreferencesDraft>(
    trainingPreferencesDraftStorageKey(user?.id ?? 'anonymous'),
    response?.updated_at ?? null,
    serverDraft,
  );
  const [validationError, setValidationError] = useState<string | null>(null);
  const formIsDirty = JSON.stringify(form) !== JSON.stringify(serverDraft);
  const formIsValid = trainingPreferencesValidationError(form) === null;
  const mutation = useMutation({
    mutationFn: () =>
      api<User>('/api/v1/me/profile', {
        method: 'PATCH',
        body: { training_preferences: form },
      }),
    onSuccess: async (savedUser) => {
      clearDraft(trainingPreferencesDraft(savedUser.profile?.training_preferences));
      await reloadUser();
      await queryClient.invalidateQueries({ queryKey: ['program-recommendation'] });
      toast('Тренировочные предпочтения сохранены');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const editor = response?.updated_by;
  const conflict = response?.conflict;
  const updateForm = (next: TrainingPreferencesDraft) => {
    setForm(next);
    setValidationError(trainingPreferencesValidationError(next));
    mutation.reset();
  };
  return (
    <Card
      className="training-preferences-card"
      family="neutral"
      id="profile-training-preferences"
      title={
        <>
          <Icon name="nav-plan" size={20} /> Тренировочные предпочтения
        </>
      }
      description="Немедицинский контекст для подбора программы и совместимых замен."
      collapsible
    >
      <form
        className="stack"
        aria-busy={mutation.isPending}
        onSubmit={(event) => {
          event.preventDefault();
          const error = trainingPreferencesValidationError(form);
          setValidationError(error);
          if (!error) mutation.mutate();
        }}
      >
        {editor && response?.updated_at && (
          <p className="training-preferences-editor">
            Последнее изменение: {editor.role === 'self' ? 'вы' : editor.display_name} ·{' '}
            {new Date(response.updated_at).toLocaleString('ru-RU')}
          </p>
        )}
        {conflict?.status === 'review_required' && (
          <div className="training-preferences-conflict" role="status">
            <strong>Текущую программу нужно проверить</strong>
            <ul>
              {(conflict.reasons ?? []).map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
            <a className="button-link secondary" href="/app?section=programs">
              Проверить программу
            </a>
          </div>
        )}
        <TrainingPreferencesFields value={form} onChange={updateForm} ownerUserId={user?.id} />
        {validationError && (
          <p className="field-error" role="alert">
            {validationError}
          </p>
        )}
        {mutation.isError && (
          <p className="field-error" role="alert">
            {(mutation.error as Error).message} Изменения сохранены в этом браузере.
          </p>
        )}
        <button type="submit" disabled={mutation.isPending || !formIsDirty || !formIsValid}>
          {mutation.isPending ? 'Сохраняем…' : 'Сохранить предпочтения'}
        </button>
      </form>
    </Card>
  );
}
