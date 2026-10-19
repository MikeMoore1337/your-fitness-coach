import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ExerciseGuideVideo } from '../../../../src/features/exercises/ExerciseGuideVideo';

const sources = [
  {
    url: '/media/approved-hd.mp4',
    mime_type: 'video/mp4',
    width: 720,
    height: 720,
    byte_size: 8000,
  },
];

describe('ExerciseGuideVideo', () => {
  let notifyIntersection: IntersectionObserverCallback;
  const observe = vi.fn();
  const disconnect = vi.fn();

  beforeEach(() => {
    observe.mockReset();
    disconnect.mockReset();
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        constructor(callback: IntersectionObserverCallback) {
          notifyIntersection = callback;
        }
        observe = observe;
        disconnect = disconnect;
      },
    );
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function intersect(visible: boolean) {
    act(() => {
      notifyIntersection(
        [{ isIntersecting: visible } as IntersectionObserverEntry],
        {} as IntersectionObserver,
      );
    });
  }

  it('loads a video only near the viewport and pauses and resumes without reloading it', () => {
    const play = vi.mocked(HTMLMediaElement.prototype.play);
    const pause = vi.mocked(HTMLMediaElement.prototype.pause);
    const { container, unmount } = render(
      <ExerciseGuideVideo
        sources={sources}
        poster="/media/approved-poster.webp"
        onError={vi.fn()}
      />,,
    );
    const video = container.querySelector('video');
    expect(video).not.toBeNull();
    expect(video?.getAttribute('src')).toBeNull();
    expect(observe).toHaveBeenCalledTimes(1);

    intersect(true);
    expect(video?.getAttribute('src')).toBe(sources[0].url);
    expect(video).toHaveAttribute('autoplay');
    intersect(false);
    expect(pause).toHaveBeenCalled();
    expect(video?.getAttribute('src')).toBe(sources[0].url);
    expect(disconnect).not.toHaveBeenCalled();

    intersect(true);
    expect(play).toHaveBeenCalled();
    expect(video?.getAttribute('src')).toBe(sources[0].url);

    unmount();
    expect(disconnect).toHaveBeenCalledTimes(1);
  });

  it('pauses when the document is hidden and resumes when visible', () => {
    const play = vi.mocked(HTMLMediaElement.prototype.play);
    const pause = vi.mocked(HTMLMediaElement.prototype.pause);
    render(
      <ExerciseGuideVideo
        expanded
        sources={sources}
        poster="/media/approved-poster.webp"
        onError={vi.fn()}
      />,,
    );
    const oldDescriptor = Object.getOwnPropertyDescriptor(document, 'hidden');
    try {
      Object.defineProperty(document, 'hidden', { configurable: true, value: true });
      act(() => {
        document.dispatchEvent(new Event('visibilitychange'));
      });
      expect(pause).toHaveBeenCalled();
      Object.defineProperty(document, 'hidden', { configurable: true, value: false });
      act(() => {
        document.dispatchEvent(new Event('visibilitychange'));
      });
      expect(play).toHaveBeenCalled();
      expect(observe).not.toHaveBeenCalled();
    } finally {
      if (oldDescriptor) Object.defineProperty(document, 'hidden', oldDescriptor);
      else Reflect.deleteProperty(document, 'hidden');
    }
  });
});
