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
  model_name?: string | null;
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

export interface BenchmarkCaseResultResponse {
  id: string;
  benchmark_run_id: string;
  case_id: string;
  case_name: string;
  category: string;
  is_adversarial: boolean;
  passed: boolean;
  failure_classification: string;
  score: number;
  reason: string;
  tool_accuracy: number;
  citation_f1: number;
  grounding_score: number;
  latency_ms: number;
  sanitized_trace?: {
    steps?: Array<{
      step_index: number;
      action: string;
      tool?: string;
      sanitized_arguments?: Record<string, unknown>;
      status?: string;
      reason?: string;
    }>;
    [key: string]: unknown;
  } | null;
  metrics?: Record<string, unknown> | null;
  created_at: string;
}

export interface BenchmarkCategoryScore {
  total_cases: number;
  passed_cases: number;
  success_rate: number;
  avg_latency_ms: number;
}

export interface BenchmarkRunResponse {
  id: string;
  workspace_id: string;
  created_by: string;
  name: string;
  dataset_id: string;
  dataset_version: string;
  execution_mode: "real" | "simulated";
  model_name: string;
  embedding_model?: string | null;
  status: "running" | "completed" | "failed";
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  task_success_rate: number;
  tool_call_accuracy: number;
  citation_f1: number;
  security_blocking_rate: number | null;
  benign_overblock_rate: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  latency_mean_ms: number;
  failure_summary?: Record<string, number> | null;
  category_scores?: Record<string, BenchmarkCategoryScore> | null;
  runtime_config?: Record<string, unknown> | null;
  created_at: string;
  completed_at?: string | null;
  case_results?: BenchmarkCaseResultResponse[];
}

export interface BenchmarkRunListResponse {
  items: BenchmarkRunResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface BenchmarkRunCreatePayload {
  name: string;
  dataset_id?: string;
  execution_mode: "real" | "simulated";
  model_name?: string | null;
  category_filter?: string | null;
}

export interface MetricDelta {
  current: number;
  baseline: number;
  delta: number;
  improved: boolean;
}

export interface BenchmarkComparisonResponse {
  current_run_id: string;
  baseline_run_id: string;
  current_mode: string;
  baseline_mode: string;
  current_model: string;
  baseline_model: string;
  task_success_rate: MetricDelta;
  tool_call_accuracy: MetricDelta;
  citation_f1: MetricDelta;
  latency_p50_ms: MetricDelta;
  security_blocking_rate?: MetricDelta | null;
  newly_failing_cases?: string[];
  newly_passing_cases?: string[];
  summary: string;
}

// ==========================================
// T260027: AI Model Registry & Adaptive Routing Types
// ==========================================

export type ModelCapabilityStatus = "verified" | "advertised" | "unknown";

export interface ModelBenchmarkProfile {
  id: string;
  model_id: string;
  model_name: string;
  model_digest: string;
  dataset_id: string;
  dataset_version: string;
  benchmark_run_id?: string | null;
  execution_mode: string;
  task_success_rate: number;
  tool_call_accuracy: number;
  citation_reference_f1: number;
  prompt_injection_resistance?: number | null;
  tenant_isolation_success?: number | null;
  policy_blocking_effectiveness?: number | null;
  actual_data_leakage_rate: number;
  benign_overblock_rate: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  sample_size: number;
  has_sufficient_sample_size: boolean;
  notes?: string | null;
  is_stale: boolean;
  measured_at: string;
}

export interface ModelRegistryEntry {
  id: string;
  name: string;
  digest: string;
  family?: string | null;
  format?: string | null;
  parameter_size?: string | null;
  quantization_level?: string | null;
  size_bytes?: number | null;
  context_length?: number | null;
  capabilities: Record<string, ModelCapabilityStatus>;
  is_installed: boolean;
  is_loaded: boolean;
  is_active: boolean;
  resource_observations?: Record<string, unknown> | null;
  raw_metadata?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  latest_benchmark_profile?: ModelBenchmarkProfile | null;
}

export interface ModelRegistryListResponse {
  items: ModelRegistryEntry[];
  total: number;
}

export interface ModelRoutingPolicy {
  id: string;
  workspace_id?: string | null;
  name: string;
  version: string;
  is_enabled: boolean;
  default_model: string;
  allowed_models: string[];
  fallback_models: string[];
  max_fallback_attempts: number;
  task_rules: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CandidateEvaluation {
  model: string;
  eligible: boolean;
  score: number;
  reason: string;
}

export interface ModelRoutingPreviewRequest {
  workspace_id?: string | null;
  prompt: string;
  has_retrieved_context?: boolean;
  context_document_count?: number;
  requires_tools?: boolean;
  is_write_operation?: boolean;
  explicit_task_type?: string | null;
}

export interface ModelRoutingPreviewResponse {
  task_type: string;
  selected_model: string;
  selection_reason: string;
  fallback_chain: string[];
  candidate_evaluations: CandidateEvaluation[];
  policy_id?: string | null;
  policy_version: string;
}

export interface ModelRoutingDecision {
  id: string;
  workspace_id?: string | null;
  task_type: string;
  policy_id?: string | null;
  policy_version: string;
  selected_model: string;
  candidate_evaluations: Array<{
    model_name: string;
    eligible: boolean;
    score: number;
    reason: string;
    is_loaded?: boolean;
  }>;
  selection_reason: string;
  fallback_occurred: boolean;
  fallback_chain: string[];
  latency_ms: number;
  context_metadata: Record<string, unknown>;
  created_at: string;
}


