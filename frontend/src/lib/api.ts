import {
  AuditLog,
  Document,
  KnowledgeSearchResponse,
  MetricsSummary,
  ReviewTask,
  User,
  UserRole,
  WorkflowRun,
} from '../types';

const API_BASE = '/api/v1';

// Preset test users for instant zero-friction RBAC switching in demo
export const DEMO_USERS: Record<UserRole, { email: string; name: string; role: UserRole; token: string }> = {
  admin: {
    email: 'admin@opspilot.ai',
    name: 'Alex Administrator',
    role: 'admin',
    token: '',
  },
  ops_manager: {
    email: 'ops@opspilot.ai',
    name: 'Morgan Ops Manager',
    role: 'ops_manager',
    token: '',
  },
  reviewer: {
    email: 'reviewer@opspilot.ai',
    name: 'Sam Reviewer',
    role: 'reviewer',
    token: '',
  },
  viewer: {
    email: 'viewer@opspilot.ai',
    name: 'Taylor Viewer',
    role: 'viewer',
    token: '',
  },
};

let currentRole: UserRole = 'admin';
let authTokens: Record<UserRole, string> = {
  admin: '',
  ops_manager: '',
  reviewer: '',
  viewer: '',
};

export const setGlobalRole = (role: UserRole) => {
  currentRole = role;
};

export const getGlobalRole = (): UserRole => currentRole;

export async function loginAs(role: UserRole): Promise<string> {
  try {
    const res = await fetch(`${API_BASE}/auth/dev-token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role }),
    });
    if (!res.ok) throw new Error('Role token retrieval failed');
    const data = await res.json();
    authTokens[role] = data.access_token;
    return data.access_token;
  } catch (e) {
    console.warn(`Could not log in as ${role}:`, e);
    return '';
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let token = authTokens[currentRole];
  if (!token) {
    token = await loginAs(currentRole);
  }

  const headers = new Headers(options.headers || {});
  headers.set('X-Request-ID', `req_fe_${Date.now()}`);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody?.error?.message || `API error ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

export const api = {
  // Metrics
  async getMetrics(): Promise<MetricsSummary> {
    return request<MetricsSummary>('/metrics');
  },

  // Documents
  async getDocuments(statusFilter?: string): Promise<{ items: Document[]; total: number }> {
    const query = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : '';
    return request<{ items: Document[]; total: number }>(`/documents${query}`);
  },

  async getDocument(id: string): Promise<Document> {
    return request<Document>(`/documents/${id}`);
  },

  async uploadDocument(file: File): Promise<{ id: string; filename: string; status: string }> {
    let token = authTokens[currentRole];
    if (!token) token = await loginAs(currentRole);

    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/documents`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err?.error?.message || 'Upload failed');
    }
    return response.json();
  },

  async reprocessDocument(id: string): Promise<any> {
    return request(`/documents/${id}/reprocess`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force: true }),
    });
  },

  // Reviews
  async getReviews(statusFilter: string = 'PENDING'): Promise<ReviewTask[]> {
    return request<ReviewTask[]>(`/reviews?status=${encodeURIComponent(statusFilter)}`);
  },

  async getReview(id: string): Promise<ReviewTask> {
    return request<ReviewTask>(`/reviews/${id}`);
  },

  async approveReview(id: string, comments?: string): Promise<any> {
    return request(`/reviews/${id}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'APPROVE', comments }),
    });
  },

  async rejectReview(id: string, comments?: string): Promise<any> {
    return request(`/reviews/${id}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'REJECT', comments }),
    });
  },

  async editReview(id: string, editedFields: Record<string, any>, comments?: string): Promise<any> {
    return request(`/reviews/${id}/edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'EDIT', edited_fields: editedFields, comments }),
    });
  },

  // Knowledge & RAG
  async searchKnowledge(query: string): Promise<KnowledgeSearchResponse> {
    return request<KnowledgeSearchResponse>('/knowledge/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, limit: 3 }),
    });
  },

  async indexKnowledge(data: { title: string; content: string; department?: string }): Promise<any> {
    return request('/knowledge/index', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: data.title,
        content: data.content,
        department: data.department || 'finance',
        acl_roles: ['admin', 'ops_manager', 'reviewer', 'viewer'],
      }),
    });
  },

  async getKnowledgeDocs(): Promise<any[]> {
    return request<any[]>('/knowledge');
  },

  // Agent Runs & Telemetry
  async getAgentRuns(): Promise<WorkflowRun[]> {
    return request<WorkflowRun[]>('/agent/runs');
  },

  async getAgentRun(id: string): Promise<WorkflowRun> {
    return request<WorkflowRun>(`/agent/runs/${id}`);
  },

  // Audit Logs
  async getAuditLogs(): Promise<AuditLog[]> {
    return request<AuditLog[]>('/audit-logs');
  },
};
