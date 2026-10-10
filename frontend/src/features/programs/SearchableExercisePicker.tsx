import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import { createPortal } from 'react-dom';
import { ExerciseMediaAsset } from '../exercises/ExerciseMediaAsset';
import {
  normalizeExerciseSearchText,
  rankExercisesForSearch,
  type ExerciseSearchItem,
} from '../exercises/exerciseSearch';
import type { Exercise } from '../../shared/api/types';
import { difficultyLabels } from './exerciseOrdering';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { Icon } from '../../shared/ui/Icon';

export type ExercisePickerExercise = ExerciseSearchItem & {
  metric_type?: Exercise['metric_type'] | null;
  difficulty_level?: Exercise['difficulty_level'];
  is_custom?: boolean;
  has_guide?: boolean;
  media_animation_url?: string | null;
  media_thumbnail_url?: string | null;
};

export function SearchableExercisePicker({
  exercises,
  value,
  clearValue = '',
  onChange,
  onOpenGuide,
  ariaLabel = 'Поиск упражнения',
  portalResults = false,
  mobileSheet = false,
}: {
  exercises: ExercisePickerExercise[];
  value: number | '';
  clearValue?: number | '';
  onChange: (id: number | '') => void;
  onOpenGuide?: (exercise: ExercisePickerExercise) => void;
  ariaLabel?: string;
  portalResults?: boolean;
  mobileSheet?: boolean;
}) {
  const selected = exercises.find((exercise) => exercise.id === value);
  const selectedTitle = selected?.title ?? '';
  const resultsId = `exercise-picker-results-${useId()}`;
  const [query, setQuery] = useState(selectedTitle);
  const [open, setOpen] = useState(false);
  const [compact, setCompact] = useState(
    () => mobileSheet && Boolean(window.matchMedia?.('(max-width: 680px)').matches),
  );
  useEffect(() => {
    if (!mobileSheet || !window.matchMedia) return;
    const media = window.matchMedia('(max-width: 680px)');
    const update = () => {
      setCompact(media.matches);
      setOpen(false);
    };
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, [mobileSheet]);
  const panelRef = useModalA11y<HTMLDivElement>(
    compact && open,
    () => {
      setOpen(false);
      setQuery(selectedTitle);
    },
    'input',
  );
  const [activeIndex, setActiveIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const [resultsStyle, setResultsStyle] = useState<CSSProperties>();
  const results = useMemo(() => {
    if (!normalizeExerciseSearchText(query)) return exercises;
    return rankExercisesForSearch(exercises, query);
  }, [exercises, query]);
  const currentActiveIndex = Math.max(0, Math.min(activeIndex, Math.max(0, results.length - 1)));

  useLayoutEffect(() => {
    if (!open || !portalResults || compact) return;
    const updateResultsPosition = () => {
      const input = inputRef.current;
      if (!input) return;
      const rect = input.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom - 12;
      const openAbove = spaceBelow < 240 && rect.top > 240;
      const availableHeight = openAbove ? rect.top - 12 : spaceBelow;
      setResultsStyle({
        position: 'fixed',
        left: rect.left,
        right: 'auto',
        width: rect.width,
        top: openAbove ? 'auto' : rect.bottom + 6,
        bottom: openAbove ? window.innerHeight - rect.top + 6 : 'auto',
        maxHeight: Math.max(96, Math.min(280, availableHeight)),
      });
    };
    updateResultsPosition();
    window.addEventListener('resize', updateResultsPosition);
    window.addEventListener('scroll', updateResultsPosition, true);
    return () => {
      window.removeEventListener('resize', updateResultsPosition);
      window.removeEventListener('scroll', updateResultsPosition, true);
    };
  }, [compact, open, portalResults, results.length]);

  const chooseExercise = (exercise: ExercisePickerExercise) => {
    onChange(exercise.id);
    setQuery(exercise.title);
    setOpen(false);
  };

  const resultsPanel = open ? (
    <div
      className={`exercise-picker__results${onOpenGuide ? ' exercise-picker__results--with-guides' : ''}`}
      style={portalResults && !compact ? resultsStyle : undefined}
    >
      {results.length ? (
        <>
          <div className="exercise-picker__options" id={resultsId} role="listbox">
            {results.map((exercise) => (
              <div
                role="option"
                id={`${resultsId}-${exercise.id}`}
                aria-selected={exercise.id === value}
                className="exercise-picker__option"
                key={exercise.id}
                tabIndex={compact ? 0 : undefined}
                onClick={() => {
                  if (compact) chooseExercise(exercise);
                }}
                onKeyDown={(event) => {
                  if (compact && (event.key === 'Enter' || event.key === ' ')) {
                    event.preventDefault();
                    chooseExercise(exercise);
                  }
                }}
                onPointerDown={(event) => {
                  if (compact) return;
                  event.preventDefault();
                  chooseExercise(exercise);
                }}
              >
                <ExerciseMediaAsset
                  animationUrl={exercise.media_animation_url}
                  alt={`${exercise.title}: изображение упражнения`}
                  className="exercise-picker__option-thumb"
                  thumbnailUrl={exercise.media_thumbnail_url}
                  variant="thumbnail"
                />
                <span className="exercise-picker__option-copy">
                  <strong>{exercise.title}</strong>
                  <span className="exercise-picker__meta">
                    <small>
                      {exercise.primary_muscle || 'Все мышцы'} ·{' '}
                      {exercise.equipment || 'Без оборудования'}
                    </small>
                    {exercise.difficulty_level && (
                      <span className="badge">{difficultyLabels[exercise.difficulty_level]}</span>
                    )}
                    {exercise.is_custom && <span className="badge">Своё</span>}
                  </span>
                </span>
              </div>
            ))}
          </div>
          {onOpenGuide && (
            <div className="exercise-picker__guides" aria-label="Техника упражнений" role="group">
              {results.map((exercise) => (
                <button
                  type="button"
                  className="text-button exercise-picker__guide"
                  aria-label={`${exercise.has_guide ? 'Техника' : 'Подробнее'}: ${exercise.title}`}
                  key={exercise.id}
                  onPointerDown={(event) => {
                    event.preventDefault();
                    onOpenGuide(exercise);
                  }}
                  onClick={(event) => {
                    if (event.detail === 0) onOpenGuide(exercise);
                  }}
                >
                  {exercise.has_guide ? 'Техника' : 'Подробнее'}
                </button>
              ))}
            </div>
          )}
        </>
      ) : (
        <span className="exercise-picker__empty" id={resultsId} role="status">
          Ничего не найдено
        </span>
      )}
    </div>
  ) : null;

  const searchInput = (
    <input
      ref={inputRef}
      type="search"
      role={compact ? 'searchbox' : 'combobox'}
      aria-label={ariaLabel}
      aria-autocomplete={compact ? undefined : 'list'}
      aria-expanded={compact ? undefined : open}
      aria-haspopup={compact ? undefined : 'listbox'}
      aria-controls={resultsId}
      aria-activedescendant={
        !compact && open && results[currentActiveIndex]
          ? `${resultsId}-${results[currentActiveIndex].id}`
          : undefined
      }
      autoComplete="off"
      enterKeyHint="search"
      value={query}
      placeholder="Начните вводить название"
      onFocus={() => {
        setActiveIndex(-1);
        setOpen(true);
      }}
      onChange={(event) => {
        setQuery(event.target.value);
        setActiveIndex(-1);
        setOpen(true);
        if (!compact && value !== clearValue) onChange(clearValue);
      }}
      onKeyDown={(event) => {
        if (event.key === 'ArrowDown') {
          event.preventDefault();
          setOpen(true);
          setActiveIndex((index) =>
            Math.min(Math.max(0, results.length - 1), index < 0 ? 0 : index + 1),
          );
        } else if (event.key === 'ArrowUp') {
          event.preventDefault();
          setOpen(true);
          setActiveIndex((index) => Math.max(0, index - 1));
        } else if (event.key === 'Enter' && open && results[currentActiveIndex]) {
          event.preventDefault();
          chooseExercise(results[currentActiveIndex]);
        } else if (event.key === 'Escape') {
          event.preventDefault();
          event.stopPropagation();
          setOpen(false);
          setQuery(selectedTitle);
        }
      }}
    />
  );
  return (
    <div
      className="exercise-picker"
      onBlur={(event) => {
        if (!compact && !event.currentTarget.contains(event.relatedTarget as Node | null))
          setOpen(false);
      }}
    >
      {compact ? (
        <button
          className="exercise-picker__trigger secondary"
          type="button"
          aria-label={ariaLabel}
          aria-haspopup="dialog"
          onClick={(event) => {
            event.currentTarget.focus();
            setOpen(true);
          }}
        >
          {selectedTitle || 'Выбрать упражнение'}
          <Icon name="search" size={20} />
        </button>
      ) : (
        searchInput
      )}
      {compact && open
        ? createPortal(
            <div
              className="exercise-picker-sheet-layer"
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) {
                  event.preventDefault();
                  setOpen(false);
                }
              }}
            >
              <div
                className="exercise-picker-sheet"
                role="dialog"
                aria-modal="true"
                aria-label="Выбор упражнения"
                ref={panelRef}
                tabIndex={-1}
              >
                <header>
                  <h2>Выбор упражнения</h2>
                  <button
                    type="button"
                    aria-label="Закрыть выбор упражнения"
                    onClick={() => setOpen(false)}
                  >
                    <Icon name="close" size={20} />
                  </button>
                </header>
                {searchInput}
                <div className="exercise-picker__results" id={resultsId}>
                  {results.length ? (
                    results.map((exercise) => (
                      <div className="exercise-picker-sheet__row" key={exercise.id}>
                        <button
                          className="exercise-picker__option"
                          type="button"
                          aria-pressed={exercise.id === value}
                          onClick={() => chooseExercise(exercise)}
                        >
                          <ExerciseMediaAsset
                            animationUrl={exercise.media_animation_url}
                            alt=""
                            className="exercise-picker__option-thumb"
                            thumbnailUrl={exercise.media_thumbnail_url}
                            variant="thumbnail"
                          />
                          <span className="exercise-picker__option-copy">
                            <strong>{exercise.title}</strong>
                            <small>
                              {exercise.primary_muscle || 'Все мышцы'} ·{' '}
                              {exercise.equipment || 'Без оборудования'}
                              {exercise.difficulty_level
                                ? ` · ${difficultyLabels[exercise.difficulty_level]}`
                                : ''}
                              {exercise.is_custom ? ' · Своё' : ''}
                            </small>
                          </span>
                        </button>
                        {onOpenGuide && (
                          <button
                            className="text-button exercise-picker__guide"
                            type="button"
                            aria-label={`${exercise.has_guide ? 'Техника' : 'Подробнее'}: ${exercise.title}`}
                            onClick={() => {
                              setOpen(false);
                              onOpenGuide(exercise);
                            }}
                          >
                            {exercise.has_guide ? 'Техника' : 'Подробнее'}
                          </button>
                        )}
                      </div>
                    ))
                  ) : (
                    <p role="status">Ничего не найдено</p>
                  )}
                </div>
              </div>
            </div>,
            document.body,
          )
        : portalResults && resultsPanel
          ? createPortal(resultsPanel, document.body)
          : resultsPanel}
    </div>
  );
}
