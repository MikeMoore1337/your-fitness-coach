import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProgramRecommendation } from '../../../../src/features/programs/ProgramRecommendation';

const authState = vi.hoisted(() => ({ profile: null as Record<string, unknown> | null }));
const feedback = vi.hoisted(() => ({ confirm: vi.fn(async () => true) }));

vi.mock('../../../../src/app/AuthProvider', () => ({
  useAuth: () => ({ user: { profile: authState.profile } }),
}));
vi.mock('../../../../src/shared/ui/FeedbackProvider', () => ({
  useFeedback: () => feedback,
}));

const preview = {
  status: 'preview',
  selection_policy_version: 'program_generator_v1',
  input_fingerprint: 'fingerprint',
  message: 'Предпросмотр готов.',
  draft_token: 'signed-draft',
  source: {
    template_id: 20,
    slug: 'full-body',
    title: 'Каноническая программа',
    goal: 'recomposition',
    level: 'beginner',
    split_type: 'full_body',
    provenance_type: 'YFC_GENERIC',
  },
  program: {
    title: 'Каноническая программа',
    goal: 'recomposition',
    level: 'beginner',
    split_type: 'full_body',
    estimated_duration_minutes: 52,
    days: [
      {
        day_number: 1,
        title: 'Всё тело',
        estimated_duration_minutes: 52,
        exercises: [
          {
            exercise_id: 11,
            source_exercise_id: 11,
            exercise_title: 'Приседание',
            metric_type: 'strength',
            prescribed_sets: 3,
            prescribed_reps: '8-10',
            rest_seconds: 90,
            prescription: null,
            group_kind: null,
          },
        ],
      },
    ],
  },
  fit_reasons: ['Цель и опыт совместимы.'],
  tradeoffs: ['Длительность — ориентир.'],
  adaptations: [],
  reason_codes: [],
  active_program: null,
};

const confirmed = {
  status: 'confirmed',
  idempotent: false,
  assigned_program_id: 44,
  workouts_created: 1,
  template: {
    id: 45,
    title: 'Каноническая программа',
    provenance_type: 'SOURCE_ADAPTATION',
    days: [],
  },
};

function renderWizard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const onConfirmed = vi.fn();
  render(
    <QueryClientProvider client={queryClient}>
      <ProgramRecommendation open onConfirmed={onConfirmed} onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  );
  return { onConfirmed };
}

function installFetch(response: unknown = preview) {
  const calls: RequestInit[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes('body-priority-options')) {
      return new Response(JSON.stringify({ items: [{ id: 'back', name: 'Спина' }] }), {
        status: 200,
      });
    }
    if (url.includes('/programs/exercises')) {
      return new Response(JSON.stringify([{ id: 11, title: 'Приседание' }]), { status: 200 });
    }
    calls.push(init ?? {});
    if (url.includes('/generator/confirm'))
      return new Response(JSON.stringify(confirmed), { status: 200 });
    return new Response(JSON.stringify(response), { status: 200 });
  });
  return calls;
}

async function reachFinalStep() {
  fireEvent.click(screen.getByRole('radio', { name: /Рекомпозиция/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Далее' }));
  fireEvent.click(screen.getByRole('radio', { name: /Начинаю/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Далее' }));
  fireEvent.click(screen.getByRole('radio', { name: /^3тренировки/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Далее' }));
  fireEvent.click(screen.getByRole('radio', { name: /60 минут/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Далее' }));
  fireEvent.click(screen.getByRole('radio', { name: /Дома/ }));
}

describe('ProgramRecommendation deterministic generator flow', () => {
  beforeEach(() => {
    authState.profile = null;
    feedback.confirm.mockClear();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('collects required inputs and sends canonical preview payload', async () => {
    const calls = installFetch();
    renderWizard();

    expect(screen.getByRole('button', { name: 'Далее' })).toBeDisabled();
    await reachFinalStep();
    fireEvent.click(screen.getByRole('button', { name: 'Показать preview' }));

    expect(
      await screen.findByRole('heading', { level: 3, name: 'Каноническая программа' }),
    ).toBeInTheDocument();
    const request = calls.find((item) => String(item.method) === 'POST');
    expect(JSON.parse(String(request?.body))).toMatchObject({
      goal: 'recomposition',
      experience: 'beginner',
      days_per_week: 3,
      preferred_session_duration_minutes: 60,
      training_location: 'home',
      available_equipment_ids: [],
    });
  });

  it('keeps answers when returning from preview and renders reasons, trade-offs and adaptations', async () => {
    const result = {
      ...preview,
      adaptations: [
        {
          code: 'equipment_substitution',
          message: 'Упражнение заменено канонически.',
          day_number: 1,
          source_exercise_id: 11,
          replacement_exercise_id: 12,
        },
      ],
    };
    installFetch(result);
    renderWizard();
    await reachFinalStep();
    fireEvent.click(screen.getByRole('button', { name: 'Показать preview' }));
    expect(await screen.findByText('Упражнение заменено канонически.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Изменить параметры' }));
    expect(screen.getByRole('radio', { name: /Дома/ })).toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Назад' }));
    expect(screen.getByRole('radio', { name: /60 минут/ })).toBeChecked();
  });

  it('shows a bounded no-compatible state with actionable reason', async () => {
    installFetch({
      ...preview,
      status: 'no_compatible',
      draft_token: null,
      program: null,
      source: null,
      reason_codes: ['duration_incompatible'],
      fit_reasons: [],
      tradeoffs: [],
      adaptations: [],
      message: 'Не удалось подобрать программу.',
    });
    renderWizard();
    await reachFinalStep();
    fireEvent.click(screen.getByRole('button', { name: 'Показать preview' }));

    expect(
      await screen.findByRole('heading', { name: 'Не удалось подобрать программу' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/длительность несовместима/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Изменить параметры' })).toBeInTheDocument();
  });

  it('confirms once and shows the persisted state', async () => {
    installFetch();
    const { onConfirmed } = renderWizard();
    await reachFinalStep();
    fireEvent.click(screen.getByRole('button', { name: 'Показать preview' }));
    await screen.findByRole('heading', { level: 3, name: 'Каноническая программа' });
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить программу' }));

    expect(
      await screen.findByText(
        'Программа подтверждена и назначена через существующий lifecycle Product v4.',
      ),
    ).toBeInTheDocument();
    expect(onConfirmed).toHaveBeenCalledTimes(1);
  });

  it('disables confirmation for trainer-owned active programs', async () => {
    installFetch({
      ...preview,
      active_program: {
        program_id: 3,
        revision_number: 2,
        status: 'active',
        assigned_by_user_id: 9,
        trainer_owned: true,
      },
    });
    renderWizard();
    await reachFinalStep();
    fireEvent.click(screen.getByRole('button', { name: 'Показать preview' }));

    expect(await screen.findByText(/назначенная тренером/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Подтвердить программу' })).toBeDisabled();
  });

  it('protects confirm from duplicate clicks while the request is pending', async () => {
    const calls = installFetch();
    const fetchMock = vi.mocked(globalThis.fetch);
    renderWizard();
    await reachFinalStep();
    fireEvent.click(screen.getByRole('button', { name: 'Показать preview' }));
    await screen.findByRole('heading', { level: 3, name: 'Каноническая программа' });
    fetchMock.mockImplementationOnce(() => new Promise<Response>(() => undefined));
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить программу' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Сохраняем…' })).toBeDisabled());
    expect(calls.length).toBeGreaterThan(0);
  });
});
