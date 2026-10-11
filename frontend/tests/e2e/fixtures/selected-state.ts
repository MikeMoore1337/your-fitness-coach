import { expect, type Locator } from '@playwright/test';

export async function expectSelectedChoice(control: Locator) {
  await expect(control).toHaveAttribute('data-yfc-choice', /capsule|compact/);
  const read = () =>
    control.evaluate((element) => {
      const style = getComputedStyle(element);
      const probe = document.createElement('span');
      probe.style.cssText =
        'position:fixed;visibility:hidden;background:var(--v2-selected-surface);color:var(--v2-selected-ink);box-shadow:var(--v2-selected-relief)';
      element.append(probe);
      const expected = getComputedStyle(probe);
      const matchesTokens =
        style.backgroundImage === expected.backgroundImage &&
        style.color === expected.color &&
        style.boxShadow === expected.boxShadow;
      probe.remove();
      const luminance = (color: number[]) =>
        color
          .map((value) => {
            const channel = value / 255;
            return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
          })
          .reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index]!, 0);
      const foreground = luminance(
        style.color
          .match(/[\d.]+/g)!
          .slice(0, 3)
          .map(Number),
      );
      const contrasts = [...style.backgroundImage.matchAll(/rgb\(([^)]+)\)/g)].map((match) => {
        const background = luminance(
          match[1]!
            .match(/[\d.]+/g)!
            .slice(0, 3)
            .map(Number),
        );
        return (
          (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05)
        );
      });
      const box = element.getBoundingClientRect();
      return {
        matchesTokens,
        surface: style.backgroundImage,
        relief: style.boxShadow,
        color: style.color,
        icons: [...element.querySelectorAll('.yfc-icon')].map(
          (icon) => getComputedStyle(icon).color,
        ),
        contrast: contrasts.length ? Math.min(...contrasts) : 0,
        width: box.width,
        height: box.height,
      };
    });
  await expect.poll(async () => (await read()).matchesTokens).toBe(true);
  const result = await read();
  expect(result.matchesTokens, JSON.stringify(result)).toBe(true);
  expect(result.surface).not.toBe('none');
  expect(result.relief).toContain('inset');
  expect(result.contrast).toBeGreaterThanOrEqual(4.5);
  expect(result.width).toBeGreaterThanOrEqual(44);
  expect(result.height).toBeGreaterThanOrEqual(44);
  await expect.poll(async () => (await read()).icons).toEqual(result.icons.map(() => result.color));
  return result;
}
