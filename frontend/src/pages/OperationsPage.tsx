import React, { useState, useEffect } from "react";
import { Activity, RefreshCw, AlertTriangle, CheckCircle2, XCircle, Clock, Zap, Shield, Server, Cpu } from "lucide-react";
import { Card, CardHeader } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { api } from "../api/client";

interface HealthCheckData {
  status: string;
  timestamp: string;
  components: {
    postgres: { status: string; error?: string };
    redis: { status: string; mode: string };
    ollama: { status: string; model?: string; base_url?: string };
  };
  message: string;
}

interface ReliabilityMetricsData {
  workspace_id: string;
  timestamp: string;
  agent_runtime: {
    active_runs: number;
    queued_runs: number;
    stuck_runs_count: number;
    stuck_runs: Array<{
      run_id: string;
      goal: string;
      status: string;
      lease_expires_at: string | null;
      recovery_attempts: number;
    }>;
  };
  inference_governor: {
    active_inferences: number;
    queued_requests: number;
    total_admitted: number;
    total_rejected: number;
    total_timeouts: number;
    max_concurrency: number;
    max_queue_size: number;
  };
  rate_limiting: {
    redis_connected: boolean;
    mode: string;
  };
}

export const OperationsPage: React.FC = () => {
  const [healthData, setHealthData] = useState<HealthCheckData | null>(null);
  const [metricsData, setMetricsData] = useState<ReliabilityMetricsData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isRecovering, setIsRecovering] = useState<boolean>(false);
  const [recoveryLog, setRecoveryLog] = useState<string | null>(null);

  const workspaceId = localStorage.getItem("current_workspace_id") || undefined;

  const fetchStatus = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      // 1. Fetch Health
      const health = await api.reliability.getReady();
      setHealthData(health);

      // 2. Fetch Metrics
      try {
        const metrics = await api.reliability.getMetrics(workspaceId);
        setMetricsData(metrics);
      } catch (err: any) {
        if (err.status === 403) {
          setErrorMessage("Chỉ thành viên có vai trò OWNER hoặc ADMIN trong workspace mới có quyền xem thông số vận hành chi tiết.");
        }
      }
    } catch (err) {
      console.error("Failed to load operations data", err);
      setErrorMessage("Không thể tải trạng thái vận hành hệ thống.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, [workspaceId]);

  const handleRecoverStuck = async () => {
    setIsRecovering(true);
    setRecoveryLog(null);
    try {
      const result = await api.reliability.recoverStuck();
      setRecoveryLog(`Đã quét xong: Phục hồi ${result.recovered_count} agent run(s) bị kẹt.`);
      await fetchStatus();
    } catch (err) {
      setRecoveryLog("Lỗi khi thực hiện quét phục hồi (yêu cầu quyền Admin/Owner).");
    } finally {
      setIsRecovering(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner & Control */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-slate-900 border border-slate-800 p-6 rounded-xl">
        <div>
          <div className="flex items-center gap-3">
            <Activity className="w-7 h-7 text-indigo-400" />
            <h2 className="text-xl font-bold text-slate-100">Vận hành & Giám sát Độ tin cậy (T260028)</h2>
          </div>
          <p className="text-slate-400 text-sm mt-1">
            Kiểm soát tài nguyên, điều tiết inference Ollama, giới hạn rate limit và tự động phục hồi Agent runs.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchStatus}
            disabled={loading}
            className="flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            Làm mới
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleRecoverStuck}
            disabled={isRecovering}
            className="flex items-center gap-2"
          >
            <Zap className={`w-4 h-4 ${isRecovering ? "animate-spin text-amber-300" : ""}`} />
            Quét phục hồi Agent Runs
          </Button>
        </div>
      </div>

      {errorMessage && (
        <div className="p-4 bg-amber-950/60 border border-amber-700/50 rounded-lg text-amber-200 text-sm flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-amber-400" />
          {errorMessage}
        </div>
      )}

      {recoveryLog && (
        <div className="p-4 bg-indigo-950/60 border border-indigo-700/50 rounded-lg text-indigo-200 text-sm flex items-center gap-2">
          <CheckCircle2 className="w-5 h-5 text-indigo-400" />
          {recoveryLog}
        </div>
      )}

      {/* Component Status Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Postgres */}
        <Card className="p-4">
          <CardHeader className="flex flex-row items-center justify-between pb-2 p-0">
            <span className="text-sm font-semibold text-slate-400 flex items-center gap-2">
              <Server className="w-4 h-4 text-emerald-400" /> PostgreSQL & pgvector
            </span>
            {healthData?.components.postgres.status === "up" ? (
              <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" /> Khỏe mạnh
              </span>
            ) : (
              <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-500/20 text-rose-400 border border-rose-500/30 flex items-center gap-1">
                <XCircle className="w-3 h-3" /> Mất kết nối
              </span>
            )}
          </CardHeader>
          <div className="mt-3">
            <div className="text-2xl font-bold text-slate-100">Lưu trữ cốt lõi</div>
            <p className="text-xs text-slate-400 mt-1">Cơ sở dữ liệu giao dịch, RBAC & Vector Embeddings</p>
          </div>
        </Card>

        {/* Redis Rate Limiter */}
        <Card className="p-4">
          <CardHeader className="flex flex-row items-center justify-between pb-2 p-0">
            <span className="text-sm font-semibold text-slate-400 flex items-center gap-2">
              <Shield className="w-4 h-4 text-indigo-400" /> Rate Limiter
            </span>
            {healthData?.components.redis.status === "up" ? (
              <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" /> Redis phân tán
              </span>
            ) : (
              <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" /> Bộ nhớ đệm (Fallback)
              </span>
            )}
          </CardHeader>
          <div className="mt-3">
            <div className="text-2xl font-bold text-slate-100">
              {metricsData?.rate_limiting.mode === "distributed_redis" ? "Distributed Redis" : "In-Memory Sliding Window"}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Bảo vệ Auth, RAG Chat, Agent Runs & Quét Benchmark khỏi tấn công quá tải
            </p>
          </div>
        </Card>

        {/* Ollama Concurrency Governor */}
        <Card className="p-4">
          <CardHeader className="flex flex-row items-center justify-between pb-2 p-0">
            <span className="text-sm font-semibold text-slate-400 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-purple-400" /> Inference Engine (Ollama)
            </span>
            {healthData?.components.ollama.status === "up" ? (
              <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" /> Sẵn sàng
              </span>
            ) : (
              <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" /> Degraded
              </span>
            )}
          </CardHeader>
          <div className="mt-3">
            <div className="text-2xl font-bold text-slate-100">
              {healthData?.components.ollama.model || "qwen3:1.7b"}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Admission Control & Giới hạn tối đa {metricsData?.inference_governor.max_concurrency || 2} inference đồng thời
            </p>
          </div>
        </Card>
      </div>

      {/* Operational Metrics (Admin view) */}
      {metricsData && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Inference Governor Details */}
            <Card className="p-5">
              <CardHeader className="p-0 pb-3">
                <h3 className="font-semibold text-slate-200 flex items-center gap-2">
                  <Zap className="w-5 h-5 text-amber-400" /> Hoạt động Inference Governor
                </h3>
              </CardHeader>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-lg">
                    <span className="text-xs text-slate-400">Inference Đang Xử lý</span>
                    <div className="text-2xl font-bold text-amber-400 mt-1">
                      {metricsData.inference_governor.active_inferences} / {metricsData.inference_governor.max_concurrency}
                    </div>
                  </div>
                  <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-lg">
                    <span className="text-xs text-slate-400">Hàng đợi Chờ Slot</span>
                    <div className="text-2xl font-bold text-indigo-400 mt-1">
                      {metricsData.inference_governor.queued_requests} / {metricsData.inference_governor.max_queue_size}
                    </div>
                  </div>
                </div>

                <div className="space-y-2 text-sm text-slate-300 pt-2 border-t border-slate-800">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Tổng inference đã cấp quyền (Admitted):</span>
                    <span className="font-semibold">{metricsData.inference_governor.total_admitted}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Bị từ chối do quá tải hàng đợi (Rejected):</span>
                    <span className="font-semibold text-rose-400">{metricsData.inference_governor.total_rejected}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Bị quá thời gian chờ trong queue (Timeouts):</span>
                    <span className="font-semibold text-amber-400">{metricsData.inference_governor.total_timeouts}</span>
                  </div>
                </div>
              </div>
            </Card>

            {/* Agent Runtime Recovery Status */}
            <Card className="p-5">
              <CardHeader className="p-0 pb-3">
                <h3 className="font-semibold text-slate-200 flex items-center gap-2">
                  <Clock className="w-5 h-5 text-indigo-400" /> Trạng thái Thực thi & Phục hồi Agent
                </h3>
              </CardHeader>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-lg">
                    <span className="text-xs text-slate-400">Agent Runs Đang Chạy</span>
                    <div className="text-2xl font-bold text-emerald-400 mt-1">
                      {metricsData.agent_runtime.active_runs}
                    </div>
                  </div>
                  <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-lg">
                    <span className="text-xs text-slate-400">Agent Runs Bị Kẹt (Stuck)</span>
                    <div className={`text-2xl font-bold mt-1 ${metricsData.agent_runtime.stuck_runs_count > 0 ? "text-rose-400" : "text-slate-400"}`}>
                      {metricsData.agent_runtime.stuck_runs_count}
                    </div>
                  </div>
                </div>

                <div className="space-y-2 text-sm text-slate-300 pt-2 border-t border-slate-800">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Cơ chế Lease Locking:</span>
                    <span className="font-semibold text-emerald-400">Kích hoạt (TTL: 60s)</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Giới hạn phục hồi tối đa:</span>
                    <span className="font-semibold">3 lần thử / run</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Phục hồi an toàn thao tác WRITE:</span>
                    <span className="font-semibold text-indigo-400">Bảo vệ chống Duplicate Side-effects</span>
                  </div>
                </div>
              </div>
            </Card>
          </div>

          {/* Stuck Runs Detail Table if any */}
          {metricsData.agent_runtime.stuck_runs.length > 0 && (
            <Card className="p-5">
              <CardHeader className="p-0 pb-3">
                <h3 className="font-semibold text-rose-300 flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5 text-rose-400" /> Danh sách Agent Runs Cần Phục Hồi
                </h3>
              </CardHeader>
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-slate-300">
                  <thead className="text-xs text-slate-400 uppercase bg-slate-900/80 border-b border-slate-800">
                    <tr>
                      <th className="px-4 py-3">Run ID</th>
                      <th className="px-4 py-3">Mục tiêu (Goal)</th>
                      <th className="px-4 py-3">Trạng thái</th>
                      <th className="px-4 py-3">Số lần thử</th>
                      <th className="px-4 py-3">Hết hạn Lease</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {metricsData.agent_runtime.stuck_runs.map((r) => (
                      <tr key={r.run_id} className="hover:bg-slate-900/40">
                        <td className="px-4 py-3 font-mono text-xs">{r.run_id.slice(0, 8)}...</td>
                        <td className="px-4 py-3">{r.goal}</td>
                        <td className="px-4 py-3">
                          <span className="px-2 py-0.5 rounded text-xs bg-amber-500/20 text-amber-300">
                            {r.status}
                          </span>
                        </td>
                        <td className="px-4 py-3">{r.recovery_attempts} / 3</td>
                        <td className="px-4 py-3 text-xs text-slate-400">{r.lease_expires_at || "Hết hạn"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
};
