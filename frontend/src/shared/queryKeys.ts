import type { QueryClient } from '@tanstack/react-query';

export const queryKeys = {
  cardio: {
    all: ['cardio'] as const,
    range: (dateFrom: string, dateTo: string) => ['cardio', dateFrom, dateTo] as const,
  },
  measurements: {
    all: ['measurements'] as const,
    subject: (clientId?: number) => ['measurements', clientId ?? 'me'] as const,
    definitions: (clientId?: number) => ['measurement-definitions', clientId ?? 'me'] as const,
  },
  progress: {
    summaries: ['workout', 'progress-summary'] as const,
    summary: (periodDays: number | string) => ['workout', 'progress-summary', periodDays] as const,
    nutritionReport: (subject: number | 'me', period: string, dateFrom?: string, dateTo?: string) =>
      ['workout', 'nutrition-report', subject, period, dateFrom ?? null, dateTo ?? null] as const,
  },
  trainer: {
    attention: ['coach', 'attention'] as const,
    operationsToday: ['coach', 'operations', 'today'] as const,
    agenda: (dateFrom: string, dateTo: string) => ['coach', 'agenda', dateFrom, dateTo] as const,
    clients: ['coach', 'clients'] as const,
    clientAnalytics: (clientId: number) => ['coach', 'client', clientId, 'analytics'] as const,
    clientSummary: (clientId: number) => ['coach', 'client', clientId, 'summary'] as const,
    clientSummaries: ['coach', 'client-summaries'] as const,
    clientWorkouts: (clientId: number) => ['coach', 'client', clientId, 'workouts'] as const,
    clientCheckIns: (clientId: number) =>
      ['coach', 'client', clientId, 'weekly-check-ins'] as const,
    clientReportHandoffs: (clientId: number) =>
      ['coach', 'client', clientId, 'report-handoffs'] as const,
    clientOperations: (clientId: number) => ['coach', 'client', clientId, 'operations'] as const,
    packages: ['coach', 'packages'] as const,
    payments: ['coach', 'payments'] as const,
    tasks: ['coach', 'tasks'] as const,
  },
  workoutComments: {
    client: (workoutId: number) => ['workout', workoutId, 'comments'] as const,
    trainer: (clientId: number, workoutId: number) =>
      ['coach', 'client', clientId, 'workout', workoutId, 'comments'] as const,
  },
  nutrition: {
    diary: ['nutrition', 'diary'] as const,
    diaryDate: (diaryDate: string) => ['nutrition', 'diary', diaryDate] as const,
    currentTarget: ['nutrition', 'targets', 'current'] as const,
    targetHistory: (targetTelegramId?: number | null) =>
      ['nutrition', 'targets', 'history', targetTelegramId ?? 'me'] as const,
    hydration: ['nutrition', 'hydration'] as const,
    hydrationDate: (diaryDate: string) => ['nutrition', 'hydration', diaryDate] as const,
    recipes: ['nutrition', 'recipes'] as const,
    mealTemplates: ['nutrition', 'meal-templates'] as const,
    foodAliases: ['nutrition', 'food-aliases'] as const,
  },
  notifications: {
    all: ['notifications'] as const,
  },
  wellbeing: {
    all: ['daily-wellbeing'] as const,
    daily: (userId: number | 'anonymous', localDate: string) =>
      ['daily-wellbeing', userId, localDate] as const,
  },
};

export async function invalidateMeasurementMutation(
  queryClient: QueryClient,
  clientId?: number,
): Promise<void> {
  const invalidations = [
    queryClient.invalidateQueries({ queryKey: queryKeys.measurements.subject(clientId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.measurements.definitions(clientId) }),
  ];
  if (clientId == null) {
    invalidations.push(
      queryClient.invalidateQueries({ queryKey: queryKeys.progress.summaries }),
      queryClient.invalidateQueries({ queryKey: queryKeys.nutrition.diary }),
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all }),
    );
  } else {
    invalidations.push(
      queryClient.invalidateQueries({ queryKey: queryKeys.trainer.clientAnalytics(clientId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.trainer.clientSummary(clientId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.trainer.clientSummaries }),
      queryClient.invalidateQueries({ queryKey: queryKeys.trainer.clients }),
    );
  }
  await Promise.all(invalidations);
}

export async function invalidateNutritionSummaries(
  queryClient: QueryClient,
  clientId?: number,
): Promise<void> {
  if (clientId == null) {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.progress.summaries }),
      queryClient.invalidateQueries({ queryKey: queryKeys.nutrition.diary }),
    ]);
    return;
  }
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.trainer.clientSummary(clientId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.trainer.clientSummaries }),
    queryClient.invalidateQueries({ queryKey: queryKeys.trainer.clients }),
  ]);
}
