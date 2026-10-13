import React, { useState } from "react";
import { useAuth } from "./context/AuthContext";
import { AuthPage } from "./pages/AuthPage";
import { AppLayout } from "./components/layout/AppLayout";
import { NavItemKey } from "./components/layout/Sidebar";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { ChatPage } from "./pages/ChatPage";
import { SettingsPage } from "./pages/SettingsPage";

export const App: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const [currentTab, setCurrentTab] = useState<NavItemKey>("dashboard");

  if (!isAuthenticated) {
    return <AuthPage />;
  }

  const renderContent = () => {
    switch (currentTab) {
      case "dashboard":
        return (
          <DashboardPage
            onNavigateToDocs={() => setCurrentTab("documents")}
            onNavigateToChat={() => setCurrentTab("chat")}
          />
        );
      case "documents":
        return <DocumentsPage />;
      case "chat":
        return <ChatPage onNavigateToDocs={() => setCurrentTab("documents")} />;
      case "settings":
        return <SettingsPage />;
      default:
        return (
          <DashboardPage
            onNavigateToDocs={() => setCurrentTab("documents")}
            onNavigateToChat={() => setCurrentTab("chat")}
          />
        );
    }
  };

  const getPageMeta = () => {
    switch (currentTab) {
      case "dashboard":
        return {
          title: "Dashboard Tổng quan",
          subtitle: "Giám sát hiệu năng và tổng hợp dữ liệu tri thức",
        };
      case "documents":
        return {
          title: "Thư viện tài liệu",
          subtitle: "Quản lý dữ liệu văn bản, file và vector index",
        };
      case "chat":
        return {
          title: "AI RAG Assistant",
          subtitle: "Hỏi đáp bảo mật với trích dẫn bằng chứng chính xác",
        };
      case "settings":
        return {
          title: "Cấu hình & Giám sát",
          subtitle: "Thiết lập bảo mật và hạ tầng pgvector",
        };
    }
  };

  const meta = getPageMeta();

  return (
    <AppLayout
      currentTab={currentTab}
      onTabChange={setCurrentTab}
      title={meta.title}
      subtitle={meta.subtitle}
    >
      {renderContent()}
    </AppLayout>
  );
};

export default App;
