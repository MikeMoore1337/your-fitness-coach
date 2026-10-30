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
import { IconButton } from '../../shared/ui/common';
import { localizedEquipmentDisplayLabel } from '../../shared/equipmentLabels';
import { AvailabilityControl, EquipmentProfileSelect } from '../equipment/EquipmentProfiles';
import {
  equipmentAvailability,
  equipmentNeedsReview,
  useEquipmentProfiles,
  type EquipmentProfile,
} from '../equipment/equipmentProfileState';

export type ExercisePickerExercise = ExerciseSearchItem & {
  equipment_ids?: Exercise['equipment_ids'];
  required_equipment_ids?: Exercise['required_equipment_ids'];
  metric_type?: Exercise['metric_type'] | null;
  difficulty_level?: Exercise['difficulty_level'];
  is_custom?: boolean;
  has_guide?: boolean;
  media_animation_url?: string | null;
  media_thumbnail_url?: string | null;
  media_thumbnail_sources?: Exercise['media_thumbnail_sources'];
  media_preferred_mode?: Exercise['media_preferred_mode'];
};

type PickerProps = {
  exercises: ExercisePickerExercise[];
  value: number | '';
  clearValue?: number | '';
  onChange: (id: number | '') => void;
  onOpenGuide?: (exercise: ExercisePickerExercise) => void;
  ariaLabel?: string;
  portalResults?: boolean;
  mobileSheet?: boolean;
  equipmentFilterEnabled?: boolean;
};

export function SearchableExercisePicker(props: PickerProps) {
  return props.equipmentFilterEnabled ? (
    <EquipmentAwarePicker {...props} />
  ) : (
    <ExercisePicker {...props} />
  );
}

function EquipmentAwarePicker(props: PickerProps) {
  const { active, query } = useEquipmentProfiles();
  const showEquipmentControls = query.isError || Boolean(query.data?.profiles?.length);
  return (
    <ExercisePicker
      {...props}
      equipmentFilterEnabled={showEquipmentControls}
      activeProfile={active}
    />
  );
}

function ExercisePicker({
  exercises,
  value,
  clearValue = '',
  onChange,
  onOpenGuide,
  ariaLabel = 'Поиск упражнения',
  portalResults = false,
  mobileSheet = false,
  equipmentFilterEnabled = false,
  activeProfile,
}: PickerProps & { activeProfile?: EquipmentProfile }) {
  const [availability, setAvailability] = useState<'available' | 'all'>('available');
  const selected = exercises.find((exercise) => exercise.id === value);
  const selectedTitle = selected?.title ?? '';
  const resultsId = `exercise-picker-results-${useId()}`;
  const [query, setQuery] = useState(selectedTitle);
  const [previousSelectedTitle, setPreviousSelectedTitle] = useState(selectedTitle);
  const [open, setOpen] = useState(false);
  if (previousSelectedTitle !== selectedTitle) {
    setPreviousSelectedTitle(selectedTitle);
    if (!open) setQuery(selectedTitle);
  }
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
  const closePicker = () => {
    setOpen(false);
    setQuery(selectedTitle);
  };
  const panelRef = useModalA11y<HTMLDivElement>(compact && open, closePicker, 'input');
  const [activeIndex, setActiveIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const sheetResultsRef = useRef<HTMLDivElement>(null);
  const [resultsStyle, setResultsStyle] = useState<CSSProperties>();
  const results = useMemo(() => {
    const ordered = !normalizeExerciseSearchText(query)
      ? exercises
      : rankExercisesForSearch(exercises, query);
    return activeProfile && availability === 'available'
      ? ordered.filter((item) => equipmentAvailability(item, activeProfile) !== 'unavailable')
      : ordered;
  }, [activeProfile, availability, exercises, query]);
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
      className={`exercise-picker__results${onOpenGuide ? ' exercise-picker__results--with-guides' : ''}${equipmentFilterEnabled && !compact ? ' exercise-picker__results--equipment' : ''}`}
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
                data-yfc-choice="compact"
                className="exercise-picker__option"
                key={exercise.id}
                onPointerDown={(event) => {
                  event.preventDefault();
                  chooseExercise(exercise);
                }}
              >
                <ExerciseMediaAsset
                  animationUrl={exercise.media_animation_url}
                  alt={`${exercise.title}: изображение упражнения`}
                  className="exercise-picker__option-thumb"
                  thumbnailUrl={exercise.media_thumbnail_url}
                  thumbnailSources={exercise.media_thumbnail_sources}
                  preferredMode={exercise.media_preferred_mode}
                  variant="thumbnail"
                />
                <span className="exercise-picker__option-copy">
                  <strong>{exercise.title}</strong>
                  <span className="exercise-picker__meta">
                    <small>
                      {exercise.primary_muscle || 'Все мышцы'} ·{' '}
                      {localizedEquipmentDisplayLabel(exercise.equipment_ids, exercise.equipment) ??
                        'Без оборудования'}
                    </small>
                    {exercise.difficulty_level && (
                      <span className="badge">{difficultyLabels[exercise.difficulty_level]}</span>
                    )}
                    {exercise.is_custom && <span className="badge">Своё</span>}
                    {activeProfile && equipmentNeedsReview(exercise, activeProfile) && (
                      <span className="badge">Проверить оборудование</span>
                    )}
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
                  {equipmentFilterEnabled ? (
                    <Icon name="info" size={20} />
                  ) : exercise.has_guide ? (
                    'Техника'
                  ) : (
                    'Подробнее'
                  )}
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
        if (sheetResultsRef.current) sheetResultsRef.current.scrollTop = 0;
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
          closePicker();
        }
      }}
    />
  );
  return (
    <div
      className="exercise-picker"
      onBlur={(event) => {
        const next = event.relatedTarget as HTMLElement | null;
        if (
          !compact &&
          !event.currentTarget.contains(next) &&
          !next?.closest('[data-equipment-profile-dialog]')
        )
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
      {!compact && open && equipmentFilterEnabled && (
        <div className="equipment-availability">
          <EquipmentProfileSelect />
          {activeProfile && <AvailabilityControl value={availability} onChange={setAvailability} />}
        </div>
      )}
      {compact && open
        ? createPortal(
            <div
              className="exercise-picker-sheet-layer"
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) {
                  event.preventDefault();
                  closePicker();
                }
              }}
            >
              <div
                className={`exercise-picker-sheet${equipmentFilterEnabled ? ' exercise-picker-sheet--equipment' : ''}`}
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
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={closePicker}
                  >
                    <Icon name="close" size={20} />
                  </button>
                </header>
                <div className="exercise-picker-sheet__search">
                  {searchInput}
                  {query && (
                    <IconButton
                      type="button"
                      className="exercise-picker-sheet__clear"
                      aria-label="Очистить поиск"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => {
                        setQuery('');
                        if (sheetResultsRef.current) sheetResultsRef.current.scrollTop = 0;
                        setActiveIndex(-1);
                        inputRef.current?.focus({ preventScroll: true });
                      }}
                    >
                      <Icon name="close" size={20} />
                    </IconButton>
                  )}
                </div>
                {equipmentFilterEnabled && (
                  <div className="equipment-availability">
                    <EquipmentProfileSelect />
                    {activeProfile && (
                      <AvailabilityControl value={availability} onChange={setAvailability} />
                    )}
                  </div>
                )}
                <div className="exercise-picker__results" id={resultsId} ref={sheetResultsRef}>
                  {results.length ? (
                    results.map((exercise) => (
                      <div className="exercise-picker-sheet__row" key={exercise.id}>
                        <button
                          className="exercise-picker__option"
                          type="button"
                          aria-pressed={exercise.id === value}
                          data-yfc-choice="compact"
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => chooseExercise(exercise)}
                        >
                          <ExerciseMediaAsset
                            animationUrl={exercise.media_animation_url}
                            alt=""
                            className="exercise-picker__option-thumb"
                            thumbnailUrl={exercise.media_thumbnail_url}
                            thumbnailSources={exercise.media_thumbnail_sources}
                            preferredMode={exercise.media_preferred_mode}
                            variant="thumbnail"
                          />
                          <span className="exercise-picker__option-copy">
                            <strong>{exercise.title}</strong>
                            <small>
                              {exercise.primary_muscle || 'Все мышцы'} ·{' '}
                              {localizedEquipmentDisplayLabel(
                                exercise.equipment_ids,
                                exercise.equipment,
                              ) ?? 'Без оборудования'}
                              {exercise.difficulty_level
                                ? ` · ${difficultyLabels[exercise.difficulty_level]}`
                                : ''}
                              {exercise.is_custom ? ' · Своё' : ''}
                              {activeProfile && equipmentNeedsReview(exercise, activeProfile)
                                ? ' · Проверить оборудование'
                                : ''}
                            </small>
                          </span>
                        </button>
                        {onOpenGuide && (
                          <button
                            className="text-button exercise-picker__guide"
                            type="button"
                            aria-label={`${exercise.has_guide ? 'Техника' : 'Подробнее'}: ${exercise.title}`}
                            onMouseDown={(event) => event.preventDefault()}
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
