
export type FactoryBrief = {
  factory_id: string;
  factory_name: string;
};

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type FactoryAdmin = FactoryBrief & {
  location?: string | null;
  created_at?: string | null;
};

export type FactoryCreate = {
  factory_id: string;
  factory_name: string;
  location?: string | null;
};

export type FactorySettingsResponse = {
  factory_id: string;
  effective: Record<string, unknown>;
  stored: Record<string, unknown>;
};

export type FactorySettingsPatch = {
  rag?: {
    min_max_score?: number | null;
    top_k_default?: number;
    chunk_profile?: string;
  };
  ingest?: {
    backend?: "native";
    chunking_strategy?: "recursive" | "semantic";
  };
  notifications?: {
    enabled?: boolean;
    channels?: Array<{ type: string; url?: string; token?: string; host?: string }>;
    insights_hotness?: boolean;
    ingest_failed?: boolean;
    predictive_at_risk?: boolean;
  };
  timezone?: string;
  llm_profile?: string;
  predictive_backend?: "heuristic" | "mcp" | "hybrid";
  inventory_report_backend?: "native" | "deepanalyze";
};

export type LoginResponse = {
  token: string;
  token_type: string;
  expires_in: number;
  username: string;
  email?: string;
  full_name?: string;
  picture_url?: string;
  factories: FactoryBrief[];
  job_position_ids?: string[];
  needs_job_position?: boolean;
  needs_privacy_acceptance?: boolean;
  is_super_admin?: boolean;
};

export type Machine = {
  machine_id: string;
  factory_id: string;
  machine_name: string;
  machine_type: string | null;
  manufacturer: string | null;
  is_active: boolean;
  image_updated_at?: string | null;
};

export type Source = {
  doc_id?: string | null;
  title?: string | null;
  source_file?: string | null;
  page?: number | null;
  source_sheet?: string | null;
  row_number?: number | null;
  extraction_source?: string | null;
  needs_review?: boolean | null;
  /** Evidence span excerpts (start/end offsets + text) backing this citation. */
  spans?: { text?: string | null }[] | null;
  document_type?: string | null;
  /** P2 parent-child chunk identifier when present in RAG payloads. */
  chunk_id?: string | null;
  score: number;
  view_url?: string | null;
  can_view?: boolean;
};

export type ChatAttachment = {
  filename: string;
  mime_type: string;
  url: string;
  sort_order: number;
};

export type RetrievalReport = {
  degraded: boolean;
  degraded_reasons?: string[];
  failed_collections?: string[];
  vector_count?: number;
  lexical_count?: number;
  fusion_method?: string;
  intent?: string;
};

export type AskResponse = {
  answer: string;
  sources: Source[];
  used_filters: Record<string, unknown>;
  intent: string;
  route?: string | null;
  routing_reason?: string | null;
  fallback_level: number;
  cache_hit?: boolean;
  assistant_message_id?: string | null;
  top_doc_score?: number | null;
  confidence_tier?: ConfidenceTier | null;
  citations_verified?: boolean;
  retrieval_report?: RetrievalReport | null;
  system_degradation?: boolean;
};

export type ConfidenceTier = "high" | "medium" | "low";


export type QualityFailure = {
  question: string;
  factory_id: string;
  answer: string | null;
  sources: Record<string, unknown>[] | null;
  feedback_count: number;
  last_seen: string;
};

export type QualityFailures = {
  items: QualityFailure[];
};

export type ChatCapabilities = {
  llm_profile: string;
  llm_model: string;
  top_k_fast: number;
  top_k_advanced: number;
  question_max_length: number;
  speech?: { whisper?: boolean; web_speech?: boolean };
};

export type FactoryBenchmarkItem = {
  factory_id: string;
  question_count: number;
  repair_count: number;
  repair_downtime_hours: number;
  hotness_score: number;
  period_days: number;
  bucket_tz: string;
};

export type CorrelationHint = {
  machine_id: string;
  topic: string;
  spike_count: number;
  baseline_count: number;
  repair_count_nearby: number;
  correlation_score: number;
};

export type CorrelationHints = {
  items: CorrelationHint[];
  disclaimer: string;
  bucket_tz: string;
};

export type JobRow = {
  job_id: string;
  doc_id: string | null;
  document_type: string;
  original_filename: string | null;
  file_size_bytes: number | null;
  factory_id: string | null;
  machine_id: string | null;
  status: string;
  rows_total: number;
  rows_ok: number;
  rows_skipped: number;
  progress_percent: number;
  chunks_count: number;
  page_count: number | null;
  document_ingest_status: string | null;
  error_count: number;
  last_error_code: string | null;
  last_error_detail: string | null;
  duration_seconds: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
  error_message: string | null;
};

export type JobErrorRow = {
  error_id: string;
  job_id: string;
  row_number: number | null;
  chunk_index: number | null;
  reason_code: string | null;
  reason_detail: string | null;
  created_at: string;
};

export type IngestFileResponse = {
  job_id: string;
  doc_id: string;
  status: string;
  celery_task_id?: string | null;
};

export type IngestPreflightPolicyHint = {
  rule_id: string;
  severity: string;
  message: string;
};

export type IngestPreflightResponse = {
  accepted: boolean;
  reasons: string[];
  estimated_pages?: number | null;
  estimated_chunks?: number | null;
  ocr_required: boolean;
  policy_hints: IngestPreflightPolicyHint[];
  document_type?: string | null;
};

export type JobPositionBrief = {
  position_id: string;
  position_code: string;
  name_th: string;
  description?: string | null;
};

export type JobPositionAdmin = JobPositionBrief & {
  is_active: boolean;
  sort_order: number;
  document_count: number;
  user_count: number;
};

export type JobPositionCreate = {
  position_code: string;
  name_th: string;
  description?: string | null;
  sort_order?: number;
};

export type JobPositionUpdate = {
  name_th?: string;
  description?: string | null;
  is_active?: boolean;
  sort_order?: number;
};

export type JobPositionUsage = {
  position_id: string;
  document_count: number;
  user_count: number;
};

export type FactoryAccessEntry = {
  factory_id: string;
  access_level: string;
};

export type AdminUserBrief = {
  user_id: string;
  username: string;
  full_name?: string | null;
  email?: string | null;
  is_active: boolean;
  roles: string[];
  factory_access: FactoryAccessEntry[];
  job_position_ids: string[];
  is_super_admin?: boolean;
  token_version: number;
};

export type AdminUserUpdate = {
  role?: string;
  is_active?: boolean;
  is_super_admin?: boolean;
  factory_access?: FactoryAccessEntry[];
  job_position_ids?: string[];
};

export type ApiKeyOut = {
  key_id: string;
  name: string;
  key_prefix: string;
  user_id: string;
  username?: string | null;
  is_active: boolean;
  expires_at?: string | null;
  last_used_at?: string | null;
  revoked_at?: string | null;
  created_at: string;
};

export type ApiKeyCreated = ApiKeyOut & {
  /** Full key — returned only once at creation. */
  api_key: string;
};

export type ApiKeyCreate = {
  name: string;
  user_id: string;
  expires_at?: string | null;
};

export type AdminUserCreate = {
  email: string;
  full_name?: string | null;
  username?: string | null;
  password: string;
  role?: string;
  factory_access?: FactoryAccessEntry[];
  job_position_ids?: string[];
};

export type UserProfile = {
  user_id: string;
  username: string;
  full_name?: string | null;
  email?: string | null;
  picture_url?: string | null;
  roles: string[];
  factories: FactoryBrief[];
  factory_access: FactoryAccessEntry[];
  job_positions: JobPositionBrief[];
  has_password: boolean;
  privacy_policy_accepted_at?: string | null;
  privacy_policy_version?: string | null;
  created_at: string;
  is_super_admin?: boolean;
};

export type SystemAdminDashboard = {
  generated_at: string;
  traffic: Record<string, unknown>;
  llm_usage: Record<string, unknown>;
  qdrant: Record<string, unknown>;
  postgres: Record<string, unknown>;
  storage: Record<string, unknown>;
  workers: Record<string, unknown>;
  agentic_circuit: Record<string, unknown>;
  rag_circuit: Record<string, unknown>;
  shadow_routing: Record<string, unknown>;
  llm_gateway: Record<string, unknown>;
  maintenance: Record<string, unknown>;
  otel_tracing: Record<string, unknown>;
  eval_quality: Record<string, unknown>;
  embed_shadow: Record<string, unknown>;
  semantic_cache: Record<string, unknown>;
  health_summary: Record<string, unknown>;
  users: Record<string, unknown>;
  timeseries: Record<string, unknown>;
  incidents: Array<{
    severity: string;
    title: string;
    detail: string;
    source: string;
    at: string;
  }>;
  active_users_window_minutes: number;
  active_users_since: string;
};

export type SystemActionResult = {
  ok: boolean;
  action: string;
  detail: Record<string, unknown>;
};

export type UserProfileUpdate = {
  full_name?: string;
  email?: string;
  job_position_id?: string;
};

export type ChangePasswordRequest = {
  current_password: string;
  new_password: string;
};

export type IndexedDocument = {
  doc_id: string;
  factory_id: string | null;
  machine_id: string | null;
  document_category: string;
  document_type: string;
  title: string | null;
  language: string;
  revision: string | null;
  source_file: string;
  original_filename?: string | null;
  mime_type?: string | null;
  file_hash_sha256?: string | null;
  file_size_bytes?: number | null;
  ingest_status: string;
  chunks_count: number;
  retrieval_enabled?: boolean;
  quarantine_reason?: string | null;
  policy_scan_version?: string | null;
  content_risk_score?: number | null;
  released_at?: string | null;
  extra_metadata?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  visible_position_ids?: string[];
};

export type PolicyFinding = {
  rule_id: string;
  severity: string;
  message: string;
  matched_text?: string | null;
};

export type PolicyFindingsResponse = {
  doc_id: string;
  policy_scan_version: string | null;
  content_risk_score: number | null;
  ingest_status: string;
  retrieval_enabled: boolean;
  findings: PolicyFinding[];
};

export type DocumentReleaseResponse = {
  document: IndexedDocument;
  released: boolean;
  index_task_id: string | null;
};

export type HandoverResponse = {
  summary: string;
  hours_back: number;
  factory_id: string | null;
  event_counts: Record<string, number>;
};

export type AssignableUser = {
  user_id: string;
  username: string;
  full_name?: string | null;
};

export type RCAResponse = {
  machine_id: string;
  symptom: string;
  analysis: string;
  top_causes: Array<{
    root_cause?: string;
    cause?: string;
    count?: number;
    pct?: number;
    score?: number;
    [key: string]: unknown;
  }>;
  similar_repairs_count: number;
  manual_sources: Source[];
  mcp_assessment?: Record<string, unknown> | null;
};

export type AtRiskMachine = {
  machine_id: string;
  last_repair_date: string | null;
  mean_interval_days: number | null;
  std_interval_days: number | null;
  repairs_last_90d: number;
  risk_score: number;
  reason: string;
};

export type Incident = {
  incident_id: string;
  machine_id: string;
  incident_date: string;
  severity: string;
  incident_type: string;
  status: string;
  description: string | null;
};

export type RepairRow = {
  repair_id: string;
  machine_id: string;
  factory_id: string;
  repair_date: string | null;
  symptom: string | null;
  root_cause: string | null;
  solution: string | null;
  result: string | null;
  downtime_hours: number | null;
  cost_thb: number | null;
};

export type Paginated<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type FeedbackAttachment = {
  attachment_id: string;
  sort_order: number;
  mime_type: string;
  url: string;
};


export type PulseItem = {
  label: string;
  source: string;
  machine_id: string | null;
  count_current: number;
  count_previous: number;
  delta_pct: number;
  is_new_signal: boolean;
  hotness_score: number;
};

export type AiTrendPoint = { bucket: string; topic: string; count: number };

export type AiDrilldownItem = {
  message_id: string;
  question: string;
  machine_id: string | null;
  asked_at: string | null;
};

export type SymptomTrend = { symptom: string; count: number; downtime_hours: number };

export type MachineHeatmapCell = {
  machine_id: string;
  week: string;
  ai_count: number;
  repair_count: number;
  total: number;
};

export type FeedbackGaps = {
  by_issue_type: { issue_type: string; count: number }[];
  top_docs: { doc_id: string; issue_type: string | null; count: number }[];
};

export type FeedbackRow = {
  feedback_id: string;
  factory_id: string;
  machine_id: string | null;
  source_type: string;
  doc_id: string | null;
  page: number | null;
  session_id: string | null;
  message_id: string | null;
  comment: string;
  issue_type: string | null;
  status: string;
  context: Record<string, unknown> | null;
  resolution_note: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  created_by: string | null;
  created_at: string;
  attachments: FeedbackAttachment[];
};

export type MachinesQuery = {
  factory_id?: string;
  machine_type?: string;
  q?: string;
  page?: number;
  page_size?: number;
  include_inactive?: boolean;
};

export type MachineCreatePayload = {
  machine_id: string;
  factory_id: string;
  machine_name: string;
  machine_type?: string | null;
  manufacturer?: string | null;
  model_number?: string | null;
  install_date?: string | null;
  notes?: string | null;
};

export type MachinePatchPayload = {
  machine_name?: string;
  machine_type?: string | null;
  manufacturer?: string | null;
  model_number?: string | null;
  install_date?: string | null;
  notes?: string | null;
  is_active?: boolean;
};

export type RepairsQuery = {
  factory_id?: string;
  machine_id?: string;
  machine_ids?: string;
  q?: string;
  symptom?: string;
  root_cause?: string;
  date_from?: string;
  date_to?: string;
  severity?: string;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  page?: number;
  page_size?: number;
};

export type RepairPatch = {
  root_cause?: string | null;
  solution?: string | null;
  result?: string | null;
  downtime_hours?: number | null;
  cost_thb?: number | null;
};

export type ObservabilitySeries = {
  label: string;
  points: { ts: number; value: number }[];
};

export type ObservabilityOverview = {
  source: string;
  prometheus_url: string;
  grafana_dashboard_uid: string;
  available: boolean;
  error?: string;
  stats: {
    requests_per_sec?: number | null;
    p95_latency_sec?: number | null;
  };
  series: {
    embedding_latency?: ObservabilitySeries[];
    rag_fallback?: ObservabilitySeries[];
    ingest_rows?: ObservabilitySeries[];
  };
};
export type ExternalDataSourceOut = {
  source_id: string;
  name: string;
  description?: string | null;
  factory_id?: string | null;
  host: string;
  port: number;
  database_name: string;
  username: string;
  ssl_mode: string;
  scope_column?: string | null;
  is_enabled: boolean;
  allowed_tables: ExternalDataSourceTableOut[];
};

export type ExternalDataSourceTableOut = {
  table_id: string;
  schema_name: string;
  table_name: string;
  description?: string | null;
  columns_meta: Array<{ column_name: string; data_type?: string; is_nullable?: string }>;
  factory_ids: string[];
  position_ids: string[];
};

export type ExternalDataSourceCreate = {
  name: string;
  description?: string | null;
  factory_id?: string | null;
  host: string;
  port?: number;
  database_name: string;
  username: string;
  password: string;
  ssl_mode?: string;
  scope_column?: string | null;
  is_enabled?: boolean;
};

export type ExternalDiscoveredTable = {
  schema_name: string;
  table_name: string;
  columns: Array<{ column_name: string; data_type?: string; is_nullable?: string }>;
};

export type ExternalConnectionTestResult = {
  ok: boolean;
  message: string;
};

export function confidenceTierLabel(tier: ConfidenceTier): string {
  switch (tier) {
    case "high":
      return "สูง";
    case "medium":
      return "ปานกลาง";
    case "low":
      return "ต่ำ";
    default:
      return tier;
  }
}
