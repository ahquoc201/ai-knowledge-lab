import React, { useState, useEffect, useCallback } from "react";
import { Card, CardHeader, CardTitle, CardDescription } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Modal } from "../components/ui/Modal";
import { Alert } from "../components/ui/Alert";
import { Spinner } from "../components/ui/Spinner";
import { useAuth } from "../context/AuthContext";
import { useWorkspace } from "../context/WorkspaceContext";
import { api } from "../api/client";
import {
  WorkspaceMember,
  WorkspaceRole,
  SecurityAuditEvent,
} from "../types";
import {
  Shield,
  Database,
  Lock,
  CheckCircle,
  Users,
  UserPlus,
  Trash2,
  LogOut,
  History,
  RefreshCw,
  Building2,
  AlertTriangle,
} from "lucide-react";

type SettingsTab = "overview" | "members" | "audit";

export const SettingsPage: React.FC = () => {
  const { userEmail } = useAuth();
  const {
    currentWorkspace,
    currentRole,
    canManageMembers,
    isOwner,
    workspaceVersion,
    leaveWorkspace,
    deleteWorkspace,
  } = useWorkspace();

  const [activeTab, setActiveTab] = useState<SettingsTab>("overview");

  // Members management state
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [isLoadingMembers, setIsLoadingMembers] = useState(false);
  const [memberError, setMemberError] = useState<string | null>(null);
  const [memberSuccess, setMemberSuccess] = useState<string | null>(null);

  // Invite modal state
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<WorkspaceRole>("viewer");
  const [isInviting, setIsInviting] = useState(false);

  // Audit events state
  const [auditEvents, setAuditEvents] = useState<SecurityAuditEvent[]>([]);
  const [isLoadingAudit, setIsLoadingAudit] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);

  // Danger zone state
  const [isLeaving, setIsLeaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const fetchMembers = useCallback(async () => {
    if (!currentWorkspace) return;
    try {
      setIsLoadingMembers(true);
      setMemberError(null);
      const data = await api.workspaces.listMembers(currentWorkspace.id);
      setMembers(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Không thể tải danh sách thành viên.";
      setMemberError(msg);
    } finally {
      setIsLoadingMembers(false);
    }
  }, [currentWorkspace]);

  const fetchAuditEvents = useCallback(async () => {
    if (!currentWorkspace || !canManageMembers) return;
    try {
      setIsLoadingAudit(true);
      setAuditError(null);
      const res = await api.workspaces.listAuditEvents(currentWorkspace.id, { limit: 50 });
      setAuditEvents(res.items);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Không thể tải nhật ký kiểm toán.";
      setAuditError(msg);
    } finally {
      setIsLoadingAudit(false);
    }
  }, [currentWorkspace, canManageMembers]);

  useEffect(() => {
    if (activeTab === "members") {
      fetchMembers();
    } else if (activeTab === "audit" && canManageMembers) {
      fetchAuditEvents();
    }
  }, [activeTab, fetchMembers, fetchAuditEvents, workspaceVersion]);

  const handleRoleChange = async (userId: string, newRole: WorkspaceRole) => {
    if (!currentWorkspace) return;
    try {
      setMemberError(null);
      setMemberSuccess(null);
      await api.workspaces.updateMemberRole(currentWorkspace.id, userId, newRole);
      setMemberSuccess("Cập nhật vai trò thành viên thành công.");
      await fetchMembers();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Lỗi khi cập nhật vai trò.";
      setMemberError(msg);
    }
  };

  const handleRemoveMember = async (userId: string, memberEmail: string) => {
    if (!currentWorkspace) return;
    if (!window.confirm(`Bạn có chắc chắn muốn xóa thành viên ${memberEmail} khỏi workspace?`)) {
      return;
    }
    try {
      setMemberError(null);
      setMemberSuccess(null);
      await api.workspaces.removeMember(currentWorkspace.id, userId);
      setMemberSuccess(`Đã xóa thành viên ${memberEmail}.`);
      await fetchMembers();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Lỗi khi xóa thành viên.";
      setMemberError(msg);
    }
  };

  const handleInviteSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace || !inviteEmail.trim()) return;

    try {
      setIsInviting(true);
      setMemberError(null);
      const res = await api.workspaces.createInvitation(currentWorkspace.id, {
        email: inviteEmail.trim(),
        role: inviteRole,
      });
      setInviteEmail("");
      setIsInviteModalOpen(false);
      setMemberSuccess(
        `Đã tạo lời mời cho email ${inviteEmail.trim()} với vai trò ${inviteRole}.${
          res.invitation_token ? ` Token: ${res.invitation_token}` : ""
        }`
      );
      await fetchMembers();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Lỗi khi gửi lời mời.";
      setMemberError(msg);
    } finally {
      setIsInviting(false);
    }
  };

  const handleLeaveWorkspace = async () => {
    if (!currentWorkspace) return;
    if (currentWorkspace.is_personal) {
      alert("Không thể rời khỏi Workspace cá nhân mặc định.");
      return;
    }
    if (!window.confirm(`Bạn có chắc chắn muốn rời khỏi workspace "${currentWorkspace.name}"?`)) {
      return;
    }
    try {
      setIsLeaving(true);
      await leaveWorkspace(currentWorkspace.id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Không thể rời khỏi workspace.";
      alert(msg);
    } finally {
      setIsLeaving(false);
    }
  };

  const handleDeleteWorkspace = async () => {
    if (!currentWorkspace) return;
    if (currentWorkspace.is_personal) {
      alert("Không thể xóa Workspace cá nhân mặc định.");
      return;
    }
    if (!window.confirm(`CẢNH BÁO: Toàn bộ tài liệu, vector index và hội thoại trong workspace "${currentWorkspace.name}" sẽ bị xóa vĩnh viễn! Bạn chắc chắn muốn xóa?`)) {
      return;
    }
    try {
      setIsDeleting(true);
      await deleteWorkspace(currentWorkspace.id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Không thể xóa workspace.";
      alert(msg);
    } finally {
      setIsDeleting(false);
    }
  };

  const getRoleBadge = (role: string) => {
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

  const getActionBadgeColor = (action: string) => {
    if (action.includes("create")) return "bg-emerald-50 text-emerald-700 border-emerald-200";
    if (action.includes("delete") || action.includes("remove")) return "bg-rose-50 text-rose-700 border-rose-200";
    if (action.includes("update") || action.includes("role")) return "bg-amber-50 text-amber-700 border-amber-200";
    if (action.includes("invite")) return "bg-blue-50 text-blue-700 border-blue-200";
    return "bg-gray-50 text-gray-700 border-gray-200";
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-foreground">Cấu hình & Quản trị Workspace</h2>
          <p className="text-xs text-foreground-muted mt-0.5">
            Quản trị không gian làm việc{" "}
            <span className="font-semibold text-foreground">{currentWorkspace?.name || "Workspace"}</span>,
            phân quyền RBAC đa cấp và kiểm toán an toàn thông tin.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {currentWorkspace && (
            <span
              className={`text-xs uppercase tracking-wider px-2.5 py-1 rounded-md border font-bold ${getRoleBadge(
                currentRole || "viewer"
              )}`}
            >
              Vai trò: {currentRole}
            </span>
          )}
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="flex items-center gap-2 border-b border-border pb-1">
        <button
          onClick={() => setActiveTab("overview")}
          className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg transition-colors ${
            activeTab === "overview"
              ? "bg-primary text-white shadow-sm"
              : "text-foreground-muted hover:bg-background hover:text-foreground"
          }`}
        >
          <Building2 className="h-4 w-4" />
          Tổng quan & Hạ tầng
        </button>

        <button
          onClick={() => setActiveTab("members")}
          className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg transition-colors ${
            activeTab === "members"
              ? "bg-primary text-white shadow-sm"
              : "text-foreground-muted hover:bg-background hover:text-foreground"
          }`}
        >
          <Users className="h-4 w-4" />
          Thành viên & Phân quyền
        </button>

        {canManageMembers && (
          <button
            onClick={() => setActiveTab("audit")}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg transition-colors ${
              activeTab === "audit"
                ? "bg-primary text-white shadow-sm"
                : "text-foreground-muted hover:bg-background hover:text-foreground"
            }`}
          >
            <History className="h-4 w-4" />
            Security Audit Trail
          </button>
        )}
      </div>

      {/* Tab 1: Overview & Infrastructure */}
      {activeTab === "overview" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Lock className="h-4 w-4 text-primary" />
                <CardTitle>Định danh người dùng & Workspace</CardTitle>
              </div>
              <CardDescription>Thông tin phiên làm việc và tenant hiện tại</CardDescription>
            </CardHeader>
            <div className="space-y-2.5 text-xs">
              <div className="flex justify-between py-1 border-b border-border">
                <span className="text-foreground-muted">Email</span>
                <span className="font-semibold text-foreground">{userEmail || "N/A"}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-border">
                <span className="text-foreground-muted">Workspace hiện tại</span>
                <span className="font-semibold text-foreground">{currentWorkspace?.name}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-border">
                <span className="text-foreground-muted">Loại Workspace</span>
                <span className="font-semibold text-foreground">
                  {currentWorkspace?.is_personal ? "Personal Workspace (Mặc định)" : "Shared Team Workspace"}
                </span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-foreground-muted">Vai trò RBAC</span>
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${getRoleBadge(currentRole || "")}`}>
                  {currentRole || "N/A"}
                </span>
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Database className="h-4 w-4 text-status-ready-text" />
                <CardTitle>Hạ tầng cơ sở dữ liệu</CardTitle>
              </div>
              <CardDescription>Cấu hình vector store và quan hệ</CardDescription>
            </CardHeader>
            <div className="space-y-2.5 text-xs">
              <div className="flex justify-between py-1 border-b border-border">
                <span className="text-foreground-muted">Cơ sở dữ liệu</span>
                <span className="font-semibold text-foreground">PostgreSQL 16 + pgvector</span>
              </div>
              <div className="flex justify-between py-1 border-b border-border">
                <span className="text-foreground-muted">Khoảng cách vector</span>
                <span className="font-semibold text-foreground">Cosine distance (HNSW Index)</span>
              </div>
              <div className="flex justify-between py-1 border-b border-border">
                <span className="text-foreground-muted">Kích thước vector</span>
                <span className="font-semibold text-foreground">1536 chiều</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-foreground-muted">Tenant Filter</span>
                <span className="font-semibold text-foreground">SQL Pre-filter JOIN trên workspace_id</span>
              </div>
            </div>
          </Card>

          <Card className="md:col-span-2">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Shield className="h-4 w-4 text-amber-600" />
                <CardTitle>Chính sách phòng vệ dữ liệu (Data Defense Policies)</CardTitle>
              </div>
              <CardDescription>Các quy tắc an toàn thông tin áp dụng trên toàn workspace</CardDescription>
            </CardHeader>
            <div className="space-y-3 text-xs">
              <div className="flex items-start gap-2.5">
                <CheckCircle className="h-4 w-4 text-status-ready-text mt-0.5 shrink-0" />
                <div>
                  <span className="font-semibold text-foreground">Tenant Isolation: </span>
                  <span className="text-foreground-muted">
                    Tất cả tài liệu, phân đoạn (chunks), embeddings và lịch sử hội thoại AI được bảo vệ nghiêm ngặt bằng khoá ngoại `workspace_id`. Không có dữ liệu rò rỉ chéo tenant.
                  </span>
                </div>
              </div>
              <div className="flex items-start gap-2.5">
                <CheckCircle className="h-4 w-4 text-status-ready-text mt-0.5 shrink-0" />
                <div>
                  <span className="font-semibold text-foreground">Role-Based Access Control (RBAC): </span>
                  <span className="text-foreground-muted">
                    Hệ thống áp dụng 4 cấp độ phân quyền (Owner, Admin, Editor, Viewer). Quyền Viewer bị cấm tải lên hoặc sửa tài liệu, được bảo đảm tại backend với mã lỗi 403 Forbidden.
                  </span>
                </div>
              </div>
              <div className="flex items-start gap-2.5">
                <CheckCircle className="h-4 w-4 text-status-ready-text mt-0.5 shrink-0" />
                <div>
                  <span className="font-semibold text-foreground">Immutable Security Audit Trail: </span>
                  <span className="text-foreground-muted">
                    Mọi hành động nhạy cảm như cấp quyền, hạ quyền, xóa thành viên, tải lên tài liệu đều được ghi nhận vào nhật ký kiểm toán không thể xóa hoặc sửa.
                  </span>
                </div>
              </div>
              <div className="flex items-start gap-2.5">
                <CheckCircle className="h-4 w-4 text-status-ready-text mt-0.5 shrink-0" />
                <div>
                  <span className="font-semibold text-foreground">Fail-Closed & Last Owner Protection: </span>
                  <span className="text-foreground-muted">
                    Không cho phép xóa hoặc hạ quyền Owner duy nhất còn lại của một workspace nhằm bảo đảm workspace luôn có người chịu trách nhiệm.
                  </span>
                </div>
              </div>
            </div>
          </Card>

          {/* Danger Zone */}
          {currentWorkspace && !currentWorkspace.is_personal && (
            <Card className="md:col-span-2 border-rose-200 dark:border-rose-950/60 bg-rose-50/20">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-rose-600" />
                  <CardTitle className="text-rose-600">Vùng nguy hiểm (Danger Zone)</CardTitle>
                </div>
                <CardDescription>Các thao tác không thể hoàn tác với Workspace</CardDescription>
              </CardHeader>
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 border-t border-rose-100 dark:border-rose-950/40">
                <div>
                  <h4 className="text-xs font-bold text-foreground">Rời khỏi Workspace này</h4>
                  <p className="text-[11px] text-foreground-muted">
                    Bạn sẽ mất toàn bộ quyền truy cập vào tài liệu và lịch sử chat của workspace này.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleLeaveWorkspace}
                  isLoading={isLeaving}
                  className="text-rose-600 hover:bg-rose-50 border-rose-300"
                >
                  <LogOut className="h-3.5 w-3.5 mr-1.5" />
                  Rời Workspace
                </Button>
              </div>

              {isOwner && (
                <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 border-t border-rose-100 dark:border-rose-950/40">
                  <div>
                    <h4 className="text-xs font-bold text-rose-600">Xóa vĩnh viễn Workspace</h4>
                    <p className="text-[11px] text-foreground-muted">
                      Xóa toàn bộ tài liệu, vector index và thành viên trong workspace này. Hành động này không thể hoàn tác!
                    </p>
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleDeleteWorkspace}
                    isLoading={isDeleting}
                    className="bg-rose-600 hover:bg-rose-700 text-white"
                  >
                    <Trash2 className="h-3.5 w-3.5 mr-1.5" />
                    Xóa Workspace
                  </Button>
                </div>
              )}
            </Card>
          )}
        </div>
      )}

      {/* Tab 2: Members & Roles */}
      {activeTab === "members" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-foreground">Danh sách thành viên ({members.length})</h3>
              <p className="text-xs text-foreground-muted">
                Quản lý các tài khoản có quyền truy cập vào kho tri thức của workspace này.
              </p>
            </div>
            {canManageMembers && (
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  setMemberError(null);
                  setIsInviteModalOpen(true);
                }}
              >
                <UserPlus className="h-3.5 w-3.5 mr-1.5" />
                Mời thành viên
              </Button>
            )}
          </div>

          {memberError && (
            <Alert type="error" onClose={() => setMemberError(null)}>
              {memberError}
            </Alert>
          )}

          {memberSuccess && (
            <Alert type="success" onClose={() => setMemberSuccess(null)}>
              {memberSuccess}
            </Alert>
          )}

          <Card className="p-0 overflow-hidden">
            {isLoadingMembers ? (
              <div className="flex h-36 items-center justify-center">
                <Spinner size="md" label="Đang tải danh sách thành viên..." />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-border bg-background/50 font-semibold text-foreground-muted">
                      <th className="py-3 px-4">Thành viên</th>
                      <th className="py-3 px-4">Vai trò hiện tại</th>
                      <th className="py-3 px-4">Ngày tham gia</th>
                      {canManageMembers && <th className="py-3 px-4 text-right">Thao tác</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {members.map((m) => {
                      const memberEmail = m.user_email || m.email || "";
                      const isCurrentUser = Boolean(
                        memberEmail &&
                          userEmail &&
                          memberEmail.toLowerCase() === userEmail.toLowerCase()
                      );
                      return (
                        <tr key={m.id} className="hover:bg-background/40 transition-colors">
                          <td className="py-3.5 px-4 font-medium text-foreground">
                            <div className="flex items-center gap-2.5">
                              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 text-primary font-bold text-xs uppercase">
                                {memberEmail.charAt(0) || "U"}
                              </div>
                              <div>
                                <span className="font-semibold block">{memberEmail}</span>
                                {isCurrentUser && (
                                  <span className="text-[10px] text-primary block font-medium">
                                    (Bạn)
                                  </span>
                                )}
                              </div>
                            </div>
                          </td>

                          <td className="py-3.5 px-4">
                            {canManageMembers && !isCurrentUser ? (
                              <select
                                value={m.role}
                                onChange={(e) =>
                                  handleRoleChange(m.user_id, e.target.value as WorkspaceRole)
                                }
                                className={`rounded-md border text-xs px-2 py-1 font-semibold focus:outline-none focus:ring-2 focus:ring-primary ${getRoleBadge(
                                  m.role
                                )}`}
                              >
                                <option value="viewer">VIEWER (Chỉ xem)</option>
                                <option value="editor">EDITOR (Biên tập)</option>
                                <option value="admin">ADMIN (Quản trị)</option>
                                <option value="owner">OWNER (Chủ sở hữu)</option>
                              </select>
                            ) : (
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${getRoleBadge(
                                  m.role
                                )}`}
                              >
                                {m.role}
                              </span>
                            )}
                          </td>

                          <td className="py-3.5 px-4 text-foreground-muted">
                            {new Date(m.created_at).toLocaleDateString("vi-VN")}
                          </td>

                          {canManageMembers && (
                            <td className="py-3.5 px-4 text-right">
                              {!isCurrentUser ? (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  title="Xóa thành viên"
                                  onClick={() => handleRemoveMember(m.user_id, memberEmail)}
                                  className="text-rose-600 hover:bg-rose-50"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                              ) : (
                                <span className="text-foreground-subtle text-[11px]">-</span>
                              )}
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Tab 3: Security Audit Trail */}
      {activeTab === "audit" && canManageMembers && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-foreground">Security Audit Trail (Nhật ký kiểm toán)</h3>
              <p className="text-xs text-foreground-muted">
                Bản ghi bất biến ghi nhận mọi sự kiện truy cập, cập nhật quyền và thay đổi dữ liệu nhạy cảm.
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={() => fetchAuditEvents()}>
              <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
              Làm mới
            </Button>
          </div>

          {auditError && (
            <Alert type="error" onClose={() => setAuditError(null)}>
              {auditError}
            </Alert>
          )}

          <Card className="p-0 overflow-hidden">
            {isLoadingAudit ? (
              <div className="flex h-36 items-center justify-center">
                <Spinner size="md" label="Đang tải nhật ký kiểm toán..." />
              </div>
            ) : auditEvents.length === 0 ? (
              <div className="py-12 text-center text-foreground-muted text-xs">
                Chưa có sự kiện kiểm toán nào được ghi nhận cho workspace này.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-border bg-background/50 font-semibold text-foreground-muted">
                      <th className="py-3 px-4">Thời gian</th>
                      <th className="py-3 px-4">Hành động (Action)</th>
                      <th className="py-3 px-4">Loại tài nguyên</th>
                      <th className="py-3 px-4">Người thực hiện (Actor)</th>
                      <th className="py-3 px-4">Chi tiết</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {auditEvents.map((evt) => (
                      <tr key={evt.id} className="hover:bg-background/40 transition-colors">
                        <td className="py-3 px-4 text-foreground-muted whitespace-nowrap">
                          {new Date(evt.created_at).toLocaleString("vi-VN")}
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className={`inline-block px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase border ${getActionBadgeColor(
                              evt.action
                            )}`}
                          >
                            {evt.action}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-foreground font-medium uppercase text-[10px]">
                          {evt.resource_type}
                        </td>
                        <td className="py-3 px-4 text-foreground">
                          {evt.actor_email || evt.actor_id || "Hệ thống"}
                        </td>
                        <td className="py-3 px-4 text-foreground-muted max-w-xs truncate font-mono text-[11px]">
                          {evt.details ? JSON.stringify(evt.details) : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Modal Mời Thành Viên */}
      <Modal
        isOpen={isInviteModalOpen}
        onClose={() => setIsInviteModalOpen(false)}
        title="Mời thành viên mới"
        description="Gửi lời mời tham gia workspace với vai trò được kiểm soát nghiêm ngặt."
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsInviteModalOpen(false)}
              disabled={isInviting}
            >
              Hủy
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleInviteSubmit}
              isLoading={isInviting}
            >
              Gửi lời mời
            </Button>
          </div>
        }
      >
        <form onSubmit={handleInviteSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-foreground mb-1">
              Email người nhận <span className="text-red-500">*</span>
            </label>
            <Input
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="user@example.com"
              required
              autoFocus
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-foreground mb-1">
              Vai trò trong Workspace
            </label>
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value as WorkspaceRole)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="viewer">VIEWER - Chỉ xem tài liệu & hỏi đáp AI (Không thể tải lên/xóa)</option>
              <option value="editor">EDITOR - Được tải lên, xóa và quản lý tài liệu trong workspace</option>
              {isOwner && (
                <>
                  <option value="admin">ADMIN - Quản lý thành viên và xem audit logs</option>
                  <option value="owner">OWNER - Chủ sở hữu toàn quyền quản trị</option>
                </>
              )}
            </select>
          </div>
        </form>
      </Modal>
    </div>
  );
};
