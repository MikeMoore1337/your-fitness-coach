const workoutStatusLabels: Record<string, string> = {
  planned: 'Запланирована',
  in_progress: 'В процессе',
  completed: 'Завершена',
  skipped: 'Пропущена',
  missed: 'Нужно решить',
  cancelled: 'Отменена',
};

const notificationStatusLabels: Record<string, string> = {
  queued: 'Ожидает отправки',
  processing: 'Отправляется',
  sent: 'Отправлено',
  failed: 'Ошибка отправки',
  cancelled: 'Отменено',
};

export function workoutStatusLabel(status: string): string {
  return workoutStatusLabels[status] ?? 'Статус не определён';
}

export function notificationStatusLabel(status: string): string {
  return notificationStatusLabels[status] ?? 'Статус не определён';
}
