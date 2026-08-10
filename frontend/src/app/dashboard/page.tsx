"use client";

import { useRef, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import DashboardSidebar from "@/components/layout/DashboardSidebar";
import DashboardHeader from "@/components/layout/DashboardHeader";
import ChatMessage from "@/components/chat/ChatMessage";
import ChatInput from "@/components/chat/ChatInput";
import WelcomeState from "@/components/chat/WelcomeState";
import { useChat } from "@/hooks/useChat";
import { useUpload } from "@/hooks/useUpload";
import { useThreads } from "@/hooks/useThreads";
import { useAuth } from "@/context/AuthContext";

import ProcessingProgressMessage from "@/components/chat/ProcessingProgressMessage";

export default function DashboardPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  // All custom hooks called unconditionally at top level
  const { messages, isLoading, error: chatError, threadId, activeDocId, send, loadThread, newChat } = useChat();
  const { uploadState, uploadingThreadId, selectedFile, error: uploadError, upload, getThreadDocument, setThreadDocument } = useUpload();
  const { threads, refresh: refreshThreads } = useThreads();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [federatedSearch, setFederatedSearch] = useState(false);
  const [auditMode, setAuditMode] = useState(false);
  const [selectedModel, setSelectedModel] = useState("gpt-4o");
  const [activeError, setActiveError] = useState<string | null>(null);

  // Auth guard: redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.replace("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  // Strictly resolve document ONLY for this exact thread
  const activeDoc = getThreadDocument(threadId);
  const isCurrentThreadUploading = uploadingThreadId === threadId && uploadState !== "idle";

  // Sync errors to banner state
  useEffect(() => {
    if (chatError) setActiveError(chatError);
    else if (uploadError) setActiveError(uploadError);
  }, [chatError, uploadError]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, uploadState]);

  // Show loading while checking auth
  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-[#03050f]">
        <div className="flex items-center gap-3 text-slate-500 dark:text-slate-400">
          <span className="material-symbols-outlined animate-spin">progress_activity</span>
          <span className="text-sm font-medium">Verifying authentication...</span>
        </div>
      </div>
    );
  }

  const handleSend = async (text: string, modelOverride?: string) => {
    const targetModel = modelOverride || selectedModel;
    const currentDocId = activeDoc?.document_id || activeDocId;
    const isFederated = federatedSearch || !currentDocId;
    const targetDocId = isFederated ? undefined : currentDocId;
    await send(text, targetDocId, {
      federatedSearch: isFederated,
      auditMode,
      model: targetModel,
    });
    refreshThreads();
  };

  const handleUpload = async (file: File) => {
    const doc = await upload(file, threadId);
    if (doc) {
      setThreadDocument(threadId, doc);
    }
    refreshThreads();
  };

  const handleSelectThread = async (id: string) => {
    const res = await loadThread(id);
    if (res?.document_info) {
      setThreadDocument(id, res.document_info);
    }
  };

  return (
    <>
      {/* Sidebar */}
      <DashboardSidebar
        onNewChat={newChat}
        threads={threads}
        activeThreadId={threadId}
        onSelectThread={handleSelectThread}
        onUpload={handleUpload}
        uploadState={isCurrentThreadUploading ? uploadState : "idle"}
      />

      {/* Main Content Canvas */}
      <main className="flex-1 md:ml-[280px] h-screen flex flex-col bg-slate-50 dark:bg-[#03050f] text-slate-900 dark:text-white relative transition-colors">

        {/* Header */}
        <DashboardHeader
          federatedSearch={federatedSearch}
          onToggleFederated={() => {
            setFederatedSearch((prev) => {
              const next = !prev;
              if (next) setAuditMode(false);
              return next;
            });
          }}
          auditMode={auditMode}
          onToggleAudit={() => {
            setAuditMode((prev) => {
              const next = !prev;
              if (next) setFederatedSearch(false);
              return next;
            });
          }}
        />

        {/* Error Alert Banner */}
        {activeError && (
          <div className="bg-red-500/10 border-b border-red-500/30 text-red-700 px-lg py-sm flex items-center justify-between z-20 text-body-sm">
            <div className="flex items-center gap-sm">
              <span className="material-symbols-outlined text-[18px]">error</span>
              <span>{activeError}</span>
            </div>
            <button
              onClick={() => setActiveError(null)}
              className="hover:bg-red-500/20 p-1 rounded transition-colors"
            >
              <span className="material-symbols-outlined text-[16px]">close</span>
            </button>
          </div>
        )}

        {/* Chat Workspace Area */}
        <section ref={scrollRef} className="flex-1 overflow-y-auto flex flex-col items-center">
          <div className="w-full max-w-[800px] px-lg py-xl flex-1 flex flex-col">
            {/* Welcome State (shown when no messages, no upload in progress, and no document bound to this thread) */}
            {messages.length === 0 && !isCurrentThreadUploading && !activeDoc && (
              <WelcomeState onSuggestionClick={handleSend} />
            )}

            {/* Inline Document Processing Progress Card / Attached Document Banner */}
            {(isCurrentThreadUploading || activeDoc) && (
              <ProcessingProgressMessage
                fileName={activeDoc?.file_name || (isCurrentThreadUploading ? selectedFile?.name : null) || "Document.pdf"}
                fileSizeMb={selectedFile && isCurrentThreadUploading ? (selectedFile.size / (1024 * 1024)).toFixed(2) : null}
                uploadState={isCurrentThreadUploading ? uploadState : "indexed"}
                strategyTier={activeDoc?.strategy_tier}
              />
            )}

            {/* Chat Messages */}
            <div className="space-y-xl pb-32">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} selectedModel={selectedModel} />
              ))}
            </div>
          </div>
        </section>

        {/* Input Bar */}
        <ChatInput
          onSend={handleSend}
          isLoading={isLoading}
          onAttachFile={handleUpload}
          selectedModel={selectedModel}
          onSelectModel={setSelectedModel}
        />

        {/* Decorative Background Element */}
        <div className="fixed top-0 right-0 -z-10 w-1/3 h-1/3 opacity-20 pointer-events-none blur-[100px] bg-gradient-to-br from-primary to-secondary" />
      </main>
    </>
  );
}
