export function detectedTimeZone(fallback = 'Europe/Moscow'): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || fallback;
  } catch {
    return fallback;
  }
}

export function formatCalendarDate(
  value: string,
  options: Intl.DateTimeFormatOptions,
  locale = 'ru-RU',
): string {
  return new Intl.DateTimeFormat(locale, options).format(new Date(`${value}T12:00:00`));
}

export function formatTimeZoneLabel(timeZone: string): string {
  try {
    return (
      new Intl.DateTimeFormat('ru-RU', { timeZone, timeZoneName: 'longGeneric' })
        .formatToParts()
        .find((part) => part.type === 'timeZoneName')?.value ?? 'Часовой пояс профиля'
    );
  } catch {
    return 'Часовой пояс профиля';
  }
}

export function dateInputValue(date: Date, timeZone = detectedTimeZone()): string {
  try {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(date);
    const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    if (value.year && value.month && value.day) return `${value.year}-${value.month}-${value.day}`;
  } catch {
    // Fall back to the device-local calendar below for an invalid or unsupported timezone.
  }
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function dateTimeInputValue(date: Date, timeZone = detectedTimeZone()): string {
  try {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(date);
    const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    if (value.year && value.month && value.day && value.hour && value.minute) {
      return `${value.year}-${value.month}-${value.day}T${value.hour}:${value.minute}`;
    }
  } catch {
    // Fall back to the device-local wall time below for an invalid or unsupported timezone.
  }
  const datePart = dateInputValue(date);
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  return `${datePart}T${hour}:${minute}`;
}

export function addCalendarDays(value: string, days: number): string {
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return value;
  const date = new Date(Date.UTC(year, month - 1, day + days));
  return date.toISOString().slice(0, 10);
}

export function calendarWeek(value: string): string[] {
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return [value];
  const date = new Date(Date.UTC(year, month - 1, day));
  const mondayOffset = (date.getUTCDay() + 6) % 7;
  const monday = new Date(Date.UTC(year, month - 1, day - mondayOffset));
  return Array.from({ length: 7 }, (_, index) => {
    const weekDay = new Date(monday);
    weekDay.setUTCDate(monday.getUTCDate() + index);
    return weekDay.toISOString().slice(0, 10);
  });
}
