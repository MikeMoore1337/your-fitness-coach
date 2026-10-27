import { describe, expect, it } from 'vitest';
import {
  aiCoachContextLabel,
  toApiAiCoachContext,
  type AiCoachContextDescriptor,
} from '../../../../src/features/ai/aiCoachContext';

describe('AI Coach contextual descriptors', () => {
  it.each([
    [{ surface: 'today' }, 'Сегодня', { surface: 'today' }],
    [
      { surface: 'workout', resourceId: 42 },
      'Эта тренировка',
      { surface: 'workout', resource_id: 42 },
    ],
    [
      { surface: 'nutrition', periodDays: 7 },
      'Питание за 7 дней',
      { surface: 'nutrition', period_days: 7 },
    ],
    [{ surface: 'program' }, 'Активная программа', { surface: 'program' }],
    [
      { surface: 'progress', periodDays: 90 },
      'Прогресс за 90 дней',
      { surface: 'progress', period_days: 90 },
    ],
  ] as const)('keeps the %s context typed and bounded', (context, label, request) => {
    expect(aiCoachContextLabel(context as AiCoachContextDescriptor)).toBe(label);
    expect(toApiAiCoachContext(context as AiCoachContextDescriptor)).toEqual(request);
  });

  it('contains only a safe surface descriptor, never private text or a chat prompt', () => {
    const context: AiCoachContextDescriptor = { surface: 'workout', resourceId: 42 };
    const request = toApiAiCoachContext(context);
    expect(request).toEqual({ surface: 'workout', resource_id: 42 });
    expect(JSON.stringify(request)).not.toContain('private');
    expect(JSON.stringify(request)).not.toContain('comment');
    expect(JSON.stringify(request)).not.toContain('prompt');
  });
});
