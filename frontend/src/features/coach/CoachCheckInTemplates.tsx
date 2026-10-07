import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type {
  CheckInTemplate,
  CheckInTemplateFieldCatalog,
  CheckInTemplateHistory,
  CheckInTemplateList,
  Client,
} from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';
import { clientDisplayName } from './coachWorkspace';

type FieldKey = 'recovery' | 'hunger' | 'training_load' | 'adherence_difficulty';
type Cadence = 'weekly' | 'biweekly' | 'monthly';

const cadenceLabels: Record<Cadence, string> = {
  weekly: 'Каждую неделю',
  biweekly: 'Раз в две недели',
  monthly: 'Раз в месяц',
};

function newIdempotencyKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

function fieldDefinitions(keys: FieldKey[], required: FieldKey[]) {
  return keys.map((key) => ({ key, required: required.includes(key) }));
}

function toggleField(
  keys: FieldKey[],
  required: FieldKey[],
  key: FieldKey,
  checked: boolean,
): { keys: FieldKey[]; required: FieldKey[] } {
  if (checked) return { keys: [...keys, key], required };
  return {
    keys: keys.filter((value) => value !== key),
    required: required.filter((value) => value !== key),
  };
}

function FieldPicker({
  catalog,
  keys,
  required,
  disabled = false,
  onChange,
}: {
  catalog: CheckInTemplateFieldCatalog[];
  keys: FieldKey[];
  required: FieldKey[];
  disabled?: boolean;
  onChange: (next: { keys: FieldKey[]; required: FieldKey[] }) => void;
}) {
  return (
    <fieldset className="coach-check-in-template__fields">
      <legend>Поля проверки</legend>
      {catalog.map((field) => {
        const key = field.key as FieldKey;
        const selected = keys.includes(key);
        return (
          <div className="coach-check-in-template__field" key={field.key}>
            <label>
              <input
                checked={selected}
                disabled={disabled}
                onChange={(event) =>
                  onChange(toggleField(keys, required, key, event.target.checked))
                }
                type="checkbox"
              />{' '}
              {field.label}
            </label>
            {selected && (
              <label className="coach-check-in-template__required">
                <input
                  checked={required.includes(key)}
                  disabled={disabled}
                  onChange={(event) =>
                    onChange({
                      keys,
                      required: event.target.checked
                        ? [...required, key]
                        : required.filter((value) => value !== key),
                    })
                  }
                  type="checkbox"
                />{' '}
                обязательно
              </label>
            )}
          </div>
        );
      })}
    </fieldset>
  );
}

function FieldSummary({ fields }: { fields: CheckInTemplateFieldCatalog[] }) {
  return (
    <ul className="coach-check-in-template__field-summary">
      {fields.map((field) => (
        <li key={field.key}>
          {field.label}
          {'required' in field && field.required ? ' · обязательно' : ' · по желанию'}
        </li>
      ))}
    </ul>
  );
}

export function CoachCheckInTemplates({
  clients,
  canManage = true,
}: {
  clients: Client[];
  canManage?: boolean;
}) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [cadence, setCadence] = useState<Cadence>('weekly');
  const [fieldKeys, setFieldKeys] = useState<FieldKey[]>(['recovery']);
  const [requiredFields, setRequiredFields] = useState<FieldKey[]>(['recovery']);
  const [assignmentClients, setAssignmentClients] = useState<Record<number, string>>({});
  const [versioningTemplate, setVersioningTemplate] = useState<number | null>(null);
  const [versionFields, setVersionFields] = useState<FieldKey[]>([]);
  const [versionRequired, setVersionRequired] = useState<FieldKey[]>([]);
  const [historyTemplate, setHistoryTemplate] = useState<number | null>(null);
  const templates = useQuery<CheckInTemplateList>({
    queryKey: queryKeys.trainer.checkInTemplates,
    queryFn: () => api<CheckInTemplateList>('/api/v1/coach/check-in-templates'),
  });
  const catalog = templates.data?.field_catalog ?? [];
  const activeClients = useMemo(
    () => clients.filter((client) => client.status === 'active' && client.id != null),
    [clients],
  );
  const history = useQuery<CheckInTemplateHistory>({
    queryKey: queryKeys.trainer.checkInTemplateHistory(historyTemplate ?? 0),
    queryFn: () =>
      api<CheckInTemplateHistory>(
        `/api/v1/coach/check-in-templates/${historyTemplate}/responses?limit=50`,
      ),
    enabled: historyTemplate != null,
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.trainer.checkInTemplates });
  };
  const create = useMutation({
    mutationFn: () =>
      api<CheckInTemplate>('/api/v1/coach/check-in-templates', {
        method: 'POST',
        headers: { 'Idempotency-Key': newIdempotencyKey('check-in-template') },
        body: {
          name,
          description: description || null,
          cadence,
          fields: fieldDefinitions(fieldKeys, requiredFields),
        },
      }),
    onSuccess: async () => {
      setName('');
      setDescription('');
      await refresh();
      toast('Шаблон проверки создан');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const state = useMutation({
    mutationFn: ({ template }: { template: CheckInTemplate }) =>
      api<CheckInTemplate>(`/api/v1/coach/check-in-templates/${template.id}`, {
        method: 'PATCH',
        body: { is_active: !template.is_active },
      }),
    onSuccess: async () => {
      await refresh();
      toast('Статус шаблона обновлён');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const version = useMutation({
    mutationFn: ({ templateId }: { templateId: number }) =>
      api(`/api/v1/coach/check-in-templates/${templateId}/versions`, {
        method: 'POST',
        headers: { 'Idempotency-Key': newIdempotencyKey('check-in-version') },
        body: { fields: fieldDefinitions(versionFields, versionRequired) },
      }),
    onSuccess: async () => {
      setVersioningTemplate(null);
      await refresh();
      toast('Новая версия шаблона создана');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const assign = useMutation({
    mutationFn: ({
      templateId,
      clientId,
      versionNumber,
    }: {
      templateId: number;
      clientId: number;
      versionNumber: number;
    }) =>
      api(`/api/v1/coach/check-in-templates/${templateId}/assignments`, {
        method: 'POST',
        headers: { 'Idempotency-Key': newIdempotencyKey('check-in-assignment') },
        body: { client_id: clientId, version: versionNumber },
      }),
    onSuccess: async () => {
      await refresh();
      toast('Проверка назначена клиенту');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  if (templates.isPending) return <LoadingState label="Загружаем шаблоны проверок…" />;
  if (templates.error) {
    return (
      <ErrorState
        message="Не удалось загрузить шаблоны проверок."
        retry={() => void templates.refetch()}
      />
    );
  }

  const items = templates.data?.items ?? [];
  return (
    <section className="coach-check-in-templates" data-testid="coach-check-in-templates">
      <Card
        className="coach-check-in-templates__create"
        collapsible={false}
        title="Шаблоны проверок"
        description="Соберите повторяемую проверку из утверждённых шкал. Ответы клиентов сохраняются в версии, в которой они были отправлены."
        actions={!canManage && <Badge tone="neutral">Только просмотр</Badge>}
      >
        <div className="coach-check-in-templates__form">
          <label className="field">
            <span>Название</span>
            <input
              className="ui-input"
              disabled={!canManage}
              maxLength={128}
              onChange={(event) => setName(event.target.value)}
              placeholder="Например, Самочувствие после недели"
              value={name}
            />
          </label>
          <label className="field">
            <span>Ритм</span>
            <select
              className="ui-input"
              disabled={!canManage}
              onChange={(event) => setCadence(event.target.value as Cadence)}
              value={cadence}
            >
              {Object.entries(cadenceLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="field coach-check-in-templates__description">
            <span>Подсказка клиенту · необязательно</span>
            <textarea
              className="ui-input"
              disabled={!canManage}
              maxLength={500}
              onChange={(event) => setDescription(event.target.value)}
              rows={2}
              value={description}
            />
          </label>
          <FieldPicker
            catalog={catalog}
            disabled={!canManage}
            keys={fieldKeys}
            required={requiredFields}
            onChange={({ keys, required }) => {
              setFieldKeys(keys);
              setRequiredFields(required);
            }}
          />
          <Button
            disabled={!canManage || !name.trim() || !fieldKeys.length || create.isPending}
            onClick={() => create.mutate()}
            type="button"
          >
            {create.isPending ? 'Создаём…' : 'Создать шаблон'}
          </Button>
        </div>
      </Card>

      {!items.length ? (
        <EmptyState
          title="Шаблонов пока нет"
          text="Создайте первую повторяемую проверку для клиентов."
        />
      ) : (
        <div className="coach-check-in-templates__list">
          {items.map((template) => {
            const currentVersion = template.current_version;
            const selectedClient = Number(assignmentClients[template.id] ?? 0);
            const isVersioning = versioningTemplate === template.id;
            return (
              <Card
                className="coach-check-in-template"
                collapsible={false}
                key={template.id}
                title={template.name}
                description={template.description ?? undefined}
                actions={
                  <Badge tone={template.is_active ? 'success' : 'neutral'}>
                    {template.is_active ? 'Активен' : 'Выключен'}
                  </Badge>
                }
              >
                <div className="coach-check-in-template__meta">
                  <span>{cadenceLabels[template.cadence as Cadence]}</span>
                  <span>Версия {currentVersion?.version ?? '—'}</span>
                </div>
                {currentVersion && <FieldSummary fields={currentVersion.fields ?? []} />}
                <div className="coach-check-in-template__actions">
                  <Button
                    disabled={!canManage || state.isPending}
                    onClick={() => state.mutate({ template })}
                    type="button"
                    variant="secondary"
                  >
                    {template.is_active ? 'Выключить' : 'Активировать'}
                  </Button>
                  <Button
                    disabled={!canManage || !currentVersion}
                    onClick={() => {
                      const fields = (currentVersion?.fields ?? []).map(
                        (field) => field.key as FieldKey,
                      );
                      const required = (currentVersion?.fields ?? [])
                        .filter((field) => field.required)
                        .map((field) => field.key as FieldKey);
                      setVersionFields(fields);
                      setVersionRequired(required);
                      setVersioningTemplate(template.id);
                    }}
                    type="button"
                    variant="secondary"
                  >
                    Новая версия
                  </Button>
                  <Button
                    onClick={() =>
                      setHistoryTemplate(historyTemplate === template.id ? null : template.id)
                    }
                    type="button"
                    variant="ghost"
                  >
                    {historyTemplate === template.id ? 'Скрыть ответы' : 'Ответы клиентов'}
                  </Button>
                </div>
                {isVersioning && (
                  <div className="coach-check-in-template__version-form">
                    <FieldPicker
                      catalog={catalog}
                      disabled={!canManage}
                      keys={versionFields}
                      required={versionRequired}
                      onChange={({ keys, required }) => {
                        setVersionFields(keys);
                        setVersionRequired(required);
                      }}
                    />
                    <Button
                      disabled={!canManage || !versionFields.length || version.isPending}
                      onClick={() => version.mutate({ templateId: template.id })}
                      type="button"
                    >
                      {version.isPending ? 'Сохраняем…' : 'Сохранить версию'}
                    </Button>
                  </div>
                )}
                {template.is_active && currentVersion && (
                  <div className="coach-check-in-template__assign">
                    <label className="field">
                      <span>Назначить клиенту</span>
                      <select
                        className="ui-input"
                        disabled={!canManage || assign.isPending}
                        onChange={(event) =>
                          setAssignmentClients((current) => ({
                            ...current,
                            [template.id]: event.target.value,
                          }))
                        }
                        value={assignmentClients[template.id] ?? ''}
                      >
                        <option value="">Выберите клиента</option>
                        {activeClients.map((client) => (
                          <option key={client.id} value={client.id ?? ''}>
                            {clientDisplayName(client)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <Button
                      disabled={!canManage || !selectedClient || assign.isPending}
                      onClick={() =>
                        assign.mutate({
                          templateId: template.id,
                          clientId: selectedClient,
                          versionNumber: currentVersion.version,
                        })
                      }
                      type="button"
                    >
                      {assign.isPending ? 'Назначаем…' : 'Назначить'}
                    </Button>
                  </div>
                )}
                {template.assignments?.length ? (
                  <div className="coach-check-in-template__assignments">
                    <strong>Назначения</strong>
                    {template.assignments.map((assignment) => (
                      <span key={assignment.id}>
                        {assignment.client_name} · v{assignment.version} · до{' '}
                        {assignment.next_due_on}
                      </span>
                    ))}
                  </div>
                ) : null}
                {historyTemplate === template.id && (
                  <div className="coach-check-in-template__history">
                    {history.isPending ? (
                      <LoadingState label="Загружаем ответы…" />
                    ) : history.error ? (
                      <ErrorState
                        message="История ответов временно недоступна."
                        retry={() => void history.refetch()}
                      />
                    ) : history.data?.items?.length ? (
                      history.data.items.map((response) => (
                        <article key={response.id}>
                          <strong>{response.client_name}</strong>
                          <span>
                            {response.submitted_at.slice(0, 10)} · v{response.version} ·{' '}
                            {Object.entries(response.values)
                              .map(([key, value]) => `${key}: ${value}`)
                              .join(' · ')}
                          </span>
                        </article>
                      ))
                    ) : (
                      <p className="muted">Ответов пока нет.</p>
                    )}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </section>
  );
}
