"use client";

import { useState, useRef, useEffect } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import FileDropzone from "@/components/upload/FileDropzone";
import { useAuth } from "@/context/AuthContext";

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
  const { user, logout } = useAuth();
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const [activeModal, setActiveModal] = useState<"settings" | "support" | "info" | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const navItems = [
    { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
    { href: "/", label: "Home", icon: "home" },
  ];

  // Close menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsAccountMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <>
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
            className="w-full flex items-center justify-center gap-sm bg-primary text-white rounded-lg px-4 py-3 mb-lg hover:opacity-90 transition-all shadow-sm group cursor-pointer"
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
                  className={`w-full text-left flex items-center justify-between gap-xs px-4 py-2 rounded-lg transition-all text-ellipsis overflow-hidden whitespace-nowrap cursor-pointer ${
                    activeThreadId === thread.thread_id
                      ? "bg-primary/10 text-primary dark:bg-white/10 dark:text-white font-bold"
                      : "text-slate-700 dark:text-slate-300 hover:bg-slate-200/50 dark:hover:bg-white/5"
                  }`}
                  title={thread.document_info ? `Attached PDF: ${thread.document_info.file_name}` : undefined}
                >
                  <div className="flex items-center gap-sm truncate min-w-0">
                    <span className="material-symbols-outlined text-sm shrink-0">chat_bubble</span>
                    <span className="font-body-sm text-body-sm truncate">{thread.title}</span>
                  </div>
                  {thread.document_info && (
                    <span className="material-symbols-outlined text-[14px] text-primary shrink-0" title={`Attached PDF: ${thread.document_info.file_name}`}>
                      description
                    </span>
                  )}
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

        {/* Bottom Interactive Account Section */}
        <div className="px-md mt-auto pt-md border-t border-slate-200 dark:border-slate-800 relative" ref={menuRef}>
          {/* Upward Account Menu Popover */}
          {isAccountMenuOpen && (
            <div className="absolute bottom-full left-3 right-3 mb-2 bg-white dark:bg-[#0c1021] border border-slate-200 dark:border-slate-800 rounded-2xl p-3 shadow-2xl z-50 fade-in space-y-1">
              {/* Account Info Header */}
              {user && (
                <div className="px-3 py-2 border-b border-slate-100 dark:border-slate-800 mb-1">
                  <p className="text-xs font-semibold text-slate-900 dark:text-white truncate">{user.email}</p>
                  <p className="text-[10px] text-slate-400 dark:text-slate-500">DocMind Enterprise Account</p>
                </div>
              )}

              {/* Info Option */}
              <button
                onClick={() => { setActiveModal("info"); setIsAccountMenuOpen(false); }}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/60 rounded-xl transition-colors text-left cursor-pointer"
              >
                <span className="material-symbols-outlined text-[18px]">info</span>
                <span>Account Info</span>
              </button>

              {/* Settings Option */}
              <button
                onClick={() => { setActiveModal("settings"); setIsAccountMenuOpen(false); }}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/60 rounded-xl transition-colors text-left cursor-pointer"
              >
                <span className="material-symbols-outlined text-[18px]">settings</span>
                <span>Settings</span>
              </button>

              {/* Support Option */}
              <button
                onClick={() => { setActiveModal("support"); setIsAccountMenuOpen(false); }}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/60 rounded-xl transition-colors text-left cursor-pointer"
              >
                <span className="material-symbols-outlined text-[18px]">help</span>
                <span>Support &amp; Docs</span>
              </button>

              <div className="border-t border-slate-100 dark:border-slate-800 pt-1 mt-1">
                {/* Sign Out Option */}
                <button
                  onClick={logout}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 rounded-xl transition-colors text-left cursor-pointer"
                >
                  <span className="material-symbols-outlined text-[18px]">logout</span>
                  <span>Sign Out</span>
                </button>
              </div>
            </div>
          )}

          {/* Account Button Card */}
          {user && (
            <button
              onClick={() => setIsAccountMenuOpen((prev) => !prev)}
              className={`w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-xl transition-all border cursor-pointer ${
                isAccountMenuOpen
                  ? "bg-slate-200/80 dark:bg-white/10 border-primary/40 shadow-sm"
                  : "bg-slate-100/70 dark:bg-white/5 border-slate-200 dark:border-slate-800 hover:bg-slate-200/50 dark:hover:bg-white/10"
              }`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-primary to-blue-500 text-white font-bold text-xs flex items-center justify-center shrink-0">
                  {user.email.charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0 text-left">
                  <p className="text-xs font-semibold text-slate-900 dark:text-white truncate max-w-[130px]" title={user.email}>
                    {user.email}
                  </p>
                  <p className="text-[10px] text-slate-500 dark:text-slate-400">Manage Account</p>
                </div>
              </div>
              <span className={`material-symbols-outlined text-slate-400 transition-transform ${isAccountMenuOpen ? "rotate-180" : ""}`}>
                expand_less
              </span>
            </button>
          )}
        </div>
      </aside>

      {/* Interactive Account Modals */}
      {activeModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-[#0c1021] border border-slate-200 dark:border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 fade-in">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary">
                  {activeModal === "settings" ? "settings" : activeModal === "support" ? "help" : "info"}
                </span>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white capitalize">
                  {activeModal === "settings" ? "Account Settings" : activeModal === "support" ? "Support & Assistance" : "Account Information"}
                </h3>
              </div>
              <button
                onClick={() => setActiveModal(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-white transition-colors"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            {activeModal === "info" && (
              <div className="space-y-3 text-sm text-slate-700 dark:text-slate-300">
                <div>
                  <label className="text-xs uppercase text-slate-400 font-semibold block">Email Address</label>
                  <p className="font-medium text-slate-900 dark:text-white">{user?.email}</p>
                </div>
                <div>
                  <label className="text-xs uppercase text-slate-400 font-semibold block">Account ID</label>
                  <p className="font-mono text-xs text-slate-500">{user?.id}</p>
                </div>
                <div>
                  <label className="text-xs uppercase text-slate-400 font-semibold block">Status</label>
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-500/10 text-green-600 dark:text-green-400 border border-green-500/20 mt-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span> Active Enterprise User
                  </span>
                </div>
              </div>
            )}

            {activeModal === "settings" && (
              <div className="space-y-3 text-sm text-slate-700 dark:text-slate-300">
                <p className="text-xs text-slate-500">Manage your LLM preferences and pipeline parameters.</p>
                <div className="p-3 bg-slate-50 dark:bg-slate-900/50 rounded-xl space-y-2 border border-slate-200 dark:border-slate-800">
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 block">Default LLM Model</label>
                  <p className="text-xs text-slate-500">GPT-4o / Gemini Flash (Configured via API)</p>
                </div>
                <div className="p-3 bg-slate-50 dark:bg-slate-900/50 rounded-xl space-y-2 border border-slate-200 dark:border-slate-800">
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 block">Zero-Trust Verification</label>
                  <p className="text-xs text-slate-500">Audit Mode enabled for spatial citations</p>
                </div>
              </div>
            )}

            {activeModal === "support" && (
              <div className="space-y-3 text-sm text-slate-700 dark:text-slate-300">
                <p className="text-xs text-slate-500">Need help or documentation for the DocMind Refinery?</p>
                <div className="space-y-2">
                  <a
                    href="https://github.com/Heban-7/DocMind"
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-900/50 hover:bg-slate-100 dark:hover:bg-slate-800/80 rounded-xl border border-slate-200 dark:border-slate-800 transition-colors"
                  >
                    <span className="font-medium text-slate-900 dark:text-white">GitHub Documentation</span>
                    <span className="material-symbols-outlined text-sm">open_in_new</span>
                  </a>
                  <a
                    href="/contact"
                    className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-900/50 hover:bg-slate-100 dark:hover:bg-slate-800/80 rounded-xl border border-slate-200 dark:border-slate-800 transition-colors"
                  >
                    <span className="font-medium text-slate-900 dark:text-white">Contact Enterprise Support</span>
                    <span className="material-symbols-outlined text-sm">mail</span>
                  </a>
                </div>
              </div>
            )}

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setActiveModal(null)}
                className="bg-primary text-white text-xs font-bold px-4 py-2 rounded-xl hover:opacity-90 transition-opacity"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
