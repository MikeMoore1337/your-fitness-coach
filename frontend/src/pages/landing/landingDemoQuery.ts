import { loadDemoSession } from '../../features/demo/demoApi';

export const landingDemoQuery = {
  queryKey: ['demo', 'landing', 'self_training'],
  queryFn: () => loadDemoSession('self_training'),
  retry: false,
  staleTime: 15_000,
};
