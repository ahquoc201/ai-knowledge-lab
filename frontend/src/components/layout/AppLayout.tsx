import React from "react";
import { Sidebar, NavItemKey } from "./Sidebar";
import { Header } from "./Header";

interface AppLayoutProps {
  currentTab: NavItemKey;
  onTabChange: (tab: NavItemKey) => void;
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({
  currentTab,
  onTabChange,
  title,
  subtitle,
  children,
}) => {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <Sidebar currentTab={currentTab} onTabChange={onTabChange} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header title={title} subtitle={subtitle} />
        <main className="flex-1 overflow-y-auto p-8">{children}</main>
      </div>
    </div>
  );
};
