import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const frontendDirectory = path.resolve(scriptDirectory, '..');
const repositoryDirectory = path.resolve(frontendDirectory, '..');
const latinWordPattern = /[A-Za-z]+(?:-[A-Za-z]+)*/g;

// Deliberate, small allowlist: only product branding and technical terms that
// have no useful Russian UI equivalent are permitted in user-facing copy.
const allowedLatinWords = new Map([
  ['API', 'technical interface abbreviation'],
  ['AI', 'technical product abbreviation'],
  ['CSS', 'web technology abbreviation'],
  ['CSV', 'file format abbreviation'],
  ['DOCX', 'file format abbreviation'],
  ['HTML', 'web technology abbreviation'],
  ['HTTP', 'protocol abbreviation'],
  ['HTTPS', 'protocol abbreviation'],
  ['ID', 'technical identifier abbreviation'],
  ['JSON', 'data format abbreviation'],
  ['OAuth', 'authentication protocol name'],
  ['PDF', 'file format abbreviation'],
  ['PWA', 'web application abbreviation'],
  ['QR', 'common technical abbreviation'],
  ['TMA', 'Telegram Mini App abbreviation'],
  ['UI', 'interface abbreviation'],
  ['URL', 'web address abbreviation'],
  ['UX', 'interface abbreviation'],
  ['XLSX', 'file format abbreviation'],
  ['Telegram', 'official external platform name'],
]);

const allowedLatinPhrases = new Map([
  ['Your Fitness Coach', 'official product brand'],
  ['Coach OS', 'official product name'],
]);

const userFacingAttributes = new Set([
  'alt',
  'aria-description',
  'aria-label',
  'aria-roledescription',
  'placeholder',
  'title',
]);

const userFacingProperties = new Set([
  'caption',
  'confirmtext',
  'description',
  'empty',
  'emptymessage',
  'error',
  'errormessage',
  'helpertext',
  'label',
  'message',
  'notice',
  'placeholder',
  'prompt',
  'reason',
  'statuslabel',
  'success',
  'successmessage',
  'text',
  'title',
  'toast',
]);

const userFacingCalls = new Set([
  'alert',
  'confirm',
  'notify',
  'seterror',
  'setmessage',
  'showerror',
  'showtoast',
  'toast',
]);

function git(args) {
  try {
    return execFileSync('git', args, {
      cwd: repositoryDirectory,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    });
  } catch {
    return '';
  }
}

function changedLineRanges(diff) {
  const files = new Map();
  let currentFile = null;

  for (const line of diff.split('\n')) {
    const fileMatch = /^diff --git a\/(.+) b\/(.+)$/.exec(line);
    if (fileMatch) {
      currentFile = fileMatch[2];
      files.set(currentFile, []);
      continue;
    }
    const hunkMatch = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/.exec(line);
    if (!hunkMatch || !currentFile) continue;
    const start = Number(hunkMatch[1]);
    const count = hunkMatch[2] === undefined ? 1 : Number(hunkMatch[2]);
    if (count > 0) files.get(currentFile).push([start, start + count - 1]);
  }
  return files;
}

function baseRevision() {
  const eventPath = process.env.GITHUB_EVENT_PATH;
  if (eventPath) {
    try {
      const event = JSON.parse(fs.readFileSync(eventPath, 'utf8'));
      const revision = event.pull_request?.base?.sha ?? event.before;
      if (revision && !/^0+$/.test(revision)) {
        const resolvedRevision = git(['rev-parse', '--verify', `${revision}^{commit}`]).trim();
        if (resolvedRevision) return resolvedRevision;
      }
    } catch {
      // Local runs do not need GitHub event metadata.
    }
  }

  const mergeBase = git(['merge-base', 'origin/master', 'HEAD']).trim();
  if (mergeBase) return mergeBase;
  const parent = git(['rev-parse', 'HEAD^']).trim();
  return parent || null;
}

function sourceChanges() {
  const revision = baseRevision();
  const diff = revision
    ? git(['diff', '--no-ext-diff', '--unified=0', revision, '--', 'frontend/src'])
    : git(['diff', '--no-ext-diff', '--unified=0', '--', 'frontend/src']);
  return changedLineRanges(diff);
}

function lineIntersects(node, sourceFile, ranges) {
  const startLine = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
  const endLine = sourceFile.getLineAndCharacterOfPosition(node.end).line + 1;
  return ranges.some(([start, end]) => startLine <= end && endLine >= start);
}

function propertyName(name) {
  if (!name) return '';
  if (ts.isIdentifier(name) || ts.isPrivateIdentifier(name)) return name.text;
  if (ts.isStringLiteral(name) || ts.isNumericLiteral(name)) return name.text;
  return name.getText().replace(/^['"]|['"]$/g, '');
}

function normalizedName(name) {
  return propertyName(name).replace(/[-_]/g, '').toLowerCase();
}

function callName(expression) {
  const text = expression.getText();
  return /([A-Za-z_$][\w$]*)$/.exec(text)?.[1]?.toLowerCase() ?? '';
}

function isWithin(node, ancestor) {
  return ancestor === node || (ancestor.pos <= node.pos && node.end <= ancestor.end);
}

function staticText(node) {
  if (ts.isJsxText(node)) return node.getText();
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
  if (ts.isTemplateExpression(node)) {
    return [node.head.text, ...node.templateSpans.map((span) => span.literal.text)].join('');
  }
  return '';
}

function hasUserFacingContext(node) {
  let current = node.parent;
  for (let depth = 0; current && depth < 6; depth += 1, current = current.parent) {
    if (ts.isJsxAttribute(current)) {
      return userFacingAttributes.has(current.name.getText().toLowerCase());
    }

    if (ts.isJsxExpression(current)) {
      const container = current.parent;
      if (ts.isJsxAttribute(container)) {
        return userFacingAttributes.has(container.name.getText().toLowerCase());
      }
      if (ts.isJsxElement(container) || ts.isJsxFragment(container)) return true;
    }

    if (ts.isPropertyAssignment(current)) {
      return userFacingProperties.has(normalizedName(current.name));
    }

    if (ts.isVariableDeclaration(current)) {
      return /(?:caption|confirm|description|empty|error|label|message|notice|placeholder|prompt|reason|status|success|text|title|toast)/i.test(
        propertyName(current.name),
      );
    }

    if (ts.isCallExpression(current)) {
      const call = callName(current.expression);
      const firstArgument = current.arguments[0];
      return (
        userFacingCalls.has(call) && firstArgument !== undefined && isWithin(node, firstArgument)
      );
    }

    if (ts.isNewExpression(current)) {
      const firstArgument = current.arguments?.[0];
      return (
        callName(current.expression) === 'error' &&
        firstArgument !== undefined &&
        isWithin(node, firstArgument)
      );
    }

    if (ts.isSourceFile(current) || ts.isFunctionLike(current)) return false;
  }
  return false;
}

function isCandidate(node) {
  if (ts.isJsxText(node)) return true;
  if (
    !ts.isStringLiteral(node) &&
    !ts.isNoSubstitutionTemplateLiteral(node) &&
    !ts.isTemplateExpression(node)
  ) {
    return false;
  }
  return hasUserFacingContext(node);
}

function violations(text) {
  let remaining = text;
  for (const phrase of allowedLatinPhrases.keys()) remaining = remaining.replaceAll(phrase, ' ');
  const words = remaining.match(latinWordPattern) ?? [];
  return words.filter((word) => !allowedLatinWords.has(word));
}

function inspectFile(fileName, text, ranges) {
  const scriptKind = fileName.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sourceFile = ts.createSourceFile(fileName, text, ts.ScriptTarget.Latest, true, scriptKind);
  const findings = [];
  function visit(node) {
    if (isCandidate(node) && lineIntersects(node, sourceFile, ranges)) {
      const textValue = staticText(node).replace(/\s+/g, ' ').trim();
      const badWords = violations(textValue);
      if (textValue && badWords.length > 0) {
        const position = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
        findings.push({
          fileName,
          line: position.line + 1,
          column: position.character + 1,
          text: textValue,
          words: [...new Set(badWords)],
        });
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
  return findings;
}

function run() {
  if (process.argv.includes('--stdin')) {
    const text = fs.readFileSync(0, 'utf8');
    const ranges = [[1, text.split('\n').length]];
    return inspectFile('stdin.tsx', text, ranges);
  }

  const findings = [];
  for (const [relativeFile, ranges] of sourceChanges()) {
    if (!/\.(?:ts|tsx)$/.test(relativeFile) || !relativeFile.startsWith('frontend/src/')) {
      continue;
    }
    const fileName = path.resolve(repositoryDirectory, relativeFile);
    if (!fs.existsSync(fileName)) continue;
    findings.push(...inspectFile(relativeFile, fs.readFileSync(fileName, 'utf8'), ranges));
  }
  return findings;
}

const findings = run();
if (findings.length > 0) {
  console.error('Russian user-facing UI guard failed:');
  for (const finding of findings) {
    console.error(
      `  ${finding.fileName}:${finding.line}:${finding.column} contains ${finding.words.join(', ')}: ${finding.text}`,
    );
  }
  process.exitCode = 1;
} else {
  console.log('Russian user-facing UI guard passed.');
}
