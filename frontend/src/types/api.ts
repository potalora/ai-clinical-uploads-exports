export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  display_name: string | null;
  is_active: boolean;
}

export interface RegisterRequest {
  email: string;
  password: string;
  display_name?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface HealthRecord {
  id: string;
  patient_id: string;
  record_type: string;
  fhir_resource_type: string;
  fhir_resource: Record<string, unknown>;
  source_format: string;
  effective_date: string | null;
  status: string | null;
  category: string[] | null;
  code_system: string | null;
  code_value: string | null;
  code_display: string | null;
  display_text: string;
  created_at: string;
}

export interface RecordListResponse {
  items: HealthRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface TimelineEvent {
  id: string;
  record_type: string;
  display_text: string;
  effective_date: string | null;
  code_display: string | null;
  category: string[] | null;
}

export interface TimelineResponse {
  events: TimelineEvent[];
  total: number;
}

export interface TimelineStats {
  total_records: number;
  records_by_type: Record<string, number>;
  date_range_start: string | null;
  date_range_end: string | null;
}

export interface DashboardOverview {
  total_records: number;
  total_patients: number;
  total_uploads: number;
  records_by_type: Record<string, number>;
  recent_records: {
    id: string;
    record_type: string;
    display_text: string;
    effective_date: string | null;
    created_at: string | null;
  }[];
  date_range_start: string | null;
  date_range_end: string | null;
}

export interface UploadResponse {
  upload_id: string;
  status: string;
  records_inserted: number;
  errors: unknown[];
}

export interface LabItem {
  id: string;
  display_text: string;
  effective_date: string | null;
  value: number | string | null;
  unit: string;
  reference_low: number | null;
  reference_high: number | null;
  interpretation: string;
  code_display: string | null;
  code_value: string | null;
}

export interface PromptResponse {
  id: string;
  summary_type: string;
  system_prompt: string;
  user_prompt: string;
  target_model: string;
  suggested_config: Record<string, unknown>;
  record_count: number;
  de_identification_report: Record<string, number> | null;
  copyable_payload: string;
  generated_at: string;
}

export interface DedupCandidate {
  id: string;
  similarity_score: number;
  match_reasons: Record<string, boolean>;
  status: string;
  record_a: {
    id: string;
    display_text: string;
    record_type: string;
    source_format: string;
    effective_date: string | null;
  } | null;
  record_b: {
    id: string;
    display_text: string;
    record_type: string;
    source_format: string;
    effective_date: string | null;
  } | null;
}
