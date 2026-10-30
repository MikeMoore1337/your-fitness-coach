import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { api } from '../../shared/api/client';
import type { ApiSchemas } from '../../shared/api/types';

export type EquipmentProfiles = ApiSchemas['EquipmentProfilesResponse'];
export type EquipmentProfile = ApiSchemas['EquipmentProfile'];
export type EquipmentProfilesUpdate = ApiSchemas['EquipmentProfilesUpdate'];
export type EquipmentId = NonNullable<EquipmentProfile['equipment_ids']>[number];

export const equipmentChoices: readonly EquipmentId[] = [
  'dumbbell',
  'barbell',
  'bench',
  'rack',
  'cable',
  'machine',
  'kettlebell',
  'pullup_bar',
  'dip_bars',
  'cardio',
  'other',
];

export function useEquipmentProfiles(enabled = true) {
  const { user } = useAuth();
  const client = useQueryClient();
  const queryKey = ['equipment-profiles', user?.id];
  const query = useQuery({
    queryKey,
    queryFn: () => api<EquipmentProfiles>('/api/v1/me/equipment-profiles'),
    enabled: enabled && Boolean(user?.id),
    retry: false,
  });
  const save = useMutation({
    mutationFn: (body: EquipmentProfilesUpdate) =>
      api<EquipmentProfiles>('/api/v1/me/equipment-profiles', { method: 'PUT', body }),
    onSuccess: (data) => client.setQueryData(queryKey, data),
  });
  const active = enabled
    ? query.data?.profiles?.find((item) => item.id === query.data?.active_profile_id)
    : undefined;
  return { query, save, active };
}

export function equipmentAvailability(
  exercise: { is_custom?: boolean; required_equipment_ids?: string[] | null },
  profile: EquipmentProfile,
): 'available' | 'unavailable' | 'unknown' {
  if (exercise.is_custom || exercise.required_equipment_ids == null) return 'unknown';
  const owned = new Set(profile.equipment_ids ?? []);
  return exercise.required_equipment_ids.every((id) => owned.has(id as EquipmentId))
    ? 'available'
    : 'unavailable';
}

export function equipmentNeedsReview(
  exercise: { is_custom?: boolean; required_equipment_ids?: string[] | null },
  profile: EquipmentProfile,
): boolean {
  return equipmentAvailability(exercise, profile) === 'unknown';
}
