// Reuse B's DOM, icons, native dialog and existing navigation; refine only this menu.
if (params.has('capture')) {
  document.body.classList.add('quick-add-refinement');
  const fitVisibleViewport = () => {
    const view = window.visualViewport;
    const covered = Math.max(0, innerHeight - (view?.height || innerHeight) - (view?.offsetTop || 0));
    document.body.style.setProperty('--sheet-covered-bottom', `${covered}px`);
  };
  visualViewport?.addEventListener('resize', fitVisibleViewport);
  visualViewport?.addEventListener('scroll', fitVisibleViewport);
  addEventListener('resize', fitVisibleViewport);
  fitVisibleViewport();
  const menu = document.querySelector('#quick-menu');
  if (menu) {
    const routes = [
      ['food', '/app?section=nutrition&quick_add=food'],
      ['water', '/app?section=nutrition&hydration=quick'],
      ['cardio', '/app?section=today&cardio=1'],
      ['measurement', '/app?section=progress&focus=measurements'],
      ['wellbeing', '/app?section=today&wellbeing=1'],
    ];
    const rows = [...menu.querySelectorAll('.quick-action')];
    rows.forEach((item, index) => {
      item.dataset.kind = routes[index][0];
      item.dataset.appRoute = routes[index][1];
      item.tabIndex = 0;
      const icon = item.querySelector('svg');
      const holder = document.createElement('span');
      holder.className = 'quick-row-icon';
      holder.setAttribute('aria-hidden', 'true');
      icon.replaceWith(holder);
      holder.append(icon);
      // Same chevron glyph already used in B's progress navigation.
      item.insertAdjacentHTML('beforeend', svg('<path d="m10 6 6 6-6 6"/>').replace('<svg ', '<svg class="quick-row-chevron" '));
      if (item.dataset.kind === 'water') item.href = `quick-add-water.html?capture=1&screen=nutrition&theme=${theme}&hydration=quick`;
    });
    menu.querySelector('nav').replaceChildren(...rows);
    menu.setAttribute('aria-modal', 'true');
  }
} else {
  document.body.classList.add('menu-review');
  const height = document.getElementById('height');
  height.value = params.get('height') || '844';
  const sizeFrame = () => {
    document.getElementById('preview-b').style.height = `${height.value}px`;
    const url = new URL(location.href);
    url.searchParams.set('height', height.value);
    history.replaceState(null, '', url);
  };
  height.addEventListener('change', sizeFrame);
  sizeFrame();
}
