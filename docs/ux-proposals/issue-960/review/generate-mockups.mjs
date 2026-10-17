import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const output = join(root, 'screenshots');
mkdirSync(output, { recursive: true });

const widths = [320, 360, 393, 430, 1280];
const themes = ['dark', 'light'];
const states = ['countdown', 'overtime', 'completed'];

const assert = (condition, message) => {
  if (!condition) throw new Error(`mockup geometry: ${message}`);
};

const palette = {
  dark: {
    page: '#090b0b',
    surface: '#111512',
    panel: '#1a1f1b',
    card: '#151a16',
    text: '#f4f6f2',
    muted: '#a9b0aa',
    edge: '#424b44',
    lime: '#b2f520',
    limeSoft: '#293719',
  },
  light: {
    page: '#edf0eb',
    surface: '#f7f9f5',
    panel: '#ffffff',
    card: '#ffffff',
    text: '#171b18',
    muted: '#59615b',
    edge: '#c9d0c9',
    lime: '#486414',
    limeSoft: '#e9f4cf',
  },
};

const escapeXml = (value) =>
  String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');

const text = (x, y, value, fill, size, weight = 400, anchor = 'start') =>
  `<text x="${x}" y="${y}" fill="${fill}" font-family="Inter,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}">${escapeXml(value)}</text>`;

const rounded = (x, y, width, height, fill, stroke, radius = 9) =>
  `<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="${radius}" fill="${fill}" stroke="${stroke}"/>`;

function render(width, theme, state) {
  const c = palette[theme];
  const mobile = width < 681;
  const height = mobile ? 760 : 720;
  const panelWidth = mobile ? width - 16 : 680;
  const panelX = mobile ? 8 : Math.round((width - panelWidth) / 2);
  const panelY = 58;
  const completed = state === 'completed';
  const panelHeight = completed ? 62 : mobile ? 110 : 64;
  const innerX = panelX + 10;
  const innerRight = panelX + panelWidth - 10;
  const timeWidth = mobile ? 52 : 58;
  const nextX = innerX + timeWidth + 12;
  const actualWidth = 83;
  const actionGap = 8;
  const actionWidth = mobile ? (panelWidth - 20 - actionGap * 2) / 3 : 88;
  const actionTotal = actionWidth * 3 + actionGap * 2;
  const actionsX = mobile ? innerX : innerRight - actionTotal;
  const nextRight = mobile ? innerRight : actionsX - 12;
  const nextWidth = nextRight - nextX;
  const actualX = nextRight - actualWidth;
  const actualCopyWidth = 33;
  const stopX = actualX + actualCopyWidth + 6;
  const rowY = panelY + (mobile ? 8 : 10);
  const actionsY = mobile ? rowY + 44 + 4 : rowY;
  const cardY = panelY + panelHeight + 22;
  const navY = height - 72;
  const cardHeight = mobile ? 210 : 260;
  const copyWidth = nextWidth - actualWidth - 6;

  assert(panelX >= 0 && panelX + panelWidth <= width, `${width}px panel exceeds viewport`);
  if (!completed) {
    assert(nextWidth > actualWidth + 70, `${width}px next copy cannot coexist with actual cluster`);
    assert(stopX + 44 <= nextRight, `${width}px stop action exceeds next block`);
    assert(actionWidth >= 44, `${width}px existing action target is too small`);
    assert(
      actionsY + 44 <= panelY + panelHeight - (mobile ? 8 : 10),
      `${width}px action row exceeds panel`,
    );
  }
  assert(cardY + cardHeight < navY, `${width}px exercise card overlaps bottom navigation`);

  const countdown = state === 'overtime' ? '0:00' : '0:48';
  const fact = state === 'overtime' ? '2:14' : '0:42';
  const clipId = `next-copy-${width}-${theme}-${state}`;
  const nav = ['Тренировка', 'Прогресс', 'Питание', 'Библиотека', 'Профиль'];
  const navWidth = mobile ? width : Math.min(900, width - 40);
  const navX = mobile ? 0 : Math.round((width - navWidth) / 2);
  const navCell = navWidth / nav.length;

  let svg = `<?xml version="1.0" encoding="UTF-8"?>\n`;
  svg += `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title desc">`;
  svg += `<title id="title">Issue #960 ${theme} ${state} baseline-preserving RestTimer mockup</title>`;
  svg += `<desc id="desc">Действующий RestTimer: плановый обратный счётчик слева, контекст Далее, фактически измеренный интервал и компактное действие Стоп справа, существующие действия плюс тридцать, плюс шестьдесят и Пропустить в текущем ряду.</desc>`;
  svg += `<defs><clipPath id="${clipId}"><rect x="${nextX}" y="${rowY}" width="${copyWidth}" height="44"/></clipPath></defs>`;
  svg += `<rect width="${width}" height="${height}" fill="${c.page}"/>`;
  svg += `<rect x="0" y="0" width="${width}" height="${panelY - 14}" fill="${c.surface}"/>`;
  svg += text(panelX, 26, 'ТЕКУЩАЯ ТРЕНИРОВКА', c.muted, 10, 800);
  svg += text(panelX, 45, 'Отдых между подходами', c.text, 17, 700);
  svg += rounded(panelX, panelY, panelWidth, panelHeight, c.panel, c.edge, 12);
  if (completed) {
    const hideWidth = 54;
    const hideX = innerRight - hideWidth;
    svg += text(innerX, rowY + 27, 'Отдых завершён · факт 0:42', c.text, 11, 750);
    svg += rounded(hideX, rowY, hideWidth, 44, 'none', c.edge, 9);
    svg += text(hideX + hideWidth / 2, rowY + 27, 'Скрыть', c.text, 10, 750, 'middle');
  } else {
    svg += text(innerX, rowY + 17, 'ОТДЫХ', c.text, 10, 800);
    svg += text(innerX, rowY + 39, countdown, c.text, 24, 750);

    if (state === 'overtime') svg += text(nextX, rowY + 12, 'ПЛАН ЗАВЕРШЁН', c.lime, 9, 800);
    const titleY = state === 'overtime' ? rowY + 27 : rowY + 25;
    const positionY = state === 'overtime' ? rowY + 41 : rowY + 40;
    svg += `<g clip-path="url(#${clipId})">`;
    svg += text(nextX, titleY, 'Далее: Тяга верхнего блока — повторный тяжёлый подход', c.text, 11, 650);
    svg += text(nextX, positionY, '2-й подход', c.muted, 11, 400);
    svg += '</g>';

    svg += text(actualX + actualCopyWidth, rowY + 16, 'ФАКТ', c.muted, 8, 800, 'end');
    svg += text(actualX + actualCopyWidth, rowY + 34, fact, c.text, 13, 750, 'end');
    svg += rounded(stopX, rowY, 44, 44, state === 'overtime' ? c.limeSoft : 'none', state === 'overtime' ? c.lime : c.edge, 9);
    svg += text(stopX + 22, rowY + 27, 'Стоп', state === 'overtime' ? c.lime : c.text, 10, 750, 'middle');

    const actions = ['+30 сек', '+60 сек', 'Пропустить'];
    for (let i = 0; i < actions.length; i += 1) {
      const x = actionsX + i * (actionWidth + actionGap);
      svg += rounded(x, actionsY, actionWidth, 44, 'none', c.edge, 9);
      svg += text(x + actionWidth / 2, actionsY + 27, actions[i], c.text, 11, 700, 'middle');
    }
  }

  svg += rounded(panelX, cardY, panelWidth, cardHeight, c.card, c.edge, 12);
  svg += text(innerX, cardY + 28, 'СЛЕДУЮЩИЙ ПОДХОД', c.muted, 10, 800);
  svg += text(innerX, cardY + 52, 'Тяга верхнего блока', c.text, 16, 700);
  svg += text(innerX, cardY + 74, '3 × 10 · 42 кг · RIR 2', c.muted, 12, 400);
  svg += `<line x1="${innerX}" y1="${cardY + 105}" x2="${panelX + panelWidth - 10}" y2="${cardY + 105}" stroke="${c.edge}"/>`;
  svg += text(innerX, cardY + 132, 'Вес', c.muted, 11, 400);
  svg += text(panelX + panelWidth / 2 - 10, cardY + 132, '42 кг', c.text, 12, 700, 'end');
  svg += text(panelX + panelWidth / 2 + 20, cardY + 132, 'Повторы', c.muted, 11, 400);
  svg += text(panelX + panelWidth - 10, cardY + 132, '10', c.text, 12, 700, 'end');
  svg += text(innerX, cardY + 178, 'Следующий подход начинается отдельным действием пользователя.', c.muted, 10, 400);
  svg += rounded(navX, navY, navWidth, 72, c.panel, c.edge, 12);
  for (let i = 0; i < nav.length; i += 1) {
    const center = navX + navCell * i + navCell / 2;
    if (i === 0) svg += rounded(navX + navCell * i + 4, navY + 10, navCell - 8, 48, c.limeSoft, 'none', 9);
    svg += text(center, navY + 39, nav[i], i === 0 ? c.lime : c.muted, 9, i === 0 ? 800 : 500, 'middle');
  }
  svg += '</svg>\n';
  return svg;
}

for (const width of widths) {
  for (const theme of themes) {
    for (const state of states) {
      const file = join(output, `${width}-${theme}-${state}.svg`);
      writeFileSync(file, render(width, theme, state), 'utf8');
    }
  }
}

console.log(`generated ${widths.length * themes.length * states.length} baseline-preserving SVG mockups in ${output}`);
