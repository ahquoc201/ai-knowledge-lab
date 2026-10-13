import React from "react";
import { Badge } from "../components/ui/Badge";
import { Sparkles, ShieldCheck } from "lucide-react";

export const ChatPlaceholderPage: React.FC = () => {
  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="rounded-2xl border border-border bg-surface p-8 shadow-sm">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-white shadow-md">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-foreground">AI Chat / RAG Assistant</h2>
              <Badge status="processing" size="sm">T260022 In Progress</Badge>
            </div>
            <p className="text-xs text-foreground-muted mt-0.5">
              Evidence-Driven Conversational Interface with Strict Citations
            </p>
          </div>
        </div>

        <div className="rounded-xl bg-background border border-border p-6 my-6 space-y-4">
          <div className="flex items-start gap-3">
            <ShieldCheck className="h-5 w-5 text-status-ready-text mt-0.5" />
            <div>
              <h4 className="text-sm font-semibold text-foreground">
                Grounded Retrieval-Augmented Generation
              </h4>
              <p className="text-xs text-foreground-muted mt-1 leading-relaxed">
                Tại tầng Backend, toàn bộ pipeline RAG (Semantic Search, Bounded Context Builder,
                Ollama LLM Provider, Strict Citation Validator) đã hoàn thiện và vượt qua 356 automated tests.
                Giao diện chat tương tác trực tiếp với trích dẫn click-to-source sẽ được bàn giao trong
                task T260022.
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
          <div className="rounded-lg border border-border p-3.5 bg-background">
            <span className="font-bold text-foreground block mb-1">1. Query Bounding</span>
            <p className="text-foreground-muted">Giới hạn context tối đa và kiểm soát token tiêu thụ.</p>
          </div>
          <div className="rounded-lg border border-border p-3.5 bg-background">
            <span className="font-bold text-foreground block mb-1">2. Strict Citations</span>
            <p className="text-foreground-muted">Kiểm tra marker [Source N] trước khi hiển thị câu trả lời.</p>
          </div>
          <div className="rounded-lg border border-border p-3.5 bg-background">
            <span className="font-bold text-foreground block mb-1">3. Refusal Policy</span>
            <p className="text-foreground-muted">Từ chối chuẩn mực khi tài liệu không có căn cứ xác thực.</p>
          </div>
        </div>
      </div>
    </div>
  );
};
