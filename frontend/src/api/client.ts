import {
  AuditEventListResponse,
  AuthTokenResponse,
  ChatStreamEvent,
  Conversation,
  ConversationDetail,
  CreateDocumentPayload,
  Document,
  DocumentListResponse,
  RAGResponse,
  User,
  Workspace,
  WorkspaceInvitation,
  WorkspaceMember,
  WorkspaceRole,
  AgentRun,
  AgentRunListResponse,
  AgentRunCreatePayload,
  AgentExecutionEvent,
  BenchmarkRunResponse,
  BenchmarkRunListResponse,
  BenchmarkRunCreatePayload,
  BenchmarkComparisonResponse,
  ModelRegistryEntry,
  ModelRegistryListResponse,
  ModelBenchmarkProfile,
  ModelRoutingPolicy,
  ModelRoutingPreviewRequest,
  ModelRoutingPreviewResponse,
  ModelRoutingDecision,
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
  const workspaceId = localStorage.getItem("current_workspace_id");
  const headers = new Headers(options.headers || {});

  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  if (workspaceId && !headers.has("X-Workspace-Id")) {
    headers.set("X-Workspace-Id", workspaceId);
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
      const workspaceId = localStorage.getItem("current_workspace_id");
      const headers = new Headers({
        "Content-Type": "application/json",
      });
      if (token) {
        headers.set("Authorization", `Bearer ${token}`);
      }
      if (workspaceId && !headers.has("X-Workspace-Id")) {
        headers.set("X-Workspace-Id", workspaceId);
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

  workspaces: {
    list: (): Promise<Workspace[]> =>
      request<Workspace[]>("/workspaces"),

    create: (payload: { name: string; description?: string }): Promise<Workspace> =>
      request<Workspace>("/workspaces", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    get: (id: string): Promise<Workspace> =>
      request<Workspace>(`/workspaces/${id}`),

    update: (id: string, payload: { name?: string; description?: string }): Promise<Workspace> =>
      request<Workspace>(`/workspaces/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),

    delete: (id: string): Promise<void> =>
      request<void>(`/workspaces/${id}`, {
        method: "DELETE",
      }),

    leave: (id: string): Promise<void> =>
      request<void>(`/workspaces/${id}/leave`, {
        method: "POST",
      }),

    listMembers: (id: string): Promise<WorkspaceMember[]> =>
      request<WorkspaceMember[]>(`/workspaces/${id}/members`),

    updateMemberRole: (id: string, userId: string, role: WorkspaceRole): Promise<WorkspaceMember> =>
      request<WorkspaceMember>(`/workspaces/${id}/members/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      }),

    removeMember: (id: string, userId: string): Promise<void> =>
      request<void>(`/workspaces/${id}/members/${userId}`, {
        method: "DELETE",
      }),

    createInvitation: (id: string, payload: { email: string; role: WorkspaceRole }): Promise<WorkspaceInvitation> =>
      request<WorkspaceInvitation>(`/workspaces/${id}/invitations`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    acceptInvitation: (token: string): Promise<void> =>
      request<void>("/workspaces/invitations/accept", {
        method: "POST",
        body: JSON.stringify({ token }),
      }),

    listAuditEvents: (id: string, params?: { limit?: number; offset?: number }): Promise<AuditEventListResponse> => {
      const searchParams = new URLSearchParams();
      if (params?.limit) searchParams.set("limit", params.limit.toString());
      if (params?.offset) searchParams.set("offset", params.offset.toString());
      const queryStr = searchParams.toString();
      return request<AuditEventListResponse>(`/workspaces/${id}/audit-events${queryStr ? `?${queryStr}` : ""}`);
    },
  },

  agent: {
    createRun: (payload: AgentRunCreatePayload, blocking = true): Promise<AgentRun> =>
      request<AgentRun>(`/agent/runs?blocking=${blocking}`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    listRuns: (params?: { limit?: number; offset?: number; mineOnly?: boolean }): Promise<AgentRunListResponse> => {
      const searchParams = new URLSearchParams();
      if (params?.limit) searchParams.set("limit", params.limit.toString());
      if (params?.offset) searchParams.set("offset", params.offset.toString());
      if (params?.mineOnly) searchParams.set("mine_only", "true");
      const queryStr = searchParams.toString();
      return request<AgentRunListResponse>(`/agent/runs${queryStr ? `?${queryStr}` : ""}`);
    },

    getRun: (runId: string): Promise<AgentRun> =>
      request<AgentRun>(`/agent/runs/${runId}`),

    cancelRun: (runId: string): Promise<AgentRun> =>
      request<AgentRun>(`/agent/runs/${runId}/cancel`, {
        method: "POST",
      }),

    getEvents: (runId: string, afterSeq = 0): Promise<AgentExecutionEvent[]> =>
      request<AgentExecutionEvent[]>(`/agent/runs/${runId}/events?after_seq=${afterSeq}`),

    approveAction: (approvalId: string, reason?: string, blocking = true): Promise<AgentRun> =>
      request<AgentRun>(`/agent/approvals/${approvalId}/approve?blocking=${blocking}`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      }),

    rejectAction: (approvalId: string, reason?: string, blocking = true): Promise<AgentRun> =>
      request<AgentRun>(`/agent/approvals/${approvalId}/reject?blocking=${blocking}`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      }),
  },

  benchmarks: {
    listDatasets: (): Promise<
      Array<{
        id: string;
        name: string;
        version: string;
        description: string;
        case_count: number;
      }>
    > => request("/benchmarks/datasets"),

    listRuns: (params?: { limit?: number; offset?: number }): Promise<BenchmarkRunListResponse> => {
      const searchParams = new URLSearchParams();
      if (params?.limit) searchParams.set("limit", params.limit.toString());
      if (params?.offset) searchParams.set("offset", params.offset.toString());
      const queryStr = searchParams.toString();
      return request<BenchmarkRunListResponse>(`/benchmarks/runs${queryStr ? `?${queryStr}` : ""}`);
    },

    getRun: (runId: string): Promise<BenchmarkRunResponse> =>
      request<BenchmarkRunResponse>(`/benchmarks/runs/${runId}`),

    triggerRun: (payload: BenchmarkRunCreatePayload): Promise<BenchmarkRunResponse> =>
      request<BenchmarkRunResponse>("/benchmarks/runs", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    compareRuns: (runId: string, baselineId: string): Promise<BenchmarkComparisonResponse> =>
      request<BenchmarkComparisonResponse>(`/benchmarks/runs/${runId}/compare/${baselineId}`),
  },

  models: {
    list: (): Promise<ModelRegistryListResponse> => request("/models"),
    refresh: (): Promise<{ message: string; discovered_count: number; updated_count: number }> =>
      request("/models/refresh", { method: "POST" }),
    get: (id: string): Promise<ModelRegistryEntry> => request(`/models/${id}`),
    toggleActive: (id: string, isActive: boolean): Promise<ModelRegistryEntry> =>
      request(`/models/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: isActive }),
      }),
    getBenchmarks: (id: string): Promise<ModelBenchmarkProfile[]> =>
      request(`/models/${id}/benchmarks`),
  },

  modelRouting: {
    getPolicy: (workspaceId?: string): Promise<ModelRoutingPolicy> => {
      const q = workspaceId ? `?workspace_id=${workspaceId}` : "";
      return request(`/model-routing/policies${q}`);
    },
    updatePolicy: (policyId: string, payload: Partial<ModelRoutingPolicy>): Promise<ModelRoutingPolicy> =>
      request(`/model-routing/policies/${policyId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    preview: (payload: ModelRoutingPreviewRequest): Promise<ModelRoutingPreviewResponse> =>
      request("/model-routing/preview", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    listDecisions: (params?: {
      workspaceId?: string;
      taskType?: string;
      limit?: number;
      offset?: number;
    }): Promise<ModelRoutingDecision[]> => {
      const searchParams = new URLSearchParams();
      if (params?.workspaceId) searchParams.set("workspace_id", params.workspaceId);
      if (params?.taskType) searchParams.set("task_type", params.taskType);
      if (params?.limit) searchParams.set("limit", params.limit.toString());
      if (params?.offset) searchParams.set("offset", params.offset.toString());
      const queryStr = searchParams.toString();
      return request(`/model-routing/decisions${queryStr ? `?${queryStr}` : ""}`);
    },
  },

  health: {
    check: (): Promise<{ status: string }> => request<{ status: string }>("/health"),
  },

  reliability: {
    getReady: (): Promise<any> => request("/health/ready"),
    getMetrics: (workspaceId?: string): Promise<any> => {
      const q = workspaceId ? `?workspace_id=${workspaceId}` : "";
      return request(`/reliability/metrics${q}`);
    },
    recoverStuck: (): Promise<any> =>
      request("/reliability/recover-stuck", { method: "POST" }),
  },
};
