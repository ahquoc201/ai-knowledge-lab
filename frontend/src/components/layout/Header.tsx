import React, { useEffect, useState } from "react";
import { LogOut, User, Activity } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { api } from "../../api/client";

interface HeaderProps {
  title?: string;
  subtitle?: string;
}

export const Header: React.FC<HeaderProps> = ({ title, subtitle }) => {
  const { userEmail, logout } = useAuth();
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    let mounted = true;
    const check = async () => {
      try {
        const res = await api.health.check();
        if (mounted) setBackendHealthy(res.status === "ok");
      } catch {
        if (mounted) setBackendHealthy(false);
      }
    };
    check();
    const interval = setInterval(check, 30000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-border bg-surface/90 px-6 backdrop-blur">
      <div>
        {title && <h1 className="text-lg font-bold text-foreground">{title}</h1>}
        {subtitle && <p className="text-xs text-foreground-muted">{subtitle}</p>}
      </div>

      <div className="flex items-center gap-4">
        {/* Backend health status pill */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-border bg-background text-xs">
          <Activity
            className={`h-3.5 w-3.5 ${
              backendHealthy === true
                ? "text-status-ready-text"
                : backendHealthy === false
                ? "text-status-failed-text"
                : "text-foreground-subtle animate-spin"
            }`}
          />
          <span className="font-medium text-foreground-muted">
            {backendHealthy === true
              ? "API Online"
              : backendHealthy === false
              ? "API Offline"
              : "Connecting..."}
          </span>
        </div>

        {/* User email & logout */}
        <div className="flex items-center gap-3 pl-2 border-l border-border">
          <div className="flex items-center gap-2 text-xs font-medium text-foreground">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary-subtle text-primary font-semibold">
              <User className="h-4 w-4" />
            </div>
            <span className="max-w-[160px] truncate">{userEmail || "User"}</span>
          </div>
          <button
            onClick={logout}
            title="Đăng xuất"
            className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-foreground-muted hover:bg-background hover:text-status-failed-text transition-colors"
          >
            <LogOut className="h-4 w-4" />
            <span className="hidden sm:inline">Logout</span>
          </button>
        </div>
      </div>
    </header>
  );
};
