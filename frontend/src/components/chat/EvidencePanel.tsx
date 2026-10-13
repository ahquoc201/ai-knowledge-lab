import React from "react";
import { RAGSource, MessageSource } from "../../types";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { X, BookOpen, FileText, CheckCircle2 } from "lucide-react";

export type DisplaySource = RAGSource | MessageSource;

interface EvidencePanelProps {
  source: DisplaySource | null;
  onClose: () => void;
}

export const EvidencePanel: React.FC<EvidencePanelProps> = ({ source, onClose }) => {
  if (!source) return null;

  const similarityPercent = Math.round(source.similarity * 100);

  return (
    <aside
      className="flex flex-col h-full w-80 lg:w-96 border-l border-border bg-surface shadow-sm overflow-hidden animate-in slide-in-from-right duration-200"
      aria-label="Khung bằng chứng trích dẫn"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-surface-hover/30">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-primary" />
          <h3 className="font-semibold text-sm text-foreground">
            Bằng chứng [Source {source.source_index}]
          </h3>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onClose}
          className="h-8 w-8 p-0 text-foreground-muted hover:text-foreground"
          aria-label="Đóng bảng bằng chứng"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Document Info */}
        <div className="rounded-xl border border-border bg-background p-4 space-y-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-foreground-muted shrink-0" />
              <span className="font-medium text-xs text-foreground line-clamp-1" title={source.document_title || "Tài liệu"}>
                {source.document_title || `Tài liệu #${source.document_id.slice(0, 8)}`}
              </span>
            </div>
            <Badge status="ready" size="sm">
              <CheckCircle2 className="h-3 w-3 mr-1 inline" />
              Độ khớp: {similarityPercent}%
            </Badge>
          </div>

          <div className="grid grid-cols-2 gap-2 text-[11px] text-foreground-muted pt-2 border-t border-border/60">
            <div>
              <span className="text-foreground-muted/80 block">Chunk thứ tự:</span>
              <span className="font-medium text-foreground">#{source.chunk_index + 1}</span>
            </div>
            {source.char_start !== undefined && source.char_start !== null && (
              <div>
                <span className="text-foreground-muted/80 block">Vị trí ký tự:</span>
                <span className="font-medium text-foreground">
                  {source.char_start} - {source.char_end}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Excerpt */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-foreground tracking-wide uppercase">
              Đoạn trích dẫn nguyên gốc
            </label>
            <span className="text-[11px] text-foreground-muted">
              {source.content.length} ký tự
            </span>
          </div>

          <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 text-xs leading-relaxed text-foreground font-sans relative">
            <div className="absolute top-0 left-0 bottom-0 w-1 bg-primary rounded-l-xl" />
            <p className="whitespace-pre-wrap pl-1">{source.content}</p>
          </div>
        </div>

        {/* RAG Verification Note */}
        <div className="rounded-lg bg-surface-hover/50 p-3 text-[11px] text-foreground-muted space-y-1">
          <span className="font-semibold text-foreground block">
            Cơ chế bảo chứng tri thức
          </span>
          <p>
            Đoạn văn bản trên được trích xuất trực tiếp từ vector index và chuyển cho mô hình LLM làm ngữ cảnh đối chiếu. Trợ lý chỉ được phép trả lời dựa trên nội dung này.
          </p>
        </div>
      </div>
    </aside>
  );
};
