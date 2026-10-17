import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const scriptPath = path.join(frontendRoot, 'scripts', 'check_thick_lime_edges.mjs');
const fixtureRoot = path.join(frontendRoot, 'tests', 'fixtures', 'styles', 'thick-lime-edges');

function runFixture(name: string) {
  return spawnSync(process.execPath, [scriptPath, '--path', path.join(fixtureRoot, name)], {
    cwd: frontendRoot,
    encoding: 'utf8',
  });
}

describe('thick lime edge safeguard', () => {
  it('fails on the isolated negative fixture', () => {
    const result = runFixture('forbidden.css');
    const output = result.stderr;

    expect(result.status).toBe(1);
    expect(output).toContain('one-sided lime border');
    expect(output).toContain('one-sided inset lime shadow');
    expect(output).toContain('positioned pseudo-element');
    expect(output).toContain('lime gradient');
  });

  it('fails on inline and CSS-in-JS-like styles', () => {
    const result = runFixture('forbidden.tsx');
    const output = result.stderr;

    expect(result.status).toBe(1);
    expect(output).toContain('inline style creates a one-sided lime border');
    expect(output).toContain('inline style creates a one-sided inset lime shadow');
    expect(output).toContain('positioned pseudo-element');
  });

  it('passes the allowed thin, state and semantic styles', () => {
    const cssResult = runFixture('allowed.css');
    const tsxResult = runFixture('allowed.tsx');

    expect(cssResult.status).toBe(0);
    expect(cssResult.stderr).toBe('');
    expect(tsxResult.status).toBe(0);
    expect(tsxResult.stderr).toBe('');
  });

  it('keeps the Progress fixes selector-specific and preserves DataConfidence', () => {
    const uxStyles = readFileSync(
      path.join(frontendRoot, 'src', 'styles', 'ux-ia-redesign.css'),
      'utf8',
    );
    const v2Styles = readFileSync(
      path.join(frontendRoot, 'src', 'styles', 'design-v2.css'),
      'utf8',
    );
    const systemStyles = readFileSync(
      path.join(frontendRoot, 'src', 'styles', 'design-system.css'),
      'utf8',
    );

    expect(uxStyles).not.toMatch(
      /\.app-section--progress \.progress-insights__column--good\s*\{[^}]*border-left\s*:/s,
    );
    expect(v2Styles).not.toMatch(
      /\.app-section--progress \.program-history-workout\s*\{[^}]*box-shadow\s*:\s*inset\s+3px\s+0/s,
    );
    expect(v2Styles).not.toMatch(
      /\.progress-report-confidence\s*\{[^}]*border-left\s*:\s*3px\s+solid\s+var\(--v2-lime\)/s,
    );
    expect(v2Styles).not.toMatch(
      /\.progress-report-tma-fallback\s*\{[^}]*border-left\s*:\s*3px\s+solid\s+var\(--v2-lime\)/s,
    );
    expect(v2Styles).not.toMatch(
      /\.progress-report-handoff-banner\s*\{[^}]*border-left\s*:\s*3px\s+solid\s+var\(--v2-lime\)/s,
    );
    expect(v2Styles).not.toMatch(
      /\.nutrition-report-coverage\s*\{[^}]*box-shadow\s*:\s*inset\s+3px\s+0\s+var\(--v2-lime\)/s,
    );
    expect(systemStyles).toMatch(
      /\.data-confidence\s*\{[^}]*border\s*:\s*1px solid var\(--v2-border\)/s,
    );
    expect(systemStyles).not.toMatch(
      /\.data-confidence\s*\{[^}]*border-inline-start-width\s*:\s*3px/s,
    );
  });
});
