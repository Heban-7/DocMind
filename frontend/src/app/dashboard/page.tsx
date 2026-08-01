"use client";

import { useRef, useEffect, useState } from "react";
import DashboardSidebar from "@/components/layout/DashboardSidebar";
import DashboardHeader from "@/components/layout/DashboardHeader";
import ChatMessage from "@/components/chat/ChatMessage";
import ChatInput from "@/components/chat/ChatInput";
import WelcomeState from "@/components/chat/WelcomeState";
import { useChat } from "@/hooks/useChat";
import { useUpload } from "@/hooks/useUpload";
import { useThreads } from "@/hooks/useThreads";

import ProcessingProgressMessage from "@/components/chat/ProcessingProgressMessage";

export default function DashboardPage() {
  const { messages, isLoading, error: chatError, threadId, send, loadThread, newChat } = useChat();
  const { uploadState, document: uploadedDoc, selectedFile, error: uploadError, upload } = useUpload();
  const { threads, refresh: refreshThreads } = useThreads();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [federatedSearch, setFederatedSearch] = useState(false);
  const [auditMode, setAuditMode] = useState(false);
  const [selectedModel, setSelectedModel] = useState("gpt-4o");
  const [activeError, setActiveError] = useState<string | null>(null);

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

  const handleSend = async (text: string, modelOverride?: string) => {
    const targetModel = modelOverride || selectedModel;
    const isFederated = federatedSearch || !uploadedDoc?.document_id;
    const targetDocId = isFederated ? undefined : uploadedDoc?.document_id;
    await send(text, targetDocId, {
      federatedSearch: isFederated,
      auditMode,
      model: targetModel,
    });
    refreshThreads();
  };

  const handleUpload = async (file: File) => {
    await upload(file);
    refreshThreads();
  };

  return (
    <>
      {/* Sidebar */}
      <DashboardSidebar
        onNewChat={newChat}
        threads={threads}
        activeThreadId={threadId}
        onSelectThread={loadThread}
        onUpload={handleUpload}
        uploadState={uploadState}
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
            {/* Welcome State (shown when no messages and no upload in progress) */}
            {messages.length === 0 && uploadState === "idle" && (
              <WelcomeState onSuggestionClick={handleSend} />
            )}

            {/* Inline Document Processing Progress Card in Agent Response stream */}
            {uploadState !== "idle" && (
              <ProcessingProgressMessage
                fileName={uploadedDoc?.file_name || selectedFile?.name || "Document.pdf"}
                fileSizeMb={selectedFile ? (selectedFile.size / (1024 * 1024)).toFixed(2) : null}
                uploadState={uploadState}
                strategyTier={uploadedDoc?.strategy_tier}
              />
            )}

            {/* Chat Messages */}
            <div className="space-y-xl pb-32">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}

              {/* Loading Indicator */}
              {isLoading && (
                <div className="flex flex-col items-start fade-in">
                  <div className="max-w-[90%] space-y-md">
                    <div className="flex items-center gap-sm mb-xs">
                      <div className="w-6 h-6 bg-primary rounded flex items-center justify-center">
                        <span className="material-symbols-outlined text-white text-[16px]">
                          auto_awesome
                        </span>
                      </div>
                      <span className="font-label-md text-label-md font-bold text-primary">
                        DocMind AI ({selectedModel})
                      </span>
                    </div>
                    <div className="flex items-center gap-sm text-on-surface-variant/50">
                      <span className="material-symbols-outlined text-sm animate-spin">
                        progress_activity
                      </span>
                      <span className="font-body-sm text-body-sm">Analyzing documents...</span>
                    </div>
                  </div>
                </div>
              )}
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



