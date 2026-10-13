import { AuthTokenResponse, CreateDocumentPayload, Document, DocumentListResponse, User } from "../types";

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
  },

  health: {
    check: (): Promise<{ status: string }> => request<{ status: string }>("/health"),
  },
};
