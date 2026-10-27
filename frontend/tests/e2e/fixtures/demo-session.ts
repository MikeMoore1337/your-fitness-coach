import type {
  DemoScenario,
  DemoSessionSnapshot,
  DemoTrainerState,
} from '../../../src/features/demo/demoApi';

const trainerClients: DemoTrainerState['clients'] = [
  {
    id: 'alexey',
    name: 'Алексей',
    status_label: 'В ритме',
    context_label: 'Последняя тренировка · сегодня, 18:40',
    workout_title: 'Ноги и корпус · неделя 4',
    facts: [
      { label: 'Выполнено', value: '6 из 6 упражнений' },
      { label: 'Объём', value: '6 840 кг' },
      { label: 'Самочувствие', value: '8 из 10' },
      { label: 'Следующий ориентир', value: '+2,5 кг в приседе' },
    ],
    comment: null,
  },
  {
    id: 'maria',
    name: 'Мария',
    status_label: 'Нужна регулярность',
    context_label: 'Две тренировки пропущены за последние четыре недели.',
    workout_title: 'Сила и мобильность · неделя 3',
    facts: [
      { label: 'Выполнено', value: '4 из 6 упражнений' },
      { label: 'Пропуски', value: '2 тренировки' },
      { label: 'Регулярность', value: '62%' },
      { label: 'Следующий ориентир', value: 'Вернуться к расписанию' },
    ],
    comment: null,
  },
  {
    id: 'ivan',
    name: 'Иван',
    status_label: 'Плато',
    context_label: 'Регулярность сохранена, но объём не меняется третью неделю.',
    workout_title: 'Верх тела · неделя 4',
    facts: [
      { label: 'Выполнено', value: '6 из 6 упражнений' },
      { label: 'Объём', value: '5 920 кг' },
      { label: 'Регулярность', value: '100%' },
      { label: 'Следующий ориентир', value: 'Обсудить прогрессию' },
    ],
    comment: null,
  },
];

function cabinetFixture(scenario: DemoScenario): DemoSessionSnapshot['cabinet'] {
  return {
    program: {
      name: 'Сила и устойчивость',
      current_week: 4,
      total_weeks: 8,
      sessions_per_week: 3,
      schedule: [
        { day_label: 'Пн', workout_title: 'Ноги и корпус', status: 'completed' },
        { day_label: 'Вт', workout_title: 'Отдых', status: 'rest' },
        { day_label: 'Ср', workout_title: 'Верх тела', status: 'completed' },
        { day_label: 'Чт', workout_title: 'Отдых', status: 'rest' },
        { day_label: 'Пт', workout_title: 'Тяга и сила', status: 'planned' },
        { day_label: 'Сб', workout_title: 'Мобильность', status: 'planned' },
        { day_label: 'Вс', workout_title: 'Отдых', status: 'rest' },
      ],
    },
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
      adherence_percent: 86,
      training_history: [
        {
          period_label: 'Неделя 4',
          workout_title: 'Ноги и корпус',
          completed_sets: 18,
          volume_kg: 6840,
        },
        {
          period_label: 'Неделя 3',
          workout_title: 'Верх тела',
          completed_sets: 18,
          volume_kg: 6480,
        },
        {
          period_label: 'Неделя 2',
          workout_title: 'Тяга и сила',
          completed_sets: 16,
          volume_kg: 6220,
        },
        {
          period_label: 'Неделя 1',
          workout_title: 'Ноги и корпус',
          completed_sets: 15,
          volume_kg: 5960,
        },
      ],
      volume_history: [
        { period_label: 'Неделя 1', volume_kg: 5960 },
        { period_label: 'Неделя 2', volume_kg: 6220 },
        { period_label: 'Неделя 3', volume_kg: 6480 },
        { period_label: 'Неделя 4', volume_kg: 6840 },
      ],
      nutrition_history: [
        { date_label: 'Пн', status: 'complete', calories: 2080, protein_g: 142 },
        { date_label: 'Вт', status: 'incomplete', calories: 1160, protein_g: 82 },
        { date_label: 'Ср', status: 'complete', calories: 2140, protein_g: 146 },
        { date_label: 'Чт', status: 'not_logged', calories: null, protein_g: null },
        { date_label: 'Пт', status: 'complete', calories: 2010, protein_g: 139 },
        { date_label: 'Сб', status: 'complete', calories: 2190, protein_g: 151 },
        { date_label: 'Вс', status: 'incomplete', calories: 1540, protein_g: 96 },
      ],
      measurements: [
        { label: 'Масса тела', value: '78,4 кг', date_label: '12 сентября' },
        { label: 'Талия', value: '84 см', date_label: '12 сентября' },
      ],
    },
    trainer: null,
    meaningful_action_completed: false,
    conversion_title: 'Готово. Вы посмотрели основной сценарий',
  };
}

function trainerFixture(): DemoTrainerState {
  return {
    kind: 'trainer',
    screen: 'client',
    selected_client_id: 'alexey',
    clients: structuredClone(trainerClients),
  };
}

export function demoFixture(scenario: DemoScenario): DemoSessionSnapshot {
  const base = {
    capability: 'demo' as const,
    scenario,
    fixture_version: 'demo-curated-v2' as const,
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
    const state = trainerFixture();
    return { ...base, state, cabinet: { ...base.cabinet, trainer: state } };
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
