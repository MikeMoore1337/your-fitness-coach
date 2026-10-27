import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../../app/AuthProvider';
import { AccountAvatar } from '../../shared/account/AccountIdentity';
import { api, ApiError } from '../../shared/api/client';
import type { User } from '../../shared/api/types';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Icon } from '../../shared/ui/Icon';
import { useModalA11y } from '../../shared/ui/useModalA11y';

const MAX_AVATAR_BYTES = 5 * 1024 * 1024;
const SUPPORTED_AVATAR_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

function userDisplayName(user: User): string {
  return user.profile?.full_name || user.first_name || user.username || 'Пользователь';
}

function selectedFileError(file: File): string | null {
  if (file.size > MAX_AVATAR_BYTES) return 'Файл больше 5 МБ. Выберите изображение поменьше.';
  if (file.type && !SUPPORTED_AVATAR_TYPES.has(file.type)) {
    return 'Поддерживаются только JPEG, PNG и WebP. HEIC, SVG и анимация не поддерживаются.';
  }
  return null;
}

export function AvatarSettings({ open, onClose }: { open: boolean; onClose(): void }) {
  const { updateUser, user } = useAuth();
  const { toast } = useFeedback();
  const inputRef = useRef<HTMLInputElement>(null);
  const deleteButtonRef = useRef<HTMLButtonElement>(null);
  const deleteCancelRef = useRef<HTMLButtonElement>(null);
  const deleteConfirmRef = useRef<HTMLButtonElement>(null);
  const deleteConfirmationWasOpenRef = useRef(false);
  const previewRef = useRef<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const blocking = saving || deleting;

  const clearSelection = () => {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    previewRef.current = null;
    setPreviewUrl(null);
    setSelectedFile(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  const closeDeleteConfirmation = () => {
    if (deleting) return;
    setConfirmDelete(false);
    setError(null);
  };

  const close = () => {
    if (blocking) return;
    if (confirmDelete) {
      closeDeleteConfirmation();
      return;
    }
    clearSelection();
    setError(null);
    onClose();
  };
  const panelRef = useModalA11y<HTMLDivElement>(open, close, '.avatar-editor__choose');

  useEffect(
    () => () => {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    },
    [],
  );

  useEffect(() => {
    if (confirmDelete) {
      deleteConfirmationWasOpenRef.current = true;
      deleteCancelRef.current?.focus();
      return;
    }
    if (!deleteConfirmationWasOpenRef.current) return;
    deleteConfirmationWasOpenRef.current = false;
    deleteButtonRef.current?.focus();
  }, [confirmDelete]);

  if (!open || !user) return null;

  const chooseFile = (file: File | null) => {
    setError(null);
    if (!file) return;
    const validationError = selectedFileError(file);
    if (validationError) {
      clearSelection();
      setError(validationError);
      return;
    }
    clearSelection();
    const objectUrl = URL.createObjectURL(file);
    previewRef.current = objectUrl;
    setPreviewUrl(objectUrl);
    setSelectedFile(file);
  };

  const saveAvatar = async () => {
    if (!selectedFile || saving) return;
    setSaving(true);
    setError(null);
    const formData = new FormData();
    formData.append('file', selectedFile, selectedFile.name);
    try {
      const current = await api<User>('/api/v1/me/avatar', {
        method: 'PUT',
        body: formData,
        timeoutMs: 20_000,
      });
      updateUser(current);
      clearSelection();
      toast('Аватар сохранён');
      onClose();
    } catch (reason) {
      setError(
        reason instanceof ApiError || reason instanceof Error
          ? reason.message
          : 'Не удалось сохранить аватар. Попробуйте снова.',
      );
    } finally {
      setSaving(false);
    }
  };

  const deleteAvatar = async () => {
    if (deleting) return;
    setDeleting(true);
    setError(null);
    try {
      const current = await api<User>('/api/v1/me/avatar', { method: 'DELETE' });
      updateUser(current);
      clearSelection();
      toast(
        current.photo_url
          ? 'Свой аватар удалён — снова показывается фото из способа входа'
          : 'Свой аватар удалён — снова показывается нейтральный emoji',
      );
      setConfirmDelete(false);
      onClose();
    } catch (reason) {
      setError(
        reason instanceof ApiError || reason instanceof Error
          ? reason.message
          : 'Не удалось удалить аватар. Попробуйте снова.',
      );
    } finally {
      setDeleting(false);
    }
  };

  const hasCustomAvatar = Boolean(user.custom_avatar);
  const sourceLabel = selectedFile
    ? 'Предпросмотр нового изображения'
    : hasCustomAvatar
      ? 'Используется свой аватар'
      : user.photo_url
        ? 'Используется фото из способа входа'
        : 'Используется нейтральный emoji';

  return (
    <div
      className="avatar-editor-layer"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div
        ref={panelRef}
        className="avatar-editor"
        role="dialog"
        aria-modal="true"
        aria-labelledby="avatar-editor-title"
        aria-describedby="avatar-editor-description"
        aria-busy={blocking || undefined}
        tabIndex={-1}
      >
        <header
          data-glass=""
          data-glass-variant="regular"
          className="avatar-editor__header"
          inert={confirmDelete}
        >
          <div>
            <span className="eyebrow">Настройка аккаунта</span>
            <h2 id="avatar-editor-title">Аватар</h2>
          </div>
          <button
            type="button"
            className="avatar-editor__close"
            aria-label="Закрыть редактор аватара"
            disabled={blocking}
            onClick={close}
          >
            <Icon name="close" />
          </button>
        </header>

        <div className="avatar-editor__content" inert={confirmDelete}>
          <div className="avatar-editor__preview">
            <AccountAvatar
              className="avatar-editor__avatar"
              customAvatarVersion={user.custom_avatar?.updated_at}
              name={userDisplayName(user)}
              photoUrl={user.photo_url}
              previewUrl={previewUrl}
            />
            <div>
              <strong>{sourceLabel}</strong>
              <p id="avatar-editor-description">
                JPEG, PNG или WebP до 5 МБ. Изображение будет обрезано по центру до квадрата без
                исходных metadata.
              </p>
            </div>
          </div>

          <input
            ref={inputRef}
            className="sr-only"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            aria-label="Выбрать изображение для аватара"
            onChange={(event) => chooseFile(event.target.files?.[0] ?? null)}
          />

          <div className="avatar-editor__media-actions">
            <button
              type="button"
              className="secondary avatar-editor__choose"
              disabled={blocking}
              onClick={() => inputRef.current?.click()}
            >
              {selectedFile
                ? 'Выбрать другое'
                : hasCustomAvatar
                  ? 'Заменить изображение'
                  : 'Выбрать изображение'}
            </button>

            {hasCustomAvatar && !selectedFile && (
              <button
                ref={deleteButtonRef}
                type="button"
                className="avatar-editor__delete"
                disabled={blocking}
                onClick={() => {
                  setError(null);
                  setConfirmDelete(true);
                }}
              >
                Удалить свой аватар
              </button>
            )}
          </div>

          {error && !confirmDelete && (
            <div className="avatar-editor__error" role="alert">
              <strong>Изменение не сохранено</strong>
              <span>{error}</span>
            </div>
          )}
        </div>

        {confirmDelete && (
          <div
            className="avatar-editor__delete-confirmation"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="avatar-delete-title"
            aria-describedby="avatar-delete-description"
            onKeyDown={(event) => {
              event.stopPropagation();
              if (event.key === 'Escape' && !deleting) {
                event.preventDefault();
                closeDeleteConfirmation();
                return;
              }
              if (event.key !== 'Tab') return;
              const first = deleteCancelRef.current;
              const last = deleteConfirmRef.current;
              if (!first || !last) return;
              if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
              } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
              }
            }}
          >
            <div>
              <strong id="avatar-delete-title">Удалить свой аватар?</strong>
              <p id="avatar-delete-description">
                Свой файл будет удалён. Фото из способа входа или emoji останется доступным.
              </p>
              {error && (
                <p className="avatar-editor__delete-error" role="alert">
                  {error}
                </p>
              )}
            </div>
            <div className="avatar-editor__delete-actions">
              <button
                ref={deleteCancelRef}
                type="button"
                className="secondary"
                disabled={deleting}
                onClick={closeDeleteConfirmation}
              >
                Отмена
              </button>
              <button
                ref={deleteConfirmRef}
                type="button"
                className="btn-danger"
                disabled={deleting}
                onClick={() => void deleteAvatar()}
              >
                {deleting ? 'Удаляем…' : error ? 'Повторить удаление' : 'Удалить'}
              </button>
            </div>
          </div>
        )}

        <footer className="avatar-editor__actions" inert={confirmDelete}>
          <button type="button" className="secondary" disabled={blocking} onClick={close}>
            Отмена
          </button>
          <button
            type="button"
            disabled={!selectedFile || blocking}
            onClick={() => void saveAvatar()}
          >
            {saving
              ? 'Сохраняем…'
              : error && selectedFile
                ? 'Повторить сохранение'
                : 'Сохранить аватар'}
          </button>
        </footer>
      </div>
    </div>
  );
}
