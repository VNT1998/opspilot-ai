import React, { useEffect, useState } from 'react';
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Clock,
  DollarSign,
  FileText,
  TrendingUp,
  Upload,
  UserCheck,
  Zap,
} from 'lucide-react';
import { api } from '../../lib/api';
import { MetricsSummary } from '../../types';

interface DashboardViewProps {
  onNavigate: (tab: string) => void;
  onOpenUpload: () => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({ onNavigate, onOpenUpload }) => {
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadMetrics();
  }, []);

  const loadMetrics = async () => {
    try {
      setLoading(true);
      const data = await api.getMetrics();
      setMetrics(data);
    } catch (e) {
      console.error('Failed to load metrics:', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-sky-950 to-slate-900 rounded-2xl p-6 text-white shadow-md flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight">Operations Intelligence Dashboard</h2>
          <p className="text-slate-300 text-sm mt-1 max-w-2xl">
            Real-time telemetry for multi-tenant document ingestion, deterministic PO reconciliation,
            LangGraph agent execution, and human-in-the-loop exception routing.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={onOpenUpload}
            className="flex items-center gap-2 bg-sky-500 hover:bg-sky-400 text-white font-semibold text-xs px-4 py-2.5 rounded-lg shadow-sm transition-all"
          >
            <Upload className="w-4 h-4" />
            Upload Document
          </button>
          <button
            onClick={() => onNavigate('reviews')}
            className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs px-4 py-2.5 rounded-lg border border-slate-700 transition-all"
          >
            <UserCheck className="w-4 h-4 text-amber-400" />
            Review Queue ({metrics?.review_queue_size || 0})
          </button>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1 */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Straight-Through Rate
            </span>
            <span className="p-2 bg-emerald-50 text-emerald-600 rounded-lg">
              <Zap className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-4">
            <div className="text-2xl font-bold text-slate-900">
              {metrics ? `${metrics.auto_completion_rate}%` : '0%'}
            </div>
            <div className="text-xs text-emerald-600 font-medium flex items-center gap-1 mt-1">
              <TrendingUp className="w-3.5 h-3.5" />
              Automated end-to-end without review
            </div>
          </div>
        </div>

        {/* Card 2 */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Review Queue
            </span>
            <span className="p-2 bg-amber-50 text-amber-600 rounded-lg">
              <UserCheck className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-4">
            <div className="text-2xl font-bold text-slate-900">
              {metrics ? metrics.review_queue_size : 0}
            </div>
            <div className="text-xs text-amber-600 font-medium flex items-center gap-1 mt-1">
              Pending human decision & sign-off
            </div>
          </div>
        </div>

        {/* Card 3 */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Avg Processing Latency
            </span>
            <span className="p-2 bg-sky-50 text-sky-600 rounded-lg">
              <Clock className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-4">
            <div className="text-2xl font-bold text-slate-900">
              {metrics ? `${metrics.avg_processing_latency_ms}ms` : '480ms'}
            </div>
            <div className="text-xs text-sky-600 font-medium flex items-center gap-1 mt-1">
              Asynchronous worker throughput
            </div>
          </div>
        </div>

        {/* Card 4 */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Hours Saved
            </span>
            <span className="p-2 bg-purple-50 text-purple-600 rounded-lg">
              <DollarSign className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-4">
            <div className="text-2xl font-bold text-slate-900">
              {metrics ? `${metrics.estimated_hours_saved} hrs` : '0 hrs'}
            </div>
            <div className="text-xs text-purple-600 font-medium flex items-center gap-1 mt-1">
              ~15 min saved per clean invoice
            </div>
          </div>
        </div>
      </div>

      {/* Secondary Metrics / Status Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Status Distribution */}
        <div className="lg:col-span-2 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-sm text-slate-800">Pipeline Status Breakdown</h3>
            <span className="text-xs text-slate-500">
              Total Documents: {metrics?.total_documents || 0}
            </span>
          </div>

          <div className="space-y-3">
            {metrics?.status_breakdown && metrics.status_breakdown.length > 0 ? (
              metrics.status_breakdown.map((item) => {
                const total = metrics.total_documents || 1;
                const pct = Math.round((item.count / total) * 100);
                return (
                  <div key={item.status} className="space-y-1">
                    <div className="flex justify-between text-xs font-medium text-slate-600">
                      <span>{item.status}</span>
                      <span>
                        {item.count} ({pct}%)
                      </span>
                    </div>
                    <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          item.status === 'COMPLETED' || item.status === 'APPROVED'
                            ? 'bg-emerald-500'
                            : item.status === 'REVIEW_REQUIRED'
                            ? 'bg-amber-500'
                            : item.status === 'PROCESSING'
                            ? 'bg-sky-500'
                            : 'bg-rose-500'
                        }`}
                        style={{ width: `${pct}%` }}
                      ></div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-xs text-slate-400 py-6 text-center">
                No documents uploaded yet. Upload a document to view processing telemetry.
              </div>
            )}
          </div>
        </div>

        {/* AI & Economics Telemetry */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div>
            <h3 className="font-semibold text-sm text-slate-800 mb-4">AI Economics & Confidence</h3>
            <div className="space-y-4">
              <div className="flex justify-between items-center py-2 border-b border-slate-100">
                <span className="text-xs text-slate-500">Average AI Confidence</span>
                <span className="text-xs font-bold text-slate-800">
                  {metrics ? `${Math.round(metrics.avg_confidence_score * 100)}%` : '95%'}
                </span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-slate-100">
                <span className="text-xs text-slate-500">Total Tokens Processed</span>
                <span className="text-xs font-bold text-slate-800">
                  {metrics ? metrics.total_tokens_used.toLocaleString() : '0'}
                </span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-slate-100">
                <span className="text-xs text-slate-500">Estimated LLM Cost</span>
                <span className="text-xs font-bold text-slate-800">
                  {metrics ? `$${metrics.total_token_cost.toFixed(4)}` : '$0.0000'}
                </span>
              </div>
              <div className="flex justify-between items-center py-2">
                <span className="text-xs text-slate-500">Avg Cost / Document</span>
                <span className="text-xs font-bold text-emerald-600">
                  {metrics && metrics.total_documents > 0
                    ? `$${(metrics.total_token_cost / metrics.total_documents).toFixed(4)}`
                    : '$0.0020'}
                </span>
              </div>
            </div>
          </div>

          <button
            onClick={() => onNavigate('agents')}
            className="w-full mt-4 flex items-center justify-center gap-1.5 text-xs font-semibold text-sky-600 hover:text-sky-700 bg-sky-50 hover:bg-sky-100 py-2.5 rounded-lg transition-all"
          >
            <span>View Agent Traces</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};
