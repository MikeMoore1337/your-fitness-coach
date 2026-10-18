import { describe, expect, it } from 'vitest';
import type { ProgramTemplate } from '../../../../src/shared/api/types';
import {
  programPreviewFacts,
  previewSourceSignature,
} from '../../../../src/features/programs/programPreviewFacts';

function template(override: Partial<ProgramTemplate> = {}): ProgramTemplate {
  return {
    id: 42,
    title: 'Программа',
    level: 'intermediate',
    default_duration_weeks: 1,
    program_metadata: null,
    days: [
      {
        id: 1,
        title: 'Всё тело',
        day_number: 1,
        exercises: [{
          id: 4,
          exercise_id: 15,
          exercise_title: 'Жим',
          metric_type: 'strength',
          prescribed_sets: 3,
          prescribed_reps: '8-10',
          prescribed_duration_minutes: null,
          rest_seconds: 90,
          weekly_prescriptions: [],
          notes: null,
          has_guide: false,
        }],
      },
    ],
    ...override,
  } as ProgramTemplate;
}

describe('program preview factual mapping', () => {
  it('does not confuse template days with frequency and keeps unknown values unknown', () => {
    const facts = programPreviewFacts(template({ level: 'unknown', program_metadata: null }));
    expect(facts.find((fact) => fact.label === 'Дни')?.value).toBe('1 в составе шаблона');
    expect(facts.find((fact) => fact.label === 'Частота')?.value).toBe('Нет данных');
    expect(facts.find((fact) => fact.label === 'Уровень')?.value).toBe('Нет данных');
    expect(facts.find((fact) => fact.label === 'Оборудование')?.value).toBe('Нет данных');
    expect(facts.find((fact) => fact.label === 'Оценка времени')?.value).toBe('Нет данных');
    expect(facts.find((fact) => fact.label === 'Недель в источнике')?.value).toBe('Нет данных');
  });

  it('uses only explicit seed metadata and source week prescriptions', () => {
    const value = template({
      program_metadata: {
        days_per_week: 3,
        equipment: ['Гантели', 'Скамья'],
      },
      days: [
        {
          id: 1,
          title: 'День A',
          day_number: 1,
          exercises: [{
            id: 5,
            exercise_id: 20,
            exercise_title: 'Жим',
            metric_type: 'strength',
            prescribed_sets: 3,
            prescribed_reps: '8',
            rest_seconds: 90,
            has_guide: false,
            weekly_prescriptions: [{
              exercise_id: 20,
              week_number: 12,
              prescribed_sets: 3,
              prescribed_reps: '8',
              rest_seconds: 90,
            }],
          }],
        },
      ],
    });
    const facts = programPreviewFacts(value);
    expect(facts.find((fact) => fact.label === 'Частота')?.value).toBe('3 в неделю');
    expect(facts.find((fact) => fact.label === 'Оборудование')?.value).toBe('Гантели · Скамья');
    expect(facts.find((fact) => fact.label === 'Недель в источнике')?.value).toBe('12');
  });

  it('detects changed content and revision before assignment', () => {
    const original = template();
    expect(previewSourceSignature(original)).toBe(previewSourceSignature(template()));
    expect(previewSourceSignature(original)).not.toBe(
      previewSourceSignature(template({ title: 'Программа обновлена' })),
    );
    expect(previewSourceSignature(original)).not.toBe(
      previewSourceSignature(template({ current_revision_number: 2 })),
    );
  });

  it('rejects incomplete equipment and non-numeric frequency', () => {
    const facts = programPreviewFacts(template({
      program_metadata: { days_per_week: '4', equipment: ['Гантели', null] },
    }));
    expect(facts.find((fact) => fact.label === 'Частота')?.value).toBe('Нет данных');
    expect(facts.find((fact) => fact.label === 'Оборудование')?.value).toBe('Нет данных');
  });
});
