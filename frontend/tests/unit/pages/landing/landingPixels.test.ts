import { describe, expect, it } from 'vitest';
import { compareLandingPixels } from '../../../e2e/fixtures/landing-pixels';

describe('immutable regional pixel comparison', () => {
  it('uses the original crop and preserves the 16-channel tolerance', () => {
    const source = {
      width: 3,
      height: 1,
      data: Buffer.from([0, 0, 0, 255, 10, 20, 30, 255, 50, 60, 70, 255]),
    };
    const candidate = {
      width: 2,
      height: 1,
      data: Buffer.from([26, 20, 30, 255, 50, 60, 87, 255]),
    };
    const result = compareLandingPixels(source, candidate, { x: 1, y: 0, width: 2, height: 1 });
    expect(result.changedPixelRatio).toBe(0.5);
    expect([...result.heatmap.data.slice(4, 8)]).toEqual([255, 35, 90, 255]);
    expect([...result.original.data.slice(0, 4)]).toEqual([10, 20, 30, 255]);
    expect(
      compareLandingPixels(
        source,
        candidate,
        { x: 1, y: 0, width: 2, height: 1 },
        { x: 0, y: 0, width: 1, height: 1 },
      ).changedPixelRatio,
    ).toBe(0);
  });
  it('fails closed when a normalization region is outside either image', () => {
    const pixels = { width: 1, height: 1, data: Buffer.from([0, 0, 0, 255]) };
    expect(() => compareLandingPixels(pixels, pixels, { x: 1, y: 0, width: 1, height: 1 })).toThrow(
      'Invalid source/candidate region',
    );
    expect(() =>
      compareLandingPixels(pixels, pixels, { x: -1, y: 0, width: 1, height: 1 }),
    ).toThrow();
    expect(() =>
      compareLandingPixels(pixels, pixels, { x: 0, y: 0, width: 0, height: 1 }),
    ).toThrow();
  });
});
