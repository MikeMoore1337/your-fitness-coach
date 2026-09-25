const params = new URLSearchParams(window.location.search);
const app = document.querySelector(".prototype-app");

const state = {
  role: params.get("role") === "client" ? "client" : "trainer",
  workspace: params.get("workspace") === "personal" ? "personal" : "work",
  screen: params.get("screen") || "today",
  direction: ["command", "radar", "stage"].includes(params.get("direction"))
    ? params.get("direction")
    : "command",
  theme: params.get("theme") === "dark" ? "dark" : "light",
};

const catalog = [
  {
    title: "Тяга верхнего блока",
    meta: "Спина · тренажёр · сила",
    tag: "Техника проверена",
  },
  {
    title: "Жим ногами",
    meta: "Ноги · plate-loaded · сила",
    tag: "2 варианта",
  },
  { title: "Гоблет-присед", meta: "Ноги · гиря · сила", tag: "Популярное" },
  {
    title: "Тяга гантели в наклоне",
    meta: "Спина · гантель · сила",
    tag: "Избранное",
  },
];

const directionCopy = {
  command: {
    label: "Command Stack",
    title: "Сначала действие. Затем детали.",
    body: "Компактный рабочий стол для следующего полезного шага тренера.",
  },
  radar: {
    label: "Client Radar",
    title: "Вся команда — в одном радаре.",
    body: "Внимание, состояние и следующий контакт собраны вокруг клиентов.",
  },
  stage: {
    label: "Exercise Stage",
    title: "Упражнение как понятная сцена.",
    body: "Каталог, техника и активная тренировка связаны одной иерархией.",
  },
};

function setState(key, value) {
  state[key] = value;
  if (state.role === "client") state.workspace = "personal";
  if (state.role === "client" && state.screen === "clients")
    state.screen = "today";
  const next = new URLSearchParams({
    role: state.role,
    workspace: state.workspace,
    screen: state.screen,
    direction: state.direction,
    theme: state.theme,
  });
  history.replaceState(null, "", `${window.location.pathname}?${next}`);
  render();
}

function button(label, attrs = "") {
  return `<button type="button" ${attrs}>${label}</button>`;
}

function contextControls() {
  const workspace = state.role === "client" ? "personal" : state.workspace;
  return `
    <section class="context-card glass-card" aria-labelledby="context-title">
      <div class="context-card__heading">
        <span class="eyebrow">Контекст просмотра</span>
        <h2 id="context-title">${state.role === "trainer" ? "Тренерский аккаунт" : "Клиентский аккаунт"}</h2>
      </div>
      <div class="segmented" role="group" aria-label="Роль в прототипе">
        ${button("Тренер", `class="${state.role === "trainer" ? "is-active" : ""}" data-action="role" data-value="trainer" aria-pressed="${state.role === "trainer"}"`)}
        ${button("Клиент", `class="${state.role === "client" ? "is-active" : ""}" data-action="role" data-value="client" aria-pressed="${state.role === "client"}"`)}
      </div>
      ${
        state.role === "trainer"
          ? `
        <div class="workspace-switch" role="group" aria-label="Рабочий контекст">
          ${button("Work · Тренер", `class="${workspace === "work" ? "is-active" : ""}" data-action="workspace" data-value="work" aria-pressed="${workspace === "work"}"`)}
          ${button("Personal · Для себя", `class="${workspace === "personal" ? "is-active" : ""}" data-action="workspace" data-value="personal" aria-pressed="${workspace === "personal"}"`)}
        </div>
        <p class="microcopy">Меняется навигационный контекст, не identity, authz или ownership.</p>
      `
          : '<p class="microcopy">Рабочий переключатель не показывается клиентскому аккаунту.</p>'
      }
    </section>
  `;
}

function directionControls() {
  return `
    <section class="direction-picker" aria-labelledby="direction-title">
      <div>
        <span class="eyebrow">Три изолированных направления</span>
        <h2 id="direction-title">${directionCopy[state.direction].label}</h2>
      </div>
      <div class="direction-buttons" role="group" aria-label="Визуальное направление">
        ${button("Command Stack", `class="${state.direction === "command" ? "is-active" : ""}" data-action="direction" data-value="command" aria-pressed="${state.direction === "command"}"`)}
        ${button("Client Radar", `class="${state.direction === "radar" ? "is-active" : ""}" data-action="direction" data-value="radar" aria-pressed="${state.direction === "radar"}"`)}
        ${button("Exercise Stage", `class="${state.direction === "stage" ? "is-active" : ""}" data-action="direction" data-value="stage" aria-pressed="${state.direction === "stage"}"`)}
      </div>
    </section>
  `;
}

function navItems() {
  const items = [
    ["today", "Сегодня", "01"],
    ...(state.role === "trainer" ? [["clients", "Клиенты", "02"]] : []),
    ["personal", state.role === "trainer" ? "Для себя" : "Мой план", "03"],
    ["catalog", "Каталог", "04"],
    ["workout", "Тренировка", "05"],
  ];
  return items;
}

function navigation(markupClass) {
  return navItems()
    .map(([screen, label, index]) => {
      const active =
        state.screen === screen ||
        (screen === "today" && state.screen === "detail");
      return button(
        `<span class="nav-index">${index}</span><span>${label}</span>`,
        `class="${markupClass}__item ${active ? "is-active" : ""}" data-action="screen" data-value="${screen}" aria-current="${active ? "page" : "false"}"`,
      );
    })
    .join("");
}

function renderRail() {
  document.querySelector("#railContext").innerHTML = contextControls();
  document.querySelector("#railNav").innerHTML =
    `<div class="nav-label">Навигация</div>${navigation("rail-nav")}`;
  document.querySelector("#mobileNav").innerHTML = navigation("mobile-nav");
}

function mediaSlot(label = "Будущее media") {
  return `<div class="media-slot" role="img" aria-label="${label}: сейчас только layout-slot, без нового asset">
    <span class="media-slot__grid" aria-hidden="true"></span>
    <strong>${label}</strong>
    <small>Только существующий verified asset на следующем этапе</small>
  </div>`;
}

function directionPanel() {
  const copy = directionCopy[state.direction];
  return `<div class="direction-panel direction-panel--${state.direction}">
    <span class="eyebrow">${copy.label}</span>
    <h2>${copy.title}</h2>
    <p>${copy.body}</p>
    <div class="direction-signal"><span></span><span></span><span></span><b>next useful action</b></div>
  </div>`;
}

function trainerToday() {
  return `
    ${directionPanel()}
    <div class="page-heading">
      <div>
        <span class="eyebrow">Work · тренерский workspace</span>
        <h1>Сегодня</h1>
        <p>Доброе утро, Алексей. Здесь начинается следующий полезный контакт.</p>
      </div>
      <div class="heading-actions">${button("Пригласить клиента", 'class="primary" data-action="notice"')}</div>
    </div>
    <section class="stat-grid" aria-label="Сводка тренера">
      <article class="metric-card"><span>Нужно внимания</span><strong>03</strong><small>2 check-in · 1 пропуск</small></article>
      <article class="metric-card metric-card--accent"><span>Активные клиенты</span><strong>12</strong><small>+2 за последние 7 дней</small></article>
      <article class="metric-card"><span>Сегодня в плане</span><strong>08</strong><small>4 тренировки · 4 follow-up</small></article>
    </section>
    <section class="split-grid">
      <article class="surface-card attention-card">
        <div class="card-heading"><div><span class="eyebrow">Приоритет</span><h2>Что требует действия</h2></div><span class="live-pill">сейчас</span></div>
        <div class="attention-row"><span class="avatar avatar--lime">М</span><div><strong>Мария · check-in</strong><small>Не отметила самочувствие 2 дня</small></div><button class="round-action" data-action="screen" data-value="clients" aria-label="Открыть Марию">→</button></div>
        <div class="attention-row"><span class="avatar avatar--dark">И</span><div><strong>Иван · тренировка</strong><small>Результат ждёт комментария</small></div><button class="round-action" data-action="screen" data-value="clients" aria-label="Открыть Ивана">→</button></div>
        <div class="attention-row"><span class="avatar">А</span><div><strong>Анна · программа</strong><small>Новый микроцикл готов к review</small></div><button class="round-action" data-action="screen" data-value="clients" aria-label="Открыть Анну">→</button></div>
      </article>
      <article class="surface-card quick-card">
        <div class="card-heading"><div><span class="eyebrow">Быстрый доступ</span><h2>Следующий шаг</h2></div><span class="step-number">01</span></div>
        <p>Откройте клиента, проверьте контекст и оставьте короткое действие.</p>
        <div class="quick-actions">${button("Открыть клиентов", 'class="primary" data-action="screen" data-value="clients"')}${button("Найти упражнение", 'class="secondary" data-action="screen" data-value="catalog"')}</div>
      </article>
    </section>
  `;
}

function personalHome(isClient = false) {
  return `
    <div class="page-heading">
      <div>
        <span class="eyebrow">${isClient ? "Клиентский аккаунт" : "Personal · для себя"}</span>
        <h1>${isClient ? "Твой сегодняшний фокус" : "Сегодня для себя"}</h1>
        <p>${isClient ? "Без тренерских инструментов — только твоя тренировка и восстановление." : "Личный контекст остаётся рядом, но не смешивается с работой тренера."}</p>
      </div>
      <div class="progress-ring" aria-label="Прогресс недели 68 процентов"><strong>68%</strong><small>неделя</small></div>
    </div>
    <section class="personal-hero surface-card">
      <div><span class="eyebrow">Сегодня · вторник</span><h2>Сила и устойчивость</h2><p>45 мин · 6 упражнений · умеренная нагрузка</p></div>
      <div class="hero-actions">${button("Начать тренировку", 'class="primary" data-action="screen" data-value="workout"')}${button("Открыть план", 'class="secondary" data-action="screen" data-value="personal"')}</div>
    </section>
    <section class="split-grid">
      <article class="surface-card"><div class="card-heading"><div><span class="eyebrow">Питание</span><h2>Дневной ритм</h2></div><strong class="value-highlight">72%</strong></div><div class="progress-bar"><span style="width:72%"></span></div><p class="muted">Белок и вода отмечены, ужин ещё впереди.</p></article>
      <article class="surface-card"><div class="card-heading"><div><span class="eyebrow">Восстановление</span><h2>Самочувствие</h2></div><span class="state-label">хорошо</span></div><p class="large-note">«Готов к спокойной прогрессии»</p><button class="text-action" data-action="notice">Обновить check-in →</button></article>
    </section>
  `;
}

function clientsView() {
  return `
    <div class="page-heading"><div><span class="eyebrow">Work · 12 активных связей</span><h1>Клиенты</h1><p>Список — для выбора контекста, не для смешения данных.</p></div>${button("Пригласить", 'class="primary" data-action="notice"')}</div>
    <div class="search-line"><label for="clientSearch">Поиск клиента</label><input id="clientSearch" type="search" placeholder="Имя или статус" /></div>
    <section class="client-list" aria-label="Клиенты тренера">
      ${[
        ["Мария", "Нужен check-in", "Пропуск 2 дня", "attention"],
        ["Иван", "Результат готов", "Комментарий тренера", "ready"],
        ["Анна", "Программа на review", "Сила и устойчивость", "plan"],
        ["Борис", "Стабильный ритм", "Следующая тренировка завтра", "steady"],
      ]
        .map(
          ([name, status, detail, kind], index) =>
            `<article class="client-row" data-client-name="${name.toLowerCase()}"><span class="avatar avatar--${kind}">${name[0]}</span><div class="client-row__main"><strong>${name}</strong><span>${status}</span><small>${detail}</small></div><span class="client-state client-state--${kind}">${String(index + 1).padStart(2, "0")}</span><button class="round-action" data-action="notice" aria-label="Открыть клиента ${name}">→</button></article>`,
        )
        .join("")}
    </section>
  `;
}

function catalogView() {
  return `
    <div class="page-heading"><div><span class="eyebrow">Global catalog · 182 stored rows</span><h1>Упражнения</h1><p>Поиск по canonical названию и контексту. Media открывается по intent.</p></div>${button("Добавить в тренировку", 'class="secondary" data-action="screen" data-value="workout"')}</div>
    <div class="search-line"><label for="catalogSearch">Поиск упражнения</label><input id="catalogSearch" type="search" placeholder="Например, тяга или жим" /></div>
    <div class="catalog-list" id="catalogList">
      ${catalog.map((item, index) => `<button class="catalog-row" type="button" data-catalog-title="${item.title.toLowerCase()}" data-action="screen" data-value="detail"><span class="catalog-index">0${index + 1}</span><span class="catalog-row__copy"><strong>${item.title}</strong><small>${item.meta}</small></span><span class="catalog-tag">${item.tag}</span><span aria-hidden="true">↗</span></button>`).join("")}
    </div>
    <p class="boundary-note"><strong>Stage 0:</strong> здесь только placement и hierarchy. Не добавляются новые assets, pipeline или media migration.</p>
  `;
}

function detailView() {
  return `
    <div class="back-line">${button("← Каталог", 'class="text-action" data-action="screen" data-value="catalog"')}</div>
    <div class="detail-layout"><section>${mediaSlot("Media slot · Тяга верхнего блока")}</section><section class="detail-copy"><span class="eyebrow">Упражнение · карточка</span><h1>Тяга верхнего блока</h1><p class="lead">Контролируемая тяга к верхней части груди с нейтральным положением корпуса.</p><div class="tag-cloud"><span>спина</span><span>тренажёр</span><span>сила</span><span>средний уровень</span></div><div class="detail-actions">${button("Добавить в тренировку", 'class="primary" data-action="screen" data-value="workout"')}${button("Сохранить", 'class="secondary" data-action="notice"')}</div><div class="technique-list"><div><b>01</b><span><strong>Подготовка</strong><small>Зафиксируйте таз и выберите удобный хват.</small></span></div><div><b>02</b><span><strong>Рабочая фаза</strong><small>Тяните локти вниз, не раскачивая корпус.</small></span></div><div><b>03</b><span><strong>Возврат</strong><small>Плавно верните рукоять под контролем.</small></span></div></div></section></div>
  `;
}

function workoutView() {
  return `
    <div class="page-heading"><div><span class="eyebrow">Активная тренировка · 02 из 06</span><h1>Сила и устойчивость</h1><p>Иерархия: блок → упражнение → подход → действие.</p></div><span class="timer">24:18</span></div>
    <section class="workout-progress"><span><b>Выполнено</b><small>1 240 кг объёма</small></span><div class="progress-bar"><span style="width:34%"></span></div><strong>34%</strong></section>
    <section class="workout-stack">
      <article class="workout-block"><header><div><span class="eyebrow">Блок A · тяга</span><h2>Спина и контроль</h2></div><span class="state-label">в работе</span></header><div class="exercise-row exercise-row--active"><div class="exercise-thumb">01</div><div class="exercise-copy"><strong>Тяга верхнего блока</strong><small>3 подхода · 10 повторений · 42 кг</small></div><span class="exercise-state">2/3</span></div><div class="set-grid"><span>Подход</span><span>Вес</span><span>Повт.</span><span>Статус</span><b>01</b><span>40 кг</span><span>10</span><span class="set-done">готово</span><b>02</b><span>42 кг</span><span>10</span><span class="set-done">готово</span><b>03</b><span>42 кг</span><span>—</span><button class="set-next" data-action="notice">Записать</button></div></article>
      <article class="workout-block workout-block--muted"><header><div><span class="eyebrow">Блок B · ноги</span><h2>Жим ногами</h2></div><span class="state-label">далее</span></header><div class="exercise-row"><div class="exercise-thumb">02</div><div class="exercise-copy"><strong>Жим ногами</strong><small>4 подхода · 8 повторений · цель 110 кг</small></div><span class="exercise-state">—</span></div></article>
    </section>
    <div class="sticky-action">${button("Завершить подход", 'class="primary" data-action="notice"')}${button("Пауза", 'class="secondary" data-action="notice"')}</div>
  `;
}

function renderMain() {
  let content;
  if (
    state.screen === "clients" &&
    state.role === "trainer" &&
    state.workspace === "work"
  )
    content = clientsView();
  else if (state.screen === "personal" || state.role === "client")
    content = personalHome(state.role === "client");
  else if (state.screen === "catalog") content = catalogView();
  else if (state.screen === "detail") content = detailView();
  else if (state.screen === "workout") content = workoutView();
  else if (state.workspace === "personal") content = personalHome();
  else content = trainerToday();

  document.querySelector("#mainContent").innerHTML = `
    <div class="main-toolbar">
      <span class="toolbar-context"><span class="status-dot" aria-hidden="true"></span>${state.role === "trainer" ? (state.workspace === "work" ? "Work · тренер" : "Personal · для себя") : "Client · для себя"}</span>
      <span class="toolbar-note">Stage 0 · данные только для просмотра</span>
    </div>
    ${content}
    <footer class="prototype-footer"><span>Прототип не подключён к API</span><span>Без новых media · без production writes</span></footer>
  `;
}

function bindInteractions() {
  document.querySelectorAll("[data-action]").forEach((element) => {
    element.addEventListener("click", () => {
      const action = element.dataset.action;
      const value = element.dataset.value;
      if (action === "screen") setState("screen", value);
      if (action === "role") setState("role", value);
      if (action === "workspace") setState("workspace", value);
      if (action === "direction") setState("direction", value);
      if (action === "notice")
        window.alert(
          "Stage 0: действие только визуализировано, данные не записываются.",
        );
    });
  });
  document
    .querySelector("#themeToggle")
    .addEventListener("click", () =>
      setState("theme", state.theme === "light" ? "dark" : "light"),
    );
  const catalogSearch = document.querySelector("#catalogSearch");
  if (catalogSearch) {
    catalogSearch.addEventListener("input", () => {
      const query = catalogSearch.value.trim().toLowerCase();
      document.querySelectorAll("[data-catalog-title]").forEach((item) => {
        item.hidden =
          Boolean(query) && !item.dataset.catalogTitle.includes(query);
      });
    });
  }
  const clientSearch = document.querySelector("#clientSearch");
  if (clientSearch) {
    clientSearch.addEventListener("input", () => {
      const query = clientSearch.value.trim().toLowerCase();
      document.querySelectorAll("[data-client-name]").forEach((item) => {
        item.hidden =
          Boolean(query) && !item.dataset.clientName.includes(query);
      });
    });
  }
}

function render() {
  document.body.dataset.theme = state.theme;
  app.dataset.direction = state.direction;
  app.dataset.theme = state.theme;
  renderRail();
  renderMain();
  bindInteractions();
}

render();
