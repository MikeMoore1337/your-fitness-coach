import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CopyDiaryDialog } from '../../../../src/features/nutrition/CopyDiaryDialog';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());
vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));

const today = '2026-11-06';
const entry = {
  id: 41,
  food_name: 'Овсяная каша',
  amount: '100',
  amount_unit: 'g',
  weight_g: '100',
  entry_kind: 'food',
  nutrition_confidence: 'exact',
};
const result = { entries: [entry], replayed: false };
const error = (status: number) => Object.assign(new Error('private server detail'), { status });

function renderDialog(sourceDate = today) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  const dialog = (date: string) => (
    <QueryClientProvider client={client}>
      <FeedbackProvider>
        <CopyDiaryDialog
          subject={{ scope: 'day', sourceDate: date, label: 'Все записи' }}
          today={today}
          onClose={onClose}
        />
      </FeedbackProvider>
    </QueryClientProvider>
  );
  const view = render(dialog(sourceDate));
  return { ...view, onClose, client, changeSource: (date: string) => view.rerender(dialog(date)) };
}

function changeTarget(date: string) {
  fireEvent.change(screen.getByLabelText('Дата назначения'), { target: { value: date } });
}

function preview(token = 'preview-1', entries = [entry]) {
  return { preview_token: token, entries };
}

describe('CopyDiaryDialog day dates', () => {
  beforeEach(() => {
    apiMock.mockReset();
  });
  afterEach(cleanup);

  it('does not request a preview for today or a future date', async () => {
    apiMock.mockResolvedValue(preview());
    renderDialog();
    await act(async () => {});
    expect(apiMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Дата назначения')).toHaveValue('');
    expect(screen.getByText('Выберите дату, которая отличается от исходной.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
    changeTarget(today);
    await act(async () => {});
    expect(apiMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Дата назначения')).toHaveAttribute('aria-invalid', 'true');
    changeTarget('2026-11-07');
    await act(async () => {});
    expect(apiMock).not.toHaveBeenCalled();
    expect(screen.getByText('Выберите дату не позже сегодняшней.')).toBeVisible();
  });

  it('previews today to an earlier day and submits the same body and token', async () => {
    apiMock.mockImplementation(async (path: string) =>
      path.endsWith('/preview') ? preview() : result,
    );
    const { onClose } = renderDialog();
    changeTarget('2026-11-05');
    await screen.findByText('Овсяная каша');
    expect(apiMock).toHaveBeenCalledWith(
      '/api/v1/nutrition/diary/copy/day/preview',
      expect.objectContaining({ body: { source_date: today, target_date: '2026-11-05' } }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(apiMock).toHaveBeenLastCalledWith(
      '/api/v1/nutrition/diary/copy/day',
      expect.objectContaining({
        body: { source_date: today, target_date: '2026-11-05', preview_token: 'preview-1' },
        headers: { 'Idempotency-Key': expect.any(String) },
      }),
    );
  });

  it('previews a historical day to today, but not to itself', async () => {
    apiMock.mockResolvedValue(preview());
    renderDialog('2026-11-03');
    await screen.findByText('Овсяная каша');
    expect(apiMock).toHaveBeenCalledWith(
      expect.stringContaining('/preview'),
      expect.objectContaining({ body: { source_date: '2026-11-03', target_date: today } }),
    );
    changeTarget('2026-11-03');
    await act(async () => {});
    expect(apiMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
  });

  it('does not confirm an empty source day', async () => {
    apiMock.mockResolvedValue(preview('empty', []));
    renderDialog('2026-11-03');
    await screen.findByText('Подходящих записей не найдено.');
    expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
    expect(apiMock).toHaveBeenCalledTimes(1);
  });

  it.each([
    [422, 'source day is empty', 'В источнике нет записей для копирования.'],
    [
      409,
      'day is marked as fasted; change completeness before adding food',
      'В дне назначения отмечено отсутствие питания. Выберите другую дату или измените статус дня.',
    ],
  ])('explains an empty source or a fasted target', async (status, detail, message) => {
    apiMock.mockRejectedValue(Object.assign(error(status), { body: { detail } }));
    renderDialog('2026-11-03');
    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(screen.queryByRole('button', { name: 'Повторить' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
  });

  it('does not reuse a cached preview while a changed date is loading', async () => {
    let finishSecond!: (value: unknown) => void;
    apiMock
      .mockResolvedValueOnce(preview('first'))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishSecond = resolve;
          }),
      )
      .mockResolvedValueOnce(preview('third'))
      .mockResolvedValue(result);
    renderDialog('2026-11-03');
    await screen.findByText('Овсяная каша');
    changeTarget('2026-11-04');
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
    changeTarget(today);
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(3));
    await screen.findByText('Овсяная каша');
    await act(async () => finishSecond(preview('obsolete')));
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenLastCalledWith(
        expect.not.stringContaining('/preview'),
        expect.objectContaining({ body: expect.objectContaining({ preview_token: 'third' }) }),
      ),
    );
  });

  it.each([
    [401, 'Сессия истекла. Войдите снова.', false],
    [422, 'Проверьте выбранные данные и попробуйте снова.', false],
    [500, 'Не удалось выполнить запрос. Попробуйте позже.', true],
    [0, 'Нет соединения с сервером. Проверьте интернет.', true],
  ])('handles preview error %s without exposing server detail', async (status, message, retry) => {
    apiMock.mockRejectedValue(error(status));
    renderDialog('2026-11-03');
    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(screen.queryByText('private server detail')).not.toBeInTheDocument();
    expect(Boolean(screen.queryByRole('button', { name: 'Повторить' }))).toBe(retry);
    expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
  });

  it('reuses the key after a network failure and replaces it after the target changes', async () => {
    let token = 0;
    apiMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/preview')) return preview(`preview-${++token}`);
      throw error(0);
    });
    renderDialog('2026-11-03');
    await screen.findByText('Овсяная каша');
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await screen.findByText(/Записи могли добавиться/);
    const firstKey = apiMock.mock.calls[1]![1].headers['Idempotency-Key'];
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(3));
    expect(apiMock.mock.calls[2]![1].headers['Idempotency-Key']).toBe(firstKey);
    changeTarget('2026-11-04');
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(4));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(5));
    expect(apiMock.mock.calls[4]![1].headers['Idempotency-Key']).not.toBe(firstKey);
    expect(apiMock.mock.calls[4]![1].body.preview_token).toBe('preview-2');
  });

  it('keeps the original token and key after a failed commit even if the preview is refreshed', async () => {
    let token = 0;
    apiMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/preview')) return preview(`preview-${++token}`);
      throw error(0);
    });
    const { client } = renderDialog('2026-11-03');
    await screen.findByText('Овсяная каша');
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await screen.findByText(/Записи могли добавиться/);
    const original = apiMock.mock.calls[1]![1];
    await act(async () => {
      await client.invalidateQueries({ queryKey: ['nutrition', 'copy-preview'] });
    });
    expect(apiMock).toHaveBeenCalledTimes(3);
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(4));
    expect(apiMock.mock.calls[3]![1].headers).toEqual(original.headers);
    expect(apiMock.mock.calls[3]![1].body).toEqual(original.body);
  });

  it.each([
    [401, 'Сессия истекла. Войдите снова.', false],
    [422, 'Проверьте выбранные данные и попробуйте снова.', false],
    [500, 'Не удалось выполнить запрос. Попробуйте позже.', true],
  ])(
    'handles confirmation error %s without exposing server detail',
    async (status, message, retry) => {
      apiMock.mockImplementation(async (path: string) => {
        if (path.endsWith('/preview')) return preview();
        throw error(status);
      });
      renderDialog('2026-11-03');
      await screen.findByText('Овсяная каша');
      fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
      expect(await screen.findByRole('alert')).toHaveTextContent(message);
      expect(screen.queryByText('private server detail')).not.toBeInTheDocument();
      expect(Boolean(screen.queryByRole('button', { name: 'Повторить' }))).toBe(retry);
      expect(screen.getByRole('button', { name: 'Подтвердить' }).hasAttribute('disabled')).toBe(
        !retry,
      );
    },
  );

  it('requires a fresh preview and a new key after a stale token', async () => {
    let token = 0;
    apiMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/preview')) return preview(`preview-${++token}`);
      throw error(409);
    });
    renderDialog('2026-11-03');
    await screen.findByText('Овсяная каша');
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await screen.findByText(/Предварительный просмотр устарел/);
    const firstKey = apiMock.mock.calls[1]![1].headers['Idempotency-Key'];
    expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Обновить просмотр' }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(4));
    expect(apiMock.mock.calls[3]![1].headers['Idempotency-Key']).not.toBe(firstKey);
    expect(apiMock.mock.calls[3]![1].body.preview_token).toBe('preview-2');
  });

  it('uses a new preview and key when the source changes', async () => {
    let token = 0;
    apiMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/preview')) return preview(`preview-${++token}`);
      throw error(0);
    });
    const { changeSource } = renderDialog('2026-11-03');
    await screen.findByText('Овсяная каша');
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await screen.findByText(/Записи могли добавиться/);
    const firstKey = apiMock.mock.calls[1]![1].headers['Idempotency-Key'];
    changeSource('2026-11-02');
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(4));
    expect(apiMock.mock.calls[3]![1].headers['Idempotency-Key']).not.toBe(firstKey);
    expect(apiMock.mock.calls[3]![1].body).toMatchObject({
      source_date: '2026-11-02',
      preview_token: 'preview-2',
    });
  });

  it('discards an in-flight attempt if the source changes away and back', async () => {
    let token = 0;
    let rejectFirst!: (reason: unknown) => void;
    let commits = 0;
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/preview')) return Promise.resolve(preview(`preview-${++token}`));
      commits += 1;
      return commits === 1
        ? new Promise((_, reject) => {
            rejectFirst = reject;
          })
        : Promise.resolve(result);
    });
    const { changeSource } = renderDialog('2026-11-03');
    await screen.findByText('Овсяная каша');
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await waitFor(() => expect(commits).toBe(1));
    const first = apiMock.mock.calls[1]![1];
    changeSource('2026-11-02');
    await waitFor(() => expect(token).toBe(2));
    changeSource('2026-11-03');
    await waitFor(() => expect(token).toBe(3));
    await act(async () => rejectFirst(error(0)));
    expect(
      await screen.findByText(
        'Не удалось узнать результат копирования. Проверьте дату назначения в дневнике.',
      ),
    ).toBeVisible();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await waitFor(() => expect(commits).toBe(2));
    const second = apiMock.mock.calls[4]![1];
    expect(second.headers['Idempotency-Key']).not.toBe(first.headers['Idempotency-Key']);
    expect(second.body.preview_token).toBe('preview-3');
  });

  it('does not close the new source after an older confirmation succeeds', async () => {
    let finish!: () => void;
    let token = 0;
    apiMock.mockImplementation((path: string) =>
      path.endsWith('/preview')
        ? Promise.resolve(preview(`preview-${++token}`))
        : new Promise((resolve) => {
            finish = () => resolve(result);
          }),
    );
    const { changeSource, onClose } = renderDialog('2026-11-03');
    await screen.findByText('Овсяная каша');
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    changeSource('2026-11-02');
    await waitFor(() => expect(token).toBe(2));
    await act(async () => finish());
    await waitFor(() => expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeEnabled());
    expect(onClose).not.toHaveBeenCalled();
  });

  it('blocks double confirmation and closing while the request is pending', async () => {
    let finish!: () => void;
    apiMock.mockImplementation((path: string) =>
      path.endsWith('/preview')
        ? Promise.resolve(preview())
        : new Promise((resolve) => {
            finish = () => resolve(result);
          }),
    );
    const { onClose } = renderDialog('2026-11-03');
    await screen.findByText('Овсяная каша');
    const confirm = screen.getByRole('button', { name: 'Подтвердить' });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await waitFor(() => expect(screen.getByLabelText('Дата назначения')).toBeDisabled());
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
    expect(apiMock).toHaveBeenCalledTimes(2);
    await act(async () => finish());
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('cancels without committing', () => {
    const { onClose } = renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(apiMock).not.toHaveBeenCalled();
  });
});
