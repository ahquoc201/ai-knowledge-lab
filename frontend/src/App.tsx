import React, { useState } from "react";
import { useAuth } from "./context/AuthContext";
import { AuthPage } from "./pages/AuthPage";
import { AppLayout } from "./components/layout/AppLayout";
import { NavItemKey } from "./components/layout/Sidebar";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { ChatPage } from "./pages/ChatPage";
import { SettingsPage } from "./pages/SettingsPage";
import { AgentWorkspacePage } from "./pages/AgentWorkspacePage";
import { BenchmarksPage } from "./pages/BenchmarksPage";
import { ModelsPage } from "./pages/ModelsPage";
import { OperationsPage } from "./pages/OperationsPage";

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
      case "agent":
        return <AgentWorkspacePage onNavigateToDocs={() => setCurrentTab("documents")} />;
      case "benchmarks":
        return <BenchmarksPage />;
      case "models":
        return <ModelsPage />;
      case "reliability":
        return <OperationsPage />;
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
      case "agent":
        return {
          title: "Governed AI Agent Runtime",
          subtitle: "Vòng lặp thực thi tự chủ với Policy Enforcement & Human Approval",
        };
      case "benchmarks":
        return {
          title: "AI Agent Evaluation & Benchmarks",
          subtitle: "Kiểm chuẩn định lượng độ chính xác tool, trích dẫn bằng chứng và an toàn đối kháng",
        };
      case "models":
        return {
          title: "AI Model Registry & Adaptive Routing",
          subtitle: "Quản lý năng lực mô hình, đánh giá benchmark và tự động điều phối có dự phòng",
        };
      case "reliability":
        return {
          title: "Vận hành & Giám sát Độ tin cậy (Operations)",
          subtitle: "Kiểm soát tài nguyên phần cứng, giới hạn tốc độ và tự động phục hồi sự cố",
        };
      case "settings":
        return {
          title: "Cấu hình & Giám sát hệ thống",
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
