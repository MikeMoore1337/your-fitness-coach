import { expect, test, type Page } from '@playwright/test';

const themes = ['dark', 'light'] as const;
const audiences = [
  { name: 'athlete', route: '/for-athletes', pageClass: 'landing-v10-page--athlete' },
  { name: 'coach', route: '/for-trainers', pageClass: 'landing-v10-page--coach' },
] as const;

async function openLanding(page: Page, route: string, theme: (typeof themes)[number]) {
  await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
  await page.addInitScript((value) => {
    localStorage.setItem('app-theme', value);
    localStorage.setItem('landing-theme', value);
  }, theme);
  await page.goto(route, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  await expect(page.locator('.ref-hero h1')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
}

async function assertHeroGeometry(page: Page, viewport: { width: number; height: number }) {
  const geometry = await page.evaluate(() => {
    const hero = document.querySelector<HTMLElement>('.ref-hero');
    const image = document.querySelector<HTMLImageElement>('.ref-hero .landing-hero__image');
    const copy = document.querySelector<HTMLElement>('.ref-hero .landing-hero__copy');
    const cta = document.querySelector<HTMLElement>('.ref-hero .landing-hero__actions');
    const rect = (element: Element | null) => element?.getBoundingClientRect().toJSON() ?? null;
    const heroRect = rect(hero);
    const imageRect = rect(image);
    const copyRect = rect(copy);
    const ctaRect = rect(cta);
    return {
      overflow: document.documentElement.scrollWidth - window.innerWidth,
      hero: heroRect,
      image: imageRect,
      copy: copyRect,
      cta: ctaRect,
      objectPosition: image ? getComputedStyle(image).objectPosition : '',
      naturalImage: image ? { width: image.naturalWidth, height: image.naturalHeight } : null,
    };
  });

  expect(geometry.overflow).toBeLessThanOrEqual(1);
  expect(geometry.naturalImage?.width).toBeGreaterThan(0);
  expect(geometry.naturalImage?.height).toBeGreaterThan(0);
  expect(geometry.hero).not.toBeNull();
  expect(geometry.image).not.toBeNull();
  expect(geometry.copy).not.toBeNull();
  expect(geometry.cta).not.toBeNull();

  const expectedHeight = viewport.width < 768 ? 850 : Math.min(Math.max(viewport.height, 860), 980);
  expect(geometry.hero!.height).toBeCloseTo(expectedHeight, 0);
  expect(geometry.image!.top).toBeCloseTo(geometry.hero!.top, 0);
  expect(geometry.image!.bottom).toBeCloseTo(geometry.hero!.bottom, 0);
  expect(geometry.cta!.left).toBeGreaterThanOrEqual(0);
  expect(geometry.cta!.right).toBeLessThanOrEqual(viewport.width + 1);
  expect(geometry.cta!.bottom).toBeLessThanOrEqual(geometry.hero!.bottom + 1);
  expect(geometry.objectPosition).toMatch(/\d+%\s+\d+%/);
}

for (const audience of audiences)
  for (const theme of themes) {
    test(`${audience.name} ${theme}: approved cinematic desktop geometry`, async ({ page }) => {
      for (const viewport of [
        { width: 1440, height: 900 },
        { width: 1920, height: 1080 },
        { width: 2560, height: 1440 },
        { width: 3440, height: 1440 },
      ]) {
        await page.setViewportSize(viewport);
        await openLanding(page, audience.route, theme);
        await expect(page.locator(`.${audience.pageClass} .ref-hero`)).toBeVisible();
        await assertHeroGeometry(page, viewport);
      }
    });

    test(`${audience.name} ${theme}: mobile hero remains reachable`, async ({ page }) => {
      for (const viewport of [
        { width: 320, height: 844 },
        { width: 390, height: 844 },
        { width: 430, height: 932 },
      ]) {
        await page.setViewportSize(viewport);
        await openLanding(page, audience.route, theme);
        await assertHeroGeometry(page, viewport);
        await expect(page.locator('.ref-hero .landing-hero__actions a').first()).toBeVisible();
      }
    });
  }
