import { AppLink } from '../shared/navigation/router';
import { Card } from '../shared/ui/common';
import '../styles/react.css';
import '../styles/design-v2.css';

export default function NotFoundPage() {
  return (
    <main className="container standalone-page standalone-page--design-v2">
      <Card collapsible={false} title="Страница не найдена">
        <AppLink className="button-link" to="/app">
          Вернуться в Your Fitness Coach
        </AppLink>
      </Card>
    </main>
  );
}
