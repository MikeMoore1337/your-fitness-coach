export function AllowedInlineStyles() {
  return (
    <>
      <div style={{ border: '1px solid var(--v2-lime)' }} />
      <button type="button" style={{ border: '1px solid var(--v2-lime)' }} />
      <div className="active-tab" style={{ borderLeft: '3px solid var(--v2-lime)' }} />
      <div style={{ outline: '3px solid var(--v2-lime)' }} />
      <div className="semantic-warning" style={{ border: '1px solid var(--v2-lime)' }} />
    </>
  );
}
