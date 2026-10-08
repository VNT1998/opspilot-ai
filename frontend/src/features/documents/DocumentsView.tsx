import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Eye,
  FileCheck,
  FileText,
  Filter,
  RefreshCw,
  RotateCw,
  Upload,
  X,
} from 'lucide-react';
import { api } from '../../lib/api';
import { Document } from '../../types';

interface DocumentsViewProps {
  onSelectDocumentForReview?: (docId: string) => void;
  isUploadOpen: boolean;
  onCloseUpload: () => void;
}

export const DocumentsView: React.FC<DocumentsViewProps> = ({
  onSelectDocumentForReview,
  isUploadOpen,
  onCloseUpload,
}) => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);

  useEffect(() => {
    loadDocuments();
  }, [statusFilter]);

  const loadDocuments = async () => {
    try {
      setLoading(true);
      const res = await api.getDocuments(statusFilter || undefined);
      setDocuments(res.items);
    } catch (e) {
      console.error('Failed to load documents:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    try {
      setUploading(true);
      setUploadMessage(null);
      const res = await api.uploadDocument(file);
      setUploadMessage(`Success: Document ${res.filename} queued for processing.`);
      await loadDocuments();
      setTimeout(() => {
        onCloseUpload();
        setUploadMessage(null);
      }, 1500);
    } catch (e: any) {
      setUploadMessage(`Error: ${e.message}`);
    } finally {
      setUploading(false);
    }
  };

  const handleCreateSampleInvoice = (
    name: string,
    content: string,
  ) => {
    const file = new File([content], name, { type: 'text/plain' });
    handleFileUpload(file);
  };

  const handleReprocess = async (docId: string) => {
    try {
      await api.reprocessDocument(docId);
      await loadDocuments();
    } catch (e: any) {
      alert(`Reprocess failed: ${e.message}`);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'COMPLETED':
      case 'APPROVED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
            <CheckCircle2 className="w-3 h-3" />
            {status}
          </span>
        );
      case 'REVIEW_REQUIRED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800">
            <AlertCircle className="w-3 h-3" />
            REVIEW REQUIRED
          </span>
        );
      case 'PROCESSING':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-100 text-sky-800 animate-pulse">
            <RotateCw className="w-3 h-3 animate-spin" />
            PROCESSING
          </span>
        );
      case 'QUEUED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700">
            <Clock className="w-3 h-3" />
            QUEUED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-800">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Top action row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Document Repository</h2>
          <p className="text-xs text-slate-500">
            Uploaded business files, extraction confidence, and automated routing lifecycle.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Status filter */}
          <div className="flex items-center gap-1.5 bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-600 shadow-sm">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-transparent border-none text-xs font-medium focus:ring-0 cursor-pointer"
            >
              <option value="">All Statuses</option>
              <option value="COMPLETED">Completed</option>
              <option value="REVIEW_REQUIRED">Review Required</option>
              <option value="PROCESSING">Processing</option>
              <option value="QUEUED">Queued</option>
              <option value="REJECTED">Rejected</option>
            </select>
          </div>

          <button
            onClick={loadDocuments}
            className="p-2 text-slate-500 hover:text-slate-800 bg-white border border-slate-200 rounded-lg shadow-sm transition-all"
            title="Refresh list"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Documents Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider">
              <tr>
                <th className="px-6 py-3.5">Document</th>
                <th className="px-6 py-3.5">Classification</th>
                <th className="px-6 py-3.5">Status</th>
                <th className="px-6 py-3.5">AI Confidence</th>
                <th className="px-6 py-3.5">Created At</th>
                <th className="px-6 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-slate-400">
                    Loading documents...
                  </td>
                </tr>
              ) : documents.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-slate-400">
                    <FileText className="w-8 h-8 mx-auto mb-2 text-slate-300" />
                    No documents found. Click "Upload Document" to process a file.
                  </td>
                </tr>
              ) : (
                documents.map((doc) => (
                  <tr key={doc.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-semibold text-slate-900">{doc.filename}</div>
                      <div className="text-[11px] text-slate-400">
                        {doc.file_type.toUpperCase()} • {(doc.file_size / 1024).toFixed(1)} KB • {doc.id}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="capitalize font-medium text-slate-700 bg-slate-100 px-2 py-0.5 rounded">
                        {doc.classification || 'Unclassified'}
                      </span>
                    </td>
                    <td className="px-6 py-4">{getStatusBadge(doc.status)}</td>
                    <td className="px-6 py-4">
                      {doc.confidence_score ? (
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-700">
                            {Math.round(doc.confidence_score * 100)}%
                          </span>
                          <div className="w-16 bg-slate-100 rounded-full h-1.5">
                            <div
                              className={`h-full rounded-full ${
                                doc.confidence_score >= 0.85 ? 'bg-emerald-500' : 'bg-amber-500'
                              }`}
                              style={{ width: `${Math.round(doc.confidence_score * 100)}%` }}
                            ></div>
                          </div>
                        </div>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-slate-500">
                      {new Date(doc.created_at).toLocaleString([], {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </td>
                    <td className="px-6 py-4 text-right space-x-2">
                      <button
                        onClick={() => setSelectedDoc(doc)}
                        className="inline-flex items-center gap-1 text-sky-600 hover:text-sky-800 font-semibold px-2 py-1 rounded hover:bg-sky-50 transition-all"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        Details
                      </button>
                      <button
                        onClick={() => handleReprocess(doc.id)}
                        className="inline-flex items-center gap-1 text-slate-500 hover:text-slate-700 font-medium px-2 py-1 rounded hover:bg-slate-100 transition-all"
                        title="Re-run LangGraph Agent pipeline"
                      >
                        <RotateCw className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Upload Modal with 1-Click Test Scenarios */}
      {isUploadOpen && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl border border-slate-200">
            <div className="flex justify-between items-center pb-4 border-b border-slate-100">
              <h3 className="font-bold text-base text-slate-900 flex items-center gap-2">
                <Upload className="w-5 h-5 text-sky-600" />
                Upload Document for AI Processing
              </h3>
              <button onClick={onCloseUpload} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drag & drop file selector */}
            <div className="mt-4">
              <label className="border-2 border-dashed border-slate-200 hover:border-sky-400 rounded-xl p-8 flex flex-col items-center justify-center cursor-pointer bg-slate-50 hover:bg-sky-50/30 transition-all">
                <FileCheck className="w-10 h-10 text-sky-500 mb-2" />
                <span className="text-xs font-semibold text-slate-700">
                  Select a document from your computer
                </span>
                <span className="text-[11px] text-slate-400 mt-1">
                  Supports PDF, DOCX, PNG, JPG, TXT (Max 20MB)
                </span>
                <input
                  type="file"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files?.[0]) handleFileUpload(e.target.files[0]);
                  }}
                />
              </label>
            </div>

            {/* Quick 1-Click Benchmark Test Invoices */}
            <div className="mt-5">
              <div className="text-xs font-semibold text-slate-600 mb-2">
                Or launch a 1-click test benchmark scenario:
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <button
                  onClick={() =>
                    handleCreateSampleInvoice(
                      'invoice_clean_match.txt',
                      'Invoice: INV-2026-881\nVendor: Acme Industrial Supplies\nPO: PO-9001\nTotal: $1450.00\nSubtotal: $1318.18\nTax: $131.82\nStandard Enterprise Service License',
                    )
                  }
                  className="p-2.5 text-left border border-slate-200 hover:border-emerald-400 bg-slate-50 hover:bg-emerald-50/40 rounded-lg transition-all"
                >
                  <div className="font-semibold text-slate-800">1. Clean Match</div>
                  <div className="text-[10px] text-slate-500">Auto-approve (STP)</div>
                </button>

                <button
                  onClick={() =>
                    handleCreateSampleInvoice(
                      'invoice_high_value_cfo.txt',
                      'Invoice: INV-HIGH-994\nVendor: Acme Industrial Supplies\nPO: PO-9001\nTotal: $15400.00\nSubtotal: $14000.00\nTax: $1400.00\nHeavy Industrial Turbines and Infrastructure',
                    )
                  }
                  className="p-2.5 text-left border border-slate-200 hover:border-amber-400 bg-slate-50 hover:bg-amber-50/40 rounded-lg transition-all"
                >
                  <div className="font-semibold text-slate-800">2. High-Value ($15.4k)</div>
                  <div className="text-[10px] text-slate-500">Requires Review Policy</div>
                </button>

                <button
                  onClick={() =>
                    handleCreateSampleInvoice(
                      'invoice_variance_mismatch.txt',
                      'Invoice: INV-VAR-402\nVendor: Acme Industrial Supplies\nPO: PO-9001\nTotal: $1780.00\nSubtotal: $1618.18\nTax: $161.82\nPrice surge exceeding 2% tolerance',
                    )
                  }
                  className="p-2.5 text-left border border-slate-200 hover:border-rose-400 bg-slate-50 hover:bg-rose-50/40 rounded-lg transition-all"
                >
                  <div className="font-semibold text-slate-800">3. PO Tolerance Mismatch</div>
                  <div className="text-[10px] text-slate-500">Triggers 3-Way exception</div>
                </button>

                <button
                  onClick={() =>
                    handleCreateSampleInvoice(
                      'invoice_blurry_scan.txt',
                      'POOR SCAN - BLURRY HANDWRITTEN\nInvoice: INV-BLUR-09\nVendor: Acme Supplies\nTotal: $1450.00\nPO: PO-9001',
                    )
                  }
                  className="p-2.5 text-left border border-slate-200 hover:border-sky-400 bg-slate-50 hover:bg-sky-50/40 rounded-lg transition-all"
                >
                  <div className="font-semibold text-slate-800">4. Low-Confidence Scan</div>
                  <div className="text-[10px] text-slate-500">Confidence &lt; 85% Escalation</div>
                </button>
              </div>
            </div>

            {uploadMessage && (
              <div
                className={`mt-4 p-3 rounded-lg text-xs font-medium ${
                  uploadMessage.startsWith('Error')
                    ? 'bg-rose-50 text-rose-700'
                    : 'bg-emerald-50 text-emerald-700'
                }`}
              >
                {uploadMessage}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Document Details Modal */}
      {selectedDoc && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-xl border border-slate-200 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center pb-4 border-b border-slate-100">
              <div>
                <h3 className="font-bold text-base text-slate-900">{selectedDoc.filename}</h3>
                <p className="text-xs text-slate-400">ID: {selectedDoc.id}</p>
              </div>
              <button onClick={() => setSelectedDoc(null)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="mt-4 space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-4 bg-slate-50 p-4 rounded-xl">
                <div>
                  <span className="text-slate-400">Classification:</span>{' '}
                  <span className="font-semibold capitalize text-slate-800">
                    {selectedDoc.classification || 'Unclassified'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400">Status:</span>{' '}
                  <span className="font-semibold text-slate-800">{selectedDoc.status}</span>
                </div>
                <div>
                  <span className="text-slate-400">AI Confidence:</span>{' '}
                  <span className="font-semibold text-slate-800">
                    {selectedDoc.confidence_score
                      ? `${Math.round(selectedDoc.confidence_score * 100)}%`
                      : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400">MIME Type:</span>{' '}
                  <span className="font-semibold text-slate-800">{selectedDoc.mime_type}</span>
                </div>
              </div>

              {selectedDoc.extraction ? (
                <div>
                  <h4 className="font-bold text-slate-800 mb-2">Structured Extraction Fields</h4>
                  <pre className="bg-slate-950 text-slate-200 p-4 rounded-xl overflow-x-auto text-[11px] font-mono leading-relaxed">
                    {JSON.stringify(selectedDoc.extraction.structured_data, null, 2)}
                  </pre>
                </div>
              ) : (
                <div className="text-slate-400 py-4 text-center">
                  Extraction pending or processing in background worker.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
