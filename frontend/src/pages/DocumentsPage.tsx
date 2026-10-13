import React, { useEffect, useState, useCallback } from "react";
import { api } from "../api/client";
import { Document, DocumentStatus } from "../types";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Badge } from "../components/ui/Badge";
import { Modal } from "../components/ui/Modal";
import { Alert } from "../components/ui/Alert";
import { Spinner } from "../components/ui/Spinner";
import { Card } from "../components/ui/Card";
import {
  Plus,
  Search,
  RefreshCw,
  Trash2,
  FileText,
  RotateCcw,
  Eye,
  Calendar,
} from "lucide-react";

export const DocumentsPage: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Create Modal State
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newContent, setNewContent] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Detail Modal State
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);

  // Action Loading
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  const fetchDocuments = useCallback(async (silent = false) => {
    if (!silent) setIsLoading(true);
    setError(null);
    try {
      const res = await api.documents.list({
        search: searchQuery.trim() || undefined,
        limit: 100,
      });
      setDocuments(res.items);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Không thể tải danh sách tài liệu.";
      setError(msg);
    } finally {
      if (!silent) setIsLoading(false);
    }
  }, [searchQuery]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleCreateDocument = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) {
      setCreateError("Vui lòng nhập tiêu đề tài liệu.");
      return;
    }
    if (!newContent.trim()) {
      setCreateError("Vui lòng nhập nội dung tài liệu.");
      return;
    }

    setIsSubmitting(true);
    setCreateError(null);
    try {
      await api.documents.create({
        title: newTitle.trim(),
        content: newContent.trim(),
      });
      setIsCreateOpen(false);
      setNewTitle("");
      setNewContent("");
      await fetchDocuments(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Lỗi khi tạo tài liệu.";
      setCreateError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReprocess = async (id: string) => {
    setActionLoadingId(id);
    try {
      await api.documents.reprocess(id);
      await fetchDocuments(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Lỗi khi chạy lại vector hóa.";
      setError(msg);
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleDelete = async (id: string, title: string) => {
    if (!window.confirm(`Bạn có chắc chắn muốn xóa tài liệu "${title}"?`)) {
      return;
    }
    setActionLoadingId(id);
    try {
      await api.documents.delete(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
      if (selectedDoc?.id === id) setSelectedDoc(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Lỗi khi xóa tài liệu.";
      setError(msg);
    } finally {
      setActionLoadingId(null);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-foreground">Thư viện tài liệu (Document Library)</h2>
          <p className="text-xs text-foreground-muted mt-0.5">
            Quản lý kho tri thức, vector hóa văn bản và kiểm tra trạng thái index RAG.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <Button variant="outline" size="sm" onClick={() => fetchDocuments()}>
            <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
            Làm mới
          </Button>
          <Button variant="primary" size="sm" onClick={() => setIsCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-1.5" />
            Thêm tài liệu
          </Button>
        </div>
      </div>

      {/* Search and Filters Bar */}
      <Card className="p-3">
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-foreground-subtle" />
            <input
              type="text"
              placeholder="Tìm kiếm tài liệu theo tiêu đề..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-md border border-border bg-background pl-9 pr-4 py-2 text-xs text-foreground placeholder-foreground-subtle focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          <Button variant="secondary" size="sm" onClick={() => fetchDocuments()}>
            Tìm kiếm
          </Button>
        </div>
      </Card>

      {/* Global Error Banner */}
      {error && (
        <Alert type="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Documents Table */}
      <Card className="p-0 overflow-hidden">
        {isLoading ? (
          <div className="flex h-48 items-center justify-center">
            <Spinner size="md" label="Đang tải dữ liệu thư viện..." />
          </div>
        ) : documents.length === 0 ? (
          <div className="py-16 text-center">
            <FileText className="mx-auto h-12 w-12 text-foreground-subtle/50" />
            <h3 className="mt-3 text-sm font-semibold text-foreground">
              {searchQuery ? "Không tìm thấy tài liệu phù hợp" : "Chưa có tài liệu nào"}
            </h3>
            <p className="mt-1 text-xs text-foreground-muted max-w-sm mx-auto">
              {searchQuery
                ? `Không có kết quả nào khớp với "${searchQuery}". Hãy thử từ khóa khác.`
                : "Hãy nạp tài liệu đầu tiên để bắt đầu quá trình trích xuất kiến thức và vector hóa."}
            </p>
            {!searchQuery && (
              <div className="mt-5">
                <Button variant="primary" size="sm" onClick={() => setIsCreateOpen(true)}>
                  <Plus className="h-4 w-4 mr-1.5" />
                  Tạo tài liệu mới
                </Button>
              </div>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-border bg-background/50 font-semibold text-foreground-muted">
                  <th className="py-3 px-4">Tiêu đề tài liệu</th>
                  <th className="py-3 px-4">Loại nguồn</th>
                  <th className="py-3 px-4">Trạng thái RAG</th>
                  <th className="py-3 px-4">Thời gian tạo</th>
                  <th className="py-3 px-4 text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {documents.map((doc) => {
                  const isBusy = actionLoadingId === doc.id;
                  return (
                    <tr key={doc.id} className="hover:bg-background/40 transition-colors">
                      <td className="py-3.5 px-4 font-medium text-foreground">
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-foreground-subtle flex-shrink-0" />
                          <span className="truncate max-w-xs md:max-w-md font-semibold">
                            {doc.title}
                          </span>
                        </div>
                      </td>

                      <td className="py-3.5 px-4 uppercase text-[10px] font-bold text-foreground-subtle">
                        {doc.source_type}
                      </td>

                      <td className="py-3.5 px-4">
                        <Badge status={doc.status as DocumentStatus}>
                          {doc.status}
                        </Badge>
                      </td>

                      <td className="py-3.5 px-4 text-foreground-muted">
                        <div className="flex items-center gap-1.5">
                          <Calendar className="h-3.5 w-3.5 text-foreground-subtle" />
                          <span>{new Date(doc.created_at).toLocaleString("vi-VN")}</span>
                        </div>
                      </td>

                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            variant="ghost"
                            size="sm"
                            title="Xem chi tiết"
                            onClick={() => setSelectedDoc(doc)}
                          >
                            <Eye className="h-3.5 w-3.5" />
                          </Button>

                          <Button
                            variant="ghost"
                            size="sm"
                            title="Reprocess Vector Index"
                            isLoading={isBusy}
                            onClick={() => handleReprocess(doc.id)}
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                          </Button>

                          <Button
                            variant="ghost"
                            size="sm"
                            title="Xóa tài liệu"
                            disabled={isBusy}
                            onClick={() => handleDelete(doc.id, doc.title)}
                            className="text-status-failed-text hover:bg-status-failed-bg"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Create Document Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => !isSubmitting && setIsCreateOpen(false)}
        title="Thêm tài liệu tri thức mới"
        description="Nội dung sẽ được phân đoạn thành các chunks và vector hóa lưu vào pgvector."
        size="lg"
        footer={
          <>
            <Button
              variant="outline"
              size="sm"
              disabled={isSubmitting}
              onClick={() => setIsCreateOpen(false)}
            >
              Hủy
            </Button>
            <Button
              variant="primary"
              size="sm"
              isLoading={isSubmitting}
              onClick={handleCreateDocument}
            >
              Lưu và Xử lý (Ingest)
            </Button>
          </>
        }
      >
        <form onSubmit={handleCreateDocument} className="space-y-4">
          {createError && (
            <Alert type="error" onClose={() => setCreateError(null)}>
              {createError}
            </Alert>
          )}

          <Input
            label="Tiêu đề tài liệu"
            placeholder="Ví dụ: Chính sách bảo mật dữ liệu khách hàng 2026"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            required
          />

          <div>
            <label className="block text-xs font-semibold text-foreground uppercase tracking-wider mb-1.5">
              Nội dung văn bản
            </label>
            <textarea
              rows={8}
              placeholder="Dán hoặc nhập toàn bộ nội dung văn bản cần nạp vào hệ thống..."
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              required
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-xs text-foreground placeholder-foreground-subtle focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <p className="mt-1 text-[11px] text-foreground-subtle">
              Tài liệu sẽ được xử lý tự động trong background pipeline và chuyển sang trạng thái
              'ready' sau khi vector hóa.
            </p>
          </div>
        </form>
      </Modal>

      {/* View Document Detail Modal */}
      <Modal
        isOpen={!!selectedDoc}
        onClose={() => setSelectedDoc(null)}
        title={selectedDoc?.title || "Chi tiết tài liệu"}
        description={`ID: ${selectedDoc?.id || ""}`}
        size="lg"
        footer={
          <Button variant="secondary" size="sm" onClick={() => setSelectedDoc(null)}>
            Đóng
          </Button>
        }
      >
        {selectedDoc && (
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-4 rounded-lg bg-background p-3.5 border border-border">
              <div>
                <span className="text-foreground-subtle font-medium">Trạng thái: </span>
                <Badge status={selectedDoc.status as DocumentStatus} size="sm">
                  {selectedDoc.status}
                </Badge>
              </div>
              <div>
                <span className="text-foreground-subtle font-medium">Loại nguồn: </span>
                <span className="font-semibold uppercase text-foreground">{selectedDoc.source_type}</span>
              </div>
              <div>
                <span className="text-foreground-subtle font-medium">Ngày tạo: </span>
                <span className="text-foreground">
                  {new Date(selectedDoc.created_at).toLocaleString("vi-VN")}
                </span>
              </div>
              <div>
                <span className="text-foreground-subtle font-medium">Cập nhật: </span>
                <span className="text-foreground">
                  {new Date(selectedDoc.updated_at).toLocaleString("vi-VN")}
                </span>
              </div>
            </div>

            <div>
              <h4 className="font-semibold text-foreground uppercase tracking-wider mb-1.5">
                Nội dung tài liệu:
              </h4>
              <div className="max-h-60 overflow-y-auto rounded-md border border-border bg-background p-3 text-xs leading-relaxed text-foreground whitespace-pre-wrap font-mono">
                {selectedDoc.content || "(Tài liệu không có nội dung text thô hoặc nội dung file)"}
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};
