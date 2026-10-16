import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const output = join(root, 'screenshots');
mkdirSync(output, { recursive: true });

const widths = [320, 360, 393, 430, 1280];
const themes = ['dark', 'light'];
const states = ['countdown', 'overtime'];

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
  const panelY = mobile ? 56 : 58;
  const panelHeight = mobile ? 226 : 178;
  const innerX = panelX + 14;
  const timeWidth = mobile ? 78 : 86;
  const nextX = innerX + timeWidth + 16;
  const finishWidth = mobile ? panelWidth - 28 : 138;
  const finishX = mobile ? innerX : panelX + panelWidth - finishWidth - 14;
  const finishY = mobile ? panelY + 98 : panelY + 12;
  const actionsY = mobile ? panelY + 154 : panelY + 112;
  const actionGap = 8;
  const actionWidth = (panelWidth - 28 - actionGap * 2) / 3;
  const cardY = panelY + panelHeight + 22;
  const navY = height - 72;
  const countdown = state === 'overtime' ? '0:00' : '0:48';
  const fact = state === 'overtime' ? 'Факт 2:14' : 'Факт 0:42';
  const title = state === 'overtime' ? 'План завершён' : 'Далее: Тяга верхнего блока';
  const titleY = state === 'overtime' ? panelY + 40 : panelY + 50;
  const nextExerciseY = state === 'overtime' ? panelY + 64 : panelY + 68;
  const nextPositionY = state === 'overtime' ? panelY + 82 : panelY + 85;

  const nav = ['Тренировка', 'Прогресс', 'Питание', 'Библиотека', 'Профиль'];
  const navWidth = width < 681 ? width : Math.min(900, width - 40);
  const navX = width < 681 ? 0 : Math.round((width - navWidth) / 2);
  const navCell = navWidth / nav.length;

  let svg = `<?xml version="1.0" encoding="UTF-8"?>\n`;
  svg += `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title desc">`;
  svg += `<title id="title">Issue #960 ${theme} ${state} baseline-preserving RestTimer mockup</title>`;
  svg += `<desc id="desc">Действующий RestTimer с обратным счётчиком ${countdown}, фактическим временем ${fact}, кнопкой Завершить отдых и существующими действиями плюс тридцать, плюс шестьдесят и Пропустить.</desc>`;
  svg += `<rect width="${width}" height="${height}" fill="${c.page}"/>`;
  svg += `<rect x="0" y="0" width="${width}" height="${panelY - 14}" fill="${c.surface}"/>`;
  svg += text(panelX, 26, 'ТЕКУЩАЯ ТРЕНИРОВКА', c.muted, 10, 800);
  svg += text(panelX, 45, 'Отдых между подходами', c.text, 17, 700);
  svg += rounded(panelX, panelY, panelWidth, panelHeight, c.panel, c.edge, 12);
  svg += text(innerX, panelY + 27, 'ОТДЫХ', c.text, 10, 800);
  svg += text(innerX, panelY + 53, countdown, c.text, 24, 750);
  svg += text(innerX, panelY + 77, fact, c.muted, 12, 600);
  if (state === 'overtime') svg += text(nextX, panelY + 23, 'ПЛАН ЗАВЕРШЁН', c.lime, 10, 800);
  svg += text(nextX, titleY, title, c.text, 12, 650);
  if (state === 'overtime') svg += text(nextX, nextExerciseY, 'Далее: Тяга верхнего блока', c.text, 11, 600);
  svg += text(nextX, nextPositionY, '2-й подход', c.muted, 11, 400);
  svg += rounded(finishX, finishY, finishWidth, 44, c.limeSoft, c.lime, 9);
  svg += text(finishX + finishWidth / 2, finishY + 27, 'Завершить отдых', c.lime, 12, 750, 'middle');
  const actions = ['+30 сек', '+60 сек', 'Пропустить'];
  for (let i = 0; i < actions.length; i += 1) {
    const x = innerX + i * (actionWidth + actionGap);
    svg += rounded(x, actionsY, actionWidth, 44, 'none', c.edge, 9);
    svg += text(x + actionWidth / 2, actionsY + 27, actions[i], c.text, 11, 700, 'middle');
  }
  svg += rounded(panelX, cardY, panelWidth, mobile ? 210 : 260, c.card, c.edge, 12);
  svg += text(innerX, cardY + 28, 'СЛЕДУЮЩИЙ ПОДХОД', c.muted, 10, 800);
  svg += text(innerX, cardY + 52, 'Тяга верхнего блока', c.text, 16, 700);
  svg += text(innerX, cardY + 74, '3 × 10 · 42 кг · RIR 2', c.muted, 12, 400);
  svg += `<line x1="${innerX}" y1="${cardY + 105}" x2="${panelX + panelWidth - 14}" y2="${cardY + 105}" stroke="${c.edge}"/>`;
  svg += text(innerX, cardY + 132, 'Вес', c.muted, 11, 400);
  svg += text(panelX + panelWidth / 2 - 10, cardY + 132, '42 кг', c.text, 12, 700, 'end');
  svg += text(panelX + panelWidth / 2 + 20, cardY + 132, 'Повторы', c.muted, 11, 400);
  svg += text(panelX + panelWidth - 14, cardY + 132, '10', c.text, 12, 700, 'end');
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

console.log(`generated ${widths.length * themes.length * states.length} SVG mockups in ${output}`);
