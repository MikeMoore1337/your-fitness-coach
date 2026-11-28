import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import type { TestInfo } from '@playwright/test';
import { PNG } from './landing-pixels';

type Tile = { file: string; sha256: string; x: number; y: number; width: number; height: number };
export type Reference = { width: number; height: number; pixelsSha256: string; tiles: Tile[] };
const root = path.resolve('tests/fixtures/landing-approved-c9');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'MANIFEST.json'), 'utf8')) as {
  sourceCommit: string;
  reviewCommit: string;
  references: Record<string, Reference>;
};
const hash = (bytes: Buffer) => crypto.createHash('sha256').update(bytes).digest('hex');

export function acceptedLandingReference(
  testInfo: TestInfo,
  suite: 'frozen' | 'archive',
  file: string,
) {
  if (
    manifest.sourceCommit !== 'c9f05232737f9072eb7716c120426a52ae990ad7' ||
    manifest.reviewCommit !== 'e5afecccc5abba141341cb2022abeafbf53ec49e'
  ) {
    throw new Error('Unexpected approved Landing reference provenance');
  }
  const browser = ['chromium', 'firefox', 'webkit'].includes(testInfo.project.name)
    ? testInfo.project.name
    : (testInfo.project.use.browserName ?? 'chromium');
  const key = `${process.platform}/${browser}/${suite}/${file}`;
  const reference = manifest.references[key];
  if (!reference) throw new Error(`Missing accepted Landing reference: ${key}`);
  return decodeLandingReference(reference, (fileName) =>
    fs.readFileSync(path.join(root, fileName)),
  );
}

export function decodeLandingReference(reference: Reference, readTile: (file: string) => Buffer) {
  const pixels = Buffer.alloc(reference.width * reference.height * 4);
  const coverage = Buffer.alloc(reference.width * reference.height);
  for (const tile of reference.tiles) {
    if (!/^tiles\/[a-f0-9]{64}\.png$/.test(tile.file)) throw new Error('Invalid reference path');
    const bytes = readTile(tile.file);
    if (hash(bytes) !== tile.sha256) throw new Error(`Reference tile hash mismatch: ${tile.file}`);
    const image = PNG.sync.read(bytes);
    if (
      image.width !== tile.width ||
      image.height !== tile.height ||
      tile.x < 0 ||
      tile.y < 0 ||
      tile.x + tile.width > reference.width ||
      tile.y + tile.height > reference.height
    ) {
      throw new Error(`Invalid reference tile geometry: ${tile.file}`);
    }
    for (let y = 0; y < tile.height; y++) {
      const offset = (tile.y + y) * reference.width + tile.x;
      for (let x = 0; x < tile.width; x++) {
        if (coverage[offset + x] !== 0) throw new Error('Overlapping reference tiles');
        coverage[offset + x] = 1;
      }
      image.data.copy(pixels, offset * 4, y * tile.width * 4, (y + 1) * tile.width * 4);
    }
  }
  if (coverage.includes(0) || hash(pixels) !== reference.pixelsSha256) {
    throw new Error('Incomplete or altered accepted reference');
  }
  return { width: reference.width, height: reference.height, data: pixels };
}
