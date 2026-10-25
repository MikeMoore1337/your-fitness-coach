import { describe, expect, it } from 'vitest';
import {
  agentationDevelopmentHtml,
  agentationDevelopmentPlugin,
} from '../../devtools/agentation-dev-plugin';

describe('Agentation local-only Vite integration', () => {
  it('leaves HTML unchanged unless explicitly enabled', () => {
    const html = '<!doctype html><html><body></body></html>';
    expect(agentationDevelopmentHtml(html, false)).toBe(html);
  });

  it('injects an external development-only module on explicit opt-in', () => {
    const result = agentationDevelopmentHtml('<html></html>', true);
    expect(typeof result).toBe('object');
    expect(result).toEqual({
      html: '<html></html>',
      tags: [
        {
          tag: 'script',
          attrs: { type: 'module', src: '/devtools/agentation.jsx' },
          injectTo: 'body',
        },
      ],
    });
  });

  it('plugin only applies to the Vite serve command, never production build', () => {
    const plugin = agentationDevelopmentPlugin();
    expect(plugin.name).toBe('yfc-optional-local-agentation');
    expect(plugin.apply).toBe('serve');
  });
});
