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
});
