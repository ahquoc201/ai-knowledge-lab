import React, { useState, useRef, useEffect } from "react";
import { Button } from "../ui/Button";
import { Send, Square } from "lucide-react";

interface ChatComposerProps {
  onSendMessage: (query: string) => void;
  isStreaming: boolean;
  onStopStreaming: () => void;
  disabled?: boolean;
}

export const ChatComposer: React.FC<ChatComposerProps> = ({
  onSendMessage,
  isStreaming,
  onStopStreaming,
  disabled = false,
}) => {
  const [query, setQuery] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!isStreaming && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [isStreaming]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    const trimmed = query.trim();
    if (!trimmed || isStreaming || disabled) return;
    onSendMessage(trimmed);
    setQuery("");
  };

  return (
    <div className="border-t border-border bg-surface p-4">
      <div className="max-w-4xl mx-auto space-y-2">
        <div className="relative flex items-end rounded-xl border border-border bg-background focus-within:border-primary focus-within:ring-1 focus-within:ring-primary shadow-xs transition-all">
          <textarea
            ref={textareaRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isStreaming
                ? "Mô hình đang sinh câu trả lời..."
                : "Đặt câu hỏi về tài liệu của bạn (VD: PostgreSQL hỗ trợ transaction như thế nào?)..."
            }
            disabled={isStreaming || disabled}
            rows={2}
            className="w-full resize-none bg-transparent px-4 py-3 text-sm text-foreground placeholder:text-foreground-muted focus:outline-hidden disabled:opacity-60 max-h-40"
          />

          <div className="p-2 shrink-0">
            {isStreaming ? (
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={onStopStreaming}
                className="h-9 px-3 gap-1.5 shadow-xs"
                title="Dừng sinh câu trả lời"
              >
                <Square className="h-3.5 w-3.5 fill-current" />
                <span className="text-xs">Dừng</span>
              </Button>
            ) : (
              <Button
                type="button"
                variant="primary"
                size="sm"
                onClick={handleSubmit}
                disabled={!query.trim() || disabled}
                className="h-9 w-9 p-0 rounded-lg shadow-xs"
                title="Gửi câu hỏi (Enter)"
              >
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between px-1 text-[11px] text-foreground-muted">
          <span>
            Bảo chứng trích dẫn: Câu trả lời luôn đi kèm bằng chứng từ tài liệu nội bộ
          </span>
          <span className="hidden sm:inline">
            <kbd className="px-1.5 py-0.5 rounded bg-surface border border-border font-mono text-[10px]">Enter</kbd> gửi, <kbd className="px-1.5 py-0.5 rounded bg-surface border border-border font-mono text-[10px]">Shift + Enter</kbd> xuống dòng
          </span>
        </div>
      </div>
    </div>
  );
};
