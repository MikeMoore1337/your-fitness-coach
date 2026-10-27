import { createContext, useContext } from 'react';
import type { AiCoachContextDescriptor } from './aiCoachContext';

export type AiCoachWorkspacePanel = 'chat' | 'settings';

export interface AiCoachWorkspaceController {
  clearContext(): void;
  close(): void;
  isMinimized: boolean;
  isOpen: boolean;
  minimize(): void;
  open(
    trigger?: HTMLElement | null,
    panel?: AiCoachWorkspacePanel,
    context?: AiCoachContextDescriptor,
  ): void;
  resetLayout(): void;
  restore(): void;
  setPanel(panel: AiCoachWorkspacePanel): void;
}

export const AiCoachWorkspaceContext = createContext<AiCoachWorkspaceController | null>(null);

export function useOptionalAiCoachWorkspace(): AiCoachWorkspaceController | null {
  return useContext(AiCoachWorkspaceContext);
}

export function useAiCoachWorkspace(): AiCoachWorkspaceController {
  const value = useOptionalAiCoachWorkspace();
  if (!value) {
    throw new Error('useAiCoachWorkspace must be used inside AiCoachWorkspaceProvider');
  }
  return value;
}
