import React, { useEffect, useState, useCallback, useRef } from "react";
import { api } from "../api/client";
import { Document, DocumentStatus } from "../types";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Badge } from "../components/ui/Badge";
import { Modal } from "../components/ui/Modal";
import { Alert } from "../components/ui/Alert";
import { Spinner } from "../components/ui/Spinner";
import { Card } from "../components/ui/Card";
import { useWorkspace } from "../context/WorkspaceContext";
import {
  Plus,
  Search,
  RefreshCw,
  Trash2,
  FileText,
  RotateCcw,
  Eye,
  Calendar,
  UploadCloud,
  AlertCircle,
  FileUp,
  CheckCircle2,
  Clock,
  X,
  Lock,
} from "lucide-react";

export const DocumentsPage: React.FC = () => {
  const { currentWorkspace, canEdit, isViewer, workspaceVersion } = useWorkspace();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Create / Upload Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"upload" | "text">("upload");

  // File Upload State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Text Document State
  const [newTitle, setNewTitle] = useState("");
  const [newContent, setNewContent] = useState("");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

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
  }, [fetchDocuments, workspaceVersion, currentWorkspace?.id]);

  // Auto-poll when any document is in pending or processing status
  useEffect(() => {
    const hasActiveJobs = documents.some(
      (doc) => doc.status === "pending" || doc.status === "processing"
    );

    if (!hasActiveJobs) return;

    const interval = setInterval(() => {
      fetchDocuments(true);
    }, 2500);

    return () => clearInterval(interval);
  }, [documents, fetchDocuments]);

  const handleOpenModal = (tab: "upload" | "text" = "upload") => {
    setActiveTab(tab);
    setFormError(null);
    setSelectedFile(null);
    setNewTitle("");
    setNewContent("");
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    if (isSubmitting) return;
    setIsModalOpen(false);
    setSelectedFile(null);
    setNewTitle("");
    setNewContent("");
    setFormError(null);
  };

  const handleFileDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      validateAndSetFile(file);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      validateAndSetFile(file);
    }
  };

  const validateAndSetFile = (file: File) => {
    const supportedExtensions = [".pdf", ".docx", ".md", ".txt"];
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!supportedExtensions.includes(ext)) {
      setFormError(`Định dạng "${ext}" không được hỗ trợ. Chỉ chấp nhận .pdf, .docx, .md, .txt.`);
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setFormError("Kích thước tệp vượt quá giới hạn tối đa 5MB.");
      return;
    }
    setFormError(null);
    setSelectedFile(file);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (activeTab === "upload") {
      if (!selectedFile) {
        setFormError("Vui lòng chọn một tệp văn bản để tải lên.");
        return;
      }
      setIsSubmitting(true);
      try {
        await api.documents.upload(selectedFile);
        handleCloseModal();
        await fetchDocuments(true);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Lỗi khi tải tệp lên.";
        setFormError(msg);
      } finally {
        setIsSubmitting(false);
      }
    } else {
      if (!newTitle.trim()) {
        setFormError("Vui lòng nhập tiêu đề tài liệu.");
        return;
      }
      if (!newContent.trim()) {
        setFormError("Vui lòng nhập nội dung tài liệu.");
        return;
      }
      setIsSubmitting(true);
      try {
        await api.documents.create({
          title: newTitle.trim(),
          content: newContent.trim(),
        });
        handleCloseModal();
        await fetchDocuments(true);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Lỗi khi tạo tài liệu.";
        setFormError(msg);
      } finally {
        setIsSubmitting(false);
      }
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

  const renderStatusBadge = (status: string, errorMessage?: string | null) => {
    switch (status) {
      case "ready":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="h-3 w-3" />
            Ready
          </span>
        );
      case "processing":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            <RotateCcw className="h-3 w-3 animate-spin" />
            Processing...
          </span>
        );
      case "pending":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-slate-500/10 text-slate-600 dark:text-slate-400 border border-slate-500/20">
            <Clock className="h-3 w-3" />
            Queued
          </span>
        );
      case "failed":
        return (
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20 cursor-help"
            title={errorMessage || "Xử lý thất bại"}
          >
            <AlertCircle className="h-3 w-3" />
            Failed
          </span>
        );
      default:
        return <Badge status={status as DocumentStatus}>{status}</Badge>;
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-foreground">Thư viện tài liệu (Document Library)</h2>
            {isViewer && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300 border border-gray-300 dark:border-gray-700">
                <Lock className="h-3 w-3" />
                Chỉ đọc (Read Only)
              </span>
            )}
          </div>
          <p className="text-xs text-foreground-muted mt-0.5">
            Quản lý kho tri thức doanh nghiệp trong không gian{" "}
            <span className="font-semibold text-foreground">{currentWorkspace?.name || "Workspace"}</span>.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <Button variant="outline" size="sm" onClick={() => fetchDocuments()}>
            <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
            Làm mới
          </Button>
          {canEdit && (
            <>
              <Button variant="outline" size="sm" onClick={() => handleOpenModal("upload")}>
                <UploadCloud className="h-4 w-4 mr-1.5 text-primary" />
                Tải lên tệp
              </Button>
              <Button variant="primary" size="sm" onClick={() => handleOpenModal("text")}>
                <Plus className="h-4 w-4 mr-1.5" />
                Thêm tài liệu
              </Button>
            </>
          )}
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
                : "Hãy tải lên tệp đầu tiên (PDF, DOCX, MD, TXT) hoặc nhập văn bản để kích hoạt tự động hóa RAG."}
            </p>
            {!searchQuery && canEdit && (
              <div className="mt-5 flex items-center justify-center gap-2">
                <Button variant="outline" size="sm" onClick={() => handleOpenModal("upload")}>
                  <UploadCloud className="h-4 w-4 mr-1.5" />
                  Tải lên tệp
                </Button>
                <Button variant="primary" size="sm" onClick={() => handleOpenModal("text")}>
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
                          <div className="truncate max-w-xs md:max-w-md">
                            <span className="font-semibold block truncate">{doc.title}</span>
                            {doc.source_name && doc.source_name !== doc.title && (
                              <span className="text-[10px] text-foreground-subtle block truncate">
                                {doc.source_name}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>

                      <td className="py-3.5 px-4 uppercase text-[10px] font-bold text-foreground-subtle">
                        {doc.source_type}
                      </td>

                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-2">
                          {renderStatusBadge(doc.status, doc.error_message)}
                          {doc.status === "failed" && doc.error_message && (
                            <span
                              className="text-[10px] text-rose-500 max-w-[140px] truncate hidden md:inline-block"
                              title={doc.error_message}
                            >
                              {doc.error_message}
                            </span>
                          )}
                        </div>
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

                          {canEdit && (
                            <>
                              <Button
                                variant="ghost"
                                size="sm"
                                title="Reprocess Vector Index"
                                isLoading={isBusy}
                                disabled={doc.status === "processing"}
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
                            </>
                          )}
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

      {/* Ingestion & Create Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title={activeTab === "upload" ? "Tải lên tệp tài liệu" : "Thêm tài liệu tri thức mới"}
        description={
          activeTab === "upload"
            ? "Tự động trích xuất nội dung, phân đoạn chunks và vector hóa lưu trữ vào cơ sở tri thức."
            : "Nội dung sẽ được phân đoạn thành các chunks và vector hóa lưu vào pgvector."
        }
        size="lg"
        footer={
          <>
            <Button
              variant="outline"
              size="sm"
              disabled={isSubmitting}
              onClick={handleCloseModal}
            >
              Hủy
            </Button>
            <Button
              variant="primary"
              size="sm"
              isLoading={isSubmitting}
              onClick={handleSubmit}
            >
              Lưu và Xử lý (Ingest)
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {/* Navigation Tabs */}
          <div className="flex border-b border-border text-xs font-semibold">
            <button
              type="button"
              onClick={() => {
                setActiveTab("upload");
                setFormError(null);
              }}
              className={`pb-2.5 px-3 border-b-2 flex items-center gap-1.5 transition-colors ${
                activeTab === "upload"
                  ? "border-primary text-primary"
                  : "border-transparent text-foreground-muted hover:text-foreground"
              }`}
            >
              <UploadCloud className="h-3.5 w-3.5" />
              Tải tệp lên (File Upload)
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveTab("text");
                setFormError(null);
              }}
              className={`pb-2.5 px-3 border-b-2 flex items-center gap-1.5 transition-colors ${
                activeTab === "text"
                  ? "border-primary text-primary"
                  : "border-transparent text-foreground-muted hover:text-foreground"
              }`}
            >
              <FileText className="h-3.5 w-3.5" />
              Nhập văn bản thô (Direct Text)
            </button>
          </div>

          {formError && (
            <Alert type="error" onClose={() => setFormError(null)}>
              {formError}
            </Alert>
          )}

          {activeTab === "upload" ? (
            <div className="space-y-4">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.md,.txt"
                onChange={handleFileSelect}
                className="hidden"
              />

              {!selectedFile ? (
                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setIsDragging(true);
                  }}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={handleFileDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                    isDragging
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50 hover:bg-background/50"
                  }`}
                >
                  <FileUp className="mx-auto h-10 w-10 text-foreground-subtle" />
                  <p className="mt-3 text-xs font-medium text-foreground">
                    Kéo thả tệp vào đây hoặc{" "}
                    <span className="text-primary underline">nhấp để duyệt tệp</span>
                  </p>
                  <p className="mt-1 text-[11px] text-foreground-muted">
                    Hỗ trợ: PDF (.pdf), Word (.docx), Markdown (.md), Văn bản thuần (.txt) • Tối đa 5MB
                  </p>
                </div>
              ) : (
                <div className="flex items-center justify-between p-3.5 rounded-lg border border-border bg-background">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded bg-primary/10 text-primary">
                      <FileText className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-foreground truncate max-w-sm">
                        {selectedFile.name}
                      </p>
                      <p className="text-[11px] text-foreground-muted">
                        {(selectedFile.size / 1024).toFixed(1)} KB • {selectedFile.type || "Tài liệu văn bản"}
                      </p>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedFile(null);
                    }}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              )}

              <p className="text-[11px] text-foreground-subtle">
                Hệ thống sẽ tự động đưa tệp vào hàng đợi Celery + Redis và kích hoạt quy trình trích xuất văn bản mà không cần thao tác thêm.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
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
          )}
        </div>
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
                {renderStatusBadge(selectedDoc.status, selectedDoc.error_message)}
              </div>
              <div>
                <span className="text-foreground-subtle font-medium">Loại nguồn: </span>
                <span className="font-semibold uppercase text-foreground">{selectedDoc.source_type}</span>
              </div>
              <div>
                <span className="text-foreground-subtle font-medium">Tên file nguồn: </span>
                <span className="font-medium text-foreground truncate block">
                  {selectedDoc.source_name || selectedDoc.title}
                </span>
              </div>
              <div>
                <span className="text-foreground-subtle font-medium">Định dạng MIME: </span>
                <span className="font-medium text-foreground">{selectedDoc.mime_type || "N/A"}</span>
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

            {selectedDoc.status === "failed" && selectedDoc.error_message && (
              <div className="rounded-lg bg-rose-500/10 border border-rose-500/20 p-3.5 text-rose-600 dark:text-rose-400">
                <div className="flex items-center gap-2 font-semibold">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  <span>Chi tiết lỗi xử lý tài liệu:</span>
                </div>
                <p className="mt-1 text-xs font-mono">{selectedDoc.error_message}</p>
              </div>
            )}

            <div>
              <h4 className="font-semibold text-foreground uppercase tracking-wider mb-1.5">
                Nội dung tài liệu đã trích xuất:
              </h4>
              <div className="max-h-60 overflow-y-auto rounded-md border border-border bg-background p-3 text-xs leading-relaxed text-foreground whitespace-pre-wrap font-mono">
                {selectedDoc.content || "(Tài liệu đang xử lý hoặc chưa có nội dung text)"}
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};
