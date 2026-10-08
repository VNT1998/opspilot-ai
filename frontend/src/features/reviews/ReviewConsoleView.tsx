import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Edit3,
  ExternalLink,
  FileText,
  Save,
  ShieldAlert,
  ThumbsDown,
  ThumbsUp,
  UserCheck,
  XCircle,
} from 'lucide-react';
import { api } from '../../lib/api';
import { ReviewTask, ValidationFinding } from '../../types';

export const ReviewConsoleView: React.FC = () => {
  const [tasks, setTasks] = useState<ReviewTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [comments, setComments] = useState('');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Editable fields state
  const [editedFields, setEditedFields] = useState<Record<string, any>>({});

  useEffect(() => {
    loadReviewTasks();
  }, []);

  const loadReviewTasks = async () => {
    try {
      setLoading(true);
      const data = await api.getReviews('PENDING');
      setTasks(data);
      if (data.length > 0 && !selectedTaskId) {
        setSelectedTaskId(data[0].id);
        initializeFields(data[0]);
      }
    } catch (e) {
      console.error('Failed to load review tasks:', e);
    } finally {
      setLoading(false);
    }
  };

  const initializeFields = (task: ReviewTask) => {
    if (task.document?.extraction?.structured_data) {
      setEditedFields({ ...task.document.extraction.structured_data });
    }
  };

  const currentTask = tasks.find((t) => t.id === selectedTaskId);

  const handleSelectTask = (task: ReviewTask) => {
    setSelectedTaskId(task.id);
    initializeFields(task);
    setComments('');
    setStatusMessage(null);
  };

  const handleFieldChange = (field: string, value: any) => {
    setEditedFields((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleApprove = async () => {
    if (!selectedTaskId) return;
    try {
      setActionLoading(true);
      const res = await api.approveReview(selectedTaskId, comments || 'Approved by human reviewer');
      setStatusMessage(`Approved: ${res.message}`);
      await loadReviewTasks();
    } catch (e: any) {
      setStatusMessage(`Error: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!selectedTaskId) return;
    try {
      setActionLoading(true);
      const res = await api.rejectReview(selectedTaskId, comments || 'Rejected by human reviewer');
      setStatusMessage(`Rejected: ${res.message}`);
      await loadReviewTasks();
    } catch (e: any) {
      setStatusMessage(`Error: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleEditAndSave = async () => {
    if (!selectedTaskId) return;
    try {
      setActionLoading(true);
      const res = await api.editReview(
        selectedTaskId,
        editedFields,
        comments || 'Edited and resolved by human reviewer',
      );
      setStatusMessage(`Saved & Approved: ${res.message}`);
      await loadReviewTasks();
    } catch (e: any) {
      setStatusMessage(`Error: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return <div className="text-center py-12 text-slate-400 text-xs">Loading review queue...</div>;
  }

  if (tasks.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center max-w-xl mx-auto shadow-sm">
        <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto mb-3" />
        <h3 className="font-bold text-base text-slate-900">Review Queue is Clear!</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
          All high-confidence documents have been automatically processed and reconciled against POs.
          Upload new test documents with exceptions to test this human-in-the-loop review console.
        </p>
      </div>
    );
  }

  const doc = currentTask?.document;
  const extraction = doc?.extraction;
  const findings = extraction?.validation_findings || [];

  return (
    <div className="space-y-4 max-w-7xl mx-auto">
      {/* Top Banner / Task Switcher */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-amber-50 text-amber-600 rounded-lg">
            <UserCheck className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              Human Review Console
              <span className="text-xs font-semibold px-2 py-0.5 bg-amber-100 text-amber-800 rounded-full">
                {tasks.length} Pending
              </span>
            </h2>
            <p className="text-xs text-slate-500">
              Split-screen inspection of original evidence, extracted fields, and policy citations.
            </p>
          </div>
        </div>

        {/* Task Selector */}
        <div className="flex items-center gap-2 overflow-x-auto">
          {tasks.map((task, idx) => (
            <button
              key={task.id}
              onClick={() => handleSelectTask(task)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
                task.id === selectedTaskId
                  ? 'bg-sky-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              Task #{idx + 1}: {task.document?.filename || task.id}
            </button>
          ))}
        </div>
      </div>

      {statusMessage && (
        <div
          className={`p-3 rounded-lg text-xs font-medium ${
            statusMessage.startsWith('Error')
              ? 'bg-rose-50 text-rose-700 border border-rose-200'
              : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
          }`}
        >
          {statusMessage}
        </div>
      )}

      {/* Split Screen Container (Section 12 specification) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-[580px]">
        {/* LEFT PANE: Document Preview & Highlighted Evidence (5 Cols) */}
        <div className="lg:col-span-5 bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
          <div className="px-5 py-3.5 bg-slate-50 border-b border-slate-200 flex justify-between items-center">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-700">
              <FileText className="w-4 h-4 text-slate-500" />
              <span>Document Evidence Preview</span>
            </div>
            <span className="text-[11px] text-slate-500 font-mono">
              {doc?.filename} • Page 1 of 1
            </span>
          </div>

          <div className="p-6 flex-1 bg-slate-900 text-slate-100 font-mono text-xs overflow-y-auto leading-relaxed select-text space-y-4">
            <div className="p-3 bg-slate-800 rounded-lg border border-slate-700 text-sky-300 font-sans text-xs">
              <span className="font-semibold block mb-1">OCR Text Stream:</span>
              Highlighting extracted entities and business policy triggers in document stream.
            </div>

            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 whitespace-pre-wrap">
              {doc?.pages && doc.pages.length > 0
                ? doc.pages[0].text_content
                : `=== INVOICE DETAILS ===
Invoice Number: ${editedFields.invoice_number || 'INV-2026-001'}
Vendor Name: ${editedFields.vendor_name || 'Acme Industrial Supplies'}
PO Reference: ${editedFields.po_number || 'PO-9001'}
Issue Date: ${editedFields.invoice_date || '2026-10-01'}

Line Items:
1. Standard Enterprise Service License (SKU: SRV-100)
   Qty: 1.0 @ $${editedFields.subtotal || '1318.18'}

Subtotal: $${editedFields.subtotal || '1318.18'}
Tax (10%): $${editedFields.tax || '131.82'}
TOTAL AMOUNT DUE: $${editedFields.total || '1450.00'}

Payment Terms: Net 30
Remit to: payments@vendor.com`}
            </div>

            {/* Exception Callout */}
            <div className="p-3 bg-amber-950/60 border border-amber-600/40 rounded-lg text-amber-200 font-sans text-xs space-y-1">
              <div className="font-bold flex items-center gap-1.5 text-amber-300">
                <AlertTriangle className="w-4 h-4" />
                Escalation Trigger:
              </div>
              <p className="text-[11px] text-amber-100">{currentTask?.reason}</p>
            </div>
          </div>
        </div>

        {/* RIGHT PANE: Extracted Fields, PO Match, Validation Rules, Policy Citations (7 Cols) */}
        <div className="lg:col-span-7 bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
          <div className="px-5 py-3.5 bg-slate-50 border-b border-slate-200 flex justify-between items-center">
            <span className="text-xs font-bold text-slate-700">Reconciliation & Extracted Fields</span>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500 font-medium">Confidence:</span>
              <span
                className={`text-xs font-bold px-2 py-0.5 rounded ${
                  (currentTask?.confidence || 0.95) >= 0.85
                    ? 'bg-emerald-100 text-emerald-800'
                    : 'bg-amber-100 text-amber-800'
                }`}
              >
                {Math.round((currentTask?.confidence || 0.95) * 100)}%
              </span>
            </div>
          </div>

          <div className="p-6 flex-1 overflow-y-auto space-y-6">
            {/* 1. Editable Extraction Fields Form */}
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3 flex items-center gap-1.5">
                <Edit3 className="w-3.5 h-3.5 text-sky-600" />
                Extracted Data (Editable by Reviewer)
              </h4>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="text-[11px] font-semibold text-slate-600 block mb-1">
                    Invoice Number
                  </label>
                  <input
                    type="text"
                    value={editedFields.invoice_number || ''}
                    onChange={(e) => handleFieldChange('invoice_number', e.target.value)}
                    className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-slate-800 focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-semibold text-slate-600 block mb-1">
                    Vendor Name
                  </label>
                  <input
                    type="text"
                    value={editedFields.vendor_name || ''}
                    onChange={(e) => handleFieldChange('vendor_name', e.target.value)}
                    className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-slate-800 focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-semibold text-slate-600 block mb-1">
                    Referenced PO Number
                  </label>
                  <input
                    type="text"
                    value={editedFields.po_number || ''}
                    onChange={(e) => handleFieldChange('po_number', e.target.value)}
                    className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-slate-800 focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-semibold text-slate-600 block mb-1">
                    Invoice Total ($)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={editedFields.total || 0}
                    onChange={(e) => handleFieldChange('total', parseFloat(e.target.value) || 0)}
                    className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-slate-800 font-bold focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-semibold text-slate-600 block mb-1">
                    Subtotal ($)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={editedFields.subtotal || 0}
                    onChange={(e) => handleFieldChange('subtotal', parseFloat(e.target.value) || 0)}
                    className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-slate-800 focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-semibold text-slate-600 block mb-1">
                    Tax ($)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={editedFields.tax || 0}
                    onChange={(e) => handleFieldChange('tax', parseFloat(e.target.value) || 0)}
                    className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-slate-800 focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
                  />
                </div>
              </div>
            </div>

            {/* 2. Deterministic Rule Findings */}
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1.5">
                <ShieldAlert className="w-3.5 h-3.5 text-slate-600" />
                Deterministic Business Rules Evaluation
              </h4>
              <div className="space-y-1.5">
                {findings.length > 0 ? (
                  findings.map((f: ValidationFinding, i: number) => (
                    <div
                      key={i}
                      className={`p-2.5 rounded-lg text-xs flex items-start gap-2 ${
                        f.passed
                          ? 'bg-emerald-50 text-emerald-800 border border-emerald-100'
                          : f.severity === 'ERROR'
                          ? 'bg-rose-50 text-rose-800 border border-rose-200 font-medium'
                          : 'bg-amber-50 text-amber-800 border border-amber-200'
                      }`}
                    >
                      {f.passed ? (
                        <Check className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                      ) : (
                        <XCircle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
                      )}
                      <div>
                        <div className="font-semibold">{f.rule_name}</div>
                        <div className="text-[11px] mt-0.5 opacity-90">{f.message}</div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-xs text-slate-400 italic">No rule anomalies detected.</div>
                )}
              </div>
            </div>

            {/* 3. Corporate Policy Citations (RAG) */}
            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2 flex items-center gap-1.5">
                <BookOpen className="w-3.5 h-3.5 text-sky-600" />
                Grounded Policy Citations (SOP-FIN-2026)
              </h4>
              <div className="text-xs text-slate-700 bg-white p-3 rounded-lg border border-slate-200 space-y-2">
                <div className="font-semibold text-slate-900">
                  Section 1.3: High-Value Threshold Policy
                </div>
                <p className="text-[11px] text-slate-600 leading-relaxed italic">
                  "Invoices exceeding $10,000.00 strictly require mandatory Operations Manager sign-off
                  and two-party human review regardless of AI confidence scores."
                </p>
                <div className="text-[10px] text-sky-600 font-semibold flex items-center gap-1">
                  <span>Source: SOP-FIN-2026 • Page 1 • Department: Finance</span>
                </div>
              </div>
            </div>

            {/* Reviewer Comments input */}
            <div>
              <label className="text-xs font-bold text-slate-700 block mb-1">
                Reviewer Justification / Comments
              </label>
              <textarea
                rows={2}
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                placeholder="Enter audit remarks or override justification..."
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs text-slate-800 focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
              />
            </div>
          </div>

          {/* BOTTOM ACTION BAR (Section 12 specification) */}
          <div className="p-4 bg-slate-50 border-t border-slate-200 flex flex-wrap items-center justify-between gap-3">
            <button
              onClick={handleReject}
              disabled={actionLoading}
              className="flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-rose-50 text-rose-700 border border-rose-200 rounded-lg text-xs font-semibold shadow-xs transition-all disabled:opacity-50"
            >
              <ThumbsDown className="w-3.5 h-3.5" />
              Reject Document
            </button>

            <div className="flex items-center gap-2">
              <button
                onClick={handleEditAndSave}
                disabled={actionLoading}
                className="flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-lg text-xs font-semibold shadow-xs transition-all disabled:opacity-50"
              >
                <Save className="w-3.5 h-3.5 text-sky-600" />
                Save Edits & Approve
              </button>

              <button
                onClick={handleApprove}
                disabled={actionLoading}
                className="flex items-center gap-1.5 px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold shadow-sm transition-all disabled:opacity-50"
              >
                <ThumbsUp className="w-3.5 h-3.5" />
                Approve & Post to ERP
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
