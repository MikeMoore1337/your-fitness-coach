import { describe, expect, it } from 'vitest';
import {
  getPublicContentPage,
  isPublishedKnowledgePath,
  publicContent,
} from '../../../src/content/publicContent';

describe('public content routing', () => {
  it('recognizes only published knowledge pages from the content manifest', () => {
    expect(isPublishedKnowledgePath('/knowledge')).toBe(true);
    expect(isPublishedKnowledgePath('/knowledge/training/repetitions-in-reserve')).toBe(true);
    expect(isPublishedKnowledgePath('/knowledge/nutrition/glycemic-index')).toBe(true);
    expect(isPublishedKnowledgePath('/knowledge/nutrition/food-sources-for-kbju')).toBe(true);
    expect(isPublishedKnowledgePath('/knowledge/progress/bmi-calculator')).toBe(true);
    expect(isPublishedKnowledgePath('/knowledge/nutrition/hydration-and-water')).toBe(true);
    expect(isPublishedKnowledgePath('/knowledge/unknown-performance-route')).toBe(false);
    expect(isPublishedKnowledgePath('/training')).toBe(false);
  });

  it('keeps the public KBJU calculator on one canonical SEO page', () => {
    const nutritionPage = getPublicContentPage('/nutrition');

    expect(nutritionPage).toMatchObject({
      title: 'Калькулятор КБЖУ — рассчитать калории, белки, жиры и углеводы | Your Fitness Coach',
      interactive: 'kbju-calculator',
    });
    expect(publicContent.pages.filter((page) => page.path === '/nutrition')).toHaveLength(1);
    const forbiddenPaths = [
      '/calculator/kbju',
      '/calculators/kbju',
      '/kbju',
      '/kbju-calculator',
      '/kz/kbju',
      '/by/kbju',
      '/ru/kbju',
    ];
    expect(publicContent.pages.some((page) => forbiddenPaths.includes(page.path))).toBe(false);
  });

  it('keeps the public 1RM calculator on one canonical SEO page with useful context', () => {
    const oneRepMaxPage = getPublicContentPage('/calculators/1rm');

    expect(oneRepMaxPage).toMatchObject({
      title: 'Калькулятор 1ПМ — рассчитать одноповторный максимум | Your Fitness Coach',
      heading: 'Калькулятор 1ПМ: оценочный одноповторный максимум',
      interactive: 'one-rm-calculator',
    });
    expect(publicContent.pages.filter((page) => page.path === '/calculators/1rm')).toHaveLength(1);
    expect(oneRepMaxPage?.related.map((link) => link.path)).toEqual([
      '/exercises/bench-press',
      '/training',
      '/knowledge/training/repetitions-in-reserve',
      '/knowledge/training/progressive-overload',
    ]);
    const forbiddenPaths = [
      '/calculator/1rm',
      '/calculators/one-rep-max',
      '/1rm',
      '/one-rep-max-calculator',
      '/calculators/bench-press-1rm',
      '/calculators/squat-1rm',
    ];
    expect(publicContent.pages.some((page) => forbiddenPaths.includes(page.path))).toBe(false);
  });

  it('documents the real five-step trainer acquisition workflow', () => {
    const trainerPage = getPublicContentPage('/for-trainers');

    expect(trainerPage?.workflow?.steps.map((step) => step.title)).toEqual([
      'Включить режим',
      'Пригласить клиента',
      'Подтвердить связь',
      'Назначить программу',
      'Смотреть факты',
    ]);
    expect(trainerPage?.cta?.label).toBe('Включить режим тренера');
    expect(JSON.stringify(trainerPage)).not.toMatch(/NO_DATA|тысяч|клиент(?:ов|а) в месяц/i);
  });

  it('keeps the three-day training program on one canonical public route', () => {
    const programPage = getPublicContentPage('/programs/full-body-3-days');

    expect(programPage).toMatchObject({
      kind: 'program',
      slug: 'full-body-3-days',
      program: { slug: 'full-body-3-days' },
      heading: 'Программа тренировок 3 раза в неделю: Full Body на 3 дня',
    });
    expect(
      publicContent.pages.filter((page) => page.path === '/programs/full-body-3-days'),
    ).toHaveLength(1);
  });

  it('keeps bench press as one canonical technique exemplar with a truthful handoff', () => {
    const benchPage = getPublicContentPage('/exercises/bench-press');

    expect(benchPage).toMatchObject({
      title: 'Жим штанги лёжа — техника выполнения, ошибки и безопасность | Your Fitness Coach',
      heading: 'Жим штанги лёжа: техника выполнения',
      cta: {
        label: 'Открыть тренировки в Your Fitness Coach',
      },
    });
    expect(
      publicContent.pages.filter((page) => page.path === '/exercises/bench-press'),
    ).toHaveLength(1);
    expect(publicContent.pages.some((page) => page.path.includes('bench-press-technique'))).toBe(
      false,
    );
  });
});
