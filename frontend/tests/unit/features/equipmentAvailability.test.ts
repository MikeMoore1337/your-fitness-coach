import { describe, expect, it } from 'vitest';
import {
  equipmentAvailability,
  equipmentChoices,
} from '../../../src/features/equipment/equipmentProfileState';

describe('equipment availability', () => {
  const home = { id: 'home', name: 'Дом', equipment_ids: ['dumbbell', 'bench'] as const };
  const profile = { ...home, equipment_ids: [...home.equipment_ids] };
  it('requires every canonical item, including accessories', () => {
    expect(equipmentAvailability({ required_equipment_ids: ['dumbbell', 'bench'] }, profile)).toBe(
      'available',
    );
    expect(
      equipmentAvailability({ required_equipment_ids: ['dumbbell', 'bench', 'rack'] }, profile),
    ).toBe('unavailable');
    expect(
      equipmentAvailability({ required_equipment_ids: [] }, { ...profile, equipment_ids: [] }),
    ).toBe('available');
    expect(
      equipmentAvailability(
        { required_equipment_ids: ['barbell', 'bench', 'rack', 'pullup_bar'] },
        { ...profile, equipment_ids: [...equipmentChoices] },
      ),
    ).toBe('available');
  });
  it('does not claim unknown or user-created requirements are available', () => {
    expect(equipmentAvailability({ required_equipment_ids: null }, profile)).toBe('unknown');
    expect(
      equipmentAvailability({ is_custom: true, required_equipment_ids: ['dumbbell'] }, profile),
    ).toBe('unknown');
  });
});
