import { expect, type Page } from '@playwright/test';

// Synthetic data exercises the shared renderer, including unbroken imported names.
export function previewTemplates() {
  return [
    ['nsuns', 'nSuns - 4-дневная программа', 4, 2],
    ['phul', 'PHUL (сила и рост мышц, верх/низ)', 4, 6],
    ['short', 'Короткая программа', 1, 1],
    ['long', 'Длинная программа / StrengthAndHypertrophy'.repeat(3), 7, 12],
    ['own', 'Моя программа — длинные русские и EnglishExerciseNames', 3, 6],
    ['coach', 'План тренера — силовая подготовка', 4, 6],
  ].map(([key, title, dayCount, exerciseCount], index) => ({
    key: String(key),
    id: 11850 + index,
    title: String(title),
    slug: `preview-${key}`,
    goal: 'muscle_gain',
    level: 'intermediate',
    split_type: 'upper_lower',
    owner_user_id: key === 'own' ? 1 : null,
    created_by_user_id: key === 'coach' ? 99 : null,
    assigned_by_user_id: key === 'coach' ? 99 : null,
    assigned_by_full_name: key === 'coach' ? 'Тренер Анна' : null,
    is_public: key !== 'own' && key !== 'coach',
    is_example: key !== 'own' && key !== 'coach',
    is_assigned_to_current_user: key === 'phul' || key === 'coach',
    is_active_for_current_user: key === 'phul' || key === 'coach',
    can_edit: key === 'own',
    default_duration_weeks: 12,
    program_metadata: {
      days_per_week: dayCount,
      equipment: ['barbell', 'dumbbell', 'bench', 'cable', 'machine'],
    },
    days: Array.from({ length: Number(dayCount) }, (_, day) => ({
      id: 118500 + day,
      day_number: day + 1,
      title: day % 2 ? 'Низ тела — сила и рост мышц' : 'Верх тела — сила и рост мышц',
      exercises: Array.from({ length: Number(exerciseCount) }, (_, exercise) => ({
        id: 1185000 + day * 100 + exercise,
        exercise_id: 1,
        exercise_title:
          exercise % 2
            ? 'StandingDumbbellShoulderPressWithControlledEccentricPhase'
            : 'Жим лёжа со штангой в силовой стойке с контролируемым опусканием',
        metric_type: 'strength',
        prescribed_sets: 4,
        prescribed_reps: '8–12',
        rest_seconds: 120,
        notes: 'Контролируйте движение. Длинное примечание для проверки полного переноса текста.',
        has_guide: true,
      })),
    })),
  }));
}

export async function measurePreview(page: Page) {
  return page.evaluate(() => {
    const panel = document.querySelector<HTMLElement>('.program-example-modal__panel')!;
    const content = panel.querySelector<HTMLElement>('.program-example-modal__content')!;
    const clip = content.getBoundingClientRect();
    const nodes = [
      document.documentElement,
      document.body,
      panel.parentElement!,
      panel,
      ...panel.querySelectorAll<HTMLElement>('*'),
    ];
    const containers = nodes
      .filter((node) => node.clientWidth > 0)
      .map((node) => {
        const style = getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        return {
          node: `${node.tagName.toLowerCase()}.${node.className}`,
          assistiveOnly: node.classList.contains('sr-only'),
          clientWidth: node.clientWidth,
          scrollWidth: node.scrollWidth,
          scrollLeft: node.scrollLeft,
          clientHeight: node.clientHeight,
          scrollHeight: node.scrollHeight,
          scrollTop: node.scrollTop,
          rect: {
            x: rect.x,
            y: rect.y,
            right: rect.right,
            bottom: rect.bottom,
            width: rect.width,
            height: rect.height,
          },
          overflowX: style.overflowX,
          overflowY: style.overflowY,
          minWidth: style.minWidth,
          maxWidth: style.maxWidth,
          display: style.display,
          width: style.width,
          boxSizing: style.boxSizing,
          marginLeft: style.marginLeft,
          marginRight: style.marginRight,
          paddingLeft: style.paddingLeft,
          paddingRight: style.paddingRight,
        };
      });
    const clippedText: string[] = [];
    const clippedControls = Array.from(
      panel.querySelectorAll<HTMLElement>(
        '.program-example-modal__close, .program-example-modal__actions button',
      ),
    )
      .filter((node) => {
        const rect = node.getBoundingClientRect();
        const top = node.classList.contains('program-example-modal__close') ? clip.top : 0;
        return (
          rect.left < clip.left - 1 ||
          rect.right > clip.right + 1 ||
          rect.top < top - 1 ||
          rect.bottom > window.innerHeight + 1
        );
      })
      .map((node) => node.getAttribute('aria-label') ?? node.textContent?.trim());
    for (const element of panel.querySelectorAll<HTMLElement>('*')) {
      if (element.closest('.sr-only, svg')) continue;
      for (const node of element.childNodes) {
        if (node.nodeType !== Node.TEXT_NODE || !node.textContent?.trim()) continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        for (const rect of range.getClientRects()) {
          if (rect.width && (rect.left < clip.left - 1 || rect.right > clip.right + 1)) {
            clippedText.push(`${element.tagName}: ${node.textContent.trim()}`);
          }
        }
      }
    }
    return {
      containers,
      clippedText,
      clippedControls,
      headerGap:
        panel.querySelector<HTMLElement>('.program-example-modal__head')!.getBoundingClientRect()
          .top - clip.top,
      verticalScrollers: containers
        .filter(
          (item) =>
            ['auto', 'scroll'].includes(item.overflowY) &&
            item.scrollHeight > item.clientHeight + 1,
        )
        .map((item) => item.node),
      horizontalOverflow: containers.filter(
        (item) => !item.assistiveOnly && item.scrollWidth > item.clientWidth + 1,
      ),
      horizontalDrift: containers.filter((item) => Math.abs(item.scrollLeft) > 1),
      documentX: window.scrollX,
      documentY: window.scrollY,
    };
  });
}

export async function previewGesture(page: Page, browserName: string, dx: number, dy: number) {
  const content = page.locator('.program-example-modal__content');
  const box = (await content.boundingBox())!;
  const x = box.x + box.width * 0.6;
  const y = box.y + box.height * 0.65;
  if (browserName === 'chromium') {
    const session = await page.context().newCDPSession(page);
    await session.send('Input.dispatchTouchEvent', {
      type: 'touchStart',
      touchPoints: [{ x, y }],
    });
    for (let step = 1; step <= 8; step++) {
      await session.send('Input.dispatchTouchEvent', {
        type: 'touchMove',
        touchPoints: [{ x: x + (dx * step) / 8, y: y + (dy * step) / 8 }],
      });
    }
    await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await session.detach();
  } else {
    // WebKit's public Playwright API has no native touch-drag injection.
    await page.mouse.move(x, y);
    await page.mouse.wheel(-dx, -dy);
  }
  await expect
    .poll(async () => {
      const first = await content.evaluate((node) => node.scrollTop);
      await page.evaluate(
        () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())),
      );
      return Math.abs(first - (await content.evaluate((node) => node.scrollTop)));
    })
    .toBeLessThanOrEqual(1);
}
