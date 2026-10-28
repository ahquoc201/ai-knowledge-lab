import React from "react";
import { LayoutDashboard, FileText, MessageSquare, Shield, Sparkles, Bot } from "lucide-react";

export type NavItemKey = "dashboard" | "documents" | "chat" | "agent" | "settings";

interface SidebarProps {
  currentTab: NavItemKey;
  onTabChange: (tab: NavItemKey) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ currentTab, onTabChange }) => {
  const navItems = [
    {
      key: "dashboard" as NavItemKey,
      label: "Dashboard",
      icon: LayoutDashboard,
      badge: null,
    },
    {
      key: "documents" as NavItemKey,
      label: "Tài liệu (Documents)",
      icon: FileText,
      badge: null,
    },
    {
      key: "chat" as NavItemKey,
      label: "AI Chat / RAG",
      icon: MessageSquare,
      badge: "T260022",
    },
    {
      key: "agent" as NavItemKey,
      label: "Governed Agent",
      icon: Bot,
      badge: "T260025",
    },
    {
      key: "settings" as NavItemKey,
      label: "Cấu hình / Audit",
      icon: Shield,
      badge: null,
    },
  ];

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-border bg-surface">
      {/* Brand header */}
      <div className="flex h-16 items-center gap-3 border-b border-border px-6">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-white shadow-sm">
          <Sparkles className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-sm font-bold tracking-tight text-foreground">AI Knowledge Lab</h2>
          <p className="text-[10px] uppercase tracking-wider text-foreground-subtle font-semibold">
            Enterprise RAG
          </p>
        </div>
      </div>

      {/* Nav items */}
      <nav className="flex-1 space-y-1 p-4">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentTab === item.key;
          return (
            <button
              key={item.key}
              id={`nav-${item.key}`}
              data-testid={`nav-${item.key}`}
              onClick={() => onTabChange(item.key)}
              className={`flex w-full items-center justify-between rounded-lg px-3.5 py-2.5 text-xs font-semibold transition-all ${
                isActive
                  ? "bg-primary text-white shadow-sm"
                  : "text-foreground-muted hover:bg-background hover:text-foreground"
              }`}
            >
              <div className="flex items-center gap-3">
                <Icon className={`h-4 w-4 ${isActive ? "text-white" : "text-foreground-subtle"}`} />
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                    isActive
                      ? "bg-white/20 text-white"
                      : "bg-primary-subtle text-primary"
                  }`}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Footer build info */}
      <div className="border-t border-border p-4 text-[11px] text-foreground-subtle space-y-1">
        <div className="flex justify-between font-medium">
          <span>Release Stage</span>
          <span className="font-semibold text-foreground">T260021</span>
        </div>
        <div className="flex justify-between">
          <span>Vector Store</span>
          <span>pgvector 1536d</span>
        </div>
        <div className="flex justify-between">
          <span>LLM Provider</span>
          <span>Ollama / DeepSeek</span>
        </div>
      </div>
    </aside>
  );
};
