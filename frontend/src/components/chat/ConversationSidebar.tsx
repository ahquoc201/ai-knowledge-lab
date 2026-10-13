import React, { useState } from "react";
import { Conversation } from "../../types";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/Spinner";
import { Plus, MessageSquare, Trash2, Clock, Check, X } from "lucide-react";

interface ConversationSidebarProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  isLoading: boolean;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onDeleteConversation: (id: string) => Promise<void>;
}

export const ConversationSidebar: React.FC<ConversationSidebarProps> = ({
  conversations,
  activeConversationId,
  isLoading,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
}) => {
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const confirmDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      setIsDeleting(true);
      await onDeleteConversation(id);
      setDeletingId(null);
    } finally {
      setIsDeleting(false);
    }
  };

  const cancelDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    setDeletingId(null);
  };

  return (
    <div className="flex flex-col h-full w-64 lg:w-72 border-r border-border bg-surface shrink-0">
      {/* Top Action */}
      <div className="p-3 border-b border-border">
        <Button
          variant="primary"
          size="sm"
          onClick={onNewChat}
          className="w-full justify-center gap-2 shadow-sm font-medium"
        >
          <Plus className="h-4 w-4" />
          <span>Cuộc trò chuyện mới</span>
        </Button>
      </div>

      {/* Conversations List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {isLoading && conversations.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-foreground-muted">
            <Spinner size="sm" className="mb-2" />
            <span className="text-xs">Đang tải lịch sử...</span>
          </div>
        ) : conversations.length === 0 ? (
          <div className="text-center py-10 px-4 text-xs text-foreground-muted">
            <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-30" />
            <p className="font-medium text-foreground">Chưa có hội thoại nào</p>
            <p className="mt-1">Nhập câu hỏi để bắt đầu phiên mới</p>
          </div>
        ) : (
          conversations.map((conv) => {
            const isActive = conv.id === activeConversationId;
            const isConfirming = deletingId === conv.id;

            return (
              <div
                key={conv.id}
                role="button"
                tabIndex={0}
                onClick={() => onSelectConversation(conv.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    onSelectConversation(conv.id);
                  }
                }}
                className={`group relative flex items-center justify-between gap-2 px-3 py-2.5 rounded-lg text-xs cursor-pointer transition-colors text-left ${
                  isActive
                    ? "bg-primary/10 text-primary font-medium"
                    : "text-foreground-muted hover:bg-surface-hover hover:text-foreground"
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  <MessageSquare className={`h-4 w-4 shrink-0 ${isActive ? "text-primary" : "text-foreground-muted"}`} />
                  <div className="min-w-0 flex-1">
                    <p className={`truncate text-xs ${isActive ? "text-primary font-medium" : "text-foreground"}`}>
                      {conv.title || "Cuộc hội thoại chưa đặt tên"}
                    </p>
                    <span className="text-[10px] text-foreground-muted/70 flex items-center gap-1 mt-0.5">
                      <Clock className="h-2.5 w-2.5" />
                      {new Date(conv.created_at).toLocaleDateString([], {
                        month: "numeric",
                        day: "numeric",
                      })}
                    </span>
                  </div>
                </div>

                {/* Actions */}
                {isConfirming ? (
                  <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      title="Xác nhận xoá"
                      onClick={(e) => confirmDelete(e, conv.id)}
                      disabled={isDeleting}
                      className="p-1 rounded bg-status-failed text-white hover:bg-status-failed/90 transition-colors"
                    >
                      <Check className="h-3 w-3" />
                    </button>
                    <button
                      type="button"
                      title="Huỷ"
                      onClick={cancelDelete}
                      className="p-1 rounded bg-surface-hover text-foreground-muted hover:text-foreground transition-colors"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    title="Xoá cuộc trò chuyện"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeletingId(conv.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded text-foreground-muted hover:text-status-failed hover:bg-surface-hover transition-all"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
