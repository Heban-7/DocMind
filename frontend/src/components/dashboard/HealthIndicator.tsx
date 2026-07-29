"use client";

import { useHealth } from "@/hooks/useHealth";

export default function HealthIndicator() {
  const { isOnline, version } = useHealth();

  return (
    <div className="flex items-center gap-xs px-3 py-1.5 rounded-full bg-surface-container border border-outline-variant/30">
      <span
        className={`w-2 h-2 rounded-full ${
          isOnline ? "bg-green-500 animate-pulse" : "bg-red-500"
        }`}
      />
      <span className="font-label-md text-[12px] text-on-surface-variant">
        {isOnline ? "Engine Online" : "Engine Offline"}
      </span>
      {isOnline && version && (
        <span className="font-label-md text-[10px] text-on-surface-variant/50">
          v{version}
        </span>
      )}
    </div>
  );
}
