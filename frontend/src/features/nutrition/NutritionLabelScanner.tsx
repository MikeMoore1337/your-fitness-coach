import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, api } from '../../shared/api/client';
import type {
  Food,
  NutritionLabelConfirmResponse,
  NutritionLabelDraft,
} from '../../shared/api/types';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { usePersistentState } from '../../shared/storage';
import { Button } from '../../shared/ui/common';
import { nutritionLabelDraftStorageKey } from '../../shared/userScopedStorage';
import {
  NutritionLabelReview,
  nutritionLabelPrefillFromValues,
  type NutritionLabelPrefill,
  type NutritionLabelReviewValues,
} from './NutritionLabelReview';

const MAX_IMAGE_BYTES = 8_388_608;
const MAX_IMAGE_PIXELS = 20_000_000;
const ALLOWED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

type CaptureStatus = 'capture' | 'preparing' | 'preview' | 'recognizing' | 'review';
type ScannerMode = 'catalog' | 'prefill';

const LOCAL_ERROR_MESSAGES: Record<string, string> = {
  camera_unavailable: 'Камера недоступна. Выберите фото из галереи.',
  unsupported_mime: 'Выберите фото в формате JPEG, PNG или WebP.',
  invalid_image: 'Файл не похож на допустимое изображение. Выберите другое фото.',
  decode_failed: 'Фото не удалось прочитать. Переснимите этикетку.',
  oversized_image: 'Фото слишком большое. Выберите снимок с меньшим размером.',
  retake_required: 'Нужен более чёткий снимок этикетки крупным планом.',
};

type NutritionLabelScannerProps = {
  mode?: 'catalog' | 'prefill';
  userId?: number | 'anonymous';
  initialName?: string;
  initialBrand?: string;
  initialBarcode?: string;
  onCancel: () => void;
  onManualFallback?: () => void;
  onSaved?: (food: Food, response: NutritionLabelConfirmResponse) => void | Promise<void>;
  onPrefilled?: (prefill: NutritionLabelPrefill) => void;
};

type NutritionLabelDraftPointer = {
  draftId: string;
  revision: number;
  mode?: ScannerMode;
};

function isDraftPointer(value: unknown): value is NutritionLabelDraftPointer {
  return Boolean(
    value &&
    typeof value === 'object' &&
    'draftId' in value &&
    typeof value.draftId === 'string' &&
    value.draftId.length > 0 &&
    'revision' in value &&
    typeof value.revision === 'number' &&
    Number.isInteger(value.revision) &&
    value.revision >= 1 &&
    (!('mode' in value) || value.mode === 'catalog' || value.mode === 'prefill'),
  );
}

function draftPointerKey(pointer: NutritionLabelDraftPointer): string {
  return `${pointer.draftId}:${pointer.revision}:${pointer.mode ?? 'catalog'}`;
}

function draftPointerMatchesMode(pointer: NutritionLabelDraftPointer, mode: ScannerMode): boolean {
  return pointer.mode ? pointer.mode === mode : mode === 'catalog';
}

function randomRequestId(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function errorCode(error: unknown): string | null {
  if (error instanceof ApiError) {
    const body = error.body;
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null;
    const code = detail && typeof detail === 'object' && 'code' in detail ? detail.code : null;
    return typeof code === 'string' ? code : null;
  }
  return error instanceof Error ? error.message : null;
}

const UNAVAILABLE_ERROR_CODES = new Set([
  'feature_disabled',
  'local_ocr_unavailable',
  'local_ocr_timeout',
  'local_ocr_failed',
]);

function recognitionOutcome(error: unknown): 'retake' | 'unavailable' | null {
  const code = errorCode(error);
  if (code === 'retake_required') return 'retake';
  if (
    UNAVAILABLE_ERROR_CODES.has(code ?? '') ||
    (error instanceof ApiError && error.status === 0)
  ) {
    return 'unavailable';
  }
  return null;
}

function safeApiMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const code = errorCode(error);
    const messages: Record<string, string> = {
      feature_disabled: 'Сканирование этикетки сейчас недоступно. Можно добавить продукт вручную.',
      local_ocr_unavailable: 'Распознавание временно недоступно. Введите данные вручную.',
      local_ocr_timeout: 'Распознавание не завершилось вовремя. Попробуйте ещё раз.',
      local_ocr_failed: 'Не удалось распознать этикетку. Попробуйте другой снимок.',
      local_ocr_output_too_large: 'Фото содержит слишком много текста. Снимите только этикетку.',
      draft_expired: 'Черновик истёк. Начните сканирование заново.',
      draft_not_active: 'Черновик уже закрыт. Начните сканирование заново.',
      stale_draft_revision: 'Черновик устарел. Начните сканирование заново.',
      contribution_conflict:
        'В каталоге уже есть другая версия этого продукта. Данные не перезаписаны.',
      duplicate_barcode: 'Продукт с этим штрихкодом уже есть в каталоге.',
      private_food_conflict: 'Такой личный продукт уже существует.',
      incomplete_required_facts: 'Заполните обязательные значения перед подтверждением.',
      ambiguous_basis: 'Уточните основу расчёта: 100 г, 100 мл или порция.',
      invalid_content_length: 'Фото не удалось передать. Выберите снимок меньшего размера.',
      request_body_too_large: 'Фото слишком большое. Выберите снимок меньшего размера.',
    };
    Object.assign(messages, LOCAL_ERROR_MESSAGES);
    if (code && messages[code]) return messages[code];
    if (error.status === 0) return error.message;
    if (error.status === 403) return messages.feature_disabled ?? 'Сканирование сейчас недоступно.';
    if (error.status >= 500) return 'Сервис временно недоступен. Попробуйте ещё раз.';
  }
  if (error instanceof DOMException) {
    if (error.name === 'NotAllowedError' || error.name === 'SecurityError') {
      return 'Доступ к камере запрещён. Выберите фото или разрешите камеру в настройках.';
    }
    if (error.name === 'NotFoundError' || error.name === 'OverconstrainedError') {
      return 'Камера не найдена. Выберите фото из галереи.';
    }
  }
  if (error instanceof Error && error.message === 'offline') {
    return 'Нет соединения. Подключитесь к интернету и попробуйте снова.';
  }
  if (error instanceof Error) {
    const localMessage = LOCAL_ERROR_MESSAGES[error.message];
    if (localMessage) return localMessage;
  }
  return 'Не удалось обработать фото. Попробуйте ещё раз или введите данные вручную.';
}

function imageExtension(name: string): string {
  const extension = name.split('.').pop()?.toLowerCase();
  return extension && /^[a-z0-9]{1,5}$/.test(extension) ? extension : 'jpg';
}

type ImageSource = {
  width: number;
  height: number;
  draw: (context: CanvasRenderingContext2D, width: number, height: number) => void;
  close: () => void;
};

async function openImage(file: File): Promise<ImageSource> {
  if (typeof createImageBitmap === 'function') {
    try {
      const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
      return {
        width: bitmap.width,
        height: bitmap.height,
        draw: (context, width, height) => context.drawImage(bitmap, 0, 0, width, height),
        close: () => bitmap.close(),
      };
    } catch {
      // Some older WebViews expose createImageBitmap without image orientation support.
    }
  }
  const url = URL.createObjectURL(file);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const element = new Image();
      element.onload = () => resolve(element);
      element.onerror = () => reject(new Error('decode_failed'));
      element.src = url;
    });
    return {
      width: image.naturalWidth,
      height: image.naturalHeight,
      draw: (context, width, height) => context.drawImage(image, 0, 0, width, height),
      close: () => URL.revokeObjectURL(url),
    };
  } catch (error) {
    URL.revokeObjectURL(url);
    throw error;
  }
}

async function canvasBlob(canvas: HTMLCanvasElement, type: 'image/jpeg'): Promise<Blob> {
  const qualities = [0.92, 0.84, 0.76];
  for (const quality of qualities) {
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, type, quality));
    if (blob && blob.size <= MAX_IMAGE_BYTES) return blob;
  }
  throw new Error('oversized_image');
}

async function prepareImage(file: File): Promise<File> {
  if (!ALLOWED_IMAGE_TYPES.has(file.type)) throw new Error('unsupported_mime');
  if (file.size === 0) throw new Error('invalid_image');
  const source = await openImage(file);
  try {
    if (!source.width || !source.height) throw new Error('decode_failed');
    if (source.width < 64 || source.height < 64) throw new Error('retake_required');
    const scale = Math.min(1, Math.sqrt(MAX_IMAGE_PIXELS / (source.width * source.height)));
    const width = Math.max(1, Math.round(source.width * scale));
    const height = Math.max(1, Math.round(source.height * scale));
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d', { alpha: false });
    if (!context) throw new Error('decode_failed');
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = 'high';
    source.draw(context, width, height);
    const blob = await canvasBlob(canvas, 'image/jpeg');
    return new File([blob], `${file.name.replace(/\.[^.]+$/, '') || 'nutrition-label'}.jpg`, {
      type: 'image/jpeg',
      lastModified: file.lastModified || Date.now(),
    });
  } finally {
    source.close();
  }
}

async function videoStill(video: HTMLVideoElement): Promise<File> {
  if (!video.videoWidth || !video.videoHeight) throw new Error('retake_required');
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const context = canvas.getContext('2d', { alpha: false });
  if (!context) throw new Error('decode_failed');
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  const blob = await canvasBlob(canvas, 'image/jpeg');
  return new File([blob], 'nutrition-label-camera.jpg', {
    type: 'image/jpeg',
    lastModified: Date.now(),
  });
}

function isDocumentHidden(): boolean {
  return document.visibilityState === 'hidden';
}

export function NutritionLabelScanner({
  mode = 'catalog',
  userId = 'anonymous',
  initialName = '',
  initialBrand = '',
  initialBarcode = '',
  onCancel,
  onManualFallback,
  onSaved,
  onPrefilled,
}: NutritionLabelScannerProps) {
  const [storedDraft, setStoredDraft, clearStoredDraft] =
    usePersistentState<NutritionLabelDraftPointer | null>(
      nutritionLabelDraftStorageKey(userId),
      null,
    );
  const [status, setStatus] = useState<CaptureStatus>(() =>
    storedDraft && isDraftPointer(storedDraft) && draftPointerMatchesMode(storedDraft, mode)
      ? 'preparing'
      : 'capture',
  );
  const [file, setFile] = useState<File | null>(null);
  const [draft, setDraft] = useState<NutritionLabelDraft | null>(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [cameraError, setCameraError] = useState('');
  const [cameraStarting, setCameraStarting] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [offline, setOffline] = useState(() => !navigator.onLine);
  const [submitError, setSubmitError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const cameraAttemptRef = useRef(0);
  const cameraStartingRef = useRef(false);
  const recognitionKeyRef = useRef<string | null>(null);
  const recognitionInFlightRef = useRef(false);
  const recognitionOperationRef = useRef(0);
  const mountedRef = useRef(true);
  const recoveredPointerRef = useRef<string | null>(null);
  const previousUserIdRef = useRef<number | 'anonymous'>(userId);
  const userGenerationRef = useRef(0);
  const cameraUserIdRef = useRef<number | 'anonymous'>(userId);
  const correctionReportedRef = useRef(false);

  const reportCorrection = useCallback(() => {
    if (correctionReportedRef.current) return;
    correctionReportedRef.current = true;
    trackProductEvent({
      name: 'nutrition_label_scan_correction_occurred',
      surface: productEventSurface(),
    });
  }, []);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    trackProductEvent({ name: 'nutrition_label_scan_started', surface: productEventSurface() });
  }, []);

  useEffect(() => {
    if (previousUserIdRef.current === userId) return;
    previousUserIdRef.current = userId;
    userGenerationRef.current += 1;
    recognitionOperationRef.current += 1;
    recognitionInFlightRef.current = false;
    recoveredPointerRef.current = null;
    setDraft(null);
    setFile(null);
    setStatus('capture');
    setErrorMessage('');
    setSubmitError('');
    recognitionKeyRef.current = null;
    correctionReportedRef.current = false;
  }, [userId]);

  useEffect(() => {
    if (!storedDraft) return;
    if (!isDraftPointer(storedDraft)) {
      clearStoredDraft();
      return;
    }
    if (!draftPointerMatchesMode(storedDraft, mode)) return;
    const pointerKey = draftPointerKey(storedDraft);
    if (recoveredPointerRef.current === pointerKey) return;
    const generation = userGenerationRef.current;
    recoveredPointerRef.current = pointerKey;
    let active = true;
    setStatus('preparing');
    void api<NutritionLabelDraft>(
      `/api/v1/nutrition/label-scans/${encodeURIComponent(storedDraft.draftId)}`,
      { timeoutMs: 8_000 },
    )
      .then((response) => {
        if (!active || !mountedRef.current || generation !== userGenerationRef.current) return;
        if (response.status !== 'draft') {
          clearStoredDraft();
          recoveredPointerRef.current = null;
          setDraft(null);
          setStatus('capture');
          setErrorMessage('Сохранённый черновик больше недоступен. Начните сканирование заново.');
          return;
        }
        setDraft(response);
        setStatus('review');
        setSubmitError('');
      })
      .catch((error: unknown) => {
        if (!active || !mountedRef.current || generation !== userGenerationRef.current) return;
        clearStoredDraft();
        recoveredPointerRef.current = null;
        setDraft(null);
        setStatus('capture');
        setErrorMessage(safeApiMessage(error));
      });
    return () => {
      active = false;
    };
  }, [clearStoredDraft, mode, storedDraft]);

  const stopCamera = useCallback((updateState = true) => {
    cameraAttemptRef.current += 1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    cameraStartingRef.current = false;
    if (updateState) {
      setCameraStarting(false);
      setCameraActive(false);
    }
  }, []);

  useEffect(() => {
    if (cameraUserIdRef.current === userId) return;
    cameraUserIdRef.current = userId;
    stopCamera();
  }, [stopCamera, userId]);

  useEffect(() => {
    const setOnline = () => setOffline(false);
    const setOfflineState = () => setOffline(true);
    window.addEventListener('online', setOnline);
    window.addEventListener('offline', setOfflineState);
    return () => {
      window.removeEventListener('online', setOnline);
      window.removeEventListener('offline', setOfflineState);
    };
  }, []);

  useEffect(() => {
    const stopInBackground = () => {
      if (isDocumentHidden()) stopCamera();
    };
    document.addEventListener('visibilitychange', stopInBackground);
    window.addEventListener('pagehide', stopInBackground);
    return () => {
      document.removeEventListener('visibilitychange', stopInBackground);
      window.removeEventListener('pagehide', stopInBackground);
      stopCamera(false);
    };
  }, [stopCamera]);

  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const choosePreparedFile = async (candidate: File) => {
    if (recognitionInFlightRef.current) return;
    const generation = userGenerationRef.current;
    stopCamera();
    setErrorMessage('');
    setSubmitError('');
    setDraft(null);
    recognitionKeyRef.current = null;
    correctionReportedRef.current = false;
    setStatus('preparing');
    clearStoredDraft();
    try {
      const prepared = await prepareImage(candidate);
      if (!mountedRef.current || generation !== userGenerationRef.current) return;
      setFile(prepared);
      setStatus('preview');
      trackProductEvent({
        name: 'nutrition_label_scan_capture_selected',
        surface: productEventSurface(),
      });
    } catch (error) {
      if (!mountedRef.current || generation !== userGenerationRef.current) return;
      setFile(null);
      setStatus('capture');
      setErrorMessage(safeApiMessage(error));
      const outcome = recognitionOutcome(error);
      if (outcome === 'retake') {
        trackProductEvent({
          name: 'nutrition_label_scan_result_retake',
          surface: productEventSurface(),
        });
      } else if (outcome === 'unavailable') {
        trackProductEvent({
          name: 'nutrition_label_scan_result_unavailable',
          surface: productEventSurface(),
        });
      }
      trackProductEvent({
        name: 'nutrition_label_scan_recognition_failed',
        surface: productEventSurface(),
      });
    }
  };

  const startCamera = async () => {
    if (cameraStartingRef.current || cameraActive) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError('Камера недоступна в этом браузере. Выберите фото из галереи.');
      trackProductEvent({
        name: 'nutrition_label_scan_result_unavailable',
        surface: productEventSurface(),
      });
      return;
    }
    cameraStartingRef.current = true;
    const attempt = cameraAttemptRef.current + 1;
    const generation = userGenerationRef.current;
    cameraAttemptRef.current = attempt;
    setCameraStarting(true);
    setCameraError('');
    setErrorMessage('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        audio: false,
      });
      if (
        cameraAttemptRef.current !== attempt ||
        generation !== userGenerationRef.current ||
        isDocumentHidden()
      ) {
        stream.getTracks().forEach((track) => track.stop());
        if (cameraAttemptRef.current === attempt) {
          cameraStartingRef.current = false;
          setCameraStarting(false);
        }
        return;
      }
      streamRef.current = stream;
      const video = videoRef.current;
      if (!video) throw new Error('camera_unavailable');
      video.srcObject = stream;
      await video.play();
      if (
        cameraAttemptRef.current !== attempt ||
        streamRef.current !== stream ||
        generation !== userGenerationRef.current ||
        isDocumentHidden()
      ) {
        stream.getTracks().forEach((track) => track.stop());
        if (cameraAttemptRef.current === attempt) {
          cameraStartingRef.current = false;
          setCameraStarting(false);
        }
        return;
      }
      setCameraStarting(false);
      setCameraActive(true);
      cameraStartingRef.current = false;
    } catch (error) {
      if (cameraAttemptRef.current !== attempt || generation !== userGenerationRef.current) return;
      stopCamera();
      setCameraError(safeApiMessage(error));
      trackProductEvent({
        name: 'nutrition_label_scan_result_unavailable',
        surface: productEventSurface(),
      });
    }
  };

  const captureFromCamera = async () => {
    if (cameraStarting || !cameraActive || !videoRef.current) return;
    const generation = userGenerationRef.current;
    try {
      const still = await videoStill(videoRef.current);
      if (generation !== userGenerationRef.current) return;
      await choosePreparedFile(still);
    } catch (error) {
      if (generation !== userGenerationRef.current) return;
      const outcome = recognitionOutcome(error);
      if (outcome === 'retake') {
        trackProductEvent({
          name: 'nutrition_label_scan_result_retake',
          surface: productEventSurface(),
        });
      } else if (outcome === 'unavailable') {
        trackProductEvent({
          name: 'nutrition_label_scan_result_unavailable',
          surface: productEventSurface(),
        });
      }
      setErrorMessage(safeApiMessage(error));
      setStatus('capture');
    }
  };

  const recognize = async () => {
    if (!file || recognitionInFlightRef.current) return;
    if (offline || !navigator.onLine) {
      setErrorMessage('Нет соединения. Подключитесь к интернету и попробуйте снова.');
      trackProductEvent({
        name: 'nutrition_label_scan_result_unavailable',
        surface: productEventSurface(),
      });
      return;
    }
    recognitionInFlightRef.current = true;
    const generation = userGenerationRef.current;
    const operation = recognitionOperationRef.current + 1;
    recognitionOperationRef.current = operation;
    setStatus('recognizing');
    setErrorMessage('');
    setSubmitError('');
    const requestId = recognitionKeyRef.current ?? randomRequestId('nutrition-label-scan');
    recognitionKeyRef.current = requestId;
    const form = new FormData();
    form.append('image', file, file.name || `nutrition-label.${imageExtension(file.name)}`);
    try {
      const response = await api<NutritionLabelDraft>('/api/v1/nutrition/label-scans', {
        method: 'POST',
        body: form,
        headers: { 'Idempotency-Key': requestId },
        timeoutMs: 20_000,
      });
      if (
        !mountedRef.current ||
        generation !== userGenerationRef.current ||
        operation !== recognitionOperationRef.current
      )
        return;
      setDraft(response);
      correctionReportedRef.current = false;
      setStoredDraft({ draftId: response.draft_id, revision: response.revision, mode });
      recoveredPointerRef.current = draftPointerKey({
        draftId: response.draft_id,
        revision: response.revision,
        mode,
      });
      setStatus('review');
      trackProductEvent({
        name: 'nutrition_label_scan_recognition_succeeded',
        surface: productEventSurface(),
      });
      trackProductEvent({
        name: 'nutrition_label_scan_result_success',
        surface: productEventSurface(),
      });
    } catch (error) {
      if (
        !mountedRef.current ||
        generation !== userGenerationRef.current ||
        operation !== recognitionOperationRef.current
      )
        return;
      setStatus('preview');
      setErrorMessage(safeApiMessage(error));
      const outcome = recognitionOutcome(error);
      if (outcome === 'retake') {
        trackProductEvent({
          name: 'nutrition_label_scan_result_retake',
          surface: productEventSurface(),
        });
      } else if (outcome === 'unavailable') {
        trackProductEvent({
          name: 'nutrition_label_scan_result_unavailable',
          surface: productEventSurface(),
        });
      }
      trackProductEvent({
        name: 'nutrition_label_scan_recognition_failed',
        surface: productEventSurface(),
      });
    } finally {
      if (operation === recognitionOperationRef.current) recognitionInFlightRef.current = false;
    }
  };

  const cancelDraft = async (currentDraft: NutritionLabelDraft) => {
    try {
      await api<void>(
        `/api/v1/nutrition/label-scans/${encodeURIComponent(currentDraft.draft_id)}/cancel?revision=${currentDraft.revision}`,
        { method: 'POST', timeoutMs: 8_000 },
      );
    } catch {
      // The draft is short-lived and owner-scoped; expiration is safe when cancellation races it.
    }
  };

  const handleCancel = () => {
    stopCamera();
    if (draft?.status === 'draft') void cancelDraft(draft);
    clearStoredDraft();
    recoveredPointerRef.current = null;
    if (draft)
      trackProductEvent({ name: 'nutrition_label_scan_cancelled', surface: productEventSurface() });
    onCancel();
  };

  const handleManualFallback = () => {
    stopCamera();
    if (draft?.status === 'draft') void cancelDraft(draft);
    clearStoredDraft();
    recoveredPointerRef.current = null;
    if (draft)
      trackProductEvent({ name: 'nutrition_label_scan_cancelled', surface: productEventSurface() });
    (onManualFallback ?? onCancel)();
  };

  const submitReview = async (values: NutritionLabelReviewValues) => {
    if (!draft || isSubmitting) return;
    const generation = userGenerationRef.current;
    setIsSubmitting(true);
    setSubmitError('');
    trackProductEvent({ name: 'nutrition_label_scan_reviewed', surface: productEventSurface() });
    try {
      if (mode === 'prefill') {
        await cancelDraft(draft);
        if (!mountedRef.current || generation !== userGenerationRef.current) return;
        clearStoredDraft();
        recoveredPointerRef.current = null;
        onPrefilled?.(nutritionLabelPrefillFromValues(values));
        trackProductEvent({
          name: 'nutrition_label_scan_confirmed',
          surface: productEventSurface(),
        });
        return;
      }
      const response = await api<NutritionLabelConfirmResponse>(
        `/api/v1/nutrition/label-scans/${encodeURIComponent(draft.draft_id)}/confirm`,
        {
          method: 'POST',
          body: { revision: draft.revision, ...values },
          timeoutMs: 15_000,
        },
      );
      if (!mountedRef.current || generation !== userGenerationRef.current) return;
      clearStoredDraft();
      recoveredPointerRef.current = null;
      trackProductEvent({ name: 'nutrition_label_scan_confirmed', surface: productEventSurface() });
      trackProductEvent({
        name:
          response.visibility === 'share_to_yfc_catalog'
            ? 'nutrition_label_catalog_saved_shared'
            : 'nutrition_label_catalog_saved_private',
        surface: productEventSurface(),
      });
      await onSaved?.(response.food, response);
    } catch (error) {
      if (!mountedRef.current) return;
      setSubmitError(safeApiMessage(error));
    } finally {
      if (generation === userGenerationRef.current) setIsSubmitting(false);
    }
  };

  if (status === 'review' && draft) {
    return (
      <NutritionLabelReview
        draft={draft}
        mode={mode}
        initialName={initialName}
        initialBrand={initialBrand}
        initialBarcode={initialBarcode}
        isSubmitting={isSubmitting}
        submitError={submitError}
        onCancel={handleCancel}
        onManualFallback={handleManualFallback}
        onCorrection={reportCorrection}
        onSubmit={(values) => void submitReview(values)}
      />
    );
  }

  if (
    storedDraft &&
    isDraftPointer(storedDraft) &&
    draftPointerMatchesMode(storedDraft, mode) &&
    !draft &&
    status === 'preparing'
  ) {
    return (
      <div className="nutrition-label-scanner" aria-label="Восстановление черновика этикетки">
        <div className="nutrition-label-scanner__intro">
          <span className="eyebrow">Продолжение</span>
          <h3>Восстанавливаем проверку</h3>
          <p>Ищем незавершённый черновик. Фото и распознанный текст не хранятся в браузере.</p>
        </div>
        <div className="nutrition-label-scanner__progress" role="status">
          <strong>Загружаем черновик…</strong>
          <span>Если срок действия истёк, можно начать новое сканирование.</span>
        </div>
        <div className="nutrition-editor__actions nutrition-label-scanner__actions">
          <Button type="button" variant="secondary" onClick={handleManualFallback}>
            Продолжить вручную
          </Button>
          <Button type="button" variant="ghost" onClick={handleCancel}>
            Отмена
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="nutrition-label-scanner" aria-label="Сканирование пищевой этикетки">
      <div className="nutrition-label-scanner__intro">
        <span className="eyebrow">{mode === 'prefill' ? 'Заполнение формы' : 'Новый продукт'}</span>
        <h3>Сканировать пищевую ценность</h3>
        <p>
          Снимите одну этикетку целиком: текст должен быть крупным, ровным и без бликов. Фото
          обрабатывается локально на сервере и не сохраняется после распознавания.
        </p>
      </div>

      <div className="nutrition-label-scanner__capture" aria-live="polite">
        <video
          ref={videoRef}
          className={cameraActive ? 'is-active' : ''}
          muted
          playsInline
          aria-label="Предпросмотр камеры"
        />
        {cameraActive ? (
          <div className="nutrition-label-scanner__camera-actions">
            <Button type="button" fullWidth onClick={() => void captureFromCamera()}>
              Сделать снимок
            </Button>
            <Button type="button" variant="secondary" fullWidth onClick={() => stopCamera()}>
              Остановить камеру
            </Button>
          </div>
        ) : (
          <Button
            type="button"
            fullWidth
            disabled={cameraStarting}
            onClick={() => void startCamera()}
          >
            {cameraStarting ? 'Запрашиваем доступ…' : 'Открыть камеру'}
          </Button>
        )}
        <p className="nutrition-label-scanner__hint">
          Камера используется только после нажатия. Если она недоступна, выберите готовое фото.
        </p>
        {cameraError && (
          <p className="nutrition-form-error" role="alert">
            {cameraError}
          </p>
        )}
      </div>

      <div className="nutrition-label-scanner__picker">
        <span className="nutrition-label-scanner__picker-title">Или выберите фото</span>
        <label className="nutrition-label-scanner__file-control">
          <span>Открыть галерею</span>
          <input
            ref={inputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            onChange={(event) => {
              const selected = event.target.files?.[0];
              event.currentTarget.value = '';
              if (selected) void choosePreparedFile(selected);
            }}
          />
        </label>
      </div>

      {status === 'preparing' && (
        <p className="nutrition-label-scanner__status">Подготавливаем фото…</p>
      )}
      {offline && (
        <p className="nutrition-provider-fallback" role="status">
          Нет соединения. Фото останется только в текущем окне — после восстановления сети нажмите
          «Распознать» ещё раз.
        </p>
      )}
      {previewUrl && status === 'preview' && (
        <div className="nutrition-label-scanner__preview">
          <img src={previewUrl} alt="Выбранное фото пищевой этикетки" />
          <div className="nutrition-label-scanner__preview-actions">
            <Button type="button" fullWidth disabled={offline} onClick={() => void recognize()}>
              {offline ? 'Нет соединения' : 'Распознать'}
            </Button>
            <Button
              type="button"
              variant="secondary"
              fullWidth
              onClick={() => {
                trackProductEvent({
                  name: 'nutrition_label_scan_result_retake',
                  surface: productEventSurface(),
                });
                setFile(null);
                setStatus('capture');
                setErrorMessage('');
                recognitionKeyRef.current = null;
              }}
            >
              Переснять
            </Button>
          </div>
        </div>
      )}
      {status === 'recognizing' && (
        <div className="nutrition-label-scanner__progress" role="status">
          <strong>Распознаём этикетку…</strong>
          <span>Сначала подготавливаем фото, затем проверяем основу и пищевые значения.</span>
        </div>
      )}
      {errorMessage && (
        <div className="nutrition-provider-fallback" role="alert">
          <strong>Не удалось распознать фото</strong>
          <span>{errorMessage}</span>
          {file && (
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                trackProductEvent({
                  name: 'nutrition_label_scan_retry',
                  surface: productEventSurface(),
                });
                void recognize();
              }}
              disabled={offline}
            >
              Повторить
            </Button>
          )}
        </div>
      )}
      <div className="nutrition-editor__actions nutrition-label-scanner__actions">
        <Button
          type="button"
          variant="secondary"
          onClick={handleManualFallback}
          disabled={status === 'recognizing'}
        >
          Продолжить вручную
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={handleCancel}
          disabled={status === 'recognizing'}
        >
          Отмена
        </Button>
      </div>
    </div>
  );
}
