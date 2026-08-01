"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import FileDropzone from "@/components/upload/FileDropzone";

import type { ThreadSummary } from "@/lib/types";

interface SidebarProps {
  onNewChat: () => void;
  threads?: ThreadSummary[];
  activeThreadId?: string;
  onSelectThread?: (threadId: string) => void;
  onUpload: (file: File) => void;
  uploadState: string;
  uploadedFileName?: string;
  strategyTier?: string;
}

export default function DashboardSidebar({
  onNewChat,
  threads = [],
  activeThreadId,
  onSelectThread,
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

  return (
    <aside className="fixed left-0 top-0 h-screen hidden md:flex flex-col py-lg w-[280px] bg-slate-50 dark:bg-[#0c1021] border-r border-slate-200 dark:border-slate-800 z-40 text-slate-900 dark:text-white transition-colors">
      <Link href="/" className="px-lg mb-xl flex items-center gap-sm hover:opacity-80 transition-opacity group" title="Return to Home Page">
        <Image
          src="/logo.jpg"
          alt="DocMind Logo"
          width={36}
          height={36}
          className="w-9 h-9 rounded-lg object-cover shadow-sm"
        />
        <div>
          <h1 className="font-headline-md text-headline-md font-bold text-slate-900 dark:text-white group-hover:text-primary transition-colors">
            DocMind AI
          </h1>
          <p className="font-body-sm text-xs text-slate-500 dark:text-slate-400">
            Enterprise Intelligence
          </p>
        </div>
      </Link>


      <nav className="flex-1 px-md space-y-xs overflow-y-auto">
        {/* New Chat Button */}
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-sm bg-primary text-white rounded-lg px-4 py-3 mb-lg hover:opacity-90 transition-all shadow-sm group"
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
                ? "bg-primary/10 text-primary dark:bg-white/10 dark:text-white font-bold translate-x-1"
                : "text-slate-700 dark:text-slate-300 hover:bg-slate-200/50 dark:hover:bg-white/5"
            }`}
          >
            <span className="material-symbols-outlined">{item.icon}</span>
            <span className="font-label-md text-label-md">{item.label}</span>
          </Link>
        ))}

        {/* Chat History */}
        <div className="pt-xl pb-sm">
          <span className="px-4 font-label-md text-label-md text-slate-400 dark:text-slate-500 uppercase tracking-wider">
            Chat
          </span>
        </div>
        <div className="space-y-xs">
          {threads.length === 0 ? (
            <p className="px-4 py-2 text-xs text-slate-400 dark:text-slate-500 italic">
              No previous threads
            </p>
          ) : (
            threads.map((thread) => (
              <button
                key={thread.thread_id}
                onClick={() => onSelectThread?.(thread.thread_id)}
                className={`w-full text-left flex items-center gap-sm px-4 py-2 rounded-lg transition-all text-ellipsis overflow-hidden whitespace-nowrap ${
                  activeThreadId === thread.thread_id
                    ? "bg-primary/10 text-primary dark:bg-white/10 dark:text-white font-bold"
                    : "text-slate-700 dark:text-slate-300 hover:bg-slate-200/50 dark:hover:bg-white/5"
                }`}
              >
                <span className="material-symbols-outlined text-sm">chat_bubble</span>
                <span className="font-body-sm text-body-sm truncate">{thread.title}</span>
              </button>
            ))
          )}
        </div>

        {/* Upload Zone */}
        <div className="pt-lg">
          <FileDropzone
            onUpload={onUpload}
            uploadState={uploadState}
          />
        </div>
      </nav>

      {/* Bottom Links */}
      <div className="px-md mt-auto pt-lg border-t border-slate-200 dark:border-slate-800">
        <Link
          href="#"
          className="flex items-center gap-sm text-slate-700 dark:text-slate-300 px-4 py-2 hover:bg-slate-200/50 dark:hover:bg-white/5 transition-all rounded-lg mb-1"
        >
          <span className="material-symbols-outlined">settings</span>
          <span className="font-label-md text-label-md">Settings</span>
        </Link>
        <Link
          href="#"
          className="flex items-center gap-sm text-slate-700 dark:text-slate-300 px-4 py-2 hover:bg-slate-200/50 dark:hover:bg-white/5 transition-all rounded-lg"
        >
          <span className="material-symbols-outlined">help</span>
          <span className="font-label-md text-label-md">Support</span>
        </Link>
      </div>
    </aside>

  );
}
