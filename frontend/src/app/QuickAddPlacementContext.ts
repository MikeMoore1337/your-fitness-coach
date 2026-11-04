import { createContext } from 'react';

export const QuickAddPlacementContext = createContext<
  ((node: HTMLDivElement | null) => void) | null
>(null);
