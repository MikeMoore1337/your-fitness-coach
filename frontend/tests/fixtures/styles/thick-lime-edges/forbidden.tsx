export function ForbiddenInlineStyles() {
  return (
    <div
      style={{
        borderLeft: '3px solid var(--v2-lime)',
        boxShadow: 'inset 0 3px 0 var(--v2-lime)',
      }}
    />
  );
}

export const forbiddenCssInJs = `
  .card::before {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: 4px;
    background: var(--v2-lime);
  }
`;
