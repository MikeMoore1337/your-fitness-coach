// Existing nutrition mock, positioned directly at hydration as required by #868.
if (new URLSearchParams(location.search).get('hydration') === 'quick') {
  const hydration = document.querySelector('.water-buttons')?.closest('section');
  if (hydration) {
    hydration.id = 'hydration';
    hydration.setAttribute('aria-label', 'Гидратация');
    document.fonts.ready.then(() => {
      hydration.scrollIntoView({ block: 'start', behavior: 'instant' });
      hydration.querySelector('button')?.focus({ preventScroll: true });
    });
  }
}
