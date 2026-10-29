import { expect, test, type Locator, type Page } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { installPlatformApi } from './fixtures/platform-api';
import { collectUiAudit } from './fixtures/ui-audit';
import { makeProgressReportFixture } from '../fixtures/progress-report';

const FIXED_DATE = '2026-09-06';
const WIDTHS = [320, 360, 390, 393, 430, 1280, 1440];
const OUTPUT = resolve(
  process.env.FINAL_UX_OUTPUT ?? '../.artifacts/tasks/final-ux-closeout/evidence/browser',
);
const CAPTURE = process.env.CAPTURE_FINAL_UX === '1';
const INTENTIONAL_OVERLAYS = ['.app-quick-add-layer', '.app-more-layer', '.modal__panel'];

type Surface = {
  name: string;
  path: string;
  root: string;
  heading: string | RegExp;
  proof: string;
  state: string;
  prepare?: (page: Page) => Promise<void>;
};

const SURFACES: Surface[] = [
  {
    name: 'today',
    path: '/app?section=today',
    root: '#appContent',
    heading: /^Сегодня ·/,
    proof: '.today-dashboard',
    state: 'Planned workout and existing synthetic daily data',
  },
  {
    name: 'plan',
    path: '/app?section=programs',
    root: '#appContent',
    heading: 'План',
    proof: '[data-semantic-family="training"]',
    state: 'Active program, schedule and existing revision fixture',
  },
  {
    name: 'program-management',
    path: '/app?section=programs&view=manage&start=templates',
    root: '#appContent',
    heading: 'Программы и шаблоны',
    proof: '.program-current-block',
    state: 'Populated template library and revision history',
  },
  {
    name: 'program-editor',
    path: '/app?section=programs&view=manage&start=templates',
    root: '[role="dialog"]',
    heading: /Редактирование программы|Редактировать программу|Редактирование шаблона/,
    proof: 'input',
    state:
      'Existing template with one empty workout and zero exercises; save disabled, no persistence assertion',
    prepare: async (page) => {
      await expect(page.locator('.program-current-block h4')).toBeVisible();
      await settle(page);
      await page.getByRole('button', { name: 'Редактировать шаблон', exact: true }).click();
      await expect(page.getByRole('dialog')).toBeVisible();
    },
  },
  {
    name: 'exercise-catalog',
    path: '/app?section=catalog',
    root: '#appContent',
    heading: 'Упражнения',
    proof: '.exercise-catalog-item',
    state: 'Populated general catalog using the existing exercise fixture',
  },
  {
    name: 'nutrition',
    path: '/app?section=nutrition',
    root: '#appContent',
    heading: 'Питание',
    proof: '.nutrition-diary',
    state: 'Diary empty state plus hydration goal/presets; no meal writes',
  },
  {
    name: 'progress',
    path: '/app?section=progress',
    root: '#appContent',
    heading: 'Прогресс',
    proof: '.progress-overview',
    state: 'Populated existing progress and measurement fixtures',
  },
  {
    name: 'history',
    path: '/app?section=progress&progress_view=history',
    root: '#appContent',
    heading: 'Прогресс',
    proof: '.workout-history-card',
    state: 'One completed contextual workout; completed exercise list is empty in fixture',
    prepare: async (page) => {
      const card = page.locator('.workout-history-card');
      await expect(card).toBeVisible();
      const summary = card.locator(':scope > summary');
      if (await summary.count()) await summary.click();
      await expect(card.locator('.workout-context-row')).toHaveCount(1);
    },
  },
  {
    name: 'profile-settings',
    path: '/app?section=profile',
    root: '#appContent',
    heading: 'Профиль и настройки',
    proof: '.profile-settings',
    state: 'Existing account, personal data, goals, trainer and notification sections',
  },
  {
    name: 'coach-today',
    path: '/coach',
    root: '#appContent',
    heading: 'Что требует действия?',
    proof: '#coach-today-title',
    state: 'One synthetic client; no attention/inbox items or assigned coach programs',
  },
  {
    name: 'coach-clients',
    path: '/coach?tab=clients',
    root: '#appContent',
    heading: 'Кабинет тренера',
    proof: '.coach-client-roster',
    state: 'One synthetic client; no client summary/history data',
    prepare: async (page) => {
      await expect(page.locator('.coach-client-roster')).toContainText('Анна Петрова');
    },
  },
  {
    name: 'coach-programs',
    path: '/coach?tab=programs',
    root: '#appContent',
    heading: 'Кабинет тренера',
    proof: '.coach-programs-card',
    state: 'Program operations shell and explicit empty assigned-program state',
  },
  {
    name: 'coach-tools',
    path: '/coach?tab=tools',
    root: '#appContent',
    heading: 'Кабинет тренера',
    proof: '.coach-tools-hub',
    state: 'Focused tools navigation; tool workflows are outside this bounded pass',
  },
  {
    name: 'progress-report',
    path: '/app/report',
    root: '.progress-report-page',
    heading: 'Отчёт о прогрессе',
    proof: '#report-overview-title',
    state: 'Existing canonical full synthetic report; screen rendering only',
  },
  {
    name: 'landing',
    path: '/',
    root: 'main',
    heading: /СИЛА.*В ДЕЙСТВИИ/,
    proof: '#landing-title',
    state: 'Public current production layout; local assets and synthetic product examples',
  },
];

async function settle(page: Page): Promise<void> {
  await expect(page.locator('[role="status"][aria-busy="true"]')).toHaveCount(0);
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([
      document.fonts.load('400 16px Inter', 'Прогресс Ёё ABC 123'),
      document.fonts.load('700 16px Oswald', 'Прогресс Ёё ABC 123'),
    ]);
    await new Promise<void>((done) =>
      requestAnimationFrame(() => requestAnimationFrame(() => done())),
    );
  });
}

type ScreenshotCapture = {
  file: string;
  clip: { x: number; y: number; width: number; height: number };
};

async function captureViewport(page: Page, file: string): Promise<ScreenshotCapture[]> {
  const viewport = page.viewportSize()!;
  // Preserve every desktop Landing pixel without resizing or lossy photo compression.
  const stripHeight =
    file.startsWith('landing-') && viewport.width === 1440 ? 300 : viewport.height;
  const captures: ScreenshotCapture[] = [];
  for (let y = 0; y < viewport.height; y += stripHeight) {
    const part: number = captures.length + 1;
    const name: string = part === 1 ? file : file.replace(/\.png$/, `-part${part}.png`);
    const clip = {
      x: 0,
      y,
      width: viewport.width,
      height: Math.min(stripHeight, viewport.height - y),
    };
    const png = await page.screenshot({
      path: resolve(OUTPUT, name),
      fullPage: false,
      clip,
      scale: 'css',
      animations: 'disabled',
      caret: 'hide',
    });
    expect(png.byteLength, `${name} stays within the 500 KiB artifact budget`).toBeLessThanOrEqual(
      500 * 1024,
    );
    captures.push({ file: name, clip });
  }
  return captures;
}

async function computed(surface: Locator) {
  return surface.evaluate((root) => {
    const visible = (element: Element) => {
      const box = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return (
        box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && style.display !== 'none'
      );
    };
    const typography = [
      ...root.querySelectorAll(
        'h1,h2,h3,h4,p,label,button,input,select,textarea,td,dt,dd,strong,small,.metric span,.ui-metric__label,.ui-metric__value,.badge,.eyebrow',
      ),
    ]
      .filter(visible)
      .map((element) => {
        const style = getComputedStyle(element);
        const box = element.getBoundingClientRect();
        return {
          selector: element.id
            ? `#${element.id}`
            : `${element.tagName.toLowerCase()}.${[...element.classList].join('.')}`,
          tag: element.tagName,
          type: element.getAttribute('type'),
          labels:
            element instanceof HTMLInputElement ||
            element instanceof HTMLSelectElement ||
            element instanceof HTMLTextAreaElement
              ? [...(element.labels ?? [])].map((label) => label.textContent?.trim())
              : [],
          role: element.matches('.ui-field__label')
            ? 'field-label'
            : element.matches('.ui-section-header__title')
              ? 'section-heading'
              : null,
          text: (element.getAttribute('aria-label') ?? element.textContent ?? '')
            .trim()
            .replace(/\s+/g, ' ')
            .slice(0, 100),
          fontFamily: style.fontFamily,
          fontSize: style.fontSize,
          fontWeight: style.fontWeight,
          lineHeight: style.lineHeight,
          letterSpacing: style.letterSpacing,
          color: style.color,
          backgroundColor: style.backgroundColor,
          borderRadius: style.borderRadius,
          left: box.left,
          right: box.right,
          top: box.top,
          bottom: box.bottom,
          width: box.width,
          height: box.height,
        };
      });
    const disclosures = [...root.querySelectorAll('summary')].filter(visible).map((summary) => {
      const icon = summary.querySelector(
        'svg[data-icon^="chevron-"],svg[data-icon^="disclosure-"]',
      );
      return {
        text: summary.textContent?.trim(),
        open: summary.closest('details')?.open,
        ariaExpanded: summary.getAttribute('aria-expanded'),
        icon: icon?.getAttribute('data-icon') ?? null,
        transform: icon ? getComputedStyle(icon).transform : null,
        before: getComputedStyle(summary, '::before').content,
        after: getComputedStyle(summary, '::after').content,
      };
    });
    // Resolve responsive tokens in this browser without changing the measured controls.
    const probe = document.createElement('span');
    probe.style.cssText =
      'position:fixed;visibility:hidden;pointer-events:none;width:0;height:0;contain:strict';
    root.append(probe);
    const roleFontSizes: Record<string, string> = {};
    for (const [role, token] of [
      ['field-label', '--font-size-body'],
      ['section-heading', '--font-size-section'],
    ] as const) {
      probe.style.fontSize = `var(${token})`;
      roleFontSizes[role] = getComputedStyle(probe).fontSize;
    }
    probe.remove();
    const panel = root.querySelector<HTMLElement>('.program-editor-modal');
    return {
      fontsStatus: document.fonts.status,
      fontFaces: [...document.fonts].map((face) => ({
        family: face.family,
        weight: face.weight,
        status: face.status,
      })),
      viewport: { width: innerWidth, height: innerHeight },
      documentWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
      typography,
      roleFontSizes,
      modalPanel: panel
        ? {
            box: panel.getBoundingClientRect().toJSON(),
            scrollTop: panel.scrollTop,
            scrollHeight: panel.scrollHeight,
            clientHeight: panel.clientHeight,
          }
        : null,
      disclosures,
      expandedControls: [...root.querySelectorAll('[aria-expanded]')]
        .filter(visible)
        .map((element) => ({
          text: (element.getAttribute('aria-label') ?? element.textContent)?.trim().slice(0, 100),
          expanded: element.getAttribute('aria-expanded'),
          controls: element.getAttribute('aria-controls'),
          icon: element.querySelector('svg[data-icon]')?.getAttribute('data-icon') ?? null,
        })),
    };
  });
}

async function exerciseDisclosures(page: Page, root: Locator, label: string) {
  const results = [];
  while (true) {
    const candidates = await root.locator('summary:not([data-final-ux-disclosure])').all();
    let summary: Locator | undefined;
    for (const candidate of candidates) {
      if (await candidate.isVisible()) {
        summary = candidate;
        break;
      }
    }
    if (!summary) break;
    const key = `${label}-${results.length}`;
    // Stable diagnostic locator while opening lazy nested sections; no UI/state override.
    await summary.evaluate(
      (element, value) => element.setAttribute('data-final-ux-disclosure', value),
      key,
    );
    summary = root.locator(`summary[data-final-ux-disclosure="${key}"]`);
    const initial = await summary.evaluate((element) => ({
      label: (element.getAttribute('aria-label') ?? element.textContent)?.trim(),
      open: element.closest('details')!.open,
      icon:
        element
          .querySelector('svg[data-icon^="chevron-"],svg[data-icon^="disclosure-"]')
          ?.getAttribute('data-icon') ?? null,
      iconTransform: element.querySelector(
        'svg[data-icon^="chevron-"],svg[data-icon^="disclosure-"]',
      )
        ? getComputedStyle(
            element.querySelector('svg[data-icon^="chevron-"],svg[data-icon^="disclosure-"]')!,
          ).transform
        : null,
    }));
    expect(initial.label, `${label}: disclosure accessible name`).toBeTruthy();
    const glyph = summary.locator(
      'svg.yfc-icon[data-icon^="chevron-"],svg.yfc-icon[data-icon^="disclosure-"]',
    );
    await expect(glyph).toHaveCount(1);
    await expect(glyph).toHaveAttribute('aria-hidden', 'true');
    await summary.focus();
    await expect(summary).toBeFocused();
    await summary.press('Enter');
    await expect
      .poll(() => summary.evaluate((element) => element.closest('details')!.open))
      .toBe(!initial.open);
    const state = await summary.evaluate((element) => {
      const icon = element.querySelector(
        'svg[data-icon^="chevron-"],svg[data-icon^="disclosure-"]',
      );
      const style = getComputedStyle(element);
      return {
        open: element.closest('details')!.open,
        ariaExpanded: element.getAttribute('aria-expanded'),
        icon: icon?.getAttribute('data-icon') ?? null,
        iconTransform: icon ? getComputedStyle(icon).transform : null,
        focusOutline: style.outlineStyle,
        focusOutlineWidth: style.outlineWidth,
        width: element.getBoundingClientRect().width,
        height: element.getBoundingClientRect().height,
      };
    });
    expect.soft(state.icon, `${label}: ${initial.label} has approved Icon-chevron`).not.toBeNull();
    if (state.ariaExpanded !== null) {
      // React-controlled disclosures sync aria-expanded after the native toggle.
      await expect(summary).toHaveAttribute('aria-expanded', String(state.open));
    }
    expect.soft(state.focusOutline, `${label}: ${initial.label} focus`).not.toBe('none');
    expect.soft(state.width, `${label}: ${initial.label} touch width`).toBeGreaterThanOrEqual(44);
    expect.soft(state.height, `${label}: ${initial.label} touch height`).toBeGreaterThanOrEqual(44);
    await expect(summary).toBeFocused();
    if (state.icon !== null)
      expect
        .soft(
          state.icon === initial.icon && state.iconTransform === initial.iconTransform,
          `${label}: ${initial.label} chevron changes direction`,
        )
        .toBe(false);
    await summary.press('Space');
    await expect
      .poll(() => summary.evaluate((element) => element.closest('details')!.open))
      .toBe(initial.open);
    results.push({ initial, toggled: state, restored: true });
    if (!initial.open) {
      await summary.press('Enter');
      await expect
        .poll(() => summary.evaluate((element) => element.closest('details')!.open))
        .toBe(true);
    }
  }
  for (const hidden of await root.locator('summary:not([data-final-ux-disclosure])').all()) {
    results.push({
      notVerified: await hidden.textContent(),
      reason: 'Summary is hidden in this fixture state',
    });
  }
  await settle(page);
  const touchControls = [];
  if (label.startsWith('program-management-')) {
    for (const name of ['Скачать XLSX-шаблон', 'Скачать CSV-шаблон', 'Удалить программу']) {
      const control = root.getByRole('button', { name, exact: true });
      await expect(control).toHaveCount(1);
      await expect(control).toBeVisible();
      const box = await control.boundingBox();
      expect(box, `${label}: ${name} geometry`).not.toBeNull();
      expect(box!.width, `${label}: ${name} width`).toBeGreaterThanOrEqual(44);
      expect(box!.height, `${label}: ${name} height`).toBeGreaterThanOrEqual(44);
      touchControls.push({ name, width: box!.width, height: box!.height });
    }
  }
  const expanded = await computed(root);
  const expandedAudit = await collectUiAudit(page, {
    checkTouchTargets: true,
    intentionalOverlaySelectors: INTENTIONAL_OVERLAYS,
  });
  expect
    .soft(
      expandedAudit.issues.filter((issue) => issue.severity === 'HIGH'),
      `${label}: expanded geometry and semantics`,
    )
    .toEqual([]);
  const expandedScreenshot = CAPTURE && results.length ? `${label}-390-expanded.png` : null;
  if (expandedScreenshot) await captureViewport(page, expandedScreenshot);
  return {
    checks: results,
    touchControls,
    expanded,
    expandedAudit,
    expandedScreenshot,
  };
}

test('audit visibility preserves real collisions while excluding zero-area native clips', async ({
  page,
}) => {
  await page.setContent(`
    <label style="display:block;min-height:44px">Загрузить документ
      <input id="hidden-upload" type="file" style="position:absolute;width:30px;height:44px;clip:rect(0 0 0 0)">
    </label>
    <button id="overlap-a" style="position:absolute;left:100px;top:60px;width:100px;height:44px">Первое действие</button>
    <button id="overlap-b" style="position:absolute;left:150px;top:60px;width:100px;height:44px">Второе действие</button>
    <input id="nonzero-clip" style="position:absolute;left:300px;top:60px;width:80px;height:44px;clip:rect(0 80px 44px 0)">
    <input id="static-zero-clip" style="width:80px;height:44px;clip:rect(0 0 0 0)">
  `);
  const audit = await collectUiAudit(page, { checkTouchTargets: true });
  expect(audit.issues.filter((issue) => issue.selector === '#hidden-upload')).toEqual([]);
  expect(audit.issues).toContainEqual(
    expect.objectContaining({
      code: 'UI-AUDIT-CONTROL-COLLISION',
      severity: 'HIGH',
      selector: '#overlap-a',
    }),
  );
  expect(audit.issues).toContainEqual(
    expect.objectContaining({
      code: 'UI-AUDIT-ACCESSIBLE-NAME',
      severity: 'HIGH',
      selector: '#nonzero-clip',
    }),
  );
  expect(audit.issues).toContainEqual(
    expect.objectContaining({
      code: 'UI-AUDIT-ACCESSIBLE-NAME',
      severity: 'HIGH',
      selector: '#static-zero-clip',
    }),
  );
});

for (const theme of ['dark', 'light'] as const) {
  test(`final UX closeout available screens ${theme}`, async ({ page }, testInfo) => {
    test.setTimeout(600_000);
    await mkdir(OUTPUT, { recursive: true });
    await page.clock.setFixedTime(new Date(`${FIXED_DATE}T12:00:00+03:00`));
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    const api = await installPlatformApi(page, {
      browserSession: true,
      trainerActive: true,
      fixedDate: FIXED_DATE,
      programHistory: 'many',
      progressState: 'populated',
      measurementHistory: 'many',
      longExerciseName: true,
      cardioState: 'completed',
      authProviders: ['telegram', 'google'],
    });
    await page.route(/\/api\/v1\/workouts\/progress\/report(?:\?|$)/, (route) =>
      route.fulfill({ json: makeProgressReportFixture('full') }),
    );
    const errors: Array<{ route: string; message: string }> = [];
    const unavailable: Array<{ route: string; path: string; status: number }> = [];
    page.on('pageerror', (error) => errors.push({ route: page.url(), message: error.message }));
    page.on('response', (response) => {
      if (response.url().includes('/api/') && response.status() >= 400)
        unavailable.push({
          route: page.url(),
          path: new URL(response.url()).pathname,
          status: response.status(),
        });
    });
    const requested = process.env.FINAL_UX_SURFACES?.split(',');
    const surfaces = requested
      ? SURFACES.filter((surface) => requested.includes(surface.name))
      : SURFACES;
    expect(surfaces.length, 'Requested existing audit surfaces').toBe(
      requested?.length ?? SURFACES.length,
    );
    const samples = [];
    let completed = false;
    try {
      for (const surface of surfaces) {
        await page.setViewportSize({ width: 390, height: 844 });
        await page.goto(surface.path);
        if (surface.path.startsWith('/app?') || surface.path.startsWith('/coach'))
          await expect(page.locator('.app-shell')).toBeVisible();
        if (surface.prepare) await surface.prepare(page);
        const root = page.locator(surface.root).first();
        await expect(root).toBeVisible();
        await expect(
          root
            .getByRole('heading', {
              name: surface.heading,
              exact: typeof surface.heading === 'string',
            })
            .first(),
        ).toBeVisible();
        await expect(root.locator(surface.proof).first()).toBeVisible();
        await settle(page);
        const keyboard = await exerciseDisclosures(
          page,
          root,
          `${surface.name}-${testInfo.project.name}-${theme}`,
        );
        // Each summary already proved Enter/Space; re-entry restores the original nested layout.
        await page.goto(surface.path);
        if (surface.prepare) await surface.prepare(page);
        await expect(
          root
            .getByRole('heading', {
              name: surface.heading,
              exact: typeof surface.heading === 'string',
            })
            .first(),
        ).toBeVisible();
        for (const width of WIDTHS) {
          await page.setViewportSize({ width, height: width < 900 ? 844 : 1000 });
          await expect.poll(() => page.evaluate(() => innerWidth)).toBe(width);
          if (surface.name === 'program-editor') {
            await expect
              .poll(() =>
                root
                  .locator('.program-editor-modal')
                  .evaluate((element) => Math.round(element.getBoundingClientRect().width)),
              )
              .toBe(Math.min(1180, width - 32));
          }
          await page.evaluate(() => window.scrollTo(0, 0));
          await settle(page);
          const styles = await computed(root);
          const audit = await collectUiAudit(page, {
            checkTouchTargets: width < 900,
            intentionalOverlaySelectors: INTENTIONAL_OVERLAYS,
          });
          expect
            .soft(
              audit.issues.filter((issue) => issue.severity === 'HIGH'),
              `${surface.name} ${width}px top geometry and semantics`,
            )
            .toEqual([]);
          expect
            .soft(styles.documentWidth, `${surface.name} ${width}px overflow`)
            .toBeLessThanOrEqual(width + 1);
          expect.soft(styles.fontsStatus, `${surface.name} fonts settled`).toBe('loaded');
          for (const family of ['Inter', 'Oswald']) {
            const faces = styles.fontFaces.filter(
              (face) => face.family.replace(/["']/g, '') === family,
            );
            expect
              .soft(
                faces.filter((face) => face.status === 'loaded').length,
                `${surface.name}: loaded ${family} Latin and Cyrillic faces`,
              )
              .toBeGreaterThanOrEqual(2);
          }
          const headingStyles = styles.typography.filter(
            (element) => element.tag === (surface.name === 'program-editor' ? 'H2' : 'H1'),
          );
          expect(headingStyles.length, `${surface.name} real heading`).toBeGreaterThan(0);
          for (const heading of headingStyles) {
            expect.soft(heading.fontFamily, `${surface.name} heading family`).toMatch(/^Oswald,/);
            expect.soft(heading.fontWeight, `${surface.name} heading weight`).toBe('700');
          }
          for (const role of styles.typography.filter((element) => element.role)) {
            const expectedFontSize = styles.roleFontSizes[role.role!];
            if (!expectedFontSize) throw new Error(`Missing canonical size for ${role.role}`);
            expect
              .soft(Number.parseFloat(role.fontSize), `${surface.name} ${role.role} size`)
              .toBeCloseTo(Number.parseFloat(expectedFontSize), 2);
          }
          const screenshots: string[] = [];
          const screenshotClips: Awaited<ReturnType<typeof captureViewport>> = [];
          if (CAPTURE && (width === 390 || width === 1440)) {
            const file = `${surface.name}-${testInfo.project.name}-${theme}-${width}.png`;
            const captures = await captureViewport(page, file);
            screenshots.push(...captures.map((capture) => capture.file));
            screenshotClips.push(...captures);
          }
          const panel =
            surface.name === 'program-editor' ? root.locator('.program-editor-modal') : null;
          if (panel) await panel.evaluate((element) => element.scrollTo(0, element.scrollHeight));
          else await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
          await settle(page);
          const bottomContext = panel
            ? await panel.evaluate((element) => {
                const save = element.querySelector<HTMLButtonElement>(
                  '.program-builder-footer__save',
                )!;
                return {
                  scrollContainer: '.program-editor-modal',
                  scrollTop: element.scrollTop,
                  scrollHeight: element.scrollHeight,
                  clientHeight: element.clientHeight,
                  panel: element.getBoundingClientRect().toJSON(),
                  save: save.getBoundingClientRect().toJSON(),
                  saveDisabled: save.disabled,
                };
              })
            : { scrollContainer: 'document', scrollTop: await page.evaluate(() => window.scrollY) };
          if ('save' in bottomContext) {
            expect(
              bottomContext.save.top,
              `${surface.name}: save reached above panel bottom`,
            ).toBeGreaterThanOrEqual(bottomContext.panel.top);
            expect(
              bottomContext.save.bottom,
              `${surface.name}: save reached within panel`,
            ).toBeLessThanOrEqual(bottomContext.panel.bottom);
            await expect(root.locator('.program-builder-footer__save')).toBeInViewport();
          }
          const bottomAudit = await collectUiAudit(page, {
            checkTouchTargets: width < 900,
            intentionalOverlaySelectors: INTENTIONAL_OVERLAYS,
          });
          expect
            .soft(
              bottomAudit.issues.filter((issue) => issue.severity === 'HIGH'),
              `${surface.name} ${width}px bottom geometry and semantics`,
            )
            .toEqual([]);
          if (CAPTURE && (width === 390 || width === 1440)) {
            const file = `${surface.name}-${testInfo.project.name}-${theme}-${width}-bottom.png`;
            const captures = await captureViewport(page, file);
            screenshots.push(...captures.map((capture) => capture.file));
            screenshotClips.push(...captures);
          }
          samples.push({
            surface: surface.name,
            path: surface.path,
            state: surface.state,
            theme,
            browser: testInfo.project.name,
            width,
            styles,
            audit,
            bottomAudit,
            bottomContext,
            keyboard: width === 390 ? keyboard : undefined,
            screenshots,
            screenshotClips,
          });
        }
      }
      if (
        surfaces.some(
          (surface) => surface.path.startsWith('/app') || surface.path.startsWith('/coach'),
        )
      )
        expect(
          api.meCalls(),
          'Authenticated surfaces used existing synthetic user API',
        ).toBeGreaterThan(0);
      expect(errors, 'No runtime crash hidden by a fallback heading').toEqual([]);
      completed = true;
    } finally {
      await writeFile(
        resolve(OUTPUT, `computed-${testInfo.project.name}-${theme}.json`),
        JSON.stringify(
          {
            synthetic: true,
            fixture: 'installPlatformApi and canonical progress report fixture',
            fixedDate: FIXED_DATE,
            selectedSurfaces: surfaces.map((surface) => surface.name),
            widths: WIDTHS,
            completed,
            assertionFailures: testInfo.errors.length,
            limitations: [
              'Viewport browser checks; physical keyboards, virtual keyboard, native Telegram, VoiceOver and production data not verified.',
              'Secondary coach workflows and populated per-exercise History list are not proven by this fixture.',
            ],
            errors,
            unavailable,
            samples,
          },
          null,
          2,
        ),
      );
    }
  });
}
