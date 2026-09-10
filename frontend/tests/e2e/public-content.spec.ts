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
    heading: /план тренировки, который остаётся перед глазами/i,
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
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 1440, height: 900 });
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
    path: '../.artifacts/screenshots/task-73a/analytics/desktop-1440x900-light-landing.png',
  });
  await page
    .locator('.landing-contact')
    .getByRole('link', { name: 'Открыть приложение', exact: true })
    .evaluate((element) => {
      element.addEventListener('click', (event) => event.preventDefault(), { once: true });
    });
  await page
    .locator('.landing-contact')
    .getByRole('link', { name: 'Открыть приложение', exact: true })
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
  await expect(page.getByRole('heading', { level: 1, name: /ориентиры кбжу/i })).toBeVisible();
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
  await expect(page.getByRole('heading', { level: 1, name: /ориентиры кбжу/i })).toBeVisible();

  const styles = await page.evaluate(() => {
    const hero = getComputedStyle(document.querySelector<HTMLElement>('.public-hero')!);
    const bodyText = getComputedStyle(document.querySelector<HTMLElement>('.public-body p')!);
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
      body: JSON.stringify({
        slug: 'bench-press',
        title: 'Жим лежа',
        primary_muscle: 'Грудь',
        secondary_muscles: ['Трицепс'],
        equipment: 'Штанга',
        difficulty_level: 'intermediate',
        technique_steps: [
          'Сведите лопатки и устойчиво поставьте стопы.',
          'Опустите гриф под контролем и выжмите его вверх.',
        ],
        breathing: 'Вдохните перед опусканием, выдохните после трудной части подъёма.',
        common_mistakes: ['Потеря опоры стоп.', 'Резкий отскок грифа.'],
        safety_notes: ['Используйте страховку при тяжёлых подходах.'],
        source_name: 'Your Fitness Coach exercise domain',
        source_url: 'https://your-fitness-coach.ru/',
        source_license: 'Собственные данные проекта',
        source_license_url: null,
      }),
    });
  });
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto('/exercises/bench-press');

  await expect(page.getByRole('status')).toContainText('Загружаем технику');
  releaseResponse?.();
  await expect(page.getByRole('heading', { name: 'Техника выполнения' })).toBeVisible();
  await expect(page.getByText('Трицепс')).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Your Fitness Coach exercise domain' }),
  ).toHaveAttribute('href', 'https://your-fitness-coach.ru/');
  expect(
    await page.evaluate(() => ({
      content: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
    })),
  ).toEqual({ content: 360, viewport: 360 });
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
