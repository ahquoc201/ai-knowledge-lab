import React from "react";
import { Message } from "../../types";
import { Bot, User, BookOpen, Clock } from "lucide-react";
import { DisplaySource } from "./EvidencePanel";

interface ChatMessageItemProps {
  message: Partial<Message> & {
    role: "user" | "assistant" | "system";
    content: string;
    isStreaming?: boolean;
    streamingStatus?: string;
    model_name?: string;
  };
  sources?: DisplaySource[];
  onSelectSource?: (source: DisplaySource) => void;
}

export const ChatMessageItem: React.FC<ChatMessageItemProps> = ({
  message,
  sources = [],
  onSelectSource,
}) => {
  const isUser = message.role === "user";

  // Match [Source N] patterns (allowing spaces, colons, case-insensitive)
  const renderFormattedContent = (content: string) => {
    const parts: React.ReactNode[] = [];
    const pattern = /\[\s*Source\s*[:#-]?\s*(\d+)\s*\]/gi;
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = pattern.exec(content)) !== null) {
      const start = match.index;
      const end = pattern.lastIndex;
      const sourceNum = parseInt(match[1], 10);

      // Add text before match
      if (start > lastIndex) {
        parts.push(content.substring(lastIndex, start));
      }

      // Find matching source
      const matchedSource = sources.find(
        (s) => s.source_index === sourceNum
      );

      parts.push(
        <button
          key={`citation-${match.index}`}
          type="button"
          onClick={() => {
            if (matchedSource && onSelectSource) {
              onSelectSource(matchedSource);
            }
          }}
          disabled={!matchedSource}
          className={`inline-flex items-center gap-1 mx-1 px-1.5 py-0.5 rounded text-[11px] font-semibold transition-colors align-baseline ${
            matchedSource
              ? "bg-primary/10 text-primary hover:bg-primary/20 border border-primary/30 cursor-pointer shadow-xs active:scale-95"
              : "bg-surface-hover text-foreground-muted border border-border cursor-default"
          }`}
          title={
            matchedSource
              ? `Xem bằng chứng trích dẫn [Source ${sourceNum}]: ${matchedSource.document_title || "Tài liệu"}`
              : `Nguồn [Source ${sourceNum}]`
          }
        >
          <BookOpen className="h-3 w-3 inline shrink-0" />
          <span>Source {sourceNum}</span>
        </button>
      );

      lastIndex = end;
    }

    if (lastIndex < content.length) {
      parts.push(content.substring(lastIndex));
    }

    return parts;
  };

  return (
    <div
      className={`flex gap-3.5 py-4 px-4 sm:px-6 transition-colors ${
        isUser ? "bg-transparent" : "bg-surface/60 border-y border-border/40"
      }`}
    >
      {/* Avatar */}
      <div
        className={`h-8 w-8 rounded-xl flex items-center justify-center shrink-0 text-white shadow-xs ${
          isUser
            ? "bg-slate-700 text-slate-100"
            : "bg-primary text-white"
        }`}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* Message Body */}
      <div className="flex-1 space-y-2 overflow-hidden">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-xs text-foreground">
              {isUser ? "Bạn" : "AI Knowledge Assistant"}
            </span>
            {!isUser && (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">
                {message.model_name || "qwen3:1.7b"}
              </span>
            )}
          </div>
          {message.created_at && (
            <span className="text-[10px] text-foreground-muted flex items-center gap-1">
              <Clock className="h-2.5 w-2.5" />
              {new Date(message.created_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          )}
        </div>

        {/* Content */}
        <div className="text-sm leading-relaxed text-foreground whitespace-pre-wrap break-words">
          {renderFormattedContent(message.content)}
          {message.isStreaming && (
            <span className="inline-block w-2 h-4 ml-1 bg-primary align-middle animate-pulse" />
          )}
        </div>

        {/* Streaming Status Subtitle */}
        {message.streamingStatus && (
          <div className="text-[11px] text-primary flex items-center gap-1.5 pt-1">
            <span className="inline-block h-2 w-2 rounded-full bg-primary animate-ping" />
            <span>{message.streamingStatus}</span>
          </div>
        )}

        {/* Evidence Pill Bar at bottom of Assistant Message */}
        {!isUser && sources.length > 0 && !message.isStreaming && (
          <div className="pt-2 border-t border-border/50 flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-medium text-foreground-muted mr-1 flex items-center gap-1">
              <BookOpen className="h-3 w-3" />
              Bằng chứng tham chiếu:
            </span>
            {sources.map((src) => (
              <button
                key={`source-pill-${src.source_index}`}
                type="button"
                onClick={() => onSelectSource && onSelectSource(src)}
                className="inline-flex items-center gap-1.5 text-[11px] px-2 py-0.5 rounded-md bg-background hover:bg-surface-hover border border-border text-foreground transition-all hover:border-primary/50 text-left"
              >
                <span className="font-semibold text-primary">[{src.source_index}]</span>
                <span className="line-clamp-1 max-w-[160px]" title={src.document_title || "Tài liệu"}>
                  {src.document_title || `Tài liệu #${src.document_id.slice(0, 8)}`}
                </span>
                <span className="text-[10px] text-foreground-muted">
                  ({Math.round(src.similarity * 100)}%)
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
