import React, { useEffect, useState } from 'react';
import { Layout } from './components/Layout';
import { AgentRunsView } from './features/agents/AgentRunsView';
import { AuditView } from './features/audit/AuditView';
import { DashboardView } from './features/dashboard/DashboardView';
import { DocumentsView } from './features/documents/DocumentsView';
import { KnowledgeView } from './features/knowledge/KnowledgeView';
import { ReviewConsoleView } from './features/reviews/ReviewConsoleView';
import { api } from './lib/api';

export function App() {
  const [currentTab, setCurrentTab] = useState<string>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('tab') || 'dashboard';
  });
  const [isUploadOpen, setIsUploadOpen] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('upload') === 'true';
  });
  const [pendingReviewsCount, setPendingReviewsCount] = useState<number>(0);

  useEffect(() => {
    refreshReviewCount();
    const interval = setInterval(refreshReviewCount, 15000);
    return () => clearInterval(interval);
  }, []);

  const refreshReviewCount = async () => {
    try {
      const reviews = await api.getReviews('PENDING');
      setPendingReviewsCount(reviews.length);
    } catch {
      // Quiet fail if API not connected yet
    }
  };

  const renderContent = () => {
    switch (currentTab) {
      case 'dashboard':
        return (
          <DashboardView
            onNavigate={(tab) => setCurrentTab(tab)}
            onOpenUpload={() => setIsUploadOpen(true)}
          />
        );
      case 'documents':
        return (
          <DocumentsView
            isUploadOpen={isUploadOpen}
            onCloseUpload={() => {
              setIsUploadOpen(false);
              refreshReviewCount();
            }}
          />
        );
      case 'reviews':
        return <ReviewConsoleView />;
      case 'knowledge':
        return <KnowledgeView />;
      case 'agents':
        return <AgentRunsView />;
      case 'audit':
        return <AuditView />;
      default:
        return (
          <DashboardView
            onNavigate={(tab) => setCurrentTab(tab)}
            onOpenUpload={() => setIsUploadOpen(true)}
          />
        );
    }
  };

  return (
    <Layout
      currentTab={currentTab}
      onSelectTab={(tab) => setCurrentTab(tab)}
      pendingReviewsCount={pendingReviewsCount}
    >
      {renderContent()}
    </Layout>
  );
}

export default App;
