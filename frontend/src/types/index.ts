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
  document_title?: string | null;
  char_start?: number | null;
  char_end?: number | null;
}

export interface RAGResponse {
  conversation_id: string;
  answer: string;
  sources: RAGSource[];
}

export interface MessageSource {
  id?: string;
  source_index: number;
  document_id: string;
  chunk_id: string;
  chunk_index: number;
  content: string;
  similarity: number;
  document_title?: string | null;
  char_start?: number | null;
  char_end?: number | null;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  sources?: MessageSource[];
}

export interface Conversation {
  id: string;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export type ChatStreamEventType =
  | "retrieval_started"
  | "retrieval_completed"
  | "generation_started"
  | "token"
  | "answer_completed"
  | "error";

export interface ChatStreamEvent {
  event: ChatStreamEventType;
  query?: string;
  conversation_id?: string;
  message_id?: string | null;
  sources?: RAGSource[];
  token?: string;
  answer?: string;
  error?: string;
}
