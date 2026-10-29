import { describe, expect, it } from 'vitest';
import type { ProgramTemplate } from '../../../../src/shared/api/types';
import {
  programPreviewFacts,
  programWeeklySessions,
  previewSourceSignature,
} from '../../../../src/features/programs/programPreviewFacts';

it('uses session frequency independently of the distinct cycle days', () => {
  expect(
    programWeeklySessions(
      template({ program_metadata: { days_per_week: 3, representation_days: 2 } }),
    ),
  ).toBe(3);
  expect(programWeeklySessions(template({ program_metadata: { days_per_week: '3' } }))).toBe(1);
  expect(programWeeklySessions(template({ program_metadata: { days_per_week: 9 } }))).toBe(1);
  expect(programWeeklySessions(template())).toBe(1);
  expect(
    programWeeklySessions(
      template({
        program_metadata: {
          days_per_week: 3,
          week_cycle: { schema_version: 1, length_weeks: 1, week_types: null, repeat: true },
        },
      }),
    ),
  ).toBe(1);
});

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
        exercises: [
          {
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
          },
        ],
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

  it('reports a three-day source separately from its unknown frequency', () => {
    const source = template();
    const sourceDay = source.days[0]!;
    const facts = programPreviewFacts({
      ...source,
      days: [1, 2, 3].map((dayNumber) => ({
        ...sourceDay,
        id: dayNumber,
        day_number: dayNumber,
      })),
    });
    expect(facts.find((fact) => fact.label === 'Дни')?.value).toBe('3 в составе шаблона');
    expect(facts.find((fact) => fact.label === 'Частота')?.value).toBe('Нет данных');
  });

  it('keeps a legacy template without metadata factual and unknown', () => {
    const facts = programPreviewFacts(
      template({ level: 'legacy', program_metadata: null, default_duration_weeks: 1 }),
    );
    expect(facts.find((fact) => fact.label === 'Уровень')?.value).toBe('Нет данных');
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
          exercises: [
            {
              id: 5,
              exercise_id: 20,
              exercise_title: 'Жим',
              metric_type: 'strength',
              prescribed_sets: 3,
              prescribed_reps: '8',
              rest_seconds: 90,
              has_guide: false,
              weekly_prescriptions: [
                {
                  exercise_id: 20,
                  week_number: 12,
                  prescribed_sets: 3,
                  prescribed_reps: '8',
                  rest_seconds: 90,
                },
              ],
            },
          ],
        },
      ],
    });
    const facts = programPreviewFacts(value);
    expect(facts.find((fact) => fact.label === 'Частота')?.value).toBe('3 в неделю');
    expect(facts.find((fact) => fact.label === 'Оборудование')?.value).toBe('Гантели · Скамья');
    expect(facts.find((fact) => fact.label === 'Недель в источнике')?.value).toBe('12 недель');
  });

  it('localizes the controlled equipment identifiers from the program source', () => {
    const facts = programPreviewFacts(
      template({
        program_metadata: {
          equipment: [
            'bodyweight',
            'dumbbell',
            'barbell',
            'bench',
            'rack',
            'cable',
            'machine',
            'kettlebell',
            'cardio',
            'other',
          ],
        },
      }),
    );
    expect(facts.find((fact) => fact.label === 'Оборудование')?.value).toBe(
      'Собственный вес · Гантели · Штанга · Скамья · Стойка/силовая рама · Тросовый блок · Тренажёр · Гиря · Кардиооборудование · Другое',
    );
  });

  it('deduplicates mixed identifiers and keeps user-provided names', () => {
    const facts = programPreviewFacts(
      template({
        program_metadata: {
          equipment: ['barbell', 'Штанга', 'rack', 'rack', 'Домашний турник'],
        },
      }),
    );
    expect(facts.find((fact) => fact.label === 'Оборудование')?.value).toBe(
      'Штанга · Стойка/силовая рама · Домашний турник',
    );
  });

  it('does not expose unknown technical identifiers and reports incomplete values honestly', () => {
    expect(
      programPreviewFacts(template({ program_metadata: { equipment: ['sandbag'] } })).find(
        (fact) => fact.label === 'Оборудование',
      )?.value,
    ).toBe('Неизвестное оборудование');
    expect(
      programPreviewFacts(template({ program_metadata: { equipment: ['barbell', ''] } })).find(
        (fact) => fact.label === 'Оборудование',
      )?.value,
    ).toBe('Нет данных');
  });

  it('uses explicit assignment schedule and duration, with metadata as a level fallback', () => {
    const facts = programPreviewFacts(
      template({
        level: 'legacy',
        program_metadata: { level: 'advanced' },
        assigned_program_duration_weeks: 4,
        assigned_program_schedule_weekdays: [0, 2, 4],
      }),
    );
    expect(facts.find((fact) => fact.label === 'Частота')).toMatchObject({
      value: '3 в неделю',
      source: 'Расписание назначения',
    });
    expect(facts.find((fact) => fact.label === 'Уровень')?.value).toBe('Продвинутый');
    expect(facts.find((fact) => fact.label === 'Срок назначения')?.value).toBe('4 недели');
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
    const facts = programPreviewFacts(
      template({
        program_metadata: { days_per_week: '4', equipment: ['Гантели', null] },
      }),
    );
    expect(facts.find((fact) => fact.label === 'Частота')?.value).toBe('Нет данных');
    expect(facts.find((fact) => fact.label === 'Оборудование')?.value).toBe('Нет данных');
  });
});
