export type UserRole = 'admin' | 'ops_manager' | 'reviewer' | 'viewer';

export interface User {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
}

export interface DocumentPage {
  id: string;
  page_number: number;
  text_content: string;
  image_path?: string | null;
}

export interface InvoiceLineItem {
  description: string;
  quantity: number;
  unit_price: number;
  total_price: number;
  tax?: number;
  sku?: string;
}

export interface StructuredInvoiceData {
  invoice_number: string;
  invoice_date: string;
  vendor_name: string;
  currency: string;
  subtotal: number;
  tax: number;
  total: number;
  payment_terms?: string;
  po_number?: string;
  line_items: InvoiceLineItem[];
}

export interface ValidationFinding {
  rule_name: string;
  passed: boolean;
  severity: 'ERROR' | 'WARNING' | 'INFO';
  message: string;
  expected_value?: any;
  actual_value?: any;
}

export interface DocumentExtraction {
  id: string;
  document_id: string;
  schema_type: string;
  structured_data: StructuredInvoiceData;
  field_confidences: Record<string, number>;
  validation_findings?: ValidationFinding[];
  is_valid: boolean;
}

export interface Document {
  id: string;
  tenant_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  mime_type: string;
  status: 'QUEUED' | 'PROCESSING' | 'EXTRACTED' | 'VALIDATING' | 'REVIEW_REQUIRED' | 'APPROVED' | 'REJECTED' | 'COMPLETED' | 'FAILED';
  classification?: string;
  confidence_score?: number;
  created_at: string;
  updated_at: string;
  pages?: DocumentPage[];
  extraction?: DocumentExtraction;
}

export interface ReviewTask {
  id: string;
  tenant_id: string;
  document_id: string;
  workflow_run_id?: string;
  status: 'PENDING' | 'RESOLVED' | 'REJECTED';
  priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT';
  reason: string;
  confidence?: number;
  assigned_to_user_id?: string;
  resolution_notes?: string;
  created_at: string;
  updated_at: string;
  document?: Document;
}

export interface Citation {
  document_id: string;
  title: string;
  page_number: number;
  snippet: string;
  relevance_score: number;
}

export interface KnowledgeSearchResponse {
  query: string;
  answer: string;
  sources: Citation[];
}

export interface ToolCall {
  id: string;
  tool_name: string;
  input_json: string;
  output_json: string;
  status: string;
  duration_ms: number;
}

export interface AgentRun {
  id: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_cost: number;
  duration_ms: number;
  tool_calls: ToolCall[];
}

export interface WorkflowStep {
  id: string;
  step_name: string;
  status: string;
  input_state?: string;
  output_state?: string;
  latency_ms: number;
  error_message?: string;
}

export interface WorkflowRun {
  id: string;
  tenant_id: string;
  document_id: string;
  status: string;
  current_step: string;
  result_summary?: string;
  created_at: string;
  steps: WorkflowStep[];
  agent_runs: AgentRun[];
}

export interface AuditLog {
  id: string;
  tenant_id: string;
  user_id?: string;
  actor_type: string;
  action: string;
  entity_type: string;
  entity_id: string;
  before_state?: string;
  after_state?: string;
  request_id?: string;
  created_at: string;
}

export interface MetricsSummary {
  total_documents: number;
  documents_today: number;
  auto_completion_rate: number;
  review_queue_size: number;
  avg_processing_latency_ms: number;
  avg_confidence_score: number;
  exception_rate: number;
  estimated_hours_saved: number;
  total_tokens_used: number;
  total_token_cost: number;
  status_breakdown: Array<{ status: string; count: number }>;
}
