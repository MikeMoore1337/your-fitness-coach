import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const interactiveTags = new Set(['button', 'a', 'summary', 'Button', 'AppLink', 'IconButton']);
const iconSymbols = /[⌄⌃›‹▲▼▶◀►◄▾▴▸◂↗↘↙↖↑↓←→✕✖✚❌✅✓✔⚠ℹ🔍⚙🗑💧🔔🕒⏱🔎✎✏⋮⋯☰☑]/u;

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? sourceFiles(path) : /\.(tsx|css)$/.test(path) ? [path] : [];
  });
}

function iconSourceViolations(source: string, path = 'source.tsx'): string[] {
  const file = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const violations: string[] = [];
  function report(node: ts.Node, reason: string) {
    violations.push(
      `${file.getLineAndCharacterOfPosition(node.getStart(file)).line + 1}: ${reason}`,
    );
  }
  function hasChevron(node: ts.Node): boolean {
    if (ts.isJsxSelfClosingElement(node)) {
      if (node.tagName.getText(file) === 'DisclosureIcon') return true;
      if (node.tagName.getText(file) === 'Icon') {
        const name = node.attributes.properties.find(
          (attribute) => ts.isJsxAttribute(attribute) && attribute.name.getText(file) === 'name',
        );
        if (name && /(?:chevron-|disclosure-)/.test(name.getText(file))) return true;
      }
    }
    return ts.forEachChild(node, hasChevron) ?? false;
  }
  function inControl(node: ts.Node): boolean {
    for (let parent = node.parent; parent; parent = parent.parent) {
      if (
        ts.isJsxElement(parent) &&
        interactiveTags.has(parent.openingElement.tagName.getText(file))
      ) {
        return true;
      }
    }
    return false;
  }
  function visit(node: ts.Node) {
    if (
      ts.isJsxSelfClosingElement(node) &&
      ['input', 'Input'].includes(node.tagName.getText(file))
    ) {
      const type = node.attributes.properties.find(
        (attribute) => ts.isJsxAttribute(attribute) && attribute.name.getText(file) === 'type',
      );
      if (
        type &&
        /type="(?:date|time)"/.test(type.getText(file)) &&
        !path.endsWith('PickerInput.tsx')
      ) {
        report(node, 'date and time fields must reuse the shared Icon picker primitives');
      }
    }
    if (ts.isJsxElement(node) && node.openingElement.tagName.getText(file) === 'svg') {
      if (!['Icon.tsx', 'DataViz.tsx', 'OAuthButtons.tsx'].some((name) => path.endsWith(name))) {
        report(
          node,
          'inline SVG must use Icon, a branded resource or the data visualization renderer',
        );
      }
    }
    if (ts.isJsxElement(node) && node.openingElement.tagName.getText(file) === 'summary') {
      if (!hasChevron(node)) report(node, 'summary needs an approved Icon chevron');
      const className = node.openingElement.attributes.properties.find(
        (attribute) => ts.isJsxAttribute(attribute) && attribute.name.getText(file) === 'className',
      );
      if (!className?.getText(file).includes('yfc-disclosure-summary')) {
        report(node, 'summary needs the shared marker and alignment styles');
      }
    }
    if (ts.isJsxText(node)) {
      const text = node.text.trim();
      const emoji = /\p{Extended_Pictographic}/u.test(text.replace(/[©®™]/g, ''));
      const version =
        text === 'v' &&
        ts.isJsxElement(node.parent) &&
        node.parent.children.some((child) => ts.isJsxExpression(child));
      if (
        emoji ||
        (inControl(node) && (iconSymbols.test(text) || (!version && /^[+−xv^<>-]$/.test(text))))
      ) {
        report(node, 'semantic symbols and emoji must use Icon');
      }
    }
    if (ts.isJsxExpression(node) && node.expression) {
      function visitExpression(value: ts.Node) {
        if (
          ts.isStringLiteralLike(value) &&
          inControl(node) &&
          /^[⌄⌃›‹▲▼▶◀▾▴+−×xv^<>-]$/.test(value.text)
        ) {
          report(value, 'symbol-only control labels must use Icon');
        }
        ts.forEachChild(value, visitExpression);
      }
      visitExpression(node.expression);
    }
    ts.forEachChild(node, visit);
  }
  visit(file);
  return violations;
}

function cssIconViolations(source: string): string[] {
  return [...source.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}]+)\{([^{}]*)\}/g)].flatMap(
    ([, selector = '', declarations = '']) => {
      const symbol = /(?:^|;)\s*content\s*:\s*['"][+−×⌄⌃›‹▲▼▶◀▾▴↑↓←→✓✕v^<>-]['"]/.test(
        declarations,
      );
      const iconSelector = /(?:icon|chevron|summary|caret|arrow)/.test(selector);
      const pseudoIcon = /::?(?:before|after)/.test(selector) && iconSelector;
      const drawsShape =
        /(?:^|;)\s*(?:border(?:-(?:top|right|bottom|left))?|clip-path|background(?:-image)?|mask(?:-image)?)\s*:/.test(
          declarations,
        );
      const rotatedShape = iconSelector && /transform\s*:\s*(?:rotate|skew)/.test(declarations);
      return symbol || ((pseudoIcon || rotatedShape) && drawsShape) ? [selector.trim()] : [];
    },
  );
}

describe('production icon sources', () => {
  it('keeps every native disclosure on the shared Icon and marker contract', () => {
    const violations = sourceFiles('src')
      .filter((path) => path.endsWith('.tsx'))
      .flatMap((path) =>
        iconSourceViolations(readFileSync(path, 'utf8'), path).map((item) => `${path}:${item}`),
      );
    expect(violations).toEqual([]);
  });

  it('rejects CSS semantic drawings while preserving borders, backgrounds and data notation', () => {
    const violations = sourceFiles('src')
      .filter((path) => path.endsWith('.css'))
      .flatMap((path) =>
        cssIconViolations(readFileSync(path, 'utf8')).map((item) => `${path}: ${item}`),
      );
    expect(violations).toEqual([]);
  });

  it('catches missing disclosure glyphs, symbolic controls, emoji and CSS icon shapes', () => {
    expect(iconSourceViolations('<details><summary>История</summary></details>')).not.toEqual([]);
    expect(iconSourceViolations('<button>Открыть →</button>')).not.toEqual([]);
    expect(iconSourceViolations('<button>{open ? "−" : "+"}</button>')).not.toEqual([]);
    expect(iconSourceViolations('<button>👍</button>')).not.toEqual([]);
    expect(iconSourceViolations('<input type="date" />')).not.toEqual([]);
    expect(iconSourceViolations('<button><svg><path d="M1 2" /></svg></button>')).not.toEqual([]);
    expect(
      cssIconViolations('.chevron::after { border-right: 2px solid; transform: rotate(45deg); }'),
    ).not.toEqual([]);
    expect(cssIconViolations('summary::after { content: "+"; }')).not.toEqual([]);
  });

  it('allows recorded quantities, mathematical signs, text changes and approved resources', () => {
    expect(
      iconSourceViolations(`
      <><p>{weight} × {reps}</p><span>{delta > 0 ? '+' : ''}{delta} кг</span>
        <li>{previous} → {current}</li><Badge>v{version}</Badge><p>© Your Fitness Coach</p>
        <button>{count} × 4</button><button><Icon name="plus" />Добавить</button>
        <details><summary className="yfc-disclosure-summary">История<Badge>v{version}</Badge><DisclosureIcon /></summary></details>
      </>
    `),
    ).toEqual([]);
    expect(
      cssIconViolations(`
      .card::before { content: ''; border: 1px solid; background: lime; }
      .delta::before { content: '·'; } .yfc-icon { transform: rotate(90deg); }
    `),
    ).toEqual([]);
  });
});
