const base = globalThis.PROTOTYPE_BASE ?? 'http://127.0.0.1:8765/docs/ux-proposals/issue-960/review/prototype.html';
const output = 'docs/ux-proposals/issue-960/review/screenshots/browser';
const widths = [320, 360, 393, 430, 1280];
const heights = new Map(widths.map((width) => [width, width < 681 ? 760 : 720]));

const assert = (condition, message) => {
  if (!condition) throw new Error(`browser mockup geometry: ${message}`);
};

const inspect = async (page, width, mode, state, baselinePanelHeight) => {
  const geometry = await page.evaluate(() => {
    const rect = (selector) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const box = element.getBoundingClientRect();
      return { x: box.x, y: box.y, width: box.width, height: box.height, right: box.right, bottom: box.bottom };
    };
    const panel = rect('.active-workout-rest');
    const next = rect('.rest-next');
    const actual = rect('.rest-actual');
    const actualCopy = rect('.rest-actual-copy');
    const stop = rect('.rest-stop');
    const completion = rect('.rest-complete');
    const card = rect('.exercise-card');
    const nav = rect('.bottom-nav');
    const actionButtons = [...document.querySelectorAll('.rest-actions button')].map((button) => {
      const box = button.getBoundingClientRect();
      return { width: box.width, height: box.height };
    });
    const nextTitle = document.querySelector('.rest-next-copy strong');
    return {
      panel,
      next,
      actual,
      actualCopy,
      stop,
      completion,
      card,
      nav,
      actionButtons,
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      titleClientWidth: nextTitle?.clientWidth ?? 0,
      titleScrollWidth: nextTitle?.scrollWidth ?? 0,
      titleOverflow: getComputedStyle(nextTitle).textOverflow,
      titleWhiteSpace: getComputedStyle(nextTitle).whiteSpace,
      stopAccessibleName: document.querySelector('.rest-stop')?.getAttribute('aria-label') ?? '',
      nextHidden: Boolean(document.querySelector('.rest-next')?.hidden),
      actualHidden: Boolean(document.querySelector('.rest-actual')?.hidden),
      stopHidden: Boolean(document.querySelector('.rest-stop')?.hidden),
      actionsHidden: Boolean(document.querySelector('.rest-actions')?.hidden),
      completionHidden: Boolean(document.querySelector('.rest-complete')?.hidden),
      completionText: document.querySelector('.rest-complete-copy')?.textContent ?? '',
      nextSetNote: document.querySelector('.note')?.textContent ?? '',
      panelState: document.querySelector('.active-workout-rest')?.className ?? '',
    };
  });

  assert(geometry.panel, `${width}px ${mode}/${state} panel is missing`);
  assert(geometry.documentWidth <= geometry.viewportWidth + 1, `${width}px ${mode}/${state} horizontal overflow`);
  assert(geometry.panel.x >= -1 && geometry.panel.right <= width + 1, `${width}px ${mode}/${state} panel clips viewport`);
  assert(geometry.card.bottom <= geometry.nav.y + 1, `${width}px ${mode}/${state} card overlaps bottom navigation`);
  assert(geometry.actionButtons.length === 3, `${width}px existing action count changed`);
  if (state !== 'completed') {
    assert(
      geometry.actionButtons.every(({ width: buttonWidth, height }) => buttonWidth >= 44 && height >= 44),
      `${width}px existing action target is below 44px`,
    );
  }

  if (state === 'completed') {
    assert(geometry.completion && !geometry.completionHidden, `${width}px completion state is missing`);
    assert(geometry.panelState.includes('is-complete'), `${width}px completion state did not compact the panel`);
    assert(geometry.nextHidden && geometry.actionsHidden, `${width}px completed rest keeps active controls visible`);
    assert(geometry.completion.height >= 44, `${width}px completion action row is below 44px`);
    assert(geometry.completionText.includes('Отдых завершён'), `${width}px completion copy is missing`);
    assert(geometry.nextSetNote.includes('отдельным действием'), `${width}px completion copy changed next-set semantics`);
    return geometry;
  }

  assert(geometry.titleOverflow === 'ellipsis' && geometry.titleWhiteSpace === 'nowrap', `${width}px long Далее text lost ellipsis contract`);
  if (width <= 430) {
    assert(geometry.titleScrollWidth > geometry.titleClientWidth, `${width}px long Далее fixture does not exercise ellipsis`);
  }

  if (mode === 'proposed') {
    assert(geometry.actual && geometry.stop && !geometry.actualHidden && !geometry.stopHidden, `${width}px factual cluster is missing`);
    assert(geometry.actual.x >= geometry.next.x - 1 && geometry.actual.right <= geometry.next.right + 1, `${width}px factual cluster left the Далее row`);
    assert(geometry.stop.x >= geometry.actualCopy.right - 1 && geometry.stop.right <= geometry.actual.right + 1, `${width}px compact stop is not in the right-side cluster`);
    assert(geometry.stop.width >= 44 && geometry.stop.height >= 44, `${width}px compact stop target is below 44px`);
    assert(geometry.stopAccessibleName === 'Завершить отдых', `${width}px stop action lost its explicit accessible name`);
    assert(Math.abs(geometry.panel.height - baselinePanelHeight) <= 1, `${width}px proposed panel height changed from current RestTimer`);
  }
  return geometry;
};

async page => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const captures = [];

  for (const width of widths) {
    for (const theme of ['dark', 'light']) {
      const height = heights.get(width);
      await page.setViewportSize({ width, height });

      await page.goto(`${base}?mode=baseline&state=countdown&theme=${theme}`);
      const baseline = await inspect(page, width, 'baseline', 'countdown', 0);
      await page.screenshot({ path: `${output}/${width}-${theme}-baseline.png`, fullPage: false });
      captures.push(`${width}-${theme}-baseline`);

      await page.goto(`${base}?mode=baseline&state=completed&theme=${theme}`);
      await inspect(page, width, 'baseline', 'completed', baseline.panel.height);
      await page.screenshot({ path: `${output}/${width}-${theme}-baseline-completed.png`, fullPage: false });
      captures.push(`${width}-${theme}-baseline-completed`);

      await page.goto(`${base}?mode=proposed&state=countdown&theme=${theme}`);
      await inspect(page, width, 'proposed', 'countdown', baseline.panel.height);
      await page.screenshot({ path: `${output}/${width}-${theme}-proposed-countdown.png`, fullPage: false });
      captures.push(`${width}-${theme}-proposed-countdown`);

      await page.goto(`${base}?mode=proposed&state=overtime&theme=${theme}`);
      await inspect(page, width, 'proposed', 'overtime', baseline.panel.height);
      await page.screenshot({ path: `${output}/${width}-${theme}-proposed-overtime.png`, fullPage: false });
      captures.push(`${width}-${theme}-proposed-overtime`);

      await page.goto(`${base}?mode=proposed&state=countdown&theme=${theme}`);
      await page.getByRole('button', { name: 'Завершить отдых' }).click();
      await page.locator('.rest-complete').waitFor({ state: 'visible' });
      await inspect(page, width, 'proposed', 'completed', baseline.panel.height);
      await page.screenshot({ path: `${output}/${width}-${theme}-proposed-completed.png`, fullPage: false });
      captures.push(`${width}-${theme}-proposed-completed`);
    }
  }

  return JSON.stringify({ captures: captures.length, output });
};
