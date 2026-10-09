import { LandingV10Shell } from './LandingV10Shell';
import { LandingV10Hero, LandingV10Cycle } from './LandingV10Hero';
import {
  ArchiveTraining,
  ArchiveNutrition,
  ArchiveProgress,
  ArchiveCoachWork,
} from './LandingV10Scenes';
import { LandingV10SharedSections } from './LandingV10SharedSections';
import { StrengthScene } from './StrengthScene';
import { useLandingHeroMotion } from './useLandingHeroMotion';
import './landing.css';
export default function LandingV10AthletePage() {
  useLandingHeroMotion();
  return (
    <LandingV10Shell audience="athlete">
      <LandingV10Hero audience="athlete" />
      <LandingV10Cycle audience="athlete" />
      <StrengthScene />
      <ArchiveTraining />
      <ArchiveNutrition />
      <ArchiveProgress />
      <ArchiveCoachWork compact />
      <LandingV10SharedSections audience="athlete" />
    </LandingV10Shell>
  );
}
