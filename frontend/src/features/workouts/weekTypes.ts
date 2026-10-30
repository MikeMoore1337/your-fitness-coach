import type { ApiSchemas } from '../../shared/api/types';

export type WeekType = ApiSchemas['WeekTypeTrainingAnalyticsResponse']['week_type'];

export const weekTypeLabels: Record<WeekType, string> = {
  light: 'Лёгкая',
  medium: 'Средняя',
  heavy: 'Тяжёлая',
};

export const weekTypeGenitive: Record<WeekType, string> = {
  light: 'лёгкого',
  medium: 'среднего',
  heavy: 'тяжёлого',
};
