import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { useEquipmentProfiles } from '../../../src/features/equipment/equipmentProfileState';

vi.mock('../../../src/app/AuthProvider', () => ({ useAuth: () => ({ user: { id: 42 } }) }));

it('never applies a cached trainer profile to a disabled client context', () => {
  const client = new QueryClient();
  client.setQueryData(['equipment-profiles', 42], {
    revision: 1,
    active_profile_id: 'home',
    profiles: [{ id: 'home', name: 'Дом тренера', equipment_ids: ['dumbbell'] }],
  });
  const { result, rerender } = renderHook(({ enabled }) => useEquipmentProfiles(enabled), {
    initialProps: { enabled: true },
    wrapper: ({ children }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
  expect(result.current.active?.name).toBe('Дом тренера');
  rerender({ enabled: false });
  expect(result.current.active).toBeUndefined();
});
