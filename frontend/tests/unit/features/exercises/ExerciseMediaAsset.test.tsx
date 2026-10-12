import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ExerciseMediaAsset } from '../../../../src/features/exercises/ExerciseMediaAsset';

describe('ExerciseMediaAsset', () => {
  afterEach(cleanup);
  it('keeps a missing decorative thumbnail out of its button name', () => {
    render(
      <button>
        <ExerciseMediaAsset alt="" thumbnailUrl={null} variant="thumbnail" />
        Приседание
      </button>,
    );
    expect(screen.getByRole('button', { name: 'Приседание' })).toBeVisible();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('keeps a concise centered missing-media label with the full accessible meaning', () => {
    render(
      <ExerciseMediaAsset
        alt="Бёрд-дог: изображение упражнения"
        className="exercise-catalog-item__thumb"
        thumbnailUrl={null}
        variant="thumbnail"
      />,
    );

    const placeholder = screen.getByRole('img', {
      name: 'Бёрд-дог: изображение упражнения. Изображение пока недоступно',
    });
    expect(placeholder).toBeVisible();
    expect(screen.getByText('Нет фото')).toHaveAttribute('aria-hidden', 'true');
    expect(placeholder).toHaveClass(
      'exercise-catalog-item__thumb',
      'exercise-media-asset--missing',
    );
  });

  it('falls back from a broken animation to its local poster', () => {
    render(
      <ExerciseMediaAsset
        alt="Жим штанги лёжа: техника движения"
        animationUrl="/static/exercise-guides/gymvisual/bench-press.gif"
        thumbnailUrl="/static/exercise-guides/gymvisual/bench-press.jpg"
        variant="animation"
      />,
    );

    const image = screen.getByAltText('Жим штанги лёжа: техника движения');
    expect(image).toHaveAttribute('data-media-mode', 'animated');
    fireEvent.error(image);

    expect(image).toHaveAttribute('src', '/static/exercise-guides/gymvisual/bench-press.jpg');
    expect(image).toHaveAttribute('data-media-mode', 'static-poster');
  });
});
