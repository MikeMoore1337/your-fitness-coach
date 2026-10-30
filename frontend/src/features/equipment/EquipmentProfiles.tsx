import { useId, useState } from 'react';
import { createPortal } from 'react-dom';
import { ApiError } from '../../shared/api/client';
import { equipmentLabels, localizedEquipmentList } from '../../shared/equipmentLabels';
import { Card, SegmentedControl } from '../../shared/ui/common';
import { AppLink } from '../../shared/navigation/router';
import { useRuntimeCapabilities } from '../../shared/runtime/runtime';
import { useOnlineStatus } from '../../shared/ui/OnlineStatus';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import {
  equipmentChoices,
  useEquipmentProfiles,
  type EquipmentId,
  type EquipmentProfile,
  type EquipmentProfiles,
} from './equipmentProfileState';
import './equipmentProfiles.css';

type Editor = {
  id: string | null;
  name: string;
  equipment: EquipmentId[];
  base: EquipmentProfiles;
  latest?: EquipmentProfile | null;
};

export function EquipmentProfilesManager({ label = 'Настроить' }: { label?: string }) {
  return (
    <AppLink className="text-button" to="/app?section=profile&view=equipment">
      {label}
    </AppLink>
  );
}

export function EquipmentProfilesWorkspace() {
  const { query, save, active } = useEquipmentProfiles();
  const online = useOnlineStatus();
  const [editor, setEditor] = useState<Editor | null>(null);
  const [deleting, setDeleting] = useState(false);
  const titleId = useId();
  const conflict = save.error instanceof ApiError && save.error.status === 409;
  const beginEdit = (profile?: EquipmentProfile) => {
    if (!query.data) return;
    setEditor({
      id: profile?.id ?? null,
      name: profile?.name ?? '',
      equipment: [...(profile?.equipment_ids ?? [])],
      base: query.data,
    });
    setDeleting(false);
    save.reset();
  };
  const submit = async () => {
    if (!editor || !editor.name.trim()) return;
    const profiles = editor.base.profiles ?? [];
    const next = { id: editor.id, name: editor.name.trim(), equipment_ids: editor.equipment };
    try {
      await save.mutateAsync({
        revision: editor.base.revision,
        active_profile_id: editor.base.active_profile_id,
        profiles: editor.id
          ? profiles.map((item) => (item.id === editor.id ? next : item))
          : [...profiles, next],
      });
      setEditor(null);
    } catch {
      // The form remains visible for retry or conflict resolution.
    }
  };
  const remove = async () => {
    if (!editor?.id) return;
    try {
      await save.mutateAsync({
        revision: editor.base.revision,
        active_profile_id:
          editor.base.active_profile_id === editor.id ? null : editor.base.active_profile_id,
        profiles: (editor.base.profiles ?? []).filter((item) => item.id !== editor.id),
      });
      setEditor(null);
      setDeleting(false);
    } catch {
      // The form remains visible for retry or conflict resolution.
    }
  };
  return (
    <>
      <header className="card hero-card equipment-profiles__hero">
        <div>
          <span className="eyebrow">Профиль / оборудование</span>
          <h1 id={titleId}>
            {editor ? (editor.id ? 'Изменить профиль' : 'Новый профиль') : 'Профили оборудования'}
          </h1>
          <p className="muted">
            {editor
              ? 'Укажите оборудование, которое действительно доступно в этом месте.'
              : 'Выберите набор для поиска упражнений. Программы, веса и история не изменятся.'}
          </p>
        </div>
      </header>
      <section className="card equipment-profiles__panel" aria-labelledby={titleId}>
        <AppLink className="text-button" to="/app?section=profile">
          К профилю
        </AppLink>
        <AppLink className="text-button" to="/app?section=catalog">
          К упражнениям
        </AppLink>
        {!online && (
          <p role="status" className="equipment-profiles__notice">
            Нет подключения. Изменения пока не сохранены на сервере.
          </p>
        )}
        {query.isLoading && <p role="status">Загружаем профили…</p>}
        {query.isError && !query.data && (
          <div role="alert">
            <p>Не удалось загрузить профили.</p>
            <button type="button" className="secondary" onClick={() => void query.refetch()}>
              Повторить
            </button>
          </div>
        )}
        {save.isError && (
          <div role="alert" className="equipment-profiles__notice">
            <strong>
              {conflict
                ? 'Профили изменились на другом устройстве'
                : 'Не удалось сохранить профиль'}
            </strong>
            <p>
              {conflict
                ? 'Ваши изменения остались на экране. Загрузите актуальные данные и проверьте их перед сохранением.'
                : 'Проверьте подключение и повторите. Ваши изменения остаются на экране.'}
            </p>
            {conflict && (
              <button
                type="button"
                className="secondary"
                onClick={async () => {
                  const result = await query.refetch();
                  if (result.data && editor)
                    setEditor({
                      ...editor,
                      base: result.data,
                      latest: editor.id
                        ? (result.data.profiles?.find((item) => item.id === editor.id) ?? null)
                        : undefined,
                    });
                  if (result.data) save.reset();
                }}
              >
                Загрузить актуальные данные
              </button>
            )}
          </div>
        )}
        {query.data &&
          (editor ? (
            <form
              className="equipment-profiles__editor"
              onSubmit={(event) => {
                event.preventDefault();
                void submit();
              }}
            >
              {editor.latest !== undefined && (
                <div className="equipment-profiles__notice" role="status">
                  {editor.latest ? (
                    <>
                      <strong>Сейчас на сервере: {editor.latest.name}</strong>
                      <p>
                        {editor.latest.equipment_ids?.length
                          ? localizedEquipmentList(editor.latest.equipment_ids)
                          : 'Дополнительное оборудование не выбрано'}
                      </p>
                      <p>Сравните с вашими изменениями перед сохранением.</p>
                    </>
                  ) : (
                    <>
                      <strong>Профиль уже удалён на другом устройстве.</strong>
                      <p>Ваши изменения остались в форме.</p>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => setEditor({ ...editor, id: null, latest: undefined })}
                      >
                        Сохранить как новый профиль
                      </button>
                    </>
                  )}
                </div>
              )}
              <label className="field">
                <span>Название профиля</span>
                <input
                  value={editor.name}
                  maxLength={64}
                  required
                  placeholder="Например, Дом или Поездка"
                  onChange={(event) => setEditor({ ...editor, name: event.target.value })}
                />
              </label>
              <div>
                <h3>Что доступно?</h3>
                <p className="muted">
                  Собственный вес доступен всегда. Отметьте также скамью, турник и другие
                  необходимые принадлежности.
                </p>
              </div>
              <div className="equipment-profiles__grid">
                {equipmentChoices.map((id) => (
                  <label
                    key={id}
                    data-yfc-choice="compact"
                    className={`equipment-profiles__choice${id === 'cardio' ? ' equipment-profiles__choice--wide' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={editor.equipment.includes(id)}
                      onChange={(event) =>
                        setEditor({
                          ...editor,
                          equipment: event.target.checked
                            ? [...editor.equipment, id]
                            : editor.equipment.filter((item) => item !== id),
                        })
                      }
                    />
                    <span>{equipmentLabels[id]}</span>
                  </label>
                ))}
              </div>
              <div className="equipment-profiles__actions">
                <button
                  type="submit"
                  disabled={
                    !online ||
                    save.isPending ||
                    !editor.name.trim() ||
                    Boolean(
                      editor.id &&
                      !(editor.base.profiles ?? []).some((item) => item.id === editor.id),
                    )
                  }
                >
                  {save.isPending ? 'Сохраняем…' : 'Сохранить'}
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => {
                    setEditor(null);
                    save.reset();
                  }}
                >
                  Отмена
                </button>
              </div>
              {editor.id &&
                (deleting ? (
                  <div className="equipment-profiles__notice">
                    <p>Удалить профиль «{editor.name}»? Это не изменит программы и историю.</p>
                    <button
                      type="button"
                      className="btn-danger"
                      disabled={!online || save.isPending}
                      onClick={() => void remove()}
                    >
                      Подтвердить удаление
                    </button>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => setDeleting(false)}
                    >
                      Отмена
                    </button>
                  </div>
                ) : (
                  <button type="button" className="text-button" onClick={() => setDeleting(true)}>
                    Удалить профиль
                  </button>
                ))}
            </form>
          ) : (
            <div className="equipment-profiles__list">
              <h3>Мои профили</h3>
              <p className="muted">Активный профиль используется только для вас.</p>
              <label className="equipment-profiles__row" data-yfc-choice="compact">
                <input
                  type="radio"
                  name={`${titleId}-active`}
                  checked={!active}
                  disabled={!online || save.isPending}
                  onChange={() => save.mutate({ ...query.data!, active_profile_id: null })}
                />
                <span>
                  <strong>Без профиля</strong>
                  <small>Показывать все упражнения</small>
                </span>
              </label>
              {(query.data.profiles ?? []).map((profile) => (
                <div className="equipment-profiles__row" key={profile.id}>
                  <label data-yfc-choice="compact">
                    <input
                      type="radio"
                      name={`${titleId}-active`}
                      checked={profile.id === active?.id}
                      disabled={!online || save.isPending}
                      onChange={() =>
                        save.mutate({ ...query.data!, active_profile_id: profile.id })
                      }
                    />
                    <span>
                      <strong>{profile.name}</strong>
                      <small>
                        {profile.equipment_ids?.length
                          ? localizedEquipmentList(profile.equipment_ids)
                          : 'Дополнительное оборудование не выбрано'}
                      </small>
                    </span>
                  </label>
                  <button type="button" className="text-button" onClick={() => beginEdit(profile)}>
                    Изменить
                  </button>
                </div>
              ))}
              <button
                type="button"
                disabled={(query.data.profiles?.length ?? 0) >= 20}
                onClick={() => beginEdit()}
              >
                Создать профиль
              </button>
            </div>
          ))}
      </section>
    </>
  );
}

export function EquipmentProfilesCard() {
  const { canMutateProfile } = useRuntimeCapabilities();
  if (!canMutateProfile) return null;
  return (
    <Card
      className="equipment-profiles-card"
      title="Профили оборудования"
      description="Сохраняйте наборы для поиска упражнений."
    >
      <EquipmentProfilesManager label="Управлять профилями" />
    </Card>
  );
}

export function EquipmentProfileSelect({ enabled = true }: { enabled?: boolean }) {
  const { query, save, active } = useEquipmentProfiles(enabled);
  const online = useOnlineStatus();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState('');
  const titleId = useId();
  const panelRef = useModalA11y<HTMLDivElement>(open, () => setOpen(false));
  if (!enabled) return null;
  if (query.isLoading) return <p role="status">Загружаем профиль оборудования…</p>;
  if (query.isError && !query.data)
    return (
      <div role="alert">
        Не удалось загрузить профиль оборудования.{' '}
        <button type="button" className="text-button" onClick={() => void query.refetch()}>
          Повторить
        </button>
      </div>
    );
  if (!query.data) return null;
  return (
    <div className="equipment-profile-context">
      <div>
        <small>Профиль оборудования</small>
        <strong>{active?.name ?? 'Без профиля'}</strong>
      </div>
      <button
        type="button"
        className="text-button"
        aria-label="Изменить профиль оборудования"
        disabled={!online}
        onClick={() => {
          setSelected(query.data?.active_profile_id ?? '');
          save.reset();
          setOpen(true);
        }}
      >
        Изменить
      </button>
      {!online && (
        <small className="equipment-profile-context__status" role="status">
          Нет подключения. Показано последнее загруженное состояние.
        </small>
      )}
      {online && query.isError && (
        <small className="equipment-profile-context__status" role="status">
          Не удалось обновить профиль. Показаны последние данные.{' '}
          <button type="button" className="text-button" onClick={() => void query.refetch()}>
            Повторить
          </button>
        </small>
      )}
      {open &&
        createPortal(
          <div
            className="modal app-section--design-v2 equipment-profile-dialog"
            data-equipment-profile-dialog=""
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
          >
            <div className="modal__backdrop" aria-hidden="true" onClick={() => setOpen(false)} />
            <div
              className="modal__panel card equipment-profile-dialog__panel"
              ref={panelRef}
              tabIndex={-1}
            >
              <h2 id={titleId}>Выбрать профиль</h2>
              <p className="muted">
                Профиль меняет список вариантов. Программа и тренировка останутся без изменений.
              </p>
              {save.isError && (
                <div role="alert" className="equipment-profiles__notice">
                  <p>Профиль не изменён. Обновите данные и повторите выбор.</p>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      save.reset();
                      void query.refetch();
                    }}
                  >
                    Обновить данные
                  </button>
                </div>
              )}
              <div className="equipment-profile-dialog__list">
                <label data-yfc-choice="compact">
                  <input
                    type="radio"
                    name={`${titleId}-select`}
                    checked={!selected}
                    onChange={() => setSelected('')}
                  />
                  <span>
                    <strong>Без профиля</strong>
                    <small>Показывать все упражнения</small>
                  </span>
                </label>
                {(query.data.profiles ?? []).map((item) => (
                  <label key={item.id} data-yfc-choice="compact">
                    <input
                      type="radio"
                      name={`${titleId}-select`}
                      checked={selected === item.id}
                      onChange={() => setSelected(item.id)}
                    />
                    <span>
                      <strong>{item.name}</strong>
                      <small>
                        {item.equipment_ids?.length
                          ? localizedEquipmentList(item.equipment_ids)
                          : 'Дополнительное оборудование не выбрано'}
                      </small>
                    </span>
                  </label>
                ))}
              </div>
              <div className="equipment-profiles__actions">
                <button
                  type="button"
                  disabled={
                    !online ||
                    save.isPending ||
                    Boolean(
                      selected && !(query.data.profiles ?? []).some((item) => item.id === selected),
                    )
                  }
                  onClick={async () => {
                    try {
                      await save.mutateAsync({
                        ...query.data!,
                        active_profile_id: selected || null,
                      });
                      setOpen(false);
                    } catch {
                      /* The choice stays open for retry. */
                    }
                  }}
                >
                  {save.isPending ? 'Сохраняем…' : 'Выбрать'}
                </button>
                <button type="button" className="secondary" onClick={() => setOpen(false)}>
                  Отмена
                </button>
              </div>
              <small className="muted">Профили можно изменить в настройках.</small>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}

export function AvailabilityControl({
  value,
  onChange,
}: {
  value: 'available' | 'all';
  onChange: (value: 'available' | 'all') => void;
}) {
  return (
    <SegmentedControl
      ariaLabel="Доступность упражнений"
      value={value}
      onChange={(next) => onChange(next as 'available' | 'all')}
      options={[
        { value: 'available', label: 'Доступное' },
        { value: 'all', label: 'Все упражнения' },
      ]}
    />
  );
}
