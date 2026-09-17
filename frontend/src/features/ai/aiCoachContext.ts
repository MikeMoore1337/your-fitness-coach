export type AiCoachContextSurface = 'today' | 'workout' | 'nutrition' | 'program' | 'progress';

export type AiCoachContextDescriptor =
  | { surface: 'today' }
  | { surface: 'workout'; resourceId: number }
  | { surface: 'nutrition'; periodDays: 7 | 30 | 90 }
  | { surface: 'program' }
  | { surface: 'progress'; periodDays: 7 | 30 | 90 };

export interface AiCoachContextRequest {
  surface: AiCoachContextSurface;
  resource_id?: number;
  period_days?: 7 | 30 | 90;
}

export function toApiAiCoachContext(context: AiCoachContextDescriptor): AiCoachContextRequest {
  switch (context.surface) {
    case 'workout':
      return { surface: context.surface, resource_id: context.resourceId };
    case 'nutrition':
    case 'progress':
      return { surface: context.surface, period_days: context.periodDays };
    default:
      return { surface: context.surface };
  }
}

export function aiCoachContextLabel(context: AiCoachContextDescriptor): string {
  switch (context.surface) {
    case 'today':
      return 'Сегодня';
    case 'workout':
      return 'Эта тренировка';
    case 'nutrition':
      return `Питание за ${context.periodDays} дней`;
    case 'program':
      return 'Активная программа';
    case 'progress':
      return `Прогресс за ${context.periodDays} дней`;
  }
}
