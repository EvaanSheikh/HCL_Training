/** Response shapes of the existing FastAPI backend (app/api/upload.py, routes.py). */

export type Json =
  | string
  | number
  | boolean
  | null
  | Json[]
  | { [key: string]: Json };

export type Row = Record<string, Json>;

export interface UploadValidation {
  valid: boolean;
  rows: number;
  columns: number;
  column_names: string[];
  missing_values: number;
  duplicate_rows: number;
  file_size_bytes: number;
}

export interface UploadResponse {
  /** Server file path. Must be sent back to /analyze exactly as received. */
  dataset_id: string;
  filename: string;
  size_bytes: number;
  extension: string;
  validation: UploadValidation;
}

export interface PlanStep {
  step?: number;
  action: string;
  parameters?: Row;
}

export interface ToolCall {
  action: string;
  parameters: Row;
}

export interface Finding {
  type?: string;
  metric?: string;
  highest?: Row;
  lowest?: Row;
  message?: string;
}

export interface EvidenceRecord {
  timestamp?: string;
  dataset_id?: string;
  columns?: string[];
  operation: string;
  parameters?: Row;
  result?: Json;
}

export interface ValidationCheck {
  check: string;
  passed: boolean;
  message: string;
}

export interface BackendError {
  type?: string;
  message: string;
}

export interface AnalyzeResponse {
  session_id: string;
  status: string;
  user_query: string;
  dataset_id: string;
  analysis_plan: PlanStep[];
  tool_calls: ToolCall[];
  findings: Finding[];
  visualizations: string[];
  evidence: EvidenceRecord[];
  validation_results: ValidationCheck[];
  errors: BackendError[];
  final_report: string;
}

export interface DatasetItem {
  dataset_id: string;
  extension: string;
  created_at: string;
  filename: string;
  size_bytes: number;
  row_count: number | null;
  col_count: number | null;
  validation_status: string;
}

export interface DatasetDetails extends DatasetItem {
  column_names: string[];
  dtypes: Record<string, string>;
  missing_values: Record<string, number>;
  duplicate_rows: number;
  profile?: Row | null;
}

export interface SessionItem {
  session_id: string;
  user_query: string;
  dataset_id: string;
  dataset_name: string;
  status: string;
  tool_calls_count: number;
  evidence_count: number;
  validation_count: number;
  all_validations_passed: boolean;
  errors_count: number;
  has_report: boolean;
  chart_count: number;
  created_at: string;
  updated_at: string;
}

export interface ReportItem {
  report_id: string;
  session_id: string;
  title: string;
  user_query: string;
  dataset_id: string;
  dataset_name: string;
  status: string;
  created_at: string;
  report_preview: string;
  report_length: number;
  final_report: string;
  chart_count: number;
  is_saved: boolean;
}

export interface TraceItem {
  session_id: string;
  user_query: string;
  dataset_id: string;
  dataset_name: string;
  status: string;
  created_at: string;
  plan_steps: PlanStep[];
  tool_calls: ToolCall[];
  evidence: EvidenceRecord[];
  errors: string[];
  total_steps: number;
  has_failures: boolean;
}

export interface PipelineValidationSummary {
  session_id: string;
  user_query: string;
  dataset_id: string;
  dataset_name: string;
  created_at: string;
  status: string;
  all_passed: boolean;
  checks: ValidationCheck[];
  passed_count: number;
  total_count: number;
}

export interface BenchmarkAssertion {
  name: string;
  expected: string;
  actual: string;
  passed: boolean;
  category: string;
}

export interface BenchmarkRun {
  run_id: string;
  benchmark_name: string;
  dataset_id: string;
  status: string;
  accuracy_score: number;
  assertions_passed: number;
  assertions_total: number;
  execution_time_ms: number;
  details: {
    dataset_name: string;
    assertions: BenchmarkAssertion[];
    summary: string;
  };
  created_at: string;
}

export interface AvailableBenchmark {
  id: string;
  name: string;
  description: string;
  dataset_file: string;
  expected_assertions: number;
}

export interface EvaluationResponse {
  pipeline_validations: PipelineValidationSummary[];
  benchmark_runs: BenchmarkRun[];
  available_benchmarks: AvailableBenchmark[];
}

export interface SuggestedQuestionItem {
  id: string;
  question: string;
  category?: string;
  target_columns?: string[];
}

export interface SuggestedQuestionsResponse {
  dataset_id: string;
  offset?: number;
  total_candidates?: number;
  suggestions: SuggestedQuestionItem[];
}
