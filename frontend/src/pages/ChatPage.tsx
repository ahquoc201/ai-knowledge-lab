import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  Conversation,
  ChatStreamEvent,
} from "../types";
import { api, ApiError } from "../api/client";
import { ConversationSidebar } from "../components/chat/ConversationSidebar";
import { ChatMessageItem } from "../components/chat/ChatMessageItem";
import { ChatComposer } from "../components/chat/ChatComposer";
import { EvidencePanel, DisplaySource } from "../components/chat/EvidencePanel";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { Spinner } from "../components/ui/Spinner";
import { useWorkspace } from "../context/WorkspaceContext";
import {
  Sparkles,
  ShieldCheck,
  BookOpen,
  FileQuestion,
  Upload,
} from "lucide-react";

interface StreamingMessageState {
  id?: string;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  sources?: DisplaySource[];
  isStreaming?: boolean;
  streamingStatus?: string;
  model_name?: string;
}

interface ChatPageProps {
  onNavigateToDocs?: () => void;
}

export const ChatPage: React.FC<ChatPageProps> = ({ onNavigateToDocs }) => {
  const { currentWorkspace, workspaceVersion } = useWorkspace();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<StreamingMessageState[]>([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedSource, setSelectedSource] = useState<DisplaySource | null>(null);
  const [readyDocsCount, setReadyDocsCount] = useState<number | null>(null);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  // Fetch initial conversations and documents count, and react to workspace switch
  useEffect(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsStreaming(false);
    }
    setActiveConversationId(null);
    setMessages([]);
    setSelectedSource(null);
    setErrorBanner(null);

    loadConversations();
    checkDocuments();
  }, [workspaceVersion, currentWorkspace?.id]);

  const loadConversations = async () => {
    try {
      setIsLoadingConversations(true);
      const list = await api.conversations.list();
      setConversations(list);
    } catch (err) {
      console.error("Failed to load conversations:", err);
    } finally {
      setIsLoadingConversations(false);
    }
  };

  const checkDocuments = async () => {
    try {
      const res = await api.documents.list({ limit: 1 });
      setReadyDocsCount(res.total);
    } catch {
      setReadyDocsCount(null);
    }
  };

  // Load conversation details when activeConversationId changes
  const handleSelectConversation = async (convId: string) => {
    if (isStreaming) {
      handleStopStreaming();
    }
    setActiveConversationId(convId);
    setSelectedSource(null);
    setErrorBanner(null);

    try {
      setIsLoadingMessages(true);
      const detail = await api.conversations.get(convId);
      setMessages(
        detail.messages.map((m) => ({
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.content,
          created_at: m.created_at,
          sources: m.sources,
        }))
      );
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Không thể tải tin nhắn.";
      setErrorBanner(msg);
    } finally {
      setIsLoadingMessages(false);
    }
  };

  const handleNewChat = () => {
    if (isStreaming) {
      handleStopStreaming();
    }
    setActiveConversationId(null);
    setMessages([]);
    setSelectedSource(null);
    setErrorBanner(null);
  };

  const handleDeleteConversation = async (convId: string) => {
    try {
      await api.conversations.delete(convId);
      setConversations((prev) => prev.filter((c) => c.id !== convId));
      if (activeConversationId === convId) {
        handleNewChat();
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Không thể xoá cuộc trò chuyện.";
      setErrorBanner(msg);
    }
  };

  const handleStopStreaming = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
    setMessages((prev) =>
      prev.map((m) =>
        m.isStreaming
          ? {
              ...m,
              isStreaming: false,
              streamingStatus: undefined,
              content: m.content || "Đã dừng sinh câu trả lời.",
            }
          : m
      )
    );
  };

  const handleSendMessage = async (query: string) => {
    setErrorBanner(null);

    // 1. Add User Message
    const userMsg: StreamingMessageState = {
      role: "user",
      content: query,
      created_at: new Date().toISOString(),
    };

    // 2. Add placeholder Assistant Message
    const assistantPlaceholder: StreamingMessageState = {
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
      isStreaming: true,
      streamingStatus: "Đang bắt đầu truy xuất...",
      sources: [],
    };

    setMessages((prev) => [...prev, userMsg, assistantPlaceholder]);
    setIsStreaming(true);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    let accumulatedContent = "";
    let currentSources: DisplaySource[] = [];
    let targetConvId = activeConversationId;

    try {
      await api.rag.askStream(
        {
          query,
          limit: 5,
          conversation_id: targetConvId || undefined,
        },
        (event: ChatStreamEvent) => {
          switch (event.event) {
            case "retrieval_started":
              if (event.conversation_id && !targetConvId) {
                targetConvId = event.conversation_id;
                setActiveConversationId(event.conversation_id);
              }
              setMessages((prev) =>
                prev.map((m, idx) =>
                  idx === prev.length - 1
                    ? { ...m, streamingStatus: "Đang truy xuất vector embeddings..." }
                    : m
                )
              );
              break;

            case "retrieval_completed":
              currentSources = event.sources || [];
              setMessages((prev) =>
                prev.map((m, idx) =>
                  idx === prev.length - 1
                    ? {
                        ...m,
                        sources: currentSources,
                        streamingStatus:
                          currentSources.length > 0
                            ? `Tìm thấy ${currentSources.length} đoạn trích dẫn. Đang khởi chạy mô hình...`
                            : "Không có tài liệu liên quan.",
                      }
                    : m
                )
              );
              break;

            case "generation_started":
              setMessages((prev) =>
                prev.map((m, idx) =>
                  idx === prev.length - 1
                    ? {
                        ...m,
                        streamingStatus: "Mô hình đang sinh câu trả lời...",
                        model_name: (event as unknown as Record<string, unknown>).model_name as string || m.model_name,
                      }
                    : m
                )
              );
              break;

            case "token":
              accumulatedContent += event.token || "";
              setMessages((prev) =>
                prev.map((m, idx) =>
                  idx === prev.length - 1
                    ? {
                        ...m,
                        content: accumulatedContent,
                        streamingStatus: undefined,
                      }
                    : m
                )
              );
              scrollToBottom();
              break;

            case "answer_completed":
              if (event.conversation_id && !targetConvId) {
                targetConvId = event.conversation_id;
                setActiveConversationId(event.conversation_id);
              }
              setMessages((prev) =>
                prev.map((m, idx) =>
                  idx === prev.length - 1
                    ? {
                        ...m,
                        id: event.message_id || undefined,
                        content: event.answer || accumulatedContent,
                        sources: event.sources || currentSources,
                        model_name: (event as unknown as Record<string, unknown>).model_name as string || m.model_name,
                        isStreaming: false,
                        streamingStatus: undefined,
                      }
                    : m
                )
              );
              setIsStreaming(false);
              loadConversations();
              break;

            case "error":
              setMessages((prev) =>
                prev.map((m, idx) =>
                  idx === prev.length - 1
                    ? {
                        ...m,
                        content: `Lỗi: ${event.error || "Quá trình sinh bị gián đoạn."}`,
                        isStreaming: false,
                        streamingStatus: undefined,
                      }
                    : m
                )
              );
              setIsStreaming(false);
              break;
          }
        },
        abortController.signal
      );
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        // User voluntarily stopped
        return;
      }
      const errDetail =
        err instanceof ApiError
          ? err.detail
          : err instanceof Error
          ? err.message
          : "Không thể kết nối đến máy chủ AI.";

      setMessages((prev) =>
        prev.map((m, idx) =>
          idx === prev.length - 1
            ? {
                ...m,
                content: `Lỗi kết nối: ${errDetail}`,
                isStreaming: false,
                streamingStatus: undefined,
              }
            : m
        )
      );
      setIsStreaming(false);
    } finally {
      abortControllerRef.current = null;
    }
  };

  const samplePrompts = [
    "PostgreSQL hỗ trợ ACID và concurrency control như thế nào?",
    "Các tài liệu trong hệ thống đề cập những chính sách gì?",
    "Quy trình xử lý dữ liệu và vector search của hệ thống?",
  ];

  return (
    <div className="flex h-[calc(100vh-8rem)] w-full rounded-2xl border border-border bg-background shadow-xs overflow-hidden">
      {/* 1. Left Sidebar: Conversation History */}
      <ConversationSidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        isLoading={isLoadingConversations}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onDeleteConversation={handleDeleteConversation}
      />

      {/* 2. Main Chat Area */}
      <div className="flex flex-1 flex-col h-full min-w-0 bg-background overflow-hidden relative">
        {/* Zero documents warning banner */}
        {readyDocsCount === 0 && (
          <div className="px-4 py-2.5 bg-status-processing/10 border-b border-status-processing/30 flex items-center justify-between text-xs text-foreground">
            <div className="flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-primary shrink-0" />
              <span>
                Kho tri thức hiện chưa có tài liệu nào. Trợ lý AI chỉ trả lời từ tài liệu được trích xuất.
              </span>
            </div>
            {onNavigateToDocs && (
              <Button
                variant="outline"
                size="sm"
                onClick={onNavigateToDocs}
                className="h-7 text-xs gap-1.5"
              >
                <Upload className="h-3 w-3" />
                <span>Nạp tài liệu ngay</span>
              </Button>
            )}
          </div>
        )}

        {/* Global Error Banner */}
        {errorBanner && (
          <div className="p-3">
            <Alert
              type="error"
              onClose={() => setErrorBanner(null)}
            >
              {errorBanner}
            </Alert>
          </div>
        )}

        {/* Message List */}
        <div className="flex-1 overflow-y-auto">
          {isLoadingMessages ? (
            <div className="flex flex-col items-center justify-center h-full text-foreground-muted gap-2">
              <Spinner size="md" />
              <span className="text-xs">Đang tải cuộc hội thoại...</span>
            </div>
          ) : messages.length === 0 ? (
            /* Empty State */
            <div className="flex flex-col items-center justify-center h-full max-w-lg mx-auto text-center px-4 py-8 space-y-6">
              <div className="h-14 w-14 rounded-2xl bg-primary/10 text-primary flex items-center justify-center shadow-xs">
                <Sparkles className="h-7 w-7" />
              </div>

              <div className="space-y-1.5">
                <h3 className="text-lg font-bold text-foreground">
                  Trợ lý Tri thức AI (Evidence-Driven)
                </h3>
                <p className="text-xs text-foreground-muted leading-relaxed">
                  Hỏi đáp thông minh với khả năng đối chiếu dữ liệu nội bộ. Mọi thông tin phản hồi đều được kiểm chứng và trích dẫn trực tiếp từ các đoạn văn bản nguồn.
                </p>
              </div>

              <div className="flex items-center gap-4 text-xs text-foreground-muted bg-surface py-2 px-4 rounded-xl border border-border">
                <span className="flex items-center gap-1.5">
                  <ShieldCheck className="h-4 w-4 text-status-ready-text" />
                  Bảo chứng nguồn gốc
                </span>
                <span className="h-3 w-px bg-border" />
                <span className="flex items-center gap-1.5">
                  <BookOpen className="h-4 w-4 text-primary" />
                  Trích dẫn click-to-view
                </span>
              </div>

              {/* Sample Prompts */}
              <div className="w-full space-y-2 pt-2 text-left">
                <span className="text-[11px] font-semibold text-foreground-muted uppercase tracking-wider block px-1">
                  Gợi ý câu hỏi bắt đầu:
                </span>
                <div className="grid grid-cols-1 gap-2">
                  {samplePrompts.map((prompt, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handleSendMessage(prompt)}
                      className="flex items-center gap-2 p-3 text-xs rounded-xl border border-border bg-surface hover:bg-surface-hover text-foreground hover:border-primary/40 transition-colors text-left"
                    >
                      <FileQuestion className="h-4 w-4 text-primary shrink-0" />
                      <span className="line-clamp-1">{prompt}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="divide-y divide-border/20">
              {messages.map((msg, index) => (
                <ChatMessageItem
                  key={msg.id || index}
                  message={msg}
                  sources={msg.sources}
                  onSelectSource={(src) => setSelectedSource(src)}
                />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* 3. Bottom Composer */}
        <ChatComposer
          onSendMessage={handleSendMessage}
          isStreaming={isStreaming}
          onStopStreaming={handleStopStreaming}
        />
      </div>

      {/* 4. Right Side Evidence Panel */}
      <EvidencePanel
        source={selectedSource}
        onClose={() => setSelectedSource(null)}
      />
    </div>
  );
};
