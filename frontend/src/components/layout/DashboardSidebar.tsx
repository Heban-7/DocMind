"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import FileDropzone from "@/components/upload/FileDropzone";

interface SidebarProps {
  onNewChat: () => void;
  chatSessions?: { id: string; title: string }[];
  onUpload: (file: File) => void;
  uploadState: string;
  uploadedFileName?: string;
  strategyTier?: string;
}

export default function DashboardSidebar({
  onNewChat,
  chatSessions = [],
  onUpload,
  uploadState,
  uploadedFileName,
  strategyTier,
}: SidebarProps) {
  const pathname = usePathname();

  const navItems = [
    { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
    { href: "/", label: "Home", icon: "home" },
  ];

  const defaultSessions = chatSessions.length > 0 ? chatSessions : [
    { id: "1", title: "Q3 Financial Review" },
    { id: "2", title: "Compliance Audit 2024" },
    { id: "3", title: "Strategic Ops Analysis" },
  ];

  return (
    <aside className="fixed left-0 top-0 h-screen hidden md:flex flex-col py-lg w-[280px] bg-surface-container-low border-r border-outline-variant/30 z-40">
      <div className="px-lg mb-xl">
        <h1 className="font-headline-md text-headline-md font-bold text-on-surface">
          DocMind AI
        </h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant/70">
          Enterprise Intelligence
        </p>
      </div>

      <nav className="flex-1 px-md space-y-xs overflow-y-auto">
        {/* New Chat Button */}
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-sm bg-primary text-white rounded-lg px-4 py-3 mb-lg hover:bg-primary-container transition-all shadow-sm group"
        >
          <span className="material-symbols-outlined text-[20px]">add</span>
          <span className="font-label-md text-label-md font-bold">New Chat</span>
        </button>

        {/* Navigation */}
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-sm rounded-lg px-4 py-2 transition-all duration-200 ${
              pathname === item.href
                ? "bg-secondary-container text-on-secondary-container font-bold translate-x-1"
                : "text-on-surface-variant hover:bg-surface-container-high"
            }`}
          >
            <span className="material-symbols-outlined">{item.icon}</span>
            <span className="font-label-md text-label-md">{item.label}</span>
          </Link>
        ))}

        {/* Chat History */}
        <div className="pt-xl pb-sm">
          <span className="px-4 font-label-md text-label-md text-on-surface-variant/50 uppercase tracking-wider">
            Chat
          </span>
        </div>
        <div className="space-y-xs">
          {defaultSessions.map((session) => (
            <button
              key={session.id}
              className="w-full text-left flex items-center gap-sm text-on-surface-variant px-4 py-2 hover:bg-surface-container-high rounded-lg transition-all text-ellipsis overflow-hidden whitespace-nowrap"
            >
              <span className="material-symbols-outlined text-sm">chat_bubble</span>
              <span className="font-body-sm text-body-sm">{session.title}</span>
            </button>
          ))}
        </div>

        {/* Collections */}
        <div className="pt-lg pb-sm">
          <span className="px-4 font-label-md text-label-md text-on-surface-variant/50 uppercase tracking-wider">
            Collections
          </span>
        </div>
        <div className="space-y-xs">
          <button className="w-full text-left flex items-center gap-sm text-on-surface-variant px-4 py-2 hover:bg-surface-container-high rounded-lg transition-all">
            <span className="material-symbols-outlined text-sm">folder_shared</span>
            <span className="font-body-sm text-body-sm">Global Intelligence</span>
          </button>
          <button className="w-full text-left flex items-center gap-sm text-on-surface-variant px-4 py-2 hover:bg-surface-container-high rounded-lg transition-all">
            <span className="material-symbols-outlined text-sm">library_books</span>
            <span className="font-body-sm text-body-sm">Legal Archive</span>
          </button>
        </div>

        {/* Upload Zone */}
        <div className="pt-lg">
          <FileDropzone
            onUpload={onUpload}
            uploadState={uploadState}
            fileName={uploadedFileName}
            strategyTier={strategyTier}
          />
        </div>
      </nav>

      {/* Bottom Links */}
      <div className="px-md mt-auto pt-lg border-t border-outline-variant/20">
        <Link
          href="#"
          className="flex items-center gap-sm text-on-surface-variant px-4 py-2 hover:bg-surface-container-high transition-all rounded-lg mb-1"
        >
          <span className="material-symbols-outlined">settings</span>
          <span className="font-label-md text-label-md">Settings</span>
        </Link>
        <Link
          href="#"
          className="flex items-center gap-sm text-on-surface-variant px-4 py-2 hover:bg-surface-container-high transition-all rounded-lg"
        >
          <span className="material-symbols-outlined">help</span>
          <span className="font-label-md text-label-md">Support</span>
        </Link>
      </div>
    </aside>
  );
}
