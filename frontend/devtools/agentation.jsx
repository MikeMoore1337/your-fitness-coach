/* global window, document */
// Operator-installed optional dependency: npm install --no-save --package-lock=false agentation@3.1.2
// Served only by the Vite development server after explicit YFC_AGENTATION=1.
import { Agentation } from 'agentation';
import { createElement } from 'react';
import { createRoot } from 'react-dom/client';

const isLoopback = ['localhost', '127.0.0.1', '::1', '[::1]'].includes(window.location.hostname);
const isDesktop = window.matchMedia('(min-width: 768px)').matches;

if (isLoopback && isDesktop && !window.Telegram?.WebApp) {
  const mount = document.createElement('div');
  mount.id = 'yfc-local-agentation';
  document.body.append(mount);

  // No MCP endpoint, webhook or onSubmit: copying notes remains a local user action.
  createRoot(mount).render(
    createElement(Agentation, {
      appName: 'YFC local UI review',
      enableKeyboardShortcuts: false,
      identifyingAttributes: ['data-testid', 'data-qa'],
    }),
  );
}
