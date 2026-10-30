import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, apiErrorDetailIncludes } from '../../shared/api/client';
import type { ProgramTemplate } from '../../shared/api/types';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import {
  Badge,
  Card,
  CloseIcon,
  DisclosureIcon,
  EmptyState,
  ErrorState,
  LoadingState,
} from '../../shared/ui/common';
import { useAuth } from '../../app/AuthProvider';
import { dateInputValue, detectedTimeZone } from '../../shared/dateTime';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { ExerciseGuideDialog } from '../exercises/ExerciseGuideDialog';
import { ProgramBuilder } from './ProgramBuilder';
import { shouldSaveTemplateAsCopy } from './templateEditing';
import { programWeeklySessions } from './programPreviewFacts';
import { DateInput } from '../../shared/ui/PickerInput';
import { ProgramRecommendation } from './ProgramRecommendation';
import { LegacyProgramRecommendation } from './LegacyProgramRecommendation';
import { productEventSurface, trackCoreProductEvent } from '../../shared/analytics/productEvents';
import { AssignedProgramDetails } from './AssignedProgramDetails';
import { ProgramImportPanel } from './ProgramImportPanel';
import { PublicProgramSharePanel } from './PublicProgramSharePanel';
import { AppLink, useNavigation } from '../../shared/navigation/router';
import { Icon, type IconName } from '../../shared/ui/Icon';
import { programPreviewFacts, previewSourceSignature } from './programPreviewFacts';
import { exerciseCountLabel } from './programDefaults';
import './programPreview.css';
import './programControlCenter.css';

const goalLabels: Record<string, string> = {
  muscle_gain: 'Набор мышечной массы',
  fat_loss: 'Снижение веса',
  maintenance: 'Поддержание формы',
  recomposition: 'Рекомпозиция',
};

const levelLabels: Record<string, string> = {
  beginner: 'Начальный уровень',
  intermediate: 'Средний уровень',
  advanced: 'Продвинутый уровень',
};
const weekdayLabels = [
  'Понедельник',
  'Вторник',
  'Среда',
  'Четверг',
  'Пятница',
  'Суббота',
  'Воскресенье',
];

function weekdayFromDate(value: string): number {
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(date.valueOf()) ? 0 : (date.getUTCDay() + 6) % 7;
}

function defaultWeekdays(template: ProgramTemplate, startDate: string): number[] {
  const frequency = programWeeklySessions(template);
  if (frequency > 7) return [];
  const firstWeekday = weekdayFromDate(startDate);
  return Array.from(
    { length: frequency },
    (_, index) =>
      (firstWeekday +
        (frequency === template.days.length ? index : Math.floor((index * 7) / frequency))) %
      7,
  );
}

function weeksLabel(value: number): string {
  const remainder = value % 10;
  const suffix =
    remainder === 1 && value % 100 !== 11
      ? 'неделя'
      : remainder >= 2 && remainder <= 4 && (value % 100 < 10 || value % 100 >= 20)
        ? 'недели'
        : 'недель';
  return `${value} ${suffix}`;
}

function programMeta(item: ProgramTemplate) {
  const remainder = item.days.length % 10;
  const suffix =
    remainder === 1 && item.days.length % 100 !== 11
      ? 'тренировка'
      : remainder >= 2 &&
          remainder <= 4 &&
          (item.days.length % 100 < 10 || item.days.length % 100 >= 20)
        ? 'тренировки'
        : 'тренировок';
  const duration =
    item.default_duration_weeks > 1 ? ` · ${weeksLabel(item.default_duration_weeks)}` : '';
  return `${goalLabels[item.goal] ?? 'Цель не указана'} · ${levelLabels[item.level] ?? 'Уровень не указан'} · ${item.days.length} ${suffix} в цикле${duration}`;
}

function programKind(item: ProgramTemplate, currentUserId?: number): string {
  if (item.assigned_by_user_id && item.assigned_by_user_id !== currentUserId) return 'От тренера';
  if (item.is_example) return 'Готовый шаблон';
  if (item.owner_user_id === currentUserId || item.can_edit) return 'Моя программа';
  return 'Шаблон';
}

function previewOwnership(item: ProgramTemplate, currentUserId?: number): string {
  if (item.assigned_by_user_id && item.assigned_by_user_id !== currentUserId) {
    return `Назначил тренер${item.assigned_by_full_name ? ` ${item.assigned_by_full_name}` : ''}. Изменения доступны только по разрешённым правам.`;
  }
  if (item.owner_user_id === currentUserId) {
    return 'Владелец: вы. Вы можете редактировать свою программу.';
  }
  if (item.owner_full_name) return `Владелец: ${item.owner_full_name}.`;
  return item.can_edit
    ? 'Вы можете редактировать свою программу.'
    : 'Изменения исходного шаблона недоступны. Можно создать личную копию.';
}

type ManagePanel = 'overview' | 'operations' | 'replace' | 'library' | 'create';

function panelFromSearch(search: string): ManagePanel {
  const params = new URLSearchParams(search);
  const value = params.get('panel');
  if (value === 'operations' || value === 'replace' || value === 'library' || value === 'create')
    return value;
  if (params.get('start') === 'templates') return 'library';
  if (params.get('start') === 'create') return 'create';
  if (params.get('start') === 'generator') return 'replace';
  return 'overview';
}

const manageActions: ReadonlyArray<{
  panel: Exclude<ManagePanel, 'overview'>;
  title: string;
  description: string;
  icon: IconName;
}> = [
  {
    panel: 'operations',
    title: 'Назначение и изменения',
    description: 'Недели, этапы, история и версии',
    icon: 'calendar',
  },
  {
    panel: 'replace',
    title: 'Заменить программу',
    description: 'Подобрать или назначить другую',
    icon: 'edit',
  },
  {
    panel: 'library',
    title: 'Программы и шаблоны',
    description: 'Мои, готовые и скрытые примеры',
    icon: 'nav-knowledge',
  },
  {
    panel: 'create',
    title: 'Создать или импортировать',
    description: 'Конструктор и загрузка программы',
    icon: 'plus',
  },
];

export function TemplatesList({
  children,
  defaultLibraryOpen = false,
  mode = 'full',
  readOnly = false,
}: {
  children?: ReactNode;
  defaultLibraryOpen?: boolean;
  mode?: 'full' | 'summary';
  readOnly?: boolean;
}) {
  const { search, navigate } = useNavigation();
  const panel = mode === 'full' ? panelFromSearch(search) : 'overview';
  const lastPanel = useRef<ManagePanel>('overview');
  const positions = useRef<Partial<Record<ManagePanel, number>>>({});
  const previousPanel = useRef(panel);
  const openPanel = (next: ManagePanel) => {
    if (mode !== 'full' || next === panel) return;
    positions.current[panel] = window.scrollY;
    if (next !== 'overview') lastPanel.current = next;
    const params = new URLSearchParams(search);
    params.set('section', 'programs');
    params.set('view', 'manage');
    params.delete('start');
    if (next === 'overview') params.delete('panel');
    else params.set('panel', next);
    navigate('/app?' + params.toString());
  };
  useEffect(() => {
    if (mode !== 'full' || previousPanel.current === panel) return;
    previousPanel.current = panel;
    const frame = window.requestAnimationFrame(() => {
      if (panel === 'overview') {
        document
          .querySelector<HTMLElement>('[data-program-panel="' + lastPanel.current + '"]')
          ?.focus({ preventScroll: true });
      } else document.getElementById('program-manage-heading')?.focus({ preventScroll: true });
      window.scrollTo({ top: positions.current[panel] ?? 0, behavior: 'instant' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [mode, panel]);

  const { toast, confirm } = useFeedback();
  const { user, reloadUser } = useAuth();
  const queryClient = useQueryClient();
  const [selectedExample, setSelectedExample] = useState<ProgramTemplate | null>(null);
  const [previewSelectionId, setPreviewSelectionId] = useState<number | null>(null);
  const [previewStale, setPreviewStale] = useState(false);
  const [previewChecking, setPreviewChecking] = useState(false);
  const templateDeleteLock = useRef(false);
  const [deletingTemplateId, setDeletingTemplateId] = useState<number | null>(null);
  const [guide, setGuide] = useState<{ id: number; title: string } | null>(null);
  const [editingTemplate, setEditingTemplate] = useState<ProgramTemplate | null>(null);
  const [editorDirty, setEditorDirty] = useState(false);
  const closeEditor = async () => {
    if (
      editorDirty &&
      !(await confirm({
        title: 'Закрыть редактор?',
        message: 'Изменения ещё не сохранены в программе. Черновик останется на этом устройстве.',
      }))
    )
      return;
    setEditingTemplate(null);
    setEditorDirty(false);
  };
  const editorPanelRef = useModalA11y<HTMLDivElement>(Boolean(editingTemplate), () => {
    void closeEditor();
  });
  const [saveAsCopy, setSaveAsCopy] = useState(false);
  const [assignmentTemplate, setAssignmentTemplate] = useState<ProgramTemplate | null>(null);
  const [recommendationOpen, setRecommendationOpen] = useState(false);
  const [generatorOpen, setGeneratorOpen] = useState(
    () => mode === 'full' && new URLSearchParams(search).get('start') === 'generator',
  );
  const defaultStartDate = dateInputValue(
    new Date(),
    user?.profile?.timezone || detectedTimeZone(),
  );
  const [assignmentStartDate, setAssignmentStartDate] = useState(defaultStartDate);
  const [assignmentDuration, setAssignmentDuration] = useState(4);
  const [assignmentWeekdays, setAssignmentWeekdays] = useState<number[]>([]);
  const examplePanelRef = useModalA11y<HTMLDivElement>(Boolean(selectedExample), () =>
    setSelectedExample(null),
  );
  const selectedExampleIsTrainerReadonly =
    selectedExample?.is_active_for_current_user === true &&
    selectedExample.assigned_by_user_id != null &&
    selectedExample.assigned_by_user_id !== user?.id;
  const assignmentPanelRef = useModalA11y<HTMLDivElement>(Boolean(assignmentTemplate), () =>
    setAssignmentTemplate(null),
  );
  const templates = useQuery({
    queryKey: ['templates', 'mine'],
    queryFn: () => api<ProgramTemplate[]>('/api/v1/programs/templates/mine'),
  });
  const hidden = useQuery({
    queryKey: ['templates', 'hidden'],
    queryFn: () => api<ProgramTemplate[]>('/api/v1/programs/templates/hidden'),
  });
  const refreshProgramState = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['templates'] }),
      queryClient.invalidateQueries({ queryKey: ['workout'] }),
      queryClient.invalidateQueries({ queryKey: ['assigned-program'] }),
      queryClient.invalidateQueries({ queryKey: ['notifications'] }),
      reloadUser(),
    ]);
  };
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body?: unknown }) =>
      api(path, { method, body }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['templates'] }),
        queryClient.invalidateQueries({ queryKey: ['workout'] }),
        reloadUser(),
      ]);
      toast('Программы обновлены');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  const deleteTemplate = async (item: ProgramTemplate) => {
    // Lock the full confirmation + request flow, including rapid taps before React renders.
    if (templateDeleteLock.current || mutation.isPending) return;
    templateDeleteLock.current = true;
    setDeletingTemplateId(item.id);
    try {
      if (
        !(await confirm({
          title: item.is_example ? 'Скрыть шаблон?' : 'Удалить программу?',
          message: item.title,
          confirmText: item.is_example ? 'Скрыть' : 'Удалить',
        }))
      )
        return;
      await mutation.mutateAsync({
        path: `/api/v1/programs/templates/${item.id}`,
        method: 'DELETE',
      });
    } catch {
      // The mutation's onError handler displays the failure; do not duplicate the toast.
    } finally {
      templateDeleteLock.current = false;
      setDeletingTemplateId(null);
    }
  };

  const assignmentMutation = useMutation({
    mutationFn: ({ templateId, replaceActive }: { templateId: number; replaceActive: boolean }) =>
      api(`/api/v1/programs/templates/${templateId}/assign-to-me`, {
        method: 'POST',
        body: {
          start_date: assignmentStartDate,
          duration_weeks: assignmentDuration,
          schedule_weekdays:
            assignmentTemplate && assignmentTemplate.days.length > 7 ? null : assignmentWeekdays,
          replace_active: replaceActive,
        },
      }),
    onSuccess: async () => {
      trackCoreProductEvent(
        { name: 'program_activated', surface: productEventSurface() },
        'program_activated',
      );
      setAssignmentTemplate(null);
      await refreshProgramState();
      toast('Программа назначена');
    },
    onError: async (reason, variables) => {
      if (
        reason instanceof ApiError &&
        reason.status === 409 &&
        !variables.replaceActive &&
        apiErrorDetailIncludes(reason, 'confirmation')
      ) {
        if (
          await confirm({
            title: 'Заменить активную программу?',
            message:
              'Текущая программа будет отправлена в архив. Тренировку, которая уже идёт, заменить нельзя.',
            confirmText: 'Заменить программу',
          })
        )
          assignmentMutation.mutate({ ...variables, replaceActive: true });
        return;
      }
      toast(
        apiErrorDetailIncludes(reason, 'in progress')
          ? 'Сначала завершите текущую тренировку — во время неё программу заменить нельзя.'
          : (reason as Error).message,
        'error',
      );
    },
  });

  const deleteAssignedMutation = useMutation({
    mutationFn: (programId: number) =>
      api<void>(`/api/v1/programs/assigned/${programId}`, { method: 'DELETE' }),
    onSuccess: async (_data, programId) => {
      queryClient.setQueryData<ProgramTemplate[]>(['templates', 'mine'], (current) =>
        current?.map((item) =>
          item.assigned_program_id === programId
            ? { ...item, is_active_for_current_user: false }
            : item,
        ),
      );
      await refreshProgramState();
      toast('Программа удалена');
    },
    onError: (reason) => {
      if (
        reason instanceof ApiError &&
        reason.status === 409 &&
        apiErrorDetailIncludes(reason, 'in progress')
      ) {
        toast(
          'Сначала завершите текущую тренировку - во время неё программу удалить нельзя.',
          'error',
        );
        return;
      }
      toast(reason instanceof Error ? reason.message : 'Не удалось удалить программу', 'error');
    },
  });

  const assignmentOffsets = assignmentWeekdays.map(
    (weekday) => (weekday - (assignmentWeekdays[0] ?? weekday) + 7) % 7,
  );
  const assignmentScheduleIsValid =
    Boolean(assignmentTemplate) &&
    ((assignmentTemplate?.days.length ?? 0) > 7
      ? assignmentWeekdays.length === 0
      : assignmentWeekdays.length ===
          (assignmentTemplate ? programWeeklySessions(assignmentTemplate) : 0) &&
        new Set(assignmentWeekdays).size === assignmentWeekdays.length &&
        assignmentOffsets.every(
          (offset, index) => index === 0 || offset > assignmentOffsets[index - 1]!,
        ));

  const openAssignment = (template: ProgramTemplate) => {
    setAssignmentStartDate(defaultStartDate);
    setAssignmentDuration(
      template.default_duration_weeks > 1 ? template.default_duration_weeks : 4,
    );
    setAssignmentWeekdays(defaultWeekdays(template, defaultStartDate));
    setAssignmentTemplate(template);
  };

  const assignFromPreview = async (template: ProgramTemplate) => {
    if (previewChecking) return;
    setPreviewChecking(true);
    try {
      // Refresh before entering the existing assignment flow; never silently use stale preview facts.
      const latest = await api<ProgramTemplate>(`/api/v1/programs/templates/${template.id}`);
      if (previewSourceSignature(latest) !== previewSourceSignature(template)) {
        setSelectedExample(latest);
        setPreviewStale(true);
        toast('Данные программы обновились. Проверьте состав и повторите выбор.', 'error');
        return;
      }
      setPreviewStale(false);
      setSelectedExample(null);
      openAssignment(latest);
    } catch (reason) {
      toast(
        reason instanceof Error ? reason.message : 'Не удалось проверить актуальность программы',
        'error',
      );
    } finally {
      setPreviewChecking(false);
    }
  };

  const editCopy = (template: ProgramTemplate) => {
    setSaveAsCopy(true);
    setEditingTemplate(template);
  };

  const activeTemplate = templates.data?.find((item) => item.is_active_for_current_user) ?? null;
  const deleteActiveProgram = async () => {
    const assignedProgramId = activeTemplate?.assigned_program_id;
    if (assignedProgramId == null || deleteAssignedMutation.isPending) return;
    if (
      await confirm({
        title: 'Удалить текущую программу?',
        message:
          'Программа перестанет быть активной, а будущие запланированные тренировки будут отменены. История выполненных тренировок и сам шаблон программы сохранятся.',
        confirmText: 'Удалить программу',
        danger: true,
      })
    ) {
      deleteAssignedMutation.mutate(assignedProgramId);
    }
  };
  const ownTemplates =
    templates.data?.filter(
      (item) =>
        !item.is_active_for_current_user &&
        !item.is_example &&
        (item.owner_user_id === user?.id || item.can_edit),
    ) ?? [];
  const readyTemplates =
    templates.data?.filter(
      (item) =>
        !item.is_active_for_current_user &&
        (item.is_example || (item.owner_user_id !== user?.id && !item.can_edit)),
    ) ?? [];

  useEffect(() => {
    if (mode !== 'full' || new URLSearchParams(search).get('start') !== 'generator') return;
    const frame = window.requestAnimationFrame(() => setGeneratorOpen(true));
    return () => window.cancelAnimationFrame(frame);
  }, [mode, search]);

  useEffect(() => {
    if (mode !== 'full' || !defaultLibraryOpen) return;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById('program-manage-heading')?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [defaultLibraryOpen, mode]);

  const isManage = mode === 'full';
  const isSummary = mode === 'summary';
  const showingOverview = panel === 'overview';

  const renderTemplate = (item: ProgramTemplate) => (
    <article className="program-template-card" key={item.id}>
      <button
        type="button"
        className="text-button program-template-card__main"
        aria-label={`Посмотреть ${item.is_example ? 'шаблон' : 'программу'} «${item.title}»`}
        onClick={(event) => {
          // WebKit does not focus mouse-clicked buttons consistently; keep the preview opener for Escape return.
          event.currentTarget.focus();
          setPreviewStale(false);
          setSelectedExample(item);
        }}
      >
        <span className="program-template-badges">
          <Badge>{programKind(item, user?.id)}</Badge>
        </span>
        <strong>{item.title}</strong>
        <span className="muted">{programMeta(item)}</span>
        <span className="program-example-trigger__hint">
          {previewSelectionId === item.id
            ? 'Выбрана для назначения · Посмотреть состав'
            : 'Посмотреть состав'}
        </span>
      </button>
      <div
        className={
          item.is_example
            ? 'program-template-card__actions program-template-card__actions--example'
            : 'program-template-card__actions'
        }
      >
        <button
          type="button"
          className="secondary"
          onClick={() => {
            setSaveAsCopy(shouldSaveTemplateAsCopy(item));
            setEditingTemplate(item);
          }}
        >
          {shouldSaveTemplateAsCopy(item) ? 'Настроить копию' : 'Редактировать'}
        </button>
        <button type="button" onClick={() => openAssignment(item)}>
          Запустить
        </button>
        {item.is_example && (
          <button
            type="button"
            className="btn-danger"
            disabled={deletingTemplateId !== null || mutation.isPending}
            onClick={() => void deleteTemplate(item)}
          >
            Скрыть шаблон
          </button>
        )}
      </div>
      {item.owner_user_id === user?.id && <PublicProgramSharePanel template={item} />}
      {!item.is_example && (
        <details className="program-danger-menu">
          <summary className="yfc-disclosure-summary">
            Другие действия
            <DisclosureIcon />
          </summary>
          <button
            type="button"
            className="btn-danger"
            disabled={deletingTemplateId !== null || mutation.isPending}
            onClick={() => void deleteTemplate(item)}
          >
            Удалить программу
          </button>
        </details>
      )}
    </article>
  );

  return (
    <>
      {isManage && (
        <header className="program-manage-intro">
          <span className="eyebrow">План / Моя программа</span>
          <h1 id="program-manage-heading" tabIndex={-1}>
            {showingOverview
              ? 'Центр управления'
              : manageActions.find((item) => item.panel === panel)?.title}
          </h1>
          <p className="muted">Текущая программа, настройки и быстрые действия.</p>
          {!showingOverview && (
            <button
              type="button"
              className="secondary program-manage-back"
              onClick={() => openPanel('overview')}
            >
              <Icon name="arrow-left" size={20} /> К центру управления
            </button>
          )}
        </header>
      )}
      <div
        className={isManage ? 'program-manage-layout' : undefined}
        hidden={isManage && !showingOverview}
      >
        <section
          className="program-active semantic-card semantic-card--action semantic-card--training"
          data-card-variant="action"
          data-semantic-family="training"
          aria-labelledby="active-program-title"
        >
          {templates.isLoading ? (
            <LoadingState label="Загружаем текущую программу…" />
          ) : templates.error ? (
            <ErrorState
              message={(templates.error as Error).message}
              retry={() => void templates.refetch()}
            />
          ) : activeTemplate ? (
            <>
              <div className="program-active__head">
                <div>
                  <span className="eyebrow">Текущая программа</span>
                  <h2 id="active-program-title">{activeTemplate.title}</h2>
                  <p>{programMeta(activeTemplate)}</p>
                </div>
                <Badge tone="success">Активна</Badge>
              </div>
              {isSummary ? (
                <div className="program-active__summary">
                  <span>Ближайшие тренировки и календарь — в разделе «План».</span>
                  {readOnly ? (
                    <span className="muted">Управление доступно после входа.</span>
                  ) : (
                    <AppLink className="button-link" to="/app?section=programs&view=manage">
                      Управление программой
                    </AppLink>
                  )}
                </div>
              ) : (
                <>
                  <div className="program-active__source">
                    <strong>{programKind(activeTemplate, user?.id)}</strong>
                    {activeTemplate.assigned_by_user_id &&
                    activeTemplate.assigned_by_user_id !== user?.id ? (
                      <span>
                        Назначил тренер
                        {activeTemplate.assigned_by_full_name
                          ? ` ${activeTemplate.assigned_by_full_name}`
                          : ''}
                      </span>
                    ) : (
                      <span>Вы можете посмотреть состав или изменить будущий шаблон.</span>
                    )}
                  </div>
                  <div className="program-active__actions">
                    <button
                      type="button"
                      className="secondary"
                      onClick={(event) => {
                        event.currentTarget.focus();
                        setPreviewStale(false);
                        setSelectedExample(activeTemplate);
                      }}
                    >
                      Посмотреть состав
                    </button>
                    {!(
                      activeTemplate.assigned_by_user_id &&
                      activeTemplate.assigned_by_user_id !== user?.id
                    ) && (
                      <button
                        type="button"
                        className="program-active__edit-action"
                        onClick={() => {
                          setSaveAsCopy(shouldSaveTemplateAsCopy(activeTemplate));
                          setEditingTemplate(activeTemplate);
                        }}
                      >
                        {shouldSaveTemplateAsCopy(activeTemplate)
                          ? 'Настроить свою копию'
                          : 'Редактировать шаблон'}
                      </button>
                    )}
                  </div>
                  {activeTemplate.owner_user_id === user?.id && (
                    <PublicProgramSharePanel template={activeTemplate} />
                  )}
                  {activeTemplate.assigned_program_id != null && (
                    <button
                      type="button"
                      className="btn-danger program-active__delete-action"
                      disabled={deleteAssignedMutation.isPending}
                      onClick={() => void deleteActiveProgram()}
                    >
                      Удалить программу
                    </button>
                  )}
                </>
              )}
            </>
          ) : (
            <div className="program-active__empty">
              <span className="eyebrow">Текущая программа</span>
              <h2 id="active-program-title">План ещё не выбран</h2>
              <p>Создайте свою программу сразу или выберите готовый шаблон.</p>
              <div className="program-active__actions">
                {isSummary ? (
                  <>
                    {readOnly ? (
                      <span className="muted">
                        Создание и выбор программы доступны после входа.
                      </span>
                    ) : (
                      <>
                        <AppLink
                          className="button-link program-wizard__anchor"
                          to="/app?section=programs&view=manage&start=create"
                        >
                          Создать свою программу
                        </AppLink>
                        <AppLink
                          className="secondary program-wizard__anchor"
                          to="/app?section=programs&view=manage&start=templates"
                        >
                          Программы и шаблоны
                        </AppLink>
                      </>
                    )}
                  </>
                ) : (
                  <>
                    <button type="button" onClick={() => openPanel('create')}>
                      Создать свою программу
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => {
                        openPanel('replace');
                        setGeneratorOpen(true);
                      }}
                    >
                      Подобрать программу
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => openPanel('library')}
                    >
                      Выбрать готовую
                    </button>
                  </>
                )}
              </div>
            </div>
          )}
        </section>
        {isManage && activeTemplate && (
          <nav className="program-manage-actions" aria-label="Управление программой">
            <div className="program-manage-actions__head">
              <h2>Управление</h2>
              <span className="muted">4 действия</span>
            </div>
            {manageActions.map((action) => (
              <button
                type="button"
                key={action.panel}
                className="program-manage-actions__item"
                data-program-panel={action.panel}
                onClick={() => openPanel(action.panel)}
              >
                <span className="program-manage-actions__icon">
                  <Icon name={action.icon} size={20} />
                </span>
                <span className="program-manage-actions__label">
                  <strong>{action.title}</strong>
                  <small>{action.description}</small>
                </span>
                <Icon name="chevron-right" size={20} />
              </button>
            ))}
          </nav>
        )}
      </div>
      {isManage && (
        <>
          <section className="program-manage-destination" hidden={panel !== 'operations'}>
            <h2>Назначение и изменения</h2>
            {panel === 'operations' &&
            activeTemplate?.assigned_program_id &&
            activeTemplate.assigned_program_start_date &&
            activeTemplate.assigned_program_duration_weeks != null &&
            activeTemplate.current_revision_number != null ? (
              <AssignedProgramDetails
                key={activeTemplate.assigned_program_id}
                programId={activeTemplate.assigned_program_id}
                currentRevisionNumber={activeTemplate.current_revision_number}
                startDate={activeTemplate.assigned_program_start_date}
                durationWeeks={activeTemplate.assigned_program_duration_weeks}
                showAiAdaptation
                workoutHistoryReturnPath="/app?section=programs&view=manage&panel=operations"
              />
            ) : (
              <p className="muted">Подробности назначения пока недоступны.</p>
            )}
          </section>
          <section className="program-manage-destination" hidden={panel !== 'replace'}>
            <h2>Заменить программу</h2>
            <p className="muted">
              Программа не изменится без явного подтверждения нового назначения.
            </p>
            <div className="program-manage-destination__actions">
              <button type="button" onClick={() => setGeneratorOpen(true)}>
                Подобрать программу
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => setRecommendationOpen(true)}
              >
                Подбор по параметрам
              </button>
              <button type="button" className="secondary" onClick={() => openPanel('library')}>
                Выбрать шаблон
              </button>
            </div>
          </section>
          <div className="program-manage-destination" hidden={panel !== 'create'}>
            {children}
            <ProgramImportPanel />
          </div>
          <LegacyProgramRecommendation
            open={recommendationOpen}
            onOpenChange={setRecommendationOpen}
            onPreview={setSelectedExample}
            onEditCopy={editCopy}
          />
          <ProgramRecommendation
            open={generatorOpen}
            onOpenChange={setGeneratorOpen}
            onOpenPrograms={() => openPanel('library')}
            onConfirmed={refreshProgramState}
          />
          <div className="program-manage-destination" hidden={panel !== 'library'}>
            <Card
              collapsible={false}
              defaultOpen={defaultLibraryOpen}
              family="training"
              id="program-library"
              title="Программы и шаблоны"
              description="Ваши заготовки и готовые варианты для быстрого запуска."
            >
              {templates.isLoading ? (
                <LoadingState />
              ) : templates.error ? (
                <ErrorState message={(templates.error as Error).message} />
              ) : !ownTemplates.length && !readyTemplates.length ? (
                <EmptyState
                  title="Программ пока нет"
                  text="Создайте первую программу в конструкторе."
                />
              ) : (
                <div className="program-library top-gap">
                  {!!ownTemplates.length && (
                    <section
                      className="program-library__group"
                      aria-labelledby="own-programs-title"
                    >
                      <div>
                        <h3 id="own-programs-title">Мои программы</h3>
                        <span>{ownTemplates.length}</span>
                      </div>
                      <div className="program-template-grid">
                        {ownTemplates.map(renderTemplate)}
                      </div>
                    </section>
                  )}
                  {!!readyTemplates.length && (
                    <section
                      className="program-library__group"
                      aria-labelledby="ready-programs-title"
                    >
                      <div>
                        <h3 id="ready-programs-title">Готовые шаблоны</h3>
                        <span>{readyTemplates.length}</span>
                      </div>
                      <div className="program-template-grid">
                        {readyTemplates.map(renderTemplate)}
                      </div>
                    </section>
                  )}
                </div>
              )}
              {!!hidden.data?.length && (
                <details className="compact-disclosure top-gap">
                  <summary className="yfc-disclosure-summary">
                    <span>Скрытые примеры программ ({hidden.data.length})</span>
                    <DisclosureIcon />
                  </summary>
                  <div className="list-grid top-gap">
                    {hidden.data.map((item) => (
                      <article className="list-row" key={item.id}>
                        <strong>{item.title}</strong>
                        <button
                          className="secondary"
                          onClick={() =>
                            mutation.mutate({
                              path: `/api/v1/programs/templates/${item.id}/restore`,
                              method: 'POST',
                            })
                          }
                        >
                          Восстановить
                        </button>
                      </article>
                    ))}
                  </div>
                </details>
              )}
            </Card>
          </div>
        </>
      )}
      {selectedExample && (
        <div
          className="modal program-example-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="program-example-title"
        >
          <button
            type="button"
            className="modal__backdrop"
            aria-label="Закрыть состав программы"
            onClick={() => setSelectedExample(null)}
          />
          <div
            className="modal__panel card program-example-modal__panel"
            ref={examplePanelRef}
            tabIndex={-1}
          >
            <div className="program-example-modal__content">
              <div className="program-example-modal__head">
                <div>
                  <span className="eyebrow">{programKind(selectedExample, user?.id)}</span>
                  <h2 id="program-example-title">{selectedExample.title}</h2>
                  <p className="muted">{programMeta(selectedExample)}</p>
                </div>
                <button
                  type="button"
                  className="secondary program-example-modal__close"
                  aria-label="Закрыть состав программы"
                  onClick={() => setSelectedExample(null)}
                >
                  <CloseIcon />
                </button>
              </div>
              <section
                className="program-preview-section"
                aria-label="Известные сведения о программе"
              >
                <h3>Что известно</h3>
                <p className="muted">Только сведения из программы без предположений о нагрузке.</p>
                <dl className="program-preview-facts">
                  {programPreviewFacts(selectedExample).map((fact) => (
                    <div className="program-preview-fact" key={fact.label}>
                      <dt>{fact.label}</dt>
                      <dd>{fact.value}</dd>
                      <small>{fact.source}</small>
                    </div>
                  ))}
                </dl>
                <p className="program-example-modal__owner">
                  {previewOwnership(selectedExample, user?.id)}
                </p>
                {selectedExample.assigned_program_revision_number != null && (
                  <p className="program-example-modal__owner">
                    Ревизия назначения: {selectedExample.assigned_program_revision_number}
                  </p>
                )}
              </section>
              <section className="program-preview-section" aria-label="Состав недели">
                <h3>Состав недели</h3>
                <p className="muted">
                  Все дни из исходного шаблона. Первый день раскрыт для примера.
                </p>
                <div className="program-example-days">
                  {selectedExample.days.map((day, dayIndex) => {
                    return (
                      <details className="program-example-day" key={day.id} open={dayIndex === 0}>
                        <summary className="yfc-disclosure-summary">
                          <span>
                            <strong>
                              День {day.day_number}. {day.title}
                            </strong>
                            <span className="muted">
                              {' '}
                              · {exerciseCountLabel(day.exercises.length)}
                            </span>
                          </span>
                          <DisclosureIcon />
                        </summary>
                        <h3 className="sr-only">
                          День {day.day_number}. {day.title}
                        </h3>
                        <ol>
                          {day.exercises.map((exercise) => {
                            const isCardio = exercise.metric_type === 'cardio';
                            return (
                              <li key={exercise.id}>
                                <strong>{exercise.exercise_title}</strong>
                                <span>
                                  {isCardio
                                    ? `${exercise.prescribed_duration_minutes ?? '—'} мин`
                                    : `${exercise.prescribed_sets} подх. × ${exercise.prescribed_reps} · отдых ${exercise.rest_seconds} сек.`}
                                </span>
                                {exercise.superset_group && (
                                  <small>
                                    Суперсет {exercise.superset_group} · упражнение{' '}
                                    {exercise.superset_order} из 2
                                  </small>
                                )}
                                {exercise.notes && <small>{exercise.notes}</small>}
                                <button
                                  type="button"
                                  className="text-button"
                                  onClick={() =>
                                    setGuide({
                                      id: exercise.exercise_id,
                                      title: exercise.exercise_title,
                                    })
                                  }
                                >
                                  {exercise.has_guide
                                    ? 'Техника и детали'
                                    : 'Подробнее об упражнении'}
                                </button>
                              </li>
                            );
                          })}
                        </ol>
                      </details>
                    );
                  })}
                </div>
              </section>
              <p className="program-preview-source">
                Состав и настройки отображены по источнику. Если данных нет, они не заменяются
                приблизительными значениями. Просмотр не изменяет активную программу.
              </p>
              {previewStale && (
                <p className="program-preview-stale" role="status">
                  Данные обновились. Проверьте сведения выше и повторите назначение.
                </p>
              )}
            </div>
            <div
              className={`program-example-modal__actions${
                selectedExampleIsTrainerReadonly ? ' program-example-modal__actions--readonly' : ''
              }`}
            >
              {selectedExampleIsTrainerReadonly ? (
                <p className="muted program-example-modal__readonly">
                  Эта программа назначена тренером. Изменение недоступно.
                </p>
              ) : (
                <>
                  <div className="program-example-modal__secondary-actions">
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => {
                        setPreviewSelectionId(selectedExample.id);
                        toast('Программа выбрана. Назначение выполняется отдельно.');
                      }}
                    >
                      {previewSelectionId === selectedExample.id ? 'Выбрана' : 'Выбрать'}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => {
                        setSaveAsCopy(true);
                        setEditingTemplate(selectedExample);
                        setSelectedExample(null);
                      }}
                    >
                      Создать копию
                    </button>
                    {selectedExample.can_edit && (
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          setSaveAsCopy(false);
                          setEditingTemplate(selectedExample);
                          setSelectedExample(null);
                        }}
                      >
                        Редактировать
                      </button>
                    )}
                  </div>
                  {selectedExample.is_active_for_current_user ? (
                    <button
                      type="button"
                      className="program-example-modal__primary-action"
                      disabled
                    >
                      Уже запущена
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="program-example-modal__primary-action"
                      disabled={previewChecking}
                      aria-label="Настроить расписание и запустить"
                      onClick={() => void assignFromPreview(selectedExample)}
                    >
                      {previewChecking ? 'Проверяем…' : 'Назначить по расписанию'}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
      {assignmentTemplate && (
        <div
          className="modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="assign-program-title"
        >
          <button
            type="button"
            className="modal__backdrop"
            aria-label="Закрыть настройку расписания"
            onClick={() => setAssignmentTemplate(null)}
          />
          <div
            className="modal__panel card assignment-modal"
            ref={assignmentPanelRef}
            tabIndex={-1}
          >
            <div className="section-head">
              <div>
                <span className="eyebrow">Расписание программы</span>
                <h2 id="assign-program-title">{assignmentTemplate.title}</h2>
              </div>
              <button
                type="button"
                className="secondary"
                aria-label="Закрыть настройку расписания"
                onClick={() => setAssignmentTemplate(null)}
              >
                <CloseIcon />
              </button>
            </div>
            <form
              className="stack"
              onSubmit={async (event) => {
                event.preventDefault();
                const active = templates.data?.find(
                  (template) => template.is_active_for_current_user,
                );
                let replaceActive = false;
                if (
                  active &&
                  !(await confirm({
                    title: 'Заменить активную программу?',
                    message: `«${active.title}» будет отправлена в архив, а «${assignmentTemplate.title}» станет активной.`,
                    confirmText: 'Заменить программу',
                  }))
                )
                  return;
                replaceActive = Boolean(active);
                assignmentMutation.mutate({ templateId: assignmentTemplate.id, replaceActive });
              }}
            >
              <div className="form-grid">
                <label className="field">
                  <span>Начать не раньше</span>
                  <DateInput
                    min={defaultStartDate}
                    value={assignmentStartDate}
                    onChange={(event) => {
                      const nextStartDate = event.target.value;
                      setAssignmentStartDate(nextStartDate);
                      setAssignmentWeekdays(defaultWeekdays(assignmentTemplate, nextStartDate));
                    }}
                    required
                  />
                </label>
                <label className="field">
                  <span>Длительность, недель</span>
                  <input
                    type="number"
                    min="1"
                    max={
                      assignmentTemplate.default_duration_weeks > 1
                        ? assignmentTemplate.default_duration_weeks
                        : 24
                    }
                    value={assignmentDuration}
                    onChange={(event) => setAssignmentDuration(Number(event.target.value))}
                    required
                  />
                </label>
              </div>
              {assignmentTemplate.default_duration_weeks > 1 && (
                <p className="auth-notice">
                  Для этого шаблона доступны назначения на{' '}
                  {assignmentTemplate.default_duration_weeks} недель с сохранённой схемой
                  повторений.
                </p>
              )}
              {assignmentTemplate.days.length > 7 ? (
                <p className="auth-notice">
                  Восьмидневный цикл планируется последовательно: одна тренировка за другой, начиная
                  с выбранной даты.
                </p>
              ) : (
                <div className="form-grid">
                  {assignmentWeekdays.map((_, dayIndex) => (
                    <label className="field" key={dayIndex}>
                      <span>
                        {programWeeklySessions(assignmentTemplate) ===
                        assignmentTemplate.days.length
                          ? assignmentTemplate.days[dayIndex]?.title || `День ${dayIndex + 1}`
                          : `Занятие ${dayIndex + 1}`}
                      </span>
                      <select
                        value={assignmentWeekdays[dayIndex] ?? ''}
                        onChange={(event) =>
                          setAssignmentWeekdays(
                            assignmentWeekdays.map((value, index) =>
                              index === dayIndex ? Number(event.target.value) : value,
                            ),
                          )
                        }
                      >
                        {weekdayLabels.map((label, weekday) => (
                          <option value={weekday} key={label}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
              )}
              {!assignmentScheduleIsValid && (
                <p className="field-error" role="alert">
                  Выберите разные дни недели в порядке тренировок. В одной неделе доступно до семи
                  дней.
                </p>
              )}
              <button
                disabled={
                  assignmentMutation.isPending ||
                  !assignmentScheduleIsValid ||
                  assignmentDuration < 1 ||
                  assignmentDuration > 24
                }
              >
                {assignmentMutation.isPending ? 'Назначаем…' : 'Назначить по расписанию'}
              </button>
            </form>
          </div>
        </div>
      )}
      {guide && (
        <ExerciseGuideDialog
          exerciseId={guide.id}
          exerciseTitle={guide.title}
          onClose={() => setGuide(null)}
        />
      )}
      {editingTemplate && (
        <div
          className="modal"
          role="dialog"
          aria-modal="true"
          aria-label={`${saveAsCopy ? 'Создание копии' : 'Редактирование'} программы «${editingTemplate.title}»`}
        >
          <button
            type="button"
            className="modal__backdrop"
            aria-label="Закрыть редактирование"
            onClick={() => void closeEditor()}
          />
          <div className="modal__panel program-editor-modal" ref={editorPanelRef} tabIndex={-1}>
            <div className="section-head">
              <strong>
                {saveAsCopy ? 'Редактирование личной копии' : 'Редактирование программы'}
              </strong>
              <button
                type="button"
                className="secondary"
                aria-label="Закрыть редактирование"
                onClick={() => void closeEditor()}
              >
                <CloseIcon />
              </button>
            </div>
            <ProgramBuilder
              editingTemplate={editingTemplate}
              saveAsCopy={saveAsCopy}
              onSaved={() => setEditingTemplate(null)}
              onDirtyChange={setEditorDirty}
            />
          </div>
        </div>
      )}
    </>
  );
}
