import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { PublicShareOwner } from '../../shared/api/types';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Button } from '../../shared/ui/common';

export function PublicShareOwnerList({ shareType }: { shareType: 'progress' | 'program' }) {
  const { confirm, toast } = useFeedback();
  const queryClient = useQueryClient();
  const shares = useQuery({
    queryKey: ['public-shares'],
    queryFn: () => api<PublicShareOwner[]>('/api/v1/shares'),
  });
  const revoke = useMutation({
    mutationFn: (shareId: string) => api<void>(`/api/v1/shares/${shareId}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['public-shares'] });
      toast('Публичная ссылка отозвана.');
    },
    onError: (reason) =>
      toast(reason instanceof Error ? reason.message : 'Не удалось отозвать ссылку', 'error'),
  });

  const filtered = Array.isArray(shares.data)
    ? shares.data.filter((share) => share.share_type === shareType)
    : [];
  if (shares.isLoading || shares.error || !filtered.length) return null;
  return (
    <div className="public-share-owner-list" aria-label="Созданные публичные ссылки">
      <h3>Созданные ссылки</h3>
      <ul>
        {filtered.map((share) => (
          <li key={share.share_id}>
            <div>
              <a href={share.public_url}>{share.public_url}</a>
              <small>{share.status === 'active' ? 'Активна' : 'Отозвана'}</small>
            </div>
            {share.status === 'active' && (
              <Button
                disabled={revoke.isPending}
                onClick={() =>
                  void confirm({
                    title: 'Отозвать публичную ссылку?',
                    message: 'После отзыва снимок больше не откроется по этой ссылке.',
                    confirmText: 'Отозвать ссылку',
                    danger: true,
                  }).then((accepted) => {
                    if (accepted) revoke.mutate(share.share_id);
                  })
                }
                type="button"
                variant="danger"
              >
                Отозвать
              </Button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
