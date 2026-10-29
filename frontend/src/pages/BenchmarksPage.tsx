import React, { useState, useEffect, useCallback } from "react";
import {
  BarChart3,
  Play,
  RotateCw,
  GitCompare,
  CheckCircle2,
  XCircle,
  ShieldAlert,
  Zap,
  Target,
  FileCheck,
  Search,
  ChevronRight,
  Eye,
  AlertTriangle,
  Clock,
  Layers,
} from "lucide-react";
import { api, ApiError } from "../api/client";
import {
  BenchmarkRunResponse,
  BenchmarkCaseResultResponse,
  BenchmarkComparisonResponse,
  BenchmarkRunCreatePayload,
} from "../types";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Modal } from "../components/ui/Modal";
import { Alert } from "../components/ui/Alert";
import { Input } from "../components/ui/Input";
import { Spinner } from "../components/ui/Spinner";

export const BenchmarksPage: React.FC = () => {
  const [runs, setRuns] = useState<BenchmarkRunResponse[]>([]);
  const [selectedRun, setSelectedRun] = useState<BenchmarkRunResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filter & Search states for Case Explorer
  const [statusFilter, setStatusFilter] = useState<"all" | "passed" | "failed" | "adversarial">("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Modals
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [isCompareModalOpen, setIsCompareModalOpen] = useState<boolean>(false);
  const [selectedTraceCase, setSelectedTraceCase] = useState<BenchmarkCaseResultResponse | null>(null);

  // Create form state
  const [createPayload, setCreatePayload] = useState<BenchmarkRunCreatePayload>({
    name: "Benchmark Run",
    dataset_id: "synthetic-agent-v1",
    execution_mode: "simulated",
    model_name: "scripted-mock-v1",
    category_filter: "",
  });
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Compare state
  const [baselineRunId, setBaselineRunId] = useState<string>("");
  const [comparisonResult, setComparisonResult] = useState<BenchmarkComparisonResponse | null>(null);
  const [comparing, setComparing] = useState<boolean>(false);

  const fetchRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.benchmarks.listRuns({ limit: 50 });
      setRuns(res.items);
      if (res.items.length > 0) {
        // Auto-select first run if none selected or keep current selected updated
        const targetId = selectedRun?.id || res.items[0].id;
        const fullRun = await api.benchmarks.getRun(targetId);
        setSelectedRun(fullRun);
        // Default baseline to second run if available
        if (res.items.length > 1 && !baselineRunId) {
          setBaselineRunId(res.items[1].id);
        }
      } else {
        setSelectedRun(null);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Không thể tải danh sách kết quả kiểm chuẩn.");
      }
    } finally {
      setLoading(false);
    }
  }, [selectedRun?.id, baselineRunId]);

  useEffect(() => {
    fetchRuns();
  }, []);

  const handleSelectRun = async (run: BenchmarkRunResponse) => {
    try {
      setLoading(true);
      const fullRun = await api.benchmarks.getRun(run.id);
      setSelectedRun(fullRun);
      if (runs.length > 1) {
        const other = runs.find((r) => r.id !== run.id);
        if (other) setBaselineRunId(other.id);
      }
    } catch (err) {
      setError("Không thể tải chi tiết run kiểm chuẩn.");
    } finally {
      setLoading(false);
    }
  };

  const handleTriggerRun = async () => {
    setIsSubmitting(true);
    setError(null);
    try {
      const payload: BenchmarkRunCreatePayload = {
        name: createPayload.name || `Benchmark ${new Date().toLocaleTimeString()}`,
        dataset_id: createPayload.dataset_id,
        execution_mode: createPayload.execution_mode,
        model_name: createPayload.execution_mode === "real" ? "qwen3:1.7b" : "scripted-mock-v1",
        category_filter: createPayload.category_filter || null,
      };
      const created = await api.benchmarks.triggerRun(payload);
      setIsCreateModalOpen(false);
      setSelectedRun(created);
      await fetchRuns();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`Lỗi khởi chạy benchmark: ${err.detail}`);
      } else {
        setError("Lỗi không xác định khi khởi chạy kiểm chuẩn.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCompare = async () => {
    if (!selectedRun) return;
    let baseId = baselineRunId;
    if (!baseId || baseId === selectedRun.id) {
      const other = runs.find((r) => r.id !== selectedRun.id);
      if (other) {
        baseId = other.id;
        setBaselineRunId(other.id);
      }
    }
    if (!baseId) {
      setError("Cần ít nhất hai lần chạy benchmark để thực hiện so sánh.");
      return;
    }
    setComparing(true);
    try {
      const res = await api.benchmarks.compareRuns(selectedRun.id, baseId);
      setComparisonResult(res);
      setIsCompareModalOpen(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`Lỗi so sánh: ${err.detail}`);
      } else {
        setError("Không thể thực hiện so sánh benchmark.");
      }
    } finally {
      setComparing(false);
    }
  };

  // Filter cases in the selected run
  const filteredCases = (selectedRun?.case_results || []).filter((c) => {
    if (statusFilter === "passed" && !c.passed) return false;
    if (statusFilter === "failed" && c.passed) return false;
    if (statusFilter === "adversarial" && !c.is_adversarial) return false;
    if (categoryFilter !== "all" && c.category !== categoryFilter) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchName = c.case_name.toLowerCase().includes(q);
      const matchId = c.case_id.toLowerCase().includes(q);
      const matchReason = c.reason.toLowerCase().includes(q);
      if (!matchName && !matchId && !matchReason) return false;
    }
    return true;
  });

  const categories = [
    { key: "retrieval_factual", label: "Retrieval & Factual QA" },
    { key: "multistep_workflow", label: "Multi-Step Workflow" },
    { key: "tool_selection_args", label: "Tool Selection & Arguments" },
    { key: "citation_grounding", label: "Citation & Grounding" },
    { key: "approval_lifecycle", label: "Approval Lifecycle" },
    { key: "cross_tenant_attack", label: "Cross-Tenant Attack" },
    { key: "prompt_injection_bypass", label: "Prompt Injection Bypass" },
    { key: "timeout_malformed_recovery", label: "Timeout & Recovery" },
  ];

  return (
    <div className="space-y-6 pb-12">
      {/* Top Banner / Actions */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <BarChart3 className="h-6 w-6 text-primary" />
            AI Agent Evaluation & Reliability Benchmarking
          </h1>
          <p className="text-xs text-foreground-muted mt-1">
            Khung kiểm chuẩn chất lượng, độ chính xác tool calling, trích dẫn bằng chứng và bảo mật tấn công đối kháng.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchRuns}
            disabled={loading}
            className="flex items-center gap-1.5"
          >
            <RotateCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Làm mới
          </Button>
          {runs.length > 1 && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleCompare}
              disabled={comparing || !selectedRun}
              className="flex items-center gap-1.5"
            >
              <GitCompare className="h-3.5 w-3.5 text-primary" />
              So sánh Baseline
            </Button>
          )}
          <Button
            size="sm"
            onClick={() => setIsCreateModalOpen(true)}
            className="flex items-center gap-1.5"
          >
            <Play className="h-3.5 w-3.5" />
            Chạy Benchmark Mới
          </Button>
        </div>
      </div>

      {error && (
        <Alert type="error" title="Thông báo hệ thống">
          {error}
        </Alert>
      )}

      {loading && !selectedRun && (
        <div className="flex h-64 items-center justify-center">
          <Spinner size="lg" />
        </div>
      )}

      {!loading && runs.length === 0 && (
        <Card className="text-center py-12">
          <BarChart3 className="mx-auto h-12 w-12 text-foreground-subtle mb-3" />
          <h3 className="text-base font-semibold text-foreground">Chưa có kết quả benchmark nào</h3>
          <p className="text-xs text-foreground-muted mt-1 max-w-md mx-auto">
            Hệ thống chưa ghi nhận lần chạy kiểm chuẩn nào trong workspace này. Hãy nhấn nút bên dưới để thực thi bộ kiểm chuẩn mô phỏng hoặc mô hình thật.
          </p>
          <div className="mt-4">
            <Button size="sm" onClick={() => setIsCreateModalOpen(true)}>
              Khởi chạy bộ Benchmark đầu tiên
            </Button>
          </div>
        </Card>
      )}

      {selectedRun && (
        <>
          {/* Active Run Header Badge & Model details */}
          <div className="flex flex-wrap items-center justify-between gap-3 bg-surface p-4 rounded-lg border border-border shadow-sm">
            <div className="flex items-center gap-3">
              <div className="flex flex-col">
                <span className="text-xs text-foreground-subtle font-medium">Lần chạy đang xem</span>
                <span className="text-sm font-bold text-foreground">{selectedRun.name}</span>
              </div>
              <Badge
                className={
                  selectedRun.execution_mode === "real"
                    ? "bg-purple-100 text-purple-800 border-purple-300"
                    : "bg-blue-100 text-blue-800 border-blue-300"
                }
              >
                {selectedRun.execution_mode === "real" ? "Real Model (Ollama)" : "Simulated (Deterministic)"}
              </Badge>
              <Badge status={selectedRun.status === "completed" ? "ready" : "processing"}>
                {selectedRun.status.toUpperCase()}
              </Badge>
            </div>
            <div className="flex items-center gap-6 text-xs text-foreground-muted">
              <div>
                <span className="font-semibold text-foreground">Model:</span> {selectedRun.model_name}
              </div>
              <div>
                <span className="font-semibold text-foreground">Dataset:</span> {selectedRun.dataset_id} ({selectedRun.dataset_version})
              </div>
              <div>
                <span className="font-semibold text-foreground">Thời gian:</span>{" "}
                {new Date(selectedRun.created_at).toLocaleString("vi-VN")}
              </div>
            </div>
          </div>

          {/* KPI Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <Card className="p-3.5">
              <div className="flex items-center gap-2 text-foreground-muted mb-1 text-xs font-medium">
                <Target className="h-3.5 w-3.5 text-primary" />
                Success Rate
              </div>
              <div className="text-xl font-bold text-foreground">
                {(selectedRun.task_success_rate * 100).toFixed(1)}%
              </div>
              <div className="text-[10px] text-foreground-subtle mt-0.5">
                {selectedRun.passed_cases}/{selectedRun.total_cases} test cases PASS
              </div>
            </Card>

            <Card className="p-3.5">
              <div className="flex items-center gap-2 text-foreground-muted mb-1 text-xs font-medium">
                <Zap className="h-3.5 w-3.5 text-amber-500" />
                Tool Accuracy
              </div>
              <div className="text-xl font-bold text-foreground">
                {(selectedRun.tool_call_accuracy * 100).toFixed(1)}%
              </div>
              <div className="text-[10px] text-foreground-subtle mt-0.5">Selection & Arguments</div>
            </Card>

            <Card className="p-3.5">
              <div className="flex items-center gap-2 text-foreground-muted mb-1 text-xs font-medium">
                <FileCheck className="h-3.5 w-3.5 text-emerald-500" />
                Citation F1
              </div>
              <div className="text-xl font-bold text-foreground">
                {(selectedRun.citation_f1 * 100).toFixed(1)}%
              </div>
              <div className="text-[10px] text-foreground-subtle mt-0.5">Precision & Grounding</div>
            </Card>

            <Card className="p-3.5">
              <div className="flex items-center gap-2 text-foreground-muted mb-1 text-xs font-medium">
                <ShieldAlert className="h-3.5 w-3.5 text-indigo-500" />
                Attack Blocked
              </div>
              <div className="text-xl font-bold text-foreground">
                {selectedRun.security_blocking_rate !== null
                  ? `${(selectedRun.security_blocking_rate * 100).toFixed(1)}%`
                  : "N/A"}
              </div>
              <div className="text-[10px] text-foreground-subtle mt-0.5">Adversarial defense</div>
            </Card>

            <Card className="p-3.5">
              <div className="flex items-center gap-2 text-foreground-muted mb-1 text-xs font-medium">
                <AlertTriangle className="h-3.5 w-3.5 text-rose-500" />
                Benign Overblock
              </div>
              <div className="text-xl font-bold text-foreground">
                {(selectedRun.benign_overblock_rate * 100).toFixed(1)}%
              </div>
              <div className="text-[10px] text-foreground-subtle mt-0.5">False positive rate</div>
            </Card>

            <Card className="p-3.5">
              <div className="flex items-center gap-2 text-foreground-muted mb-1 text-xs font-medium">
                <Clock className="h-3.5 w-3.5 text-blue-500" />
                Latency P50 / P95
              </div>
              <div className="text-base font-bold text-foreground">
                {selectedRun.latency_p50_ms.toFixed(0)} / {selectedRun.latency_p95_ms.toFixed(0)} ms
              </div>
              <div className="text-[10px] text-foreground-subtle mt-0.5">
                Mean: {selectedRun.latency_mean_ms.toFixed(0)} ms
              </div>
            </Card>
          </div>

          {/* Category Breakdown Cards */}
          {selectedRun.category_scores && Object.keys(selectedRun.category_scores).length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-foreground-muted flex items-center gap-1.5">
                <Layers className="h-3.5 w-3.5" /> Phân loại theo 8 nhóm kiểm chuẩn
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
                {Object.entries(selectedRun.category_scores).map(([catKey, catVal]) => (
                  <div
                    key={catKey}
                    className="p-3 rounded-lg border border-border bg-surface flex flex-col justify-between"
                  >
                    <div>
                      <div className="text-xs font-bold text-foreground truncate" title={catKey}>
                        {catKey}
                      </div>
                      <div className="text-[11px] text-foreground-muted mt-0.5">
                        {catVal.passed_cases}/{catVal.total_cases} passed (
                        {(catVal.success_rate * 100).toFixed(0)}%)
                      </div>
                    </div>
                    <div className="mt-2 flex items-center justify-between text-[10px] text-foreground-subtle">
                      <span>Avg Latency:</span>
                      <span className="font-semibold text-foreground">{catVal.avg_latency_ms.toFixed(0)} ms</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Test Case Explorer & History Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            {/* Run History Sidebar List */}
            <div className="lg:col-span-1 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-foreground-muted">
                  Lịch sử Benchmarks ({runs.length})
                </h3>
              </div>
              <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
                {runs.map((r) => {
                  const isSelected = r.id === selectedRun.id;
                  return (
                    <div
                      key={r.id}
                      onClick={() => handleSelectRun(r)}
                      className={`p-3 rounded-lg border cursor-pointer transition-all ${
                        isSelected
                          ? "border-primary bg-primary-subtle/30 shadow-sm"
                          : "border-border bg-surface hover:border-border-strong hover:bg-surface-hover"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-foreground truncate">{r.name}</span>
                        <ChevronRight className={`h-3.5 w-3.5 ${isSelected ? "text-primary" : "text-foreground-subtle"}`} />
                      </div>
                      <div className="mt-1 flex items-center gap-1.5">
                        <span
                          className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase ${
                            r.execution_mode === "real"
                              ? "bg-purple-100 text-purple-700"
                              : "bg-blue-100 text-blue-700"
                          }`}
                        >
                          {r.execution_mode}
                        </span>
                        <span className="text-[10px] text-foreground-muted">{r.model_name}</span>
                      </div>
                      <div className="mt-2 flex items-center justify-between text-[11px]">
                        <span className="text-foreground-subtle">Pass rate:</span>
                        <span className="font-bold text-foreground">
                          {(r.task_success_rate * 100).toFixed(0)}% ({r.passed_cases}/{r.total_cases})
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Test Case Explorer Table */}
            <div className="lg:col-span-3 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-foreground-muted">
                    Test Case Explorer ({filteredCases.length})
                  </h3>
                </div>
                {/* Filters */}
                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex rounded-md border border-border bg-surface p-0.5">
                    <button
                      onClick={() => setStatusFilter("all")}
                      className={`px-2 py-1 text-[11px] rounded font-medium ${
                        statusFilter === "all" ? "bg-primary text-white" : "text-foreground-muted"
                      }`}
                    >
                      Tất cả
                    </button>
                    <button
                      onClick={() => setStatusFilter("passed")}
                      className={`px-2 py-1 text-[11px] rounded font-medium ${
                        statusFilter === "passed" ? "bg-emerald-600 text-white" : "text-foreground-muted"
                      }`}
                    >
                      PASS
                    </button>
                    <button
                      onClick={() => setStatusFilter("failed")}
                      className={`px-2 py-1 text-[11px] rounded font-medium ${
                        statusFilter === "failed" ? "bg-rose-600 text-white" : "text-foreground-muted"
                      }`}
                    >
                      FAIL
                    </button>
                    <button
                      onClick={() => setStatusFilter("adversarial")}
                      className={`px-2 py-1 text-[11px] rounded font-medium ${
                        statusFilter === "adversarial" ? "bg-indigo-600 text-white" : "text-foreground-muted"
                      }`}
                    >
                      Adversarial
                    </button>
                  </div>

                  <select
                    value={categoryFilter}
                    onChange={(e) => setCategoryFilter(e.target.value)}
                    className="h-7 text-[11px] rounded border border-border bg-surface px-2 text-foreground"
                  >
                    <option value="all">Mọi nhóm category</option>
                    {categories.map((c) => (
                      <option key={c.key} value={c.key}>
                        {c.label}
                      </option>
                    ))}
                  </select>

                  <div className="relative">
                    <Search className="absolute left-2 top-2 h-3 w-3 text-foreground-subtle" />
                    <input
                      type="text"
                      placeholder="Tìm test case..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="h-7 w-36 rounded border border-border bg-surface pl-7 pr-2 text-[11px] text-foreground focus:w-48 transition-all"
                    />
                  </div>
                </div>
              </div>

              {/* Cases List */}
              <div className="space-y-2">
                {filteredCases.map((c) => (
                  <div
                    key={c.id}
                    className="p-3.5 rounded-lg border border-border bg-surface hover:border-border-strong transition-all"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-2.5">
                        {c.passed ? (
                          <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                        ) : (
                          <XCircle className="h-4 w-4 text-rose-500 shrink-0 mt-0.5" />
                        )}
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-foreground">{c.case_name}</span>
                            <span className="text-[10px] font-mono text-foreground-subtle bg-background px-1.5 py-0.5 rounded">
                              {c.case_id}
                            </span>
                            {c.is_adversarial && (
                              <span className="text-[9px] font-bold uppercase bg-amber-100 text-amber-800 border border-amber-200 px-1.5 py-0.2 rounded">
                                Adversarial Attack
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-foreground-muted mt-1">{c.reason}</p>
                        </div>
                      </div>

                      <div className="flex items-center gap-3 shrink-0">
                        <div className="text-right text-[11px]">
                          <div className="font-semibold text-foreground">{c.latency_ms.toFixed(0)} ms</div>
                          <div className="text-foreground-subtle text-[10px]">
                            Tool: {(c.tool_accuracy * 100).toFixed(0)}% | F1: {(c.citation_f1 * 100).toFixed(0)}%
                          </div>
                        </div>

                        {c.sanitized_trace && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setSelectedTraceCase(c)}
                            className="h-7 px-2 text-[10px] flex items-center gap-1"
                          >
                            <Eye className="h-3 w-3" />
                            Trace
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}

                {filteredCases.length === 0 && (
                  <div className="text-center py-8 text-xs text-foreground-muted border border-dashed border-border rounded-lg">
                    Không có test case nào khớp với bộ lọc.
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      {/* Trigger Run Modal */}
      <Modal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        title="Khởi chạy Kiểm chuẩn AI (Benchmark Run)"
        description="Đo lường độ tin cậy, an toàn và hiệu năng agent trên môi trường cô lập disposable workspace."
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setIsCreateModalOpen(false)}>
              Hủy
            </Button>
            <Button size="sm" onClick={handleTriggerRun} disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Spinner size="sm" className="mr-1.5" />
                  Đang chạy benchmark...
                </>
              ) : (
                "Bắt đầu Benchmark"
              )}
            </Button>
          </div>
        }
      >
        <div className="space-y-4 text-xs">
          <div>
            <label className="block font-semibold text-foreground mb-1">Tên lần chạy (Run Name)</label>
            <Input
              value={createPayload.name}
              onChange={(e) => setCreatePayload({ ...createPayload, name: e.target.value })}
              placeholder="VD: Nightly Regression Benchmark"
            />
          </div>

          <div>
            <label className="block font-semibold text-foreground mb-1">Chế độ thực thi (Execution Mode)</label>
            <div className="grid grid-cols-2 gap-3 mt-1">
              <div
                onClick={() =>
                  setCreatePayload({
                    ...createPayload,
                    execution_mode: "simulated",
                    model_name: "scripted-mock-v1",
                  })
                }
                className={`p-3 rounded-lg border cursor-pointer ${
                  createPayload.execution_mode === "simulated"
                    ? "border-primary bg-primary-subtle/30"
                    : "border-border bg-surface"
                }`}
              >
                <div className="font-bold text-foreground">Simulated (Deterministic)</div>
                <div className="text-[10px] text-foreground-muted mt-0.5">
                  Kiểm chuẩn nhanh dựa trên kịch bản fixture, mock model outputs, offline 100% tái tạo.
                </div>
              </div>

              <div
                onClick={() =>
                  setCreatePayload({
                    ...createPayload,
                    execution_mode: "real",
                    model_name: "qwen3:1.7b",
                  })
                }
                className={`p-3 rounded-lg border cursor-pointer ${
                  createPayload.execution_mode === "real"
                    ? "border-purple-600 bg-purple-50"
                    : "border-border bg-surface"
                }`}
              >
                <div className="font-bold text-foreground">Real Model (Ollama)</div>
                <div className="text-[10px] text-foreground-muted mt-0.5">
                  Chạy trực tiếp với model Ollama và pgvector thật trong sandbox cô lập.
                </div>
              </div>
            </div>
          </div>

          <div>
            <label className="block font-semibold text-foreground mb-1">Bộ Dataset</label>
            <select
              value={createPayload.dataset_id}
              onChange={(e) => setCreatePayload({ ...createPayload, dataset_id: e.target.value })}
              className="w-full rounded border border-border bg-surface px-2.5 py-1.5 text-xs text-foreground"
            >
              <option value="synthetic-agent-v1">Synthetic Agent Dataset v1.0 (14 representative cases)</option>
            </select>
          </div>

          <div>
            <label className="block font-semibold text-foreground mb-1">Lọc theo Category (Tùy chọn)</label>
            <select
              value={createPayload.category_filter || ""}
              onChange={(e) => setCreatePayload({ ...createPayload, category_filter: e.target.value })}
              className="w-full rounded border border-border bg-surface px-2.5 py-1.5 text-xs text-foreground"
            >
              <option value="">Tất cả các category (Đầy đủ 8 nhóm)</option>
              {categories.map((c) => (
                <option key={c.key} value={c.key}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Modal>

      {/* Trace Inspector Modal */}
      <Modal
        isOpen={Boolean(selectedTraceCase)}
        onClose={() => setSelectedTraceCase(null)}
        title={`Sanitized Execution Trace: ${selectedTraceCase?.case_name}`}
        description="Toàn bộ token, mật khẩu và PII đã được loại bỏ trước khi lưu trữ audit."
        size="lg"
        footer={
          <Button size="sm" onClick={() => setSelectedTraceCase(null)}>
            Đóng
          </Button>
        }
      >
        <div className="space-y-3 text-xs">
          <div className="flex items-center justify-between bg-surface p-2.5 rounded border border-border">
            <div>
              <span className="font-bold text-foreground">Case ID:</span> {selectedTraceCase?.case_id}
            </div>
            <div>
              <span className="font-bold text-foreground">Thời gian:</span> {selectedTraceCase?.latency_ms.toFixed(0)} ms
            </div>
            <div>
              <span className="font-bold text-foreground">Kết quả:</span>{" "}
              {selectedTraceCase?.passed ? (
                <span className="text-emerald-600 font-bold">PASS</span>
              ) : (
                <span className="text-rose-600 font-bold">FAIL ({selectedTraceCase?.failure_classification})</span>
              )}
            </div>
          </div>

          <div className="font-semibold text-foreground">Các bước thực thi (Execution Steps):</div>
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {selectedTraceCase?.sanitized_trace?.steps &&
            Array.isArray(selectedTraceCase.sanitized_trace.steps) ? (
              selectedTraceCase.sanitized_trace.steps.map((step, idx) => (
                <div key={idx} className="p-2.5 rounded border border-border bg-background space-y-1">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-bold text-foreground">
                      Bước #{step.step_index + 1}: {step.action}
                    </span>
                    <span className="text-foreground-subtle text-[10px]">{step.status}</span>
                  </div>
                  {step.tool && (
                    <div className="text-[11px] text-primary font-mono">Tool: {step.tool}</div>
                  )}
                  {step.sanitized_arguments && (
                    <pre className="text-[10px] font-mono bg-surface p-1.5 rounded border border-border overflow-x-auto text-foreground-muted">
                      {JSON.stringify(step.sanitized_arguments, null, 2)}
                    </pre>
                  )}
                  {step.reason && (
                    <div className="text-[10px] text-foreground-subtle italic">{step.reason}</div>
                  )}
                </div>
              ))
            ) : (
              <pre className="text-[11px] font-mono bg-background p-3 rounded border border-border overflow-x-auto">
                {JSON.stringify(selectedTraceCase?.sanitized_trace, null, 2)}
              </pre>
            )}
          </div>
        </div>
      </Modal>

      {/* Comparison Modal */}
      <Modal
        isOpen={isCompareModalOpen}
        onClose={() => setIsCompareModalOpen(false)}
        title="So sánh Kiểm chuẩn với Baseline (Regression & Delta)"
        description="Đối chiếu toán học giữa lần chạy hiện tại và baseline nhằm phát hiện regression."
        size="lg"
        footer={
          <Button size="sm" onClick={() => setIsCompareModalOpen(false)}>
            Đóng
          </Button>
        }
      >
        {comparisonResult && (
          <div className="space-y-4 text-xs">
            {/* Header comparison */}
            <div className="grid grid-cols-2 gap-3 bg-surface p-3 rounded-lg border border-border">
              <div>
                <span className="text-[10px] uppercase font-bold text-foreground-subtle">Lần chạy hiện tại</span>
                <div className="font-bold text-foreground text-sm">{selectedRun?.name}</div>
                <div className="text-foreground-muted text-[11px]">
                  {comparisonResult.current_model} ({comparisonResult.current_mode})
                </div>
              </div>
              <div>
                <span className="text-[10px] uppercase font-bold text-foreground-subtle">Baseline đối chiếu</span>
                <div className="font-bold text-foreground text-sm">
                  {runs.find((r) => r.id === comparisonResult.baseline_run_id)?.name || "Baseline Run"}
                </div>
                <div className="text-foreground-muted text-[11px]">
                  {comparisonResult.baseline_model} ({comparisonResult.baseline_mode})
                </div>
              </div>
            </div>

            {/* Summary narrative */}
            <div className="p-3 bg-primary-subtle/30 rounded border border-primary/20 text-foreground">
              <span className="font-bold text-primary mr-1">Tóm tắt phân tích:</span>
              {comparisonResult.summary}
            </div>

            {/* Metric Deltas Table */}
            <div className="border border-border rounded-lg overflow-hidden">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-background border-b border-border text-foreground-muted">
                    <th className="p-2.5 font-semibold">Chỉ số đo lường</th>
                    <th className="p-2.5 font-semibold">Hiện tại</th>
                    <th className="p-2.5 font-semibold">Baseline</th>
                    <th className="p-2.5 font-semibold">Độ lệch (Delta)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  <tr>
                    <td className="p-2.5 font-medium text-foreground">Task Success Rate</td>
                    <td className="p-2.5">{(comparisonResult.task_success_rate.current * 100).toFixed(1)}%</td>
                    <td className="p-2.5">{(comparisonResult.task_success_rate.baseline * 100).toFixed(1)}%</td>
                    <td className="p-2.5 font-bold">
                      <span
                        className={
                          comparisonResult.task_success_rate.improved
                            ? "text-emerald-600"
                            : comparisonResult.task_success_rate.delta === 0
                            ? "text-foreground-muted"
                            : "text-rose-600"
                        }
                      >
                        {comparisonResult.task_success_rate.delta > 0 ? "+" : ""}
                        {(comparisonResult.task_success_rate.delta * 100).toFixed(1)}%
                      </span>
                    </td>
                  </tr>

                  <tr>
                    <td className="p-2.5 font-medium text-foreground">Tool-Call Accuracy</td>
                    <td className="p-2.5">{(comparisonResult.tool_call_accuracy.current * 100).toFixed(1)}%</td>
                    <td className="p-2.5">{(comparisonResult.tool_call_accuracy.baseline * 100).toFixed(1)}%</td>
                    <td className="p-2.5 font-bold">
                      <span
                        className={
                          comparisonResult.tool_call_accuracy.improved
                            ? "text-emerald-600"
                            : comparisonResult.tool_call_accuracy.delta === 0
                            ? "text-foreground-muted"
                            : "text-rose-600"
                        }
                      >
                        {comparisonResult.tool_call_accuracy.delta > 0 ? "+" : ""}
                        {(comparisonResult.tool_call_accuracy.delta * 100).toFixed(1)}%
                      </span>
                    </td>
                  </tr>

                  <tr>
                    <td className="p-2.5 font-medium text-foreground">Citation Quality (F1)</td>
                    <td className="p-2.5">{(comparisonResult.citation_f1.current * 100).toFixed(1)}%</td>
                    <td className="p-2.5">{(comparisonResult.citation_f1.baseline * 100).toFixed(1)}%</td>
                    <td className="p-2.5 font-bold">
                      <span
                        className={
                          comparisonResult.citation_f1.improved
                            ? "text-emerald-600"
                            : comparisonResult.citation_f1.delta === 0
                            ? "text-foreground-muted"
                            : "text-rose-600"
                        }
                      >
                        {comparisonResult.citation_f1.delta > 0 ? "+" : ""}
                        {(comparisonResult.citation_f1.delta * 100).toFixed(1)}%
                      </span>
                    </td>
                  </tr>

                  {comparisonResult.security_blocking_rate && (
                    <tr>
                      <td className="p-2.5 font-medium text-foreground">Security Attack Blocking</td>
                      <td className="p-2.5">{(comparisonResult.security_blocking_rate.current * 100).toFixed(1)}%</td>
                      <td className="p-2.5">{(comparisonResult.security_blocking_rate.baseline * 100).toFixed(1)}%</td>
                      <td className="p-2.5 font-bold">
                        <span
                          className={
                            comparisonResult.security_blocking_rate.improved
                              ? "text-emerald-600"
                              : comparisonResult.security_blocking_rate.delta === 0
                              ? "text-foreground-muted"
                              : "text-rose-600"
                          }
                        >
                          {comparisonResult.security_blocking_rate.delta > 0 ? "+" : ""}
                          {(comparisonResult.security_blocking_rate.delta * 100).toFixed(1)}%
                        </span>
                      </td>
                    </tr>
                  )}

                  <tr>
                    <td className="p-2.5 font-medium text-foreground">Latency P50 (ms)</td>
                    <td className="p-2.5">{comparisonResult.latency_p50_ms.current.toFixed(0)} ms</td>
                    <td className="p-2.5">{comparisonResult.latency_p50_ms.baseline.toFixed(0)} ms</td>
                    <td className="p-2.5 font-bold">
                      <span
                        className={
                          comparisonResult.latency_p50_ms.improved
                            ? "text-emerald-600"
                            : comparisonResult.latency_p50_ms.delta === 0
                            ? "text-foreground-muted"
                            : "text-rose-600"
                        }
                      >
                        {comparisonResult.latency_p50_ms.delta > 0 ? "+" : ""}
                        {comparisonResult.latency_p50_ms.delta.toFixed(0)} ms
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};
export default BenchmarksPage;
