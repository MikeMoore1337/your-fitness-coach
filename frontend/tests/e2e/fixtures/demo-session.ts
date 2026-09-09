import type { DemoScenario, DemoSessionSnapshot } from '../../../src/features/demo/demoApi';

function cabinetFixture(scenario: DemoScenario): DemoSessionSnapshot['cabinet'] {
  return {
    today: {
      title: scenario === 'trainer' ? 'Результат клиента готов к разбору' : 'План на сегодня',
      summary: 'Подготовленный связный контекст',
      status_label: 'Нужно действие',
      completed_days: 3,
      planned_days: 5,
    },
    nutrition: {
      calories: 1160,
      calorie_target: 2150,
      protein_g: 82,
      protein_target_g: 145,
      meals_logged: 2,
      item_added: false,
      recent_item: {
        name: 'Овсяная каша с бананом и греческим йогуртом',
        serving: '320 г · недавний продукт',
        calories: 428,
        protein_g: 24,
      },
    },
    progress: {
      workouts_completed: 11,
      latest_volume_kg: 6220,
      volume_change_percent: 4.2,
      nutrition_days_logged: 5,
      nutrition_completion_percent: 54,
      summary: 'Итог использует только подтверждённые записи.',
    },
    trainer: null,
    meaningful_action_completed: false,
    conversion_title:
      scenario === 'nutrition'
        ? 'Настройте дневник питания под себя'
        : scenario === 'trainer'
          ? 'Начните работать с реальными клиентами'
          : 'Ведите настоящую историю тренировок',
  };
}

export function demoFixture(scenario: DemoScenario): DemoSessionSnapshot {
  const base = {
    capability: 'demo' as const,
    scenario,
    fixture_version: 'demo-curated-v1' as const,
    revision: 1,
    expires_at: '2026-08-24T12:30:00Z',
    cabinet: cabinetFixture(scenario),
  };
  if (scenario === 'nutrition') {
    return {
      ...base,
      state: {
        kind: 'nutrition',
        screen: 'diary',
        date_label: 'Сегодня · подготовленный дневник',
        item_added: false,
        recent_item: {
          name: 'Овсяная каша с бананом и греческим йогуртом',
          serving: '320 г · недавний продукт',
          calories: 428,
          protein_g: 24,
        },
        calories: 1160,
        calorie_target: 2150,
        protein_g: 82,
        protein_target_g: 145,
        meals_logged: 2,
      },
    };
  }
  if (scenario === 'trainer') {
    const trainerState = {
      kind: 'trainer' as const,
      screen: 'client' as const,
      client_name: 'Алексей Воронов — подготовленный демо-клиент',
      context_label: 'Последняя тренировка · сегодня, 18:40',
      workout_title: 'Ноги и корпус · неделя 4',
      facts: [
        { label: 'Выполнено', value: '6 из 6 упражнений' },
        { label: 'Объём', value: '6 840 кг' },
        { label: 'Самочувствие', value: '8 из 10' },
        { label: 'Следующий ориентир', value: '+2,5 кг в приседе' },
      ],
      comment: null,
    };
    return {
      ...base,
      state: trainerState,
      cabinet: { ...base.cabinet, trainer: trainerState },
    };
  }
  return {
    ...base,
    state: {
      kind: 'self_training',
      screen: 'today',
      workout_title: 'Верх тела · уверенный старт',
      workout_subtitle: 'Подготовленная тренировка на сегодня',
      completed_sets: 2,
      total_sets: 3,
      exercises: [
        {
          name: 'Жим гантелей лёжа с контролируемой паузой',
          prescription: '3 × 10 · 18 кг · отдых 90 сек.',
          status: 'current',
        },
        {
          name: 'Тяга верхнего блока нейтральным хватом',
          prescription: '3 × 12 · 40 кг · отдых 75 сек.',
          status: 'next',
        },
      ],
      duration_minutes: 0,
      total_volume_kg: 0,
      progress_change_percent: 0,
    },
  };
}
