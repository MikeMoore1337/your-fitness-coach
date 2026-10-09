import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
type Pixels = { width: number; height: number; data: Buffer };
export const { PNG } = require(
  path.join(path.dirname(require.resolve('playwright-core/package.json')), 'lib/utilsBundle.js'),
) as {
  PNG: { sync: { read: (data: Buffer) => Pixels; write: (image: Pixels) => Buffer } };
};

export function compareLandingPixels(
  source: Pixels,
  candidate: Pixels,
  sourceCrop: { x: number; y: number; width: number; height: number },
  region = { x: 0, y: 0, width: candidate.width, height: candidate.height },
) {
  const { width, height } = region;
  if (
    sourceCrop.x < 0 ||
    sourceCrop.y < 0 ||
    region.x < 0 ||
    region.y < 0 ||
    width <= 0 ||
    height <= 0 ||
    region.x + width > sourceCrop.width ||
    region.y + height > sourceCrop.height ||
    region.x + width > candidate.width ||
    region.y + height > candidate.height ||
    sourceCrop.x + region.x + width > source.width ||
    sourceCrop.y + region.y + height > source.height
  )
    throw new Error('Invalid source/candidate region');
  const original = { width, height, data: Buffer.alloc(width * height * 4) };
  const actual = { width, height, data: Buffer.alloc(width * height * 4) };
  const heatmap = { width, height, data: Buffer.alloc(width * height * 4) };
  let changed = 0;
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++) {
      const a = ((y + region.y) * candidate.width + x + region.x) * 4;
      const b = ((y + sourceCrop.y + region.y) * source.width + x + sourceCrop.x + region.x) * 4;
      const target = (y * width + x) * 4;
      const differs = [0, 1, 2].some(
        (channel) => Math.abs(candidate.data[a + channel]! - source.data[b + channel]!) > 16,
      );
      if (differs) changed++;
      source.data.copy(original.data, target, b, b + 4);
      candidate.data.copy(actual.data, target, a, a + 4);
      heatmap.data.set(
        differs
          ? [255, 35, 90, 255]
          : [source.data[b]! / 3, source.data[b + 1]! / 3, source.data[b + 2]! / 3, 255],
        target,
      );
    }
  return { changedPixelRatio: changed / (width * height), original, actual, heatmap };
}
