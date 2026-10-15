import React, { useEffect, useState, useRef } from "react";
import { LogOut, User, Activity, Building2, ChevronDown, Plus, Check } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { useWorkspace } from "../../context/WorkspaceContext";
import { api } from "../../api/client";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";

interface HeaderProps {
  title?: string;
  subtitle?: string;
}

export const Header: React.FC<HeaderProps> = ({ title, subtitle }) => {
  const { userEmail, logout } = useAuth();
  const {
    workspaces,
    currentWorkspace,
    currentRole,
    switchWorkspace,
    createWorkspace,
  } = useWorkspace();

  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [newWsName, setNewWsName] = useState("");
  const [newWsDesc, setNewWsDesc] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const dropdownRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWsName.trim()) return;

    try {
      setIsCreating(true);
      setCreateError(null);
      await createWorkspace(newWsName.trim(), newWsDesc.trim() || undefined);
      setIsCreateModalOpen(false);
      setNewWsName("");
      setNewWsDesc("");
      setDropdownOpen(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Không thể tạo workspace.";
      setCreateError(msg);
    } finally {
      setIsCreating(false);
    }
  };

  const getRoleBadgeColor = (role?: string | null) => {
    switch (role) {
      case "owner":
        return "bg-purple-100 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300 border-purple-200 dark:border-purple-800";
      case "admin":
        return "bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300 border-blue-200 dark:border-blue-800";
      case "editor":
        return "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800";
      case "viewer":
        return "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300 border-gray-200 dark:border-gray-700";
      default:
        return "bg-gray-100 text-gray-600 border-gray-200";
    }
  };

  return (
    <>
      <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-border bg-surface/90 px-6 backdrop-blur">
        <div>
          {title && <h1 className="text-lg font-bold text-foreground">{title}</h1>}
          {subtitle && <p className="text-xs text-foreground-muted">{subtitle}</p>}
        </div>

        <div className="flex items-center gap-4">
          {/* Workspace Switcher */}
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-2.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-surface transition-colors shadow-sm"
              title="Chuyển đổi Workspace"
              id="workspace-switcher-button"
            >
              <div className="flex h-5 w-5 items-center justify-center rounded bg-primary/10 text-primary">
                <Building2 className="h-3.5 w-3.5" />
              </div>
              <div className="flex flex-col text-left">
                <span className="font-semibold text-foreground max-w-[130px] truncate">
                  {currentWorkspace?.name || "Chọn Workspace"}
                </span>
              </div>
              {currentRole && (
                <span
                  className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border font-bold ${getRoleBadgeColor(
                    currentRole
                  )}`}
                >
                  {currentRole}
                </span>
              )}
              <ChevronDown className="h-3.5 w-3.5 text-foreground-muted" />
            </button>

            {dropdownOpen && (
              <div className="absolute right-0 mt-2 w-64 rounded-xl border border-border bg-surface shadow-lg z-50 py-1.5 animate-in fade-in slide-in-from-top-2">
                <div className="px-3 py-2 border-b border-border">
                  <p className="text-[11px] font-semibold text-foreground-muted uppercase tracking-wider">
                    Không gian làm việc
                  </p>
                </div>

                <div className="max-h-60 overflow-y-auto py-1">
                  {workspaces.map((ws) => {
                    const isSelected = ws.id === currentWorkspace?.id;
                    return (
                      <button
                        key={ws.id}
                        onClick={() => {
                          switchWorkspace(ws.id);
                          setDropdownOpen(false);
                        }}
                        className={`flex w-full items-center justify-between px-3 py-2 text-xs transition-colors ${
                          isSelected
                            ? "bg-primary-subtle/50 text-foreground font-semibold"
                            : "text-foreground-muted hover:bg-background hover:text-foreground"
                        }`}
                      >
                        <div className="flex items-center gap-2 max-w-[180px]">
                          <Building2
                            className={`h-4 w-4 shrink-0 ${
                              isSelected ? "text-primary" : "text-foreground-subtle"
                            }`}
                          />
                          <div className="flex flex-col text-left truncate">
                            <span className="truncate">{ws.name}</span>
                            {ws.is_personal && (
                              <span className="text-[9px] text-foreground-subtle">Cá nhân</span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {ws.role && (
                            <span
                              className={`text-[9px] uppercase tracking-wider px-1 py-0.5 rounded border font-semibold ${getRoleBadgeColor(
                                ws.role
                              )}`}
                            >
                              {ws.role}
                            </span>
                          )}
                          {isSelected && <Check className="h-3.5 w-3.5 text-primary" />}
                        </div>
                      </button>
                    );
                  })}
                </div>

                <div className="border-t border-border pt-1 mt-1 px-1">
                  <button
                    onClick={() => {
                      setIsCreateModalOpen(true);
                      setDropdownOpen(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-primary hover:bg-primary-subtle transition-colors"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Tạo Workspace mới</span>
                  </button>
                </div>
              </div>
            )}
          </div>

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
              <span className="max-w-[140px] truncate">{userEmail || "User"}</span>
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

      {/* Modal Tạo Workspace */}
      <Modal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        title="Tạo Workspace Mới"
        description="Workspace độc lập có tài liệu, vector index và hội thoại AI riêng biệt được bảo vệ bởi RBAC."
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsCreateModalOpen(false)}
              disabled={isCreating}
            >
              Hủy
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleCreateSubmit}
              isLoading={isCreating}
            >
              Tạo Workspace
            </Button>
          </div>
        }
      >
        <form onSubmit={handleCreateSubmit} className="space-y-4">
          {createError && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400">
              {createError}
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-foreground mb-1">
              Tên Workspace <span className="text-red-500">*</span>
            </label>
            <Input
              value={newWsName}
              onChange={(e) => setNewWsName(e.target.value)}
              placeholder="VD: Phòng Nghiên Cứu AI, Dự án Falcon..."
              required
              autoFocus
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-foreground mb-1">
              Mô tả ngắn (tùy chọn)
            </label>
            <Input
              value={newWsDesc}
              onChange={(e) => setNewWsDesc(e.target.value)}
              placeholder="Mô tả mục đích và phạm vi dữ liệu của workspace..."
            />
          </div>
        </form>
      </Modal>
    </>
  );
};
