import Link from "next/link";
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


        {/* User Avatar */}
        <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-white font-bold text-sm">
          JD
        </div>
      </div>
    </header>
  );
}

