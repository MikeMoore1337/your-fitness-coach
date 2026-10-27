import type { IndexHtmlTransformResult, Plugin } from 'vite';

/**
 * Local development opt-in only. Never inject devtools into a production build.
 * Package installation is deliberately optional and never part of npm ci.
 */
export function agentationDevelopmentHtml(
  html: string,
  enabled: boolean,
): IndexHtmlTransformResult {
  if (!enabled) return html;
  return {
    html,
    tags: [
      {
        tag: 'script',
        attrs: { type: 'module', src: '/devtools/agentation.jsx' },
        injectTo: 'body',
      },
    ],
  };
}

export function agentationDevelopmentPlugin(): Plugin {
  return {
    name: 'yfc-optional-local-agentation',
    apply: 'serve',
    transformIndexHtml(html) {
      return agentationDevelopmentHtml(html, process.env.YFC_AGENTATION === '1');
    },
  };
}
