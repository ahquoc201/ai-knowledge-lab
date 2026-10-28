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
  error_message?: string | null;
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

export type WorkspaceRole = "owner" | "admin" | "editor" | "viewer";

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  status?: string;
  is_personal: boolean;
  created_at: string;
  updated_at: string;
  role?: WorkspaceRole;
  current_user_role?: WorkspaceRole;
  member_count?: number;
}

export interface WorkspaceMember {
  id: string;
  workspace_id?: string;
  user_id: string;
  email?: string;
  user_email: string;
  full_name?: string | null;
  role: WorkspaceRole;
  created_at: string;
  updated_at?: string;
}

export interface WorkspaceInvitation {
  id: string;
  workspace_id: string;
  email: string;
  role: WorkspaceRole;
  inviter_id?: string | null;
  status: string;
  expires_at: string;
  created_at: string;
  invitation_token?: string;
}

export interface SecurityAuditEvent {
  id: string;
  workspace_id: string;
  actor_id?: string | null;
  actor_email?: string | null;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  details?: Record<string, unknown> | null;
  ip_address?: string | null;
  created_at: string;
}

export interface AuditEventListResponse {
  items: SecurityAuditEvent[];
  total: number;
  limit: number;
  offset: number;
}


// =========================================================================
// Governed Agent Runtime (T260025)
// =========================================================================

export type AgentRunStatus =
  | "created"
  | "running"
  | "awaiting_approval"
  | "completed"
  | "failed"
  | "cancelled";

export type AgentStepStatus =
  | "pending"
  | "awaiting_approval"
  | "succeeded"
  | "failed"
  | "denied"
  | "rejected"
  | "expired"
  | "cancelled";

export type ApprovalStatus =
  | "pending"
  | "approved"
  | "executing"
  | "executed"
  | "rejected"
  | "expired"
  | "cancelled"
  | "failed";

export interface AgentStep {
  id: string;
  run_id: string;
  step_index: number;
  tool_name: string;
  side_effect?: string | null;
  reason?: string | null;
  arguments?: Record<string, unknown> | null;
  status: AgentStepStatus;
  result?: Record<string, unknown> | null;
  error_code?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface AgentApprovalRequest {
  id: string;
  run_id: string;
  step_id: string;
  workspace_id: string;
  requested_by: string;
  tool_name: string;
  payload: {
    action?: string;
    tool?: string;
    arguments?: Record<string, unknown>;
    impact?: string;
    required_permission?: string;
    [key: string]: unknown;
  };
  payload_hash: string;
  status: ApprovalStatus;
  decided_by?: string | null;
  decided_at?: string | null;
  decision_reason?: string | null;
  expires_at: string;
  created_at: string;
}

export interface AgentExecutionEvent {
  id: string;
  run_id: string;
  seq: number;
  event_type: string;
  step_id?: string | null;
  data?: Record<string, unknown> | null;
  created_at: string;
}

export interface AgentRun {
  id: string;
  workspace_id: string;
  initiated_by: string;
  goal: string;
  status: AgentRunStatus;
  status_reason?: string | null;
  current_step: number;
  tool_call_count: number;
  denial_count: number;
  max_steps: number;
  max_tool_calls: number;
  allowed_tools: string[];
  cancel_requested: boolean;
  final_answer?: string | null;
  sources?: Array<{ document_id: string; title?: string }> | null;
  error_code?: string | null;
  error_message?: string | null;
  deadline_at?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  pending_approval?: AgentApprovalRequest | null;
  steps?: AgentStep[] | null;
}

export interface AgentRunListResponse {
  items: AgentRun[];
  total: number;
  limit: number;
  offset: number;
}

export interface AgentRunCreatePayload {
  goal: string;
  allowed_tools?: string[] | null;
  correlation_id?: string | null;
}
