import React, { useEffect, useState } from 'react';
import {
  BookOpen,
  CheckCircle2,
  FileText,
  Lock,
  Plus,
  Search,
  Shield,
  Sparkles,
} from 'lucide-react';
import { api } from '../../lib/api';
import { Citation, KnowledgeSearchResponse } from '../../types';

export const KnowledgeView: React.FC = () => {
  const [query, setQuery] = useState('');
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResult, setSearchResult] = useState<KnowledgeSearchResponse | null>(null);
  const [docs, setDocs] = useState<any[]>([]);
  const [showAddModal, setShowAddModal] = useState(false);

  // New doc form state
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [department, setDepartment] = useState('finance');
  const [indexLoading, setIndexLoading] = useState(false);
  const [indexMessage, setIndexMessage] = useState<string | null>(null);

  useEffect(() => {
    loadKnowledgeDocs();
  }, []);

  const loadKnowledgeDocs = async () => {
    try {
      const data = await api.getKnowledgeDocs();
      setDocs(data);
    } catch (e) {
      console.error('Failed to load knowledge docs:', e);
    }
  };

  const handleSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return;
    try {
      setSearchLoading(true);
      const res = await api.searchKnowledge(searchQuery);
      setSearchResult(res);
    } catch (e: any) {
      alert(`Search failed: ${e.message}`);
    } finally {
      setSearchLoading(false);
    }
  };

  const handleIndexSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setIndexLoading(true);
      await api.indexKnowledge({ title, content, department });
      setIndexMessage('Document indexed and embedded into vector store successfully.');
      setTitle('');
      setContent('');
      await loadKnowledgeDocs();
      setTimeout(() => {
        setShowAddModal(false);
        setIndexMessage(null);
      }, 1500);
    } catch (e: any) {
      setIndexMessage(`Error: ${e.message}`);
    } finally {
      setIndexLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Enterprise Knowledge Base & RAG</h2>
          <p className="text-xs text-slate-500">
            ACL-aware hybrid retrieval (dense embeddings + lexical matching) with exact source citations.
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-1.5 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shadow-sm transition-all self-start"
        >
          <Plus className="w-4 h-4" />
          Index Policy Document
        </button>
      </div>

      {/* Interactive Search Console */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch(query)}
              placeholder="Ask a policy question e.g. What approval threshold applies to invoices above $10k?"
              className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:bg-white focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
            />
          </div>
          <button
            onClick={() => handleSearch(query)}
            disabled={searchLoading}
            className="px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs rounded-xl shadow-sm transition-all disabled:opacity-50"
          >
            {searchLoading ? 'Searching...' : 'Hybrid Search'}
          </button>
        </div>

        {/* Preset Sample Policy Queries */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-[11px] font-semibold text-slate-400">Sample Queries:</span>
          {[
            'What is the approval threshold for invoices over $10,000?',
            'What are the three-way matching rules for purchase orders?',
            'Can duplicate invoice numbers be approved?',
          ].map((sample, i) => (
            <button
              key={i}
              onClick={() => {
                setQuery(sample);
                handleSearch(sample);
              }}
              className="px-2.5 py-1 bg-slate-100 hover:bg-sky-50 text-slate-600 hover:text-sky-700 rounded-lg text-[11px] font-medium border border-slate-200 transition-all"
            >
              {sample}
            </button>
          ))}
        </div>

        {/* Search Results & Citations Display */}
        {searchResult && (
          <div className="mt-6 pt-6 border-t border-slate-100 space-y-4">
            {/* Synthesized Answer */}
            <div className="bg-gradient-to-r from-sky-50 to-indigo-50/40 p-5 rounded-xl border border-sky-100">
              <div className="flex items-center gap-2 text-xs font-bold text-sky-900 mb-2">
                <Sparkles className="w-4 h-4 text-sky-600" />
                Grounded Knowledge Synthesis
              </div>
              <p className="text-xs text-slate-700 leading-relaxed font-medium">
                {searchResult.answer}
              </p>
            </div>

            {/* Citations Grid */}
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">
                Verifiable Source Citations ({searchResult.sources.length})
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {searchResult.sources.map((src: Citation, idx: number) => (
                  <div
                    key={idx}
                    className="p-4 bg-white rounded-xl border border-slate-200 shadow-xs space-y-2"
                  >
                    <div className="flex justify-between items-start">
                      <span className="font-bold text-xs text-slate-800">{src.title}</span>
                      <span className="text-[10px] font-bold px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded-md">
                        {Math.round(src.relevance_score * 100)}% Match
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-600 bg-slate-50 p-2.5 rounded-lg border border-slate-100 font-mono italic">
                      "{src.snippet}"
                    </p>
                    <div className="text-[10px] text-slate-400 flex items-center justify-between">
                      <span>Doc: {src.document_id}</span>
                      <span>Page {src.page_number}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Indexed Documents Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center">
          <h3 className="font-bold text-sm text-slate-900">Active Indexed Policy Documents</h3>
          <span className="text-xs text-slate-400">{docs.length} Documents</span>
        </div>
        <div className="divide-y divide-slate-100 text-xs">
          {docs.map((d) => (
            <div key={d.id} className="p-4 px-6 flex justify-between items-center hover:bg-slate-50">
              <div>
                <div className="font-semibold text-slate-800">{d.title}</div>
                <div className="text-[11px] text-slate-400 mt-0.5">
                  Dept: {d.department} • Type: {d.doc_type} • ID: {d.id}
                </div>
              </div>
              <div className="flex items-center gap-1.5 text-[11px] text-slate-600 bg-slate-100 px-2.5 py-1 rounded-md">
                <Shield className="w-3 h-3 text-sky-600" />
                <span>ACL: {d.acl_roles?.join(', ')}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Modal: Index New Policy */}
      {showAddModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl border border-slate-200">
            <h3 className="font-bold text-base text-slate-900 mb-4 flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-sky-600" />
              Index New Policy Document
            </h3>
            <form onSubmit={handleIndexSubmit} className="space-y-4 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Document Title</label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Travel & Entertainment Reimbursement Policy"
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-slate-800"
                />
              </div>
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Department</label>
                <select
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-slate-800"
                >
                  <option value="finance">Finance & Accounts Payable</option>
                  <option value="procurement">Procurement</option>
                  <option value="compliance">Legal & Compliance</option>
                </select>
              </div>
              <div>
                <label className="font-semibold text-slate-700 block mb-1">
                  Policy Content (Supports --- Page X --- delimiters)
                </label>
                <textarea
                  required
                  rows={6}
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder="Enter full text of the policy or SOP..."
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-slate-800 font-mono text-[11px]"
                />
              </div>

              {indexMessage && (
                <div className="p-3 bg-emerald-50 text-emerald-800 rounded-lg text-xs font-medium">
                  {indexMessage}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 border border-slate-200 rounded-lg text-slate-600"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={indexLoading}
                  className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg font-semibold"
                >
                  {indexLoading ? 'Chunking & Embedding...' : 'Index Policy'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
