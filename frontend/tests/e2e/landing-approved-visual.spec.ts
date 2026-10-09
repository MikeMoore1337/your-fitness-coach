import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test';
import cases from '../fixtures/landing-archive-normalization.json' with { type: 'json' };
import dispositions from '../fixtures/landing-archive-disposition.json' with { type: 'json' };
import regionCases from '../fixtures/landing-archive-regions.json' with { type: 'json' };
import acceptance from '../../../docs/design/references/product-v10-landing-acceptance.json' with { type: 'json' };
import { PNG, compareLandingPixels } from './fixtures/landing-pixels';
const root = path.resolve(
  process.env.LANDING_ARCHIVE_ROOT ?? '../docs/design/references/landing-archive-owner-canonical',
);
const evidence = path.resolve(
  process.env.LANDING_VISUAL_EVIDENCE_DIR ?? '../.artifacts/tasks/895/evidence/archive-restoration',
);
const ownerEvidence = path.resolve(
  process.env.LANDING_OWNER_EVIDENCE_DIR ??
    '../docs/design/references/product-v10-landing-approved/final-895',
);
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'MANIFEST.json'), 'utf8')) as {
  source_zip_sha256: string;
  images: { filename: string; sha256: string }[];
};

type ArchiveCase = (typeof cases)[number];
type ComparisonStatus =
  | 'ACTIVE_COMPARABLE'
  | 'OWNER_SUPERSEDED'
  | 'INVALID_CAPTURE'
  | 'GENUINE_VISUAL_DEFECT'
  | 'UNRESOLVED';
type Disposition = {
  comparisonStatus: ComparisonStatus;
  ownerDecision?: string;
  ownerSource?: string;
  ownerSourceScope?: string;
  baselineAssertions?: string[];
  baselineAbsent?: string[];
  captureAdjustment?: string;
  visualProof?: string;
};
const dispositionByFile = dispositions as Record<string, Disposition>;
const approvedSourceHashes: Record<string, string> = {
  'athlete-dark-desktop-first-screen.png':
    'cf6f76617f854f689a380efb8da2d38e39e56198426ddeffc3a91c532358d6d7',
  'coach-dark-desktop-first-screen.png':
    '252031c6d9b60a7c019f8734211cecdc39a25408da7dd56362ba4381a001b865',
};

for (const folder of ['candidate', 'regions', 'normalized-originals', 'diff'])
  fs.mkdirSync(path.join(evidence, folder), { recursive: true });

test('all 28 immutable owner originals retain their hashes', () => {
  expect(manifest.source_zip_sha256).toBe(
    '2be733d3539d98ecb575e9da0449978dfaf8ee993dda8bebbadb7d7e03d3acef',
  );
  expect(manifest.images).toHaveLength(28);
  for (const item of manifest.images)
    expect(
      crypto
        .createHash('sha256')
        .update(fs.readFileSync(path.join(root, 'screenshots', item.filename)))
        .digest('hex'),
    ).toBe(item.sha256);
});

test('current acceptance coverage requires every state and an approved pixel reference', () => {
  // This is an approval-completeness gate, never a pixel-parity substitute.
  const states = acceptance.mandatoryCandidateStates;
  const chapterStates = {
    connect: ['initial', 'accepted'],
    program: ['initial', 'version-2', 'assigned'],
    facts: ['initial', 'client-360'],
    review: ['initial', 'changes', 'checked'],
    decision: ['initial', 'preview-one', 'confirmed'],
    followup: ['initial', 'edited-draft', 'confirmed'],
  };
  expect(states).toHaveLength(176);
  expect(
    new Set(states.map((item) => `${item.audience}/${item.theme}/${item.width}/${item.state}`))
      .size,
  ).toBe(states.length);
  for (const theme of ['light', 'dark'])
    for (const width of [1440, 320, 390, 430]) {
      for (const audience of ['athlete', 'coach'])
        for (const state of ['full-initial', 'cycle'])
          expect(
            states.filter(
              (item) =>
                item.audience === audience &&
                item.theme === theme &&
                item.width === width &&
                item.state === state,
            ),
          ).toHaveLength(1);
      expect(
        states.filter(
          (item) =>
            item.audience === 'athlete' &&
            item.theme === theme &&
            item.width === width &&
            item.state === 'progress-ready',
        ),
      ).toHaveLength(1);
      expect(
        states.filter(
          (item) =>
            item.audience === 'coach' &&
            item.theme === theme &&
            item.width === width &&
            item.state === 'full-interacted',
        ),
      ).toHaveLength(1);
      for (const [chapter, required] of Object.entries(chapterStates))
        for (const state of required)
          expect(
            states.filter(
              (item) =>
                item.audience === 'coach' &&
                item.theme === theme &&
                item.width === width &&
                item.state === `coach-${chapter}-${state}`,
            ),
          ).toHaveLength(1);
    }
  expect(
    states.filter((item) => item.status !== 'APPROVED' || !item.approvedPixelReference),
    'NEEDS_OWNER_REVIEW: candidate screenshots cannot become approved baselines automatically. Missing current states must block the gate.',
  ).toEqual([]);
});

async function openLanding(page: Page, entry: ArchiveCase) {
  await page.setViewportSize(entry.viewport);
  await page.emulateMedia({
    colorScheme: 'dark',
    reducedMotion:
      entry.selector === '.strength-scene' || entry.state === 'bridge-effort'
        ? 'no-preference'
        : 'reduce',
  });
  await page.addInitScript(() => localStorage.setItem('app-theme', 'dark'));
  await page.goto(entry.audience === 'coach' ? '/for-trainers' : '/', { waitUntil: 'networkidle' });
  await expect(page.locator('.ref-hero h1')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

async function settleVisibleAssets(page: Page) {
  await page.waitForFunction(() =>
    [...document.images]
      .filter(
        (image) =>
          image.getBoundingClientRect().bottom > 0 &&
          image.getBoundingClientRect().top < innerHeight,
      )
      .every((image) => image.complete && image.naturalWidth > 0),
  );
  await page.evaluate(() => document.fonts.ready);
  const progress = page.locator('#progress');
  if (
    (await progress.count()) &&
    (await progress.locator('[aria-busy]').evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      return bounds.bottom > 0 && bounds.top < innerHeight;
    }))
  ) {
    await expect(progress.getByRole('heading', { name: 'Объём тренировок' })).toBeVisible();
    await expect(progress.locator('.data-viz-chart')).toBeVisible();
    await expect(progress.getByText('Загружаем пример прогресса…')).toHaveCount(0);
  }
}

async function prepareInteractiveState(page: Page, entry: ArchiveCase) {
  if (entry.state === 'summary-purchases' || entry.state === 'progress-diary') {
    const training = page.locator('#training');
    await training.getByRole('button', { name: 'Начать тренировку' }).click();
    for (let i = 0; i < 3; i++)
      await training.getByRole('button', { name: 'Завершить текущий подход' }).click();
    await training.getByRole('button', { name: 'Завершить тренировку' }).click();
    if (entry.state === 'progress-diary') {
      await training.getByRole('button', { name: 'Перейти к прогрессу' }).click();
      await page.getByRole('button', { name: 'Дневник', exact: true }).click();
      await page.getByRole('button', { name: 'Отметить съеденное в примере' }).click();
    } else await page.getByRole('button', { name: 'Покупки', exact: true }).click();
  }
  if (entry.state === 'weekly') {
    await page.locator('.ref-weekly summary').click();
    await page.getByRole('radio', { name: '3', exact: true }).check();
  }
  if (entry.state === 'changes')
    await page.getByRole('button', { name: 'Открыть изменения' }).click();
  if (entry.state === 'message')
    await page.getByRole('button', { name: 'Сообщение', exact: true }).click();
}

async function scrollToScene(page: Page, target: Locator, entry: ArchiveCase) {
  await target.evaluate(
    (element, { state, offset }) => {
      const bounds = element.getBoundingClientRect();
      let top = bounds.top + scrollY + offset;
      if (element.classList.contains('strength-scene')) {
        const sticky = element.querySelector<HTMLElement>('.strength-scene__sticky')!;
        // The archive effort frame is the lowered pose before the lift animation begins.
        const fraction = state === 'effort' ? 0.02 : state === 'record' ? 0.68 : 0.96;
        top += (element.clientHeight - sticky.clientHeight) * fraction;
      }
      if (element.classList.contains('ref-hero')) top = 0;
      window.scrollTo({ top, behavior: 'instant' });
    },
    { state: entry.state, offset: entry.scrollOffset },
  );
  await settleVisibleAssets(page);
}

async function waitForSceneState(page: Page, target: Locator, entry: ArchiveCase) {
  if (entry.selector === '#progress') {
    await expect(page.locator('#progress [aria-busy="false"]')).toHaveCount(1);
    await expect(page.locator('#progress .landing-progress__heading h3')).toHaveText(
      'Объём тренировок',
    );
    await expect(page.locator('#progress .data-viz-chart')).toBeVisible();
  }
  if (entry.selector !== '.strength-scene') return;
  const phase = entry.state === 'effort' ? '0' : entry.state === 'record' ? '1' : '2';
  await expect.poll(() => target.getAttribute('data-phase'), { timeout: 5000 }).toBe(phase);
  if (entry.state === 'effort') {
    await expect
      .poll(() =>
        target
          .locator('.strength-scene__raised')
          .evaluate((element) => Number(getComputedStyle(element).opacity)),
      )
      .toBeLessThan(0.1);
    await expect(target.locator('[data-reps]')).toHaveText('2');
  } else if (entry.state === 'record') {
    await expect(target.locator('[data-reps]')).toHaveText('3');
    await expect(target.locator('[data-record]')).toHaveText('18 кг × 3');
  } else await expect(target.locator('.strength-scene__result')).toBeVisible();
}

function writeSceneResult(entry: ArchiveCase, disposition: Disposition, result: object) {
  fs.writeFileSync(
    path.join(evidence, 'candidate', entry.file + '.json'),
    JSON.stringify(
      {
        ...entry,
        ...disposition,
        threshold: 0.01,
        acceptanceLimit: 0.01,
        channelTolerance: 16,
        dpr: 1,
        ...result,
      },
      null,
      2,
    ),
  );
}

for (const entry of cases) {
  const disposition = dispositionByFile[entry.file];
  if (!disposition) throw new Error(`Missing archive disposition for ${entry.file}`);

  if (disposition.comparisonStatus === 'OWNER_SUPERSEDED') {
    test(`${entry.file}: later-owner reference coverage, not pixel parity`, async ({
      page,
    }, testInfo: TestInfo) => {
      await openLanding(page, entry);
      for (const selector of disposition.baselineAssertions ?? [])
        await expect(page.locator(selector)).toHaveCount(1);
      for (const selector of disposition.baselineAbsent ?? [])
        await expect(page.locator(selector)).toHaveCount(0);
      const replacement = entry.audience === 'athlete' ? '#coach-promo' : '#coach-connect';
      if (disposition.visualProof !== 'FROZEN_FIRST_SCREEN')
        await page.locator(replacement).scrollIntoViewIfNeeded();
      await settleVisibleAssets(page);
      const actual = await page.screenshot({
        path: path.join(evidence, 'candidate', `owner-baseline-${entry.file}`),
        animations: 'disabled',
      });
      const ownerSourcePath = disposition.ownerSource
        ? path.resolve(ownerEvidence, path.basename(disposition.ownerSource))
        : null;
      const ownerSourceHash =
        ownerSourcePath && fs.existsSync(ownerSourcePath)
          ? crypto.createHash('sha256').update(fs.readFileSync(ownerSourcePath)).digest('hex')
          : null;
      if (ownerSourceHash && disposition.ownerSource)
        expect(ownerSourceHash).toBe(approvedSourceHashes[path.basename(disposition.ownerSource)]);
      writeSceneResult(entry, disposition, {
        comparisonResult: 'NOT_COMPARABLE',
        ownerBaselineResult:
          disposition.visualProof === 'FROZEN_FIRST_SCREEN'
            ? 'CHECK_SEPARATE_FROZEN_PIXEL_SUITE'
            : 'VISUAL_NOT_PROVEN',
        structureResult: 'PASS',
        ownerApproval: false,
        approvedReferenceScope: 'FIRST_SCREEN_ONLY; current pixels require separate comparison',
        ownerSourcePresent: Boolean(ownerSourcePath && fs.existsSync(ownerSourcePath)),
        ownerSourcePath,
        ownerSourceHash,
      });
      await testInfo.attach('current-owner-baseline', { body: actual, contentType: 'image/png' });
      expect(
        disposition.visualProof,
        'VISUAL_NOT_PROVEN: a first-screen reference cannot approve a replacement lower scene.',
      ).toBe('FROZEN_FIRST_SCREEN');
    });
    continue;
  }

  test(`${entry.file}: ${entry.description}`, async ({ page }, testInfo) => {
    await openLanding(page, entry);
    await prepareInteractiveState(page, entry);
    const target = page.locator(entry.selector).first();
    await scrollToScene(page, target, entry);
    await waitForSceneState(page, target, entry);
    // Lazy content changes section height; recompute scroll after its real state is ready.
    await scrollToScene(page, target, entry);
    await waitForSceneState(page, target, entry);
    const actual = await page.screenshot({
      path: path.join(evidence, 'candidate', entry.file),
      clip: entry.candidateClip,
      animations: 'disabled',
    });
    const source = PNG.sync.read(fs.readFileSync(path.join(root, 'screenshots', entry.file)));
    const candidate = PNG.sync.read(actual);
    const crop = entry.sourceCrop;
    expect(candidate.width).toBe(crop.width);
    expect(candidate.height).toBe(crop.height);
    const scene = regionCases[entry.file as keyof typeof regionCases];
    const full = compareLandingPixels(source, candidate, crop);
    const results = scene.regions.map((region) => {
      const result = compareLandingPixels(source, candidate, crop, region);
      const prefix = `${entry.file}-${region.name}`;
      for (const [suffix, pixels] of [
        ['original', result.original],
        ['candidate', result.actual],
        ['diff', result.heatmap],
      ] as const)
        fs.writeFileSync(
          path.join(evidence, 'regions', `${prefix}-${suffix}.png`),
          PNG.sync.write(pixels),
        );
      return {
        ...region,
        changedPixelRatio: result.changedPixelRatio,
        threshold: 0.01,
        result: result.changedPixelRatio <= 0.01 ? 'PASS' : 'FAIL',
        original: `regions/${prefix}-original.png`,
        candidate: `regions/${prefix}-candidate.png`,
        heatmap: `regions/${prefix}-diff.png`,
      };
    });
    fs.writeFileSync(
      path.join(evidence, 'normalized-originals', entry.file),
      PNG.sync.write(full.original),
    );
    fs.writeFileSync(path.join(evidence, 'diff', entry.file), PNG.sync.write(full.heatmap));
    const geometry = await page.locator('.ref-section, .strength-scene').evaluateAll((elements) =>
      elements.map((element) => ({
        id: element.id,
        className: element.className,
        bounds: element.getBoundingClientRect().toJSON(),
      })),
    );
    writeSceneResult(entry, disposition, {
      comparisonResult: results.every((result) => result.result === 'PASS')
        ? 'REGION_PASS'
        : 'REGION_FAIL',
      changedPixelRatio: full.changedPixelRatio,
      fullScreenRatioIsAcceptance: false,
      regions: results,
      excluded: scene.excluded,
      geometry,
      ownerApproval: false,
    });
    await testInfo.attach('candidate', { body: actual, contentType: 'image/png' });
    expect(
      results
        .filter((result) => result.result !== 'PASS')
        .map((result) => ({ region: result.name, ratio: result.changedPixelRatio })),
      'Unchanged archive region differs. Inspect capture provenance and the regional gallery; never change the reference or tolerance.',
    ).toEqual([]);
  });
}
