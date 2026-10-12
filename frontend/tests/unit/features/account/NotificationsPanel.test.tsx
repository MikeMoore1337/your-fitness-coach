import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NotificationsPanel } from '../../../../src/features/account/NotificationsPanel';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

vi.mock('../../../../src/app/AuthProvider', () => ({
  useAuth: () => ({
    user: { id: 10, profile: { timezone: 'Europe/Moscow' } },
  }),
}));

const notifications = [
  {
    id: 1,
    category: 'workout_reminder',
    event_kind: 'reminder',
    title: 'Скоро тренировка',
    body: 'По плану: Тренировка A',
    created_at: '2030-01-10T08:00:00',
    scheduled_for: '2030-01-10T09:00:00',
    delivery_status: 'queued',
    sent_at: null,
    read_at: null,
    action_url: '/app?section=today',
  },
  {
    id: 2,
    category: 'nutrition_update',
    event_kind: 'transactional',
    title: 'КБЖУ пересчитаны',
    body: 'Проверьте новые ориентиры.',
    created_at: '2030-01-09T09:00:00',
    scheduled_for: '2030-01-09T09:00:00',
    delivery_status: 'sent',
    sent_at: '2030-01-09T09:00:01',
    read_at: '2030-01-09T10:00:00',
    action_url: '/app?section=nutrition',
  },
  {
    id: 3,
    category: 'custom_reminder',
    event_kind: 'reminder',
    title: 'Личная заметка',
    body: 'Не забыть воду.',
    created_at: '2030-01-08T08:00:00',
    scheduled_for: '2030-01-08T09:00:00',
    delivery_status: 'processing',
    sent_at: null,
    read_at: null,
    action_url: null,
  },
];

const reminderTemplates = [
  {
    template_key: 'meal_logging',
    version: 'v1',
    label: 'Записать приём пищи',
    purpose: 'Мягко напомнить добавить запись, когда выбранное окно ещё пусто.',
    schedule_kind: 'times',
    allowed_schedule: 'До трёх выбранных окон в выбранные дни недели.',
    quiet_hours_behavior: 'Окно внутри тихих часов пропускается без переноса на утро.',
    deep_link: 'Питание → быстрый ввод за выбранный приём пищи.',
    suppression: 'Пропускается, если в этом окне уже есть сохранённая запись питания.',
    neutral_copy: 'Можно записать приём пищи. Подробности — в приложении.',
    default_enabled: false,
    enabled: false,
    weekdays: [0, 1, 2, 3, 4, 5, 6],
    times: ['08:00:00', '13:00:00', '19:00:00'],
    window_start: null,
    window_end: null,
    interval_minutes: null,
    max_per_day: 3,
    minimum_spacing_minutes: 120,
    telegram_linked: true,
    telegram_enabled: true,
    channel_note: 'Событие появится в приложении; в Telegram придёт нейтральный текст.',
  },
  {
    template_key: 'hydration',
    version: 'v1',
    label: 'Выпить воду',
    purpose: 'Напомнить отметить воду или другой напиток в дневнике.',
    schedule_kind: 'interval',
    allowed_schedule: 'Повтор в выбранном рабочем окне с ограничением числа напоминаний в день.',
    quiet_hours_behavior: 'Слоты внутри тихих часов пропускаются без catch-up серии.',
    deep_link: 'Питание → быстрый ввод воды за текущую дату.',
    suppression: 'Ближайший слот пропускается после недавней записи гидратации.',
    neutral_copy: 'Можно выпить воды. Подробности — в приложении.',
    default_enabled: false,
    enabled: false,
    weekdays: [0, 1, 2, 3, 4, 5, 6],
    times: [],
    window_start: '09:00:00',
    window_end: '21:00:00',
    interval_minutes: 120,
    max_per_day: 6,
    minimum_spacing_minutes: 120,
    telegram_linked: true,
    telegram_enabled: true,
    channel_note: 'Событие появится в приложении; в Telegram придёт нейтральный текст.',
  },
  {
    template_key: 'movement_break',
    version: 'v1',
    label: 'Разминка / перерыв от сидения',
    purpose: 'Предложить короткий перерыв и немного подвигаться по расписанию.',
    schedule_kind: 'interval',
    allowed_schedule: 'Плановые слоты в выбранном рабочем окне; приложение не измеряет сидение.',
    quiet_hours_behavior: 'Слоты внутри тихих часов пропускаются без catch-up серии.',
    deep_link: 'Сегодня → контекст приложения для короткого перерыва.',
    suppression: 'Слот не переносится автоматически, если он был пропущен.',
    neutral_copy:
      'Пора сделать короткий перерыв и немного подвигаться. Подробности — в приложении.',
    default_enabled: false,
    enabled: false,
    weekdays: [0, 1, 2, 3, 4],
    times: [],
    window_start: '10:00:00',
    window_end: '18:00:00',
    interval_minutes: 120,
    max_per_day: 5,
    minimum_spacing_minutes: 120,
    telegram_linked: true,
    telegram_enabled: true,
    channel_note: 'Событие появится в приложении; в Telegram придёт нейтральный текст.',
  },
];

function renderPanel(onNavigate = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <NotificationsPanel onNavigate={onNavigate} />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
  return onNavigate;
}

let failTemplateSave = false;

describe('NotificationsPanel', () => {
  beforeEach(() => {
    localStorage.clear();
    failTemplateSave = false;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path === '/api/v1/notifications/web-push/config') {
        return new Response(JSON.stringify({ enabled: false, application_server_key: null }), {
          status: 200,
        });
      }
      if (path === '/api/v1/notifications/settings') {
        return new Response(
          JSON.stringify({
            workout_reminders_enabled: true,
            weekly_check_in_reminders_enabled: true,
            measurement_reminders_enabled: false,
            meal_reminders_enabled: false,
            hydration_reminders_enabled: false,
            movement_reminders_enabled: false,
            telegram_enabled: true,
            telegram_linked: true,
            reminder_hour: 9,
            quiet_hours_start: null,
            quiet_hours_end: null,
          }),
          { status: 200 },
        );
      }
      if (path === '/api/v1/notifications/templates') {
        return new Response(JSON.stringify(reminderTemplates), { status: 200 });
      }
      if (path === '/api/v1/notifications/templates/meal_logging') {
        if (failTemplateSave) {
          return new Response(JSON.stringify({ detail: 'Template service unavailable' }), {
            status: 503,
          });
        }
        return new Response(JSON.stringify({ ...reminderTemplates[0], enabled: true }), {
          status: 200,
        });
      }
      if (path === '/api/v1/notifications') {
        return new Response(JSON.stringify(notifications), { status: 200 });
      }
      if (path === '/api/v1/notifications/1/open') {
        return new Response(
          JSON.stringify({ destination: '/app?section=today', stale: false, message: null }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('разделяет каналы и открывает canonical destination через server resolver', async () => {
    const onNavigate = renderPanel();

    expect((await screen.findAllByText('Непрочитанные · 2')).length).toBeGreaterThan(0);
    const notificationCenter = screen.getByText('Центр уведомлений').closest('details');
    expect(notificationCenter).not.toHaveAttribute('open');
    fireEvent.click(screen.getByText('Центр уведомлений'));
    expect(notificationCenter).toHaveAttribute('open');
    expect(screen.getByText('В приложении')).toBeInTheDocument();
    expect(screen.getByText('Готовые шаблоны')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Готовые шаблоны'));
    expect(screen.getByText('Записать приём пищи')).toBeInTheDocument();
    expect(screen.getByText('Предстоящая тренировка')).toBeInTheDocument();
    expect(screen.queryByText('Комментарий тренера')).not.toBeInTheDocument();
    expect(screen.getByText('Личное напоминание', { selector: 'strong' })).toBeInTheDocument();
    expect(screen.queryByText('queued')).not.toBeInTheDocument();
    expect(screen.queryByText('sent')).not.toBeInTheDocument();
    expect(screen.getByText(/Создано: 9 января в 09:00/)).toBeInTheDocument();

    fireEvent.click(await screen.findByRole('button', { name: 'Открыть: Скоро тренировка' }));

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/notifications/1/open',
        expect.objectContaining({ method: 'POST' }),
      ),
    );
    await waitFor(() => expect(onNavigate).toHaveBeenCalledWith('/app?section=today'));
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/notifications/1/open',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(screen.getByText('Личная заметка').closest('button')).toBeNull();
  });

  it('сохраняет включение шаблона отдельным запросом и оставляет кнопку выключенной после успеха', async () => {
    renderPanel();

    fireEvent.click(await screen.findByText('Готовые шаблоны'));
    const toggle = await screen.findByRole('checkbox', { name: 'Включить: Записать приём пищи' });
    fireEvent.click(toggle);

    expect(screen.getByText('Окно 1')).toBeInTheDocument();
    const saveButton = screen.getByRole('button', {
      name: 'Сохранить шаблон «Записать приём пищи»',
    });
    expect(saveButton).toBeEnabled();
    fireEvent.click(saveButton);

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/notifications/templates/meal_logging',
        expect.objectContaining({
          method: 'PATCH',
          body: expect.stringContaining('"enabled":true'),
        }),
      ),
    );
    await waitFor(() => expect(saveButton).toBeDisabled());
  });

  it('сохраняет изменённый черновик и доступную кнопку после ошибки шаблона', async () => {
    failTemplateSave = true;
    renderPanel();

    fireEvent.click(await screen.findByText('Готовые шаблоны'));
    const toggle = await screen.findByRole('checkbox', { name: 'Включить: Записать приём пищи' });
    fireEvent.click(toggle);
    const saveButton = screen.getByRole('button', {
      name: 'Сохранить шаблон «Записать приём пищи»',
    });
    fireEvent.click(saveButton);

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/notifications/templates/meal_logging',
        expect.objectContaining({ method: 'PATCH' }),
      ),
    );
    await waitFor(() => expect(saveButton).toBeEnabled());
    expect(toggle).toBeChecked();
  });
});
