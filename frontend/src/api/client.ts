import {
  AuthTokenResponse,
  ChatStreamEvent,
  Conversation,
  ConversationDetail,
  CreateDocumentPayload,
  Document,
  DocumentListResponse,
  RAGResponse,
  User,
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("auth_token");
  const headers = new Headers(options.headers || {});

  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let detail = "An unexpected error occurred.";
    try {
      const errorJson = await response.json();
      detail = errorJson.detail || JSON.stringify(errorJson);
    } catch {
      detail = response.statusText || detail;
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

export const api = {
  auth: {
    login: (email: string, password: string): Promise<AuthTokenResponse> =>
      request<AuthTokenResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }),

    register: (email: string, password: string): Promise<User> =>
      request<User>("/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }),
  },

  documents: {
    list: (params?: { limit?: number; offset?: number; search?: string }): Promise<DocumentListResponse> => {
      const searchParams = new URLSearchParams();
      if (params?.limit) searchParams.set("limit", params.limit.toString());
      if (params?.offset) searchParams.set("offset", params.offset.toString());
      if (params?.search) searchParams.set("search", params.search);
      const queryStr = searchParams.toString();
      return request<DocumentListResponse>(`/documents${queryStr ? `?${queryStr}` : ""}`);
    },

    get: (id: string): Promise<Document> =>
      request<Document>(`/documents/${id}`),

    create: (payload: CreateDocumentPayload): Promise<Document> =>
      request<Document>("/documents", {
        method: "POST",
        body: JSON.stringify({
          ...payload,
          source_type: "text",
        }),
      }),

    delete: (id: string): Promise<void> =>
      request<void>(`/documents/${id}`, {
        method: "DELETE",
      }),

    reprocess: (id: string): Promise<Document> =>
      request<Document>(`/documents/${id}/reprocess`, {
        method: "POST",
      }),

    upload: (file: File): Promise<Document> => {
      const formData = new FormData();
      formData.append("file", file);
      return request<Document>("/documents/upload", {
        method: "POST",
        body: formData,
      });
    },
  },

  conversations: {
    list: (): Promise<Conversation[]> =>
      request<Conversation[]>("/conversations"),

    get: (id: string): Promise<ConversationDetail> =>
      request<ConversationDetail>(`/conversations/${id}`),

    create: (title?: string): Promise<Conversation> =>
      request<Conversation>("/conversations", {
        method: "POST",
        body: JSON.stringify({ title }),
      }),

    delete: (id: string): Promise<void> =>
      request<void>(`/conversations/${id}`, {
        method: "DELETE",
      }),
  },

  rag: {
    ask: (payload: { query: string; limit?: number; conversation_id?: string }): Promise<RAGResponse> =>
      request<RAGResponse>("/rag/ask", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    askStream: async (
      payload: { query: string; limit?: number; conversation_id?: string },
      onEvent: (event: ChatStreamEvent) => void,
      signal?: AbortSignal
    ): Promise<void> => {
      const token = localStorage.getItem("auth_token");
      const headers = new Headers({
        "Content-Type": "application/json",
      });
      if (token) {
        headers.set("Authorization", `Bearer ${token}`);
      }

      const response = await fetch(`${API_BASE}/rag/ask/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        signal,
      });

      if (!response.ok) {
        let detail = "An unexpected error occurred.";
        try {
          const err = await response.json();
          detail = err.detail || JSON.stringify(err);
        } catch {
          detail = response.statusText || detail;
        }
        throw new ApiError(response.status, detail);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new ApiError(500, "ReadableStream not supported by browser");
      }

      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        // Keep the last partial chunk in the buffer
        buffer = parts.pop() || "";

        for (const block of parts) {
          const trimmed = block.trim();
          if (!trimmed) continue;

          for (const line of trimmed.split("\n")) {
            if (line.startsWith("data: ")) {
              const dataStr = line.slice(6).trim();
              if (dataStr) {
                try {
                  const eventObj: ChatStreamEvent = JSON.parse(dataStr);
                  onEvent(eventObj);
                } catch {
                  // Ignore parse error for malformed lines
                }
              }
            }
          }
        }
      }

      if (buffer.trim()) {
        for (const line of buffer.trim().split("\n")) {
          if (line.startsWith("data: ")) {
            const dataStr = line.slice(6).trim();
            if (dataStr) {
              try {
                const eventObj: ChatStreamEvent = JSON.parse(dataStr);
                onEvent(eventObj);
              } catch {
                // Ignore parse error
              }
            }
          }
        }
      }
    },
  },

  health: {
    check: (): Promise<{ status: string }> => request<{ status: string }>("/health"),
  },
};
