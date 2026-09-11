import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Icon } from '../../../../src/shared/ui/Icon';
import type { IconName } from '../../../../src/shared/ui/Icon';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

describe('Icon', () => {
  it('provides a real flat raster for every supported semantic icon', () => {
    const source = readFileSync(resolve('src/shared/ui/Icon.tsx'), 'utf8');
    const names = [
      ...source.slice(0, source.indexOf('export interface')).matchAll(/\| '([^']+)'/g),
    ];
    expect(names.length).toBeGreaterThan(60);
    for (const [, name] of names) {
      const { container, unmount } = render(<Icon name={name as IconName} />);
      const src = container.querySelector('img')?.getAttribute('src');
      expect(src).toMatch(/^\/assets\/icons\/flat-[a-z-]+\.webp$/);
      expect(existsSync(resolve('public', src!.slice(1)))).toBe(true);
      unmount();
    }
  });
  it('renders theme-specific raster assets at supported optical sizes', () => {
    const { container } = render(<Icon name="nav-progress" size={20} />);
    const icon = container.querySelector('[data-icon="nav-progress"]');

    expect(icon).toHaveStyle({ width: '20px', height: '20px' });
    expect(icon?.querySelector('.yfc-icon__light')).toHaveAttribute(
      'src',
      '/assets/icons/flat-progress.webp',
    );
    expect(icon?.querySelector('.yfc-icon__dark')).toHaveAttribute(
      'src',
      '/assets/icons/flat-progress.webp',
    );
    expect(icon).toHaveAttribute('aria-hidden', 'true');
  });

  it('keeps an explicit accessible name only when the icon carries meaning itself', () => {
    const { container } = render(<Icon label="Нет доступа" name="permission-denied" />);
    const icon = container.querySelector('[data-icon="permission-denied"]');

    expect(icon).toHaveAttribute('role', 'img');
    expect(icon).toHaveAttribute('aria-label', 'Нет доступа');
    expect(icon).not.toHaveAttribute('aria-hidden');
  });

  it('uses the approved dumbbell for the exercise catalogue', () => {
    const { container } = render(<Icon name="nav-exercise-catalog" size={16} />);
    const icon = container.querySelector('[data-icon="nav-exercise-catalog"]');

    expect(icon).toHaveStyle({ width: '16px', height: '16px' });
    expect(icon?.querySelector('.yfc-icon__dark')).toHaveAttribute(
      'src',
      '/assets/icons/flat-dumbbell.webp',
    );
  });

  it('keeps action icons decorative inside their named controls', () => {
    const { container } = render(<Icon name="theme-moon" />);
    const icon = container.querySelector('[data-icon="theme-moon"]');

    expect(icon?.querySelector('svg')).not.toBeInTheDocument();
    expect(icon?.querySelectorAll('img')).toHaveLength(2);
    icon?.querySelectorAll('img').forEach((image) => expect(image).toHaveAttribute('alt', ''));
  });
});
