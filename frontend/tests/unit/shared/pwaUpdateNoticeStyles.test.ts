import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('PWA update notice styles', () => {
  it('keeps the mobile update action content-sized', () => {
    const css = readFileSync('src/styles/react.css', 'utf8');

    expect(css).toContain(`
  .pwa-update-notice button {
    flex: 0 0 auto;
    width: 100%;
  }
`);
    expect(css).not.toContain(`
  .pwa-install-prompt__actions button,
  .pwa-update-notice button {
    flex: 1 1 160px;
  }
`);
  });
});
