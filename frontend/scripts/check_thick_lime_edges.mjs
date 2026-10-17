import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const MIN_THICKNESS_PX = 3;

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, '../..');
const SOURCE_EXTENSIONS = new Set([
  '.css',
  '.less',
  '.pcss',
  '.sass',
  '.scss',
  '.js',
  '.jsx',
  '.mjs',
  '.ts',
  '.tsx',
]);
const LIME_VALUE_RE =
  /(?:var\(\s*--[^)]*(?:lime|accent|brand-lime|weekly-review-lime)[^)]*\)|--(?:[^,\s)]*lime|[^,\s)]*accent|brand-lime|weekly-review-lime)\b|#(?:b2f520|b6f238|98d62f|a7e52d|99d522|6b8f20|79a71c)\b)/i;
const ALLOWED_CONTEXT_RE =
  /(?:\b(?:active|selected|selection|current|focus|focused|focus-visible|pressed|checked|cta|call-to-action|primary-action)\b|:(?:focus|focus-visible|active|checked)|\[\s*aria-(?:current|selected|pressed|checked))/i;

const SIDE_PROPERTIES = new Map([
  ['border-left', 'left'],
  ['border-right', 'right'],
  ['border-top', 'top'],
  ['border-bottom', 'bottom'],
  ['border-inline-start', 'inline-start'],
  ['border-inline-end', 'inline-end'],
  ['border-block-start', 'block-start'],
  ['border-block-end', 'block-end'],
]);
const SIDE_WIDTH_PROPERTIES = new Map([
  ['border-left-width', 'left'],
  ['border-right-width', 'right'],
  ['border-top-width', 'top'],
  ['border-bottom-width', 'bottom'],
  ['border-inline-start-width', 'inline-start'],
  ['border-inline-end-width', 'inline-end'],
  ['border-block-start-width', 'block-start'],
  ['border-block-end-width', 'block-end'],
]);
const SIDE_COLOR_PROPERTIES = new Map([
  ['border-left-color', 'left'],
  ['border-right-color', 'right'],
  ['border-top-color', 'top'],
  ['border-bottom-color', 'bottom'],
  ['border-inline-start-color', 'inline-start'],
  ['border-inline-end-color', 'inline-end'],
  ['border-block-start-color', 'block-start'],
  ['border-block-end-color', 'block-end'],
]);

function preserveLineNumbers(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\r\n]/g, ' '));
}

function lineNumber(text, index, lineOffset = 0) {
  return lineOffset + text.slice(0, index).split(/\r?\n/).length;
}

function isAllowedContext(context) {
  return ALLOWED_CONTEXT_RE.test(context);
}

function splitTopLevel(value, separator = ',') {
  const parts = [];
  let start = 0;
  let depth = 0;
  let quote = null;

  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];
    if (quote) {
      if (character === quote && value[index - 1] !== '\\') {
        quote = null;
      }
      continue;
    }
    if (character === "'" || character === '"') {
      quote = character;
      continue;
    }
    if (character === '(') {
      depth += 1;
    } else if (character === ')') {
      depth = Math.max(0, depth - 1);
    } else if (character === separator && depth === 0) {
      parts.push(value.slice(start, index));
      start = index + 1;
    }
  }
  parts.push(value.slice(start));
  return parts;
}

function extractBlocks(text) {
  const cleaned = preserveLineNumbers(text);
  const stack = [];
  const blocks = [];
  let quote = null;

  for (let index = 0; index < cleaned.length; index += 1) {
    const character = cleaned[index];
    if (quote) {
      if (character === quote && cleaned[index - 1] !== '\\') {
        quote = null;
      }
      continue;
    }
    if (character === "'" || character === '"') {
      quote = character;
      continue;
    }
    if (character === '{') {
      let headerStart = index - 1;
      while (headerStart >= 0 && !/[{};]/.test(cleaned[headerStart])) {
        headerStart -= 1;
      }
      stack.push({
        open: index,
        selector: cleaned.slice(headerStart + 1, index).trim(),
      });
    } else if (character === '}' && stack.length > 0) {
      const block = stack.pop();
      block.close = index;
      blocks.push(block);
    }
  }
  return { cleaned, blocks };
}

function parseDeclaration(segment, startIndex, text, lineOffset) {
  const colonIndex = segment.indexOf(':');
  if (colonIndex < 0) {
    return null;
  }
  const property = segment.slice(0, colonIndex).trim().toLowerCase();
  if (!/^-{0,2}[a-z][\w-]*$/i.test(property)) {
    return null;
  }
  const value = segment.slice(colonIndex + 1).trim();
  if (!value) {
    return null;
  }
  const propertyOffset = segment.indexOf(property);
  return {
    property,
    value,
    index: startIndex + Math.max(0, propertyOffset),
    line: lineNumber(text, startIndex + Math.max(0, propertyOffset), lineOffset),
  };
}

function extractDeclarations(text, block) {
  const declarations = [];
  let depth = 0;
  let segmentStart = block.open + 1;
  let quote = null;

  for (let index = block.open + 1; index < block.close; index += 1) {
    const character = text[index];
    if (quote) {
      if (character === quote && text[index - 1] !== '\\') {
        quote = null;
      }
      continue;
    }
    if (character === "'" || character === '"') {
      quote = character;
      continue;
    }
    if (character === '{') {
      if (depth === 0) {
        segmentStart = index + 1;
      }
      depth += 1;
    } else if (character === '}') {
      depth = Math.max(0, depth - 1);
      if (depth === 0) {
        segmentStart = index + 1;
      }
    } else if (character === ';' && depth === 0) {
      const declaration = parseDeclaration(text.slice(segmentStart, index), segmentStart, text, 0);
      if (declaration) {
        declarations.push(declaration);
      }
      segmentStart = index + 1;
    }
  }

  const finalDeclaration = parseDeclaration(
    text.slice(segmentStart, block.close),
    segmentStart,
    text,
    0,
  );
  if (finalDeclaration) {
    declarations.push(finalDeclaration);
  }
  return declarations;
}

function expandVariables(value, customProperties) {
  let expanded = value;
  for (let iteration = 0; iteration < 4; iteration += 1) {
    const next = expanded.replace(
      /var\(\s*(--[\w-]+)(?:\s*,\s*([^)]*))?\)/g,
      (full, name, fallback) => customProperties.get(name) ?? fallback ?? full,
    );
    if (next === expanded) {
      break;
    }
    expanded = next;
  }
  return expanded;
}

function numericThickness(value) {
  let maximum = 0;
  for (const match of value.matchAll(/(-?\d+(?:\.\d+)?)\s*(px|rem|em)\b/gi)) {
    const amount = Math.abs(Number(match[1]));
    const multiplier = match[2].toLowerCase() === 'px' ? 1 : 16;
    maximum = Math.max(maximum, amount * multiplier);
  }
  if (/\bmedium\b/i.test(value)) {
    maximum = Math.max(maximum, MIN_THICKNESS_PX);
  }
  if (/\bthick\b/i.test(value)) {
    maximum = Math.max(maximum, 5);
  }
  return maximum;
}

function inlineThickness(value) {
  const parsed = numericThickness(value);
  if (parsed > 0) {
    return parsed;
  }
  const unitless = value.match(/^\s*["']?(\d+(?:\.\d+)?)["']?\s*$/);
  return unitless ? Number(unitless[1]) : 0;
}

function containsLime(value) {
  return LIME_VALUE_RE.test(value);
}

function hasForbiddenInsetShadow(value) {
  return splitTopLevel(value).some((shadow) => {
    if (!/\binset\b/i.test(shadow) || !containsLime(shadow)) {
      return false;
    }
    const withoutFunctions = shadow
      .replace(/var\([^)]*\)/gi, ' ')
      .replace(/rgba?\([^)]*\)/gi, ' ')
      .replace(/#[\da-f]+/gi, ' ');
    const numbers = [...withoutFunctions.matchAll(/-?\d+(?:\.\d+)?/g)].map((match) =>
      Number(match[0]),
    );
    const x = numbers[0] ?? 0;
    const y = numbers[1] ?? 0;
    return (
      (Math.abs(x) >= MIN_THICKNESS_PX && Math.abs(y) < MIN_THICKNESS_PX) ||
      (Math.abs(y) >= MIN_THICKNESS_PX && Math.abs(x) < MIN_THICKNESS_PX)
    );
  });
}

function hasForbiddenGradient(value, hasEdgeSizedBackground) {
  return (
    /gradient\s*\(/i.test(value) &&
    containsLime(value) &&
    (/\d+(?:\.\d+)?\s*px\b/i.test(value) || hasEdgeSizedBackground)
  );
}

function addViolation(violations, violation) {
  const key = [violation.line, violation.kind, violation.selector ?? ''].join(':');
  if (!violations.some((entry) => entry.key === key)) {
    violations.push({ ...violation, key });
  }
}

function analyzeCssText(text, lineOffset = 0) {
  const { cleaned, blocks } = extractBlocks(text);
  const allDeclarations = blocks.flatMap((block) => extractDeclarations(cleaned, block));
  const customProperties = new Map(
    allDeclarations
      .filter((declaration) => declaration.property.startsWith('--'))
      .map((declaration) => [declaration.property, declaration.value]),
  );
  const violations = [];

  for (const block of blocks) {
    const declarations = extractDeclarations(cleaned, block);
    if (declarations.length === 0) {
      continue;
    }
    const selector = block.selector;
    const allowed = isAllowedContext(selector);
    const sides = new Map();
    const values = new Map();
    const hasEdgeSizedBackground = declarations.some(
      (declaration) =>
        declaration.property === 'background-size' &&
        numericThickness(expandVariables(declaration.value, customProperties)) >= MIN_THICKNESS_PX,
    );

    for (const declaration of declarations) {
      const value = expandVariables(declaration.value, customProperties);
      values.set(declaration.property, value);
      const side = SIDE_PROPERTIES.get(declaration.property);
      if (side) {
        const sideState = sides.get(side) ?? {};
        sideState.thickness = Math.max(sideState.thickness ?? 0, numericThickness(value));
        sideState.lime = sideState.lime || containsLime(value);
        sideState.line = declaration.line;
        sides.set(side, sideState);
      }

      const sideWidth = SIDE_WIDTH_PROPERTIES.get(declaration.property);
      if (sideWidth) {
        const sideState = sides.get(sideWidth) ?? {};
        sideState.thickness = Math.max(
          sideState.thickness ?? 0,
          numericThickness(value),
          inlineThickness(value),
        );
        sideState.line = declaration.line;
        sides.set(sideWidth, sideState);
      }

      const sideColor = SIDE_COLOR_PROPERTIES.get(declaration.property);
      if (sideColor) {
        const sideState = sides.get(sideColor) ?? {};
        sideState.lime = sideState.lime || containsLime(value);
        sideState.line = declaration.line;
        sides.set(sideColor, sideState);
      }

      if (
        (declaration.property === 'box-shadow' || declaration.property === '-webkit-box-shadow') &&
        hasForbiddenInsetShadow(value) &&
        !allowed
      ) {
        addViolation(violations, {
          line: lineOffset + declaration.line,
          kind: 'inset-shadow',
          selector,
          message:
            'one-sided inset lime shadow is at least 3px; use a thin frame or an allowed state',
        });
      }

      if (declaration.property === 'background' || declaration.property === 'background-image') {
        if (hasForbiddenGradient(value, hasEdgeSizedBackground) && !allowed) {
          addViolation(violations, {
            line: lineOffset + declaration.line,
            kind: 'gradient-edge',
            selector,
            message: 'lime gradient contains a 3px-or-thicker edge stop or edge-sized background',
          });
        }
      }
    }

    for (const [side, state] of sides) {
      if (state.thickness >= MIN_THICKNESS_PX && state.lime && !allowed) {
        addViolation(violations, {
          line: lineOffset + state.line,
          kind: 'one-sided-border',
          selector,
          message: 'one-sided lime border is at least 3px; use a thin frame or an allowed state',
          side,
        });
      }
    }

    if (!allowed && /(?:::before|::after|:(?:before|after)\b)/.test(selector)) {
      const position = values.get('position') ?? '';
      const width = numericThickness(values.get('width') ?? '');
      const height = numericThickness(values.get('height') ?? '');
      const hasVerticalPins = declarations.some((declaration) =>
        /^(?:left|right|inset-inline-start|inset-inline-end)$/.test(declaration.property),
      );
      const hasHorizontalPins = declarations.some((declaration) =>
        /^(?:top|bottom|inset-block-start|inset-block-end)$/.test(declaration.property),
      );
      const hasInset = declarations.some((declaration) => declaration.property === 'inset');
      if (
        /^(?:absolute|fixed|sticky)$/.test(position.trim()) &&
        containsLime(
          (values.get('background') ?? '') + ' ' + (values.get('background-color') ?? ''),
        ) &&
        ((width >= MIN_THICKNESS_PX && ((hasVerticalPins && hasHorizontalPins) || hasInset)) ||
          (height >= MIN_THICKNESS_PX && ((hasVerticalPins && hasHorizontalPins) || hasInset)))
      ) {
        const declaration = declarations.find(
          (entry) => entry.property === 'background' || entry.property === 'background-color',
        );
        addViolation(violations, {
          line: lineOffset + (declaration?.line ?? declarations[0].line),
          kind: 'pseudo-edge',
          selector,
          message: 'positioned pseudo-element creates a 3px-or-thicker lime edge',
        });
      }
    }
  }
  return violations;
}

function stripJavaScriptQuotes(value) {
  return value.trim().replace(/^['"]|['"]$/g, '');
}

function analyzeInlineStyles(text, lineOffset = 0) {
  const violations = [];
  const sideStates = new Map();
  const propertyPattern =
    /\b(borderLeft|borderRight|borderTop|borderBottom|borderInlineStart|borderInlineEnd|borderBlockStart|borderBlockEnd|borderLeftWidth|borderRightWidth|borderTopWidth|borderBottomWidth|borderInlineStartWidth|borderInlineEndWidth|borderBlockStartWidth|borderBlockEndWidth|borderLeftColor|borderRightColor|borderTopColor|borderBottomColor|borderInlineStartColor|borderInlineEndColor|borderBlockStartColor|borderBlockEndColor|boxShadow|backgroundImage|background)\s*:\s*([^,}\n]+)/g;

  for (const match of text.matchAll(propertyPattern)) {
    const property = match[1];
    const rawValue = stripJavaScriptQuotes(match[2]);
    const start = match.index ?? 0;
    const line = lineNumber(text, start, lineOffset);
    const context = text.slice(Math.max(0, start - 180), start + 180);
    const allowed = isAllowedContext(context);
    const sideName = {
      borderLeft: 'left',
      borderRight: 'right',
      borderTop: 'top',
      borderBottom: 'bottom',
      borderInlineStart: 'inline-start',
      borderInlineEnd: 'inline-end',
      borderBlockStart: 'block-start',
      borderBlockEnd: 'block-end',
    }[property.replace(/Width$|Color$/, '')];
    if (sideName) {
      const state = sideStates.get(sideName) ?? {};
      if (property.endsWith('Width')) {
        state.thickness = Math.max(state.thickness ?? 0, inlineThickness(rawValue));
      } else if (property.endsWith('Color')) {
        state.lime = state.lime || containsLime(rawValue);
      } else {
        state.thickness = Math.max(state.thickness ?? 0, numericThickness(rawValue));
        state.lime = state.lime || containsLime(rawValue);
      }
      state.line = line;
      state.allowed = state.allowed || allowed;
      sideStates.set(sideName, state);
    }

    if (property === 'boxShadow' && hasForbiddenInsetShadow(rawValue) && !allowed) {
      addViolation(violations, {
        line,
        kind: 'inline-inset-shadow',
        message: 'inline style creates a one-sided inset lime shadow of at least 3px',
      });
    }
    if (
      (property === 'background' || property === 'backgroundImage') &&
      hasForbiddenGradient(rawValue, numericThickness(rawValue) >= MIN_THICKNESS_PX) &&
      !allowed
    ) {
      addViolation(violations, {
        line,
        kind: 'inline-gradient-edge',
        message: 'inline style creates a lime gradient edge of at least 3px',
      });
    }
  }

  for (const [side, state] of sideStates) {
    if (state.thickness >= MIN_THICKNESS_PX && state.lime && !state.allowed) {
      addViolation(violations, {
        line: state.line,
        kind: 'inline-one-sided-border',
        message: 'inline style creates a one-sided lime border of at least 3px',
        side,
      });
    }
  }
  return violations;
}

function analyzeSource(text, sourceName = 'source', lineOffset = 0) {
  const extension = path.extname(sourceName).toLowerCase();
  const violations =
    extension === '.css' ||
    extension === '.scss' ||
    extension === '.sass' ||
    extension === '.less' ||
    extension === '.pcss'
      ? analyzeCssText(text, lineOffset)
      : analyzeInlineStyles(text, lineOffset);

  if (extension !== '.css' && extension !== '.scss') {
    const templateMark = String.fromCharCode(96);
    const templatePattern = new RegExp(templateMark + '([\\s\\S]*?)' + templateMark, 'g');
    for (const match of text.matchAll(templatePattern)) {
      if (
        !/(?:border-(?:left|right|top|bottom|inline|block)|box-shadow|background(?:-image|-color)?\s*:)/i.test(
          match[1],
        )
      ) {
        continue;
      }
      const templateStart = (match.index ?? 0) + match[0].indexOf(templateMark) + 1;
      const templateLine = lineNumber(text, templateStart, lineOffset) - 1;
      violations.push(...analyzeCssText(match[1], templateLine));
    }
  }

  const unique = new Map();
  for (const violation of violations) {
    const key = [violation.line, violation.kind, violation.side ?? '', violation.message].join(':');
    unique.set(key, violation);
  }
  return [...unique.values()];
}

function isSourceFile(filePath) {
  return SOURCE_EXTENSIONS.has(path.extname(filePath).toLowerCase());
}

function collectFiles(target) {
  const stats = fs.statSync(target);
  if (stats.isFile()) {
    return isSourceFile(target) ? [target] : [];
  }
  const files = [];
  for (const entry of fs.readdirSync(target, { withFileTypes: true })) {
    if (['node_modules', 'dist', 'coverage', '.git'].includes(entry.name)) {
      continue;
    }
    const child = path.join(target, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectFiles(child));
    } else if (isSourceFile(child)) {
      files.push(child);
    }
  }
  return files;
}

function git(args) {
  return execFileSync('git', args, {
    cwd: REPO_ROOT,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

function resolveBase() {
  const candidates = [];
  if (process.env.LIME_EDGE_BASE_SHA) {
    candidates.push(process.env.LIME_EDGE_BASE_SHA);
  }
  if (process.env.GITHUB_BASE_REF) {
    candidates.push('origin/' + process.env.GITHUB_BASE_REF);
  }
  candidates.push('origin/master');
  for (const candidate of candidates) {
    try {
      git(['rev-parse', '--verify', candidate + '^{commit}']);
      return candidate;
    } catch {
      continue;
    }
  }
  return null;
}

function changedSourceFiles() {
  const base = resolveBase();
  if (!base) {
    throw new Error(
      'could not resolve a base revision; set LIME_EDGE_BASE_SHA or fetch origin/master',
    );
  }
  const diff = git(['diff', '--unified=0', '--no-color', base, '--', 'frontend/src']);
  const changes = new Map();
  let currentFile = null;
  let currentLines = new Set();
  for (const line of diff.split(/\r?\n/)) {
    if (line.startsWith('+++ b/')) {
      currentFile = path.resolve(REPO_ROOT, line.slice(6));
      currentLines = new Set();
      changes.set(currentFile, currentLines);
      continue;
    }
    const hunk = line.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/);
    if (hunk && currentFile) {
      const start = Number(hunk[1]);
      const count = hunk[2] === undefined ? 1 : Number(hunk[2]);
      for (let offset = 0; offset < count; offset += 1) {
        currentLines.add(start + offset);
      }
    }
  }
  for (const untracked of git(['ls-files', '--others', '--exclude-standard', '--', 'frontend/src'])
    .split(/\r?\n/)
    .filter(Boolean)) {
    const filePath = path.resolve(REPO_ROOT, untracked);
    if (isSourceFile(filePath)) {
      const lineCount = fs.readFileSync(filePath, 'utf8').split(/\r?\n/).length;
      changes.set(filePath, new Set(Array.from({ length: lineCount }, (_, index) => index + 1)));
    }
  }
  return { base, changes };
}

function formatViolation(filePath, violation) {
  const relative = path.relative(REPO_ROOT, filePath).replaceAll(path.sep, '/');
  return (
    relative +
    ':' +
    violation.line +
    ' ' +
    violation.message +
    (violation.selector ? ' (' + violation.selector + ')' : '')
  );
}

export function run(argv = process.argv.slice(2)) {
  const pathArgumentIndex = argv.indexOf('--path');
  const pathArgument = pathArgumentIndex >= 0 ? argv[pathArgumentIndex + 1] : null;
  const violations = [];
  if (pathArgument) {
    const target = path.resolve(process.cwd(), pathArgument);
    for (const filePath of collectFiles(target)) {
      const source = fs.readFileSync(filePath, 'utf8');
      for (const violation of analyzeSource(source, filePath)) {
        violations.push({ filePath, violation });
      }
    }
  } else {
    const { base, changes } = changedSourceFiles();
    if (changes.size === 0) {
      console.log('thick lime edge check passed: no changed frontend source files');
      return 0;
    }
    for (const [filePath, changedLines] of changes) {
      if (!fs.existsSync(filePath)) {
        continue;
      }
      const source = fs.readFileSync(filePath, 'utf8');
      for (const violation of analyzeSource(source, filePath)) {
        if (changedLines.has(violation.line)) {
          violations.push({ filePath, violation });
        }
      }
    }
    if (violations.length === 0) {
      console.log('thick lime edge check passed: changed frontend source is clean against ' + base);
      return 0;
    }
  }

  if (violations.length > 0) {
    console.error('thick lime edge check failed:');
    for (const { filePath, violation } of violations) {
      console.error('  ' + formatViolation(filePath, violation));
    }
    return 1;
  }
  console.log('thick lime edge check passed');
  return 0;
}

const invokedPath = process.argv[1] ? pathToFileURL(path.resolve(process.argv[1])).href : null;
if (invokedPath === import.meta.url) {
  try {
    process.exitCode = run();
  } catch (error) {
    console.error(
      'thick lime edge check could not run: ' +
        (error instanceof Error ? error.message : String(error)),
    );
    process.exitCode = 2;
  }
}
