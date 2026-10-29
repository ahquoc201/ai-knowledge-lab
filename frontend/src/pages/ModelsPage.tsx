import React, { useState, useEffect, useCallback } from "react";
import {
  Cpu,
  RefreshCw,
  Sliders,
  History,
  ShieldCheck,
  ShieldAlert,
  Zap,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Play,
  Save,
  Check,
  Activity,
  Database,
  BarChart2,
} from "lucide-react";
import { api, ApiError } from "../api/client";
import {
  ModelRegistryEntry,
  ModelRoutingPolicy,
  ModelRoutingPreviewResponse,
  ModelRoutingDecision,
  ModelCapabilityStatus,
} from "../types";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Alert } from "../components/ui/Alert";
import { Spinner } from "../components/ui/Spinner";

export const ModelsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"registry" | "comparison" | "routing" | "decisions">("registry");
  const [models, setModels] = useState<ModelRegistryEntry[]>([]);
  const [policy, setPolicy] = useState<ModelRoutingPolicy | null>(null);
  const [decisions, setDecisions] = useState<ModelRoutingDecision[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Workspace ID from local storage
  const workspaceId = localStorage.getItem("current_workspace_id") || undefined;

  // Routing Simulator State
  const [simPrompt, setSimPrompt] = useState<string>("Tóm tắt các tài liệu tài chính và so sánh doanh thu");
  const [simRequiresTools, setSimRequiresTools] = useState<boolean>(false);
  const [simIsWrite, setSimIsWrite] = useState<boolean>(false);
  const [simHasContext, setSimHasContext] = useState<boolean>(true);
  const [simDocCount, setSimDocCount] = useState<number>(2);
  const [simLoading, setSimLoading] = useState<boolean>(false);
  const [simResult, setSimResult] = useState<ModelRoutingPreviewResponse | null>(null);

  // Policy Form State
  const [policyEnabled, setPolicyEnabled] = useState<boolean>(true);
  const [policyDefaultModel, setPolicyDefaultModel] = useState<string>("");
  const [policyAllowedModels, setPolicyAllowedModels] = useState<string[]>([]);
  const [policyFallbackModels, setPolicyFallbackModels] = useState<string[]>([]);
  const [policyMaxFallback, setPolicyMaxFallback] = useState<number>(2);
  const [policySaving, setPolicySaving] = useState<boolean>(false);

  // Load initial data
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [modelsRes, policyRes, decisionsRes] = await Promise.all([
        api.models.list(),
        api.modelRouting.getPolicy(workspaceId).catch(() => null),
        api.modelRouting.listDecisions({ workspaceId, limit: 30 }).catch(() => []),
      ]);

      setModels(modelsRes.items);
      if (policyRes) {
        setPolicy(policyRes);
        setPolicyEnabled(policyRes.is_enabled);
        setPolicyDefaultModel(policyRes.default_model);
        setPolicyAllowedModels(policyRes.allowed_models);
        setPolicyFallbackModels(policyRes.fallback_models);
        setPolicyMaxFallback(policyRes.max_fallback_attempts);
      }
      setDecisions(decisionsRes);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Không thể tải danh sách mô hình hoặc chính sách.");
      }
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Handle Ollama refresh
  const handleSyncOllama = async () => {
    setRefreshing(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await api.models.refresh();
      setSuccessMsg(`Đã đồng bộ thành công: phát hiện ${res.discovered_count} mô hình, cập nhật ${res.updated_count}.`);
      await fetchData();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Đồng bộ từ Ollama thất bại. Hãy chắc chắn Ollama daemon đang chạy.");
      }
    } finally {
      setRefreshing(false);
    }
  };

  // Toggle model active status
  const handleToggleActive = async (modelId: string, currentActive: boolean) => {
    try {
      await api.models.toggleActive(modelId, !currentActive);
      setModels((prev) =>
        prev.map((m) => (m.id === modelId ? { ...m, is_active: !currentActive } : m))
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      }
    }
  };

  // Save policy
  const handleSavePolicy = async () => {
    if (!policy) return;
    setPolicySaving(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const updated = await api.modelRouting.updatePolicy(policy.id, {
        is_enabled: policyEnabled,
        default_model: policyDefaultModel,
        allowed_models: policyAllowedModels,
        fallback_models: policyFallbackModels,
        max_fallback_attempts: policyMaxFallback,
      });
      setPolicy(updated);
      setSuccessMsg("Đã lưu chính sách điều phối mô hình thành công.");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Không thể lưu cấu hình chính sách.");
      }
    } finally {
      setPolicySaving(false);
    }
  };

  // Run Preview Simulator
  const handleRunSimulator = async () => {
    setSimLoading(true);
    setError(null);
    try {
      const res = await api.modelRouting.preview({
        workspace_id: workspaceId,
        prompt: simPrompt,
        has_retrieved_context: simHasContext,
        context_document_count: simDocCount,
        requires_tools: simRequiresTools,
        is_write_operation: simIsWrite,
      });
      setSimResult(res);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Thử nghiệm mô phỏng điều phối thất bại.");
      }
    } finally {
      setSimLoading(false);
    }
  };

  const renderCapabilityBadge = (name: string, status?: ModelCapabilityStatus) => {
    switch (status) {
      case "verified":
        return (
          <Badge key={name} status="ready" className="text-xs">
            {name}: Verified
          </Badge>
        );
      case "advertised":
        return (
          <Badge key={name} status="info" className="text-xs">
            {name}: Advertised
          </Badge>
        );
      default:
        return (
          <Badge key={name} status="default" className="text-xs opacity-60">
            {name}: Unknown
          </Badge>
        );
    }
  };

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white flex items-center gap-2">
            <Cpu className="h-7 w-7 text-indigo-600 dark:text-indigo-400" />
            Quản lý & Điều phối Mô hình (AI Model Registry & Routing)
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Quản lý kho mô hình cục bộ Ollama, đánh giá năng lực bảo mật và điều phối thông minh có dự phòng.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleSyncOllama}
            disabled={refreshing}
            className="flex items-center gap-1.5"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin text-indigo-600" : ""}`} />
            Đồng bộ Ollama
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchData}
            className="flex items-center gap-1.5"
          >
            <RotateCwIcon className="h-4 w-4" />
            Tải lại
          </Button>
        </div>
      </div>

      {/* Notifications */}
      {error && <Alert type="error" onClose={() => setError(null)}>{error}</Alert>}
      {successMsg && <Alert type="success" onClose={() => setSuccessMsg(null)}>{successMsg}</Alert>}

      {/* Navigation Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-800">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab("registry")}
            className={`flex items-center gap-2 border-b-2 py-4 px-1 text-sm font-medium ${
              activeTab === "registry"
                ? "border-indigo-500 text-indigo-600 dark:text-indigo-400"
                : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400"
            }`}
          >
            <Database className="h-4 w-4" />
            Kho mô hình ({models.length})
          </button>
          <button
            onClick={() => setActiveTab("comparison")}
            className={`flex items-center gap-2 border-b-2 py-4 px-1 text-sm font-medium ${
              activeTab === "comparison"
                ? "border-indigo-500 text-indigo-600 dark:text-indigo-400"
                : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400"
            }`}
          >
            <BarChart2 className="h-4 w-4" />
            So sánh năng lực (Comparison)
          </button>
          <button
            onClick={() => setActiveTab("routing")}
            className={`flex items-center gap-2 border-b-2 py-4 px-1 text-sm font-medium ${
              activeTab === "routing"
                ? "border-indigo-500 text-indigo-600 dark:text-indigo-400"
                : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400"
            }`}
          >
            <Sliders className="h-4 w-4" />
            Cấu hình & Thử nghiệm Điều phối
          </button>
          <button
            onClick={() => setActiveTab("decisions")}
            className={`flex items-center gap-2 border-b-2 py-4 px-1 text-sm font-medium ${
              activeTab === "decisions"
                ? "border-indigo-500 text-indigo-600 dark:text-indigo-400"
                : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400"
            }`}
          >
            <History className="h-4 w-4" />
            Nhật ký Quyết định ({decisions.length})
          </button>
        </nav>
      </div>

      {/* Tab 1: Model Registry Cards */}
      {activeTab === "registry" && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {models.map((model) => {
              const prof = model.latest_benchmark_profile;
              return (
                <Card key={model.id} className="p-5 flex flex-col justify-between border dark:border-gray-800">
                  <div className="space-y-3">
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="font-semibold text-lg text-gray-900 dark:text-white">{model.name}</h3>
                        <p className="text-xs font-mono text-gray-400 truncate max-w-[200px]" title={model.digest}>
                          {model.digest}
                        </p>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        {model.is_loaded ? (
                          <Badge status="ready" className="text-xs flex items-center gap-1">
                            <Activity className="h-3 w-3 animate-pulse" /> Sẵn sàng trong RAM
                          </Badge>
                        ) : (
                          <Badge status="default" className="text-xs">
                            Cold-start
                          </Badge>
                        )}
                        <Badge status={model.is_active ? "info" : "failed"} className="text-xs">
                          {model.is_active ? "Kích hoạt" : "Vô hiệu hóa"}
                        </Badge>
                      </div>
                    </div>

                    {/* Hardware & Spec metadata */}
                    <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-gray-800/50 p-2.5 rounded-md">
                      <div>
                        <span className="text-gray-400">Tham số:</span> {model.parameter_size || "N/A"}
                      </div>
                      <div>
                        <span className="text-gray-400">Định dạng:</span> {model.quantization_level || model.format || "N/A"}
                      </div>
                      <div>
                        <span className="text-gray-400">Bộ nhớ:</span>{" "}
                        {model.size_bytes ? `${(model.size_bytes / (1024 * 1024 * 1024)).toFixed(1)} GB` : "N/A"}
                      </div>
                      <div>
                        <span className="text-gray-400">Context:</span> {model.context_length ? `${model.context_length.toLocaleString()} tokens` : "N/A"}
                      </div>
                    </div>

                    {/* Capabilities */}
                    <div className="space-y-1.5">
                      <div className="text-xs font-medium text-gray-500">Năng lực (Capabilities):</div>
                      <div className="flex flex-wrap gap-1.5">
                        {renderCapabilityBadge("chat", model.capabilities?.chat)}
                        {renderCapabilityBadge("tools", model.capabilities?.tools)}
                        {renderCapabilityBadge("structured", model.capabilities?.structured_output)}
                      </div>
                    </div>

                    {/* Benchmark Quality Metrics */}
                    {prof ? (
                      <div className="border-t pt-2.5 dark:border-gray-800 space-y-1">
                        <div className="text-xs font-medium text-gray-500 flex items-center justify-between">
                          <span>Chỉ số đo lường (Benchmark):</span>
                          {!prof.has_sufficient_sample_size && (
                            <span className="text-amber-500 text-[10px] flex items-center gap-0.5" title="Mẫu đo nhỏ N=14 < 30">
                              <AlertTriangle className="h-3 w-3" /> Mẫu sơ bộ
                            </span>
                          )}
                        </div>
                        <div className="grid grid-cols-3 gap-1 text-center text-xs">
                          <div className="bg-gray-50 dark:bg-gray-800/40 p-1.5 rounded">
                            <div className="text-[10px] text-gray-400">Đạt tác vụ</div>
                            <div className="font-semibold text-indigo-600 dark:text-indigo-400">
                              {(prof.task_success_rate * 100).toFixed(0)}%
                            </div>
                          </div>
                          <div className="bg-gray-50 dark:bg-gray-800/40 p-1.5 rounded">
                            <div className="text-[10px] text-gray-400">Chuẩn tool</div>
                            <div className="font-semibold text-emerald-600 dark:text-emerald-400">
                              {(prof.tool_call_accuracy * 100).toFixed(0)}%
                            </div>
                          </div>
                          <div className="bg-gray-50 dark:bg-gray-800/40 p-1.5 rounded">
                            <div className="text-[10px] text-gray-400">P50 Latency</div>
                            <div className="font-semibold text-gray-700 dark:text-gray-300">
                              {(prof.latency_p50_ms / 1000).toFixed(1)}s
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="text-xs text-gray-400 italic">Chưa có kết quả benchmark thực nghiệm.</div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="mt-4 pt-3 border-t dark:border-gray-800 flex justify-end">
                    <Button
                      variant={model.is_active ? "outline" : "primary"}
                      size="sm"
                      onClick={() => handleToggleActive(model.id, model.is_active)}
                    >
                      {model.is_active ? "Vô hiệu hóa" : "Kích hoạt mô hình"}
                    </Button>
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {/* Tab 2: Model Benchmark Comparison */}
      {activeTab === "comparison" && (
        <Card className="p-6">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Bảng đối sánh hiệu năng & an toàn mô hình</h2>
                <p className="text-xs text-gray-500">So sánh trực quan các tiêu chuẩn chất lượng và cổng an toàn (Hard Gates) thực tế.</p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800 text-sm">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-800/50 text-gray-500 text-left text-xs uppercase font-medium">
                    <th className="px-4 py-3">Mô hình</th>
                    <th className="px-4 py-3">Năng lực</th>
                    <th className="px-4 py-3">Task Success</th>
                    <th className="px-4 py-3">Tool Accuracy</th>
                    <th className="px-4 py-3">Citation F1</th>
                    <th className="px-4 py-3">Rò rỉ dữ liệu</th>
                    <th className="px-4 py-3">Cô lập Tenant</th>
                    <th className="px-4 py-3">Độ trễ P50</th>
                    <th className="px-4 py-3">Độ tin cậy mẫu</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  {models.map((m) => {
                    const prof = m.latest_benchmark_profile;
                    return (
                      <tr key={m.id} className="hover:bg-gray-50/50 dark:hover:bg-gray-800/30">
                        <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                          {m.name}
                          <div className="text-[11px] text-gray-400">{m.parameter_size || "Local"}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1">
                            {m.capabilities?.tools === "verified" ? (
                              <Badge status="ready" className="text-[10px]">Tool verified</Badge>
                            ) : (
                              <Badge status="default" className="text-[10px]">No verified tool</Badge>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          {prof ? `${(prof.task_success_rate * 100).toFixed(1)}%` : "—"}
                        </td>
                        <td className="px-4 py-3">
                          {prof ? `${(prof.tool_call_accuracy * 100).toFixed(1)}%` : "—"}
                        </td>
                        <td className="px-4 py-3">
                          {prof ? `${(prof.citation_reference_f1 * 100).toFixed(1)}%` : "—"}
                        </td>
                        <td className="px-4 py-3">
                          {prof ? (
                            prof.actual_data_leakage_rate > 0 ? (
                              <span className="text-red-600 font-bold flex items-center gap-1">
                                <XCircle className="h-4 w-4" /> {(prof.actual_data_leakage_rate * 100).toFixed(1)}% (FAIL)
                              </span>
                            ) : (
                              <span className="text-emerald-600 font-semibold flex items-center gap-1">
                                <CheckCircle2 className="h-4 w-4" /> 0.0% (PASS)
                              </span>
                            )
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {prof?.tenant_isolation_success !== null && prof?.tenant_isolation_success !== undefined ? (
                            prof.tenant_isolation_success >= 1.0 ? (
                              <span className="text-emerald-600 font-semibold flex items-center gap-1">
                                <ShieldCheck className="h-4 w-4" /> 100%
                              </span>
                            ) : (
                              <span className="text-red-600 font-bold flex items-center gap-1">
                                <ShieldAlert className="h-4 w-4" /> {(prof.tenant_isolation_success * 100).toFixed(0)}%
                              </span>
                            )
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {prof ? `${(prof.latency_p50_ms / 1000).toFixed(1)}s` : "—"}
                        </td>
                        <td className="px-4 py-3">
                          {prof ? (
                            prof.has_sufficient_sample_size ? (
                              <Badge status="ready" className="text-[10px]">Mẫu đầy đủ (N={prof.sample_size})</Badge>
                            ) : (
                              <Badge status="pending" className="text-[10px] text-amber-700 bg-amber-50">
                                ⚠️ Sơ bộ (N={prof.sample_size})
                              </Badge>
                            )
                          ) : (
                            <span className="text-gray-400 italic text-xs">Chưa đo</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 p-3 rounded-md text-xs text-amber-800 dark:text-amber-300 flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
              <div>
                <strong>Lưu ý về kích thước mẫu (Sample Size Policy):</strong> Kết quả từ các lượt benchmark với số mẫu nhỏ ($N &lt; 30$) chỉ phản ánh định hướng sơ bộ của môi trường phát triển hiện tại. Hệ thống hiển thị trung thực số mẫu đo và không tự động đưa ra kết luận tuyệt đối khi chưa đủ mẫu kiểm chứng.
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Tab 3: Routing Policy & Simulator */}
      {activeTab === "routing" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: Policy Configuration */}
          <Card className="p-6 space-y-5">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                <Sliders className="h-5 w-5 text-indigo-600" />
                Chính sách Điều phối Workspace (Routing Policy)
              </h2>
              <p className="text-xs text-gray-500">Cấu hình danh sách mô hình cho phép và thiết lập dự phòng tin cậy.</p>
            </div>

            {policy && (
              <div className="space-y-4">
                {/* Auto Routing Toggle */}
                <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800/50 rounded-md">
                  <div>
                    <div className="font-medium text-sm text-gray-900 dark:text-white">Tự động điều phối (Adaptive Auto-Routing)</div>
                    <div className="text-xs text-gray-500">Tự động chọn mô hình tối ưu theo 7 loại tác vụ và điểm số bảo mật.</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={policyEnabled}
                    onChange={(e) => setPolicyEnabled(e.target.checked)}
                    className="h-5 w-5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                </div>

                {/* Default Model */}
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Mô hình mặc định (Default Model):
                  </label>
                  <select
                    value={policyDefaultModel}
                    onChange={(e) => setPolicyDefaultModel(e.target.value)}
                    className="w-full text-sm rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 p-2 text-gray-900 dark:text-white"
                  >
                    {models.map((m) => (
                      <option key={m.id} value={m.name}>
                        {m.name} {m.is_loaded ? "(Sẵn sàng)" : ""}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Workspace Model Allowlist */}
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Danh sách mô hình được phép (Allowlist):
                  </label>
                  <div className="space-y-1.5 p-2 bg-gray-50 dark:bg-gray-800/50 rounded-md max-h-36 overflow-y-auto">
                    {models.map((m) => (
                      <label key={m.id} className="flex items-center gap-2 text-xs text-gray-800 dark:text-gray-200">
                        <input
                          type="checkbox"
                          checked={policyAllowedModels.includes(m.name)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setPolicyAllowedModels([...policyAllowedModels, m.name]);
                            } else {
                              setPolicyAllowedModels(policyAllowedModels.filter((name) => name !== m.name));
                            }
                          }}
                          className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                        />
                        <span>{m.name}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Fallback Chain */}
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Mô hình dự phòng (Fallback Chain):
                  </label>
                  <div className="space-y-1.5 p-2 bg-gray-50 dark:bg-gray-800/50 rounded-md max-h-36 overflow-y-auto">
                    {models.map((m) => (
                      <label key={m.id} className="flex items-center gap-2 text-xs text-gray-800 dark:text-gray-200">
                        <input
                          type="checkbox"
                          checked={policyFallbackModels.includes(m.name)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setPolicyFallbackModels([...policyFallbackModels, m.name]);
                            } else {
                              setPolicyFallbackModels(policyFallbackModels.filter((name) => name !== m.name));
                            }
                          }}
                          className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                        />
                        <span>{m.name}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Max Fallback Attempts */}
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Số lần thử dự phòng tối đa (Max Fallback Attempts):
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="5"
                    value={policyMaxFallback}
                    onChange={(e) => setPolicyMaxFallback(parseInt(e.target.value) || 0)}
                    className="w-full text-sm rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 p-2 text-gray-900 dark:text-white"
                  />
                </div>

                <Button
                  variant="primary"
                  className="w-full flex items-center justify-center gap-2"
                  onClick={handleSavePolicy}
                  disabled={policySaving}
                >
                  <Save className="h-4 w-4" />
                  {policySaving ? "Đang lưu..." : "Lưu chính sách"}
                </Button>
              </div>
            )}
          </Card>

          {/* Right: Routing Simulator */}
          <Card className="p-6 space-y-5">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                <Play className="h-5 w-5 text-emerald-600" />
                Trình mô phỏng Điều phối (Routing Simulator)
              </h2>
              <p className="text-xs text-gray-500">Thử nghiệm xác định task type và xem kết quả tính điểm router thời gian thực.</p>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Prompt hoặc Mục tiêu:</label>
                <textarea
                  rows={3}
                  value={simPrompt}
                  onChange={(e) => setSimPrompt(e.target.value)}
                  className="w-full text-sm rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 p-2.5 text-gray-900 dark:text-white"
                  placeholder="Nhập prompt hoặc mục tiêu agent để mô phỏng..."
                />
              </div>

              {/* Simulation Context Toggles */}
              <div className="grid grid-cols-2 gap-3 text-xs">
                <label className="flex items-center gap-2 p-2 bg-gray-50 dark:bg-gray-800/40 rounded">
                  <input
                    type="checkbox"
                    checked={simHasContext}
                    onChange={(e) => setSimHasContext(e.target.checked)}
                    className="rounded text-indigo-600"
                  />
                  <span>Có tài liệu RAG</span>
                </label>
                <label className="flex items-center gap-2 p-2 bg-gray-50 dark:bg-gray-800/40 rounded">
                  <input
                    type="checkbox"
                    checked={simRequiresTools}
                    onChange={(e) => setSimRequiresTools(e.target.checked)}
                    className="rounded text-indigo-600"
                  />
                  <span>Yêu cầu Tools (Agent)</span>
                </label>
                <label className="flex items-center gap-2 p-2 bg-gray-50 dark:bg-gray-800/40 rounded">
                  <input
                    type="checkbox"
                    checked={simIsWrite}
                    onChange={(e) => setSimIsWrite(e.target.checked)}
                    className="rounded text-indigo-600"
                  />
                  <span>Tác vụ Ghi/Sửa</span>
                </label>
                <div className="flex items-center gap-2 p-2 bg-gray-50 dark:bg-gray-800/40 rounded">
                  <span className="text-gray-500">Số tài liệu:</span>
                  <input
                    type="number"
                    min="0"
                    max="10"
                    value={simDocCount}
                    onChange={(e) => setSimDocCount(parseInt(e.target.value) || 0)}
                    className="w-16 p-1 text-xs rounded border dark:border-gray-700 bg-white dark:bg-gray-800 text-center"
                  />
                </div>
              </div>

              <Button
                variant="primary"
                className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700"
                onClick={handleRunSimulator}
                disabled={simLoading || !simPrompt.trim()}
              >
                <Zap className="h-4 w-4" />
                {simLoading ? "Đang tính toán..." : "Chạy thử nghiệm mô phỏng"}
              </Button>

              {/* Simulation Result */}
              {simResult && (
                <div className="border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-950/20 p-4 rounded-md space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-emerald-800 dark:text-emerald-300">Kết quả phân loại:</span>
                    <Badge status="info" className="text-xs font-mono">{simResult.task_type}</Badge>
                  </div>

                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-600 dark:text-gray-400">Mô hình được chọn:</span>
                    <span className="font-bold text-gray-900 dark:text-white flex items-center gap-1">
                      <Check className="h-4 w-4 text-emerald-600" /> {simResult.selected_model}
                    </span>
                  </div>

                  <div className="text-xs text-gray-600 dark:text-gray-300 bg-white dark:bg-gray-800 p-2.5 rounded border dark:border-gray-700">
                    <span className="font-medium text-gray-500">Lý giải điều phối:</span> {simResult.selection_reason}
                  </div>

                  {simResult.fallback_chain.length > 0 && (
                    <div className="text-xs text-gray-600 dark:text-gray-300">
                      <span className="font-medium text-gray-500">Chuỗi dự phòng (Fallback):</span>{" "}
                      {simResult.fallback_chain.join(" ➔ ")}
                    </div>
                  )}

                  {/* Candidate Evaluations */}
                  <div className="space-y-1.5 pt-2">
                    <div className="text-xs font-semibold text-gray-700 dark:text-gray-300">Điểm số từng ứng viên:</div>
                    <div className="space-y-1 max-h-36 overflow-y-auto text-xs">
                      {simResult.candidate_evaluations.map((c) => (
                        <div
                          key={c.model}
                          className="flex items-center justify-between p-2 rounded bg-white dark:bg-gray-800 border dark:border-gray-700"
                        >
                          <div className="flex items-center gap-1.5">
                            {c.eligible ? (
                              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                            ) : (
                              <XCircle className="h-3.5 w-3.5 text-red-500" />
                            )}
                            <span className="font-medium text-gray-900 dark:text-white">{c.model}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-indigo-600 dark:text-indigo-400">{c.score.toFixed(2)}</span>
                            <span className="text-[11px] text-gray-400 truncate max-w-[150px]" title={c.reason}>
                              {c.reason}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </Card>
        </div>
      )}

      {/* Tab 4: Routing Decisions Audit Trail */}
      {activeTab === "decisions" && (
        <Card className="p-6">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                  <History className="h-5 w-5 text-indigo-600" />
                  Nhật ký Quyết định Điều phối (Routing Observability)
                </h2>
                <p className="text-xs text-gray-500">Bằng chứng kiểm toán minh bạch cho từng lượt định tuyến mô hình trong hệ thống.</p>
              </div>
            </div>

            {decisions.length === 0 ? (
              <div className="py-12 text-center text-sm text-gray-500">Chưa có bản ghi quyết định điều phối nào.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800 text-sm">
                  <thead>
                    <tr className="bg-gray-50 dark:bg-gray-800/50 text-gray-500 text-left text-xs uppercase font-medium">
                      <th className="px-4 py-3">Thời gian</th>
                      <th className="px-4 py-3">Loại tác vụ</th>
                      <th className="px-4 py-3">Mô hình đã chọn</th>
                      <th className="px-4 py-3">Dự phòng</th>
                      <th className="px-4 py-3">Độ trễ router</th>
                      <th className="px-4 py-3">Lý do điều phối</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                    {decisions.map((d) => (
                      <tr key={d.id} className="hover:bg-gray-50/50 dark:hover:bg-gray-800/30 text-xs">
                        <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                          {new Date(d.created_at).toLocaleString("vi-VN")}
                        </td>
                        <td className="px-4 py-3 font-mono font-medium text-indigo-600 dark:text-indigo-400">
                          {d.task_type}
                        </td>
                        <td className="px-4 py-3 font-semibold text-gray-900 dark:text-white">
                          {d.selected_model}
                        </td>
                        <td className="px-4 py-3">
                          {d.fallback_occurred ? (
                            <Badge status="pending" className="text-[10px]">Đã dự phòng</Badge>
                          ) : (
                            <Badge status="ready" className="text-[10px]">Tiêu chuẩn</Badge>
                          )}
                        </td>
                        <td className="px-4 py-3 font-mono text-gray-500">
                          {d.latency_ms.toFixed(1)} ms
                        </td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-300 max-w-xs truncate" title={d.selection_reason}>
                          {d.selection_reason}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      )}
    </div>
  );
};

function RotateCwIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
    </svg>
  );
}
