import { createServer } from 'node:net';
import { writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { randomUUID } from 'node:crypto';
import { expect, firefox, type Page, type TestInfo } from '@playwright/test';

async function availableLoopbackPort(): Promise<number> {
  return await new Promise((resolve, reject) => {
    const server = createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (!address || typeof address === 'string') {
        server.close();
        reject(new Error('No loopback port for Firefox print verification'));
        return;
      }
      server.close((error) => (error ? reject(error) : resolve(address.port)));
    });
  });
}

type BiDiReply = { id?: number; type?: string; result?: unknown; error?: string; message?: string };

// Playwright's page.pdf() is Chromium-only. Use Firefox's native WebDriver BiDi
// print command against the same synthetic report, then inspect its PDF viewer.
export async function expectFirefoxWhitePrintPages(
  configureReport: (page: Page) => Promise<void>,
  testInfo: TestInfo,
) {
  const port = await availableLoopbackPort();
  const browser = await firefox.launch({
    args: [`--remote-debugging-port=${port}`],
    firefoxUserPrefs: { 'pdfjs.disabled': false },
  });
  let socket: WebSocket | undefined;
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const report = await context.newPage();
    await configureReport(report);
    await report.emulateMedia({ media: 'print' });
    const marker = `yfc-print-${randomUUID()}`;
    await report.evaluate((value) => {
      window.name = value;
    }, marker);

    socket = new WebSocket(`ws://127.0.0.1:${port}/session`);
    await new Promise<void>((resolve, reject) => {
      socket!.addEventListener('open', () => resolve(), { once: true });
      socket!.addEventListener('error', () => reject(new Error('Firefox BiDi connection failed')), {
        once: true,
      });
    });
    let id = 0;
    const pending = new Map<
      number,
      { resolve: (result: unknown) => void; reject: (error: Error) => void }
    >();
    socket.addEventListener('close', () => {
      for (const waiter of pending.values())
        waiter.reject(new Error('Firefox BiDi connection closed'));
      pending.clear();
    });
    socket.addEventListener('message', (event) => {
      const reply = JSON.parse(String(event.data)) as BiDiReply;
      const waiter = reply.id === undefined ? undefined : pending.get(reply.id);
      if (!waiter) return;
      pending.delete(reply.id!);
      if (reply.type === 'error')
        waiter.reject(new Error(`Firefox BiDi: ${reply.error}: ${reply.message}`));
      else waiter.resolve(reply.result);
    });
    const send = (method: string, params: object) =>
      new Promise<unknown>((resolve, reject) => {
        const requestId = ++id;
        pending.set(requestId, { resolve, reject });
        socket!.send(JSON.stringify({ id: requestId, method, params }));
      });

    await send('session.new', { capabilities: {} });
    const tree = (await send('browsingContext.getTree', {})) as {
      contexts: Array<{ context: string; url: string }>;
    };
    const targets = tree.contexts.filter((item) => item.url === report.url());
    expect(targets, 'Firefox print target must be the synthetic report').toHaveLength(1);
    const identity = (await send('script.evaluate', {
      expression: 'window.name',
      target: { context: targets[0]!.context },
      awaitPromise: false,
    })) as { result: { value: string } };
    expect(identity.result.value).toBe(marker);
    const result = (await send('browsingContext.print', {
      context: targets[0]!.context,
      background: true,
      page: { width: 21, height: 29.7 },
      margin: { top: 1.7, bottom: 1.9, left: 1.6, right: 1.6 },
    })) as { data: string };
    const pdf = Buffer.from(result.data, 'base64');
    expect(pdf.subarray(0, 4).toString()).toBe('%PDF');
    const file = testInfo.outputPath('firefox-progress-report.pdf');
    await writeFile(file, pdf);

    const viewer = await context.newPage();
    await viewer.goto(pathToFileURL(file).href);
    const pages = viewer.locator('.page');
    await expect(pages.first()).toBeVisible();
    const pageCount = await pages.count();
    expect(pageCount).toBeGreaterThan(0);
    for (let index = 0; index < pageCount; index++) {
      const page = pages.nth(index);
      await page.scrollIntoViewIfNeeded();
      const canvas = page.locator('canvas').first();
      await expect(canvas).toBeVisible();
      await expect(page.locator('.textLayer span').first()).toBeAttached();
      const pixels = await canvas.evaluate((element: HTMLCanvasElement) => {
        const drawing = element.getContext('2d');
        if (!drawing || element.width < 12 || element.height < 12)
          throw new Error('PDF page is not rendered');
        return {
          ratio: element.width / element.height,
          corners: [
            [5, 5],
            [element.width - 6, 5],
            [5, element.height - 6],
            [element.width - 6, element.height - 6],
          ].map(([x, y]) => Array.from(drawing.getImageData(x!, y!, 1, 1).data)),
        };
      });
      expect(Math.abs(pixels.ratio - 21 / 29.7)).toBeLessThan(0.005);
      expect(pixels.corners, `Firefox PDF page ${index + 1} must have white paper`).toEqual(
        Array.from({ length: 4 }, () => [255, 255, 255, 255]),
      );
    }
  } finally {
    socket?.close();
    await browser.close();
  }
}
