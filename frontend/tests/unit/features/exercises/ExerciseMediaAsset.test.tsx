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

  it('keeps animation primary and uses the verified HD poster only after a playback failure', () => {
    render(
      <ExerciseMediaAsset
        alt="Тяга: техника движения"
        animationUrl="/static/exercise-guides/gymvisual/example.gif"
        thumbnailUrl="/static/exercise-guides/exercises-media/example/poster-1280.jpg"
        thumbnailSources={[
          {
            url: '/static/exercise-guides/exercises-media/example/poster-1280.webp',
            mime_type: 'image/webp',
            width: 1280,
          },
          {
            url: '/static/exercise-guides/exercises-media/example/poster-1280.jpg',
            mime_type: 'image/jpeg',
            width: 1280,
          },
        ]}
        preferredMode="static"
        variant="animation"
      />,
    );

    const image = screen.getByAltText('Тяга: техника движения');
    expect(image).toHaveAttribute('data-media-mode', 'animated');
    expect(image).toHaveAttribute('src', '/static/exercise-guides/gymvisual/example.gif');
    fireEvent.error(image);
    const fallback = screen.getByAltText('Тяга: техника движения');
    expect(fallback).toHaveAttribute('data-media-mode', 'static-poster');
    expect(fallback).toHaveAttribute(
      'src',
      '/static/exercise-guides/exercises-media/example/poster-1280.jpg',
    );
    expect(document.querySelector('source[type="image/webp"]')).toHaveAttribute(
      'srcset',
      expect.stringContaining('poster-1280.webp 1280w'),
    );
  });
  it('uses approved AI video before the original GIF and recovers on error', () => {
    render(
      <ExerciseMediaAsset
        alt="Становая тяга"
        variant="animation"
        animationUrl="/static/exercise-guides/gymvisual/deadlift.gif"
        thumbnailUrl="/static/exercise-guides/gymvisual/deadlift.jpg"
        videoSources={[
          {
            url: '/static/exercise-guides/gymvisual/ai-reviewed/deadlift-x4plus-720.mp4',
            mime_type: 'video/mp4',
            width: 720,
          },
        ]}
      />,
    );
    const video = screen.getByLabelText('Становая тяга');
    expect(video).toHaveAttribute('data-media-mode', 'video');
    expect(video).toHaveAttribute('autoplay');
    expect(video).toHaveProperty('muted', true);
    expect(video).toHaveAttribute('playsinline');
    fireEvent.error(video);
    const fallback = screen.getByAltText('Становая тяга');
    expect(fallback).toHaveAttribute('src', '/static/exercise-guides/gymvisual/deadlift.gif');
    expect(fallback).toHaveAttribute('data-media-mode', 'animated');
  });
});
