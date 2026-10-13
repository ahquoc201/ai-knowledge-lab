import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import { Document } from "../types";
import { Card, CardHeader, CardTitle, CardDescription } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Spinner } from "../components/ui/Spinner";
import {
  FileText,
  CheckCircle2,
  Clock,
  AlertTriangle,
  ArrowRight,
  ShieldCheck,
  Server,
  Zap,
} from "lucide-react";

interface DashboardPageProps {
  onNavigateToDocs: () => void;
  onNavigateToChat: () => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  onNavigateToDocs,
  onNavigateToChat,
}) => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    const fetchDocs = async () => {
      try {
        const res = await api.documents.list({ limit: 100 });
        if (mounted) setDocuments(res.items);
      } catch {
        // Handled silently for dashboard summary
      } finally {
        if (mounted) setIsLoading(false);
      }
    };
    fetchDocs();
    return () => {
      mounted = false;
    };
  }, []);

  const totalDocs = documents.length;
  const readyDocs = documents.filter((d) => d.status === "ready").length;
  const processingDocs = documents.filter(
    (d) => d.status === "processing" || d.status === "pending"
  ).length;
  const failedDocs = documents.filter((d) => d.status === "failed").length;

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Welcome Banner */}
      <div className="rounded-2xl border border-border bg-gradient-to-r from-surface to-background p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-primary-subtle text-primary border border-blue-200 mb-2">
            AI Knowledge Lab v0.2.0
          </span>
          <h2 className="text-xl font-bold text-foreground">
            Trung tâm điều khiển tri thức doanh nghiệp
          </h2>
          <p className="text-xs text-foreground-muted mt-1 max-w-2xl">
            Quản trị tài liệu, giám sát tiến trình vector hóa pgvector và thực hiện hỏi đáp RAG
            với cơ chế kiểm định nguồn dẫn chứng nghiêm ngặt.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="secondary" onClick={onNavigateToDocs}>
            <FileText className="h-4 w-4 mr-2" />
            Quản lý tài liệu
          </Button>
          <Button variant="primary" onClick={onNavigateToChat}>
            <Zap className="h-4 w-4 mr-2" />
            Hỏi đáp AI
          </Button>
        </div>
      </div>

      {/* KPI Stats */}
      {isLoading ? (
        <div className="flex h-32 items-center justify-center">
          <Spinner size="md" label="Đang tải dữ liệu tổng quan..." />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-foreground-subtle uppercase">
                  Tổng tài liệu
                </p>
                <p className="text-2xl font-extrabold text-foreground mt-1">{totalDocs}</p>
              </div>
              <div className="rounded-lg bg-blue-50 p-2.5 text-primary">
                <FileText className="h-6 w-6" />
              </div>
            </div>
            <p className="text-[11px] text-foreground-muted mt-3">
              Toàn bộ văn bản đã nạp vào workspace
            </p>
          </Card>

          <Card>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-foreground-subtle uppercase">
                  Sẵn sàng truy xuất
                </p>
                <p className="text-2xl font-extrabold text-status-ready-text mt-1">{readyDocs}</p>
              </div>
              <div className="rounded-lg bg-status-ready-bg p-2.5 text-status-ready-text">
                <CheckCircle2 className="h-6 w-6" />
              </div>
            </div>
            <p className="text-[11px] text-foreground-muted mt-3">
              Đã vector hóa & đánh chỉ mục thành công
            </p>
          </Card>

          <Card>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-foreground-subtle uppercase">
                  Đang xử lý / Hàng đợi
                </p>
                <p className="text-2xl font-extrabold text-status-pending-text mt-1">
                  {processingDocs}
                </p>
              </div>
              <div className="rounded-lg bg-status-pending-bg p-2.5 text-status-pending-text">
                <Clock className="h-6 w-6" />
              </div>
            </div>
            <p className="text-[11px] text-foreground-muted mt-3">
              Đang trong pipeline chunking & embedding
            </p>
          </Card>

          <Card>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-foreground-subtle uppercase">
                  Lỗi xử lý
                </p>
                <p className="text-2xl font-extrabold text-status-failed-text mt-1">
                  {failedDocs}
                </p>
              </div>
              <div className="rounded-lg bg-status-failed-bg p-2.5 text-status-failed-text">
                <AlertTriangle className="h-6 w-6" />
              </div>
            </div>
            <p className="text-[11px] text-foreground-muted mt-3">
              {failedDocs > 0 ? "Cần reprocess lại tài liệu lỗi" : "Không có tài liệu nào bị lỗi"}
            </p>
          </Card>
        </div>
      )}

      {/* Engine & Pipeline Health Status Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Kiến trúc bảo mật & Kiểm soát ảo giác (Guardrails)</CardTitle>
            <CardDescription>
              Các chốt chặn kiểm duyệt nội dung đang hoạt động trong hệ thống RAG
            </CardDescription>
          </CardHeader>

          <div className="space-y-4">
            <div className="flex items-start gap-3 rounded-lg border border-border p-3.5 bg-background">
              <ShieldCheck className="h-5 w-5 text-status-ready-text mt-0.5" />
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="text-xs font-bold text-foreground">Strict Citation Validator</h4>
                  <Badge status="ready" size="sm">Active</Badge>
                </div>
                <p className="text-xs text-foreground-muted mt-1">
                  Mọi câu trả lời của mô hình ngôn ngữ lớn (LLM) bắt buộc phải gắn thẻ nguồn dẫn chứng hợp lệ
                  dạng [Source N]. Các câu trả lời trích nguồn sai hoặc bịa đặt chỉ mục sẽ tự động bị từ chối.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3 rounded-lg border border-border p-3.5 bg-background">
              <Server className="h-5 w-5 text-primary mt-0.5" />
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="text-xs font-bold text-foreground">PgVector Semantic Search</h4>
                  <Badge status="ready" size="sm">Active</Badge>
                </div>
                <p className="text-xs text-foreground-muted mt-1">
                  Chỉ mục cosine distance trên PostgreSQL bảo đảm tốc độ tìm kiếm dưới 100ms
                  ngay cả khi kho tài liệu tăng trưởng lớn.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3 rounded-lg border border-border p-3.5 bg-background">
              <Zap className="h-5 w-5 text-amber-600 mt-0.5" />
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="text-xs font-bold text-foreground">Standardized Refusal Policy</h4>
                  <Badge status="ready" size="sm">Enforced</Badge>
                </div>
                <p className="text-xs text-foreground-muted mt-1">
                  Khi tài liệu không đủ dữ kiện, hệ thống tự động trả về thông báo từ chối tiêu chuẩn,
                  ngăn chặn suy đoán hoặc đưa ra dữ liệu không có căn cứ.
                </p>
              </div>
            </div>
          </div>
        </Card>

        {/* Recent Documents Snippet */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Tài liệu mới nạp</CardTitle>
                <CardDescription>Danh sách tài liệu gần đây</CardDescription>
              </div>
              <button
                onClick={onNavigateToDocs}
                className="text-xs font-semibold text-primary hover:underline flex items-center gap-1"
              >
                Tất cả <ArrowRight className="h-3 w-3" />
              </button>
            </div>
          </CardHeader>

          {documents.length === 0 ? (
            <div className="py-8 text-center text-xs text-foreground-muted">
              Chưa có tài liệu nào trong thư viện.
            </div>
          ) : (
            <div className="space-y-3">
              {documents.slice(0, 5).map((doc) => (
                <div
                  key={doc.id}
                  className="flex items-center justify-between rounded-md border border-border p-2.5 bg-background text-xs"
                >
                  <div className="truncate pr-2">
                    <p className="font-medium text-foreground truncate">{doc.title}</p>
                    <p className="text-[10px] text-foreground-subtle">
                      {new Date(doc.created_at).toLocaleDateString("vi-VN")}
                    </p>
                  </div>
                  <Badge status={doc.status} size="sm">
                    {doc.status}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};
