"use client";

import HealthIndicator from "@/components/dashboard/HealthIndicator";

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
  return (
    <header className="h-16 flex items-center justify-between px-lg glass-nav bg-surface/70 border-b border-outline-variant/30 z-30 sticky top-0">
      <div className="flex items-center gap-lg">
        {/* View Switcher */}
        <nav className="flex bg-surface-container p-1 rounded-lg">
          <button className="px-4 py-1.5 font-label-md text-label-md bg-white rounded-md shadow-sm text-primary font-bold transition-all">
            Chat
          </button>
          <button className="px-4 py-1.5 font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors">
            Analysis
          </button>
          <button className="px-4 py-1.5 font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors">
            Compare
          </button>
        </nav>

        {/* Health Indicator */}
        <HealthIndicator />
      </div>

      <div className="flex items-center gap-md">
        {/* Federated Search Toggle */}
        <button
          onClick={onToggleFederated}
          className={`flex items-center gap-xs px-3 py-1.5 rounded-full text-label-md font-label-md font-bold transition-all border ${
            federatedSearch
              ? "bg-primary text-white border-primary"
              : "bg-surface-container text-on-surface-variant border-outline-variant/30 hover:border-primary"
          }`}
        >
          <span className="material-symbols-outlined text-[16px]">travel_explore</span>
          <span className="text-[12px]">Federated</span>
        </button>

        {/* Audit Mode Toggle */}
        <button
          onClick={onToggleAudit}
          className={`flex items-center gap-xs px-3 py-1.5 rounded-full text-label-md font-label-md font-bold transition-all border ${
            auditMode
              ? "bg-primary text-white border-primary"
              : "bg-surface-container text-on-surface-variant border-outline-variant/30 hover:border-primary"
          }`}
        >
          <span className="material-symbols-outlined text-[16px]">verified_user</span>
          <span className="text-[12px]">Audit</span>
        </button>

        {/* User Avatar */}
        <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-white font-bold text-sm">
          JD
        </div>
      </div>
    </header>
  );
}
