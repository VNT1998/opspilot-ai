import React, { useEffect, useState } from 'react';
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Clock,
  Cpu,
  Layers,
  Terminal,
  Wrench,
  Zap,
} from 'lucide-react';
import { api } from '../../lib/api';
import { WorkflowRun, WorkflowStep } from '../../types';

export const AgentRunsView: React.FC = () => {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<WorkflowRun | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadRuns();
  }, []);

  const loadRuns = async () => {
    try {
      setLoading(true);
      const data = await api.getAgentRuns();
      setRuns(data);
      if (data.length > 0 && !selectedRun) {
        setSelectedRun(data[0]);
      }
    } catch (e) {
      console.error('Failed to load agent runs:', e);
    } finally {
      setLoading(false);
    }
  };

  const PIPELINE_NODES = [
    { id: 'intake', label: 'Intake' },
    { id: 'classification', label: 'Classification' },
    { id: 'extraction', label: 'Extraction' },
    { id: 'validation', label: 'Validation (Deterministic)' },
    { id: 'rag_policy', label: 'RAG Policy Lookup' },
    { id: 'decision', label: 'Decision Node' },
    { id: 'action', label: 'Action & ERP/Review' },
  ];

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Top Header */}
      <div>
        <h2 className="text-lg font-bold text-slate-900">LangGraph Agent Orchestration Telemetry</h2>
        <p className="text-xs text-slate-500">
          Stateful agent graph execution traces, allowlisted tool calls, token economics, and latency profiling.
        </p>
      </div>

      {/* Visual LangGraph Pipeline Diagram */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm overflow-x-auto">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-4 flex items-center gap-1.5">
          <Layers className="w-4 h-4 text-sky-600" />
          LangGraph StateGraph Architecture
        </h3>

        <div className="flex items-center justify-between min-w-[750px] gap-2">
          {PIPELINE_NODES.map((node, idx) => (
            <React.Fragment key={node.id}>
              <div className="flex-1 bg-slate-50 border border-slate-200 rounded-xl p-3 text-center shadow-xs">
                <div className="text-[10px] font-bold text-slate-400 uppercase">Step {idx + 1}</div>
                <div className="text-xs font-semibold text-slate-800 mt-1">{node.label}</div>
              </div>
              {idx < PIPELINE_NODES.length - 1 && (
                <ArrowRight className="w-4 h-4 text-slate-300 flex-shrink-0" />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Runs Grid & Trace Details */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Execution Runs List (5 Cols) */}
        <div className="lg:col-span-5 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
          <div className="px-5 py-3.5 bg-slate-50 border-b border-slate-200 font-bold text-xs text-slate-700">
            Execution History ({runs.length})
          </div>

          <div className="divide-y divide-slate-100 overflow-y-auto max-h-[600px]">
            {loading ? (
              <div className="p-8 text-center text-xs text-slate-400">Loading traces...</div>
            ) : runs.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-400">
                No workflow runs recorded yet. Upload a document to trigger the pipeline.
              </div>
            ) : (
              runs.map((run) => (
                <div
                  key={run.id}
                  onClick={() => setSelectedRun(run)}
                  className={`p-4 cursor-pointer transition-all ${
                    selectedRun?.id === run.id ? 'bg-sky-50/70 border-l-4 border-sky-600' : 'hover:bg-slate-50'
                  }`}
                >
                  <div className="flex justify-between items-start text-xs">
                    <span className="font-bold text-slate-900">{run.id}</span>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                        run.status === 'COMPLETED'
                          ? 'bg-emerald-100 text-emerald-800'
                          : run.status === 'PAUSED_FOR_REVIEW'
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-slate-100 text-slate-700'
                      }`}
                    >
                      {run.status}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1">Doc: {run.document_id}</div>
                  <div className="text-[11px] text-slate-400 mt-1 flex items-center justify-between">
                    <span>Steps: {run.steps?.length || 0}</span>
                    <span>
                      {new Date(run.created_at).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right: Step Trace & Tool Execution Breakdown (7 Cols) */}
        <div className="lg:col-span-7 bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
          <div className="px-5 py-3.5 bg-slate-50 border-b border-slate-200 flex justify-between items-center text-xs font-bold text-slate-700">
            <span>Trace Detail: {selectedRun?.id || 'Select a run'}</span>
            {selectedRun && (
              <span className="text-slate-500 font-mono text-[11px]">
                Tokens: ~
                {selectedRun.agent_runs?.[0]
                  ? (selectedRun.agent_runs[0].input_tokens + selectedRun.agent_runs[0].output_tokens).toLocaleString()
                  : '640'}{' '}
                • Cost: $
                {selectedRun.agent_runs?.[0] ? selectedRun.agent_runs[0].total_cost.toFixed(4) : '0.0020'}
              </span>
            )}
          </div>

          <div className="p-6 flex-1 overflow-y-auto space-y-4 max-h-[600px]">
            {selectedRun ? (
              <>
                {/* Steps Timeline */}
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                  Node Progression Trace
                </h4>
                <div className="space-y-2">
                  {selectedRun.steps && selectedRun.steps.length > 0 ? (
                    selectedRun.steps.map((st: WorkflowStep, idx: number) => (
                      <div
                        key={st.id || idx}
                        className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1"
                      >
                        <div className="flex justify-between items-center">
                          <span className="font-bold text-slate-800 capitalize flex items-center gap-2">
                            <span className="w-5 h-5 rounded-full bg-sky-100 text-sky-700 flex items-center justify-center text-[10px] font-bold">
                              {idx + 1}
                            </span>
                            {st.step_name} Node
                          </span>
                          <span className="text-[11px] font-mono text-slate-500">
                            {st.latency_ms} ms
                          </span>
                        </div>
                        {st.output_state && (
                          <div className="text-[11px] font-mono text-slate-600 bg-white p-2 rounded border border-slate-100 truncate">
                            Output: {st.output_state}
                          </div>
                        )}
                      </div>
                    ))
                  ) : (
                    <div className="text-xs text-slate-400 italic">No node steps recorded.</div>
                  )}
                </div>

                {/* Executed Tool Calls */}
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mt-6 mb-2 flex items-center gap-1.5">
                  <Wrench className="w-3.5 h-3.5 text-slate-600" />
                  Allowlisted Tool Calls ({selectedRun.agent_runs?.[0]?.tool_calls?.length || 0})
                </h4>
                <div className="space-y-2">
                  {selectedRun.agent_runs?.[0]?.tool_calls &&
                  selectedRun.agent_runs[0].tool_calls.length > 0 ? (
                    selectedRun.agent_runs[0].tool_calls.map((tc, i) => (
                      <div
                        key={tc.id || i}
                        className="p-3 bg-slate-900 text-slate-200 rounded-xl text-xs font-mono space-y-1.5"
                      >
                        <div className="flex justify-between text-sky-400 font-bold">
                          <span>tool: {tc.tool_name}()</span>
                          <span className="text-emerald-400">{tc.status}</span>
                        </div>
                        <div className="text-[11px] text-slate-400">input: {tc.input_json}</div>
                        <div className="text-[11px] text-slate-300">output: {tc.output_json}</div>
                      </div>
                    ))
                  ) : (
                    <div className="text-xs text-slate-400 italic">
                      No tool calls executed for this workflow run.
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="text-center py-12 text-slate-400 text-xs">
                Select an execution run on the left to inspect telemetry traces.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
