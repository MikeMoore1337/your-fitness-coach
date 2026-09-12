import { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { Exercise } from '../../shared/api/types';
import { Badge, CloseIcon, ErrorState, LoadingState } from '../../shared/ui/common';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { ExerciseGuideMedia } from './ExerciseGuideMedia';

const difficultyLabels: Record<Exercise['difficulty_level'], string> = {
  beginner: 'Начальный уровень',
  intermediate: 'Средний уровень',
  advanced: 'Продвинутый уровень',
};

function resolveDialogDocumentTop() {
  if (document.body.style.position === 'fixed') {
    const lockedBodyTop = Number.parseFloat(document.body.style.top);
    if (Number.isFinite(lockedBodyTop)) return Math.max(0, -lockedBodyTop);
  }
  return window.scrollY;
}

export function ExerciseGuideDialog({
  exerciseId,
  exerciseTitle,
  onClose,
}: {
  exerciseId: number;
  exerciseTitle: string;
  onClose: () => void;
}) {
  const [currentExercise, setCurrentExercise] = useState({ id: exerciseId, title: exerciseTitle });
  const [dialogScrollTop] = useState(resolveDialogDocumentTop);
  const [mediaExpanded, setMediaExpanded] = useState(false);
  const panelRef = useModalA11y<HTMLDivElement>(!mediaExpanded, onClose);
  const details = useQuery({
    queryKey: ['exercises', currentExercise.id, 'details'],
    queryFn: () => api<Exercise>(`/api/v1/programs/exercises/${currentExercise.id}`),
  });
  const guide = details.data?.guide;
  const primaryMuscles = useMemo(
    () => guide?.muscles.filter((muscle) => muscle.role_id === 'primary') ?? [],
    [guide?.muscles],
  );
  const secondaryMuscles = useMemo(
    () => guide?.muscles.filter((muscle) => muscle.role_id === 'secondary') ?? [],
    [guide?.muscles],
  );
  const alternatives = guide?.alternatives ?? details.data?.alternatives ?? [];

  const openAlternative = (alternative: (typeof alternatives)[number]) => {
    setMediaExpanded(false);
    setCurrentExercise({ id: alternative.id, title: alternative.title });
    if (panelRef.current) panelRef.current.scrollTop = 0;
  };

  return createPortal(
    <div
      className="modal exercise-guide-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="exercise-guide-title"
      style={{ position: 'absolute', top: dialogScrollTop, bottom: 'auto', height: '100dvh' }}
    >
      <div className="modal__backdrop" aria-hidden="true" onClick={onClose} />
      <div className="modal__panel card exercise-guide-modal__panel" ref={panelRef} tabIndex={-1}>
        <div data-glass="" data-glass-variant="regular" className="exercise-guide-modal__head">
          <div>
            <span className="eyebrow">Карточка упражнения</span>
            <h2 className="modal__title" id="exercise-guide-title" aria-live="polite">
              {details.data?.title ?? currentExercise.title}
            </h2>
          </div>
          <button
            type="button"
            className="secondary exercise-guide-modal__close"
            aria-label="Закрыть карточку упражнения"
            onClick={onClose}
          >
            <CloseIcon />
          </button>
        </div>
        <div className="exercise-guide-modal__body">
          {details.isLoading && <LoadingState />}
          {details.error && (
            <ErrorState
              message={(details.error as Error).message}
              retry={() => void details.refetch()}
            />
          )}
          {details.data && (
            <div className="exercise-guide-card">
              <div className="exercise-guide-meta toolbar wrap" aria-label="Краткие сведения">
                <Badge>{difficultyLabels[details.data.difficulty_level]}</Badge>
                {details.data.is_custom && <Badge>Пользовательское упражнение</Badge>}
                {guide && <Badge>Техника доступна</Badge>}
              </div>

              {guide?.media.length ? (
                <ExerciseGuideMedia items={guide.media} onExpandedChange={setMediaExpanded} />
              ) : null}

              {guide ? (
                <div className="exercise-guide-notes">
                  {!!guide.technique_steps.length && (
                    <section className="exercise-guide-note exercise-guide-note--technique">
                      <h3>Техника выполнения</h3>
                      <ol>
                        {guide.technique_steps.map((step) => (
                          <li key={step}>{step}</li>
                        ))}
                      </ol>
                    </section>
                  )}
                  {guide.breathing && (
                    <section className="exercise-guide-note">
                      <h3>Дыхание</h3>
                      <p>{guide.breathing}</p>
                    </section>
                  )}
                  {!!guide.common_mistakes.length && (
                    <section className="exercise-guide-note exercise-guide-note--warning">
                      <h3>Частые ошибки</h3>
                      <ul>
                        {guide.common_mistakes.map((mistake) => (
                          <li key={mistake}>{mistake}</li>
                        ))}
                      </ul>
                    </section>
                  )}
                </div>
              ) : (
                <section className="exercise-guide-empty" aria-labelledby="guide-empty-title">
                  <span className="eyebrow">Доступные сведения</span>
                  <h3 id="guide-empty-title">Техника пока не добавлена</h3>
                  <p>
                    Для этого упражнения нет проверенного пошагового руководства. Мы не заменяем его
                    общими или неподтверждёнными советами.
                  </p>
                </section>
              )}

              <div className="exercise-guide-facts">
                {(primaryMuscles.length > 0 || details.data.primary_muscle) && (
                  <section
                    className="exercise-guide-section"
                    aria-labelledby="guide-primary-muscles"
                  >
                    <h3 id="guide-primary-muscles">Основные мышцы</h3>
                    {primaryMuscles.length > 0 ? (
                      <div className="exercise-guide-muscles">
                        {primaryMuscles.map((muscle) => (
                          <article
                            className="exercise-guide-muscle"
                            key={muscle.identifier ?? muscle.name}
                          >
                            <strong>{muscle.name}</strong>
                            {muscle.function && <p>{muscle.function}</p>}
                          </article>
                        ))}
                      </div>
                    ) : (
                      <div className="toolbar wrap">
                        <Badge>{details.data.primary_muscle}</Badge>
                      </div>
                    )}
                  </section>
                )}

                {secondaryMuscles.length > 0 && (
                  <section
                    className="exercise-guide-section"
                    aria-labelledby="guide-secondary-muscles"
                  >
                    <h3 id="guide-secondary-muscles">Дополнительные мышцы</h3>
                    <div className="exercise-guide-muscles">
                      {secondaryMuscles.map((muscle) => (
                        <article
                          className="exercise-guide-muscle"
                          key={muscle.identifier ?? muscle.name}
                        >
                          <strong>{muscle.name}</strong>
                          {muscle.function && <p>{muscle.function}</p>}
                        </article>
                      ))}
                    </div>
                  </section>
                )}

                {(guide?.equipment.length || details.data.equipment) && (
                  <section className="exercise-guide-section" aria-labelledby="guide-equipment">
                    <h3 id="guide-equipment">Оборудование</h3>
                    <div className="toolbar wrap">
                      {guide?.equipment.length ? (
                        guide.equipment.map((item) => (
                          <Badge key={item.identifier}>{item.name}</Badge>
                        ))
                      ) : (
                        <Badge>{details.data.equipment}</Badge>
                      )}
                    </div>
                  </section>
                )}

                {!!guide?.safety_notes.length && (
                  <section
                    className="exercise-guide-section exercise-guide-section--safety"
                    aria-labelledby="guide-safety"
                  >
                    <h3 id="guide-safety">Что важно для безопасности</h3>
                    <ul>
                      {guide.safety_notes.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  </section>
                )}
              </div>

              {!!alternatives.length && (
                <section className="exercise-guide-section exercise-guide-alternatives">
                  <h3>Варианты замены</h3>
                  <p>Откройте карточку другого проверенного варианта и сравните технику.</p>
                  <div className="toolbar wrap">
                    {alternatives.map((alternative) => (
                      <button
                        type="button"
                        className="secondary exercise-guide-alternative"
                        key={alternative.id}
                        onClick={() => openAlternative(alternative)}
                      >
                        {alternative.title}
                      </button>
                    ))}
                  </div>
                </section>
              )}

              {guide && (
                <footer className="exercise-guide-source">
                  <span>Материал и иллюстрации</span>
                  <p>
                    Источник:{' '}
                    <a href={guide.source_url} target="_blank" rel="noreferrer">
                      {guide.source_name}
                    </a>
                    {' · '}
                    {guide.source_license_url ? (
                      <a href={guide.source_license_url} target="_blank" rel="noreferrer">
                        {guide.source_license}
                      </a>
                    ) : (
                      guide.source_license
                    )}
                  </p>
                </footer>
              )}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
