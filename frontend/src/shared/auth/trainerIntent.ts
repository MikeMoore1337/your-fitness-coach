import { loginUrlForHostname } from '../navigation/appUrl';

export const TRAINER_INTENT_PATH = '/app?trainer_intent=1';
const TELEGRAM_TRANSPORT_PARAMS = new Set(['tgWebAppData', 'tgWebAppPlatform', 'tgWebAppVersion']);

export function trainerIntentLoginUrl(hostname: string): string {
  return `${loginUrlForHostname(hostname)}?next=${encodeURIComponent(TRAINER_INTENT_PATH)}`;
}

export function isTrainerIntentLocation(path: string, search: string, hash = ''): boolean {
  if (path !== '/app' || hash !== '') return false;
  const params = new URLSearchParams(search);
  return (
    params.getAll('trainer_intent').length === 1 &&
    params.get('trainer_intent') === '1' &&
    Array.from(params.keys()).every(
      (key) => key === 'trainer_intent' || TELEGRAM_TRANSPORT_PARAMS.has(key),
    )
  );
}
