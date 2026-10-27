import type { DemoScenario } from './demoApi';

export type DemoScenarioContent = {
  value: DemoScenario;
  label: 'Тренировка' | 'Питание и прогресс' | 'Работа тренера';
  description: string;
  duration: string;
};

export const DEMO_SCENARIOS: readonly DemoScenarioContent[] = [
  {
    value: 'self_training',
    label: 'Тренировка',
    description:
      'Пройдите часть тренировки и посмотрите, как выполненные подходы становятся частью прогресса.',
    duration: 'около 2 минут',
  },
  {
    value: 'nutrition',
    label: 'Питание и прогресс',
    description: 'Добавьте продукт и посмотрите, как меняются дневной итог и показатели.',
    duration: 'около 1 минуты',
  },
  {
    value: 'trainer',
    label: 'Работа тренера',
    description:
      'Откройте подготовленного клиента, посмотрите результат тренировки и оставьте комментарий.',
    duration: 'около 2 минут',
  },
];

export function demoScenarioContent(scenario: DemoScenario): DemoScenarioContent {
  return DEMO_SCENARIOS.find((item) => item.value === scenario) ?? DEMO_SCENARIOS[0]!;
}
