"use client";

import Link from "next/link";
import HealthIndicator from "@/components/dashboard/HealthIndicator";
import { useAuth } from "@/context/AuthContext";

interface DashboardHeaderProps {
  federatedSearch: boolean;
  onToggleFederated: () => void;
  auditMode: boolean;
  onToggleAudit: () => void;
}

export default function DashboardHeader({
  federatedSearch,
  onToggleFederated,
  auditMode,
  onToggleAudit,
}: DashboardHeaderProps) {
  const { user, logout } = useAuth();

  return (
    <header className="h-16 flex items-center justify-between px-lg glass-nav bg-white/80 dark:bg-[#0c1021]/80 backdrop-blur-xl border-b border-slate-200 dark:border-slate-800 z-30 sticky top-0 text-slate-900 dark:text-white transition-colors">
      <div className="flex items-center gap-lg">
        {/* Easy Back Navigation */}
        <nav className="flex items-center gap-md">
          <Link
            href="/"
            className="flex items-center gap-xs font-label-md text-xs text-slate-700 dark:text-slate-300 hover:text-primary dark:hover:text-white transition-colors"
          >
            <span className="material-symbols-outlined text-[18px]">home</span>
            <span>Home</span>
          </Link>
          <span className="text-slate-400 dark:text-slate-600 text-xs">•</span>
          <Link
            href="/about"
            className="font-label-md text-xs text-slate-700 dark:text-slate-300 hover:text-primary dark:hover:text-white transition-colors"
          >
            About
          </Link>
          <span className="text-slate-400 dark:text-slate-600 text-xs">•</span>
          <Link
            href="/contact"
            className="font-label-md text-xs text-slate-700 dark:text-slate-300 hover:text-primary dark:hover:text-white transition-colors"
          >
            Contact
          </Link>
        </nav>

        {/* Health Indicator */}
        <HealthIndicator />
      </div>

      <div className="flex items-center gap-md">
        {/* Federated Search Toggle */}
        <button
          onClick={onToggleFederated}
          title="Federated Mode: Search across all your uploaded documents"
          className={`flex items-center gap-xs px-3 py-1.5 rounded-full text-label-md font-label-md font-bold transition-all border ${
            federatedSearch
              ? "bg-primary text-white border-primary shadow-sm"
              : "bg-slate-100 dark:bg-white/10 text-slate-700 dark:text-slate-200 border-slate-300 dark:border-slate-700 hover:border-primary"
          }`}
        >
          <span className="material-symbols-outlined text-[16px]">travel_explore</span>
          <span className="text-[12px]">Federated</span>
        </button>

        {/* Audit Mode Toggle */}
        <button
          onClick={onToggleAudit}
          title="Audit Mode: Ground query strictly on the loaded document"
          className={`flex items-center gap-xs px-3 py-1.5 rounded-full text-label-md font-label-md font-bold transition-all border ${
            auditMode
              ? "bg-primary text-white border-primary shadow-sm"
              : "bg-slate-100 dark:bg-white/10 text-slate-700 dark:text-slate-200 border-slate-300 dark:border-slate-700 hover:border-primary"
          }`}
        >
          <span className="material-symbols-outlined text-[16px]">verified_user</span>
          <span className="text-[12px]">Audit</span>
        </button>

        {/* User Avatar Badge on Top Right */}
        {user ? (
          <div className="relative group flex items-center">
            <div
              className="w-9 h-9 rounded-full bg-gradient-to-tr from-primary to-blue-500 text-white font-bold text-sm flex items-center justify-center shadow-md cursor-pointer border-2 border-white dark:border-slate-800 transition-transform group-hover:scale-105"
              title={user.email}
            >
              {user.email.charAt(0).toUpperCase()}
            </div>

            {/* Hover Tooltip displaying email & Sign Out */}
            <div className="absolute right-0 top-11 hidden group-hover:flex flex-col items-end min-w-[200px] bg-white dark:bg-[#0c1021] border border-slate-200 dark:border-slate-800 rounded-xl p-3 shadow-xl z-50 fade-in">
              <span className="text-xs font-semibold text-slate-900 dark:text-white truncate max-w-[180px]">
                {user.email}
              </span>
              <span className="text-[10px] text-slate-400 dark:text-slate-500 mb-2">Authenticated User</span>
              <button
                onClick={logout}
                className="w-full flex items-center justify-center gap-1.5 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 hover:bg-red-100 dark:hover:bg-red-900/40 py-1.5 px-3 rounded-lg font-medium transition-colors"
              >
                <span className="material-symbols-outlined text-[16px]">logout</span>
                <span>Sign Out</span>
              </button>
            </div>
          </div>
        ) : (
          <div className="w-9 h-9 rounded-full bg-primary/20 flex items-center justify-center text-primary font-bold text-xs">
            DM
          </div>
        )}
      </div>
    </header>
  );
}
