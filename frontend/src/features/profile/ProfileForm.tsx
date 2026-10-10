import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useAuth } from '../../app/AuthProvider';
import { api } from '../../shared/api/client';
import type { ApiSchemas, User, UserProfileUpdate } from '../../shared/api/types';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Card, DisclosureIcon } from '../../shared/ui/common';
import { detectedTimeZone } from '../../shared/dateTime';
import { usePersistentState } from '../../shared/storage';
import { profileDraftStorageKey } from '../../shared/userScopedStorage';
import { getTimezoneOptions } from './timezones';
import { DateInput } from '../../shared/ui/PickerInput';
import { profileGoals } from './goals';
import { BodyPriorityPicker, isBodyPriorityComplete } from './BodyPriorityPicker';
import { TrainingPreferencesForm } from './TrainingPreferencesForm';
import { Icon } from '../../shared/ui/Icon';
import { AccountAvatar } from '../../shared/account/AccountIdentity';
import { AvatarSettings } from './AvatarSettings';

const emptyProfile: UserProfileUpdate = {
  full_name: '',
  birth_date: null,
  goal: null,
  level: null,
  height_cm: null,
  weight_kg: null,
  workouts_per_week: 3,
  cardio_trainings_per_week: 0,
  resting_heart_rate: null,
  body_priority: null,
  timezone: detectedTimeZone(),
};

function profileFormFromUser(user: User | null | undefined): UserProfileUpdate {
  return user?.profile
    ? {
        ...emptyProfile,
        full_name: user.profile.full_name,
        birth_date: user.profile.birth_date,
        goal: (user.profile.goal as UserProfileUpdate['goal']) ?? null,
        level: (user.profile.level as UserProfileUpdate['level']) ?? null,
        height_cm: user.profile.height_cm,
        weight_kg: user.profile.weight_kg,
        workouts_per_week: user.profile.workouts_per_week,
        cardio_trainings_per_week: user.profile.cardio_trainings_per_week,
        resting_heart_rate: user.profile.resting_heart_rate,
        body_priority: user.profile.body_priority,
        timezone: user.profile.timezone,
      }
    : emptyProfile;
}

const cardioRecommendationDescriptions = {
  fat_loss:
    'Рекомендуемый диапазон для продолжительного кардио с акцентом на расход энергии и сохранение восстановления.',
  recomposition:
    'Умеренное кардио, которое помогает контролировать энергозатраты и поддерживать выносливость без излишней нагрузки на восстановление после силовых тренировок.',
  maintenance:
    'Комфортная умеренная нагрузка для поддержания аэробной формы, здоровья и общей активности.',
  muscle_gain:
    'Лёгкое или умеренное кардио для поддержания выносливости с минимальной дополнительной нагрузкой на восстановление и силовые тренировки.',
} as const;

type ProfileFieldErrors = Partial<
  Record<
    | 'birth_date'
    | 'goal'
    | 'level'
    | 'height_cm'
    | 'weight_kg'
    | 'workouts_per_week'
    | 'cardio_trainings_per_week'
    | 'resting_heart_rate',
    string
  >
>;

function ageOn(date: Date, birthDate: Date): number {
  let age = date.getFullYear() - birthDate.getFullYear();
  const birthdayPassed =
    date.getMonth() > birthDate.getMonth() ||
    (date.getMonth() === birthDate.getMonth() && date.getDate() >= birthDate.getDate());
  if (!birthdayPassed) age -= 1;
  return age;
}

function birthDateError(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return 'Укажите дату рождения полностью.';
  const birthDate = new Date(`${value}T12:00:00`);
  if (Number.isNaN(birthDate.getTime())) return 'Укажите корректную дату рождения.';
  const age = ageOn(new Date(), birthDate);
  if (age < 10 || age > 100) return 'Возраст должен быть от 10 до 100 лет.';
  return undefined;
}

function rangeError(
  value: number | null | undefined,
  min: number,
  max: number,
  message: string,
  integer = false,
): string | undefined {
  if (value == null) return undefined;
  if (
    !Number.isFinite(value) ||
    value < min ||
    value > max ||
    (integer && !Number.isInteger(value))
  )
    return message;
  return undefined;
}

export function validateProfileForm(form: UserProfileUpdate): ProfileFieldErrors {
  return {
    birth_date: birthDateError(form.birth_date),
    goal: form.goal ? undefined : 'Выберите основную цель.',
    level: form.level ? undefined : 'Выберите уровень подготовки.',
    height_cm: rangeError(form.height_cm, 100, 250, 'Укажите рост от 100 до 250 см.'),
    weight_kg: rangeError(form.weight_kg, 20, 350, 'Укажите вес от 20 до 350 кг.'),
    workouts_per_week: rangeError(
      form.workouts_per_week,
      0,
      14,
      'Укажите целое число от 0 до 14.',
      true,
    ),
    cardio_trainings_per_week: rangeError(
      form.cardio_trainings_per_week,
      0,
      14,
      'Укажите целое число от 0 до 14.',
      true,
    ),
    resting_heart_rate: rangeError(
      form.resting_heart_rate,
      30,
      120,
      'Укажите целое число от 30 до 120 уд/мин.',
      true,
    ),
  };
}

export function ProfileForm() {
  const { user, reloadUser } = useAuth();
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const [avatarEditorOpen, setAvatarEditorOpen] = useState(false);
  const [validationErrors, setValidationErrors] = useState<ProfileFieldErrors>({});
  const [form, setForm, clearDraft] = usePersistentState<UserProfileUpdate>(
    profileDraftStorageKey(user?.id ?? 'anonymous'),
    () => profileFormFromUser(user),
  );
  const [persistedSnapshot, setPersistedSnapshot] = useState(() =>
    JSON.stringify(profileFormFromUser(user)),
  );
  const formIsDirty = JSON.stringify(form) !== persistedSnapshot;
  const formIsValid =
    !Object.values(validateProfileForm(form)).some(Boolean) &&
    isBodyPriorityComplete(form.body_priority);
  const timezoneOptions = getTimezoneOptions(form.timezone);
  const validBirthDate = Boolean(form.birth_date) && !birthDateError(form.birth_date);
  const validRestingHeartRate =
    form.resting_heart_rate == null ||
    (form.resting_heart_rate >= 30 && form.resting_heart_rate <= 120);
  const heartRatePreview = useQuery({
    queryKey: ['heart-rate-preview', form.birth_date, form.resting_heart_rate, form.goal],
    queryFn: () =>
      api<ApiSchemas['HeartRatePreviewResponse']>('/api/v1/me/profile/heart-rates/preview', {
        method: 'POST',
        body: {
          birth_date: form.birth_date,
          resting_heart_rate: form.resting_heart_rate,
          goal: form.goal,
        },
      }),
    enabled: validBirthDate && validRestingHeartRate,
    retry: false,
  });
  const heartRate = heartRatePreview.data;
  const latestBirthDate = new Date();
  latestBirthDate.setFullYear(latestBirthDate.getFullYear() - 10);
  const earliestBirthDate = new Date();
  earliestBirthDate.setFullYear(earliestBirthDate.getFullYear() - 100);

  const mutation = useMutation({
    mutationFn: () => api<User>('/api/v1/me/profile', { method: 'PATCH', body: form }),
    onSuccess: async () => {
      setPersistedSnapshot(JSON.stringify(form));
      clearDraft();
      await reloadUser();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workout'] }),
        queryClient.invalidateQueries({ queryKey: ['notifications'] }),
      ]);
      toast('Профиль сохранён');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  const numberValue = (value: string) => (value === '' ? null : Number(value));
  const avatarSource = user?.custom_avatar
    ? 'Используется свой аватар'
    : user?.photo_url
      ? 'Используется фото из способа входа'
      : 'Используется нейтральный emoji';
  const displayName =
    user?.profile?.full_name || user?.first_name || user?.username || 'Пользователь';
  const updateField = <Key extends keyof UserProfileUpdate>(
    key: Key,
    value: UserProfileUpdate[Key],
  ) => {
    const nextForm = { ...form, [key]: value };
    setForm(nextForm);
    setValidationErrors((current) => ({
      ...current,
      [key]: validateProfileForm(nextForm)[key as keyof ProfileFieldErrors],
    }));
    mutation.reset();
  };
  return (
    <>
      <Card
        className="profile-primary-card"
        family="neutral"
        id="profile-personal"
        title={
          <>
            <Icon name="nav-profile" size={20} /> Личные данные и фитнес-профиль
          </>
        }
        description="Обновляйте данные, которые помогают подбирать программу и показывать корректные даты."
        collapsible
      >
        <form
          className="stack profile-form"
          noValidate
          aria-busy={mutation.isPending}
          onSubmit={(event) => {
            event.preventDefault();
            const errors = validateProfileForm(form);
            setValidationErrors(errors);
            const firstInvalidField = Object.entries(errors).find(([, message]) => message)?.[0];
            if (firstInvalidField) {
              window.requestAnimationFrame(() =>
                document.getElementById(`profile-${firstInvalidField}`)?.focus(),
              );
              return;
            }
            if (!isBodyPriorityComplete(form.body_priority)) {
              toast('Выберите хотя бы одну приоритетную мышечную группу', 'error');
              return;
            }
            mutation.mutate();
          }}
        >
          <section className="profile-form-section" aria-labelledby="profile-personal-title">
            <div className="profile-form-section__head">
              <h3 id="profile-personal-title">
                <Icon name="nav-profile" size={20} /> Личные данные
              </h3>
              <p>
                Аватар, имя, дата рождения и часовой пояс используются только в вашем рабочем
                контексте.
              </p>
            </div>
            {user && (
              <div className="profile-avatar-setting">
                <AccountAvatar
                  className="profile-avatar-setting__avatar"
                  customAvatarVersion={user.custom_avatar?.updated_at}
                  name={displayName}
                  photoUrl={user.photo_url}
                />
                <div className="profile-avatar-setting__copy">
                  <strong>Фото профиля</strong>
                  <span>{avatarSource}</span>
                </div>
                <button
                  type="button"
                  className="secondary profile-avatar-setting__action"
                  aria-label="Изменить аватар"
                  aria-haspopup="dialog"
                  onClick={() => setAvatarEditorOpen(true)}
                >
                  Изменить
                </button>
              </div>
            )}
            <div className="form-grid profile-form-grid profile-form-grid--personal">
              <label className="field">
                <span>Имя</span>
                <input
                  id="profile-full_name"
                  value={form.full_name ?? ''}
                  maxLength={128}
                  autoComplete="name"
                  onChange={(event) => updateField('full_name', event.target.value)}
                />
              </label>
              <label className="field">
                <span>Дата рождения</span>
                <DateInput
                  id="profile-birth_date"
                  aria-label="Дата рождения"
                  controlClassName="profile-birth-date-control"
                  min={earliestBirthDate.toISOString().slice(0, 10)}
                  max={latestBirthDate.toISOString().slice(0, 10)}
                  value={form.birth_date ?? ''}
                  aria-invalid={Boolean(validationErrors.birth_date)}
                  aria-describedby={
                    validationErrors.birth_date
                      ? 'profile-birth_date-error'
                      : 'profile-birth_date-hint'
                  }
                  onChange={(event) => updateField('birth_date', event.target.value || null)}
                />
                {validationErrors.birth_date ? (
                  <small className="field-error" id="profile-birth_date-error" role="alert">
                    {validationErrors.birth_date}
                  </small>
                ) : (
                  <small className="field-hint" id="profile-birth_date-hint">
                    Нужна для расчёта пульсовых зон по Танаки.
                  </small>
                )}
              </label>
              <label className="field">
                <span>Часовой пояс</span>
                <select
                  id="profile-timezone"
                  value={form.timezone ?? ''}
                  onChange={(event) => updateField('timezone', event.target.value)}
                >
                  {timezoneOptions.map((timezone) => (
                    <option value={timezone} key={timezone}>
                      {timezone}
                    </option>
                  ))}
                </select>
                <small className="field-hint">Для дат тренировок и времени уведомлений.</small>
              </label>
            </div>
          </section>

          <section
            className="profile-form-section"
            id="profile-fitness"
            aria-labelledby="profile-fitness-title"
          >
            <div className="profile-form-section__head">
              <h3 id="profile-fitness-title">
                <Icon name="nav-plan" size={20} /> Цели и параметры
              </h3>
              <p>Цель, уровень и частота тренировок участвуют в рекомендации программы.</p>
            </div>
            <div className="form-grid profile-form-grid profile-form-grid--fitness">
              <label className="field">
                <span>Цель</span>
                <select
                  id="profile-goal"
                  aria-label="Цель"
                  value={form.goal ?? ''}
                  aria-invalid={Boolean(validationErrors.goal)}
                  aria-describedby={
                    validationErrors.goal
                      ? 'profile-goal-value profile-goal-error'
                      : 'profile-goal-value'
                  }
                  onChange={(event) =>
                    updateField('goal', event.target.value as UserProfileUpdate['goal'])
                  }
                >
                  <option value="" disabled>
                    Выберите цель
                  </option>
                  {profileGoals.map((option) => (
                    <option value={option.value} key={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <small className="field-hint" id="profile-goal-value">
                  {profileGoals.find((option) => option.value === form.goal)?.label ??
                    'Выберите цель из списка.'}
                </small>
                {validationErrors.goal && (
                  <small className="field-error" id="profile-goal-error" role="alert">
                    {validationErrors.goal}
                  </small>
                )}
              </label>
              <label className="field">
                <span>Уровень подготовки</span>
                <select
                  id="profile-level"
                  aria-label="Уровень подготовки"
                  value={form.level ?? ''}
                  aria-invalid={Boolean(validationErrors.level)}
                  aria-describedby={validationErrors.level ? 'profile-level-error' : undefined}
                  onChange={(event) =>
                    updateField('level', event.target.value as UserProfileUpdate['level'])
                  }
                >
                  <option value="" disabled>
                    Выберите уровень
                  </option>
                  <option value="beginner">Начальный</option>
                  <option value="intermediate">Средний</option>
                  <option value="advanced">Продвинутый</option>
                </select>
                {validationErrors.level && (
                  <small className="field-error" id="profile-level-error" role="alert">
                    {validationErrors.level}
                  </small>
                )}
              </label>
              <label className="field">
                <span>Силовых тренировок в неделю</span>
                <input
                  id="profile-workouts_per_week"
                  aria-label="Силовых тренировок в неделю"
                  type="number"
                  inputMode="numeric"
                  min="0"
                  max="14"
                  step="1"
                  value={form.workouts_per_week ?? ''}
                  aria-invalid={Boolean(validationErrors.workouts_per_week)}
                  aria-describedby={
                    validationErrors.workouts_per_week
                      ? 'profile-workouts_per_week-error'
                      : undefined
                  }
                  onChange={(event) =>
                    updateField('workouts_per_week', numberValue(event.target.value))
                  }
                />
                {validationErrors.workouts_per_week && (
                  <small className="field-error" id="profile-workouts_per_week-error" role="alert">
                    {validationErrors.workouts_per_week}
                  </small>
                )}
              </label>
              <label className="field">
                <span>Рост, см</span>
                <input
                  id="profile-height_cm"
                  aria-label="Рост, см"
                  type="number"
                  inputMode="numeric"
                  min="100"
                  max="250"
                  step="1"
                  value={form.height_cm ?? ''}
                  aria-invalid={Boolean(validationErrors.height_cm)}
                  aria-describedby={
                    validationErrors.height_cm ? 'profile-height_cm-error' : undefined
                  }
                  onChange={(event) => updateField('height_cm', numberValue(event.target.value))}
                />
                {validationErrors.height_cm && (
                  <small className="field-error" id="profile-height_cm-error" role="alert">
                    {validationErrors.height_cm}
                  </small>
                )}
              </label>
              <label className="field">
                <span>Вес, кг</span>
                <input
                  id="profile-weight_kg"
                  aria-label="Вес, кг"
                  type="number"
                  inputMode="decimal"
                  min="20"
                  max="350"
                  step="0.1"
                  value={form.weight_kg ?? ''}
                  aria-invalid={Boolean(validationErrors.weight_kg)}
                  aria-describedby={
                    validationErrors.weight_kg ? 'profile-weight_kg-error' : undefined
                  }
                  onChange={(event) => updateField('weight_kg', numberValue(event.target.value))}
                />
                {validationErrors.weight_kg && (
                  <small className="field-error" id="profile-weight_kg-error" role="alert">
                    {validationErrors.weight_kg}
                  </small>
                )}
              </label>
              <label className="field">
                <span>Кардио в неделю</span>
                <input
                  id="profile-cardio_trainings_per_week"
                  aria-label="Кардио в неделю"
                  type="number"
                  inputMode="numeric"
                  min="0"
                  max="14"
                  step="1"
                  value={form.cardio_trainings_per_week ?? ''}
                  aria-invalid={Boolean(validationErrors.cardio_trainings_per_week)}
                  aria-describedby={
                    validationErrors.cardio_trainings_per_week
                      ? 'profile-cardio_trainings_per_week-error'
                      : undefined
                  }
                  onChange={(event) =>
                    updateField('cardio_trainings_per_week', numberValue(event.target.value))
                  }
                />
                {validationErrors.cardio_trainings_per_week && (
                  <small
                    className="field-error"
                    id="profile-cardio_trainings_per_week-error"
                    role="alert"
                  >
                    {validationErrors.cardio_trainings_per_week}
                  </small>
                )}
              </label>
            </div>
            <BodyPriorityPicker
              value={form.body_priority}
              onChange={(body_priority) => updateField('body_priority', body_priority)}
            />
          </section>

          <details className="profile-form-advanced">
            <summary>
              <span>
                <strong>Пульс и кардио-ориентиры</strong>
                <small>Необязательные параметры для расчёта пульсовых зон</small>
              </span>
              <DisclosureIcon />
            </summary>
            <div className="profile-form-advanced__body">
              <label className="field profile-form-advanced__field">
                <span>Средний пульс в покое, уд/мин</span>
                <input
                  id="profile-resting_heart_rate"
                  aria-label="Средний пульс в покое, уд/мин"
                  type="number"
                  inputMode="numeric"
                  min="30"
                  max="120"
                  step="1"
                  value={form.resting_heart_rate ?? ''}
                  aria-invalid={Boolean(validationErrors.resting_heart_rate)}
                  aria-describedby={
                    validationErrors.resting_heart_rate
                      ? 'profile-resting_heart_rate-error'
                      : 'profile-resting_heart_rate-hint'
                  }
                  onChange={(event) =>
                    updateField('resting_heart_rate', numberValue(event.target.value))
                  }
                />
                {validationErrors.resting_heart_rate ? (
                  <small className="field-error" id="profile-resting_heart_rate-error" role="alert">
                    {validationErrors.resting_heart_rate}
                  </small>
                ) : (
                  <small className="field-hint" id="profile-resting_heart_rate-hint">
                    Лучше использовать среднее значение за 3–7 спокойных утренних измерений.
                  </small>
                )}
              </label>
              {heartRatePreview.isError && validBirthDate && validRestingHeartRate && (
                <div className="nutrition-warning" role="alert">
                  Проверьте значение пульса в покое. Если оно указано верно и заметно отличается от
                  вашего обычного значения, ориентируйтесь на рекомендации врача.
                </div>
              )}
              {heartRate && (
                <section className="auth-notice stack" aria-labelledby="heart-rate-zones-title">
                  <div className="metric-grid">
                    <div className="metric">
                      <span>Максимальный расчётный пульс</span>
                      <strong>{heartRate.estimated_max_heart_rate} уд/мин</strong>
                      <small>
                        Расчётное значение по возрасту. Реальный максимальный пульс может
                        отличаться.
                      </small>
                    </div>
                    {heartRate.recommended_cardio_range && (
                      <div className="metric">
                        <span>Рекомендуемый пульс для кардио</span>
                        <strong>
                          {heartRate.recommended_cardio_range.min_bpm}–
                          {heartRate.recommended_cardio_range.max_bpm} уд/мин
                        </strong>
                        {form.goal && <small>{cardioRecommendationDescriptions[form.goal]}</small>}
                      </div>
                    )}
                  </div>
                  {!heartRate.recommended_cardio_range && (
                    <p className="muted">
                      Укажите средний пульс в покое, чтобы получить более персональный расчёт и
                      рекомендуемый диапазон для кардио.
                    </p>
                  )}
                  <div>
                    <strong id="heart-rate-zones-title">Пульсовые зоны</strong>
                    <p className="muted">
                      {heartRate.heart_rate_calculation_method === 'heart_rate_reserve'
                        ? 'Персональный расчёт с учётом пульса в покое.'
                        : 'Базовый расчёт по максимальному пульсу.'}
                    </p>
                  </div>
                  <div className="list-grid">
                    {heartRate.heart_rate_zones.map((zone) => (
                      <div className="list-row" key={zone.zone}>
                        <span>
                          Зона {zone.zone}. {zone.title}
                        </span>
                        <strong>
                          {zone.min_bpm}–{zone.max_bpm} уд/мин
                        </strong>
                      </div>
                    ))}
                  </div>
                  <small className="muted">
                    Пульсовые зоны являются расчётным ориентиром. Индивидуальные физиологические
                    пороги могут отличаться.
                  </small>
                  <small className="muted">
                    Смарт-часы и фитнес-браслеты могут измерять пульс с погрешностью. Для расчёта
                    лучше использовать среднее значение за несколько дней, а не единичное измерение.
                  </small>
                </section>
              )}
            </div>
          </details>
          <div className="profile-form__save">
            <div aria-live="polite">
              {mutation.isError && (
                <p className="field-error" role="alert">
                  {(mutation.error as Error).message} Введённые данные сохранены в этом браузере.
                </p>
              )}
            </div>
            <button type="submit" disabled={mutation.isPending || !formIsDirty || !formIsValid}>
              {mutation.isPending ? 'Сохраняем…' : 'Сохранить изменения'}
            </button>
          </div>
        </form>
      </Card>
      <TrainingPreferencesForm />
      <AvatarSettings open={avatarEditorOpen} onClose={() => setAvatarEditorOpen(false)} />
    </>
  );
}
