import React, { useState } from 'react';
import {
  Activity,
  AlertCircle,
  BookOpen,
  CheckCircle2,
  Clock,
  Cpu,
  FileText,
  Home,
  Shield,
  Upload,
  UserCheck,
} from 'lucide-react';
import { DEMO_USERS, getGlobalRole, setGlobalRole } from '../lib/api';
import { UserRole } from '../types';

interface LayoutProps {
  currentTab: string;
  onSelectTab: (tab: string) => void;
  pendingReviewsCount?: number;
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({
  currentTab,
  onSelectTab,
  pendingReviewsCount = 0,
  children,
}) => {
  const [activeRole, setActiveRole] = useState<UserRole>(getGlobalRole());

  const handleRoleChange = (role: UserRole) => {
    setActiveRole(role);
    setGlobalRole(role);
  };

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: Home },
    { id: 'documents', label: 'Documents', icon: FileText },
    {
      id: 'reviews',
      label: 'Review Queue',
      icon: UserCheck,
      badge: pendingReviewsCount > 0 ? pendingReviewsCount : undefined,
    },
    { id: 'knowledge', label: 'Knowledge Base', icon: BookOpen },
    { id: 'agents', label: 'Agent Telemetry', icon: Cpu },
    { id: 'audit', label: 'Audit Trail', icon: Shield },
  ];

  return (
    <div className="flex h-screen bg-slate-50 text-slate-800 antialiased overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900 text-white flex flex-col flex-shrink-0 border-r border-slate-800">
        <div className="p-6 border-b border-slate-800">
          <div className="flex items-center space-x-3">
            <div className="h-9 w-9 rounded-lg bg-sky-500 flex items-center justify-center text-white shadow-md shadow-sky-500/20 font-bold text-lg">
              OP
            </div>
            <div>
              <h1 className="font-bold text-base tracking-tight text-white flex items-center gap-1.5">
                OpsPilot AI
              </h1>
              <p className="text-xs text-sky-400 font-medium">Enterprise Edition</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  isActive
                    ? 'bg-sky-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                }`}
              >
                <div className="flex items-center space-x-3">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-slate-400'}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge !== undefined && (
                  <span
                    className={`px-2 py-0.5 text-xs font-semibold rounded-full ${
                      isActive ? 'bg-white text-sky-700' : 'bg-amber-500 text-white'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Tenant and System Information */}
        <div className="p-4 border-t border-slate-800 bg-slate-950/60">
          <div className="text-xs text-slate-400">Tenant Isolation</div>
          <div className="text-xs font-semibold text-slate-200 truncate mt-0.5">
            Nexus Corp (Multi-Tenant)
          </div>
          <div className="flex items-center gap-1.5 mt-2 text-[11px] text-emerald-400 font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            LangGraph Engine Active
          </div>
        </div>
      </aside>

      {/* Main Container */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Header */}
        <header className="h-16 bg-white border-b border-slate-200 px-6 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center space-x-3">
            <span className="text-xs font-semibold px-2.5 py-1 bg-slate-100 text-slate-700 rounded-md border border-slate-200 uppercase tracking-wider">
              {currentTab}
            </span>
          </div>

          {/* Active User and Live Role Switcher */}
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2 bg-slate-100 p-1.5 rounded-lg border border-slate-200 text-xs">
              <span className="text-slate-500 font-medium px-1">Role:</span>
              {(['admin', 'ops_manager', 'reviewer', 'viewer'] as UserRole[]).map((r) => (
                <button
                  key={r}
                  onClick={() => handleRoleChange(r)}
                  className={`px-2.5 py-1 rounded text-xs font-semibold transition-all ${
                    activeRole === r
                      ? 'bg-sky-600 text-white shadow-sm'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200'
                  }`}
                >
                  {r === 'ops_manager' ? 'Ops Mgr' : r.charAt(0).toUpperCase() + r.slice(1)}
                </button>
              ))}
            </div>

            <div className="flex items-center space-x-2 pl-2 border-l border-slate-200">
              <div className="w-8 h-8 rounded-full bg-slate-800 text-white flex items-center justify-center text-xs font-semibold">
                {DEMO_USERS[activeRole].name.charAt(0)}
              </div>
              <div className="text-left hidden md:block">
                <div className="text-xs font-semibold text-slate-800">
                  {DEMO_USERS[activeRole].name}
                </div>
                <div className="text-[11px] text-slate-500">{DEMO_USERS[activeRole].email}</div>
              </div>
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
};
