export function isValidGtin(value: string): boolean {
  if (![8, 12, 13, 14].includes(value.length) || !/^\d+$/.test(value)) return false;
  const digits = [...value].map(Number);
  const payload = digits.slice(0, -1);
  const sum = payload.reduce(
    (total, digit, index) => total + digit * ((payload.length - index) % 2 === 1 ? 3 : 1),
    0,
  );
  return (10 - (sum % 10)) % 10 === digits.at(-1);
}
