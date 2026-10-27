import { AuthenticatedAppRoute, AuthenticatedRoute } from './AuthenticatedRoutes';
import MiniAppPage from '../pages/miniapp/MiniAppPage';

export function AuthenticatedAppPage() {
  return (
    <AuthenticatedRoute>
      <AuthenticatedAppRoute>
        <MiniAppPage />
      </AuthenticatedAppRoute>
    </AuthenticatedRoute>
  );
}
