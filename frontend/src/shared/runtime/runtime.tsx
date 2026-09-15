import { createContext, useContext, useLayoutEffect, useMemo } from 'react';

export type RuntimeKind = 'production' | 'demo';

export interface RuntimeCapabilities {
  canMutateWorkout: boolean;
  canMutateNutrition: boolean;
  canMutateNutritionEntries: boolean;
  canMutateProgress: boolean;
  canMutateProfile: boolean;
  canMutatePrograms: boolean;
  canMutateCoach: boolean;
  canManageCoach: boolean;
  canCreateCatalog: boolean;
  canExport: boolean;
}

export const PRODUCTION_CAPABILITIES: RuntimeCapabilities = {
  canMutateWorkout: true,
  canMutateNutrition: true,
  canMutateNutritionEntries: true,
  canMutateProgress: true,
  canMutateProfile: true,
  canMutatePrograms: true,
  canMutateCoach: true,
  canManageCoach: true,
  canCreateCatalog: true,
  canExport: true,
};

export const DEMO_CAPABILITIES: RuntimeCapabilities = {
  canMutateWorkout: true,
  canMutateNutrition: true,
  canMutateNutritionEntries: false,
  canMutateProgress: false,
  canMutateProfile: false,
  canMutatePrograms: false,
  canMutateCoach: true,
  canManageCoach: false,
  canCreateCatalog: false,
  canExport: false,
};

export interface DemoApiRuntime {
  kind: 'demo';
  sessionToken: string;
  capabilities: RuntimeCapabilities;
  mapNavigationPath(to: string): string;
  onNavigate?: (to: string) => void;
  onMutation?: () => void | Promise<void>;
}

export interface ProductionApiRuntime {
  kind: 'production';
  capabilities: RuntimeCapabilities;
}

export type ApiRuntime = DemoApiRuntime | ProductionApiRuntime;

const productionRuntime: ProductionApiRuntime = {
  kind: 'production',
  capabilities: PRODUCTION_CAPABILITIES,
};

let activeRuntime: ApiRuntime = productionRuntime;

export function getApiRuntime(): ApiRuntime {
  return activeRuntime;
}

export function setApiRuntime(runtime: ApiRuntime): void {
  activeRuntime = runtime;
}

export function resetApiRuntime(): void {
  activeRuntime = productionRuntime;
}

const RuntimeContext = createContext<ApiRuntime>(productionRuntime);

export function useRuntime(): ApiRuntime {
  return useContext(RuntimeContext);
}

export function useRuntimeCapabilities(): RuntimeCapabilities {
  return useRuntime().capabilities;
}

export function DemoRuntimeProvider({
  children,
  mapNavigationPath,
  onNavigate,
  onMutation,
  sessionToken,
}: {
  children: React.ReactNode;
  mapNavigationPath(to: string): string;
  onNavigate?: (to: string) => void;
  onMutation?: () => void | Promise<void>;
  sessionToken: string;
}) {
  const runtime = useMemo<DemoApiRuntime>(
    () => ({
      kind: 'demo',
      sessionToken,
      capabilities: DEMO_CAPABILITIES,
      mapNavigationPath,
      onNavigate,
      onMutation,
    }),
    [mapNavigationPath, onMutation, onNavigate, sessionToken],
  );

  useLayoutEffect(() => {
    setApiRuntime(runtime);
    return () => {
      resetApiRuntime();
    };
  }, [runtime]);

  return <RuntimeContext.Provider value={runtime}>{children}</RuntimeContext.Provider>;
}
