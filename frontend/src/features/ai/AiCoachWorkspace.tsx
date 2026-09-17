import { createPortal } from 'react-dom';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react';
import type { AiCoachStatus } from '../../shared/api/types';
import { Button, IconButton, LoadingState } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { useDocumentScrollLock } from '../../shared/ui/useModalA11y';
import { useTelegramOverlayBackButton } from '../../shared/telegram/useTelegramOverlayBackButton';
import {
  AiCoachExperience,
  AiCoachPersonalConsentPanel,
  MemoryPanel,
  aiCoachQuotaHeaderCopy,
  getAiCoachQuotaState,
  useAiCoachQuota,
  useAiCoachStatus,
} from './AiCoachExperience';
import {
  AiCoachWorkspaceContext,
  type AiCoachWorkspaceController,
  type AiCoachWorkspacePanel,
} from './AiCoachWorkspaceContext';
import type { AiCoachContextDescriptor } from './aiCoachContext';

export const AI_COACH_WORKSPACE_LAYOUT_KEY = 'yfc:ai-coach:workspace-layout:v1';
export const AI_COACH_WORKSPACE_BREAKPOINT = 900;
export const AI_COACH_WORKSPACE_DEFAULT_WIDTH = 420;
export const AI_COACH_WORKSPACE_DEFAULT_HEIGHT = 660;

const AI_COACH_WORKSPACE_MIN_WIDTH = 360;
const AI_COACH_WORKSPACE_MAX_WIDTH = 560;
const AI_COACH_WORKSPACE_MIN_HEIGHT = 480;
const AI_COACH_WORKSPACE_MAX_HEIGHT = 800;
const AI_COACH_WORKSPACE_EDGE_GAP = 16;
const AI_COACH_WORKSPACE_BOTTOM_RESERVE = 88;

export interface AiCoachWorkspaceLayout {
  height: number;
  minimized: boolean;
  width: number;
  x: number;
  y: number;
}

export interface WorkspaceViewport {
  height: number;
  width: number;
}

export type AiCoachWorkspaceResizeDirection =
  'top' | 'right' | 'bottom' | 'left' | 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';

export const AI_COACH_WORKSPACE_RESIZE_DIRECTIONS: readonly AiCoachWorkspaceResizeDirection[] = [
  'top',
  'right',
  'bottom',
  'left',
  'top-left',
  'top-right',
  'bottom-left',
  'bottom-right',
];

type WorkspacePointerSession =
  | {
      kind: 'drag';
      pointerId: number;
      startLayout: AiCoachWorkspaceLayout;
      startX: number;
      startY: number;
    }
  | {
      kind: 'resize';
      direction: AiCoachWorkspaceResizeDirection;
      pointerId: number;
      startLayout: AiCoachWorkspaceLayout;
      startX: number;
      startY: number;
    };

const focusableSelector = [
  'button:not([disabled])',
  'a[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

function readWorkspaceViewport(): WorkspaceViewport {
  const width = Math.max(
    320,
    Math.round(window.innerWidth || document.documentElement.clientWidth || 1024),
  );
  const visualHeight = window.visualViewport?.height;
  const height = Math.max(
    1,
    Math.round(visualHeight || window.innerHeight || document.documentElement.clientHeight || 768),
  );
  return { width, height };
}

function isWorkspaceMobile(viewport: WorkspaceViewport): boolean {
  return viewport.width < AI_COACH_WORKSPACE_BREAKPOINT;
}

function finiteOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function bounded(value: number, minimum: number, maximum: number): number {
  if (maximum < minimum) return minimum;
  return Math.min(maximum, Math.max(minimum, value));
}

export function clampAiCoachWorkspaceLayout(
  value: Partial<AiCoachWorkspaceLayout> = {},
  viewport: WorkspaceViewport = readWorkspaceViewport(),
): AiCoachWorkspaceLayout {
  const maxWidth = Math.max(
    AI_COACH_WORKSPACE_MIN_WIDTH,
    Math.min(AI_COACH_WORKSPACE_MAX_WIDTH, viewport.width - AI_COACH_WORKSPACE_EDGE_GAP * 2),
  );
  const maxHeight = Math.max(
    AI_COACH_WORKSPACE_MIN_HEIGHT,
    Math.min(
      AI_COACH_WORKSPACE_MAX_HEIGHT,
      viewport.height - AI_COACH_WORKSPACE_EDGE_GAP * 2 - AI_COACH_WORKSPACE_BOTTOM_RESERVE,
    ),
  );
  const width = bounded(
    finiteOrNull(value.width) ?? AI_COACH_WORKSPACE_DEFAULT_WIDTH,
    AI_COACH_WORKSPACE_MIN_WIDTH,
    maxWidth,
  );
  const height = bounded(
    finiteOrNull(value.height) ?? AI_COACH_WORKSPACE_DEFAULT_HEIGHT,
    AI_COACH_WORKSPACE_MIN_HEIGHT,
    maxHeight,
  );
  const maxX = Math.max(
    AI_COACH_WORKSPACE_EDGE_GAP,
    viewport.width - width - AI_COACH_WORKSPACE_EDGE_GAP,
  );
  const maxY = Math.max(
    AI_COACH_WORKSPACE_EDGE_GAP,
    viewport.height - height - AI_COACH_WORKSPACE_BOTTOM_RESERVE,
  );
  const defaultX = Math.max(AI_COACH_WORKSPACE_EDGE_GAP, viewport.width - width - 24);
  const defaultY = Math.max(
    AI_COACH_WORKSPACE_EDGE_GAP,
    viewport.height - height - AI_COACH_WORKSPACE_BOTTOM_RESERVE,
  );
  return {
    height,
    minimized: value.minimized === true,
    width,
    x: bounded(finiteOrNull(value.x) ?? defaultX, AI_COACH_WORKSPACE_EDGE_GAP, maxX),
    y: bounded(finiteOrNull(value.y) ?? defaultY, AI_COACH_WORKSPACE_EDGE_GAP, maxY),
  };
}

function maxWidthWithinViewport(viewport: WorkspaceViewport, anchorX: number): number {
  const viewportMax = Math.min(
    AI_COACH_WORKSPACE_MAX_WIDTH,
    viewport.width - AI_COACH_WORKSPACE_EDGE_GAP * 2,
  );
  return Math.max(
    AI_COACH_WORKSPACE_MIN_WIDTH,
    Math.min(viewportMax, viewport.width - AI_COACH_WORKSPACE_EDGE_GAP - anchorX),
  );
}

function maxHeightWithinViewport(viewport: WorkspaceViewport, anchorY: number): number {
  const viewportMax = Math.min(
    AI_COACH_WORKSPACE_MAX_HEIGHT,
    viewport.height - AI_COACH_WORKSPACE_EDGE_GAP * 2 - AI_COACH_WORKSPACE_BOTTOM_RESERVE,
  );
  return Math.max(
    AI_COACH_WORKSPACE_MIN_HEIGHT,
    Math.min(viewportMax, viewport.height - AI_COACH_WORKSPACE_BOTTOM_RESERVE - anchorY),
  );
}

export function resizeAiCoachWorkspaceLayout(
  value: AiCoachWorkspaceLayout,
  direction: AiCoachWorkspaceResizeDirection,
  deltaX: number,
  deltaY: number,
  viewport: WorkspaceViewport = readWorkspaceViewport(),
): AiCoachWorkspaceLayout {
  const resizeLeft = direction.includes('left');
  const resizeRight = direction.includes('right');
  const resizeTop = direction.includes('top');
  const resizeBottom = direction.includes('bottom');
  let { height, width, x, y } = value;

  if (resizeLeft) {
    const right = value.x + value.width;
    width = bounded(
      value.width - deltaX,
      AI_COACH_WORKSPACE_MIN_WIDTH,
      Math.min(
        maxWidthWithinViewport(viewport, AI_COACH_WORKSPACE_EDGE_GAP),
        right - AI_COACH_WORKSPACE_EDGE_GAP,
      ),
    );
    x = right - width;
  } else if (resizeRight) {
    width = bounded(
      value.width + deltaX,
      AI_COACH_WORKSPACE_MIN_WIDTH,
      maxWidthWithinViewport(viewport, value.x),
    );
  }

  if (resizeTop) {
    const bottom = value.y + value.height;
    height = bounded(
      value.height - deltaY,
      AI_COACH_WORKSPACE_MIN_HEIGHT,
      Math.min(
        AI_COACH_WORKSPACE_MAX_HEIGHT,
        viewport.height - AI_COACH_WORKSPACE_EDGE_GAP * 2,
        bottom - AI_COACH_WORKSPACE_EDGE_GAP,
      ),
    );
    y = bottom - height;
  } else if (resizeBottom) {
    height = bounded(
      value.height + deltaY,
      AI_COACH_WORKSPACE_MIN_HEIGHT,
      maxHeightWithinViewport(viewport, value.y),
    );
  }

  return clampAiCoachWorkspaceLayout({ ...value, height, width, x, y }, viewport);
}

export function readAiCoachWorkspaceLayout(
  viewport: WorkspaceViewport = readWorkspaceViewport(),
): AiCoachWorkspaceLayout | null {
  try {
    const raw = window.localStorage.getItem(AI_COACH_WORKSPACE_LAYOUT_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    const record = parsed as Record<string, unknown>;
    if (record.version !== 1) return null;
    return clampAiCoachWorkspaceLayout(
      {
        height: record.height as number | undefined,
        minimized: record.minimized === true,
        width: record.width as number | undefined,
        x: record.x as number | undefined,
        y: record.y as number | undefined,
      },
      viewport,
    );
  } catch {
    return null;
  }
}

function storeAiCoachWorkspaceLayout(layout: AiCoachWorkspaceLayout): void {
  try {
    window.localStorage.setItem(
      AI_COACH_WORKSPACE_LAYOUT_KEY,
      JSON.stringify({ version: 1, ...layout }),
    );
  } catch {
    // A restrictive WebView should keep the layout usable in memory.
  }
}

function useWorkspaceViewport(): WorkspaceViewport {
  const [viewport, setViewport] = useState<WorkspaceViewport>(readWorkspaceViewport);

  useEffect(() => {
    const sync = () => setViewport(readWorkspaceViewport());
    const visualViewport = window.visualViewport;
    window.addEventListener('resize', sync);
    visualViewport?.addEventListener('resize', sync);
    visualViewport?.addEventListener('scroll', sync);
    sync();
    return () => {
      window.removeEventListener('resize', sync);
      visualViewport?.removeEventListener('resize', sync);
      visualViewport?.removeEventListener('scroll', sync);
    };
  }, []);

  return viewport;
}

function workspaceStatusCopy(status: AiCoachStatus): string {
  return status.generic_available ? 'Готов' : 'Недоступен';
}

function AiCoachWorkspaceSettings({
  mobile,
  onResetLayout,
  status,
}: {
  mobile: boolean;
  onResetLayout(): void;
  status: AiCoachStatus;
}) {
  return (
    <div className="ai-coach-workspace__settings" data-testid="ai-coach-workspace-settings">
      <div className="ai-coach-workspace__settings-intro">
        <h3 id="ai-coach-settings-title">Настройки</h3>
        <p>Персонализация и память AI Coach.</p>
      </div>
      <AiCoachPersonalConsentPanel status={status} />
      <div className="ai-coach-workspace__memory">
        <MemoryPanel />
      </div>
      {!mobile && (
        <section className="ai-coach-settings-section ai-coach-settings-section--layout">
          <div>
            <h3>Положение окна</h3>
            <p>Позиция и размер сохраняются на этом устройстве.</p>
          </div>
          <Button type="button" variant="secondary" onClick={onResetLayout}>
            Сбросить
          </Button>
        </section>
      )}
    </div>
  );
}

function AiCoachWorkspacePortal({
  close,
  isMinimized,
  isOpen,
  layout,
  minimize,
  panel,
  resetLayout,
  restore,
  setPanel,
  focusRevision,
  updateLayout,
  persistLayout,
  status,
  context,
  onClearContext,
  viewport,
}: {
  close(): void;
  isMinimized: boolean;
  isOpen: boolean;
  layout: AiCoachWorkspaceLayout;
  minimize(): void;
  panel: AiCoachWorkspacePanel;
  persistLayout(): void;
  resetLayout(): void;
  restore(): void;
  setPanel(next: AiCoachWorkspacePanel): void;
  status?: AiCoachStatus;
  context: AiCoachContextDescriptor | null;
  onClearContext(): void;
  focusRevision: number;
  updateLayout(next: AiCoachWorkspaceLayout, persist?: boolean): void;
  viewport: WorkspaceViewport;
}) {
  const mobile = isWorkspaceMobile(viewport);
  const minimized = isMinimized && !mobile;
  const modalOpen = mobile && isOpen && !minimized;
  const [pointerSession, setPointerSession] = useState<WorkspacePointerSession | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const focusedRevisionRef = useRef<number | null>(null);
  const layoutRef = useRef(layout);
  const viewportRef = useRef(viewport);
  const [historySlot, setHistorySlot] = useState<HTMLDivElement | null>(null);
  const quota = useAiCoachQuota();
  const quotaState = getAiCoachQuotaState(quota.data);

  useEffect(() => {
    layoutRef.current = layout;
  }, [layout]);

  useEffect(() => {
    viewportRef.current = viewport;
  }, [viewport]);

  useEffect(() => {
    const root = document.documentElement;
    if (!isOpen || mobile || minimized || context?.surface !== 'workout') {
      root.style.removeProperty('--ai-coach-workspace-right-reserve');
      return;
    }

    const rightReserve = Math.max(0, viewport.width - layout.x + AI_COACH_WORKSPACE_EDGE_GAP);
    root.style.setProperty('--ai-coach-workspace-right-reserve', `${rightReserve}px`);
    return () => {
      root.style.removeProperty('--ai-coach-workspace-right-reserve');
    };
  }, [context?.surface, isOpen, layout.x, minimized, mobile, viewport.width]);

  const handleBack = useCallback(() => {
    if (panel === 'settings') {
      setPanel('chat');
      return;
    }
    close();
  }, [close, panel, setPanel]);

  useDocumentScrollLock(modalOpen);
  useTelegramOverlayBackButton(modalOpen, handleBack);

  useEffect(() => {
    if (!isOpen || minimized || !status) return;
    const frame = window.requestAnimationFrame(() => {
      const isInitialMobileChatFocus =
        mobile && panel === 'chat' && focusedRevisionRef.current !== focusRevision;
      focusedRevisionRef.current = focusRevision;
      const contextualTarget = panelRef.current?.querySelector<HTMLElement>(
        '[data-ai-coach-contextual-focus]',
      );
      if (context && !contextualTarget) return;
      const target =
        contextualTarget ??
        (isInitialMobileChatFocus
          ? panelRef.current
          : (panelRef.current?.querySelector<HTMLElement>(
              '[data-ai-coach-workspace-initial-focus]',
            ) ??
            panelRef.current?.querySelector<HTMLElement>(
              'button:not([disabled]), textarea, [tabindex="-1"]',
            )));
      (target ?? panelRef.current)?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [context, focusRevision, isOpen, minimized, mobile, panel, status]);

  useEffect(() => {
    if (!isOpen || minimized || !bodyRef.current) return;
    bodyRef.current.scrollTop = 0;
  }, [isOpen, minimized, panel]);

  useEffect(() => {
    if (!isOpen || minimized) return;
    const onDocumentKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      handleBack();
    };
    document.addEventListener('keydown', onDocumentKeyDown);
    return () => document.removeEventListener('keydown', onDocumentKeyDown);
  }, [handleBack, isOpen, minimized]);

  useEffect(() => {
    if (!pointerSession) return;
    const onPointerMove = (event: PointerEvent) => {
      if (event.pointerId !== pointerSession.pointerId) return;
      const deltaX = event.clientX - pointerSession.startX;
      const deltaY = event.clientY - pointerSession.startY;
      const start = pointerSession.startLayout;
      const next =
        pointerSession.kind === 'drag'
          ? clampAiCoachWorkspaceLayout(
              { ...start, x: start.x + deltaX, y: start.y + deltaY },
              viewportRef.current,
            )
          : resizeAiCoachWorkspaceLayout(
              start,
              pointerSession.direction,
              deltaX,
              deltaY,
              viewportRef.current,
            );
      updateLayout(next);
    };
    const finish = (event: PointerEvent) => {
      if (event.pointerId !== pointerSession.pointerId) return;
      persistLayout();
      setPointerSession(null);
    };
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', finish);
    window.addEventListener('pointercancel', finish);
    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', finish);
      window.removeEventListener('pointercancel', finish);
    };
  }, [persistLayout, pointerSession, updateLayout]);

  const beginPointerSession = (
    event: ReactPointerEvent<HTMLDivElement>,
    kind: WorkspacePointerSession['kind'],
    direction: AiCoachWorkspaceResizeDirection = 'bottom-right',
  ) => {
    if (mobile || event.button !== 0 || !isOpen || minimized) return;
    if ((event.target as HTMLElement).closest('button, a, input, select, textarea')) return;
    event.preventDefault();
    if (kind === 'resize') {
      setPointerSession({
        direction,
        kind,
        pointerId: event.pointerId,
        startLayout: layoutRef.current,
        startX: event.clientX,
        startY: event.clientY,
      });
      return;
    }
    setPointerSession({
      kind,
      pointerId: event.pointerId,
      startLayout: layoutRef.current,
      startX: event.clientX,
      startY: event.clientY,
    });
  };

  const resizeWithKeyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (mobile) return;
    const step = event.shiftKey ? 64 : 32;
    const deltas: Record<string, [number, number]> = {
      ArrowDown: [0, step],
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
    };
    const delta = deltas[event.key];
    if (!delta) return;
    event.preventDefault();
    updateLayout(
      resizeAiCoachWorkspaceLayout(
        layoutRef.current,
        'bottom-right',
        delta[0],
        delta[1],
        viewportRef.current,
      ),
      true,
    );
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (!mobile || event.key !== 'Tab' || !panelRef.current) return;
    const focusable = Array.from(
      panelRef.current.querySelectorAll<HTMLElement>(focusableSelector),
    ).filter((element) => element.offsetParent !== null);
    if (!focusable.length) {
      event.preventDefault();
      panelRef.current.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  };

  if (!isOpen) return null;
  if (!status) {
    return createPortal(
      <aside className="ai-coach-workspace-layer" data-testid="ai-coach-workspace-layer">
        <section
          className={`ai-coach-workspace ai-coach-workspace--${mobile ? 'mobile' : 'desktop'}`}
          role={mobile ? 'dialog' : 'region'}
          aria-modal={mobile ? true : undefined}
          aria-labelledby="ai-coach-workspace-title"
        >
          <header className="ai-coach-workspace__header">
            <div className="ai-coach-workspace__drag-handle">
              <h2 id="ai-coach-workspace-title">AI Coach</h2>
            </div>
            <IconButton
              aria-label="Закрыть AI Coach"
              title="Закрыть AI Coach"
              type="button"
              onClick={close}
            >
              <Icon name="close" size={20} />
            </IconButton>
          </header>
          <div className="ai-coach-workspace__loading">
            <LoadingState label="Проверяем доступность AI Coach…" />
          </div>
        </section>
      </aside>,
      document.body,
    );
  }

  const workspaceStyle = mobile
    ? ({ '--ai-coach-visual-height': `${viewport.height}px` } as CSSProperties)
    : ({
        height: `${layout.height}px`,
        left: `${layout.x}px`,
        top: `${layout.y}px`,
        width: `${layout.width}px`,
      } as CSSProperties);

  return createPortal(
    <aside
      className="ai-coach-workspace-layer"
      data-testid="ai-coach-workspace-layer"
      style={
        mobile
          ? ({ '--ai-coach-visual-height': `${viewport.height}px` } as CSSProperties)
          : undefined
      }
    >
      <section
        aria-label={minimized ? 'AI Coach' : undefined}
        aria-labelledby={minimized ? undefined : 'ai-coach-workspace-title'}
        aria-modal={mobile ? true : undefined}
        className={`ai-coach-workspace ai-coach-workspace--${mobile ? 'mobile' : 'desktop'}${
          minimized ? ' is-minimized' : ''
        }`}
        data-minimized={minimized || undefined}
        data-context-surface={context?.surface}
        data-testid="ai-coach-workspace"
        ref={panelRef}
        role={mobile ? 'dialog' : 'region'}
        style={workspaceStyle}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        <header className="ai-coach-workspace__header">
          <div
            className="ai-coach-workspace__drag-handle"
            title={mobile ? undefined : 'Перетащить окно AI Coach'}
            onPointerDown={(event) => beginPointerSession(event, 'drag')}
          >
            {minimized ? (
              <button
                aria-label="Открыть AI Coach"
                className="ai-coach-workspace__minimized-trigger"
                data-ai-coach-workspace-initial-focus
                data-testid="ai-coach-workspace-restore"
                title="Открыть AI Coach"
                type="button"
                onClick={restore}
              >
                <Icon name="ai-coach" size={20} />
                <span>AI Coach</span>
              </button>
            ) : (
              <>
                <h2 id="ai-coach-workspace-title">
                  {mobile && panel === 'settings' ? 'AI Coach / Настройки' : 'AI Coach'}
                </h2>
                {(!mobile || panel === 'chat') && (
                  <span
                    className={`ai-coach-workspace__status${
                      status.generic_available
                        ? quotaState === 'unknown'
                          ? ''
                          : ` ai-coach-workspace__status--${quotaState}`
                        : ' is-unavailable'
                    }`}
                    data-testid="ai-coach-workspace-status"
                    title={quota.data ? `Лимит: ${quota.data.limit} запросов` : undefined}
                  >
                    <span aria-hidden="true" />
                    <span
                      data-quota-limit={quota.data?.limit}
                      data-quota-remaining={quota.data?.remaining}
                      data-testid="ai-coach-quota"
                    >
                      {status.generic_available
                        ? aiCoachQuotaHeaderCopy(quota.data)
                        : workspaceStatusCopy(status)}
                    </span>
                  </span>
                )}
              </>
            )}
          </div>
          {!minimized && (
            <div className="ai-coach-workspace__header-actions">
              {(!mobile || panel === 'chat') && (
                <div className="ai-coach-workspace__history-slot" ref={setHistorySlot} />
              )}
              {mobile && panel === 'settings' && (
                <IconButton
                  aria-label="Назад в чат"
                  data-ai-coach-workspace-initial-focus
                  title="Назад в чат"
                  type="button"
                  onClick={() => setPanel('chat')}
                >
                  <Icon name="arrow-left" size={20} />
                </IconButton>
              )}
              {!mobile && (
                <IconButton
                  aria-label="Свернуть AI Coach"
                  data-testid="ai-coach-workspace-minimize"
                  title="Свернуть AI Coach"
                  type="button"
                  onClick={minimize}
                >
                  <Icon name="minus" size={20} />
                </IconButton>
              )}
              {(!mobile || panel === 'chat') && (
                <IconButton
                  aria-label={
                    panel === 'settings' ? 'Вернуться в чат' : 'Открыть настройки AI Coach'
                  }
                  data-testid="ai-coach-workspace-settings-toggle"
                  title={panel === 'settings' ? 'Вернуться в чат' : 'Настройки AI Coach'}
                  type="button"
                  onClick={() => setPanel(panel === 'settings' ? 'chat' : 'settings')}
                >
                  <Icon name={panel === 'settings' ? 'arrow-left' : 'settings'} size={20} />
                </IconButton>
              )}
              {(!mobile || panel === 'chat') && (
                <IconButton
                  aria-label="Закрыть AI Coach"
                  data-ai-coach-workspace-initial-focus
                  title="Закрыть AI Coach"
                  type="button"
                  onClick={close}
                >
                  <Icon name="close" size={20} />
                </IconButton>
              )}
            </div>
          )}
        </header>

        <div className="ai-coach-workspace__body" hidden={minimized} ref={bodyRef}>
          <div className="ai-coach-workspace__view" hidden={panel !== 'chat'}>
            <AiCoachExperience
              entryPoint="profile"
              historyTarget={historySlot}
              showMemorySettings={false}
              showPersonalConsent={false}
              status={status}
              context={context}
              onClearContext={onClearContext}
            />
          </div>
          <div className="ai-coach-workspace__view" hidden={panel !== 'settings'}>
            <AiCoachWorkspaceSettings mobile={mobile} onResetLayout={resetLayout} status={status} />
          </div>
        </div>
        {!mobile && !minimized && (
          <>
            <div
              className="ai-coach-workspace__resize-zones"
              data-testid="ai-coach-workspace-resize-zones"
            >
              {AI_COACH_WORKSPACE_RESIZE_DIRECTIONS.map((direction) => (
                <div
                  aria-hidden="true"
                  className={`ai-coach-workspace__resize-zone ai-coach-workspace__resize-zone--${direction}`}
                  data-resize-direction={direction}
                  data-testid={`ai-coach-workspace-resize-${direction}`}
                  key={direction}
                  onPointerDown={(event) => beginPointerSession(event, 'resize', direction)}
                />
              ))}
            </div>
            <div
              aria-label="Изменить размер окна AI Coach с клавиатуры"
              className="ai-coach-workspace__keyboard-resize"
              data-testid="ai-coach-workspace-resize"
              role="button"
              tabIndex={0}
              onKeyDown={resizeWithKeyboard}
            />
          </>
        )}
      </section>
    </aside>,
    document.body,
  );
}

type AiCoachWorkspacePortalProps = Parameters<typeof AiCoachWorkspacePortal>[0];

function AiCoachWorkspaceStatusQueryBridge(props: Omit<AiCoachWorkspacePortalProps, 'status'>) {
  const statusQuery = useAiCoachStatus();
  return <AiCoachWorkspacePortal {...props} status={statusQuery.data} />;
}

function AiCoachWorkspaceStatusBridge({
  providedStatus,
  ...portalProps
}: AiCoachWorkspacePortalProps & { providedStatus?: AiCoachStatus }) {
  if (providedStatus) {
    return <AiCoachWorkspacePortal {...portalProps} status={providedStatus} />;
  }
  return <AiCoachWorkspaceStatusQueryBridge {...portalProps} />;
}

export function AiCoachWorkspaceProvider({
  children,
  status,
}: {
  children: ReactNode;
  status?: AiCoachStatus;
}) {
  const viewport = useWorkspaceViewport();
  const viewportRef = useRef(viewport);
  const [layout, setLayout] = useState<AiCoachWorkspaceLayout>(
    () => readAiCoachWorkspaceLayout(viewport) ?? clampAiCoachWorkspaceLayout({}, viewport),
  );
  const [isOpen, setIsOpen] = useState(false);
  const [panel, setPanel] = useState<AiCoachWorkspacePanel>('chat');
  const [context, setContext] = useState<AiCoachContextDescriptor | null>(null);
  const [focusRevision, setFocusRevision] = useState(0);
  const layoutRef = useRef(layout);
  const triggerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    viewportRef.current = viewport;
    if (isWorkspaceMobile(viewport)) return;
    const next = clampAiCoachWorkspaceLayout(layoutRef.current, viewport);
    layoutRef.current = next;
    setLayout(next);
  }, [viewport]);

  const persistLayout = useCallback(() => {
    storeAiCoachWorkspaceLayout(layoutRef.current);
  }, []);

  const updateLayout = useCallback((next: AiCoachWorkspaceLayout, persist = false) => {
    const clamped = clampAiCoachWorkspaceLayout(next, viewportRef.current);
    layoutRef.current = clamped;
    setLayout(clamped);
    if (persist) storeAiCoachWorkspaceLayout(clamped);
  }, []);

  const resetLayout = useCallback(() => {
    updateLayout(clampAiCoachWorkspaceLayout({}, viewportRef.current), true);
  }, [updateLayout]);

  const open = useCallback(
    (
      trigger?: HTMLElement | null,
      nextPanel: AiCoachWorkspacePanel = 'chat',
      nextContext?: AiCoachContextDescriptor,
    ) => {
      triggerRef.current =
        trigger ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
      setContext(nextContext ?? null);
      setPanel(nextPanel);
      setFocusRevision((revision) => revision + 1);
      if (layoutRef.current.minimized) {
        updateLayout({ ...layoutRef.current, minimized: false }, true);
      }
      setIsOpen(true);
    },
    [updateLayout],
  );

  const close = useCallback(() => {
    setIsOpen(false);
    setPanel('chat');
    setContext(null);
    const trigger = triggerRef.current;
    window.requestAnimationFrame(() => {
      if (trigger?.isConnected) trigger.focus();
    });
  }, []);

  const clearContext = useCallback(() => setContext(null), []);

  const minimize = useCallback(() => {
    if (isWorkspaceMobile(viewportRef.current)) return;
    updateLayout({ ...layoutRef.current, minimized: true }, true);
  }, [updateLayout]);

  const restore = useCallback(() => {
    updateLayout({ ...layoutRef.current, minimized: false }, true);
  }, [updateLayout]);

  const controller = useMemo<AiCoachWorkspaceController>(
    () => ({
      clearContext,
      close,
      isMinimized: layout.minimized,
      isOpen,
      minimize,
      open,
      resetLayout,
      restore,
      setPanel,
    }),
    [clearContext, close, isOpen, layout.minimized, minimize, open, resetLayout, restore],
  );

  return (
    <AiCoachWorkspaceContext.Provider value={controller}>
      {children}
      {isOpen && (
        <AiCoachWorkspaceStatusBridge
          close={close}
          isMinimized={layout.minimized}
          isOpen={isOpen}
          layout={layout}
          minimize={minimize}
          panel={panel}
          persistLayout={persistLayout}
          providedStatus={status}
          resetLayout={resetLayout}
          restore={restore}
          setPanel={setPanel}
          context={context}
          onClearContext={clearContext}
          focusRevision={focusRevision}
          updateLayout={updateLayout}
          viewport={viewport}
        />
      )}
    </AiCoachWorkspaceContext.Provider>
  );
}
