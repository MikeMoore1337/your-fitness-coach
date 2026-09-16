import { expect, type Page, type TestInfo } from '@playwright/test';

export const UI_AUDIT_VIEWPORTS = [
  { name: 'phone-320', width: 320, height: 568 },
  { name: 'phone-360', width: 360, height: 800 },
  { name: 'phone-390', width: 390, height: 844 },
  { name: 'phone-430', width: 430, height: 932 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'desktop-1280', width: 1280, height: 720 },
  { name: 'desktop-1440', width: 1440, height: 900 },
  { name: 'desktop-1920', width: 1920, height: 1080 },
  { name: 'desktop-2560', width: 2560, height: 1440 },
] as const;

export type UiAuditSeverity = 'BLOCKER' | 'HIGH' | 'MEDIUM' | 'LOW';
export type UiAuditCategory =
  | 'overflow'
  | 'boundary'
  | 'clipping'
  | 'collision'
  | 'accessibility'
  | 'iconography'
  | 'design-token';

export interface UiAuditIssue {
  code: string;
  category: UiAuditCategory;
  severity: UiAuditSeverity;
  selector: string;
  message: string;
}

export interface UiAuditReport {
  viewport: { width: number; height: number };
  scroll: { x: number; y: number };
  issues: UiAuditIssue[];
}

interface UiAuditOptions {
  checkTouchTargets?: boolean;
  minTouchTarget?: number;
  fixedOverlaySelectors?: string[];
  intentionalOverlaySelectors?: string[];
}

const AUDITABLE_INTERACTIVE_SELECTOR =
  'button, a, input, select, textarea, [role="button"], [role="link"], [role="tab"], [role="menuitem"], [role="checkbox"], [role="radio"], [role="switch"], [role="slider"]';

export async function collectUiAudit(
  page: Page,
  options: UiAuditOptions = {},
): Promise<UiAuditReport> {
  return page.evaluate(
    ({
      checkTouchTargets,
      minTouchTarget,
      fixedOverlaySelectors,
      intentionalOverlaySelectors,
      interactiveSelector,
    }) => {
      type BrowserIssue = UiAuditIssue;

      const issues: BrowserIssue[] = [];
      const seen = new Set<string>();
      const root = document.body;
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;

      const selectorFor = (element: Element): string => {
        if (element.id) return `#${element.id}`;
        const classes = [...element.classList].filter(Boolean).slice(0, 2);
        return `${element.tagName.toLowerCase()}${classes.map((name) => `.${name}`).join('')}`;
      };

      const addIssue = (
        code: string,
        category: UiAuditCategory,
        severity: UiAuditSeverity,
        element: Element | null,
        message: string,
      ): void => {
        const selector = element ? selectorFor(element) : 'document';
        const key = `${code}:${selector}:${message}`;
        if (seen.has(key)) return;
        seen.add(key);
        issues.push({ code, category, severity, selector, message });
      };

      const isVisible = (element: Element): element is HTMLElement => {
        const candidate = element as HTMLElement;
        const style = getComputedStyle(candidate);
        const rect = candidate.getBoundingClientRect();
        return (
          candidate.getClientRects().length > 0 &&
          rect.width > 0 &&
          rect.height > 0 &&
          style.display !== 'none' &&
          style.visibility !== 'hidden' &&
          style.visibility !== 'collapse' &&
          style.opacity !== '0' &&
          style.pointerEvents !== 'none'
        );
      };

      const isSkipLink = (element: Element): boolean =>
        element.matches('.public-shell__skip-link, [data-ui-audit-skip-link]');

      const isNativeChoiceControl = (element: HTMLElement): boolean =>
        element instanceof HTMLInputElement &&
        (element.type === 'checkbox' || element.type === 'radio');

      const hasAriaHiddenAncestor = (element: Element): boolean =>
        Boolean(element.closest('[aria-hidden="true"]'));

      const labelFromReference = (element: Element): string => {
        const labelledBy = element.getAttribute('aria-labelledby');
        if (!labelledBy) return '';
        return labelledBy
          .split(/\s+/)
          .map((id) => document.getElementById(id)?.textContent ?? '')
          .join(' ')
          .replace(/\s+/g, ' ')
          .trim();
      };

      const accessibleName = (element: HTMLElement): string => {
        const ariaLabel = element.getAttribute('aria-label')?.trim();
        if (ariaLabel) return ariaLabel;
        const referencedLabel = labelFromReference(element);
        if (referencedLabel) return referencedLabel;
        if (
          element instanceof HTMLInputElement ||
          element instanceof HTMLSelectElement ||
          element instanceof HTMLTextAreaElement
        ) {
          const associatedLabel = element.id
            ? document.querySelector(`label[for="${CSS.escape(element.id)}"]`)
            : null;
          const wrappingLabel = element.closest('label');
          const label = associatedLabel?.textContent ?? wrappingLabel?.textContent ?? '';
          if (label.trim()) return label.replace(/\s+/g, ' ').trim();
        }
        const title = element.getAttribute('title')?.trim();
        if (title) return title;
        return (element.textContent ?? '').replace(/\s+/g, ' ').trim();
      };

      const overlaps = (left: DOMRect, right: DOMRect): boolean =>
        left.left < right.right &&
        left.right > right.left &&
        left.top < right.bottom &&
        left.bottom > right.top;

      const hasScrollableAncestor = (element: Element, axis: 'x' | 'y'): boolean => {
        let ancestor = element.parentElement;
        while (
          ancestor &&
          ancestor !== document.body &&
          ancestor !== document.documentElement &&
          ancestor.id !== 'root'
        ) {
          const style = getComputedStyle(ancestor);
          const isScrollable =
            axis === 'x'
              ? (style.overflowX === 'auto' || style.overflowX === 'scroll') &&
                ancestor.scrollWidth > ancestor.clientWidth + 1
              : (style.overflowY === 'auto' || style.overflowY === 'scroll') &&
                ancestor.scrollHeight > ancestor.clientHeight + 1;
          if (isScrollable) return true;
          ancestor = ancestor.parentElement;
        }
        return false;
      };

      const documentWidth = Math.max(
        document.documentElement.scrollWidth,
        document.body.scrollWidth,
      );
      if (documentWidth > viewportWidth + 1) {
        addIssue(
          'UI-AUDIT-OVERFLOW-X',
          'overflow',
          'HIGH',
          null,
          `document scrollWidth ${documentWidth}px exceeds viewport ${viewportWidth}px`,
        );
      }

      const interactive = [...root.querySelectorAll<HTMLElement>(interactiveSelector)]
        .filter((element) => isVisible(element) && !hasAriaHiddenAncestor(element))
        .filter((element) => element.getAttribute('type') !== 'hidden');

      // Full-viewport modal layers intentionally cover controls from the page beneath them.
      // Keep auditing controls inside the layer, but exclude the obscured underlying controls
      // from pairwise and fixed-nav collision checks.
      const intentionalOverlays = intentionalOverlaySelectors.flatMap((selector) =>
        [...root.querySelectorAll<HTMLElement>(selector)].filter(isVisible),
      );
      const isCoveredByIntentionalOverlay = (element: HTMLElement): boolean => {
        const rect = element.getBoundingClientRect();
        return intentionalOverlays.some(
          (overlay) =>
            !overlay.contains(element) && overlaps(rect, overlay.getBoundingClientRect()),
        );
      };

      for (const element of interactive) {
        const rect = element.getBoundingClientRect();
        const insideHorizontalScroller = hasScrollableAncestor(element, 'x');
        if ((rect.left < -1 || rect.right > viewportWidth + 1) && !insideHorizontalScroller) {
          addIssue(
            'UI-AUDIT-BOUNDARY-X',
            'boundary',
            'HIGH',
            element,
            `interactive control is outside horizontal viewport (${Math.round(rect.left)}..${Math.round(rect.right)} of ${viewportWidth}px)`,
          );
        }

        if (
          checkTouchTargets &&
          !isSkipLink(element) &&
          !isNativeChoiceControl(element) &&
          getComputedStyle(element).display !== 'inline' &&
          (Math.ceil(rect.width) < minTouchTarget || Math.ceil(rect.height) < minTouchTarget)
        ) {
          addIssue(
            'UI-AUDIT-TOUCH-TARGET',
            'accessibility',
            'MEDIUM',
            element,
            `interactive control is ${Math.round(rect.width)}x${Math.round(rect.height)}px; minimum is ${minTouchTarget}px`,
          );
        }

        if (!accessibleName(element)) {
          addIssue(
            'UI-AUDIT-ACCESSIBLE-NAME',
            'accessibility',
            'HIGH',
            element,
            'interactive control has no accessible name',
          );
        }

        let ancestor = element.parentElement;
        while (
          ancestor &&
          ancestor !== document.body &&
          ancestor !== document.documentElement &&
          ancestor.id !== 'root'
        ) {
          const style = getComputedStyle(ancestor);
          const ancestorRect = ancestor.getBoundingClientRect();
          const clipsX = style.overflowX === 'hidden' || style.overflowX === 'clip';
          const clipsY = style.overflowY === 'hidden' || style.overflowY === 'clip';
          const clippedHorizontally =
            clipsX && (rect.left < ancestorRect.left - 1 || rect.right > ancestorRect.right + 1);
          const clippedVertically =
            clipsY && (rect.top < ancestorRect.top - 1 || rect.bottom > ancestorRect.bottom + 1);
          if (
            (clippedHorizontally || clippedVertically) &&
            !(clippedHorizontally && insideHorizontalScroller) &&
            !ancestor.hasAttribute('data-ui-audit-allow-clipping') &&
            overlaps(rect, ancestorRect)
          ) {
            addIssue(
              'UI-AUDIT-CLIPPING',
              'clipping',
              'HIGH',
              element,
              `interactive control is clipped by ${selectorFor(ancestor)}`,
            );
            break;
          }
          ancestor = ancestor.parentElement;
        }
      }

      for (const details of [...root.querySelectorAll<HTMLDetailsElement>('details:not([open])')]) {
        for (const child of [...details.children].filter(
          (candidate): candidate is HTMLElement =>
            candidate.tagName.toLowerCase() !== 'summary' && isVisible(candidate),
        )) {
          addIssue(
            'UI-AUDIT-CLOSED-DISCLOSURE',
            'accessibility',
            'HIGH',
            details,
            `closed disclosure renders its non-summary child ${selectorFor(child)}`,
          );
        }
      }

      const idOwners = new Map<string, Element>();
      for (const element of [...root.querySelectorAll<HTMLElement>('[id]')]) {
        const id = element.id.trim();
        if (!id) continue;
        const firstOwner = idOwners.get(id);
        if (firstOwner) {
          addIssue(
            'UI-AUDIT-DUPLICATE-ID',
            'accessibility',
            'HIGH',
            element,
            `id "${id}" is also used by ${selectorFor(firstOwner)}`,
          );
        } else {
          idOwners.set(id, element);
        }
      }

      for (const image of [...root.querySelectorAll<HTMLImageElement>('img')].filter(isVisible)) {
        if (!image.hasAttribute('alt')) {
          addIssue(
            'UI-AUDIT-IMAGE-ALT',
            'accessibility',
            'HIGH',
            image,
            'visible image is missing an alt attribute',
          );
        }
        if (image.complete && image.naturalWidth === 0) {
          addIssue(
            'UI-AUDIT-BROKEN-IMAGE',
            'boundary',
            'HIGH',
            image,
            `visible image failed to load: ${image.currentSrc || image.src}`,
          );
        }
      }

      for (const icon of [...root.querySelectorAll<SVGElement>('svg')].filter(isVisible)) {
        const isAllowedBrandIcon = Boolean(icon.closest('.oauth-button__icon'));
        const isAllowedDataViz = Boolean(icon.closest('.data-viz-chart'));
        if (!icon.hasAttribute('data-icon') && !isAllowedBrandIcon && !isAllowedDataViz) {
          addIssue(
            'UI-AUDIT-INLINE-SVG',
            'iconography',
            'MEDIUM',
            icon,
            'visible UI SVG is not rendered by the shared Icon registry',
          );
        }
      }

      for (const element of [...root.querySelectorAll<HTMLElement>('[data-glass-variant]')].filter(
        isVisible,
      )) {
        if (!element.hasAttribute('data-glass')) {
          addIssue(
            'UI-AUDIT-GLASS-CONTRACT',
            'design-token',
            'MEDIUM',
            element,
            'glass variant is present without the shared data-glass marker',
          );
        }
      }

      const collisionCandidates = interactive.filter((element) => {
        if (isNativeChoiceControl(element)) return false;
        if (isCoveredByIntentionalOverlay(element)) return false;
        const style = getComputedStyle(element);
        const closestDialog = element.closest('[role="dialog"]');
        return (
          element.hasAttribute('data-ui-audit-collision') ||
          style.position === 'absolute' ||
          style.position === 'fixed' ||
          style.position === 'sticky' ||
          Boolean(closestDialog)
        );
      });
      for (let index = 0; index < collisionCandidates.length; index += 1) {
        const left = collisionCandidates[index];
        if (!left) continue;
        const leftRect = left.getBoundingClientRect();
        for (const right of collisionCandidates.slice(index + 1)) {
          if (left.contains(right) || right.contains(left)) continue;
          const rightRect = right.getBoundingClientRect();
          if (!overlaps(leftRect, rightRect)) continue;
          const intersectionWidth =
            Math.min(leftRect.right, rightRect.right) - Math.max(leftRect.left, rightRect.left);
          const intersectionHeight =
            Math.min(leftRect.bottom, rightRect.bottom) - Math.max(leftRect.top, rightRect.top);
          const intersectionArea = intersectionWidth * intersectionHeight;
          const smallerArea = Math.min(
            leftRect.width * leftRect.height,
            rightRect.width * rightRect.height,
          );
          if (smallerArea > 0 && intersectionArea / smallerArea > 0.2) {
            addIssue(
              'UI-AUDIT-CONTROL-COLLISION',
              'collision',
              'HIGH',
              left,
              `overlaps ${selectorFor(right)} by ${Math.round((intersectionArea / smallerArea) * 100)}% of the smaller control`,
            );
          }
        }
      }

      for (const overlaySelector of fixedOverlaySelectors) {
        const overlay = root.querySelector<HTMLElement>(overlaySelector);
        if (!overlay || !isVisible(overlay)) continue;
        const overlayRect = overlay.getBoundingClientRect();
        const criticalInteractive = interactive
          .filter(
            (element) =>
              element.hasAttribute('data-ui-audit-critical') ||
              element.matches('.ui-button--primary, .button-link:not(.secondary-link)'),
          )
          .filter((element) => !element.closest(intentionalOverlaySelectors.join(',')));
        for (const element of criticalInteractive) {
          if (overlay.contains(element)) continue;
          const rect = element.getBoundingClientRect();
          if (rect.bottom <= 0 || rect.top >= viewportHeight || !overlaps(rect, overlayRect))
            continue;
          addIssue(
            'UI-AUDIT-FIXED-COLLISION',
            'collision',
            'HIGH',
            element,
            `interactive control intersects fixed ${overlaySelector}`,
          );
        }
      }

      return {
        viewport: { width: viewportWidth, height: viewportHeight },
        scroll: { x: window.scrollX, y: window.scrollY },
        issues,
      };
    },
    {
      checkTouchTargets: options.checkTouchTargets ?? false,
      minTouchTarget: options.minTouchTarget ?? 44,
      fixedOverlaySelectors: options.fixedOverlaySelectors ?? ['#appBottomNav'],
      intentionalOverlaySelectors: options.intentionalOverlaySelectors ?? [
        '.app-quick-add-layer',
        '.app-more-layer',
      ],
      interactiveSelector: AUDITABLE_INTERACTIVE_SELECTOR,
    },
  );
}

export async function expectUiAuditClean(
  page: Page,
  context: string,
  options: UiAuditOptions = {},
): Promise<UiAuditReport> {
  const report = await collectUiAudit(page, options);
  expect(report.issues, `${context}\n${JSON.stringify(report.issues, null, 2)}`).toEqual([]);
  return report;
}

export async function attachUiAuditReport(
  testInfo: TestInfo,
  label: string,
  report: UiAuditReport,
): Promise<void> {
  await testInfo.attach(label, {
    body: JSON.stringify(report, null, 2),
    contentType: 'application/json',
  });
}
