import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BarcodeLookup } from '../../../../src/features/nutrition/BarcodeLookup';

const apiMock = vi.hoisted(() => vi.fn());
const scannerMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/features/nutrition/barcodeScanner', () => ({
  startBarcodeScanner: scannerMock,
}));

const localFood = {
  id: 7,
  name: 'Овсяная каша',
  brand: null,
  barcode: '4006381333931',
  energy_kcal_per_100g: '420.00',
  protein_g_per_100g: '18.500',
  fat_g_per_100g: '12.000',
  carbs_g_per_100g: '54.000',
  fiber_g_per_100g: '7.000',
  standard_serving_amount: null,
  standard_serving_unit: null,
  standard_serving_weight_g: null,
  food_type: 'system' as const,
  is_favorite: false,
  last_used_at: null,
  created_at: '2026-08-01T07:00:00Z',
  updated_at: '2026-08-01T07:00:00Z',
};

function renderLookup(onSelect = vi.fn(), onScanLabel = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const result = render(
    <QueryClientProvider client={client}>
      <BarcodeLookup onCreate={vi.fn()} onScanLabel={onScanLabel} onSelect={onSelect} />
    </QueryClientProvider>,
  );
  return { ...result, onSelect, onScanLabel };
}

function installTouchCamera(getUserMedia?: () => Promise<MediaStream>) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches: query === '(hover: none) and (pointer: coarse)',
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: getUserMedia ? { getUserMedia: vi.fn(getUserMedia) } : undefined,
  });
}

describe('BarcodeLookup camera fallback', () => {
  const originalMediaDevices = navigator.mediaDevices;
  const originalVisibility = Object.getOwnPropertyDescriptor(document, 'visibilityState');

  beforeEach(() => {
    apiMock.mockReset();
    scannerMock.mockReset();
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    Object.defineProperty(globalThis, 'BarcodeDetector', { configurable: true, value: undefined });
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: originalMediaDevices,
    });
    Object.defineProperty(globalThis, 'BarcodeDetector', { configurable: true, value: undefined });
    if (originalVisibility) Object.defineProperty(document, 'visibilityState', originalVisibility);
    else Reflect.deleteProperty(document, 'visibilityState');
  });

  it('offers a lazy local decoder without BarcodeDetector and selects the scanned local food', async () => {
    const trackStop = vi.fn();
    const scannerStop = vi.fn();
    const stream = { getTracks: () => [{ stop: trackStop }] } as unknown as MediaStream;
    installTouchCamera(async () => stream);
    let detect: ((value: string) => boolean) | undefined;
    scannerMock.mockImplementation(async (options: { onDetected: (value: string) => boolean }) => {
      detect = options.onDetected;
      return { strategy: 'zxing', stop: scannerStop };
    });
    apiMock.mockResolvedValue({
      barcode: '4006381333931',
      status: 'found',
      source: 'local',
      local_item: localFood,
      external_item: null,
      provider_status: 'not_needed',
      provider_statuses: [],
    });
    const { onSelect } = renderLookup();

    fireEvent.click(screen.getByRole('button', { name: 'Сканировать камерой' }));
    expect(
      await screen.findByText('Камера активна. Код распознаётся на устройстве.'),
    ).toBeVisible();
    act(() => expect(detect?.('4006381333931')).toBe(true));
    fireEvent.click(await screen.findByRole('button', { name: 'Выбрать продукт' }));

    expect(apiMock).toHaveBeenCalledWith('/api/v1/nutrition/foods/barcode/4006381333931');
    expect(onSelect).toHaveBeenCalledWith(localFood);
    expect(scannerStop).toHaveBeenCalledOnce();
    expect(trackStop).toHaveBeenCalledOnce();
  });

  it('keeps manual entry available when camera permission is denied before decoder loading', async () => {
    installTouchCamera(async () => {
      throw new DOMException('Denied', 'NotAllowedError');
    });
    renderLookup();

    fireEvent.click(screen.getByRole('button', { name: 'Сканировать камерой' }));

    expect(
      await screen.findByText(
        'Доступ к камере запрещён. Разрешите его в настройках браузера или введите код вручную.',
      ),
    ).toBeVisible();
    expect(screen.getByRole('textbox', { name: 'Штрихкод' })).toBeEnabled();
    expect(scannerMock).not.toHaveBeenCalled();
  });

  it('stops decoder and MediaStream when the document enters background', async () => {
    const trackStop = vi.fn();
    const scannerStop = vi.fn();
    const stream = { getTracks: () => [{ stop: trackStop }] } as unknown as MediaStream;
    installTouchCamera(async () => stream);
    scannerMock.mockResolvedValue({ strategy: 'native', stop: scannerStop });
    renderLookup();
    fireEvent.click(screen.getByRole('button', { name: 'Сканировать камерой' }));
    await screen.findByText('Камера активна. Наведите её на штрихкод.');

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    act(() => document.dispatchEvent(new Event('visibilitychange')));

    await waitFor(() => expect(scannerStop).toHaveBeenCalledOnce());
    expect(trackStop).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: 'Сканировать камерой' })).toBeEnabled();
  });

  it('discards a pending camera stream if the document enters background', async () => {
    let resolveStream: ((stream: MediaStream) => void) | undefined;
    const pendingStream = new Promise<MediaStream>((resolve) => {
      resolveStream = resolve;
    });
    const trackStop = vi.fn();
    const stream = { getTracks: () => [{ stop: trackStop }] } as unknown as MediaStream;
    installTouchCamera(() => pendingStream);
    renderLookup();

    fireEvent.click(screen.getByRole('button', { name: 'Сканировать камерой' }));
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await act(async () => resolveStream?.(stream));

    await waitFor(() => expect(trackStop).toHaveBeenCalledOnce());
    expect(scannerMock).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Сканировать камерой' })).toBeEnabled();
  });

  it('discards stale scanner startup after a newer camera attempt becomes active', async () => {
    const firstTrackStop = vi.fn();
    const secondTrackStop = vi.fn();
    const firstStream = {
      getTracks: () => [{ stop: firstTrackStop }],
    } as unknown as MediaStream;
    const secondStream = {
      getTracks: () => [{ stop: secondTrackStop }],
    } as unknown as MediaStream;
    let mediaAttempt = 0;
    installTouchCamera(async () => (mediaAttempt++ === 0 ? firstStream : secondStream));
    let resolveFirstScanner:
      ((scanner: { strategy: 'native'; stop: () => void }) => void) | undefined;
    const firstScanner = new Promise<{ strategy: 'native'; stop: () => void }>((resolve) => {
      resolveFirstScanner = resolve;
    });
    const firstScannerStop = vi.fn();
    const secondScannerStop = vi.fn();
    scannerMock
      .mockImplementationOnce(() => firstScanner)
      .mockResolvedValueOnce({ strategy: 'zxing', stop: secondScannerStop });
    renderLookup();

    fireEvent.click(screen.getByRole('button', { name: 'Сканировать камерой' }));
    await waitFor(() => expect(scannerMock).toHaveBeenCalledOnce());
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    fireEvent.click(screen.getByRole('button', { name: 'Сканировать камерой' }));
    expect(
      await screen.findByText('Камера активна. Код распознаётся на устройстве.'),
    ).toBeVisible();

    await act(async () => resolveFirstScanner?.({ strategy: 'native', stop: firstScannerStop }));
    await waitFor(() => expect(firstScannerStop).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole('button', { name: 'Остановить камеру' }));

    expect(secondScannerStop).toHaveBeenCalledOnce();
    expect(firstTrackStop).toHaveBeenCalledOnce();
    expect(secondTrackStop).toHaveBeenCalledOnce();
  });

  it('keeps manual GTIN lookup primary when camera capture is unavailable', async () => {
    installTouchCamera();
    apiMock.mockResolvedValue({
      barcode: '3017620422003',
      status: 'not_found',
      source: null,
      local_item: null,
      external_item: null,
      provider_status: 'disabled',
      provider_statuses: [],
    });
    renderLookup();

    expect(screen.queryByRole('button', { name: 'Сканировать камерой' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: 'Штрихкод' }), {
      target: { value: '3017620422003' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Найти' }));

    expect(await screen.findByText('Продукт не найден')).toBeVisible();
    expect(screen.getByRole('textbox', { name: 'Штрихкод' })).toHaveValue('3017620422003');
  });

  it('offers the label scanner for an incomplete local product without another provider lookup', async () => {
    const incompleteLocalFood = {
      ...localFood,
      canonical_complete: false,
      catalog_quality: 'community_unverified' as const,
    };
    apiMock.mockResolvedValue({
      barcode: incompleteLocalFood.barcode,
      status: 'found',
      source: 'local',
      local_item: incompleteLocalFood,
      external_item: null,
      provider_status: 'not_needed',
      provider_statuses: [],
    });
    const { onScanLabel } = renderLookup();

    fireEvent.change(screen.getByRole('textbox', { name: 'Штрихкод' }), {
      target: { value: incompleteLocalFood.barcode },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Найти' }));

    expect(await screen.findByText(/Карточка заполнена не полностью/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Распознать по фото' }));
    expect(onScanLabel).toHaveBeenCalledWith(incompleteLocalFood.barcode);
    expect(apiMock).toHaveBeenCalledTimes(1);
    expect(apiMock).toHaveBeenCalledWith(
      `/api/v1/nutrition/foods/barcode/${incompleteLocalFood.barcode}`,
    );
  });
});
