import path from 'node:path';
import { expect, test } from '@playwright/test';

function channelToLinear(channel: number): number {
  const normalized = channel / 255;
  return normalized <= 0.03928 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
}

function contrastRatio(foreground: string, background: string): number {
  const parse = (color: string): [number, number, number] => {
    const channels = (color.match(/[\d.]+/g) ?? []).slice(0, 3).map((channel) => Number(channel));
    if (channels.length !== 3) throw new Error(`Unsupported color: ${color}`);
    return [channels[0]!, channels[1]!, channels[2]!];
  };
  const luminance = (color: string) => {
    const [red, green, blue] = parse(color);
    return (
      0.2126 * channelToLinear(red) +
      0.7152 * channelToLinear(green) +
      0.0722 * channelToLinear(blue)
    );
  };
  const lighter = Math.max(luminance(foreground), luminance(background));
  const darker = Math.min(luminance(foreground), luminance(background));
  return (lighter + 0.05) / (darker + 0.05);
}

const representativePages = [
  {
    path: '/training',
    heading: /дневник тренировок: от программы до прогресса/i,
  },
  {
    path: '/for-trainers',
    heading: /рабочий кабинет тренера, который держит день в фокусе/i,
  },
  {
    path: '/exercises',
    heading: /техника упражнений из общего каталога/i,
  },
  {
    path: '/calculators/1rm',
    heading: /калькулятор 1пм: оценочный одноповторный максимум/i,
  },
  {
    path: '/knowledge',
    heading: /материалы, которые помогают понять следующий шаг/i,
  },
  {
    path: '/knowledge/nutrition/kbju-as-a-reference',
    heading: /кбжу как ориентир, а не обещание результата/i,
  },
  {
    path: '/knowledge/training/repetitions-in-reserve',
    heading: /повторы в запасе: полезная оценка/i,
  },
  {
    path: '/knowledge/nutrition/glycemic-index',
    heading: /гликемический индекс описывает продукт/i,
  },
  {
    path: '/knowledge/nutrition/food-sources-for-kbju',
    heading: /источники кбжу — это варианты/i,
  },
  {
    path: '/knowledge/progress/bmi-calculator',
    heading: /имт — скрининговый ориентир/i,
  },
  {
    path: '/knowledge/nutrition/hydration-and-water',
    heading: /гидратация: ориентир помогает/i,
  },
];

const publicArticleCard = {
  slug: 'strength-basics',
  title: 'Основы силовых тренировок',
  description: 'План, записи и ограничения для понятного старта.',
  lead: 'Начните с посильного плана и записывайте факты.',
  topics: ['training', 'strength_hypertrophy'],
  article_kind: 'evergreen_explainer',
  published_at: '2026-09-01T10:00:00Z',
  updated_at: '2026-09-02T10:00:00Z',
  canonical_url: 'http://127.0.0.1:4173/articles/strength-basics',
};

const publicArticle = {
  ...publicArticleCard,
  body_sections: [
    {
      heading: 'С чего начать',
      paragraphs: ['Выберите посильные движения и заранее определите дни занятий.'],
      points: ['Записывайте фактические подходы'],
    },
    {
      heading: 'Как читать записи',
      paragraphs: ['Сверяйте план и факт по нескольким занятиям.'],
      points: [],
    },
  ],
  search_intent: 'informational',
  primary_query: 'как начать силовые тренировки',
  secondary_queries: ['план силовых тренировок'],
  risk_level: 'low',
  evidence_level: 'moderate',
  claims: [
    {
      claim_id: 'plan-context',
      claim_text: 'Повторяемый план помогает сравнивать записи.',
      normalized_claim: 'repeatable plan supports comparison',
    },
  ],
  sources: [
    {
      source_id: 'source-guideline',
      title: 'Physical activity guidance',
      publisher: 'World Health Organization',
      url: 'https://www.who.int/news-room/fact-sheets/detail/physical-activity',
      source_type: 'official_organization',
      published_at: null,
      limitations: 'Общие рекомендации.',
    },
  ],
  claim_source_matrix: [
    {
      claim_id: 'plan-context',
      source_ids: ['source-guideline'],
      support_level: 'supports',
      limitations: 'Источник не задаёт индивидуальную программу.',
      review_status: 'verified',
    },
  ],
  author: { name: 'Your Fitness Coach', type: 'Organization' },
  editor: { name: 'YFC Editorial Desk', type: 'Organization' },
  domain_reviewer: null,
  related_slugs: [],
  cta: {
    destination: 'web',
    label: 'Открыть Your Fitness Coach',
    description: 'Сохраняйте план и фактические результаты.',
  },
  content_version: 1,
  generated_with_ai: true,
  research_assistance: true,
};

const publicBenchExerciseDetail = {
  slug: 'bench-press',
  title: 'Жим лежа',
  primary_muscle: 'Грудь',
  secondary_muscles: ['Трицепс', 'Передняя дельта'],
  equipment: 'Штанга',
  difficulty_level: 'intermediate',
  technique_steps: [
    'Сведи и опусти лопатки, поставь стопы устойчиво и сохрани естественный прогиб спины.',
    'Опускай снаряд под контролем к нижней части груди, удерживая предплечья близко к вертикали.',
    'Выжми вес по устойчивой траектории, не теряя опору стоп и положение лопаток.',
  ],
  breathing: 'Вдох на опускании, выдох после прохождения самой тяжёлой части жима.',
  common_mistakes: [
    'Отрыв таза или стоп',
    'Раскрытые плечи и потеря лопаток',
    'Удар снарядом о грудь',
  ],
  safety_notes: [
    'Используйте нагрузку и амплитуду, при которых сохраняется описанная техника; при острой боли останови подход.',
  ],
  media: [
    {
      type: 'image',
      url: '/static/exercise-guides/bench-press-start.jpg',
      poster: '/static/exercise-guides/bench-press-start.jpg',
      phase_id: 'concentric_end',
      phase: 'Фаза усилия',
      alt: 'Жим лежа: фаза усилия',
      source_name: 'free-exercise-db',
      source_url: 'https://github.com/yuhonas/free-exercise-db',
      source_license: 'Unlicense (общественное достояние)',
      source_license_url: 'https://github.com/yuhonas/free-exercise-db/blob/main/LICENSE.md',
      width: 850,
      height: 567,
      byte_size: 72816,
      sort_order: 0,
      sources: [
        {
          url: '/static/exercise-guides/bench-press-start.jpg',
          mime_type: 'image/jpeg',
          width: 850,
          height: 567,
          byte_size: 72816,
        },
      ],
    },
    {
      type: 'image',
      url: '/static/exercise-guides/bench-press-active.jpg',
      poster: '/static/exercise-guides/bench-press-active.jpg',
      phase_id: 'eccentric_end',
      phase: 'Фаза возврата',
      alt: 'Жим лежа: фаза возврата',
      source_name: 'free-exercise-db',
      source_url: 'https://github.com/yuhonas/free-exercise-db',
      source_license: 'Unlicense (общественное достояние)',
      source_license_url: 'https://github.com/yuhonas/free-exercise-db/blob/main/LICENSE.md',
      width: 850,
      height: 567,
      byte_size: 72202,
      sort_order: 1,
      sources: [
        {
          url: '/static/exercise-guides/bench-press-active.jpg',
          mime_type: 'image/jpeg',
          width: 850,
          height: 567,
          byte_size: 72202,
        },
      ],
    },
  ],
  source_name: 'free-exercise-db',
  source_url: 'https://github.com/yuhonas/free-exercise-db',
  source_license: 'Unlicense (общественное достояние)',
  source_license_url: 'https://github.com/yuhonas/free-exercise-db/blob/main/LICENSE.md',
};

const publicFullBodyProgram = {
  slug: 'full-body-3-days',
  title: 'Фуллбади 3 дня',
  goal: 'recomposition',
  level: 'beginner',
  split_type: 'full_body',
  days: [
    {
      day_number: 1,
      title: 'Фуллбади A',
      exercises: [
        ['squat', 'Приседания', 'Квадрицепс', 'Штанга', 4, '6-8', 150],
        ['bench-press', 'Жим лежа', 'Грудь', 'Штанга', 4, '6-8', 150],
        ['seated-cable-row', 'Тяга горизонтального блока', 'Спина', 'Кроссовер', 3, '10-12', 90],
        [
          'romanian-deadlift',
          'Румынская тяга',
          'Задняя поверхность бедра',
          'Штанга',
          3,
          '8-10',
          120,
        ],
        ['plank', 'Планка', 'Мышцы корпуса', 'Без оборудования', 3, '30-60 сек', 60],
      ],
    },
    {
      day_number: 2,
      title: 'Фуллбади B',
      exercises: [
        ['deadlift', 'Становая тяга', 'Ягодицы', 'Штанга', 3, '3-5', 180],
        ['overhead-press', 'Жим штанги стоя', 'Плечи', 'Штанга', 4, '6-8', 150],
        ['lat-pulldown', 'Вертикальная тяга', 'Спина', 'Тренажер', 3, '10-12', 90],
        ['leg-press', 'Жим ногами', 'Квадрицепс', 'Тренажер', 3, '10-12', 120],
        ['hanging-leg-raise', 'Подъем ног в висе', 'Мышцы корпуса', 'Турник', 3, '10-15', 60],
      ],
    },
    {
      day_number: 3,
      title: 'Фуллбади C',
      exercises: [
        ['front-squat', 'Фронтальные приседания', 'Квадрицепс', 'Штанга', 4, '6-8', 150],
        [
          'incline-dumbbell-press',
          'Жим гантелей на наклонной скамье',
          'Грудь',
          'Гантели',
          3,
          '8-10',
          120,
        ],
        ['barbell-row', 'Тяга штанги в наклоне', 'Спина', 'Штанга', 4, '6-8', 150],
        ['hip-thrust', 'Ягодичный мост', 'Ягодицы', 'Штанга', 3, '8-10', 120],
        ['face-pull', 'Тяга к лицу', 'Плечи', 'Кроссовер', 3, '12-15', 60],
      ],
    },
  ].map((day) => ({
    ...day,
    exercises: day.exercises.map(
      ([
        slug,
        title,
        primary_muscle,
        equipment,
        prescribed_sets,
        prescribed_reps,
        rest_seconds,
      ]) => ({
        slug,
        title,
        primary_muscle,
        equipment,
        difficulty_level: 'intermediate',
        prescribed_sets,
        prescribed_reps,
        rest_seconds,
      }),
    ),
  })),
};

test('legacy app knowledge URLs hand off to the equivalent Public Web article', async ({
  page,
}) => {
  await page.goto('/app/knowledge/training/repetitions-in-reserve');

  await expect(page).toHaveURL('/knowledge/training/repetitions-in-reserve');
  await expect(
    page.getByRole('heading', { level: 1, name: /повторы в запасе: полезная оценка/i }),
  ).toBeVisible();
});

test('landing emits a privacy-safe acquisition event without changing the desktop result', async ({
  page,
}, testInfo) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route('**/api/v1/public/articles*', (route) => route.fulfill({ json: [] }));
  await page.addInitScript(() => {
    const events: unknown[] = [];
    Object.defineProperty(window, '__productAnalyticsEvents', { value: events, writable: false });
    window.addEventListener('yfc:product-event', (event) => {
      events.push((event as CustomEvent).detail);
    });
  });

  await page.goto('/');
  await expect(
    page.getByRole('heading', {
      level: 1,
      name: 'СИЛА В ДЕЙСТВИИ.',
    }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath('landing-acquisition-desktop-1440-light.png'),
  });
  await page
    .locator('.landing-contact')
    .getByRole('link', { name: 'Начать со своими данными', exact: true })
    .evaluate((element) => {
      element.addEventListener('click', (event) => event.preventDefault(), { once: true });
    });
  await page
    .locator('.landing-contact')
    .getByRole('link', { name: 'Начать со своими данными', exact: true })
    .click();

  const analyticsEvents = await page.evaluate(
    () =>
      (
        window as typeof window & {
          __productAnalyticsEvents: Array<Record<string, unknown>>;
        }
      ).__productAnalyticsEvents,
  );
  expect(analyticsEvents).toContainEqual(
    expect.objectContaining({ name: 'landing_viewed', surface: 'desktop_web' }),
  );
  expect(analyticsEvents).toContainEqual(
    expect.objectContaining({ name: 'landing_app_selected', surface: 'desktop_web' }),
  );
  expect(analyticsEvents.every((event) => !('url' in event))).toBe(true);
});

test('публичные страницы сохраняют hierarchy и не создают overflow', async ({ page }) => {
  await page.route('**/api/v1/public/exercises', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(
        ['bench-press', 'lat-pulldown', 'squat', 'deadlift', 'overhead-press'].map((slug) => ({
          slug,
          title: slug,
          primary_muscle: 'Группа мышц',
          secondary_muscles: [],
          equipment: 'Штанга',
          difficulty_level: 'intermediate',
        })),
      ),
    });
  });
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 768, height: 900 },
    { width: 430, height: 932 },
    { width: 390, height: 844 },
    { width: 360, height: 800 },
  ]) {
    await page.setViewportSize(viewport);
    for (const publicPage of representativePages) {
      await page.goto(publicPage.path);

      await expect(page.getByRole('heading', { level: 1, name: publicPage.heading })).toBeVisible();
      await expect(page.getByRole('navigation', { name: 'Хлебные крошки' })).toBeVisible();
      if (viewport.width >= 768) {
        await expect(page.getByRole('link', { name: 'Войти' })).toBeVisible();
      } else {
        await expect(page.getByRole('button', { name: 'Открыть меню' })).toBeVisible();
      }
      await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'index, follow');
      await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
        'href',
        `http://127.0.0.1:4173${publicPage.path}`,
      );
      await expect(page.locator('meta[property="og:image"]')).toHaveAttribute(
        'content',
        'http://127.0.0.1:4173/assets/brand/yfc-social-preview.png',
      );
      await expect(page.locator('meta[name="twitter:card"]')).toHaveAttribute(
        'content',
        'summary_large_image',
      );
      expect(
        await page.evaluate(() => ({
          content: document.documentElement.scrollWidth,
          viewport: window.innerWidth,
        })),
      ).toEqual({ content: viewport.width, viewport: viewport.width });

      if (viewport.width === 1440) {
        const heroGutters = await page.evaluate(() => {
          const hero = document.querySelector('.public-hero')!.getBoundingClientRect();
          const copy = document.querySelector('.public-hero__copy')!.getBoundingClientRect();
          const summary = document.querySelector('.public-hero__summary')!.getBoundingClientRect();
          return {
            left: copy.left - hero.left,
            right: hero.right - summary.right,
          };
        });
        expect(heroGutters.left).toBeGreaterThanOrEqual(40);
        expect(heroGutters.right).toBeGreaterThanOrEqual(40);
      }
    }
  }
});

test('related materials use one editorial measure and compact inline CTAs', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const relatedArticle = {
    ...publicArticleCard,
    slug: 'recovery-basics',
    title: 'Восстановление после тренировки',
  };
  await page.route('**/api/v1/public/articles/strength-basics', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ ...publicArticle, related_slugs: [relatedArticle.slug] }),
    });
  });
  await page.route('**/api/v1/public/articles', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([publicArticleCard, relatedArticle]),
    });
  });
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    for (const route of ['/for-trainers', '/training', '/articles/strength-basics']) {
      await page.goto(route);
      await expect(page.locator('.public-related-card').first()).toBeVisible();
      const metrics = await page.evaluate(() => {
        const copy = document.querySelector<HTMLElement>('.public-body');
        const sectionHeading = document.querySelector<HTMLElement>('.public-section-heading');
        const cards = [...document.querySelectorAll<HTMLElement>('.public-related-card')];
        return {
          copyWidth: copy?.getBoundingClientRect().width ?? 0,
          sectionHeadingWidth: sectionHeading?.getBoundingClientRect().width ?? 0,
          cards: cards.map((card) => {
            const cta = card.querySelector<HTMLElement>('small');
            return {
              height: card.getBoundingClientRect().height,
              ctaText: cta?.textContent,
              ctaHeight: cta?.getBoundingClientRect().height ?? 0,
              ctaScrollHeight: cta?.scrollHeight ?? 0,
              ctaSvgCount: cta?.querySelectorAll('svg').length ?? 0,
            };
          }),
        };
      });

      expect(metrics.copyWidth).toBeLessThanOrEqual(820);
      expect(metrics.sectionHeadingWidth).toBeLessThanOrEqual(820);
      expect(metrics.cards.length).toBeGreaterThan(0);
      for (const card of metrics.cards) {
        expect(card.height).toBeLessThanOrEqual(230);
        expect(card.ctaText).toBe('Открыть →');
        expect(card.ctaHeight).toBeGreaterThan(0);
        expect(card.ctaScrollHeight).toBeLessThanOrEqual(Math.ceil(card.ctaHeight));
        expect(card.ctaSvgCount).toBe(0);
      }
    }
  }
});

test('canonical three-day program stays useful, stateless and responsive', async ({ page }) => {
  await page.route('**/api/v1/public/programs/full-body-3-days', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(publicFullBodyProgram),
    });
  });
  await page.addInitScript(() => {
    const events: unknown[] = [];
    Object.defineProperty(window, '__productAnalyticsEvents', { value: events, writable: false });
    window.addEventListener('yfc:product-event', (event) => {
      events.push((event as CustomEvent).detail);
    });
  });

  const evidenceDirectory = process.env.TASK_286_EVIDENCE_DIR;
  const states = [
    { name: '320-light', width: 320, height: 740, colorScheme: 'light' as const },
    { name: '360-light', width: 360, height: 800, colorScheme: 'light' as const },
    { name: '390-light', width: 390, height: 844, colorScheme: 'light' as const },
    { name: '390-dark', width: 390, height: 844, colorScheme: 'dark' as const },
    { name: '430-light', width: 430, height: 932, colorScheme: 'light' as const },
    { name: '430-dark', width: 430, height: 932, colorScheme: 'dark' as const },
    { name: '768-light', width: 768, height: 900, colorScheme: 'light' as const },
    { name: '768-dark', width: 768, height: 900, colorScheme: 'dark' as const },
    { name: '1366-light', width: 1366, height: 900, colorScheme: 'light' as const },
    { name: '1366-dark', width: 1366, height: 900, colorScheme: 'dark' as const },
    { name: '1440-light', width: 1440, height: 900, colorScheme: 'light' as const },
    { name: '1440-dark', width: 1440, height: 900, colorScheme: 'dark' as const },
  ];

  for (const state of states) {
    await page.setViewportSize({ width: state.width, height: state.height });
    await page.goto('/programs/full-body-3-days');
    await page.evaluate((colorScheme) => {
      window.localStorage.setItem('app-theme', colorScheme);
    }, state.colorScheme);
    await page.reload();

    await expect(
      page.getByRole('heading', {
        level: 1,
        name: /программа тренировок 3 раза в неделю: full body на 3 дня/i,
      }),
    ).toBeVisible();
    await expect(page.locator('.public-program-day')).toHaveCount(3);
    await expect(page.getByRole('link', { name: 'Приседания' })).toHaveAttribute(
      'href',
      '/exercises/squat',
    );
    await expect(
      page.getByRole('link', { name: 'Выбрать программу в приложении' }).first(),
    ).toHaveAttribute('href', /\/app\?section=programs$/);
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'index, follow');
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      'href',
      'http://127.0.0.1:4173/programs/full-body-3-days',
    );
    await expect(page.locator('.public-shell')).toHaveClass(
      state.colorScheme === 'dark' ? /public-shell--dark/ : /public-shell--light/,
    );
    expect(
      await page.evaluate(() => ({
        content: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
        events: (
          window as typeof window & {
            __productAnalyticsEvents: Array<Record<string, unknown>>;
          }
        ).__productAnalyticsEvents,
      })),
    ).toMatchObject({ content: state.width, viewport: state.width, events: [] });
    if (evidenceDirectory) {
      await page.screenshot({
        path: path.join(evidenceDirectory, `${state.name}.png`),
        fullPage: true,
      });
    }
  }
});

test('public article index and detail stay readable and crawlable across desktop and mobile', async ({
  page,
}) => {
  await page.route('**/api/v1/public/articles/strength-basics', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(publicArticle),
    });
  });
  await page.route('**/api/v1/public/articles', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([publicArticleCard]),
    });
  });

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/articles');
    await expect(
      page.getByRole('heading', { level: 1, name: 'Статьи, которые помогают разобраться.' }),
    ).toBeVisible();
    await expect(page.getByRole('link', { name: /Основы силовых тренировок/ })).toHaveAttribute(
      'href',
      '/articles/strength-basics',
    );
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'index, follow');

    await page.goto('/articles/strength-basics');
    await expect(page.getByRole('heading', { level: 1, name: publicArticle.title })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Источники' })).toBeVisible();
    expect(publicArticle.sources).toHaveLength(1);
    await expect(page.getByRole('link', { name: 'Physical activity guidance' })).toHaveAttribute(
      'href',
      publicArticle.sources[0]!.url,
    );
    await expect(page.getByRole('link', { name: 'Открыть Your Fitness Coach' })).toHaveAttribute(
      'href',
      '/app',
    );
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      'href',
      publicArticle.canonical_url,
    );
    expect(
      await page.evaluate(() => ({
        content: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
      })),
    ).toEqual({ content: viewport.width, viewport: viewport.width });
  }
});

test('product and knowledge index heroes stay compact on desktop and mobile', async ({ page }) => {
  for (const viewport of [
    { width: 1440, height: 900, maxHeading: 78, maxHero: 560 },
    { width: 390, height: 844, maxHeading: 44, maxHero: 700 },
  ]) {
    await page.setViewportSize(viewport);
    for (const path of ['/training', '/nutrition', '/knowledge']) {
      await page.goto(path);
      await expect(page.locator('.public-hero h1')).toBeVisible();
      const metrics = await page.evaluate(() => {
        const header = document.querySelector<HTMLElement>('.public-header')!;
        const breadcrumbs = document.querySelector<HTMLElement>('.public-breadcrumbs')!;
        const breadcrumbList = breadcrumbs.querySelector<HTMLElement>('ol')!;
        const hero = document.querySelector<HTMLElement>('.public-hero')!;
        const heading = hero.querySelector<HTMLElement>('h1')!;
        const heroStyle = getComputedStyle(hero);
        const headerStyle = getComputedStyle(header);
        const headerBounds = header.getBoundingClientRect();
        const breadcrumbBounds = breadcrumbList.getBoundingClientRect();
        const heroBounds = hero.getBoundingClientRect();
        return {
          headingSize: Number.parseFloat(getComputedStyle(heading).fontSize),
          headerDisplay: headerStyle.display,
          headerBackground: headerStyle.backgroundColor,
          heroHeight: heroBounds.height,
          paddingTop: Number.parseFloat(heroStyle.paddingTop),
          breadcrumbTopGap: breadcrumbBounds.top - headerBounds.bottom,
          breadcrumbBottomGap: heroBounds.top - breadcrumbBounds.bottom,
        };
      });
      expect(metrics.headingSize).toBeLessThanOrEqual(viewport.maxHeading);
      expect(metrics.headerDisplay).toBe('grid');
      expect(metrics.headerBackground).toBe('rgb(9, 11, 11)');
      expect(metrics.heroHeight).toBeLessThanOrEqual(viewport.maxHero);
      expect(metrics.paddingTop).toBeLessThanOrEqual(viewport.width === 1440 ? 80 : 44);
      expect(Math.abs(metrics.breadcrumbTopGap - metrics.breadcrumbBottomGap)).toBeLessThanOrEqual(
        2,
      );
    }
  }
});

test('mobile menu, skip link and contextual navigation work without an auth wall', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/progress');

  const skipLink = page.getByRole('link', { name: 'К содержимому' });
  await skipLink.focus();
  await expect(skipLink).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(page.locator('#public-content')).toBeFocused();

  const menu = page.getByRole('button', { name: 'Открыть меню' });
  await menu.click();
  await expect(page.getByRole('button', { name: 'Закрыть меню' })).toHaveAttribute(
    'aria-expanded',
    'true',
  );
  const publicNavigation = page.getByRole('navigation', { name: 'Публичные разделы' });
  await expect(publicNavigation.getByRole('link', { name: 'Питание' })).toBeVisible();
  await publicNavigation.getByRole('link', { name: 'Питание' }).click();
  await expect(page).toHaveURL('/nutrition');
  await expect(
    page.getByRole('heading', { level: 1, name: /рассчитать кбжу: калории/i }),
  ).toBeVisible();
});

test('public KBJU calculator works without auth or sensitive transport and stays responsive', async ({
  page,
}) => {
  const apiRequests: string[] = [];
  const evidenceDirectory = process.env.TASK_241B_EVIDENCE_DIR;
  page.on('request', (request) => {
    if (request.url().includes('/api/')) apiRequests.push(`${request.method()} ${request.url()}`);
  });

  for (const viewport of [
    { width: 320, height: 740 },
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
    { width: 768, height: 900 },
    { width: 1366, height: 900 },
    { width: 1440, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/nutrition');

    await expect(page.getByRole('heading', { level: 1, name: /рассчитать кбжу/i })).toBeVisible();
    const calculator = page.locator('#public-kbju-calculator');
    await expect(calculator).toHaveClass(/ym-hide-content/);
    const form = calculator.getByRole('form', { name: 'Рассчитать КБЖУ онлайн' });

    await form.getByRole('button', { name: 'Рассчитать КБЖУ' }).click();
    await expect(calculator.getByRole('alert')).toContainText('Возраст');
    await expect(calculator.getByRole('status')).toHaveCount(0);

    await calculator.getByLabel('Возраст, лет').fill('34');
    await calculator.getByLabel('Вес, кг').fill('78');
    await calculator.getByLabel('Рост, см').fill('165');
    await calculator.getByLabel('Силовых тренировок в неделю').fill('3');
    await calculator.getByText('Уточнить расчёт тренировочной нагрузки').click();
    await calculator.getByLabel('Длительность силовой, минут').fill('60');
    await form.getByRole('button', { name: 'Рассчитать КБЖУ' }).click();

    await expect(calculator.getByRole('status')).toContainText('Калории');
    await expect(calculator.getByRole('status')).toContainText('Белки');
    await expect(calculator.getByRole('status')).toContainText('Для поддержания');
    if (evidenceDirectory && [320, 390, 768, 1366, 1440].includes(viewport.width)) {
      await calculator.screenshot({
        path: path.join(evidenceDirectory, `kbju-${viewport.width}-light.png`),
      });
      await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
      await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
      await calculator.screenshot({
        path: path.join(evidenceDirectory, `kbju-${viewport.width}-dark.png`),
      });
      await page.getByRole('button', { name: 'Включить светлую тему' }).click();
    }
    expect(
      await page.evaluate(() => ({
        content: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
        url: window.location.href,
        sensitiveStoredKeys: Object.keys(localStorage).filter((key) =>
          /calculator|nutrition|weight|height|age|calorie|protein|fat|carb/i.test(key),
        ),
      })),
    ).toEqual({
      content: viewport.width,
      viewport: viewport.width,
      url: `http://127.0.0.1:4173/nutrition`,
      sensitiveStoredKeys: [],
    });
  }

  expect(apiRequests).toEqual([]);
});

test('public 1RM calculator stays stateless, bounded and readable in light and dark themes', async ({
  page,
}) => {
  const apiRequests: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/')) apiRequests.push(`${request.method()} ${request.url()}`);
  });
  await page.addInitScript(() => {
    const events: unknown[] = [];
    Object.defineProperty(window, '__productAnalyticsEvents', { value: events, writable: false });
    window.addEventListener('yfc:product-event', (event) => {
      events.push((event as CustomEvent).detail);
    });
  });

  const states = [
    { name: '320-light', width: 320, height: 740, colorScheme: 'light' as const },
    { name: '360-light', width: 360, height: 800, colorScheme: 'light' as const },
    { name: '390-light', width: 390, height: 844, colorScheme: 'light' as const },
    { name: '390-dark', width: 390, height: 844, colorScheme: 'dark' as const },
    { name: '430-dark', width: 430, height: 932, colorScheme: 'dark' as const },
    { name: '768-light', width: 768, height: 900, colorScheme: 'light' as const },
    { name: '768-dark', width: 768, height: 900, colorScheme: 'dark' as const },
    { name: '1366-light', width: 1366, height: 900, colorScheme: 'light' as const },
    { name: '1440-dark', width: 1440, height: 900, colorScheme: 'dark' as const },
  ];

  for (const state of states) {
    await page.setViewportSize({ width: state.width, height: state.height });
    await page.goto('/calculators/1rm');
    await page.evaluate((colorScheme) => {
      window.localStorage.setItem('app-theme', colorScheme);
    }, state.colorScheme);
    await page.reload();

    await expect(
      page.getByRole('heading', {
        level: 1,
        name: /калькулятор 1пм: оценочный одноповторный максимум/i,
      }),
    ).toBeVisible();
    const calculator = page.locator('#public-one-rm-calculator');
    await expect(calculator).toHaveClass(/ym-hide-content/);
    await expect(page.locator('.public-shell')).toHaveClass(
      state.colorScheme === 'dark' ? /public-shell--dark/ : /public-shell--light/,
    );
    const form = calculator.getByRole('form', { name: 'Рассчитать 1ПМ онлайн' });

    await form.getByRole('button', { name: 'Рассчитать 1ПМ' }).click();
    await expect(calculator.getByText('Укажите вес от 0,5 до 500 кг.')).toBeVisible();
    await expect(calculator.getByRole('status')).toHaveCount(0);

    await calculator.getByLabel('Вес в подходе, кг').fill('100');
    await calculator.getByLabel('Повторения в подходе').fill('5');
    await form.getByRole('button', { name: 'Рассчитать 1ПМ' }).click();
    await expect(calculator.getByRole('status')).toContainText('112,5 кг');
    await expect(calculator.getByRole('row', { name: '95% 107 кг' })).toBeVisible();
    await expect(calculator.getByRole('row', { name: '70% 79 кг' })).toBeVisible();
    await expect(calculator.getByRole('row')).toHaveCount(7);

    const pageState = await page.evaluate(() => ({
      content: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
      url: window.location.href,
      sensitiveStoredKeys: Object.keys(window.localStorage).filter((key) =>
        /calculator|1rm|weight|repetition|result/i.test(key),
      ),
      html: document.documentElement.outerHTML,
      events: (
        window as typeof window & {
          __productAnalyticsEvents: Array<Record<string, unknown>>;
        }
      ).__productAnalyticsEvents,
    }));
    expect(pageState).toMatchObject({
      content: state.width,
      viewport: state.width,
      url: `http://127.0.0.1:4173/calculators/1rm`,
      sensitiveStoredKeys: [],
    });
    expect(pageState.html).not.toContain('one_rm_');
    expect(pageState.events.map((event) => event.name)).toContain('calculator_started');
    expect(pageState.events.map((event) => event.name)).toContain('calculator_result');
    expect(pageState.events.every((event) => Object.keys(event).length === 5)).toBe(true);
    expect(JSON.stringify(pageState.events)).not.toContain('100');
    expect(JSON.stringify(pageState.events)).not.toContain('112');

    if (process.env.TASK_241E_EVIDENCE_DIR) {
      await page.evaluate(() => {
        const calculator = document.querySelector<HTMLElement>('#public-one-rm-calculator');
        if (!calculator) throw new Error('1RM calculator is missing');
        window.scrollTo({ top: window.scrollY + calculator.getBoundingClientRect().top - 20 });
      });
      await calculator.screenshot({
        path: path.join(process.env.TASK_241E_EVIDENCE_DIR, `${state.name}.png`),
      });
    }
  }

  expect(apiRequests).toEqual([]);
});

test('BMI calculator validates adult metric inputs and stays stateless on narrow screens', async ({
  page,
}) => {
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 360, height: 800 },
    { width: 430, height: 932 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/knowledge/progress/bmi-calculator');

    const form = page.getByRole('form', { name: 'Рассчитать ИМТ' });
    await form.getByRole('button', { name: 'Рассчитать ИМТ' }).click();
    await expect(page.getByRole('alert')).toContainText('массу тела от 1 до 500 кг');

    await page.getByLabel('Масса тела, кг').fill('80');
    await page.getByLabel('Рост, см').fill('180');
    await form.getByRole('button', { name: 'Рассчитать ИМТ' }).click();
    await expect(page.getByRole('status')).toContainText('ИМТ: 24,7');
    await expect(page.getByRole('status')).toContainText('Нормальный диапазон для взрослых');
    expect(
      await page.evaluate(() => ({
        content: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
        stored: localStorage.getItem('public-bmi-calculator'),
      })),
    ).toEqual({ content: viewport.width, viewport: viewport.width, stored: null });
  }
});

test('mobile article spacing, justified type, CTA contrast and landing theme behavior stay readable', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/nutrition');
  await expect(
    page.getByRole('heading', { level: 1, name: /рассчитать кбжу: калории/i }),
  ).toBeVisible();

  const styles = await page.evaluate(() => {
    const hero = getComputedStyle(document.querySelector<HTMLElement>('.public-hero')!);
    const bodyText = getComputedStyle(
      document.querySelector<HTMLElement>('.public-body > section:not(.public-calculator) p')!,
    );
    const cta = document.querySelector<HTMLElement>('.public-cta')!;
    const ctaStyle = getComputedStyle(cta);
    return {
      heroPaddingLeft: Number.parseFloat(hero.paddingLeft),
      bodyFontSize: Number.parseFloat(bodyText.fontSize),
      bodyTextAlign: bodyText.textAlign,
      ctaBackground: ctaStyle.backgroundColor,
      ctaTitle: getComputedStyle(cta.querySelector('h2')!).color,
      ctaDescription: getComputedStyle(cta.querySelector('p:not(.landing-kicker)')!).color,
    };
  });

  expect(styles.heroPaddingLeft).toBeGreaterThanOrEqual(20);
  expect(styles.bodyFontSize).toBeGreaterThanOrEqual(17);
  expect(styles.bodyTextAlign).toBe('justify');
  expect(contrastRatio(styles.ctaTitle, styles.ctaBackground)).toBeGreaterThanOrEqual(4.5);
  expect(contrastRatio(styles.ctaDescription, styles.ctaBackground)).toBeGreaterThanOrEqual(4.5);

  const themeToggle = page.getByRole('button', { name: 'Включить тёмную тему' });
  await themeToggle.click();
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(page.locator('.public-shell')).toHaveClass(/public-shell--dark/);
  await expect(page.locator('body')).toHaveClass(/public-shell-dark-mode/);
  await page.getByRole('button', { name: 'Включить светлую тему' }).click();
  await expect(page.locator('.public-shell')).toHaveClass(/public-shell--light/);
});

test('guide exposes visible editorial metadata, sources and matching Article schema', async ({
  page,
}) => {
  await page.goto('/knowledge/training/how-to-start-strength-training');

  await expect(page.getByText('Редакция Your Fitness Coach')).toBeVisible();
  await expect(page.getByText(/22 августа 2026/i).first()).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Оглавление' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Источники' })).toBeVisible();
  await expect(page.getByRole('link', { name: /WHO Guidelines/i })).toHaveAttribute(
    'href',
    'https://www.who.int/publications/i/item/9789240015128',
  );
  const structuredData = await page
    .locator('script[type="application/ld+json"][data-public-seo]')
    .textContent();
  expect(structuredData).not.toBeNull();
  const payload = JSON.parse(structuredData ?? '{}') as {
    '@graph': Array<{ '@type': string }>;
  };
  expect(payload['@graph'].map((item) => item['@type'])).toEqual(['Article', 'BreadcrumbList']);
});

test('a public exercise stays readable on mobile and gets facts from the public API', async ({
  page,
}) => {
  let releaseResponse: (() => void) | undefined;
  const responseGate = new Promise<void>((resolve) => {
    releaseResponse = resolve;
  });
  await page.route('**/api/v1/public/exercises/bench-press', async (route) => {
    await responseGate;
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(publicBenchExerciseDetail),
    });
  });
  for (const imageName of ['bench-press-start.jpg', 'bench-press-active.jpg']) {
    await page.route(`**/static/exercise-guides/${imageName}`, async (route) => {
      await route.fulfill({
        path: path.resolve('..', 'backend', 'assets', 'exercise-guides', imageName),
      });
    });
  }
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto('/exercises/bench-press');

  await expect(page.getByRole('status')).toContainText('Загружаем технику');
  releaseResponse?.();
  await expect(
    page.getByRole('heading', { name: 'Техника выполнения', exact: true }),
  ).toBeVisible();
  await expect(page.getByText('Трицепс')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Положения в движении' })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Жим лежа: фаза усилия' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Что важно для безопасности' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'free-exercise-db' })).toHaveAttribute(
    'href',
    'https://github.com/yuhonas/free-exercise-db',
  );
  await expect(page.getByText('Unlicense (общественное достояние)')).toBeVisible();
  expect(
    await page.evaluate(() => ({
      content: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
    })),
  ).toEqual({ content: 360, viewport: 360 });
});

test('bench exemplar stays readable across the public visual matrix', async ({ page }) => {
  await page.route('**/api/v1/public/exercises/bench-press', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(publicBenchExerciseDetail),
    });
  });
  for (const imageName of ['bench-press-start.jpg', 'bench-press-active.jpg']) {
    await page.route(`**/static/exercise-guides/${imageName}`, async (route) => {
      await route.fulfill({
        path: path.resolve('..', 'backend', 'assets', 'exercise-guides', imageName),
      });
    });
  }

  const states = [
    { name: '320-light', width: 320, height: 780, colorScheme: 'light' as const },
    { name: '360-light', width: 360, height: 800, colorScheme: 'light' as const },
    { name: '390-light', width: 390, height: 844, colorScheme: 'light' as const },
    { name: '390-dark', width: 390, height: 844, colorScheme: 'dark' as const },
    { name: '430-dark', width: 430, height: 932, colorScheme: 'dark' as const },
    { name: '768-light', width: 768, height: 900, colorScheme: 'light' as const },
    { name: '768-dark', width: 768, height: 900, colorScheme: 'dark' as const },
    { name: '1366-light', width: 1366, height: 900, colorScheme: 'light' as const },
    { name: '1440-dark', width: 1440, height: 900, colorScheme: 'dark' as const },
  ];

  for (const state of states) {
    await page.setViewportSize({ width: state.width, height: state.height });
    await page.goto('/exercises/bench-press');
    await page.evaluate((colorScheme) => {
      window.localStorage.setItem('app-theme', colorScheme);
    }, state.colorScheme);
    await page.reload();
    await expect(
      page.getByRole('heading', { level: 1, name: /жим штанги лёжа: техника выполнения/i }),
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Техника выполнения', exact: true }),
    ).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Положения в движении' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Что важно для безопасности' })).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Открыть тренировки в Your Fitness Coach' }),
    ).toBeVisible();
    expect(
      await page.evaluate(() => ({
        content: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
      })),
    ).toEqual({ content: state.width, viewport: state.width });
    await page.screenshot({
      path: path.join('..', '.artifacts', 'tasks', '241C', 'evidence', `${state.name}.png`),
      fullPage: true,
    });
  }
});

test('campaign parameters keep one canonical URL and a fetchable social preview', async ({
  page,
  request,
}) => {
  await page.goto(
    '/training?utm_source=telegram&utm_medium=organic_social&utm_campaign=strength_start_guide&utm_content=channel_post',
  );

  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    'href',
    'http://127.0.0.1:4173/training',
  );
  await expect(page.locator('meta[property="og:url"]')).toHaveAttribute(
    'content',
    'http://127.0.0.1:4173/training',
  );
  const socialImage = page.locator('meta[property="og:image"]');
  await expect(socialImage).toHaveAttribute(
    'content',
    'http://127.0.0.1:4173/assets/brand/yfc-social-preview.png',
  );
  await expect(page.locator('meta[property="og:image:alt"]')).toHaveAttribute(
    'content',
    /тренировки, питание и прогресс/i,
  );

  const imageUrl = await socialImage.getAttribute('content');
  if (!imageUrl) throw new Error('Social preview URL is missing');
  const response = await request.get(imageUrl);
  expect(response.ok()).toBe(true);
  expect(response.headers()['content-type']).toContain('image/png');
  expect(
    await page.evaluate(
      (url) =>
        new Promise<{ width: number; height: number }>((resolve, reject) => {
          const image = new Image();
          image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight });
          image.onerror = () => reject(new Error('Social preview failed to load'));
          image.src = url;
        }),
      imageUrl,
    ),
  ).toEqual({ width: 1200, height: 630 });
});
