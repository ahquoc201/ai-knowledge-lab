export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
}

export interface Document {
  id: string;
  user_id: string;
  title: string;
  content: string | null;
  source_type: "text" | "file";
  source_name: string | null;
  mime_type: string | null;
  status: DocumentStatus;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: Document[];
  total: number;
  limit: number;
  offset: number;
}

export interface CreateDocumentPayload {
  title: string;
  content: string;
  source_type?: "text";
}

export interface RAGSource {
  source_index: number;
  document_id: string;
  chunk_id: string;
  chunk_index: number;
  content: string;
  similarity: number;
}

export interface RAGResponse {
  conversation_id: string;
  answer: string;
  sources: RAGSource[];
}
