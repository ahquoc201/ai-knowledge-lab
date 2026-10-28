import React, { useState, useEffect, useCallback } from "react";
import {
  Bot,
  Play,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  RotateCw,
  FileText,
  Plus,
  Shield,
  ShieldAlert,
  ChevronDown,
  ChevronRight,
  Ban,
  Info,
} from "lucide-react";
import { useWorkspace } from "../context/WorkspaceContext";
import { api, ApiError } from "../api/client";
import {
  AgentRun,
  AgentRunStatus,
} from "../types";

interface AgentWorkspacePageProps {
  onNavigateToDocs?: () => void;
}

export const AgentWorkspacePage: React.FC<AgentWorkspacePageProps> = ({ onNavigateToDocs }) => {
  const { currentWorkspace, currentRole, isViewer } = useWorkspace();

  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<AgentRun | null>(null);
  const [isLoadingRuns, setIsLoadingRuns] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // New run form state
  const [isCreatingNew, setIsCreatingNew] = useState(false);
  const [goalInput, setGoalInput] = useState("");
  const [selectedTools, setSelectedTools] = useState<string[]>([
    "search_workspace_documents",
    "get_document_details",
    "create_workspace_document",
  ]);

  // Approval decision state
  const [approvalReason, setApprovalReason] = useState("");
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({});

  const availableToolsList = [
    {
      name: "search_workspace_documents",
      label: "Tìm kiếm tài liệu (Search Docs)",
      type: "READ_ONLY",
      desc: "Truy vấn ngữ nghĩa vector pgvector trong phạm vi workspace hiện tại.",
    },
    {
      name: "get_document_details",
      label: "Đọc chi tiết tài liệu (Get Details)",
      type: "READ_ONLY",
      desc: "Trích xuất metadata và nội dung bounded an toàn của tài liệu.",
    },
    {
      name: "create_workspace_document",
      label: "Tạo tài liệu mới (Create Document)",
      type: "WRITE",
      desc: "Ghi tài liệu tổng hợp mới vào workspace. Yêu cầu phê duyệt từ con người (Human Approval).",
    },
  ];

  const fetchRuns = useCallback(async () => {
    if (!currentWorkspace) return;
    setIsLoadingRuns(true);
    try {
      const res = await api.agent.listRuns({ limit: 30 });
      setRuns(res.items);
      if (res.items.length > 0 && !selectedRun && !isCreatingNew) {
        setSelectedRun(res.items[0]);
      } else if (selectedRun) {
        // Refresh selected run
        const updated = res.items.find((r) => r.id === selectedRun.id);
        if (updated) setSelectedRun(updated);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Không thể tải danh sách Agent Runs");
      }
    } finally {
      setIsLoadingRuns(false);
    }
  }, [currentWorkspace, selectedRun, isCreatingNew]);

  // Reload when workspace changes
  useEffect(() => {
    setSelectedRun(null);
    setIsCreatingNew(false);
    setError(null);
    fetchRuns();
  }, [currentWorkspace?.id]);

  const handleStartRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!goalInput.trim()) return;

    setIsExecuting(true);
    setError(null);
    try {
      const created = await api.agent.createRun(
        {
          goal: goalInput.trim(),
          allowed_tools: selectedTools,
        },
        true // blocking: execute until first pause/completion
      );
      setRuns((prev) => [created, ...prev]);
      setSelectedRun(created);
      setIsCreatingNew(false);
      setGoalInput("");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Khởi tạo Agent Run thất bại.");
      }
    } finally {
      setIsExecuting(false);
    }
  };

  const handleApprove = async (approvalId: string) => {
    setActionLoading(true);
    setError(null);
    try {
      const updatedRun = await api.agent.approveAction(approvalId, approvalReason, true);
      setSelectedRun(updatedRun);
      setRuns((prev) => prev.map((r) => (r.id === updatedRun.id ? updatedRun : r)));
      setApprovalReason("");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Không thể phê duyệt hành động.");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async (approvalId: string) => {
    setActionLoading(true);
    setError(null);
    try {
      const updatedRun = await api.agent.rejectAction(approvalId, approvalReason, true);
      setSelectedRun(updatedRun);
      setRuns((prev) => prev.map((r) => (r.id === updatedRun.id ? updatedRun : r)));
      setApprovalReason("");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Không thể từ chối hành động.");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async (runId: string) => {
    setActionLoading(true);
    try {
      const updatedRun = await api.agent.cancelRun(runId);
      setSelectedRun(updatedRun);
      setRuns((prev) => prev.map((r) => (r.id === updatedRun.id ? updatedRun : r)));
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Không thể huỷ Agent Run.");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const toggleStepDetails = (stepId: string) => {
    setExpandedSteps((prev) => ({ ...prev, [stepId]: !prev[stepId] }));
  };

  const renderStatusBadge = (status: AgentRunStatus) => {
    switch (status) {
      case "running":
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-500/10 px-2.5 py-0.5 text-xs font-semibold text-blue-500 animate-pulse border border-blue-500/20">
            <RotateCw className="h-3 w-3 animate-spin" />
            Đang chạy
          </span>
        );
      case "awaiting_approval":
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-semibold text-amber-500 border border-amber-500/30 shadow-sm animate-bounce">
            <ShieldAlert className="h-3 w-3" />
            Chờ phê duyệt
          </span>
        );
      case "completed":
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-500 border border-emerald-500/20">
            <CheckCircle2 className="h-3 w-3" />
            Hoàn thành
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-500/10 px-2.5 py-0.5 text-xs font-semibold text-rose-500 border border-rose-500/20">
            <XCircle className="h-3 w-3" />
            Thất bại
          </span>
        );
      case "cancelled":
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-500/10 px-2.5 py-0.5 text-xs font-semibold text-slate-400 border border-slate-500/20">
            <Ban className="h-3 w-3" />
            Đã huỷ
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-500/10 px-2.5 py-0.5 text-xs font-semibold text-slate-400">
            <Clock className="h-3 w-3" />
            Khởi tạo
          </span>
        );
    }
  };

  const renderStepStatus = (status: string) => {
    switch (status) {
      case "succeeded":
        return <span className="text-emerald-500 font-medium text-xs flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5" /> Thành công</span>;
      case "awaiting_approval":
        return <span className="text-amber-500 font-medium text-xs flex items-center gap-1"><ShieldAlert className="h-3.5 w-3.5" /> Đợi duyệt</span>;
      case "denied":
        return <span className="text-rose-500 font-medium text-xs flex items-center gap-1"><Shield className="h-3.5 w-3.5" /> Policy từ chối</span>;
      case "failed":
        return <span className="text-rose-400 font-medium text-xs flex items-center gap-1"><XCircle className="h-3.5 w-3.5" /> Lỗi</span>;
      case "rejected":
        return <span className="text-orange-400 font-medium text-xs flex items-center gap-1"><Ban className="h-3.5 w-3.5" /> Bị từ chối</span>;
      default:
        return <span className="text-slate-400 font-medium text-xs">{status}</span>;
    }
  };

  return (
    <div className="flex h-full w-full gap-4 p-6 overflow-hidden">
      {/* LEFT PANEL: RUNS LIST */}
      <div className="flex w-80 flex-col rounded-xl border border-border bg-surface shadow-sm overflow-hidden flex-shrink-0">
        <div className="flex items-center justify-between border-b border-border p-4 bg-surface-subtle">
          <div className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-primary" />
            <h3 className="text-sm font-bold text-foreground">Agent History</h3>
          </div>
          <button
            onClick={fetchRuns}
            disabled={isLoadingRuns}
            className="rounded p-1 text-foreground-subtle hover:text-foreground hover:bg-background transition-colors"
            title="Làm mới danh sách"
          >
            <RotateCw className={`h-4 w-4 ${isLoadingRuns ? "animate-spin" : ""}`} />
          </button>
        </div>

        {/* Start new run action button */}
        <div className="p-3 border-b border-border">
          <button
            onClick={() => {
              setIsCreatingNew(true);
              setSelectedRun(null);
            }}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-white shadow-sm hover:bg-primary-hover transition-all"
          >
            <Plus className="h-4 w-4" />
            Tạo Nhiệm Vụ Mới
          </button>
        </div>

        {/* Runs list */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1.5 divide-y divide-border/30">
          {runs.length === 0 ? (
            <div className="p-6 text-center text-xs text-foreground-subtle">
              Chưa có nhiệm vụ nào trong workspace này. Bấm nút trên để tạo tác vụ đầu tiên.
            </div>
          ) : (
            runs.map((r) => {
              const isSelected = selectedRun?.id === r.id && !isCreatingNew;
              return (
                <button
                  key={r.id}
                  onClick={() => {
                    setSelectedRun(r);
                    setIsCreatingNew(false);
                  }}
                  className={`flex w-full flex-col gap-1.5 rounded-lg p-3 text-left transition-all ${
                    isSelected
                      ? "bg-primary-subtle/50 border border-primary/30"
                      : "hover:bg-background border border-transparent"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    {renderStatusBadge(r.status)}
                    <span className="text-[10px] text-foreground-subtle">
                      {new Date(r.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                  <p className="line-clamp-2 text-xs font-medium text-foreground">
                    {r.goal}
                  </p>
                  <div className="flex items-center gap-3 text-[11px] text-foreground-subtle">
                    <span>{r.current_step} bước</span>
                    <span>•</span>
                    <span>{r.tool_call_count} công cụ</span>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Workspace role badge in sidebar bottom */}
        <div className="border-t border-border p-3 text-xs bg-surface-subtle flex items-center justify-between">
          <span className="text-foreground-subtle">Vai trò hiện tại:</span>
          <span className="font-semibold uppercase tracking-wider text-primary text-[11px]">
            {currentRole || "Chưa xác định"}
          </span>
        </div>
      </div>

      {/* RIGHT PANEL: MAIN WORKSPACE */}
      <div className="flex flex-1 flex-col rounded-xl border border-border bg-surface shadow-sm overflow-hidden">
        {error && (
          <div className="flex items-center gap-2 border-b border-rose-500/30 bg-rose-500/10 p-3 text-xs font-medium text-rose-500">
            <AlertTriangle className="h-4 w-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* MODE A: CREATE NEW RUN */}
        {isCreatingNew ? (
          <div className="flex flex-1 flex-col overflow-y-auto p-6">
            <div className="mb-6">
              <div className="flex items-center gap-2 text-primary font-bold text-sm mb-1">
                <Bot className="h-5 w-5" />
                <span>Thiết lập Governed Agent Run</span>
              </div>
              <p className="text-xs text-foreground-subtle">
                Agent sẽ tự động lập kế hoạch nhiều bước, truy vấn tài liệu trong workspace và xin phê duyệt trước khi ghi dữ liệu.
              </p>
            </div>

            {isViewer && (
              <div className="mb-4 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-500">
                <Info className="h-4 w-4 flex-shrink-0" />
                <span>
                  Bạn đang ở vai trò <strong>VIEWER</strong>. Bạn có thể yêu cầu agent tìm kiếm thông tin, nhưng các thao tác ghi (như tạo tài liệu) sẽ bị Policy Enforcement từ chối.
                </span>
              </div>
            )}

            <form onSubmit={handleStartRun} className="space-y-6">
              <div>
                <label className="block text-xs font-semibold text-foreground mb-1.5">
                  Mục tiêu yêu cầu (User Goal) *
                </label>
                <textarea
                  rows={4}
                  value={goalInput}
                  onChange={(e) => setGoalInput(e.target.value)}
                  placeholder="Ví dụ: Tìm các tài liệu nói về kiến trúc backend, tổng hợp các điểm quan trọng và tạo một tài liệu ghi chú mới cho tôi."
                  className="w-full rounded-lg border border-border bg-background p-3 text-xs text-foreground placeholder-foreground-subtle focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  required
                />
                {/* Suggestions */}
                <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                  <span className="text-foreground-subtle">Gợi ý nhanh:</span>
                  <button
                    type="button"
                    onClick={() =>
                      setGoalInput(
                        "Tìm các tài liệu nói về kiến trúc backend, tổng hợp các điểm quan trọng và tạo một tài liệu ghi chú mới cho tôi."
                      )
                    }
                    className="text-primary hover:underline"
                  >
                    Tổng hợp kiến trúc & tạo ghi chú
                  </button>
                  <span className="text-foreground-subtle">•</span>
                  <button
                    type="button"
                    onClick={() =>
                      setGoalInput("Tìm kiếm và phân tích các chính sách bảo mật trong workspace.")
                    }
                    className="text-primary hover:underline"
                  >
                    Tìm kiếm chính sách bảo mật
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-foreground mb-2">
                  Danh sách công cụ được phép (Tool Allowlist)
                </label>
                <div className="space-y-2">
                  {availableToolsList.map((tool) => {
                    const isChecked = selectedTools.includes(tool.name);
                    return (
                      <label
                        key={tool.name}
                        className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-all ${
                          isChecked
                            ? "border-primary/40 bg-primary-subtle/20"
                            : "border-border bg-background/50 hover:bg-background"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSelectedTools([...selectedTools, tool.name]);
                            } else {
                              setSelectedTools(selectedTools.filter((t) => t !== tool.name));
                            }
                          }}
                          className="mt-0.5 rounded border-border text-primary focus:ring-primary"
                        />
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-foreground">{tool.label}</span>
                            <span
                              className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${
                                tool.type === "WRITE"
                                  ? "bg-amber-500/20 text-amber-500"
                                  : "bg-blue-500/20 text-blue-500"
                              }`}
                            >
                              {tool.type}
                            </span>
                          </div>
                          <p className="mt-0.5 text-[11px] text-foreground-subtle">{tool.desc}</p>
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>

              <div className="flex items-center gap-3 pt-4 border-t border-border">
                <button
                  type="submit"
                  disabled={isExecuting || !goalInput.trim() || selectedTools.length === 0}
                  className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-primary-hover disabled:opacity-50 transition-all"
                >
                  {isExecuting ? (
                    <>
                      <RotateCw className="h-4 w-4 animate-spin" />
                      Đang xử lý vòng lặp Agent...
                    </>
                  ) : (
                    <>
                      <Play className="h-4 w-4" />
                      Kích hoạt Governed Agent
                    </>
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => setIsCreatingNew(false)}
                  className="rounded-lg border border-border px-4 py-2.5 text-xs font-semibold text-foreground-muted hover:bg-background"
                >
                  Huỷ
                </button>
              </div>
            </form>
          </div>
        ) : selectedRun ? (
          /* MODE B: VIEW SELECTED RUN */
          <div className="flex flex-1 flex-col overflow-y-auto">
            {/* Run Header */}
            <div className="flex items-start justify-between border-b border-border p-5 bg-surface-subtle">
              <div className="space-y-1.5 max-w-2xl">
                <div className="flex items-center gap-3">
                  {renderStatusBadge(selectedRun.status)}
                  <span className="text-[11px] text-foreground-subtle font-mono">
                    ID: {selectedRun.id.slice(0, 8)}...
                  </span>
                  <span className="text-[11px] text-foreground-subtle">
                    Bắt đầu: {new Date(selectedRun.created_at).toLocaleString()}
                  </span>
                </div>
                <h2 className="text-base font-bold text-foreground">{selectedRun.goal}</h2>
                <div className="flex items-center gap-4 text-xs text-foreground-subtle pt-1">
                  <span>
                    Số bước: <strong>{selectedRun.current_step}</strong> / {selectedRun.max_steps}
                  </span>
                  <span>•</span>
                  <span>
                    Số lượt gọi tool: <strong>{selectedRun.tool_call_count}</strong> / {selectedRun.max_tool_calls}
                  </span>
                  <span>•</span>
                  <span>
                    Từ chối Policy: <strong>{selectedRun.denial_count}</strong>
                  </span>
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex items-center gap-2">
                {(selectedRun.status === "running" || selectedRun.status === "awaiting_approval") && (
                  <button
                    onClick={() => handleCancel(selectedRun.id)}
                    disabled={actionLoading}
                    className="flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-500 hover:bg-rose-500/20 transition-all"
                  >
                    <Ban className="h-3.5 w-3.5" />
                    Dừng Nhiệm Vụ
                  </button>
                )}
              </div>
            </div>

            {/* HUMAN-IN-THE-LOOP APPROVAL PANEL */}
            {selectedRun.status === "awaiting_approval" && selectedRun.pending_approval && (
              <div className="m-5 rounded-xl border border-amber-500/40 bg-amber-500/10 p-5 shadow-sm space-y-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500 text-white shadow-sm flex-shrink-0">
                    <ShieldAlert className="h-6 w-6" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-amber-500 uppercase tracking-wide">
                      Yêu cầu Phê duyệt Hành động Ghi (Human Approval Required)
                    </h3>
                    <p className="text-xs text-foreground-muted">
                      Agent đề xuất thực thi công cụ có side-effect. Hệ thống đã tạm dừng để bạn đánh giá tính an toàn.
                    </p>
                  </div>
                </div>

                {/* Details box */}
                <div className="rounded-lg border border-amber-500/20 bg-background/80 p-4 space-y-2 text-xs">
                  <div className="flex justify-between border-b border-border/50 pb-2">
                    <span className="text-foreground-subtle">Công cụ đề xuất:</span>
                    <span className="font-mono font-bold text-foreground">
                      {selectedRun.pending_approval.tool_name}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-border/50 pb-2">
                    <span className="text-foreground-subtle">Quyền hạn yêu cầu:</span>
                    <span className="font-mono text-primary font-semibold">
                      {selectedRun.pending_approval.payload?.required_permission || "document.create"}
                    </span>
                  </div>
                  <div className="space-y-1">
                    <span className="text-foreground-subtle block">Tác động dự kiến:</span>
                    <p className="text-foreground font-medium bg-amber-500/5 p-2 rounded border border-amber-500/20">
                      {selectedRun.pending_approval.payload?.impact || "Tạo dữ liệu mới trong workspace."}
                    </p>
                  </div>
                  <div className="space-y-1 pt-1">
                    <span className="text-foreground-subtle block">Tham số payload:</span>
                    <pre className="overflow-x-auto rounded bg-surface p-2 font-mono text-[11px] text-foreground">
                      {JSON.stringify(selectedRun.pending_approval.payload?.arguments, null, 2)}
                    </pre>
                  </div>
                </div>

                {/* Action inputs */}
                <div className="space-y-3">
                  <div>
                    <label className="block text-[11px] font-semibold text-foreground mb-1">
                      Lý do phê duyệt / từ chối (tùy chọn):
                    </label>
                    <input
                      type="text"
                      value={approvalReason}
                      onChange={(e) => setApprovalReason(e.target.value)}
                      placeholder="Ghi chú xác thực kiểm duyệt..."
                      className="w-full rounded-lg border border-border bg-background p-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>

                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => handleApprove(selectedRun.pending_approval!.id)}
                      disabled={actionLoading || isViewer}
                      className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-700 disabled:opacity-50 transition-all shadow-sm"
                      title={isViewer ? "Vai trò Viewer không có quyền phê duyệt tạo tài liệu" : undefined}
                    >
                      <CheckCircle2 className="h-4 w-4" />
                      Phê duyệt & Thực thi
                    </button>
                    <button
                      onClick={() => handleReject(selectedRun.pending_approval!.id)}
                      disabled={actionLoading}
                      className="flex items-center gap-2 rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-2 text-xs font-bold text-rose-500 hover:bg-rose-500/20 transition-all"
                    >
                      <XCircle className="h-4 w-4" />
                      Từ chối
                    </button>
                  </div>
                  {isViewer && (
                    <p className="text-[11px] text-rose-500 font-medium">
                      * Tài khoản Viewer không có quyền thực thi WRITE tool. Bạn chỉ có thể từ chối.
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* FINAL ANSWER SECTION */}
            {selectedRun.final_answer && (
              <div className="m-5 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-5 space-y-3">
                <div className="flex items-center gap-2 text-emerald-500 font-bold text-sm">
                  <CheckCircle2 className="h-5 w-5" />
                  <span>Kết quả tổng hợp từ Agent</span>
                </div>
                <div className="prose prose-sm max-w-none text-foreground whitespace-pre-wrap leading-relaxed text-xs">
                  {selectedRun.final_answer}
                </div>

                {/* Sources & Citations */}
                {selectedRun.sources && selectedRun.sources.length > 0 && (
                  <div className="pt-3 border-t border-border/50">
                    <span className="text-[11px] font-bold text-foreground-subtle uppercase tracking-wider block mb-2">
                      Tài liệu trích dẫn (References):
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {selectedRun.sources.map((src, i) => (
                        <button
                          key={i}
                          type="button"
                          onClick={() => onNavigateToDocs?.()}
                          className="flex items-center gap-1.5 rounded-lg border border-border bg-background px-2.5 py-1 text-[11px] text-foreground font-medium hover:border-primary/50 transition-colors"
                          title="Mở thư viện tài liệu"
                        >
                          <FileText className="h-3 w-3 text-primary" />
                          <span>{src.title || "Tài liệu không tên"}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* EXECUTION TIMELINE */}
            <div className="p-5 space-y-4">
              <h3 className="text-xs font-bold text-foreground uppercase tracking-wider">
                Nhật ký thực thi (Execution Trace & Steps)
              </h3>

              {(!selectedRun.steps || selectedRun.steps.length === 0) ? (
                <div className="rounded-lg border border-dashed border-border p-6 text-center text-xs text-foreground-subtle">
                  Chưa có bước thực thi nào được ghi nhận.
                </div>
              ) : (
                <div className="relative pl-6 space-y-4 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-border">
                  {selectedRun.steps.map((step) => {
                    const isExpanded = !!expandedSteps[step.id];
                    return (
                      <div
                        key={step.id}
                        className="relative rounded-lg border border-border bg-background p-3.5 space-y-2 shadow-xs"
                      >
                        {/* Step timeline marker */}
                        <div className="absolute -left-7 top-4 h-3 w-3 rounded-full border-2 border-primary bg-surface" />

                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-xs text-primary">Bước {step.step_index}:</span>
                            <span className="font-mono text-xs font-semibold text-foreground">
                              {step.tool_name}
                            </span>
                            {step.side_effect && (
                              <span
                                className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${
                                  step.side_effect === "write"
                                    ? "bg-amber-500/20 text-amber-500"
                                    : "bg-blue-500/20 text-blue-500"
                                }`}
                              >
                                {step.side_effect}
                              </span>
                            )}
                          </div>
                          <div>{renderStepStatus(step.status)}</div>
                        </div>

                        {step.reason && (
                          <p className="text-xs text-foreground-muted italic">
                            "{step.reason}"
                          </p>
                        )}

                        {step.error_message && (
                          <div className="rounded bg-rose-500/10 p-2 text-[11px] text-rose-500 font-medium">
                            {step.error_code && <strong>[{step.error_code}] </strong>}
                            {step.error_message}
                          </div>
                        )}

                        {/* Expandable JSON details */}
                        <div>
                          <button
                            type="button"
                            onClick={() => toggleStepDetails(step.id)}
                            className="flex items-center gap-1 text-[11px] font-medium text-foreground-subtle hover:text-foreground"
                          >
                            {isExpanded ? (
                              <ChevronDown className="h-3.5 w-3.5" />
                            ) : (
                              <ChevronRight className="h-3.5 w-3.5" />
                            )}
                            <span>{isExpanded ? "Thu gọn chi tiết" : "Xem tham số & kết quả"}</span>
                          </button>

                          {isExpanded && (
                            <div className="mt-2 space-y-2 pt-2 border-t border-border/50 text-[11px]">
                              {step.arguments && (
                                <div>
                                  <span className="font-semibold text-foreground-subtle block mb-1">
                                    Tham số (Arguments):
                                  </span>
                                  <pre className="overflow-x-auto rounded bg-surface p-2 font-mono text-foreground">
                                    {JSON.stringify(step.arguments, null, 2)}
                                  </pre>
                                </div>
                              )}
                              {step.result && (
                                <div>
                                  <span className="font-semibold text-foreground-subtle block mb-1">
                                    Kết quả (Result):
                                  </span>
                                  <pre className="overflow-x-auto rounded bg-surface p-2 font-mono text-foreground">
                                    {JSON.stringify(step.result, null, 2)}
                                  </pre>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        ) : (
          /* Empty placeholder */
          <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
            <Bot className="h-12 w-12 text-foreground-subtle mb-3" />
            <h3 className="text-sm font-bold text-foreground mb-1">Chưa chọn Agent Run</h3>
            <p className="text-xs text-foreground-subtle max-w-sm mb-4">
              Chọn một nhiệm vụ từ danh sách bên trái hoặc tạo tác vụ mới để bắt đầu.
            </p>
            <button
              onClick={() => setIsCreatingNew(true)}
              className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-primary-hover"
            >
              <Plus className="h-4 w-4" />
              Tạo Nhiệm Vụ Mới
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
