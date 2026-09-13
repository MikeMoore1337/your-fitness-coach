import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { ExternalFood, Food, FoodBarcodeLookup } from '../../shared/api/types';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { Button, Field, Input, LoadingState } from '../../shared/ui/common';
import { startBarcodeScanner, type BarcodeScannerSession } from './barcodeScanner';
import { isValidGtin } from './nutritionFoodUtils';

const TOUCH_CAMERA_QUERY = '(hover: none) and (pointer: coarse)';
const documentIsHidden = () => document.visibilityState === 'hidden';

function providerMessage(status: FoodBarcodeLookup['provider_status']): string | null {
  if (status === 'disabled')
    return 'Внешний каталог не подключён. Локальный поиск и свои продукты доступны.';
  if (status === 'rate_limited')
    return 'Внешний каталог временно занят. Можно добавить продукт вручную.';
  if (status === 'unavailable')
    return 'Внешний каталог временно недоступен. Можно добавить продукт вручную.';
  return null;
}

function ExternalBarcodeResult({ food }: { food: ExternalFood }) {
  return (
    <article className="nutrition-external-result">
      <div>
        <span className="eyebrow">Внешний каталог</span>
        <h3>{food.name}</h3>
        <p>
          {food.brand || 'Без бренда'} ·{' '}
          {Number(food.energy_kcal_per_100g).toLocaleString('ru-RU', { maximumFractionDigits: 1 })}{' '}
          ккал / 100 г
        </p>
      </div>
      <p>
        Эта карточка доступна только для сверки. Чтобы сохранить данные в личный каталог, создайте
        свой продукт и проверьте значения на упаковке.
      </p>
      <div className="nutrition-external-result__links">
        <a href={food.source.source_url} target="_blank" rel="noreferrer">
          Открыть источник
        </a>
        <a href={food.source.license_url} target="_blank" rel="noreferrer">
          {food.source.attribution} · {food.source.license}
        </a>
      </div>
    </article>
  );
}

export function BarcodeLookup({
  onCreate,
  onScanLabel,
  onSelect,
}: {
  onCreate: (barcode: string) => void;
  onScanLabel?: (barcode: string) => void;
  onSelect: (food: Food) => void;
}) {
  const [barcode, setBarcode] = useState('');
  const [validationError, setValidationError] = useState('');
  const [cameraError, setCameraError] = useState('');
  const [cameraStarting, setCameraStarting] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scannerStrategy, setScannerStrategy] = useState<BarcodeScannerSession['strategy'] | null>(
    null,
  );
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const scannerRef = useRef<BarcodeScannerSession | null>(null);
  const cameraStartRef = useRef(false);
  const cameraAttemptRef = useRef(0);
  const cameraSupported = Boolean(navigator.mediaDevices?.getUserMedia);
  const [touchCameraSurface, setTouchCameraSurface] = useState(
    () => window.matchMedia?.(TOUCH_CAMERA_QUERY).matches ?? false,
  );
  const cameraFirst = cameraSupported && touchCameraSurface;

  useEffect(() => {
    const media = window.matchMedia?.(TOUCH_CAMERA_QUERY);
    if (!media) return;
    const sync = () => setTouchCameraSurface(media.matches);
    sync();
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, []);

  const stopCamera = useCallback((updateState = true) => {
    cameraAttemptRef.current += 1;
    scannerRef.current?.stop();
    scannerRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    cameraStartRef.current = false;
    if (updateState) {
      setCameraStarting(false);
      setScanning(false);
      setScannerStrategy(null);
    }
  }, []);
  useEffect(() => () => stopCamera(false), [stopCamera]);
  useEffect(() => {
    const stopInBackground = () => {
      if (documentIsHidden()) stopCamera();
    };
    document.addEventListener('visibilitychange', stopInBackground);
    return () => document.removeEventListener('visibilitychange', stopInBackground);
  }, [stopCamera]);

  const lookup = useMutation({
    mutationFn: (value: string) =>
      api<FoodBarcodeLookup>(`/api/v1/nutrition/foods/barcode/${value}`),
    onSuccess: (response) => {
      trackProductEvent({
        name:
          response.local_item || response.external_item
            ? 'nutrition_label_scan_barcode_hit'
            : 'nutrition_label_scan_barcode_miss',
        surface: productEventSurface(),
      });
      if (response.source === 'local') {
        trackProductEvent({
          name: 'yfc_food_catalog_local_hit',
          surface: productEventSurface(),
        });
      } else if (response.source === 'external') {
        trackProductEvent({
          name: 'yfc_food_catalog_external_fallback',
          surface: productEventSurface(),
        });
      }
    },
  });
  const submitBarcode = (value: string) => {
    const normalized = value.replace(/\s+/g, '');
    if (!isValidGtin(normalized)) {
      setValidationError('Проверьте цифры штрихкода GTIN-8, UPC-A, EAN-13 или GTIN-14.');
      return;
    }
    setValidationError('');
    setBarcode(normalized);
    lookup.mutate(normalized);
  };
  const startCamera = async () => {
    if (cameraStartRef.current || !navigator.mediaDevices?.getUserMedia) {
      setCameraError(
        'Сканирование камерой не поддерживается в этом браузере. Введите код вручную.',
      );
      return;
    }
    cameraStartRef.current = true;
    const attempt = cameraAttemptRef.current + 1;
    cameraAttemptRef.current = attempt;
    setCameraStarting(true);
    setCameraError('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } },
        audio: false,
      });
      if (cameraAttemptRef.current !== attempt || documentIsHidden()) {
        stream.getTracks().forEach((track) => track.stop());
        if (cameraAttemptRef.current === attempt) stopCamera();
        return;
      }
      streamRef.current = stream;
      const video = videoRef.current;
      if (!video) return stopCamera();
      video.srcObject = stream;
      await video.play();
      if (
        cameraAttemptRef.current !== attempt ||
        streamRef.current !== stream ||
        documentIsHidden()
      ) {
        if (cameraAttemptRef.current === attempt) stopCamera();
        return;
      }
      const scanner = await startBarcodeScanner({
        stream,
        video,
        onDetected: (value) => {
          if (!isValidGtin(value)) return false;
          stopCamera();
          submitBarcode(value);
          return true;
        },
        onFatalError: () => {
          setCameraError(
            'Не удалось распознать код. Наведите камеру на штрихкод или введите его вручную.',
          );
          stopCamera();
        },
      });
      if (cameraAttemptRef.current !== attempt || streamRef.current !== stream) {
        scanner.stop();
        return;
      }
      scannerRef.current = scanner;
      cameraStartRef.current = false;
      setCameraStarting(false);
      setScannerStrategy(scanner.strategy);
      setScanning(true);
    } catch (error) {
      if (cameraAttemptRef.current !== attempt) return;
      const hadStream = Boolean(streamRef.current);
      stopCamera();
      const name = error instanceof DOMException ? error.name : '';
      setCameraError(
        hadStream
          ? 'Не удалось запустить распознавание. Введите штрихкод вручную или попробуйте снова.'
          : name === 'NotAllowedError' || name === 'SecurityError'
            ? 'Доступ к камере запрещён. Разрешите его в настройках браузера или введите код вручную.'
            : name === 'NotFoundError' || name === 'OverconstrainedError'
              ? 'Камера не найдена. Введите штрихкод вручную.'
              : 'Не удалось открыть камеру. Введите штрихкод вручную.',
      );
    }
  };
  const result = lookup.data;
  const providerFallback = result ? providerMessage(result.provider_status) : null;

  return (
    <div className="nutrition-barcode">
      <div className="nutrition-tools-heading">
        <div>
          <h3>Поиск по штрихкоду</h3>
          <p>Сначала проверим личный и локальный каталоги, затем — бесплатный внешний источник.</p>
        </div>
      </div>
      {cameraFirst && (
        <div className="nutrition-camera">
          <video
            ref={videoRef}
            muted
            playsInline
            className={scanning ? 'is-active' : ''}
            aria-label="Изображение с камеры"
          />
          {scanning ? (
            <Button type="button" variant="secondary" fullWidth onClick={() => stopCamera()}>
              Остановить камеру
            </Button>
          ) : (
            <Button
              type="button"
              fullWidth
              disabled={cameraStarting}
              onClick={() => void startCamera()}
            >
              {cameraStarting ? 'Запускаем камеру…' : 'Сканировать камерой'}
            </Button>
          )}
          {scanning && scannerStrategy && (
            <p className="nutrition-camera__status" role="status">
              {scannerStrategy === 'native'
                ? 'Камера активна. Наведите её на штрихкод.'
                : 'Камера активна. Код распознаётся на устройстве.'}
            </p>
          )}
          {cameraError && (
            <p className="nutrition-form-error" role="alert">
              {cameraError}
            </p>
          )}
        </div>
      )}
      <form
        className="nutrition-barcode__manual"
        onSubmit={(event) => {
          event.preventDefault();
          submitBarcode(barcode);
        }}
      >
        {cameraFirst && <p className="nutrition-barcode__manual-title">Или введите код вручную</p>}
        <Field
          label="Штрихкод"
          labelFor="nutrition-barcode-input"
          error={validationError}
          hint="8, 12, 13 или 14 цифр"
        >
          <div className="nutrition-barcode__input-row">
            <Input
              id="nutrition-barcode-input"
              inputMode="numeric"
              autoComplete="off"
              maxLength={14}
              value={barcode}
              onChange={(event) => {
                lookup.reset();
                setValidationError('');
                setBarcode(event.target.value.replace(/\D/g, ''));
              }}
              placeholder="3017620422003"
            />
            <Button
              className="nutrition-barcode__manual-submit"
              type="submit"
              variant={cameraFirst ? 'secondary' : 'primary'}
              disabled={lookup.isPending}
            >
              {lookup.isPending ? 'Ищем…' : 'Найти'}
            </Button>
          </div>
        </Field>
      </form>
      {touchCameraSurface && !cameraSupported && (
        <p className="nutrition-camera-unavailable">
          Сканирование камерой недоступно — введите цифры со штрихкода вручную.
        </p>
      )}
      {lookup.isPending && <LoadingState label="Проверяем каталоги…" />}
      {lookup.error && (
        <div className="nutrition-provider-fallback" role="alert">
          <strong>Не удалось выполнить поиск.</strong>
          <span>
            Дневник и локальные продукты продолжают работать. Попробуйте снова или создайте свой
            продукт.
          </span>
        </div>
      )}
      {result?.status === 'found' && result.local_item && (
        <div className="nutrition-barcode__found">
          <strong>{result.local_item.name}</strong>
          <span>
            {result.local_item.brand || 'Локальный каталог'} ·{' '}
            {Number(result.local_item.energy_kcal_per_100g).toLocaleString('ru-RU', {
              maximumFractionDigits: 1,
            })}{' '}
            ккал / 100 г
          </span>
          {result.local_item.canonical_complete === false && (
            <span>Карточка заполнена не полностью — сверить данные можно по фото этикетки.</span>
          )}
          <div className="nutrition-barcode__result-actions">
            {result.local_item.canonical_complete === false && onScanLabel && (
              <Button type="button" onClick={() => onScanLabel(result.barcode)}>
                Распознать по фото
              </Button>
            )}
            <Button
              type="button"
              variant={result.local_item.canonical_complete === false ? 'secondary' : 'primary'}
              onClick={() => onSelect(result.local_item!)}
            >
              Выбрать продукт
            </Button>
          </div>
        </div>
      )}
      {result?.status === 'found' && result.external_item && (
        <>
          <ExternalBarcodeResult food={result.external_item} />
          <Button type="button" variant="secondary" onClick={() => onCreate(result.barcode)}>
            Создать свой продукт
          </Button>
        </>
      )}
      {result?.status === 'not_found' && (
        <div className="nutrition-provider-fallback">
          <strong>Продукт не найден</strong>
          <span>
            {providerFallback || 'Проверьте код или добавьте продукт по данным с упаковки.'}
          </span>
          <div className="nutrition-barcode__result-actions">
            {onScanLabel && (
              <Button type="button" onClick={() => onScanLabel(result.barcode)}>
                Распознать по фото
              </Button>
            )}
            <Button type="button" variant="secondary" onClick={() => onCreate(result.barcode)}>
              Создать свой продукт
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
