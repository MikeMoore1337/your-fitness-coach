import crypto from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { decodeLandingReference, type Reference } from '../e2e/fixtures/landing-accepted-reference';
import { PNG } from '../e2e/fixtures/landing-pixels';

const sha = (value: Buffer) => crypto.createHash('sha256').update(value).digest('hex');
const pixels = Buffer.from([255, 0, 0, 255, 0, 255, 0, 255]);
const png = PNG.sync.write({ width: 2, height: 1, data: pixels });
const digest = sha(png);
const reference: Reference = {
  width: 2,
  height: 1,
  pixelsSha256: sha(pixels),
  tiles: [{ file: `tiles/${digest}.png`, sha256: digest, x: 0, y: 0, width: 2, height: 1 }],
};

describe('accepted Landing reference integrity', () => {
  it('reconstructs exactly the accepted pixels', () => {
    expect(decodeLandingReference(reference, () => png).data).toEqual(pixels);
  });

  it('rejects altered bytes, missing pixels and overlapping tiles', () => {
    expect(() => decodeLandingReference(reference, () => Buffer.from('changed'))).toThrow(
      'hash mismatch',
    );
    expect(() => decodeLandingReference({ ...reference, tiles: [] }, () => png)).toThrow(
      'Incomplete',
    );
    expect(() =>
      decodeLandingReference(
        { ...reference, tiles: [...reference.tiles, ...reference.tiles] },
        () => png,
      ),
    ).toThrow('Overlapping');
  });
});
