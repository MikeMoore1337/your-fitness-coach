import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Icon } from '../../../../src/shared/ui/Icon';

describe('Icon', () => {
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
