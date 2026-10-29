import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProgramBuilder } from '../../../../src/features/programs/ProgramBuilder';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';
import type { ProgramTemplate } from '../../../../src/shared/api/types';

const { apiMock, reloadUser } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  reloadUser: vi.fn(),
}));

vi.mock('../../../../src/shared/api/client', () => {
  class MockApiError extends Error {
    status: number;
    body: unknown;

    constructor(message: string, status: number, body: unknown = null) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
      this.body = body;
    }
  }

  return {
    api: (...args: unknown[]) => apiMock(...args),
    ApiError: MockApiError,
  };
});

vi.mock('../../../../src/app/AuthProvider', () => ({
  useAuth: () => ({
    user: { id: 7, profile: { timezone: 'Europe/Moscow' } },
    reloadUser,
  }),
}));

const catalog = [
  {
    id: 11,
    title: 'Жим штанги лёжа',
    slug: 'bench-press',
    metric_type: 'strength',
    primary_muscle: 'Грудь',
    equipment: 'Штанга',
    primary_muscle_ids: ['chest'],
    secondary_muscle_ids: ['triceps'],
    equipment_ids: ['barbell'],
    aliases: [],
    movement_pattern: 'chest_press',
    machine_variant_tags: [],
    execution_variant_tags: ['bilateral'],
    alternatives: [],
    difficulty_level: 'beginner',
    is_custom: false,
    is_personalized: false,
    has_guide: false,
  },
  {
    id: 12,
    title: 'Велотренажёр',
    slug: 'stationary-bike',
    metric_type: 'cardio',
    primary_muscle: 'Кардио',
    equipment: 'Велотренажёр',
    primary_muscle_ids: ['cardio'],
    secondary_muscle_ids: [],
    equipment_ids: ['cardio'],
    aliases: [],
    movement_pattern: null,
    machine_variant_tags: [],
    execution_variant_tags: ['cyclic'],
    alternatives: [],
    difficulty_level: 'beginner',
    is_custom: false,
    is_personalized: false,
    has_guide: false,
  },
  {
    id: 13,
    title: 'Верхняя рычажная тяга с упором грудью',
    slug: 'lever-high-row',
    metric_type: 'strength',
    primary_muscle: 'Спина',
    equipment: 'Тренажёр',
    primary_muscle_ids: ['back'],
    secondary_muscle_ids: ['biceps', 'posterior_deltoid', 'forearms'],
    equipment_ids: ['machine'],
    aliases: ['верхняя тяга хаммер', 'high row'],
    movement_pattern: 'row',
    machine_variant_tags: ['plate_loaded', 'lever', 'independent'],
    execution_variant_tags: ['bilateral', 'unilateral'],
    alternatives: [],
    difficulty_level: 'beginner',
    is_custom: false,
    is_personalized: false,
    has_guide: true,
  },
];

function renderBuilder(props: { editingTemplate?: ProgramTemplate } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <NavigationProvider>
          <ProgramBuilder defaultOpen {...props} />
        </NavigationProvider>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

function emulateMobileEditorViewport() {
  const mobileStyle = document.createElement('style');
  mobileStyle.dataset.mobileCopyEditorTest = 'true';
  mobileStyle.textContent = '.copy-editor__mobile-days { display: block !important; }';
  document.head.append(mobileStyle);
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query === '(max-width: 1099px)',
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

describe('ProgramBuilder type-aware prescription', () => {
  beforeEach(() => {
    localStorage.clear();
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });
    apiMock.mockReset();
    reloadUser.mockReset();
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/programs/exercises') return Promise.resolve(catalog);
      if (path === '/api/v1/programs/templates') return Promise.resolve({ template: { id: 1 } });
      if (path === '/api/v1/programs/templates/9') {
        return Promise.resolve({
          ...activeTemplate,
          assigned_program_updated: true,
          future_workouts_updated: 2,
          assigned_program_revision_number: 5,
        });
      }
      throw new Error(`Unexpected API path: ${path}`);
    });
  });

  afterEach(() => {
    cleanup();
    document.querySelectorAll('[data-mobile-copy-editor-test]').forEach((node) => node.remove());
    vi.unstubAllGlobals();
  });

  it('для cardio запрашивает длительность и не отправляет силовое назначение', async () => {
    const user = userEvent.setup();
    renderBuilder();

    const picker = await screen.findByRole('combobox', { name: 'Поиск упражнения' });
    await user.click(picker);
    await user.click(screen.getByRole('option', { name: /Велотренажёр/ }));

    const duration = screen.getByRole('spinbutton', { name: 'Плановая длительность, мин' });
    const exerciseRow = duration.closest<HTMLElement>('.program-exercise-row');
    expect(exerciseRow).not.toBeNull();
    expect(duration).toHaveValue(30);
    expect(within(exerciseRow!).queryByText('Рабочие подходы')).not.toBeInTheDocument();
    expect(within(exerciseRow!).queryByText('Повторы')).not.toBeInTheDocument();
    expect(within(exerciseRow!).queryByText('Отдых, сек')).not.toBeInTheDocument();
    await user.clear(duration);
    await user.type(duration, '25');
    await user.click(screen.getByRole('button', { name: 'Создать программу' }));

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/programs/templates',
        expect.objectContaining({
          method: 'POST',
          body: expect.objectContaining({
            days: [
              expect.objectContaining({
                exercises: [
                  expect.objectContaining({
                    exercise_id: 12,
                    prescribed_sets: null,
                    prescribed_reps: null,
                    prescribed_duration_minutes: 25,
                  }),
                ],
              }),
            ],
          }),
        }),
      ),
    );
  });

  it('находит machine/lever упражнение по разговорному alias и добавляет canonical item', async () => {
    const user = userEvent.setup();
    renderBuilder();

    const picker = await screen.findByRole('combobox', { name: 'Поиск упражнения' });
    await user.type(picker, 'верхняя тяга хаммер');

    const listbox = screen.getByRole('listbox');
    const option = within(listbox).getByRole('option', {
      name: /Верхняя рычажная тяга с упором грудью/,
    });
    expect(option).toBeVisible();
    expect(within(listbox).getAllByRole('option')).toHaveLength(1);
    await user.click(option);

    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'Поиск упражнения' })).toHaveValue(
        'Верхняя рычажная тяга с упором грудью',
      ),
    );
    expect(screen.getByRole('spinbutton', { name: 'Рабочие подходы' })).toBeVisible();
  });

  it('передаёт revision активной программы и показывает подтверждение применения', async () => {
    const user = userEvent.setup();
    renderBuilder({ editingTemplate: activeTemplate });

    await user.click(await screen.findByRole('button', { name: 'Сохранить программу' }));

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/programs/templates/9',
        expect.objectContaining({
          method: 'PATCH',
          body: expect.objectContaining({ expected_revision_number: 4 }),
        }),
      ),
    );
    expect(
      await screen.findByText('Программа сохранена. Будущие тренировки обновлены'),
    ).toBeInTheDocument();
  });

  it('редактирует только выбранное упражнение и сохраняет порядок без потери назначений', async () => {
    const user = userEvent.setup();
    renderBuilder({ editingTemplate: activeTemplate });
    await screen.findByRole('combobox', { name: 'Поиск упражнения' });
    await user.click(screen.getByRole('button', { name: 'Добавить упражнение' }));
    await user.click(screen.getByRole('combobox', { name: 'Поиск упражнения' }));
    await user.click(screen.getByRole('option', { name: /Велотренажёр/ }));

    const duration = screen.getByRole('spinbutton', { name: 'Плановая длительность, мин' });
    await user.clear(duration);
    await user.type(duration, '25');
    await user.click(screen.getByRole('button', { name: 'Изменить порядок' }));
    await user.click(screen.getByRole('button', { name: 'Выше' }));

    const rows = document.querySelectorAll('.copy-editor__exercise');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Велотренажёр');
    expect(rows[1]).toHaveTextContent('Жим штанги лёжа');
    expect(screen.getAllByRole('combobox', { name: 'Поиск упражнения' })).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Сохранить программу' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/programs/templates/9',
        expect.objectContaining({
          body: expect.objectContaining({
            days: [
              expect.objectContaining({
                exercises: [
                  expect.objectContaining({ exercise_id: 12, prescribed_duration_minutes: 25 }),
                  expect.objectContaining({ exercise_id: 11, prescribed_reps: '8-10' }),
                ],
              }),
            ],
          }),
        }),
      ),
    );
  });

  it('переключает дни без потери несохранённых изменений', async () => {
    const user = userEvent.setup();
    const editingTemplate = {
      ...activeTemplate,
      days: [1, 2, 3].map((number) => ({
        ...activeTemplate.days[0],
        id: 90 + number,
        day_number: number,
        title: 'Тренировка ' + number,
        exercises: activeTemplate.days[0]!.exercises.map((exercise) => ({ ...exercise })),
      })),
    } as ProgramTemplate;
    renderBuilder({ editingTemplate });
    await screen.findByRole('combobox', { name: 'Поиск упражнения' });
    const rail = document.querySelector('.copy-editor__rail') as HTMLElement;
    await user.click(within(rail).getByRole('tab', { name: /День 2/ }));
    expect(screen.getByRole('textbox', { name: 'Название дня' })).toHaveValue('Тренировка 2');
    const titleInput = screen.getByRole('textbox', { name: 'Название дня' });
    await user.clear(titleInput);
    await user.type(titleInput, 'День с прогрессией');
    await user.click(within(rail).getByRole('tab', { name: /День 3/ }));
    await user.click(within(rail).getByRole('tab', { name: /День 2/ }));
    expect(screen.getByRole('textbox', { name: 'Название дня' })).toHaveValue('День с прогрессией');
    await user.click(screen.getByRole('button', { name: 'Сохранить программу' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/programs/templates/9',
        expect.objectContaining({
          body: expect.objectContaining({
            days: expect.arrayContaining([
              expect.objectContaining({ title: 'День с прогрессией' }),
            ]),
          }),
        }),
      ),
    );
  });

  it('даёт быстрый переход к последнему дню и не прокручивает одно-дневный цикл', async () => {
    emulateMobileEditorViewport();
    const user = userEvent.setup();
    const editingTemplate = {
      ...activeTemplate,
      days: Array.from({ length: 8 }, (_, index) => ({
        ...activeTemplate.days[0],
        id: index + 100,
        day_number: index + 1,
        title: 'Тренировка ' + (index + 1),
      })),
    } as ProgramTemplate;
    renderBuilder({ editingTemplate });
    await screen.findByRole('button', { name: 'Все дни' });
    await user.click(screen.getByRole('button', { name: 'Все дни' }));
    const chooser = screen.getByRole('dialog', { name: 'Все дни программы' });
    await user.click(within(chooser).getByRole('button', { name: /День 8/ }));
    expect(screen.getByRole('textbox', { name: 'Название дня' })).toHaveValue('Тренировка 8');
    expect(screen.getAllByText('День 8 из 8').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('button', { name: 'Следующий день' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Предыдущий день' }));
    expect(screen.getByRole('textbox', { name: 'Название дня' })).toHaveValue('Тренировка 7');
  });

  it('сортирует дни внутри «Все дни» без смены выбранной тренировки и сохраняет новый порядок', async () => {
    emulateMobileEditorViewport();
    const user = userEvent.setup();
    const editingTemplate = {
      ...activeTemplate,
      days: [1, 2, 3].map((number) => ({
        ...activeTemplate.days[0],
        id: 90 + number,
        day_number: number,
        title: 'Тренировка ' + number,
        exercises: activeTemplate.days[0]!.exercises.map((exercise) => ({ ...exercise })),
      })),
    } as ProgramTemplate;
    renderBuilder({ editingTemplate });
    const titleInput = await screen.findByRole('textbox', { name: 'Название дня' });
    await user.clear(titleInput);
    await user.type(titleInput, 'Изменённая первая');
    expect(screen.queryByRole('button', { name: 'Переместить день выше' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Переместить день ниже' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Все дни' }));
    const chooser = screen.getByRole('dialog', { name: 'Все дни программы' });
    await user.click(within(chooser).getByRole('button', { name: 'Изменить порядок' }));
    expect(
      within(chooser).getByRole('button', { name: 'Переместить день 1 раньше' }),
    ).toBeDisabled();
    expect(
      within(chooser).getByRole('button', { name: 'Переместить день 3 позже' }),
    ).toBeDisabled();

    await user.click(within(chooser).getByRole('button', { name: 'Переместить день 2 раньше' }));
    expect(titleInput).toHaveValue('Изменённая первая');
    expect(screen.getAllByText('День 2 из 3').length).toBeGreaterThan(0);
    await user.click(within(chooser).getByRole('button', { name: 'Готово' }));
    await user.click(within(chooser).getByRole('button', { name: /День 1/ }));
    expect(screen.getByRole('textbox', { name: 'Название дня' })).toHaveValue('Тренировка 2');

    await user.click(screen.getByRole('button', { name: 'Сохранить программу' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/programs/templates/9',
        expect.objectContaining({
          body: expect.objectContaining({
            days: [
              expect.objectContaining({ title: 'Тренировка 2' }),
              expect.objectContaining({ title: 'Изменённая первая' }),
              expect.objectContaining({ title: 'Тренировка 3' }),
            ],
          }),
        }),
      ),
    );
  });

  it('на desktop открывает сортировку из списка дней и возвращает фокус по Escape', async () => {
    const user = userEvent.setup();
    const editingTemplate = {
      ...activeTemplate,
      days: [1, 2].map((number) => ({
        ...activeTemplate.days[0],
        id: 90 + number,
        day_number: number,
        title: 'Тренировка ' + number,
        exercises: activeTemplate.days[0]!.exercises.map((exercise) => ({ ...exercise })),
      })),
    } as ProgramTemplate;
    renderBuilder({ editingTemplate });
    const trigger = await screen.findByRole('button', { name: 'Изменить порядок дней' });
    await user.click(trigger);
    const chooser = screen.getByRole('dialog', { name: 'Все дни программы' });
    expect(within(chooser).getByRole('button', { name: 'Готово' })).toBeInTheDocument();
    await user.click(within(chooser).getByRole('button', { name: 'Переместить день 1 позже' }));
    expect(screen.getByRole('textbox', { name: 'Название дня' })).toHaveValue('Тренировка 1');
    await user.keyboard('{Escape}');
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(screen.queryByRole('dialog', { name: 'Все дни программы' })).not.toBeInTheDocument();
  });

  it('отключает стрелки карусели для единственного дня', async () => {
    emulateMobileEditorViewport();
    renderBuilder({ editingTemplate: activeTemplate });
    await screen.findByRole('button', { name: 'Предыдущий день' });
    expect(screen.getByRole('button', { name: 'Предыдущий день' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Следующий день' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Изменить порядок дней' })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Все дни' }));
    expect(
      within(screen.getByRole('dialog', { name: 'Все дни программы' })).queryByRole('button', {
        name: 'Изменить порядок',
      }),
    ).not.toBeInTheDocument();
  });

  it('связывает разделы с собственными заголовками при двух открытых редакторах', async () => {
    const user = userEvent.setup();
    renderBuilder();
    renderBuilder({ editingTemplate: activeTemplate });
    await waitFor(() =>
      expect(screen.getAllByRole('combobox', { name: 'Поиск упражнения' })).toHaveLength(2),
    );
    const settings = screen.getAllByText('Настройки программы', { exact: true });
    expect(settings).toHaveLength(2);
    for (const summary of settings) await user.click(summary);
    const ids: string[] = [];
    for (const name of [
      'Основа программы',
      'Цель и уровень',
      'Расписание',
      'Быстрое заполнение',
      'Отдых между подходами',
    ]) {
      const sections = screen.getAllByRole('region', { name });
      expect(sections).toHaveLength(2);
      for (const section of sections) {
        const id = section.getAttribute('aria-labelledby');
        expect(id).toBeTruthy();
        ids.push(id!);
        const heading = document.getElementById(id!);
        expect(heading).toHaveTextContent(name);
        expect(section).toContainElement(heading);
      }
    }
    expect(new Set(ids).size).toBe(10);
  });
});

const activeTemplate = {
  id: 9,
  title: 'Активная программа',
  slug: 'active-program',
  goal: 'recomposition',
  level: 'intermediate',
  split_type: null,
  owner_user_id: 7,
  owner_telegram_user_id: 700,
  owner_full_name: 'Тестовый пользователь',
  created_by_user_id: 7,
  is_public: false,
  is_example: false,
  is_assigned_to_current_user: true,
  is_active_for_current_user: true,
  can_edit: true,
  assigned_by_user_id: 7,
  assigned_by_full_name: 'Тестовый пользователь',
  assigned_program_id: 9,
  assigned_program_status: 'active',
  assigned_program_start_date: '2026-10-14',
  assigned_program_duration_weeks: 3,
  assigned_program_schedule_weekdays: [1],
  current_revision_number: 4,
  assigned_program_updated: false,
  future_workouts_updated: 0,
  assigned_program_revision_number: null,
  default_duration_weeks: 1,
  provenance_type: 'CUSTOM',
  provenance: null,
  program_metadata: null,
  days: [
    {
      id: 90,
      day_number: 1,
      title: 'Силовая',
      exercises: [
        {
          id: 91,
          exercise_id: 11,
          exercise_title: 'Жим штанги лёжа',
          metric_type: 'strength',
          prescribed_sets: 3,
          prescribed_reps: '8-10',
          prescribed_duration_minutes: null,
          rest_seconds: 90,
          notes: null,
          superset_group: null,
          superset_order: null,
          prescription: null,
          group_id: null,
          group_kind: null,
          group_order: null,
          has_guide: false,
          weekly_prescriptions: [],
        },
      ],
    },
  ],
} as unknown as ProgramTemplate;
