import { expect, type Locator } from '@playwright/test';

export async function scrollIntoStablePosition(target: Locator) {
  await target.scrollIntoViewIfNeeded();
  let previous: { x: number; y: number } | null = null;
  let stableSamples = 0;
  await expect
    .poll(async () => {
      const current = await target.boundingBox();
      stableSamples =
        current &&
        previous &&
        Math.abs(current.x - previous.x) < 0.5 &&
        Math.abs(current.y - previous.y) < 0.5
          ? stableSamples + 1
          : 0;
      previous = current;
      return stableSamples;
    })
    .toBeGreaterThanOrEqual(2);
}
